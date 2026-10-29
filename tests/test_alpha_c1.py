import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.c1 import (
    ADVERSE_OFFSETS_S,
    HORIZONS_S,
    LAG,
    MAKER_ROUND_TRIP,
    MEAN_BLOCK,
    MONTHS,
    N_RESAMPLES,
    PAIRS,
    SEED,
    SIDES,
    SIGMA_WINDOW,
    SIZES,
    SPAN,
    THRESHOLDS,
    TRADE_FILL_S,
    cell_name,
    fill_table,
    quarter_hour_mids,
    reversal_cells,
)
from cli.alpha.c2 import log_returns
from cli.panel.fills import rows_frame
from cli.validation.spa import reality_check_pvalue

STEP = timedelta(minutes=15)
EPSILON = 1e-4
BID, ASK = 99.99, 100.01
CENSORED = "censored"


def _post(ts, side, size, *, mid=100.0, fill_s=None, fill_price=None, mid_60=None, mid_900=None, mid_3600=None, censored=False):
    filled = fill_s is not None
    return {
        "ts": ts,
        "pair": "BTC/EUR",
        "side": side,
        "size": size,
        "mid_at_post": mid,
        "spread_at_post_bps": 2.0,
        "stale_seconds_at_post": 1.0,
        "queue_ahead_qty": 1.0,
        "queue_ahead_notional": 100.0,
        "our_qty": 0.1,
        "filled": filled,
        "time_to_fill_s": fill_s,
        "cancelled_s": None if filled or censored else 900.0,
        "fill_price": fill_price,
        "mid_at_fill_plus_60s": mid_60,
        "mid_at_fill_plus_900s": mid_900,
        "mid_at_post_plus_900s": mid,
        "mid_at_post_plus_3600s": mid_3600,
    }


def _filled(ts, side, size, fill_s, *, after_60=5e-4, after_900=9e-4):
    """A fill at the touch followed by a mid `after_60` and `after_900` of its price against the order: lower after a bid's
    fill, higher after an ask's."""
    price = BID if side == "bid" else ASK
    away = -1 if side == "bid" else 1
    return _post(
        ts,
        side,
        size,
        fill_s=fill_s,
        fill_price=price,
        mid_60=None if after_60 is None else price * (1 + away * after_60),
        mid_900=None if after_900 is None else price * (1 + away * after_900),
    )


def _mids(n, planted, *, anchor=0):
    """The mid at each bar: its 15m log return EPSILON either way, alternating, but at the planted bars, where it is the
    planted multiple of EPSILON; scaled so the mid at `anchor` is 100.0."""
    logs = [0.0]
    for i in range(1, n):
        logs.append(logs[-1] + EPSILON * planted.get(i, 1.0 if i % 2 else -1.0))
    return [100.0 * math.exp(x - logs[anchor]) for x in logs]


def _bars(start, mids, trades):
    """Four posts at each bar, each unfilled but where `trades` names its bar, side and size."""
    rows = []
    for i, mid in enumerate(mids):
        for side in SIDES:
            for size in SIZES:
                rows.append(trades.get((i, side, size)) or _post(start + i * STEP, side, size, mid=mid))
    return rows_frame(rows)


def _trade(start, mids, i, side, gross, *, fill_s=30.0, marked=True):
    """The post of `side` at rung 0 at bar `i`, filled at the touch and followed an hour after the post by the mid that
    makes its move from the fill price in its favour `gross`."""
    price = mids[i] * (1 - EPSILON) if side == "bid" else mids[i] * (1 + EPSILON)
    favour = 1 if side == "bid" else -1
    after = price * (1 + favour * gross) if marked else None
    return _post(start + i * STEP, side, 0, mid=mids[i], fill_s=fill_s, fill_price=price, mid_3600=after)


def test_the_constants_are_the_specs():
    assert MAKER_ROUND_TRIP == 0.008
    assert THRESHOLDS == (1, 2) and SIZES == (0, 1) and SIDES == ("bid", "ask")
    assert (MEAN_BLOCK, N_RESAMPLES, SEED) == (30, 4000, 42)
    assert (SIGMA_WINDOW, LAG, TRADE_FILL_S) == (96, 1, 900)
    assert HORIZONS_S == (60, 300, 900) and ADVERSE_OFFSETS_S == (60, 900)
    assert MONTHS == ("2026-08", "2026-09", "2026-10")
    assert SPAN == (datetime(2026, 8, 1, tzinfo=UTC), datetime(2026, 10, 26, tzinfo=UTC))
    assert PAIRS == (
        "ADA/EUR",
        "AVAX/EUR",
        "BTC/EUR",
        "DOGE/EUR",
        "DOT/EUR",
        "ETH/EUR",
        "LINK/EUR",
        "LTC/EUR",
        "SOL/EUR",
        "XRP/EUR",
        "ETH/BTC",
        "SOL/BTC",
    )


