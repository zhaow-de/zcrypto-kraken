"""The queue-position fill model over the replayed depth-100 book and the healed trades (spec 00151 D2).

Every `GRID_S` seconds four passive orders -- bid and ask, at each rung of `SIZE_RUNGS` -- join the back of the queue at
the touch. An order fills once the prints at or through its price have met its whole quantity, the queue ahead first;
it cancels once its side's best quote has stood a tick or more away for `CANCEL_AFTER_S` seconds, or at `HORIZON_S`.
Each post becomes one row once the mid an hour after it is read. Prices compare as `Decimal`, the book's own type, and
are written as Float64.
"""

from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

import polars as pl

from cli.capture.book import OrderBook
from cli.panel.materialize import SECONDS_PER_HOUR
from cli.panel.primitives import notionals_for

GRID_S = 15
HORIZON_S = 900
CANCEL_AFTER_S = 5
STALE_S = 30
SIZE_RUNGS = (0, 1)
MID_OFFSETS_S = (60, 900, 3600)

COLUMNS = (
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
)
_KINDS: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "pair": pl.String(),
    "side": pl.String(),
    "size": pl.Int64(),
    "filled": pl.Boolean(),
}
_SCHEMA: dict[str, pl.DataType] = {name: _KINDS.get(name, pl.Float64()) for name in COLUMNS}

_FILL_MIDS = (("mid_at_fill_plus_60s", MID_OFFSETS_S[0]), ("mid_at_fill_plus_900s", MID_OFFSETS_S[1]))
_POST_MIDS = (("mid_at_post_plus_900s", MID_OFFSETS_S[1]), ("mid_at_post_plus_3600s", MID_OFFSETS_S[2]))
# The last of a post's instants: a fill comes by post + 900 s, so its own mids are read by post + 1800 s.
_LAST_MID = "mid_at_post_plus_3600s"
_ORDERS_PER_POST = 2 * len(SIZE_RUNGS)


@dataclass
class Order:
    ts: datetime
    pair: str
    side: str
    size: int
    price: Decimal
    our_qty: float
    queue_ahead_qty: float
    queue_ahead_notional: float
    mid_at_post: float
    spread_at_post_bps: float
    stale_seconds_at_post: float | None
    filled_qty: float = 0.0  # the part of our order the prints at or through its price have met
    away_since: datetime | None = None
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    mids: dict[str, float] = field(default_factory=dict)  # the mids read so far, by column name
    ahead_qty: float = field(init=False)  # the queue ahead's bound: `apply_trade` lowers it, `tick_cancel` caps it
    level_qty: float = field(init=False)  # the level's resting quantity at `price` as the last boundary left it

    def __post_init__(self) -> None:
        self.ahead_qty = self.queue_ahead_qty
        self.level_qty = self.queue_ahead_qty

    @property
    def is_open(self) -> bool:
        return self.filled_at is None and self.cancelled_at is None


def post_orders(book: OrderBook, ts: datetime, pair: str, *, stale_seconds: float | None) -> list[Order]:
    """The four orders at the touch, each at the back of its level's queue; none when either side is empty, since a
    one-sided book has no mid. `our_qty` is the rung's notional in the pair's quote over the price."""
    quoted = [(side, levels) for side, levels in (("bid", book.bids), ("ask", book.asks)) if levels]
    if len(quoted) < 2:
        return []
    bid, ask = float(max(book.bids)), float(min(book.asks))
    mid = (bid + ask) / 2
    spread_bps = (ask - bid) / mid * 1e4
    notionals = notionals_for(pair.split("/")[-1])
    orders = []
    for side, levels in quoted:
        price = max(levels) if side == "bid" else min(levels)
        queue_ahead = float(levels[price])
        for rung in SIZE_RUNGS:
            orders.append(
                Order(
                    ts=ts,
                    pair=pair,
                    side=side,
                    size=rung,
                    price=price,
                    our_qty=notionals[rung] / float(price),
                    queue_ahead_qty=queue_ahead,
                    queue_ahead_notional=queue_ahead * float(price),
                    mid_at_post=mid,
                    spread_at_post_bps=spread_bps,
                    stale_seconds_at_post=stale_seconds,
                )
            )
    return orders


