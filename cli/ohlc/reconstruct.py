from __future__ import annotations

import polars as pl


def fill_gaps(frame: pl.DataFrame, interval_secs: int) -> pl.DataFrame:
    """Reconstruct empty intervals in `frame` by inserting a synthetic bar for every missing grid point.

    `frame` is the canonical schema from `cli.ohlc.dataset.to_frame` (sorted ascending, every `ts` on the
    `interval_secs` grid). Each synthetic bar carries the prior (forward-filled) close: `open == high ==
    low == close == vwap == <last real close before this ts>`, `volume = 0.0`, `count = 0`. Consecutive
    gaps all carry the same forward-filled close. A frame with fewer than 2 rows, or already contiguous,
    is returned unchanged. Output has the same schema, column order, and dtypes as `frame`.
    """
    if frame.height < 2:
        return frame

    grid = pl.datetime_range(
        frame["ts"][0], frame["ts"][-1], interval=f"{interval_secs}s", time_unit="us", time_zone="UTC", eager=True
    ).alias("ts")

    if grid.len() == frame.height:
        return frame

    joined = pl.DataFrame({"ts": grid}).join(frame, on="ts", how="left")
    is_synthetic = pl.col("count").is_null()

    result = joined.with_columns(pl.col("close").fill_null(strategy="forward").alias("close")).with_columns(
        pl.when(is_synthetic).then(pl.col("close")).otherwise(pl.col("open")).alias("open"),
        pl.when(is_synthetic).then(pl.col("close")).otherwise(pl.col("high")).alias("high"),
        pl.when(is_synthetic).then(pl.col("close")).otherwise(pl.col("low")).alias("low"),
        pl.when(is_synthetic).then(pl.col("close")).otherwise(pl.col("vwap")).alias("vwap"),
        pl.when(is_synthetic).then(0.0).otherwise(pl.col("volume")).alias("volume"),
        pl.when(is_synthetic).then(0).otherwise(pl.col("count")).alias("count"),
    )

    return result.select(frame.columns).cast(frame.schema)
