"""Guard: a `keep` relabel drops every series it does not list (T0051), so a series missing from
the keep-regex does not go undashboarded -- it does not exist. These tests pin the regexes against
the series the stack actually publishes, so deleting one from the config fails here rather than
silently going dark in production."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NAS_ALLOY = REPO / "infra/nas/config.alloy"
# NOTE: files/, not templates/ — this config is installed with `ansible.builtin.copy`, which
# only ever searches a role's files/ dir. It lived in templates/ briefly and the copy task
# could not find it; the real converge caught that, no syntax check could.
OPS_ALLOY = REPO / "infra/ansible/roles/ops/files/config.alloy"
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"
ACCESS_ALLOY = REPO / "infra/ansible/roles/access/files/config.alloy"

# The series each host must ship. NAS: Role A/B (gate) + its host metrics. OPS: the four timer
# textfiles (written since OPS-3/OPS-4 but scraped by nothing until spec 00054 Task 1) plus the
# overlay writer's series (moved to this host by spec 00054 Task 6/OPS-5).
# T0048 defect 1: discovery.docker used to wedge permanently, and the ONLY positive signal was this
# counter going flat. `discovery.docker` is retired fleet-wide now (00068 D6/D8: capture T5, ops
# T6, NAS T8), so neither series exists on any host any more, and the alert that used to watch them
# (zcrypto-alloy-docker-sd-wedged) is gone too. Kept as named constants only so the
# excludes-the-retired-pair test below can reference them.
_SD_SERIES = "prometheus_sd_refresh_duration_seconds_count"
_SD_FAILURES = "prometheus_sd_refresh_failures_total"
# T0079: `up` is alert-bearing on EVERY host -- the four `Fleet · Alloy dark` rules fire on its
# silence (`count(up{...}) or on() vector(0)` below 1). Dropping it from any keep-list would leave
# that host's rule permanently unable to fire while still provisioned: green-when-blind, the same
# failure class the log-dead canaries exist to close. So it is pinned for all three configs, not
# just the two that happened to list it already.

# 00069 T6/T7: the app daemons' own `/metrics` series, admitted per host below. The six
# ProcessCollector families are shared by every app endpoint AND (per each config.alloy's own
# `exporter.self "alloy"` comment) admitted uniformly for Alloy's own self-scrape too -- the plan's
# earlier "shave Alloy down to a process pair" idea was dropped as machinery for nothing, so all
# three hosts admit the same six names (spec 00069 D5, cold-review -- a keep-list admitting four
# while the app publishes six is the T0051 admitted-but-unpublished trap in the other direction).
PROCESS_FAMILIES = [
    "process_cpu_seconds_total",
    "process_max_fds",
    "process_open_fds",
    "process_resident_memory_bytes",
    "process_start_time_seconds",
    "process_virtual_memory_bytes",
]
# The 00068 ship-handler internals, shared by every daemon that runs with `--ship-logs` (capture
# x2, engine, the liquidations poller) -- NOT the NAS, which runs no `--ship-logs`/`/metrics`
# daemon at all (its pull loop is shell).
LOGSHIP_SERIES = [
    "zcrypto_logship_dropped_lines_total",
    "zcrypto_logship_shipped_lines_total",
    "zcrypto_logship_last_success_timestamp_seconds",
    "zcrypto_logship_last_cycle_timestamp_seconds",
]
CAPTURE_APP_SERIES = [
    "zcrypto_capture_reconnects_total",
    "zcrypto_capture_resubscribes_total",
    "zcrypto_capture_segments_written_total",
    "zcrypto_capture_segment_bytes_total",
    "zcrypto_capture_rows_held_total",
    "zcrypto_capture_rows_quarantined_total",
    "zcrypto_capture_gap_seconds_total",
    # T0101: without these two here, dropping either from the producer or from the
    # keep-regex leaves every test green while the series goes dark -- the T0051 trap.
    "zcrypto_capture_seconds_since_last_book_message",
    "zcrypto_capture_venue_status_total",
    "zcrypto_capture_book_desynced",
    "zcrypto_capture_disk_watermark_breached",
]
# Scraped from the capture role's config.alloy on BOTH capture hosts (one file serves both,
# `engine_app` included on the secondary too even though nothing listens there -- see that file's
# own `engine_app` scrape comment).
ENGINE_APP_SERIES = [
    "zcrypto_engine_target_weight",
    "zcrypto_engine_orders_total",
    "zcrypto_engine_order_notional_eur",
    "zcrypto_engine_cycle_success",
    "zcrypto_engine_cycle_completed_at_seconds",
    "zcrypto_engine_cycle_duration_seconds",
    # T0124: the shadow book combines three sleeves at fixed 1/3 weights and two have been flat for
    # months. `active_sleeves` is alert-bearing (zcrypto-engine-sleeve-count-changed), so
    # dropping it from the keep-regex would leave that rule permanently NoData -- indistinguishable
    # from a composition that never changes. `sleeve_gross` is the per-sleeve detail the page's
    # responder reads to see WHICH sleeve moved.
    "zcrypto_engine_sleeve_gross",
    "zcrypto_engine_active_sleeves",
    # The execution safety envelope's published state (cli/engine/command.py's `_ExecGauges`).
    # Three are alert-bearing (zcrypto-engine-exec-armed-too-long, -exec-kill-tripped,
    # -exec-not-evaluated); dropping any of the six from the keep-regex leaves its dashboard panel
    # permanently NoData and, for the alerted three, the rule unable to ever fire.
    "zcrypto_exec_gate_level",
    "zcrypto_exec_armed",
    "zcrypto_exec_kill_tripped",
    "zcrypto_exec_venue_ok",
    "zcrypto_exec_last_evaluation_timestamp_seconds",
    "zcrypto_exec_restart_hold",
    # The attended-window execution instruments (cli/engine/command.py's `_ExecutionMetrics`), plus
    # the intent-side limit counter. None is alert-bearing by design, which is exactly why they are
    # pinned HERE: nothing else would notice them being dropped from the keep-regex, and an
    # execution board reading NoData through a live probe window is the failure this list exists to
    # stop -- the T0051 trap in the direction a rule-shaped guard cannot see.
    "zcrypto_exec_orders_total",
    "zcrypto_exec_fills_total",
    "zcrypto_exec_fees_eur_total",
    "zcrypto_exec_position",
    "zcrypto_exec_realized_pnl_eur",
    "zcrypto_engine_limit_bound_total",
    # 00089: venue truth -- the executor's ratified basket vs what Kraken's own instrument set and
    # constraints actually report. Two are alert-bearing (zcrypto-venue-concordance-failed,
    # zcrypto-venue-snapshot-stale); dropping any of the four from the keep-regex leaves the alerted
    # two unable to ever fire and all four invisible to the dashboard panel 00090's engine-board
    # metrics pass owes them (NOT_CHARTED in tests/test_dashboards_cover_metrics.py).
    "zcrypto_venue_snapshot_timestamp_seconds",
    "zcrypto_venue_instruments_loaded",
    "zcrypto_venue_instruments_expected",
    "zcrypto_venue_concordance_failures",
]
LIQUIDATIONS_APP_SERIES = [
    "zcrypto_liquidations_polls_total",
    "zcrypto_liquidations_api_errors_total",
    "zcrypto_liquidations_last_success_timestamp_seconds",
]

NAS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "zcrypto_gate_streak_days",
    *PROCESS_FAMILIES,
]
# ADMITTED by the NAS keep-regex but NOT published there any more: the overlay writer moved to the
# ops node (spec 00054 D2) and the NAS's stale reconcile/trade-backfill textfiles were deleted at
# the 2026-07-16 cutover, so these families publish from ops ONLY (the one-publisher invariant --
# a resurrected NAS twin would freeze and page the host-unscoped exporter-stale rule forever).
# They are listed separately so this guard never again claims the NAS "must ship" them: keeping
# them in the NAS regex is today's standing admission (asserted here so a trim is a conscious act,
# not silent drift), while trimming them -- so a hand-deploy regression (T0056) could never
# resurrect the frozen twin -- is a deliberate hardening decision that would move these entries
# out of this list, not a regression this test should block.
NAS_LEGACY_ADMITTED = [
    "zcrypto_reconcile_last_success_timestamp_seconds",
    "zcrypto_trade_backfill_exit_code",
]
# Names assembled at runtime never appear as literals, so the scan cannot derive them. cli/archive/
# command.py builds every reconcile series as f"zcrypto_reconcile_{name}", which yields only the
# meaningless stem below -- and `zcrypto_reconcile_.*` admits that stem vacuously while the thirteen
# real names are absent from the candidate set entirely. They are fed to BOTH the union guard and the
# per-host OPS list: the union bar alone would not catch the realistic drift, since narrowing the
# wildcard on ops -- the host that actually publishes them -- still leaves NAS's copy satisfying the
# union. A reviewer measured that: ops-only narrowing flagged 0 of 9.
INTERPOLATED_METRIC_NAMES = [
    # Verified by counting `_emit` call sites in cli/archive/command.py, not by trusting the previous
    # count: all thirteen. Includes last_success_timestamp_seconds, which the scan only ever picked up
    # because an unrelated comment in archive-pull.sh.j2 happens to spell it out -- accidental
    # coverage, not derivation.
    "zcrypto_reconcile_last_success_timestamp_seconds",
    # spec 00097: alert-bearing (the cycle-duration rule). Admitted today only by the same
    # `zcrypto_reconcile_.*` wildcard, so narrowing it must fail here rather than silently
    # NoData-ing the rule -- which renders identically to a healthy cycle.
    "zcrypto_reconcile_cycle_duration_seconds",
    # spec 00097: alert-ADJACENT -- the cycle-duration rule's runbook triage reads this gauge first,
    # to tell "the skip cache stopped engaging" from "the window's volume genuinely grew". It is the
    # only Prometheus-side observable of a cache that degrades silently (a pair dropped from capture
    # makes every window hour incomplete, and nothing errors), so a narrowed wildcard would blank the
    # discriminator during the page that sends the operator to it.
    "zcrypto_reconcile_hours_skipped",
    # spec 00096: was missing from this list until 2026-08-21 and reached the bar by NO path -- the
    # name appears nowhere under _SOURCE_GLOBS, so the scan cannot derive it either. It is where the
    # residual-gap alert summary sends triage, so a narrowed wildcard would have blanked the metric
    # the operator is told to open, during the page that tells them to.
    "zcrypto_reconcile_dark_episode_seconds_total",
    "zcrypto_reconcile_source_lag_seconds",
    "zcrypto_reconcile_healed_gap_seconds_total",
    "zcrypto_reconcile_healable_gap_seconds_total",
    "zcrypto_reconcile_residual_gap_seconds_total",
    "zcrypto_reconcile_spliced_hours_total",
    "zcrypto_reconcile_union_hours_total",
    "zcrypto_reconcile_trade_dedup_rows_total",
    "zcrypto_reconcile_trade_deficit_rows_total",
    "zcrypto_reconcile_ledger_records",
]

OPS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "ops_archive_pull_exit_code",
    "ops_archive_pull_last_success_timestamp",
    "ops_panel_exit_code",
    "ops_verify_replay_exit_code",
    # spec 00077: failed_hours/hours_total/run_ok are new series, and two of the three are now
    # alert-bearing. Admitted today only by the `ops_verify_replay_.*` wildcard -- pinned by name
    # so narrowing that wildcard fails here rather than silently NoData-ing both new rules.
    "ops_verify_replay_failed_hours",
    "ops_verify_replay_hours_total",
    "ops_verify_replay_run_ok",
    # spec 00078: the incremental sweep's census. `pending_hours` is alert-bearing (the backlog-stuck
    # rule) and `duration_seconds` is the runway trend the whole spec exists to make observable --
    # both admitted today only by the same `ops_verify_replay_.*` wildcard, so narrowing it must fail
    # here rather than silently NoData-ing the rule and flat-lining the trend.
    "ops_verify_replay_replayed_hours",
    "ops_verify_replay_reused_hours",
    "ops_verify_replay_pending_hours",
    "ops_verify_replay_duration_seconds",
    # The audit-mismatch count: on that run the summary is withheld, so run_ok=0 is the only other
    # trace and it cannot tell a mismatch from a crash.
    "ops_verify_replay_audit_mismatches",
    "ops_verified_replay_exit_code",
    "ops_verified_replay_last_success_timestamp",
    # The "did the timer RUN?" discriminator. Absent from the ops keep-regex until 2026-07-28 while
    # capture carried it, so on the host running four timers it was published and dropped at
    # remote-write -- found by a reviewer checking a coverage claim that turned out to be false.
    "node_textfile_mtime_seconds",
    "zcrypto_trade_backfill_exit_code",
    "zcrypto_trade_backfill_last_success_timestamp",
    *INTERPOLATED_METRIC_NAMES,
    # T0043: the repair count, exported as a monotone total by archive-pull.sh.j2. Admitted today
    # only by the `zcrypto_trade_backfill_.*` wildcard — pinned by name so narrowing that wildcard
    # fails here rather than silently dropping the series.
    "zcrypto_trade_backfill_hours_repaired_after_loss_total",
    # spec 00087: the tape-bars materializer's gauges. Admitted today only by the
    # `zcrypto_tapebars_.*` wildcard, and the alert-bearing ones are pinned by name because this
    # timer's failure mode is a GREEN SILENCE -- the not-yet-healed path exits 0 by design, so
    # narrowing that wildcard would disarm the only two signals that can see a stalled healer:
    # days_gap (a day just became permanently unpublishable, and nothing else will ever say so) and
    # last_publish (the dataset stopped growing while every run kept exiting clean).
    "zcrypto_tapebars_exit_code",
    "zcrypto_tapebars_days_gap",
    "zcrypto_tapebars_last_success_timestamp_seconds",
    "zcrypto_tapebars_last_publish_timestamp_seconds",
    # T0083: the hc.io watchdog scrape's series. zcrypto-hcio-watchdog alerts on
    # hc_checks_down_total — dropping THAT silently disarms the Grafana half of the mutual
    # watchdog (same failure class as `up` above); hc_check_up is the per-check triage detail
    # the page's responder reads. Names read from the live hc.io Prometheus endpoint
    # 2026-07-21 — the endpoint exposes hc_checks_down_total, NOT the bare hc_checks_down a
    # reasonable guess produces.
    "hc_check_up",
    "hc_checks_down_total",
    *LIQUIDATIONS_APP_SERIES,
    *LOGSHIP_SERIES,
    *PROCESS_FAMILIES,
    # D11: the ops-side tunnel/cert probe (access_ops role) publishes the SAME two names the
    # bridgehead does (ACCESS_APP_SERIES below) -- host="ops" vs host="zaccess" tells them apart.
    "zaccess_wireguard_handshake_age_seconds",
    "zaccess_tls_not_after_seconds",
]
# The capture host's own alert-bearing families (cold-review Important 2): `Capture · spool disk
# low` (alerts.yaml:1442-1443) reads node_filesystem_avail_bytes/node_filesystem_size_bytes, and
# `Capture · node load high` (alerts.yaml:1486-1488) reads node_load1/node_cpu_seconds_total --
# all four already pass today's keep-regex, but the CAPTURE_REQUIRED list that used to carry only
# `up` (with a comment admitting capture had no FULL required-list) read as authoritative once it
# grew long, while these four alert-bearing names stayed unpinned. Pinned now so a future keep-list
# edit that drops one fails here instead of silently disarming that alert.
# One-off timers publish a .prom, not a /metrics endpoint (spec 00071 D1) -- a daily oneshot runs
# for a second and has no process to scrape. The keep-regex is an ALLOW-list with no `node_.*`
# wildcard (D2), so a published-but-unadmitted series is dropped at the remote-write boundary and
# looks exactly like a producer that never ran. That is not hypothetical: it is how T0021's prune
# came to be observable through nothing. Pinned here so the keep-list edit is TDD-gated.
ONEOFF_TEXTFILE_SERIES = [
    "node_reboot_required",
    # A MALFORMED .prom raises this; a STALE one does not (D3).
    "node_textfile_scrape_error",
    # ...staleness is `node_textfile_mtime_seconds{file=...}`, which the collector emits for EVERY
    # .prom it reads. Free, standard, and the only signal that distinguishes "the timer stopped" from
    # "the timer ran and had nothing to report" -- a stopped timer leaves its last file in place and
    # the collector serves those values forever.
    "node_textfile_mtime_seconds",
    "zcrypto_engine_journal_prune_deleted_days",
    "zcrypto_engine_journal_prune_kept_days",
    "zcrypto_engine_journal_prune_oldest_day_age_seconds",
    "zcrypto_engine_journal_prune_last_run_timestamp_seconds",
]

CAPTURE_REQUIRED = [
    "up",
    "node_load1",
    "node_cpu_seconds_total",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    *ONEOFF_TEXTFILE_SERIES,
    *CAPTURE_APP_SERIES,
    *ENGINE_APP_SERIES,
    *LOGSHIP_SERIES,
    *PROCESS_FAMILIES,
]

# The bridgehead's own probe-textfile series (zaccess-probe.sh.j2, spec 00075 D11): WireGuard
# tunnel handshake age + edge TLS cert notAfter, per target.
ACCESS_APP_SERIES = [
    "zaccess_wireguard_handshake_age_seconds",
    "zaccess_tls_not_after_seconds",
]

# Native Alloy (D11, apt package, no docker) -- no `prometheus.exporter.self "alloy"` component in
# this config (mirror-the-ops-shape stops at unix exporter + textfile + scrape + keep +
# remote_write), so unlike NAS/OPS/CAPTURE this host does NOT admit PROCESS_FAMILIES: nothing here
# publishes them, and admitting an unpublished family is the T0051 trap in the other direction (see
# the exclusion test below). Every name in this list is spelled out individually in the keep-regex
# (files/config.alloy) -- no wildcards on this small a host -- so every one of them is pinned here.
ACCESS_REQUIRED = [
    "up",
    "node_load1",
    "node_cpu_seconds_total",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemTotal_bytes",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    "node_network_receive_bytes_total",
    "node_network_transmit_bytes_total",
    # The `Node · a node-exporter collector is failing` rule (alerts.yaml) evaluates
    # `min by (host) (node_scrape_collector_success)` with no host selector -- meant to cover
    # every host. Without this admitted here, zaccess is structurally invisible to that rule.
    "node_scrape_collector_success",
    # The did-the-timer-RUN discriminators (the ops green-when-blind lesson, 2026-07-28): without
    # them a dead probe timer serves its last gauges forever and the tunnel-stale/cert alerts can
    # never fire.
    "node_textfile_mtime_seconds",
    "node_textfile_scrape_error",
    *ACCESS_APP_SERIES,
]


def _keep_regex(path: Path) -> re.Pattern:
    """Extract the `keep` write_relabel_config's regex from an Alloy config."""
    text = path.read_text()
    blocks = re.findall(r"write_relabel_config\s*\{(.*?)\}", text, re.DOTALL)
    keeps = [b for b in blocks if "action" in b and '"keep"' in b]
    assert len(keeps) == 1, f"{path}: expected exactly one keep block, found {len(keeps)}"
    m = re.search(r'regex\s*=\s*"([^"]+)"', keeps[0])
    assert m, f"{path}: keep block has no regex"
    # Prometheus relabel regexes are fully anchored.
    return re.compile(r"\A(?:" + m.group(1) + r")\Z")


