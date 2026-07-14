"""Pure reconciliation logic for spec 00050: cross-stream book-gap detection.

No I/O and no Typer here — `mint.py` owns the write path and `command.py` the wiring, so the rules
below are testable on plain DataFrames.

Load-bearing constraints (spec 00050, constraints 1 + 2):
  * Kraken coalesces book updates PER CONNECTION, so two healthy hosts record different message
    sequences for the same pair. A gap is therefore only ever detected — never repaired — by
    comparing row-level content across hosts; repair is whole-window block substitution.
  * A secondary *snapshot* row is full state, not market activity. It must never, on its own,
    testify that the primary lost something: after any reconnect the secondary re-snapshots, and a
    quiet market would otherwise be "healed" for a window in which nothing happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl


@dataclass(frozen=True)
class Gap:
    """A window in which the primary stream was silent and the secondary was demonstrably alive."""

    start: datetime
    end: datetime
    seconds: float


def _message_ts(df: pl.DataFrame) -> list[datetime]:
    """One entry per wire message: many rows share a `ts` (one row per book level)."""
    if df.height == 0:
        return []
    return df.select(pl.col("ts").unique(maintain_order=True)).to_series().to_list()


def secondary_covers(secondary: pl.DataFrame, gap: Gap) -> bool:
    """True iff the secondary has at least one **update** row strictly inside `gap`.

    Strict inequalities: a row exactly at a boundary belongs to the wire message that defines the
    boundary, and splitting a message across blocks would tear one book update in half.
    """
    if secondary.height == 0:
        return False
    inside = secondary.filter((pl.col("ts") > gap.start) & (pl.col("ts") < gap.end) & (pl.col("type") == "update"))
    return inside.height > 0


def find_book_gaps(primary: pl.DataFrame, secondary: pl.DataFrame, *, min_gap_seconds: float) -> list[Gap]:
    """Windows where the primary was silent > `min_gap_seconds` AND the secondary was alive inside.

    A wholly-absent primary hour degenerates to one window spanning the secondary's own extent.
    """
    sec_ts = _message_ts(secondary)
    if not sec_ts:
        return []

    pri_ts = _message_ts(primary)
    if not pri_ts:
        gap = Gap(start=sec_ts[0], end=sec_ts[-1], seconds=(sec_ts[-1] - sec_ts[0]).total_seconds())
        # The primary is wholly absent, so `gap`'s own boundaries ARE the secondary's first/last
        # message -- unlike a real primary silence, there is no wire message to protect at the
        # edges. `secondary_covers`'s strict inequalities would then always exclude those two rows
        # (the only ones that can exist), so use an inclusive bound here instead; the `type ==
        # "update"` guard still means snapshot-only secondary activity never witnesses a gap.
        covered = (
            secondary.filter((pl.col("ts") >= gap.start) & (pl.col("ts") <= gap.end) & (pl.col("type") == "update")).height > 0
        )
        return [gap] if covered else []

    gaps: list[Gap] = []
    for a, b in zip(pri_ts, pri_ts[1:], strict=False):
        seconds = (b - a).total_seconds()
        if seconds <= min_gap_seconds:
            continue
        gap = Gap(start=a, end=b, seconds=seconds)
        if secondary_covers(secondary, gap):
            gaps.append(gap)
    return gaps


@dataclass(frozen=True)
class Block:
    """One contiguous run of rows from one source. Blocks concatenate in list order — never sorted."""

    source: str
    frame: pl.DataFrame
    from_ts: datetime | None
    to_ts: datetime | None


def _span(frame: pl.DataFrame) -> tuple[datetime | None, datetime | None]:
    if frame.height == 0:
        return None, None
    return frame["ts"].min(), frame["ts"].max()


def _block(source: str, frame: pl.DataFrame) -> Block:
    lo, hi = _span(frame)
    return Block(source=source, frame=frame, from_ts=lo, to_ts=hi)


def splice_book(primary: pl.DataFrame, secondary: pl.DataFrame, gaps: list[Gap]) -> list[Block]:
    """Mint the hour as ordered blocks: primary up to each gap, secondary inside it, primary after.

    Boundaries are **strict** on the secondary side (`start < ts < end`) and **inclusive** on the
    primary side (`ts <= start`, `ts >= end`), so the rows of one wire message — which all share a
    `ts` — always stay together in the same block. Rows are concatenated in source order and NEVER
    sorted: L2 updates carry absolute quantities, so reordering within a `ts` changes the book.
    """
    if not gaps:
        return [_block("primary", primary)] if primary.height else []

    if primary.height == 0:
        # The primary is wholly absent for the hour, so `gaps` is the single degenerate gap that
        # `find_book_gaps` builds from the secondary's OWN first/last message (see its `covered`
        # comment) -- there is no primary wire message at either edge to protect from splitting, so
        # the strict secondary-side boundary below would wrongly exclude those two rows, which are
        # the only ones that exist. Take the secondary verbatim, in its own order.
        return [_block("secondary", secondary)] if secondary.height else []

    blocks: list[Block] = []
    cursor: datetime | None = None
    for gap in gaps:
        head = primary.filter(pl.col("ts") <= gap.start)
        if cursor is not None:
            head = head.filter(pl.col("ts") >= cursor)
        if head.height:
            blocks.append(_block("primary", head))
        middle = secondary.filter((pl.col("ts") > gap.start) & (pl.col("ts") < gap.end))
        if middle.height:
            blocks.append(_block("secondary", middle))
        cursor = gap.end

    tail = primary.filter(pl.col("ts") >= cursor) if cursor is not None else primary
    if tail.height:
        blocks.append(_block("primary", tail))
    return blocks
