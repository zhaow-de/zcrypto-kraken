"""The queue-position fill model over the replayed depth-100 book and the healed trades (spec 00151 D2).

Prices compare as `Decimal`, the book's own type, and are written as Float64.
"""

from __future__ import annotations

import heapq
import itertools
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.archive.replay import regroup_messages
from cli.capture.book import OrderBook
from cli.capture.segment_writer import _replace_durably
from cli.data.manifest import build_manifest, series_entry
from cli.ohlc.dataset import dataset_hash
from cli.panel.errors import PanelError
from cli.panel.materialize import SECONDS_PER_HOUR, _code_ref, _state_path, load_state
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
    have met of it reaches `our_qty`."""
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
    on `materialize_hour`'s second boundaries; the messages and prints after the last boundary are applied after the
    loop, for the next hour to carry.

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


RUN_RECORD = "fills-run.json"
PRODUCER = "zcrypto panel fills"
_HOUR = timedelta(hours=1)
_DAY = timedelta(days=1)
_POSTS_PER_HOUR = SECONDS_PER_HOUR // GRID_S * _ORDERS_PER_POST
_DAY_NAME = re.compile(r"^(\d{2})\.parquet$")
_LISTS = ("hours_unanchored", "hours_absent", "trades_absent", "book_reconciled", "trades_reconciled")


def _require_root(root: Path) -> None:
    """Refuse a root that cannot be listed as a directory: a stat passes a directory the mount cannot scan, and
    `canonical_segments` reads an overlay it cannot stat as no overlay and a root it cannot scan as empty."""
    try:
        os.listdir(root)
    except OSError as exc:
        raise PanelError(f"{root} cannot be read as a directory: {exc}") from exc


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _hours(start: datetime, until: datetime) -> list[datetime]:
    hours = []
    hour = start
    while hour < until:
        hours.append(hour)
        hour += _HOUR
    return hours


def _pair_root(out_root: Path, pair: str) -> Path:
    base, quote = pair.split("/")
    return out_root / base / quote


def _day_files(pair_root: Path) -> dict[date, Path]:
    days = {}
    for path in pair_root.glob("*/*/*.parquet"):
        if (match := _DAY_NAME.match(path.name)) is None:
            continue
        try:
            days[date(int(path.parts[-3]), int(path.parts[-2]), int(match.group(1)))] = path
        except ValueError:  # a hand-made directory that is not a date -- not ours
            continue
    return days


def _read_record(pair_root: Path) -> dict | None:
    path = pair_root / RUN_RECORD
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except ValueError as exc:
        raise PanelError(f"{path} is not a run record: {exc}") from exc


def _check_run_record(pair_root: Path, params: dict, code_ref: str) -> None:
    """A resume continues only the run that wrote the pair's record."""
    record = _read_record(pair_root)
    if record is None:
        if stray := sorted(_day_files(pair_root).values()):
            raise PanelError(
                f"{pair_root} holds day files (e.g. {stray[0]}) and no {RUN_RECORD}: the run that wrote them is unknown"
            )
        return
    if record["params"] != params or record["code_ref"] != code_ref:
        raise PanelError(
            f"{pair_root / RUN_RECORD}: written with params {record['params']} at code {record['code_ref']}, "
            f"not this run's params {params} at code {code_ref} -- a change is a new out root"
        )


def _healed(path: Path, reconciled_root: Path | None) -> bool:
    return reconciled_root is not None and path.is_relative_to(reconciled_root)


def _listing(
    primary_root: Path, reconciled_root: Path | None, pair: str, hours: set[datetime], *, kind: str
) -> dict[datetime, Path]:
    return {
        hour: path
        for seg_pair, hour, path in canonical_segments(primary_root, reconciled_root, kind=kind)
        if seg_pair == pair and hour in hours
    }


def seed_book(panel_root: Path, pair: str, hour: datetime, *, depth: int) -> tuple[OrderBook | None, datetime | None]:
    """The panel's book and clock as the hour before `hour` left them, `(None, None)` where the panel holds no state for
    that hour. A state the read cannot open, or one `load_state` returns no book for, refuses the run: over the soft mount
    a read error is an exit 1, never a counted gap."""
    before = hour - _HOUR
    path = _state_path(panel_root, pair, before)
    try:
        path.read_bytes()
    except FileNotFoundError:
        return None, None
    except OSError as exc:
        raise PanelError(f"{pair}: the panel state {path} cannot be read: {exc}") from exc
    book, last_msg_ts = load_state(panel_root, pair, before, depth=depth)
    if book is None:
        raise PanelError(f"{pair}: the panel state {path} holds no book")
    return book, last_msg_ts


