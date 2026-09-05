from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import polars as pl

from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError

logger = get_logger("trades.gaps")


@dataclass(frozen=True)
class IdGap:
    """A contiguous run of missing `trade_id`s, bracketed by the surviving ids either side.

    `ts_lo`/`ts_hi` are those ids' timestamps ordered low-to-high — the fetch window, since REST is queried by time, not by id.
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

    Kraken's `trade_id` is dense and per-pair monotone (spec 00053 D1): a hole inside the observed span IS missing data.
    """
    if frame.height == 0:
        return Detection([], [], 0, 0, 0, 0)

    df = frame.select("ts", "trade_id")
    if df["trade_id"].null_count() > 0:
        raise TradeBackfillError("null trade_id in frame; cannot detect gaps")
    ids = df["trade_id"].to_list()

    # Duplicates are counted before `unique()` below drops them; after that drop `b > a` always holds, so the
    # gap test's comparator (`>` or `!=`) never decides a duplicate's fate — `unique()` does.
    dup_ids = df.group_by("trade_id").len().filter(pl.col("len") > 1)["trade_id"].sort().to_list()

    first = df.unique(subset=["trade_id"], keep="first").sort("trade_id")
    uids = first["trade_id"].to_list()
    tss = first["ts"].to_list()

    gaps = []
    for i, (a, b) in enumerate(zip(uids, uids[1:], strict=False)):
        if b > a + 1:
            ts_lo, ts_hi = tss[i], tss[i + 1]
            # `ts` non-monotone in `trade_id` (the reconnect-overwrite signature of T0026, resolved)
            # would otherwise hand REST an inverted `since`/`until` window that silently yields nothing.
            if ts_lo > ts_hi:
                logger.warning(
                    "trades.gaps: non-monotone ts across gap after_id=%d before_id=%d (ts_lo=%s > ts_hi=%s);"
                    " normalizing fetch window",
                    a,
                    b,
                    ts_lo,
                    ts_hi,
                )
                ts_lo, ts_hi = ts_hi, ts_lo
            gaps.append(IdGap(after_id=a, before_id=b, ts_lo=ts_lo, ts_hi=ts_hi))
    # The span is the observed ids' own range: neither endpoint is ever a gap — capture-start and the live edge, not holes.
    span = uids[-1] - uids[0] + 1
    missing = span - len(uids)
    return Detection(gaps, dup_ids, len(ids), len(uids), span, missing)
