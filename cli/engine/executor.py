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

import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nautilus_trader.model import InstrumentId, OrderSide, OrderStatus, TimeInForce, Venue

from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.execgate import KILL_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
from cli.engine.execledger import (
    append_plan_entry,
    append_submitted_row,
    exec_records_through,
    ledgered_intent_keys,
    ledgered_plan_ids,
    open_submitted_rows,
    update_plan_intent,
    update_submitted_row,
)
from cli.engine.feeders import CycleStages
from cli.engine.instruments import EUR_CODES, INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order
from cli.engine.journal import CycleRecord, from_json
from cli.engine.probeplan import PLAN_FILENAME, ProbeIntent, ProbePlanError, parse_plan, plan_refusals
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
# Kraken spells one asset three ways across its surfaces; the balance read tries them in order.
# Every other base gets the plain code plus its `X`-prefixed classic spelling.
_BTC_BALANCE_ALIASES = ("BTC", "XBT", "XXBT")

# Module-level, None-safe, installed by command.run() -- the `cycle.set_metrics_sink` pattern. Left
# unset (the default), every call below is a no-op, so a one-shot subcommand or a test that never
# installs them runs unaffected.
_publish_verdict = None
_metrics = None


def set_executor_hooks(*, publish_verdict=None, metrics=None) -> None:
    """Install (or clear, with the defaults) the executor's telemetry hooks: `publish_verdict` is
    called `(verdict, evaluated_at=...)` after EVERY gate evaluation, `metrics` is an object with
    `inc_order(outcome)`, `inc_external(disposition)`, `inc_fill(liquidity, fee_eur)`,
    `set_position(symbol, qty)` and `set_realized(value)` (`command._ExecutionMetrics`). Neither can
    affect an order -- both are wrapped."""
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
    """What the venue record says is held of `base`, or 0.0 when no spelling of it is present.
    Raises on a present-but-unreadable value -- the caller turns that into a refusal, because a
    balance this process cannot parse is not a balance it may reason about."""
    aliases = _BTC_BALANCE_ALIASES if base == "BTC" else (base, f"X{base}")
    for alias in aliases:
        if alias in balances:
            return float(balances[alias])
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
        if record.cycle_ts <= until:
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


