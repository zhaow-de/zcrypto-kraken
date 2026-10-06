"""Draft one rung-2 probe plan: each leg's target from the newest cycle record, minus what Kraken itself says is held.

Pure functions over parsed inputs. The two network reads -- the public ticker and the status page's maintenance feed --
take their opener as an argument, so no test reaches the venue. Nothing here holds a credential or places an order."""

from __future__ import annotations

import http.client
import json
import math
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from cli.engine.errors import EngineError
from cli.engine.instruments import _floor_to_step
from cli.engine.journal import CycleRecord
from cli.engine.probeplan import ProbePlan, ProbePlanError, parse_plan
from cli.engine.store import PAIR_KEYS

LEGS: tuple[str, ...] = ("BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR", "DOGE/EUR", "LTC/EUR", "ADA/EUR", "AVAX/EUR", "DOT/EUR")
EUR_PER_WEIGHT = 720.0
BUY_ORDERMIN_HEADROOM = 1.05
MIN_BUY_EUR = 0.50
CASH_RESERVE_EUR = 5.0
PLAN_CAP_EUR = 95.0
MAX_INTENTS = 3
INTENT_TIME_BOX = timedelta(minutes=15)
EXPORT_MAX_AGE = timedelta(minutes=30)
GROSS_JUMP_HIGH = 1.8
GROSS_JUMP_LOW = 0.55
# The boundaries a drop window follows, and its slots, whose gaps clear valkey2's and valkey3's
# `base_unattended_upgrades_reboot_time`.
DROP_SLOTS: dict[int, tuple[tuple[time, time], ...]] = {
    12: ((time(12, 10), time(13, 15)), (time(13, 30), time(15, 0))),
    16: ((time(16, 10), time(17, 15)), (time(17, 30), time(19, 0))),
}
BOX_FIRST_DAY = date(2026, 10, 5)
BOX_DAYS = 28
BOX_LAST_DAY = BOX_FIRST_DAY + timedelta(days=BOX_DAYS - 1)
EXIT_DAYS = (BOX_FIRST_DAY + timedelta(days=26), BOX_FIRST_DAY + timedelta(days=27))

_TICKER_URL = "https://api.kraken.com/0/public/Ticker"
_MAINTENANCE_FEED = "https://status.kraken.com/api/v2/scheduled-maintenances.json"
_TIMEOUT_SECONDS = 30
_BASES = frozenset(symbol.split("/")[0] for symbol in LEGS)
_PLAN_ID = re.compile(r"r2-(\d{8})-(\d+)")
# `infra/scripts/deploy-log-audit.py`'s `_NAMES_AN_API`, whose `api_impacting` docstring says why.
_NAMES_AN_API = re.compile(r"(?<![A-Za-z0-9])(?:websocket|rest)(?![A-Za-z0-9])", re.IGNORECASE)


class DraftPlanError(EngineError):
    """A refusal: no plan is drafted and nothing is written."""


@dataclass(frozen=True)
class Constraints:
    ordermin: float
    lot_step: float


@dataclass(frozen=True)
class BalanceExport:
    held: dict[str, float]  # base -> balance, 0.0 for a base the export does not list
    free_eur: float
    outside: dict[str, float]  # every other non-zero row, under the export's own code


@dataclass(frozen=True)
class LegDecision:
    symbol: str
    weight: float
    target_eur: float
    kraken_held: float
    engine_held: float | None
    venue_b: float
    price: float
    ordermin: float
    lot_step: float
    delta_eur: float
    outcome: str  # placed (drafted into this run's plan) | queued | carried | on-target
    side: str | None = None  # the delta's direction
    qty: float | None = None  # a sell's, set only while placed or queued
    notional_eur: float | None = None  # a buy's, set only while placed or queued
    reason: str = ""

    @property
    def eur(self) -> float:
        return self.notional_eur if self.side == "buy" else self.qty * self.price

    @property
    def buy_floor(self) -> float:
        return max(BUY_ORDERMIN_HEADROOM * self.ordermin * self.price, MIN_BUY_EUR)


@dataclass(frozen=True)
class Draft:
    decisions: tuple[LegDecision, ...]
    plan_id: str | None
    plan_text: str | None
    rows: tuple[dict, ...]
    report: str


def _get_json(url: str, opener, what: str) -> object:
    try:
        with opener(url, timeout=_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (OSError, ValueError, http.client.HTTPException) as exc:
        raise DraftPlanError(f"could not read {what}: {exc}") from exc


def fetch_ticker(opener=urllib.request.urlopen) -> dict:
    payload = _get_json(f"{_TICKER_URL}?pair={','.join(PAIR_KEYS[symbol] for symbol in LEGS)}", opener, "the public ticker")
    if not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("result"), dict):
        raise DraftPlanError(f"the public ticker answered without a result: {payload!r:.300}")
    return payload["result"]


