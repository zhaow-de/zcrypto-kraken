"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure -- it writes nothing and reaches no venue -- and it refuses rather than return a number nobody
can stand behind, because that number will be read as a gate input."""

from __future__ import annotations

import csv
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.execledger import credited_qty
from cli.engine.feeders import CycleStages, _median, _p95, _weekly_drift, accumulation_payload
from cli.engine.instruments import EUR_CODES
from cli.engine.store import BASKET
from cli.logging import get_logger
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

logger = get_logger("engine.tracking")

# The venue's own names, as `executor._liquidity` writes them -- NOT lowercased: a casing the
# venue never writes would abort every real fill.
_PRICEABLE_LIQUIDITY = frozenset({"MAKER", "TAKER"})
_VENUE_LIQUIDITY = _PRICEABLE_LIQUIDITY | {"NO_LIQUIDITY_SIDE"}
_SIDES = frozenset({"buy", "sell"})
# The model's targets are the /EUR legs (`cycle._MODEL_SYMBOLS`); a /BTC leg is a real basket
# symbol with none, so it maps to base None -- counted, but excluded from drift.
_BASE_BY_SYMBOL = {s: (s.split("/")[0] if s.endswith("/EUR") else None) for s in BASKET}
_GATE_MIN_WEEKS = 3
_H4 = timedelta(hours=4)
# The opening holdings record's shape: one row per basket base, the model's ten.
_OPENING_SCHEMA_VERSION = 1
_OPENING_KEYS = frozenset({"schema_version", "birth", "rows"})
_OPENING_ROW_KEYS = frozenset({"base", "codes", "balance", "close"})
_OPENING_BASES = tuple(sorted(base for base in _BASE_BY_SYMBOL.values() if base is not None))


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
    # What the fill moved its row's `filled_qty` by (`execledger.credited_qty`), where `qty` stays the blend's weight and
    # the venue's figure; None on a Fill built by hand, which moved its row by `qty`.
    credited: float | None = None


class OpeningHoldings(NamedTuple):
    """A tracking series' opening holdings: the instant the series was born, where the weekly report starts reading it,
    and per basket base the spot balance the account held then, in base units."""

    birth: datetime
    held: dict[str, float]


def _finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def parse_opening_holdings(doc: object) -> OpeningHoldings:
    """The record's birth and per-base balances, or EngineError naming the field it refuses -- never a value read from
    the record."""
    if not isinstance(doc, dict) or doc.get("schema_version") != _OPENING_SCHEMA_VERSION:
        raise EngineError(f"the opening holdings record's schema_version is not {_OPENING_SCHEMA_VERSION}")
    if frozenset(doc) != _OPENING_KEYS:
        raise EngineError(f"the opening holdings record's keys are not {', '.join(sorted(_OPENING_KEYS))}")
    rows = doc["rows"]
    tabular = isinstance(rows, list) and all(isinstance(row, dict) for row in rows)
    if not tabular or sorted(str(row.get("base")) for row in rows) != list(_OPENING_BASES):
        raise EngineError(f"the opening holdings record's rows are not one per basket base, {', '.join(_OPENING_BASES)}")
    by_base = {row["base"]: row for row in rows}
    held: dict[str, float] = {}
    for base in _OPENING_BASES:
        row = by_base[base]
        if frozenset(row) != _OPENING_ROW_KEYS:
            raise EngineError(f"the opening holdings row for {base} has keys other than {', '.join(sorted(_OPENING_ROW_KEYS))}")
        codes = row["codes"]
        if not isinstance(codes, list) or not all(isinstance(code, str) for code in codes):
            raise EngineError(f"the opening holdings row for {base} carries codes that are not a list of strings")
        if not _finite(row["balance"]) or row["balance"] < 0:
            raise EngineError(f"the opening holdings row for {base} carries a balance that is not a finite, non-negative number")
        if not _finite(row["close"]) or row["close"] <= 0:
            raise EngineError(f"the opening holdings row for {base} carries a close that is not a finite, positive number")
        held[base] = float(row["balance"])
    try:
        birth = datetime.fromisoformat(doc["birth"])
    except TypeError, ValueError:
        birth = None
    if birth is None or birth.utcoffset() is None or _off_the_4h_grid(birth.astimezone(UTC)):
        raise EngineError("the opening holdings record's birth is not an aware instant on a 4-hourly boundary")
    return OpeningHoldings(birth=birth.astimezone(UTC), held=held)


def _off_the_4h_grid(at: datetime) -> bool:
    return bool(at.hour % 4) or (at.minute, at.second, at.microsecond) != (0, 0, 0)


def read_opening_holdings(path: Path) -> OpeningHoldings:
    """`parse_opening_holdings` over the record at `path`. An absent record raises FileNotFoundError, so a caller tells
    a series no one has recorded from one whose record will not read, which raises EngineError."""
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise EngineError(f"the opening holdings record {path} could not be read: {type(exc).__name__}") from exc
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise EngineError(f"the opening holdings record {path} is not JSON") from exc
    return parse_opening_holdings(doc)


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
                    # An adopted order that filled at the venue while this process was down: the ONLY non-fill event
                    # that moves `filled_qty`. No price or fee exists by construction, and the row's own side signs it
                    # (`filled_qty` is a magnitude in the ORDER's direction).
                    qty = float(ev["qty"])
                    client_order_id = row.get("client_order_id")
                    note(f"{symbol} carries a venue repair of {qty:.10g} base units on {client_order_id} -- counted, with no price")
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
                            # A repair carries no venue trade id; this one is unique per row and
                            # timestamp, and unmistakable for the venue id the ledger match keys on.
                            f"reconciled:{client_order_id}:{ev['at']}",
                            credited=qty,
                        )
                    )
                    continue
                if kind != "fill":
                    # A `withdrawn` event -- the venue reporting a closed order filled for LESS than this row recorded --
                    # reverses nothing on purpose (spec 00100 D16); the kill switch it latched has already stopped the engine.
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
                        credited=credited_qty(ev),
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

    Plain dicts because the engine host carries no refdata snapshot for minimums; one implementation,
    so the number a human bands (`weekly_tracking`) and the number the engine trips on (`executor`) cannot drift apart."""
    drift_eur = 0.0
    for a, weight in final.items():
        close = closes[a]
        drift_eur += abs((weight * nav) / close - held.get(a, 0.0)) * close
    return drift_eur / nav * 10_000


