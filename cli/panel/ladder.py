"""The engine's maker-first ladder replayed at a cycle boundary over the captured book (spec 00153 D2): four orders
posted at the touch `POST_OFFSET_S` into the boundary hour, resting under the fill model's rule with no away-cancel
for `BOX_S`, each recorded with the opposite touch at the box end -- the fallback's price."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl

from cli.capture.book import OrderBook
from cli.panel import fills

BOUNDARY_HOURS = (0, 4, 8, 12, 16, 20)
POST_OFFSET_S = 120
BOX_S = 900

COLUMNS = (
    "ts",
    "pair",
    "side",
    "size",
    "price",
    "our_qty",
    "queue_ahead_qty",
    "mid_at_post",
    "spread_at_post_bps",
    "filled",
    "time_to_fill_s",
    "fill_price",
    "box_end_mid",
    "box_end_touch_price",
    "box_end_touch_qty",
    "met_qty",
)
_KINDS: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "pair": pl.String(),
    "side": pl.String(),
    "size": pl.Int64(),
    "filled": pl.Boolean(),
}
_SCHEMA: dict[str, pl.DataType] = {name: _KINDS.get(name, pl.Float64()) for name in COLUMNS}
_BOX_END_S = POST_OFFSET_S + BOX_S


def _opposite_touch(order: fills.Order, book: OrderBook) -> tuple[float, float]:
    levels, best = (book.asks, min) if order.side == "bid" else (book.bids, max)
    price = best(levels)
    return float(price), float(levels[price])


def _row(order: fills.Order, book: OrderBook, box_end_mid: float | None) -> dict:
    filled = order.filled_at is not None
    touch_price, touch_qty = _opposite_touch(order, book) if box_end_mid is not None else (None, None)
    return {
        "ts": order.ts,
        "pair": order.pair,
        "side": order.side,
        "size": order.size,
        "price": float(order.price),
        "our_qty": order.our_qty,
        "queue_ahead_qty": order.queue_ahead_qty,
        "mid_at_post": order.mid_at_post,
        "spread_at_post_bps": order.spread_at_post_bps,
        "filled": filled,
        "time_to_fill_s": (order.filled_at - order.ts).total_seconds() if filled else None,
        "fill_price": float(order.price) if filled else None,
        "box_end_mid": box_end_mid,
        "box_end_touch_price": touch_price,
        "box_end_touch_qty": touch_qty,
        "met_qty": order.filled_qty,
    }


def simulate_episode(
    messages: list[dict],
    trades: list[dict],
    book: OrderBook,
    hour: datetime,
    *,
    pair: str,
    last_msg_ts: datetime | None,
) -> tuple[list[dict], dict[str, int]]:
    """Run one boundary hour's episode over its book hour's `regroup_messages` and its trades hour's rows sorted by
    `ts`, second by second as `fills.simulate_hour` takes them, up to the box end and no message or print after it.

    Returns `(rows, counts)`: a row per order posted, `counts` the posts and the skips, in orders."""
    counts = {"posts": 0, "skipped_no_quote": 0, "skipped_stale": 0}
    orders: list[fills.Order] = []
    msg_idx = trade_idx = 0
    for second in range(_BOX_END_S + 1):
        boundary = hour + timedelta(seconds=second)
        while msg_idx < len(messages) and messages[msg_idx]["ts"] <= boundary:
            last_msg_ts = fills._ingest(book, messages[msg_idx])
            msg_idx += 1
        while trade_idx < len(trades) and trades[trade_idx]["ts"] <= boundary:
            for order in orders:
                fills.apply_trade(order, trades[trade_idx])
            trade_idx += 1
        for order in orders:
            if order.is_open:
                fills.cap_queue(order, book)
        if second == POST_OFFSET_S:
            orders = fills._post(book, boundary, pair, last_msg_ts, counts)
    box_end_mid = fills._fresh_mid(book, hour + timedelta(seconds=_BOX_END_S), last_msg_ts)
    return [_row(order, book, box_end_mid) for order in orders], counts


def rows_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=_SCHEMA).sort("ts", "side", "size")
