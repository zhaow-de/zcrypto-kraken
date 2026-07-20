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
# dead-man fires. It is alerted on (zcrypto-alloy-docker-sd-wedged), so dropping it from a keep-list
# would silently disarm that alert rather than merely lose a graph.
_SD_SERIES = "prometheus_sd_refresh_duration_seconds_count"

NAS_REQUIRED = [
    _SD_SERIES,
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
        # capture has no full required-list here (pre-existing gap), but it runs discovery.docker on
        # both hosts and so is covered by the same alert -- pin the series that alert depends on.
        (CAPTURE_ALLOY, [_SD_SERIES]),
    ],
    ids=["nas", "ops", "capture"],
)
def test_keep_regex_admits_every_published_series(path, required):
    keep = _keep_regex(path)
    missing = [s for s in required if not keep.match(s)]
    assert not missing, f"{path}: keep-regex drops {missing} -- those series will NOT exist"


@pytest.mark.parametrize("path", [NAS_ALLOY, OPS_ALLOY], ids=["nas", "ops"])
def test_alloy_self_metrics_are_dropped_before_the_keep(path):
    """Defence in depth, and the ordering matters: the drop must precede the keep."""
    text = path.read_text()
    drop_at = text.find('"drop"')
    keep_at = text.find('"keep"')
    assert drop_at != -1, f"{path}: no drop block"
    assert keep_at != -1, f"{path}: no keep block"
    assert drop_at < keep_at, f"{path}: the drop block must come before the keep block"
