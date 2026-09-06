from datetime import datetime, timedelta

import pytest

from cli.portfolio import PortfolioError, daily_cadence_governor, expand_daily_positions
from cli.risk import GovernorConfig, drawdown_governor

# --- expand_daily_positions fixtures -----------------------------------------------------------
# Irregular spacing on purpose (D1 -> D2 is 3 days, not 1) so the mapping cannot assume regularity.
D0 = datetime(2024, 1, 1)
D1 = datetime(2024, 1, 2)
D2 = datetime(2024, 1, 5)
DAILY_TS = [D0, D1, D2]
DAILY_POSITIONS = {"AAA": [1.0, 2.0], "BBB": [0.1, 0.2]}

# 6 stamps -> 5 bars whose ends span every case: at D0, inside a daily span, exactly on a boundary,
# and past the last daily stamp.
INTRADAY_TS = [
    datetime(2023, 12, 31),
    D0,
    datetime(2024, 1, 1, 12, 0),
    D1,
    datetime(2024, 1, 3, 6, 0),
    datetime(2024, 1, 6),
]


def test_expand_planted_mapping():
    out = expand_daily_positions(DAILY_POSITIONS, DAILY_TS, INTRADAY_TS)
    assert out["AAA"] == [0.0, 1.0, 1.0, 2.0, 0.0]
    assert out["BBB"] == [0.0, 0.1, 0.1, 0.2, 0.0]


def test_expand_output_length():
    out = expand_daily_positions(DAILY_POSITIONS, DAILY_TS, INTRADAY_TS)
    for series in out.values():
        assert len(series) == len(INTRADAY_TS) - 1


def test_expand_no_lookahead():
    base = expand_daily_positions(DAILY_POSITIONS, DAILY_TS, INTRADAY_TS)
    perturbed = {"AAA": [1.0, 999.0], "BBB": [0.1, 999.0]}  # only day-1 (k=1) position changes
    pert = expand_daily_positions(perturbed, DAILY_TS, INTRADAY_TS)
    # bars 0-2 all end at or before D1 -> must be unaffected by a day-1 position perturbation.
    for asset in DAILY_POSITIONS:
        assert pert[asset][:3] == base[asset][:3]


@pytest.mark.parametrize(
    "daily_positions,daily_ts,intraday_ts",
    [
        ({"AAA": [1.0, 2.0], "BBB": [1.0, 2.0, 3.0]}, DAILY_TS, INTRADAY_TS),  # ragged dict
        (DAILY_POSITIONS, list(reversed(DAILY_TS)), INTRADAY_TS),  # unsorted daily_ts
        (DAILY_POSITIONS, DAILY_TS, list(reversed(INTRADAY_TS))),  # unsorted intraday_ts
        ({"AAA": [1.0, float("nan")]}, DAILY_TS, INTRADAY_TS),  # non-finite position
        ({"AAA": [1.0, float("inf")]}, DAILY_TS, INTRADAY_TS),  # non-finite position
        (DAILY_POSITIONS, [D0, D1], INTRADAY_TS),  # daily_ts wrong length
        ({}, DAILY_TS, INTRADAY_TS),  # empty dict
        ("not a dict", DAILY_TS, INTRADAY_TS),
    ],
)
def test_expand_validation(daily_positions, daily_ts, intraday_ts):
    with pytest.raises(PortfolioError):
        expand_daily_positions(daily_positions, daily_ts, intraday_ts)


