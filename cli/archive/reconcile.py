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

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import polars as pl

from cli.archive.settle import dt_from_us, us_from_dt
from cli.capture.errors import CaptureError


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


def _pair_label(df: pl.DataFrame) -> str:
    """The stream's symbol, for an error message — an ad-hoc frame need not carry the column."""
    return df["symbol"][0] if "symbol" in df.columns else "?"


def _message_ts(df: pl.DataFrame) -> np.ndarray:
    """One entry per wire message, in ARRIVAL order: many rows share a `ts` (one row per book level).

    Returns int64 microseconds since epoch (spec 00097 D3); `dt_from_us` is the exact inverse.

    REQUIRES `ts` to be non-decreasing, and says so loudly: out-of-order input would otherwise
    fabricate one wide window that swallows the interleaved messages, and the splice would drop their
    rows — silent, permanent corruption of an unbackfillable archive. Sorting is NOT the repair and is
    forbidden: L2 rows carry absolute quantities, so reordering them reconstructs a different book.
    Kraken's `ts` is non-decreasing across every production row measured (3.15 M rows, T0037), so this
    assertion should never fire — which is exactly what makes it worth having.

    The check runs on the RAW row order, before dedup: an exact-duplicate stamp reappearing after a
    strictly newer one (raw `[0, 5, 0]`) is out of order, but dropping equal neighbours would collapse
    it to `[0, 5]` first — which looks monotone. Checking the deduped list can't see that.

    Dropping equal NEIGHBOURS is the dedup, and it is exactly `unique(maintain_order=True)` only
    because the sequence has just been proven non-decreasing.
    """
    if df.height == 0:
        return np.empty(0, dtype=np.int64)
    stamps = df["ts"]
    if stamps.null_count():
        # A null becomes iNaT in the int64 view — the most negative int64 — which would fabricate a
        # window spanning the whole epoch and clamp a real message out of the timeline, silently.
        raise CaptureError(f"null ts in the {_pair_label(df)} book stream — refusing to reconcile a frame with missing timestamps")
    if getattr(stamps.dtype, "time_unit", None) != "us":
        # The int64 view reads the column's OWN unit as microseconds while the hour bounds always
        # arrive as microseconds, so any other unit mixes two scales in one `edges` array — and the
        # two directions fail differently, both unacceptably. Measured on a 0 s/3300 s frame:
        # `ns` overflows (first window ~1.78e18 µs) and `dt_from_us` raises an untyped
        # `OverflowError` that escapes the caller's `except CaptureError` and kills the whole cycle;
        # `ms` does NOT raise — the real 3300 s outage reads as 3.3 s, falls under the threshold and
        # is never booked, while a fabricated 1782411804.3 s gap anchored in 1970 reaches the splice
        # and the ledger. Silent corruption is the worse of the two, so refuse both, typed.
        raise CaptureError(f"ts in the {_pair_label(df)} book stream is {stamps.dtype}, not Datetime in microseconds")
    raw = stamps.to_numpy().view(np.int64)  # Datetime(us, UTC) → datetime64[us] → μs ints, zero-copy
    drops = np.nonzero(np.diff(raw) < 0)[0]
    if drops.size:
        i = int(drops[0])
        raise CaptureError(
            f"non-monotonic ts in the {_pair_label(df)} book stream: {dt_from_us(raw[i]).isoformat()} is followed by "
            f"{dt_from_us(raw[i + 1]).isoformat()}. Refusing to reconcile — sorting is forbidden (L2 rows carry "
            f"absolute quantities), so the input itself must be fixed."
        )
    keep = np.empty(raw.shape, dtype=bool)
    keep[0] = True
    np.not_equal(raw[1:], raw[:-1], out=keep[1:])
    return raw[keep]


def secondary_covers(secondary: pl.DataFrame, gap: Gap) -> bool:
    """True iff the secondary has at least one **update** row inside `gap`.

    "Inside" honours the gap's boundary ownership (see `Gap`): strict on a boundary that is a primary
    message, inclusive on one that is not.
    """
    if secondary.height == 0:
        return False
    return secondary.filter(_inside(gap) & (pl.col("type") == "update")).height > 0


