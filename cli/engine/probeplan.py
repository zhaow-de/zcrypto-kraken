"""The probe-plan model (spec 00090, rung 1): a pure parse + refusal-check layer for the JSON control files the account owner
drops for the engine to submit as a real order. Imports only stdlib, `cli.engine.errors` and `cli.engine.store.BASKET` --
never nautilus -- so the offline `probe-plan --check` validator stays fast and the model never depends on anything that
talks to the venue."""

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
MODES = frozenset({"execute", "rest-cancel", "rest-hold"})
_MIN_LEVERAGE = 2
_MAX_LEVERAGE = 10
# Exact legal key sets, checked before any field-specific validation (cli/config.py's unknown-key convention): an optional
# key has no required counterpart to catch a typo, so a `"levarage": 3` would otherwise parse cleanly as a spot intent with
# the operator's intended leverage silently dropped. Owner ruling: refuse the whole plan on any unrecognized key.
_PLAN_KEYS = frozenset({"plan_id", "created_at", "intents"})
_INTENT_KEYS = frozenset({"symbol", "side", "action", "mode", "notional_eur", "qty", "leverage", "offset_pct", "hold_minutes"})
_MAX_HOLD_MINUTES = 60
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
    mode: str  # one of MODES
    notional_eur: float | None  # exactly one of notional_eur / qty
    qty: float | None  # the disposal's explicit base quantity (close + spot only)
    leverage: int | None  # None = spot; margin requires 2..10 (the committed band)
    offset_pct: float | None = None  # rest-hold only: PERCENT passive of the touch -- 5.0 is five percent
    hold_minutes: int | None = None  # rest-hold only: how long the order rests, 1.._MAX_HOLD_MINUTES


@dataclass(frozen=True)
class ProbePlan:
    plan_id: str
    created_at: datetime
    intents: tuple[ProbeIntent, ...]
    raw: dict  # the parsed document verbatim, journaled by the executor


def _parse_positive_number(value: object, name: str) -> float:
    # bool is a subclass of int -- reject it explicitly, as cli/config.py's numeric fields do: a JSON `true` is not a EUR amount,
    # a base quantity or a percent, and it floats to a plausible-looking 1.0 that would pass the finite/positive check below.
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
    if mode not in MODES:
        raise ProbePlanError(f"probe plan intent mode must be one of {sorted(MODES)}, got {mode!r}")

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

    offset_raw = raw.get("offset_pct")
    hold_raw = raw.get("hold_minutes")
    offset_pct: float | None = None
    hold_minutes: int | None = None
    if mode == "rest-hold":
        if offset_raw is None or hold_raw is None:
            raise ProbePlanError(
                "probe plan intent mode 'rest-hold' requires both offset_pct and hold_minutes, got "
                f"offset_pct={offset_raw!r} hold_minutes={hold_raw!r}"
            )
        if action != "open":
            raise ProbePlanError(f"probe plan intent mode 'rest-hold' requires action == 'open', got {action!r}")
        # PERCENT, not a fraction: 5.0 is five percent. An intent copying `_REST_CANCEL_OFFSET`'s fractional 0.05 would rest
        # five hundredths of a percent off the touch, and fill -- on a mode built never to.
        offset_pct = _parse_positive_number(offset_raw, "offset_pct")
        # `True` is an int inside the range, so without this arm `hold_minutes: true` would parse as a 1-minute hold.
        if isinstance(hold_raw, bool) or not isinstance(hold_raw, int) or not (1 <= hold_raw <= _MAX_HOLD_MINUTES):
            raise ProbePlanError(f"probe plan intent hold_minutes must be an int in [1, {_MAX_HOLD_MINUTES}], got {hold_raw!r}")
        hold_minutes = hold_raw
    elif offset_raw is not None or hold_raw is not None:
        raise ProbePlanError(
            "probe plan intent offset_pct/hold_minutes are legal only on mode 'rest-hold', got "
            f"mode={mode!r} offset_pct={offset_raw!r} hold_minutes={hold_raw!r}"
        )

    if qty is not None and (action != "close" or leverage is not None):
        raise ProbePlanError(
            f"probe plan intent qty requires action == 'close' and no leverage, got action={action!r} leverage={leverage!r}"
        )

    return ProbeIntent(
        symbol=symbol,
        side=side,
        action=action,
        mode=mode,
        notional_eur=notional_eur,
        qty=qty,
        leverage=leverage,
        offset_pct=offset_pct,
        hold_minutes=hold_minutes,
    )


def parse_plan(text: str) -> ProbePlan:
    """Parse `text` into a ProbePlan, raising ProbePlanError on ANY shape violation -- there is no partially-valid plan."""
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
    """Every applicable refusal reason for `plan`, in declaration order -- plural by design: the operator sees every condition
    between them and submission, not just the first. A `qty` intent contributes 0.0 to the notional sum, no price yet to convert it
    -- deferred, never exempt: the executor's `_over_cap_reason` cumulates its real notional at sizing time. The qty intent is
    absent from the margin sum by design: `parse_plan` refuses qty with leverage, so it is a spot close, which extends no margin."""
    reasons: list[str] = []

    ttl_minutes = int(PLAN_TTL.total_seconds() // 60)
    if now - plan.created_at > PLAN_TTL:
        reasons.append(f"plan expired: created_at {plan.created_at.isoformat()} is over {ttl_minutes} minutes old")
    if plan.created_at > now:
        reasons.append("created_at is in the future")
    if plan.plan_id in ledgered:
        reasons.append("plan_id already ledgered")

    # Both bounds are checked finite at the point of use -- a NaN or +inf bound compares False against any total and fails its
    # check open, and `free_zeur` is a live venue balance, outside `cli/config.py`'s own finiteness check.
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
