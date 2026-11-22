"""The writer of the vintage chain (spec D6, D8): under the chain's lock, the newest lines verified and their recorded
block hashes re-read, then the base when the chain is empty and the index is at the node's tip, else each UTC day
after the head that a block of a later monotonic day has closed and whose last block is `DEPTH` deep, in order."""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl

from cli.capture.command import single_instance_lock
from cli.logging import get_logger
from cli.onchain.brk import BrkClient, BrkError
from cli.onchain.chain import (
    ChainError,
    Line,
    chain_name,
    head,
    line_days,
    read_line,
    staging_leftovers,
    verify,
    walk,
    write_base,
    write_day,
)
from cli.onchain.series import BRK_SERIES, SCHEMA, mvrv_z, sth_supply_share

DEPTH = 12
REORG_REREAD_DAYS = 30
STALE_HOURS = 48
_COMMIT = re.compile(r"[0-9a-f]{40}")

log = get_logger("onchain.write")


@dataclass(frozen=True)
class WriteOutcome:
    wrote: tuple[date, ...]
    base: bool
    stopped: str | None


def closed_days(height_days: list[date], first_height: int, tip: int) -> list[tuple[date, int]]:
    """Each day of `height_days`, the monotonic days of the heights from `first_height` on, that a block of a later day
    follows, with its last height, where that height is at least `DEPTH` below `tip`, the node's."""
    return [
        (day, first_height + offset)
        for offset, (day, after) in enumerate(itertools.pairwise(height_days))
        if after > day and first_height + offset + DEPTH <= tip
    ]


def _lacked(client: BrkClient) -> str | None:
    missing = sorted(set(BRK_SERIES.values()) - client.series_ids())
    return f"the index serves no series {', '.join(missing)}, which the writer pins; nothing written" if missing else None


def _brk_rows(client: BrkClient, closed: list[tuple[date, int]]) -> tuple[dict[str, list], str | None]:
    """The days' rows as BRK serves them, and, where a series' answer lacks one of the days, the stop naming that series
    and the first such day; `None` otherwise."""
    rows: dict[str, list] = {
        "ts": [datetime.combine(day, time(), UTC) for day, _ in closed],
        "last_height": [height for _, height in closed],
        "last_hash": [client.block_hash(height) for _, height in closed],
    }
    for column, series_id in BRK_SERIES.items():
        values = client.read_days(series_id, closed[0][0], closed[-1][0])
        unserved = [day for day, _ in closed if day not in values]
        if unserved:
            return rows, f"the index serves no value of {series_id} for {unserved[0]}; nothing written"
        rows[column] = [values[day] for day, _ in closed]
    return rows, None


def _frame(rows: dict[str, list], past_caps: list[float | None], past_realized: list[float | None]) -> pl.DataFrame:
    """`rows` with the two series computed outside BRK; a day's MVRV-Z reads the past days' market caps and the rows'
    through that day."""
    z = mvrv_z(past_caps + rows["market_cap"], past_realized + rows["realized_cap"])[len(past_caps) :]
    data = rows | {"mvrv_z": z, "sth_supply_share": sth_supply_share(rows["sth_supply"], rows["supply"])}
    return pl.DataFrame({column: data[column] for column in SCHEMA}, schema=SCHEMA)


def _history(root: Path, through: date) -> pl.DataFrame:
    """The market and realized caps of every day through `through`: the base file's rows, then each day file's row."""
    files = [root / relpath for line in walk(root, through) for relpath in line.files]
    return pl.concat([pl.read_parquet(path, columns=["market_cap", "realized_cap"]) for path in files])


def _stale(head_day: date, now: datetime, indexed: int | None) -> str | None:
    due = head_day + timedelta(days=1)
    if now <= datetime.combine(due + timedelta(days=1), time(), UTC) + timedelta(hours=STALE_HOURS):
        return None
    height = "unread" if indexed is None else indexed
    return f"stale index: {due} is unwritten {STALE_HOURS} hours past its end, the index at height {height}"


