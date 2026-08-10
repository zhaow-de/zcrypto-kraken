"""Materialize 15m bars from the captured trade tape (spec 00087).

The tape is the only fine-cadence source whose reach does not expire: REST's window recedes and the
OHLCVT dumps are quarterly, while captured trades accrue. This module turns one healed UTC day of
that tape into the 15m bars that `tape-bars` publishes as a daily final.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.tick.aggregate import ticks_to_bars
from cli.tick.errors import TickError
from cli.trades.gaps import detect

BASE_INTERVAL_MINUTES = 15


SegmentIndex = dict[str, dict[datetime, Path]]


def segment_index(primary_root: Path, reconciled_root: Path) -> SegmentIndex:
    """`{pair: {hour: path}}` for the whole healed trade archive, walked ONCE.

    `canonical_segments` globs the entire archive, so calling it per pair or per day is
    O(pairs x days x archive) on a tree that grows forever under an hourly sweep. Every consumer
    below takes this index instead of the roots.
    """
    index: SegmentIndex = {}
    for pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        index.setdefault(pair, {})[hour] = path
    return index


def build_day(index: SegmentIndex, pair: str, day: date) -> pl.DataFrame:
    """The healed tape for `pair` on UTC `day`, aggregated to 15m bars.

    Reads the pre-built index (reconciled-first by construction). Aggregates whatever hours the day
    HAS: hour-file presence is not a completeness signal, because a quiet hour writes no final.
    Completeness is `is_heal_complete`'s measured trade_id contiguity (D3/D4).
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    hours = index.get(pair, {})
    present = {hour: path for hour, path in hours.items() if start <= hour < end}
    if not present:
        raise TickError(f"tape-bars: {pair} {day.isoformat()} has no trade segments at all")

    # Deliberately NO 24-hour completeness check. The capture writer commits no final for an hour
    # with no events, and zero-print trades hours are production-measured (settle.py records
    # LINK/EUR: 8 prints in hour 01, 9 in hour 04, zero between), so an absent hour means "quiet",
    # not "missing". Requiring 24 would make every day with a quiet hour permanently unpublishable.
    # Completeness is trade_id contiguity -- is_heal_complete -- which tells the two apart.
    frames = [pl.read_parquet(present[hour]) for hour in sorted(present)]
    ticks = pl.concat(frames).rename({"qty": "volume"}).select("ts", "price", "volume")
    return ticks_to_bars(ticks, interval_minutes=BASE_INTERVAL_MINUTES)


def derive_bars(bars: pl.DataFrame, *, interval_minutes: int) -> pl.DataFrame:
    """Aggregate 15m base bars up to `interval_minutes` -- exactly, not approximately.

    `ticks_to_bars` computes a TRUE tick-weighted vwap, so `Σ(vwap_i · volume_i)` over sub-bars
    telescopes to `Σ(price · volume)` over the whole window and the coarse vwap re-derives as
    `Σ(vwap_i·vol_i) / Σ(vol_i)`. A plain mean of sub-bar vwaps is the tempting form and is WRONG on
    any window whose volume is not uniform. Empty windows stay absent: a coarse bar exists iff at
    least one sub-bar does.
    """
    if bars.height == 0:
        return bars
    return (
        bars.sort("ts")
        .group_by_dynamic("ts", every=f"{interval_minutes}m", closed="left")
        .agg(
            pl.col("open").first(),
            pl.col("high").max(),
            pl.col("low").min(),
            pl.col("close").last(),
            pl.col("volume").sum(),
            pl.col("count").sum(),
            (pl.col("vwap") * pl.col("volume")).sum().alias("_pv_sum"),
        )
        .with_columns((pl.col("_pv_sum") / pl.col("volume")).alias("vwap"))
        .select("ts", "open", "high", "low", "close", "volume", "count", "vwap")
    )