def realized_drift(stages: list[CycleStages], nav: float, *, books: dict[datetime, dict[str, float] | None] | None = None) -> dict:
    """Per-cycle drift against the book the cycle's own trading left: the `held` journaled at the NEXT boundary, whose venue
    read the cycle's plan has ended before. That book is the stage's there, or `books`' for a boundary no stage holds --
    the one after the last stage, or one whose cycle could not be staged.

    A cycle whose next boundary journaled no book is not scored and is named under `unscored`: the writer journals none when
    the venue read failed, and no other position stands in for it."""
    if not math.isfinite(nav) or nav <= 0:
        raise EngineError(f"NAV must be finite and positive, got {nav!r} -- a negative one signs every drift_bps")
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    held_at = {**{s.cycle_ts: s.held for s in ordered}, **(books or {})}
    rows: list[dict] = []
    unscored: list[str] = []
    for s in ordered:
        after = s.cycle_ts + _H4
        held = held_at.get(after)
        if held is None:
            unscored.append(s.cycle_ts.isoformat())
            continue
        # A leg the book does not carry would read as flat, which is a real position.
        missing = sorted(set(s.final) - set(held))
        if missing:
            raise EngineError(f"the book journaled at {after.isoformat()} carries no {', '.join(missing)}")
        # Each cycle is scored under the NAV that was LIVE for it (T0150): a `shadow_nav_eur` change
        # must not re-price a closed week, and the caller's scalar is the fallback for older records.
        cycle_nav = nav if s.nav is None else s.nav
        if not math.isfinite(cycle_nav) or cycle_nav <= 0:
            raise EngineError(
                f"NAV must be finite and positive, got {cycle_nav!r} for cycle {s.cycle_ts.isoformat()} "
                "-- a negative one signs every drift_bps"
            )
        bps = drift_bps(s.final, s.closes, {a: held[a] for a in s.final}, cycle_nav)
        rows.append({"cycle_ts": s.cycle_ts.isoformat(), "drift_bps": bps, "drift_eur": bps / 10_000 * cycle_nav})
    values = [r["drift_bps"] for r in rows]
    # NaN on an empty window, never None: `_median`/`_p95` do the same, and the renderer `feeders._bps` raises TypeError on None.
    return {
        "cycles": rows,
        "unscored": unscored,
        "median_drift_bps": _median(values),
        "p95_drift_bps": _p95(values),
    }


