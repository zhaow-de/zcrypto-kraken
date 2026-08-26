"""The probe-plan model (spec 00090, rung 1): a pure parse + refusal-check layer for the small
JSON control files the account owner drops for the engine to submit as a real order. Deliberately
imports only stdlib, `cli.engine.errors`, and `cli.engine.store.BASKET` -- no nautilus -- so the
offline `probe-plan --check` validator and this module's tests stay fast, and so the model itself
never depends on anything that talks to the venue.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from cli.engine.errors import EngineError
from cli.engine.store import BASKET

PLAN_FILENAME = "probe-plan.json"
PLAN_TTL = timedelta(minutes=60)

_SIDES = frozenset({"buy", "sell"})
_ACTIONS = frozenset({"open", "close"})
_MODES = frozenset({"execute", "rest-cancel"})
_MIN_LEVERAGE = 2
_MAX_LEVERAGE = 10
# Exact legal key sets, checked before any field-specific validation (cli/config.py's own
# unknown-key convention) -- every field below is typo-safe via its own missing/mistyped check
# EXCEPT an optional key like `leverage`: a typo'd `"levarage": 3` has no required counterpart to
# catch it, so it would otherwise parse cleanly as a spot intent with the operator's intended
# leverage silently dropped. Owner ruling: refuse the whole plan on any unrecognized key instead.
_PLAN_KEYS = frozenset({"plan_id", "created_at", "intents"})
_INTENT_KEYS = frozenset({"symbol", "side", "action", "mode", "notional_eur", "qty", "leverage"})
# Sec 10's 250% floor at rung scale: required margin (notional / leverage, summed over margin
# intents) times this multiplier must fit under the account's free collateral.
_MARGIN_FLOOR_MULTIPLIER = 2.5


class ProbePlanError(EngineError):
    """A probe plan document violates its shape -- refuse the whole plan, never a partial parse."""


@dataclass(frozen=True)
class ProbeIntent:
    symbol: str
    side: str  # "buy" | "sell"
    action: str  # "open" | "close"
    mode: str  # "execute" | "rest-cancel"
    notional_eur: float | None  # exactly one of notional_eur / qty
    qty: float | None  # the disposal's explicit base quantity (close + spot only)
    leverage: int | None  # None = spot; margin requires 2..10 (the committed band)


@dataclass(frozen=True)
class ProbePlan:
    plan_id: str
    created_at: datetime
    intents: tuple[ProbeIntent, ...]
    raw: dict  # the parsed document verbatim, journaled by the executor


def _parse_positive_number(value: object, name: str) -> float:
    # bool is a subclass of int -- reject it explicitly, mirroring cli/config.py's numeric
    # fields: a JSON `true` is not a EUR amount or a base quantity, and 1.0 is a plausible-looking
    # value that would otherwise silently pass the finite/positive check below.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProbePlanError(f"probe plan intent {name} must be a number, got {value!r}")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ProbePlanError(f"probe plan intent {name} must be a finite positive number, got {value!r}")
    return number


def _parse_intent(raw: object) -> ProbeIntent:
    if not isinstance(raw, dict):
        raise ProbePlanError(f"probe plan intent must be an object, got {raw!r}")
    unknown = sorted(set(raw) - _INTENT_KEYS)
    if unknown:
        raise ProbePlanError(f"probe plan intent has unknown key(s): {', '.join(unknown)}")

    symbol = raw.get("symbol")
    if symbol not in BASKET:
        raise ProbePlanError(f"probe plan intent symbol {symbol!r} is not in the basket")

    side = raw.get("side")
    if side not in _SIDES:
        raise ProbePlanError(f"probe plan intent side must be one of {sorted(_SIDES)}, got {side!r}")

    action = raw.get("action")
    if action not in _ACTIONS:
        raise ProbePlanError(f"probe plan intent action must be one of {sorted(_ACTIONS)}, got {action!r}")

    mode = raw.get("mode")
    if mode not in _MODES:
        raise ProbePlanError(f"probe plan intent mode must be one of {sorted(_MODES)}, got {mode!r}")

    has_notional = raw.get("notional_eur") is not None
    has_qty = raw.get("qty") is not None
    if has_notional == has_qty:
        raise ProbePlanError(
            "probe plan intent must carry exactly one of notional_eur/qty, got "
            f"notional_eur={raw.get('notional_eur')!r} qty={raw.get('qty')!r}"
        )
    notional_eur = _parse_positive_number(raw["notional_eur"], "notional_eur") if has_notional else None
    qty = _parse_positive_number(raw["qty"], "qty") if has_qty else None

    leverage_raw = raw.get("leverage")
    leverage = None
    if leverage_raw is not None:
        if not isinstance(leverage_raw, int) or not (_MIN_LEVERAGE <= leverage_raw <= _MAX_LEVERAGE):
            raise ProbePlanError(
                f"probe plan intent leverage must be an int in [{_MIN_LEVERAGE}, {_MAX_LEVERAGE}], got {leverage_raw!r}"
            )
        leverage = leverage_raw

    if qty is not None and (action != "close" or leverage is not None):
        raise ProbePlanError(
            f"probe plan intent qty requires action == 'close' and no leverage, got action={action!r} leverage={leverage!r}"
        )

    return ProbeIntent(symbol=symbol, side=side, action=action, mode=mode, notional_eur=notional_eur, qty=qty, leverage=leverage)


def parse_plan(text: str) -> ProbePlan:
    """Parse `text` into a ProbePlan, raising ProbePlanError on ANY shape violation -- refusal by
    default; there is no such thing as a partially-valid plan."""
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProbePlanError(f"probe plan is not valid JSON: {exc}") from exc
    if not isinstance(doc, dict):
        raise ProbePlanError(f"probe plan must be a JSON object, got {type(doc).__name__}")
    unknown = sorted(set(doc) - _PLAN_KEYS)
    if unknown:
        raise ProbePlanError(f"probe plan has unknown key(s): {', '.join(unknown)}")

    plan_id = doc.get("plan_id")
    if not isinstance(plan_id, str) or not plan_id.strip():
        raise ProbePlanError(f"probe plan plan_id must be a non-empty string, got {plan_id!r}")

    created_raw = doc.get("created_at")
    if not isinstance(created_raw, str):
        raise ProbePlanError(f"probe plan created_at must be a string, got {created_raw!r}")
    try:
        created_at = datetime.fromisoformat(created_raw)
    except ValueError as exc:
        raise ProbePlanError(f"probe plan created_at is not a valid ISO datetime: {created_raw!r}") from exc
    if created_at.utcoffset() is None:
        raise ProbePlanError(f"probe plan created_at must be timezone-aware, got {created_raw!r}")

    intents_raw = doc.get("intents")
    if not isinstance(intents_raw, list) or not intents_raw:
        raise ProbePlanError(f"probe plan intents must be a non-empty list, got {intents_raw!r}")
    intents = tuple(_parse_intent(i) for i in intents_raw)

    return ProbePlan(plan_id=plan_id, created_at=created_at, intents=intents, raw=doc)


def plan_refusals(
    plan: ProbePlan,
    *,
    now: datetime,
    ledgered: frozenset[str],
    max_plan_notional_eur: float,
    free_zeur: float,
) -> tuple[str, ...]:
    """Every applicable refusal reason for `plan`, in declaration order (the gate's
    plural-reasons discipline -- an operator sees every condition standing between them and
    submission, not just the first one found).

    The notional cap sums `notional_eur or 0.0` per intent: a `qty` intent contributes 0.0 here
    because no price exists yet to convert its base quantity into EUR at validation time -- it is
    NOT exempt from the cap, only deferred. Its real notional (`qty x the chosen limit price`) is
    known only at sizing time, where the executor enforces the cumulative plan cap on first
    submission.

    The margin floor (Sec 10's 250% floor at rung scale) sums `notional_eur / leverage` over
    margin intents (those with `leverage is not None`) and requires that sum, x2.5, to fit under
    `free_zeur`. A `qty` disposal intent is excluded from this sum -- `parse_plan` already refuses
    qty combined with leverage, so a qty intent can only be a spot close, and a spot sell extends
    no margin.

    `max_plan_notional_eur` and `free_zeur` are each validated for finiteness HERE, at the point of
    use, not just wherever they were sourced: `x > nan` is always False, so a NaN cap or a NaN
    free-balance would otherwise fail the corresponding comparison OPEN, and an infinite cap
    disables the blast-radius bound entirely (nothing ever compares as "exceeding" it). `free_zeur`
    in particular comes from a live venue balance read by the executor, not from config, so it
    cannot rely on `cli/config.py`'s own finiteness check.
    """
    reasons: list[str] = []

    ttl_minutes = int(PLAN_TTL.total_seconds() // 60)
    if now - plan.created_at > PLAN_TTL:
        reasons.append(f"plan expired: created_at {plan.created_at.isoformat()} is over {ttl_minutes} minutes old")
    if plan.created_at > now:
        reasons.append("created_at is in the future")
    if plan.plan_id in ledgered:
        reasons.append("plan_id already ledgered")

    total_notional = sum(i.notional_eur or 0.0 for i in plan.intents)
    if not math.isfinite(max_plan_notional_eur):
        reasons.append(f"max_plan_notional_eur is not finite: {max_plan_notional_eur!r}")
    elif total_notional > max_plan_notional_eur:
        reasons.append(f"plan notional {total_notional:.2f} EUR exceeds the cap {max_plan_notional_eur:.2f} EUR")

    margin_required = sum(i.notional_eur / i.leverage for i in plan.intents if i.leverage is not None) * _MARGIN_FLOOR_MULTIPLIER
    if not math.isfinite(free_zeur):
        reasons.append(f"free_zeur is not finite: {free_zeur!r}")
    elif margin_required > free_zeur:
        reasons.append(f"margin floor: {margin_required:.2f} EUR required exceeds free_zeur {free_zeur:.2f} EUR")

    return tuple(reasons)