def fetch_maintenance_feed(opener=urllib.request.urlopen) -> dict:
    payload = _get_json(_MAINTENANCE_FEED, opener, "the maintenance feed")
    if not isinstance(payload, dict):
        raise DraftPlanError(f"the maintenance feed is not a JSON object: {payload!r:.300}")
    return payload


def latest_boundary(now: datetime) -> datetime:
    now = now.astimezone(timezone.utc)
    return now.replace(hour=now.hour - now.hour % 4, minute=0, second=0, microsecond=0)


def drop_slots(boundary: datetime) -> tuple[tuple[datetime, datetime], ...]:
    boundary = boundary.astimezone(timezone.utc)
    slots = DROP_SLOTS.get(boundary.hour)
    if slots is None or boundary != latest_boundary(boundary):
        raise DraftPlanError(
            f"no drop window follows the {boundary:%Y-%m-%d %H:%M}Z record -- plans are drafted from the 12Z record, "
            "or from the 16Z record as the same-day fallback"
        )
    day = boundary.date()
    return tuple(
        (datetime.combine(day, start, tzinfo=timezone.utc), datetime.combine(day, end, tzinfo=timezone.utc)) for start, end in slots
    )


def last_drop(window_end: datetime, intents: int) -> datetime:
    return window_end - intents * INTENT_TIME_BOX


def box_day_refusal(day: date, *, exiting: bool) -> str | None:
    if not BOX_FIRST_DAY <= day <= BOX_LAST_DAY:
        return f"{day:%a %Y-%m-%d} is outside the box, {BOX_FIRST_DAY:%a %Y-%m-%d} to {BOX_LAST_DAY:%a %Y-%m-%d}"
    if day in EXIT_DAYS and not exiting:
        return f"{day:%a %Y-%m-%d} is an exit day -- only --exit drafts on it, and nothing is bought"
    if exiting and day not in EXIT_DAYS:
        return (
            f"{day:%a %Y-%m-%d} is not an exit day -- --exit drafts on {EXIT_DAYS[0]:%a %Y-%m-%d} and "
            f"{EXIT_DAYS[1]:%a %Y-%m-%d} alone"
        )
    return None


def _instant(raw: object) -> datetime:
    moment = datetime.fromisoformat(raw)
    if moment.utcoffset() is None:
        raise ValueError(f"{raw!r} carries no offset")
    return moment


def maintenance_conflicts(feed: dict, start: datetime, end: datetime) -> list[str]:
    """Each published WebSocket/REST maintenance overlapping [start, end], named with its own window."""
    entries = feed.get("scheduled_maintenances")
    if not isinstance(entries, list) or not entries:
        raise DraftPlanError(
            "the maintenance feed lists no maintenances -- an empty or misshapen feed is no evidence the drop window is clear"
        )
    conflicts = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise DraftPlanError(f"the maintenance feed carries an entry that is not an object: {entry!r:.200}")
        components = entry.get("components") or []
        names = [str(c.get("name") or "") for c in components if isinstance(c, dict)] + [str(entry.get("name") or "")]
        if not any(_NAMES_AN_API.search(name) for name in names):
            continue
        try:
            begins, ends = _instant(entry.get("scheduled_for")), _instant(entry.get("scheduled_until"))
        except (TypeError, ValueError) as exc:
            raise DraftPlanError(
                f"the WebSocket/REST maintenance {entry.get('name')!r} carries no readable window ({exc}) -- "
                "its overlap with the drop window cannot be ruled out"
            ) from exc
        if begins <= end and ends >= start:
            conflicts.append(f"{entry.get('name')!r} {begins:%Y-%m-%d %H:%M}Z to {ends:%Y-%m-%d %H:%M}Z ({entry.get('status')})")
    return conflicts


def _amount(value: object, what: str) -> float:
    if isinstance(value, bool):
        raise DraftPlanError(f"balance export {what} is not a number: {value!r}")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DraftPlanError(f"balance export {what} is not a number: {value!r}") from exc
    if not math.isfinite(number) or number < 0:
        raise DraftPlanError(f"balance export {what} is not a finite non-negative amount: {value!r}")
    return number


