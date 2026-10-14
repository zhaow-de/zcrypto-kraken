"""Records 45 and 46, B1's trials 1 and 2, re-derived by their subjects over ohlc-full at the precision their lost writer
stored (docs/specs/00130 D4): a moved metric, a moved input file or a moved verdict fails here, where the data is."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.registry import TrialRegistry
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research.subjects import SUBJECTS
from tests.test_trial_registry_provenance import REGISTRY

pytestmark = pytest.mark.data

_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# The lost writer's decimals (docs/specs/00130's measured basis): 4 unless named; ints and per-year dicts exact.
_DECIMALS = {
    "dsr_corrected": 5,
    "per_period_sharpe_4h": 5,
    "turnover_a": 2,
    "turnover_b": 2,
    "turnover_reduction_pct": 2,
    "head_to_head_mean_outperf_2016": 9,
}


def _matrix(m: dict) -> str:
    """docs/specs/00045's decision matrix, the from-2016 read primary: the test's check, no subject's rule."""
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_2016"] > 0:
        if m["head_to_head_spa_p_2016"] < 0.05:
            return "adopt"
        if m["turnover_reduction_pct"] >= 20:
            return "park"
    return "reject"


def _stored(key: str, value):
    return round(value, _DECIMALS.get(key, 4)) if isinstance(value, float) else value


@pytest.mark.parametrize(
    ("trial_id", "name", "block_hash"),
    [
        pytest.param(
            45,
            "b1-conditioning",
            "349b04f3808e6364ff6a3b60f13b306d50c4157a6cc43530f5502a8122edf520",
            marks=pytest.mark.skipif(
                not (_DATA_ROOT / "ohlc-15m").is_dir(), reason="data/ohlc-15m absent — the reproduction runs on the data host only"
            ),
            id="record-45",
        ),
        pytest.param(46, "b1-window-only", "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69", id="record-46"),
    ],
)
@pytest.mark.skipif(
    not (_DATA_ROOT / "ohlc-full").is_dir(), reason="data/ohlc-full absent — the reproduction runs on the data host only"
)
def test_the_b1_subject_reproduces_its_record(trial_id, name, block_hash):
    record = {r.trial_id: r for r in TrialRegistry(REGISTRY).records}[trial_id]
    reader = ObservedReader(_DATA_ROOT)
    metrics = SUBJECTS[name].build(reader, "ohlc-full", None)

    assert compute_hash(reader.block()) == block_hash
    assert set(metrics) == set(record.metrics)
    assert {key: _stored(key, value) for key, value in metrics.items()} == record.metrics
    assert _matrix(metrics) == record.verdict


@pytest.mark.parametrize(
    ("passes", "outperf", "p_value", "turnover_cut", "verdict"),
    [
        pytest.param(0, 1e-06, 0.0, 50.0, "reject", id="the-bar-fails"),
        pytest.param(1, 0.0, 0.0, 50.0, "reject", id="no-outperformance"),
        pytest.param(1, 1e-06, 0.049, 0.0, "adopt", id="significant"),
        pytest.param(1, 1e-06, 0.05, 20.0, "park", id="turnover-down-20"),
        pytest.param(1, 1e-06, 0.05, 19.99, "reject", id="the-open-case"),
    ],
)
def test_the_matrix_gives_each_leaf_its_verdict(passes, outperf, p_value, turnover_cut, verdict):
    metrics = {
        "passes": passes,
        "head_to_head_mean_outperf_2016": outperf,
        "head_to_head_spa_p_2016": p_value,
        "turnover_reduction_pct": turnover_cut,
    }

    assert _matrix(metrics) == verdict
