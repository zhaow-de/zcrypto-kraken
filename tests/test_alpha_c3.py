import math
from datetime import UTC, date, datetime, timedelta

import pytest

from cli.alpha.b2 import event_contrast_blocks, stationary_bootstrap_blocks
from cli.alpha.c3 import (
    COST_ROUND_TRIP,
    FAR,
    FEATURES,
    FIRST_DAY,
    HIGH,
    HORIZONS,
    LAG_DAYS,
    LOW,
    MEAN_BLOCK,
    MIN_EVENT_YEARS,
    MIN_HISTORY,
    N_RESAMPLES,
    SEED,
    STATES,
    TAILS,
    a1_daily_positions,
    bands,
    cell_name,
    event_years,
    flags,
    forwards,
    from_first_day,
    lagged,
    states,
)
from cli.portfolio import CrossfreqSystemConfig, build_crossfreq_system
from cli.portfolio.crossfreq import expand_daily_positions


def test_the_constants_are_the_specs():
    assert FEATURES == ("mvrv", "mvrv_z", "asopr", "sth_supply_share")
    assert TAILS == ("low", "high")
    assert STATES == ("long", "flat")
    assert HORIZONS == (7, 30)
    assert LOW == 0.10
    assert HIGH == 0.90
    assert MIN_HISTORY == 365
    assert LAG_DAYS == 1
    assert MEAN_BLOCK == 102
    assert N_RESAMPLES == 10000
    assert SEED == 42
    assert FAR == (0.078125, 99.921875)
    assert COST_ROUND_TRIP == 0.012
    assert MIN_EVENT_YEARS == 4
    assert FIRST_DAY == date(2011, 1, 1)


def test_a_day_before_the_first_day_is_no_value():
    days = [FIRST_DAY - timedelta(days=2), FIRST_DAY - timedelta(days=1), FIRST_DAY, FIRST_DAY + timedelta(days=1)]
    assert from_first_day(days, [1.0, 2.0, 3.0, None]) == [None, None, 3.0, None]


def _planted():
    values = [float(i + 1) for i in range(400)]
    values[369] = 36.5  # 37 of the 370 read values at or below it: p = 0.10
    values[370] = math.nan
    values[380] = 55.5  # 57 of 380: p = 0.15
    values[390] = 348.5  # 351 of 390: p = 0.90
    values[395] = 0.5  # 1 of 395
    return values


def test_bands_on_a_known_answer():
    values = _planted()
    out = bands(values)
    assert out[:364] == [None] * 364
    assert [out[i] for i in (364, 369, 380, 390, 395)] == ["high", "low", "mid", "high", "low"]
    assert out[370] is None
    holed = list(values)
    holed[370] = None
    assert out[371:] == bands(holed)[371:]


def test_a_band_reads_no_later_day():
    values = [100.0 + i for i in range(380)] + [136.5] + [2.0 + 0.01 * j for j in range(19)]
    later = values[:381] + [v * 100 for v in values[381:]]
    out = bands(values)
    assert out[380] == "low"  # 38 of 381 at or below it; the 19 later values, read, would lift it to mid
    assert bands(later)[:381] == out[:381]


def test_index_k_reads_the_day_before_its_bar():
    d0 = date(2024, 3, 1)
    by_day = {d0 + timedelta(days=i): float(i) for i in (-1, 0, 1, 2)}
    grid = [datetime(2024, 3, 1, tzinfo=UTC) + timedelta(days=k) for k in range(3)]
    assert lagged(by_day, grid) == [-1.0, 0.0, 1.0]


_LISTED = {"AVAX": 200, "DOT": 201, "SOL": 202}  # after the 200-day gate's first read, at index 199
_N_DAYS = 233  # the fewest at which SOL, listed last, holds an A1 position