def _drop_regex(path: Path) -> re.Pattern:
    """Extract the `drop` write_relabel_config's regex from an Alloy config."""
    text = path.read_text()
    blocks = re.findall(r"write_relabel_config\s*\{(.*?)\}", text, re.DOTALL)
    drops = [b for b in blocks if "action" in b and '"drop"' in b]
    assert len(drops) == 1, f"{path}: expected exactly one drop block, found {len(drops)}"
    m = re.search(r'regex\s*=\s*"([^"]+)"', drops[0])
    assert m, f"{path}: drop block has no regex"
    # Prometheus relabel regexes are fully anchored.
    return re.compile(r"\A(?:" + m.group(1) + r")\Z")


@pytest.mark.parametrize(
    ("path", "required"),
    [
        (NAS_ALLOY, NAS_REQUIRED + NAS_LEGACY_ADMITTED),
        (OPS_ALLOY, OPS_REQUIRED),
        (CAPTURE_ALLOY, CAPTURE_REQUIRED),
        (ACCESS_ALLOY, ACCESS_REQUIRED),
    ],
    ids=["nas", "ops", "capture", "access"],
)
def test_keep_regex_admits_every_published_series(path, required):
    keep = _keep_regex(path)
    missing = [s for s in required if not keep.match(s)]
    assert not missing, f"{path}: keep-regex drops {missing} -- those series will NOT exist"


