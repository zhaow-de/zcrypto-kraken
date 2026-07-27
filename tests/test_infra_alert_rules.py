"""Guard: `infra/grafana/alerts.yaml` is pushed to Grafana Cloud's provisioning API by
`infra/scripts/grafana-push.sh`, and the API rejects a malformed rule with a bare HTTP 400 whose
body the script discards. That failure mode is expensive out of proportion to its cause: it needs a
vaulted token and a TTY for the GPG pinentry, so it can only be discovered during an attended push,
and the operator sees `curl: (22) ... error: 400` with no indication of which rule or which field.

Every constraint pinned here is one the API enforces silently and the repo previously did not. The
40-char UID limit cost a full attended round-trip on 2026-07-20 (a 41-char uid); note that the
longest surviving uid is exactly 40, so the ceiling is real and routinely approached."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Grafana's alert-rule UID column is `varchar(40)`, and the provisioning API's OpenAPI spec declares
# `maxLength: 40`. A uid is IMMUTABLE once the rule exists, so an update never carries a new uid --
# the length is therefore only ever tested at creation, and a too-long uid breaks exactly once, on
# the run that first introduces it, which is when the diagnosis is hardest. (It is not that updates
# skip a validation: they simply never present a fresh uid to validate.)
_UID_MAX = 40

# The provisioning API's enums. A value outside these is a 400, not a validation message.
_NO_DATA_STATES = {"Alerting", "NoData", "OK"}
_EXEC_ERR_STATES = {"Alerting", "Error", "OK"}


def _rules():
    return yaml.safe_load(ALERTS.read_text())["rules"]


def test_alert_rule_uids_fit_grafanas_column():
    over = [(r["uid"], len(r["uid"])) for r in _rules() if len(r["uid"]) > _UID_MAX]
    assert not over, f"uid longer than Grafana's {_UID_MAX}-char limit -- the create call will 400: {over}"


def test_alert_rule_uids_are_unique():
    uids = [r["uid"] for r in _rules()]
    dupes = sorted({u for u in uids if uids.count(u) > 1})
    assert not dupes, f"duplicate uid -- the second push silently overwrites the first: {dupes}"


@pytest.mark.parametrize("field,allowed", [("noDataState", _NO_DATA_STATES), ("execErrState", _EXEC_ERR_STATES)])
def test_alert_rule_states_are_valid_enums(field, allowed):
    bad = [(r["uid"], r.get(field)) for r in _rules() if r.get(field) not in allowed]
    assert not bad, f"{field} outside the API's enum {sorted(allowed)}: {bad}"


def test_every_rule_has_the_fields_the_api_requires():
    # Omitting any of these is a 400. `condition` must also name a refId that exists in `data`,
    # which the API checks but does not explain.
    required = ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "ruleGroup", "folderUID")
    problems = []
    for r in _rules():
        missing = [f for f in required if f not in r]
        if missing:
            problems.append((r.get("uid", "<no uid>"), f"missing {missing}"))
            continue
        refids = {d.get("refId") for d in r["data"]}
        if r["condition"] not in refids:
            problems.append((r["uid"], f"condition {r['condition']!r} not among data refIds {sorted(refids)}"))
    assert not problems, f"rules the provisioning API would reject: {problems}"


def test_datasource_uids_are_templated_not_hardcoded():
    # grafana-push.sh substitutes ${GRAFANA_*_DS_UID} at push time. A hardcoded uid silently
    # repoints a rule at another datasource -- the API accepts it and reports health=ok (T0034),
    # so the push-time read-back is the only other thing that would catch it.
    allowed = {"${GRAFANA_PROM_DS_UID}", "${GRAFANA_LOKI_DS_UID}", "__expr__"}
    bad = [(r["uid"], d.get("datasourceUid")) for r in _rules() for d in r["data"] if d.get("datasourceUid") not in allowed]
    assert not bad, f"datasourceUid neither templated nor the expression node: {bad}"


# --- A shipped metric that nothing watches ------------------------------------------------------
# T0008's content, generalized. Spec 00069 shipped `zcrypto_capture_book_desynced` and
# `zcrypto_capture_resubscribes_total`, both scraped and live on both hosts, and for two months no
# alert rule mentioned either -- the topic's own trigger was measurable but unwatched. The same gap
# hid T0100 (a producer shipping into a transport nobody reads) and, found by the review of this
# very commit, `zcrypto_capture_disk_watermark_breached` -- whose breach makes the daemon DISCARD
# unbackfillable L2.
#
# `test_infra_alloy_series.py` proves a metric REACHES Grafana; this proves something looks at it.
# Admitting a series and watching nothing is the more expensive half, and nothing else would
# surface it: the Grafana dashboard carries no `zcrypto_capture_*` or `zcrypto_engine_*` panel at
# all, so an unwatched app metric is invisible everywhere.
#
# The candidate set is DERIVED from the capture keep-regex, not hand-listed. A hand-list cannot
# catch the next unwatched metric, which is precisely the mechanism that let these sit for months:
# a new fault gauge added to the keep-regex tomorrow would be invisible to a fixed list. Every
# admitted series is therefore a candidate until explicitly excluded below, so omitting one is a
# conscious act with a written reason rather than an oversight.
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"


def _admitted_series() -> list[str]:
    """Every metric name the capture hosts' keep-regex admits to remote_write."""
    line = next(ln for ln in CAPTURE_ALLOY.read_text().splitlines() if "regex" in ln and "node_load1" in ln)
    return line.split('"')[1].split("|")


