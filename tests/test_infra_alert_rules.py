"""Guard: `infra/scripts/grafana-push.sh` pushes `infra/grafana/alerts.yaml` to Grafana Cloud's
provisioning API, which rejects a malformed rule with a bare HTTP 400 whose body the script
discards -- a failure only an attended push can reach, and one that names neither rule nor field."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Grafana's alert-rule UID column is `varchar(40)`, and the provisioning API's OpenAPI spec declares
# `maxLength: 40`. A uid is IMMUTABLE once the rule exists, so an update never carries a new uid --
# the length is therefore only ever tested at creation, and a too-long uid breaks exactly once, on
# the run that first introduces it, which is when the diagnosis is hardest.
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


# --- A dead-man that cannot announce its own recovery -------------------------------------------
# `grafana-push.sh` mints two Slack contact points against the SAME webhook and channel, differing
# in one property: `logs` sets `disableResolveMessage: true`, `metrics` does not. Suppressing the
# resolve is right for a burst rule -- a flurry of ERROR lines ages out of its own window (T0047) --
# and wrong for a dead-man, where the clear IS the news.
#
# The two families are told apart structurally, never by a list of uids: a hand-list would admit
# the next dead-man added tomorrow, which is the mechanism this guard exists to close.
#
# The read is the THRESHOLD node's evaluator, so a comparison folded into a `math` node (`$B < 1`
# thresholded `gt 0`) is invisible to it; a dead-man written that way on `logs` would pass. Widen
# the classifier, never the receiver.
PUSH = REPO / "infra/scripts/grafana-push.sh"


def _receivers_suppressing_resolve() -> set[str]:
    """The receiver names `grafana-push.sh` mints with `disableResolveMessage: true`, read from the
    script rather than restated here: the flag and the pin live in different files, and this guard is
    only worth anything if it fails when EITHER of them moves."""
    calls = re.findall(r'upsert_slack_integration\s+"[^"]+"\s+"([^"]+)"\s+(true|false)', PUSH.read_text())
    assert calls, "no upsert_slack_integration calls in grafana-push.sh -- the receiver minting moved"
    return {name for name, disable in calls if disable == "true"}


def _fires_on_absence(rule) -> bool:
    """True when the rule pages because a measured value fell BELOW its threshold -- every dead-man
    here, and every disk or staleness rule that says "too little of something"."""
    return any(
        cond.get("evaluator", {}).get("type") == "lt"
        for node in rule["data"]
        for cond in (node.get("model", {}).get("conditions") or [])
    )


def test_a_rule_that_fires_on_absence_can_notify_its_clear():
    """A rule that fires on ABSENCE must not sit on a receiver that suppresses resolved notices --
    the receiver is the whole difference between a clear that reaches the channel and one that
    never arrives."""
    suppressed = _receivers_suppressing_resolve()
    mute = [
        (r["uid"], (r.get("notification_settings") or {}).get("receiver"))
        for r in _rules()
        if _fires_on_absence(r) and (r.get("notification_settings") or {}).get("receiver") in suppressed
    ]
    assert not mute, (
        "these rules page on absence but pin a receiver that suppresses the resolve, so an operator "
        f"is never told the condition ended: {mute}"
    )


def test_a_burst_rule_keeps_the_receiver_that_suppresses_its_resolve():
    """The over-correction guard, and the true positive for the test above: moving the whole Loki
    family onto `metrics` would clear the dead-men by re-introducing exactly the noise T0047
    removed. The ERROR-log rules fire on `gt` and stay where they are."""
    suppressed = _receivers_suppressing_resolve()
    burst = [
        r["uid"]
        for r in _rules()
        if not _fires_on_absence(r) and (r.get("notification_settings") or {}).get("receiver") in suppressed
    ]
    assert burst, (
        "no rule pins a resolve-suppressing receiver any more -- if that was deliberate, "
        "grafana-push.sh should stop minting one; T0047 put the ERROR-log rules there"
    )


# --- notification_settings must survive the payload the push actually sends ----------------------
# The script's rule payload is built by one jq program; this runs THAT program rather than a copy of
# it, so a projection or a `del` added there fails here instead of silently defaulting a field on the
# next attended push. The datasource half is read back live by the script itself (T0034).
_RULE_PAYLOAD_JQ = re.compile(r"rule_payload=\$\(jq\b.*?'(.*?)'\s*<<<\"\$\{rules_json\}\"", re.S)


def _pushed_payload(program: str, rules_json: str, uid: str) -> dict:
    """One rule's PUT body, produced by `grafana-push.sh`'s own jq program under placeholder values
    that cannot collide with anything in the file."""
    proc = subprocess.run(
        ["jq", "--arg", "uid", uid, "--arg", "prom", "P", "--arg", "loki", "L", "--arg", "folder", "F", program],
        input=rules_json,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"the push's jq program failed on {uid}: {proc.stderr}"
    return json.loads(proc.stdout)


def test_notification_settings_survive_the_payload_the_push_sends():
    """`repeat_interval` is set by exactly one rule, so a payload step that dropped or defaulted it
    would cost that rule its re-notify interval and leave every other rule's block intact -- nothing
    on any surface would say so. The block is compared whole, and it carries no `${...}` placeholder,
    so equality is exact rather than a re-implementation of the script's substitution."""
    if shutil.which("jq") is None:  # pragma: no cover - jq is present wherever grafana-push.sh runs
        pytest.skip("jq not available, so the push's own payload program cannot be run")
    program = _RULE_PAYLOAD_JQ.search(PUSH.read_text())
    assert program, "grafana-push.sh no longer builds its rule payload with a jq program this test can run"
    jq_program = program.group(1)
    # config-selector-ok: confirming the regex caught the right program, not selecting a value out of it
    assert "select(.uid == $uid)" in jq_program, f"the extracted program is not the per-rule payload builder: {jq_program!r}"

    rules = _rules()
    rules_json = json.dumps(rules)
    configured = {r["uid"]: r["notification_settings"] for r in rules if "notification_settings" in r}
    assert configured, "no rule sets notification_settings -- this guard would pass vacuously"
    repeating = sorted(uid for uid, ns in configured.items() if "repeat_interval" in ns)
    assert repeating, (
        "no rule sets a non-default repeat_interval, so this guard can no longer see the field it "
        "exists for -- a payload dropping only repeat_interval would pass it"
    )

    dropped = {
        uid: (_pushed_payload(jq_program, rules_json, uid).get("notification_settings"), settings)
        for uid, settings in configured.items()
    }
    dropped = {uid: pair for uid, pair in dropped.items() if pair[0] != pair[1]}
    assert not dropped, (
        f"the payload grafana-push.sh sends does not carry the notification_settings the file "
        f"declares (uid: sent, declared): {dropped}"
    )


# --- A shipped metric that nothing watches ------------------------------------------------------
# `test_infra_alloy_series.py` proves a metric REACHES Grafana; this proves something looks at it
# (T0008, T0100). The candidate set is DERIVED, never hand-listed, from the two sources that name
# series one by one -- the capture hosts' keep-regex and the nightly sweep runner's `# TYPE` lines;
# the ops keep-regex admits that family by wildcard, which names nothing. Every candidate is a fault
# signal until excluded below with a written reason.
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"
VERIFY_REPLAY_RUNNER = REPO / "infra/ansible/roles/ops/templates/verify-replay.sh.j2"


def _admitted_series() -> list[str]:
    """Every metric name the capture hosts' keep-regex admits to remote_write."""
    line = next(ln for ln in CAPTURE_ALLOY.read_text().splitlines() if ln.strip().startswith("regex") and "node_load1" in ln)
    return line.split('"')[1].split("|")