def apply_trade(order: Order, trade: dict) -> None:
    """Meet an open order with one print of the trades frame -- a sell at or below a bid's price, a buy at or above an
    ask's. At the price the print meets the queue ahead first; through it, price priority has met every order resting
    at the price already, so its whole quantity meets ours. The order fills, whole or not at all, once what the prints
    have met of it reaches `our_qty`; any other print, and any print on a closed order, changes nothing."""
    if not order.is_open:
        return
    price = Decimal(str(trade["price"]))  # the conversion `OrderBook` makes of a level's Float64 price
    if order.side == "bid":
        meets = trade["side"] == "sell" and price <= order.price
        through = price < order.price
    else:
        meets = trade["side"] == "buy" and price >= order.price
        through = price > order.price
    if not meets:
        return
    if through:
        order.filled_qty += trade["qty"]
    else:
        order.filled_qty += max(0.0, trade["qty"] - order.ahead_qty)
        order.ahead_qty = max(0.0, order.ahead_qty - trade["qty"])
    if order.filled_qty >= order.our_qty:
        order.filled_at = trade["ts"]


def tick_cancel(order: Order, book: OrderBook, ts: datetime, tick: Decimal) -> None:
    """At the boundary `ts`, after its prints: cap an open order's queue ahead at its level as the boundary before left
    it, read the level for the next boundary's cap, then run the cancel clock -- away while the order's side is empty
    or its best quote stands `tick` or more from the order's price; cancelled on the sixth away second in a row, or at
    the horizon."""
    if not order.is_open:
        return
    own = book.bids if order.side == "bid" else book.asks
    # The level is read a second late (spec 00151 D2): a print's book update can land at the boundary before the
    # print, and a level read at the print's own boundary would count that print against the queue ahead twice.
    order.ahead_qty = min(order.ahead_qty, order.level_qty)
    order.level_qty = float(own.get(order.price, 0))
    best = max(book.bids, default=None) if order.side == "bid" else min(book.asks, default=None)
    away = best is None or (best != order.price and abs(best - order.price) >= tick)
    if not away:
        order.away_since = None
    elif order.away_since is None:
        order.away_since = ts
    away_s = (ts - order.away_since).total_seconds() if order.away_since is not None else 0.0
    if away_s >= CANCEL_AFTER_S or (ts - order.ts).total_seconds() >= HORIZON_S:
        order.cancelled_at = ts


def pair_tick(book: OrderBook) -> Decimal:
    """The smallest gap between consecutive levels on either side, the tick's proxy; 0 when neither side holds two
    levels, and with a tick of 0 any move is away."""
    gaps = [high - low for levels in (book.bids, book.asks) for low, high in itertools.pairwise(sorted(levels))]
    return min(gaps, default=Decimal(0))


def _staleness(boundary: datetime, last_msg_ts: datetime | None) -> float | None:
    return (boundary - last_msg_ts).total_seconds() if last_msg_ts is not None else None


def _fresh_mid(book: OrderBook, boundary: datetime, last_msg_ts: datetime | None) -> float | None:
    """The book's mid at `boundary`, or None when either side is empty or the book is stale -- a frozen book's mid is a
    carried one, never read."""
    stale = _staleness(boundary, last_msg_ts)
    if not book.bids or not book.asks or (stale is not None and stale > STALE_S):
        return None
    return (float(max(book.bids)) + float(min(book.asks))) / 2


def _post(book: OrderBook, boundary: datetime, pair: str, last_msg_ts: datetime | None, counts: dict[str, int]) -> list[Order]:
    stale = _staleness(boundary, last_msg_ts)
    if stale is not None and stale > STALE_S:
        counts["skipped_stale"] += _ORDERS_PER_POST
        return []
    orders = post_orders(book, boundary, pair, stale_seconds=stale)
    counts["posts" if orders else "skipped_no_quote"] += _ORDERS_PER_POST
    return orders


def _await(pending: list, seq: itertools.count, order: Order, mids: tuple[tuple[str, int], ...], start: datetime) -> None:
    for name, offset in mids:
        if name not in order.mids:
            heapq.heappush(pending, (start + timedelta(seconds=offset), next(seq), name, order))


def _ingest(book: OrderBook, message: dict) -> datetime:
    if message["type"] == "snapshot":
        book.ingest_snapshot(message)
    else:
        book.ingest_update(message)
    return message["ts"]


