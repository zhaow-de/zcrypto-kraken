"""B1 trial 5's reads half and interior hourly closes against spec 00135's measured basis, computing no state, and arm A
against records 48 and 49's stored figures, run only after the spec's hash."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b1_exit import interior_closes_by_asset
from cli.alpha.b2 import net_of_cost
from cli.portfolio.crossfreq_system import _ffill_btc
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_BLOCK_HASH = "8216f4db47db18c63c78a9225e59cf0c44ba703c3881af22acdb9d315d3849a1"
_H1, _H4 = timedelta(hours=1), timedelta(hours=4)
_LAST_HOUR = datetime(2026, 3, 31, 23, tzinfo=UTC)
# Per asset, from the spec's measured basis: hourly rows, first hour, missing hours of the grid to the last, those inside a
# present 240 bar's span; over each 240 bar after the first, the count holding 0..3 interior hourly closes; the union-adjacent
# intervals and those holding all three; the 240 bars holding the hourly bar 3h in.
_BASIS = {
    "ADA": (65_623, (2018, 9, 28, 13), 172, 161, {0: 3, 1: 10, 2: 92, 3: 16_340}, (16_444, 16_340), 16_407),
    "AVAX": (37_157, (2021, 12, 21, 15), 316, 303, {0: 2, 1: 10, 2: 183, 3: 9_169}, (9_362, 9_169), 9_274),
    "BTC": (108_786, (2013, 9, 10, 23), 1_255, 542, {0: 28, 1: 111, 2: 98, 3: 27_094}, (27_326, 27_093), 27_197),
    "DOGE": (53_237, (2019, 12, 19, 14), 1_829, 1_603, {0: 42, 1: 266, 2: 512, 3: 12_889}, (13_660, 12_881), 13_279),
    "DOT": (49_181, (2020, 8, 18, 17), 50, 43, {0: 1, 1: 5, 2: 18, 3: 12_281}, (12_305, 12_281), 12_295),
    "ETH": (92_294, (2015, 8, 7, 11), 1_055, 874, {0: 25, 1: 139, 2: 305, 3: 22_822}, (23_260, 22_817), 23_079),
    "LINK": (56_518, (2019, 9, 25, 13), 589, 550, {0: 8, 1: 53, 2: 263, 3: 13_942}, (14_259, 13_939), 14_111),
    "LTC": (99_565, (2013, 9, 14, 8), 10_395, 7_419, {0: 269, 1: 1_353, 2: 2_019, 3: 23_104}, (26_383, 23_057), 24_861),
    "SOL": (41_918, (2021, 6, 17, 15), 43, 26, {1: 4, 2: 9, 3: 10_472}, (10_483, 10_472), 10_480),
    "XRP": (77_653, (2017, 5, 18, 15), 92, 39, {0: 4, 1: 3, 2: 12, 3: 19_403}, (19_420, 19_403), 19_417),
}
# The union index of each stamp `_ffill_btc` fills, and its stamp.
_FILLS = [
    (6, datetime(2013, 9, 14, 8, tzinfo=UTC)),
    (26, datetime(2013, 9, 29, 4, tzinfo=UTC)),
    (160, datetime(2013, 11, 3, 8, tzinfo=UTC)),
    (235, datetime(2013, 11, 16, 4, tzinfo=UTC)),
    (9_340, datetime(2018, 1, 12, 0, tzinfo=UTC)),
    (9_341, datetime(2018, 1, 12, 16, tzinfo=UTC)),
]
# Records 48 and 49's arm A and benchmark, stored unrounded.
_ARM_A = {
    "arm_a_ann_sharpe_noc": 1.404998307684581,
    "arm_a_ann_sharpe_noc_decisive": 1.3716011675660076,
    "arm_a_max_drawdown": 0.2154323695072342,
    "turnover_a": 146.18534602048504,
    "arm_a_spot_drag_pct_yr": 0.07026650498259404,
    "benchmark_ann_sharpe_noc": 1.2128451567638199,
    "benchmark_ann_sharpe_noc_decisive": 1.2446890489958136,
}


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/60.parquet"),
    reason="the frozen ohlc-full set's hourly files are absent under data/",
)
def test_the_b1_hourly_exit_reads_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    h4_ts, h4_prices, hourly = subjects._b1_hourly_rv_reads(
        reader, "ohlc-full", None, None, False, subject="b1-hourly-channel-exits"
    )
    block = reader.block()
    assert compute_hash(block) == _BLOCK_HASH
    assert (len(block["ohlc-full"]["files"]), block["ohlc-full"]["rows"]) == (20, 855_305)
    assert (len(h4_ts), h4_ts[0], h4_ts[-1]) == (
        27_338,
        datetime(2013, 9, 10, 20, tzinfo=UTC),
        datetime(2026, 3, 31, 20, tzinfo=UTC),
    )
    assert sum(later - earlier != _H4 for earlier, later in zip(h4_ts, h4_ts[1:])) == 63
    assert [(k, h4_ts[k]) for k, p in enumerate(h4_prices["BTC"]) if p is None] == _FILLS

    # Its refusals are D4's: every hourly row clean, on the hour, increasing and inside a 240 bar of its asset.
    fed = _ffill_btc(h4_prices)
    interior = interior_closes_by_asset(fed, h4_prices, h4_ts, hourly)
    btc_own = {t: j for j, t in enumerate(h4_ts)}
    assert [interior["BTC"][btc_own[t]] for _, t in _FILLS] == [(None, None, None)] * 6

    for asset, (rows, first, missing, inside, present, (adjacent, adjacent_all), fourth) in _BASIS.items():
        stamps, closes = hourly[asset]
        by_hour = dict(zip(stamps, closes, strict=True))
        bars = [(k, t, p) for k, (t, p) in enumerate(zip(h4_ts, h4_prices[asset])) if p is not None]
        own = {t: j for j, t in enumerate(t for t, p in zip(h4_ts, fed[asset]) if p is not None)}
        held = [sum(c is not None for c in interior[asset][own[t]]) for _, t, _ in bars[1:]]
        pairs = [t1 for (k0, _, _), (k1, t1, _) in zip(bars, bars[1:]) if k1 == k0 + 1]
        assert (len(stamps), stamps[0], stamps[-1]) == (rows, datetime(*first, tzinfo=UTC), _LAST_HOUR), asset
        assert (int((_LAST_HOUR - stamps[0]) / _H1) + 1 - rows, 4 * len(bars) - rows) == (missing, inside), asset
        assert Counter(held) == present, asset
        assert (len(pairs), sum(None not in interior[asset][own[t]] for t in pairs)) == (adjacent, adjacent_all), asset
        # The seam: the hourly bar 3h in closes at the 240 close, and so does the last present hourly bar of every 240 bar.
        assert sum(t + 3 * _H1 in by_hour for _, t, _ in bars) == fourth, asset
        assert all([by_hour[t + i * _H1] for i in range(4) if t + i * _H1 in by_hour][-1:] == [p] for _, t, p in bars), asset


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/60.parquet"),
    reason="the frozen ohlc-full set's hourly files are absent under data/",
)
def test_the_b1_hourly_exit_arm_a_reproduces_records_48_and_49s_arm_a():
    reads = subjects._b1_hourly_rv_reads(
        ObservedReader(_DATA_ROOT), "ohlc-full", None, None, False, subject="b1-hourly-channel-exits"
    )
    inputs = subjects._b1_hourly_exit_inputs(reads)
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.h4_ts) - 1

    assert n == 27_337
    assert {
        "arm_a_ann_sharpe_noc": sharpe(net_a, periods_per_year=2190),
        "arm_a_ann_sharpe_noc_decisive": sharpe(net_a[1380:], periods_per_year=2190),
        "arm_a_max_drawdown": max_drawdown(net_a),
        "turnover_a": turnover_a,
        "arm_a_spot_drag_pct_yr": turnover_a / n * 0.006 * 2190,
        "benchmark_ann_sharpe_noc": sharpe(bench, periods_per_year=2190),
        "benchmark_ann_sharpe_noc_decisive": sharpe(bench[1380:], periods_per_year=2190),
    } == _ARM_A
    assert all({key: _trials()[record]["metrics"][key] for key in _ARM_A} == _ARM_A for record in (48, 49))