def _verify_replay_series() -> list[str]:
    """Every metric name the nightly sweep's runner publishes to its textfile: the `# TYPE` lines,
    checked against the `# HELP` lines so a printf that lost one fails here instead of silently
    dropping a candidate."""
    text = VERIFY_REPLAY_RUNNER.read_text()
    typed = re.findall(r"^\s*printf '# TYPE (ops_verify_replay_\w+) ", text, re.M)
    helped = re.findall(r"^\s*printf '# HELP (ops_verify_replay_\w+) ", text, re.M)
    assert typed and sorted(typed) == sorted(helped), f"TYPE/HELP lines disagree: {sorted(set(typed) ^ set(helped))}"
    return typed


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
    # Cumulative gap seconds. No rule reads THIS counter and none is owed: the paging half is on
    # `zcrypto_capture_seconds_since_last_book_message`, which never touches
    # `gap_monitor.is_healthy()` -- so a bad bar there costs a false page rather than darkening the
    # dead-man fleet-wide.
    "zcrypto_capture_gap_seconds_total",
    # Engine intent and execution LEVELS, plus the cycle's own duration. Every value any of them can
    # take is legitimate -- a weight that moved, an order that was placed, a cycle that ran long --
    # so no threshold on them means anything; they are the detail read once something else has paged.
    "zcrypto_engine_cycle_duration_seconds",
    "zcrypto_engine_target_weight",
    "zcrypto_engine_orders_total",
    "zcrypto_engine_order_notional_eur",
    # Per-sleeve gross: a LEVEL whose every value is legitimate -- a long-only sleeve flat through a
    # downtrend is correct behaviour -- so no threshold on it means anything. The event worth paging
    # on is the active-sleeve COUNT stepping, which zcrypto-engine-sleeve-count-changed owns.
    "zcrypto_engine_sleeve_gross",
    # Process self-metrics: diagnostic context, no fault semantics of their own.
    "process_cpu_seconds_total",
    "process_max_fds",
    "process_open_fds",
    "process_virtual_memory_bytes",
    # Prune bookkeeping -- LEVELS whose every value is legitimate. The fault is the run STOPPING, and
    # `zcrypto-engine-journal-prune-dead` reads the one gauge that says whether it did, so these
    # three are the detail read once it has paged.
    "zcrypto_engine_journal_prune_deleted_days",
    "zcrypto_engine_journal_prune_kept_days",
    "zcrypto_engine_journal_prune_oldest_day_age_seconds",
    # The execution safety envelope's unwatched families; armed, kill_tripped and
    # last_evaluation_timestamp_seconds are watched, and this list is what keeps that true.
    #   gate_level is the SUMMARY its inputs (armed, kill switch, restart hold, venue) already reduce
    #   to -- every value is legitimate depending on which input is active -- and the two worth
    #   paging on have their own rules.
    "zcrypto_exec_gate_level",
    # A LEVEL, not an event: HELD is the expected reading immediately after every restart and
    # self-clears only by a human decision, so no duration or presence threshold on it means
    # anything the two arming/kill rules do not already cover more precisely.
    "zcrypto_exec_restart_hold",
    # A gating INPUT, not the venue alert itself: the underlying condition already pages from the
    # capture side via zcrypto-capture-venue-not-online, which reads the daemon's own
    # zcrypto_capture_venue_status_total, so a second rule on this engine-side cached copy would
    # double-page the same event. The divergence that rule cannot see -- an engine-side REST read
    # failing CLOSED parks this gauge at 0 while the venue is online -- is a deferred alert in
    # docs/open-topics/T0018-phase6-build-sequence.md.
    "zcrypto_exec_venue_ok",
    # The execution instruments (spec 00090 D12). Attended-window instruments: arming is episodic, so
    # between windows these are legitimately flat and any rule on them is alarm fatigue, while inside
    # a window an operator is on the board; the two states that OUTLIVE a window already page
    # (zcrypto-engine-exec-kill-tripped, zcrypto-engine-exec-armed-too-long).
    "zcrypto_exec_orders_total",
    "zcrypto_exec_fills_total",
    "zcrypto_exec_fees_eur_total",
    # `zcrypto_exec_position` keeps its exclusion for its BARE VALUE, which stays no fault at any
    # level -- but it is no longer unwatched: zcrypto-engine-dark-with-exposure pages on it non-zero
    # at last sight WITH the engine's scrape gone, a conjunction the attended-window reasoning above
    # does not cover, since nobody is watching the board when the engine is the thing that left.
    "zcrypto_exec_position",
    "zcrypto_exec_realized_pnl_eur",
    # The resting order's age. NO rule, deliberately and not by omission (spec 00108 D7, which
    # records the rule it declines and why): a threshold above the `timebox_at` cap can never be
    # crossed and one below it fires on every lawful hold, and the condition a rule would be FOR --
    # an order resting at the venue with nothing tracking it -- is exactly where this gauge reads 0.
    "zcrypto_exec_resting_order_age_seconds",
    # The external-events counter is a forensic instrument: `matched` rising is a restart-adopted
    # order filling, and `unmatched` says an order event no entry in this engine's ledger vouches for
    # arrived and was acted on nowhere. NO rule, deliberately and not by omission: the candidate --
    # `unmatched` rising while `zcrypto_exec_armed` is 0 -- is unsound, because `zcrypto_exec_armed`
    # is published only when the gate is EVALUATED (engine start, then each 4-hourly cycle), so it is
    # a snapshot rather than an attendance signal and is stale in BOTH directions: loud during the
    # owner's own attended activity, mute through the hours after a window closes. What would make
    # the candidate work is one change: publish `zcrypto_exec_armed` on the executor's 5s tick --
    # engine code on the live trade path, so a decision of its own. The silent failure no rule could
    # catch either way -- an adopted order whose events fail to key into `_attached` -- is a
    # by-value reading in T0018.
    "zcrypto_exec_external_events_total",
    # The weekly tracking-error verdict. NO rule, deliberately and not by omission: the only value
    # that is a fault -- the band breached -- latches the kill file, which
    # zcrypto-engine-exec-kill-tripped already pages on; `not scored` is a refusal to decide and
    # `disarmed` is the resting state of an engine never given a band.
    "zcrypto_exec_tracking_state",
    # A level-shift detail read on the board: the §10 whole-book limits binding is the limits doing
    # their job, not a fault. What would be a fault -- the book they shape going somewhere it should
    # not -- is the intent-side gauges' business, not this counter's.
    "zcrypto_engine_limit_bound_total",
    # Venue-truth LEVELS (spec 00089 D6): loaded vs expected are the detail read once
    # zcrypto-venue-concordance-failed has already paged, not fault signals of their own -- the
    # failures count already reduces both into the one number that matters, and a threshold on
    # either directly would double-page the same event.
    "zcrypto_venue_instruments_loaded",
    "zcrypto_venue_instruments_expected",
    # The nightly canonical sweep's textfile (spec 00077, spec 00078): every way the sweep fails has
    # a rule -- failed_hours (new-breakage), run_ok (run-broken), pending_hours (backlog-stuck),
    # last_run_timestamp (stale) -- and the rest is what a responder reads once one has paged.
    #   exit_code: 1 on every run once any bad hour stands, so its rule paged daily (spec 00077 D1/D4).
    "ops_verify_replay_exit_code",
    #   last_success_timestamp: frozen while any bad hour stands (rc gates it, D5) -- a staleness rule
    #   on it would be the exit-code page in a third channel; the stale rule reads last_run_timestamp.
    "ops_verify_replay_last_success_timestamp",
    #   hours_total, replayed_hours: the census denominators, legitimate at every value.
    "ops_verify_replay_hours_total",
    "ops_verify_replay_replayed_hours",
    #   reused_hours, duration_seconds: a lost checkpoint reverts the sweep to a full rescan (reused
    #   near zero, duration long) while every rule reads healthy -- a human read on the ops host, not
    #   a rule (the owner's decision, T0167): a trend across nights, a step the backlog-stuck runbook names.
    "ops_verify_replay_reused_hours",
    "ops_verify_replay_duration_seconds",
    #   audit_mismatches: a discriminator, not a signal -- nonzero withholds the summary, so run-broken
    #   pages and its runbook reads this first to tell a cache disagreement from a crash.
    "ops_verify_replay_audit_mismatches",
}

_ADMITTED = frozenset(_admitted_series()) | frozenset(_verify_replay_series())
FAULT_SIGNAL_METRICS = sorted(_ADMITTED - NOT_A_FAULT_SIGNAL)


def test_the_exclusion_list_has_not_gone_stale():
    """Every exclusion must name a series the keep-regex still admits — otherwise a rename leaves a
    dead entry silently excusing nothing, and the metric it was renamed to is unguarded."""
    stale = NOT_A_FAULT_SIGNAL - _ADMITTED
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
        f"{metric} reaches Grafana (the capture keep-list or the ops sweep's textfile) but no alert rule queries it — nothing "
        f"would surface it, since no dashboard panel carries the app-metric families either. Add a "
        f"rule, or add it to NOT_A_FAULT_SIGNAL with the reason."
    )


# --- the summary must state the quantity the evaluator actually measures (T0103) -------------------


def _rule(uid):
    return next(r for r in _rules() if r["uid"] == uid)


def _threshold(rule):
    for node in rule["data"]:
        for cond in node.get("model", {}).get("conditions", []) or []:
            params = cond.get("evaluator", {}).get("params") or []
            if params:
                return params[0]
    raise AssertionError(f"no evaluator threshold in {rule['uid']}")


def test_the_healable_gap_rate_is_denominated_in_the_unit_its_summary_claims():
    """The threshold is per-stream and the summary's minutes are that threshold's own: summed ACROSS
    streams a bare bar is denominated in pair-seconds while the summary promises minutes, and the two
    halves live in different fields with nothing else comparing them."""
    rule = _rule("zcrypto-reconcile-healable-gap-rate")
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    summary = rule["annotations"]["summary"]

    assert "count by (pair)" in expr, "the threshold must be per-stream, not a cross-stream sum"
    minutes = _threshold(rule) / 60.0
    assert f"{minutes:.0f} minutes" in summary, f"summary claims a different quantity than {_threshold(rule)}s implies"


def test_the_healable_gap_summary_defers_the_loss_question_to_the_field_that_answers_it():
    """`healable` counts the silence a gap was ADMITTED on, which is `claimed_seconds`; what a splice
    inserted is `healed_seconds` and the permanent shortfall is `residual_seconds`. A summary that
    settles the loss question itself -- "every gap was covered" -- is read on a phone as an all-clear
    this counter cannot support, so it must name the ledger field that answers it instead."""
    rule = _rule("zcrypto-reconcile-healable-gap-rate")
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    assert "zcrypto_reconcile_healable_gap_seconds_total" in expr, f"not the healable counter: {expr!r}"
    assert "zcrypto_reconcile_healed_gap_seconds_total" not in expr, (
        f"reading MINTED repair would make the old wording true and destroy the detect-only signal: {expr!r}"
    )
    ledger = (REPO / "cli/archive/command.py").read_text()
    assert '"residual_seconds"' in ledger, "the ledger key moved -- the summary would point a paged operator at nothing"
    assert "residual_seconds" in rule["annotations"]["summary"], (
        "the summary does not name the field that says whether anything was actually lost, so it either "
        "leaves the question open or answers it from a counter that cannot"
    )


def test_the_permanent_loss_page_outlives_a_single_evaluation_hour():
    """It fires on `increase(...)` over a relative range, so the window IS how long the page stays
    up: at 1h a permanent, unbackfillable condition self-resolves to MissingSeries an hour after
    firing, so the range and the increase() window must span at least a day."""
    rule = _rule("zcrypto-reconcile-residual-gap")
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) >= 86400, f"query range {max(ranges)}s is shorter than a day"
    assert "[24h]" in expr, "the increase() window must match the query range"


def test_the_new_breakage_window_matches_its_relative_time_range():
    """Same coupling as the residual-gap test above, for the rule guarding NEW breakage in
    unbackfillable canonical data: `relativeTimeRange.from` and the `delta()` window must agree, or a
    future edit shortening one silently truncates what the other reads."""
    rule = _rule("zcrypto-ops-verify-replay-new-breakage")
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) >= 90000, f"query range {max(ranges)}s is shorter than 25h"
    assert "[25h]" in expr, "the delta() window must match the query range"


# --- the re-verification backlog rule: its two-night shape IS the rule ---------------------------
# The incremental sweep announces `pending` -- hours whose bytes changed that the nightly drain
# budget did not reach. A backlog is normal and self-clearing; one that stops shrinking means the
# instrument is degraded.

_BACKLOG_STUCK = "zcrypto-ops-verify-replay-backlog-stuck"


def test_the_backlog_stuck_rule_exists_and_fits_the_uid_column():
    """Presence, pinned separately so the shape tests below fail on their own subject rather than on
    a `StopIteration` from the lookup helper."""
    assert _BACKLOG_STUCK in [r["uid"] for r in _rules()], "the re-verification backlog has no alert rule"
    assert len(_BACKLOG_STUCK) <= _UID_MAX, f"{len(_BACKLOG_STUCK)} chars -- the create call will 400"


def _duration_seconds(text: str) -> int:
    """Grafana durations as they appear in this file: `0s`, `15m`, `27h`."""
    unit = {"s": 1, "m": 60, "h": 3600}[text[-1]]
    return int(text[:-1]) * unit


def _backlog_window_seconds(rule) -> int:
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    return int(re.search(r"\[(\d+)h\]", expr).group(1)) * 3600


