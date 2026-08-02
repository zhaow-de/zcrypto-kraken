"""Seam primitives shared by the REST reach round (`cli/ohlc/reach.py`) and the engine's live
price store (`cli/engine/store.py`): the drop-the-in-progress-candle rule and the seam definition
itself (what counts as overlap, what counts as a mismatch). The guard POLICIES stay with the
callers -- their exception types, message texts, and merge rules differ on purpose -- but a change
to what a seam IS belongs here, where both callers inherit it."""

from __future__ import annotations

from datetime import datetime

import polars as pl

# Shared stamps required before a seam counts as verified: below this the join rests on too few
# agreeing bars to distinguish "the same series" from "coincidentally equal at the boundary".
MIN_SEAM_OVERLAP = 6


def drop_in_progress(frame: pl.DataFrame, interval: int, now: datetime) -> pl.DataFrame:
    """Drop any row whose interval end (stamp + interval minutes) lies after `now` -- Kraken's
    OHLC response always includes the currently-forming candle as its last row; persisting it
    would write a bar that is still changing. A row ending exactly at `now` is complete, so kept."""
    return frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)


def seam_overlap(left: pl.DataFrame, right: pl.DataFrame) -> tuple[int, pl.DataFrame]:
    """Join `left` and `right` on `ts` and return `(overlap_bars, mismatches)`: the shared-stamp
    count, and the shared rows whose closes disagree (right-side columns suffixed `_rest`). This
    is the seam DEFINITION -- both callers' guards read these two values, so a change to what
    counts as agreement lands here and neither copy can drift."""
    shared = left.join(right, on="ts", how="inner", suffix="_rest")
    return shared.height, shared.filter(pl.col("close") != pl.col("close_rest"))
