"""The engine's maker-first ladder replayed at a cycle boundary over the captured book (spec 00153 D2): four orders
posted at the touch `POST_OFFSET_S` into the boundary hour, resting under the fill model's rule with no away-cancel
for `BOX_S`, each recorded with the opposite touch at the box end -- the fallback's price."""

from __future__ import annotations

import itertools
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.replay import regroup_messages
from cli.capture.book import OrderBook
from cli.capture.segment_writer import _replace_durably
from cli.data.manifest import build_manifest, series_entry
from cli.panel import fills
from cli.panel.errors import PanelError
from cli.panel.materialize import _code_ref

BOUNDARY_HOURS = (0, 4, 8, 12, 16, 20)
POST_OFFSET_S = 120
BOX_S = 900
RUN_RECORD = "ladder-run.json"
PRODUCER = "zcrypto panel ladder"
LADDER_PARAMS = {
    "post_offset_s": POST_OFFSET_S,
    "box_s": BOX_S,
    "boundary_hours": list(BOUNDARY_HOURS),
    "size_rungs": list(fills.SIZE_RUNGS),
    "stale_s": fills.STALE_S,
}

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


def _boundaries(start: datetime, until: datetime) -> list[datetime]:
    return [hour for hour in fills._hours(start, until) if hour.hour in BOUNDARY_HOURS]


def write_day(
    out_root: Path, pair: str, day: date, frame: pl.DataFrame, entry: dict, *, params: dict, code_ref: str
) -> Path | None:
    return fills.write_day(out_root, pair, day, frame, entry, params=params, code_ref=code_ref, record=RUN_RECORD)


