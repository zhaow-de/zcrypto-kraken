"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure. Reads a journal already on disk and returns numbers; writes nothing, reaches no venue. The
refusals are the point -- a tracking number nobody can stand behind is worse than none, because it
will be read as a gate input.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.feeders import CycleStages, _median, _p95, _weekly_drift, accumulation_payload
from cli.engine.instruments import EUR_CODES
from cli.engine.store import BASKET
from cli.logging import get_logger

logger = get_logger("engine.tracking")

# The venue's own names, as `executor._liquidity` writes them. NOT lowercased: matching a casing
# the ledger never writes would abort every real fill while every fixture passed.
_PRICEABLE_LIQUIDITY = frozenset({"MAKER", "TAKER"})
_VENUE_LIQUIDITY = _PRICEABLE_LIQUIDITY | {"NO_LIQUIDITY_SIDE"}
_SIDES = frozenset({"buy", "sell"})
# The MODEL's universe is the ten EUR legs (cycle._MODEL_SYMBOLS). The two /BTC legs are real
# basket symbols with no model target, so they map to base None: excluded from drift, counted.
_BASE_BY_SYMBOL = {s: (s.split("/")[0] if s.endswith("/EUR") else None) for s in BASKET}
# Weeks that must be decided before the comparison carries a verdict at all.
_GATE_MIN_WEEKS = 3


class Fill(NamedTuple):
    boundary: datetime  # the cycle whose decision produced it -- NOT the wall clock
    at: datetime
    base: str | None  # None for the /BTC legs, which carry no model target
    side: str
    qty: float
    px: float | None  # None for a venue repair, which has no price by construction
    fee: float | None  # None when not euro-denominated or the side is unpriceable
    liquidity: str
    trade_id: str


def extract_fills(records: list[dict]) -> tuple[list[Fill], list[str]]:
    """Every journaled fill, in ledger order, plus the notes that disabled part of the report."""
    out: list[Fill] = []
    notes: list[str] = []

    def note(text: str) -> None:
        if text not in notes:
            notes.append(text)
            logger.warning("%s", text)

    for rec in records:
        boundary = datetime.fromisoformat(rec["cycle_ts"])
        for row in rec.get("submitted", []):
            intent = row.get("intent") or {}
            symbol = intent.get("symbol")
            if symbol not in _BASE_BY_SYMBOL:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} names symbol {symbol!r}, "
                    "which is not in the basket -- refusing to attribute its fills"
                )
            side = intent.get("side")
            if side not in _SIDES:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} carries side {side!r}, not one "
                    f"of {sorted(_SIDES)} -- an unsigned quantity would book a sell as a buy"
                )
            base = _BASE_BY_SYMBOL[symbol]
            if base is None:
                note(f"{symbol} has no model target and is excluded from the drift half")
            for ev in row.get("events", []):
                kind = ev.get("event")
                if kind == "reconciled":
                    # An adopted order that filled at the venue while this process was down.
                    # `_reconcile_adopted_rows` credits the delta to the row's `filled_qty`, and it
                    # is the ONLY non-fill event that moves it (every other journaled event is a
                    # `{"type": ...}` payload written with `add_filled_qty=0.0`), so skipping it
                    # would make `held` under-report by exactly the repaired amount after every
                    # adopted-order repair.
                    #
                    # It becomes a Fill rather than a note, because `held` is base units only: the
                    # quantity is the whole of what the drift half needs, and a note announcing that
                    # the number is wrong is worse than the right number. No price and no fee exist
                    # by construction, so `px`/`fee` are None and it stays out of the cost blend --
                    # which is the same judgment the executor makes when it keeps a repair off the
                    # fill/fee counters.
                    #
                    # The row's own side signs it, exactly like a fill: `filled_qty` is a magnitude,
                    # so a positive delta means more filled in the ORDER's direction.
                    qty = float(ev["qty"])
                    client_order_id = row.get("client_order_id")
                    note(
                        f"{symbol} carries a venue repair of {qty:.10g} base units on "
                        f"{client_order_id} -- counted in the drift half, with no price"
                    )
                    out.append(
                        Fill(
                            boundary,
                            datetime.fromisoformat(ev["at"]),
                            base,
                            side,
                            qty,
                            None,
                            None,
                            "NO_LIQUIDITY_SIDE",
                            # A repair carries no venue trade id. This one is unique (a row is
                            # reconciled at most once per timestamp) and unmistakable for a venue
                            # id, which matters because the ledger match is keyed on `trade_id`.
                            f"reconciled:{client_order_id}:{ev['at']}",
                        )
                    )
                    continue
                if kind != "fill":
                    continue
                liq = ev.get("liquidity")
                if liq not in _VENUE_LIQUIDITY:
                    raise EngineError(
                        f"fill on {row.get('client_order_id')!r} carries liquidity={liq!r}, which "
                        "is not a name the venue's enum yields -- refusing to blend an unlabelled side"
                    )
                cur = ev.get("fee_currency")
                fee: float | None = float(ev["fee"])
                if cur not in EUR_CODES:
                    fee = None
                    note(f"fee on {symbol} is denominated in {cur}, not euro -- excluded from the cost blend")
                if liq not in _PRICEABLE_LIQUIDITY:
                    fee = None
                    note(f"a fill on {symbol} carries {liq} -- counted, but excluded from the cost blend")
                out.append(
                    Fill(
                        boundary,
                        datetime.fromisoformat(ev["at"]),
                        base,
                        side,
                        float(ev["qty"]),
                        float(ev["px"]),
                        fee,
                        liq,
                        str(ev["trade_id"]),
                    )
                )
    return out, notes