def parse_balance_export(doc: object) -> BalanceExport:
    # flatten imports nautilus; at module level every `zcrypto engine --help` would pay for it.
    from cli.engine.flatten import earn_wallet_base, resolve_base

    if isinstance(doc, dict) and isinstance(doc.get("error"), str):
        raise DraftPlanError(f"the balance export is an error answer, not balances: {doc.get('message') or doc['error']}")
    if isinstance(doc, dict) and isinstance(doc.get("error"), list) and "result" in doc:
        raise DraftPlanError(
            "the balance export is a REST answer envelope {error, result}, not the asset map the extended balance export prints"
        )
    if not isinstance(doc, dict) or not doc:
        raise DraftPlanError("the balance export must be a non-empty JSON object of asset -> {balance, hold_trade}")
    found: dict[str, tuple[str, float]] = {}
    outside: dict[str, float] = {}
    for code, row in doc.items():
        if not isinstance(row, dict) or "balance" not in row:
            raise DraftPlanError(
                f"balance export row {code!r} is not an object carrying a balance -- export the extended balance, which "
                "carries hold_trade"
            )
        balance = _amount(row["balance"], f"{code} balance")
        hold = _amount(row.get("hold_trade", 0), f"{code} hold_trade")
        asset = resolve_base(code, _BASES | {"EUR"})
        if asset is None:
            wallet_base = earn_wallet_base(code, _BASES)
            if balance and wallet_base is not None:
                raise DraftPlanError(
                    f"{code} holds {balance:.10g} {wallet_base} outside the spot wallet -- the leg would be drafted against "
                    "part of what is held; move it back to spot before drafting"
                )
            if balance:
                outside[code] = balance
            continue
        if asset in found:
            raise DraftPlanError(f"the balance export lists {asset} twice, as {found[asset][0]!r} and {code!r}")
        if hold:
            raise DraftPlanError(
                f"{code} has {hold:.10g} held against a resting order -- the previous plan is not terminal; read Kraken's "
                "open orders before drafting"
            )
        found[asset] = (code, balance)
    if "EUR" not in found:
        raise DraftPlanError("the balance export carries no EUR row")
    held = {base: found[base][1] if base in found else 0.0 for base in sorted(_BASES)}
    return BalanceExport(held=held, free_eur=found["EUR"][1], outside=outside)


def venue_view(doc: dict, cycle_ts: datetime) -> tuple[dict[str, Constraints], dict[str, float], dict]:
    """Each leg's ordermin and lot step, the engine's held per leg, and the balances b is read from, off the venue
    record of `cycle_ts`'s boundary."""
    if doc.get("status") != "ok" or doc.get("schema_version") != 2:
        raise DraftPlanError(
            f"the venue record is not an ok schema-2 snapshot (status {doc.get('status')!r}, schema_version "
            f"{doc.get('schema_version')!r}) -- it carries no b to check a sell against"
        )
    venue_ts = datetime.fromisoformat(doc["cycle_ts"])
    if venue_ts != cycle_ts:
        raise DraftPlanError(
            f"the venue record is for {venue_ts.isoformat()} and the cycle record for {cycle_ts.isoformat()} -- pass one "
            "boundary's pair"
        )
    constraints: dict[str, Constraints] = {}
    for symbol in LEGS:
        entry = doc["state"]["instruments"].get(symbol)
        if entry is None:
            raise DraftPlanError(f"the venue record carries no {symbol} constraints")
        try:
            ordermin, lot_step = float(entry["ordermin"]), float(entry["lot_step"])
        except (TypeError, ValueError) as exc:
            raise DraftPlanError(f"the venue record's {symbol} constraints are not numbers: {exc}") from exc
        if not (ordermin > 0 and lot_step > 0):
            raise DraftPlanError(f"the venue record's {symbol} ordermin {ordermin!r} or lot step {lot_step!r} is not positive")
        constraints[symbol] = Constraints(ordermin=ordermin, lot_step=lot_step)
    positions: dict[str, float] = {}
    for symbol in LEGS:
        if symbol not in doc["state"]["positions"]:
            continue
        size = doc["state"]["positions"][symbol]
        try:
            held = float(size)
        except TypeError, ValueError:
            held = math.nan
        if not math.isfinite(held):
            raise DraftPlanError(f"the venue record's {symbol} position {size!r} is unreadable")
        positions[symbol] = held
    return constraints, positions, doc["state"]["balances"]


def refuse_open_margin_positions(doc: object) -> None:
    error = doc.get("error") if isinstance(doc, dict) else None
    if error and isinstance(error, (str, list)):
        raise DraftPlanError(f"the positions export is an error answer, not positions: {doc.get('message') or error}")
    if isinstance(error, list):
        raise DraftPlanError(
            "the positions export is a REST answer envelope {error, result}, not the position map the open-positions export prints"
        )
    if not isinstance(doc, dict):
        raise DraftPlanError("the positions export must be a JSON object of position id -> position, empty when nothing is open")
    stray = [str(txid) for txid, row in doc.items() if not (isinstance(row, dict) and "pair" in row)]
    if stray:
        raise DraftPlanError(
            "the positions export is not the position map the open-positions export prints: "
            f"{', '.join(stray)} carries no position's pair"
        )
    if doc:
        named = "; ".join(f"{txid} ({row['pair']} {row.get('side')} {row.get('vol')})" for txid, row in doc.items())
        raise DraftPlanError(f"Kraken reports an open margin position {named}: the box is spot only")


def venue_balance(balances: dict, base: str) -> float:
    # `executor._spot_balance`'s rule, so b is the figure the engine's own sell refusal reads.
    from cli.engine.flatten import resolve_base

    for code, value in balances.items():
        if resolve_base(code, frozenset((base,))) == base:
            try:
                b = float(value)
            except TypeError, ValueError:
                b = math.nan
            if not math.isfinite(b):
                raise DraftPlanError(
                    f"the venue record's {code} balance {value!r} is unreadable -- no b to check a {base} sell against"
                )
            return b
    return 0.0


