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


def _as_price(raw) -> float | None:
    """A usable touch, or None. Anything non-numeric, non-finite or non-positive is not a price --
    and a tick that carries one is not a quote, so it neither prices an order nor counts as the
    liveness that holds the quote-silence guard open."""
    try:
        value = float(raw)
    except TypeError, ValueError:
        return None
    return value if math.isfinite(value) and value > 0 else None


def _level_permits(level: str, intent: ProbeIntent) -> bool:
    """An OPEN intent needs the full level; a CLOSE intent is permitted at reduce-only too -- the
    restart hold exists to let the engine flatten, not to trap it."""
    if intent.action == "close":
        return level in (GateLevel.REDUCE_ONLY, GateLevel.FULL)
    return level == GateLevel.FULL


@dataclass
class _ActiveIntent:
    """The one intent in flight. Mutable and process-local -- everything durable about it is the
    exec ledger's submitted row, which is written before the order exists.

    `filled` is cumulative across ALL of this intent's orders and `order_filled` across the live one
    only: every resubmission is sized `target_qty - filled`, because successive full-size orders
    would over-execute the intent by whatever the earlier ones already got. `target_qty` is the
    FIRST order's sized quantity, not the raw target -- a notional intent's raw target rarely lands
    on the lot step, and a remainder of one flooring residue would never terminate.
    """

    index: int
    intent: ProbeIntent
    raw_intent: dict
    instrument_id: InstrumentId
    constraints: InstrumentConstraints
    phase: str
    started_at: datetime
    quote_deadline: datetime
    timebox_at: datetime
    last_quote_at: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    reprices: int = 0
    ioc_attempts: int = 0
    filled: float = 0.0
    target_qty: float = 0.0
    order: object | None = None
    order_payload: dict | None = None
    client_order_id: str | None = None
    order_qty: float = 0.0
    order_filled: float = 0.0
    cancel_requested: bool = False
    falling_back: bool = False
    revoke_reasons: tuple[str, ...] = ()


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
        # intent index -> the EUR notional a `qty` intent only acquired at sizing time. Kept for the
        # running plan so a second disposal cumulates against the first one's real notional rather
        # than against the 0.00 the plan wall had to assume for it.
        self._resolved_notional: dict[int, float] = {}

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
        self._resolved_notional = {}

    def _pump(self, now: datetime) -> None:
        if self._plan is None:
            return
        # A plan is running: publish a fresh verdict on every tick -- and this ONE evaluation is
        # also what an order in flight is polled against, so a tick never reads the gate twice.
        verdict = self._evaluate(now)
        if self._active is not None:
            self._poll(now, verdict)
            return
        while self._active is None and self._plan is not None:
            if self._index >= len(self._plan.intents):
                logger.info("probe plan %s has no intents left to run", self._plan.plan_id)
                self._plan = None
                return
            self._start_intent(now)

    def _poll(self, now: datetime, verdict: GateVerdict) -> None:
        """The timer's whole authority over an in-flight intent. Only a RESTING order is revocable
        or time-boxable: a cancel is already outstanding in `cancelling`, and an IOC resolves at the
        venue within the tick rather than sitting there."""
        active = self._active
        if active.phase == "awaiting_quote":
            if now > active.quote_deadline:
                self._finish_active("refused", (f"no quote within {int(_QUOTE_WAIT.total_seconds())}s",))
            return
        if active.phase != "resting":
            return

        # The kill file, a disarm, the restart hold latching, and the venue leaving online all reach
        # here as a level this intent no longer clears -- one condition, read off the same verdict.
        if not _level_permits(verdict.level, active.intent):
            self._revoke(active, verdict.reasons)
            return
        if active.last_quote_at is not None and now - active.last_quote_at > _QUOTE_SILENCE:
            # Repricing against a stale touch is worse than not repricing at all.
            self._revoke(active, ("quote_silence",))
            return
        if now > active.timebox_at:
            active.cancel_requested = True
            # A rest-cancel drill must never execute: the time-box cancels it and stops there.
            active.falling_back = active.intent.mode != "rest-cancel"
            active.revoke_reasons = ("time box elapsed",)
            active.phase = "cancelling"
            self._cancel(active)

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
            started_at=now,
            quote_deadline=now + _QUOTE_WAIT,
            timebox_at=now + _TIME_BOX,
        )

    # --- quotes --------------------------------------------------------------------------------

    def on_quote(self, tick) -> None:
        try:
            active = self._active
            if active is None:
                return
            if str(getattr(tick, "instrument_id", "")) != str(active.instrument_id):
                return
            bid = _as_price(getattr(tick, "bid_price", None))
            ask = _as_price(getattr(tick, "ask_price", None))
            if bid is not None and ask is not None:
                # Both sides or neither: a reprice needs the near touch and the IOC fallback the
                # far one, and half a book is not a book to price either against.
                active.bid, active.ask = bid, ask
                active.last_quote_at = self._now()
            if active.phase == "awaiting_quote":
                self._first_submission(active)
        except Exception:
            logger.exception("executor quote handling raised -- refusing the intent")
            if self._active is not None:
                self._finish_active("refused", ("quote handling failed",))

    def _limit_price(self, active: _ActiveIntent) -> float | None:
        """The resting price for this intent's side and mode, or None when no usable touch is known.

        `execute` joins the touch -- a buy the bid, a sell the ask; crossing the spread would be
        taking. `rest-cancel` is a drill that must never fill, so it prices `_REST_CANCEL_OFFSET`
        away on the passive side instead: joining the touch can fill in the instant between the
        venue's acknowledgment and this process's cancel.
        """
        touch = active.bid if active.intent.side == "buy" else active.ask
        if touch is None:
            return None
        if active.intent.mode == "rest-cancel":
            return touch * (1 - _REST_CANCEL_OFFSET) if active.intent.side == "buy" else touch * (1 + _REST_CANCEL_OFFSET)
        return touch

    def _opposite_touch(self, active: _ActiveIntent) -> float | None:
        """What the marketable fallback is bounded by: a buy's ask, a sell's bid. A limit, always --
        a market order has no price bound at all, which is the one thing this path may not emit."""
        return active.ask if active.intent.side == "buy" else active.bid

    def _over_cap_reason(self, active: _ActiveIntent, target_qty: float, price: float) -> str | None:
        """D8's sizing-time half of the plan-notional cap, and the only place a `qty` intent meets
        it: `plan_refusals` had no price to convert its base quantity with, so it counted the intent
        as 0.00 EUR. There is no exclusion -- the disposal's real notional cumulates with the plan's
        declared ones. Checked on the PRE-floor target, which can only overstate the order.
        """
        if active.intent.qty is None:
            return None  # a notional intent was already summed, in EUR, at the plan wall
        notional = target_qty * price
        cap = self._config.exec_max_plan_notional_eur
        declared = sum(i.notional_eur or 0.0 for i in self._plan.intents)
        resolved = sum(value for index, value in self._resolved_notional.items() if index != active.index)
        total = declared + resolved + notional
        if total > cap:
            return f"plan notional {total:.2f} EUR exceeds the cap {cap:.2f} EUR"
        self._resolved_notional[active.index] = notional
        return None

    def _place(self, active: _ActiveIntent, target_qty: float, price: float, *, time_in_force, post_only: bool) -> tuple[str, str]:
        """Size, build and submit ONE order through the chokepoint. Returns
        `(result, detail)` where result is `_submit`'s outcome or the local `"below_minimum"` /
        `"error"` -- the caller owns what each means for the intent, because the same sizing failure
        is a refusal before the first order and a terminal partial after one has filled.
        """
        intent = active.intent
        try:
            sized = size_probe_order(target_qty, price, active.constraints)
        except EngineError as exc:
            return "error", str(exc)
        if isinstance(sized, BelowMinimum):
            return "below_minimum", sized.reason

        instrument = self._client.cache.instrument(active.instrument_id)
        if instrument is None:
            return "error", f"{intent.symbol}: instrument not found in Cache"

        order = self._client.order_factory.limit(
            instrument_id=active.instrument_id,
            order_side=OrderSide.BUY if intent.side == "buy" else OrderSide.SELL,
            quantity=instrument.make_qty(sized.qty),
            price=instrument.make_price(sized.price),
            time_in_force=time_in_force,
            post_only=post_only,
        )
        active.order = order
        active.order_qty = sized.qty
        active.order_filled = 0.0
        # A new order carries none of the previous one's in-flight state: a cancel ack arriving for
        # THIS order must not be read as the ack of the cancel that ended the last one.
        active.cancel_requested = False
        active.falling_back = False
        active.order_payload = {
            "symbol": intent.symbol,
            "side": intent.side,
            "qty": sized.qty,
            "price": sized.price,
            "notional": sized.notional,
            "time_in_force": "IOC" if time_in_force == TimeInForce.IOC else "GTC",
            "post_only": post_only,
            "leverage": intent.leverage,
        }
        params = {"leverage": intent.leverage} if intent.leverage is not None else None
        return self._submit(active, order, params), ""

    def _first_submission(self, active: _ActiveIntent) -> None:
        price = self._limit_price(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",))
            return
        target_qty = active.intent.qty if active.intent.qty is not None else active.intent.notional_eur / price
        over_cap = self._over_cap_reason(active, target_qty, price)
        if over_cap is not None:
            self._finish_active("refused", (over_cap,))
            return

        result, detail = self._place(active, target_qty, price, time_in_force=TimeInForce.GTC, post_only=True)
        if result in ("below_minimum", "error"):
            self._finish_active("refused", (detail,))
            return
        if result == "ambiguous":
            self._drop_remainder_after_ambiguity(active)
            return
        if result == "refused":
            self._finish_active()
            return
        active.target_qty = active.order_qty
        active.phase = "resting"

    def _reprice(self, active: _ActiveIntent) -> None:
        """Both crossing surfaces funnel here: the venue's synchronous post-only rejection and its
        accept-then-cancel. The counter counts RESUBMISSIONS -- the first submission was never a
        reprice -- so `_MAX_REPRICES` of them happen and the next one refuses."""
        active.reprices += 1
        if active.reprices > _MAX_REPRICES:
            self._finish_active("unfilled", ("reprice budget exhausted",), active.filled)
            return
        price = self._limit_price(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",), active.filled)
            return
        self._resubmit(active, price, time_in_force=TimeInForce.GTC, post_only=True, next_phase="resting")

    def _fallback(self, active: _ActiveIntent) -> None:
        """The bounded marketable fallback: at most `_MAX_IOC_ATTEMPTS` limit-IOC orders at the
        opposite touch, each sized to what is still owed. The budget spent unfilled is a terminal
        `unfilled` for the operator, never a further attempt."""
        if active.ioc_attempts >= _MAX_IOC_ATTEMPTS:
            self._finish_active("unfilled", ("the bounded fallback did not fill",), active.filled)
            return
        active.ioc_attempts += 1
        price = self._opposite_touch(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",), active.filled)
            return
        self._resubmit(active, price, time_in_force=TimeInForce.IOC, post_only=False, next_phase="ioc")

    def _resubmit(self, active: _ActiveIntent, price: float, *, time_in_force, post_only: bool, next_phase: str) -> None:
        """Every order after the first, sized to `target_qty - filled`. Quantity conservation is the
        whole point: a resubmission at the intent's full size would re-buy what the earlier orders
        already got. A remainder the venue cannot accept is a terminal `partial` -- a legitimate end
        state -- never an order that would only be rejected.
        """
        remainder = active.target_qty - active.filled
        result, detail = self._place(active, remainder, price, time_in_force=time_in_force, post_only=post_only)
        if result == "below_minimum":
            self._finish_active("partial", (detail,), active.filled)
            return
        if result == "error":
            self._finish_active("refused", (detail,), active.filled)
            return
        if result == "ambiguous":
            self._drop_remainder_after_ambiguity(active)
            return
        if result == "refused":
            self._finish_active(None, (), active.filled)
            return
        active.phase = next_phase

    def _revoke(self, active: _ActiveIntent, reasons) -> None:
        """Pull the resting order and stop: NO fallback follows a revocation. Whatever revoked it --
        the kill file, a disarm, the hold, the venue going offline, a dead quote feed -- is a reason
        not to be at the venue at all, and a marketable IOC would be the most aggressive order this
        path can emit. Terminal on the cancel ack, where the row is written."""
        active.cancel_requested = True
        active.falling_back = False
        active.revoke_reasons = tuple(reasons)
        active.phase = "cancelling"
        self._cancel(active)

    def _cancel(self, active: _ActiveIntent) -> None:
        try:
            self._client.cancel_order(active.order)
        except Exception:
            # No retry and no fallback: the order may still rest, and the intent stays in
            # `cancelling` -- an open ledger row for reconciliation, and no further order.
            logger.critical("cancel of %s raised -- the order may still rest at the venue", active.client_order_id, exc_info=True)

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
            _inc_order("accepted")
            active.phase = "resting"
            if active.intent.mode == "rest-cancel":
                # The drill's whole shape: rest, be acknowledged, come straight back off the book.
                active.cancel_requested = True
                active.phase = "cancelling"
                self._cancel(active)
            return

        if name == "OrderFilled":
            self._on_fill(active, event)
            return

        if name == "OrderRejected":
            self._on_rejected(active, str(reason), payload, due_post_only=bool(getattr(event, "due_post_only", False)))
            return

        if name == "OrderDenied":
            # A LOCAL refusal -- nothing reached the venue, so there is nothing ambiguous about it.
            self._update_row(active, state="rejected", event=payload)
            _inc_order("rejected")
            self._finish_active("rejected", (str(reason),) if reason is not None else (), active.filled)
            return

        if name in ("OrderCanceled", "OrderExpired"):
            self._on_cancel_ack(active, payload)
            return

        self._update_row(active, event=payload)  # recorded as evidence, no state claim

    def _on_rejected(self, active: _ActiveIntent, reason: str, payload: dict, *, due_post_only: bool) -> None:
        """Three verdicts, and telling them apart is the whole safety of this branch.

        A post-only rejection is the venue saying the touch moved -- the order does not exist, so
        repricing it is safe. A Kraken error code is a positive verdict on the same terms, and one
        this process must not argue with. ANYTHING ELSE is not a verdict at all: the installed
        adapter maps any submit failure onto a rejection, so the order may be live at the venue --
        no resubmission, no fallback, and the plan halts until an open-orders re-read says what
        actually reached it.
        """
        if due_post_only or _POST_ONLY_MARKER in reason:
            self._update_row(active, state="rejected", event=payload)
            _inc_order("rejected")
            self._reprice(active)
            return
        if any(marker in reason for marker in _KRAKEN_ERROR_MARKERS):
            self._update_row(active, state="rejected", event=payload)
            _inc_order("rejected")
            self._finish_active("rejected", (reason,), active.filled)
            return
        self._update_row(active, state="ambiguous", event=payload)
        _inc_order("ambiguous")
        self._journal_intent(active.index, "ambiguous", (reason,), active.filled)
        self._drop_remainder_after_ambiguity(active)

    def _on_cancel_ack(self, active: _ActiveIntent, payload: dict) -> None:
        """A cancel WE asked for writes its row terminal here -- the mid-rest revoke, the time-box
        cancel and the rest-cancel drill alike -- before anything decides what the intent becomes.
        One that we did NOT ask for is the venue's own doing: the accept-then-venue-cancel crossing
        surface while resting, or an IOC's unfilled remainder coming back.
        """
        if active.cancel_requested:
            self._update_row(active, state="canceled", event=payload)
            _inc_order("canceled")
            if active.falling_back:
                self._fallback(active)
                return
            if active.intent.mode == "rest-cancel":
                self._finish_active("rest_cancel_ok" if active.filled == 0.0 else "partial", (), active.filled)
                return
            index = active.index
            self._finish_active("revoked", active.revoke_reasons, active.filled)
            self._halt_plan(index, f"not run -- intent {index} was revoked mid-flight")
            return

        if active.phase == "ioc":
            self._update_row(active, state="venue_canceled", event=payload)
            self._fallback(active)
            return
        self._update_row(active, state="venue_canceled", event=payload)
        _inc_order("venue_canceled")
        self._reprice(active)

    def _on_fill(self, active: _ActiveIntent, event) -> None:
        qty = float(event.last_qty)
        active.filled += qty
        active.order_filled += qty
        payload = {
            "event": "fill",
            "at": self._now().isoformat(),
            "qty": qty,
            "px": float(event.last_px),
            "fee": float(event.commission),
            "fee_currency": event.commission.currency.code,
            "liquidity": str(event.liquidity_side),
            "trade_id": str(event.trade_id),
        }
        order_done = active.order_filled >= active.order_qty
        self._update_row(active, state="filled" if order_done else "accepted", event=payload, add_filled_qty=qty)
        if order_done:
            _inc_order("filled")
        if active.target_qty - active.filled <= 0:
            self._finish_active("filled", (), active.filled)
        # A partial on a resting GTC keeps resting: the remainder is still working at the touch.

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
        active.phase = "done"
        self._active = None
        self._index += 1

    def _halt_plan(self, from_index: int, reason: str) -> None:
        """Stop the plan after `from_index`: journal every later intent as refused, naming why, and
        drop the running plan. The ledger, not this process's memory, is what says they never ran."""
        for index in range(from_index + 1, len(self._plan.intents)):
            self._journal_intent(index, "refused", (reason,))
            _inc_order("refused")
        self._active = None
        self._plan = None
        self._index = 0

    def _drop_remainder_after_ambiguity(self, active: _ActiveIntent) -> None:
        """An ambiguous submit ends the WHOLE plan, not just its intent (owner ruling).

        The order may be live at the venue, so the account's real position and free balance are
        unknown -- and the notional cap and margin floor that authorized every LATER intent in this
        plan were computed against a venue state that may no longer hold. Submitting the next one
        would be authorizing an order on unknown state, which is exactly what refusal by default
        forbids. Rung-1 plans carry one or two intents and the operator is attended, so the cost of
        stopping is a re-drop after reading the venue.

        The ambiguous intent itself is already journaled when this is reached -- by `_submit` for a
        transport failure (leaving its row `submitting`, an OPEN state reconciliation must keep
        seeing) or by `_on_rejected` for an unclassifiable rejection.
        """
        try:
            self._client.unsubscribe_quote_ticks(active.instrument_id)
        except Exception:
            logger.warning("unsubscribe failed for %s -- continuing", active.instrument_id, exc_info=True)
        logger.critical(
            "plan %s dropped after intent %d ended ambiguous -- %d later intent(s) will not run",
            self._plan.plan_id,
            active.index,
            len(self._plan.intents) - active.index - 1,
        )
        self._halt_plan(
            active.index,
            f"not run -- intent {active.index} ended ambiguous, so the venue state this plan was authorized against is unknown",
        )

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