def weekly_tracking(
    stages: list[CycleStages],
    fills: list[Fill],
    minimums: dict[str, tuple[float, float]],
    nav: float,
    *,
    rung_by_week: dict[str, int] | None = None,
    opening: OpeningHoldings | None = None,
    books: dict[datetime, dict[str, float] | None] | None = None,
) -> dict:
    """That week's floor p95 against that week's realized MEAN drift (`realized_drift`, `books` handed through). A week
    holding a cycle that drift is not scored for carries no realized mean, and names the first such cycle. With `opening`,
    the series starts at its birth: the stages and fills before it are a prior series' and are left out of both halves."""
    rung_by_week = rung_by_week or {}
    ordered = sorted(stages, key=lambda s: s.cycle_ts)
    if opening is not None:
        ordered = [s for s in ordered if s.cycle_ts >= opening.birth]
        fills = [f for f in fills if f.boundary >= opening.birth]
    # Deliberate asymmetry: the floor is present tense, measured at the caller's scalar NAV that `accumulation_payload` holds
    # constant by design -- one moving with NAV would fold return into a venue-minimum measurement -- while realized drift is
    # past tense and scored per journaled cycle, so do NOT thread per-cycle NAV into the floor. Across a `shadow_nav_eur` change
    # the two are quoted at different NAVs, so that week's `within_band` is advisory; `--simulated-fills` shares the seam.
    floor = accumulation_payload(ordered, minimums, [nav])["by_nav"][nav]
    real = realized_drift(ordered, nav, books=books)
    scored = {datetime.fromisoformat(row["cycle_ts"]): row["drift_bps"] for row in real["cycles"]}
    floor_weeks = {(w["iso_year"], w["iso_week"]): w for w in _weekly_drift(ordered, floor["cycles"])}
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
        # "Started" is the realized series having begun, not "had a fill this week": a week with no
        # fills but a non-zero `held` is fully measured, and is what a tracking-error trip catches.
        started = first_fill is not None and any(t >= first_fill for t in week_cycles)
        # A week holding cycles on BOTH sides of the first fill averages a cycle-level series over a
        # week-level flag -- every pre-fill cycle contributes a book not yet traded toward its targets,
        # biasing the first live week toward `fail` -- so it is measured and reported but excluded,
        # like a partial week.
        straddles = started and any(t < first_fill for t in week_cycles)
        # `rung == 3`, never `rung != 2`: an absent rung must read INELIGIBLE, and the inverted form
        # is a false `pass` on a live-trading gate. `rung_by_week` fails closed -- a caller that
        # supplies nothing decides nothing, while every week still carries its floor p95 and mean.
        gate_eligible = complete and rung == 3 and not straddles
        unscored = [t for t in week_cycles if t not in scored]
        realized_mean = sum(scored[t] for t in week_cycles) / len(week_cycles) if started and not unscored else None
        # p95, not a median: the edge was pinned by the T0116 amendment (spec 00091), not chosen here.
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
                "unscored_from": unscored[0].isoformat() if unscored else None,
            }
        )
    decided = [w for w in weeks if w["within_band"] is not None]
    verdict = (
        "insufficient-data" if len(decided) < _GATE_MIN_WEEKS else "pass" if all(w["within_band"] for w in decided) else "fail"
    )
    return {"weeks": weeks, "complete_gate_eligible_weeks": len(decided), "verdict": verdict}


