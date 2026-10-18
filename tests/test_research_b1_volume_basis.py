"""B1 trial 4's reads half against spec 00134's measured basis, computing no direction, and arm A against record 45's
anchors at the registry's precision."""

from __future__ import annotations

import statistics
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import net_of_cost
from cli.portfolio.record44_legs import benchmark_4h_net_of_cost
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from cli.validation import max_drawdown, sharpe
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_BLOCK_HASH = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
_ROWS = {
    "ADA": 16_446,
    "AVAX": 9_365,
    "BTC": 27_332,
    "DOGE": 13_710,
    "DOT": 12_306,
    "ETH": 23_292,
    "LINK": 14_267,
    "LTC": 26_746,
    "SOL": 10_486,
    "XRP": 19_423,
}
# The union index of each stamp `_ffill_btc` fills, its stamp, and BTC's own bars before it.
_FILLS = [
    (6, datetime(2013, 9, 14, 8, tzinfo=UTC), 6),
    (26, datetime(2013, 9, 29, 4, tzinfo=UTC), 25),
    (160, datetime(2013, 11, 3, 8, tzinfo=UTC), 158),
    (235, datetime(2013, 11, 16, 4, tzinfo=UTC), 232),
    (9_340, datetime(2018, 1, 12, 0, tzinfo=UTC), 9_336),
    (9_341, datetime(2018, 1, 12, 16, tzinfo=UTC), 9_336),
]
# Per asset over its own bars: the first with 180 prior bars, the smallest 180-bar median volume, the fewest and the most
# observations in a cell, all of them, the first cell to reach 100 earlier observations, and the last of the 42.
_NORM = {
    "ADA": ((2018, 10, 28, 12), 145253.043832995, 385, 388, 16_266, (2020, 9, 27, 12), (2020, 10, 4, 8)),
    "AVAX": ((2022, 1, 20, 12), 574.973046415, 217, 219, 9_185, (2023, 12, 21, 12), (2023, 12, 30, 0)),
    "BTC": ((2013, 11, 7, 8), 2.0, 645, 647, 27_152, (2015, 10, 8, 8), (2015, 10, 19, 0)),
    "DOGE": ((2020, 1, 21, 12), 174459.3690752, 317, 324, 13_530, (2021, 12, 21, 12), (2022, 2, 5, 0)),
    "DOT": ((2020, 9, 17, 16), 7220.07636406, 288, 289, 12_126, (2022, 8, 18, 16), (2022, 8, 25, 12)),
    "ETH": ((2015, 9, 7, 4), 297.74406141500003, 545, 552, 23_112, (2017, 8, 7, 4), (2017, 9, 16, 0)),
    "LINK": ((2019, 10, 25, 12), 2420.1512037700004, 333, 336, 14_087, (2021, 9, 24, 12), (2021, 10, 10, 4)),
    "LTC": ((2013, 12, 4, 8), 51.778360160000005, 608, 642, 26_566, (2015, 11, 11, 8), (2016, 6, 1, 0)),
    "SOL": ((2021, 7, 17, 20), 2022.8965592499999, 243, 246, 10_306, (2023, 6, 17, 20), (2023, 6, 24, 16)),
    "XRP": ((2017, 6, 17, 12), 316059.421934235, 457, 459, 19_243, (2019, 5, 18, 12), (2019, 6, 1, 4)),
}
_H4 = timedelta(hours=4)


def _utc(parts: tuple[int, ...]) -> datetime:
    return datetime(*parts, tzinfo=UTC)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set's 4h files are absent under data/",
)
def test_the_b1_volume_reads_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader = ObservedReader(_DATA_ROOT)
    h4_ts, h4_prices, volumes = subjects._b1_volume_reads(reader, "ohlc-full", None, None, False, subject="b1-volume-confirmation")

    block = reader.block()
    assert compute_hash(block) == _BLOCK_HASH
    assert (len(block["ohlc-full"]["files"]), block["ohlc-full"]["rows"]) == (10, 173_373)
    assert len(h4_ts) == 27_338
    assert (h4_ts[0], h4_ts[-1]) == (datetime(2013, 9, 10, 20, tzinfo=UTC), datetime(2026, 3, 31, 20, tzinfo=UTC))
    present = {asset: [v is not None for v in vs] == [p is not None for p in h4_prices[asset]] for asset, vs in volumes.items()}
    assert present == dict.fromkeys(_ROWS, True)
    assert {asset: sum(v is not None for v in vs) for asset, vs in volumes.items()} == _ROWS
    filled = [k for k in range(1, len(h4_ts)) if h4_prices["BTC"][k] is None]
    assert [(k, h4_ts[k], sum(p is not None for p in h4_prices["BTC"][:k])) for k in filled] == _FILLS

    for asset, (first, smallest, fewest, most, total, first_bound, last_bound) in _NORM.items():
        own = [(t, v) for t, v in zip(h4_ts, volumes[asset], strict=True) if v is not None]
        cells, bound = Counter(), {}
        for j in range(180, len(own)):
            b = own[j][0] + _H4
            cell = (b.hour, b.weekday())
            if cells[cell] >= 100 and cell not in bound:
                bound[cell] = own[j][0]
            cells[cell] += 1
        assert own[180][0] == _utc(first), asset
        assert min(statistics.median(v for _, v in own[j - 180 : j]) for j in range(180, len(own))) == smallest, asset
        assert (len(cells), sorted({hour for hour, _ in cells})) == (42, [0, 4, 8, 12, 16, 20]), asset
        assert (min(cells.values()), max(cells.values()), sum(cells.values())) == (fewest, most, total), asset
        assert (len(bound), min(bound.values()), max(bound.values())) == (42, _utc(first_bound), _utc(last_bound)), asset


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set's 4h files are absent under data/",
)
def test_the_b1_volume_arm_a_reproduces_record_45s_arm_a():
    reads = subjects._b1_volume_reads(ObservedReader(_DATA_ROOT), "ohlc-full", None, None, False, subject="b1-volume-confirmation")
    inputs = subjects._b1_volume_inputs(reads)
    net_a = net_of_cost(inputs.arm_a, inputs.returns, cost_per_side=0.006)
    bench = benchmark_4h_net_of_cost(inputs.h4_prices, cost_per_side=0.006)
    turnover_a, n = book_turnover(inputs.arm_a), len(inputs.h4_ts) - 1

    assert n == 27_337
    assert round(sharpe(net_a, periods_per_year=2190), 4) == 1.405
    assert round(sharpe(net_a[1380:], periods_per_year=2190), 4) == 1.3716
    assert round(max_drawdown(net_a), 4) == 0.2154
    assert (round(turnover_a, 2), round(turnover_a / n * 0.006 * 2190, 4)) == (146.19, 0.0703)
    assert round(sharpe(bench, periods_per_year=2190), 4) == 1.2128
    assert round(sharpe(bench[1380:], periods_per_year=2190), 4) == 1.2447