def write_day(
    out_root: Path, pair: str, day: date, frame: pl.DataFrame, entry: dict, *, params: dict, code_ref: str
) -> Path | None:
    """Write `pair`'s day: its entry into the run record first, then, unless `frame` is empty, the day file as
    `write_hour` publishes an hour -- the sidecar before the rename, so a kill leaves no day file and the re-run computes
    the day again. The sidecar holds the frame's `dataset_hash`, the grade a manifest vouches, never the bytes' sha256."""
    pair_root = _pair_root(out_root, pair)
    pair_root.mkdir(parents=True, exist_ok=True)
    days = (_read_record(pair_root) or {}).get("days", {})
    days[day.isoformat()] = entry
    record = pair_root / RUN_RECORD
    record_tmp = record.with_name(f"{RUN_RECORD}.{os.getpid()}.tmp")
    record_tmp.write_text(json.dumps({"params": params, "code_ref": code_ref, "days": days}, indent=1, sort_keys=True) + "\n")
    _replace_durably(record_tmp, record)
    if frame.height == 0:
        return None
    directory = pair_root / f"{day:%Y}" / f"{day:%m}"
    directory.mkdir(parents=True, exist_ok=True)
    final = directory / f"{day:%d}.parquet"
    tmp = directory / f"{final.name}.{os.getpid()}.tmp"
    frame.write_parquet(tmp, compression="zstd")
    sidecar_tmp = directory / f"{final.name}.sha256.{os.getpid()}.tmp"
    sidecar_tmp.write_text(f"{dataset_hash(pl.read_parquet(tmp))}  {final.name}\n")
    _replace_durably(sidecar_tmp, final.with_name(f"{final.name}.sha256"))
    _replace_durably(tmp, final)
    return final


def _new_entry() -> dict:
    return {"hours": 0, "posts": 0, "skipped_no_quote": 0, "skipped_stale": 0, **{name: [] for name in _LISTS}}


def _file(rows_by_day: dict[date, list[dict]], rows: list[dict]) -> None:
    for row in rows:
        rows_by_day.setdefault(row["ts"].date(), []).append(row)