def test_the_backlog_stuck_window_sees_exactly_two_nightly_runs():
    """26h in BOTH fields: wide enough that night two's sample is always inside the window (24h plus
    slack for a run that starts late), narrow enough that a THIRD run's history never is -- widen it
    and the sign of `delta` stops meaning "did the last run make progress"."""
    rule = _rule(_BACKLOG_STUCK)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    windows = re.findall(r"\[(\d+)h\]", expr)

    assert windows == ["26"], f"expected exactly one 26h range selector, got {windows}"
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    assert max(ranges) == 26 * 3600, f"relativeTimeRange {max(ranges)}s does not match the {windows[0]}h delta window"


def test_the_backlog_stuck_for_strictly_exceeds_a_healthy_drains_true_duration():
    """`ops_verify_replay_pending_hours` is a PERSISTENT textfile gauge that holds its value between the
    daily runs, so the condition goes true at the bump night's publish `T1` and cannot go false until
    the window's left edge passes `T1`: until then the window still contains a pre-bump sample and
    `delta` stays positive even after night two's decrease has landed."""
    rule = _rule(_BACKLOG_STUCK)
    hold = max(24 * 3600, _backlog_window_seconds(rule))

    assert _duration_seconds(rule["for"]) > hold, (
        f"for: {rule['for']} does not strictly exceed the {hold / 3600:g}h a HEALTHY drain holds this "
        f"condition true -- healthy and stuck would page identically"
    )


def test_a_healthy_drain_stays_quiet_and_a_stuck_one_pages():
    """Replays nightly-gauge histories through the rule's OWN window and `for:` (read from
    `alerts.yaml`, never restated here) and asserts it discriminates a healthy drain from a stuck one.
    The gauge is modelled as a step function holding its last published value, with
    `delta(pending[W])` read as `v(t) - v(t-W)` -- Prometheus extrapolates the edges, but the SIGN of
    the difference, which is all this rule reads, is unaffected."""
    rule = _rule(_BACKLOG_STUCK)
    window, hold_for = _backlog_window_seconds(rule), _duration_seconds(rule["for"])

    day, first_run = 24 * 3600, 3 * 3600 + 41 * 60  # the nightly timer's 03:41 start
    scenarios = {
        "steady state, nothing ever stale": [0, 0, 0, 0, 0, 0],
        "healthy drain, ~1500 hours a night": [4500, 3000, 1500, 0, 0, 0],
        "stuck flat -- budget zero or drain broken": [3500, 3500, 3500, 3500, 3500, 3500],
        "growing -- staleness outruns the drain": [1000, 2000, 3000, 4000, 5000, 6000],
    }

    def fires(published: list[int], hold_for: int) -> bool:
        events = [(first_run + n * day, v) for n, v in enumerate(published)]

        def value(t):  # the gauge holds its last published value; 0 before the first run
            return next((v for at, v in reversed(events) if at <= t), 0)

        run = 0
        for t in range(0, 10 * day, 60):
            if value(t) > 0 and value(t) - value(t - window) >= 0:
                run += 60
                if run >= hold_for:
                    return True
            else:
                run = 0
        return False

    verdicts = {name: fires(pub, hold_for) for name, pub in scenarios.items()}
    assert verdicts == {
        "steady state, nothing ever stale": False,
        "healthy drain, ~1500 hours a night": False,
        "stuck flat -- budget zero or drain broken": True,
        "growing -- staleness outruns the drain": True,
    }, f"the rule does not discriminate a healthy drain from a stuck one: {verdicts}"

    # And the discrimination is genuinely the `for`'s doing, not an artifact of this simulation: at
    # the 25h that first shipped, the healthy drain fires too -- indistinguishable from stuck.
    assert fires(scenarios["healthy drain, ~1500 hours a night"], 25 * 3600), (
        "the simulation cannot reproduce the defect it exists to prevent -- it is not proving anything"
    )


def test_the_backlog_stuck_rule_needs_both_a_live_backlog_and_a_non_shrinking_one():
    """Two halves, and dropping either one inverts the rule. Without `$A > 0` a drained-to-zero
    backlog reads `delta == 0` forever and pages permanently on a healthy fleet; without
    `$B >= 0` any nonzero backlog pages, which is every night of a legitimate multi-night drain."""
    rule = _rule(_BACKLOG_STUCK)
    by_ref = {n["refId"]: n.get("model", {}) for n in rule["data"]}

    assert by_ref["A"].get("expr") == "ops_verify_replay_pending_hours"
    assert by_ref["B"].get("expr") == "delta(ops_verify_replay_pending_hours[26h])"
    math = [m for m in by_ref.values() if m.get("type") == "math"]
    assert len(math) == 1, f"expected one math node combining the two halves, got {len(math)}"
    assert math[0]["expression"] == "$A > 0 && $B >= 0", f"the two halves are not both required: {math[0]['expression']!r}"


def test_the_backlog_stuck_rule_fires_in_the_direction_it_claims_to():
    """The conjunction is decorative unless the CONDITION reads the node that computes it and
    compares it the right way round: `condition: A` drops the `delta` half and pages on any nonzero
    backlog, and a `lt` evaluator can NEVER fire, since the math node emits only 0 or 1."""
    rule = _rule(_BACKLOG_STUCK)
    by_ref = {n["refId"]: n.get("model", {}) for n in rule["data"]}

    assert rule["condition"] == "D", f"condition {rule['condition']!r} is not the node that combines both halves"
    assert by_ref["D"].get("expression") == "C", "the threshold must read the math node, not a raw query"
    assert by_ref["D"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}, (
        "the math node emits 0 or 1 -- anything but `gt 0` here makes the rule unable to fire"
    )


def test_the_backlog_stuck_rule_stays_quiet_on_a_host_that_has_never_swept():
    """`noDataState: OK` -- the dead-man owns "did the sweep run at all", so a missing series here is
    absence, not a stuck backlog, and Alerting on it would page every fresh host. `execErrState:
    Alerting` because a query that cannot evaluate leaves the backlog unwatched."""
    rule = _rule(_BACKLOG_STUCK)
    assert rule["noDataState"] == "OK", "a host with no sweep history would page"
    assert rule["execErrState"] == "Alerting", "a broken query would leave the backlog silently unwatched"


# --- the sleeve-composition rule: `changes`, not `delta`, is the whole rule ------------------------

_SLEEVE_CHANGED = "zcrypto-engine-sleeve-count-changed"


def test_the_sleeve_composition_rule_counts_steps_rather_than_netting_them():
    """`changes()`, never `delta()`: `zcrypto_engine_active_sleeves` is a non-monotone gauge, so
    `delta` reads the NET change across the window and a sleeve arming while another goes flat —
    exactly the event this rule announces — nets to zero. Counting steps is why the evaluator can be
    a plain `gt 0` in either direction."""
    rule = _rule(_SLEEVE_CHANGED)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert "changes(" in expr, f"the rule must count steps, not net them: {expr!r}"
    assert "delta(" not in expr, f"delta() nets an arm against a flat and reads zero: {expr!r}"
    assert _threshold(rule) == 0, "any step is the event -- a higher threshold would ignore single re-armings"


def test_the_sleeve_composition_window_matches_its_relative_time_range():
    """The same coupling the residual-gap and new-breakage rules pin: shortening one field without
    the other silently truncates what the rule reads."""
    rule = _rule(_SLEEVE_CHANGED)
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert re.findall(r"\[(\d+)h\]", expr) == ["26"], f"expected exactly one 26h range selector: {expr!r}"
    assert max(ranges) == 26 * 3600, f"relativeTimeRange {max(ranges)}s does not match the 26h changes() window"


def test_the_sleeve_composition_rule_stays_quiet_while_the_series_does_not_exist_yet():
    """`noDataState: OK` is load-bearing twice over: the series does not exist until the engine
    converge that ships it lands, and it is deliberately left unpublished until the first cycle
    measures a composition. Alerting on absence would page continuously through both, and the
    engine going dark is already the dead-man's and the cycle-staleness rule's job."""
    rule = _rule(_SLEEVE_CHANGED)
    assert rule["noDataState"] == "OK", "an engine that has not yet published a composition would page"
    assert rule["execErrState"] == "Alerting", "a broken query would leave the composition silently unwatched"
    assert rule["labels"]["severity"] == "warning", "this announces a change in the book, not a fault"


# --- the journal-prune liveness rule: the ABSENCE is the alarm ------------------------------------
# A deleted `.prom` takes its mtime series away rather than ageing it, so the mtime rule's empty
# result meets `noDataState: OK` and nothing fires. This rule reads the value the prune writes on
# completion, under `noDataState: Alerting`, so the vanishing pages.

_PRUNE_DEAD = "zcrypto-engine-journal-prune-dead"
_PRUNE_STALE_MTIME = "zcrypto-oneoff-textfile-stale"


def test_the_prune_liveness_rule_reads_the_completion_gauge_rather_than_the_files_mtime():
    """The two reads are not interchangeable: a restore or an rsync refreshes an mtime over a prune
    that never ran, and only a completed run writes the gauge. Reading mtime here would leave the
    pair with two views of the same lie."""
    expr = " ".join(n.get("model", {}).get("expr", "") for n in _rule(_PRUNE_DEAD)["data"])
    assert "zcrypto_engine_journal_prune_last_run_timestamp_seconds" in expr, f"not the completion gauge: {expr!r}"
    assert "node_textfile_mtime_seconds" not in expr, f"this is the mtime rule's read, not this rule's: {expr!r}"
    assert len(_PRUNE_DEAD) <= _UID_MAX, f"{len(_PRUNE_DEAD)} chars -- the create call will 400"


def test_a_vanished_prune_gauge_pages_while_a_daily_run_stays_quiet():
    """Replays gauge histories through the rule's OWN threshold, `for:` and `noDataState` (read from
    `alerts.yaml`, never restated): a timer running daily, one stopped with its `.prom` left behind,
    and a `.prom` deleted so the series never exists. Only `noDataState` decides the third, which the
    closing assertion shows by re-running all three under the mtime rule's `OK` posture."""
    rule, minute, day = _rule(_PRUNE_DEAD), 60, 24 * 3600
    bar, hold_for = _threshold(rule), _duration_seconds(rule["for"])
    first_run = 1 * 3600 + 23 * 60  # the timer's 01:23 UTC start

    def fires(runs: list[int], no_data_state: str) -> bool:
        """`runs` are the completion times; the series exists only while at least one precedes t."""
        run = 0
        for t in range(first_run, first_run + 10 * day, minute):
            last = max((at for at in runs if at <= t), default=None)
            firing = no_data_state == "Alerting" if last is None else (t - last) > bar
            run = run + minute if firing else 0
            if run >= hold_for:
                return True
        return False

    daily = [first_run + n * day for n in range(10)]
    stopped = daily[:3]  # the timer stops on the third day; the .prom stays, so the gauge freezes
    deleted: list[int] = []  # the file is removed, so the series never exists at all

    verdicts = {
        name: fires(runs, rule["noDataState"]) for name, runs in (("daily", daily), ("stopped", stopped), ("deleted", deleted))
    }
    assert verdicts == {"daily": False, "stopped": True, "deleted": True}, (
        f"the rule does not discriminate a live daily prune from a stopped or deleted one: {verdicts}"
    )

    # The defect this rule exists to close, constructed: under the mtime rule's posture the deleted
    # arm alone flips to silence, so `noDataState` is doing the work and not the threshold.
    under_ok = {name: fires(runs, "OK") for name, runs in (("daily", daily), ("stopped", stopped), ("deleted", deleted))}
    assert under_ok == {"daily": False, "stopped": True, "deleted": False}, (
        f"the simulation cannot reproduce the silence `noDataState: OK` causes -- it is proving nothing: {under_ok}"
    )
    assert _rule(_PRUNE_STALE_MTIME)["noDataState"] == "OK", (
        "the mtime rule no longer swallows the empty result, so re-derive whether this rule's Alerting posture is still the only cover"
    )