def _validate_hour_bounds(hour_start: datetime, hour_end: datetime) -> None:
    """`hour_start`/`hour_end` must bound exactly one whole, tz-aware hour.

    Both windows this function protects (see `find_book_gaps`'s docstring) exist ONLY by virtue of
    these bounds, so a wrong one is not cosmetic: a too-EARLY `hour_end` truncates a genuine tail
    gap — the remaining silence is real, secondary-witnessed loss that lands in no `Gap`, is never
    ledgered, never spliced. A silent, permanent hole — the exact failure this system exists to
    prevent. A too-LATE `hour_end` (or a misaligned `hour_start`) risks admitting rows from the wrong
    hour into this hour's splice. Both are refused loudly here rather than left for a caller to
    discover downstream.
    """
    if hour_start.tzinfo is None:
        raise CaptureError(f"hour_start {hour_start!r} is not tz-aware")
    if (hour_start.minute, hour_start.second, hour_start.microsecond) != (0, 0, 0):
        raise CaptureError(f"hour_start {hour_start.isoformat()} is not aligned to an hour boundary")
    if hour_end != hour_start + timedelta(hours=1):
        raise CaptureError(
            f"hour_end {hour_end!r} is not exactly one hour after hour_start {hour_start.isoformat()} "
            f"— hour_end must be the EXCLUSIVE next-hour boundary"
        )


def _validate_rows_within_hour(df: pl.DataFrame, name: str, hour_start: datetime, hour_end: datetime) -> None:
    """Reject any row whose `ts` falls outside `[hour_start, hour_end)`: a row from the wrong hour
    must be a loud error, never silently spliced into this hour's output."""
    if df.height == 0:
        return
    outside = df.filter((pl.col("ts") < hour_start) | (pl.col("ts") >= hour_end))
    if outside.height:
        bad_ts = outside["ts"][0]
        raise CaptureError(
            f"{name} row with ts {bad_ts.isoformat()} falls outside the hour [{hour_start.isoformat()}, {hour_end.isoformat()})"
        )


def find_book_gaps(
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    *,
    min_gap_seconds: float,
    hour_start: datetime,
    hour_end: datetime,
) -> list[Gap]:
    """Windows where the primary was silent > `min_gap_seconds` AND the secondary was alive inside.

    Windows are formed by pairing CONSECUTIVE boundaries in arrival order: `hour_start`, every primary
    wire message, `hour_end` (the hour's start and its **exclusive** end — the next hour boundary).

    The bounds are REQUIRED, not optional, because two of the windows exist only by virtue of them —
    and they are the ones that matter most:

      * `hour_start` → first primary message — the primary started recording late in the hour;
      * last primary message → `hour_end` — **the primary crashed mid-hour**. That is the natural
        shape of an outage and precisely what this detector exists to catch: there is no "next
        primary message" to pair with, so without the bounds the silence is simply invisible.

    An optional bound on a detector whose false negative is permanent loss is a footgun: a caller that
    omitted it would silently get crash-blindness back, and no test would fail. Required means the
    mistake is a `TypeError` at the call site instead.

    Both edge windows obey the same threshold and the same secondary-witness rule as an interior gap;
    their outer boundary is the hour boundary, which is nobody's wire message (see `Gap`).
    """
    return partition_gaps(primary, secondary, min_gap_seconds=min_gap_seconds, hour_start=hour_start, hour_end=hour_end)[0]


def find_unwitnessed_gaps(
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    *,
    min_gap_seconds: float,
    hour_start: datetime,
    hour_end: datetime,
) -> list[Gap]:
    """The complement of `find_book_gaps`: primary silence the secondary did NOT witness.

    Together the two partition every primary-silence window wider than the threshold, which is the
    point — before this existed, an unwitnessed window produced no `Gap`, no ledger record and no
    log line, so the pair with the LARGEST hole in an outage was the one the system had nothing to
    say about. (2026-07-27: ADA/EUR lost 208.566668 s, the biggest hole of that hour, and its
    secondary held 200 rows inside the gap — every one a `snapshot` at a single instant, not one an
    `update`.) A snapshot is full state, never market activity, so it still may not witness; the
    remedy is to REPORT the window, not to relax what counts as a witness.
    """
    return partition_gaps(primary, secondary, min_gap_seconds=min_gap_seconds, hour_start=hour_start, hour_end=hour_end)[1]