def leg_weights(record: CycleRecord) -> dict[str, float]:
    if record.schema_version != 2:
        raise DraftPlanError(f"the cycle record is schema {record.schema_version}; the legs are read from schema 2's full symbols")
    missing = [symbol for symbol in LEGS if symbol not in record.final_targets]
    if missing:
        raise DraftPlanError(f"the cycle record carries no target for {', '.join(missing)}")
    return {symbol: float(record.final_targets[symbol]) for symbol in LEGS}


def mid_prices(ticker: dict) -> dict[str, float]:
    prices = {}
    for symbol in LEGS:
        key = PAIR_KEYS[symbol]
        try:
            ask, bid = float(ticker[key]["a"][0]), float(ticker[key]["b"][0])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise DraftPlanError(f"the ticker carries no readable touch for {symbol} ({key})") from exc
        if not (math.isfinite(ask) and math.isfinite(bid) and 0 < bid <= ask):
            raise DraftPlanError(f"the ticker's {symbol} touch is not a market: bid {bid!r}, ask {ask!r}")
        prices[symbol] = (ask + bid) / 2
    return prices


def decide_leg(
    symbol: str,
    *,
    weight: float,
    price: float,
    constraints: Constraints,
    kraken_held: float,
    engine_held: float | None,
    venue_b: float,
    exiting: bool = False,
    eur_per_weight: float = EUR_PER_WEIGHT,
) -> LegDecision:
    target = 0.0 if exiting else eur_per_weight * max(weight, 0.0)
    leg = LegDecision(
        symbol=symbol,
        weight=weight,
        target_eur=target,
        kraken_held=kraken_held,
        engine_held=engine_held,
        venue_b=venue_b,
        price=price,
        ordermin=constraints.ordermin,
        lot_step=constraints.lot_step,
        delta_eur=target - kraken_held * price,
        outcome="carried",
    )
    if leg.delta_eur == 0:
        return replace(leg, outcome="on-target", reason="target equals held")
    if leg.delta_eur > 0:
        if leg.delta_eur < leg.buy_floor:
            return replace(leg, side="buy", reason=f"buy {leg.delta_eur:.4f} EUR is under the buy floor {leg.buy_floor:.4f} EUR")
        # Rounded first, or a whole-cent delta's float noise floors it a cent low.
        return replace(leg, outcome="placed", side="buy", notional_eur=_floor_to_step(round(leg.delta_eur, 9), 0.01))
    qty = _floor_to_step(kraken_held - target / price, constraints.lot_step)
    if qty < constraints.ordermin:
        return replace(leg, side="sell", reason=f"sell {qty:.10g} is under ordermin {constraints.ordermin:.10g}")
    reason = ""
    whole = kraken_held - qty < constraints.ordermin
    if whole:
        qty = _floor_to_step(kraken_held, constraints.lot_step)
        reason = "the whole leg" if exiting else "the whole leg: the remainder would be under ordermin"
    if 0 < venue_b < qty:
        # `executor._classify_spot_close`'s refusal; it admits a sell of no more than b.
        capped = _floor_to_step(venue_b, constraints.lot_step)
        if capped < constraints.ordermin:
            return replace(
                leg,
                side="sell",
                reason=f"the venue record's b {venue_b:.10g} is under the sell qty {qty:.10g}, which the engine refuses, and "
                f"under ordermin {constraints.ordermin:.10g}, so no part of the sell is placeable -- the leg cannot be sold "
                "through the engine while the venue record carries that b: see the venue record's balances in the rung-2 "
                "procedure, `engine-rung-2-box` in infra/runbooks/engine-procedures.md",
            )
        left = float(Decimal(str(qty)) - Decimal(str(capped)))
        if left < constraints.ordermin and whole:
            rest = f"the remaining {left:.10g} is under ordermin {constraints.ordermin:.10g}: dust"
        elif left < constraints.ordermin:
            # Not dust: the account keeps the rest of the leg.
            rest = f"the remaining {left:.10g} of the sell is under ordermin {constraints.ordermin:.10g} and is not drafted"
        else:
            rest = (
                f"the remaining {left:.10g} carries to a later draft, which sells up to b again -- to sell more at once, "
                "restart the engine inside an inter-cycle gap, which raises b for a coin Kraken holds, and draft from the "
                "first boundary record written after it"
            )
        reason = f"capped at the venue record's b {venue_b:.10g}, under the sell qty {qty:.10g}; {rest}"
        qty = capped
    return replace(leg, outcome="placed", side="sell", qty=qty, reason=reason)


