from __future__ import annotations

import polars as pl


def fill_gaps(frame: pl.DataFrame, interval_secs: int) -> pl.DataFrame:
    """Insert a synthetic bar — the prior close in every price column, zero volume and count — at each missing grid point.

    `frame` is `cli.ohlc.dataset.to_frame`'s canonical schema, ascending with every `ts` on the `interval_secs` grid.
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
