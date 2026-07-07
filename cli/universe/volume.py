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