def cost_blend(fills: list[Fill]) -> dict:
    """The realized maker/taker blend and the fee-per-side it implies.

    Weighted by NOTIONAL, never by fill count, which under-prices a book of one large taker fill among many small maker ones."""
    cfg = CrossfreqSystemConfig()
    # Counted but never priced: a fill with no price or no euro fee would deflate the blend at zero.
    priced = [f for f in fills if f.fee is not None and f.px is not None]
    notional: dict[str, float] = {}
    for f in fills:
        if f.px is None:
            continue
        # `.get`: NO_LIQUIDITY_SIDE is a legal venue value a fixed two-key dict would KeyError on.
        notional[f.liquidity] = notional.get(f.liquidity, 0.0) + abs(f.qty) * f.px
    maker, taker = notional.get("MAKER", 0.0), notional.get("TAKER", 0.0)
    gross = maker + taker
    priced_notional = sum(abs(f.qty) * f.px for f in priced)  # every `priced` fill has a px
    per_fill = sorted(f.fee / (abs(f.qty) * f.px) for f in priced if f.qty and f.px)
    # None, never 0.0, when nothing is priced: a 0.0 proposal reads as "trading is free". The
    # numerator carries `per_fill`'s `if f.qty and f.px` filter, or headline and dispersion disagree.
    realized = (sum(f.fee for f in priced if f.qty and f.px) / priced_notional) if priced_notional > 0 else None
    # Three branches: `basis` ships in `--json`, so it must not blame missing euro fills for missing notional.
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
        # min/median/max, never a standard deviation: probe-scale samples cannot support one.
        "per_fill_min": per_fill[0] if per_fill else None,
        "per_fill_median": _median(per_fill) if per_fill else None,
        "per_fill_max": per_fill[-1] if per_fill else None,
        "current_fee_per_side": cfg.fee_per_side,
        "current_spread_per_side": cfg.spread_per_side,
        # The FEE term only, for `fee_per_side` -- never for `cost_per_side`, the sum
        # the builder seam is fed, where a fee-only rate would delete the spread.
        "proposed_fee_per_side": realized,
        "basis": basis,
    }


class LedgerRow(NamedTuple):
    txid: str
    # The venue trade id a `trade` or `margin` row belongs to -- what `Fill.trade_id` carries; a
    # `rollover` or `collateralconversion` row carries its position's OPENING trade id instead.
    refid: str
    at: datetime
    type: str
    subtype: str
    asset: str
    amount: float
    fee: float


# The columns this reader USES, not the whole documented header: a venue that ADDS a column must
# not break the read, while one that drops a column the read depends on must.
_LEDGER_COLUMNS = ("txid", "refid", "time", "type", "subtype", "asset", "amount", "fee")
# The assets a fee is summed under as euro: the venue's two spellings, and EURC, which it charges a margin open's fee in
# after converting euro to it at par beside the row, the export's `collateralconversion` pair, so a EURC fee counts at par.
_EURO_FEE_ASSETS = frozenset(EUR_CODES) | {"EURC"}
# The row types a journaled fill is matched by: a spot fill writes `trade` rows and a margin open or close writes a
# `margin` row, each under the fill's own trade id and a margin fill with no `trade` row beside it.
_MATCHED_LEDGER_TYPES = frozenset({"trade", "margin"})
# Row types with no fill behind them BY CONSTRUCTION -- an allowlist, so an unknown type is reported rather than passed
# over, while failing on a deposit would fail every export. `settled` is a hand settle's delivery pair, which the journal
# holds no row for; `collateralconversion` is the venue's own currency swap for a margin fee, keyed to the position's
# opening trade; `staking` is a reward the venue credits on a spot holding, in the API's spelling.
_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer", "settled", "collateralconversion", "staking"})
# The same reward in the CSV export's spelling.
_EARN_REWARD = ("earn", "reward")
# The venue's small-balance conversion writes no trade: a `spend` row per coin and a `receive` row for the proceeds, each
# with this subtype.
_DUST_SWEEP_SUBTYPE = "dustsweeping"
_DUST_SWEEP_TYPES = frozenset({"spend", "receive"})