# Not fault signals: context you read once something ELSE has paged, or state whose meaning is a
# level rather than an event. Each exclusion states why, because an unexamined exclusion is how the
# original defect would grow back.
NOT_A_FAULT_SIGNAL = {
    # Capacity/utilisation context. Read while diagnosing; alerting on them directly is noise, and
    # the conditions that matter already have their own rules (disk-low, load-high).
    "up",
    "node_load1",
    "node_load5",
    "node_load15",
    "node_memory_MemTotal_bytes",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemFree_bytes",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    "node_filesystem_free_bytes",
    "node_network_receive_bytes_total",
    "node_network_transmit_bytes_total",
    "node_cpu_seconds_total",
    "node_scrape_collector_duration_seconds",
    "node_textfile_mtime_seconds",  # the staleness INPUT; the rules keyed on it are the signal
    # Throughput counters -- healthy when RISING. Their failure mode is going flat, which the
    # dead-man and the log-dead rules already own.
    "zcrypto_capture_segments_written_total",
    "zcrypto_capture_segment_bytes_total",
    "zcrypto_capture_rows_held_total",
    "zcrypto_logship_shipped_lines_total",
    "zcrypto_logship_last_success_timestamp_seconds",
    # Reconnects run 32-35/week per host (measured 2026-07-26): that is BASELINE, not a fault, so a
    # naive threshold here is pure alarm fatigue. T0035's trigger is a reconnect counter RESET
    # alongside a process_start_time_seconds jump (a crash-restart), which needs the correlation,
    # not a raw count -- it stays that topic's work.
    "zcrypto_capture_reconnects_total",
    # Cumulative gap seconds. BOTH of this exclusion's original grounds were falsified on 2026-07-27
    # (T0101) and are rewritten rather than left standing, because as written they argue against the
    # fix. It said the metric measured zero across all 24 series -- that ZERO WAS THE BLIND SPOT: the
    # daemon booked nothing through a total 12-pair blackout on both hosts. And it said an open gap
    # is covered twice over by the dead-man and the desync rule -- NEITHER saw it, because
    # `is_healthy()` consults open gap windows and a connected-but-silent stream opened none.
    # Spec 00073 makes the silence observable; alerting on it is deliberately deferred to T0105,
    # since an unfitted threshold in `is_healthy()` darkens the dead-man fleet-wide on both hosts.
    "zcrypto_capture_gap_seconds_total",
    # Seconds since the last book message (spec 00073 D4): the proof-it-runs gauge for the staleness
    # watchdog. Excluded on purpose -- it exists to be READ so T0105 can fit a paging threshold to a
    # real production distribution; a rule on it before that fitting is the guess this defers.
    "zcrypto_capture_seconds_since_last_book_message",
    # Engine cycle health -- registered under T0095 with `ripe_when: the dashboards/alerting design
    # iteration`. Named here so its absence is a decision, not an oversight.
    "zcrypto_engine_cycle_success",
    "zcrypto_engine_cycle_completed_at_seconds",
    "zcrypto_engine_cycle_duration_seconds",
    "zcrypto_engine_target_weight",
    "zcrypto_engine_orders_total",
    "zcrypto_engine_order_notional_eur",
    # Process self-metrics: diagnostic context, no fault semantics of their own.
    "process_cpu_seconds_total",
    "process_max_fds",
    "process_open_fds",
    "process_resident_memory_bytes",
    "process_start_time_seconds",
    "process_virtual_memory_bytes",
    # Prune bookkeeping -- the fault is the timer STOPPING, which the staleness rules own.
    "zcrypto_engine_journal_prune_deleted_days",
    "zcrypto_engine_journal_prune_kept_days",
    "zcrypto_engine_journal_prune_oldest_day_age_seconds",
    "zcrypto_engine_journal_prune_last_run_timestamp_seconds",
}

FAULT_SIGNAL_METRICS = sorted(set(_admitted_series()) - NOT_A_FAULT_SIGNAL)


def test_the_exclusion_list_has_not_gone_stale():
    """Every exclusion must name a series the keep-regex still admits — otherwise a rename leaves a
    dead entry silently excusing nothing, and the metric it was renamed to is unguarded."""
    stale = NOT_A_FAULT_SIGNAL - set(_admitted_series())
    assert not stale, f"excluded but no longer admitted (rename? removal?): {sorted(stale)}"


@pytest.mark.parametrize("metric", FAULT_SIGNAL_METRICS)
def test_every_fault_signal_metric_is_watched_by_a_rule(metric):
    """A fault signal nobody alerts on is a metric that renders green while the fault is live."""
    # Word-boundary, not substring: `node_load1` is a strict prefix of `node_load15` (both admitted),
    # so a plain `in` lets a node_load15 rule satisfy a node_load1 entry. Same for
    # process_virtual_memory_bytes / _max_bytes.
    pattern = re.compile(rf"\b{re.escape(metric)}\b(?!_)")
    watching = [
        r["uid"] for r in _rules() if any(pattern.search(str(q.get("model", {}).get("expr", ""))) for q in r.get("data", []))
    ]
    assert watching, (
        f"{metric} is admitted to the capture keep-list but no alert rule queries it — nothing "
        f"would surface it, since no dashboard panel carries the app-metric families either. Add a "
        f"rule, or add it to NOT_A_FAULT_SIGNAL with the reason."
    )
