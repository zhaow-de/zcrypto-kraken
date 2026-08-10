"""Materialize 15m bars from the captured trade tape (spec 00087).

The tape is the only fine-cadence source whose reach does not expire: REST's window recedes and the
OHLCVT dumps are quarterly, while captured trades accrue. This module turns one healed UTC day of
that tape into the 15m bars that `tape-bars` publishes as a daily final.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.tick.aggregate import ticks_to_bars
from cli.tick.errors import TickError

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