def _write_base(root: Path, client: BrkClient, stamp: dict) -> WriteOutcome:
    try:
        lacked = _lacked(client)
        if lacked is not None:
            return WriteOutcome((), False, lacked)
        indexed = client.indexed_height()
        tip = client.node_tip()
        if indexed < tip:
            log.info(
                "the index is at height %d and the node's tip at %d: the base waits for the index to reach the tip; nothing written",
                indexed,
                tip,
            )
            return WriteOutcome((), False, None)
        closed = closed_days(client.height_days(0, indexed), 0, tip)
        if not closed:
            return WriteOutcome((), False, None)
        rows, unserved = _brk_rows(client, closed)
        if unserved is not None:
            return WriteOutcome((), False, unserved)
    except BrkError as exc:
        log.info("the index is unreachable or unreadable before the base: %s; nothing written", exc)
        return WriteOutcome((), False, None)
    day, height = closed[-1]
    write_base(root, _frame(rows, [], []), stamp | {"last_height": height, "last_hash": rows["last_hash"][-1], "tip_height": tip})
    return WriteOutcome((day,), True, None)


def _write_days(root: Path, client: BrkClient, start: Line, stamp: dict, now: datetime) -> WriteOutcome:
    verify(root, start.day, newest=REORG_REREAD_DAYS)
    recent = [read_line(root, day) for day in line_days(root)[-REORG_REREAD_DAYS:]]
    indexed = None
    try:
        for line in recent:
            height, recorded = line.vintage["last_height"], line.vintage["last_hash"]
            found = client.block_hash(height)
            if found != recorded:
                stop = f"the block at height {height}, {line.day}'s last, hashes to {found}, not the {recorded} its line records"
                return WriteOutcome((), False, f"{stop}: a reorg past the depth; nothing written")
        lacked = _lacked(client)
        if lacked is not None:
            return WriteOutcome((), False, lacked)
        indexed = client.indexed_height()
        tip = client.node_tip()
        first = start.vintage["last_height"] + 1
        closed = closed_days(client.height_days(first, indexed), first, tip)
        rows, unserved = _brk_rows(client, closed) if closed else ({}, None)
        if unserved is not None:
            return WriteOutcome((), False, unserved)
    except BrkError as exc:
        stale = _stale(start.day, now, indexed)
        if stale is None:
            log.warning("the index could not be read: %s; nothing written", exc)
            return WriteOutcome((), False, None)
        return WriteOutcome((), False, f"{stale}; {exc}")
    written: list[date] = []
    if closed:
        past = _history(root, start.day)
        frame = _frame(rows, past["market_cap"].to_list(), past["realized_cap"].to_list())
        for index, (_, height) in enumerate(closed):
            vintage = stamp | {"last_height": height, "last_hash": rows["last_hash"][index], "tip_height": tip}
            try:
                written.append(write_day(root, frame.slice(index, 1), vintage).day)
            except ChainError as exc:
                return WriteOutcome(tuple(written), False, str(exc))
    stale = _stale(written[-1] if written else start.day, now, indexed)
    return WriteOutcome(tuple(written), False, stale)


def run_write(
    chain_root: Path, client: BrkClient, *, brk_commit: str, bitview_image: str, bitcoind_image: str, now: datetime
) -> WriteOutcome:
    """One run over `chain_root`'s chain for `brk_commit`, under its lock, which raises `CaptureError` while another
    writer holds it. A commit not of 40 lowercase hex characters, or a `chain_root` that is not a directory, stops the
    run before anything is opened. `now` is the run's start; after the base, a run stops once it is more than
    `STALE_HOURS` past the end of the day after the head its writes leave."""
    if not _COMMIT.fullmatch(brk_commit):
        return WriteOutcome((), False, f"the BRK commit {brk_commit!r} is not 40 lowercase hex characters; no chain is opened")
    if not chain_root.is_dir():
        return WriteOutcome((), False, f"{chain_root} is not a directory; the writer never makes the chain root")
    root = chain_root / chain_name(brk_commit)
    root.mkdir(exist_ok=True)
    with single_instance_lock(root):
        for path in staging_leftovers(root):
            log.warning("%s: a temporary file left by a writer that died, which no line names; read it and delete it by hand", path)
        stamp = {
            "written_at": now.astimezone(UTC).isoformat(),
            "depth": DEPTH,
            "brk_commit": brk_commit,
            "bitview_image": bitview_image,
            "bitcoind_image": bitcoind_image,
            "chain": root.name,
        }
        try:
            start = head(root)
            if start is None:
                return _write_base(root, client, stamp)
            return _write_days(root, client, start, stamp, now)
        except ChainError as exc:
            return WriteOutcome((), False, str(exc))
