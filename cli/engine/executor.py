"""The single venue-mutating module (spec 00090, the D4 walk test's anchor): every place this
engine talks to the venue lives here -- `submit_order`, `cancel_order`, and the `order_factory`
that builds what they carry. Two properties are structural rather than conventional:

- **The gate is TAKEN, never held.** `_submit` evaluates the gate itself, as its first act,
  immediately before the venue call, and takes no verdict parameter. There is no permission token a
  caller could hold while the arm file, the kill file or the venue change underneath it.
- **The ledger write PRECEDES the venue call.** The write-ahead row lands before `submit_order`,
  and a write that fails refuses the submission -- so a fill can never exist without a record of
  the order that produced it.

Refusal by default: every error, ambiguity or absent input on this path ends in "no order". A raise
becomes a journaled refusal here and never propagates out of a submission site, where an unhandled
exception has no safe direction. The one thing that is NOT a refusal is a transport failure after
the write-ahead row landed -- that is `ambiguous`, and saying "refused" there would be a claim this
process cannot make.

Every ledger scanner call site is handed an aware-UTC `now` (`_aware_utc`): `execledger._day_dirs`
takes its two-day window from `now.date()`, so a caller-tz `now` would slide the dedup window off
the day the records are actually filed under.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId

from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.execgate import ExecutionGate, GateLevel, GateVerdict, exec_dir
from cli.engine.execledger import (
    append_plan_entry,
    append_submitted_row,
    ledgered_intent_keys,
    ledgered_plan_ids,
    update_plan_intent,
    update_submitted_row,
)
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order
from cli.engine.probeplan import PLAN_FILENAME, ProbeIntent, ProbePlanError, parse_plan, plan_refusals
from cli.engine.venuestate import InstrumentConstraints, venue_state_from_cache
from cli.logging import get_logger

logger = get_logger("engine.executor")

_TICK_SECONDS = 5.0
_QUOTE_WAIT = timedelta(seconds=30)
# The escalation envelope's remaining constants live here rather than at their use sites so the
# whole risk surface of the order path reads in one block. `_QUOTE_SILENCE`, `_TIME_BOX`,
# `_MAX_REPRICES`, `_MAX_IOC_ATTEMPTS` and `_REST_CANCEL_OFFSET` bound the reprice/IOC ladder; the
# two marker tuples classify the venue's own error text on an order event.
_QUOTE_SILENCE = timedelta(seconds=30)
_TIME_BOX = timedelta(minutes=15)
_MAX_REPRICES = 5
_MAX_IOC_ATTEMPTS = 3
_REST_CANCEL_OFFSET = 0.05
_KRAKEN_ERROR_MARKERS = ("EOrder:", "EGeneral:", "EAccount:")
_POST_ONLY_MARKER = "POST_ONLY_REJECTED:"

_H4 = 4

# Module-level, None-safe, installed by command.run() -- the `cycle.set_metrics_sink` pattern. Left
# unset (the default), every call below is a no-op, so a one-shot subcommand or a test that never
# installs them runs unaffected.
_publish_verdict = None
_metrics = None


def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None:
    """Install (or clear, with the defaults) the executor's telemetry hooks: `publish_verdict` is
    called `(verdict, evaluated_at=...)` after EVERY gate evaluation, `metrics` is an object with
    `inc_order(outcome)`. Neither can affect an order -- both are wrapped."""
    global _publish_verdict, _metrics
    _publish_verdict = publish_verdict
    _metrics = metrics


def _publish(verdict: GateVerdict, evaluated_at: datetime) -> None:
    if _publish_verdict is None:
        return
    try:
        _publish_verdict(verdict, evaluated_at=evaluated_at)
    except Exception:
        logger.exception("executor verdict hook raised -- continuing")


def _inc_order(outcome: str) -> None:
    if _metrics is None:
        return
    try:
        _metrics.inc_order(outcome)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _aware_utc(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.utcoffset() is None:
        raise EngineError(f"now must be an aware datetime, got {now!r}")
    return now.astimezone(timezone.utc)


def _boundary(now: datetime) -> datetime:
    """The most recent 00/04/08/12/16/20 UTC boundary <= `now` -- which exec record this plan's
    rows are filed under. A local copy of `cli.engine.node.most_recent_boundary`'s arithmetic:
    importing node here would be an import cycle, since node imports this module."""
    now = _aware_utc(now)
    return now.replace(hour=now.hour - now.hour % _H4, minute=0, second=0, microsecond=0)


def size_probe_order(target_qty: float, touch_price: float, constraints: InstrumentConstraints) -> SizedOrder | BelowMinimum:
    """THE sizing call site (spec 00090 D8): every probe order is sized here, on the Cache-fresh
    constraints and the committed costmin, through the one proven size_order. The comparison this
    module makes is EUR-denominated end to end (an EUR intent notional, an EUR-quoted touch), so the
    guard T0138 holds lands immediately where the notional meets constraints.costmin: a floor
    denominated in anything but EUR must never be compared here -- a /BTC leg's 2e-05 BTC floor
    against a EUR notional passes everything silently (the fail-open defect). Route a future
    /BTC-leg notional through fx_eur_notional first; until then this raises."""
    if constraints.costmin_quote != "EUR":
        raise EngineError(
            f"{constraints.symbol}: costmin is denominated in {constraints.costmin_quote!r} but this "
            "path compares an EUR notional against it -- refusing a cross-denomination comparison "
            "(convert through fx_eur_notional before sizing a non-EUR-quoted leg)"
        )
    return size_order(
        target_qty,
        touch_price,
        ordermin=constraints.ordermin,
        costmin=constraints.costmin,
        lot_step=constraints.lot_step,
        tick_size=constraints.tick_size,
    )


def _level_permits(level: str, intent: ProbeIntent) -> bool:
    """An OPEN intent needs the full level; a CLOSE intent is permitted at reduce-only too -- the
    restart hold exists to let the engine flatten, not to trap it."""
    if intent.action == "close":
        return level in (GateLevel.REDUCE_ONLY, GateLevel.FULL)
    return level == GateLevel.FULL


@dataclass
class _ActiveIntent:
    """The one intent in flight. Mutable and process-local -- everything durable about it is the
    exec ledger's submitted row, which is written before the order exists."""

    index: int
    intent: ProbeIntent
    raw_intent: dict
    instrument_id: InstrumentId
    constraints: InstrumentConstraints
    phase: str
    quote_deadline: datetime
    order_payload: dict | None = None
    client_order_id: str | None = None
    order_qty: float = 0.0
    filled_qty: float = 0.0