def trim_buys_to_cash(
    decisions: list[LegDecision], free_eur: float, *, cash_reserve_eur: float = CASH_RESERVE_EUR
) -> list[LegDecision]:
    """Buys are counted in whole cents, so a sum of cent amounts never drifts across the budget."""
    budget = round(_floor_to_step(round(free_eur - cash_reserve_eur, 9), 0.01) * 100) if free_eur > cash_reserve_eur else 0
    buys = sorted((d for d in decisions if d.outcome == "placed" and d.side == "buy"), key=lambda d: (d.notional_eur, d.symbol))
    excess = sum(round(d.notional_eur * 100) for d in buys) - budget
    trimmed: dict[str, LegDecision] = {}
    for leg in buys:
        if excess <= 0:
            break
        cents = round(leg.notional_eur * 100)
        kept = (cents - excess) / 100
        if kept >= leg.buy_floor:
            trimmed[leg.symbol] = replace(
                leg,
                notional_eur=kept,
                reason=f"trimmed by {excess / 100:.2f} EUR to free EUR - {cash_reserve_eur:.0f}; the rest carries",
            )
            excess = 0
        else:
            trimmed[leg.symbol] = replace(
                leg,
                outcome="carried",
                notional_eur=None,
                reason=f"buys beyond free EUR - {cash_reserve_eur:.0f} trim from the smallest",
            )
            excess -= cents
    return [trimmed.get(d.symbol, d) for d in decisions]


def trim_to_plan_cap(decisions: list[LegDecision], cap_eur: float) -> list[LegDecision]:
    """Carries whole legs from the smallest: sells until the sells fit `cap_eur`, then buys until sells and buys together fit
    it -- the total `_over_cap_reason` checks at the last sell's sizing. Never a trimmed quantity: a trimmed sell would leave
    a lot the next boundary sells again."""
    placed = [d for d in decisions if d.outcome == "placed"]
    sells = sorted((d for d in placed if d.side == "sell"), key=lambda d: (d.eur, d.symbol))
    buys = sorted((d for d in placed if d.side == "buy"), key=lambda d: (d.eur, d.symbol))
    while sells and sum(d.eur for d in sells) > cap_eur:
        sells.pop(0)
    while buys and sum(d.eur for d in sells + buys) > cap_eur:
        buys.pop(0)
    kept = {d.symbol for d in sells + buys}
    reason = f"over the plan cap {cap_eur:.0f} EUR; carries to the next boundary"
    return [
        replace(d, outcome="carried", qty=None, notional_eur=None, reason=reason)
        if d.outcome == "placed" and d.symbol not in kept
        else d
        for d in decisions
    ]


def assemble_plans(
    decisions: list[LegDecision], max_intents: int | None = MAX_INTENTS, plan_cap_eur: float | None = PLAN_CAP_EUR
) -> list[list[LegDecision]]:
    ordered = sorted((d for d in decisions if d.outcome == "placed"), key=lambda d: (d.side != "sell", -d.eur, d.symbol))
    plans: list[list[LegDecision]] = []
    total = 0.0
    for leg in ordered:
        if plan_cap_eur is not None and leg.eur > plan_cap_eur:
            raise DraftPlanError(
                f"{leg.symbol}'s {leg.side} of {leg.eur:.2f} EUR is over the {plan_cap_eur:.0f} EUR plan cap on its own -- "
                "no plan can carry it"
            )
        if (
            not plans
            or (max_intents is not None and len(plans[-1]) == max_intents)
            or (plan_cap_eur is not None and total + leg.eur > plan_cap_eur)
        ):
            plans.append([])
            total = 0.0
        plans[-1].append(leg)
        total += leg.eur
    return plans


def queue_later_plans(decisions: list[LegDecision], plans: list[list[LegDecision]], plan_id: str | None) -> list[LegDecision]:
    later = {leg.symbol for plan in plans[1:] for leg in plan}
    note = f"behind {plan_id}"
    return [
        replace(d, outcome="queued", reason="; ".join(filter(None, (d.reason, note)))) if d.symbol in later else d
        for d in decisions
    ]


def plan_document(plan_id: str, created_at: datetime, legs: list[LegDecision]) -> dict:
    intents = [
        {"symbol": leg.symbol, "side": "sell", "action": "close", "mode": "execute", "qty": leg.qty}
        if leg.side == "sell"
        else {"symbol": leg.symbol, "side": "buy", "action": "open", "mode": "execute", "notional_eur": leg.notional_eur}
        for leg in legs
    ]
    return {"plan_id": plan_id, "created_at": created_at.isoformat(), "intents": intents}