def _primary_silence(primary: pl.DataFrame, min_gap_seconds: float, hour_start: datetime, hour_end: datetime) -> list[Gap]:
    """Every window in which the PRIMARY was silent longer than the threshold, witnessed or not."""
    _validate_hour_bounds(hour_start, hour_end)
    _validate_rows_within_hour(primary, "primary", hour_start, hour_end)

    pri = _message_ts(primary)
    if pri.size == 0:
        # No primary message exists to pair against, so the whole hour is one gap whose boundaries
        # belong to neither side. A file with zero messages is total loss, not quiescence, so
        # `min_gap_seconds` does not apply to it.
        return [
            Gap(
                start=hour_start,
                end=hour_end,
                seconds=(hour_end - hour_start).total_seconds(),
                start_is_primary_message=False,
                end_is_primary_message=False,
            )
        ]

    edges = np.concatenate(([us_from_dt(hour_start)], pri, [us_from_dt(hour_end)]))
    seconds = np.diff(edges).astype(np.float64) / 1e6  # identical float to total_seconds()
    # STRICTLY greater. `int(i)` is load-bearing: a numpy index makes the flags below `np.bool_`,
    # which is not `is True` and serializes as a quoted string in the ledger.
    idx = [int(i) for i in np.nonzero(seconds > min_gap_seconds)[0]]
    last = edges.size - 1
    return [
        Gap(
            start=dt_from_us(edges[i]),
            end=dt_from_us(edges[i + 1]),
            seconds=float(seconds[i]),
            # Only the two outer edges are hour boundaries; every interior edge is a primary message.
            start_is_primary_message=(i != 0),
            end_is_primary_message=(i + 1 != last),
        )
        for i in idx
    ]


def partition_gaps(
    primary: pl.DataFrame,
    secondary: pl.DataFrame,
    *,
    min_gap_seconds: float,
    hour_start: datetime,
    hour_end: datetime,
) -> tuple[list[Gap], list[Gap]]:
    """Both halves of the primary-silence partition in ONE derivation: (witnessed, unwitnessed).

    `find_book_gaps` and `find_unwitnessed_gaps` are thin views over this — spec 00097 D3 collapses
    what used to be two independent derivations of the same silence windows per pair-hour.
    """
    _validate_hour_bounds(hour_start, hour_end)
    _validate_rows_within_hour(secondary, "secondary", hour_start, hour_end)
    _message_ts(secondary)  # for its check alone: raises on non-decreasing `ts` (see its docstring)
    witnessed: list[Gap] = []
    blind: list[Gap] = []
    for gap in _primary_silence(primary, min_gap_seconds, hour_start, hour_end):
        (witnessed if secondary_covers(secondary, gap) else blind).append(gap)
    return witnessed, blind


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


def measure_residual(gaps: list[Gap], spliced: pl.DataFrame, *, min_gap_seconds: float) -> list[Gap]:
    """What each gap STILL lacks after the splice — the output, measured, not the input assumed.

    `healed_seconds` used to be the full width of a primary-silence window, admitted on the strength
    of a single secondary `update` row anywhere inside it (`secondary_covers`). One row admits the
    window; it does not fill it. Measured on the real 2026-07-27 07:00 hour that read as
    2,311.536587 s healed against 82.955463 s actually inserted — and the same hour separately
    booked 2,385.847992 s of `both_streams_silent`, so 2,187.027326 stream-seconds appeared in a
    "we covered it" counter and a "nobody covered it" counter in the same cycle.

    So: re-run the window arithmetic over the spliced rows. Within each gap, pair consecutive
    boundaries — the gap's own start, every spliced message inside it, the gap's end — and keep the
    windows still wider than `min_gap_seconds`. The SAME threshold as `find_book_gaps`, deliberately:
    a hole too small to be a gap on the way in must not become residual on the way out.

    Boundary ownership is inherited from the gap being measured, so a residual window that reaches
    an original edge still says who owns it and stays safe to filter with.

    Every spliced message counts as fill here, including a **snapshot** — unlike `secondary_covers`,
    which refuses to let one witness a gap at all. The asymmetry is deliberate and bounded: a snapshot
    IS book state at that instant, so the second it lands is genuinely not missing, and each distinct
    mark can credit at most `min_gap_seconds` of the surrounding window. Admitting the window remains
    the strict question; measuring what the window still lacks is the lenient one.
    """
    if not gaps:
        return []
    # Back to datetimes at this boundary and nowhere else: the arithmetic below stays byte-identical,
    # and the cost is bounded — this runs only for the hours that carry an admitted gap.
    inside_ts = [dt_from_us(u) for u in _message_ts(spliced)] if spliced.height else []
    residual: list[Gap] = []
    for gap in gaps:
        marks = [t for t in inside_ts if gap.start <= t <= gap.end]
        boundaries = [gap.start, *marks, gap.end]
        for lo, hi in zip(boundaries, boundaries[1:], strict=False):
            if (hi - lo).total_seconds() <= min_gap_seconds:
                continue
            residual.append(
                Gap(
                    start=lo,
                    end=hi,
                    seconds=(hi - lo).total_seconds(),
                    # An interior boundary is a spliced message; an outer one keeps the gap's own
                    # ownership so the result filters exactly like the gap it came from.
                    start_is_primary_message=gap.start_is_primary_message if lo == gap.start else False,
                    end_is_primary_message=gap.end_is_primary_message if hi == gap.end else False,
                )
            )
    return residual


