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
exception has no safe direction. The one thing that is NOT a refusal is an outcome the venue never
established -- that is `ambiguous`, and saying "refused" there would be a claim this process cannot
make. An ambiguous intent's ROW says `ambiguous` too, which is one of
`execledger._OPEN_ORDER_STATES`: the record has to keep pointing at a possibly-live order.

Every ledger scanner call site is handed an aware-UTC `now` (`_aware_utc`): `execledger._day_dirs`
takes its two-day window from `now.date()`, so a caller-tz `now` would slide the dedup window off
the day the records are actually filed under.
"""

from __future__ import annotations

import asyncio
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nautilus_trader.common import SocketState
from nautilus_trader.model import (
    AccountId,
    AccountType,
    ClientOrderId,
    InstrumentId,
    OrderSide,
    OrderStatus,
    TimeInForce,
    Venue,
    VenueOrderId,
)

from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.execgate import KILL_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
from cli.engine.execledger import (
    _OPEN_ORDER_STATES,
    FLAT_TOLERANCE,
    append_plan_entry,
    append_submitted_row,
    closed_submitted_rows,
    exec_records_through,
    ledgered_intent_keys,
    ledgered_plan_ids,
    open_submitted_rows,
    pending_plan_intents,
    update_plan_intent,
    update_submitted_row,
)
from cli.engine.feeders import CycleStages
from cli.engine.instruments import EUR_CODES, INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order
from cli.engine.journal import CycleRecord, from_json, require_comparable_cycle_ts, validate_record
from cli.engine.probeplan import MODES, PLAN_FILENAME, ProbeIntent, ProbePlanError, parse_plan, plan_refusals
from cli.engine.store import BASKET
from cli.engine.tracking import extract_fills, realized_drift
from cli.engine.venueledger import read_venue_record, validate_venue_record
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
# A liveness bound on this process's OWN bookkeeping, not a trading behaviour: how long a cancel or
# an IOC may sit without the venue answering either way. Past it the intent is ambiguous, because an
# unanswered order is exactly an unknown venue outcome -- and without the bound the intent parks
# forever, which leaves `self._plan` non-None and makes the executor ignore every later plan file
# until a restart: a dead engine that looks alive.
_ACK_WAIT = timedelta(seconds=30)
_MAX_REPRICES = 5
_MAX_IOC_ATTEMPTS = 3
_REST_CANCEL_OFFSET = 0.05
# The overfill trips compare a SUM of per-fill floats against a single sized float, so an exactly
# complete order routinely lands an ulp over what it asked for. One ulp is not an overfill. Nothing
# tradeable hides under this either -- the smallest quantity any leg can express is its lot step,
# orders of magnitude above it.
_OVERFILL_TOLERANCE = 1e-12
# What the in-process backstop journals when it refuses. The kill FILE is the durable latch and the
# gate's own input; this is what is left when the file could not be written, and it says so.
_TRIPPED_REFUSAL = "the kill switch tripped in this process"
# The write-once record of when this engine's realized series began, in the control-file directory
# beside the arm and kill files. Named HERE and not in `execgate` because it is not a gate input:
# nothing about it can permit or refuse an order. It exists because `held` is cumulative from the
# first fill ever while the journal prune deletes whole day-dirs at a fixed retention -- so once the
# day holding the first fill ages out, the journal alone can no longer tell "this engine has always
# tracked its targets" from "everything it bought before the horizon was deleted", and those two
# read as 46 bps and 298 bps against the same 120 bps band. Write-once, and only ever read to
# DISAGREE and refuse: unlike a rolling checkpoint, a stale value here cannot reinforce itself into
# a wrong `held`, it can only stop a week from being scored.
FIRST_FILL_FILE = "first-fill"
_KRAKEN_ERROR_MARKERS = ("EOrder:", "EGeneral:", "EAccount:")
_POST_ONLY_MARKER = "POST_ONLY_REJECTED:"
# The terminal order events the execution engine can MINT rather than receive. Past
# `inflight_check_retries` it stops waiting on an unanswered in-flight order and publishes one of
# these itself, carrying `reconciliation=True`. `OrderFilled` carries the same flag and is
# deliberately absent -- `_on_order_event` says why.
#
# `OrderFillVoided` carries it too and is absent for a different reason: it cannot be dispatched to
# a strategy here at all. The only route to one at this venue is the mass-status reconciliation the
# node runs before it starts the trader, so no handler is subscribed when it publishes; what reaches
# this engine is the venue order the library already lowered, and `_reconcile_finished_rows` is what
# reads it (spec 00100 D16).
_RECONCILED_TERMINALS = frozenset({"OrderRejected", "OrderCanceled", "OrderExpired"})
# What an ADOPTED order's row writes as its state, on BOTH paths that write one -- the startup
# reconciliation and the live external stream -- taken from `execledger._ROW_STATES`' existing names
# rather than minting one.
#
# Keyed on the order's own status, never on an event class name, and that is the whole point: the
# library's closed statuses are a finite declared set, so this map can be PROVEN total over them and
# is; a class name is an open string space where no such proof is even expressible. It also reaches
# what no event could -- the commonest closed-while-down shape is a cancel with zero fills, which
# publishes no event this process is alive to hear and leaves no quantity delta to notice it by.
#
# A status outside the map leaves the row's state untouched rather than minting one, since `_store`
# refuses a state outside `_ROW_STATES` and a raise here would cost the caller its pass. The open
# statuses fall through that way on purpose: an order the venue REFUSED to move -- a rejected
# cancel, a stale ack the state machine declined -- is still resting, and its row has to keep
# pointing at a possibly-live order.
#
# `canceled` makes no we-requested claim -- nothing here can tell a venue cancel from one this
# engine sent -- and `VOIDED`, the venue undoing an order's fills, reads `venue_canceled` for the
# reason `EXPIRED` does: the venue ended it and this engine did not ask.
_ADOPTED_TERMINAL_STATES = {
    OrderStatus.FILLED: "filled",
    OrderStatus.CANCELED: "canceled",
    OrderStatus.EXPIRED: "venue_canceled",
    OrderStatus.VOIDED: "venue_canceled",
    OrderStatus.REJECTED: "rejected",
    OrderStatus.DENIED: "rejected",
}

_H4 = 4
# What a complete ISO week holds -- derived, not the literal 42, so the two halves of the sentence
# cannot drift apart.
_WEEK_BOUNDARIES = 7 * (24 // _H4)
# The MODEL's key space: the ten EUR bases. `final_targets` is symbol-keyed TWELVE (the two /BTC
# legs ride in it at 0.0) while a journaled `closes` is base-keyed TEN, so a record's targets are
# contracted to these before any drift arithmetic -- `drift_bps` indexes closes by the key it finds
# in the targets, and handed the raw record it raises KeyError on the first /EUR symbol. Taken from
# BASKET so this and `tracking.extract_fills` are provably the same ten.
_MODEL_BASES = frozenset(symbol.split("/")[0] for symbol in BASKET if symbol.endswith("/EUR"))
# What the tracking trip publishes about the most recently closed week. The alphabet starts at 1 on
# purpose: this gauge is registered on first use, and a 0 -- eager or accidental -- would render as
# a legitimate reading on the board rather than as the absence it is.
# How stale a candidate may be and still be minted as this engine's birth. On the healthy path the
# record lands at the FIRST boundary after the first fill -- hours, not days -- so anything much
# older is a reconstruction from whatever the journal still holds. An order of magnitude under the
# journal's 60-day retention, so a fill old enough for its own head to have been pruned can never
# fall inside it; an order over the 4-hourly cadence, so a converge window or a weekend outage
# still mints normally.
_BIRTH_MINT_WINDOW = timedelta(days=7)
_TRACKING_DISARMED = 1
_TRACKING_UNSCORED = 2
_TRACKING_WITHIN_BAND = 3
_TRACKING_BREACHED = 4

_VENUE = Venue("KRAKEN")
# The instrument-id -> symbol direction, for labelling a fill's metric. Inverted from the ratified
# map rather than string-split off the id, so an id this engine never ratified raises instead of
# inventing a label.
_SYMBOL_BY_INSTRUMENT_ID = {instrument_id: symbol for symbol, instrument_id in INSTRUMENT_IDS.items()}
# The one symbol a traded coin's spot balance is counted under by the venue's holdings read, its EUR pair, so a base
# with two pairs is counted once.
_SPOT_SYMBOL_BY_BASE = {symbol.split("/")[0]: symbol for symbol in INSTRUMENT_IDS if symbol.endswith("/EUR")}
# The startup pass's one read of the venue's orders runs on the node's main thread, so this bound is
# also the longest the pass can hold that thread. The client's own request timeout is no bound: it
# retries with backoff underneath it.
_VENUE_READ_TIMEOUT_SECONDS = 30.0
# How far before the earliest row's boundary that read reaches. A row's order is submitted after the
# boundary it is filed under; the margin covers clock skew against the venue, not a real gap.
_VENUE_READ_MARGIN = timedelta(hours=1)
# How many ticks the re-read pass may fail to read the venue before it stops asking: the sockets'
# return says the host's network is back, not that Kraken's REST edge answers yet, and a pass that
# asked on every tick until it did would be the retry storm the engine runbook's socket section
# forbids. Past the budget the rows keep their state and the line names the hand cancel.
_REREAD_ATTEMPTS = 3
# The idle cadence the gate is re-evaluated and its readings republished at, against the kill-switch
# rule's `for: 5m`: a refresh, a scrape and the rule's evaluation are a minute each at most, so a
# switch removed on an idle engine reaches the rule within three minutes, and one removed inside the
# first two minutes of the rule's pending period pages no one. While a plan runs the tick evaluates
# anyway. The refresh moves no heartbeat: `_ExecGauges.update`'s `heartbeat` says why.
_GATE_REFRESH = timedelta(seconds=60)
# Why a row that names no venue order cannot be matched after a restart: written into the row as the
# `what` of its `ambiguous` event, and compared there so a later restart does not append it again.
_NO_VENUE_ORDER_ID = "no Kraken order id is recorded for it, so a restart cannot match it to a venue order"

# Module-level, None-safe, installed by command.run() -- the `cycle.set_metrics_sink` pattern. Left
# unset (the default), every call below is a no-op, so a one-shot subcommand or a test that never
# installs them runs unaffected.
_publish_verdict = None
_metrics = None


def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None:
    """Install (or clear, with the defaults) the executor's telemetry hooks: `publish_verdict` is
    called `(verdict, evaluated_at=..., heartbeat=...)` after EVERY gate evaluation, `heartbeat`
    False on the idle refresh alone, `metrics` is an object with
    `inc_order(outcome)`, `inc_external(disposition)`, `inc_fill(liquidity, fee_eur)`,
    `set_position(symbol, qty)` and `set_realized(value)` (`command._ExecutionMetrics`). Neither can
    affect an order -- both are wrapped."""
    global _publish_verdict, _metrics
    _publish_verdict = publish_verdict
    _metrics = metrics


def _publish(verdict: GateVerdict, evaluated_at: datetime, *, heartbeat: bool = True) -> None:
    if _publish_verdict is None:
        return
    try:
        _publish_verdict(verdict, evaluated_at=evaluated_at, heartbeat=heartbeat)
    except Exception:
        logger.exception("executor verdict hook raised -- continuing")


def _inc_order(outcome: str) -> None:
    if _metrics is None:
        return
    try:
        _metrics.inc_order(outcome)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")


def _set_resting_age(mode: str, seconds: float) -> None:
    if _metrics is None:
        return
    try:
        _metrics.set_resting_age(mode, seconds)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")


def _inc_external(disposition: str) -> None:
    if _metrics is None:
        return
    try:
        _metrics.inc_external(disposition)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")


def _set_tracking_state(state: int) -> None:
    if _metrics is None:
        return
    try:
        _metrics.set_tracking_state(state)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")


def _liquidity(side) -> str:
    """The venue's own NAME for a fill's liquidity side -- `LiquiditySide.name`, so the forensic row
    and the metric label both read `MAKER`/`TAKER`/`NO_LIQUIDITY_SIDE` rather than a number.

    Anything the enum cannot name is recorded verbatim and logged: this sits on the write-ahead path
    where a raise costs the fill its row, so an unnameable side is never allowed to become an
    exception. `tracking.py` refuses a liquidity outside the venue's own names downstream, where a
    refusal is affordable."""
    name = getattr(side, "name", None)
    if isinstance(name, str):
        return name
    logger.warning("fill carries an unrecognisable liquidity side %r -- recording it verbatim", side)
    return str(side)


def _fee_eur(commission) -> float | None:
    """One fill's commission in EUR, or `None` when it is denominated in anything else.

    A fee is NEVER summed across currencies: the counter this feeds is EUR by name, and a `/BTC`
    leg's BTC-denominated commission added to it would be a number with no unit. Converting one
    needs the BTC/EUR close (`cli.engine.instruments.fx_eur_notional`, the one proven conversion),
    which no fill event carries -- so the honest answer here is "not a EUR fee", logged."""
    code = getattr(getattr(commission, "currency", None), "code", None)
    if code not in EUR_CODES:
        logger.warning("fill commission is denominated in %s, not EUR -- it is left out of the EUR fee total", code)
        return None
    return float(commission)


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


def _spot_balance(balances: dict, base: str) -> float:
    """What the venue record says is held of `base`, or 0.0 when no spelling of it is present: a
    code is `base`'s when `resolve_base` maps it there, the rule `read_venue_holdings` reads the
    balances by, so Kraken's `XDG` is DOGE and `XBT` BTC. Raises on a present-but-unreadable value --
    the caller turns that into a refusal, because a balance this process cannot parse is not a
    balance it may reason about."""
    from cli.engine.flatten import resolve_base

    bases = frozenset((base,))
    for code, value in balances.items():
        if resolve_base(code, bases) == base:
            return float(value)
    return 0.0


def _ordered_qty(row: dict) -> float:
    """What the ledger says an order was submitted for -- the only figure the per-order overfill
    trip may trust, because an order a PREVIOUS process placed is knowable no other way. A row
    carrying no readable qty reads 0.0, so any fill on it trips: a fill this process cannot bound is
    exactly the divergence the trip exists for, and a row shaped like that is not one to reason
    from."""
    try:
        return float(row.get("order", {}).get("qty"))
    except AttributeError, TypeError, ValueError:
        return 0.0


def restored_fill_state(order) -> str:
    """How far a restored order has filled, read off `filled_qty` against `quantity` and never off its
    status: reconciliation appends `OrderAccepted(reconciliation=True)` to a partially filled restored
    order, since Kraken's `open` maps to ACCEPTED whatever `vol_exec` says, so the status reads open
    where the fills say partial."""
    filled = float(order.filled_qty)
    if filled >= float(order.quantity) - _OVERFILL_TOLERANCE:
        return "filled"
    return "partial" if filled > _OVERFILL_TOLERANCE else "open"


def _minted_terminal(order) -> bool:
    """Whether `order` was closed by a terminal the execution engine minted rather than received: it
    is closed and an event in its history is one of `_RECONCILED_TERMINALS` carrying the
    `reconciliation` flag -- the set the two minted arms key on; an `OrderFillVoided` carries the
    flag from the venue's own report and is not one. The history, not the last event: the state
    machine refuses a venue's later cancel ack of an order already closed but applies a later fill,
    which leaves a whole fill FILLED and a partial one CANCELED with `last_event` `OrderFilled`, so a
    last-event test would drop from the re-read pass the maker order that part-filled during the
    cut, the one it exists for. A stand-in without those attributes reads as not minted."""
    if order is None or not bool(getattr(order, "is_closed", False)):
        return False
    events = getattr(order, "events", None)
    return any(
        type(event).__name__ in _RECONCILED_TERMINALS and bool(getattr(event, "reconciliation", False))
        for event in (events() if callable(events) else ())
    )


def _unread_what(venue_order_id: str) -> str:
    """The `what` of the `ambiguous` mark on a row whose txid (`_read_id`) the venue read does not return."""
    return f"the venue's order read has no order {venue_order_id}"


def _mark_what(row: dict, venue_order_id: str | None) -> str:
    """The `what` of `_mark_unmatched`'s mark on `row` read by `venue_order_id`, the executor's `_read_id`."""
    return _unmatchable_what(row) if venue_order_id is None else _unread_what(venue_order_id)


def _marked_unmatched(row: dict, what: str) -> bool:
    """Whether `row` carries `_mark_unmatched`'s `ambiguous` event for `what`. The strand's `ambiguous`
    event carries another `what`."""
    return any(isinstance(e, dict) and e.get("type") == "ambiguous" and e.get("what") == what for e in row.get("events") or ())


def _venue_order_id_of(order_or_event) -> str | None:
    venue_order_id = getattr(order_or_event, "venue_order_id", None)
    return None if venue_order_id is None else str(venue_order_id)


def _row_venue_order_ids(row: dict) -> set[str]:
    return {
        event["venue_order_id"]
        for event in row.get("events") or ()
        if isinstance(event, dict) and isinstance(event.get("venue_order_id"), str) and event["venue_order_id"]
    }


def _row_venue_order_id(row: dict) -> str | None:
    """The Kraken txid this row's order was accepted under, read off the row's own events: the
    acceptance, or a fill where no acceptance reached the ledger.

    None when no event carries one, and None when two disagree: a row naming two venue orders vouches
    for neither, so it is handled as a row that names none, and `_unmatchable_what` says which of the
    two it is."""
    found = _row_venue_order_ids(row)
    return next(iter(found)) if len(found) == 1 else None


def _unmatchable_what(row: dict) -> str:
    """The `what` of the `ambiguous` mark on a row the executor's `_read_id` gives no txid. Sorted, so a
    later restart writes the same text and `_mark_unmatched` finds its mark already there."""
    found = sorted(_row_venue_order_ids(row))
    if len(found) < 2:
        return _NO_VENUE_ORDER_ID
    return (
        f"its events record {len(found)} different Kraken order ids ({', '.join(found)}), so a restart cannot tell "
        "which venue order is its own"
    )


def _row_label(row: dict, venue_order_id: str | None) -> str:
    """How a log line or a kill reason names a row's order: the id this engine keys it by, and the
    txid an operator finds it under on Kraken's own pages when the row recorded one."""
    own = row["client_order_id"]
    return own if venue_order_id is None else f"{own} (Kraken {venue_order_id})"


def _log_resting_outside_the_cache(label: str, report) -> None:
    """A venue report stands in for a Cache order only when the Cache holds none under the row's
    ids, so a report that is not terminal names an order resting at Kraken that startup
    reconciliation dropped (`_cancel_resting` says how). Every cancel this process can issue goes
    through the Cache, so neither the startup pass nor a kill trip reaches it, and the operator is
    the only one who can."""
    if report.order_status in _ADOPTED_TERMINAL_STATES:
        return
    logger.critical(
        "ledgered order %s rests at Kraken (%s) but this process's Cache does not hold it, so neither the startup "
        "pass nor a kill trip can cancel it -- cancel it by hand on Kraken's open-orders page",
        label,
        report.order_status.name,
    )


def read_venue_orders(since: datetime, *, base_url: str | None = None) -> list:
    """Every order the venue reports open, or closed since `since`, as the adapter's
    `OrderStatusReport`s: the startup pass's only source for an order the Cache cannot hold. The
    startup reconciliation reads open orders only, and nothing on the strategy's surface reaches the
    execution client's closed-order read, so this is a bare HTTP client beside that one, on the same
    trade credentials -- the construction `zcrypto engine flatten` uses. `base_url` is None on the
    engine, which is the venue's own.

    A second client on one key is a nonce hazard: the adapter serialises signed requests per client,
    so this client's can reach the venue out of order against the execution client's, and one of them
    is answered `Invalid nonce`. The startup pass therefore makes this read once, before this process
    has sent anything -- before its own cancels, and no plan is picked up before the pass has run --
    and never retries it; the re-read pass reads again on a tick with no intent live and no order
    of this process in flight in the Cache's terms (`_nothing_in_flight`), and `cancel_venue_order`
    follows it on the same terms. What that gate cannot see is the execution client's own signed
    token request while its socket is still reconnecting: a collision there costs the library one
    reconnect attempt or this pass one try, and the library's retry of an `Invalid nonce` is
    unmeasured.

    The listing is cached into the client first because the order read resolves every row through
    that cache and its altname index: an open order it cannot resolve fails the whole read, and a
    closed one it cannot resolve is skipped. `asyncio.run` needs no event loop running on the calling
    thread: the node runs the strategy's timer callbacks on its main thread, with no asyncio loop
    running there. If that ever changes, this raises and the caller fails closed. Anything short of a
    complete answer inside `_VENUE_READ_TIMEOUT_SECONDS` raises."""
    # Imported here rather than at the top: node.py imports this module.
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        for instrument in await client.request_instruments() or ():
            client.cache_instrument(instrument)
        return await client.request_order_status_reports(AccountId(_ACCOUNT_ID), start=since, open_only=False)

    return list(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)) or ())


def read_venue_fills(since: datetime, *, base_url: str | None = None) -> list:
    """The venue's own fills since `since`, as the adapter's `FillReport`s from Kraken's trade history, on
    a client of its own (`_bare_client`) and on `read_venue_orders`' terms: the withdrawal check's second
    source (spec 00120 D19), whose reason `_trades_cover` states. A timeout past
    `_VENUE_READ_TIMEOUT_SECONDS` raises, and an answer of None reads as no fills, which leaves the trip
    standing."""
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        for instrument in await client.request_instruments() or ():
            client.cache_instrument(instrument)
        return await client.request_fill_reports(AccountId(_ACCOUNT_ID), start=since)

    return list(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)) or ())


def cancel_venue_order(venue_order_id: str, instrument_id: str, *, base_url: str | None = None) -> None:
    """Cancel one order at the venue by its txid, on a client of its own (`_bare_client`) and on
    `read_venue_orders`' terms: the re-read pass's cancel of an order the Cache holds closed by a
    terminal this engine minted, which the strategy handle refuses to cancel
    (`Cannot cancel order: state is ...`, sent nowhere). The listing is cached first because the client
    resolves the pair through it. Returns on the venue's answer without reading its `count` --
    `{"count": 0}` and `{"count": 1}` return alike, which the loopback cases pin -- and raises on a
    refusal the venue phrases as an error, or on anything short of an answer inside
    `_VENUE_READ_TIMEOUT_SECONDS`. Which of the two Kraken gives for a txid already closed is
    unmeasured; drill F2's record reads it."""
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _cancel():
        for instrument in await client.request_instruments() or ():
            client.cache_instrument(instrument)
        await client.cancel_order(
            AccountId(_ACCOUNT_ID), InstrumentId.from_str(instrument_id), venue_order_id=VenueOrderId(venue_order_id)
        )

    asyncio.run(asyncio.wait_for(_cancel(), timeout=_VENUE_READ_TIMEOUT_SECONDS))