def ruling_refusals(
    plan: ProbePlan, prices: dict[str, float], *, exiting: bool = False, window_end: datetime | None = None
) -> list[str]:
    """What the ruling refuses in a parsed plan; a sell's EUR is its qty at the leg's drafted price."""
    reasons: list[str] = []
    created = plan.created_at.astimezone(timezone.utc)
    if refusal := box_day_refusal(created.date(), exiting=exiting):
        reasons.append(refusal)
    if len(plan.intents) > MAX_INTENTS:
        reasons.append(f"{len(plan.intents)} intents, over the {MAX_INTENTS} a plan may carry")
    if window_end is not None and created > (by := last_drop(window_end, len(plan.intents))):
        reasons.append(
            f"a plan of {len(plan.intents)} intent(s) created at {created:%H:%M:%S}Z is past its last drop at {by:%H:%M}Z"
        )
    sides = [intent.side for intent in plan.intents]
    if "buy" in sides and "sell" in sides[sides.index("buy") :]:
        reasons.append("a buy precedes a sell -- sells come first")
    if exiting and "buy" in sides:
        reasons.append("a buy in an exit plan -- the exit only sells")
    total = 0.0
    for index, intent in enumerate(plan.intents):
        if intent.symbol not in LEGS:
            reasons.append(f"intent {index}: {intent.symbol} is not one of the nine legs")
            continue
        if intent.leverage is not None:
            reasons.append(f"intent {index}: leverage {intent.leverage} -- every intent is spot")
        if intent.mode != "execute":
            reasons.append(f"intent {index}: mode {intent.mode!r} -- every intent executes")
        if (intent.side, intent.action, intent.qty is not None) not in (("buy", "open", False), ("sell", "close", True)):
            reasons.append(
                f"intent {index}: a {intent.side} {intent.action} -- a buy opens a notional, a sell closes a qty, nothing is shorted"
            )
        total += intent.notional_eur if intent.notional_eur is not None else intent.qty * prices[intent.symbol]
    if total > PLAN_CAP_EUR:
        reasons.append(f"plan EUR {total:.2f} is over the {PLAN_CAP_EUR:.0f} EUR cap")
    return reasons


def parse_decision_log(text: str) -> list[dict]:
    rows = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DraftPlanError(f"decision log line {number} is not JSON ({exc}) -- the plan_id sequence cannot be read") from exc
        if not isinstance(row, dict):
            raise DraftPlanError(f"decision log line {number} is not a JSON object")
        rows.append(row)
    return rows


def next_plan_id(rows: list[dict], day: date) -> str:
    stamp = f"{day:%Y%m%d}"
    used = [
        int(m.group(2))
        for row in rows
        if isinstance(row.get("plan_id"), str) and (m := _PLAN_ID.fullmatch(row["plan_id"])) and m.group(1) == stamp
    ]
    return f"r2-{stamp}-{max(used, default=0) + 1}"


def placed_today(rows: list[dict], day: date) -> dict[str, tuple[str, datetime]]:
    """Each leg a plan of `day` carried, as its plan_id and drafting time, less the plans a `discarded` row withdraws.
    The helper cannot see whether a plan filled, so any leg one of them carried is not drafted again that day."""
    stamp = f"{day:%Y%m%d}"
    ids = [(row, row.get("plan_id")) for row in rows if isinstance(row.get("plan_id"), str)]
    discarded = {plan_id for row, plan_id in ids if row.get("outcome") == "discarded"}
    legs: dict[str, tuple[str, datetime]] = {}
    for row, plan_id in ids:
        if row.get("outcome") != "placed" or row.get("symbol") not in LEGS or plan_id in discarded:
            continue
        match = _PLAN_ID.fullmatch(plan_id)
        if match is None or match.group(1) != stamp:
            continue
        try:
            drafted_at = _instant(row.get("drafted_at"))
        except (TypeError, ValueError) as exc:
            raise DraftPlanError(f"the decision log's {plan_id} row for {row['symbol']} carries no readable drafted_at") from exc
        legs[row["symbol"]] = (plan_id, drafted_at)
    return legs


def gross_line(gross: float, cycle_ts: datetime, rows: list[dict]) -> str:
    """The record's gross against the previous attended record's, the newest earlier one the decision log holds."""
    previous: tuple[datetime, float] | None = None
    for row in rows:
        try:
            row_ts, row_gross = datetime.fromisoformat(row["cycle_ts"]), float(row["record_gross"])
        except KeyError, TypeError, ValueError:
            continue
        if row_ts < cycle_ts and (previous is None or row_ts > previous[0]):
            previous = (row_ts, row_gross)
    if previous is None:
        return f"gross {gross:.4f}; no earlier attended record in the decision log"
    ratio = gross / previous[1] if previous[1] else (math.inf if gross else 1.0)
    line = f"gross {gross:.4f} against {previous[1]:.4f} at {previous[0]:%Y-%m-%d %H:%M}Z: x{ratio:.2f}"
    if ratio >= GROSS_JUMP_HIGH or ratio <= GROSS_JUMP_LOW:
        line += " -- FLAGGED: read the multiplier with `zcrypto engine decompose` and record it"
    return line


def _detail(leg: LegDecision) -> str:
    if leg.outcome not in ("placed", "queued"):
        return leg.reason
    amount = f"buy {leg.notional_eur:.2f} EUR" if leg.side == "buy" else f"sell {leg.qty:.10g}"
    return f"{amount} -- {leg.reason}" if leg.reason else amount


