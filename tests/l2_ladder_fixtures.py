"""`write_l2_ladder_set`: an l2-ladder set written through the producer's own `write_day` and `write_ladder_manifest`, so
the reading's tests read a tree the code under test did not write -- the twelve pairs' six episodes a day, each pair's
prices, box-end touches and absent trades hours planted apart by its place k in `PAIRS`, from 1."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from cli.alpha.c1 import PAIRS
from cli.panel.fills import _ORDERS_PER_POST, SIZE_RUNGS, _midnight, _new_entry
from cli.panel.ladder import BOUNDARY_HOURS, LADDER_PARAMS, POST_OFFSET_S, rows_frame, write_day, write_ladder_manifest
from cli.panel.primitives import notionals_for
from tests.l2_fills_fixtures import DAYS, EMPTY_PRIMARY, WRITTEN_AT

CODE_REF = "l2-ladder-fixture"
# Pair k's orders post DELTA / k inside the mid and its box ends' opposite touches stand k * DELTA_PRIME outside it, so a
# maker fill costs the maker fee less DELTA / k and a fallback the taker fee plus k * DELTA_PRIME.
DELTA = 2e-4
DELTA_PRIME = 1e-4
# The episodes, by place in their day, whose order fills -- each side and size filled in some and falling back in the rest.
FILLED = {("bid", 0): (0, 1, 2, 3), ("bid", 1): (1, 3, 5), ("ask", 0): (0, 4), ("ask", 1): (2,)}
FILL_S = {("bid", 0): 30.0, ("bid", 1): 200.0, ("ask", 0): 600.0, ("ask", 1): 450.0}
QUEUE_NOTIONAL = {("bid", 0): 1000.0, ("bid", 1): 2000.0, ("ask", 0): 1500.0, ("ask", 1): 2500.0}
STALE_PAIR = PAIRS[0]  # its last day entered with every episode skipped stale and no row


def _rows(pair: str, k: int, boundaries: list[datetime]) -> list[dict]:
    notionals = notionals_for(pair.split("/")[1])
    # Halfway between the quote's two rungs, so the €1,000 order is larger than its box end's touch and the €100 one is not.
    touch_notional = (notionals[0] + notionals[1]) / 2
    rows = []
    for i, boundary in enumerate(boundaries):
        mid = (100.0 + k) * (1 + 1e-3 * i)
        for side, sign in (("bid", 1), ("ask", -1)):
            price = mid * (1 - sign * DELTA / k)
            touch = mid * (1 + sign * k * DELTA_PRIME)
            for size in SIZE_RUNGS:
                filled = i % len(BOUNDARY_HOURS) in FILLED[side, size]
                our_qty = notionals[size] / price
                rows.append(
                    {
                        "ts": boundary + timedelta(seconds=POST_OFFSET_S),
                        "pair": pair,
                        "side": side,
                        "size": size,
                        "price": price,
                        "our_qty": our_qty,
                        "queue_ahead_qty": QUEUE_NOTIONAL[side, size] / price,
                        "mid_at_post": mid,
                        "spread_at_post_bps": 2 * DELTA / k * 1e4,
                        "filled": filled,
                        "time_to_fill_s": FILL_S[side, size] if filled else None,
                        "fill_price": price if filled else None,
                        "box_end_mid": mid,
                        "box_end_touch_price": touch,
                        "box_end_touch_qty": touch_notional / touch,
                        "met_qty": our_qty if filled else 0.0,
                    }
                )
    return rows


def write_l2_ladder_set(root: Path, dataset: str, *, days: tuple[date, ...] = DAYS) -> datetime:
    """`days` consecutive; returns the first day's midnight."""
    start = _midnight(days[0])
    params = {**LADDER_PARAMS, "depth": 100, "since": start.isoformat(), "until": (start + timedelta(days=len(days))).isoformat()}
    out_root = root / dataset
    for k, pair in enumerate(PAIRS, start=1):
        boundaries = [_midnight(day) + timedelta(hours=hour) for day in days for hour in BOUNDARY_HOURS]
        trades_absent = {boundary.isoformat() for boundary in boundaries[:k]}
        rows = _rows(pair, k, boundaries)
        for day in days:
            stale = pair == STALE_PAIR and day == days[-1]
            day_boundaries = [boundary for boundary in boundaries if boundary.date() == day]
            frame = rows_frame([] if stale else [row for row in rows if row["ts"].date() == day])
            entry = _new_entry()
            entry["hours"] = len(day_boundaries)
            entry["posts"] = frame.height
            entry["skipped_stale"] = _ORDERS_PER_POST * len(day_boundaries) - frame.height
            entry["trades_absent"] = [boundary.isoformat() for boundary in day_boundaries if boundary.isoformat() in trades_absent]
            write_day(out_root, pair, day, frame, entry, params=params, code_ref=CODE_REF)
    (root / EMPTY_PRIMARY).mkdir(parents=True, exist_ok=True)
    write_ladder_manifest(out_root, root / EMPTY_PRIMARY, None, written_at=WRITTEN_AT)
    return start
