"""B2 trial 2's inputs half on the frozen ohlc-full set and the funding set against spec 00137's measured basis, and arm A
against records 45 and 50's stored figures: no bar, and no position or return of arm B."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost, calendar_year_slices
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the basis test's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
_BLOCK_HASH = "3da5e39721940924e481b802cffb7c30c03ea3165c2b16412b0c5402d0fc18a8"
_RETURN_INDICES = 27_337
_CLOSES_PER_YEAR = {
    "2013": 509,
    "2014": 2_190,
    "2015": 2_190,
    "2016": 2_195,
    "2017": 2_190,
    "2018": 2_183,
    "2019": 2_190,
    "2020": 2_196,
    "2021": 2_190,
    "2022": 2_190,
    "2023": 2_190,
    "2024": 2_195,
    "2025": 2_189,
    "2026": 540,
}
# Per asset: the closes holding a z-score, the first of them, and those in 2020.
_Z = {
    "ADA": (13_400, (2020, 2, 18, 8), 1_906),
    "AVAX": (11_918, (2020, 10, 22, 8), 424),
    "BTC": (13_512, (2020, 1, 30, 16), 2_018),
    "DOGE": (12_364, (2020, 8, 9, 0), 870),
    "DOT": (12_118, (2020, 9, 19, 0), 624),
    "ETH": (13_512, (2020, 1, 30, 16), 2_018),
    "LINK": (13_414, (2020, 2, 16, 0), 1_920),
    "LTC": (13_462, (2020, 2, 8, 0), 1_968),
    "SOL": (11_741, (2020, 10, 13, 8), 478),
    "XRP": (13_480, (2020, 2, 5, 0), 1_986),
}
_SOL_2022 = 1_959
ENGAGED_PER_ASSET = {
    "ADA": 372,
    "AVAX": 164,
    "BTC": 402,
    "DOGE": 326,
    "DOT": 347,
    "ETH": 454,
    "LINK": 336,
    "LTC": 458,
    "SOL": 210,
    "XRP": 417,
}
ENGAGED_PER_YEAR = dict.fromkeys(map(str, range(2013, 2020)), 0) | {
    "2020": 780,
    "2021": 1_189,
    "2022": 8,
    "2023": 572,
    "2024": 908,
    "2025": 27,
    "2026": 2,
}
# Records 48-50's arm A and benchmark, stored unrounded.
ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


def coverage() -> dict[str, dict[str, list[int]]]:
    """`binperp_funding_z30d_coverage` as the basis measured it."""
    out = {}
    for asset, (_, _, in_2020) in _Z.items():
        held = dict.fromkeys(map(str, range(2013, 2020)), 0) | {"2020": in_2020}
        if asset == "SOL":
            held["2022"] = _SOL_2022
        out[asset] = {year: [held.get(year, total), total] for year, total in _CLOSES_PER_YEAR.items()}
    return out


@pytest.fixture(scope="module")
def _reads():
    reader = ObservedReader(_DATA_ROOT)
    inputs = subjects._b2_inputs(reader, "ohlc-full", None, None, False, subject="b2-funding-derisk-full")
    return inputs, reader.block()


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_b2_full_inputs_reproduce_the_measured_basis(_reads):
    assert _DATA_ROOT == research_command._DATA_ROOT
    inputs, block = _reads
    assert compute_hash(block) == _BLOCK_HASH
    assert {dataset: (len(entry["files"]), entry["rows"], entry["span"]) for dataset, entry in block.items()} == {
        "derivatives-funding": (10, 68_281, ["2020-01-01 00:00:00+00:00", "2026-06-30 16:00:00+00:00"]),
        "ohlc-full": (10, 173_373, ["2013-09-10 20:00:00+00:00", "2026-03-31 20:00:00+00:00"]),
    }
    h4_ts, close, z = inputs.h4_ts, inputs.close, inputs.binperp_funding_z30d
    assert (len(h4_ts), h4_ts[0], h4_ts[-1]) == (
        27_338,
        datetime(2013, 9, 10, 20, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert sum(later - earlier != timedelta(hours=4) for earlier, later in zip(h4_ts, h4_ts[1:])) == 63
    assert (len(close), close[0], close[-1]) == (
        _RETURN_INDICES,
        datetime(2013, 9, 11, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert h4_ts[1380] == datetime(2014, 5, 26, tzinfo=UTC)
    k21 = next(k for k, t in enumerate(close) if t >= datetime(2021, 1, 1, tzinfo=UTC))
    assert (k21, _RETURN_INDICES - k21) == (15_843, 11_494)
    assert dict(Counter(str(t.year) for t in close)) == _CLOSES_PER_YEAR
    assert list(calendar_year_slices([0.0] * _RETURN_INDICES, h4_ts)) == [str(year) for year in range(2014, 2026)]

    for asset, (defined, first, _) in _Z.items():
        held = [k for k in range(_RETURN_INDICES) if z[asset][k] is not None]
        assert (len(held), close[held[0]], close[held[-1]]) == (defined, datetime(*first, tzinfo=UTC), close[-1]), asset
    assert subjects._b2_full_engagement(inputs) == {
        "engaged_per_asset": ENGAGED_PER_ASSET,
        "engaged_per_year": ENGAGED_PER_YEAR,
        "binperp_funding_z30d_coverage": coverage(),
    }
    assert (sum(p > 0 for positions in inputs.arm_a.values() for p in positions), sum(map(len, inputs.arm_a.values()))) == (
        93_462,
        273_370,
    )
    assert {s for scales in inputs.scales.values() for s in scales} == {0.5, 1.0}

    any_z = [any(z[a][k] is not None for a in z) for k in range(_RETURN_INDICES)]
    all_z = [all(z[a][k] is not None for a in z) for k in range(_RETURN_INDICES)]
    assert (any_z.index(True), any_z.count(False), any_z[1380:].count(False)) == (13_825, 13_825, 12_445)
    assert (all_z.index(True), all_z[k21:].count(True)) == (15_419, 11_263)
    sol = [close[k] for k in range(k21, _RETURN_INDICES) if z["SOL"][k] is None]
    assert (len(sol), sol[0], sol[-1]) == (231, datetime(2022, 11, 9, 20, tzinfo=UTC), datetime(2022, 12, 18, 4, tzinfo=UTC))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet"),
    reason="the frozen ohlc-full set or the derivatives-funding set is absent under data/",
)
def test_the_b2_full_arm_a_reproduces_records_45_and_50s_arm_a(_reads):
    inputs, _ = _reads
    net_a = net_of_cost(inputs.arm_a, subjects._b2_returns(inputs.h4_prices), cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a = book_turnover(inputs.arm_a)

    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / _RETURN_INDICES * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == ARM_A
    assert {key: _trials()[50]["metrics"][key] for key in ARM_A} == ARM_A
    assert {key: round(value, 2 if key == "turnover_a" else 4) for key, value in ARM_A.items()} == {
        key: _trials()[45]["metrics"][key] for key in ARM_A
    }
