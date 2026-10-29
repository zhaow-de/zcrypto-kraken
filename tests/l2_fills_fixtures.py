"""`write_l2_fills_set`: an l2-fills set written through the producer's own `write_day` and `write_fills_manifest`, so the
reading's tests read a tree the code under test did not write -- the twelve pairs over two days, their posts at every
quarter-hour boundary, each pair's fills and 15m moves planted apart."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from cli.alpha.c1 import PAIRS
from cli.panel.fills import (
    CANCEL_AFTER_S,
    GRID_S,
    HORIZON_S,
    MID_OFFSETS_S,
    SIZE_RUNGS,
    STALE_S,
    _new_entry,
    rows_frame,
    write_day,
    write_fills_manifest,
)
from cli.panel.primitives import notionals_for

DAYS = (date(2026, 8, 31), date(2026, 9, 1))
STEP = timedelta(minutes=15)
BARS_PER_DAY = 96
POSTS_PER_HOUR = 960
EMPTY_PRIMARY = "capture-empty"
WRITTEN_AT = "2026-10-28T00:00:00+00:00"
CODE_REF = "l2-fills-fixture"

# The mid's 15m log return is EPSILON either way between the planted moves, so the trailing 96-bar scale, warm from the
# second day's first bar, sits just above EPSILON and no unplanted bar signals. The medium moves, MEDIUM scales of
# EPSILON, all come before the big ones, so each lies past 1 sigma and short of 2; each big move lies past 2.
EPSILON = 1e-4
MEDIUM, BIG = 1.8, 10.0
DOWN_MEDIUM = tuple(100 + 4 * j for j in range(12))
UP_MEDIUM = (102, 106, 110, 114, 118)
DOWN_BIG = (150, 156, 162)
UP_BIG = (153, 159)
HALF_SPREAD = 1e-4
FILL_S = {("bid", 0): 30.0, ("bid", 1): 200.0, ("ask", 0): 600.0, ("ask", 1): 200.0}
QUEUE_NOTIONAL = {("bid", 0): 1000.0, ("bid", 1): 2000.0, ("ask", 0): 1500.0, ("ask", 1): 2500.0}
SECOND_DAY_QUEUE = 100.0
UNANCHORED_HOURS, ABSENT_HOURS, TRADES_ABSENT_HOURS = (5,), (6, 7), (1, 2, 3)


def skipped_no_quote(k: int) -> int:
    return 400 + 4 * k


def _fills(k: int, side: str, size: int) -> tuple[int, ...]:
    return {
        ("bid", 0): DOWN_MEDIUM[:k],
        ("bid", 1): DOWN_BIG,
        ("ask", 0): UP_MEDIUM,
        ("ask", 1): UP_BIG,
    }[side, size]


def _mids(k: int, bars: int) -> list[float]:
    planted = {i: -MEDIUM for i in DOWN_MEDIUM} | {i: MEDIUM for i in UP_MEDIUM}
    planted |= {i: -BIG for i in DOWN_BIG} | {i: BIG for i in UP_BIG}
    mids = [100.0 + k]
    for i in range(1, bars):
        mids.append(mids[-1] * math.exp(EPSILON * planted.get(i, 1.0 if i % 2 else -1.0)))
    return mids


def _rows(pair: str, k: int, start: datetime, bars: int, skip_hours: set[int]) -> list[dict]:
    mids = _mids(k, bars)
    notionals = notionals_for(pair.split("/")[1])
    rows = []
    for i in range(bars):
        ts = start + i * STEP
        if i < BARS_PER_DAY and ts.hour in skip_hours:
            continue
        mid = mids[i]
        for side in ("bid", "ask"):
            price = mid * (1 - HALF_SPREAD) if side == "bid" else mid * (1 + HALF_SPREAD)
            for size in SIZE_RUNGS:
                filled = i in _fills(k, side, size)
                notional = QUEUE_NOTIONAL[side, size] + (SECOND_DAY_QUEUE if i >= BARS_PER_DAY else 0.0)
                rows.append(
                    {
                        "ts": ts,
                        "pair": pair,
                        "side": side,
                        "size": size,
                        "mid_at_post": mid,
                        "spread_at_post_bps": 2 * HALF_SPREAD * 1e4,
                        "stale_seconds_at_post": None if i % BARS_PER_DAY == 0 else 1.0,
                        "queue_ahead_qty": notional / price,
                        "queue_ahead_notional": notional,
                        "our_qty": notionals[size] / price,
                        "filled": filled,
                        "time_to_fill_s": FILL_S[side, size] if filled else None,
                        "cancelled_s": None if filled else float(HORIZON_S),
                        "fill_price": price if filled else None,
                        "mid_at_fill_plus_60s": mid if filled else None,
                        "mid_at_fill_plus_900s": mids[i + 1] if filled and i + 1 < bars else None,
                        "mid_at_post_plus_900s": mids[i + 1] if i + 1 < bars else None,
                        "mid_at_post_plus_3600s": mids[i + 4] if i + 4 < bars else None,
                    }
                )
    return rows


def write_l2_fills_set(root: Path, dataset: str, *, gaps: bool = False, days: tuple[date, ...] = DAYS) -> datetime:
    """`days` consecutive; returns the first post's stamp, the first day's midnight."""
    start = datetime(days[0].year, days[0].month, days[0].day, tzinfo=UTC)
    since, until = start, start + timedelta(days=len(days))
    params = {
        "grid_s": GRID_S,
        "horizon_s": HORIZON_S,
        "cancel_after_s": CANCEL_AFTER_S,
        "stale_s": STALE_S,
        "size_rungs": list(SIZE_RUNGS),
        "mid_offsets_s": list(MID_OFFSETS_S),
        "depth": 100,
        "since": since.isoformat(),
        "until": until.isoformat(),
    }
    out_root = root / dataset
    for k, pair in enumerate(PAIRS, start=1):
        gapped = gaps and k == 1
        rows = _rows(pair, k, start, BARS_PER_DAY * len(days), set(UNANCHORED_HOURS + ABSENT_HOURS) if gapped else set())
        for d, day in enumerate(days):
            frame = rows_frame([row for row in rows if row["ts"].date() == day])
            entry = _new_entry()
            if gapped and d == 0:
                for name, hours in (
                    ("hours_unanchored", UNANCHORED_HOURS),
                    ("hours_absent", ABSENT_HOURS),
                    ("trades_absent", TRADES_ABSENT_HOURS),
                ):
                    entry[name] = [(start + timedelta(hours=h)).isoformat() for h in hours]
            entry["hours"] = 24 - len(entry["hours_unanchored"]) - len(entry["hours_absent"])
            entry["posts"] = frame.height
            entry["skipped_no_quote"] = skipped_no_quote(k)
            entry["skipped_stale"] = POSTS_PER_HOUR * entry["hours"] - frame.height - skipped_no_quote(k)
            write_day(out_root, pair, day, frame, entry, params=params, code_ref=CODE_REF)
    (root / EMPTY_PRIMARY).mkdir(parents=True, exist_ok=True)
    write_fills_manifest(out_root, root / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    return start
