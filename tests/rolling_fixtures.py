"""`write_chain`: a rolling set written by hand -- its base files, its day files and its chained index lines -- so a reader's
test reads a tree the code under test did not write."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import FRAME_SCHEMA

BASE_DAY = date(2026, 9, 30)
SEAM = date(2026, 10, 1)
BARS_PER_DAY = 96
TAPE_ORDER = ("ts", "open", "high", "low", "close", "volume", "count", "vwap")
HOLE = "no tape-bars final past the re-scan window"
CLOSED = "closed on the owner's word"
_FIELDS = frozenset({"close", "vwap", "volume"})


def line_bytes(line: dict) -> bytes:
    return (json.dumps(line, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def day_bars(pair_index: int, day: date, fields: dict[str, float]) -> pl.DataFrame:
    assert fields.keys() <= _FIELDS, f"a bar override names only {sorted(_FIELDS)}, not {sorted(fields)}"
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    level = 100.0 * (pair_index + 1) + 10.0 * (day - BASE_DAY).days
    slots = range(BARS_PER_DAY)
    columns = {
        "ts": [start + timedelta(minutes=15 * i) for i in slots],
        "open": [level + i for i in slots],
        "high": [level + i + 2 for i in slots],
        "low": [level + i - 1 for i in slots],
        "close": [level + i + 1 for i in slots],
        "vwap": [level + i + 0.5 for i in slots],
        "volume": [0.5] * BARS_PER_DAY,
        "count": [3] * BARS_PER_DAY,
    }
    for name, value in fields.items():
        columns[name] = [value] * BARS_PER_DAY
    return pl.DataFrame(columns, schema=FRAME_SCHEMA).select(FRAME_SCHEMA.names())


def _put(root: Path, relpath: str, data: bytes) -> str:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _parquet(frame: pl.DataFrame) -> bytes:
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    return buffer.getvalue()


def write_chain(
    root: Path,
    *,
    pairs: tuple[str, ...] = ("BTC/EUR", "ETH/BTC"),
    days: int = 3,
    holes: dict[date, set[str]] | None = None,
    closed: dict[date, set[str]] | None = None,
    skip: date | None = None,
    bar: Callable[[str, date], dict[str, float]] | None = None,
) -> list[str]:
    """The base on BASE_DAY, in `FRAME_SCHEMA`'s order, and `days` days from SEAM, each pair's day file in the tape's order,
    every line in the index's canonical form and chained by `prev` to the line written before it; returns the lines'
    relpaths, the base line's first.

    `holes` and `closed` put the pairs they name for a day under that day's `holes`, writing no file for them; `closed`
    also gives the line the `closed <PAIR>` note a close in force carries. `skip` leaves a day's line and files out, the
    next line chained to the one before the gap. `bar(pair, day)`, the base day among the days, names the fields
    `day_bars` sets on every bar of that day."""
    holes, closed = holes or {}, closed or {}
    fields = bar or (lambda pair, day: {})
    relpaths: list[str] = []

    def put_line(line: dict) -> str:
        day = date.fromisoformat(line["day"])
        relpath = f"index/{day:%Y}/{day:%m}/{day:%d}.json"
        relpaths.append(relpath)
        return _put(root, relpath, line_bytes(line))

    base_files = {}
    for index, pair in enumerate(pairs):
        asset, quote = pair.split("/")
        base_files[f"base/{asset}/{quote}/15.parquet"] = _put(
            root, f"base/{asset}/{quote}/15.parquet", _parquet(day_bars(index, BASE_DAY, fields(pair, BASE_DAY)))
        )
    notes = {
        "seam": "2026-10-01T00:00:00+00:00",
        "base_from": "ohlc-15m-fixture",
        "base_identity_digest": hashlib.sha256(b"ohlc-15m-fixture").hexdigest(),
        "vwap": "the dump's close-weighted proxy before the seam, the tape's tick-weighted mean from it",
    }
    prev = put_line({"day": BASE_DAY.isoformat(), "prev": None, "files": base_files, "holes": {}, "notes": notes})

    closed_since: dict[str, date] = {}
    for offset in range(days):
        day = SEAM + timedelta(days=offset)
        if day == skip:
            continue
        files, line_holes, line_notes = {}, {}, {}
        for index, pair in enumerate(pairs):
            if pair in closed.get(day, set()):
                since = closed_since.setdefault(pair, day)
                line_holes[pair] = CLOSED
                line_notes[f"closed {pair}"] = f"from {since}, the owner's word of {since}: the fixture's close"
                continue
            closed_since.pop(pair, None)
            if pair in holes.get(day, set()):
                line_holes[pair] = HOLE
                continue
            asset, quote = pair.split("/")
            relpath = f"days/{asset}/{quote}/{day:%Y}/{day:%m}/{day:%d}.parquet"
            frame = day_bars(index, day, fields(pair, day)).select(TAPE_ORDER)
            files[relpath] = _put(root, relpath, _parquet(frame))
        line = {"day": day.isoformat(), "prev": prev, "files": files, "holes": line_holes}
        if line_notes:
            line["notes"] = line_notes
        prev = put_line(line)
    return relpaths