def _row(order: Order) -> dict:
    filled = order.filled_at is not None
    return {
        "ts": order.ts,
        "pair": order.pair,
        "side": order.side,
        "size": order.size,
        "mid_at_post": order.mid_at_post,
        "spread_at_post_bps": order.spread_at_post_bps,
        "stale_seconds_at_post": order.stale_seconds_at_post,
        "queue_ahead_qty": order.queue_ahead_qty,
        "queue_ahead_notional": order.queue_ahead_notional,
        "our_qty": order.our_qty,
        "filled": filled,
        "time_to_fill_s": (order.filled_at - order.ts).total_seconds() if filled else None,
        "cancelled_s": (order.cancelled_at - order.ts).total_seconds() if order.cancelled_at is not None else None,
        "fill_price": float(order.price) if filled else None,
        **{name: order.mids.get(name) for name, _ in _FILL_MIDS + _POST_MIDS},
    }


def simulate_hour(
    messages: list[dict],
    trades: list[dict],
    book: OrderBook,
    hour: datetime,
    *,
    pair: str,
    carried: list[Order],
    last_msg_ts: datetime | None,
) -> tuple[list[dict], list[Order], OrderBook, datetime | None, dict]:
    """Run one hour of the fill model over the book hour's `regroup_messages` and the trades hour's rows sorted by `ts`,
    in `materialize_hour`'s loop: at each second boundary of the hour apply the messages up to it, then meet every open
    order with the prints up to it, then run each open order's cap and cancel clock, then read each order's pending mids
    whose instant has come -- at a fresh book, both sides quoted -- turning an order into a row once its `post + 3600 s`
    mid is read; then, on a grid second, post the four orders unless the book is stale or one-sided. The messages and
    prints after the last boundary are applied after the loop, for the next hour to carry.

    Returns `(rows, carried, book, last_msg_ts, counts)`: `carried` every open order and every closed one whose
    `post + 3600 s` mid is unread, `counts` the posts and the skips, in orders."""
    carried = list(carried)
    live = [order for order in carried if order.is_open]
    pending: list[tuple[datetime, int, str, Order]] = []
    seq = itertools.count()
    for order in carried:
        _await(pending, seq, order, _POST_MIDS, order.ts)
        if order.filled_at is not None:
            _await(pending, seq, order, _FILL_MIDS, order.filled_at)
    rows: list[dict] = []
    counts = {"posts": 0, "skipped_no_quote": 0, "skipped_stale": 0}
    msg_idx = trade_idx = 0
    tick = Decimal(0)
    for second in range(SECONDS_PER_HOUR):
        boundary = hour + timedelta(seconds=second)
        while msg_idx < len(messages) and messages[msg_idx]["ts"] <= boundary:
            last_msg_ts = _ingest(book, messages[msg_idx])
            msg_idx += 1
        on_grid = second % GRID_S == 0
        if on_grid:
            tick = pair_tick(book)
        while trade_idx < len(trades) and trades[trade_idx]["ts"] <= boundary:
            for order in live:
                if order.is_open:
                    apply_trade(order, trades[trade_idx])
                    if order.filled_at is not None:
                        _await(pending, seq, order, _FILL_MIDS, order.filled_at)
            trade_idx += 1
        for order in live:
            tick_cancel(order, book, boundary, tick)
        live = [order for order in live if order.is_open]
        mid = _fresh_mid(book, boundary, last_msg_ts)
        while mid is not None and pending and pending[0][0] <= boundary:
            _, _, name, order = heapq.heappop(pending)
            order.mids[name] = mid
            if name == _LAST_MID:
                rows.append(_row(order))
        if on_grid:
            for order in _post(book, boundary, pair, last_msg_ts, counts):
                carried.append(order)
                live.append(order)
                _await(pending, seq, order, _POST_MIDS, order.ts)
    for message in messages[msg_idx:]:
        last_msg_ts = _ingest(book, message)
    for trade in trades[trade_idx:]:
        for order in live:
            apply_trade(order, trade)
    carried = [order for order in carried if _LAST_MID not in order.mids]
    return rows, carried, book, last_msg_ts, counts


def flush(carried: list[Order]) -> list[dict]:
    """Every carried order as a row where the data ends: its unread mids null, an order still open a censored post."""
    return [_row(order) for order in carried]


def rows_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=_SCHEMA).sort("ts", "side", "size")
