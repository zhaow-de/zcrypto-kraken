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
]
CAPTURE_APP_SERIES = [
    "zcrypto_capture_reconnects_total",
    "zcrypto_capture_resubscribes_total",
    "zcrypto_capture_segments_written_total",
    "zcrypto_capture_segment_bytes_total",
    "zcrypto_capture_rows_held_total",
    "zcrypto_capture_rows_quarantined_total",
    "zcrypto_capture_gap_seconds_total",
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
OPS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "ops_archive_pull_exit_code",
    "ops_archive_pull_last_success_timestamp",
    "ops_panel_exit_code",
    "ops_verify_replay_exit_code",
    "ops_verified_replay_exit_code",
    "ops_verified_replay_last_success_timestamp",
    "zcrypto_reconcile_last_success_timestamp_seconds",
    "zcrypto_reconcile_source_lag_seconds",
    "zcrypto_trade_backfill_exit_code",
    "zcrypto_trade_backfill_last_success_timestamp",
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
]
CAPTURE_REQUIRED = ["up", *CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LOGSHIP_SERIES, *PROCESS_FAMILIES]


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


@pytest.mark.parametrize(
    ("path", "required"),
    [
        (NAS_ALLOY, NAS_REQUIRED + NAS_LEGACY_ADMITTED),
        (OPS_ALLOY, OPS_REQUIRED),
        (CAPTURE_ALLOY, CAPTURE_REQUIRED),
    ],
    ids=["nas", "ops", "capture"],
)
def test_keep_regex_admits_every_published_series(path, required):
    keep = _keep_regex(path)
    missing = [s for s in required if not keep.match(s)]
    assert not missing, f"{path}: keep-regex drops {missing} -- those series will NOT exist"


@pytest.mark.parametrize(
    ("path", "excluded"),
    [
        # No daemon runs on the NAS at all (00069 T7) -- none of the app/logship families exist there.
        (NAS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES, *LIQUIDATIONS_APP_SERIES, *LOGSHIP_SERIES]),
        # The poller runs on ops, not capture or engine.
        (OPS_ALLOY, [*CAPTURE_APP_SERIES, *ENGINE_APP_SERIES]),
        # Capture/engine run on the capture hosts, not the poller.
        (CAPTURE_ALLOY, LIQUIDATIONS_APP_SERIES),
    ],
    ids=["nas", "ops", "capture"],
)
def test_keep_regex_excludes_families_not_published_on_this_host(path, excluded):
    """T0051, the other direction (00069 T6/T7): admitting a family this host never publishes is
    not merely wasted machinery -- it is silent go-ahead for a future daemon addition to ship
    there unreviewed."""
    keep = _keep_regex(path)
    admitted = [s for s in excluded if keep.match(s)]
    assert not admitted, f"{path}: keep-regex admits {admitted}, which nothing on this host publishes"


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY], ids=["nas", "ops", "capture"])
def test_keep_regex_excludes_the_retired_sd_pair(path):
    """00068 D6/D8: discovery.docker is gone fleet-wide (capture T5, ops T6, NAS T8), so admitting
    its series anywhere is the T0051 admitted-but-unpublished trap."""
    keep = _keep_regex(path)
    assert not keep.match(_SD_SERIES) and not keep.match(_SD_FAILURES)


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY], ids=["nas", "ops", "capture"])
def test_alloy_self_metrics_are_dropped_before_the_keep(path):
    """Defence in depth, and the ordering matters: the drop must precede the keep."""
    text = path.read_text()
    drop_at = text.find('"drop"')
    keep_at = text.find('"keep"')
    assert drop_at != -1, f"{path}: no drop block"
    assert keep_at != -1, f"{path}: no keep block"
    assert drop_at < keep_at, f"{path}: the drop block must come before the keep block"
