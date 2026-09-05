from __future__ import annotations

import polars as pl

_BAR_SCHEMA = {
    "ts": pl.Datetime("us", "UTC"),
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Float64,
    "count": pl.Int64,
    "vwap": pl.Float64,
}


def ticks_to_bars(df: pl.DataFrame, *, interval_minutes: int) -> pl.DataFrame:
    """Aggregate a tick frame (`cli.tick.read.read_trades_csv`'s) into OHLCV bars sorted by `ts`, in epoch-aligned buckets so that
    1440-minute bars fall on UTC midnight, matching the canonical OHLCVT convention. An interval with no ticks yields no bar
    (never gap-filled), and empty input is a normal outcome rather than the `TickError` `read_trades_csv` raises. `vwap` is the
    true tick-weighted mean, not `cli.backfill.aggregate.aggregate_minutes`' close-price proxy."""
    if df.height == 0:
        return pl.DataFrame(schema=_BAR_SCHEMA)

    bars = (
        df.sort("ts")
        .group_by_dynamic("ts", every=f"{interval_minutes}m", closed="left")
        .agg(
            pl.col("price").first().alias("open"),
            pl.col("price").max().alias("high"),
            pl.col("price").min().alias("low"),
            pl.col("price").last().alias("close"),
            pl.col("volume").sum().alias("volume"),
            pl.len().cast(pl.Int64).alias("count"),
            (pl.col("price") * pl.col("volume")).sum().alias("_pv_sum"),
        )
        .with_columns((pl.col("_pv_sum") / pl.col("volume")).alias("vwap"))
    )
    return bars.select(list(_BAR_SCHEMA))
