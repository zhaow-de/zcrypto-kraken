"""Materialize 15m bars from the captured trade tape into the daily finals `tape-bars` publishes (spec 00087).

The tape is the only fine-cadence source whose reach does not expire: REST's window recedes and the OHLCVT dumps are
quarterly, while captured trades accrue."""

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
    """`{pair: {hour: path}}` for the whole healed trade archive, walked ONCE: `canonical_segments` globs the entire archive,
    so calling it per pair or per day is O(pairs x days x archive) on a tree that grows forever."""
    index: SegmentIndex = {}
    for pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="trades"):
        index.setdefault(pair, {})[hour] = path
    return index


def build_day(index: SegmentIndex, pair: str, day: date) -> pl.DataFrame:
    """The healed tape for `pair` on UTC `day`, aggregated to 15m bars -- whatever hours the day HAS, since completeness is
    `is_heal_complete`'s measured trade_id contiguity (D3/D4) and never hour-file presence."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    hours = index.get(pair, {})
    present = {hour: path for hour, path in hours.items() if start <= hour < end}
    if not present:
        raise TickError(f"tape-bars: {pair} {day.isoformat()} has no trade segments at all")

    # No 24-hour completeness check: the capture writer commits no final for an hour with no events, so an absent hour may
    # be merely quiet, and requiring 24 would make every day with a quiet hour permanently unpublishable.
    frames = [pl.read_parquet(present[hour]) for hour in sorted(present)]
    ticks = pl.concat(frames).rename({"qty": "volume"}).select("ts", "price", "volume")
    return ticks_to_bars(ticks, interval_minutes=BASE_INTERVAL_MINUTES)


def derive_bars(bars: pl.DataFrame, *, interval_minutes: int) -> pl.DataFrame:
    """Aggregate 15m base bars up to `interval_minutes` -- exactly, not approximately: `ticks_to_bars`' vwap is TRUE
    tick-weighted, so `Σ(vwap_i·vol_i)` telescopes to `Σ(price·volume)` over the coarse window and the coarse vwap re-derives
    as `Σ(vwap_i·vol_i)/Σ(vol_i)` -- a plain mean of sub-bar vwaps is wrong on any window whose volume is not uniform."""
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


# A cheap pre-filter, never the gate: it clears the daily `zcrypto archive backfill-trades` run that heals a day's last hour
# -- which defers on its own `_SETTLE` in `cli/trades/backfill.py`, never `cli.archive.settle.SETTLE_HOURS` -- and
# heal-completeness is `is_heal_complete`'s measured trade_id contiguity (D3), so drift here costs latency, not correctness.
TAPE_SETTLE = timedelta(hours=26)
RESCAN_DAYS = 3


@dataclass(frozen=True)
class MaterializeResult:
    """One sweep's verdict; a day that raises is isolated into `errors` -- one bad day must not cost the others."""

    days_written: int
    days_skipped: int
    days_unsettled: int
    days_unhealed: int
    #: Settled, unpublished days that have fallen OUTSIDE the candidate window -- permanent gaps, counted from the calendar
    #: and the published set alone, so the one signal for the dataset's permanent failure mode never expires.
    days_gap: int
    rows: int
    errors: list[tuple[str, date, str]]


def is_heal_complete(index: SegmentIndex, pair: str, day: date) -> bool:
    """Has the healer finished with this day? MEASURED, never inferred from the clock (D3): `cli.trades.gaps.detect` treats
    the first and last observed ids as endpoints rather than gaps, so the day is read with the NEAREST PRESENT segment each
    side -- never merely the adjacent hour, which a quiet hour leaves absent, silently publishing a truncated day; no later
    segment is the live edge and is refused, no earlier is the archive's genesis day and is accepted."""
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
    span = own + ([max(before)] if before else []) + [min(after)]
    detection = detect(pl.concat(pl.read_parquet(hours[h]) for h in sorted(span)))
    return not detection.gaps and not detection.duplicate_ids


