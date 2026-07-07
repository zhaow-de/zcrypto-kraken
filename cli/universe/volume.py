from __future__ import annotations

import polars as pl

from cli.universe.errors import UniverseError


def median_quote_volume(daily: pl.DataFrame, *, window: int = 30) -> float:
    """Median per-day quote volume (`volume * vwap`) over the last `window` rows of `daily`.

    `daily` is a canonical OHLC daily-bar frame (`cli.ohlc.to_frame` schema), assumed sorted
    ascending by `ts`. Raises `UniverseError` if `daily` has fewer than `window` rows.
    """
    if daily.height < window:
        raise UniverseError(f"need at least {window} daily rows for a median quote volume, got {daily.height}")
    tail = daily.tail(window)
    quote_volume = tail["volume"] * tail["vwap"]
    return float(quote_volume.median())


def quote_volume_in_eur(daily: pl.DataFrame, *, fx_daily: pl.DataFrame | None = None, window: int = 30) -> float:
    """Median 30d quote-volume normalized to EUR.

    For a EUR-quoted pair (fx_daily=None) this equals median_quote_volume(daily, window). For a
    non-EUR quote, fx_daily is the {quote}/EUR canonical daily frame (cli.ohlc.to_frame schema),
    per-day EUR turnover is volume * vwap * fx_close (fx_close = fx_daily's close, joined on ts),
    and the result is the median over the last `window` aligned rows. Raises UniverseError if fewer
    than `window` rows are available (in daily, or after the ts-join with fx_daily).
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
