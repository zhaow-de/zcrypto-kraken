"""The B2 trial's pre-flight on the data root the run reads: the subject's inputs half -- arm A's positions, the funding
feature and the scales, no return of arm B -- reproduces spec 00128's measured basis, and its block is the one that spec
names, so a re-promotion of the rolling set or the funding set fails here by design."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.alpha.b2 import per_year_engaged_counts
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig, build_crossfreq_system_fast
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

_WINDOW = ("2020-09-22 00:00:00+00:00", "2026-06-30 23:59:59+00:00")
_AS_OF = "2026-10-10"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "500b55ea53eee9f4601f8d0f8dda6c1197dd048fdac5975ef4cb4c2e220be1b0"
_RETURN_INDICES = 12_645
_ENGAGED_PER_ASSET = {
    "ADA": 311,
    "AVAX": 164,
    "BTC": 350,
    "DOGE": 318,
    "DOT": 347,
    "ETH": 344,
    "LINK": 304,
    "LTC": 334,
    "SOL": 210,
    "XRP": 323,
}
_ENGAGED_PER_YEAR = {"2020": 283, "2021": 1_189, "2022": 8, "2023": 572, "2024": 908, "2025": 27, "2026": 18}


@pytest.mark.skipif(
    nothing_found_under(Path("data"), "ohlc-rolling/index/2026/10/10.json")
    or nothing_found_under(Path("data"), "derivatives-funding/*/funding.parquet"),
    reason="the rolling set's 2026-10-10 line or the derivatives-funding set is absent under data/",
)
def test_the_b2_inputs_reproduce_the_measured_basis_and_arm_a_is_the_builders_a2_sleeve():
    assets = CrossfreqSystemConfig().assets
    reader = ObservedReader(research_command._DATA_ROOT)
    inputs = subjects._b2_inputs(reader, "ohlc-rolling", _WINDOW, _AS_OF, True)
    assert compute_hash(reader.block()) == _BLOCK_HASH

    assert len(inputs.close) == _RETURN_INDICES
    for series in (inputs.arm_a, inputs.binperp_funding_z30d, inputs.scales):
        assert {a: len(values) for a, values in series.items()} == dict.fromkeys(assets, _RETURN_INDICES)
    assert sum(p > 0 for a in assets for p in inputs.arm_a[a]) == 67_093
    assert sum(len(positions) for positions in inputs.arm_a.values()) == 126_450
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(inputs.arm_a[a], inputs.scales[a])) for a in assets}
    assert engaged == _ENGAGED_PER_ASSET
    assert per_year_engaged_counts(inputs.arm_a, inputs.scales, inputs.close) == _ENGAGED_PER_YEAR
    assert sum(engaged.values()) == 3_005
    defined = {a: sum(z is not None for z in inputs.binperp_funding_z30d[a]) for a in assets}
    assert defined == dict.fromkeys(assets, _RETURN_INDICES) | {"AVAX": 12_464, "SOL": 12_287}
    assert {s for a in assets for s in inputs.scales[a]} == {0.5, 1.0}

    daily_ts, daily_prices = subjects._capturing_union(reader, "ohlc-rolling", 1440, _WINDOW, _AS_OF, True)
    sleeve = build_crossfreq_system_fast(daily_prices, daily_ts, inputs.h4_prices, inputs.h4_ts).sleeve_positions["A2"]
    assert max(abs(sleeve[a][k] - inputs.arm_a[a][k]) for a in assets for k in range(_RETURN_INDICES)) <= 1e-12