# Each month's posts per side and rung, as the seconds each took to fill, None unfilled: the bid fills more than the ask,
# a rung-1 post fills where its rung-0 twin does not, September fills unlike August, and October posts nothing.
_PLANTED = {
    (datetime(2026, 8, 10, tzinfo=UTC), "bid", 0): (30.0, 200.0, 600.0, None),
    (datetime(2026, 8, 10, tzinfo=UTC), "bid", 1): (30.0, 200.0, 600.0, 600.0),
    (datetime(2026, 8, 10, tzinfo=UTC), "ask", 0): (30.0, None, 600.0, None),
    (datetime(2026, 8, 10, tzinfo=UTC), "ask", 1): (None, 200.0, 600.0, None),
    (datetime(2026, 9, 10, tzinfo=UTC), "bid", 0): (200.0, None),
    (datetime(2026, 9, 10, tzinfo=UTC), "bid", 1): (30.0, None),
    (datetime(2026, 9, 10, tzinfo=UTC), "ask", 0): (None, CENSORED),
    (datetime(2026, 9, 10, tzinfo=UTC), "ask", 1): (600.0, None),
}
# (posts, n_filled, fill_rate, median_time_to_fill_s) per key, month and span.
_TABLE = {
    "bid|S0|H60": {"2026-08": (4, 1, 0.25, 30.0), "2026-09": (2, 0, 0.0, None), "span": (6, 1, 1 / 6, 30.0)},
    "bid|S0|H300": {"2026-08": (4, 2, 0.5, 115.0), "2026-09": (2, 1, 0.5, 200.0), "span": (6, 3, 0.5, 200.0)},
    "bid|S0|H900": {"2026-08": (4, 3, 0.75, 200.0), "2026-09": (2, 1, 0.5, 200.0), "span": (6, 4, 4 / 6, 200.0)},
    "bid|S1|H60": {"2026-08": (4, 1, 0.25, 30.0), "2026-09": (2, 1, 0.5, 30.0), "span": (6, 2, 2 / 6, 30.0)},
    "bid|S1|H300": {"2026-08": (4, 2, 0.5, 115.0), "2026-09": (2, 1, 0.5, 30.0), "span": (6, 3, 0.5, 30.0)},
    "bid|S1|H900": {"2026-08": (4, 4, 1.0, 400.0), "2026-09": (2, 1, 0.5, 30.0), "span": (6, 5, 5 / 6, 200.0)},
    "ask|S0|H60": {"2026-08": (4, 1, 0.25, 30.0), "2026-09": (2, 0, 0.0, None), "span": (6, 1, 1 / 6, 30.0)},
    "ask|S0|H300": {"2026-08": (4, 1, 0.25, 30.0), "2026-09": (2, 0, 0.0, None), "span": (6, 1, 1 / 6, 30.0)},
    "ask|S0|H900": {"2026-08": (4, 2, 0.5, 315.0), "2026-09": (2, 0, 0.0, None), "span": (6, 2, 2 / 6, 315.0)},
    "ask|S1|H60": {"2026-08": (4, 0, 0.0, None), "2026-09": (2, 0, 0.0, None), "span": (6, 0, 0.0, None)},
    "ask|S1|H300": {"2026-08": (4, 1, 0.25, 200.0), "2026-09": (2, 0, 0.0, None), "span": (6, 1, 1 / 6, 200.0)},
    "ask|S1|H900": {"2026-08": (4, 2, 0.5, 400.0), "2026-09": (2, 1, 0.5, 600.0), "span": (6, 3, 0.5, 600.0)},
}


def _leaves(posts, n_filled, fill_rate, median):
    """Every fill planted above is followed by a mid 5 bps against it at +60 s and 9 bps at +900 s."""
    leaves = {"posts": posts, "n_filled": n_filled, "fill_rate": fill_rate, "n_unmarked_60": 0, "n_unmarked_900": 0}
    if n_filled:
        leaves |= {"median_time_to_fill_s": median, "adverse_60_bps": 5.0, "adverse_900_bps": 9.0}
    return leaves