# --- the runbook link an alert sends an operator to must actually exist ---------------------------
# `grafana-push.sh` ships the summary verbatim, so a renamed or never-written anchor renders as a
# plain `#fragment` that scrolls nowhere -- worth exactly as much as no runbook at all to a
# responder on a phone with nothing open.

RUNBOOKS = REPO / "infra/runbooks"
# The anchors are explicit `<a name=...>` tags rather than heading slugs precisely so the
# `-- ALERT` / `-- KNOWN LIMITATION` marker cannot become part of them; match that literal form.
_ANCHOR_TAG = re.compile(r'<a name="([A-Za-z0-9._-]+)"></a>')
# Path-agnostic across the runbook directory -- the procedures live in per-subsystem files and the
# README is only the index -- and BOTH halves are captured, because a link resolves against the file
# it names: an anchor living in a SIBLING file scrolls nowhere. The anchor half excludes `.` (the
# file half needs it), since a dashboard description ends its sentence right after the citation and
# a dot-accepting class would swallow it.
_RUNBOOK_LINK = re.compile(r"infra/runbooks/([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)")
# The index's own rows link SIDEWAYS -- `](capture.md#anchor)`, relative, no `infra/runbooks/`
# prefix -- so `_RUNBOOK_LINK` structurally cannot see them. Matched separately for that reason.
_INDEX_LINK = re.compile(r"\]\(([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)\)")


def _runbook_anchors() -> dict[str, list[str]]:
    """Every anchor under `infra/runbooks/`, mapped to the file name(s) that define it."""
    found: dict[str, list[str]] = {}
    for path in sorted(RUNBOOKS.glob("*.md")):
        for anchor in _ANCHOR_TAG.findall(path.read_text()):
            found.setdefault(anchor, []).append(path.name)
    return found


def test_every_runbook_anchor_is_defined_in_exactly_one_file():
    """Two files defining the same anchor makes every citation of it ambiguous -- and a section
    copied to its new subsystem file without being deleted from the old one is exactly how that
    happens, silently, while every citation still resolves."""
    dupes = {anchor: files for anchor, files in _runbook_anchors().items() if len(files) > 1}
    assert not dupes, f"a runbook anchor is defined in more than one file, so a citation of it is ambiguous: {dupes}"


def test_every_alert_rule_carries_a_resolving_runbook_link():
    """A rule with no runbook is read on a phone, in Slack, with nothing open -- the situation the
    runbook protocol exists for. Requiring the link on EVERY rule is what keeps a new rule from
    shipping without a procedure; the sibling test above only checks the links that are present."""
    anchors = _runbook_anchors()
    unlinked = []
    for rule in _rules():
        summary = (rule.get("annotations") or {}).get("summary") or ""
        links = _RUNBOOK_LINK.findall(summary)
        if not links or any(filename not in anchors.get(anchor, ()) for filename, anchor in links):
            unlinked.append(rule["uid"])
    assert not unlinked, (
        f"{len(unlinked)} rule(s) carry no resolving runbook link in their summary, so a paged "
        f"operator has nothing to open: {sorted(unlinked)}"
    )


def test_every_runbook_link_in_an_alert_summary_resolves():
    anchors = _runbook_anchors()
    cited, broken = [], []
    for rule in _rules():
        for filename, anchor in _RUNBOOK_LINK.findall(" ".join((rule.get("annotations") or {}).values())):
            cited.append(f"{filename}#{anchor}")
            if filename not in anchors.get(anchor, ()):
                broken.append((rule["uid"], f"{filename}#{anchor}", anchors.get(anchor) or "no runbook file"))

    assert cited, "no rule cites a runbook anchor -- the regex is broken, not the summaries"
    assert not broken, (
        f"an alert summary points at a runbook anchor the file it names does not define -- the "
        f"responder gets a fragment and no next step (uid, cited, actually defined in): {broken}"
    )


def test_the_runbook_link_pattern_truncates_a_dot_bearing_anchor_so_it_cannot_resolve():
    """`_RUNBOOK_LINK`'s anchor class excludes `.`, so an anchor carrying one is captured TRUNCATED
    and the resolve test fails on it rather than skipping it."""
    assert _RUNBOOK_LINK.findall("infra/runbooks/capture.md#some.anchor") == [("capture.md", "some")]
    assert "some" not in _runbook_anchors(), "the truncated anchor resolved -- the fail-closed claim is false"
    # The true positive: a dot-free anchor is captured whole.
    assert _RUNBOOK_LINK.findall("infra/runbooks/capture.md#zcrypto-capture-stream-silent") == [
        ("capture.md", "zcrypto-capture-stream-silent")
    ]


def test_every_runbook_link_in_a_dashboard_description_resolves():
    """The panel descriptions cite sections the same way the summaries do, and they are read at the
    same moment -- a responder who followed the notification's panel link is already on the board.
    Held to the same bar rather than left to the summaries' test, which reads `alerts.yaml` only."""
    anchors = _runbook_anchors()
    cited, broken = [], []
    for path in sorted((REPO / "infra/grafana").glob("*.json")):
        for filename, anchor in _RUNBOOK_LINK.findall(path.read_text()):
            cited.append(f"{filename}#{anchor}")
            if filename not in anchors.get(anchor, ()):
                broken.append((path.name, f"{filename}#{anchor}", anchors.get(anchor) or "no runbook file"))

    assert cited, "no dashboard cites a runbook anchor -- the regex is broken, not the descriptions"
    assert not broken, f"a dashboard description points at a runbook anchor its named file does not define: {broken}"


def test_the_index_routes_to_every_section_and_only_to_real_ones():
    """Every index row resolves and every section is routed to. The README is a pure index, so its
    rows ARE the entry point a summary's path lands on, and their links are relative, which puts them
    outside every other guard here -- a move that updates the summaries and forgets the index
    misroutes exactly the page the responder lands on."""
    anchors = _runbook_anchors()
    linked = _INDEX_LINK.findall((RUNBOOKS / "README.md").read_text())

    assert linked, "the index has no anchor-bearing rows -- the regex is broken, not the index"
    broken = [(f"{name}#{a}", anchors.get(a) or "no runbook file") for name, a in linked if name not in anchors.get(a, ())]
    assert not broken, f"an index row links at a section the file it names does not define (row, actually defined in): {broken}"

    unrouted = sorted(set(anchors) - {a for _, a in linked})
    assert not unrouted, f"a runbook section no index row routes to -- unreachable from the entry point: {unrouted}"


def test_the_backlog_stuck_summary_sits_where_the_vocabulary_guard_reads_it():
    """`test_internal_terms_not_operator_visible` joins `annotations.values()` and scans nothing
    else, so operator text parked anywhere but `annotations` ships unscanned. Pin that this rule's
    Slack message is inside what that guard reads, and that it is self-contained enough to act on:
    it names the runbook, so the responder is never left with a fragment and no next step."""
    rule = _rule(_BACKLOG_STUCK)
    summary = (rule.get("annotations") or {}).get("summary", "")

    assert summary.strip(), "no annotations.summary -- the vocabulary guard would scan an empty string"
    assert _RUNBOOK_LINK.search(summary), "the summary names no runbook, so the page carries no next step"


# --- a summary may never interpolate the internal hostname ----------------------------------------

# Every form Grafana's Go templater accepts for the same field. A summary is baked at EVALUATION
# time, before any notification template runs, so the notification templates' `zcrypto.host` ->
# friendly-name mapping cannot reach it: an interpolated `host` ships the raw internal hostname
# straight to a phone. The TOKEN is literal text in the file and therefore walkable.
_HOST_INTERPOLATIONS = ("$labels.host", ".Labels.host", 'index $labels "host"')


def test_no_alert_summary_interpolates_the_internal_hostname():
    offenders = [
        (r["uid"], token)
        for r in _rules()
        for token in _HOST_INTERPOLATIONS
        if token in (r.get("annotations") or {}).get("summary", "")
    ]
    assert not offenders, (
        f"an alert summary interpolates the internal hostname: {offenders}. Summaries are rendered "
        f"before the notification template's host mapping, so say 'the host this notification names' "
        f"and let the template do the naming."
    )


# --- the total-blackout rule, pinned by uid because the family guard cannot see it ---------------

_ALL_STREAMS_SILENT = "zcrypto-capture-all-streams-silent"


def test_the_total_blackout_rule_exists_and_keeps_its_discriminating_aggregation():
    """The cross-pair `min by (host)` IS this rule: the minimum across pairs is what distinguishes
    one quiet leg (normal at any hour) from the whole feed stopping -- the shape the dead-man, the
    desync rule and the gap counter all sit green through, over unbackfillable L2.

    Pinned by uid rather than left to `test_every_fault_signal_metric_is_watched_by_a_rule`, which
    cannot cover it: that guard is FAMILY-level, and `zcrypto-capture-stream-silent` queries the same
    `zcrypto_capture_seconds_since_last_book_message`, so each rule excuses the other."""
    rule = _rule(_ALL_STREAMS_SILENT)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert len(_ALL_STREAMS_SILENT) <= _UID_MAX, f"{len(_ALL_STREAMS_SILENT)} chars -- the create call will 400"
    assert "min by (host) (" in expr, (
        f"the cross-pair MINIMUM is the discriminator -- any other aggregation reads a healthy pair "
        f"and sits green through a total blackout: {expr!r}"
    )


_STREAM_SILENT = "zcrypto-capture-stream-silent"