def _iso_key(dt: datetime) -> tuple[int, int]:
    iso = dt.isocalendar()
    return (iso.year, iso.week)


def _iso_label(key: tuple[int, int]) -> str:
    return f"{key[0]}-W{key[1]:02d}"


def drift_bps(final: dict[str, float], closes: dict[str, float], held: dict[str, float], nav: float) -> float:
    """One cycle's drift, in bps of NAV, from plain dicts.

    THE shared core: component A calls it from replayed stages, component C from journaled
    artifacts. No CycleStages, no venue minimums, no accumulation_payload -- component C runs on
    the engine host, which carries no refdata snapshot, so anything needing `load_minimums` cannot
    run there at all. One implementation, two callers: the number a human bands and the number the
    engine trips on cannot drift apart.
    """
    drift_eur = 0.0
    for a, weight in final.items():
        close = closes[a]
        drift_eur += abs((weight * nav) / close - held.get(a, 0.0)) * close
    return drift_eur / nav * 10_000


def realized_drift(stages: list[CycleStages], fills: list[Fill], nav: float) -> dict:
    """Per-cycle drift with `held` taken from REAL fills instead of the modelled policy.

    `held` is SIGNED BASE UNITS: a sell that booked as a buy would double the apparent position
    and silently halve the measured drift. Fills are applied by the BOUNDARY their row was
    journaled under, so a fill arriving minutes after boundary N counts at N -- the decision that
    produced it -- rather than at N+1.
    """
    if not math.isfinite(nav) or nav <= 0:
        raise EngineError(f"NAV must be finite and positive, got {nav!r} -- a negative one signs every drift_bps")
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    by_boundary: dict[datetime, list[Fill]] = {}
    for f in fills:
        if f.base is None:  # a /BTC leg: no model target, so no drift contribution
            continue
        by_boundary.setdefault(f.boundary, []).append(f)
    # A fill whose boundary carries no stage never enters `held`, overstating drift for every later
    # cycle -- silently, and on component C that is a spurious kill-file trip. The two ways it
    # happens need different answers from the operator, so they are refused separately:
    #   * INSIDE the cycle span -- a hole. `accumulation_report` drops a record whose
    #     `replay_stages` raises, names it in `failures` and counts it in `n_failed`; a fill
    #     journaled under that boundary lands here. Widening the window cannot help.
    #   * OUTSIDE it -- a truncated window. A fill BEFORE the first cycle holds a position the
    #     first cycle already carries, so it is refused rather than dropped; one after the last
    #     cycle is harmless, but telling them apart needs a span the caller chose, not one this
    #     function guesses. Widening the window is the fix.
    # Compared as datetime INSTANTS, never as isoformat strings: `+02:00` and `+00:00` spellings of
    # one instant are equal to `by_boundary`'s lookup and unequal as text, so a string difference
    # would refuse a fill the loop below goes on to apply.
    orphans = sorted(set(by_boundary) - {s.cycle_ts for s in ordered})
    if orphans:
        span = (ordered[0].cycle_ts, ordered[-1].cycle_ts) if ordered else None
        inside = [b for b in orphans if span is not None and span[0] <= b <= span[1]]
        if inside:
            raise EngineError(
                f"{len(inside)} fill boundary(ies) fall INSIDE the cycle span but match no cycle "
                f"({[b.isoformat() for b in inside[:3]]}) -- a hole, not a truncation: a cycle whose "
                "replay failed was dropped, and widening the window cannot recover its position"
            )
        raise EngineError(
            f"{len(orphans)} fill boundary(ies) fall OUTSIDE the cycle span "
            f"({[b.isoformat() for b in orphans[:3]]}) -- a truncated window: widen it rather than "
            "report a drift that omits their position"
        )
    held: dict[str, float] = {}
    rows: list[dict] = []
    for s in ordered:
        for f in by_boundary.get(s.cycle_ts, []):
            held[f.base] = held.get(f.base, 0.0) + (f.qty if f.side == "buy" else -f.qty)
        bps = drift_bps(s.final, s.closes, held, nav)
        rows.append({"cycle_ts": s.cycle_ts.isoformat(), "drift_bps": bps, "drift_eur": bps / 10_000 * nav})
    values = [r["drift_bps"] for r in rows]
    # NaN on an empty window, never None: `_median`/`_p95` already answer that way, and
    # `feeders._bps` -- the renderer this feeds -- branches on `math.isnan` and raises TypeError on
    # None. One convention for "nothing to average" across both halves of the report.
    return {
        "cycles": rows,
        "median_drift_bps": _median(values),
        "p95_drift_bps": _p95(values),
        "n_fills": len(fills),
    }