@pytest.mark.parametrize(
    ("path", "required"),
    [
        (NAS_ALLOY, NAS_REQUIRED + NAS_LEGACY_ADMITTED),
        (OPS_ALLOY, OPS_REQUIRED),
        (CAPTURE_ALLOY, CAPTURE_REQUIRED),
        (ACCESS_ALLOY, ACCESS_REQUIRED),
    ],
    ids=["nas", "ops", "capture", "access"],
)
def test_drop_regex_does_not_shadow_the_keep_list(path, required):
    """The D4 mechanism this task exists to implement (00069 T6/T7): the drop rule used to discard
    `process_.*` fleet-wide before the keep stage ever saw it. `test_keep_regex_admits_every_
    published_series` above only checks the keep-regex in isolation, so reverting the drop rule to
    re-admit `process_.*` (undoing D4 entirely) left that test -- and the whole suite -- green: the
    keep-regex still matches `process_cpu_seconds_total` on its own, it just never gets the chance
    to see it. This test runs both stages in order, the way remote_write actually does."""
    drop = _drop_regex(path)
    shadowed = [s for s in required if drop.match(s)]
    assert not shadowed, f"{path}: the drop rule eats {shadowed} before the keep stage sees them"


@pytest.mark.parametrize(
    ("path", "excluded"),
    [
        # No daemon runs on the NAS at all (00069 T7) -- none of the app/logship families exist there.
        (NAS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
        # The poller runs on ops, not capture or engine.
        (OPS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES]),
        # Capture/engine run on the capture hosts, not the poller.
        (CAPTURE_ALLOY, LIQUIDATIONS_APP_SERIES),
        # No app daemon runs on the bridgehead, and (D11) no `exporter.self "alloy"` component
        # either -- none of the app/logship/process families exist there.
        (ACCESS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES, *PROCESS_FAMILIES]),
    ],
    ids=["nas", "ops", "capture", "access"],
)
def test_keep_regex_excludes_families_not_published_on_this_host(path, excluded):
    """T0051, the other direction (00069 T6/T7): admitting a family this host never publishes is
    not merely wasted machinery -- it is silent go-ahead for a future daemon addition to ship
    there unreviewed."""
    keep = _keep_regex(path)
    admitted = [s for s in excluded if keep.match(s)]
    assert not admitted, f"{path}: keep-regex admits {admitted}, which nothing on this host publishes"


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY], ids=["nas", "ops", "capture", "access"])
def test_keep_regex_excludes_the_retired_sd_pair(path):
    """00068 D6/D8: discovery.docker is gone fleet-wide (capture T5, ops T6, NAS T8), so admitting
    its series anywhere is the T0051 admitted-but-unpublished trap."""
    keep = _keep_regex(path)
    assert not keep.match(_SD_SERIES) and not keep.match(_SD_FAILURES)


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY], ids=["nas", "ops", "capture", "access"])
def test_alloy_self_metrics_are_dropped_before_the_keep(path):
    """Defence in depth, and the ordering matters: the drop must precede the keep."""
    text = path.read_text()
    drop_at = text.find('"drop"')
    keep_at = text.find('"keep"')
    assert drop_at != -1, f"{path}: no drop block"
    assert keep_at != -1, f"{path}: no keep block"
    assert drop_at < keep_at, f"{path}: the drop block must come before the keep block"