def _render(
    decisions: list[LegDecision],
    *,
    header: list[str],
    plans: list[list[LegDecision]],
    plan_id: str | None,
    outside: dict[str, float],
    since_record: dict[str, str],
) -> str:
    lines = list(header)
    lines.append(
        f"{'leg':<9} {'weight':>8} {'target EUR':>10} {'Kraken held':>14} {'engine held':>14} {'venue b':>14} "
        f"{'price':>12} {'delta EUR':>10}  {'outcome':<9} detail"
    )
    for leg in decisions:
        engine = "n/a" if leg.engine_held is None else f"{leg.engine_held:.10g}"
        lines.append(
            f"{leg.symbol:<9} {leg.weight:>8.5f} {leg.target_eur:>10.2f} {leg.kraken_held:>14.10g} {engine:>14} "
            f"{leg.venue_b:>14.10g} {leg.price:>12.6g} {leg.delta_eur:>+10.2f}  {leg.outcome:<9} {_detail(leg)}"
        )
    differ = [
        leg.symbol + (f" (in {since_record[leg.symbol]}, drafted after the record)" if leg.symbol in since_record else "")
        for leg in decisions
        if leg.engine_held is not None and round(abs(leg.engine_held - leg.kraken_held) / leg.lot_step, 6) > 1
    ]
    if differ:
        lines.append(
            "engine held is the engine Cache's net -- 0 on a leg held through a restart, negative on a leg sold since one -- "
            "and Kraken's exports are the book: nothing is drafted from it. It differs from Kraken held by more than a lot "
            f"step on: {', '.join(differ)}"
        )
    if outside:
        lines.append(
            "balances outside the nine legs, never drafted: " + ", ".join(f"{c} {v:.10g}" for c, v in sorted(outside.items()))
        )
    if not plans:
        lines.append("nothing placeable: no plan drafted, nothing to arm")
        return "\n".join(lines)
    total = sum(leg.eur for leg in plans[0])
    lines.append(f"plan {plan_id}: {len(plans[0])} intent(s), {total:.2f} EUR")
    if len(plans) > 1:
        queued = ", ".join(leg.symbol for plan in plans[1:] for leg in plan)
        lines.append(
            f"{len(plans) - 1} more plan(s) queued ({queued}): draft again from fresh balance and positions exports once "
            f"{plan_id} is terminal"
        )
    return "\n".join(lines)


def _export_age(what: str, written_at: datetime, now: datetime) -> timedelta:
    age = now - written_at
    if age > EXPORT_MAX_AGE:
        raise DraftPlanError(
            f"the {what} export is {age.total_seconds() / 60:.0f} minutes old, over {EXPORT_MAX_AGE.total_seconds() / 60:.0f} "
            "-- take it again right before drafting"
        )
    if age < -timedelta(minutes=1):
        raise DraftPlanError(
            f"the {what} export is dated {-age.total_seconds() / 60:.0f} minutes after now -- check the workstation's clock"
        )
    return age


