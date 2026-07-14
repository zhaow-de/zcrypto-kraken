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
    """A window in which the primary stream was silent and the secondary was demonstrably alive.

    `start` and `end` bound the window; the two flags say **who owns each boundary**, which is what
    every consumer needs in order to filter rows without either splitting a wire message or dropping
    one. The rules follow mechanically and are the whole point of the flags:

      * flag **True** — the boundary IS a primary wire message. The primary block owns every row at
        that `ts` (all rows of one Kraken message share it), so the secondary side must be **strict**
        there (`>` / `<`): admitting it would tear one book update in half.
      * flag **False** — the boundary is the hour boundary (head/tail gap) or the window's own edge
        (wholly-absent primary). **Nobody** owns it, so the secondary side must be **inclusive**
        there (`>=` / `<=`): excluding it silently drops real rows — every level-row of the message
        that sits exactly on that edge.

    Symmetrically, the primary head block for a gap takes `ts <= start` only when `start` IS a
    primary message, and the primary tail resumes at `ts >= end`.
    """

    start: datetime
    end: datetime
    seconds: float
    start_is_primary_message: bool
    end_is_primary_message: bool


def _inside(gap: Gap) -> pl.Expr:
    """The gap's row filter, honouring boundary ownership. The ONE place the rule is written."""
    lo = pl.col("ts") > gap.start if gap.start_is_primary_message else pl.col("ts") >= gap.start
    hi = pl.col("ts") < gap.end if gap.end_is_primary_message else pl.col("ts") <= gap.end
    return lo & hi


def _message_ts(df: pl.DataFrame) -> list[datetime]:
    """One entry per wire message, in ARRIVAL order: many rows share a `ts` (one row per book level).

    ASSUMES `ts` is non-decreasing. That holds empirically for every Kraken stream measured (3.15 M
    rows, T0037) but is NOT enforced here, because the only repair would be to sort — and sorting is
    forbidden: L2 rows carry absolute quantities, so reordering them reconstructs a different book.
    On out-of-order input the caller therefore sees a fabricated window that swallows the interleaved
    messages, which `test_message_ts_preserves_arrival_order_and_never_sorts` pins. The input must be
    trusted. `maintain_order=True` is load-bearing: plain `.unique()` does not preserve order.
    """
    if df.height == 0:
        return []
    return df.select(pl.col("ts").unique(maintain_order=True)).to_series().to_list()


def secondary_covers(secondary: pl.DataFrame, gap: Gap) -> bool:
    """True iff the secondary has at least one **update** row inside `gap`.

    "Inside" honours the gap's boundary ownership (see `Gap`): strict on a boundary that is a primary
    message, inclusive on one that is not.
    """
    if secondary.height == 0:
        return False
    return secondary.filter(_inside(gap) & (pl.col("type") == "update")).height > 0


def find_book_gaps(
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    *,
    min_gap_seconds: float,
    hour_start: datetime | None = None,
    hour_end: datetime | None = None,
) -> list[Gap]:
    """Windows where the primary was silent > `min_gap_seconds` AND the secondary was alive inside.

    Windows are formed by pairing CONSECUTIVE boundaries in arrival order. Pass `hour_start` and
    `hour_end` (the hour's start and its **exclusive** end — the next hour boundary) and the scan also
    covers the two windows that pairing primary messages alone cannot see:

      * `hour_start` → first primary message — the primary started recording late in the hour;
      * last primary message → `hour_end` — **the primary crashed mid-hour**. That is the natural
        shape of an outage and precisely what this detector exists to catch: there is no "next
        primary message" to pair with, so without the bounds the silence is invisible.

    Both obey the same threshold and the same secondary-witness rule as an interior gap; their outer
    boundary is the hour boundary, which is nobody's wire message (see `Gap`). Omitting the bounds
    scans interior windows only — a caller reconciling a real hour must always pass them.
    """
    sec_ts = _message_ts(secondary)
    if not sec_ts:
        return []

    pri_ts = _message_ts(primary)
    if not pri_ts:
        # No primary message exists to pair against, so the whole scanned window is one gap whose
        # boundaries belong to neither side. A file with zero messages is total loss, not quiescence,
        # so `min_gap_seconds` does not apply. Absent the hour bounds, the secondary's own extent is
        # the only window we can name.
        start = hour_start if hour_start is not None else sec_ts[0]
        end = hour_end if hour_end is not None else sec_ts[-1]
        gap = Gap(
            start=start,
            end=end,
            seconds=(end - start).total_seconds(),
            start_is_primary_message=False,
            end_is_primary_message=False,
        )
        return [gap] if secondary_covers(secondary, gap) else []

    edges: list[tuple[datetime, bool]] = [(hour_start, False)] if hour_start is not None else []
    edges += [(ts, True) for ts in pri_ts]
    if hour_end is not None:
        edges.append((hour_end, False))

    gaps: list[Gap] = []
    for (a, a_is_pri), (b, b_is_pri) in zip(edges, edges[1:], strict=False):
        seconds = (b - a).total_seconds()
        if seconds <= min_gap_seconds:  # silence must be STRICTLY greater than the threshold
            continue
        gap = Gap(
            start=a,
            end=b,
            seconds=seconds,
            start_is_primary_message=a_is_pri,
            end_is_primary_message=b_is_pri,
        )
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

    Every boundary is filtered by who owns it (see `Gap`). The secondary side is **strict** on a
    primary-message boundary — the primary block keeps every row of that message, so one wire message
    is never split across two blocks — and **inclusive** on a boundary that is nobody's message (an
    hour boundary, or the window edge of a wholly-absent primary), where a strict bound would
    silently drop real secondary rows. A wholly-absent primary needs no special case: its single gap
    owns neither boundary, so the head/tail primary filters select nothing and the secondary block is
    the whole hour. Rows are concatenated in source order and NEVER sorted: L2 updates carry absolute
    quantities, so reordering within a `ts` changes the book.
    """
    if not gaps:
        return [_block("primary", primary)] if primary.height else []

    blocks: list[Block] = []
    cursor: datetime | None = None
    for gap in gaps:
        # The primary owns `gap.start` only when that boundary is its own message.
        before = pl.col("ts") <= gap.start if gap.start_is_primary_message else pl.col("ts") < gap.start
        head = primary.filter(before)
        if cursor is not None:
            head = head.filter(pl.col("ts") >= cursor)
        if head.height:
            blocks.append(_block("primary", head))
        middle = secondary.filter(_inside(gap))
        if middle.height:
            blocks.append(_block("secondary", middle))
        cursor = gap.end

    tail = primary.filter(pl.col("ts") >= gaps[-1].end)
    if tail.height:
        blocks.append(_block("primary", tail))
    return blocks