def produce_pair(
    primary_root: Path,
    reconciled_root: Path | None,
    panel_root: Path,
    out_root: Path,
    pair: str,
    *,
    since: datetime,
    until: datetime,
    depth: int = 100,
) -> dict:
    """Run the fill model over `pair`'s hours of `[since, until)` -- resuming at the 00Z after its newest day file -- and
    write its days (spec 00151 D2).

    Every hour of the span is posted on, unanchored or absent, each filed in its own day's entry with the root each
    kind's listing gave it, so `write_fills_manifest` can hold a second listing against the record. Days land in order,
    which the resume's start at the 00Z after the newest day file relies on.

    Returns the run's counts; `seconds` is the wall time from the first hour's read to the last day written."""
    params = {
        "grid_s": GRID_S,
        "horizon_s": HORIZON_S,
        "cancel_after_s": CANCEL_AFTER_S,
        "stale_s": STALE_S,
        "size_rungs": list(SIZE_RUNGS),
        "mid_offsets_s": list(MID_OFFSETS_S),
        "depth": depth,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }
    code_ref = _code_ref()
    for root in (primary_root, reconciled_root, panel_root):
        if root is not None:
            _require_root(root)
    out_root.mkdir(parents=True, exist_ok=True)
    pair_root = _pair_root(out_root, pair)
    _check_run_record(pair_root, params, code_ref)
    written = _day_files(pair_root)
    start = _midnight(max(written) + _DAY) if written else since
    span = _hours(start, until)
    book_paths = _listing(primary_root, reconciled_root, pair, set(span), kind="book")
    trades_paths = _listing(primary_root, reconciled_root, pair, set(span), kind="trades")

    entries: dict[date, dict] = {}
    pending: list[date] = []
    rows_by_day: dict[date, list[dict]] = {}
    carried: list[Order] = []
    book: OrderBook | None = None
    last_msg_ts: datetime | None = None
    threaded = False  # whether `book` is the one the hour before left in memory
    days_written = 0
    clock: float | None = None

    def land(day: date) -> int:
        frame = rows_frame(rows_by_day.pop(day, []))
        return write_day(out_root, pair, day, frame, entries[day], params=params, code_ref=code_ref) is not None

    for hour in span:
        if hour.date() not in entries:
            entries[hour.date()] = _new_entry()
            pending.append(hour.date())
        entry = entries[hour.date()]
        iso = hour.isoformat()
        trades_path = trades_paths.get(hour)
        if trades_path is None:
            entry["trades_absent"].append(iso)
        elif _healed(trades_path, reconciled_root):
            entry["trades_reconciled"].append(iso)
        book_path = book_paths.get(hour)
        if book_path is None:
            entry["hours_absent"].append(iso)
            _file(rows_by_day, flush(carried))
            carried, book, last_msg_ts, threaded = [], None, None, False
        else:
            if _healed(book_path, reconciled_root):
                entry["book_reconciled"].append(iso)
            if clock is None:
                clock = time.monotonic()
            if not threaded:
                book, last_msg_ts = seed_book(panel_root, pair, hour, depth=depth)
            threaded = True
            messages = regroup_messages(pl.read_parquet(book_path))
            if messages and messages[0]["type"] == "snapshot":
                book = OrderBook(pair, depth)
            if book is None:
                entry["hours_unanchored"].append(iso)
                last_msg_ts = None
            else:
                trades = pl.read_parquet(trades_path).sort("ts", maintain_order=True).to_dicts() if trades_path is not None else []
                rows, carried, book, last_msg_ts, counts = simulate_hour(
                    messages, trades, book, hour, pair=pair, carried=carried, last_msg_ts=last_msg_ts
                )
                _file(rows_by_day, rows)
                entry["hours"] += 1
                for name, value in counts.items():
                    entry[name] += value
        while pending and hour >= _midnight(pending[0]) + _DAY and all(order.ts.date() != pending[0] for order in carried):
            days_written += land(pending.pop(0))
    _file(rows_by_day, flush(carried))
    for day in pending:
        days_written += land(day)
    seconds = time.monotonic() - clock if clock is not None else 0.0

    if not _day_files(pair_root):
        raise PanelError(
            f"{pair}: the run left no day file in {pair_root} -- the archive holds no hour of the pair in "
            f"[{since.isoformat()}, {until.isoformat()}), or none anchored"
        )
    totals = {
        name: sum(entry[name] for entry in entries.values()) for name in ("hours", "posts", "skipped_no_quote", "skipped_stale")
    }
    absent = {
        name: sum(len(entry[name]) for entry in entries.values()) for name in ("hours_unanchored", "hours_absent", "trades_absent")
    }
    return {
        "hours": totals["hours"],
        **absent,
        "posts": totals["posts"],
        "skipped_no_quote": totals["skipped_no_quote"],
        "skipped_stale": totals["skipped_stale"],
        "days_written": days_written,
        "seconds": seconds,
    }


def _recorded_root(entry: dict | None, iso: str, kind: str) -> str:
    if entry is None:
        return "no entry"
    absent, healed = ("hours_absent", "book_reconciled") if kind == "book" else ("trades_absent", "trades_reconciled")
    if iso in entry[absent]:
        return "absent"
    return "reconciled" if iso in entry[healed] else "primary"


def _relisting_disputes(records: dict[str, dict], primary_root: Path, reconciled_root: Path | None) -> list[str]:
    """Every hour of a recorded pair's `[since, until)` the archive lists now from another root than the run recorded
    for it; an hour this listing lacks is not compared."""
    spans = {
        pair: set(_hours(datetime.fromisoformat(r["params"]["since"]), datetime.fromisoformat(r["params"]["until"])))
        for pair, r in records.items()
    }
    disputes = []
    for kind in ("book", "trades"):
        for pair, hour, path in canonical_segments(primary_root, reconciled_root, kind=kind):
            if hour not in spans.get(pair, ()):
                continue
            listed = "reconciled" if _healed(path, reconciled_root) else "primary"
            recorded = _recorded_root(records[pair]["days"].get(hour.date().isoformat()), hour.isoformat(), kind)
            if listed != recorded:
                disputes.append((pair, kind, hour, f"{pair} {kind} {hour.isoformat()}: run {recorded}, second listing {listed}"))
    return [dispute for *_, dispute in sorted(disputes)]