# ---------------------------------------------------------------------------
# The lists above are hand-maintained, which bounds what they can catch: they prove the keep-regex
# still admits the series someone remembered to list. They cannot see a metric added to the code and
# to no list -- and since the keep is an allow-list, that metric is dropped at remote_write and any
# rule watching it reads no data forever, which renders identically to healthy.
#
# This guard closes that gap by DERIVING its candidates from the source tree. Two things it must get
# right, both learned by getting them wrong on 2026-07-28:
#   1. Membership is MATCHED, not compared -- keep entries are regexes, and the NAS admits the whole
#      gate family as `zcrypto_gate_.*`. A literal comparison called all ten unadmitted; all are live.
#   2. The union of all three configs is the bar, since a metric may legitimately be admitted only on
#      the host that publishes it.
# It cannot see a host running an older config than the repo -- that is a converge concern, not CI.
# Scope is `zcrypto_*` only: the ops_*, node_* and hc_* families this infra also publishes are out
# of range, and an uppercase name would fall out of the token pattern rather than fail. Both are
# fail-open gaps. The per-host lists above cover them only as far as someone remembered to list the
# name -- `node_textfile_mtime_seconds` sat outside both this guard and the ops list while ops
# published it, so do not read those lists as coverage.
_SOURCE_GLOBS = ("cli/**/*.py", "infra/**/*.j2", "infra/**/*.sh", "infra/**/*.py")

