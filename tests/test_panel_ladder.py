"""The ladder episode of `cli/panel/ladder.py` and the queue cap it shares with the fill model (spec 00153 D2), each
case on a known answer over a synthetic boundary hour."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import polars as pl

from cli.archive.replay import regroup_messages
from cli.capture.book import OrderBook
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA
from cli.panel.fills import cap_queue, post_orders
from cli.panel.ladder import simulate_episode

H = datetime(2026, 9, 2, 12, tzinfo=UTC)
PAIR = "BTC/EUR"
BIDS = [(1000.0, 1.0), (999.0, 1.0), (990.0, 1.0)]
# Two ticks of spread, so the best bid can step a tick up without crossing.
ASKS = [(1002.0, 0.8), (1003.0, 1.0), (1010.0, 1.0)]
GONE_ASKS = [(price, 0.0) for price, _ in ASKS]
OUR_SMALL_BID = 100 / 1000.0


def _at(seconds: float) -> datetime:
    return H + timedelta(seconds=seconds)


def _levels(levels: list[tuple[float, float]]) -> list[dict]:
    return [{"price": price, "qty": qty} for price, qty in levels]


def _book(bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> OrderBook:
    book = OrderBook(PAIR, 100)
    book.ingest_snapshot({"bids": _levels(bids), "asks": _levels(asks), "checksum": 0})
    return book


def _update(book: OrderBook, bids: list[tuple[float, float]], asks: list[tuple[float, float]]) -> None:
    book.ingest_update({"bids": _levels(bids), "asks": _levels(asks), "checksum": 0})


def _hour(messages=(), trades=(), *, quiet=None):
    """The boundary hour's book messages as `regroup_messages` rebuilds them from the exploded rows, and its prints as
    the trades frame's rows: a snapshot of `BIDS` and `ASKS` at :00, the deepest bid restated every 5 s outside the open
    interval `quiet` (seconds into the hour), and the planted `messages` -- `(offset, bids, asks)`, a level of qty 0
    removing it -- and `trades` -- `(offset, side, price, qty)`."""
    planned = [(0.0, "snapshot", BIDS, ASKS)]
    planned += [(float(s), "update", [min(BIDS)], []) for s in range(5, 3600, 5) if quiet is None or not quiet[0] < s < quiet[1]]
    planned += [(float(offset), "update", b, a) for offset, b, a in messages]
    planned.sort(key=lambda message: message[0])
    rows = [
        {"ts": _at(offset), "symbol": PAIR, "type": kind, "side": side, "price": price, "qty": qty, "checksum": n}
        for n, (offset, kind, b, a) in enumerate(planned)
        for side, levels in (("bid", b), ("ask", a))
        for price, qty in levels
    ]
    prints = [
        {"ts": _at(offset), "symbol": PAIR, "side": side, "price": price, "qty": qty, "ord_type": "limit", "trade_id": n}
        for n, (offset, side, price, qty) in enumerate(trades)
    ]
    frame = pl.DataFrame(prints, schema=TRADE_SCHEMA).sort("ts", maintain_order=True)
    return regroup_messages(pl.DataFrame(rows, schema=BOOK_SCHEMA)), frame.to_dicts()


def _episode(messages=(), trades=(), *, quiet=None) -> tuple[list[dict], dict[str, int]]:
    hour_messages, hour_trades = _hour(messages, trades, quiet=quiet)
    return simulate_episode(hour_messages, hour_trades, OrderBook(PAIR, 100), H, pair=PAIR, last_msg_ts=None)


def _row(rows: list[dict], side: str, size: int = 0) -> dict:
    [row] = [r for r in rows if r["side"] == side and r["size"] == size]
    return row


def test_cap_queue_caps_at_the_cut_and_reads_the_refill():
    for side, price in (("bid", 1000.0), ("ask", 1002.0)):
        book = _book(BIDS, ASKS)
        [order] = [o for o in post_orders(book, _at(120), PAIR, stale_seconds=0.0) if o.side == side and o.size == 0]
        for qty, capped in ((0.5, (order.queue_ahead_qty, 0.5)), (3.0, (0.5, 3.0))):
            level = [(price, qty)]
            _update(book, *((level, []) if side == "bid" else ([], level)))
            cap_queue(order, book)
            assert (order.ahead_qty, order.level_qty) == capped, (side, qty)


def test_the_episode_caps_the_queue_at_the_level_a_second_late():
    rows, _ = _episode([(125, [(1000.0, 0.5)], [])], [(127, "sell", 1000.0, 0.5), (128, "sell", 1000.0, OUR_SMALL_BID)])
    assert (_row(rows, "bid")["filled"], _row(rows, "bid")["time_to_fill_s"]) == (True, 8.0)
    rows, _ = _episode([(125, [(1000.0, 0.0)], [])], [(125.5, "sell", 1000.0, 1.0)])
    assert [_row(rows, "bid", size)["filled"] for size in (0, 1)] == [False, False]


def test_orders_post_at_boundary_plus_120s():
    rows, counts = _episode([(120, [(1000.5, 0.7)], [])])
    assert len(rows) == 4 and {row["ts"] for row in rows} == {_at(120)} and counts["posts"] == 4
    for size in (0, 1):
        assert (_row(rows, "bid", size)["price"], _row(rows, "bid", size)["queue_ahead_qty"]) == (1000.5, 0.7)
    bid, ask = 1000.5, 1002.0
    for size, notional in ((0, 100.0), (1, 1000.0)):
        assert (_row(rows, "bid", size)["our_qty"], _row(rows, "ask", size)["our_qty"]) == (notional / bid, notional / ask)
    spread_bps = (ask - bid) / ((bid + ask) / 2) * 1e4
    assert [(row["spread_at_post_bps"], row["pair"]) for row in rows] == [(spread_bps, PAIR)] * 4


def test_a_print_at_second_300_fills_the_bid_and_never_the_ask():
    rows, _ = _episode(trades=[(60, "sell", 1000.0, 5.0), (120, "sell", 1000.0, 5.0), (300, "sell", 1000.0, 2.0)])
    outcome = ("filled", "time_to_fill_s", "fill_price", "box_end_touch_price", "box_end_touch_qty")
    for size in (0, 1):
        assert [_row(rows, "bid", size)[name] for name in outcome] == [True, 180.0, 1000.0, 1002.0, 0.8]
        assert [_row(rows, "ask", size)[name] for name in outcome] == [False, None, None, 1000.0, 1.0]


def test_an_order_the_touch_leaves_and_returns_to_is_filled_by_a_later_print():
    rows, _ = _episode([(130, [(1001.0, 0.4)], []), (400, [(1001.0, 0.0)], [])], [(500, "sell", 1000.0, 2.0)])
    outcome = [(_row(rows, "bid", size)["filled"], _row(rows, "bid", size)["time_to_fill_s"]) for size in (0, 1)]
    assert outcome == [(True, 380.0), (True, 380.0)]


def test_the_box_end_reads_the_opposite_touch_at_post_plus_900s():
    touches = [
        (1019, [(1000.2, 0.21)], [(1001.8, 0.31)]),
        (1020, [(1000.4, 0.22)], [(1001.7, 0.32)]),
        (1021, [(1000.6, 0.23)], [(1001.4, 0.33)]),
    ]
    rows, _ = _episode(touches)
    touch = ("box_end_touch_price", "box_end_touch_qty")
    for size in (0, 1):
        assert [_row(rows, "bid", size)[name] for name in touch] == [1001.7, 0.32]
        assert [_row(rows, "ask", size)[name] for name in touch] == [1000.4, 0.22]
    box_end_mid = (1000.4 + 1001.7) / 2
    assert [row["box_end_mid"] for row in rows] == [box_end_mid] * 4
    assert all(row["mid_at_post"] != box_end_mid for row in rows)


def test_a_print_at_the_box_end_second_fills_and_one_after_does_not():
    rows, _ = _episode(trades=[(1020, "sell", 1000.0, 2.0)])
    assert [(_row(rows, "bid", size)["filled"], _row(rows, "bid", size)["time_to_fill_s"]) for size in (0, 1)] == [
        (True, 900.0),
        (True, 900.0),
    ]
    rows, _ = _episode(trades=[(1021, "sell", 1000.0, 2.0)])
    assert [_row(rows, "bid", size)["filled"] for size in (0, 1)] == [False, False]


def test_an_order_larger_than_the_box_end_touch_is_recorded_larger():
    rows, _ = _episode([(1000, [], [(1002.0, 0.5)])])
    small, large = _row(rows, "bid", 0), _row(rows, "bid", 1)
    assert (large["box_end_touch_price"], large["box_end_touch_qty"]) == (1002.0, 0.5)
    assert large["box_end_touch_qty"] < large["our_qty"] and small["box_end_touch_qty"] > small["our_qty"]


def test_an_order_the_prints_partly_met_is_recorded_unfilled_with_its_met_qty():
    rows, _ = _episode(trades=[(300, "sell", 1000.0, 1.25)])
    small, large = _row(rows, "bid", 0), _row(rows, "bid", 1)
    assert (small["filled"], large["filled"], large["met_qty"]) == (True, False, 0.25)
    assert [_row(rows, "ask", size)["met_qty"] for size in (0, 1)] == [0.0, 0.0]


def test_a_stale_or_one_sided_box_end_records_no_touch():
    stale, _ = _episode(quiet=(980, 3600))
    one_sided, _ = _episode([(1020, [], GONE_ASKS)])
    box_end = ("box_end_mid", "box_end_touch_price", "box_end_touch_qty")
    for rows in (stale, one_sided):
        assert len(rows) == 4 and all(row[name] is None for row in rows for name in box_end)


def test_a_stale_or_one_sided_book_at_the_post_skips_and_counts():
    rows, counts = _episode(quiet=(85, 3600))
    assert (rows, counts) == ([], {"posts": 0, "skipped_no_quote": 0, "skipped_stale": 4})
    rows, counts = _episode([(120, [], GONE_ASKS)])
    assert (rows, counts) == ([], {"posts": 0, "skipped_no_quote": 4, "skipped_stale": 0})