@pytest.mark.parametrize("uid", [_ALL_STREAMS_SILENT, _STREAM_SILENT])
def test_the_capture_silence_rules_stay_quiet_when_the_query_itself_cannot_run(uid):
    """`execErrState: OK` on these two ALONE, and it is the same blindness class as their
    `noDataState: OK` rather than a relaxation of it: when Grafana cannot execute the query, the
    query did not run, so `Alerting` cannot report a blackout -- it ASSERTS one, in a summary that
    names a host and says every stream on it has been silent for minutes. Measured from Grafana's
    alert state history, the instances these two raised were overwhelmingly Grafana Cloud failing to
    reach its own Prometheus, and `for: 0s` is what made a one-minute platform hiccup page instantly.

    The residual -- a rule-scoped execution error on these two pages nothing -- is read by the daily
    pass's rule-health report (`infra/scripts/ops_daily.py`) and named in the runbook."""
    rule = _rule(uid)
    assert rule["execErrState"] == "OK", "a Grafana query failure would page a total-capture-blackout that nothing observed"
    assert rule["noDataState"] == "OK", "the sibling blindness state moved without its reason"
    assert rule["for"] == "0s", (
        "the execErrState reasoning above rests on `for: 0s` -- a pending period would already "
        "have absorbed the one-minute transients, and this pin should be re-derived"
    )


def test_no_other_rule_quietly_joins_the_execerrstate_exemption():
    """The exemption is justified by measurement on exactly two rules; a third arriving without its
    own evidence is how a deliberate, narrow choice becomes a silent default."""
    exempt = {r["uid"] for r in _rules() if r["execErrState"] == "OK"}
    assert exempt == {_ALL_STREAMS_SILENT, _STREAM_SILENT}, (
        f"execErrState: OK is measured-and-argued for the two capture silence rules only; found {sorted(exempt)}"
    )


# --- a self-declared provisional threshold must be registered here, not only in a comment ---------
# `grafana-push.sh` upserts unconditionally, so a bar whose own comment calls itself provisional
# ships anyway unless something in the repo names it. Each entry states what derives the real value;
# when that value lands, the comment and the entry are deleted together.

PROVISIONAL_THRESHOLDS: set[str] = {
    # Both bars come from a linear fit in `infra/scripts/bench-ledger-scan.py` over synthetic records,
    # not from a ledger ever observed at that size; the critical bar also encodes the ops host's
    # MemAvailable. What derives the real values: re-run that benchmark against the ledger's own
    # record shape, and read the operand live as node_memory_MemAvailable_bytes{host="ops"} -- never
    # MemFree, which reads far smaller.
    "zcrypto-reconcile-ledger-scan-slow",
    "zcrypto-reconcile-ledger-scan-critical",
    # Hourly-floor growth over 24 h, sized for notice ahead of the headroom page rather than fitted
    # to a distribution. What derives the real value: the first leak it fires on, or thirty days of
    # floor deltas read from the fleet board's growth-per-day panel.
    "zcrypto-fleet-memory-leak",
}

_PROVISIONAL = "PROVISIONAL"


def _uids_with_a_provisional_marker() -> set[str]:
    """Attribute each `PROVISIONAL` comment line to the rule it sits inside. Comments are stripped by
    the YAML parser, so this walks the raw text -- the marker only ever lives in a comment."""
    uid, found = None, set()
    for line in ALERTS.read_text().splitlines():
        if line.startswith("  - uid:"):
            uid = line.split("uid:", 1)[1].strip()
        # config-selector-ok: scanning every line for a marker, not selecting a setting
        if _PROVISIONAL in line and uid is not None:
            found.add(uid)
    return found


def test_every_provisional_threshold_is_registered():
    unregistered = _uids_with_a_provisional_marker() - PROVISIONAL_THRESHOLDS
    assert not unregistered, (
        f"a rule declares its own threshold {_PROVISIONAL} but nothing outside that comment knows: "
        f"{sorted(unregistered)}. Add it to PROVISIONAL_THRESHOLDS with what derives the real value, "
        f"or derive the value and delete the marker."
    )


def test_the_provisional_register_has_not_gone_stale():
    """The other half, and the half that makes the register worth having: an entry outliving its
    marker is a deferral that reads live while the value it guarded was quietly settled, which is
    exactly the failure the register exists to prevent."""
    discharged = PROVISIONAL_THRESHOLDS - _uids_with_a_provisional_marker()
    assert not discharged, (
        f"registered as provisional but the rule no longer says so: {sorted(discharged)}. If the "
        f"threshold was derived, delete the entry in the same change."
    )


# --- Grafana's template parser is stricter than Go's ------------------------------------------
# A leading trim marker on a define declaration -- `{{- define "x" ... }}` -- parses in Go's own
# text/template but Grafana's provisioning API REJECTS it with `invalid template: unexpected
# <define> in command`, and the whole push aborts under `set -euo pipefail`. Trim markers everywhere
# else (`-}}`, `{{- end`, `{{- template`) are accepted, so only the leading one goes -- and a
# Go-based test cannot catch this, which is why it is here.
NOTIFICATION_TEMPLATES = sorted((REPO / "infra/grafana/notification-templates").glob("*.tmpl"))


@pytest.mark.parametrize("path", NOTIFICATION_TEMPLATES, ids=lambda p: p.name)
def test_no_define_carries_a_leading_trim_marker(path):
    offenders = [
        f"{path.name}:{i}: {line.strip()[:70]}"
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"\{\{-\s*define\s", line)
    ]
    assert not offenders, (
        "Grafana's provisioning API rejects a define whose action opens with a trim marker, and the "
        "push aborts before any rule ships. Drop the leading `-` (keep the trailing `-}}`):\n  " + "\n  ".join(offenders)
    )


# --- the venue pair: a latch that cannot self-resolve, plus the recurrence signal that can --------
# `zcrypto-capture-venue-not-online` fires on PRESENCE of a non-online series and never falls until
# the capture daemon restarts. That latch is deliberate, but it means a repeat of an already-seen
# state only steps a counter whose alert instance is already Alerting, so nothing notifies; the
# recurrence rule below closes that, and both are needed while each keeps its own form.

_VENUE_LATCH = "zcrypto-capture-venue-not-online"
_VENUE_RECURRENCE = "zcrypto-capture-venue-state-recurrence"


def test_the_venue_recurrence_rule_exists_and_fits_the_uid_column():
    """Pinned separately so the shape tests below fail on their own subject rather than on a
    `StopIteration` from the lookup helper."""
    assert _VENUE_RECURRENCE in [r["uid"] for r in _rules()], "a repeat venue degradation has no alert rule"
    assert len(_VENUE_RECURRENCE) <= _UID_MAX, f"{len(_VENUE_RECURRENCE)} chars -- the create call will 400"


def test_the_venue_recurrence_window_matches_its_relative_time_range():
    """Same coupling the residual-gap and new-breakage rules carry: `relativeTimeRange.from` and the
    `increase()` window must agree, or a future edit to one silently truncates what the other reads."""
    rule = _rule(_VENUE_RECURRENCE)
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) == 900, f"query range {max(ranges)}s is not the 15m the summary promises"
    assert "[15m]" in expr, "the increase() window must match the query range"


def test_the_two_venue_rules_keep_opposite_forms():
    """The latch stays a PRESENCE form and the recurrence rule an `increase()`: increase() cannot
    lead -- Prometheus inserts no implicit zero, so a series born non-online reports nothing on its
    first transition -- and presence cannot follow, being already Alerting on the repeat."""
    latch = " ".join(n.get("model", {}).get("expr", "") for n in _rule(_VENUE_LATCH)["data"])
    recurrence = " ".join(n.get("model", {}).get("expr", "") for n in _rule(_VENUE_RECURRENCE)["data"])

    assert "increase(" not in latch, (
        "the latch must stay a PRESENCE form -- increase() is blind to a series whose whole burst precedes its first scrape"
    )
    assert "increase(" in recurrence, "the recurrence rule must stay an increase() form -- presence cannot re-notify"


def test_both_venue_rules_group_by_the_label_the_responder_acts_on():
    """`maintenance` (planned, wait) and `cancel_only`/`post_only` (degraded, act) demand opposite
    responses, so collapsing `system` discards the one label the page is read for. The `on()` on the
    fallback is load-bearing for the same grouping: `vector(0)` is unlabelled, so a bare `or` stops
    being mutually exclusive once the left arm carries labels and rides through as a permanent series."""
    for uid in (_VENUE_LATCH, _VENUE_RECURRENCE):
        expr = " ".join(n.get("model", {}).get("expr", "") for n in _rule(uid)["data"])
        assert "by (host, system)" in expr, f"{uid} collapsed the label the responder acts on"
        assert "or on() vector(0)" in expr, f"{uid} lost the labelled-arm-safe NoData fallback"


# --- memory is watched as a routine, never as a rollout read ---------------------------------------
# These rules run regardless of converges, so a bake owes no memory read at all: a hand-read RSS row
# is a human scheduling a query, the next converge voids it, and the reads become a lock on the fleet.

_MEM_HEADROOM = "zcrypto-fleet-memory-headroom"
_MEM_LEAK = "zcrypto-fleet-memory-leak"
_DAEMON_RESTARTED = "zcrypto-fleet-daemon-restarted"
ANSIBLE = REPO / "infra/ansible"


def _compose_alloy_limit_bytes(path: Path) -> int:
    """The `memory:` limit under the grafana-alloy service in a compose file, where it is a literal.
    ops is deliberately excluded: its cap is the `ops_alloy_memory_limit` var, not a literal, so
    passing its template through here would trip the `assert m` below."""
    text = path.read_text()
    start = text.index("container_name: grafana-alloy")
    m = re.search(r"memory:\s*\"?(\d+)([gGmM])\"?", text[start:])
    assert m, f"no memory limit under grafana-alloy in {path}"
    return int(m.group(1)) * {"g": 1024**3, "m": 1024**2}[m.group(2).lower()]


def _ansible_memory_limit_bytes(path: Path, key: str) -> int:
    """`"2g"` / `"1g"` as docker reads them -- binary units, the only ones compose accepts here."""
    value = yaml.safe_load(path.read_text())[key]
    units = {"g": 1024**3, "m": 1024**2}
    return int(value[:-1]) * units[value[-1].lower()]


_GOMEMLIMIT_UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


def _parse_size_bytes(value: str) -> int:
    """`"920MiB"`, as Alloy's GOMEMLIMIT -- Go's own suffixes only (`B`/`KiB`/`MiB`/`GiB`/`TiB`).
    Docker's `m`/`g` (the `_ansible_memory_limit_bytes`/`_compose_alloy_limit_bytes` side) parse to
    the same bytes at the SAME value but are invalid GOMEMLIMIT syntax -- Go rejects them and Alloy
    crash-loops at startup, so accepting them here would let that defect read as a passing ratio."""
    m = re.match(r"(\d+)(TiB|GiB|MiB|KiB|B)$", value.strip())
    assert m, f"not a valid Go GOMEMLIMIT suffix: {value!r}"
    return int(m.group(1)) * _GOMEMLIMIT_UNITS[m.group(2).lower()]


