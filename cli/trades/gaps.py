from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl


@dataclass(frozen=True)
class IdGap:
    """A contiguous run of missing `trade_id`s, bracketed by the ids/timestamps that survive.

    `ts_lo`/`ts_hi` are the timestamps of `after_id`/`before_id` — the fetch window, since REST is
    queried by time, not by id.
    """

    after_id: int
    before_id: int
    ts_lo: dt.datetime
    ts_hi: dt.datetime

    @property
    def missing(self) -> int:
        return self.before_id - self.after_id - 1


@dataclass(frozen=True)
class Detection:
    gaps: list[IdGap]
    duplicate_ids: list[int]
    rows: int
    unique: int
    span: int
    missing: int


def detect(frame: pl.DataFrame) -> Detection:
    """Find missing and duplicated `trade_id`s in one pair's trades.

    Kraken's `trade_id` is DENSE and per-pair monotone (spec 00053 D1, verified empirically), so a
    hole in the sequence IS missing data — provable with no REST call. The span is bounded by the
    first and last observed id: neither endpoint is a gap (capture-start / the live edge).
    """
    if frame.height == 0:
        return Detection([], [], 0, 0, 0, 0)

    df = frame.select("ts", "trade_id").sort("trade_id")
    ids = df["trade_id"].to_list()

    # Duplicates first, and SEPARATELY from gaps: on a sorted series a duplicate is (x, x), which a
    # naive `b != a+1` reads as a negative-width gap.
    dup_ids = df.group_by("trade_id").len().filter(pl.col("len") > 1)["trade_id"].sort().to_list()

    first = df.unique(subset=["trade_id"], keep="first").sort("trade_id")
    uids = first["trade_id"].to_list()
    tss = first["ts"].to_list()

    gaps = [
        IdGap(after_id=a, before_id=b, ts_lo=tss[i], ts_hi=tss[i + 1])
        for i, (a, b) in enumerate(zip(uids, uids[1:], strict=False))
        if b > a + 1
    ]
    span = uids[-1] - uids[0] + 1
    missing = span - len(uids)
    assert sum(g.missing for g in gaps) == missing, "gap widths must sum to the missing count"
    return Detection(gaps, dup_ids, len(ids), len(uids), span, missing)