# D3, derived rather than estimated. An hour heals only when `zcrypto archive backfill-trades`
# repairs it, and that job DEFERS any hour younger than its own module-local `_SETTLE` (2h) in
# `cli/trades/backfill.py` -- NOT `cli.archive.settle.SETTLE_HOURS`, which it never imports while
# running only once per UTC day (~00:12, the `.trade-backfill-last-utc-day` stamp on the *:12,42 pull
# timer). So at the D+1 run day D's hours 00-22 heal but hour 23 is still inside the 2h gate and is
# deferred -- it heals at the D+2 run. Day D is therefore heal-complete at D+2 00:12 UTC, ~24.2h
# after it closes; 26h adds buffer for the NAS pull cycle and clock skew. IF THE BACKFILL'S CADENCE
# OR backfill.py's _SETTLE CHANGES, THIS PRE-FILTER DRIFTS -- harmless now that the real gate is
# the measured trade_id contiguity check, which is why this constant is no longer load-bearing.
TAPE_SETTLE = timedelta(hours=26)
RESCAN_DAYS = 3


@dataclass(frozen=True)
class MaterializeResult:
    """One sweep's verdict: published, already-covered, deferred as not-yet-heal-complete (D3), and
    failed outright (isolated, never raised -- one bad day must not cost the others)."""

    days_written: int
    days_skipped: int
    days_unsettled: int
    days_unhealed: int
    #: settled, unpublished days that have fallen OUTSIDE the candidate window -- permanent gaps.
    #: Counted from the calendar and the published set alone (zero file reads), so the signal never
    #: expires: without it, a day that leaves the window also leaves every counter, and the dataset's
    #: one permanent failure mode becomes invisible at exactly the moment it becomes final.
    days_gap: int
    rows: int
    errors: list[tuple[str, date, str]]


def is_heal_complete(index: SegmentIndex, pair: str, day: date) -> bool:
    """Has the healer finished with this day? MEASURED, never inferred from the clock (D3).

    Kraken's `trade_id` is dense and per-pair monotone, so a hole in the sequence IS missing data --
    `cli.trades.gaps.detect` proves it with no REST call. The day is read WITH the NEAREST PRESENT
    segment on each side, not merely the adjacent hour: `detect` treats the first and last observed
    id as endpoints rather than gaps, and the adjacent hour is often legitimately absent (a quiet
    hour writes no final), so an adjacent-hour-only extension degrades silently back to endpoint
    blindness and publishes a truncated day. No later segment at all means the live edge, which is
    refused; no earlier segment at all means the archive's genesis day, where the endpoint rule is
    correct and the day is accepted.
    """
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    hours = index.get(pair, {})
    own = sorted(h for h in hours if start <= h < end)
    if not own:
        return False
    before = [h for h in hours if h < start]
    after = [h for h in hours if h >= end]
    if not after:
        return False  # live edge: nothing after the day, so its tail id is an endpoint, not proof
    # `[max(before)] * bool(before)` LOOKS lazy but is not: Python evaluates max() before the
    # multiply, so an empty `before` -- the genesis day, the case this rule ACCEPTS -- crashed with
    # ValueError, and the sweep's broad except turned every pair's first day into a permanent error.
    span = own + ([max(before)] if before else []) + [min(after)]
    detection = detect(pl.concat(pl.read_parquet(hours[h]) for h in sorted(span)))
    return not detection.gaps and not detection.duplicate_ids