def _compose_alloy_gomemlimit_bytes(path: Path) -> int:
    """The `GOMEMLIMIT:` literal under the grafana-alloy service -- sibling of
    `_compose_alloy_limit_bytes`, same container_name-scoped search, reading the Go soft limit
    instead of the container cap."""
    text = path.read_text()
    start = text.index("container_name: grafana-alloy")
    m = re.search(r'GOMEMLIMIT:\s*"?(\d+(?:TiB|GiB|MiB|KiB|B))"?', text[start:])
    assert m, f"no GOMEMLIMIT under grafana-alloy in {path}"
    return _parse_size_bytes(m.group(1))


def test_the_headroom_rule_encodes_the_limits_ansible_actually_deploys():
    """The ratio's denominators are literal bytes in the expr, because no metric carries the container
    limit (no cadvisor on the capture hosts). A literal drifts silently when the ansible var moves --
    the rule would then measure headroom against a ceiling the host no longer has. So the three
    constants are read from the vars that render the compose files, never from this test's memory."""
    rule = _rule(_MEM_HEADROOM)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    primary = _ansible_memory_limit_bytes(ANSIBLE / "roles/capture/defaults/main.yml", "capture_memory_limit")
    secondary = _ansible_memory_limit_bytes(ANSIBLE / "host_vars/zcrypto-red/vars.yml", "capture_memory_limit")
    engine = _ansible_memory_limit_bytes(ANSIBLE / "roles/engine/defaults/main.yml", "engine_memory_limit")
    legs = [("zcrypto", "capture_app", primary), ("zcrypto-red", "capture_app", secondary), ("zcrypto", "engine_app", engine)]
    for host, job, limit in legs:
        leg = re.search(
            rf'process_resident_memory_bytes\{{[^}}]*host="{host}"[^}}]*job="{job}"[^}}]*\}}\s*/\s*(\d+)', expr
        ) or re.search(rf'process_resident_memory_bytes\{{[^}}]*job="{job}"[^}}]*host="{host}"[^}}]*\}}\s*/\s*(\d+)', expr)
        assert leg, f"no headroom leg for host={host} job={job} in {expr!r}"
        assert int(leg.group(1)) == limit, f"{host}/{job}: expr divides by {leg.group(1)}, ansible deploys {limit}"
    cond = rule["data"][-1]["model"]["conditions"][0]["evaluator"]
    assert cond == {"type": "gt", "params": [0.7]}, "70% of the container limit is the owner's bar (2026-08-28)"
    assert rule["for"] == "5m" and rule["noDataState"] == "OK"


def test_the_leak_rule_reads_hourly_floors_a_day_apart():
    """Read the FLOOR not a sample (the rotation sawtooth spans MiB), compare across a 24 h band
    (steps arrive as ramps and repeat at the same clock offset), and gate the comparison OFF for a
    process younger than 30 h. That gate is load-bearing: `offset 24h` addresses the series by
    labels, which a restart does not change, so an ungated subtraction compares a young process
    against its predecessor's floor. 30 h = the 24 h band plus the 6 h pending period, so no
    evaluation inside the pending window can straddle the restart."""
    rule = _rule(_MEM_LEAK)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    assert expr.count("min_over_time(process_resident_memory_bytes") == 2, expr
    assert "[1h]" in expr and "offset 24h" in expr, expr
    assert re.search(r"and on\(host, job\)\s*\(\(time\(\) - process_start_time_seconds\{[^}]*\}\) > 108000\)", expr), (
        "the age gate is what makes the restart claim true -- without it the rule compares a young process against its predecessor"
    )
    assert rule["for"] == "6h" and rule["noDataState"] == "OK"
    assert rule["labels"]["severity"] == "warning"


def test_the_restart_rule_is_the_only_restart_signal_and_absorbs_a_datasource_hiccup():
    """No cadvisor, so `RestartCount` has no metric -- but `process_start_time_seconds` is kept and
    moves on every restart, which is the same fact. `changes(...[15m])` stays >0 for fifteen minutes,
    so a pending period costs no detection and keeps the rule out of the `for: 0s` set that a
    one-minute datasource error can fire (see the execErrState reasoning on the silence rules)."""
    rule = _rule(_DAEMON_RESTARTED)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    assert "changes(process_start_time_seconds" in expr and "[15m]" in expr, expr
    assert rule["for"] != "0s", "a pending period is what keeps a datasource hiccup from firing this"
    assert rule["noDataState"] == "OK" and rule["execErrState"] == "Alerting"


# --- the ops ERROR rule's selector covers every container the ops log plane can label -------------
OPS_ALLOY = REPO / "infra/ansible/roles/ops/files/config.alloy"
OPS_COMPOSE = REPO / "infra/ansible/roles/ops/templates/compose.yaml.j2"


def _ops_log_containers() -> set[str]:
    """Every `container` label the ops host's log plane can emit: the journal units the keep-regex
    admits (their unit stem), Alloy's own stream, and the poller's direct-ship service name."""
    keep = next(ln for ln in OPS_ALLOY.read_text().splitlines() if re.search(r'regex\s*=\s*"zcrypto-\(', ln))
    units = re.search(r"zcrypto-\(([^)]+)\)", keep)
    assert units and re.search(r"grafana-alloy", keep), f"the ops journal keep-regex changed shape: {keep!r}"
    poller = re.search(r"ZCRYPTO_LOG_SERVICE:\s*(\S+)", OPS_COMPOSE.read_text())
    assert poller, "the poller's direct-ship service label moved out of the ops compose"
    return {f"zcrypto-{u}" for u in units.group(1).split("|")} | {"alloy", poller.group(1)}


def test_the_ops_error_rule_selects_every_container_the_ops_log_plane_can_emit():
    """A container the journal keep-regex or the poller's direct-ship can label, but the ERROR
    rule's selector omits, ships errors nothing watches."""
    rule = _rule("zcrypto-ops-error-logs")
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    selector = re.search(r'container=~"([^"]+)"', expr)
    assert selector, f"the ops ERROR rule no longer selects on container: {expr!r}"
    admitted = _ops_log_containers()
    assert len(admitted) >= 5, f"the log plane derivation found only {sorted(admitted)} -- vacuous"
    unmatched = sorted(c for c in admitted if not re.fullmatch(selector.group(1), c))  # Loki's =~ is anchored
    assert not unmatched, f"the ops log plane can label {unmatched}; the ERROR rule's selector {selector.group(1)!r} misses them"


# --- every memory-LIMITED job has a headroom leg, or is named absent with its reason ----------------
# compose source carrying a `memory:` limit -> the (host, job) pairs it renders to. The local
# infra/docker compose is nobody's host.
_LIMITED_JOBS: dict[str, tuple[tuple[str, str], ...]] = {
    "infra/ansible/roles/capture/templates/compose.yaml.j2": (("zcrypto", "capture_app"), ("zcrypto-red", "capture_app")),
    "infra/ansible/roles/engine/templates/compose.yaml.j2": (("zcrypto", "engine_app"),),
    "infra/ansible/roles/capture/templates/alloy-compose.yaml.j2": (
        ("zcrypto", "integrations/self"),
        ("zcrypto-red", "integrations/self"),
    ),
    "infra/ansible/roles/ops/templates/alloy-compose.yaml.j2": (("ops", "integrations/self"),),
    "infra/nas/compose.yaml": (("nas", "integrations/self"),),
    "infra/docker/compose.yaml": (),
}
# (host, job) with a limit and no headroom leg, each with the reason it is left out.
_HEADROOM_DELIBERATELY_ABSENT: dict[tuple[str, str], str] = {}

_ALLOY_HEADROOM = "zcrypto-fleet-alloy-memory-headroom"


def test_every_memory_limited_job_has_a_headroom_leg_or_a_recorded_absence():
    """A compose service with a `memory:` limit is a container the OOM-killer can take; every
    (host, job) it renders to divides by a limit in one of the two headroom rules, or is named in
    `_HEADROOM_DELIBERATELY_ABSENT` with its reason."""
    # config-selector-ok: presence of any `memory:` line is the question, not a value to parse
    limited = sorted(str(p.relative_to(REPO)) for p in REPO.glob("infra/**/*compose*.y*ml*") if "memory:" in p.read_text())
    assert limited == sorted(_LIMITED_JOBS), f"the memory-limited compose sources changed: {limited} -- update the map"
    exprs = " ".join(
        str(n.get("model", {}).get("expr", "")) for uid in (_MEM_HEADROOM, _ALLOY_HEADROOM) for n in _rule(uid)["data"]
    )
    legs = re.findall(r"process_resident_memory_bytes\{([^}]*)\}\s*/\s*\d+", exprs)
    assert len(legs) >= 4, f"the two headroom rules carry only {len(legs)} legs -- the parse is broken"

    def covered(host: str, job: str) -> bool:
        for leg in legs:
            h, j = re.search(r'host(=~?)"([^"]+)"', leg), re.search(r'job="([^"]+)"', leg)
            if not (h and j) or j.group(1) != job:
                continue
            if host in (h.group(2).split("|") if h.group(1) == "=~" else [h.group(2)]):
                return True
        return False

    pairs = [pair for pairs in _LIMITED_JOBS.values() for pair in pairs]
    missing = [pair for pair in pairs if not covered(*pair) and pair not in _HEADROOM_DELIBERATELY_ABSENT]
    assert not missing, f"memory-limited but no headroom leg and no recorded absence: {missing}"
    stale = [pair for pair in _HEADROOM_DELIBERATELY_ABSENT if covered(*pair)]
    assert not stale, f"named absent but a leg exists -- the excuse outlived the gap: {stale}"