def test_fill_table_rates_and_adverse_selection_on_a_planted_frame():
    rows = []
    for (day, side, size), fills in _PLANTED.items():
        for j, fill_s in enumerate(fills):
            ts = day + timedelta(seconds=15 * j)
            if fill_s is None or fill_s == CENSORED:
                rows.append(_post(ts, side, size, censored=fill_s == CENSORED))
            else:
                rows.append(_filled(ts, side, size, fill_s))
    table = fill_table(rows_frame(rows))

    assert set(table) == set(_TABLE)
    for key, expected in _TABLE.items():
        assert list(table[key]["months"]) == list(MONTHS)
        for month in ("2026-08", "2026-09"):
            assert table[key]["months"][month] == pytest.approx(_leaves(*expected[month])), (key, month)
        assert table[key]["span"] == pytest.approx(_leaves(*expected["span"])), key
        assert table[key]["months"]["2026-10"] == {"posts": 0, "n_filled": 0, "n_unmarked_60": 0, "n_unmarked_900": 0}


def test_fill_table_leaves_a_null_mid_out_of_the_adverse_mean_and_counts_it():
    day = datetime(2026, 9, 10, tzinfo=UTC)
    rows = [
        _filled(day, "bid", 0, 30.0, after_60=5e-4, after_900=None),
        _filled(day + timedelta(seconds=15), "bid", 0, 200.0, after_60=7e-4, after_900=9e-4),
        _post(day + timedelta(seconds=30), "bid", 0),
    ]
    table = fill_table(rows_frame(rows))
    assert table["bid|S0|H900"]["span"] == pytest.approx(
        {
            "posts": 3,
            "n_filled": 2,
            "fill_rate": 2 / 3,
            "median_time_to_fill_s": 115.0,
            "adverse_60_bps": 6.0,
            "adverse_900_bps": 9.0,
            "n_unmarked_60": 0,
            "n_unmarked_900": 1,
        }
    )
    assert table["bid|S0|H60"]["span"] == pytest.approx(
        {
            "posts": 3,
            "n_filled": 1,
            "fill_rate": 1 / 3,
            "median_time_to_fill_s": 30.0,
            "adverse_60_bps": 5.0,
            "n_unmarked_60": 0,
            "n_unmarked_900": 1,
        }
    )


def test_quarter_hour_mids_take_the_post_at_each_boundary_and_leave_an_absent_one_out():
    hour = datetime(2026, 9, 10, 12, tzinfo=UTC)
    mids = {
        hour: 100.0,
        hour + timedelta(seconds=15): 100.5,
        hour + timedelta(minutes=15): 101.0,
        hour + timedelta(minutes=45): 102.0,
        hour + timedelta(minutes=45, seconds=15): 103.0,
    }
    frame = rows_frame([_post(ts, side, size, mid=mid) for ts, mid in mids.items() for side in SIDES for size in SIZES])

    ts, closes = quarter_hour_mids(frame.reverse())

    assert ts == [hour, hour + timedelta(minutes=15), hour + timedelta(minutes=45)]
    assert closes == [100.0, 101.0, 102.0]
    returns = log_returns(ts, closes)
    assert returns[0] is None and returns[1] == pytest.approx(math.log(1.01)) and returns[2] is None


def test_reversal_cells_trade_against_the_move_and_take_the_half_spread_once():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    down = _mids(101, {100: -10.0}, anchor=100)
    up = _mids(101, {100: 10.0}, anchor=100)
    bid_post = _post(start + 100 * STEP, "bid", 0, fill_s=30.0, fill_price=BID, mid_3600=100.00)
    after_down = _bars(start, down, {(100, "bid", 0): bid_post})
    ask_posts = {
        mid_3600: _post(start + 100 * STEP, "ask", 0, fill_s=30.0, fill_price=ASK, mid_3600=mid_3600)
        for mid_3600 in (100.00, 100.02)
    }

    bid = reversal_cells(after_down, threshold=1, size=0, side="bid")
    assert (bid["n_signals"], bid["span"]["n"]) == (1, 1)
    assert bid["span"]["mean_gross"] == pytest.approx(0.01 / 99.99)
    assert reversal_cells(after_down, threshold=1, size=0, side="ask")["n_signals"] == 0
    for mid_3600, gross in ((100.00, 0.01 / 100.01), (100.02, -0.01 / 100.01)):
        after_up = _bars(start, up, {(100, "ask", 0): ask_posts[mid_3600]})
        ask = reversal_cells(after_up, threshold=1, size=0, side="ask")
        assert (ask["n_signals"], ask["span"]["n"]) == (1, 1)
        assert ask["span"]["mean_gross"] == pytest.approx(gross)
        assert reversal_cells(after_up, threshold=1, size=0, side="bid")["n_signals"] == 0