class ProbeExecutor:
    """Owns every venue-mutating call in this repository.

    `client` is the strategy handle (or a stub with the same surface): `.cache`,
    `.order_factory.limit(...)`, `.submit_order(order, params=...)`, `.cancel_order(client_order_id)`,
    `.subscribe_quotes(id)`, `.unsubscribe_quotes(id)`.
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
        # client_order_id -> (the boundary whose exec record holds its row, the row). EVERY order
        # this process knows about is here: the ones it submitted, and the ones the startup pass
        # adopted from a previous process. It is what makes a fill land in a forensic row even when
        # the order is not the one currently in flight -- without it, a fill for a superseded or
        # adopted order is dropped by the client-order-id filter, which costs the row (D5) and
        # understates the remainder the next resubmission is sized against.
        self._attached: dict[str, tuple[datetime, dict]] = {}
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
        survived the restart is exactly the state the operator pulled the switch for.

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
        from inside the handler. Which is also why the
        cache read below is the WIDE one: an order that filled, was canceled or expired while this
        process was down is reconciled as CLOSED and never appears in `orders_open` at all, so the
        pass can no longer return early when nothing is resting -- an idle startup can still owe row
        repairs. The classification population is unchanged: it is the open orders, taken from that
        same list by the order's own predicate.
        """
        try:
            orders = list(self._client.cache.orders(venue=_VENUE))
        except Exception:
            # Nothing can be adopted OR canceled without the list, and nothing has been touched --
            # so the pass does NOT latch: leaving a previous process's orders unclassified for the
            # life of this one is worse than reading again next tick, and there is no cancel to
            # duplicate.
            logger.critical("venue orders could not be read at startup -- retrying on the next tick", exc_info=True)
            return
        # Derived from the list already read rather than from a second cache call: two reads can
        # disagree, and one of them failing would leave the sweep and the classification reasoning
        # from different populations of the same account.
        resting = [order for order in orders if order.is_open]
        self._adopted = True  # the read succeeded: this pass classified what there was to classify

        try:
            rows = {row["client_order_id"]: (boundary, row) for boundary, row in open_submitted_rows(self._journal_dir, now)}
        except Exception:
            # The claim is scoped to what is actually resting: the rows are now read on every
            # startup, including idle ones where nothing could be canceled at all.
            logger.critical(
                "the exec ledger could not be read at startup -- no row can be reconciled against venue truth%s",
                " and every resting order will be canceled" if resting else "",
                exc_info=True,
            )
            rows = {}
        self._reconcile_adopted_rows(orders, rows)
        if not resting:
            return  # nothing adopted -- and no gate read, so an idle startup stays the cheap path

        # Read AFTER the sweep: a repair that latched the kill switch above makes this `none`, and
        # then the pass cancels everything, ledgered reducers included -- which is exactly what a
        # latched kill file means.
        kill_latched = self._evaluate(now).level == GateLevel.NONE

        for order in resting:
            client_order_id = str(getattr(order, "client_order_id", ""))
            attached = rows.get(client_order_id)
            if attached is not None:
                self._attached[client_order_id] = attached
            payload = attached[1].get("order") if attached is not None else None
            if isinstance(payload, dict) and payload.get("reduce_only") is True and not kill_latched:
                logger.warning("adopted resting order %s is a ledgered reducer -- left resting and re-attached", client_order_id)
                continue
            logger.warning(
                "canceling adopted resting order %s -- %s",
                client_order_id,
                "the kill switch is latched" if kill_latched else "the ledger does not carry it as a resting reducer",
            )
            try:
                self._client.cancel_order(order.client_order_id)
            except Exception:
                logger.critical(
                    "cancel of adopted order %s raised -- it may still rest at the venue", client_order_id, exc_info=True
                )

    def _reconcile_adopted_rows(self, orders: list, rows: dict) -> None:
        """The startup reconciliation sweep (spec 00098 D7): every ledgered row this pass can match
        to a cache order, compared against that order's own quantity, before anything is classified.

        The ROWS are iterated and the orders indexed, never the other way round: the cache holds no
        previous session's state, but the venue's mass-status read is unbounded, so `orders` can be
        the account's entire closed-order history while the rows are the two-day re-attach window.
        A row whose order the cache holds no record of at all is left exactly as it is -- there is
        no venue-truth source for it at this point in startup, and inventing one would be worse than
        an open row a human can read.

        Wrapped twice, and both wrappings earn their place. PER ROW, so one row's failure -- or its
        trip -- costs only that row and the rest still get their repairs. And around the whole
        sweep, because `_adopted` is already set when this runs: an escape would leave a previous
        process's resting opener working at the venue, uncanceled and unattached, for the life of
        this process, and the sweep introduces raising calls the pass never had.

        Neither of those is what protects the kill trips, and the difference is load-bearing: each
        ledger write inside `_reconcile_adopted_row` carries its OWN `try` (`_record_trip_fill`'s
        precedent), because both trip arms are preceded by a write. Catching those here instead
        would let a read-only journal swallow the latch over a live divergence -- one CRITICAL
        logged, no kill file, and the gate reading normal.
        """
        try:
            by_client_order_id = {str(getattr(order, "client_order_id", "")): order for order in orders}
            for client_order_id, (boundary, row) in rows.items():
                order = by_client_order_id.get(client_order_id)
                if order is None:
                    continue
                try:
                    self._reconcile_adopted_row(boundary, client_order_id, row, order)
                except Exception:
                    logger.critical("adopted row %s could not be reconciled against the venue", client_order_id, exc_info=True)
        except Exception:
            logger.critical("the startup reconciliation sweep raised -- classifying resting orders anyway", exc_info=True)

    def _reconcile_adopted_row(self, boundary: datetime, client_order_id: str, row: dict, order) -> None:
        """One ledgered row against the venue truth the reconciled order carries.

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
        `filled` over a row that says `canceled`. No test pins that precedence, deliberately: the
        library's own state machine makes the conflict unreachable, since an order filled to its
        quantity is FILLED and never CANCELED/EXPIRED/REJECTED/DENIED, and the one shape that could
        fake it (an unreadable ledgered qty, which reads 0.0) routes to the overshoot trip before
        the completion arm is consulted. Pinning an input the venue cannot produce would be a guard
        on a door with no caller.

        Every ledger write here is wrapped where it is MADE, never by the caller's per-row wrapper:
        both trip arms have a write in front of them -- the repair on the overshoot arm, the
        terminal state on a closed order's negative one -- so a wrapper spanning the arm would let a
        ledger failure suppress the kill switch on exactly the divergences it exists for. The
        in-process figures are mirrored either way, `_record_trip_fill`'s ruling: they track what
        the venue says filled, not what could be written down.

        The row is written into `self._attached` here rather than left to the classification loop,
        which only ever sees the RESTING orders: that is what puts a closed order's row in the map
        too, so a late duplicate or racing event for it lands matched rather than counted as the
        operator's hand settle. The mirror carries `state` as well as the quantity -- the external
        path's once-only completion guard reads that state, and its overfill trip reads that
        quantity.
        """
        venue_filled = float(order.filled_qty)
        ledgered = row["filled_qty"]
        delta = venue_filled - ledgered
        ordered = _ordered_qty(row)
        repairs = delta > _OVERFILL_TOLERANCE
        if repairs:
            payload = {"event": "reconciled", "at": self._now().isoformat(), "qty": delta, "venue_filled_qty": venue_filled}
            try:
                update_submitted_row(self._journal_dir, boundary, client_order_id, event=payload, add_filled_qty=delta)
            except Exception:
                logger.critical("the repair for adopted order %s could not be journaled", client_order_id, exc_info=True)
            row["filled_qty"] = ledgered + delta
            logger.warning(
                "adopted order %s reconciled against the venue: %.10g filled there against the %.10g recorded here",
                client_order_id,
                venue_filled,
                ledgered,
            )
        total = row["filled_qty"]
        overshoots = repairs and total > ordered + _OVERFILL_TOLERANCE
        completes = repairs and not overshoots and row.get("state") != "filled" and total >= ordered - _OVERFILL_TOLERANCE
        state = _ADOPTED_TERMINAL_STATES.get(order.status) or ("filled" if completes else None)
        if state is not None:
            try:
                update_submitted_row(self._journal_dir, boundary, client_order_id, state=state)
            except Exception:
                logger.critical("the startup state for adopted row %s could not be journaled", client_order_id, exc_info=True)
            row["state"] = state
        self._attached[client_order_id] = (boundary, row)
        if completes and state == "filled":
            _inc_order("filled")
        if delta < -_OVERFILL_TOLERANCE:
            # The dangerous direction: the ledger claims more filled than the venue reports, so this
            # engine believes it reduced more than it did. Clamping it to zero would swallow the
            # signal, and it is the same class of divergence the per-order fill trip already guards.
            self._trip_kill(
                f"adopted order {client_order_id} shows {venue_filled:.10g} filled at the venue, "
                f"less than the {ledgered:.10g} this engine has already recorded"
            )
        elif overshoots:
            # The repair is journaled above, before this: the fill happened at the venue, and
            # no-fill-without-a-record has no divergence exemption.
            self._trip_kill(
                f"adopted order {client_order_id} shows {total:.10g} filled at the venue, "
                f"more than the {ordered:.10g} the ledger says it was submitted for"
            )

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

        try:
            state = venue_state_from_cache(self._client.cache, clock=self._now)
        except Exception:
            logger.warning("venue truth unavailable -- refusing plan %s", plan.plan_id, exc_info=True)
            if self._journal_plan(
                cycle_ts, verdict, now, plan_id=plan.plan_id, plan=plan.raw, disposition="refused", reasons=("no venue truth",)
            ):
                self._delete(path)
            return

        # Live balances spell the free-cash currency `EUR` -- measured against the live engine
        # (`{'EUR': 99.84}`), so this resolves on its SECOND arm in production. The `ZEUR` arm stays
        # first and is not dead: the adapter's other surface genuinely spells the euro `ZEUR` (the
        # instrument quote currency), so the two differ by surface and the fallback covers both.
        # Both absent reads 0.0, which refuses any margin intent.
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
            active.cancel_requested = True
            # A rest-cancel drill must never execute: the time-box cancels it and stops there.
            active.falling_back = active.intent.mode != "rest-cancel"
            active.revoke_reasons = ("time box elapsed",)
            self._enter(active, "cancelling")
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
                float(p.signed_qty)
                for p in self._client.cache.positions_open(instrument_id=instrument_id, strategy_id=self._client.strategy_id)
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
            timebox_at=now + _TIME_BOX,
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
        }
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
        """Both crossing surfaces funnel here: the venue's synchronous post-only rejection and its
        accept-then-cancel. The counter counts RESUBMISSIONS -- the first submission was never a
        reprice -- so `_MAX_REPRICES` of them happen and the next one refuses."""
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
        self._enter(active, next_phase)

    def _enter(self, active: _ActiveIntent, phase: str) -> None:
        """Move to `phase`, arming the venue-answer deadline for the two phases that wait on one and
        clearing it everywhere else -- a stale deadline would strand an intent that is not waiting."""
        active.phase = phase
        active.phase_deadline = self._now() + _ACK_WAIT if phase in ("cancelling", "ioc") else None

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
        """Latch the execution kill switch: create the kill file, pull everything that may still be
        working at the venue, and stop the plan.

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
        # Publish now rather than waiting for a tick that may never evaluate again: with no plan
        # running, `on_timer` takes the idle path and reads no gate at all, so the trip gauge would
        # otherwise sit at its pre-trip value until the next cycle happens to publish one.
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
            resting = list(self._client.cache.orders_open(venue=_VENUE))
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
        events are by construction this engine's submissions; `_on_external_event` carries the
        `events.order.EXTERNAL` topic, which is account-wide, and it is that method's unmatched
        early-return -- no `_attached` row, so counted, logged, and dropped -- that keeps the hand
        settle away from here. Delete that early-return and this trip becomes account-wide.

        Per-order before per-intent, because when both are true the per-order one is the more
        specific fact: it names the one order that did it, where the cross-order sum would send an
        operator to the ladder's remainder arithmetic instead.
        """
        client_order_id = str(getattr(event, "client_order_id", ""))
        attached = self._attached.get(client_order_id)
        if attached is None:
            # Says "no open record", not "never submitted": a terminal row, or one older than the
            # ledger scan window, is not in the attachment map either, and firing is still right
            # there -- a fill on an order this process already accounted for is its own divergence.
            self._trip_kill(f"a fill arrived for order {client_order_id}, for which this engine holds no open order record")
            return True
        boundary, row = attached
        qty = float(event.last_qty)
        ordered = _ordered_qty(row)
        if row["filled_qty"] + qty > ordered + _OVERFILL_TOLERANCE:
            self._record_trip_fill(boundary, client_order_id, row, event, qty)
            self._trip_kill(
                f"order {client_order_id} has now filled {row['filled_qty']:.10g} of the {ordered:.10g} it was submitted for"
            )
            return True
        active = self._active
        if active is not None and self._claims(row, active) and active.filled + qty > active.target_qty + _OVERFILL_TOLERANCE:
            self._record_trip_fill(boundary, client_order_id, row, event, qty)
            self._trip_kill(
                f"intent {active.index} has now filled {active.filled:.10g} across its orders, "
                f"more than the {active.target_qty:.10g} it asked for"
            )
            return True
        return False

    def _record_trip_fill(self, boundary: datetime, client_order_id: str, row: dict, event, qty: float) -> None:
        """The fill that is about to trip the switch still gets its forensic row. It HAPPENED at the
        venue, and the no-fill-without-a-record invariant has no divergence exemption -- the operator
        reading the kill reason needs the fill itself sitting next to it. Wrapped, because a ledger
        failure may never cost the trip; the in-process quantities are credited either way, since
        they track what filled rather than what could be written down.
        """
        try:
            update_submitted_row(self._journal_dir, boundary, client_order_id, event=self._fill_payload(event), add_filled_qty=qty)
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

        DELIBERATELY NOT reached from the four ambiguous exits (a raising submit, an unclassifiable
        rejection, a cancel the venue rejected, a cancel or IOC it never answered): each of those
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
                for p in self._client.cache.positions_open(instrument_id=active.instrument_id, strategy_id=self._client.strategy_id)
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

    def _on_order_event(self, event) -> None:
        # D11's fill-time trips run FIRST, before any row update and before the in-flight/detached
        # split: an unknown order has no row to update, and an overfill must not be credited to a
        # ladder that would then size its next order against it.
        if type(event).__name__ == "OrderFilled" and self._trip_on_fill(event):
            return
        active = self._active
        client_order_id = str(getattr(event, "client_order_id", ""))
        if active is None or active.client_order_id is None or client_order_id != active.client_order_id:
            self._on_detached_event(client_order_id, event)
            return

        name = type(event).__name__
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)

        if name == "OrderAccepted":
            # Deliberately does NOT set `phase = "resting"`. The submission paths already did, and
            # the adapter acknowledges an IOC exactly like a GTC: forcing `resting` here would put
            # a fallback attempt back in the reprice regime, so its unfilled remainder returning as
            # an unrequested cancel would read as the crossing surface and submit a new post-only
            # GTC after the time-box had already expired.
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
            self._finish_revoked(active)
            return

        # Both unrequested cases write the SAME row state, so both count it -- written once above
        # the branch rather than in each arm, because the arms drifting apart is exactly how an
        # unfilled fallback ladder came to advance `submitted` with no terminal outcome behind it.
        self._update_row(active, state="venue_canceled", event=payload)
        _inc_order("venue_canceled")
        if active.phase == "ioc":
            self._fallback(active)
            return
        self._reprice(active)

    def on_external_order_event(self, event) -> None:
        try:
            self._on_external_event(event)
        except Exception:
            # Bookkeeping on an adopted order, never a submission: log and continue (the
            # on_order_event idiom).
            logger.exception("executor external-order-event handling raised -- continuing")

    def _venue_terminal_state(self, event) -> str | None:
        """The row state a non-fill event writes, read off the VENUE's own order.

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

        Three things mean the same thing here -- no terminal state, row untouched: a status outside
        the map (every OPEN one, so a refused cancel leaves the row pointing at a live order), an
        order the Cache does not hold, and a Cache that cannot be read at all. The last is not
        hypothetical: a read inside a handler for an event this process's own command generated
        raises `Already mutably borrowed`, because the Cache is still mutably borrowed for the write
        that produced it. Letting that escape would abandon the whole handler and cost the row its
        event payload -- the forensic record this path exists to keep -- to decide a state those
        events never carried anyway.
        """
        try:
            order = self._client.cache.order(event.client_order_id)
        except Exception:
            logger.warning(
                "the venue order behind %s could not be read -- its row keeps the state it has",
                getattr(event, "client_order_id", "?"),
                exc_info=True,
            )
            return None
        return None if order is None else _ADOPTED_TERMINAL_STATES.get(order.status)

    def _on_external_event(self, event) -> None:
        """Events from `events.order.EXTERNAL` (spec 00098 D1): the delivery path for orders this
        process adopted at startup, filtered by disposition BEFORE anything else runs.

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
        """
        client_order_id = str(getattr(event, "client_order_id", ""))
        attached = self._attached.get(client_order_id)
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
            self._on_detached_event(client_order_id, event)
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
                update_submitted_row(self._journal_dir, boundary, client_order_id, state="filled")
                row["state"] = "filled"
                _inc_order("filled")
            return
        payload = {"type": name, "at": self._now().isoformat()}
        reason = getattr(event, "reason", None)
        if reason is not None:
            payload["reason"] = str(reason)
        boundary, row = attached
        terminal_state = self._venue_terminal_state(event)
        if row.get("state") == "filled":
            # A completed row is never demoted by a later or replayed terminal ack: the fills that
            # completed it happened and `_inc_order("filled")` already counted them, and the venue
            # can legitimately cancel the REMAINDER of an order whose ledgered quantity is full.
            terminal_state = None
        update_submitted_row(self._journal_dir, boundary, client_order_id, state=terminal_state, event=payload)
        if terminal_state is not None:
            row["state"] = terminal_state  # the mirror the completion guard and D7 both read

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

        The position comes from the CACHE, never from this process's own running total. Note this
        read is instrument-scoped, so it carries any holding this engine never ordered too --
        `_reconcile_terminal` doubts the strategy-scoped quantity, not this one.

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
            held = self._client.cache.positions_open(instrument_id=instrument_id)
            _metrics.set_position(_SYMBOL_BY_INSTRUMENT_ID[str(instrument_id)], sum(float(p.signed_qty) for p in held))
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
        account did; the reconciliation answers what our own orders did."""
        cache = self._client.cache
        total = 0.0
        for instrument_id in self._traded:
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

    def _fill_payload(self, event) -> dict:
        """The forensic shape of one fill. Shared by the in-flight path and the detached one so an
        adopted order's fill is recorded in exactly the same terms as an order this process placed."""
        commission = event.commission
        return {
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
        }

    def _on_detached_event(self, client_order_id: str, event) -> None:
        """An event for an order that is not the one in flight: an order this process superseded, one
        it already finished with, or one the startup pass adopted from a previous process.

        It still gets its ledger row -- that is the no-fill-without-a-forensic-row invariant, and the
        row is chosen by the boundary the ORDER was filed under, never the boundary of the tick that
        saw the event. No state claim is made: this process is not tracking that order's lifecycle,
        so the row keeps whatever open state it has and stays visible to the next re-attach.

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
        attached = self._attached.get(client_order_id)
        if attached is None:
            return  # an order this process never ledgered -- nothing to append to
        boundary, row = attached
        is_fill = type(event).__name__ == "OrderFilled"
        payload = self._fill_payload(event) if is_fill else {"type": type(event).__name__, "at": self._now().isoformat()}
        qty = float(event.last_qty) if is_fill else 0.0
        update_submitted_row(self._journal_dir, boundary, client_order_id, event=payload, add_filled_qty=qty)
        if qty:
            self._mirror_row_fill(client_order_id, qty)
            active = self._active
            if active is not None and self._claims(row, active):
                active.filled += qty
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
        """End the in-flight intent: unsubscribe, journal its outcome, and hand the tick to the next
        intent. `outcome=None` means `_submit` already journaled and counted this one -- it knows
        whether the order was refused or left ambiguous, and this does not."""
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
        """Stop the plan after `from_index`: journal every later intent as refused, naming why, and
        drop the running plan. The ledger, not this process's memory, is what says they never ran."""
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

        Four callers, one meaning -- "this process cannot say what reached the venue": a raising
        submit, an unclassifiable rejection, a cancel the venue rejected, and a cancel or IOC it
        never answered. Each has already journaled its own intent by the time it gets here, and each
        leaves the row in one of `execledger._OPEN_ORDER_STATES` so re-attach still sees the order.
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