def test_expand_close_indexed_daily_book_shifted_boundaries_day_aligned():
    # Bar-START-stamped grids (this repo's parquet convention): a close-indexed daily book's position
    # k is decided from bar k's close, so RAW stamps apply it one calendar day early -- look-ahead.
    # Shift both ts lists to close time (daily +1 day; intraday +4h here) to line position k up on
    # the six 4h bars composing close[k]->close[k+1].
    day0 = datetime(2024, 1, 1)
    day1 = datetime(2024, 1, 2)
    day2 = datetime(2024, 1, 3)
    day3 = datetime(2024, 1, 4)
    daily_ts = [day0, day1, day2, day3]  # 3 daily positions: p0 (day0->day1), p1 (day1->day2), p2 (day2->day3)
    positions = {"AAA": [10.0, 20.0, 30.0]}

    # One day longer than daily_ts so the close-time shift below has runway for all six of p2's bars.
    intraday_ts = [day0 + timedelta(hours=4 * i) for i in range(25)]

    # (a) close-time-shifted inputs.
    shifted_daily_ts = [ts + timedelta(days=1) for ts in daily_ts]
    shifted_intraday_ts = [ts + timedelta(hours=4) for ts in intraday_ts]
    shifted = expand_daily_positions(positions, shifted_daily_ts, shifted_intraday_ts)

    expected_shifted = (
        [0.0] * 5  # bars ending before day1's close (day1 00:00) -- book not decided into yet
        + [10.0] * 6  # the six 4h bars composing close[0]->close[1] (calendar day1)
        + [20.0] * 6  # close[1]->close[2] (calendar day2)
        + [30.0] * 6  # close[2]->close[3] (calendar day3)
        + [0.0] * 1  # past the book's life (day3's close already spent)
    )
    assert shifted["AAA"] == expected_shifted

    # (b) raw (bar-start) stamps, the naive usage: position k lands one calendar day early.
    raw = expand_daily_positions(positions, daily_ts, intraday_ts)
    expected_raw = [10.0] * 6 + [20.0] * 6 + [30.0] * 6 + [0.0] * 6
    assert raw["AAA"] == expected_raw

    assert shifted["AAA"] != raw["AAA"]


# --- daily_cadence_governor ---------------------------------------------------------------------


def test_governor_daily_loss_broadcast():
    # Day 0: three bars of -0.011 compound to -0.0327 (<= -3% daily-loss limit); day 1 flat.
    intraday_returns = [-0.011, -0.011, -0.011, 0.0, 0.0, 0.0]
    day_index = [0, 0, 0, 1, 1, 1]
    out = daily_cadence_governor(intraday_returns, day_index)
    day0_ret = (1 - 0.011) ** 3 - 1
    direct = drawdown_governor([day0_ret, 0.0])
    assert out == [direct.multipliers[0]] * 3 + [direct.multipliers[1]] * 3
    assert out == [1.0, 1.0, 1.0, 0.5, 0.5, 0.5]


def test_governor_custom_config():
    cfg = GovernorConfig(daily_loss_limit=0.5, ladder=((0.01, 0.0),), restart_after=1)
    intraday_returns = [-0.02, -0.02, 0.0, 0.0]
    day_index = [0, 0, 1, 1]
    out = daily_cadence_governor(intraday_returns, day_index, config=cfg)
    day0_ret = (1 - 0.02) ** 2 - 1
    direct = drawdown_governor([day0_ret, 0.0], config=cfg)
    assert out == [direct.multipliers[0]] * 2 + [direct.multipliers[1]] * 2


def test_governor_no_lookahead():
    intraday_returns = [-0.011, -0.011, -0.011, 0.0, 0.0, 0.0, 0.01, 0.01]
    day_index = [0, 0, 0, 1, 1, 1, 2, 2]
    base = daily_cadence_governor(intraday_returns, day_index)
    perturbed = list(intraday_returns)
    perturbed[6] = -0.5  # day 2's bars
    perturbed[7] = -0.5
    pert = daily_cadence_governor(perturbed, day_index)
    assert pert[:6] == base[:6]  # days 0 and 1 bit-identical


def test_governor_identity_and_length():
    intraday_returns = [0.01, -0.02, 0.03, 0.0, 0.01, -0.01, 0.02]
    day_index = [0, 0, 1, 1, 1, 2, 2]
    out = daily_cadence_governor(intraday_returns, day_index)
    assert len(out) == len(intraday_returns)
    assert out[0] == out[1]
    assert out[2] == out[3] == out[4]
    assert out[5] == out[6]


@pytest.mark.parametrize(
    "intraday_returns,day_index",
    [
        ([0.01, 0.02], [1, 0]),  # decreasing day_index
        ([0.01, 0.02], [0]),  # length mismatch (short)
        ([0.01, 0.02], [0, 1, 2]),  # length mismatch (long)
        ([0.01, 0.02], [-1, 0]),  # negative start
        ([0.01, 0.02, 0.03], [0, 0, 2]),  # day-index gap (not contiguous)
        ([0.01, float("nan")], [0, 0]),  # non-finite return
        ([0.01, -1.0], [0, 0]),  # return <= -1
        ([], []),  # empty
    ],
)
def test_governor_validation(intraday_returns, day_index):
    with pytest.raises(PortfolioError):
        daily_cadence_governor(intraday_returns, day_index)
