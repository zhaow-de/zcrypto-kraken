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
    """Aggregate a tick frame (as returned by `cli.tick.read.read_trades_csv`) into OHLCV bars.

    Buckets ticks into `interval_minutes`-wide, left-closed windows aligned to the epoch — matching
    the canonical OHLCVT bar convention (e.g. 1440-minute buckets fall on UTC midnight, since the
    epoch origin 1970-01-01T00:00:00Z is itself UTC midnight). A tick exactly on a bucket boundary
    belongs to the bucket it opens, not the one it closes. Per bucket, in `ts` order: `open`=first
    trade price, `high`=max, `low`=min, `close`=last trade price, `volume`=sum, `count`=n trades, and
    `vwap`=`Σ(price·volume)/Σ(volume)` — the true tick-weighted VWAP (not a close-price reconstruction
    proxy, unlike `cli.backfill.aggregate.aggregate_minutes`, which lacks per-trade data to compute one).

    Returns columns `[ts, open, high, low, close, volume, count, vwap]` sorted by `ts`. An interval
    with zero ticks simply produces no bar (no gap-filling). Empty input returns an empty frame with
    the same schema — no error (unlike `read_trades_csv`, empty is a normal outcome here: an interval
    boundary or a pair/window with no trades).
    """
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