def overlap_seconds(spans: Iterable[tuple[datetime, datetime]], windows: Iterable[tuple[datetime, datetime]]) -> float:
    """How much of `spans` lies inside `windows` — the seconds a SECOND record has already booked.

    Permanent loss is booked from two directions. `both_streams_silent` books the fleet-dark
    intersection as window × dark stream count; a healed hour books whatever its splice left unfilled.
    A gap straddling the darkness contains the same seconds, so booking both in full counts them
    twice — correcting a heal over-count by manufacturing a loss over-count in the same counter. Each
    side subtracts what the LEDGER shows the other already booked, so every second of loss is
    attributed exactly once regardless of which side decided first.

    Windows are merged before intersecting: two overlapping windows must not subtract the same second
    twice, which would under-book a loss that really is unbooked.
    """
    merged: list[list[datetime]] = []
    for start, end in sorted(windows):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    total = 0.0
    for a, b in spans:
        for lo, hi in merged:
            span = (min(b, hi) - max(a, lo)).total_seconds()
            if span > 0:
                total += span
    return total


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

    Output is BLOCK-ordered, not necessarily time-ordered (a row that leaked in from an adjacent hour
    lands in a trailing primary block rather than being dropped) — a consumer must never "fix" that by
    sorting, for the same absolute-quantity reason.

    The secondary block deliberately keeps its **snapshot** rows. A snapshot is a full book state, so
    it re-anchors a replaying consumer at the splice boundary — and it is what makes a CRC replay
    across the boundary meaningful. (A snapshot still never *witnesses* a gap: see `secondary_covers`.)
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


@dataclass(frozen=True)
class TradeUnion:
    """The healed hour's trades, plus what changed and what the secondary was missing.

    `secondary_deficit` counts ids the secondary lacks that the primary has. That is evidence about
    the SECONDARY's own health — a QA signal — and must never trigger a mint: this reconciler only
    ever heals a primary deficit, never the reverse.
    """

    frame: pl.DataFrame
    added_from_secondary: int
    deduped_rows: int
    secondary_deficit: int


def union_trades(primary: pl.DataFrame, secondary: pl.DataFrame) -> TradeUnion:
    """Heal a primary trade deficit from the secondary. Row-level union is safe here — and ONLY
    here in the reconciler — because `trade_id` is globally unique and identical across hosts (spec
    00050 constraint 2), unlike book rows, which carry absolute quantities and may never be
    interleaved across hosts.

    Ordered by `trade_id`. That column is `TRADE_SCHEMA`'s `Int64` (`cli/capture/segment_writer.py`,
    populated by `int(trade["trade_id"])`) — never a string — so `sort("trade_id")` is a numeric
    sort, not a lexicographic one. `trade_id` is per-pair monotone, so the numeric sort is also a
    chronological one and the result is deterministic.

    Deduped with primary priority: the deployed writer dedups intra-hour at capture time (T0037), but
    pre-fix archive hours genuinely contain reconnect-replay duplicates (T0026), and this must handle
    that history. Concatenating primary-then-added-secondary and keeping the FIRST occurrence per
    `trade_id` means a duplicated primary row always wins over a later copy of itself; an added
    secondary row is never itself a duplicate, since it was, by construction, absent from the primary.
    """
    pri_ids = set(primary["trade_id"].to_list()) if primary.height else set()
    sec_ids = set(secondary["trade_id"].to_list()) if secondary.height else set()

    missing = sec_ids - pri_ids
    to_add = secondary.filter(pl.col("trade_id").is_in(list(missing))) if missing else secondary.head(0)

    combined = pl.concat([primary, to_add]) if to_add.height else primary
    before = combined.height
    deduped = combined.unique(subset=["trade_id"], keep="first", maintain_order=True).sort("trade_id")

    return TradeUnion(
        frame=deduped,
        added_from_secondary=len(missing),
        deduped_rows=before - deduped.height,
        secondary_deficit=len(pri_ids - sec_ids),
    )