def test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling():
    """Alloy runs near its ceiling -- ops nearest -- so the 0.7 bar the app daemons carry would page
    a healthy fleet every evaluation. This bar clears steady state; the OOM it warns about is owned
    separately by `Fleet · Alloy dark`."""
    rule = _rule(_ALLOY_HEADROOM)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    # ops divides by its OWN cap: it runs too close to the 512m every other Alloy carries, and ops is
    # the one host where margin is free. Read the number back from the ansible var so raising the cap
    # without the rule fails here.
    ops_cap = _ansible_memory_limit_bytes(ANSIBLE / "roles/ops/defaults/main.yml", "ops_alloy_memory_limit")
    assert re.search(rf'host="ops", job="integrations/self"\}}\s*/\s*{ops_cap}\b', expr), (
        f"the ops leg must divide by ops_alloy_memory_limit ({ops_cap}); a cap raised without this ratio lies: {expr!r}"
    )
    # The other three are LITERALS in their own compose sources, so read each back the same way --
    # asserting the rule merely contains 536870912 would let `memory: 512m` move in a template while
    # the ratio kept dividing by the old cap, which is the silent lie the ops pin above exists to stop.
    others = {
        "zcrypto": ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2",
        "zcrypto-red": ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2",
        "nas": REPO / "infra/nas/compose.yaml",
    }
    caps = {h: _compose_alloy_limit_bytes(p) for h, p in others.items()}
    assert len(set(caps.values())) == 1, f"the three shared-cap hosts no longer share a cap: {caps} -- split the leg"
    shared = next(iter(caps.values()))
    assert re.search(rf'host=~"zcrypto\|zcrypto-red\|nas", job="integrations/self"\}}\s*/\s*{shared}\b', expr), (
        f"the shared leg must divide by the compose literal ({shared}); found: {expr!r}"
    )
    assert rule["data"][-1]["model"]["conditions"][0]["evaluator"]["params"] == [0.9]
    assert rule["for"] != "0s" and rule["noDataState"] == "OK"


_SLACK_TEMPLATE = REPO / "infra/grafana/notification-templates/zcrypto-slack.tmpl"
# The operator name for each host label, read from the template that renders it -- the vocabulary a
# summary must use, since a phone shows that name and nothing else.
_HOST_VOCABULARY = re.compile(r'eq \. "([^"]+)" \}\}([^\n{]+)')


def test_the_headroom_summary_names_the_hosts_its_expression_actually_reads():
    """A summary is read on a phone with nothing open, so "512 MiB elsewhere" promised every other
    Alloy host while the expression selects four by name. The edge runs the apt Alloy under no
    container and no cap, so this ratio has no denominator for it and `zcrypto-alloy-dark-zaccess`
    owns its OOM; a CAPPED host is forced in by the memory-limited-job test above."""
    vocabulary = dict(_HOST_VOCABULARY.findall(_SLACK_TEMPLATE.read_text()))
    vocabulary = {label: name.strip() for label, name in vocabulary.items()}
    assert len(vocabulary) >= 5, f"the host vocabulary parse found only {vocabulary} -- the template's shape moved"

    rule = _rule(_ALLOY_HEADROOM)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    selected = {h for match in re.findall(r'host=~?"([^"]+)"', expr) for h in match.split("|")}
    assert selected <= set(vocabulary), f"the expression selects a host the notification template cannot name: {selected}"

    summary = rule["annotations"]["summary"]
    named = {label for label, name in vocabulary.items() if re.search(rf"\b{re.escape(name)}\b", summary, re.I)}
    assert named == selected, (
        f"the summary names {sorted(named) or 'no host'} while the expression reads {sorted(selected)} -- a paged "
        f"operator is told this rule watches hosts it does not, or is not told about ones it does"
    )


def test_ops_alloy_memory_limit_has_no_override_the_pin_above_would_miss():
    """`ops_alloy_memory_limit` is not overridden outside `roles/ops/defaults/main.yml`, the only
    file `test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling` reads -- the sibling
    `capture_memory_limit` uses exactly that override shape for real, in
    `host_vars/zcrypto-red/vars.yml`. Vault files are walked too: this repo vaults per-VALUE, so a
    key's NAME stays plaintext even in a `vault.yml` and the substring search below reads it."""
    hits = [
        path
        for base in (ANSIBLE / "host_vars", ANSIBLE / "group_vars")
        for path in base.rglob("*.yml")
        if "ops_alloy_memory_limit" in path.read_text()
    ]
    assert not hits, f"ops_alloy_memory_limit overridden outside roles/ops/defaults/main.yml: {hits}"