# Name-shaped tokens that are not published metrics. Each states why: an unexamined exclusion is how
# the trap grows back.

NOT_A_PUBLISHED_METRIC = {
    "zcrypto_ed25519",  # the vaulted deploy-key filename in infra/ansible/scripts/run.sh
    "zcrypto_owned",  # the logger-ownership marker in cli/logging/config.py, never exported
    "zcrypto_reconcile_",  # the f-string STEM, not a series -- the real names are listed above
    # Named only in a cli/obs/metrics.py comment explaining why it is SUPPRESSED: prometheus_client
    # adds a `_created` series per Counter by default and `_use_created = False` disables them
    # process-wide. Confirmed absent from Grafana Cloud, as intended.
    "zcrypto_engine_orders_created",
}


def _tokens_in_tree() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for glob in _SOURCE_GLOBS:
        for path in REPO.glob(glob):
            for m in re.finditer(r"zcrypto_[a-z0-9_]{4,}", path.read_text()):
                found.setdefault(m.group(0), set()).add(str(path.relative_to(REPO)))
    return found


# Deliberately a shape match over the whole source, not a scan of definition sites: scanning
# `MetricFamily(` and `# HELP` misses how cli/engine/command.py, cli/liquidations/coinalyze.py and
# archive-pull.sh.j2 each publish, and a guard with blind spots is worse than none.
PUBLISHED_METRIC_NAMES = sorted({n for n in _tokens_in_tree() if n not in NOT_A_PUBLISHED_METRIC} | set(INTERPOLATED_METRIC_NAMES))