def weekly_tracking(
    stages: list[CycleStages],
    fills: list[Fill],
    minimums: dict[str, tuple[float, float]],
    nav: float,
    *,
    rung_by_week: dict[str, int] | None = None,
) -> dict:
    """That week's floor p95 against that week's realized MEAN drift.

    The edge is ratified, not chosen here: on the data the band was derived from a median edge
    fails two of four weeks while a p95 edge passes all four.

    "No data" means the realized series NEVER STARTED -- not that a week was quiet. A week with
    no fills but a non-zero `held` is fully measured, and is precisely the week a tracking-error
    trip exists to catch.
    """
    rung_by_week = rung_by_week or {}
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    floor = accumulation_payload(ordered, minimums, [nav])["by_nav"][nav]
    real = realized_drift(ordered, fills, nav)
    floor_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, floor["cycles"])}
    real_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, real["cycles"])}
    floor_cycles: dict[tuple[int, int], list[float]] = {}
    for stage, row in zip(ordered, floor["cycles"], strict=True):
        floor_cycles.setdefault(_iso_key(stage.cycle_ts), []).append(row["drift_bps"])
    first_fill = min((f.boundary for f in fills if f.base is not None), default=None)

    weeks: list[dict] = []
    for key, fw in sorted(floor_weeks.items()):
        label = _iso_label(key)
        complete = not fw["partial"]
        rung = rung_by_week.get(label)
        week_cycles = [s.cycle_ts for s in ordered if _iso_key(s.cycle_ts) == key]
        # Started, not "had a fill this week".
        started = first_fill is not None and any(t >= first_fill for t in week_cycles)
        # A week holding cycles on BOTH sides of the first fill averages a cycle-level series over a
        # week-level flag: every pre-fill cycle contributes an undeployed book at the full 10000 bps,
        # so the FIRST week of live trading reads near half that and would be biased toward `fail`.
        # Ruled the same way a partial week is: the mean is not comparable to a settled week's, so
        # it is measured and reported, and excluded from the verdict.
        straddles = started and any(t < first_fill for t in week_cycles)
        gate_eligible = complete and rung != 2 and not straddles
        realized_mean = real_weeks[key]["mean_drift_bps"] if started else None
        floor_p95 = _p95(floor_cycles[key])
        weeks.append(
            {
                "iso_week": label,
                "cycles": fw["n_cycles"],
                "complete": complete,
                "rung": rung,
                "gate_eligible": gate_eligible,
                "floor_p95_bps": floor_p95,
                "realized_mean_bps": realized_mean,
                "within_band": (realized_mean <= floor_p95) if (gate_eligible and realized_mean is not None) else None,
            }
        )
    decided = [w for w in weeks if w["within_band"] is not None]
    verdict = (
        "insufficient-data" if len(decided) < _GATE_MIN_WEEKS else "pass" if all(w["within_band"] for w in decided) else "fail"
    )
    return {"weeks": weeks, "complete_gate_eligible_weeks": len(decided), "verdict": verdict}
