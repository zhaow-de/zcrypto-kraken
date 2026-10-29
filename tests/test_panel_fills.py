"""The queue-position fill model of `cli/panel/fills.py` (spec 00151 D2), each case on a known answer over a synthetic
book, prints or hours."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest

from cli.archive.replay import regroup_messages
from cli.capture.book import OrderBook
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA
from cli.panel.fills import (
    COLUMNS,
    Order,
    apply_trade,
    flush,
    pair_tick,
    post_orders,
    rows_frame,
    simulate_hour,
    tick_cancel,
)

H = datetime(2026, 9, 2, 10, tzinfo=UTC)
H2 = H + timedelta(hours=1)
PAIR = "BTC/EUR"
BIDS = [(1000.0, 1.0), (999.0, 1.0), (990.0, 1.0)]
ASKS = [(1001.0, 1.0), (1002.0, 1.0), (1010.0, 1.0)]
# Two ticks between asks, so each removal of the best moves the mid by one.
LADDER = [(1002.0, 1.0), (1004.0, 1.0), (1006.0, 1.0), (1008.0, 1.0), (1010.0, 1.0)]


def _at(seconds: float, hour: datetime = H) -> datetime:
    return hour + timedelta(seconds=seconds)


def _levels(levels: list[tuple[float, float]]) -> list[dict]:
    return [{"price": price, "qty": qty} for price, qty in levels]


def _book(bids: list[tuple[float, float]], asks: list[tuple[float, float]], pair: str = PAIR) -> OrderBook:
    book = OrderBook(pair, 100)
    book.ingest_snapshot({"bids": _levels(bids), "asks": _levels(asks), "checksum": 0})
    return book


def _update(book: OrderBook, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
    book.ingest_update({"bids": _levels(bids), "asks": _levels(asks), "checksum": 0})


def _trade(seconds: float, side: str, price: float, qty: float) -> dict:
    return {"ts": _at(seconds), "side": side, "price": price, "qty": qty}


def _order(side: str, price: float, *, ahead: float = 1.0, our: float = 0.1) -> Order:
    return Order(
        ts=_at(0),
        pair=PAIR,
        side=side,
        size=0,
        price=Decimal(str(price)),
        our_qty=our,
        queue_ahead_qty=ahead,
        queue_ahead_notional=ahead * price,
        mid_at_post=1000.5,
        spread_at_post_bps=9.995,
        stale_seconds_at_post=0.0,
    )


def _hour(bids, asks, messages=(), trades=(), *, hour=H, quiet=None, snapshot=True):
    """One hour's book messages as `regroup_messages` rebuilds them from the exploded rows, and its prints as the trades
    frame's rows: a snapshot of `bids` and `asks` at :00 unless the hour continues the one before, the deepest bid
    restated every 5 s outside the open interval `quiet` (seconds into the hour), and the planted `messages` --
    `(offset, bids, asks)`, a level of qty 0 removing it -- and `trades` -- `(offset, side, price, qty)`."""
    planned = [(0.0, "snapshot", bids, asks)] if snapshot else []
    planned += [
        (float(s), "update", [min(bids)], [])
        for s in range(5 if snapshot else 0, 3600, 5)
        if quiet is None or not quiet[0] < s < quiet[1]
    ]
    planned += [(float(offset), "update", b, a) for offset, b, a in messages]
    planned.sort(key=lambda message: message[0])
    rows = [
        {"ts": _at(offset, hour), "symbol": PAIR, "type": kind, "side": side, "price": price, "qty": qty, "checksum": n}
        for n, (offset, kind, b, a) in enumerate(planned)
        for side, levels in (("bid", b), ("ask", a))
        for price, qty in levels
    ]
    prints = [
        {"ts": _at(offset, hour), "symbol": PAIR, "side": side, "price": price, "qty": qty, "ord_type": "limit", "trade_id": n}
        for n, (offset, side, price, qty) in enumerate(trades)
    ]
    frame = pl.DataFrame(prints, schema=TRADE_SCHEMA).sort("ts", maintain_order=True)
    return regroup_messages(pl.DataFrame(rows, schema=BOOK_SCHEMA)), frame.to_dicts()


def _run(hour_data, *, hour=H, carried=(), book=None, last_msg_ts=None):
    messages, trades = hour_data
    book = book if book is not None else OrderBook(PAIR, 100)
    return simulate_hour(messages, trades, book, hour, pair=PAIR, carried=list(carried), last_msg_ts=last_msg_ts)


def _one(orders: list[Order], seconds: float, side: str, size: int = 0, hour: datetime = H) -> Order:
    [order] = [o for o in orders if o.ts == _at(seconds, hour) and o.side == side and o.size == size]
    return order


def _row_of(rows: list[dict], seconds: float, side: str, size: int = 0, hour: datetime = H) -> dict:
    [row] = [r for r in rows if r["ts"] == _at(seconds, hour) and r["side"] == side and r["size"] == size]
    return row


def _walk(order: Order, book: OrderBook, tick: Decimal, upto: int, *, start: int = 1, updates=None, trades=None) -> None:
    """Seconds `start..upto` of `order`'s life as the hour's loop takes each: the second's book update, its prints, then
    the cancel clock -- `updates` (`(bids, asks)`) and `trades` keyed by the second they land at."""
    for second in range(start, upto + 1):
        if second in (updates or {}):
            _update(book, *updates[second])
        for trade in (trades or {}).get(second, ()):
            apply_trade(order, trade)
        tick_cancel(order, book, _at(second), tick)


def test_post_orders_make_four_at_the_touch_with_the_rungs_quantities():
    cases = (
        (
            "BTC/EUR",
            [(40000.0, 0.75), (39999.5, 2.0)],
            [(40010.0, 0.25), (40011.0, 1.0)],
            {
                ("bid", 0): (0.0025, 0.75, 30000.0),
                ("bid", 1): (0.025, 0.75, 30000.0),
                ("ask", 0): (0.0024993751562109472, 0.25, 10002.5),
                ("ask", 1): (0.02499375156210947, 0.25, 10002.5),
            },
            (40005.0, 2.4996875390576174),
        ),
        (
            "ETH/BTC",
            [(0.03512, 4.0), (0.03511, 1.0)],
            [(0.03513, 2.5), (0.03514, 1.0)],
            {
                ("bid", 0): (0.05095865722111843, 4.0, 0.14048),
                ("bid", 1): (0.5095865722111843, 4.0, 0.14048),
                ("ask", 0): (0.050944151483224565, 2.5, 0.087825),
                ("ask", 1): (0.5094415148322456, 2.5, 0.087825),
            },
            (0.035125, 2.846975088968843),
        ),
    )
    for pair, bids, asks, quantities, (mid, spread_bps) in cases:
        orders = post_orders(_book(bids, asks, pair), _at(15), pair, stale_seconds=3.5)
        assert sorted((o.side, o.size) for o in orders) == sorted(quantities)
        for o in orders:
            assert o.price == Decimal(str(bids[0][0] if o.side == "bid" else asks[0][0]))
            assert (o.our_qty, o.queue_ahead_qty, o.queue_ahead_notional) == pytest.approx(quantities[(o.side, o.size)], rel=1e-12)
            assert (o.mid_at_post, o.spread_at_post_bps) == pytest.approx((mid, spread_bps), rel=1e-12)
            assert (o.ts, o.pair, o.stale_seconds_at_post, o.ahead_qty, o.is_open) == (_at(15), pair, 3.5, o.queue_ahead_qty, True)


def test_post_orders_skip_both_sides_of_a_one_sided_book():
    assert post_orders(_book(BIDS, []), _at(0), PAIR, stale_seconds=0.0) == []
    assert post_orders(_book([], ASKS), _at(0), PAIR, stale_seconds=0.0) == []


def test_a_stale_book_skips_the_post_and_counts_it():
    gone = [(price, 0.0) for price, _ in ASKS]
    _, carried, _, _, counts = _run(_hour(BIDS, ASKS, [(200, [], gone), (214, [], ASKS)], quiet=(100, 140)))
    assert counts == {"posts": 952, "skipped_no_quote": 4, "skipped_stale": 4}
    posted = {o.ts for o in carried}
    assert len(posted) == 238 and _at(135) not in posted and _at(210) not in posted
    assert _one(carried, 120, "bid").stale_seconds_at_post == 20.0


def test_a_partial_consumption_leaves_the_order_open():
    order = _order("bid", 1000.0)
    apply_trade(order, _trade(1, "sell", 1000.0, 0.6))
    apply_trade(order, _trade(2, "sell", 1000.0, 0.45))
    assert order.is_open and order.ahead_qty == 0.0 and order.filled_qty == pytest.approx(0.05)


def test_a_sell_at_our_bid_fills_once_the_queue_ahead_and_our_order_are_consumed():
    order = _order("bid", 1000.0)
    apply_trade(order, _trade(1, "sell", 1000.0, 0.6))
    apply_trade(order, _trade(2, "sell", 1000.0, 0.45))
    assert order.is_open
    apply_trade(order, _trade(3, "sell", 1000.0, 0.1))
    assert order.filled_at == _at(3) and flush([order])[0]["fill_price"] == 1000.0


def test_a_trade_on_the_wrong_side_never_fills():
    order = _order("bid", 1000.0)
    apply_trade(order, _trade(1, "buy", 1000.0, 2.0))
    apply_trade(order, _trade(2, "buy", 1000.0, 2.0))
    assert order.is_open and (order.ahead_qty, order.filled_qty) == (1.0, 0.0)


def test_a_sell_above_our_bid_never_fills():
    order = _order("bid", 1000.0)
    apply_trade(order, _trade(1, "sell", 1001.0, 2.0))
    apply_trade(order, _trade(2, "sell", 1001.0, 2.0))
    assert order.is_open and (order.ahead_qty, order.filled_qty) == (1.0, 0.0)


def test_a_buy_at_our_ask_fills_once_the_queue_ahead_and_our_order_are_consumed():
    order = _order("ask", 1001.0)
    apply_trade(order, _trade(1, "buy", 1001.0, 0.6))
    apply_trade(order, _trade(2, "buy", 1001.0, 0.45))
    assert order.is_open
    apply_trade(order, _trade(3, "buy", 1001.0, 0.1))
    assert order.filled_at == _at(3) and flush([order])[0]["fill_price"] == 1001.0


def test_a_sell_at_our_ask_never_fills():
    order = _order("ask", 1001.0)
    apply_trade(order, _trade(1, "sell", 1001.0, 2.0))
    apply_trade(order, _trade(2, "sell", 1001.0, 2.0))
    assert order.is_open and (order.ahead_qty, order.filled_qty) == (1.0, 0.0)


def test_a_buy_below_our_ask_never_fills():
    order = _order("ask", 1001.0)
    apply_trade(order, _trade(1, "buy", 1000.0, 2.0))
    apply_trade(order, _trade(2, "buy", 1000.0, 2.0))
    assert order.is_open and (order.ahead_qty, order.filled_qty) == (1.0, 0.0)


def test_a_trade_through_the_price_fills_once_its_quantity_reaches_our_order():
    bid, ask = _order("bid", 1000.0), _order("ask", 1001.0)
    apply_trade(bid, _trade(1, "sell", 999.0, 0.1))
    apply_trade(ask, _trade(1, "buy", 1002.0, 0.1))
    assert [flush([o])[0]["fill_price"] for o in (bid, ask)] == [1000.0, 1001.0]
    assert bid.filled_at == ask.filled_at == _at(1) and (bid.ahead_qty, ask.ahead_qty) == (1.0, 1.0)
    bid, ask = _order("bid", 1000.0), _order("ask", 1001.0)
    apply_trade(bid, _trade(1, "sell", 1000.0, 0.1))
    apply_trade(ask, _trade(1, "buy", 1001.0, 0.1))
    assert bid.is_open and ask.is_open
    bid, ask = _order("bid", 1000.0), _order("ask", 1001.0)
    apply_trade(bid, _trade(1, "sell", 999.0, 0.05))
    apply_trade(ask, _trade(1, "buy", 1002.0, 0.05))
    assert bid.is_open and ask.is_open


def test_trades_fill_exactly_the_third_post_and_no_other():
    hour = _hour(
        [(1000.0, 2.0), (999.0, 1.0), (990.0, 1.0)],
        ASKS,
        [(16, [(1000.0, 0.0)], []), (25, [(1000.0, 0.5)], []), (35, [(1000.0, 3.0)], [])],
        [(38, "sell", 1000.0, 0.4), (44.5, "sell", 1000.0, 3.5)],
    )
    _, carried, _, _, _ = _run(hour)
    filled = {(o.ts, o.side, o.size): o.filled_at for o in carried if o.filled_at is not None}
    assert filled == {(_at(30), "bid", 0): _at(44.5), (_at(30), "bid", 1): _at(44.5)}
    assert [_one(carried, seconds, "bid").cancelled_at for seconds in (0, 15)] == [_at(21), _at(21)]
    assert (_one(carried, 30, "bid").queue_ahead_qty, _one(carried, 45, "bid").queue_ahead_qty) == (0.5, 3.0)


def test_a_removed_level_starts_the_cancel_clock_and_a_fill_before_it_counts():
    book = _book(BIDS, ASKS)
    order = _one(post_orders(book, _at(0), PAIR, stale_seconds=0.0), 0, "bid")
    tick = pair_tick(book)
    _walk(order, book, tick, 4, updates={4: ([(1000.0, 0.0)], [])})
    assert order.away_since == _at(4) and order.is_open
    _walk(order, book, tick, 10, start=5, trades={7: [_trade(7, "sell", 999.0, order.our_qty)]})
    assert order.filled_at == _at(7) and order.cancelled_at is None


def test_the_levels_resting_quantity_caps_the_queue_ahead():
    ours = {"bid": 100 / 1000.0, "ask": 100 / 1001.0}
    cut = _hour(
        BIDS,
        ASKS,
        [(5, [(1000.0, 0.5)], [(1001.0, 0.5)])],
        [(7, "sell", 1000.0, 0.5), (7, "buy", 1001.0, 0.5), (8, "sell", 1000.0, ours["bid"]), (8, "buy", 1001.0, ours["ask"])],
    )
    _, carried, *_ = _run(cut)
    assert [(_one(carried, 0, side).our_qty, _one(carried, 0, side).filled_at) for side in ours] == [
        (ours["bid"], _at(8)),
        (ours["ask"], _at(8)),
    ]
    refilled = _hour(BIDS, ASKS, [(5, [(1000.0, 0.0)], []), (7, [(1000.0, 0.5)], [])], [(9, "sell", 1000.0, ours["bid"])])
    _, carried, *_ = _run(refilled)
    assert _one(carried, 0, "bid").filled_at == _at(9)
    for print_at in (4.5, 5.5):
        _, carried, *_ = _run(_hour(BIDS, ASKS, [(5, [(1000.0, 0.0)], [])], [(print_at, "sell", 1000.0, 1.0)]))
        assert _one(carried, 0, "bid").filled_at is None, print_at


def test_the_cancel_fires_at_the_sixth_away_second_and_resets_when_back():
    book = _book(BIDS, ASKS)
    order = _one(post_orders(book, _at(0), PAIR, stale_seconds=0.0), 0, "bid")
    tick = pair_tick(book)
    _walk(order, book, tick, 7, updates={3: ([(1000.0, 0.0)], [])})
    assert order.away_since == _at(3) and order.cancelled_at is None
    _walk(order, book, tick, 9, start=8)
    assert order.cancelled_at == _at(8)
    book = _book(BIDS, ASKS)
    order = _one(post_orders(book, _at(0), PAIR, stale_seconds=0.0), 0, "bid")
    _walk(order, book, tick, 6, updates={3: ([(1000.0, 0.0)], []), 6: ([(1000.0, 1.0)], [])})
    assert order.away_since is None and order.is_open
    _walk(order, book, tick, 13, start=7, updates={7: ([(1000.0, 0.0)], [])})
    assert order.cancelled_at == _at(12)


def test_an_ask_at_an_unchanged_best_ask_is_never_cancelled_while_the_bid_moves():
    book = _book([(1000.0 - i, 1.0) for i in range(40)], ASKS)
    order = _one(post_orders(book, _at(0), PAIR, stale_seconds=0.0), 0, "ask")
    _walk(order, book, pair_tick(book), 30, updates={s: ([(1001.0 - s, 0.0)], []) for s in range(1, 31)})
    assert max(book.bids) == Decimal("970")
    assert order.is_open and order.away_since is None


def test_a_one_tick_move_off_a_non_binary_grid_starts_the_cancel_clock():
    cases = (
        ("BTC/EUR", [(63412.1, 1.0), (63412.0, 1.0)], [(63412.5, 1.0), (63412.6, 1.0)], 63412.2, Decimal("0.1")),
        ("ETH/BTC", [(0.03512, 1.0), (0.03511, 1.0)], [(0.03514, 1.0), (0.03515, 1.0)], 0.03513, Decimal("0.00001")),
    )
    for pair, bids, asks, better, tick in cases:
        book = _book(bids, asks, pair)
        order = _one(post_orders(book, _at(0), pair, stale_seconds=0.0), 0, "bid")
        assert pair_tick(book) == tick
        _walk(order, book, tick, 9, updates={3: ([(better, 1.0)], [])})
        assert (order.away_since, order.cancelled_at) == (_at(3), _at(8)), pair


def test_a_float64_print_at_exactly_the_orders_price_counts():
    ask, bid = _order("ask", 63412.2), _order("bid", 63412.3)
    for second in (1, 2):
        apply_trade(ask, _trade(second, "buy", 63412.2, 0.6))
        apply_trade(bid, _trade(second, "sell", 63412.3, 0.6))
    assert ask.filled_at == bid.filled_at == _at(2)


def test_the_horizon_cancels_at_900_seconds():
    book = _book(BIDS, ASKS)
    order = _one(post_orders(book, _at(0), PAIR, stale_seconds=0.0), 0, "bid")
    tick = pair_tick(book)
    _walk(order, book, tick, 899)
    assert order.is_open
    _walk(order, book, tick, 901, start=900)
    assert order.cancelled_at == _at(900)


def test_a_trade_after_the_cancel_or_after_the_fill_changes_nothing():
    _, carried, *_ = _run(_hour(BIDS, ASKS, [(20, [(1000.0, 0.0)], [])], [(30, "sell", 1000.0, 2.0)]))
    cancelled = _one(carried, 0, "bid")
    assert (cancelled.cancelled_at, cancelled.filled_at, cancelled.filled_qty) == (_at(25), None, 0.0)
    _, carried, *_ = _run(_hour(BIDS, ASKS, trades=[(5, "sell", 1000.0, 1.2), (8, "sell", 1000.0, 2.0)]))
    filled = _one(carried, 0, "bid")
    assert filled.filled_at == _at(5) and filled.filled_qty == pytest.approx(0.2)
    assert _one(carried, 0, "bid", 1).filled_at == _at(8)


def test_the_mid_offsets_are_read_at_the_first_boundary_at_or_after_the_instant():
    first = _hour(
        BIDS,
        LADDER,
        [(70.5, [], [(1002.0, 0.0)]), (899.6, [], [(1004.0, 0.0)]), (910.5, [], [(1006.0, 0.0)])],
        [(10.4, "sell", 1000.0, 1.2)],
    )
    _, carried, book, last, _ = _run(first)
    second = _hour(BIDS, LADDER, [(0, [], [(1008.0, 0.0)])], hour=H2, snapshot=False)
    rows, *_ = _run(second, hour=H2, carried=carried, book=book, last_msg_ts=last)
    row = _row_of(rows, 0, "bid")
    assert (row["filled"], row["time_to_fill_s"], row["fill_price"]) == (True, 10.4, 1000.0)
    mids = ("mid_at_fill_plus_60s", "mid_at_fill_plus_900s", "mid_at_post_plus_900s", "mid_at_post_plus_3600s")
    assert [row[name] for name in mids] == [1002.0, 1004.0, 1003.0, 1005.0]


def test_a_mid_in_a_stale_stretch_is_read_at_the_first_fresh_second_after_it():
    _, carried, *_ = _run(_hour(BIDS, ASKS, [(905, [], [(1001.0, 0.0)])], quiet=(865, 905)))
    assert _one(carried, 0, "bid").mids["mid_at_post_plus_900s"] == 1001.0


def test_a_closed_order_waits_for_its_post_plus_3600s_mid_across_the_hour():
    rows, carried, book, last, _ = _run(_hour(BIDS, LADDER, trades=[(2750.5, "sell", 1000.0, 1.2)]))
    assert rows == [] and _one(carried, 2400, "bid").filled_at == _at(2750.5)
    second = _hour(BIDS, LADDER, [(50.5, [], [(1002.0, 0.0)]), (2399.5, [], [(1004.0, 0.0)])], hour=H2, snapshot=False)
    rows, carried, *_ = _run(second, hour=H2, carried=carried, book=book, last_msg_ts=last)
    row = _row_of(rows, 2400, "bid")
    assert (row["time_to_fill_s"], row["mid_at_fill_plus_900s"], row["mid_at_post_plus_3600s"]) == (350.5, 1002.0, 1003.0)
    assert (row["mid_at_fill_plus_60s"], row["mid_at_post_plus_900s"]) == (1001.0, 1001.0)
    assert _at(2400) not in {o.ts for o in carried}


def test_flush_nulls_the_unreached_mids_and_censors_an_open_order():
    still_open, filled = _order("bid", 1000.0), _order("ask", 1001.0)
    still_open.mids = {"mid_at_post_plus_900s": 1001.0}
    filled.filled_at = _at(12)
    filled.mids = {"mid_at_fill_plus_60s": 1002.0, "mid_at_post_plus_900s": 1003.0}
    censored, closed = flush([still_open, filled])
    outcome = ("filled", "time_to_fill_s", "cancelled_s", "fill_price")
    mids = ("mid_at_fill_plus_60s", "mid_at_fill_plus_900s", "mid_at_post_plus_900s", "mid_at_post_plus_3600s")
    assert [censored[name] for name in outcome] == [False, None, None, None]
    assert [censored[name] for name in mids] == [None, None, 1001.0, None]
    assert [closed[name] for name in outcome] == [True, 12.0, None, 1001.0]
    assert [closed[name] for name in mids] == [1002.0, None, 1003.0, None]


def test_an_order_carried_across_the_hour_keeps_its_clock():
    _, carried, book, last, _ = _run(_hour(BIDS, ASKS))
    second = _hour(BIDS, ASKS, trades=[(3, "sell", 1000.0, 1.2)], hour=H2, snapshot=False)
    rows, *_ = _run(second, hour=H2, carried=carried, book=book, last_msg_ts=last)
    row = _row_of(rows, 3585, "bid")
    assert (row["filled"], row["time_to_fill_s"]) == (True, 18.0)


def test_the_last_fractional_second_is_drained_for_the_next_hour():
    first = _hour(BIDS, ASKS, messages=[(3599.5, [(1000.0, 0.0)], [])], trades=[(3599.5, "sell", 1000.0, 1.1)])
    _, carried, book, last, _ = _run(first)
    assert max(book.bids) == Decimal("999")
    second = _hour(BIDS, ASKS, hour=H2, snapshot=False)
    rows, *_ = _run(second, hour=H2, carried=carried, book=book, last_msg_ts=last)
    row = _row_of(rows, 3585, "bid")
    assert (row["filled"], row["time_to_fill_s"]) == (True, 14.5)


def test_pair_tick_is_the_smallest_level_gap_and_zero_on_a_one_level_book():
    book = _book([(100.0, 1.0), (99.5, 1.0), (99.0, 1.0), (97.0, 1.0)], [(100.7, 1.0), (100.8, 1.0), (101.5, 1.0)])
    assert pair_tick(book) == Decimal("0.1")
    assert pair_tick(_book([(100.0, 1.0), (99.0, 1.0)], [(101.0, 1.0)])) == Decimal("1")
    assert pair_tick(_book([(100.0, 1.0)], [(101.0, 1.0)])) == Decimal(0)
    assert pair_tick(_book([], [])) == Decimal(0)


def test_rows_frame_has_the_eighteen_columns_in_order():
    names = [
        "ts",
        "pair",
        "side",
        "size",
        "mid_at_post",
        "spread_at_post_bps",
        "stale_seconds_at_post",
        "queue_ahead_qty",
        "queue_ahead_notional",
        "our_qty",
        "filled",
        "time_to_fill_s",
        "cancelled_s",
        "fill_price",
        "mid_at_fill_plus_60s",
        "mid_at_fill_plus_900s",
        "mid_at_post_plus_900s",
        "mid_at_post_plus_3600s",
    ]
    assert list(COLUMNS) == names
    orders = [_order("ask", 1001.0), _order("bid", 1000.0), _order("bid", 1000.0), _order("ask", 1001.0)]
    orders[0].ts, orders[2].size = _at(15), 1
    frame = rows_frame(flush(orders))
    assert frame.columns == names
    kinds = {"ts": pl.Datetime("us", "UTC"), "pair": pl.String, "side": pl.String, "size": pl.Int64, "filled": pl.Boolean}
    assert dict(frame.schema) == {name: kinds.get(name, pl.Float64) for name in names}
    assert frame.select("ts", "side", "size").rows() == [
        (_at(0), "ask", 0),
        (_at(0), "bid", 0),
        (_at(0), "bid", 1),
        (_at(15), "ask", 0),
    ]