# pytest SKIPS an empty parametrize by default, so a glob that stops matching (a cli/ reorg, a
# rename) would silently evaporate this guard with the suite still green. The floor is deliberately
# a real count, not `> 0`: the staleness test below cannot serve as the backstop, since emptying
# NOT_A_PUBLISHED_METRIC makes it pass vacuously too.
assert len(PUBLISHED_METRIC_NAMES) >= 30, (
    f"only {len(PUBLISHED_METRIC_NAMES)} metric names found -- the source globs have drifted and this guard would pass vacuously"
)


def test_the_not_a_published_metric_list_has_not_gone_stale():
    """An exclusion naming a token no longer in the tree excuses nothing while the name it was
    renamed to goes unguarded."""
    stale = NOT_A_PUBLISHED_METRIC - set(_tokens_in_tree())
    assert not stale, f"excluded but no longer in the tree (rename? removal?): {sorted(stale)}"


@pytest.mark.parametrize("metric", PUBLISHED_METRIC_NAMES)
def test_every_published_metric_is_admitted_by_some_hosts_keep_regex(metric):
    keeps = [_keep_regex(p) for p in (NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY)]
    assert any(k.match(metric) for k in keeps), (
        f"{metric} is published by this repo but matches no keep-regex on any host, so it is "
        f"dropped silently at remote_write and any rule watching it reads no data forever. Add it "
        f"to the keep-regex of the host that publishes it, or -- if it is not a metric -- to "
        f"NOT_A_PUBLISHED_METRIC with the reason."
    )