def _union():
    assets = CrossfreqSystemConfig().assets
    start = datetime(2020, 1, 1, tzinfo=UTC)
    daily_ts = [start + timedelta(days=k) for k in range(_N_DAYS)]
    h4_ts = [start + timedelta(hours=4 * j) for j in range(6 * _N_DAYS)]
    h4 = {}
    for i, a in enumerate(assets):
        drift, period = 1.0004 + 0.00005 * i, 9 + 2 * i
        first = 6 * _LISTED.get(a, 0)
        h4[a] = [None if j < first else 10.0 * (i + 1) * drift**j * (1 + 0.04 * math.sin(j / period)) for j in range(6 * _N_DAYS)]
    for a, day in (("BTC", 210), ("LTC", 215), ("XRP", 215)):
        h4[a][6 * day : 6 * day + 6] = [None] * 6
    daily = {a: [h4[a][6 * k + 5] for k in range(_N_DAYS)] for a in assets}
    return daily, daily_ts, h4, h4_ts


def test_the_arm_expands_to_the_builders_a1_sleeve():
    daily, daily_ts, h4, h4_ts = _union()
    arm = a1_daily_positions(daily)
    assert {len(rows) for rows in arm.values()} == {_N_DAYS}
    for asset, day in _LISTED.items():
        assert set(arm[asset][:day]) == {0.0} and arm[asset][-1] > 0
    assert arm["LTC"][215] > 0 and arm["XRP"][215] > 0
    d_ts = daily_ts + [daily_ts[-1] + timedelta(days=1)]
    h_ts = h4_ts + [h4_ts[-1] + timedelta(hours=4)]
    expanded = expand_daily_positions(arm, [t + timedelta(days=1) for t in d_ts], [t + timedelta(hours=4) for t in h_ts])
    config = CrossfreqSystemConfig(fee_per_side=0.0040, spread_per_side=0.0020)
    assert expanded == build_crossfreq_system(daily, daily_ts, h4, h4_ts, config=config).sleeve_positions["A1"]


def test_the_arm_refuses_an_order_other_than_the_builders():
    daily = _union()[0]
    reordered = {"BTC": daily["BTC"], **{a: closes for a, closes in daily.items() if a != "BTC"}}
    with pytest.raises(ValueError) as refused:
        a1_daily_positions(reordered)
    assert str(CrossfreqSystemConfig().assets) in str(refused.value) and str(tuple(reordered)) in str(refused.value)


def test_states_and_flags():
    positions = {"A": [0.0, 0.3, 0.0, 0.2]}
    prices = {"A": [None, 10.0, 11.0, None]}
    assert states(positions, prices) == {"A": [None, "long", "flat", None]}
    band = ["low", "mid", "high", None] * 3
    state = ["long"] * 4 + ["flat"] * 4 + [None] * 4
    assert flags(band, state, tail="low", in_state="long") == [True, False, False, None] + [None] * 8
    assert flags(band, state, tail="high", in_state="flat") == [None] * 4 + [False, False, True, None] + [None] * 4


def test_forwards_on_a_known_answer_and_none_past_the_end():
    prices = [64.0, 80.0, 120.0, 90.0, None, 180.0, 135.0, 101.25]
    log, summed = forwards(prices, 3)
    assert log == [math.log(1.40625), None, math.log(1.5), math.log(1.5), None, None, None, None]
    assert summed == [0.5, None, -0.25, -0.25, None, None, None, None]


def test_cell_name_and_event_years():
    assert cell_name("mvrv", "low", "long", 7) == "mvrv|low|long|H7"
    n = 24
    years = [2018 + k // 4 for k in range(n)]
    usable = [0.01 * (k % 5) - 0.02 for k in range(21)] + [None] * 3

    def marks(true, false):
        return [True if k in true else False if k in false else None for k in range(n)]

    flagged = {
        "A": marks({5, 9, 22}, {6, 10}),  # 22 lies in the last 3 indices, its forward None
        "B": marks({2, 13, 14}, {7, 15}),  # 2 lies before B's listing, its forward None
        "C": marks({17}, {18, 19}),  # one usable event
    }
    forward = {"A": usable, "B": [None] * 4 + usable[4:], "C": usable}
    out = event_years(flagged, forward, years)
    assert out == {"2019": 1, "2020": 1, "2021": 2}
    blocks = stationary_bootstrap_blocks(n, mean_block=3, n_resamples=50, seed=7)
    assert sum(out.values()) == event_contrast_blocks(flagged, {"log": forward}, blocks, far=FAR)["log"]["pooled"][0]