def test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host():
    """The 0.9 headroom bar means "the runtime lost its soft limit" only if GOMEMLIMIT sits at the
    same fraction of the container cap on every host -- ops's 920MiB/1g and the other three's
    460MiB/512m both land at 0.898. [0.88, 0.92] tolerates the MiB-vs-binary-GiB rounding without
    tolerating a cap raised (or a GOMEMLIMIT left behind) without its ratio partner."""
    ops_defaults = ANSIBLE / "roles/ops/defaults/main.yml"
    ops_soft = _parse_size_bytes(yaml.safe_load(ops_defaults.read_text())["ops_alloy_gomemlimit"])
    ops_cap = _ansible_memory_limit_bytes(ops_defaults, "ops_alloy_memory_limit")
    ops_template = ANSIBLE / "roles/ops/templates/alloy-compose.yaml.j2"
    assert 'GOMEMLIMIT: "{{ ops_alloy_gomemlimit }}"' in ops_template.read_text(), (
        "the ops template does not read GOMEMLIMIT from the var above -- the ratio this test proves "
        "would hold on paper while a literal left in the template ships something else entirely"
    )
    ratios = {"ops": ops_soft / ops_cap}
    for host, compose_path in (
        ("zcrypto", ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2"),
        ("zcrypto-red", ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2"),
        ("nas", REPO / "infra/nas/compose.yaml"),
    ):
        ratios[host] = _compose_alloy_gomemlimit_bytes(compose_path) / _compose_alloy_limit_bytes(compose_path)
    for host, ratio in ratios.items():
        assert 0.88 <= ratio <= 0.92, f"{host}: GOMEMLIMIT/cap = {ratio:.3f}, outside [0.88, 0.92]"


@pytest.mark.parametrize("uid", [_MEM_HEADROOM, _MEM_LEAK, _DAEMON_RESTARTED])
def test_the_memory_routine_rules_cover_both_capture_hosts_and_the_engine(uid):
    """All three rules cover both capture daemons and the engine (primary only -- nothing listens on
    the engine port on the secondary, so a `zcrypto-red` engine selector would name a series that
    never exists). The leak and restart rules additionally cover the ops liquidations poller and
    Alloy itself, under the `integrations/self` job its exporter.self metrics carry."""
    rule = _rule(uid)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    if uid == _MEM_HEADROOM:  # the app daemons only: Alloy has its own bar, the poller has no limit
        for token in ("capture_app", "engine_app"):
            assert token in expr, f"{uid} does not cover {token}: {expr!r}"
        assert "integrations/self" not in expr, "Alloy runs near its ceiling; a shared bar pages it on a healthy fleet"
        assert "liquidations_app" not in expr, "the poller has no limit to measure against"
    else:
        for token in ("capture_app", "engine_app", "integrations/self", "liquidations_app", "|nas"):
            assert token in expr, f"{uid} does not cover {token}: {expr!r}"
    assert not re.search(r'job="engine_app"[^}]*host=~"zcrypto\|zcrypto-red"', expr), "engine_app must not select zcrypto-red"
    assert not re.search(r'host=~"zcrypto\|zcrypto-red"[^}]*job="engine_app"', expr), "engine_app must not select zcrypto-red"


_CROSS_REF = re.compile(r"\b([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)")


def test_every_runbook_cross_reference_resolves():
    """A runbook citing a section in another runbook must cite one that exists.

    `test_the_index_routes_to_every_section_and_only_to_real_ones` covers README.md's index rows in a
    direction this test does not -- that every anchor is routed TO -- so do not drop it on the
    strength of this one. The charset matches its siblings deliberately: broad enough that a stray
    capital produces a MATCH that fails the assert, rather than no match and silent non-coverage.
    """
    anchors = {f"{name}#{anchor}" for anchor, names in _runbook_anchors().items() for name in names}
    refs = [
        (path.name, f"{m.group(1)}#{m.group(2)}")
        for path in sorted(RUNBOOKS.glob("*.md"))
        for m in _CROSS_REF.finditer(path.read_text())
    ]
    assert refs, "no cross-references found at all -- the extraction broke, not the runbooks"
    broken = sorted({(src, ref) for src, ref in refs if ref not in anchors})
    assert not broken, f"runbook references pointing at sections that do not exist: {broken}"


# --- the engine dark WITH exposure open: the two-node conjunction IS the rule --------------------
# `zcrypto-engine-cycle-stale` already pages on any engine darkness; what this rule adds is *and
# there is money exposed*, and both halves are written in forms whose obvious spelling cannot fire:
# the position gauge is served by the engine that has gone dark, so it must be read BACKWARDS over a
# lookback rather than instantaneously, and `engine_app` is a STATIC scrape target, so its `up`
# series stays present reading 0 when the container dies and a presence count reads 1 forever.

_DARK_WITH_EXPOSURE = "zcrypto-engine-dark-with-exposure"
# Pinned string, not a keyword: the phone shows the title before the summary, and the two properties
# argued into this wording -- that it holds on the Alloy route too, and that `at last report` does
# not assert a position the rule cannot see is still there -- are not expressible as a substring.
_DARK_WITH_EXPOSURE_TITLE = "Engine · position open at last report and the engine is not reporting"
# The discriminator the summary must name, spelled as that rule's own title so a responder can find
# it in the notification list.
_DARK_DISCRIMINATOR = "Fleet · Alloy dark — Capture primary"

# The `zcrypto-gate` group's evaluation interval, read from Grafana's provisioning rule-group
# endpoint (`/api/v1/provisioning/folder/<folder uid>/rule-groups/zcrypto-gate`, the `interval`
# field) on 2026-08-31. Only the replay's step size; the rule's own numbers are read from the file.
_EVAL_INTERVAL = 60
# Prometheus's own staleness horizon. The unlookbacked control below is defeated by exactly this:
# an instant read of the position gauge holds its value for this long after the engine stops
# publishing and then goes away.
_STALENESS = 300


def test_the_dark_with_exposure_rule_exists_and_fits_the_uid_column():
    """Presence, pinned separately so the shape tests below fail on their own subject rather than on
    a `StopIteration` from the lookup helper."""
    assert _DARK_WITH_EXPOSURE in [r["uid"] for r in _rules()], "an engine dark with exposure open has no alert rule"
    assert len(_DARK_WITH_EXPOSURE) <= _UID_MAX, f"{len(_DARK_WITH_EXPOSURE)} chars -- the create call will 400"


def _dark_with_exposure_lookback(rule) -> int:
    """The seconds of node A's own `last_over_time` selector, parsed rather than restated."""
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    selector = re.search(r"last_over_time\([^)]*\[(\d+[smh])\]\)", expr)
    assert selector, f"node A no longer reads the position over a `last_over_time` range: {expr!r}"
    return _duration_seconds(selector.group(1))


def test_the_dark_with_exposure_range_declares_the_window_its_expression_reads():
    """`relativeTimeRange.from` does not feed a range selector on an instant node, so a mismatch here
    breaks nothing at evaluation time. What it breaks is the record: this file declares a node's
    range as the widest window its expression reads, so `relativeTimeRange` is what a maintainer
    reads for the node's real horizon."""
    node_a = next(n for n in _rule(_DARK_WITH_EXPOSURE)["data"] if n["refId"] == "A")
    selector = re.search(r"last_over_time\([^)]*\[(\d+[smh])\]\)", node_a["model"]["expr"])
    assert selector, f"node A no longer reads the position over a `last_over_time` range: {node_a['model']['expr']!r}"
    assert node_a["relativeTimeRange"]["from"] == _duration_seconds(selector.group(1)), (
        f"node A declares {node_a['relativeTimeRange']['from']}s but reads {selector.group(1)} -- the declared "
        f"horizon and the real one have drifted apart"
    )


def _replay_dark_with_exposure(published, up_at, *, lookback, hold_for, span, a_form="lookbacked", b_form="value"):
    """Evaluation timestamps at which the rule is FIRING, over one `(position, scrape)` history.

    `published` is the position gauge's samples as `(t, value)`; `up_at(t)` returns 1, 0, or `None`
    for a series that is not there at all -- the engine dying leaves `up` PRESENT at 0 (a static
    scrape target is never removed), while the primary's Alloy going dark takes the series away.
    Node A is modelled as what it says: `last_over_time` returns the LAST sample in the window, never
    the largest, so a position closed before the engine went dark reads 0 here."""

    def a(t: int) -> float:
        window = lookback if a_form == "lookbacked" else _STALENESS
        inside = [v for at, v in published if t - window < at <= t]
        return abs(inside[-1]) if inside else 0.0

    def b(t: int) -> float:
        u = up_at(t)
        if u is None:  # both forms fall through `or on() vector(0)` when the series is gone
            return 0.0
        return 1.0 if b_form == "presence" else float(u)

    firing, run = set(), 0
    for t in range(0, span, _EVAL_INTERVAL):
        if a(t) > 0 and b(t) < 1:
            run += _EVAL_INTERVAL
            if run >= hold_for:
                firing.add(t)
        else:
            run = 0
    return firing


def test_a_dark_engine_with_exposure_pages_and_the_three_healthy_shapes_do_not():
    """Replays `(position, scrape)` histories through the rule's OWN lookback and `for:` -- both read
    out of `alerts.yaml`, never restated here, so this fails when the rule changes."""
    rule = _rule(_DARK_WITH_EXPOSURE)
    lookback, hold_for = _dark_with_exposure_lookback(rule), _duration_seconds(rule["for"])

    dark_at = 3600
    closed_at = 1800
    span = dark_at + lookback + 2 * 3600
    open_then_dark = [(t, 0.5) for t in range(0, dark_at, _EVAL_INTERVAL)]
    flat_then_dark = [(t, 0.0) for t in range(0, dark_at, _EVAL_INTERVAL)]
    open_throughout = [(t, 0.5) for t in range(0, span, _EVAL_INTERVAL)]
    # The executor's fill hook calls `set_position` with the sum over `positions_open`, so a full
    # close publishes an explicit 0 rather than stopping the series -- which is what makes this
    # history a published 0 that `last_over_time` can read, and not an absence.
    closed_then_dark = [(t, 0.5 if t < closed_at else 0.0) for t in range(0, dark_at, _EVAL_INTERVAL)]

    def goes_dark(t):  # the container dies; the static target keeps publishing `up = 0`
        return 1 if t < dark_at else 0

    def alloy_goes_dark(t):  # the plane goes dark; the series is REMOVED, not set to 0
        return 1 if t < dark_at else None

    firing = _replay_dark_with_exposure(open_then_dark, goes_dark, lookback=lookback, hold_for=hold_for, span=span)
    assert firing, "a position open at last report and no engine scrape does not page -- the rule cannot fire"
    assert dark_at <= min(firing) <= dark_at + hold_for, (
        f"first page at {min(firing)}s is not within `for: {rule['for']}` of the engine going dark at {dark_at}s"
    )
    horizon = max(at for at, _ in open_then_dark) + lookback
    assert horizon - _EVAL_INTERVAL <= max(firing) < horizon, (
        f"the page stops at {max(firing)}s rather than surviving to the {lookback / 3600:g}h horizon at {horizon}s -- "
        f"an operator asleep through a daily pass would find it self-resolved"
    )

    quiet_flat = _replay_dark_with_exposure(flat_then_dark, goes_dark, lookback=lookback, hold_for=hold_for, span=span)
    assert not quiet_flat, (
        f"a dark engine with NOTHING exposed pages here too, which is cycle-stale's job: {sorted(quiet_flat)[:3]}"
    )

    quiet_scraping = _replay_dark_with_exposure(open_throughout, lambda t: 1, lookback=lookback, hold_for=hold_for, span=span)
    assert not quiet_scraping, f"a healthy engine holding a position pages: {sorted(quiet_scraping)[:3]}"

    quiet_closed = _replay_dark_with_exposure(closed_then_dark, goes_dark, lookback=lookback, hold_for=hold_for, span=span)
    assert not quiet_closed, (
        f"a position CLOSED before the engine went dark still pages -- that is `max_over_time` behaviour, and it "
        f"keeps this page up for the rest of the day over money that is not at risk: {sorted(quiet_closed)[:3]}"
    )

    # The SECOND darkness route, which the rule fires on deliberately: the primary's Alloy takes the
    # series away and `or on() vector(0)` supplies the 0. Replayed because it is half of what this
    # rule does and because control 2 below rests on the two routes reaching `$B < 1` differently.
    alloy_route = _replay_dark_with_exposure(open_then_dark, alloy_goes_dark, lookback=lookback, hold_for=hold_for, span=span)
    assert alloy_route, "a position open with the primary's whole plane dark does not page -- the accepted double-page is gone"

    # The two controls: each replays the TRUE POSITIVE through a defective form of one node and
    # asserts it does not fire, so the replay is shown to move on each defect.
    #
    # (1) Node A read instant, its lookback stripped: the gauge holds its last value only to
    # Prometheus's staleness horizon, so the condition never survives to `for`.
    unlookbacked = _replay_dark_with_exposure(
        open_then_dark, goes_dark, lookback=lookback, hold_for=hold_for, span=span, a_form="instant"
    )
    assert not unlookbacked, (
        f"an instant read of the position gauge fires too, so this replay is not proving the lookback: {sorted(unlookbacked)[:3]}"
    )

    # (2) Node B counting the series' PRESENCE (`count(up{...}) or on() vector(0)`) instead of
    # reading its VALUE. This control and the true positive above are jointly satisfiable only under
    # the real behaviour of a static scrape target: model the dark scrape as an ABSENT series and
    # `count()` falls through its own fallback to 0 and fires here too.
    presence_counting = _replay_dark_with_exposure(
        open_then_dark, goes_dark, lookback=lookback, hold_for=hold_for, span=span, b_form="presence"
    )
    assert not presence_counting, (
        f"a presence count fires on a dead exporter, so this replay is not proving the value read: {sorted(presence_counting)[:3]}"
    )
    # And that control's silence is a property of the EXPORTER route alone, not of the presence form:
    # on the Alloy route the series really is gone, so the count falls through its own fallback and
    # fires. Asserting it here is what makes the sentence above checkable -- a replay that modelled
    # the dead exporter as an absent series would turn the control green for the wrong reason.
    presence_on_alloy_route = _replay_dark_with_exposure(
        open_then_dark, alloy_goes_dark, lookback=lookback, hold_for=hold_for, span=span, b_form="presence"
    )
    assert presence_on_alloy_route, (
        "the presence form stays quiet even when the series is ABSENT, so this replay is not modelling the "
        "`or on() vector(0)` fallback and control 2 proves nothing"
    )


def test_the_dark_with_exposure_page_keeps_the_wording_two_reviews_argued_into_it():
    """The title must hold on BOTH routes this rule fires on: the primary's Alloy going dark trips
    `$B < 1` with the engine running fine, so a title asserting the engine is dark is false there,
    and a bare *exposure open* asserts a position the rule cannot see is still there. The summary
    names the discriminator because the page is read before any runbook is opened."""
    rule = _rule(_DARK_WITH_EXPOSURE)
    assert rule["title"] == _DARK_WITH_EXPOSURE_TITLE, f"the title no longer holds on both routes: {rule['title']!r}"
    summary = (rule.get("annotations") or {}).get("summary", "")
    assert _DARK_DISCRIMINATOR in summary, (
        f"the summary does not name {_DARK_DISCRIMINATOR!r}, so the page's first instruction is missing and a "
        f"responder may flatten a live position for a telemetry incident"
    )


# --- Drift ratchets --------------------------------------------------------------------------

# One section may legitimately serve several uids, and one rule may point at a procedure named for
# the host rather than the rule. Each entry is a decision, not a backlog: adding one is how you
# record a deliberate exception, and an empty diff here means no rule quietly drifted off-target.
_ANCHOR_EXCEPTIONS = {
    "zcrypto-reconcile-ledger-scan-slow": "reconcile-ledger-scan-cost",
    "zcrypto-reconcile-ledger-scan-critical": "reconcile-ledger-scan-cost",
    "zcrypto-alloy-dark-zaccess": "zaccess-bridgehead-dark",
}


def test_every_rule_routes_to_its_OWN_runbook_section() -> None:
    """Every rule's `Runbook:` link points at that rule's OWN section: a link that RESOLVES can still
    send the operator to a sibling rule's, which
    `test_every_runbook_link_in_an_alert_summary_resolves` cannot see.
    """
    wrong = []
    for rule in _rules():
        summary = (rule.get("annotations") or {}).get("summary", "")
        match = re.search(r"Runbook:\s*\S+?#(\S+?)\"?\s*$", summary.strip())
        assert match, f"{rule['uid']} carries no Runbook anchor"
        anchor, uid = match.group(1).rstrip('"'), rule["uid"]
        if anchor != _ANCHOR_EXCEPTIONS.get(uid, uid):
            wrong.append(f"{uid} -> #{anchor}")
    assert not wrong, (
        "these rules route to a section that is not their own; add a deliberate exception to "
        f"_ANCHOR_EXCEPTIONS or fix the anchor: {wrong}"
    )


# Grafana Cloud's free tier retains 14 days of metrics AND logs. A query past that does not error --
# it returns a SHORTER series -- so the window is truncated in silence and any figure derived from it
# is recorded at the width it asked for (`T0129`, resolved, re-derived two thresholds on that).
#
# There is DELIBERATELY no guard for it: computing a query's true reach means parsing PromQL and
# LogQL, and every partial parser built for it shipped a hole while reading as complete, which is
# worse than nothing because it licenses the belief that the class is covered. Re-measure the widest
# window in an audit; do not add a regex that claims to settle it.