def draft(
    *,
    record: CycleRecord,
    venue: dict,
    balances: object,
    balances_written_at: datetime,
    positions: object,
    positions_written_at: datetime,
    log_rows: list[dict],
    now: datetime,
    read_ticker: Callable[[], dict],
    read_feed: Callable[[], dict],
    exiting: bool = False,
    discard: str | None = None,
) -> Draft:
    """Every refusal that needs no price runs before either network read."""
    now = now.astimezone(timezone.utc)
    if refusal := box_day_refusal(now.date(), exiting=exiting):
        raise DraftPlanError(refusal)
    boundary = latest_boundary(now)
    if record.cycle_ts < boundary:
        raise DraftPlanError(
            f"the cycle record is for {record.cycle_ts:%Y-%m-%d %H:%M}Z, older than the latest boundary "
            f"{boundary:%Y-%m-%d %H:%M}Z -- draft from that boundary's record"
        )
    age = _export_age("balance", balances_written_at, now)
    _export_age("positions", positions_written_at, now)
    slots = drop_slots(record.cycle_ts)
    window_end = slots[-1][1]
    box_minutes = f"{INTENT_TIME_BOX.total_seconds() / 60:.0f} minutes"
    fits = min(MAX_INTENTS, (window_end - now) // INTENT_TIME_BOX)
    if fits < 1:
        raise DraftPlanError(
            f"it is {now:%H:%M:%S}Z, past {last_drop(window_end, 1):%H:%M}Z, the last drop of a one-intent plan in the "
            f"window after the {record.cycle_ts:%H}Z record -- each intent takes {box_minutes} before the window's "
            f"{window_end:%H:%M}Z end"
        )
    rows_in = list(log_rows)
    discard_row = None
    if discard is not None:
        live = sorted(
            {plan for plan, _ in placed_today(rows_in, now.date()).values()},
            key=lambda plan: int(_PLAN_ID.fullmatch(plan).group(2)),
        )
        if discard not in live:
            raise DraftPlanError(
                f"{discard} is not one of today's plans the decision log still holds legs under ({', '.join(live) or 'none'}) "
                "-- a plan is discarded on the day it was drafted, and once"
            )
        discard_row = {"drafted_at": now.isoformat(), "plan_id": discard, "outcome": "discarded", "reason": "never placed"}
        rows_in.append(discard_row)
    export = parse_balance_export(balances)
    refuse_open_margin_positions(positions)
    constraints, engine_held, venue_balances = venue_view(venue, record.cycle_ts)
    venue_bs = {symbol: venue_balance(venue_balances, symbol.split("/")[0]) for symbol in LEGS}
    weights = leg_weights(record)
    today = placed_today(rows_in, now.date())
    conflicts = maintenance_conflicts(read_feed(), slots[0][0], window_end)
    if conflicts:
        raise DraftPlanError("a published Kraken WebSocket/REST maintenance overlaps the drop window: " + "; ".join(conflicts))
    prices = mid_prices(read_ticker())

    decisions = [
        decide_leg(
            symbol,
            weight=weights[symbol],
            price=prices[symbol],
            constraints=constraints[symbol],
            kraken_held=export.held[symbol.split("/")[0]],
            engine_held=engine_held.get(symbol),
            venue_b=venue_bs[symbol],
            exiting=exiting,
        )
        for symbol in LEGS
    ]
    decisions = [
        replace(
            d,
            outcome="carried",
            qty=None,
            notional_eur=None,
            reason=f"{today[d.symbol][0]} carried it earlier today; never re-placed the same day",
        )
        if d.outcome == "placed" and d.symbol in today
        else d
        for d in decisions
    ]
    if exiting:
        decisions = [replace(d, reason="; ".join(filter(None, ("exit: target 0", d.reason)))) for d in decisions]
    decisions = trim_buys_to_cash(decisions, export.free_eur)
    plans = assemble_plans(decisions, max_intents=fits)
    plan_id = next_plan_id(rows_in, now.date()) if plans else None
    decisions = queue_later_plans(decisions, plans, plan_id)

    plan_text = None
    if plans:
        plan_text = json.dumps(plan_document(plan_id, now, plans[0]), indent=2)
        try:
            parsed = parse_plan(plan_text)
        except ProbePlanError as exc:
            raise DraftPlanError(f"the drafted plan does not parse: {exc}") from exc
        refusals = ruling_refusals(parsed, prices, exiting=exiting, window_end=window_end)
        if refusals:
            raise DraftPlanError("the drafted plan is refused: " + "; ".join(refusals))

    gross = sum(abs(value) for value in record.final_targets.values())
    minutes = int((now - record.cycle_ts).total_seconds() // 60)
    rows = tuple(
        {
            "drafted_at": now.isoformat(),
            "cycle_ts": record.cycle_ts.isoformat(),
            "minutes_after_boundary": minutes,
            "record_gross": gross,
            "symbol": leg.symbol,
            "weight": leg.weight,
            "target_eur": leg.target_eur,
            "kraken_held": leg.kraken_held,
            "engine_held": leg.engine_held,
            "venue_b": leg.venue_b,
            "price": leg.price,
            "delta_eur": leg.delta_eur,
            "outcome": leg.outcome,
            "side": leg.side,
            "qty": leg.qty,
            "notional_eur": leg.notional_eur,
            "plan_id": plan_id if leg.outcome == "placed" else None,
            "reason": leg.reason,
        }
        for leg in decisions
    )
    header = [
        f"cycle record {record.cycle_ts:%Y-%m-%d %H:%M}Z, drafted {minutes} min after it; balance export "
        f"{age.total_seconds() / 60:.0f} min old",
        f"no published WebSocket/REST maintenance overlaps {slots[0][0]:%H:%M}-{window_end:%H:%M}Z, the window after the "
        f"{record.cycle_ts:%H}Z record",
        f"free EUR {export.free_eur:.2f}; buys capped at free EUR - {CASH_RESERVE_EUR:.0f}",
        gross_line(gross, record.cycle_ts, rows_in),
    ]
    if plans:
        drops = [*slots[:-1], (slots[-1][0], last_drop(window_end, len(plans[0])))]
        drop_line = (
            "drop window "
            + ", ".join(f"{a:%H:%M}-{b:%H:%M}Z" for a, b in drops)
            + f" for this plan's {len(plans[0])} intent(s), {box_minutes} each before {window_end:%H:%M}Z"
        )
        if fits < MAX_INTENTS:
            drop_line += f"; a plan drafted at {now:%H:%M:%S}Z fits at most {fits}"
        header.insert(2, drop_line)
    if exiting:
        header.insert(0, "EXIT: every leg's target is 0 -- nothing is bought")
    if discard_row is not None:
        header.append(f"{discard} discarded as never placed: its legs may be drafted again today")
    since_record = {symbol: plan for symbol, (plan, at) in today.items() if at >= record.cycle_ts}
    report = _render(decisions, header=header, plans=plans, plan_id=plan_id, outside=export.outside, since_record=since_record)
    if discard_row is not None:
        rows = (discard_row, *rows)
    return Draft(decisions=tuple(decisions), plan_id=plan_id, plan_text=plan_text, rows=rows, report=report)
