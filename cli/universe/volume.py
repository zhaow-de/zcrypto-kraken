from __future__ import annotations

import polars as pl

from cli.universe.errors import UniverseError


def median_quote_volume(daily: pl.DataFrame, *, window: int = 30) -> float:
    """Median daily quote volume (`volume * vwap`) over the last `window` rows of a `ts`-ascending `cli.ohlc.to_frame` frame."""
    if daily.height < window:
        raise UniverseError(f"need at least {window} daily rows for a median quote volume, got {daily.height}")
    tail = daily.tail(window)
    quote_volume = tail["volume"] * tail["vwap"]
    return float(quote_volume.median())


def quote_volume_in_eur(daily: pl.DataFrame, *, fx_daily: pl.DataFrame | None = None, window: int = 30) -> float:
    """Median daily quote volume over the last `window` rows, normalized to EUR.

    `fx_daily` is the `{quote}/EUR` daily frame whose `close` converts each day's turnover, `None` for a EUR-quoted pair.
    """
    if fx_daily is None:
        return median_quote_volume(daily, window=window)

    fx = fx_daily.select("ts", pl.col("close").alias("fx_close"))
    joined = daily.join(fx, on="ts", how="inner")
    if joined.height < window:
        raise UniverseError(f"need at least {window} fx-aligned daily rows for a median quote volume, got {joined.height}")
    tail = joined.sort("ts").tail(window)
    quote_volume = tail["volume"] * tail["vwap"] * tail["fx_close"]
    return float(quote_volume.median())
