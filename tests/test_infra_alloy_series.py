"""Guard: a `keep` relabel drops every series it does not list (T0051), so a series missing from
the keep-regex does not go undashboarded -- it does not exist. These tests pin the regexes against
the series the stack actually publishes, so deleting one from the config fails here rather than
silently going dark in production."""

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NAS_ALLOY = REPO / "infra/nas/config.alloy"
OPS_ALLOY = REPO / "infra/ansible/roles/ops/templates/config.alloy.j2"

# The series each host must ship. NAS: Role A/B (gate) + its host metrics. OPS: the four timer
# textfiles (written since OPS-3/OPS-4 but scraped by nothing until spec 00054 Task 1) plus the
# overlay writer's series, which move to this host in Task 6.
NAS_REQUIRED = [
    "up",
    "node_load1",
    "node_filesystem_avail_bytes",
    "zcrypto_gate_streak_days",
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
    [(NAS_ALLOY, NAS_REQUIRED), (OPS_ALLOY, OPS_REQUIRED)],
    ids=["nas", "ops"],
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