def _final_path(out_root: Path, pair: str, day: date) -> Path:
    base, quote = pair.split("/")
    return out_root / base / quote / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def publish_day(out_root: Path, pair: str, day: date, bars: pl.DataFrame) -> Path:
    """Atomic publish: tmp in the destination dir -> sidecar minted from the tmp bytes -> os.replace
    -> fsync the dir. The sidecar is written BEFORE the publishing rename so a reader never sees a
    final without its digest (the `cli/archive/mint.py` pattern)."""
    final = _final_path(out_root, pair, day)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_suffix(f".parquet.{os.getpid()}.tmp")
    bars.write_parquet(tmp)
    _fsync(tmp)  # data before rename -- mint.py's `_replace_durably` semantics, for BOTH artifacts
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    sidecar_tmp = final.with_suffix(f".parquet.sha256.{os.getpid()}.tmp")
    sidecar_tmp.write_text(f"{digest}  {final.name}\n")
    # A torn sidecar is PERMANENT: the .exists() skip means the day is never re-published, so an
    # un-fsynced sidecar that loses its bytes at power loss reads as corruption on an irreplaceable
    # final, forever. The sidecar gets the same durability as the final it vouches for.
    _fsync(sidecar_tmp)
    os.replace(sidecar_tmp, final.with_suffix(".parquet.sha256"))
    os.replace(tmp, final)
    _fsync(final.parent)
    return final


def _fsync(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _archive_calendar(index: SegmentIndex) -> dict[str, list[date]]:
    """Every archived pair -> its sorted distinct UTC days, read off the one index walk."""
    return {pair: sorted({hour.date() for hour in hours}) for pair, hours in sorted(index.items())}


def _watermark(out_root: Path, pair: str) -> date | None:
    """The newest published day for `pair`, or None on a first run."""
    base, quote = pair.split("/")
    finals = sorted((out_root / base / quote).rglob("*.parquet"))
    if not finals:
        return None
    newest = finals[-1]
    return date(int(newest.parents[1].name), int(newest.parent.name), int(newest.stem))


def materialize(
    primary_root: Path,
    reconciled_root: Path,
    out_root: Path,
    *,
    now: datetime,
    settle: timedelta = TAPE_SETTLE,
    rescan_days: int = RESCAN_DAYS,
) -> MaterializeResult:
    """Sweep every archived pair, publishing each settled day that has no final yet.

    `now` is injected so the settle boundary is testable. A day is settled once
    `now - (day_end) >= settle`; an unsettled day is counted and left alone, so a later sweep takes
    it once heal-complete (D3 / T0066 option (a)). A day that raises is isolated into `errors`.
    """
    written = skipped = unsettled = unhealed = gap = rows = 0
    errors: list[tuple[str, date, str]] = []
    index = segment_index(primary_root, reconciled_root)
    for pair, days in _archive_calendar(index).items():
        settled = [d for d in days if now - (datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)) >= settle]
        unsettled += len(days) - len(settled)
        if not settled:
            continue
        # Bounded candidate range (D4): everything past the watermark, plus a trailing re-scan window
        # so a day that failed while its tape was incomplete is retried while a late overlay mint can
        # still rescue it -- and then becomes a permanent, VISIBLE gap rather than an unbounded retry.
        watermark = _watermark(out_root, pair)
        if watermark is None:
            # FIRST RUN: sweep the whole archive. Bounding it here would silently strand the entire
            # backlog -- the watermark would jump to the newest day and everything below the floor
            # would never be attempted again, with no error and no counter. A permanently short
            # dataset that looks complete is the worst outcome this design can produce.
            candidates = settled
        else:
            floor = min(settled[-1] - timedelta(days=rescan_days), watermark + timedelta(days=1))
            candidates = [d for d in settled if d >= floor]
            gap += sum(1 for d in settled if d < floor and not _final_path(out_root, pair, d).exists())
        for day in candidates:
            if _final_path(out_root, pair, day).exists():
                skipped += 1
                continue
            try:
                if not is_heal_complete(index, pair, day):
                    unhealed += 1
                    continue
                bars = build_day(index, pair, day)
            except Exception as exc:  # noqa: BLE001 -- one bad day must not abort the sweep
                # Broad on purpose, matching cli/panel/materialize.py: a corrupt parquet or an
                # unexpected error inside detect must cost one day, never every pair's whole sweep.
                errors.append((pair, day, f"{type(exc).__name__}: {exc}"))
                continue
            publish_day(out_root, pair, day, bars)
            written += 1
            rows += bars.height
    return MaterializeResult(written, skipped, unsettled, unhealed, gap, rows, errors)