def _bare_client(base_url: str | None):
    """The bare `KrakenSpotHttpClient` the venue functions beside this one build, on the trade
    credentials -- the construction `zcrypto engine flatten` uses -- refused before it is built when
    the environment lacks them. `base_url` is None on the engine, which is the venue's own."""
    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    # Imported here rather than at the top: node.py imports this module.
    from cli.engine.node import _credentials

    credentials = _credentials()
    if credentials is None:
        raise EngineError("the trade credentials are not in this environment")
    api_key, api_secret = credentials
    return KrakenSpotHttpClient(api_key=api_key, api_secret=api_secret, base_url=base_url)


def read_venue_holdings(*, base_url: str | None = None) -> dict[str, float]:
    """What the account holds under every `INSTRUMENT_IDS` symbol, from the venue's own two reads on a
    client each call builds for itself (`_bare_client`): each margin position, signed by its side, under
    its instrument, and each traded coin's spot balance -- its total, the part held against a resting
    order included -- under the coin's EUR pair (`_SPOT_SYMBOL_BY_BASE`), so a base is counted once and
    `ETH/BTC` carries its margin positions alone. The balances are read beside the positions because a
    settled margin position is a spot lot the account holds until it is sold. A margin position on a
    pair outside the basket, and a coin outside it, are not read: the gauge's children are the basket's.
    A symbol within `FLAT_TOLERANCE` of zero reads 0.0, the seed's own snap. The listing is cached first
    because the position read resolves its rows through it. Anything short of both answers inside
    `_VENUE_READ_TIMEOUT_SECONDS` raises, and so does a position side that is not LONG, SHORT or FLAT.
    An empty listing, through which no margin position resolves, and a positions answer of `None` raise
    too, the two shapes `zcrypto engine flatten` refuses: neither is read as a flat margin book, which
    an empty positions list from a venue that answered is."""
    from cli.engine.flatten import QUOTE_CURRENCY, resolve_base
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        instruments = await client.request_instruments()
        if not instruments:
            raise EngineError("the venue's instrument listing came back empty -- no margin position resolves through it")
        for instrument in instruments:
            client.cache_instrument(instrument)
        positions = await client.request_position_status_reports(
            AccountId(_ACCOUNT_ID), account_type=AccountType.MARGIN, use_spot_position_reports=False, quote_currency=QUOTE_CURRENCY
        )
        if positions is None:
            raise EngineError("the venue answered nothing for the margin positions -- it is never read as a flat margin book")
        state = await client.request_account_state(AccountId(_ACCOUNT_ID), account_type=AccountType.CASH)
        return list(positions), state

    positions, state = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))
    held = _margin_positions(positions)
    bases = frozenset(_SPOT_SYMBOL_BY_BASE)
    for balance in state.balances:
        symbol = _SPOT_SYMBOL_BY_BASE.get(resolve_base(balance.currency.code, bases))
        if symbol is not None:
            held[symbol] += float(balance.total)
    return {symbol: 0.0 if abs(qty) <= FLAT_TOLERANCE else qty for symbol, qty in held.items()}


def _margin_positions(reports) -> dict[str, float]:
    held = dict.fromkeys(INSTRUMENT_IDS, 0.0)
    for report in reports:
        symbol = _SYMBOL_BY_INSTRUMENT_ID.get(str(report.instrument_id))
        if symbol is None:
            continue
        qty = float(report.quantity)
        held[symbol] += {"LONG": qty, "SHORT": -qty, "FLAT": 0.0}[str(report.position_side).rsplit(".", 1)[-1]]
    return held


def read_venue_positions(*, base_url: str | None = None) -> dict[str, float]:
    """The venue's margin positions under every `INSTRUMENT_IDS` symbol, signed by side, on a client of its
    own (`_bare_client`) and on `read_venue_holdings`' terms: the mixed-inventory refusal's source (spec
    00120 D12), since no Cache read tells a margin lot from a spot lot, which the Cache books as a position
    too."""
    from cli.engine.flatten import QUOTE_CURRENCY
    from cli.engine.node import _ACCOUNT_ID

    client = _bare_client(base_url)

    async def _read():
        instruments = await client.request_instruments()
        if not instruments:
            raise EngineError("the venue's instrument listing came back empty -- no margin position resolves through it")
        for instrument in instruments:
            client.cache_instrument(instrument)
        positions = await client.request_position_status_reports(
            AccountId(_ACCOUNT_ID), account_type=AccountType.MARGIN, use_spot_position_reports=False, quote_currency=QUOTE_CURRENCY
        )
        if positions is None:
            raise EngineError("the venue answered nothing for the margin positions -- it is never read as a flat margin book")
        return list(positions)

    return _margin_positions(asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS)))


def _newest_venue_balances(journal_dir: Path) -> dict:
    """`state.balances` from the newest `ok`, schema-2 `venue-<HH>.json`, or `{}` when the journal
    holds none. Mirrors `command._seed_exec_positions`: every record is `validate_venue_record`-
    checked BEFORE its `status` is consulted, and a malformed one raises rather than being skipped
    -- silently reading past a broken record would make the disposal bound fail open."""
    newest: tuple[datetime, dict] | None = None
    for path in sorted(Path(journal_dir).glob("*/venue-*.json")):
        doc = read_venue_record(path)
        validate_venue_record(doc)
        if doc.get("status") != "ok" or doc.get("schema_version") != 2:
            continue
        cycle_ts = datetime.fromisoformat(doc["cycle_ts"])
        if newest is None or cycle_ts > newest[0]:
            newest = (cycle_ts, doc)
    return {} if newest is None else dict(newest[1]["state"]["balances"])


def _cycle_records_through(journal_dir: Path, until: datetime) -> dict[datetime, CycleRecord]:
    """Every success record stamped at or before `until`, keyed by the boundary it names.

    Keyed by the record's OWN `cycle_ts`, not by its path, because that is the stamp
    `tracking.extract_fills` gives a fill and `realized_drift` matches the two on: a record filed
    under a path that disagrees with its content must miss rather than silently pair a fill with a
    different cycle's targets.

    Sidecars are `failed-cycle-<HH>.json` and this glob never sees them -- a boundary the engine
    failed has no targets to compare anything against, and it reads here as the absence it is.
    """
    out: dict[datetime, CycleRecord] = {}
    for path in sorted(Path(journal_dir).glob("*/cycle-*.json")):
        record = from_json(path.read_text())
        require_comparable_cycle_ts(record)
        if record.cycle_ts > until:
            # Filter first, validate second: a record this pass discards must not refuse it for a SCHEMA fault.
            # Validating above the filter let one invalid artifact from any week -- including one no pass will
            # ever score -- refuse every later scoring pass, and the refusal lands as a WARNING with no alert
            # behind it.
            continue
        # `_stage` reads final, closes and nav straight out of these on the live trade path, so the read's own
        # guarantee is not enough here and a refusal propagates (T0194).
        validate_record(record)
        out[record.cycle_ts] = record
    return out


def _stage(record: CycleRecord) -> CycleStages:
    """One journaled cycle as the shape `tracking.realized_drift` reads.

    Only `cycle_ts`, `final`, `closes` and `nav` are read there; the remaining fields are structural and
    carry no meaning for this caller -- the alternative, a private per-cycle drift loop here, is the
    one thing this must not be: the number a human bands and the number the engine trips on have to
    come from the same function.

    Raises when the record cannot be turned into a comparable stage. Both refusals are the
    fail-CLOSED direction of a fail-open trap: a missing `closes` (every artifact written before the
    key existed) cannot be reconstructed afterwards and a guessed price moves every leg at once,
    while a leg missing from `final_targets` contributes NO drift, so a book that dropped one reads
    better than it is.
    """
    targets = {symbol.split("/")[0]: weight for symbol, weight in record.final_targets.items() if symbol.endswith("/EUR")}
    if set(targets) != _MODEL_BASES:
        raise EngineError(
            f"the cycle record for {record.cycle_ts.isoformat()} carries targets for "
            f"{sorted(targets)}, not the model's {sorted(_MODEL_BASES)}"
        )
    if record.closes is None or not _MODEL_BASES <= set(record.closes):
        raise EngineError(
            f"the cycle record for {record.cycle_ts.isoformat()} does not journal the closes it "
            "priced every model leg at, and a close cannot be recovered after the fact"
        )
    return CycleStages(
        cycle_ts=record.cycle_ts,
        sleeve_positions={},
        combined={},
        capped={},
        limited={},
        final=targets,
        multiplier=1.0,
        closes=dict(record.closes),
        cap_bound=False,
        # Carried through so the boundary scores each cycle under the NAV it actually priced
        # against (T0150). None for records written before the key existed.
        nav=record.nav,
    )


@dataclass(frozen=True)
class _CloseDecision:
    """D10's verdict on a close intent: the quantity that may be ordered and whether the venue's own
    `reduce_only` flag rides with it -- or `refusal`, which means no order at all."""

    qty: float = 0.0
    reduce_only: bool = False
    refusal: str | None = None


def _classify_margin_close(intent: ProbeIntent, held: float) -> _CloseDecision:
    """A margin closer is sized from the Cache's LIVE position, never from the plan (the plan's
    `notional_eur` on a closer is advisory): an over-|held| closer is thereby unconstructible rather
    than merely refused. The venue's own `reduce_only` flag rides too, so the same bound is enforced
    at both ends."""
    if held == 0.0:
        return _CloseDecision(refusal="no position to close")
    if (held > 0) != (intent.side == "sell"):
        return _CloseDecision(refusal="side does not reduce the position")
    return _CloseDecision(qty=abs(held), reduce_only=True)


def _classify_spot_close(intent: ProbeIntent, *, balances: dict, level: str) -> _CloseDecision:
    """The D7 disposal: a sell of coin a manual venue action created, whose `qty` came through the
    owner's sign-off from the ledger export.

    Before the restart the venue record can REFUTE but not confirm that figure -- its balances come
    from the connect-time account read, so no pre-restart record can see the settle; a positive
    balance smaller than `qty` is a contradiction and refuses, while zero-or-absent proves nothing
    and the intent proceeds on the signed figure with the venue's own insufficient-funds rejection
    as the enforcing backstop. At `reduce_only` -- which implies the hold, which implies a restart,
    which implies a fresh startup account read -- the record CAN confirm, so the full `qty <=
    balance` bound applies and an absent balance reads 0.0.

    NO venue-side flag either way: Kraken's `reduce_only` is a margin-order concept a spot order
    cannot carry, so this bound plus the venue backstop IS the whole guard.
    """
    if intent.qty is None:
        # Neither closer shape: nothing to size against a position, nothing for the record to bound.
        return _CloseDecision(refusal="a spot close needs an explicit qty")
    if intent.side != "sell":
        return _CloseDecision(refusal="a spot close must be a sell")
    balance = _spot_balance(balances, intent.symbol.split("/")[0])
    if level == GateLevel.REDUCE_ONLY:
        if intent.qty > balance:
            return _CloseDecision(refusal="the venue record's balance does not cover the signed qty")
        return _CloseDecision(qty=intent.qty)
    if 0.0 < balance < intent.qty:
        return _CloseDecision(refusal="the venue record refutes the signed qty")
    return _CloseDecision(qty=intent.qty)


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
    # D10's classification, decided once at intent start: the quantity a close intent may ask for
    # (None for an opener, which sizes from the plan) and whether the order carries the venue's own
    # reduce-only flag.
    close_qty: float | None = None
    reduce_only: bool = False
    # What the Cache said was held in this symbol when the intent started, off the SAME frozen venue
    # truth the intent was authorized against. Instrument-scoped, because SIZING trades the real
    # book: what the operator holds is part of what this engine must size against.
    position_before: float = 0.0
    # The same read scoped to THIS engine's strategy, which the post-terminal reconciliation
    # subtracts against instead: NETTING position ids are `f"{instrument_id}-{strategy_id}"`, so an
    # external fill lands in a separate position and a scoped read excludes it by construction.
    # The two baselines are never compared to each other, so they need not be simultaneous.
    own_position_before: float = 0.0
    order: object | None = None
    order_payload: dict | None = None
    client_order_id: str | None = None
    order_qty: float = 0.0
    order_filled: float = 0.0
    cancel_requested: bool = False
    falling_back: bool = False
    revoke_reasons: tuple[str, ...] = ()
    # When the venue owes an answer by, for the phases that are waiting on one (`cancelling`,
    # `ioc`). None in the phases where nothing is outstanding.
    phase_deadline: datetime | None = None
    # Set whenever an order enters `resting`, so it tracks the CURRENT order rather than the intent:
    # a post-only rejection's reprice replaces the order, and its age restarts with it.
    placed_at: datetime | None = None
    # A rest-hold order reaching `_on_cancel_ack` got there one of two ways -- its hold elapsed, or
    # the kill file revoked it -- and only the first is `rest_hold_expired`. Matching on
    # `revoke_reasons`' text instead would tie the outcome to a string written for a human.
    hold_expired: bool = False
    # `quote_seq` counts the ticks stored since the intent started and `priced_seq` is its value when
    # the live order was priced, so a reprice can tell a tick that arrived after that order from the
    # one that priced it.
    quote_seq: int = 0
    priced_seq: int = 0