def produce_ladder_pair(
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
    """Run an episode at each of `pair`'s cycle boundaries in `[since, until)` -- resuming at the 00Z after its newest
    day file -- and write its days (spec 00153 D2).

    Every boundary hour is replayed, unanchored or absent, each filed in its own day's entry with the root each kind's
    listing gave it, so `write_ladder_manifest` can hold a second listing against the record. Each episode is seeded on
    its own, from the panel's state of the hour before it; no book carries from one episode to the next.

    Returns the run's counts; `seconds` is the wall time from the first hour's read to the last day written."""
    params = {**LADDER_PARAMS, "depth": depth, "since": since.isoformat(), "until": until.isoformat()}
    code_ref = _code_ref()
    for root in (primary_root, reconciled_root, panel_root):
        if root is not None:
            fills._require_root(root)
    try:
        out_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PanelError(f"{pair}: the out root {out_root} cannot be created: {exc}") from exc
    manifest = out_root / "manifest.json"
    if manifest.exists():
        raise PanelError(f"{pair}: {manifest} is present: the set is finished, and a change is a new out root")
    pair_root = fills._pair_root(out_root, pair)
    fills._check_run_record(pair_root, params, code_ref, record=RUN_RECORD)
    fills._mark(out_root, pair)
    written = fills._day_files(pair_root)
    start = fills._midnight(max(written) + fills._DAY) if written else since
    boundaries = _boundaries(start, until)
    book_paths = fills._listing(primary_root, reconciled_root, pair, set(boundaries), kind="book")
    trades_paths = fills._listing(primary_root, reconciled_root, pair, set(boundaries), kind="trades")

    entries: list[dict] = []
    days_written = 0
    clock: float | None = None
    for day, day_boundaries in itertools.groupby(boundaries, key=lambda boundary: boundary.date()):
        entry = fills._new_entry()
        entries.append(entry)
        rows: list[dict] = []
        for boundary in day_boundaries:
            iso = boundary.isoformat()
            trades_path = trades_paths.get(boundary)
            if trades_path is None:
                entry["trades_absent"].append(iso)
            elif fills._healed(trades_path, reconciled_root):
                entry["trades_reconciled"].append(iso)
            book_path = book_paths.get(boundary)
            if book_path is None:
                entry["hours_absent"].append(iso)
                continue
            if fills._healed(book_path, reconciled_root):
                entry["book_reconciled"].append(iso)
            if clock is None:
                clock = time.monotonic()
            book, last_msg_ts = fills.seed_book(panel_root, pair, boundary, depth=depth)
            messages = regroup_messages(fills._read_hour(book_path, f"{pair} {iso}"))
            if messages and messages[0]["type"] == "snapshot":
                book = OrderBook(pair, depth)
            if book is None:
                entry["hours_unanchored"].append(iso)
                continue
            trades = (
                fills._read_hour(trades_path, f"{pair} {iso}").sort("ts", maintain_order=True).to_dicts()
                if trades_path is not None
                else []
            )
            episode, counts = simulate_episode(messages, trades, book, boundary, pair=pair, last_msg_ts=last_msg_ts)
            rows += episode
            entry["hours"] += 1
            for name, value in counts.items():
                entry[name] += value
        days_written += write_day(out_root, pair, day, rows_frame(rows), entry, params=params, code_ref=code_ref) is not None
        fills._mark(out_root, pair)
    seconds = time.monotonic() - clock if clock is not None else 0.0

    totals = {name: sum(entry[name] for entry in entries) for name in fills._COUNTS}
    absent = {name: sum(len(entry[name]) for entry in entries) for name in ("hours_unanchored", "hours_absent", "trades_absent")}
    return {**totals, **absent, "days_written": days_written, "seconds": seconds}


def write_ladder_manifest(out_root: Path, primary_root: Path, reconciled_root: Path | None, *, written_at: str) -> Path:
    """Write the dataset's conformant `manifest.json`, once every pair's run has exited (spec 00153 D2): the fill set's
    checks over the ladder's records, four orders an episode and the boundary hours."""
    for root in (primary_root, reconciled_root):
        if root is not None:
            fills._require_root(root)
    pair_roots = {f"{path.parent.name}/{path.name}": path for path in sorted(out_root.glob("*/*")) if path.is_dir()}
    records = {
        pair: record for pair, root in pair_roots.items() if (record := fills._read_record(root, record=RUN_RECORD)) is not None
    }
    base_pair = min(records, default=None)
    for pair, record in sorted(records.items()):
        base = records[base_pair]
        if record["params"] != base["params"] or record["code_ref"] != base["code_ref"]:
            raise PanelError(
                f"{pair_roots[base_pair] / RUN_RECORD} and {pair_roots[pair] / RUN_RECORD} disagree: params "
                f"{base['params']} at code {base['code_ref']} against {record['params']} at code {record['code_ref']}"
            )
    files = {(pair, day): path for pair, root in pair_roots.items() for day, path in fills._day_files(root).items()}
    if not files:
        raise PanelError(f"{out_root} holds no day file: nothing for a manifest to attest")

    series = {}
    for (pair, day), path in sorted(files.items()):
        if pair not in records:
            raise PanelError(f"{pair} {day}: {path} has no run record beside it")
        entry = records[pair]["days"].get(day.isoformat())
        if entry is None:
            raise PanelError(f"{pair} {day}: {path} has no entry in its pair's run record")
        frame = fills._read_hour(path, f"{pair} {day}")
        if frame.height != entry["posts"]:
            raise PanelError(f"{pair} {day}: {path} holds {frame.height} rows, its record's entry {entry['posts']} posts")
        relpath = path.relative_to(out_root).as_posix()
        leaf = series_entry(frame, relpath)
        sidecar = path.with_name(f"{path.name}.sha256")
        try:
            held = sidecar.read_text().split()[:1]
        except (OSError, ValueError) as exc:
            raise PanelError(f"{pair} {day}: the sidecar {sidecar} cannot be read: {exc}") from exc
        if held != [leaf["sha256"]]:
            raise PanelError(f"{pair} {day}: the sidecar {sidecar} does not hold the frame hash of {path}")
        series[relpath] = leaf

    for pair, record in sorted(records.items()):
        since, until = (datetime.fromisoformat(record["params"][bound]) for bound in ("since", "until"))
        for iso_day, entry in sorted(record["days"].items()):
            day = date.fromisoformat(iso_day)
            if entry["posts"] and (pair, day) not in files:
                raise PanelError(f"{pair} {iso_day}: its record's entry holds {entry['posts']} posts and no day file")
            if entry["posts"] + entry["skipped_no_quote"] + entry["skipped_stale"] != fills._ORDERS_PER_POST * entry["hours"]:
                raise PanelError(
                    f"{pair} {iso_day}: the entry's posts and skips are not {fills._ORDERS_PER_POST} for each of its "
                    f"{entry['hours']} episodes"
                )
            midnight = fills._midnight(day)
            span_boundaries = len(_boundaries(max(since, midnight), min(until, midnight + fills._DAY)))
            if entry["hours"] + len(entry["hours_unanchored"]) + len(entry["hours_absent"]) != span_boundaries:
                raise PanelError(
                    f"{pair} {iso_day}: the entry's episodes replayed, unanchored and absent are not the day's "
                    f"{span_boundaries} boundary hours in the span"
                )

    disputes = fills._relisting_disputes(records, primary_root, reconciled_root, hours_of_day=BOUNDARY_HOURS)
    if disputes:
        raise PanelError(
            f"{out_root}: a second listing of the archive holds boundary hours from another root than the runs recorded -- "
            f"the run's listing dropped the hour or its overlay directory, and the set would freeze the hole or the "
            f"un-healed copy; 'no entry': the run stopped before the hour's day landed, and a re-run completes it: "
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
    try:
        tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        _replace_durably(tmp, path)
    except OSError as exc:
        raise PanelError(f"{path} cannot be written: {exc}") from exc
    marker = out_root / fills.PRODUCING_MARKER
    try:
        marker.unlink(missing_ok=True)
    except OSError as exc:
        raise PanelError(f"{marker} cannot be removed: {exc}") from exc
    return path