def _final_path(out_root: Path, pair: str, day: date) -> Path:
    base, quote = pair.split("/")
    return out_root / base / quote / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"


def publish_day(out_root: Path, pair: str, day: date, bars: pl.DataFrame) -> Path:
    """Atomic publish, `cli/archive/mint.py`'s `mint_hour` order: the sidecar is renamed into place BEFORE the final,
    so a reader never sees a final without its digest."""
    final = _final_path(out_root, pair, day)
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_suffix(f".parquet.{os.getpid()}.tmp")
    bars.write_parquet(tmp)
    _fsync(tmp)  # data before rename -- mint.py's `_replace_durably` semantics, for BOTH artifacts
    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    sidecar_tmp = final.with_suffix(f".parquet.sha256.{os.getpid()}.tmp")
    sidecar_tmp.write_text(f"{digest}  {final.name}\n")
    # The `.exists()` skip means a day is never re-published, so a sidecar that loses its bytes at power loss reads as
    # corruption on an irreplaceable final, forever: it gets the same durability as the final it vouches for.
    _fsync(sidecar_tmp)
    os.replace(sidecar_tmp, final.with_suffix(".parquet.sha256"))
    # The directory fsync goes BETWEEN the two renames, not only after both: without it a crash can leave the final visible
    # while the sidecar rename is unpersisted, and the `.exists()` skip means that sidecar is never minted again.
    _fsync(final.parent)
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
    """The newest published day for `pair`, None on a first run, a refusal when that newest path is not one of ours."""
    base, quote = pair.split("/")
    finals = sorted((out_root / base / quote).rglob("*.parquet"))
    if not finals:
        return None
    newest = finals[-1]
    try:
        return date(int(newest.parents[1].name), int(newest.parent.name), int(newest.stem))
    except (ValueError, OverflowError) as exc:  # OverflowError: `int()` is arbitrary-precision, `date()`'s C-int year is not
        raise TickError(f"tape-bars: {pair} published path is not <YYYY>/<MM>/<DD>.parquet: {newest}") from exc


def materialize(
    primary_root: Path,
    reconciled_root: Path,
    out_root: Path,
    *,
    now: datetime,
    settle: timedelta = TAPE_SETTLE,
    rescan_days: int = RESCAN_DAYS,
) -> MaterializeResult:
    """Sweep every archived pair, publishing each settled day that has no final yet. A day is settled once
    `now - day_end >= settle` -- `now` is injected so the boundary is testable -- and an unsettled day is counted and left
    alone so a later sweep takes it once heal-complete (D3)."""
    written = skipped = unsettled = unhealed = gap = rows = 0
    errors: list[tuple[str, date, str]] = []
    index = segment_index(primary_root, reconciled_root)
    for pair, days in _archive_calendar(index).items():
        settled = [d for d in days if now - (datetime(d.year, d.month, d.day, tzinfo=UTC) + timedelta(days=1)) >= settle]
        unsettled += len(days) - len(settled)
        if not settled:
            continue
        # Bounded candidate range (D4): everything past the watermark plus a trailing re-scan window, so a day that failed on
        # an incomplete tape is retried while a late overlay mint can still rescue it, then becomes a VISIBLE gap.
        watermark = _watermark(out_root, pair)
        if watermark is None:
            # FIRST RUN sweeps the whole archive: bounding it here would silently strand the backlog -- the
            # watermark would jump to the newest day and nothing below the floor would ever be attempted again.
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
                publish_day(out_root, pair, day, bars)
            except Exception as exc:  # noqa: BLE001 -- one bad day must not abort the sweep
                # `publish_day` is INSIDE the try deliberately: an environmental publish failure (ENOSPC, EACCES,
                # a rename error) must cost one day, never every remaining pair of the sweep.
                errors.append((pair, day, f"{type(exc).__name__}: {exc}"))
                continue
            written += 1
            rows += bars.height
    return MaterializeResult(written, skipped, unsettled, unhealed, gap, rows, errors)