# August's ten trades fill at its last day's down moves, the last at its last quarter-hour bar, whose hour after lies in
# September; September's ten at its first day's.
_AUGUST_BARS = tuple(110 + 9 * j for j in range(10))
_SEPTEMBER_BARS = tuple(200 + 9 * j for j in range(10))
_GROSSES = (0.0081,) * 16 + (0.0119,) * 4


def test_reversal_cells_file_each_trade_under_its_signal_bars_month_and_net_the_maker_round_trip():
    start = datetime(2026, 8, 30, tzinfo=UTC)
    bars = _AUGUST_BARS + _SEPTEMBER_BARS
    assert start + _AUGUST_BARS[-1] * STEP == datetime(2026, 8, 31, 23, 45, tzinfo=UTC)
    mids = _mids(288, dict.fromkeys(bars, -10.0))
    frame = _bars(start, mids, {(i, "bid", 0): _trade(start, mids, i, "bid", g) for i, g in zip(bars, _GROSSES, strict=True)})

    cell = reversal_cells(frame, threshold=1, size=0, side="bid")

    assert (cell["n_signals"], cell["fill_rate_900"], cell["n_unmarked"]) == (20, 1.0, 0)
    months = cell["months"]
    assert months["2026-08"] == pytest.approx({"n": 10, "mean_gross": 0.0081, "mean_net": 0.0081 - 0.008})
    assert months["2026-09"] == pytest.approx({"n": 10, "mean_gross": 0.00962, "mean_net": 0.00962 - 0.008})
    assert months["2026-10"] == {"n": 0}
    span = cell["span"]
    assert {key: span[key] for key in ("n", "mean_gross", "mean_net")} == pytest.approx(
        {"n": 20, "mean_gross": 0.00886, "mean_net": 0.00886 - 0.008}
    )
    expected = reality_check_pvalue([[g - 0.008] for g in _GROSSES], mean_block=30, n_resamples=4000, seed=42)["p_value"]
    assert span["p"] == expected


def test_an_unfilled_signal_bar_counts_as_no_trade():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    mids = _mids(130, {100: -10.0, 110: -10.0, 120: -10.0})
    trades = {
        (100, "bid", 0): _trade(start, mids, 100, "bid", 0.01),
        (120, "bid", 0): _post(start + 120 * STEP, "bid", 0, mid=mids[120], censored=True),
    }

    cell = reversal_cells(_bars(start, mids, trades), threshold=1, size=0, side="bid")

    assert (cell["n_signals"], cell["n_unmarked"]) == (3, 0)
    assert cell["fill_rate_900"] == pytest.approx(1 / 3)
    assert cell["span"] == pytest.approx({"n": 1, "mean_gross": 0.01, "mean_net": 0.002})


def test_a_filled_signal_trade_without_its_3600s_mid_is_unmarked():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    mids = _mids(130, {100: -10.0, 110: -10.0})
    trades = {
        (100, "bid", 0): _trade(start, mids, 100, "bid", 0.01),
        (110, "bid", 0): _trade(start, mids, 110, "bid", 0.03, marked=False),
    }

    cell = reversal_cells(_bars(start, mids, trades), threshold=1, size=0, side="bid")

    assert (cell["n_signals"], cell["fill_rate_900"], cell["n_unmarked"]) == (2, 1.0, 1)
    assert cell["span"] == pytest.approx({"n": 1, "mean_gross": 0.01, "mean_net": 0.002})


def test_a_cell_keys_every_month_and_the_span():
    # Bars from 2026-08-30 into 2026-09-01, the one trade in August.
    start = datetime(2026, 8, 30, tzinfo=UTC)
    mids = _mids(200, {150: -10.0})
    frame = _bars(start, mids, {(150, "bid", 0): _trade(start, mids, 150, "bid", 0.01)})

    bid = reversal_cells(frame, threshold=1, size=0, side="bid")
    assert set(bid) == {"n_signals", "fill_rate_900", "n_unmarked", "months", "span"}
    assert list(bid["months"]) == list(MONTHS)
    assert bid["months"]["2026-08"] == pytest.approx({"n": 1, "mean_gross": 0.01, "mean_net": 0.002})
    assert bid["months"]["2026-09"] == bid["months"]["2026-10"] == {"n": 0}
    assert bid["span"] == pytest.approx({"n": 1, "mean_gross": 0.01, "mean_net": 0.002})

    ask = reversal_cells(frame, threshold=1, size=0, side="ask")
    assert ask == {"n_signals": 0, "n_unmarked": 0, "months": dict.fromkeys(MONTHS, {"n": 0}), "span": {"n": 0}}


def test_cell_name():
    assert cell_name("BTC/EUR", 2, 0, "bid") == "BTC/EUR|th2|S0|bid"