def read_ledger_export(path: Path) -> list[LedgerRow]:
    """The owner's hand-exported Kraken ledger CSV, read by HEADER NAME and refusing rather than defaulting."""
    row_no = 0  # 0 while the header is being read; the first data row is 1
    try:
        # `utf-8-sig`: the runbook has the owner opening this file by hand, and an Excel
        # round-trip prefixes a BOM that would glue itself to the first column name.
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            header = reader.fieldnames or []
            missing = [column for column in _LEDGER_COLUMNS if column not in header]
            if missing:
                raise EngineError(
                    f"the ledger export {path} has no {', '.join(missing)} column -- its header reads "
                    f"{', '.join(header) or '(empty)'}. Refusing rather than defaulting"
                )
            rows: list[LedgerRow] = []
            width = len(header)
            # A row ordinal, not a physical line number: a quoted field may carry a newline, after
            # which the two drift and a line number sends the operator to the wrong place.
            for row_no, raw in enumerate(reader, start=1):
                # Read a row only at the header's field count: DictReader puts a long row's extras under None, a short
                # row's gaps as None, and a field inserted mid-row shifts every column after it into the wrong name.
                if None in raw or None in raw.values():
                    count = width + len(raw[None]) if None in raw else width - sum(value is None for value in raw.values())
                    raise EngineError(
                        f"the ledger export {path} has a field count of {count} at data row {row_no}, against its "
                        f"header's {width}. Refusing rather than defaulting"
                    )
                # The export writes no offset and the venue stamps UTC: a naive one raises against aware boundaries.
                at = datetime.fromisoformat(raw["time"])
                rows.append(
                    LedgerRow(
                        raw["txid"],
                        raw["refid"],
                        at if at.tzinfo is not None else at.replace(tzinfo=UTC),
                        raw["type"],
                        raw["subtype"],
                        raw["asset"],
                        float(raw["amount"]),
                        float(raw["fee"]),
                    )
                )
    # One catch spans every decode and parse, the header included: the caller handles only this module's error and OSError.
    except (TypeError, ValueError, csv.Error) as exc:
        where = "its header" if row_no == 0 else f"data row {row_no}, or just after it"
        raise EngineError(f"the ledger export {path} is unreadable at {where}: {exc}") from exc
    return rows


def reconcile_ledger(rows: list[LedgerRow], fills: list[Fill]) -> dict:
    """An unmatched venue trade or margin row FAILS the comparison; an export with neither decides nothing; a known
    no-fill row is counted under `known`, an unknown type under `ignored`."""
    journaled = {f.trade_id for f in fills}
    matched = 0
    compared = 0
    unmatched: list[str] = []
    known: dict[str, int] = {}
    ignored: dict[str, int] = {}
    rollover_fees_eur = 0.0
    matched_fees_eur = 0.0
    for row in rows:
        # Rollover is why the function exists: the venue charges it against the POSITION, so a fill-based cost basis omits it.
        if row.type == "rollover":
            # `_EURO_FEE_ASSETS`: the venue spells the euro two ways and charges some fees in EURC, and `== "EUR"` would
            # drop the rest.
            if row.asset in _EURO_FEE_ASSETS:
                rollover_fees_eur += row.fee
        elif row.type in _MATCHED_LEDGER_TYPES:
            compared += 1
            if row.refid in journaled:
                # ROWS, not fills: one venue trade writes one ledger row per asset leg.
                matched += 1
                # The row's `fee` is the venue's own figure for the fill; its `amount` is a margin row's realized
                # PnL, a result and never a cost, so it is summed nowhere.
                if row.asset in _EURO_FEE_ASSETS:
                    matched_fees_eur += row.fee
            # Venue activity the journal does not know about is the one thing
            # this comparison exists to detect: it FAILS, and each id is named.
            elif row.refid not in unmatched:
                unmatched.append(row.refid)
        elif row.type in _NO_FILL_LEDGER_TYPES or (row.type, row.subtype) == _EARN_REWARD:
            known[row.type] = known.get(row.type, 0) + 1
        elif row.subtype == _DUST_SWEEP_SUBTYPE and row.type in _DUST_SWEEP_TYPES:
            known[row.subtype] = known.get(row.subtype, 0) + 1
        else:
            ignored[row.type] = ignored.get(row.type, 0) + 1
    return {
        # A third value, never "ok": with no trade or margin row compared, "every venue trade matched" claims nothing.
        "status": "FAILED" if unmatched else "ok" if compared else "insufficient-data",
        # Every row read: what separates an empty export from one carrying no trade or margin rows.
        "n_rows": len(rows),
        "matched": matched,
        "matched_fees_eur": matched_fees_eur,
        "rollover_fees_eur": rollover_fees_eur,
        "unmatched": unmatched,
        "known": known,
        "ignored": ignored,
    }