# type(event).__name__ -> the submitted row's terminal state. Dispatching on the class NAME keeps
# this stub-friendly and adapter-real at once: the nautilus event classes are matched without
# importing them, and a test double named the same way exercises the identical branch.
_TERMINAL_EVENT_STATES = {
    "OrderRejected": "rejected",
    "OrderDenied": "rejected",
    "OrderCanceled": "venue_canceled",
    "OrderExpired": "venue_canceled",
}


class ProbeExecutor:
    """Owns every venue-mutating call in this repository.

    `client` is the strategy handle (or a stub with the same surface): `.cache`,
    `.order_factory.limit(...)`, `.submit_order(order, params=...)`, `.cancel_order(order)`,
    `.subscribe_quote_ticks(id)`, `.unsubscribe_quote_ticks(id)`.
    """

    def __init__(self, *, client, gate: ExecutionGate, config: EngineConfig, clock=_utc_now) -> None:
        self._client = client
        self._gate = gate
        self._config = config
        self._now = clock
        self._journal_dir = Path(config.journal_dir)
        # The 00088 convention: the control-file tree sits beside the journal, not inside it.
        self._state_dir = Path(config.journal_dir).parent
        self._plan = None
        self._plan_cycle_ts: datetime | None = None
        self._index = 0
        self._active: _ActiveIntent | None = None

    # --- the gate ------------------------------------------------------------------------------

    def _evaluate(self, now: datetime) -> GateVerdict:
        """The ONE gate read. Every evaluation reaches the publish hook (D4's cadence ruling), so
        the gate's published state is seconds-fresh for as long as a plan is running and reverts to
        the between-cycles cadence the moment one is not."""
        verdict = self._gate.evaluate(now)
        _publish(verdict, now)
        return verdict

    # --- the chokepoint ------------------------------------------------------------------------

    def _submit(self, ctx: _ActiveIntent, order, params) -> str:
        """THE chokepoint: the only path from this repository to a live order.

        Takes no verdict and reads no stored one -- it evaluates the gate itself, first, so there is
        no holdable token to go stale between a caller's decision and the venue call. Then it writes
        the forensic row and only then submits, exactly once -- there is no retry on this path.

        Returns the intent's outcome: `"submitted"`, `"refused"` (no order exists) or `"ambiguous"`
        (the venue may hold one). Both non-submitted paths have already journaled and counted
        themselves; the caller decides what happens to the rest of the plan.
        """
        verdict = self._evaluate(self._now())
        if not _level_permits(verdict.level, ctx.intent):
            self._journal_intent(ctx.index, "refused", verdict.reasons)
            _inc_order("refused")
            return "refused"

        client_order_id = str(order.client_order_id)
        row = {
            "plan_id": self._plan.plan_id,
            "intent_index": ctx.index,
            "client_order_id": client_order_id,
            "intent": dict(ctx.raw_intent),
            "order": dict(ctx.order_payload or {}),
            "state": "submitting",
            "filled_qty": 0.0,
            "events": [],
        }
        try:
            append_submitted_row(self._journal_dir, self._plan_cycle_ts, row, verdict=verdict, evaluated_at=self._now())
        except Exception:
            logger.critical("write-ahead row for %s could not be stored -- refusing to submit", client_order_id, exc_info=True)
            if not self._journal_intent(ctx.index, "refused", ("exec ledger write failed",)):
                # Not even the refusal could be recorded: the ledger is down, so nothing may trade.
                logger.critical("the exec ledger is unavailable -- no order may be submitted while it stays down")
            _inc_order("refused")
            return "refused"

        ctx.client_order_id = client_order_id
        try:
            self._client.submit_order(order, params=params)
        except Exception:
            # Exactly one attempt: no retry. The row is already on disk saying `submitting`, which
            # is the honest state -- this process cannot tell whether the venue received the order,
            # and `submitting` is an OPEN state, so re-attach still finds a possibly-live order
            # (the `ambiguous` row state would hide it). Calling this "refused" would assert no
            # order exists, which is precisely what is unknown.
            logger.critical("submit of %s raised -- outcome unknown, the write-ahead row stands", client_order_id, exc_info=True)
            self._journal_intent(ctx.index, "ambiguous", ("submit raised -- venue outcome unknown",))
            _inc_order("ambiguous")
            return "ambiguous"
        _inc_order("submitted")
        return "submitted"

    # --- the timer -----------------------------------------------------------------------------

    def on_timer(self, now: datetime) -> None:
        try:
            now = _aware_utc(now)
            if self._plan is None:
                self._pickup(now)
            self._pump(now)
        except Exception:
            # Refusal by default: whatever broke, stop running this plan. Anything already resting
            # at the venue stays in the ledger as an open row for reconciliation to pick up.
            logger.exception("executor tick raised -- dropping the running plan")
            self._plan = None
            self._active = None
            self._index = 0

    def _pickup(self, now: datetime) -> None:
        path = exec_dir(self._state_dir) / PLAN_FILENAME
        try:
            os.lstat(path)
        except FileNotFoundError:
            return  # the cheap idle path: no gate read, no venue read, nothing published
        except OSError, ValueError:
            logger.warning("probe plan %s cannot be stat'd -- no pickup this tick", path, exc_info=True)
            return

        verdict = self._evaluate(now)
        cycle_ts = _boundary(now)

        try:
            plan = parse_plan(path.read_text())
        except (ProbePlanError, OSError) as exc:
            # An unreadable file cannot be journaled verbatim, so it is journaled as the refusal it
            # is -- and still deleted, or the next tick re-reads the same broken file forever.
            if self._journal_plan(
                cycle_ts, verdict, now, plan_id="unparseable", plan={}, disposition="refused", reasons=(str(exc),)
            ):
                self._delete(path)
            return

        try:
            state = venue_state_from_cache(self._client.cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing plan %s", plan.plan_id, exc_info=True)
            if self._journal_plan(
                cycle_ts, verdict, now, plan_id=plan.plan_id, plan=plan.raw, disposition="refused", reasons=("no venue truth",)
            ):
                self._delete(path)
            return

        # Live balances spell the currency `ZEUR` (the adapter's code, measured); the `EUR` fallback
        # covers a constructed state, and both absent reads 0.0, which refuses any margin intent.
        free_zeur = state.balances.get("ZEUR", 0.0) or state.balances.get("EUR", 0.0)
        reasons = plan_refusals(
            plan,
            now=now,
            ledgered=ledgered_plan_ids(self._journal_dir, now),
            max_plan_notional_eur=self._config.exec_max_plan_notional_eur,
            free_zeur=free_zeur,
        )
        intents = [
            {"index": i, "intent": raw, "outcome": "pending", "reasons": [], "filled_qty": 0.0}
            for i, raw in enumerate(plan.raw["intents"])
        ]
        # Journal FIRST, delete SECOND, run THIRD. A crash in between re-picks the file next tick,
        # where the now-ledgered plan_id refuses it and the delete still runs; only a filesystem
        # restore brings it back, straight into the TTL and dedup walls.
        if not self._journal_plan(
            cycle_ts,
            verdict,
            now,
            plan_id=plan.plan_id,
            plan=plan.raw,
            disposition="refused" if reasons else "accepted",
            reasons=reasons,
            intents=[] if reasons else intents,
        ):
            return
        self._delete(path)
        if reasons:
            logger.warning("probe plan %s refused: %s", plan.plan_id, "; ".join(reasons))
            return
        self._plan = plan
        self._plan_cycle_ts = cycle_ts
        self._index = 0

    def _pump(self, now: datetime) -> None:
        if self._plan is None:
            return
        self._evaluate(now)  # a plan is running: publish a fresh verdict on every tick
        if self._active is not None:
            self._poll(now)
            return
        while self._active is None and self._plan is not None:
            if self._index >= len(self._plan.intents):
                logger.info("probe plan %s has no intents left to run", self._plan.plan_id)
                self._plan = None
                return
            self._start_intent(now)

    def _poll(self, now: datetime) -> None:
        active = self._active
        if active.phase == "awaiting_quote" and now > active.quote_deadline:
            self._finish_active("refused", (f"no quote within {int(_QUOTE_WAIT.total_seconds())}s",))

    def _start_intent(self, now: datetime) -> None:
        """Always either arms `_active` or advances `_index` -- `_pump`'s loop depends on it."""
        plan = self._plan
        index = self._index
        intent = plan.intents[index]

        # The per-intent belt behind the plan-level wall: a submitted row for this key means the
        # order already exists, whatever this process remembers.
        if (plan.plan_id, index) in ledgered_intent_keys(self._journal_dir, now):
            logger.warning("intent %d of plan %s already has a submitted row -- not resubmitting", index, plan.plan_id)
            self._journal_intent(index, "already_ledgered", ())
            self._index += 1
            return

        verdict = self._evaluate(now)
        if not _level_permits(verdict.level, intent):
            self._refuse_intent(index, verdict.reasons)
            return

        try:
            state = venue_state_from_cache(self._client.cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing intent %d of plan %s", index, plan.plan_id, exc_info=True)
            self._refuse_intent(index, ("no venue truth",))
            return

        constraints = state.instruments.get(intent.symbol)
        if constraints is None:
            self._refuse_intent(index, (f"{intent.symbol} is absent from venue truth",))
            return

        instrument_id = InstrumentId.from_str(INSTRUMENT_IDS[intent.symbol])
        self._client.subscribe_quote_ticks(instrument_id)
        self._active = _ActiveIntent(
            index=index,
            intent=intent,
            raw_intent=plan.raw["intents"][index],
            instrument_id=instrument_id,
            constraints=constraints,
            phase="awaiting_quote",
            quote_deadline=now + _QUOTE_WAIT,
        )

    # --- quotes --------------------------------------------------------------------------------

    def on_quote(self, tick) -> None:
        try:
            active = self._active
            if active is None or active.phase != "awaiting_quote":
                return
            if str(getattr(tick, "instrument_id", "")) != str(active.instrument_id):
                return
            self._on_touch(active, tick)
        except Exception:
            logger.exception("executor quote handling raised -- refusing the intent")
            if self._active is not None:
                self._finish_active("refused", ("quote handling failed",))

    def _on_touch(self, active: _ActiveIntent, tick) -> None:
        intent = active.intent
        # Post-only: a buy joins the bid and a sell the ask. Crossing the spread would be taking.
        raw_touch = tick.bid_price if intent.side == "buy" else tick.ask_price
        try:
            touch = float(raw_touch)
        except TypeError, ValueError:
            touch = float("nan")
        if not math.isfinite(touch) or touch <= 0:
            self._finish_active("refused", (f"no usable touch price for {intent.symbol}",))
            return

        target_qty = intent.qty if intent.qty is not None else intent.notional_eur / touch
        try:
            sized = size_probe_order(target_qty, touch, active.constraints)
        except EngineError as exc:
            self._finish_active("refused", (str(exc),))
            return
        if isinstance(sized, BelowMinimum):
            self._finish_active("refused", (sized.reason,))
            return

        instrument = self._client.cache.instrument(active.instrument_id)
        if instrument is None:
            self._finish_active("refused", (f"{intent.symbol}: instrument not found in Cache",))
            return

        order = self._client.order_factory.limit(
            instrument_id=active.instrument_id,
            order_side=OrderSide.BUY if intent.side == "buy" else OrderSide.SELL,
            quantity=instrument.make_qty(sized.qty),
            price=instrument.make_price(sized.price),
            time_in_force=TimeInForce.GTC,
            post_only=True,
        )
        active.order_qty = sized.qty
        active.order_payload = {
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": sized.qty,
            "price": sized.price,
            "notional": sized.notional,
            "time_in_force": "GTC",
            "post_only": True,
            "leverage": intent.leverage,
        }
        params = {"leverage": intent.leverage} if intent.leverage is not None else None
        outcome = self._submit(active, order, params)
        if outcome == "ambiguous":
            self._drop_remainder_after_ambiguity(active)
            return
        if outcome == "refused":
            self._finish_active()
            return
        active.phase = "resting"

    # --- order events --------------------------------------------------------------------------

    def on_order_event(self, event) -> None:
        try:
            self._on_order_event(event)
        except Exception:
            # Bookkeeping, not a submission: log it and leave the row as it stands rather than
            # dropping a plan whose order may be live.
            logger.exception("executor order-event handling raised -- continuing")

    def _on_order_event(self, event) -> None:
        active = self._active
        if active is None or active.client_order_id is None:
            return
        if str(getattr(event, "client_order_id", "")) != active.client_order_id:
            return

        name = type(event).__name__
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)

        if name == "OrderAccepted":
            self._update_row(active, state="accepted", event=payload)
            active.phase = "resting"
            return

        if name == "OrderFilled":
            filled = float(getattr(event, "last_qty", 0.0) or 0.0)
            active.filled_qty += filled
            done = active.filled_qty >= active.order_qty
            self._update_row(active, state="filled" if done else "accepted", event=payload, add_filled_qty=filled)
            if done:
                self._finish_active("filled", (), active.filled_qty)
            return

        state = _TERMINAL_EVENT_STATES.get(name)
        if state is None:
            self._update_row(active, event=payload)  # recorded as evidence, no state claim
            return
        self._update_row(active, state=state, event=payload)
        self._finish_active(state, (str(reason),) if reason is not None else (), active.filled_qty)

    # --- journaling ----------------------------------------------------------------------------

    def _journal_plan(
        self,
        cycle_ts: datetime,
        verdict: GateVerdict,
        now: datetime,
        *,
        plan_id: str,
        plan: dict,
        disposition: str,
        reasons=(),
        intents=(),
    ) -> bool:
        entry = {
            "plan_id": plan_id,
            "received_at": now.isoformat(),
            "disposition": disposition,
            "reasons": list(reasons),
            "plan": plan,
            "intents": list(intents),
        }
        try:
            append_plan_entry(self._journal_dir, cycle_ts, entry, verdict=verdict, evaluated_at=now)
        except Exception:
            # Neither delete nor run: an unjournaled plan is an unrunnable plan.
            logger.critical("plan %s could not be journaled -- it will not be run", plan_id, exc_info=True)
            return False
        return True

    def _refuse_intent(self, index: int, reasons) -> None:
        """Refuse an intent that never became active -- nothing is subscribed yet, so unlike
        `_finish_active` there is nothing to unsubscribe."""
        logger.warning("intent %d of plan %s refused: %s", index, self._plan.plan_id, "; ".join(reasons))
        self._journal_intent(index, "refused", reasons)
        _inc_order("refused")
        self._index += 1

    def _journal_intent(self, index: int, outcome: str, reasons, filled_qty: float = 0.0) -> bool:
        try:
            update_plan_intent(
                self._journal_dir,
                self._plan_cycle_ts,
                self._plan.plan_id,
                index,
                outcome=outcome,
                reasons=tuple(reasons),
                filled_qty=filled_qty,
            )
        except Exception:
            logger.exception("intent %d of plan %s could not be journaled as %s", index, self._plan.plan_id, outcome)
            return False
        return True

    def _update_row(
        self, active: _ActiveIntent, *, state: str | None = None, event: dict | None = None, add_filled_qty: float = 0.0
    ) -> None:
        update_submitted_row(
            self._journal_dir,
            self._plan_cycle_ts,
            active.client_order_id,
            state=state,
            event=event,
            add_filled_qty=add_filled_qty,
        )

    def _finish_active(self, outcome: str | None = None, reasons=(), filled_qty: float = 0.0) -> None:
        """End the in-flight intent: unsubscribe, journal its outcome, and hand the tick to the next
        intent. `outcome=None` means `_submit` already journaled and counted this one -- it knows
        whether the order was refused or left ambiguous, and this does not."""
        active = self._active
        try:
            self._client.unsubscribe_quote_ticks(active.instrument_id)
        except Exception:
            logger.warning("unsubscribe failed for %s -- continuing", active.instrument_id, exc_info=True)
        if outcome is not None:
            self._journal_intent(active.index, outcome, reasons, filled_qty)
            if outcome == "refused":
                _inc_order("refused")
        self._active = None
        self._index += 1

    def _drop_remainder_after_ambiguity(self, active: _ActiveIntent) -> None:
        """An ambiguous submit ends the WHOLE plan, not just its intent (owner ruling).

        The order may be live at the venue, so the account's real position and free balance are
        unknown -- and the notional cap and margin floor that authorized every LATER intent in this
        plan were computed against a venue state that may no longer hold. Submitting the next one
        would be authorizing an order on unknown state, which is exactly what refusal by default
        forbids. Rung-1 plans carry one or two intents and the operator is attended, so the cost of
        stopping is a re-drop after reading the venue.

        `_submit` has already journaled the ambiguous intent and left its row `submitting`, which is
        an OPEN state -- reconciliation must keep seeing a possibly-live order.
        """
        try:
            self._client.unsubscribe_quote_ticks(active.instrument_id)
        except Exception:
            logger.warning("unsubscribe failed for %s -- continuing", active.instrument_id, exc_info=True)
        reason = f"not run -- intent {active.index} ended ambiguous, so the venue state this plan was authorized against is unknown"
        for index in range(active.index + 1, len(self._plan.intents)):
            self._journal_intent(index, "refused", (reason,))
            _inc_order("refused")
        logger.critical(
            "plan %s dropped after intent %d ended ambiguous -- %d later intent(s) will not run",
            self._plan.plan_id,
            active.index,
            len(self._plan.intents) - active.index - 1,
        )
        self._active = None
        self._plan = None
        self._index = 0

    def _delete(self, path: Path) -> None:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.critical(
                "probe plan %s could not be deleted -- it is already journaled, so the dedup wall refuses it next tick",
                path,
                exc_info=True,
            )