class ProbeExecutor:
    """Owns every venue-mutating call in this repository.

    `client` is the strategy handle (or a stub with the same surface): `.cache`,
    `.order_factory.limit(...)`, `.submit_order(order, params=...)`, `.cancel_order(client_order_id)`,
    `.subscribe_quotes(id)`, `.unsubscribe_quotes(id)`.

    `venue_orders` is `read_venue_orders`' signature, `venue_cancel` is `cancel_venue_order`'s and
    `venue_holdings` is `read_venue_holdings`'. None, the engine's construction, reads the module's
    own at call time, so a test can replace it before any executor exists.
    """

    def __init__(
        self,
        *,
        client,
        gate: ExecutionGate,
        config: EngineConfig,
        clock=_utc_now,
        venue_orders=None,
        venue_cancel=None,
        venue_holdings=None,
        venue_fills=None,
        venue_positions=None,
    ) -> None:
        self._client = client
        # The Cache and the strategy id, taken here, inside `on_start`, where the strategy is not
        # borrowed, and read through these handles ever after: `client.cache` is a getter on the
        # strategy, and inside the dispatch of an event the strategy's own command publishes before
        # it returns -- `OrderPendingCancel` from `cancel_order`, `OrderInitialized` from
        # `submit_order` -- it raises `Already mutably borrowed`, the strategy's PyO3 cell being held
        # by that command, while the Cache itself is free and a handle taken earlier reads it
        # (tests/test_engine_executor.py measures both against a real engine).
        self._cache = client.cache
        self._strategy_id = client.strategy_id
        self._gate = gate
        self._config = config
        self._now = clock
        self._venue_orders = venue_orders
        self._venue_cancel = venue_cancel
        self._venue_holdings = venue_holdings
        self._venue_fills = venue_fills
        self._venue_positions = venue_positions
        # The pass's trade-history read (`_trades_cover`), reset at each pass by `_reset_fills_read`.
        self._venue_fills_read: dict[str, float] | None = None
        self._venue_fills_failed = False
        self._venue_fills_floor: datetime | None = None
        # The venue's figure less the Cache's, per symbol, at the last settle of the position gauge
        # (`_settle_positions_from_venue`): `_publish_fill` adds it to the Cache's net, so a fill
        # between two passes moves the gauge from the venue's figure and not from a position the
        # Cache never let go -- a hand close the state machine refused, or a settled lot the Cache
        # holds as a margin position.
        self._venue_correction: dict[str, float] = {}
        # The socket endpoints the client has reported down and not yet back, and the re-read pass's
        # tries left, set by an endpoint's return and by a mint with no endpoint down: the pass runs
        # on the next tick with nothing in flight, and a read that fails spends one try, or closes the
        # arm while an endpoint is held down (`_reread_pass`). A `DISCONNECTED` clears a mint's arm,
        # and a return's the pass has not run on when it is the drop of the endpoint whose return set
        # it, `_reread_armed_by` (`on_socket_state`).
        self._sockets_down: set[str] = set()
        self._reread_tries = 0
        self._reread_armed_by: str | None = None
        # The rows the re-read pass repaired from the venue's report in this process, whose later
        # fills `_fill_credit` caps at what the Cache's order holds beyond the row.
        self._rows_the_pass_repaired: set[str] = set()
        # When the gate was last evaluated, for the idle refresh: the process's startup evaluation
        # published moments before this construction.
        self._gate_evaluated_at: datetime = self._now()
        # Set once, when the startup pass could not read the venue's orders or the restored set could not
        # be read at construction (`_read_restored`), and never cleared: every plan is refused with it for
        # the life of this process, and a restart is the retry.
        self._reconciliation_refusal: str | None = None
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
        # client_order_id -> (the boundary whose exec record holds its row, the row). EVERY order
        # this process knows about is here: the ones it submitted, and the ones the startup pass
        # adopted from a previous process. It is what makes a fill land in a forensic row even when
        # the order is not the one currently in flight -- without it, a fill for a superseded or
        # adopted order is dropped by the client-order-id filter, which costs the row (D5) and
        # understates the remainder the next resubmission is sized against.
        self._attached: dict[str, tuple[datetime, dict]] = {}
        # The same entries by the order's Kraken txid, for an event whose client order id is none of
        # the keys above. A row's own id is the key of every ledger write, whichever map found it.
        self._attached_by_venue: dict[str, tuple[datetime, dict]] = {}
        # Instrument ids this process has actually filled in, for the realized-PnL sum. Scoped to
        # them rather than to the whole basket so a leg this process never touched cannot drag a
        # previous run's closed positions into a number presented as this window's. Held as
        # `InstrumentId`, never as its string: the Cache accessors are Cython-typed and REFUSE a
        # str, so a set of strings would raise on every read into the swallowing `except`.
        self._traded: set[InstrumentId] = set()
        # The startup pass runs on the first tick, once, whatever it finds.
        self._adopted = False
        # Set by the first trip and never cleared. NOT a substitute for the kill file -- the file is
        # the latch, this only stops a second divergence from rewriting the first one's reason and
        # re-halting a plan that is already gone.
        self._kill_tripped = False
        # The restored set (`_read_restored`): the txid of every order the Cache held for the venue at
        # construction, by client order id, for the process's life; empty without the cache.
        self._restored: dict[str, str | None] = {}
        # Set when the restored set could not be read at construction: which rows the Cache holds a copy
        # of is then unknown, so every row is read as a restored one (`_restored_row`).
        self._restored_unread = False
        # The (row, `what`) pairs a sweep of this process marked unmatched (`_mark_unmatched`), which the
        # re-read pass leaves out.
        self._marked: set[tuple[str, str]] = set()
        # The rows the open sweep or the re-read pass left unread on a failed venue read, each until a later
        # read of this process answers it: with `_marked`, the rows no read of this process repaired. A
        # finished row the startup leaves unread is not recorded: it is never attached, so no event or pass
        # of this process reaches its intent.
        self._unread: set[str] = set()
        # The restored rows a fill reached and the re-read pass has not repaired since: the credit is
        # nothing (`_fill_credit`) and the pass repairs the row from the venue's cumulative figure.
        self._restored_fills: set[str] = set()
        # The realized PnL the Cache held per instrument at construction, what a restored position
        # carried in from a previous run, subtracted from the gauge so it reads this process's own.
        self._realized_baseline: dict[InstrumentId, float] = {}
        cache_settings = config.cache
        self._cache_enabled = cache_settings.enabled
        if self._cache_enabled:
            self._read_restored()
        self._read_realized_baseline()

    def _read_restored(self) -> None:
        """The restored set (spec 00120 D6): every order the Cache holds for the venue at construction,
        open or closed, own and EXTERNAL -- a closed copy can be the double booking's FILLED (D7), and a
        restored EXTERNAL copy is one nothing tells from a copy this boot's reconciliation created. Each
        whose row the ledger's window carries is attached here, so a fill on it before the first tick lands
        in its row and never in the unknown-order trip."""
        try:
            orders = list(self._cache.orders(venue=_VENUE))
        except Exception:
            self._restored_unread = True
            self._reconciliation_refusal = (
                "the restored orders could not be read at start, so no ledgered row can be told from one the Cache "
                "restored -- restart the engine to retry"
            )
            logger.critical(
                "the restored orders could not be read at start -- every ledgered row is read at the venue as a restored "
                "one, and every plan is refused until the engine is restarted",
                exc_info=True,
            )
            return
        self._restored = {str(order.client_order_id): _venue_order_id_of(order) for order in orders}
        if not self._restored:
            return
        try:
            rows = open_submitted_rows(self._journal_dir, self._now())
        except Exception:
            logger.critical(
                "the exec ledger could not be read at start -- the restored orders are attached at the startup pass", exc_info=True
            )
            return
        by_own = {row["client_order_id"]: (boundary, row) for boundary, row in rows}
        by_venue = {}
        for boundary, row in rows:
            venue_order_id = _row_venue_order_id(row)
            if venue_order_id is not None:
                by_venue[venue_order_id] = (boundary, row)
        for client_order_id, venue_order_id in self._restored.items():
            entry = by_own.get(client_order_id)
            if entry is None and venue_order_id is not None:
                entry = by_venue.get(venue_order_id)
            if entry is not None:
                self._attach(entry, client_order_id, venue_order_id=venue_order_id)

    def _read_realized_baseline(self) -> None:
        """`_realized_eur`'s baseline (spec 00120 D10): per basket instrument, the realized PnL the Cache
        holds at construction, after reconciliation's fills and before any of this process's. Telemetry: a
        read that fails logs, and an instrument it did not reach keeps no baseline."""
        try:
            for instrument_id in (InstrumentId.from_str(value) for value in INSTRUMENT_IDS.values()):
                held = self._realized_on(instrument_id)
                if held:
                    self._realized_baseline[instrument_id] = held
        except Exception:
            logger.exception("the realized baseline could not be read at start -- the gauge counts every restored realization")

    # --- the gate ------------------------------------------------------------------------------

    def _evaluate(self, now: datetime, *, heartbeat: bool = True) -> GateVerdict:
        """The ONE gate read. Every evaluation reaches the publish hook (D4's cadence ruling), so
        the gate's published state is seconds-fresh for as long as a plan is running and at most
        `_GATE_REFRESH` old while none is (`_refresh_gate`), since the board's kill-switch rule reads
        the gauge and a switch removed on an idle engine would otherwise page until the boundary.
        `heartbeat` False, the refresh's, publishes the readings and not the staleness rule's
        series, which stays the boundary path's."""
        verdict = self._gate.evaluate(now)
        self._gate_evaluated_at = now
        _publish(verdict, now, heartbeat=heartbeat)
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
        if self._kill_tripped:
            # The backstop BEHIND the kill file, at the one place every order goes through. It reads
            # process memory rather than the gate, which is the whole point: if the file could not be
            # written, the gate reads permissive and this is the last thing that refuses. Tripping
            # direction only -- it can refuse an order, never permit one, and never clear anything.
            self._journal_intent(ctx.index, "refused", (_TRIPPED_REFUSAL,), ctx.filled)
            _inc_order("refused")
            return "refused"
        if not _level_permits(verdict.level, ctx.intent):
            # `ctx.filled` on every journal call here, not 0.0: `update_plan_intent` SETS the field
            # rather than accumulating, and a resubmission refused after earlier orders already
            # filled would otherwise erase what was really bought from the operator's summary.
            self._journal_intent(ctx.index, "refused", verdict.reasons, ctx.filled)
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
            if not self._journal_intent(ctx.index, "refused", ("exec ledger write failed",), ctx.filled):
                # Not even the refusal could be recorded: the ledger is down, so nothing may trade.
                logger.critical("the exec ledger is unavailable -- no order may be submitted while it stays down")
            _inc_order("refused")
            return "refused"

        ctx.client_order_id = client_order_id
        # Attached BEFORE the venue call, for the same reason the row is written before it: an order
        # whose submit raises may still be live, and its fill must have somewhere to land.
        self._attached[client_order_id] = (self._plan_cycle_ts, row)
        try:
            self._client.submit_order(order, params=params)
        except Exception:
            # Exactly one attempt: no retry. The row is marked `ambiguous` -- the honest state, since
            # this process cannot tell whether the venue received the order -- and `ambiguous` is one
            # of `execledger._OPEN_ORDER_STATES`, so re-attach still finds a possibly-live order.
            # Calling this "refused" would assert no order exists, which is precisely what is
            # unknown.
            logger.critical("submit of %s raised -- outcome unknown, the write-ahead row stands", client_order_id, exc_info=True)
            self._mark_ambiguous(ctx, "submit raised")
            self._journal_intent(ctx.index, "ambiguous", ("submit raised -- venue outcome unknown",), ctx.filled)
            _inc_order("ambiguous")
            return "ambiguous"
        _inc_order("submitted")
        return "submitted"

    # --- the timer -----------------------------------------------------------------------------

    def on_timer(self, now: datetime) -> None:
        try:
            now = _aware_utc(now)
            if not self._adopted:
                self._adopt_resting_orders(now)
            # Before the pickup and the pump, so a plan dropped during a cut starts behind the re-cancel
            # on this tick and never ahead of it, where the pass would wait behind its every intent;
            # with nothing in flight, `read_venue_orders`' nonce terms.
            if self._reread_tries and self._nothing_in_flight():
                self._reread_pass(now)
            # No plan before the startup pass has run: until it has, no row is reconciled against the
            # venue, and the pass's one venue read must reach the venue before any order of this
            # process does (`read_venue_orders` says why).
            if self._plan is None and self._adopted:
                self._pickup(now)
            self._pump(now)
            self._publish_resting_age(now)
            self._refresh_gate(now)
        except Exception:
            # Refusal by default: whatever broke, stop running this plan. Anything already resting
            # at the venue stays in the ledger as an open row for reconciliation to pick up.
            logger.exception("executor tick raised -- dropping the running plan")
            self._plan = None
            self._active = None
            self._index = 0

    def _publish_resting_age(self, now: datetime) -> None:
        """Eagerly zero for every mode, then set the one that is resting: the board's convention is
        that execution numbers read flat zero rather than absent, and a panel over an absent series
        cannot distinguish 'nothing rests' from 'the engine stopped publishing'.

        Wrapped WHOLE, not just at the metrics call. `_set_resting_age`'s try/except is a
        helper-level guard; everything computed around it -- the mode loop, the phase read, the age
        arithmetic -- would otherwise raise into `on_timer`'s catch-all, which drops the plan and
        nulls `_active`. A live order would then rest at the venue with nothing left to end it:
        `_poll` is unreachable with no `_active`, the adopt pass has already run, and a kill file
        would sweep nothing. A telemetry defect may never end a plan.
        """
        try:
            active = self._active
            resting = active is not None and active.phase == "resting" and active.placed_at is not None
            for mode in MODES:
                age = 0.0
                if resting and active.intent.mode == mode:
                    age = max(0.0, (now - active.placed_at).total_seconds())
                _set_resting_age(mode, age)
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")

    def _refresh_gate(self, now: datetime) -> None:
        """The idle refresh: one evaluation, published, once `_GATE_REFRESH` has passed since the last
        -- the tick a plan runs on evaluates anyway and stamps it. What it publishes is what the gate
        reads, its own fail-closed readings included, and not the heartbeat, which stays the boundary
        path's so the staleness rule keeps watching the sink and its exec record; it journals
        nothing, since the exec record's verdict is the boundary sink's alone. Wrapped as
        `_publish_resting_age` is: telemetry may never end a plan."""
        try:
            if now - self._gate_evaluated_at >= _GATE_REFRESH:
                self._evaluate(now, heartbeat=False)
        except Exception:
            logger.exception("executor gate refresh raised -- continuing")

    # --- the sockets ---------------------------------------------------------------------------

    def on_socket_state(self, event) -> None:
        """The client's socket-state stream, the strategy's `on_socket_state` once it subscribed:
        `DISCONNECTED` names an endpoint down, `CONNECTED` one back. The re-read pass is owed on each
        return of an endpoint held down -- the data socket's, whatever the execution socket reports, and
        a second socket's later return owes it again, an empty population consuming that arm with the
        holdings read alone -- and runs on the tick, never here: it reads the Cache and the venue, which
        the tick does on the main thread with no loop running (`read_venue_orders`). A `CONNECTED` for
        no endpoint held down, the connect itself, owes nothing; a `DISCONNECTED` holds off a pass a
        mint armed (`_arm_reread_after_mint`), so a mint inside a cut reads at most once, on a tick inside the
        mint-to-`DISCONNECTED` gap, and the return arms it again; a pass a return armed that has not run
        yet it clears only when the endpoint whose return set it (`_reread_armed_by`) drops again -- a
        cut drops both endpoints, so an arm left pending behind a live intent goes with the cut; where
        the other endpoint's drop leads and the mint has ended the intent, the arm stands until the
        first read that fails with an endpoint held down closes it (`_reread_pass`) -- and never on
        another endpoint's drop, since the execution socket drops about hourly on this wheel and a drop
        of it behind the data socket's return would otherwise hold that return's pass off until a
        `CONNECTED` under its own string. Arming once the set empties, both sockets resubscribed, was
        set aside: it rests on the execution client reporting `CONNECTED` under the string its
        `DISCONNECTED` carried, unmeasured offline, and an entry whose return never comes under that
        string would hold the pass off for the life of the process. Bookkeeping, never a submission: log
        and continue."""
        try:
            endpoint = str(getattr(event, "endpoint", "?"))
            state = getattr(event, "state", None)
            if state == SocketState.DISCONNECTED:
                self._sockets_down.add(endpoint)
                if self._reread_armed_by in (None, endpoint):
                    self._reread_tries = 0  # a mint's arm, or this endpoint's own return's: a return arms the pass again
                    self._reread_armed_by = None
                logger.warning(
                    "socket %s is down -- an order whose terminal this engine mints meanwhile is re-read at the venue "
                    "once a socket is back",
                    endpoint,
                )
            elif state == SocketState.CONNECTED and endpoint in self._sockets_down:
                self._sockets_down.discard(endpoint)
                self._reread_tries = _REREAD_ATTEMPTS
                self._reread_armed_by = endpoint
                logger.warning(
                    "socket %s is back%s -- the re-read pass runs on the next tick with nothing in flight",
                    endpoint,
                    f" ({', '.join(sorted(self._sockets_down))} still down)" if self._sockets_down else " and none is down",
                )
        except Exception:
            logger.exception("executor socket-state handling raised -- continuing")

    def _arm_reread_after_mint(self) -> None:
        """The re-read pass's second trigger: a terminal this engine minted -- on the plan's own order, on
        one no intent holds any more (`_on_detached_event`), or on one the startup pass adopted, whose
        cancel's ack goes unapplied on this wheel -- or a fill on a restored row, whose credit is nothing
        until the pass reads the venue (`_fill_credit`). A trigger while a socket is held down arms
        nothing: the socket's return does (`on_socket_state`), so a mint inside a cut reads at most once,
        on a tick inside the mint-to-`DISCONNECTED` gap, one try spent at WARNING and the tick held up to
        `_VENUE_READ_TIMEOUT_SECONDS`. The cost is a stale entry, an endpoint whose `CONNECTED` never comes
        under its `DISCONNECTED`'s string, holding every later mint's settlement off until a startup inside
        the re-attach window."""
        if not self._sockets_down:
            self._reread_tries = _REREAD_ATTEMPTS

    def _adopt_resting_orders(self, now: datetime) -> None:
        """The startup pass (D10), run once on the first tick: decide, per resting order this
        process just adopted, whether it may keep resting.

        Classified against the LEDGER, never against the adopted report's own flags -- whether
        Kraken's OpenOrders echo survives adoption with a truthful `is_reduce_only` is unverifiable
        in the installed source (the population happens in the opaque Rust layer), so the
        write-ahead row is the only trusted witness. An order matching a non-terminal row whose
        LEDGERED order was reduce-only is left resting, and its row is preserved. Its later fills
        are preserved with it: the live engine reconciles a venue-resting order under the EXTERNAL
        strategy id (the instrument is never claimed) and routes its events to the strategy
        registered under that id -- `node.py`'s external order observer, which forwards them into
        `_on_external_event` (spec 00098 D1, 00100 D2) -- so the `_attached` entry this pass writes
        below is precisely what that filter matches a post-restart fill against, and a matched fill
        appends to the row, moves the counters, and latches the overfill trip exactly as an own
        order's does. The claim list stays
        empty, so a genuinely external act -- the owner's sanctioned hand settle -- still matches no
        ledgered row and is counted and dropped rather than acted on. Everything else is canceled: a
        resting opener is a pending widening the hold exists to forbid, and an order with no row
        would fill with no appender.
        Cancelling is always available to this pass; keeping is not -- an unreadable ledger
        justifies nothing, so it cancels everything rather than keeping what it cannot vouch for.
        A canceled close leg is re-dropped as a new signed-off plan.

        At level NONE the pass cancels EVERYTHING, ledgered reducers included: a trip cancels
        resting orders, `_poll` already revokes even a resting close when the level drops there, and
        "nothing is working at the venue" must not have a restart-shaped hole -- a kill file that
        survived the restart is exactly the state the operator pulled the switch for. "EVERYTHING" is
        everything the Cache holds, which at startup is every order resting at the venue that
        reconciliation did not drop: `_cancel_resting` says why, and what it drops.

        EVERY matched row is attached, canceled ones included, before any cancel goes out: a cancel
        is a request, not an outcome, and an order can still fill between it and the venue's answer.
        Attaching costs nothing (the detached path makes no state claim, and credits a running
        intent only on a plan-and-index match) and is the only thing that keeps that fill, and the
        ack itself, in a forensic row.

        BEFORE any of that, the pass reconciles every row it can match against the venue's own
        figure (spec 00098 D7), because the stream above cannot reach backwards: a fill applied
        during nautilus's own reconciliation is published before this pass has attached a single
        row, so it matches nothing and is dropped as a genuinely external act.
        The quantity is not lost with it -- an order event is applied to the order and to the Cache
        BEFORE it is dispatched, so the fill is resident in the reconciled order's own `filled_qty`
        by the time this runs, and that is what `_reconcile_adopted_rows` reads. That ordering is a
        measurement, not a reading: the execution engine is compiled and offers no source, so
        tests/test_engine_executor.py drives a real order through a real engine and reads the Cache
        from inside the handler.

        The classification population below is `orders_open`, but the row sweep is NOT: an order that
        filled, was canceled or expired while this process was down is not in the Cache at all when the
        cache is off -- the startup reconciliation reads open orders only -- so the pass cannot return
        early when nothing is resting: an idle startup can still owe row repairs.

        With the cache enabled the Cache may already hold this engine's OWN orders and positions from a
        previous process (spec 00120 D6, D7): the sweep takes the venue's report over the Cache's copy for
        every order of the restored set (`_venue_answers`); one the venue reports closed has its row
        written from the report and is sent no cancel, its stale open copy left in the Cache, and one it
        reports open is classified as an adopted one is -- cancelled unless its row is a ledgered reducer.

        LAST, the window's `pending` intents are settled (`_settle_pending_intents`): no process runs
        their plans, so each is written terminal from what its rows show, except one with an open row
        this pass sent no cancel for -- kept, or beyond its reach -- or a restored row this pass marked,
        and none when either read above failed or a sweep above latched the kill switch.
        """
        try:
            resting = list(self._cache.orders_open(venue=_VENUE))
        except Exception:
            # Nothing can be adopted OR canceled without the list, and nothing has been touched --
            # so the pass does NOT latch: leaving a previous process's orders unclassified for the
            # life of this one is worse than reading again next tick, and there is no cancel to
            # duplicate.
            logger.critical("venue orders could not be read at startup -- retrying on the next tick", exc_info=True)
            return
        self._adopted = True  # the read succeeded: this pass classified what there was to classify

        ledger_read = True
        try:
            rows = {row["client_order_id"]: (boundary, row) for boundary, row in open_submitted_rows(self._journal_dir, now)}
            # The two reads partition the same window's rows and come from the same records, so one
            # failing means neither is available -- hence one `try` around both. Only `rows` reaches
            # the classification loop below: a resting order matching a CLOSED row is a ledger that
            # disagrees with the venue about the order's lifecycle, and letting such a row vouch for
            # it as a resting reducer would leave a live order working on a stale claim.
            finished = {row["client_order_id"]: (boundary, row) for boundary, row in closed_submitted_rows(self._journal_dir, now)}
        except Exception:
            # The claim is scoped to what is actually resting: the rows are now read on every
            # startup, including idle ones where nothing could be canceled at all.
            logger.critical(
                "the exec ledger could not be read at startup -- no row can be reconciled against venue truth%s",
                " and every resting order the Cache holds will be canceled" if resting else "",
                exc_info=True,
            )
            rows, finished, ledger_read = {}, {}, False
        self._reset_fills_read([*rows.values(), *finished.values()])
        venue_orders = self._read_venue_orders(rows, finished)
        self._settle_positions_from_venue("the startup pass")
        self._reconcile_adopted_rows(rows, venue_orders)
        self._reconcile_finished_rows(finished, venue_orders)
        if not resting:
            self._settle_pending_intents(now, rows, finished, set(), venue_orders, ledger_read=ledger_read)
            return  # nothing adopted -- and no gate read, so an idle startup stays the cheap path

        # Read AFTER both sweeps: a repair or a withdrawal that latched the kill switch above makes
        # this `none`, and then the pass cancels everything, ledgered reducers included. A kill file
        # is only one of the reasons the gate reads `none` -- a disarmed engine reads it too -- so the
        # cancel line names the verdict's own reasons rather than assuming one.
        verdict = self._evaluate(now)
        cancel_all = verdict.level == GateLevel.NONE

        # A resting order a previous process placed is named by its Kraken txid in the Cache, so the
        # row it belongs to is found by the txid the row recorded when its own id misses.
        rows_by_venue = {}
        for entry in rows.values():
            venue_order_id = _row_venue_order_id(entry[1])
            if venue_order_id is not None:
                rows_by_venue[venue_order_id] = entry
        cancelled: set[str] = set()
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            venue_order_id = _venue_order_id_of(order)
            attached = rows.get(client_order_id)
            if attached is None and venue_order_id is not None:
                attached = rows_by_venue.get(venue_order_id)
            if attached is not None:
                self._attach(attached, client_order_id, venue_order_id=venue_order_id)
            own = self._cache_enabled and str(getattr(order, "strategy_id", "")) == str(self._strategy_id)
            report = None if not venue_orders or venue_order_id is None else venue_orders.get(venue_order_id)
            if client_order_id in self._restored and report is not None and report.order_status in _ADOPTED_TERMINAL_STATES:
                # The venue's report alone decides: a row a mint closed can stand for an order still resting.
                logger.warning(
                    "restored order %s is %s at the venue -- its stale open copy stays in the Cache and no cancel is sent",
                    client_order_id,
                    _ADOPTED_TERMINAL_STATES[report.order_status],
                )
                continue
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not cancel_all:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
            reason = (
                f"the gate reads none ({', '.join(verdict.reasons) or '-'})"
                if cancel_all
                else "the ledger does not carry it as a resting reducer"
            )
            if own:
                # An order under this engine's own id at startup is one the cache restored (spec 00120 D9).
                logger.warning("canceling restored order %s, %s -- %s", client_order_id, restored_fill_state(order), reason)
            else:
                logger.warning("canceling adopted resting order %s -- %s", client_order_id, reason)
            try:
                self._client.cancel_order(order.client_order_id)
            except Exception:
                logger.critical(
                    "cancel of adopted order %s raised -- it may still rest at the venue", client_order_id, exc_info=True
                )
                continue
            if attached is not None:
                # The cancel went out, so this row holds its intent `pending` no longer; a fill racing the ack lands on the row.
                cancelled.add(attached[1]["client_order_id"])
        self._settle_pending_intents(now, rows, finished, cancelled, venue_orders, ledger_read=ledger_read)

    def _settle_pending_intents(
        self,
        now: datetime,
        rows: dict,
        finished: dict,
        cancelled: set,
        venue_orders: dict | None,
        *,
        ledger_read: bool,
    ) -> None:
        """A `pending` intent in the window belongs to a plan no process runs, so nothing else would
        ever end it. Each is written from what its rows show -- `filled` when they carry the first
        order's quantity, `revoked` when it ran and its order did not survive the restart, `refused`
        when it never ran -- except one with an open row this pass sent no cancel for: an order left
        resting, kept as a reducer or beyond the pass's reach, is still live and its row the live
        record -- and one with a row of the restored set this pass marked (`_marked_here`), which the
        pass could not repair: its intent stays `pending`, never settled from a figure no read answered,
        the credit-0 one among them (spec 00120 D8), and its mark names why. Skipped whole when either
        read failed or this pass latched the kill switch, since the rows' fills were then never
        compared, never read, or refuted by the venue, and are no figure to journal."""
        if venue_orders is None or not ledger_read or self._kill_tripped:
            return
        try:
            pending = pending_plan_intents(self._journal_dir, now)
        except Exception:
            logger.critical(
                "the plan entries could not be read at startup -- pending intents keep the state they have", exc_info=True
            )
            return
        filled: dict[tuple[str, int], float] = {}
        ordered: dict[tuple[str, int], float] = {}
        left: set[tuple[str, int]] = set()
        for _, row in [*rows.values(), *finished.values()]:
            key = (row["plan_id"], row["intent_index"])
            filled[key] = filled.get(key, 0.0) + float(row["filled_qty"])
            # The first order carries the intent's whole quantity and every later one a remainder, so
            # the largest of them is the target.
            ordered[key] = max(ordered.get(key, 0.0), _ordered_qty(row))
            if (row.get("state") in _OPEN_ORDER_STATES and row["client_order_id"] not in cancelled) or (
                self._restored_row(row) and self._marked_here(row)
            ):
                left.add(key)
        for boundary, plan_id, index in pending:
            key = (plan_id, index)
            if key in left:
                continue
            if key not in filled:
                outcome, reasons = "refused", ("not run -- the engine restarted before it ran",)
            elif ordered[key] > 0.0 and filled[key] >= ordered[key] - _OVERFILL_TOLERANCE:
                outcome, reasons = "filled", ()
            else:
                outcome, reasons = "revoked", ("the engine restarted while the intent was in flight",)
            try:
                update_plan_intent(
                    self._journal_dir, boundary, plan_id, index, outcome=outcome, reasons=reasons, filled_qty=filled.get(key, 0.0)
                )
            except Exception:
                logger.critical(
                    "intent %d of plan %s could not be journaled as %s at startup", index, plan_id, outcome, exc_info=True
                )

    def _nothing_in_flight(self) -> bool:
        """No intent of this process live, and no order of it in flight in the Cache's own terms --
        `orders_inflight`, the set the library's in-flight check queries -- so the pass's signed
        requests race nothing of the execution client's: `_active` None alone leaves the startup
        pass's cancels of adopted orders, and a trip's, PENDING_CANCEL with no intent live. A Cache
        that cannot be read holds the pass, and under the cache the pickup of a plan with an opening
        intent (`_pickup`) until the read answers, when its expiry refuses the file; never a plan otherwise."""
        try:
            return self._active is None and not list(self._cache.orders_inflight(venue=_VENUE))
        except Exception:
            logger.exception("executor in-flight read raised -- the re-read pass and a held pickup wait for the next tick")
            return False

    def _reread_pass(self, now: datetime) -> None:
        """The startup sweep at one more moment -- after the sockets come back, or after a terminal this
        engine minted with no socket held down -- over every open row of the window whose Cache order
        was closed by a terminal this engine minted: the cancel the venue never acknowledged, on the
        plan's own order (drill F2's shape: the REST cancel fails in the cut and the engine mints
        `OrderCanceled` while the order rests at Kraken) or on one the startup pass adopted (drills G's
        and A1's: the venue cancels at the second asked and answers nothing this engine applies, the
        mint landing about 31 s on with the sockets up). The venue's report settles each: a closed
        report as at startup, an open one by a cancel, since the Cache's own order is the guess the
        venue must answer. The rows are read from the ledger and the Cache when the pass runs, not
        collected at the mint: a mint can land before the socket's own deadline reports the cut, F2's
        order, and a mint the ack deadline had already stranded lands detached. No intent is written:
        each is terminal at its mint or by the startup sweep, and a plan may be running beside the pass.
        A read that fails spends one try and the tick asks again; past the budget the rows keep their
        state and the line names the hand cancel and, when the ledger read succeeded, each row it could
        not read for, and a startup inside the re-attach window reads them too, under the restart rule
        the error-logs page names. A read that fails while an endpoint is held down closes the arm at
        WARNING instead of spending a try: the cut stands and a socket's return arms three again, so a
        return's arm the other endpoint's drop left standing -- F2's order, the mint ahead of the first
        `DISCONNECTED` and the execution socket's own drop later -- spends no budget into the cut; a
        stale entry, an endpoint whose `CONNECTED` never comes under its drop's string, then closes
        every return's arm at its first failed read, the read's CRITICAL never reaching the page while
        it stands. A row a sweep of this process marked unmatched under the id it is read by now
        (`_marked_here`) is left out: no read of this process settles it, and each arm would re-read it and
        page the same line; an earlier process's mark leaves it in, since this process's reads may answer
        for it. A run whose reads
        answer -- the ledger's, and the venue's orders when the population is not empty -- ends by
        settling the position gauge from the venue's holdings (`_settle_positions_from_venue`), so an
        opposing hand trade the state machine refused settles at the next such arm; a run whose read
        fails returns before the settle. Wrapped whole: a raise here may never drop a plan."""
        self._reread_armed_by = None  # a return's arm is consumed by this run, whatever it reads
        rows: dict = {}
        try:
            rows = {
                row["client_order_id"]: (boundary, row)
                for boundary, row in open_submitted_rows(self._journal_dir, now)
                if (self._minted_closed(row) or row["client_order_id"] in self._restored_fills) and not self._marked_here(row)
            }
            # A restored row a fill reached and a terminal then closed before this pass -- the venue's
            # cancel ack, an expiry -- is in the window's closed rows: its credit-0 fill is repaired
            # here all the same (spec 00120 D8), and its intent waits for that repair.
            rows.update(
                {
                    row["client_order_id"]: (boundary, row)
                    for boundary, row in closed_submitted_rows(self._journal_dir, now)
                    if row["client_order_id"] in self._restored_fills and not self._marked_here(row)
                }
            )
            self._reset_fills_read(rows.values())
            reports = []
            if rows:
                since = min(boundary for boundary, _ in rows.values()) - _VENUE_READ_MARGIN
                reports = (self._venue_orders or read_venue_orders)(since)
        except Exception:
            self._unread.update(rows)
            if self._sockets_down:
                self._reread_tries = 0
                self._reread_armed_by = None
                logger.warning(
                    "the re-read pass could not read the ledger or the venue while socket %s is down -- the arm closes, and "
                    "a socket's return arms it again",
                    ", ".join(sorted(self._sockets_down)),
                    exc_info=True,
                )
                return
            self._reread_tries -= 1
            if self._reread_tries:
                logger.warning("the re-read pass could not read the ledger or the venue -- asking again next tick", exc_info=True)
            else:
                labels = ", ".join(_row_label(row, self._read_id(row)) for _, row in rows.values())
                logger.critical(
                    "the re-read pass could not read the ledger or the venue on %d ticks -- an order this engine minted "
                    "terminal may still rest at Kraken%s: cancel it by hand on Kraken's open-orders page",
                    _REREAD_ATTEMPTS,
                    f" ({labels})" if labels else " (the ledger read failed, so no row is named)",
                    exc_info=True,
                )
            return
        self._reread_tries = 0
        if rows:
            restored = [cid for cid in rows if cid in self._restored_fills]
            if len(rows) > len(restored):
                logger.warning(
                    "the re-read pass reads %d row(s) this engine minted terminal against the venue", len(rows) - len(restored)
                )
            if restored:
                logger.warning(
                    "the re-read pass reads %d restored row(s) with a fill since its last read against the venue", len(restored)
                )
            self._reconcile_adopted_rows(rows, {str(report.venue_order_id): report for report in reports}, recancel=True)
        self._settle_positions_from_venue("the re-read pass")

    def _reset_fills_read(self, entries) -> None:
        """A pass's trade-history state (`_trades_cover`): nothing read yet, no failure, and the floor
        at the earliest boundary among the pass's rows, so the one read a shortfall triggers covers
        every row the pass holds."""
        self._venue_fills_read = None
        self._venue_fills_failed = False
        self._venue_fills_floor = min((boundary for boundary, _ in entries), default=None)

    def _minted_closed(self, row: dict) -> bool:
        """Whether the Cache's order for `row` was closed by a terminal this engine minted, read off its
        history (`_minted_terminal`). A Cache that cannot be read answers no."""
        try:
            order = self._cache_lookup(row, self._read_id(row))
        except Exception:
            return False
        return _minted_terminal(order)

    def _reconcile_adopted_rows(self, rows: dict, venue_orders: dict | None, *, recancel: bool = False) -> None:
        """The startup reconciliation sweep (spec 00098 D7): every open ledgered row, compared
        against its order's own quantity and status, before anything is classified -- and the
        re-read pass's, with `recancel`, over the rows it reads, ledger-closed restored rows among them,
        which take the report's figure and keep their closed state whatever status it reads.

        The ROWS drive it, and each asks for exactly the order it names. The alternative -- reading
        the account's whole order history and matching it against the rows -- reads a population with
        no bound on it, while the rows are the two-day re-attach window; the one venue read the pass
        makes (`_read_venue_orders`) is bounded by the earliest of those rows instead.

        Each row finds its order by the id this engine minted and, when that misses, by the txid the
        row recorded at acceptance: in the Cache first (`_cached_order`), where a restart leaves every
        resting order under its txid alone, and then in `venue_orders` -- the venue's own report, by
        txid, for an order that filled, was canceled or expired while this process was down, which the
        startup reconciliation never puts in the Cache because it reads open orders only. Both answers
        take the same arms in `_reconcile_adopted_row`, so a closed-while-down order gets its repair,
        its terminal state and both trips exactly as a resting one does. A report that is still open
        is an order reconciliation dropped, which `_log_resting_outside_the_cache` logs CRITICAL at
        startup; the re-read pass cancels it instead (`_recancel`), by txid on the bare client, since
        the row is this engine's own record of an order it placed or adopted and the Cache's closed
        copy is why no cancel through the strategy handle reaches it.

        A row neither answers is never given a venue truth nobody read: `_mark_unmatched` marks it by
        its ledger state unless the venue read it needed failed, which `_read_venue_orders` has already
        turned into a refusal of every plan. Outside the restored set the order behind such a row is neither
        attached nor kept by the pass above, and `_on_external_event` says what becomes of its later fills; a
        restored copy is attached at construction and, resting in the Cache, kept as a ledgered reducer or
        cancelled through the strategy handle.

        Wrapped twice, and both wrappings earn their place. PER ROW, so one row's failure -- its
        lookup, its repair, or its trip -- costs only that row and the rest still get their repairs.
        And around the whole sweep, because `_adopted` is already set when this runs: an escape would
        leave a previous process's resting opener working at the venue, uncanceled and unattached,
        for the life of this process.

        Neither of those is what protects the kill trips, and the difference is load-bearing: each
        ledger write inside `_reconcile_adopted_row` carries its OWN `try` (`_record_trip_fill`'s
        precedent), because both trip arms are preceded by a write. Catching those here instead
        would let a read-only journal swallow the latch over a live divergence -- one CRITICAL
        logged, no kill file, and the gate reading normal.
        """
        try:
            for client_order_id, (boundary, row) in rows.items():
                try:
                    venue_order_id = self._read_id(row)
                    order = self._cached_order(row, venue_order_id)
                    report = None if venue_orders is None or venue_order_id is None else venue_orders.get(venue_order_id)
                    if report is not None:
                        self._unread.discard(client_order_id)
                    restored = order is not None and self._venue_answers(row, finished=False)
                    if restored and report is not None:
                        # A restored order the venue answered for: the report over the Cache's copy, the
                        # previous process's view (spec 00120 D6), and no re-cancel -- a restored order is
                        # cancelled or kept by the startup's classification.
                        self._reconcile_adopted_row(
                            boundary,
                            row,
                            float(report.filled_qty),
                            report.order_status,
                            order_id=str(order.client_order_id),
                            venue_order_id=venue_order_id,
                        )
                        if recancel:
                            # The repair is what the intent waited for: the row leaves the fill set
                            # before the settle reads it.
                            self._restored_fills.discard(client_order_id)
                            self._settle_restored_intent(boundary, row)
                        continue
                    if order is not None and not restored:
                        self._reconcile_adopted_row(
                            boundary,
                            row,
                            float(order.filled_qty),
                            order.status,
                            order_id=str(order.client_order_id),
                            venue_order_id=venue_order_id or _venue_order_id_of(order),
                        )
                        continue
                    # A restored row no report answered for takes the tail below as a row outside the restored set does,
                    # never repaired from the Cache's copy, which runs ahead of the venue on a kept reducer (spec 00120 D8).
                    if venue_order_id is not None and venue_orders is None:
                        self._unread.add(client_order_id)
                        continue  # the read failed: unread, not unknowable, and every plan is refused
                    if report is None:
                        self._mark_unmatched(boundary, row, venue_order_id)
                        continue
                    # The pass's row is in the Cache under the id it was minted closed by, which
                    # `_attached` still maps to the mirror the startup built: re-attached under that id
                    # too, this fresh dict is what a later fill's completion guard and trip read. At
                    # startup the Cache holds none of these rows, and the id stays None.
                    order = self._cache_lookup(row, venue_order_id) if recancel else None
                    order_id = None if order is None else str(order.client_order_id)
                    if recancel:
                        self._rows_the_pass_repaired.add(client_order_id)
                    if recancel and report.order_status not in _ADOPTED_TERMINAL_STATES:
                        self._recancel(boundary, row, venue_order_id, report, order_id=order_id)
                        if self._restored_row(row):
                            # A restored row whose minted terminal stood for an order still resting: the
                            # re-cancel writes it `canceled` from the repaired figure, and its intent is
                            # written then, as the closed report's arm below writes it.
                            self._restored_fills.discard(client_order_id)
                            self._settle_restored_intent(boundary, row)
                        continue
                    _log_resting_outside_the_cache(_row_label(row, venue_order_id), report)
                    self._reconcile_adopted_row(
                        boundary,
                        row,
                        float(report.filled_qty),
                        report.order_status,
                        order_id=order_id,
                        venue_order_id=venue_order_id,
                    )
                    if recancel and self._restored_row(row):
                        # A restored row a fill reached whose terminal the library minted -- D7's race,
                        # the ack flagged `reconciliation` -- takes this path, and the repair is what its
                        # intent waited for.
                        self._restored_fills.discard(client_order_id)
                        self._settle_restored_intent(boundary, row)
                except Exception:
                    logger.critical("adopted row %s could not be reconciled against the venue", client_order_id, exc_info=True)
        except Exception:
            logger.critical("the startup reconciliation sweep raised -- classifying resting orders anyway", exc_info=True)

    def _recancel(self, boundary: datetime, row: dict, venue_order_id: str, report, *, order_id: str | None = None) -> None:
        """The re-read pass's cancel of an order the venue still reports open: the report's fills
        repair the row first, through the arms and trips a startup's repair takes, the row re-attached
        under the Cache order's own id (`order_id`) so a later fill reads this row, then the cancel
        goes out by txid on the bare client, and its return writes the row `canceled` with a
        `recancelled` event -- the client reads no `count` from the venue's answer and the library
        drops the stream's later event for an order it already holds closed, so `canceled` says the
        pass read the order open and its cancel returned; a fill landing between the two is in the
        row once the stream delivers it, `_fill_credit` crediting what the Cache's order holds beyond
        the repair -- the fill whole where the Cache had the report's fills, only what exceeds the
        Cache's lag where the stream never delivered them -- and on the adopted path completes it
        `filled` off this pass's own mirror, and one the stream never delivers is on Kraken's closed
        orders alone, which the page has the operator read. A cancel
        that raises -- the cut not over for REST, or a refusal the venue phrases as an error --
        leaves the row and names the hand cancel, the refused-cancel arm's precedent. No counter
        moves for the re-cancel and no intent is written here -- a restored row's the caller writes
        once the row reads `canceled` (`_settle_restored_intent`); a closed report that completes the row
        counts `filled` through `_reconcile_adopted_row`'s arm, the startup's rule."""
        label = _row_label(row, venue_order_id)
        self._reconcile_adopted_row(
            boundary, row, float(report.filled_qty), report.order_status, order_id=order_id, venue_order_id=venue_order_id
        )
        try:
            (self._venue_cancel or cancel_venue_order)(venue_order_id, str(report.instrument_id))
        except Exception:
            logger.critical(
                "the re-read pass's cancel of %s raised or was refused -- the order may still rest at Kraken: cancel it "
                "by hand on Kraken's open-orders page",
                label,
                exc_info=True,
            )
            return
        event = {"event": "recancelled", "at": self._now().isoformat(), "venue_order_id": venue_order_id}
        try:
            update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state="canceled", event=event)
        except Exception:
            logger.critical("the re-cancel of %s could not be journaled -- its row keeps the state it has", label, exc_info=True)
            return
        row["state"] = "canceled"
        logger.warning(
            "re-cancelled %s -- it rested at Kraken (%s) after a terminal this engine minted; its row reads canceled",
            label,
            report.order_status.name,
        )

    def _mark_unmatched(self, boundary: datetime, row: dict, venue_order_id: str | None) -> None:
        """A row no venue report answers for, read by `venue_order_id` (`_read_id`), marked in the
        ledger's own word for an outcome this process could not establish: `ambiguous`, with the event
        `_mark_ambiguous` writes, its `what` the missing txid (`_unmatchable_what`) or the one the read
        omits (`_unread_what`). Every sweep of both passes marks here, and whether the row is open -- its
        LEDGER state one of `execledger._OPEN_ORDER_STATES` -- decides the rest, whichever sweep asks.

        An open row takes the state as well. It is one of `execledger._OPEN_ORDER_STATES`, so the row
        stays in the re-attach set, pointing at an order that may still rest. A finished row takes the
        event only: its order ended, so the state would falsely claim it may be resting, and what is
        unestablished is only whether the venue has since withdrawn a fill.

        The line is a WARNING, except for an open row whose txid the venue read does not return: CRITICAL,
        the level `_log_resting_outside_the_cache` logs at, since that read skips an order row the adapter
        cannot parse (`_cancel_resting`), so the order may still rest at Kraken, where no cancel this
        process can issue reaches it outside the restored set; a restored copy resting in the Cache is
        attached and kept as a ledgered reducer or cancelled through the strategy handle.

        A row already carrying the mark -- the event, for this `what` (`_marked_unmatched`) -- is left
        alone, so a row that stays unmatched does not gain an event every restart; its line is logged
        every restart all the same, and the re-read pass leaves a row this process marked out of its
        later arms (`_marked_here`), an open row's `ambiguous` state being the mint's or the strand's as
        readily as a mark's. Nothing is refused and nothing trips: the operator reads the row against
        Kraken's own open and closed orders. The write is not wrapped: the caller's per-row `try` logs
        its failure, and no trip stands behind it."""
        client_order_id = row["client_order_id"]
        open_row = row.get("state") in _OPEN_ORDER_STATES
        what = _mark_what(row, venue_order_id)
        log = logger.critical if open_row and venue_order_id is not None else logger.warning
        log("ledgered order %s matches no venue order -- %s; its row is marked ambiguous", client_order_id, what)
        self._marked.add((client_order_id, what))
        if _marked_unmatched(row, what):
            return
        event = {"type": "ambiguous", "at": self._now().isoformat(), "what": what}
        update_submitted_row(self._journal_dir, boundary, client_order_id, state="ambiguous" if open_row else None, event=event)
        if open_row:
            row["state"] = "ambiguous"

    def _read_venue_orders(self, rows: dict, finished: dict) -> dict | None:
        """The venue's own orders by txid, for the rows the Cache cannot answer for: `{}` when no row
        needs them, which is every startup with nothing ledgered to compare, and so no order read; the
        holdings read the pass makes next (`_settle_positions_from_venue`) builds a client of its own at
        every startup.

        A read that fails leaves those rows unread and returns None, and that is a refusal, not a
        retry: the read is not repeated in this process (`read_venue_orders` says why), and every
        plan is refused until a restart reads again. The kill switch is not tripped -- an unread
        figure is no divergence, and a trip would cancel reducers the pass may keep."""
        needed: list[datetime] = []
        for is_finished, entries in ((False, rows.values()), (True, finished.values())):
            for boundary, row in entries:
                try:
                    if is_finished and not row["filled_qty"] > _OVERFILL_TOLERANCE and not self._restored_row(row):
                        continue
                    venue_order_id = self._read_id(row)
                    if venue_order_id is None:
                        continue
                    # The venue first, so a row it answers for is read whatever a read of its copy does.
                    if self._venue_answers(row, finished=is_finished) or self._cached_order(row, venue_order_id) is None:
                        needed.append(boundary)
                except Exception:
                    continue  # the sweep reads this row again, and logs what fails there
        if not needed:
            return {}
        try:
            reports = (self._venue_orders or read_venue_orders)(min(needed) - _VENUE_READ_MARGIN)
            return {str(report.venue_order_id): report for report in reports}
        except Exception:
            self._reconciliation_refusal = (
                f"the startup reconciliation could not read the venue's orders, so {len(needed)} ledgered row(s) "
                "were never compared against venue truth -- restart the engine to retry"
            )
            logger.critical(
                "the venue's orders could not be read at startup -- %d ledgered row(s) were never compared "
                "against venue truth; every plan is refused until the engine is restarted",
                len(needed),
                exc_info=True,
            )
            return None

    def _trades_cover(self, boundary: datetime, venue_order_id: str | None, ledgered: float) -> bool | None:
        """Whether the venue's trade history holds fills for `venue_order_id` summing to at least
        `ledgered`, the withdrawal check's second source (spec 00120 D19): an order's figure falls short of
        the ledger without a withdrawal when the library created the order from the venue's report with
        none of its fills applied, a cold start's shape. None -- the check then trips on the order's figure
        -- for a row with no txid and, for the rest of the pass, once the history's one read
        (`_reset_fills_read`) has failed, since an unread history is no evidence either way."""
        if venue_order_id is None or self._venue_fills_failed:
            return None
        if self._venue_fills_read is None:
            since = (boundary if self._venue_fills_floor is None else self._venue_fills_floor) - _VENUE_READ_MARGIN
            try:
                reports = (self._venue_fills or read_venue_fills)(since)
            except Exception:
                self._venue_fills_failed = True
                logger.critical(
                    "the venue's trade history could not be read for the withdrawal check -- the order's figure decides",
                    exc_info=True,
                )
                return None
            filled: dict[str, float] = {}
            for report in reports:
                key = str(report.venue_order_id)
                filled[key] = filled.get(key, 0.0) + float(report.last_qty)
            self._venue_fills_read = filled
        return self._venue_fills_read.get(venue_order_id, 0.0) >= ledgered - _OVERFILL_TOLERANCE

    def _cached_order(self, row: dict, venue_order_id: str | None):
        """The Cache's answer for `row`: its order (`_cache_lookup`), unless that order was closed by
        a terminal this engine minted (`_minted_terminal`), when the Cache holds this engine's own
        guess and answers nothing, so the venue is asked. Without the cache no order is closed that
        way at startup -- reconciliation adopts open orders, and the void it can mint is not one of
        those terminals -- so the startup sweeps read as before; with it, an order a previous process
        closed with a minted terminal is restored closed, its terminal in its history, and is withheld
        here at startup too, and `_venue_answers` says which restored rows the venue is asked over."""
        order = self._cache_lookup(row, venue_order_id)
        return None if _minted_terminal(order) else order

    def _cache_lookup(self, row: dict, venue_order_id: str | None):
        """The Cache's order for `row`: by the id this engine minted, then by the txid the row
        recorded. The second lookup is the one every order a restart reconciled needs, since the
        adapter's reports carry no client order id and reconciliation names the order by its txid;
        it goes through the Cache's own venue-order-id index rather than an assumption about how
        reconciliation names what it adopts. `cache.order` serves closed orders as readily as open
        ones, and both accessors are typed and refuse a plain str. With the cache enabled the first
        lookup answers for an order a previous process placed too, restored under the id this engine
        minted; `_venue_answers` says which of those the venue is asked over."""
        cache = self._cache
        order = cache.order(ClientOrderId(row["client_order_id"]))
        if order is None and venue_order_id is not None:
            client_order_id = cache.client_order_id(VenueOrderId(venue_order_id))
            order = None if client_order_id is None else cache.order(client_order_id)
        return order

    def _venue_answers(self, row: dict, *, finished: bool) -> bool:
        """Whether the venue is asked over an order the Cache holds (spec 00120 D6): with the cache
        enabled, every finished row with fills, whatever the Cache's copy, and every row of the restored
        set, whatever its copy's status -- the copy is the previous process's view, or the double
        booking's, which reads an order FILLED where the venue says partial (D7), and a check against it
        would compare the ledger with itself. Without the cache the Cache holds only what this boot's
        reconciliation adopted, and it answers as before."""
        if not self._cache_enabled:
            return False
        return finished or self._restored_row(row)

    def _read_id(self, row: dict) -> str | None:
        """The txid a row is read at the venue by: the one it recorded, else its restored copy's
        (`_restored`), which carries the acceptance a ledger row can miss."""
        return _row_venue_order_id(row) or self._restored.get(row["client_order_id"])

    def _marked_here(self, row: dict) -> bool:
        """Whether a sweep of this process marked `row` unmatched under the id it is read by now (`_read_id`)."""
        return (row["client_order_id"], _mark_what(row, self._read_id(row))) in self._marked

    def _restored_row(self, row: dict) -> bool:
        """Whether the Cache held `row`'s order at construction (`_read_restored`): under the id this
        engine minted, or, for an EXTERNAL copy, under the txid the row recorded, which is that copy's
        own client order id. Every row when that read failed, since any row may then have a copy."""
        return self._restored_unread or row["client_order_id"] in self._restored or _row_venue_order_id(row) in self._restored

    def _settle_restored_intent(self, boundary: datetime, row: dict) -> None:
        """A restored row's intent, written once at the row's terminal while it still reads `pending` (spec
        00120 D8), by the path that ends the row, at the row's own boundary without `self._plan`, the
        sweep's shape: `filled`, or `revoked` naming the row's kind and whether it filled. A row in
        `_restored_fills` waits: its `filled_qty` is the credit-0 figure until the re-read pass repairs it,
        and the pass writes the intent after that repair; a row the pass could not repair, marked or
        unread, stays in the set, its intent `pending`, never settled from that figure. A row a sweep of
        this process marked (`_marked_here`), the startup's marks among them, or left unread on a failed
        read (`_unread`) until a later read answers it, keeps its intent `pending` at its terminal too: its
        figure is one no read answered, the credit-0 one among them, and its mark or the failed read's
        line names why."""
        if not self._restored_row(row) or row.get("state") in _OPEN_ORDER_STATES:
            return
        if row["client_order_id"] in self._restored_fills or self._marked_here(row) or row["client_order_id"] in self._unread:
            return
        key = (row.get("plan_id"), row.get("intent_index"))
        try:
            pending = {(plan_id, index) for _, plan_id, index in pending_plan_intents(self._journal_dir, self._now())}
        except Exception:
            logger.critical(
                "the plan entries could not be read -- the intent of restored row %s keeps the state it has",
                row["client_order_id"],
                exc_info=True,
            )
            return
        if key not in pending:
            return
        if row.get("state") == "filled":
            outcome, reasons = "filled", ()
        else:
            payload = row.get("order")
            kind = "kept reducer" if isinstance(payload, dict) and payload.get("reduce_only") is True else "restored opener"
            how = "partly filled" if float(row["filled_qty"]) > _OVERFILL_TOLERANCE else "without filling"
            outcome, reasons = "revoked", (f"the {kind} ended {how}",)
        try:
            update_plan_intent(
                self._journal_dir, boundary, key[0], key[1], outcome=outcome, reasons=reasons, filled_qty=float(row["filled_qty"])
            )
        except Exception:
            logger.critical("intent %s of plan %s could not be journaled as %s", key[1], key[0], outcome, exc_info=True)

    def _attach(self, entry: tuple[datetime, dict], *client_order_ids: str, venue_order_id: str | None) -> None:
        for client_order_id in client_order_ids:
            self._attached[client_order_id] = entry
        if venue_order_id is not None:
            self._attached_by_venue[venue_order_id] = entry

    def _attached_for(self, event) -> tuple[datetime, dict] | None:
        """The row an order event belongs to: by the event's client order id, then by its venue order
        id, which finds a row whose order the event names by an id no key in `_attached` holds."""
        attached = self._attached.get(str(getattr(event, "client_order_id", "")))
        venue_order_id = _venue_order_id_of(event)
        if attached is None and venue_order_id is not None:
            attached = self._attached_by_venue.get(venue_order_id)
        return attached

    def _reconcile_adopted_row(
        self,
        boundary: datetime,
        row: dict,
        venue_filled: float,
        status,
        *,
        order_id: str | None,
        venue_order_id: str | None,
    ) -> None:
        """One ledgered row against the venue truth its order carries: the quantity the venue says
        filled, and the order's status.

        The comparison takes exactly one of four arms, on a dead-band of `_OVERFILL_TOLERANCE`: the
        ledgered figure is a SUM of per-fill floats and the venue's is one exactly-rounded
        `float(Quantity)`, so a clean multi-fill restart differs by ulps and must be silent. Without
        the dead-band every healthy restart would journal a phantom repair and log a warning.

        A repair is journaled as a REPAIR, not as a fill, and is deliberately not published to the
        fill/fee counters: there is no per-fill detail and no fee behind it, and a fills increment
        with no fee would make the two counters disagree in a way the row cannot explain. One
        knock-on, named rather than discovered later: `_publish_fill` is what admits an instrument
        to `self._traded`, so a leg whose only fill happened while this process was down does not
        enter the realized-PnL gauge until it fills live again.

        The terminal-state write is INDEPENDENT of all four arms, because the commonest
        closed-while-down shape -- a cancel with zero fills -- has no delta at all, and a
        `delta == 0 -> skip` sweep would leave its row open forever. A repair that COMPLETES the
        ledgered quantity writes `filled` and counts the outcome by the same arithmetic and the same
        once-only guard the external path's completion uses; the terminal write alone moves no
        outcome counter, exactly as a terminal event on that path does not.

        When both could speak, the venue's status wins -- it is truth about the ORDER's lifecycle,
        where the completion is an inference from the ledgered quantity -- and the outcome is
        counted only when the state actually written is `filled`, so the counter can never say
        `filled` over a row that says `canceled`. No test pins that precedence, deliberately: neither
        source of the status can produce the conflict. A Cache order's status comes from the
        library's own state machine, where an order filled to its quantity is FILLED and never
        CANCELED/EXPIRED/REJECTED/DENIED. A venue report's status is the adapter's mapping of
        Kraken's own, where an order executed to its full volume is `closed`, and `closed` maps to
        FILLED. The one shape that could fake the conflict on either (an unreadable ledgered qty,
        which reads 0.0) routes to the overshoot trip before the completion arm is consulted.
        Pinning an input the venue cannot produce would be a guard on a door with no caller.

        Every ledger write here is wrapped where it is MADE, never by the caller's per-row wrapper:
        both trip arms have a write in front of them -- the repair on the overshoot arm, the
        terminal state on a closed order's negative one -- so a wrapper spanning the arm would let a
        ledger failure suppress the kill switch on exactly the divergences it exists for. The
        in-process figures are mirrored either way, `_record_trip_fill`'s ruling: they track what
        the venue says filled, not what could be written down.

        The row is attached here rather than left to the classification loop, which only ever sees
        the RESTING orders: that is what puts a closed order's row in the maps too, so a late
        duplicate or racing event for it lands matched rather than counted as the operator's hand
        settle. It is attached under the row's own id, the id the Cache names the order by, and the
        txid, since an event names the order the Cache's way; every ledger write here keys on the
        row's own id whichever of them found it. The mirror carries `state` as well as the quantity
        -- the external path's once-only completion guard reads that state, and its overfill trip
        reads that quantity.
        """
        client_order_id = row["client_order_id"]
        label = _row_label(row, venue_order_id)
        ledgered = row["filled_qty"]
        delta = venue_filled - ledgered
        ordered = _ordered_qty(row)
        repairs = delta > _OVERFILL_TOLERANCE
        if repairs:
            payload = {"event": "reconciled", "at": self._now().isoformat(), "qty": delta, "venue_filled_qty": venue_filled}
            try:
                update_submitted_row(self._journal_dir, boundary, client_order_id, event=payload, add_filled_qty=delta)
            except Exception:
                logger.critical("the repair for adopted order %s could not be journaled", label, exc_info=True)
            row["filled_qty"] = ledgered + delta
            logger.warning(
                "adopted order %s reconciled against the venue: %.10g filled there against the %.10g recorded here",
                label,
                venue_filled,
                ledgered,
            )
        total = row["filled_qty"]
        overshoots = repairs and total > ordered + _OVERFILL_TOLERANCE
        completes = repairs and not overshoots and row.get("state") != "filled" and total >= ordered - _OVERFILL_TOLERANCE
        state = _ADOPTED_TERMINAL_STATES.get(status) or ("filled" if completes else None)
        if state is not None:
            try:
                update_submitted_row(self._journal_dir, boundary, client_order_id, state=state)
            except Exception:
                logger.critical("the startup state for adopted row %s could not be journaled", label, exc_info=True)
            row["state"] = state
        self._attach((boundary, row), client_order_id, *([order_id] if order_id else []), venue_order_id=venue_order_id)
        if completes and state == "filled":
            _inc_order("filled")
        if delta < -_OVERFILL_TOLERANCE and self._trades_cover(boundary, venue_order_id, ledgered) is True:
            # The row keeps its figure and joins the repaired set, so a fill the library later infers for
            # this order credits only what the Cache holds beyond the row.
            self._rows_the_pass_repaired.add(client_order_id)
            logger.warning(
                "adopted order %s reads %.10g filled on its order figure against the %.10g recorded here, and the venue's "
                "trade history covers the ledger -- the figure is the library's copy without its fills applied, no withdrawal",
                label,
                venue_filled,
                ledgered,
            )
        elif delta < -_OVERFILL_TOLERANCE:
            # The dangerous direction: the ledger claims more filled than the venue reports, so this
            # engine believes it reduced more than it did. Clamping it to zero would swallow the
            # signal, and it is the same class of divergence the per-order fill trip already guards.
            self._trip_kill(
                f"adopted order {label} shows {venue_filled:.10g} filled at the venue, "
                f"less than the {ledgered:.10g} this engine has already recorded"
            )
        elif overshoots:
            # The repair is journaled above, before this: the fill happened at the venue, and
            # no-fill-without-a-record has no divergence exemption.
            self._trip_kill(
                f"adopted order {label} shows {total:.10g} filled at the venue, "
                f"more than the {ordered:.10g} the ledger says it was submitted for"
            )

    def _reconcile_finished_rows(self, rows: dict, venue_orders: dict | None) -> None:
        """The rows the sweep above cannot reach (spec 00100 D16): every ledgered row this engine
        already closed, asked the one question a finished order can still answer wrongly.

        The population is the whole reason this exists. `_reconcile_adopted_rows` runs over the
        re-attach set, which by definition holds only the states an order can still be live in -- so
        a row that reads `filled`, `canceled`, `venue_canceled` or `rejected` is compared against
        nothing, ever. That is fine for everything an order can do going forward and wrong for the
        one thing it can do backwards: the venue withdrawing a fill it already reported. A withdrawal
        lands on a COMPLETED order by construction, which is exactly the row the re-attach set omits.
        A row with no fills has none to withdraw, so only rows with fills are asked, and the restored rows below.

        This engine never sees the withdrawal as an event: it happens to an order this process may
        never have held, and what shows it is the venue's own `filled_qty` for the order having come
        DOWN while the ledger row still carries the quantity this engine recorded, published and
        sized against. The row finds that order, and is marked when it finds none, as an open row
        does in `_reconcile_adopted_rows`; `_mark_unmatched` says how a finished row's mark differs. A
        row of the restored set finds it in the venue's report alone, by `_read_id`, never in its Cache
        copy (`_venue_answers` says why), and is asked with no fills too, since a credit-0 fill no re-read
        pass repaired leaves its figure below the venue's (spec 00120 D8): a report above the row repairs
        it through the startup's repair arm before the pass settles its intent.

        Wrapped per row and around the whole loop for `_reconcile_adopted_rows`' reasons, and the
        ledger write carries its own `try` for the same one: the trip stands behind it, so a
        read-only journal may never swallow a latch.
        """
        try:
            for client_order_id, (boundary, row) in rows.items():
                try:
                    restored = self._restored_row(row)
                    venue_order_id = self._read_id(row)
                    if not row["filled_qty"] > _OVERFILL_TOLERANCE and not (restored and venue_order_id is not None):
                        continue
                    label = _row_label(row, venue_order_id)
                    order = None if restored else self._cached_order(row, venue_order_id)
                    if order is not None and (venue_order_id is None or not self._venue_answers(row, finished=True)):
                        self._reconcile_finished_row(boundary, row, float(order.filled_qty), label, venue_order_id=venue_order_id)
                        continue
                    if venue_order_id is not None and venue_orders is None:
                        continue  # the read failed: unread, not unknowable, and every plan is refused
                    report = None if venue_order_id is None else venue_orders.get(venue_order_id)
                    if report is None:
                        self._mark_unmatched(boundary, row, venue_order_id)
                        continue
                    if not restored and order is None:
                        _log_resting_outside_the_cache(label, report)
                    if restored and float(report.filled_qty) > row["filled_qty"] + _OVERFILL_TOLERANCE:
                        self._reconcile_adopted_row(
                            boundary,
                            row,
                            float(report.filled_qty),
                            report.order_status,
                            order_id=None,
                            venue_order_id=venue_order_id,
                        )
                    else:
                        self._reconcile_finished_row(boundary, row, float(report.filled_qty), label, venue_order_id=venue_order_id)
                    # A restored row's copy is read only once its figure is applied, and only for the line below.
                    if (
                        restored
                        and report.order_status not in _ADOPTED_TERMINAL_STATES
                        and self._cached_order(row, venue_order_id) is None
                    ):
                        _log_resting_outside_the_cache(label, report)
                except Exception:
                    logger.critical("finished row %s could not be reconciled against the venue", client_order_id, exc_info=True)
        except Exception:
            logger.critical("the finished-row sweep raised -- classifying resting orders anyway", exc_info=True)

    def _reconcile_finished_row(
        self, boundary: datetime, row: dict, venue_filled: float, label: str, *, venue_order_id: str | None = None
    ) -> None:
        """One closed row against the venue's own figure: does the venue still report the quantity
        this row was closed on?

        ONE direction, on the same `_OVERFILL_TOLERANCE` dead-band the sweep above uses and for the
        same reason -- the ledgered figure is a sum of per-fill floats and the venue's is one
        exactly-rounded `float(Quantity)`, so a clean multi-fill order differs by ulps. A shortfall
        is the withdrawal's whole signature, and it means this engine holds less than every figure
        downstream of the row already says it does: `held`, the position the ladder sizes against,
        the fills and fee counters. That is the same divergence 00098 D7's negative arm latches on
        for an open row, reaching the rows D7 cannot see.

        NOTHING is repaired, reversed or restated, and that is the decision rather than an omission.
        The row records what the venue reported when it reported it, and the withdrawal appends
        beside it, so the two readings sit together for whoever reads the kill. Subtracting instead
        would move the overfill trip's base under it, and would leave a ledger that agrees with the
        venue and no longer shows that they ever disagreed -- deleting exactly the evidence the trip
        is about. There is no next order to size correctly either: a latched kill is the last thing
        this process decides about trading.
        """
        ledgered = row["filled_qty"]
        if venue_filled >= ledgered - _OVERFILL_TOLERANCE:
            return
        if self._trades_cover(boundary, venue_order_id, ledgered) is True:
            logger.warning(
                "finished order %s reads %.10g filled on its order figure against the %.10g it was closed on, and the venue's "
                "trade history covers the ledger -- no withdrawal",
                label,
                venue_filled,
                ledgered,
            )
            return
        payload = {
            "event": "withdrawn",
            "at": self._now().isoformat(),
            "qty": venue_filled - ledgered,
            "venue_filled_qty": venue_filled,
        }
        try:
            update_submitted_row(self._journal_dir, boundary, row["client_order_id"], event=payload)
        except Exception:
            logger.critical("the withdrawal on finished row %s could not be journaled", label, exc_info=True)
        self._trip_kill(
            f"order {label} shows {venue_filled:.10g} filled at the venue, less than the "
            f"{ledgered:.10g} this engine recorded and closed it on"
        )

    def _pickup(self, now: datetime) -> None:
        path = exec_dir(self._state_dir) / PLAN_FILENAME
        try:
            os.lstat(path)
        except FileNotFoundError:
            # The cheap idle path: no gate read, no venue read, nothing published here -- the tick's
            # `_refresh_gate` is the idle path's one gate read, once a period.
            return
        except OSError, ValueError:
            logger.warning("probe plan %s cannot be stat'd -- no pickup this tick", path, exc_info=True)
            return

        verdict = self._evaluate(now)
        cycle_ts = _boundary(now)

        try:
            plan = parse_plan(path.read_text())
        except (ProbePlanError, OSError, TypeError, ValueError, OverflowError) as exc:
            # An unreadable file cannot be journaled verbatim, so it is journaled as the refusal it
            # is -- and still deleted, or the next tick re-reads the same broken file forever. The
            # builtins join ProbePlanError because a malformed document can leave the parser as one
            # of them, and the reason carries the class: str(exc) alone never says which refused.
            if self._journal_plan(
                cycle_ts,
                verdict,
                now,
                plan_id="unparseable",
                plan={},
                disposition="refused",
                reasons=(f"{type(exc).__name__}: {exc}",),
            ):
                self._delete(path)
            return

        if self._kill_tripped:
            # A trip stops THIS plan through `_halt_plan`; without this it would stop nothing else,
            # and a plan dropped afterwards would be picked up and run whenever the kill file could
            # not be written. Journaled and deleted like any other refusal, or the next tick re-reads
            # the same file forever.
            logger.critical("probe plan %s refused: %s", plan.plan_id, _TRIPPED_REFUSAL)
            if self._journal_plan(
                cycle_ts, verdict, now, plan_id=plan.plan_id, plan=plan.raw, disposition="refused", reasons=(_TRIPPED_REFUSAL,)
            ):
                self._delete(path)
            return

        if self._reconciliation_refusal is not None:
            # The startup pass could not read the venue's orders, so ledgered rows were never compared
            # with what the venue did while this process was down -- a withdrawn fill among them would
            # have latched the kill switch -- or the restored set could not be read, so any order's fill
            # may be a restored copy's, credited nothing. Refused the way the backstop above refuses, for
            # the life of this process.
            logger.critical("probe plan %s refused: %s", plan.plan_id, self._reconciliation_refusal)
            if self._journal_plan(
                cycle_ts,
                verdict,
                now,
                plan_id=plan.plan_id,
                plan=plan.raw,
                disposition="refused",
                reasons=(self._reconciliation_refusal,),
            ):
                self._delete(path)
            return

        try:
            state = venue_state_from_cache(self._cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing plan %s", plan.plan_id, exc_info=True)
            if self._journal_plan(
                cycle_ts, verdict, now, plan_id=plan.plan_id, plan=plan.raw, disposition="refused", reasons=("no venue truth",)
            ):
                self._delete(path)
            return

        if self._cache_enabled and any(intent.action == "open" for intent in plan.intents) and not self._nothing_in_flight():
            # The mixed-inventory check's venue read (`_mixed_inventory_refusals`) is a signed read on
            # the trade key, on the passes' nonce terms: on the first tick the startup pass's cancels
            # are still PENDING_CANCEL, so the plan waits in its file for a tick with nothing in flight.
            logger.info(
                "probe plan %s waits for a tick with nothing in flight -- its opening intents take a venue read", plan.plan_id
            )
            return
        # Live balances spell the free-cash currency `EUR`, so this resolves on its SECOND arm in
        # production; the `ZEUR` arm stays first because the adapter's instrument quote currency spells
        # the euro `ZEUR`. Both absent reads 0.0, which refuses any margin intent.
        free_zeur = state.balances.get("ZEUR", 0.0) or state.balances.get("EUR", 0.0)
        reasons = plan_refusals(
            plan,
            now=now,
            ledgered=ledgered_plan_ids(self._journal_dir, now),
            max_plan_notional_eur=self._config.exec_max_plan_notional_eur,
            free_zeur=free_zeur,
        )
        if self._cache_enabled and not reasons:
            reasons = [*reasons, *self._mixed_inventory_refusals(plan, state)]
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

    def _mixed_inventory_refusals(self, plan, state) -> list[str]:
        """Spec 00120 D12's refusal of an opening intent that would put a spot lot beside a margin lot on
        one pair, the margin figure the venue's (`read_venue_positions`); the spot floor is the pair's
        `ordermin`, since a lot under it is dust the engine cannot sell and would refuse every margin open
        on the pair while the cache is enabled."""
        opens = [(index, intent) for index, intent in enumerate(plan.intents) if intent.action == "open"]
        if not opens:
            return []
        try:
            margin = (self._venue_positions or read_venue_positions)()
        except Exception as exc:
            return [
                f"intent {index}: the venue's margin positions could not be read for the mixed-inventory check -- "
                f"{type(exc).__name__}: {exc}"
                for index, _ in opens
            ]
        out: list[str] = []
        for index, intent in opens:
            base = intent.symbol.split("/")[0]
            try:
                spot = _spot_balance(state.balances, base)
            except Exception as exc:
                out.append(f"intent {index}: {intent.symbol} spot inventory could not be read -- {type(exc).__name__}: {exc}")
                continue
            held = margin.get(intent.symbol, 0.0)
            floor = max(state.instruments[intent.symbol].ordermin, FLAT_TOLERANCE)
            if intent.leverage is None and abs(held) > FLAT_TOLERANCE:
                out.append(
                    f"intent {index}: a spot open on {intent.symbol} beside a margin position of {held:.10g} there"
                    " -- the cache's restore does not distinguish them"
                )
            elif intent.leverage is not None and spot >= floor:
                out.append(
                    f"intent {index}: a margin open on {intent.symbol} beside {spot:.10g} {base} spot inventory"
                    " -- the cache's restore does not distinguish them"
                )
        return out

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
        """The timer's whole authority over an in-flight intent. A RESTING order, or a reprice
        waiting for its tick, is revocable or time-boxable: a cancel is already outstanding in
        `cancelling`, and an IOC resolves at the venue within the tick rather than sitting there."""
        active = self._active
        if active.phase == "awaiting_quote":
            if now > active.quote_deadline:
                self._finish_active("refused", (f"no quote within {int(_QUOTE_WAIT.total_seconds())}s",))
            return
        if active.phase == "awaiting_reprice":
            # Nothing rests, so a revoke ends the intent on this tick with no cancel to wait on; the
            # checks are `resting`'s, in `resting`'s order, after `_resubmit`'s completion test: a
            # detached fill can complete the intent inside the wait, and a feed silent from then on
            # would otherwise revoke what has already filled.
            if active.target_qty - active.filled < active.constraints.lot_step:
                self._finish_active("filled", (), active.filled)
            elif not _level_permits(verdict.level, active.intent):
                active.revoke_reasons = tuple(verdict.reasons)
                self._finish_revoked(active)
            elif active.last_quote_at is not None and now - active.last_quote_at > _QUOTE_SILENCE:
                active.revoke_reasons = ("quote_silence",)
                self._finish_revoked(active)
            elif now > active.timebox_at:
                try:
                    self._time_box_with_nothing_resting(active)
                except Exception:
                    # In `execute` mode the box fires the IOC, a resubmission, so a raise takes the quote
                    # handler's refusal, `filled` carried, `_submit`'s rule.
                    logger.exception("executor time-box handling raised -- refusing the intent")
                    if self._active is not None:
                        self._finish_active("refused", ("time-box handling failed",), self._active.filled)
            return
        if active.phase != "resting":
            # `cancelling` and `ioc` are both waiting on the venue. An answer that never comes is an
            # unknown outcome, and the intent takes the same ambiguity exit as any other.
            if active.phase_deadline is not None and now > active.phase_deadline:
                self._strand_ambiguous(active, f"no venue answer within {int(_ACK_WAIT.total_seconds())}s of the {active.phase}")
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
            # Only `execute` crosses when its box elapses. Both resting modes exist never to fill,
            # so for them the box cancels and stops there. Written `== "execute"` rather than
            # `!= "rest-cancel"` so a fourth mode inherits the arm that cannot cross; the pin on
            # `MODES` is what forces this line to be re-read when one arrives.
            active.cancel_requested = True
            active.falling_back = active.intent.mode == "execute"
            active.hold_expired = active.intent.mode == "rest-hold"
            active.revoke_reasons = ("time box elapsed",)
            self._enter(active, "cancelling")
            self._cancel(active)

    def _time_box_with_nothing_resting(self, active: _ActiveIntent) -> None:
        """The time-box elapsing while a reprice waits: `_on_cancel_ack`'s requested arm less the
        cancel, since no order is out to cancel."""
        if active.intent.mode == "execute":
            self._fallback(active)
        elif active.intent.mode == "rest-cancel":
            self._finish_active("rest_cancel_ok" if active.filled == 0.0 else "partial", (), active.filled)
        else:
            self._finish_active("rest_hold_expired" if active.filled == 0.0 else "partial", (), active.filled)

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
            state = venue_state_from_cache(self._cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing intent %d of plan %s", index, plan.plan_id, exc_info=True)
            self._refuse_intent(index, ("no venue truth",))
            return

        constraints = state.instruments.get(intent.symbol)
        if constraints is None:
            self._refuse_intent(index, (f"{intent.symbol} is absent from venue truth",))
            return

        decision = _CloseDecision()
        if intent.action == "close":
            decision = self._classify_close(intent, state, verdict.level)
            if decision.refusal is not None:
                self._refuse_intent(index, (decision.refusal,))
                return

        instrument_id = InstrumentId.from_str(INSTRUMENT_IDS[intent.symbol])
        try:
            # Before the subscribe, and guarded like the venue-truth read above: this is the second
            # Cache read of the same instant, and a raise after subscribing would leak the quote
            # subscription until restart.
            own_position_before = sum(
                float(p.signed_qty) for p in self._cache.positions_open(instrument_id=instrument_id, strategy_id=self._strategy_id)
            )
        except Exception:
            logger.warning("own position unreadable -- refusing intent %d of plan %s", index, plan.plan_id, exc_info=True)
            self._refuse_intent(index, ("no venue truth",))
            return
        self._client.subscribe_quotes(instrument_id)
        self._active = _ActiveIntent(
            index=index,
            intent=intent,
            raw_intent=plan.raw["intents"][index],
            instrument_id=instrument_id,
            constraints=constraints,
            phase="awaiting_quote",
            started_at=now,
            quote_deadline=now + _QUOTE_WAIT,
            timebox_at=now + (timedelta(minutes=intent.hold_minutes) if intent.mode == "rest-hold" else _TIME_BOX),
            close_qty=decision.qty if intent.action == "close" else None,
            reduce_only=decision.reduce_only,
            position_before=state.positions.get(intent.symbol, 0.0),
            own_position_before=own_position_before,
        )

    def _classify_close(self, intent: ProbeIntent, state, level: str) -> _CloseDecision:
        """D10's classification, taken at intent start off the venue truth this intent was resolved
        against. A margin closer (leverage present) reads the Cache's live position -- the same
        `sum(signed_qty)` the frozen snapshot already computed, so the sizing and the venue-truth
        artifact can never disagree; a spot disposal reads the newest venue record's balances, and a
        record it cannot read is a refusal rather than a bound that fails open."""
        if intent.leverage is not None:
            return _classify_margin_close(intent, state.positions.get(intent.symbol, 0.0))
        try:
            balances = _newest_venue_balances(self._journal_dir)
        except Exception:
            logger.warning("the newest venue record could not be read -- refusing the disposal", exc_info=True)
            return _CloseDecision(refusal="the venue record could not be read")
        try:
            return _classify_spot_close(intent, balances=balances, level=level)
        except Exception:
            logger.warning("the venue record's balance for %s is unreadable -- refusing", intent.symbol, exc_info=True)
            return _CloseDecision(refusal="the venue record could not be read")

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
            stored = bid is not None and ask is not None
            if stored:
                # Both sides or neither: a reprice needs the near touch and the IOC fallback the
                # far one, and half a book is not a book to price either against.
                active.bid, active.ask = bid, ask
                active.last_quote_at = self._now()
                active.quote_seq += 1
            if active.phase == "awaiting_quote":
                self._first_submission(active)
            elif active.phase == "awaiting_reprice" and stored:
                self._reprice_at_touch(active)
        except Exception:
            logger.exception("executor quote handling raised -- refusing the intent")
            if self._active is not None:
                # `filled` carried, `_submit`'s rule: a resubmission runs here, and a raise after
                # earlier orders filled must not erase what was bought from the operator's summary.
                self._finish_active("refused", ("quote handling failed",), self._active.filled)

    def _limit_price(self, active: _ActiveIntent) -> float | None:
        """The resting price for this intent's side and mode, or None when no usable touch is known.

        `execute` joins the touch -- a buy the bid, a sell the ask; crossing the spread would be
        taking. `rest-cancel` is a drill that must never fill, so it prices `_REST_CANCEL_OFFSET`
        away on the passive side instead: joining the touch can fill in the instant between the
        venue's acknowledgment and this process's cancel. `rest-hold` rests the same way but at the
        distance its own intent declared, because an order meant to sit for many minutes chooses how
        far from the touch it is willing to sit.
        """
        touch = active.bid if active.intent.side == "buy" else active.ask
        if touch is None:
            return None
        if active.intent.mode == "rest-cancel":
            offset = _REST_CANCEL_OFFSET
        elif active.intent.mode == "rest-hold":
            offset = active.intent.offset_pct / 100.0  # the field is PERCENT; the arithmetic is a fraction
        else:
            return touch
        return touch * (1 - offset) if active.intent.side == "buy" else touch * (1 + offset)

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

        instrument = self._cache.instrument(active.instrument_id)
        if instrument is None:
            return "error", f"{intent.symbol}: instrument not found in Cache"

        # `reduce_only` is passed ONLY when the classification set it (a margin closer). Kraken's
        # reduce-only is a margin-order concept, so a spot order never carries it at all.
        flag = {"reduce_only": True} if active.reduce_only else {}
        # `make_qty` REFUSES a quantity that rounds to zero, and it is called outside the try above.
        # What keeps that unreachable is `size_order`: it floors to `lot_step`, so `sized.qty` is a
        # whole number of increments, and the notional floors refuse zero of them. `ordermin` is the
        # usual one, but it reads 0.0 when the venue reports no minimum, and 0.0 < 0.0 refuses
        # nothing -- the floor that always holds is the committed `costmin`, positive on every leg.
        order = self._client.order_factory.limit(
            instrument_id=active.instrument_id,
            order_side=OrderSide.BUY if intent.side == "buy" else OrderSide.SELL,
            quantity=instrument.make_qty(sized.qty),
            price=instrument.make_price(sized.price),
            time_in_force=time_in_force,
            post_only=post_only,
            **flag,
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
            # The startup pass's ONLY witness: whether the order this row stands for was a reducer.
            "reduce_only": active.reduce_only,
            # The quote this order was priced from: two rows of one intent sharing a `quote_seq` were priced off one tick.
            "bid": active.bid,
            "ask": active.ask,
            "quote_seq": active.quote_seq,
        }
        active.priced_seq = active.quote_seq
        params = {"leverage": intent.leverage} if intent.leverage is not None else None
        return self._submit(active, order, params), ""

    def _first_submission(self, active: _ActiveIntent) -> None:
        price = self._limit_price(active)
        if price is None:
            self._finish_active("refused", (f"no usable touch price for {active.intent.symbol}",))
            return
        # A close intent's quantity is D10's, not the plan's: a margin closer is sized from the live
        # position, and a disposal from the qty the venue record did not refute.
        if active.close_qty is not None:
            target_qty = active.close_qty
        elif active.intent.qty is not None:
            target_qty = active.intent.qty
        else:
            target_qty = active.intent.notional_eur / price
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
        self._enter(active, "resting")

    def _reprice(self, active: _ActiveIntent) -> None:
        """Two callers: the venue's synchronous post-only rejection and its accept-then-cancel. The
        rejection arm is unconditional; the accept-then-cancel arm is filtered before it arrives,
        since a rest-hold order's venue cancel is terminal. The counter counts RESUBMISSIONS -- the
        first submission was never a reprice -- so `_MAX_REPRICES` of them happen; the next crossing
        spends the maker budget, and in `execute` mode that crosses through the bounded IOC rather
        than ending the intent, since an unfilled leg strands the probe.

        A crossing says the stored touch is behind the venue's book, so the resubmission prices off
        a tick newer than the one that priced the order it replaces: at once when one has already
        arrived, else from `awaiting_reprice` when `on_quote` stores one; without the wait each
        resubmission rides its own rejection or cancel dispatch, and the whole budget is spent off
        one tick. The wait is entered with the ended order detached, so a fill racing the cancel or
        a replayed ack takes the detached path -- a row append with no state claim, the fill
        credited to the intent -- and spends no budget."""
        if active.cancel_requested:
            # A cancel is already out, so this order is over either way -- but WHY it is out decides
            # what happens next, and the two answers are opposites. A revoke (kill file, disarm,
            # hold, venue offline, quote silence) declared the book untradeable: stop, and never
            # reprice onto exactly that book. The time-box declared only the MAKER attempt over:
            # cross now. Conflating them would silently drop the fallback, and the fallback is why
            # maker-first is acceptable at all -- an unfilled leg strands the probe. Guarded HERE so
            # both crossing surfaces get the distinction from one check.
            if active.falling_back:
                self._fallback(active)
            else:
                self._finish_revoked(active)
            return
        active.reprices += 1
        if active.reprices > _MAX_REPRICES:
            if active.intent.mode == "execute":
                self._fallback(active)
            else:
                self._finish_active("unfilled", ("reprice budget exhausted",), active.filled)
            return
        if active.quote_seq > active.priced_seq:
            self._reprice_at_touch(active)
            return
        active.client_order_id = active.order = None
        self._enter(active, "awaiting_reprice")

    def _reprice_at_touch(self, active: _ActiveIntent) -> None:
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
        if active.target_qty - active.filled < active.constraints.lot_step:
            # A late fill on the order this one replaces can complete the intent before the tick
            # arrives: `_on_fill`'s completion test, so the intent ends `filled`, where sizing would
            # refuse the zero remainder as below the minimum and end it `partial` carrying its whole
            # quantity.
            self._finish_active("filled", (), active.filled)
            return
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
        self._enter(active, next_phase)

    def _enter(self, active: _ActiveIntent, phase: str) -> None:
        """Move to `phase`, arming the venue-answer deadline for the two phases that wait on one and
        clearing it everywhere else -- a stale deadline would strand an intent that is not waiting.

        Entering `resting` also stamps `placed_at`. Both submission paths funnel through here, so an
        order that replaced an earlier one carries its OWN placement time, never the intent's.
        """
        active.phase = phase
        active.phase_deadline = self._now() + _ACK_WAIT if phase in ("cancelling", "ioc") else None
        if phase == "resting":
            active.placed_at = self._now()

    def _strand_ambiguous(self, active: _ActiveIntent, reason: str) -> None:
        """The one exit for an outcome the venue never established: journal the intent ambiguous and
        halt the plan. Nothing is submitted, and the executor is free to pick up a later plan --
        parking the intent instead would leave `self._plan` set and silently ignore every one."""
        logger.critical("intent %d of plan %s: %s -- the plan stops here", active.index, self._plan.plan_id, reason)
        self._journal_intent(active.index, "ambiguous", (reason,), active.filled)
        _inc_order("ambiguous")
        self._drop_remainder_after_ambiguity(active)

    def _revoke(self, active: _ActiveIntent, reasons) -> None:
        """Pull the resting order and stop: NO fallback follows a revocation. Whatever revoked it --
        the kill file, a disarm, the hold, the venue going offline, a dead quote feed -- is a reason
        not to be at the venue at all, and a marketable IOC would be the most aggressive order this
        path can emit. Terminal on the cancel ack, where the row is written."""
        active.cancel_requested = True
        active.falling_back = False
        active.revoke_reasons = tuple(reasons)
        self._enter(active, "cancelling")
        self._cancel(active)

    def _cancel(self, active: _ActiveIntent) -> None:
        try:
            self._client.cancel_order(active.order.client_order_id)
        except Exception:
            # No retry and no fallback: the order may still rest, and the intent stays in
            # `cancelling` -- an open ledger row for reconciliation, and no further order.
            logger.critical("cancel of %s raised -- the order may still rest at the venue", active.client_order_id, exc_info=True)

    # --- the weekly tracking-error trip ----------------------------------------------------------

    def on_boundary(self, boundary: datetime) -> None:
        """The 4-hourly boundary alert's one call into the executor, made after that boundary's
        cycle has journaled.

        THE call site, and the whole reason this is not on the timer: every `_evaluate` on the tick
        path sits behind an operator-written plan file, so a trip hooked there could only fire while
        a plan was running -- never in the stopped-placing state it exists to catch. The alert chain
        reads neither the plan file nor the venue, and it fires whether or not anything is trading.

        Wrapped whole, and the wrapping is not defensive habit: the caller invokes this from a
        `finally`, so a raise here would either reach the alert chain or REPLACE an in-flight
        exception from the cycle with one from a measurement.
        """
        try:
            self._record_series_birth()
            self._evaluate_tracking(boundary)
        except Exception:
            # Publishes, rather than falling silent: an escape here leaves the last verdict standing
            # on the board, so a trip that has stopped working reads exactly like one that keeps
            # passing. Same opening phrase as every other refusal, so ONE grep finds them all --
            # this one carries a traceback under it. The metrics hook is itself exception-guarded.
            logger.exception("the most recently closed week is not scored: the evaluation itself raised")
            _set_tracking_state(_TRACKING_UNSCORED)

    def _record_series_birth(self) -> None:
        """Write the first-fill birth record, once, at the first boundary that can WITNESS the
        series beginning -- and never again.

        Run on EVERY boundary, disarmed included, and that is the point: it must be written while
        the journal's head is still intact, which is a property of when the engine first FILLS, not
        of when an operator chooses to set a band. An engine that armed a band months into trading
        would otherwise date itself off an already-pruned journal and take the short `held` for the
        truth.

        TWO preconditions, and the second is not redundant. The first -- a journal whose oldest
        boundary carries no fill -- is the same evidence the pruned-head check uses, and it is the
        one this method is gated on being able to ask honestly. But the gate above is
        `path.exists()`, which is "no record yet", NOT "the series has not started": whenever the
        file is absent while fills already exist -- it was lost, or the state directory was rebuilt
        -- this runs against a journal whose head may be long gone, and a prune that happened to cut
        at a QUIET boundary satisfies the first precondition perfectly. The scorer would then agree
        with a record that is a reconstruction, and the false kill this whole file exists to prevent
        comes back through the missing-file path.

        So the second: on the healthy path the record lands at the first boundary AFTER the first
        fill, hours later. A candidate older than `_BIRTH_MINT_WINDOW` is therefore not a birth
        anyone witnessed, it is the earliest fill that happens to have survived, and minting it is
        the one move that can end in a latched kill file. Refusing turns that into a permanent,
        loud refusal instead -- the honest residual, since the position it would need is not on this
        host at all.

        Best-effort in both directions: a failure to read or write leaves no record, and the scorer
        then refuses rather than guessing. Nothing here can raise into the caller's scoring pass.
        """
        path = exec_dir(self._state_dir) / FIRST_FILL_FILE
        if path.exists():
            return
        try:
            docs = exec_records_through(self._journal_dir, self._now())
            fills, _notes = extract_fills([docs[b] for b in sorted(docs)])
            first_fill = min((f.boundary for f in fills if f.base is not None), default=None)
            oldest = min(docs, default=None)
            if first_fill is None or oldest is None or first_fill <= oldest:
                return
            if self._now() - first_fill > _BIRTH_MINT_WINDOW:
                logger.warning(
                    "this engine has no record of when its realized series began and the earliest fill "
                    "the journal still holds is %s, too old to be that beginning -- no week will be "
                    "scored until a human establishes what was held before it",
                    first_fill.isoformat(),
                )
                return
            # Written through a temporary sibling: the reader above is gated on the file EXISTING,
            # so a crash mid-write would leave a truncated record nothing ever repairs -- and the
            # only recovery would be deleting it, which is exactly the reconstruction path this
            # method refuses to take later in life.
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(f"{first_fill.isoformat()}\n")
            os.replace(tmp_path, path)
        except Exception:
            logger.warning("this engine's realized series could not be dated this boundary", exc_info=True)
            return
        logger.info("recorded the realized series' first fill at %s", first_fill.isoformat())

    def _series_birth(self) -> datetime | None:
        """What the birth record says, or None when there is none this process can read."""
        try:
            return datetime.fromisoformat((exec_dir(self._state_dir) / FIRST_FILL_FILE).read_text().strip())
        except FileNotFoundError:
            return None
        except OSError, ValueError:
            logger.warning("the realized series' birth record is unreadable", exc_info=True)
            return None

    def _refuse_tracking(self, reason: str) -> None:
        """No verdict this boundary. Published as its own state so an operator can tell a week that
        was measured and passed from one nothing could score."""
        logger.warning("the most recently closed week is not scored: %s", reason)
        _set_tracking_state(_TRACKING_UNSCORED)

    def _evaluate_tracking(self, boundary: datetime) -> None:
        """Score the most recently CLOSED ISO week and latch the kill switch when its realized mean
        drift exceeds the configured band.

        Carries no durable state whatsoever: the week is re-derived from immutable journal artifacts
        at every boundary, and idempotence comes from the kill file plus `_kill_tripped`. A
        checkpoint would be strictly worse -- `update_submitted_row` files a fill under the boundary
        its ORDER was filed under, so a fill can land in an already-scored boundary days later,
        which a checkpoint loses permanently and a re-derivation folds in at the next boundary.

        Eligibility is each boundary's JOURNALED level, never live config: `restart_hold` is written
        unconditionally at every engine start and cleared only by hand, so a week spent under it
        reads as fully armed while the engine never traded -- `held` frozen, targets moving, and the
        kill file latched on a perfectly healthy engine. The journaled level is the one field that
        reduces arm file, kill file, restart hold, config and venue status together.

        Every other exit is a refusal, never a guess: a week short of its full boundary count, a
        week whose first fill falls inside it, a week the journal cannot price, and a span whose
        oldest boundary already carries a fill (the prune may have taken the position that explains
        it) all decline to decide. Refusing costs a week of coverage; guessing halts live trading.
        """
        band = self._config.tracking_band_bps
        if band is None:
            _set_tracking_state(_TRACKING_DISARMED)  # ships disarmed: with no band nothing can be exceeded
            return
        if not self._config.exec_armed:
            self._refuse_tracking("order submission is not armed in this engine's config")
            return
        if self._kill_tripped or (exec_dir(self._state_dir) / KILL_FILE).exists():
            # The latch is the idempotence. Re-deriving here would rewrite the FIRST reason -- the
            # one that explains why the engine stopped -- with a restatement of it hours later.
            self._refuse_tracking("the kill switch is already latched")
            return
        try:
            self._score_closed_week(_aware_utc(boundary), band)
        except EngineError as exc:
            # Every refusal this arithmetic can raise (a hole in the cycle span, a fill on a symbol
            # outside the basket, a record that cannot be priced) is a reason not to decide -- not a
            # reason to take the engine's telemetry down with a traceback every four hours.
            self._refuse_tracking(str(exc))

    def _score_closed_week(self, boundary: datetime, band: float) -> None:
        week_end = (boundary - timedelta(days=boundary.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = week_end - timedelta(days=7)
        last = week_end - timedelta(hours=_H4)
        label = f"{week_start.isocalendar().year}-W{week_start.isocalendar().week:02d}"
        expected = [week_start + timedelta(hours=_H4 * i) for i in range(_WEEK_BOUNDARIES)]

        # Everything through the week's last boundary, never just the week: `held` is cumulative
        # from the first fill ever, so a week-scoped read would report the book bought earlier as
        # drift it never had.
        exec_docs = exec_records_through(self._journal_dir, last)
        cycles = _cycle_records_through(self._journal_dir, last)
        week = [b for b in expected if b in exec_docs and b in cycles]
        if len(week) < _WEEK_BOUNDARIES:
            self._refuse_tracking(
                f"{label} has {len(week)} of the {_WEEK_BOUNDARIES} boundaries a complete week holds -- "
                "a week the engine did not live through is not comparable to one it did"
            )
            return
        held_back = [b for b in week if exec_docs[b]["level"] != GateLevel.FULL]
        if held_back:
            self._refuse_tracking(
                f"{label} spent {len(held_back)} of its {_WEEK_BOUNDARIES} boundaries below the full "
                f"level (first at {held_back[0].isoformat()}) -- the engine was not free to trade it"
            )
            return

        fills, _notes = extract_fills([exec_docs[b] for b in sorted(exec_docs)])
        first_fill = min((f.boundary for f in fills if f.base is not None), default=None)
        if first_fill is None:
            self._refuse_tracking("no model-leg fill has been journaled yet -- the realized series has not started")
            return
        birth = self._series_birth()
        if birth != first_fill:
            # NOT "does the oldest surviving boundary carry a fill". That question passes whenever
            # the prune happens to have cut at a quiet boundary, and then `held` silently omits
            # everything bought before the horizon: the true positive's own fixture reads 298.4 bps
            # against a 120 bps band and latches the kill file on a perfectly healthy engine. The
            # birth record answers the question that is actually being asked -- is the head of this
            # series still on disk -- and when it is not, there is nothing to score with, ever
            # again, because those fills are gone from this host. That refusal is permanent by
            # design and loud; see the runbook.
            self._refuse_tracking(
                f"the journal's earliest fill is {first_fill.isoformat()} but this engine's realized "
                f"series began at {birth.isoformat() if birth is not None else '(no record)'} -- the "
                "position bought before that is not on this host, so no week can be scored against it"
            )
            return
        if first_fill >= week_start:
            # `>=`, never `>`: a first fill landing exactly ON the Monday boundary -- what an
            # operator arming at a week boundary produces -- would otherwise leave the week
            # containing it fully scored, ramp and all, which is the one week D10 excludes by name.
            # The week the series STARTED in is not comparable to a settled one whichever way it is
            # read: its pre-fill cycles hold a book the engine had not bought yet, so counting them
            # averages a full 10000 bps a cycle into the mean, while dropping them -- which is
            # exactly what the span below does -- scores a fraction of a week under a whole week's
            # name. A week entirely before the first fill is not measured at all, and takes the
            # same exit.
            self._refuse_tracking(
                f"the realized series starts at {first_fill.isoformat()}, at or after {label} began "
                "-- the week the series starts in is measurable on only the part that follows it"
            )
            return

        # The span starts at the first fill, not at the journal's start: earlier cycles contribute
        # nothing to `held`, and requiring them to be priceable would make every artifact written
        # before `closes` existed refuse a week it cannot affect.
        stages = [_stage(cycles[b]) for b in sorted(cycles) if first_fill <= b <= last]
        # NAV sets both halves of the comparison (a target is `weight * nav / close`, and the
        # drift is divided by `nav`), so a `shadow_nav_eur` converge used to re-score weeks that
        # closed under the OLD value against the new one. Each record now journals the NAV it was
        # priced against and is scored under THAT; the scalar below is the fallback for records
        # written before the field existed, which age out with the journal's retention.
        rows = realized_drift(stages, fills, self._config.shadow_nav_eur)["cycles"]
        scored = set(week)
        # The straddle refusal above is what guarantees every one of the week's boundaries is in the
        # span, and so what makes this a mean over the WHOLE week rather than over its tail.
        values = [row["drift_bps"] for row in rows if datetime.fromisoformat(row["cycle_ts"]) in scored]
        mean = sum(values) / len(values)
        logger.info("%s tracked %.1f bps of NAV across %d cycles, against a %.1f bps band", label, mean, len(values), band)
        if mean > band:
            _set_tracking_state(_TRACKING_BREACHED)
            self._trip_kill(
                f"{label} tracked {mean:.1f} bps of NAV across its {len(values)} cycles, outside the "
                f"{band:.1f} bps band this engine is allowed to drift from its targets"
            )
            return
        _set_tracking_state(_TRACKING_WITHIN_BAND)

    # --- the kill switch -----------------------------------------------------------------------

    def _trip_kill(self, reason: str) -> None:
        """Latch the execution kill switch: create the kill file, pull everything the Cache reports
        still working at the venue, and stop the plan. "Everything the Cache reports" is narrower
        than "everything working" by any order the Cache does not hold; `_cancel_resting` says which.

        The file's semantics are `00088`'s, untouched -- presence is the whole protocol, the contents
        are for the human who finds it, and NO code path anywhere clears it. That is what makes this
        the LAST thing this process decides about trading: from here every gate evaluation reads
        `none`, so every further intent refuses, across restarts, until a person says otherwise.

        Idempotent through a process-local flag, which is not a clear: a second divergence must not
        overwrite the first one's reason -- the first is the one that explains the state -- nor
        re-halt a plan that is already gone.
        """
        if self._kill_tripped:
            return
        self._kill_tripped = True
        logger.critical("execution kill switch tripped -- %s; cancelling resting orders and stopping the plan", reason)
        self._write_kill_file(reason)
        active = self._active
        self._cancel_resting(active)
        if active is not None:
            try:
                self._client.unsubscribe_quotes(active.instrument_id)
            except Exception:
                logger.warning("unsubscribe failed for %s -- continuing", active.instrument_id, exc_info=True)
            # The intent was mid-flight, so nothing else will ever journal it: without this its line
            # in the operator's summary stays `pending` forever, next to a plan that plainly stopped.
            self._journal_intent(active.index, "revoked", (f"kill switch tripped -- {reason}",), active.filled)
        if self._plan is not None:
            self._halt_plan(
                active.index if active is not None else self._index - 1,
                f"not run -- the kill switch tripped: {reason}",
            )
        self._active = None
        self._plan = None
        self._index = 0
        # Publish now rather than waiting for the tick: with no plan running, the idle path reads
        # the gate once a period (`_refresh_gate`), so the trip gauge would otherwise sit at its
        # pre-trip value for up to `_GATE_REFRESH`. This evaluation stamps the heartbeat too, its
        # `heartbeat` left at the default True.
        self._evaluate(self._now())

    def _write_kill_file(self, reason: str) -> None:
        """Presence is load-bearing, the text is not -- so the text is written for whoever finds it
        mid-incident: what diverged, on which order or intent, and when."""
        path = exec_dir(self._state_dir) / KILL_FILE
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"{self._now().isoformat()} {reason}\n")
        except OSError:
            logger.critical(
                "the kill file %s could not be written -- this process refuses every further plan and order from "
                "here, but NOTHING ON DISK will stop the next one: stop the engine by hand",
                path,
                exc_info=True,
            )

    def _cancel_resting(self, active: _ActiveIntent | None) -> None:
        """A trip must leave NOTHING working at the venue: the in-flight order AND everything else
        the Cache reports open, which after a restart includes orders the startup pass deliberately
        left resting. That pass makes the same call when it starts up onto a latched kill -- a
        tripped switch has no order it is willing to leave working, however well justified.

        An order ALREADY RESTING at the venue when this process started -- a previous process's, or
        one placed by hand before the start -- reaches the Cache only through startup reconciliation:
        the executions subscription carries `snap_orders:false`, so no WS event heals it afterwards.
        On the pinned wheel that reconciliation reads open orders unscoped and resolves both of
        Kraken's pair spellings through the listing's altname index, and an open order whose pair it
        cannot resolve fails the read and stops the node from starting. So the list below holds the
        orders resting at the start, named by their Kraken txid rather than this engine's id, and
        the cancel goes out by that name. `filter_unclaimed_external_orders=False` in
        `cli/engine/node.py` is what keeps such an order in the Cache at all.

        Not every resting order reaches the list, though: an order row the adapter cannot parse, or
        whose report the library cannot build an order from, is dropped with a log line of the
        library's own, and the node starts without it. The cancel is issued PER ORDER off the list,
        where flatten's is account-wide, so such an order is never requested. No retry of the trip
        reaches one, and neither does a wider Cache query, which reads the same populated set: only a
        venue-side open-order read at trip time would. The startup pass logs one CRITICAL only when a
        ledger row recorded its txid, and an order no row names is seen by nothing in this process.

        Best-effort throughout, and never able to stop the trip: a cancel is a request rather than an
        outcome, the rows keep their open states, and a fill racing a cancel still lands through the
        attachment map.
        """
        requested: set[str] = set()
        if active is not None and active.order is not None:
            active.cancel_requested = True
            active.falling_back = False
            requested.add(str(active.client_order_id))
            self._cancel(active)
        try:
            resting = list(self._cache.orders_open(venue=_VENUE))
        except Exception:
            logger.critical("open orders could not be read while tripping -- others may still rest at the venue", exc_info=True)
            return
        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            if client_order_id in requested:
                continue
            try:
                self._client.cancel_order(order.client_order_id)
            except Exception:
                logger.critical(
                    "cancel of %s raised while tripping -- it may still rest at the venue", client_order_id, exc_info=True
                )

    def _trip_on_fill(self, event) -> bool:
        """The three fill-time divergences, checked in this order and BEFORE the fill is dispatched
        anywhere. Returns True when one fired, and the caller then drops the event: the plan is gone
        and nothing further may be decided from a fill that should not exist.

        The unknown-order trip only ever sees fills the engine's own ledger vouches for, and that is
        what makes it safe to have at all: a sanctioned account-external fill -- the owner settling a
        position by hand in the venue's UI, mid-probe -- must never reach this check, and stay what
        it is, venue truth for reconciliation to read. Latching the kill switch on the probe's own
        final act is the failure this scoping exists to prevent. Two paths reach here and each keeps
        that scoping its own way: `on_order_event` carries only the strategy's own order topic, whose
        events are by construction this engine's own orders -- this process's submissions, and the
        ones the cache restored under its id, attached at construction (`_read_restored`); `_on_external_event` carries the
        `events.order.EXTERNAL` topic, which is account-wide, and it is that method's unmatched
        early-return -- no `_attached` row, so counted, logged, and dropped -- that keeps the hand
        settle away from here. Delete that early-return and this trip becomes account-wide.

        Per-order before per-intent, because when both are true the per-order one is the more
        specific fact: it names the one order that did it, where the cross-order sum would send an
        operator to the ladder's remainder arithmetic instead.
        """
        client_order_id = str(getattr(event, "client_order_id", ""))
        attached = self._attached_for(event)
        if attached is None:
            # Says "no open record", not "never submitted": a terminal row, or one older than the
            # ledger scan window, is not in the attachment map either, and firing is still right
            # there -- a fill on an order this process already accounted for is its own divergence.
            self._trip_kill(f"a fill arrived for order {client_order_id}, for which this engine holds no open order record")
            return True
        boundary, row = attached
        qty = self._fill_credit(event, row, float(event.last_qty))
        ordered = _ordered_qty(row)
        if row["filled_qty"] + qty > ordered + _OVERFILL_TOLERANCE:
            self._record_trip_fill(boundary, row, event, qty)
            self._trip_kill(
                f"order {_row_label(row, _row_venue_order_id(row))} has now filled {row['filled_qty']:.10g} "
                f"of the {ordered:.10g} it was submitted for"
            )
            return True
        active = self._active
        if active is not None and self._claims(row, active) and active.filled + qty > active.target_qty + _OVERFILL_TOLERANCE:
            self._record_trip_fill(boundary, row, event, qty)
            self._trip_kill(
                f"intent {active.index} has now filled {active.filled:.10g} across its orders, "
                f"more than the {active.target_qty:.10g} it asked for"
            )
            return True
        return False

    def _record_trip_fill(self, boundary: datetime, row: dict, event, qty: float) -> None:
        """The fill that is about to trip the switch still gets its forensic row. It HAPPENED at the
        venue, and the no-fill-without-a-record invariant has no divergence exemption -- the operator
        reading the kill reason needs the fill itself sitting next to it. Wrapped, because a ledger
        failure may never cost the trip; the in-process quantities are credited either way, since
        they track what filled rather than what could be written down.
        """
        client_order_id = row["client_order_id"]
        try:
            update_submitted_row(
                self._journal_dir, boundary, client_order_id, event=self._fill_payload(event, qty), add_filled_qty=qty
            )
        except Exception:
            logger.critical("the fill that tripped the kill switch could not be journaled for %s", client_order_id, exc_info=True)
        row["filled_qty"] = row["filled_qty"] + qty
        active = self._active
        if active is not None and self._claims(row, active):
            active.filled += qty
        self._publish_fill(event)

    def _claims(self, row: dict, active: _ActiveIntent) -> bool:
        """Whether `row`'s order belongs to the intent running right now -- same plan, same index.
        That, and never the order id, is what makes another order's fill part of THIS intent's
        cumulative quantity."""
        return self._plan is not None and row.get("plan_id") == self._plan.plan_id and row.get("intent_index") == active.index

    def _mirror_row_fill(self, client_order_id: str, qty: float) -> None:
        """`update_submitted_row` mutates the STORED document, never the row dict this process holds
        in `_attached`. Without this mirror the per-order overfill trip would compare every fill
        after the first against a `filled_qty` frozen at write-ahead time, and an order could double
        its quantity unnoticed."""
        attached = self._attached.get(client_order_id)
        if attached is not None:
            attached[1]["filled_qty"] = attached[1]["filled_qty"] + qty

    def _reconcile_terminal(self, active: _ActiveIntent) -> None:
        """The post-terminal reconciliation: what this intent's fills say this engine's OWN position
        should now be, against what the Cache says it is.

        Scoped to this engine's strategy on BOTH ends, never to the instrument: an instrument-scoped
        read carries holdings this engine never ordered, and an operator's hand settle must reach no
        trip, no row and no cancel (spec 00098 D1). `position_before` stays instrument-scoped
        because SIZING trades the real book; only this comparison is narrowed.

        The tolerance is the instrument's own lot step -- the smallest quantity the venue can even
        express, so nothing tradeable hides under it. Anything larger is either a fill this engine
        never saw or one it saw and mis-accounted, and both are reasons to stop rather than to place
        the next order against a position it cannot describe.

        DELIBERATELY NOT reached from the five ambiguous exits (a raising submit, an unclassifiable
        rejection, a cancel the venue rejected, a cancel or IOC it never answered, and a terminal
        this engine minted for itself rather than received): each of those
        means an order may still be live and may still legitimately fill, so `filled` is not an
        expectation to hold the Cache to, and checking there would fire on a delayed venue answer
        rather than on a divergence. The cost is real and accepted: a divergence born during an
        ambiguous intent is not caught here, and the next intent's `position_before` baselines it
        away. What covers it instead is that an ambiguous outcome already stops the whole plan and
        leaves an open row for the attended operator, which is the state that path exists to produce.
        """
        expected = active.own_position_before + (active.filled if active.intent.side == "buy" else -active.filled)
        try:
            actual = sum(
                float(p.signed_qty)
                for p in self._cache.positions_open(instrument_id=active.instrument_id, strategy_id=self._strategy_id)
            )
        except Exception:
            # The venue-truth read at intent start proved this same Cache readable minutes ago, so a
            # raise here is an anomaly rather than routine -- and an unverifiable position after a
            # fill is not something to trade on.
            logger.critical("the %s position could not be read after intent %d", active.intent.symbol, active.index, exc_info=True)
            self._trip_kill(
                f"the {active.intent.symbol} position could not be read after intent {active.index}, so nothing can "
                "confirm what this engine's orders did to it"
            )
            return
        if abs(actual - expected) > active.constraints.lot_step:
            self._trip_kill(
                f"{active.intent.symbol} holds {actual:.10g} in this engine's own position after intent "
                f"{active.index}, not the {expected:.10g} its fills account for"
            )

    # --- order events --------------------------------------------------------------------------

    def on_order_event(self, event) -> None:
        try:
            self._on_order_event(event)
        except Exception:
            # Bookkeeping, not a submission: log it and leave the row as it stands rather than
            # dropping a plan whose order may be live.
            logger.exception("executor order-event handling raised -- continuing")

    def _resubmit_on_event(self, active: _ActiveIntent, resubmission) -> None:
        """The quote handler's rule for a raise inside a resubmission: `on_order_event`'s catch-all
        refuses nothing, and would leave the intent on the order the venue has just ended."""
        try:
            resubmission(active)
        except Exception:
            logger.exception("executor order-event resubmission raised -- refusing the intent")
            if self._active is not None:
                self._finish_active("refused", ("order-event handling failed",), self._active.filled)

    def _on_order_event(self, event) -> None:
        # D11's fill-time trips run FIRST, before any row update and before the in-flight/detached
        # split: an unknown order has no row to update, and an overfill must not be credited to a
        # ladder that would then size its next order against it.
        if type(event).__name__ == "OrderFilled" and self._trip_on_fill(event):
            return
        active = self._active
        client_order_id = str(getattr(event, "client_order_id", ""))
        if active is None or active.client_order_id is None or client_order_id != active.client_order_id:
            self._on_detached_event(event)
            return

        name = type(event).__name__
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)

        if name in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):
            # This terminal was MINTED by the execution engine, not sent by the venue: past its
            # in-flight retry budget it stops waiting on an unanswered order and publishes the
            # `OrderCanceled`, or the `INFLIGHT_TIMEOUT` `OrderRejected`, on its own authority. It
            # says nothing about what happened at the venue, so the order may still be resting --
            # which is the ambiguous exit's whole definition, and exactly what `_ACK_WAIT` expiring
            # already means. Taken ABOVE the dispatch so no arm below can reach `_fallback`,
            # `_reprice` or `_finish_revoked` on it, and so an entry added to
            # `_KRAKEN_ERROR_MARKERS` cannot turn the rejection into a resubmission.
            #
            # `OrderFilled` is excluded deliberately. A reconciled fill is the venue's OWN report
            # transcribed late -- its quantity and price are the venue's, and only the trade id is
            # minted, because the report carries none -- so it is a fill that HAPPENED, and its row,
            # its quantity credit and its published fill are all owed for money that moved: no fill
            # without a record. Dropping the credit would also make the next resubmission over-ask
            # by exactly that quantity, which is this same double exposure in the other direction.
            #
            # What covers a fill that did NOT happen is narrower than it looks, and naming the limit
            # is the point. Reconciliation tops an order up to the venue report's CUMULATIVE
            # quantity and infers nothing unless the report exceeds what the order already holds, so
            # a stale or replayed report cannot over-report; upstream's `check_overfill`, with
            # `allow_overfills` False, refuses an application past the order's own quantity; and the
            # fill-time trips above latch on anything past the quantity the row was submitted for.
            # `_reconcile_terminal` is NOT one of them: a minted fill reaches the order and the Cache
            # before it is dispatched, so it moves `active.filled` and the strategy-scoped position
            # that comparison holds it against by the same amount, and the check passes. A phantom
            # INSIDE the remaining quantity, born of a venue misreport, is past every guard this
            # process has.
            payload["reconciliation"] = True  # the ledger's own evidence of the mint, once the venue's report settles the row
            self._update_row(active, state="ambiguous", event=payload)
            self._arm_reread_after_mint()  # the plan's own order: F2's shape, where the cut's DISCONNECTED then holds it
            self._strand_ambiguous(active, f"{name} was reconciled, not received -- the venue never answered")
            return

        if name == "OrderAccepted":
            # Deliberately does NOT set `phase = "resting"`. The submission paths already did, and
            # the adapter acknowledges an IOC exactly like a GTC: forcing `resting` here would put
            # a fallback attempt back in the reprice regime, so its unfilled remainder returning as
            # an unrequested cancel would read as the crossing surface and submit a new post-only
            # GTC after the time-box had already expired.
            #
            # The venue order id is recorded here because nothing else can find this order after a
            # restart: the adapter's order reports carry no client order id, so reconciliation names
            # the order by its Kraken txid and this engine's own id no longer resolves it.
            payload["venue_order_id"] = str(event.venue_order_id)
            self._update_row(active, state="accepted", event=payload)
            _inc_order("accepted")
            if active.intent.mode == "rest-cancel":
                # The drill's whole shape: rest, be acknowledged, come straight back off the book.
                active.cancel_requested = True
                self._enter(active, "cancelling")
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

        if name == "OrderCancelRejected":
            # The venue positively says the cancel did NOT take, so the order may still rest --
            # while whatever asked for the cancel (a kill file, the time-box) says it must not.
            # Nothing further may be submitted against a position this process can no longer
            # describe. The row keeps its OPEN state; only the intent is journaled.
            logger.critical(
                "cancel of %s was REJECTED by the venue -- the order may still rest; the plan stops here",
                active.client_order_id,
            )
            self._update_row(active, event=payload)
            self._journal_intent(active.index, "ambiguous", (f"cancel rejected: {reason}",), active.filled)
            _inc_order("ambiguous")
            self._drop_remainder_after_ambiguity(active)
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

        A rejection this engine minted for itself never arrives here: `_on_order_event` routes it
        straight to the ambiguous exit above the dispatch. So a marker added to
        `_KRAKEN_ERROR_MARKERS` is a statement about the VENUE's error text only, and cannot
        promote an in-flight timeout into a terminal verdict.
        """
        if due_post_only or _POST_ONLY_MARKER in reason:
            self._update_row(active, state="rejected", event=payload)
            _inc_order("rejected")
            self._resubmit_on_event(active, self._reprice)
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
                self._resubmit_on_event(active, self._fallback)
                return
            if active.intent.mode == "rest-cancel":
                self._finish_active("rest_cancel_ok" if active.filled == 0.0 else "partial", (), active.filled)
                return
            if active.intent.mode == "rest-hold" and active.hold_expired:
                self._finish_active("rest_hold_expired" if active.filled == 0.0 else "partial", (), active.filled)
                return
            # A rest-hold order the kill file (or any other revoke) took off the book falls through
            # to `_finish_revoked`, which is correct: it was revoked, not held to its expiry.
            self._finish_revoked(active)
            return

        # Both unrequested cases write the SAME row state, so both count it -- written once above
        # the branch rather than in each arm, because the arms drifting apart is exactly how an
        # unfilled fallback ladder came to advance `submitted` with no terminal outcome behind it.
        self._update_row(active, state="venue_canceled", event=payload)
        _inc_order("venue_canceled")
        if active.phase == "ioc":
            self._resubmit_on_event(active, self._fallback)
            return
        if active.intent.mode == "rest-hold":
            # Spec 00108 D5. This arm runs for ANY venue-originated cancel or expiry while the
            # phase is not `ioc` -- it tests nothing about crossing -- and a resting rest-hold order
            # is a drill's SUBJECT. Re-placing it at the current touch under a new client-order-id
            # swaps the subject mid-induction, silently undoes an operator's own cancel at the
            # venue, and contaminates exactly the continuity drill G exists to measure.
            self._finish_active("rest_hold_venue_canceled" if active.filled == 0.0 else "partial", (), active.filled)
            return
        self._resubmit_on_event(active, self._reprice)

    def on_external_order_event(self, event) -> None:
        try:
            self._on_external_event(event)
        except Exception:
            # Bookkeeping on an adopted order, never a submission: log and continue (the
            # on_order_event idiom).
            logger.exception("executor external-order-event handling raised -- continuing")

    def _venue_terminal_state(self, event) -> str | None:
        """The row state a non-fill event writes: `ambiguous` for a terminal the engine minted, else
        read off the VENUE's own order, and none for a refused cancel, which logs CRITICAL.

        An event the execution engine MINTED for itself writes `ambiguous`, and that is decided
        first, before the order is even read. Past its in-flight retry budget the engine stops
        waiting on an unanswered order and publishes that order's terminal itself, flagged
        `reconciliation`; the Cache's order has already taken it, so its status reads CANCELED or
        EXPIRED or REJECTED exactly as a venue answer would. It is not one. Nobody at the venue
        confirmed anything and the adopted order may still be resting, so a terminal state here
        would put a venue claim in the ledger on this engine's own authority -- and close a row that
        `_OPEN_ORDER_STATES` then never re-attaches, leaving a live order untracked for the life of
        the process. `ambiguous` claims nothing about the venue, is the active path's word for the
        same event, and keeps the row in the re-attach set: the event appends as evidence, with the
        flag recorded so the ledger can tell the mint from the venue's own ack once the row is
        settled, the entry stays in `_attached` for a fill that can still arrive, and the venue's own
        report settles the row -- the re-read pass's on the next tick with nothing in flight
        (`_arm_reread_after_mint`), or a startup's inside the re-attach window where the pass could
        not read; until then the pages have the operator read Kraken's open orders, which tell a
        cancel the venue executed unacknowledged from one that did not reach it, and the pass cancels
        one still resting by txid on the bare client, the hand cancel being the fallback its CRITICAL
        lines name. The line is a
        WARNING and pages nothing: on the pinned wheel the venue's answer to a cancel of an order
        reconciled as external is not one this engine applies, so the mint is the expected end of an
        adopt-pass cancel and not a fault. Keyed on the flag and the terminal's name, as the
        own-order path is, and never on the mechanism that set the flag: a synthesis route nothing
        here enumerates is covered by construction, while the library's non-terminals carry the flag
        too and a flagged acceptance or cancel-side event writes nothing; the cost when the flag
        sits on a venue-derived terminal is one row the re-read pass settles on its next tick, the direction
        to be wrong in. `OrderFilled` never reaches this method -- the caller's fill branch returns
        above it -- so a reconciled fill keeps its row, its credit and its counter without anything
        here having to exempt it.

        The order already carries the event by the time this runs -- an order event is applied to the
        order and to the Cache before it is dispatched, which tests/test_engine_executor.py measures
        against a real engine -- so its status is the settled answer to what the event did, and
        `_ADOPTED_TERMINAL_STATES` is proven total over every closed status the library defines.

        It is also the more truthful answer wherever the order's status and the event's name
        disagree, and they do exactly when the state machine REFUSED the event and it was published
        anyway. `ownTrades` and `openOrders` are separate Kraken WS channels with no cross-stream
        ordering guarantee, so a stale `OrderExpired` can land after a cancel this engine asked for
        and got: the name claims the venue ended the order, the order says CANCELED, and the order
        is right.

        Three things write nothing here -- no terminal state, row untouched: a status outside the
        map (every OPEN one, PENDING_CANCEL among them, the status behind the `OrderPendingCancel`
        the adopt pass's and a trip's cancels put on this path), an order the Cache does not hold,
        and a Cache that cannot be read at all; a refused cancel writes nothing too, decided before
        the read and logged CRITICAL, since the order may still rest where the cancel is not re-sent
        and, where the pass cancelled it and its sweep ran, after the sweep has written its intent;
        absent from Kraken's open orders, the venue had already ended it. The read goes through the
        handle taken at construction and not through the client: `OrderPendingCancel` is dispatched
        while the client's own `cancel_order` still runs, and the client's `cache` getter raises
        `Already mutably borrowed` there -- the strategy's PyO3 cell is what that command holds; the
        Cache itself is free, and the handle reads PENDING_CANCEL. A read that raises all the same
        is caught rather than let escape, which would abandon the whole handler and cost the row its
        event payload -- the forensic record this path exists to keep -- to decide a state those
        events never carried anyway.
        """
        if type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):
            logger.warning(
                "%s for %s was reconciled, not received -- no venue answer reached this engine; its row reads ambiguous "
                "until the re-read pass settles it from the venue's own report",
                type(event).__name__,
                getattr(event, "client_order_id", "?"),
            )
            self._arm_reread_after_mint()
            return "ambiguous"
        if type(event).__name__ == "OrderCancelRejected":
            # The venue positively says the cancel did not take, so the order may still rest where the cancel is not re-sent
            # and, where the pass cancelled it and its sweep ran, after the sweep has written its intent; absent from Kraken's
            # open orders, the venue had already ended it. The hand cancel is the operator's, the own-order path's line.
            logger.critical(
                "cancel of adopted order %s was REJECTED by the venue -- the order may still rest, and the cancel is not "
                "re-sent: cancel it by hand on Kraken's open-orders page",
                getattr(event, "client_order_id", "?"),
            )
            return None
        try:
            order = self._cache.order(event.client_order_id)
        except Exception:
            logger.warning(
                "the venue order behind %s could not be read -- its row keeps the state it has",
                getattr(event, "client_order_id", "?"),
                exc_info=True,
            )
            return None
        return None if order is None else _ADOPTED_TERMINAL_STATES.get(order.status)

    def _on_external_event(self, event) -> None:
        """Events from `events.order.EXTERNAL` (spec 00098 D1): the delivery path for orders this process
        adopted at startup under the venue's txid, filtered by disposition BEFORE anything else runs. A
        restored own order keeps its own id and its events reach the own topic (spec 00120 D12); an
        EXTERNAL copy the store restored keeps this path and is handled here as a restored own order is
        (`_restored_row`).

        Matched (the ledger vouches for the order): delegate into the existing pipeline --
        `_trip_on_fill` FIRST, exactly as the own-topic path does, so a matched overfill trips the
        kill with the same arithmetic; a clean fill lands in `_on_detached_event`, which already
        appends the row by the order's own boundary, mirrors the quantity, and publishes counters.
        A fill completing the ledgered quantity additionally writes the row's state `filled` --
        nautilus publishes no terminal event after a resting order's final fill, so without that the
        row would read open forever -- and every other event asks `_venue_terminal_state`, which
        reads the VENUE's own order rather than the event's class name. `canceled` there makes no
        we-requested claim: the dominant real source on this path is a cancel THIS process sent --
        from the adopt pass, or from a trip -- whose ack now arrives matched, and `venue_canceled`
        would be false for exactly those.

        What NEITHER of those does is end tracking: no path here pops `_attached`, exactly as the own
        path does not. `ownTrades` and `openOrders` are separate Kraken WS channels with no
        cross-stream ordering guarantee, so a fill can arrive after the terminal ack or after the
        completing fill -- and an entry popped at either point would send it to the unmatched branch
        to be counted and never journaled, breaking no-fill-without-a-record on the one path built to
        restore it. Retained, that fill journals as a detached append when it fits inside the
        ledgered quantity and latches the overfill trip when it does not: the own path's semantics,
        on both paths.

        Unmatched (the operator's hand settle, any genuinely external act): counted, logged, and
        NOTHING else -- it must never reach `_trip_on_fill`, a row write, or a cancel. That filter
        is what keeps the unknown-order trip scoped while this second stream exists at all.
        The set is wider than "no ledgered row" by the rows the startup pass could not match to an
        order: a row that recorded no single txid names an order the Cache holds only under its
        txid, so it was never attached, and a fill on it lands here -- no row write, no counters, no
        overfill trip -- with nothing in the log line saying the ledger knew the order.
        """
        client_order_id = str(getattr(event, "client_order_id", ""))
        attached = self._attached_for(event)
        name = type(event).__name__
        if attached is None:
            _inc_external("unmatched")
            logger.info(
                "external order event ignored: %s for %s on %s -- no ledgered adopted row",
                name,
                client_order_id,
                getattr(event, "instrument_id", "?"),
            )
            return
        _inc_external("matched")
        if name == "OrderFilled":
            if self._trip_on_fill(event):
                return
            self._on_detached_event(event)
            # `_on_detached_event` mirrored the fill into the attached row, so this reads the
            # post-fill total. The unpack stays inside each branch deliberately: the early return
            # above is meant to be the ONLY thing between an unmatched event and this pipeline, and
            # a hoisted unpack would quietly become a second one.
            boundary, row = attached
            # Guarded on the MIRRORED state so the completion fires once: a further fill on a
            # completed row is an overfill, and `_trip_on_fill` above has already latched for it.
            # A row whose ledgered qty is unreadable reads 0.0 and never arrives here at all --
            # its first fill trips there too.
            if row.get("state") != "filled" and row["filled_qty"] >= _ordered_qty(row) - _OVERFILL_TOLERANCE:
                update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state="filled")
                row["state"] = "filled"
                _inc_order("filled")
                self._settle_restored_intent(boundary, row)
            return
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)
        if name in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):
            payload["reconciliation"] = True  # the flag a minted terminal carries: the ledger's own evidence of the mint
        boundary, row = attached
        terminal_state = self._venue_terminal_state(event)
        if row.get("state") == "filled":
            # A completed row is never demoted by a later or replayed terminal ack: the fills that
            # completed it happened and `_inc_order("filled")` already counted them, and the venue
            # can legitimately cancel the REMAINDER of an order whose ledgered quantity is full.
            terminal_state = None
        update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state=terminal_state, event=payload)
        if terminal_state is not None:
            row["state"] = terminal_state  # the mirror the completion guard and D7 both read
            self._settle_restored_intent(boundary, row)

    def _cache_net(self, symbol: str) -> float:
        """The Cache's instrument-scoped net position under `symbol`, the gauge's own basis."""
        held = self._cache.positions_open(instrument_id=InstrumentId.from_str(INSTRUMENT_IDS[symbol]))
        return sum(float(p.signed_qty) for p in held)

    def _settle_positions_from_venue(self, moment: str) -> None:
        """The venue's own holdings settle the position gauge where the Cache disagrees: at the startup
        pass, after its order read and before its cancels, and at the end of every re-read pass whose reads
        answered -- on the two passes' nonce terms, nothing of this process sent or in flight -- the venue's
        figure is published for every symbol the read answers, and its difference from the Cache's net is
        kept for `_publish_fill`, so a fill between two passes moves the gauge from the venue's figure. What
        the Cache never took, a hand margin open or a fill made while the engine was down, reads here; what
        it never let go, a hand close it refused or a settled lot it holds as a margin position, reads here
        too, the settled lot by the coin's spot balance. A read that fails logs WARNING and the gauge keeps
        its reading until the next pass, the seed's fold at the first; a disagreement logs WARNING per
        symbol, since it names a hand act or a fill this engine never saw. The read serves the gauge alone,
        so with no metrics hook installed, the exporter off, nothing is read. Wrapped as `_publish_fill` is:
        telemetry never alters what this engine does."""
        if _metrics is None:
            return
        try:
            held = (self._venue_holdings or read_venue_holdings)()
        except Exception:
            logger.warning(
                "the venue's holdings could not be read at %s -- the position gauge keeps its reading until the next pass",
                moment,
                exc_info=True,
            )
            return
        try:
            for symbol, venue_qty in sorted(held.items()):
                cache_qty = self._cache_net(symbol)
                self._venue_correction[symbol] = venue_qty - cache_qty
                if abs(venue_qty - cache_qty) > FLAT_TOLERANCE:
                    logger.warning(
                        "the venue holds %s %s where the Cache reads %s -- the position gauge takes the venue's figure at %s",
                        venue_qty,
                        symbol,
                        cache_qty,
                        moment,
                    )
                _metrics.set_position(symbol, venue_qty)
        except Exception:
            logger.exception("executor position settle raised -- continuing")

    def _publish_fill(self, event) -> None:
        """The live view of the fill that just went into the ledger row -- same event, same numbers.

        Called from every path that records A FILL EVENT -- in-flight, detached, and the overfill
        trips -- because each of those fills cost real money: publishing only the in-flight ones
        would under-report the fees actually paid with every test still green. Those paths are
        mutually exclusive by construction, so nothing is counted twice.

        TWO row writes deliberately publish nothing, for one reason in both cases: the metric is the
        live view of a fill, and an increment the ledger row cannot explain would make the counter
        and the forensic record disagree -- with the record, which is the authority, on the losing
        side. The unknown-order trip is the first, where `_trip_on_fill` finds no attachment and so
        has no row to append to either; that fill is not unreported, it latches the kill switch,
        `zcrypto_exec_kill_tripped` goes to 1, and the kill file names the order id an operator then
        reads the venue for. The startup reconciliation's repair (spec 00098 D7) is the second: it
        writes a row from the venue's AGGREGATE quantity, with no per-fill detail and no fee behind
        it, so a fills increment there would leave the fills and fees counters disagreeing in a way
        the row cannot explain. Its knock-on is `self._traded`, admitted here and nowhere else: a
        leg whose only fill happened while this process was down does not enter the realized-PnL
        gauge until it fills live again.

        The position comes from the CACHE, never from this process's own running total, plus the
        correction the last venue settle left (`_settle_positions_from_venue`): the venue's figure
        then, carried through what the Cache took since. Note this read is instrument-scoped, so it
        carries any holding this engine never ordered too -- `_reconcile_terminal` doubts the
        strategy-scoped quantity, not this one.

        Wrapped whole, `_inc_order`'s contract: the Cache reads here are telemetry and a metrics
        failure may never alter what this engine does with a fill. `inc_fill` runs first, so a
        Cache that cannot be read still costs only the position/PnL half.
        """
        if _metrics is None:
            return
        try:
            _metrics.inc_fill(_liquidity(event.liquidity_side).lower(), _fee_eur(event.commission))
            instrument_id = event.instrument_id
            self._traded.add(instrument_id)
            symbol = _SYMBOL_BY_INSTRUMENT_ID[str(instrument_id)]
            _metrics.set_position(symbol, self._cache_net(symbol) + self._venue_correction.get(symbol, 0.0))
            _metrics.set_realized(self._realized_eur())
        except Exception:
            logger.exception("executor fill metrics hook raised -- continuing")

    def _realized_eur(self) -> float:
        """Realized PnL over every instrument this process has traded, EUR only.

        Both halves are needed: an OPEN position accrues realized PnL as it is partly closed, and a
        round trip's final PnL lives only on the CLOSED one. `Position.realized_pnl` is
        `Money | None` -- a `None` contributes zero and is never `float()`-ed -- and a position
        denominated in anything but EUR is logged and skipped rather than added to a EUR total.

        Instrument-scoped on purpose, unlike the post-terminal reconciliation: a hand settle of a
        leg this engine opened realizes an outcome that is genuinely this engine's, and scoping to
        our own strategy would systematically miss exactly that case. Telemetry answers what the
        account did; the reconciliation answers what our own orders did.

        Less the baseline read at construction (spec 00120 D10): with the cache enabled the Cache
        holds a previous run's closed positions and a restored open one's earlier partial closes,
        and their realizations are that run's, not this window's."""
        total = 0.0
        for instrument_id in self._traded:
            total += self._realized_on(instrument_id) - self._realized_baseline.get(instrument_id, 0.0)
        return total

    def _realized_on(self, instrument_id: InstrumentId) -> float:
        """The Cache's realized PnL on one instrument, open and closed positions both, EUR only."""
        cache = self._cache
        total = 0.0
        positions = list(cache.positions_open(instrument_id=instrument_id)) + list(
            cache.positions_closed(instrument_id=instrument_id)
        )
        for position in positions:
            pnl = position.realized_pnl
            if pnl is None:
                continue
            code = getattr(getattr(pnl, "currency", None), "code", None)
            if code not in EUR_CODES:
                logger.warning(
                    "realized pnl on %s is denominated in %s, not EUR -- it is left out of the EUR total",
                    instrument_id,
                    code,
                )
                continue
            total += float(pnl)
        return total

    def _fill_payload(self, event, credited: float | None = None) -> dict:
        """The forensic shape of one fill. Shared by the in-flight path and the detached one so an
        adopted order's fill is recorded in exactly the same terms as an order this process placed.

        It carries the venue order id beside the acceptance's copy: an order can reach FILLED with no
        acceptance in the ledger -- the library admits SUBMITTED to FILLED, and an acceptance whose
        write failed leaves none -- and a filled row with no venue id cannot be checked for a
        withdrawn fill after a restart. `credited` is what the fill moved the row's `filled_qty` by
        where `_fill_credit` capped it below the event's quantity, written as `credited` beside `qty`
        and only then, so every line whose quantity moved the row whole reads as before and the
        ledger's readers count what moved the row (`execledger.credited_qty`)."""
        commission = event.commission
        payload = {
            "event": "fill",
            "at": self._now().isoformat(),
            "qty": float(event.last_qty),
            "px": float(event.last_px),
            # `commission` is optional on the event, and a fee-less fill still gets its row: the
            # quantity and price ARE the fill, and "no fee reported" is a truthful null. Read bare,
            # an absent commission raises inside the handler's blanket except, dropping the row
            # entirely -- while `_on_fill` has ALREADY credited the quantity to the ladder. That is
            # a split brain on the one invariant this path exists to hold, so the row never gives
            # way. `_fee_eur` guards the same field for the EUR counter.
            "fee": None if commission is None else float(commission),
            "fee_currency": None if commission is None else commission.currency.code,
            "liquidity": _liquidity(event.liquidity_side),
            "trade_id": str(event.trade_id),
            "venue_order_id": _venue_order_id_of(event),
        }
        if credited is not None and credited != payload["qty"]:
            payload["credited"] = credited
        return payload

    def _fill_credit(self, event, row: dict, qty: float) -> float:
        """What a fill adds to `row`'s `filled_qty`: the event's own quantity, capped, for a row the
        re-read pass repaired from the venue's report in this process, at what the Cache's order has
        filled beyond the row -- so that fill, should the stream replay it after the pass (F2's shape,
        the execution socket resubscribing behind the data socket's return; whether it replays is
        unmeasured on this wheel, and F2's Record reads it), adds nothing, where the event's quantity
        would count it twice, a false overfill trip on a whole fill and a false withdrawal trip at the
        next startup on a partial. The `fill` line keeps the event's own quantity either way, the
        stream's record, and carries `credited` where the cap moved the row by less (`_fill_payload`),
        the figure the ledger's readers count into `held` beside the repair's `reconciled` line. The cap
        under-credits a fill the Cache is behind on, the safe direction: a fill after the pass on an
        order whose cut fills the stream never delivered is credited only beyond the Cache's lag,
        nothing where the lag exceeds it, and the row keeps the shortfall with the `fill` line carrying
        the fill -- a row whose re-cancel returned, or whose closed report settled it, being terminal,
        outside the open rows a startup repairs and read at a startup for a withdrawal alone, which a
        shortfall never trips, while one whose re-cancel raised stays open, a row a startup inside the
        re-attach window reads against the venue's report. Every other row, and a Cache that
        cannot be read or does not hold the order, credits the event's quantity: the startup's repair
        rebuilds the Cache from the venue first, so nothing replays behind it."""
        if self._restored_row(row):
            # A restored row's fill credits nothing (spec 00120 D8): the library books a trade frame on a
            # restored open order twice, so the event's quantity would trip a false overfill, and the re-read
            # pass repairs the row from the venue's cumulative figure. Nothing here tells a double booking
            # from a single one, so the WARNING an operator searches before a restart is logged once per row
            # until the pass repairs it; the trip check and the row's append both ask this credit.
            if row["client_order_id"] not in self._restored_fills:
                logger.warning(
                    "a fill on restored order %s credits nothing until the venue is read -- the next restart is taken flat",
                    row["client_order_id"],
                )
            self._restored_fills.add(row["client_order_id"])
            self._arm_reread_after_mint()
            return 0.0
        if row["client_order_id"] not in self._rows_the_pass_repaired:
            return qty
        try:
            held = self._cache.order(event.client_order_id)
        except Exception:
            return qty
        if held is None:
            return qty
        beyond = float(held.filled_qty) - row["filled_qty"]
        # The sweep's dead band: the two figures are float sums a rounding apart, and a credit that rounding short of
        # the event's quantity would write a `credited` saying the fill moved the row by less than it did.
        if beyond >= qty - _OVERFILL_TOLERANCE:
            return qty
        return max(0.0, min(qty, beyond))

    def _on_detached_event(self, event) -> None:
        """An event for an order that is not the one in flight: an order this process superseded, one
        it already finished with, or one the startup pass adopted from a previous process.

        It still gets its ledger row -- that is the no-fill-without-a-forensic-row invariant, and the row
        is chosen by the boundary the ORDER was filed under, never the boundary of the tick that saw the
        event. No state claim is made for an order of this process: it is not tracking that order's
        lifecycle, so the row keeps whatever open state it has and stays visible to the next re-attach. A
        RESTORED order's events land here too, under its own id (spec 00120 D12), and for its row this path
        makes the external path's two writes and settles its intent (`_settle_restored_intent`).

        A fill on an order belonging to the RUNNING intent also grows `filled`, so the next
        resubmission is sized against it. Without that the remainder over-asks by exactly the
        dropped quantity. Journal first, count second: a fill this process could not record is not
        one it may account for.

        That credit is inert for a row the startup pass ADOPTED, and deliberately so: `_claims`
        needs the row's `plan_id` to be the running plan's, while `plan_refusals` refuses any
        `plan_id` already in `ledgered_plan_ids` -- scanned over the same two-UTC-day window
        `open_submitted_rows` re-attaches from, so a plan accepted today cannot share a plan_id
        with a row adopted from that window. The boundary is that `_attached` outlives the window:
        a process still running two days past an adopted row's boundary could accept a plan reusing
        its plan_id, and that fill would then be credited to the running intent.
        """
        attached = self._attached_for(event)
        if attached is None:
            return  # an order this process never ledgered -- nothing to append to
        boundary, row = attached
        is_fill = type(event).__name__ == "OrderFilled"
        qty = self._fill_credit(event, row, float(event.last_qty)) if is_fill else 0.0
        payload = self._fill_payload(event, qty) if is_fill else {"type": type(event).__name__, "at": self._now().isoformat()}
        if not is_fill and type(event).__name__ in _RECONCILED_TERMINALS and getattr(event, "reconciliation", False):
            # The third mint site: the engine minted a terminal for an order no intent holds -- the ack
            # deadline stranded the intent first, or a reprice superseded the order -- and it lands here.
            payload["reconciliation"] = True  # the mint's own evidence on the detached path
            self._arm_reread_after_mint()  # the detached site: the order may rest, and no intent of this process will ask
        if type(event).__name__ == "OrderAccepted":
            # A superseded order's acceptance can land after the order it was replaced by: the same
            # record `_on_order_event` writes for the one in flight.
            payload["venue_order_id"] = str(event.venue_order_id)
        update_submitted_row(self._journal_dir, boundary, row["client_order_id"], event=payload, add_filled_qty=qty)
        if qty:
            # The mirror `_mirror_row_fill` makes, on the row already in hand: the event's own id
            # may be no key of `_attached`.
            row["filled_qty"] = row["filled_qty"] + qty
            active = self._active
            if active is not None and self._claims(row, active):
                active.filled += qty
        if self._restored_row(row):
            if is_fill:
                if row.get("state") != "filled" and row["filled_qty"] >= _ordered_qty(row) - _OVERFILL_TOLERANCE:
                    update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state="filled")
                    row["state"] = "filled"
                    _inc_order("filled")
                    self._settle_restored_intent(boundary, row)
            else:
                terminal_state = None if row.get("state") == "filled" else self._venue_terminal_state(event)
                if terminal_state is not None:
                    update_submitted_row(self._journal_dir, boundary, row["client_order_id"], state=terminal_state)
                    row["state"] = terminal_state
                    self._settle_restored_intent(boundary, row)
        if is_fill:
            self._publish_fill(event)

    def _on_fill(self, active: _ActiveIntent, event) -> None:
        qty = float(event.last_qty)
        active.filled += qty
        active.order_filled += qty
        payload = self._fill_payload(event)
        # Both completion tests carry a one-lot-step tolerance, because both compare a SUM of
        # per-fill floats against a single sized float: 0.1 + 0.7 == 0.7999999999999999, an ulp
        # under the 0.8 that was ordered. Exact tests strand a fully-filled intent on a dead order
        # -- the time-box then cancels it and the venue answers a cancel-rejection. A remainder
        # below one lot step could never be ordered anyway, which is the same judgment the
        # BelowMinimum path already makes; the tolerance is the venue's own granularity, not an
        # invented epsilon.
        lot_step = active.constraints.lot_step
        order_done = active.order_qty - active.order_filled < lot_step
        self._update_row(active, state="filled" if order_done else "accepted", event=payload, add_filled_qty=qty)
        self._mirror_row_fill(active.client_order_id, qty)
        self._publish_fill(event)
        if order_done:
            _inc_order("filled")
        if active.target_qty - active.filled < lot_step:
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

    def _mark_ambiguous(self, active: _ActiveIntent, what: str) -> None:
        """Flip the row to the one OPEN state that says the venue outcome is unknown. Wrapped
        because this is a SECOND ledger write and its failure must not cost the refusal journaling
        that follows it."""
        try:
            self._update_row(active, state="ambiguous", event={"type": "ambiguous", "at": self._now().isoformat(), "what": what})
        except Exception:
            logger.critical("could not mark %s ambiguous -- its row stands as it was", active.client_order_id, exc_info=True)

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
        """`outcome=None` means `_submit` already journaled and counted this one -- it knows whether the order
        was refused or left ambiguous, and this does not."""
        active = self._active
        try:
            self._client.unsubscribe_quotes(active.instrument_id)
        except Exception:
            logger.warning("unsubscribe failed for %s -- continuing", active.instrument_id, exc_info=True)
        if outcome is not None:
            self._journal_intent(active.index, outcome, reasons, filled_qty)
            if outcome == "refused":
                _inc_order("refused")
        self._enter(active, "done")
        self._active = None
        self._index += 1
        # Reconciled AFTER the teardown, so a trip cannot re-enter this method through the very
        # intent it is ending -- by here `self._active` is None, and the plan pointer is all
        # `_trip_kill` still needs to refuse the rest.
        self._reconcile_terminal(active)

    def _finish_revoked(self, active: _ActiveIntent) -> None:
        """End a revoked intent and stop the plan -- whatever revoked this one applies to the rest."""
        index = active.index
        self._finish_active("revoked", active.revoke_reasons, active.filled)
        self._halt_plan(index, f"not run -- intent {index} was revoked mid-flight")

    def _halt_plan(self, from_index: int, reason: str) -> None:
        """The ledger, not this process's memory, is what says the intents after `from_index` never ran."""
        if self._plan is None:
            return  # a trip inside the terminal that led here already dropped it -- nothing left to stop
        for index in range(from_index + 1, len(self._plan.intents)):
            self._journal_intent(index, "refused", (reason,))
            _inc_order("refused")
        self._active = None
        self._plan = None
        self._index = 0

    def _drop_remainder_after_ambiguity(self, active: _ActiveIntent) -> None:
        """An ambiguous outcome ends the WHOLE plan, not just its intent (owner ruling).

        The order may be live at the venue, so the account's real position and free balance are
        unknown -- and the notional cap and margin floor that authorized every LATER intent in this
        plan were computed against a venue state that may no longer hold. Submitting the next one
        would be authorizing an order on unknown state, which is exactly what refusal by default
        forbids. Rung-1 plans carry one or two intents and the operator is attended, so the cost of
        stopping is a re-drop after reading the venue.

        Five callers, one meaning -- "this process cannot say what reached the venue": a raising
        submit, an unclassifiable rejection, a cancel the venue rejected, a cancel or IOC it never
        answered, and a terminal this engine minted for itself rather than received. Each has
        already journaled its own intent by the time it gets here, and each leaves the row in one of
        `execledger._OPEN_ORDER_STATES` so re-attach still sees the order.
        """
        try:
            self._client.unsubscribe_quotes(active.instrument_id)
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