def write_fills_manifest(out_root: Path, primary_root: Path, reconciled_root: Path | None, *, written_at: str) -> Path:
    """Write the dataset's conformant `manifest.json`, once every pair's run has exited (spec 00151 D2)."""
    for root in (primary_root, reconciled_root):
        if root is not None:
            _require_root(root)
    pair_roots = {f"{path.parent.name}/{path.name}": path for path in sorted(out_root.glob("*/*")) if path.is_dir()}
    records = {pair: record for pair, root in pair_roots.items() if (record := _read_record(root)) is not None}
    base_pair = min(records, default=None)
    for pair, record in sorted(records.items()):
        base = records[base_pair]
        if record["params"] != base["params"] or record["code_ref"] != base["code_ref"]:
            raise PanelError(
                f"{pair_roots[base_pair] / RUN_RECORD} and {pair_roots[pair] / RUN_RECORD} disagree: params "
                f"{base['params']} at code {base['code_ref']} against {record['params']} at code {record['code_ref']}"
            )
    files = {(pair, day): path for pair, root in pair_roots.items() for day, path in _day_files(root).items()}
    if not files:
        raise PanelError(f"{out_root} holds no day file: nothing for a manifest to attest")

    series = {}
    for (pair, day), path in sorted(files.items()):
        if pair not in records:
            raise PanelError(f"{pair} {day}: {path} has no run record beside it")
        entry = records[pair]["days"].get(day.isoformat())
        if entry is None:
            raise PanelError(f"{pair} {day}: {path} has no entry in its pair's run record")
        frame = pl.read_parquet(path)
        if frame.height != entry["posts"]:
            raise PanelError(f"{pair} {day}: {path} holds {frame.height} rows, its record's entry {entry['posts']} posts")
        relpath = path.relative_to(out_root).as_posix()
        leaf = series_entry(frame, relpath)
        sidecar = path.with_name(f"{path.name}.sha256")
        if sidecar.read_text().split()[:1] != [leaf["sha256"]]:
            raise PanelError(f"{pair} {day}: the sidecar {sidecar} does not hold the frame hash of {path}")
        series[relpath] = leaf

    for pair, record in sorted(records.items()):
        since, until = (datetime.fromisoformat(record["params"][bound]) for bound in ("since", "until"))
        for iso_day, entry in sorted(record["days"].items()):
            day = date.fromisoformat(iso_day)
            if entry["posts"] and (pair, day) not in files:
                raise PanelError(f"{pair} {iso_day}: its record's entry holds {entry['posts']} posts and no day file")
            if entry["posts"] + entry["skipped_no_quote"] + entry["skipped_stale"] != _POSTS_PER_HOUR * entry["hours"]:
                raise PanelError(
                    f"{pair} {iso_day}: the entry's posts and skips are not {_POSTS_PER_HOUR} for each of its {entry['hours']} hours"
                )
            span_hours = len(_hours(max(since, _midnight(day)), min(until, _midnight(day) + _DAY)))
            if entry["hours"] + len(entry["hours_unanchored"]) + len(entry["hours_absent"]) != span_hours:
                raise PanelError(
                    f"{pair} {iso_day}: the entry's hours posted, unanchored and absent are not the day's {span_hours} in the span"
                )

    if disputes := _relisting_disputes(records, primary_root, reconciled_root):
        raise PanelError(
            f"{out_root}: a second listing of the archive holds hours from another root than the runs recorded -- the run's "
            f"listing dropped the hour or its overlay directory, and the set would freeze the hole or the un-healed copy: "
            f"{'; '.join(disputes)}"
        )

    base = records[base_pair]
    provenance = {
        "producer": PRODUCER,
        "code_ref": base["code_ref"],
        "params": base["params"],
        "pairs": {pair: record["days"] for pair, record in sorted(records.items())},
    }
    manifest = build_manifest(series, written_at=written_at, identity="set", provenance=provenance)
    path = out_root / "manifest.json"
    tmp = path.with_name(f"manifest.json.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _replace_durably(tmp, path)
    return path
