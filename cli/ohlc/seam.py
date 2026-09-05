"""Seam primitives shared by `cli/ohlc/reach.py` and `cli/engine/store.py`: what a seam IS is defined here; the guard policies stay with the callers and deliberately differ."""

from __future__ import annotations

from datetime import datetime

import polars as pl

# Below this many shared stamps a join cannot tell "the same series" from "coincidentally equal at the boundary".
MIN_SEAM_OVERLAP = 6


def drop_in_progress(frame: pl.DataFrame, interval: int, now: datetime) -> pl.DataFrame:
    """Drop rows whose interval end (stamp + interval minutes) lies after `now` -- Kraken's OHLC response always carries the currently-forming candle."""
    return frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)


def seam_overlap(left: pl.DataFrame, right: pl.DataFrame) -> tuple[int, pl.DataFrame]:
    """Join `left` and `right` on `ts`, returning the shared-stamp count and the shared rows whose closes disagree (right-side columns suffixed `_rest`)."""
    shared = left.join(right, on="ts", how="inner", suffix="_rest")
    return shared.height, shared.filter(pl.col("close") != pl.col("close_rest"))
