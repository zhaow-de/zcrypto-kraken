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
# T0048 defect 1: discovery.docker can wedge permanently and the ONLY positive signal is this
# counter going flat -- a hang logs nothing, so without it the failure is silent for hours until the
# dead-man fires. NAS and ops still run discovery.docker (unlike capture, retired by 00068 D6), so
# this is still genuinely published there -- dropping it from either keep-list would silently
# regress a series that exists (T0051), even though the alert that used to watch it fleet-wide
# (zcrypto-alloy-docker-sd-wedged) retired alongside capture's copy (00068 D8).
_SD_SERIES = "prometheus_sd_refresh_duration_seconds_count"
# The disambiguator: a CLIMBING failures counter means a persistently erroring refresh, not a
# hang -- identical symptom, different cause. Shipping it is what makes the two separable.
_SD_FAILURES = "prometheus_sd_refresh_failures_total"
# T0079: `up` is alert-bearing on EVERY host -- the four `Fleet · Alloy dark` rules fire on its
# silence (`count(up{...}) or on() vector(0)` below 1). Dropping it from any keep-list would leave
# that host's rule permanently unable to fire while still provisioned: green-when-blind, the same
# failure class the log-dead canaries exist to close. So it is pinned for all three configs, not
# just the two that happened to list it already.

NAS_REQUIRED = [
    _SD_SERIES,
    _SD_FAILURES,
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "zcrypto_gate_streak_days",
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
    _SD_SERIES,
    _SD_FAILURES,
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


@pytest.mark.parametrize(
    ("path", "required"),
    [
        (NAS_ALLOY, NAS_REQUIRED + NAS_LEGACY_ADMITTED),
        (OPS_ALLOY, OPS_REQUIRED),
        # capture still has no FULL required-list (pre-existing gap), but every series an alert
        # depends on is pinned: `up`, for the two Fleet · Alloy dark rules scoped to
        # host="zcrypto" / host="zcrypto-red" (T0079). The SD pair is deliberately NOT required
        # here any more (00068 D6/D8): `discovery.docker` -- their only producer -- is retired on
        # this host, so admitting them would be a keep-list entry for a series that cannot exist
        # (the T0051 trap), and the alert that watched them (zcrypto-alloy-docker-sd-wedged) is
        # gone too.
        (CAPTURE_ALLOY, ["up"]),
    ],
    ids=["nas", "ops", "capture"],
)
def test_keep_regex_admits_every_published_series(path, required):
    keep = _keep_regex(path)
    missing = [s for s in required if not keep.match(s)]
    assert not missing, f"{path}: keep-regex drops {missing} -- those series will NOT exist"


def test_capture_keep_regex_excludes_the_retired_sd_pair():
    """00068 D6/D8: discovery.docker is gone on capture, so admitting its series is the T0051
    admitted-but-unpublished trap. Generalizes to nas/ops once Tasks 6/8 land."""
    keep = _keep_regex(CAPTURE_ALLOY)
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
