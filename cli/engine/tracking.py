"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure. Reads a journal already on disk -- and the venue ledger the owner exports by hand -- and
returns numbers; writes nothing, reaches no venue and needs no API key. The
refusals are the point -- a tracking number nobody can stand behind is worse than none, because it
will be read as a gate input.
"""

from __future__ import annotations

import csv
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.feeders import CycleStages, _median, _p95, _weekly_drift, accumulation_payload
from cli.engine.instruments import EUR_CODES
from cli.engine.store import BASKET
from cli.logging import get_logger
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

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
        # Each cycle is scored under the NAV that was LIVE for it (T0150): a `shadow_nav_eur`
        # change must not re-price a week that closed under the old value. The caller's scalar is
        # the fallback for records written before the key existed, which reproduces the previous
        # behaviour exactly for them -- so a week straddling the widening scores each half right.
        cycle_nav = nav if s.nav is None else s.nav
        if not math.isfinite(cycle_nav) or cycle_nav <= 0:
            raise EngineError(
                f"NAV must be finite and positive, got {cycle_nav!r} for cycle {s.cycle_ts.isoformat()} "
                "-- a negative one signs every drift_bps"
            )
        bps = drift_bps(s.final, s.closes, held, cycle_nav)
        rows.append({"cycle_ts": s.cycle_ts.isoformat(), "drift_bps": bps, "drift_eur": bps / 10_000 * cycle_nav})
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

    `rung_by_week` FAILS CLOSED: eligibility requires an explicit rung 3, so a caller that supplies
    nothing decides nothing. The measurement half is untouched either way -- every week still
    carries its floor p95 and its realized mean -- because withholding the verdict is the safe
    direction while withholding the numbers is merely unhelpful.
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
        # `rung == 3`, never `rung != 2`: an absent rung must read INELIGIBLE. The inverted
        # form reads a window nobody has classified as fully gate-eligible, which is a false
        # `pass` on a live-trading gate and never a false `fail`.
        gate_eligible = complete and rung == 3 and not straddles
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


def cost_blend(fills: list[Fill]) -> dict:
    """The realized maker/taker blend and the fee-per-side it implies.

    Weighted by NOTIONAL, never by fill count: one large taker fill beside nine tiny maker ones
    is a taker-heavy book, and a count-weighted blend would under-price the cost the whole
    portfolio is evaluated against.

    Unpriced fills are COUNTED but not PRICED -- leaving their notional in the denominator while
    dropping their fee from the numerator would silently deflate the rate. With nothing priced the
    answer is None: a proposal of 0.0 reads as "trading is free" to whoever ratifies it.

    Prices the FEE term only. `spread_per_side` is a separate, deliberately-kept term: the builder
    seam is fed their SUM (`cost_per_side`), so proposing a fee-only rate against that sum would
    silently delete the spread.
    """
    cfg = CrossfreqSystemConfig()
    # A repair has no price by construction, so it is neither priced nor notional -- multiplying
    # by its None px would raise, and counting it at zero would deflate the blend.
    priced = [f for f in fills if f.fee is not None and f.px is not None]
    notional: dict[str, float] = {}
    for f in fills:
        if f.px is None:
            continue
        # `.get`, not a fixed two-key dict: NO_LIQUIDITY_SIDE is a legal value the venue yields, and
        # a fixed dict would KeyError on it.
        notional[f.liquidity] = notional.get(f.liquidity, 0.0) + abs(f.qty) * f.px
    maker, taker = notional.get("MAKER", 0.0), notional.get("TAKER", 0.0)
    gross = maker + taker
    priced_notional = sum(abs(f.qty) * f.px for f in priced)  # every `priced` fill has a px
    per_fill = sorted(f.fee / (abs(f.qty) * f.px) for f in priced if f.qty and f.px)
    # The numerator carries the same `if f.qty and f.px` filter as `per_fill`: a fee with no
    # notional behind it inflates the headline rate while the dispersion already drops it, so one
    # payload would contradict itself.
    realized = (sum(f.fee for f in priced if f.qty and f.px) / priced_notional) if priced_notional > 0 else None
    # Three branches, not two. "No euro-denominated fills" is false of a window whose priced fills
    # simply carry no notional, and `basis` is a payload key read straight out of `--json`, so the
    # sentence has to be true here rather than at whatever renders it.
    if not priced:
        basis = "no euro-denominated fills in the window -- no rate proposed"
    elif realized is None:
        basis = f"{len(priced)} euro-denominated fill(s) carry no notional -- no rate proposed"
    else:
        basis = f"{len(priced)} euro-denominated fill(s) over {priced_notional:,.2f} EUR of notional"
    return {
        "n_fills": len(fills),
        "n_priced": len(priced),
        "maker_share": (maker / gross) if gross > 0 else None,
        "taker_share": (taker / gross) if gross > 0 else None,
        "realized_fee_per_side": realized,
        # min/median/max, never a standard deviation: a handful of probe-scale fills cannot support
        # a parametric dispersion, and quoting one would dress up a sample of tens.
        "per_fill_min": per_fill[0] if per_fill else None,
        "per_fill_median": _median(per_fill) if per_fill else None,
        "per_fill_max": per_fill[-1] if per_fill else None,
        "current_fee_per_side": cfg.fee_per_side,
        "current_spread_per_side": cfg.spread_per_side,
        "proposed_fee_per_side": realized,
        "basis": basis,
    }


class LedgerRow(NamedTuple):
    txid: str
    refid: str  # the venue trade id a `trade` row belongs to -- what `Fill.trade_id` carries
    at: datetime
    type: str
    asset: str
    amount: float
    fee: float


# The columns this reader USES, not the whole documented header (`txid,refid,time,type,subtype,
# aclass,asset,amount,fee,balance`): a venue that ADDS a column must not break the read, while one
# that drops a column the arithmetic depends on must.
_LEDGER_COLUMNS = ("txid", "refid", "time", "type", "asset", "amount", "fee")
# Row types with no fill behind them BY CONSTRUCTION -- an allowlist, so anything outside it is
# reported rather than passed over. Failing the reconciliation on a deposit would make every real
# export FAILED at once and the signal worthless; assuming the same of an unknown type would hide it.
_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer"})


def read_ledger_export(path: Path) -> list[LedgerRow]:
    """The owner's hand-exported Kraken ledger CSV, read by HEADER NAME rather than by position.

    Header-driven and REFUSING, never defaulting: the export's format is an assumption until a real
    one has been read, and a missing column silently defaulted parses into plausible nonsense --
    a rollover total that is confidently zero reads exactly like a window with no rollovers.

    The export writes no offset, and the venue stamps it UTC; a naive datetime here would raise the
    first time anything compared it against the journal's aware boundaries.

    `utf-8-sig`, never plain `utf-8`: an Excel "CSV UTF-8" round-trip prefixes a BOM, and the
    runbook has the owner opening this very file by hand. Decoded as plain utf-8 the BOM glues
    itself to the first column name, and the refusal then reads "has no txid column -- its header
    reads txid", telling the operator the column both is and is not there. Plain utf-8 input decodes
    identically under `utf-8-sig`, so nothing else changes.

    Every decode and parse sits inside ONE catch, the header read included: the caller catches this
    module's error and OSError, so anything else -- a `UnicodeDecodeError` out of the very first
    read, a NUL byte out of the csv module -- reaches the operator as a traceback instead of as the
    one-line refusal every other bad export gets.
    """
    row_no = 0  # 0 while the header is being read; the first data row is 1
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            missing = [column for column in _LEDGER_COLUMNS if column not in header]
            if missing:
                raise EngineError(
                    f"the ledger export {path} has no {', '.join(missing)} column -- its header reads "
                    f"{', '.join(header) or '(empty)'}. Refusing rather than defaulting: this reader's "
                    "arithmetic is keyed on those names, and a defaulted column parses into a plausible number"
                )
            rows: list[LedgerRow] = []
            # A row ordinal, not a physical line number: a quoted field may carry a newline, after
            # which the two drift and a line number sends the operator to the wrong place.
            for row_no, raw in enumerate(reader, start=1):
                at = datetime.fromisoformat(raw["time"])
                rows.append(
                    LedgerRow(
                        raw["txid"],
                        raw["refid"],
                        at if at.tzinfo is not None else at.replace(tzinfo=UTC),
                        raw["type"],
                        raw["asset"],
                        float(raw["amount"]),
                        float(raw["fee"]),
                    )
                )
    except (TypeError, ValueError, csv.Error) as exc:
        where = "its header" if row_no == 0 else f"data row {row_no}, or just after it"
        raise EngineError(f"the ledger export {path} is unreadable at {where}: {exc}") from exc
    return rows


def reconcile_ledger(rows: list[LedgerRow], fills: list[Fill]) -> dict:
    """The venue's own ledger against the engine's journal: the rollover cost, and what went unmatched.

    Rollover is why this exists. The venue charges it against the POSITION rather than against a
    fill, so it appears in no execution record at all and a cost basis built from fills alone omits
    it entirely.

    Only rows whose `asset` is a euro are summed into a euro total -- `EUR_CODES`, because the venue
    spells the euro two ways and a hand-written `== "EUR"` drops every ZEUR row silently.

    An unmatched `trade` row FAILS the reconciliation: it is account activity the engine's record
    does not know about, which is the one thing this comparison exists to detect, so every such id
    is NAMED rather than counted. Failing the reconciliation is not failing the run -- the caller
    still prints the drift half, because denying the operator the numbers they need to investigate
    with is the wrong proportion.

    `matched` counts ROWS, not fills: one venue trade writes one ledger row per asset leg, so a
    single fill legitimately matches two.

    A row this reader places NOWHERE is counted by type in `ignored` rather than passed over. Only
    `trade` rows are matched today, and `margin` -- which a margin position writes carrying the SAME
    refid as its trade -- is exactly the type the first real export will be full of, because the
    first activity this reader is aimed at is a margin probe. Consuming it would guess semantics
    nobody has verified; accepting it silently would hide a whole class of row precisely where the
    reader is first used. So the count is surfaced and the operator decides whether the match widens.

    `n_rows` is every row read. Without it "read 0 rows" and "read 400 rows, none of them trades"
    are the same clean bill -- the confidently-zero failure this reader's refusals exist to prevent,
    moved from a missing column to a missing body.
    """
    journaled = {f.trade_id for f in fills}
    matched = 0
    unmatched: list[str] = []
    ignored: dict[str, int] = {}
    rollover_fees_eur = 0.0
    for row in rows:
        if row.type == "rollover":
            if row.asset in EUR_CODES:
                rollover_fees_eur += row.fee
        elif row.type == "trade":
            if row.refid in journaled:
                matched += 1
            elif row.refid not in unmatched:
                unmatched.append(row.refid)
        elif row.type not in _NO_FILL_LEDGER_TYPES:
            ignored[row.type] = ignored.get(row.type, 0) + 1
    return {
        "status": "FAILED" if unmatched else "ok",
        "n_rows": len(rows),
        "matched": matched,
        "rollover_fees_eur": rollover_fees_eur,
        "unmatched": unmatched,
        "ignored": ignored,
    }
