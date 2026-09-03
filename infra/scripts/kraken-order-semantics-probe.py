#!/usr/bin/env python3
"""Kraken adapter order-semantics verification -- the six-probe protocol (spec 00039), run against
the exact nautilus-trader build the engine is about to be armed on.

Committed because the obligation recurs: every nautilus bump owes this run before the engine may be
armed on it, and the probes are only comparable across versions if they are the SAME probes.
Rebuilding them from prose each time silently drifts the comparison.

THIS PLACES REAL ORDERS ON A LIVE KRAKEN ACCOUNT WITH REAL MONEY.

The six questions, and the probe that answers each:

  1. Does the exec client surface real account balances?
  2. Are open orders and positions reported without spurious entries?
  3. Do quotes arrive for all pairs, and unsubscribe cleanly?
  4. Does post-only protection hold without a fill?  (4a spot, 4b crossing, 4c/4d margin)
  5. Does submit -> fill -> reconcile -> close -> flat work?
  6. Is the account flat afterwards, with balances reflecting only probe 5?

Shape: `node.run()` owns this thread, and the probe sequence IS the strategy's callbacks. Each step
either finishes in the callback it started in, or arms a wait -- a predicate plus a clock alert --
that the next order event, quote or deadline resolves. There is no polling loop and no second
thread: a node installs its message bus and registries into thread-local storage for the thread
that drives it, and both `LiveNode` and `Strategy` are pyo3-unsendable, so an attribute read from
another thread aborts the process with an uncatchable SIGABRT.

THE CACHE IS THE ONLY TRUTH ABOUT AN ORDER. `submit_order` copies the order into the Cache and
every later event applies to the CACHE's copy; the object the caller kept stays `INITIALIZED`
forever. This harness therefore holds no order object at all -- it keeps client order ids and reads
`cache.order(ClientOrderId(...))` at every point where an order's status, fill or venue id matters.
Reading a held object would classify a resting order as "never submitted" and report a clean bill
while real money sits at the venue.

Safety model (read this before running):
  * Dry-run by default. `--apply` is required before any order reaches the venue. Without it
    probes 1-3 and 6 run for real (all read-only) and probes 4-5 PRINT the exact submission.
  * Probe 5 -- the only probe that spends money -- needs `--probe5` ON TOP of `--apply`.
  * Every order is bounded by an explicit pre-submit notional assertion that REFUSES, never
    clamps. This harness's own assertion is the ONLY notional rail it relies on: the node is
    assembled without a risk-engine config, so nothing inside the library is set up to bound
    an order's size, and a library-side bound would in any case have to be re-measured against
    a MARGIN account before it could be trusted here.
  * Probe 4's resting prices come from a LIVE quote whose age is checked; a missing or stale
    quote is a refusal, never a guessed price.
  * Nothing is left resting: every client order id this harness submits is swept at the end of the
    sequence, swept again from `on_stop` (which is where an interrupted run lands), and read once
    more from the Cache on this thread after the node has stopped. That last read is the one the
    exit code and the cancel-by-hand banner come from.
  * Cancels are always BY CLIENT ORDER ID. `cancel_all_orders` is never called: the live
    production engine trades this same account, and a venue-wide cancel would reach its orders.

Probe 6's venue re-read needs a SECOND invocation. Nothing in the library makes the venue answer
again for the whole account mid-run -- the node hands out no execution engine, so there is no
whole-venue mass status to request. What DOES read the venue is a node START, whose startup
reconciliation asks for open orders and positions; so after the main run, run `--probes 6` on its
own and read THAT row. Probe 6 refuses to report PASS in an invocation that submitted anything,
because there its cache's venue anchor predates the orders.

Credentials: read from `KRAKEN_SPOT_API_KEY` / `KRAKEN_SPOT_API_SECRET` and handed straight to the
exec client's config, which requires them. Their values are never stored on a harness object,
logged, printed, interpolated into a message, or written to the evidence file -- the refusals below
name the VARIABLES and never their contents.

Collision safety: the production engine runs `TraderId("SHADOW-001")` with a default-tagged
strategy, so its client order ids carry the infix `-001-000-`. This harness mints
`O-<YYYYMMDD>-<HHMMSS>-901-P6V-<n>` -- nautilus's own id SHAPE (proven accepted by Kraken on
2026-07-10) with tags the engine structurally cannot emit. Each id is asserted distinct from
the engine's infix before submission.
"""

from __future__ import annotations

import argparse
import faulthandler
import json
import math
import os
import re
import signal
import sys
import tempfile
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import nautilus_trader
from nautilus_trader.adapters.kraken import (
    KRAKEN,
    KRAKEN_VENUE,
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenEnvironment,
    KrakenExecutionClientConfig,
    KrakenExecutionClientFactory,
    KrakenProductType,
)
from nautilus_trader.common import Environment, LogLevel
from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
from nautilus_trader.live import LiveNode, LiveNodeBuilder
from nautilus_trader.model import (
    AccountId,
    AccountType,
    ClientOrderId,
    InstrumentId,
    OrderSide,
    OrderStatus,
    TimeInForce,
    TraderId,
)
from nautilus_trader.trading import Strategy, StrategyConfig

# --------------------------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------------------------

# The pin this harness must bind to lives in `pyproject.toml` and moves on a nightly cadence.
# `pinned_nautilus_version` reads it there rather than restating it here: a hand-maintained copy of
# a daily-moving string is stale by default, and the whole point of the check is which build the
# attended pass measured.
PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
# `===` is PEP 440 arbitrary equality, and the pin must keep using it. The index publishes both
# `<version>` and `<version>+<build>` for the same wheel; `==<version>` matches the local-segment
# form as well and ORDERS IT ABOVE, so `==` silently resolves to a different artifact than the one
# written down -- and this run's whole deliverable is the exact string it bound to.
NAUTILUS_PIN = re.compile(r"^nautilus-trader\s*===\s*(?P<version>\S+)$")

# Spec 00039 probe 3: "the 10-asset EUR universe". The engine's basket has since grown two
# BTC-quoted legs (ETH/BTC, SOL/BTC); they are OFF by default so the probe-3 row stays directly
# comparable with the 2026-07-10 memo, and `--probe3-basket` adds them.
EUR_UNIVERSE = (
    "ADA/EUR",
    "AVAX/EUR",
    "BTC/EUR",
    "DOGE/EUR",
    "DOT/EUR",
    "ETH/EUR",
    "LINK/EUR",
    "LTC/EUR",
    "SOL/EUR",
    "XRP/EUR",
)
BTC_QUOTED_LEGS = ("ETH/BTC", "SOL/BTC")

# The legs Kraken spells two ways -- `AssetPairs` key `XXBTZEUR` against altname `XBTEUR`. The
# adapter's instrument cache is scanned by the KEY while an open order is looked up by the order's
# own altname, and the lookup drops an unresolved row with no warning and a successful return, so
# startup reconciliation cannot see an order resting on one of these -- which is what probe 6 reads.
# Restated here rather than imported: this script must run when the repo's own code is what changed.
# `--pair` defaults to BTC/EUR, so the default run trades one of them.
RECONCILE_BLIND_LEGS = ("BTC/EUR", "ETH/EUR", "XRP/EUR", "LTC/EUR", "ETH/BTC")

# The production engine's identity -- the source of the infix our ids must never carry.
ENGINE_TRADER_ID = "SHADOW-001"
ENGINE_ORDER_ID_INFIX = "-001-000-"

PROBE_TRADER_ID = "P6PROBE-901"
PROBE_TRADER_TAG = "901"
PROBE_ORDER_TAG = "P6V"
PROBE_ORDER_ID_INFIX = f"-{PROBE_TRADER_TAG}-{PROBE_ORDER_TAG}-"
# The node's own name, which nautilus prefixes its log components with (`P6PROBE-901.<name>`).
PROBE_NODE_NAME = "p6probe"
# The account the exec client reports under. The issuer half must be the venue -- the Cache indexes
# accounts by it, and every account read here goes through `portfolio.account(KRAKEN_VENUE)`. The
# numeric half is the probe's own 901, never the engine's 001, so nothing this harness records can
# be mistaken for the engine's view of the same Kraken account.
PROBE_ACCOUNT_ID = "KRAKEN-901"
# The two variables carrying the trade credentials. Named here so the refusals can say WHICH is
# missing without ever touching a value.
# Where a run's PASS is written up, one file per version, named for the exact version string the
# interpreter reports. `cli/engine/order-semantics-verified.json` maps version -> doc and is the
# index; there is deliberately no second list to drift.
VERIFICATION_DOC_DIR = "docs/reference/adapter-verification/"

API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"

# Hard ceilings. `--max-notional` may lower these; nothing raises them past ABSOLUTE_MAX.
DEFAULT_NOTIONAL_EUR = 10.0
DEFAULT_MAX_NOTIONAL_EUR = 15.0
ABSOLUTE_MAX_NOTIONAL_EUR = 50.0
DEFAULT_MAX_RUN_FILLED_EUR = 25.0

# Spec 00039 probe 4: resting orders ">= 25 % below/above market".
MIN_AWAY_FRACTION = 0.25
DEFAULT_AWAY_FRACTION = 0.30

VERDICT_PASS = "PASS"
VERDICT_FAIL = "FAIL"
VERDICT_REVIEW = "REVIEW"
VERDICT_DRY = "DRY-RUN"
VERDICT_SKIP = "SKIPPED"
VERDICT_GATED = "GATED"
VERDICT_REFUSED = "REFUSED"
VERDICT_ERROR = "ERROR"

TERMINAL_STATUSES = frozenset(
    {
        OrderStatus.DENIED,
        OrderStatus.REJECTED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.VOIDED,
        OrderStatus.FILLED,
    },
)
# A status that says the venue has not answered yet. Waiting for "accepted or terminal" has to
# exclude these two explicitly, or the wait resolves on the local echo of our own submission.
PRE_VENUE_STATUSES = frozenset({OrderStatus.INITIALIZED, OrderStatus.SUBMITTED})

_P4A = "Spot post-only limit, resting"
_P4B = "Crossing post-only"


class Refusal(Exception):
    """A pre-submit rail said no. Never clamp, never retry -- report and stop the probe."""


# --------------------------------------------------------------------------------------------
# Pure helpers (exercised by --selftest; no network, no venue, no credentials)
# --------------------------------------------------------------------------------------------


def pinned_nautilus_version(pyproject: Path) -> str:
    """The nautilus-trader version `pyproject.toml` pins, or a Refusal naming what is wrong with it.

    Derived rather than restated so the version this run demands cannot drift from the version the
    tree resolves. A pin spelled with anything but `===` is a refusal, not a spelling to tolerate:
    `==` can install a build whose `__version__` is not the string anyone wrote down, and this run's
    deliverable is exactly that string.
    """
    try:
        parsed = tomllib.loads(pyproject.read_text())
    except OSError as exc:
        raise Refusal(f"cannot read the pin from {pyproject}: {exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise Refusal(f"{pyproject} is not valid TOML: {exc}") from None
    deps = parsed.get("project", {}).get("dependencies", [])
    entries = [str(d).strip() for d in deps if re.match(r"^nautilus-trader\b", str(d).strip())]
    if len(entries) != 1:
        raise Refusal(f"expected exactly one nautilus-trader dependency in {pyproject}, found {entries}")
    matched = NAUTILUS_PIN.match(entries[0])
    if not matched:
        raise Refusal(f"the nautilus-trader dependency must pin with `===`, found {entries[0]!r}")
    return matched.group("version")


def parse_probes(spec: str) -> set[int]:
    """`"1,2,3"` / `"all"` -> the selected probe numbers. Unknown numbers are an error, not a
    silent drop -- a typo'd `--probes 45` must not quietly run nothing."""
    spec = spec.strip().lower()
    if spec in ("all", "*"):
        return {1, 2, 3, 4, 5, 6}
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise Refusal(f"--probes: {part!r} is not a probe number")
        n = int(part)
        if n not in (1, 2, 3, 4, 5, 6):
            raise Refusal(f"--probes: {n} is not one of probes 1-6")
        out.add(n)
    if not out:
        raise Refusal("--probes selected nothing")
    return out


def mint_client_order_id(stamp: str, seq: int) -> str:
    """`O-<YYYYMMDD>-<HHMMSS>-901-P6V-<seq>` -- nautilus's own client-order-id shape, with a
    trader tag and an order tag the production engine cannot emit."""
    return f"O-{stamp}-{PROBE_TRADER_TAG}-{PROBE_ORDER_TAG}-{seq}"


def assert_collision_free(coid: str, already_minted: set[str]) -> None:
    """Both halves matter: it must NOT look like the engine's, and it MUST look like ours --
    a refactor that silently reverted to nautilus's generator would fail the second check."""
    if ENGINE_ORDER_ID_INFIX in coid:
        raise Refusal(f"client order id {coid!r} carries the engine's infix {ENGINE_ORDER_ID_INFIX!r}")
    if PROBE_ORDER_ID_INFIX not in coid:
        raise Refusal(f"client order id {coid!r} does not carry the probe infix {PROBE_ORDER_ID_INFIX!r}")
    if coid in already_minted:
        raise Refusal(f"client order id {coid!r} was already minted in this run")


def resting_price(mid: float, away: float, side: str) -> float:
    """A price `away` fraction from `mid`, on the far side for the given order side."""
    if mid <= 0 or not math.isfinite(mid):
        raise Refusal(f"mid price {mid!r} is not a usable reference")
    if away < MIN_AWAY_FRACTION:
        raise Refusal(f"away fraction {away} is below the protocol's {MIN_AWAY_FRACTION}")
    if side == "BUY":
        return mid * (1.0 - away)
    if side == "SELL":
        return mid * (1.0 + away)
    raise Refusal(f"unknown side {side!r}")


def verify_away(price: float, mid: float, side: str, min_away: float = MIN_AWAY_FRACTION) -> float:
    """Re-measure the distance AFTER tick quantization. Quantizing a 30 % offset cannot realistically
    walk it under 25 %, but the protocol's number is a property of the SUBMITTED price, so it is
    asserted on the submitted price."""
    if mid <= 0:
        raise Refusal(f"mid price {mid!r} is not a usable reference")
    actual = (mid - price) / mid if side == "BUY" else (price - mid) / mid
    if actual < min_away:
        raise Refusal(
            f"quantized price {price} is only {actual:.4%} from mid {mid} -- the protocol requires "
            f">= {min_away:.0%}; refusing (never clamped)",
        )
    return actual


def crossing_price(ask: float, cross_fraction: float) -> float:
    """Probe 4b: a BUY price that genuinely crosses the ask. Priced only just through it, so an
    unexpected fill executes at the ask rather than at our (worse) limit."""
    if ask <= 0 or not math.isfinite(ask):
        raise Refusal(f"ask price {ask!r} is not a usable reference")
    if cross_fraction <= 0:
        raise Refusal("the crossing offset must be positive or the order does not cross")
    return ask * (1.0 + cross_fraction)


def require_eur_quote(instrument, label: str) -> None:
    """Every ceiling in this harness is denominated in EUR. On a non-EUR-quoted pair they would
    silently become quote-currency units -- `--notional 10` against ETH/BTC means TEN BITCOIN."""
    quote = str(instrument.quote_currency)
    if quote not in ("EUR", "ZEUR"):
        raise Refusal(
            f"{label}: {instrument.id} is quoted in {quote}, not EUR -- every notional ceiling in this "
            f"harness is denominated in EUR and would silently mean {quote} here",
        )


def check_notional(notional: float, max_notional: float, label: str) -> None:
    """The one rail that actually holds. REFUSES -- never clamps to the maximum."""
    if not math.isfinite(notional) or notional <= 0:
        raise Refusal(f"{label}: computed notional {notional!r} is not a positive number")
    if notional > max_notional:
        raise Refusal(
            f"{label}: computed notional EUR {notional:.4f} exceeds the ceiling EUR {max_notional:.2f} "
            f"-- refusing to submit (the harness never clamps a size down to fit)",
        )


def floor_to_increment(value: float, increment: float) -> float:
    """Exact base-10 floor, the way the engine's own `_floor_to_step` does it -- plain float
    division drifts by an ULP and a venue minimum is checked on the exact number."""
    if increment <= 0:
        raise Refusal(f"increment must be positive, got {increment}")
    dv = Decimal(str(value))
    di = Decimal(str(increment))
    return float((dv // di) * di)


def quote_age_secs(ts_event_ns: int, now_ns: int) -> float:
    return (now_ns - ts_event_ns) / 1e9


def check_quote(bid: float, ask: float, age: float, max_age: float) -> None:
    if not (math.isfinite(bid) and math.isfinite(ask)) or bid <= 0 or ask <= 0:
        raise Refusal(f"quote is unusable (bid={bid!r} ask={ask!r})")
    if ask < bid:
        raise Refusal(f"crossed quote (bid={bid} > ask={ask}) -- refusing to price against it")
    if age > max_age:
        raise Refusal(
            f"quote is {age:.2f}s old, older than the {max_age:.1f}s freshness bound -- refusing "
            f"to price an order against it (the protocol forbids guessing a price)",
        )
    if age < -2.0:
        raise Refusal(f"quote timestamp is {-age:.2f}s in the future -- clock skew; refusing")


def is_post_only_rejection(detail: str) -> bool:
    """True only when the venue rejected the order BECAUSE it would have crossed as post-only.

    Matching the bare substring "post_only" is WRONG and was a live defect: `event_detail` emits
    the attribute NAME, so an insufficient-funds rejection carries `due_post_only=False` and
    matched it -- making every REJECTED a PASS on the one probe that exists to test protection.
    """
    return "due_post_only=True" in detail or "POST_ONLY_REJECTED" in detail or "postWouldExecute" in detail


@dataclass
class LeftoverSplit:
    """What the Cache says about every client order id this harness handed to `submit_order`."""

    closed: list[str] = field(default_factory=list)
    resting: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def outstanding(self) -> list[str]:
        """Everything that is not provably finished. `unknown` belongs here: an id the Cache has no
        record of was still handed to `submit_order`, so it may have reached the venue."""
        return self.resting + self.unknown


def classify_submitted(submitted: Iterable[str], lookup: Callable[[str], object | None]) -> LeftoverSplit:
    """Split the submitted client order ids by what the CACHE says about each one now.

    `lookup` is `cache.order(ClientOrderId(coid))`, and it is the only admissible source. The order
    object a caller keeps after `submit_order` is a snapshot that never advances past
    `INITIALIZED`; classifying by it reads a resting order as "never submitted, nothing at the
    venue" and returns a clean bill while real money sits at Kraken.

    "Never submitted" is not a status this can infer at all -- it is whether the harness called
    `submit_order`, which is what the input list records. Everything in that list is treated as
    possibly at the venue until the Cache says otherwise.
    """
    split = LeftoverSplit()
    for coid in submitted:
        order = lookup(coid)
        if order is None:
            split.unknown.append(coid)
        elif order.is_closed:
            split.closed.append(coid)
        else:
            split.resting.append(coid)
    return split


def render_table(results: list[ProbeResult]) -> str:
    """The deliverable: a GitHub-flavoured table whose rows paste straight into the memo's
    `## Probe results`. `|` inside a cell is escaped -- an unescaped one silently eats cells."""

    def cell(text: str) -> str:
        return str(text).replace("|", "\\|").replace("\n", " ")

    lines = [
        "| # | Probe | Expected | Observed | Verdict |",
        "| -- | -- | -- | -- | -- |",
    ]
    for r in results:
        lines.append(f"| {cell(r.label)} | {cell(r.name)} | {cell(r.expected)} | {cell(r.observed)} | {cell(r.verdict)} |")
    return "\n".join(lines)


def event_detail(event) -> str:
    bits = []
    for attr in ("reason", "last_qty", "last_px", "commission", "due_post_only"):
        val = getattr(event, attr, None)
        if val is not None:
            bits.append(f"{attr}={val}")
    return " ".join(bits)


# --------------------------------------------------------------------------------------------
# The waiting primitive
# --------------------------------------------------------------------------------------------

# Every deadline this harness arms is a clock alert under this prefix, numbered. The names are
# distinct per wait so a late alert from an already-resolved wait is recognisable and ignored.
ALERT_PREFIX = "probe-wait-"


@dataclass
class _Wait:
    name: str
    predicate: Callable[[], bool]
    then: Callable[[bool], None]
    on_quote: bool


class Sequencer:
    """The harness's only way of waiting: a predicate, a deadline, and a continuation.

    A callback may not block, so nothing here sleeps or loops. `until` evaluates the predicate at
    once -- an already-satisfied wait continues immediately and arms no alert at all -- and
    otherwise arms a deadline and returns. `on_event` re-evaluates when something that could have
    satisfied it happened; `on_alert` resolves the deadline. The continuation is called exactly
    once, with True iff the predicate held.

    `arm_alert(name, seconds)` and `cancel_alert(name)` are injected so the whole primitive is
    exercisable with no clock, no node and no venue.
    """

    def __init__(self, arm_alert: Callable[[str, float], None], cancel_alert: Callable[[str], None]) -> None:
        self._arm = arm_alert
        self._cancel = cancel_alert
        self._pending: _Wait | None = None
        self._seq = 0

    @property
    def pending_name(self) -> str | None:
        return self._pending.name if self._pending else None

    def until(
        self,
        predicate: Callable[[], bool],
        timeout_secs: float,
        then: Callable[[bool], None],
        *,
        on_quote: bool = False,
    ) -> None:
        if self._pending is not None:
            raise Refusal(f"a wait ({self._pending.name}) is already pending -- the sequence would fork")
        self._seq += 1
        name = f"{ALERT_PREFIX}{self._seq}"
        if predicate():
            then(True)
            return
        self._pending = _Wait(name=name, predicate=predicate, then=then, on_quote=on_quote)
        self._arm(name, timeout_secs)

    def after(self, seconds: float, then: Callable[[], None]) -> None:
        """A plain delay: a wait whose predicate can never hold, so only the deadline resolves it."""
        self.until(lambda: False, seconds, lambda _satisfied: then())

    def on_event(self, *, from_quote: bool = False) -> None:
        """Something happened that could have satisfied the pending wait. Quotes only reach a wait
        that asked for them -- probe 3's -- because quotes arrive in the hundreds and every other
        predicate is an order read."""
        wait = self._pending
        if wait is None or (from_quote and not wait.on_quote):
            return
        if not wait.predicate():
            return
        self._pending = None
        self._cancel(wait.name)
        wait.then(True)

    def on_alert(self, name: str) -> bool:
        """Resolve the deadline named `name`. Returns whether it was this sequencer's -- an alert
        from a wait that already resolved must never advance the sequence a second time."""
        wait = self._pending
        if wait is None or name != wait.name:
            return False
        self._pending = None
        wait.then(bool(wait.predicate()))
        return True


# --------------------------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------------------------


@dataclass
class ProbeResult:
    label: str
    name: str
    expected: str
    observed: str
    verdict: str


@dataclass
class PlannedOrder:
    probe: str
    instrument: str
    side: str
    order_type: str
    qty: str
    price: str | None
    post_only: bool
    reduce_only: bool
    time_in_force: str
    leverage: int | None
    client_order_id: str
    notional_eur: float
    reference: str

    def describe(self) -> str:
        return (
            f"{self.instrument} {self.side} {self.order_type} qty={self.qty} "
            f"price={self.price} post_only={self.post_only} reduce_only={self.reduce_only} "
            f"tif={self.time_in_force} leverage={self.leverage} "
            f"client_order_id={self.client_order_id} notional=EUR {self.notional_eur:.4f} "
            f"[{self.reference}]"
        )


@dataclass
class EventRecord:
    seq: int
    ts: str
    kind: str
    client_order_id: str | None
    venue_order_id: str | None
    detail: str


@dataclass
class RunState:
    results: list[ProbeResult] = field(default_factory=list)
    events: list[EventRecord] = field(default_factory=list)
    planned: list[PlannedOrder] = field(default_factory=list)
    minted: set[str] = field(default_factory=set)
    submitted: list[str] = field(default_factory=list)
    filled_notional_eur: float = 0.0
    notes: list[str] = field(default_factory=list)
    aborted_by: str | None = None
    # True once every selected probe step has run. It is the difference between "the sequence
    # finished and probe 5 closed its own position" and "the run ended somewhere in the middle" --
    # which is what decides whether a fill left an OPEN POSITION behind. A signal is only one of
    # the ways a run ends early; an exec client that dies takes the node down with no signal at all.
    sequence_complete: bool = False


# --------------------------------------------------------------------------------------------
# The strategy: the probe sequence
# --------------------------------------------------------------------------------------------


def _probe_strategy_config() -> StrategyConfig:
    """The strategy's whole configuration: the probe's order-id tag, and nothing else.

    `external_order_claims` stays at its `None` default, so this strategy structurally never claims
    an order it did not submit -- the same scoping the production node relies on.

    The tag is set rather than left unset so that even an id this harness did NOT mint carries the
    probe infix: `assert_collision_free` requires that infix, and with the tag in place the
    library's own generator produces one too."""
    return StrategyConfig(order_id_tag=PROBE_ORDER_TAG)


class ProbeStrategy(Strategy):
    """The six probes, as the callbacks of one strategy.

    The sequence is a queue of steps. A step runs in whatever callback reached it and then either
    calls `_advance` (done) or arms a wait through `Sequencer` whose continuation eventually does.
    A step that raises is recorded against its own row and the sequence continues with the next
    one: a refusal on 4a must not silently cost 4b-4d, which are the margin semantics the entry
    criterion turns on.

    When the queue empties the sequence tears down -- cancel every submitted id the Cache does not
    report closed, wait for the cancels to confirm, then stop the node. `on_stop` sweeps again,
    which is where an interrupted run lands: a signal stops the trader, and commands issued from
    `on_stop` still reach the execution engine because the node keeps its clients connected for the
    post-stop window (`--order-timeout`, set on the builder).
    """

    def __new__(cls, *args, **kwargs):
        """`Strategy` is a pyo3 class, so construction hands `__new__` this subclass's own
        arguments and the base rejects every one it does not know -- `state` among them. Swallowing
        them is what makes this class constructible at all, and passing the config here is what
        keeps `strategy_id` and `config` saying the same thing from construction onward."""
        return super().__new__(cls, _probe_strategy_config())

    def __init__(self, args, state: RunState) -> None:
        super().__init__(config=_probe_strategy_config())
        self.args = args
        self.state = state
        self.stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.pair_id = InstrumentId.from_str(f"{args.pair}.KRAKEN")
        self.subscribed: list[InstrumentId] = []
        self.first_quote_ns: dict[str, int] = {}
        self.subscribe_ns: int = 0
        self.teardown_done = False
        # Set the moment anything starts taking the node down. Stopping the node FLUSHES its
        # pending clock alerts -- measured: an interrupted run's settle alert fires during the
        # shutdown and would otherwise run the entire remaining sequence, submitting orders after
        # the operator pressed Ctrl-C.
        self._stopping = False
        self._seq = Sequencer(self._arm_alert, self._cancel_alert)
        self._coid_seq = 0
        self._steps: list[tuple[str, str, Callable[[], None]]] = []
        self._current: tuple[str, str] = ("-", "sequence")

    # -- clock plumbing ------------------------------------------------------------------

    def _arm_alert(self, name: str, seconds: float) -> None:
        self.clock.set_time_alert(name, self.clock.utc_now() + timedelta(seconds=max(0.05, seconds)))

    def _cancel_alert(self, name: str) -> None:
        self.clock.cancel_timer(name)

    # -- lifecycle -----------------------------------------------------------------------

    def on_start(self) -> None:
        # The harness's OWN signal handlers, installed here rather than before the run: the node
        # installs its own while starting, and the last writer wins. Theirs stops the node, which
        # is what lands the sweep in `on_stop`; ours exists so a SECOND interrupt cannot raise
        # KeyboardInterrupt into a library callback and abandon that sweep half-done.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._on_signal)
            except ValueError, OSError:  # pragma: no cover - not the main thread, or no such signal
                pass
        self.subscribe_ns = self.clock.timestamp_ns()
        for iid in self.subscribed:
            try:
                self.subscribe_quotes(iid)
            except Exception as exc:  # noqa: BLE001 - a failed subscribe is probe-3 evidence
                self.log.error(f"subscribe_quotes({iid}) raised: {exc}")
        self._steps = self._build_steps()
        print(f"node ready: trader_id={self.trader_id}, run stamp {self.stamp}")
        print(f"\n== settling {self.args.settle:.0f}s (instrument load, reconciliation, first quotes) ==")
        self._seq.after(self.args.settle, self._advance)

    def _on_signal(self, signum, _frame) -> None:
        name = signal.Signals(signum).name
        self._stopping = True
        if self.state.aborted_by is not None:
            return  # a later interrupt: recorded once, and deliberately not acted on again
        self.state.aborted_by = name
        self.state.notes.append(f"run aborted by {name}")
        # A handler runs between bytecodes of whatever the interpreter was doing, so this print can
        # land inside another one -- which CPython answers with a reentrant-call RuntimeError. The
        # banner is worth having and an exception escaping into an interrupted callback is not, so
        # the write is the only thing that may fail here, and it fails silently.
        try:
            print(f"\n!! {name} received -- the node is stopping and the cancel-everything sweep runs on the way out.")
            print("!! Further interrupts are IGNORED so that sweep always completes; kill -9 from another")
            print("!! terminal only if you are prepared to cancel leftovers by hand at Kraken.")
        except RuntimeError:  # pragma: no cover - a print interrupted mid-write
            pass

    def on_stop(self) -> None:
        """The last point at which a cancel can still reach the venue. Reached on every stop --
        the sequence's own, a signal, or a node failure -- so it is where an interrupted run's
        orders are cancelled. It only ISSUES cancels: the post-stop window drains them, and the
        read that decides the exit code happens on the main thread once the node has stopped."""
        self._stopping = True
        if self.teardown_done:
            return
        try:
            outstanding = self._outstanding()
            if not outstanding:
                return
            print(f"\n!! stopping with {len(outstanding)} submitted order(s) not confirmed closed -- cancelling each now")
            for coid in outstanding:
                self._cancel(coid)
        except Exception as exc:  # noqa: BLE001 - nothing here may derail the node's shutdown
            print(f"!! the stop-time cancel sweep raised: {exc!r} -- CHECK KRAKEN OPEN ORDERS BY HAND")
            self.state.notes.append(f"the stop-time cancel sweep raised: {exc!r}")

    # -- the sequence --------------------------------------------------------------------

    def _build_steps(self) -> list[tuple[str, str, Callable[[], None]]]:
        """(label, name, step) for every selected probe, in protocol order. Probe 4's four
        sub-probes are separate steps so a refusal on one costs only its own row."""
        # Named once each: the row's name and the name the step reports its own failure under are
        # the same string by construction, so they cannot drift apart into two spellings of one
        # probe in the same table.
        long_name = f"Margin long (leverage {self.args.leverage}), resting"
        short_name = f"Margin short (leverage {self.args.leverage}), resting"
        catalogue: dict[int, list[tuple[str, str, Callable[[], None]]]] = {
            1: [("1", "Auth + account read", self._probe1)],
            2: [("2", "Reconciliation at node start", self._probe2)],
            3: [("3", "WS market data", self._probe3)],
            4: [
                ("4a", _P4A, lambda: self._resting("4a", _P4A, "BUY", None)),
                ("4b", _P4B, self._probe4b),
                ("4c", long_name, lambda: self._resting("4c", long_name, "BUY", self.args.leverage)),
                ("4d", short_name, lambda: self._resting("4d", short_name, "SELL", self.args.leverage)),
            ],
            5: [("5", "Real ~EUR 10 fill round-trip", self._probe5)],
            6: [("6", "Post-run reconciliation", self._probe6)],
        }
        steps: list[tuple[str, str, Callable[[], None]]] = []
        for n in sorted(self.args.selected_probes):
            steps.extend(catalogue[n])
        return steps

    def _advance(self) -> None:
        """Run the next step, or tear down. Every step ends here, and a step that raises is
        recorded against its own row rather than stopping the sequence.

        Once the node is going down the sequence stops dead. The remaining probes are abandoned
        deliberately and their rows never appear: a probe that ran during the shutdown would price
        against a quote feed that is closing, and -- with `--apply` -- would submit orders after the
        operator asked for the run to end."""
        if self._stopping:
            if self._steps:
                print(f"\n!! the node is stopping -- abandoning the {len(self._steps)} probe step(s) not yet run")
                self.state.notes.append(f"{len(self._steps)} probe step(s) were abandoned when the run stopped")
                self._steps = []
            return
        if not self._steps:
            self.state.sequence_complete = True
            self._begin_teardown()
            return
        label, name, step = self._steps.pop(0)
        self._current = (label, name)
        print(f"\n== probe {label} ==")
        try:
            step()
        except Refusal as exc:
            self.record(label, name, "-", f"REFUSED: {exc}", VERDICT_REFUSED)
            print("   (a refusal is a rail doing its job -- nothing was submitted for this probe)")
            self._advance()
        except Exception as exc:  # noqa: BLE001 - one probe's failure is a row, not the run
            self.record(label, name, "-", f"ERROR: {exc!r}", VERDICT_ERROR)
            self._advance()

    def _resume(self, fn: Callable[[], None]) -> None:
        """Run a continuation with the same per-row guard `_advance` gives a step. Continuations
        run inside library callbacks, where an escaping exception would abandon the sequence with
        orders live at the venue."""
        label, name = self._current
        try:
            fn()
        except Refusal as exc:
            self.record(label, name, "-", f"REFUSED: {exc}", VERDICT_REFUSED)
            self._advance()
        except Exception as exc:  # noqa: BLE001
            self.record(label, name, "-", f"ERROR: {exc!r}", VERDICT_ERROR)
            self._advance()

    # -- library callbacks ---------------------------------------------------------------

    def on_quote(self, tick) -> None:
        key = str(tick.instrument_id)
        if key not in self.first_quote_ns:
            self.first_quote_ns[key] = self.clock.timestamp_ns()
        self._resume(lambda: self._seq.on_event(from_quote=True))

    def on_order_event(self, event) -> None:
        self.state.events.append(
            EventRecord(
                seq=len(self.state.events) + 1,
                ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                kind=type(event).__name__,
                client_order_id=str(getattr(event, "client_order_id", "") or "") or None,
                venue_order_id=str(getattr(event, "venue_order_id", "") or "") or None,
                detail=event_detail(event),
            ),
        )
        self._resume(self._seq.on_event)

    def on_time_event(self, event) -> None:
        self._resume(lambda: self._seq.on_alert(event.name))

    # -- order state: the Cache, never a held object -------------------------------------

    def order_of(self, coid: str):
        """The Cache's copy of an order, which is the only one that advances. `None` means the
        Cache has no record of that id at all."""
        return self.cache.order(ClientOrderId(coid))

    def status_of(self, coid: str) -> OrderStatus | None:
        order = self.order_of(coid)
        return None if order is None else order.status

    def status_name(self, coid: str) -> str:
        status = self.status_of(coid)
        return "NOT-IN-CACHE" if status is None else status.name

    def filled_of(self, coid: str) -> float:
        order = self.order_of(coid)
        return 0.0 if order is None else float(order.filled_qty)

    def is_closed(self, coid: str) -> bool:
        order = self.order_of(coid)
        return bool(order is not None and order.is_closed)

    def venue_id_of(self, coid: str) -> str:
        order = self.order_of(coid)
        return str(getattr(order, "venue_order_id", None)) if order is not None else "none"

    def _outstanding(self) -> list[str]:
        return classify_submitted(self.state.submitted, self.order_of).outstanding

    def _events_for(self, coid: str) -> list[str]:
        return [e.kind for e in self.state.events if e.client_order_id == coid]

    def _reason_for(self, coid: str) -> str:
        return next((e.detail for e in self.state.events if e.client_order_id == coid and e.detail), "")

    # -- reporting -----------------------------------------------------------------------

    def record(self, label: str, name: str, expected: str, observed: str, verdict: str) -> None:
        self.state.results.append(ProbeResult(label, name, expected, observed, verdict))
        print(f"  [{verdict:8s}] probe {label}: {observed}")

    # -- order plumbing ------------------------------------------------------------------

    def next_client_order_id(self) -> ClientOrderId:
        self._coid_seq += 1
        coid = mint_client_order_id(self.stamp, self._coid_seq)
        assert_collision_free(coid, self.state.minted)
        if self.cache.order(ClientOrderId(coid)) is not None:
            raise Refusal(f"client order id {coid} already exists in the cache -- refusing to reuse")
        self.state.minted.add(coid)
        return ClientOrderId(coid)

    def live_quote(self) -> tuple[float, float, float]:
        """(bid, ask, mid) from the latest cached quote, freshness-checked. Refuses rather than
        guesses -- spec requirement, and a stale mid is how a 25 %-away order becomes a fill."""
        tick = self.cache.quote(self.pair_id)
        if tick is None:
            raise Refusal(
                f"no quote for {self.pair_id} has arrived -- refusing to price probe orders "
                f"(the protocol forbids guessing a price)",
            )
        bid, ask = float(tick.bid_price), float(tick.ask_price)
        age = quote_age_secs(tick.ts_event, self.clock.timestamp_ns())
        check_quote(bid, ask, age, self.args.max_quote_age)
        return bid, ask, (bid + ask) / 2.0

    def plan_limit(
        self,
        *,
        probe: str,
        side: str,
        price_raw: float,
        notional_eur: float,
        post_only: bool,
        leverage: int | None,
        reference: str,
    ) -> tuple[PlannedOrder, object]:
        """Quantize, run every rail, and build the order object. Nothing is submitted here."""
        instrument = self.cache.instrument(self.pair_id)
        if instrument is None:
            raise Refusal(f"instrument {self.pair_id} is not loaded")
        require_eur_quote(instrument, probe)

        price = instrument.make_price(price_raw)
        price_f = float(price)
        if price_f <= 0:
            raise Refusal(f"{probe}: quantized price {price_f} is not positive")

        qty_raw = floor_to_increment(notional_eur / price_f, float(instrument.size_increment))
        qty = instrument.make_qty(qty_raw, round_down=True)
        qty_f = float(qty)
        if qty_f <= 0:
            raise Refusal(f"{probe}: quantized quantity is zero at price {price_f} -- raise --notional")

        min_qty = instrument.min_quantity
        if min_qty is not None and qty_f < float(min_qty):
            needed = float(min_qty) * price_f
            raise Refusal(
                f"{probe}: quantity {qty_f} is below the venue minimum {float(min_qty)} -- "
                f"refusing. Raise --notional to at least EUR {needed:.2f} (and --max-notional with it) "
                f"if that is what you intend.",
            )

        notional = qty_f * price_f
        check_notional(notional, self.args.max_notional, probe)

        coid = self.next_client_order_id()
        order = self.order_factory.limit(
            instrument_id=self.pair_id,
            order_side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            quantity=qty,
            price=price,
            time_in_force=TimeInForce.GTC,
            post_only=post_only,
            reduce_only=False,
            client_order_id=coid,
        )
        assert_collision_free(str(order.client_order_id), set())
        planned = PlannedOrder(
            probe=probe,
            instrument=str(self.pair_id),
            side=side,
            order_type="LIMIT",
            qty=str(qty),
            price=str(price),
            post_only=post_only,
            reduce_only=False,
            time_in_force="GTC",
            leverage=leverage,
            client_order_id=str(order.client_order_id),
            notional_eur=notional,
            reference=reference,
        )
        self.state.planned.append(planned)
        return planned, order

    def plan_market(
        self,
        *,
        probe: str,
        side: str,
        qty_raw: float,
        ref_price: float,
        reference: str,
        count_against_run_total: bool = True,
    ) -> tuple[PlannedOrder, object]:
        instrument = self.cache.instrument(self.pair_id)
        if instrument is None:
            raise Refusal(f"instrument {self.pair_id} is not loaded")
        require_eur_quote(instrument, probe)
        qty = instrument.make_qty(floor_to_increment(qty_raw, float(instrument.size_increment)), round_down=True)
        qty_f = float(qty)
        if not count_against_run_total and qty_f < qty_raw:
            # A closing leg that got floored leaves dust on the books -- flat is the probe's whole
            # claim, so say so loudly rather than letting probe 6 discover it.
            self.state.notes.append(
                f"{probe}: the closing quantity was floored from {qty_raw} to {qty_f} "
                f"(lot step {float(instrument.size_increment)}) -- {qty_raw - qty_f} of dust will remain",
            )
        if qty_f <= 0:
            raise Refusal(f"{probe}: quantized quantity is zero -- raise --notional")
        min_qty = instrument.min_quantity
        if min_qty is not None and qty_f < float(min_qty):
            raise Refusal(
                f"{probe}: quantity {qty_f} is below the venue minimum {float(min_qty)} -- refusing "
                f"(raise --notional to about EUR {float(min_qty) * ref_price:.2f})",
            )
        notional = qty_f * ref_price
        # NEITHER ceiling applies to a POSITION-CLOSING order, and for the same reason: its size is
        # dictated by what actually filled, not by operator input. A ceiling that can refuse the leg
        # that gets us flat is not a safety rail, it is the way a probe leaves an open position
        # behind -- and a buy filling above its planned price is enough to push the closing sell
        # past a per-order ceiling the operator set just above --notional, which this harness's own
        # venue-minimum message advises them to do.
        if count_against_run_total:
            check_notional(notional, self.args.max_notional, probe)
            remaining = self.args.max_run_filled - self.state.filled_notional_eur
            if notional > remaining:
                raise Refusal(
                    f"{probe}: EUR {notional:.4f} would take this run's FILLED total past its "
                    f"EUR {self.args.max_run_filled:.2f} ceiling (EUR {self.state.filled_notional_eur:.4f} already filled)",
                )
        coid = self.next_client_order_id()
        order = self.order_factory.market(
            instrument_id=self.pair_id,
            order_side=OrderSide.BUY if side == "BUY" else OrderSide.SELL,
            quantity=qty,
            time_in_force=TimeInForce.GTC,
            reduce_only=False,
            client_order_id=coid,
        )
        planned = PlannedOrder(
            probe=probe,
            instrument=str(self.pair_id),
            side=side,
            order_type="MARKET",
            qty=str(qty),
            price=None,
            post_only=False,
            reduce_only=False,
            time_in_force="GTC",
            leverage=None,
            client_order_id=str(order.client_order_id),
            notional_eur=notional,
            reference=reference,
        )
        self.state.planned.append(planned)
        return planned, order

    def submit(self, order, leverage: int | None = None) -> str:
        """Hand the order to the library and keep only its id. The object is not retained: after
        this call it is a snapshot that will never change again.

        The single choke point through which every probe order reaches the venue, and therefore
        where the stopping check belongs: commands issued from a stopped strategy still reach the
        execution engine, so nothing else would prevent a continuation resumed during the shutdown
        from opening a new position on the way out."""
        if self._stopping:
            raise Refusal("the node is stopping -- refusing to submit; an aborted run opens nothing further")
        coid = str(order.client_order_id)
        params = {"leverage": int(leverage)} if leverage is not None else None
        self.state.submitted.append(coid)
        self.submit_order(order, params=params)
        return coid

    def _cancel(self, coid: str) -> bool:
        """Cancel BY CLIENT ORDER ID -- never `cancel_all_orders`, which would reach the production
        engine's own resting orders on this same account."""
        try:
            self.cancel_order(ClientOrderId(coid))
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  !! cancel of {coid} raised: {exc!r}")
            return False

    def _await_closed(self, coid: str, then: Callable[[bool], None]) -> None:
        self._seq.until(lambda: self.is_closed(coid), self.args.order_timeout, then)

    # -- probe 1 -------------------------------------------------------------------------

    def _probe1(self) -> None:
        label, name = "1", "Auth + account read"
        expected = "AccountState via the exec client; the account's actual balances"
        if self.args.no_exec:
            self.record(label, name, expected, "skipped: --no-exec", VERDICT_SKIP)
            self._advance()
            return
        self._seq.until(
            lambda: self.portfolio.account(KRAKEN_VENUE) is not None,
            self.args.settle,
            lambda ok: self._probe1_read(ok, expected),
        )

    def _probe1_read(self, ok: bool, expected: str) -> None:
        label, name = "1", "Auth + account read"
        account = self.portfolio.account(KRAKEN_VENUE)
        if not ok or account is None:
            self.record(label, name, expected, "no AccountState arrived", VERDICT_FAIL)
            self._advance()
            return
        balances = {str(c): str(b.total) for c, b in account.balances().items()}
        observed = f"{account.account_type.name}-type account {account.id}; balances {balances}"
        print(f"      account_type={account.account_type.name} id={account.id}")
        print(f"      balances={balances}")
        # Whether these are wallet balances or TradeBalance-derived equity is the adapter's choice
        # and it is not readable from here, so this asks rather than tells: an earlier reading
        # restated as a fact would be validated by agreement and never re-checked.
        print("      note: under spot_account_type=MARGIN these may be TradeBalance-derived equity")
        print("            in margin_balance_asset rather than per-asset wallet balances. RECORD")
        print("            which; the Kraken UI or the raw Balance endpoint is the tie-breaker.")
        self.record(label, name, expected, observed, VERDICT_PASS)
        self._advance()

    # -- probe 2 -------------------------------------------------------------------------

    def _probe2(self) -> None:
        label, name = "2", "Reconciliation at node start"
        expected = "Open orders + positions empty-or-actual, no spurious entries"
        if self.args.no_exec:
            self.record(label, name, expected, "skipped: --no-exec", VERDICT_SKIP)
            self._advance()
            return
        orders = self.cache.orders_open(venue=KRAKEN_VENUE)
        positions = self.cache.positions_open(venue=KRAKEN_VENUE)
        for o in orders:
            print(
                f"      pre-existing open order: {o.client_order_id} {o.instrument_id} {o.side} "
                f"{o.quantity} @ {getattr(o, 'price', None)}"
            )
        for p in positions:
            print(f"      pre-existing open position: {p.instrument_id} {p.side} {p.quantity}")
        observed = f"open orders {len(orders)}, open positions {len(positions)}"
        if orders or positions:
            observed += " -- PRE-EXISTING venue state, listed above; adjudicate before ordering"
            self.state.notes.append("probe 2 found pre-existing venue state; see the printed list")
            self.record(label, name, expected, observed, VERDICT_REVIEW)
        else:
            self.record(label, name, expected, observed + " (both empty)", VERDICT_PASS)
        self._advance()

    # -- probe 3 -------------------------------------------------------------------------

    def _probe3(self) -> None:
        want = {str(i) for i in self.subscribed}
        expected = f"Quotes for all {len(want)} pairs within seconds; clean unsubscribe"
        self._seq.until(
            lambda: want.issubset(self.first_quote_ns.keys()),
            self.args.probe3_timeout,
            lambda _ok: self._probe3_read(want, expected),
            on_quote=True,
        )

    def _probe3_read(self, want: set[str], expected: str) -> None:
        label, name = "3", "WS market data"
        got = {k: (v - self.subscribe_ns) / 1e9 for k, v in self.first_quote_ns.items() if k in want}
        missing = sorted(want - set(got))
        slowest = max(got.values()) if got else float("nan")
        for k in sorted(got):
            print(f"      first quote {k:22s} at {got[k]:5.2f}s")
        clean = True
        for iid in list(self.subscribed):
            if iid == self.pair_id:
                continue  # probes 4/5 price against this one; it stays subscribed
            try:
                self.unsubscribe_quotes(iid)
            except Exception as exc:  # noqa: BLE001
                clean = False
                print(f"      !! unsubscribe {iid} raised: {exc!r}")
        instruments = len(self.cache.instruments(venue=KRAKEN_VENUE))
        if missing:
            observed = f"{len(got)}/{len(want)} pairs ticked within {self.args.probe3_timeout:.0f}s; missing {missing}"
            self.record(label, name, expected, observed, VERDICT_FAIL)
            self._advance()
            return
        observed = (
            f"first tick on all {len(want)} pairs by {slowest:.1f}s after subscribe; "
            f"{instruments} instruments loaded; unsubscribe {'clean' if clean else 'RAISED'}"
        )
        self.record(label, name, expected, observed, VERDICT_PASS if clean else VERDICT_REVIEW)
        self._advance()

    # -- probe 4a / 4c / 4d: accept, rest, cancel ----------------------------------------

    def _resting(self, label: str, name: str, side: str, leverage: int | None) -> None:
        expected = (
            "Accept -> rest -> cancel confirmed"
            if leverage is None
            else f"Accept with leverage {leverage} -> rest -> cancel confirmed"
        )
        bid, ask, mid = self.live_quote()
        raw = resting_price(mid, self.args.away, side)
        planned, order = self.plan_limit(
            probe=label,
            side=side,
            price_raw=raw,
            notional_eur=self.args.notional,
            post_only=True,
            leverage=leverage,
            reference=f"mid={mid:.8g} bid={bid:.8g} ask={ask:.8g} away={self.args.away:.2%}",
        )
        actual_away = verify_away(float(planned.price), mid, side)
        planned.reference += f" actual_away={actual_away:.2%}"
        print(f"      PLAN {planned.describe()}")
        if not self.args.apply:
            self.record(label, name, expected, f"DRY-RUN, would submit: {planned.describe()}", VERDICT_DRY)
            self._advance()
            return
        coid = self.submit(order, leverage=leverage)
        # "Accepted, or terminal" -- not "accepted" alone: a DENIED or REJECTED order resolves the
        # wait at once instead of burning the whole timeout on an answer that has already arrived.
        self._seq.until(
            lambda: self.status_of(coid) not in PRE_VENUE_STATUSES and self.status_of(coid) is not None,
            self.args.order_timeout,
            lambda ok: self._resting_answered(label, name, expected, coid, ok),
        )

    def _resting_answered(self, label: str, name: str, expected: str, coid: str, answered: bool) -> None:
        status = self.status_of(coid)
        if not answered or status != OrderStatus.ACCEPTED:
            observed = f"no rest: status={self.status_name(coid)} events={self._events_for(coid)}"
            if self.is_closed(coid):
                self.record(label, name, expected, observed, VERDICT_FAIL)
                self._advance()
                return
            self._cancel(coid)
            self._await_closed(coid, lambda _ok: self._resting_gave_up(label, name, expected, coid, observed))
            return
        print(f"      accepted at the venue as {self.venue_id_of(coid)}")
        self._cancel(coid)
        self._await_closed(coid, lambda ok: self._resting_cancelled(label, name, expected, coid, ok))

    def _resting_gave_up(self, label: str, name: str, expected: str, coid: str, observed: str) -> None:
        self.record(label, name, expected, f"{observed}; then cancelled -> {self.status_name(coid)}", VERDICT_FAIL)
        self._advance()

    def _resting_cancelled(self, label: str, name: str, expected: str, coid: str, cancelled: bool) -> None:
        filled = self.filled_of(coid)
        if filled:
            self.state.notes.append(f"{label}: UNEXPECTED FILL of {filled} -- a reportable finding (probe 4)")
        observed = (
            f"accepted ({self.venue_id_of(coid)}), rested, cancel {'confirmed' if cancelled else 'NOT confirmed'}; "
            f"status={self.status_name(coid)}; filled_qty={filled}"
        )
        verdict = VERDICT_PASS if (cancelled and filled == 0.0 and self.status_of(coid) == OrderStatus.CANCELED) else VERDICT_FAIL
        self.record(label, name, expected, observed, verdict)
        self._advance()

    # -- probe 4b: the crossing post-only ------------------------------------------------

    def _probe4b(self) -> None:
        label, name = "4b", "Crossing post-only"
        # The requirement is post-only protection with no fill. WHICH terminal event the adapter
        # surfaces that as -- OrderCanceled or a post-only OrderRejected -- is an adapter mapping
        # this run OBSERVES; the verdict logic below accepts either. It is stated as owed rather
        # than carried over from an earlier reading, because a reading taken on one adapter build
        # and matched against another turns agreement into evidence of nothing.
        expected = (
            "Venue post-only protection, no fill; RECORD which terminal event it arrives as "
            "(OrderCanceled or a post-only OrderRejected -- either passes)"
        )
        bid, ask, mid = self.live_quote()
        raw = crossing_price(ask, self.args.cross)
        planned, order = self.plan_limit(
            probe=label,
            side="BUY",
            price_raw=raw,
            notional_eur=self.args.notional,
            post_only=True,
            leverage=None,
            reference=f"bid={bid:.8g} ask={ask:.8g} cross=+{self.args.cross:.4%} (crosses the ask)",
        )
        if float(planned.price) <= ask:
            raise Refusal(f"{label}: quantized price {planned.price} does not cross the ask {ask} -- refusing")
        print(f"      PLAN {planned.describe()}")
        if not self.args.apply:
            self.record(label, name, expected, f"DRY-RUN, would submit: {planned.describe()}", VERDICT_DRY)
            self._advance()
            return
        coid = self.submit(order)
        # A protected post-only ends terminal on its own. If it instead RESTS, it did not cross:
        # a protocol artifact (the quote moved), not an adapter failure -- and it must be cancelled.
        self._seq.until(
            lambda: self.status_of(coid) in TERMINAL_STATUSES,
            self.args.order_timeout,
            lambda ok: self._probe4b_answered(expected, coid, ok),
        )

    def _probe4b_answered(self, expected: str, coid: str, terminal: bool) -> None:
        label, name = "4b", "Crossing post-only"
        filled = self.filled_of(coid)
        if not terminal:
            self._cancel(coid)
            self._await_closed(coid, lambda ok: self._probe4b_rested(expected, coid, ok, filled))
            return
        kinds = self._events_for(coid)
        observed = f"status={self.status_name(coid)} via {kinds}; filled_qty={filled}"
        reason = self._reason_for(coid)
        if reason:
            observed += f"; {reason}"
        if filled:
            observed += " -- UNEXPECTED FILL"
            self.state.notes.append(f"{label}: post-only protection did NOT hold; filled {filled}")
        # What this probe verifies is that KRAKEN protected a crossing post-only. DENIED is a LOCAL
        # refusal the venue never saw, and a REJECTED for insufficient funds says nothing about
        # post-only -- both used to record as a passed verification.
        status = self.status_of(coid)
        if status == OrderStatus.DENIED:
            verdict = VERDICT_ERROR
            observed += " -- DENIED locally; the venue never saw it, so post-only was never exercised"
        elif filled != 0.0:
            verdict = VERDICT_FAIL
        elif status == OrderStatus.CANCELED:
            verdict = VERDICT_PASS
        elif status == OrderStatus.REJECTED and is_post_only_rejection(reason):
            verdict = VERDICT_PASS
        elif status == OrderStatus.REJECTED:
            verdict = VERDICT_FAIL
            observed += " -- REJECTED for a reason other than post-only; protection was not exercised"
        else:
            verdict = VERDICT_FAIL
        self.record(label, name, expected, observed, verdict)
        self._advance()

    def _probe4b_rested(self, expected: str, coid: str, cancelled: bool, filled_when_resting: float) -> None:
        label, name = "4b", "Crossing post-only"
        filled = max(filled_when_resting, self.filled_of(coid))
        if filled:
            # It rested AND filled, so it did cross and post-only did not protect it. That is
            # the defect this probe exists to catch -- never the benign quote-moved artifact.
            self.state.notes.append(f"{label}: post-only protection did NOT hold; filled {filled} while resting")
            self.record(
                label,
                name,
                expected,
                f"order RESTED and FILLED {filled} (status={self.status_name(coid)}) -- post-only did NOT protect it; "
                f"cancel {'confirmed' if cancelled else 'NOT confirmed'}",
                VERDICT_FAIL,
            )
            self._advance()
            return
        observed = (
            f"order RESTED instead of being protected (status={self.status_name(coid)}) -- the quote moved "
            f"between pricing and submission, so it never crossed; cancel "
            f"{'confirmed' if cancelled else 'NOT confirmed'}. Protocol artifact: re-run 4b."
        )
        self.record(label, name, expected, observed, VERDICT_REVIEW)
        self._advance()

    # -- probe 5: the round trip ---------------------------------------------------------

    def _probe5(self) -> None:
        label, name = "5", "Real ~EUR 10 fill round-trip"
        expected = "Submit -> fill -> reconcile -> close -> flat"
        # Plan BEFORE the gates so a dry run SHOWS the order that would spend money. With the gates
        # first, probe 5's plan was unreachable in dry-run and first appeared in the live run,
        # milliseconds ahead of submission.
        bid, ask, mid = self.live_quote()
        planned, buy = self.plan_market(
            probe=f"{label}-buy",
            side="BUY",
            qty_raw=self.args.notional / ask,
            ref_price=ask,
            reference=f"ask={ask:.8g} target notional EUR {self.args.notional:.2f}",
        )
        print(f"      PLAN {planned.describe()}")
        if not self.args.probe5:
            self.record(
                label,
                name,
                expected,
                f"not run: --probe5 was not given (money gate); would have submitted: {planned.describe()}",
                VERDICT_GATED,
            )
            self._advance()
            return
        if not self.args.apply:
            # Backstop, not a reachable state: preflight refuses --probe5 without --apply, so a dry
            # run reaches the GATED branch above. Kept so probe 5 still cannot submit if that
            # preflight rail is ever relaxed.
            self.record(
                label,
                name,
                expected,
                f"DRY-RUN, would submit: {planned.describe()} then sell the filled qty back",
                VERDICT_DRY,
            )
            self._advance()
            return

        print("      >>> THIS SPENDS MONEY <<<")
        coid = self.submit(buy)
        self._seq.until(
            lambda: self.status_of(coid) in TERMINAL_STATUSES,
            self.args.fill_timeout,
            lambda ok: self._probe5_bought(expected, coid, ok),
        )

    def _probe5_bought(self, expected: str, buy_coid: str, terminal: bool) -> None:
        label, name = "5", "Real ~EUR 10 fill round-trip"
        if not terminal or self.status_of(buy_coid) != OrderStatus.FILLED:
            observed = (
                f"buy did not fill within {self.args.fill_timeout:.0f}s: status={self.status_name(buy_coid)}, "
                f"filled_qty={self.filled_of(buy_coid)}"
            )
            if not self.is_closed(buy_coid):
                self._cancel(buy_coid)
            if self.filled_of(buy_coid) > 0:
                self.state.notes.append(
                    f"{label}: PARTIAL BUY of {self.filled_of(buy_coid)} left on the books -- sell it by hand",
                )
                observed += " -- PARTIAL POSITION LEFT; see the manual-cleanup block"
            self.record(label, name, expected, observed, VERDICT_FAIL)
            self._advance()
            return

        buy_order = self.order_of(buy_coid)
        bought_qty = float(buy_order.filled_qty)
        buy_px = float(buy_order.avg_px)
        self.state.filled_notional_eur += bought_qty * buy_px
        print(f"      BUY filled {bought_qty} @ {buy_px} (EUR {bought_qty * buy_px:.5f}); commissions={buy_order.commissions()}")

        positions = self.cache.positions_open(venue=KRAKEN_VENUE)
        account = self.portfolio.account(KRAKEN_VENUE)
        post_buy_balances = {str(c): str(b.total) for c, b in account.balances().items()} if account else {}
        print(f"      post-buy: open positions={len(positions)}, balances={post_buy_balances}")
        print("      note: a SPOT buy under spot_account_type=MARGIN may open no OpenPositions row --")
        print("            RECORD what this build reports there. Wallet truth is the raw Balance endpoint.")

        try:
            planned_sell, sell = self.plan_market(
                probe=f"{label}-sell",
                side="SELL",
                qty_raw=bought_qty,
                ref_price=buy_px,
                reference=f"closing the {bought_qty} bought at {buy_px}",
                count_against_run_total=False,
            )
        except Refusal as exc:
            # The buy already filled, so refusing the close strands a real position. This must never
            # reach the generic REFUSED handler, whose message says nothing was submitted.
            self.state.notes.append(
                f"{label}: flatten {self.args.pair} by hand at Kraken -- {bought_qty} is still held",
            )
            self.record(
                label,
                name,
                expected,
                f"BUY filled {bought_qty} @ {buy_px} but the closing SELL could not be planned ({exc}) -- POSITION LEFT OPEN",
                VERDICT_FAIL,
            )
            self._advance()
            return
        print(f"      PLAN {planned_sell.describe()}")
        sell_coid = self.submit(sell)
        self._seq.until(
            lambda: self.status_of(sell_coid) in TERMINAL_STATUSES,
            self.args.fill_timeout,
            lambda ok: self._probe5_sold(expected, buy_coid, sell_coid, bought_qty, buy_px, ok),
        )

    def _probe5_sold(
        self,
        expected: str,
        buy_coid: str,
        sell_coid: str,
        bought_qty: float,
        buy_px: float,
        terminal: bool,
    ) -> None:
        label, name = "5", "Real ~EUR 10 fill round-trip"
        if not terminal or self.status_of(sell_coid) != OrderStatus.FILLED:
            observed = (
                f"BUY filled {bought_qty} @ {buy_px} but the closing SELL did not fill "
                f"(status={self.status_name(sell_coid)}, filled={self.filled_of(sell_coid)}) -- POSITION LEFT OPEN"
            )
            self.state.notes.append(f"{label}: closing sell incomplete -- flatten {self.args.pair} by hand at Kraken")
            self.record(label, name, expected, observed, VERDICT_FAIL)
            self._advance()
            return
        buy_order = self.order_of(buy_coid)
        sell_order = self.order_of(sell_coid)
        sell_px = float(sell_order.avg_px)
        self.state.filled_notional_eur += float(sell_order.filled_qty) * sell_px
        gross = (sell_px - buy_px) * bought_qty
        observed = (
            f"market buy {bought_qty} @ {buy_px} filled ({buy_order.venue_order_id}); "
            f"market sell @ {sell_px} filled ({sell_order.venue_order_id}); flat; "
            f"gross spread P&L EUR {gross:+.5f}; commissions buy={buy_order.commissions()} sell={sell_order.commissions()}"
        )
        self.record(label, name, expected, observed, VERDICT_PASS)
        self._advance()

    # -- probe 6 -------------------------------------------------------------------------

    def _probe6(self) -> None:
        label, name = "6", "Post-run reconciliation"
        expected = "No open orders/positions; balances reflect only probe 5"
        if self.args.no_exec:
            self.record(label, name, expected, "skipped: --no-exec", VERDICT_SKIP)
            self._advance()
            return
        venue_anchored = self._venue_anchored()
        # A FLOOR, never a total. This cache is populated by startup reconciliation, whose order read
        # cannot see a row on `RECONCILE_BLIND_LEGS` -- and `--pair` defaults to one of them, so the
        # order this probe is most likely to have left resting is exactly the one it cannot count.
        # A zero therefore cannot be signed off on its own; the banner below says so on the row that
        # counts, and section 8 of infra/runbooks/order-semantics-verification.md owns the by-hand
        # read that closes it.
        orders = self.cache.orders_open(venue=KRAKEN_VENUE)
        positions = self.cache.positions_open(venue=KRAKEN_VENUE)
        # Match the probe INFIX, not this process's minted set. A fresh `--probes 6` invocation --
        # the documented recovery read -- has an empty minted set, so a crashed run's own leftovers
        # would classify as somebody else's and downgrade a FAIL to a REVIEW. The infix also
        # survives Kraken's 18-char client-order-id truncation.
        ours = [o for o in orders if PROBE_ORDER_ID_INFIX in str(o.client_order_id)]
        foreign = [o for o in orders if PROBE_ORDER_ID_INFIX not in str(o.client_order_id)]
        account = self.portfolio.account(KRAKEN_VENUE)
        balances = {str(c): str(b.total) for c, b in account.balances().items()} if account else {}
        for o in orders:
            print(f"      open order: {o.client_order_id} {o.instrument_id} {o.side} {o.quantity} status={o.status.name}")
        for p in positions:
            print(f"      open position: {p.instrument_id} {p.side} {p.quantity}")
        if venue_anchored:
            print(f"      !! this read CANNOT see an order resting on {', '.join(RECONCILE_BLIND_LEGS)},")
            print("      !! so a zero above is a floor. Read Kraken -> Trade -> Open Orders by eye")
            print("      !! before signing this probe off.")
        anchor = (
            "startup reconciliation, nothing submitted since"
            if venue_anchored
            else "NOT re-read -- this run submitted after its only venue read"
        )
        observed = (
            f"venue re-read ({anchor}): open orders {len(orders)} (ours {len(ours)}, other {len(foreign)}), "
            f"open positions {len(positions)}; balances {balances}"
        )
        verdict = VERDICT_PASS
        if not venue_anchored:
            # The venue was last asked before this run placed anything, so "nothing is open" is
            # this process's cache talking. Never a PASS -- that is "we failed to ask" wearing a
            # clean answer.
            verdict = VERDICT_REVIEW
            self.state.notes.append(
                "probe 6: this row reads the cache, whose venue read predates this run's orders -- "
                "run `--probes 6` as a SEPARATE invocation and read THAT row for the verdict",
            )
        if ours:
            verdict = VERDICT_FAIL
            self.state.notes.append(f"probe 6: {len(ours)} of OUR orders are still open -- cancel them by hand")
        elif foreign or positions:
            verdict = VERDICT_REVIEW
            self.state.notes.append("probe 6: venue state that is not ours is open -- adjudicate before signing off")
        self.record(label, name, expected, observed, verdict)
        self._advance()

    def _venue_anchored(self) -> bool:
        """Whether probe 6's cache read still stands for VENUE truth.

        The node's start is the only thing that asks the venue what is open for the whole account:
        startup reconciliation requests open orders and positions and populates the cache from the
        answer. The library exposes no way to ask that again -- the node hands out no execution
        engine -- so an invocation that submitted orders AFTER its start is reading a cache whose
        venue answer predates them. Such a run cannot report a clean venue; a separate `--probes 6`
        invocation, which submits nothing, can.

        True only of the ANCHOR, not of completeness: even a correctly anchored read is missing any
        row on `RECONCILE_BLIND_LEGS`. This method answers "is this cache still speaking for the
        venue?", never "is this cache the whole venue" -- probe 6's banner carries the second.

        `state.submitted` is the test: it holds exactly the ids handed to `submit_order`, which is
        the conservative set -- an order whose submission raised is still counted as possibly
        having reached the venue."""
        if self.state.submitted:
            print("      !! this invocation submitted orders after its only venue read, so what follows is")
            print("      !! the CACHE. Run `--probes 6` as a SEPARATE invocation for a true venue read.")
            return False
        return True

    # -- teardown ------------------------------------------------------------------------

    def _begin_teardown(self) -> None:
        """Cancel everything this harness submitted that the Cache does not report closed, then
        wait for the cancels to confirm while the clients are still connected.

        Nothing here may raise past this frame: an exception escaping the teardown would leave the
        node running with orders live and no sequence left to stop it, so every failure ends at
        `_finish_teardown`, which stops the node."""
        try:
            outstanding = self._outstanding()
            if not outstanding:
                self._finish_teardown(True)
                return
            print("\n-- teardown: cancelling orders this harness placed --")
            for coid in outstanding:
                print(f"   cancelling {coid} (status={self.status_name(coid)})")
                self._cancel(coid)
            self._seq.until(lambda: not self._outstanding(), self.args.order_timeout, self._finish_teardown)
        except Exception as exc:  # noqa: BLE001
            print(f"!! teardown itself raised: {exc!r}")
            self.state.notes.append(f"teardown raised: {exc!r} -- check the venue by hand")
            self._finish_teardown(False)

    def _finish_teardown(self, clean: bool) -> None:
        try:
            if not clean:
                for coid in self._outstanding():
                    print(f"   !! STILL OPEN after cancel: {coid} status={self.status_name(coid)}")
        except Exception as exc:  # noqa: BLE001
            print(f"!! reading the leftovers raised: {exc!r}")
        self.teardown_done = clean
        self.shutdown_system("probe sequence complete")


# --------------------------------------------------------------------------------------------
# Node assembly
# --------------------------------------------------------------------------------------------


def exec_client_config() -> KrakenExecutionClientConfig:
    """The exec client, in the production engine's own shape: MARGIN spot account reporting in
    ZEUR, under this harness's own account id. Both currency fields read ZEUR because that is
    the `quote_currency.code` every EUR pair carries -- "EUR" would match nothing.

    The credentials are read here and handed straight to the config; they are never stored on a
    harness object, and the refusal below names the VARIABLES, never their contents."""
    api_key = os.environ.get(API_KEY_VAR, "")
    api_secret = os.environ.get(API_SECRET_VAR, "")
    missing = [name for name, value in ((API_KEY_VAR, api_key), (API_SECRET_VAR, api_secret)) if not value]
    if missing:
        raise Refusal(f"{' and '.join(missing)} not set in the environment; refusing to build an exec client")
    return KrakenExecutionClientConfig(
        account_id=AccountId(PROBE_ACCOUNT_ID),
        # Stated rather than inherited, as the engine states them: these two select WHICH Kraken
        # venue is reached, and a run that verified a different one verifies nothing.
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        api_key=api_key,
        api_secret=api_secret,
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        spot_positions_quote_currency="ZEUR",
        # Explicit, not inherited: the library default is True, which would move order submission
        # from REST to WebSocket. The engine submits over REST, and a probe run that verified a
        # different transport from the one production uses verifies nothing.
        use_ws_trade=False,
    )


def build_node(args, strategy: ProbeStrategy) -> LiveNode:
    """The assembled node: trader identity, logging, the two exec-engine knobs, the Kraken data
    client, and -- unless `--no-exec` -- the Kraken exec client, with the probe strategy attached.

    The adapter loads the venue's instrument universe itself on connect, so nothing here selects
    it. `filter_unclaimed_external_orders=False` keeps venue-tagged unclaimed orders in the cache,
    which is what lets probe 6 see state this harness did not place.

    `delay_post_stop_secs` is the window in which a cancel issued from `on_stop` can still reach
    the venue, so it is sized to the same timeout the sequence gives a cancel to confirm."""
    builder: LiveNodeBuilder = (
        LiveNode.builder(name=PROBE_NODE_NAME, trader_id=TraderId(PROBE_TRADER_ID), environment=Environment.LIVE)
        .with_logging(LoggerConfig(stdout_level=LogLevel(args.log_level)))
        .with_exec_engine_config(LiveExecutionEngineConfig(reconciliation=True, filter_unclaimed_external_orders=False))
        .with_timeout_connection(int(args.connect_timeout))
        .with_delay_post_stop_secs(int(max(10.0, args.order_timeout)))
        .add_data_client(
            name=KRAKEN,
            factory=KrakenDataClientFactory(),
            config=KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE),
        )
    )
    if not args.no_exec:
        builder = builder.add_exec_client(name=KRAKEN, factory=KrakenExecutionClientFactory(), config=exec_client_config())
    node = builder.build()
    symbols = list(EUR_UNIVERSE) + (list(BTC_QUOTED_LEGS) if args.probe3_basket else [])
    strategy.subscribed = [InstrumentId.from_str(f"{s}.KRAKEN") for s in symbols]
    if strategy.pair_id not in strategy.subscribed:
        strategy.subscribed.append(strategy.pair_id)
    node.add_strategy(strategy)
    return node


# --------------------------------------------------------------------------------------------
# Selftest (no network, no venue, no credentials)
# --------------------------------------------------------------------------------------------


def selftest() -> int:
    failures: list[str] = []
    ran: list[str] = []

    def check(name: str, fn) -> None:
        """Every outcome is a line and a verdict. `Exception` and not `AssertionError`, because a
        check that raises something else is still a failed check -- and a traceback out of the
        selftest is the one report the operator cannot act on."""
        ran.append(name)
        try:
            fn()
            print(f"  ok   {name}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: {exc}")
            print(f"  FAIL {name}: {exc}")

    def refuses(fn) -> str:
        try:
            fn()
        except Refusal as exc:
            return str(exc)
        raise AssertionError("expected a Refusal, none raised")

    # --- true positives: the healthy, production-shaped inputs MUST pass -------------------
    check("parse_probes selects", lambda: _eq(parse_probes("1,2,3"), {1, 2, 3}))
    check("parse_probes all", lambda: _eq(parse_probes("all"), {1, 2, 3, 4, 5, 6}))
    check("mint shape", lambda: _eq(mint_client_order_id("20260823-120000", 3), "O-20260823-120000-901-P6V-3"))
    check(
        "mint is collision-free",
        lambda: assert_collision_free(mint_client_order_id("20260823-120000", 1), set()),
    )
    check("resting buy 30% below", lambda: _close(resting_price(100.0, 0.30, "BUY"), 70.0))
    check("resting sell 30% above", lambda: _close(resting_price(100.0, 0.30, "SELL"), 130.0))
    check("verify_away passes at 30%", lambda: _close(verify_away(70.0, 100.0, "BUY"), 0.30))
    check("crossing price is above ask", lambda: _true(crossing_price(100.0, 0.0005) > 100.0))
    check("healthy notional passes", lambda: check_notional(10.0, 15.0, "t"))
    check("fresh quote passes", lambda: check_quote(100.0, 100.2, 0.4, 10.0))
    check("floor_to_increment is exact", lambda: _eq(floor_to_increment(0.1234567, 0.0001), 0.1234))
    check(
        "table renders and escapes pipes",
        lambda: _true("\\|" in render_table([ProbeResult("1", "n", "e", "a|b", "PASS")])),
    )
    check("the pin is readable from this tree", lambda: _true(bool(pinned_nautilus_version(PYPROJECT))))
    check(
        "an arbitrary-equality pin is read exactly",
        lambda: _eq(_pin_from(_pyproject_text('"nautilus-trader===2.0.0rc4.dev20260825"')), "2.0.0rc4.dev20260825"),
    )

    # --- the rails must BITE on the defect each one names ---------------------------------
    check(
        "engine-prefixed id is refused",
        lambda: _true("engine's infix" in refuses(lambda: assert_collision_free("O-20260823-120000-001-000-1", set()))),
    )
    check(
        "foreign-shaped id is refused",
        lambda: _true("probe infix" in refuses(lambda: assert_collision_free("O-20260823-120000-777-ZZZ-1", set()))),
    )
    check(
        "re-minted id is refused",
        lambda: _true(
            "already minted"
            in refuses(lambda: assert_collision_free("O-20260823-120000-901-P6V-1", {"O-20260823-120000-901-P6V-1"}))
        ),
    )
    check(
        "over-size notional is refused",
        lambda: _true("exceeds the ceiling" in refuses(lambda: check_notional(15.01, 15.0, "t"))),
    )
    check("zero notional is refused", lambda: _true("positive number" in refuses(lambda: check_notional(0.0, 15.0, "t"))))
    check("under-25% away is refused", lambda: _true("below the protocol" in refuses(lambda: resting_price(100.0, 0.24, "BUY"))))
    check(
        "quantized-too-close price is refused",
        lambda: _true("refusing (never clamped)" in refuses(lambda: verify_away(80.0, 100.0, "BUY"))),
    )
    check("stale quote is refused", lambda: _true("freshness bound" in refuses(lambda: check_quote(100.0, 100.2, 30.0, 10.0))))
    check("crossed quote is refused", lambda: _true("crossed quote" in refuses(lambda: check_quote(101.0, 100.0, 0.1, 10.0))))
    check("future-dated quote is refused", lambda: _true("clock skew" in refuses(lambda: check_quote(100.0, 100.2, -5.0, 10.0))))
    check("non-crossing offset is refused", lambda: _true("does not cross" in refuses(lambda: crossing_price(100.0, 0.0))))
    check("bad probe number is refused", lambda: _true("probes 1-6" in refuses(lambda: parse_probes("7"))))
    check(
        "insufficient-funds rejection is NOT read as post-only",
        lambda: _true(not is_post_only_rejection("reason=EGeneral:Insufficient funds due_post_only=False")),
    )
    check(
        "a real post-only rejection IS recognised",
        lambda: _true(is_post_only_rejection("reason=EOrder:Post only order due_post_only=True")),
    )
    check(
        "non-EUR quote is refused",
        lambda: _true("not EUR" in refuses(lambda: require_eur_quote(_Instrument("BTC", "ETH/BTC"), "t"))),
    )
    check("non-numeric probe is refused", lambda: _true("not a probe number" in refuses(lambda: parse_probes("4a"))))
    check(
        "a `==` pin is refused",
        lambda: _true("must pin with" in refuses(lambda: _pin_from(_pyproject_text('"nautilus-trader==2.0.0rc4"')))),
    )
    check(
        "a missing pin is refused",
        lambda: _true("exactly one" in refuses(lambda: _pin_from(_pyproject_text('"typer>=0.9"')))),
    )
    check(
        "two nautilus pins are refused",
        lambda: _true(
            "exactly one" in refuses(lambda: _pin_from(_pyproject_text('"nautilus-trader===1.0", "nautilus-trader-extra===2.0"')))
        ),
    )
    check(
        "an unreadable pyproject is refused",
        lambda: _true("cannot read the pin" in refuses(lambda: pinned_nautilus_version(Path("/nonexistent/pyproject.toml")))),
    )

    # --- the leftover split: the Cache is the only truth about an order --------------------
    closed = _CachedOrder(status="CANCELED", is_closed=True)
    resting = _CachedOrder(status="ACCEPTED", is_closed=False)
    # What a HELD order object reads after submission, forever: the event applies to the Cache's
    # copy, never to this one.
    held_snapshot = _CachedOrder(status="INITIALIZED", is_closed=False)
    check(
        "a fully cancelled run leaves nothing outstanding",
        lambda: _eq(classify_submitted(["a", "b"], {"a": closed, "b": closed}.get).outstanding, []),
    )
    check(
        "a resting order is outstanding",
        lambda: _eq(classify_submitted(["a", "b"], {"a": closed, "b": resting}.get).outstanding, ["b"]),
    )
    check(
        "an id the cache has no record of is outstanding, not clean",
        lambda: _eq(classify_submitted(["a"], {}.get).unknown, ["a"]),
    )
    check(
        "the snapshot a caller keeps is never read as 'never submitted'",
        lambda: _eq(classify_submitted(["a"], {"a": held_snapshot}.get).outstanding, ["a"]),
    )
    check(
        "closed orders are not cancelled again",
        lambda: _eq(classify_submitted(["a", "b"], {"a": closed, "b": resting}.get).closed, ["a"]),
    )

    # --- the waiting primitive ------------------------------------------------------------
    check("an already-satisfied wait never arms an alert", _seq_immediate)
    check("an event that satisfies the wait cancels its alert", _seq_event)
    check("a quote only reaches a wait that asked for quotes", _seq_quote_scoped)
    check("a deadline resolves with the predicate's final answer", _seq_deadline)
    check("an alert from a resolved wait is ignored", _seq_stale_alert)
    check("a second wait while one is pending is refused", lambda: _true("already pending" in _seq_double_wait()))

    # --- the constants themselves ---------------------------------------------------------
    check("engine infix is what the engine emits", lambda: _eq(ENGINE_TRADER_ID.split("-")[1], "001"))
    check("default notional is under the default ceiling", lambda: _true(DEFAULT_NOTIONAL_EUR < DEFAULT_MAX_NOTIONAL_EUR))
    check("default away clears the protocol floor", lambda: _true(DEFAULT_AWAY_FRACTION >= MIN_AWAY_FRACTION))
    check("EUR quote is accepted", lambda: _true(require_eur_quote(_Instrument("EUR", "BTC/EUR"), "t") is None))
    check("ZEUR quote is accepted", lambda: _true(require_eur_quote(_Instrument("ZEUR", "XBT/ZEUR"), "t") is None))
    check(
        "a status the venue has not answered yet is never terminal",
        lambda: _true(not (PRE_VENUE_STATUSES & TERMINAL_STATUSES)),
    )

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"SELFTEST PASSED ({len(ran)} checks)")
    return 0


def _eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


def _close(a, b, tol=1e-9):
    assert abs(a - b) <= tol, f"{a!r} !~ {b!r}"


def _true(v):
    assert v, "expected truthy"


class _Instrument:
    """Minimal stand-in for the selftest's EUR-quote checks: the guard reads these two only."""

    def __init__(self, quote_currency: str, ident: str) -> None:
        self.quote_currency = quote_currency
        self.id = ident


@dataclass
class _CachedOrder:
    """What `classify_submitted` reads off an order: its status name and whether it is closed."""

    status: str
    is_closed: bool


def _pyproject_text(deps: str) -> str:
    return f'[project]\nname = "x"\ndependencies = [{deps}]\n'


def _pin_from(text: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
        fh.write(text)
        path = Path(fh.name)
    try:
        return pinned_nautilus_version(path)
    finally:
        path.unlink()


class _FakeAlerts:
    """Records what a Sequencer armed and cancelled, so the selftest can assert on both."""

    def __init__(self) -> None:
        self.armed: list[tuple[str, float]] = []
        self.cancelled: list[str] = []

    def arm(self, name: str, secs: float) -> None:
        self.armed.append((name, secs))

    def cancel(self, name: str) -> None:
        self.cancelled.append(name)


def _seq_immediate() -> None:
    alerts = _FakeAlerts()
    seen: list[bool] = []
    Sequencer(alerts.arm, alerts.cancel).until(lambda: True, 30.0, seen.append)
    _eq(seen, [True])
    _eq(alerts.armed, [])  # a satisfied wait that still armed a deadline would stall the sequence


def _seq_event() -> None:
    alerts = _FakeAlerts()
    ready = {"yes": False}
    seen: list[bool] = []
    seq = Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: ready["yes"], 30.0, seen.append)
    _eq(len(alerts.armed), 1)
    seq.on_event()
    _eq(seen, [])  # nothing happened yet: the continuation must not fire early
    ready["yes"] = True
    seq.on_event()
    _eq(seen, [True])
    _eq(alerts.cancelled, [alerts.armed[0][0]])
    seq.on_event()
    _eq(seen, [True])  # exactly once


def _seq_quote_scoped() -> None:
    ready = {"yes": True}
    # An order wait: satisfied, but a quote must not be what notices it -- every quote would
    # otherwise re-read every order predicate, hundreds of times a second.
    alerts = _FakeAlerts()
    order_wait: list[bool] = []
    order_seq = Sequencer(alerts.arm, alerts.cancel)
    order_seq.until(lambda: ready["yes"], 30.0, order_wait.append)
    order_wait.clear()  # it was satisfied at arm time; re-arm one that is not yet
    ready["yes"] = False
    order_seq = Sequencer(alerts.arm, alerts.cancel)
    order_seq.until(lambda: ready["yes"], 30.0, order_wait.append)
    ready["yes"] = True
    order_seq.on_event(from_quote=True)
    _eq(order_wait, [])
    order_seq.on_event()
    _eq(order_wait, [True])
    # A quote wait: a quote IS what resolves it.
    quote_wait: list[bool] = []
    arrived = {"yes": False}
    quote_seq = Sequencer(alerts.arm, alerts.cancel)
    quote_seq.until(lambda: arrived["yes"], 30.0, quote_wait.append, on_quote=True)
    arrived["yes"] = True
    quote_seq.on_event(from_quote=True)
    _eq(quote_wait, [True])


def _seq_deadline() -> None:
    alerts = _FakeAlerts()
    seen: list[bool] = []
    seq = Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, seen.append)
    name = alerts.armed[0][0]
    _true(seq.on_alert(name))
    _eq(seen, [False])
    ready = {"yes": False}
    late: list[bool] = []
    seq2 = Sequencer(alerts.arm, alerts.cancel)
    seq2.until(lambda: ready["yes"], 5.0, late.append)
    ready["yes"] = True  # satisfied between the last event and the deadline
    _true(seq2.on_alert(alerts.armed[-1][0]))
    _eq(late, [True])


def _seq_stale_alert() -> None:
    alerts = _FakeAlerts()
    seen: list[bool] = []
    seq = Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, seen.append)
    _true(not seq.on_alert("probe-wait-999"))
    _eq(seen, [])
    _true(seq.on_alert(alerts.armed[0][0]))
    _eq(seen, [False])
    _true(not seq.on_alert(alerts.armed[0][0]))  # the same alert again must not re-fire it
    _eq(seen, [False])


def _seq_double_wait() -> str:
    alerts = _FakeAlerts()
    seq = Sequencer(alerts.arm, alerts.cancel)
    seq.until(lambda: False, 5.0, lambda _ok: None)
    try:
        seq.until(lambda: False, 5.0, lambda _ok: None)
    except Refusal as exc:
        return str(exc)
    raise AssertionError("a forked sequence was not refused")


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------


def _default_expected_version() -> str | None:
    try:
        return pinned_nautilus_version(PYPROJECT)
    except Refusal:
        return None


def build_parser() -> argparse.ArgumentParser:
    pinned = _default_expected_version()
    p = argparse.ArgumentParser(
        description="Kraken adapter order-semantics verification probes. Places REAL orders with --apply.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--apply", action="store_true", help="actually submit orders. Without it, probes 4-5 only print what they WOULD submit."
    )
    p.add_argument(
        "--probe5", action="store_true", help="additionally allow probe 5, the only probe that spends money. Requires --apply."
    )
    p.add_argument("--probes", default="all", help="which probes to run, e.g. '1,2,3' or 'all' (default: all)")
    p.add_argument("--pair", default="BTC/EUR", help="the instrument probes 4-5 trade (default: BTC/EUR)")
    p.add_argument(
        "--notional", type=float, default=DEFAULT_NOTIONAL_EUR, help=f"per-order notional in EUR (default: {DEFAULT_NOTIONAL_EUR})"
    )
    p.add_argument(
        "--max-notional",
        type=float,
        default=DEFAULT_MAX_NOTIONAL_EUR,
        help=f"hard per-order ceiling in EUR; a computed size above it is REFUSED, never clamped (default: {DEFAULT_MAX_NOTIONAL_EUR})",
    )
    p.add_argument(
        "--max-run-filled",
        type=float,
        default=DEFAULT_MAX_RUN_FILLED_EUR,
        help=f"ceiling on total FILLED notional for the run (default: {DEFAULT_MAX_RUN_FILLED_EUR})",
    )
    p.add_argument(
        "--away",
        type=float,
        default=DEFAULT_AWAY_FRACTION,
        help=f"probe-4 resting distance from mid, as a fraction; the protocol floor is {MIN_AWAY_FRACTION} (default: {DEFAULT_AWAY_FRACTION})",
    )
    p.add_argument("--cross", type=float, default=0.0005, help="probe-4b offset THROUGH the ask, as a fraction (default: 0.0005)")
    p.add_argument("--leverage", type=int, default=2, help="leverage for probes 4c/4d (default: 2)")
    p.add_argument("--max-quote-age", type=float, default=10.0, help="a quote older than this is refused, not used (default: 10s)")
    p.add_argument("--settle", type=float, default=20.0, help="seconds to settle after the node is ready (default: 20)")
    p.add_argument(
        "--order-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for an accept/cancel, and the window a cancel issued while stopping has to reach the venue (default: 30)",
    )
    p.add_argument("--fill-timeout", type=float, default=60.0, help="seconds to wait for a probe-5 fill (default: 60)")
    p.add_argument(
        "--probe3-timeout", type=float, default=30.0, help="seconds to wait for the first quote on every pair (default: 30)"
    )
    p.add_argument(
        "--probe3-basket",
        action="store_true",
        help="also subscribe the two BTC-quoted basket legs (protocol says the 10 EUR pairs)",
    )
    p.add_argument(
        "--connect-timeout",
        type=float,
        default=60.0,
        help="seconds the node gives its clients to connect before it aborts the start (default: 60)",
    )
    p.add_argument(
        "--no-exec",
        action="store_true",
        help="build no exec client: a credential-free, order-free smoke test of the harness itself",
    )
    p.add_argument(
        "--log-level", default="WARNING", help="nautilus log level (default: WARNING; use INFO to see the adapter's own narration)"
    )
    p.add_argument(
        "--expect-nautilus",
        default=pinned,
        help=f"required nautilus-trader version (default: the version pyproject.toml pins, {pinned or 'unreadable here'})",
    )
    p.add_argument("--allow-version-mismatch", action="store_true", help="run against a different nautilus version anyway")
    p.add_argument(
        "--evidence-dir",
        default=".",
        help="where the evidence JSON is written (default: cwd -- pass a path outside the repo, or run from one)",
    )
    p.add_argument("--selftest", action="store_true", help="run the pure-logic rail tests and exit; no network, no credentials")
    return p


def preflight(args) -> None:
    try:
        args.selected_probes = parse_probes(args.probes)
    except Refusal as exc:
        raise SystemExit(f"REFUSING: {exc}") from None
    print(f"probes selected: {sorted(args.selected_probes)}")

    installed = nautilus_trader.__version__
    if not args.expect_nautilus:
        raise SystemExit(
            f"REFUSING: the nautilus-trader pin could not be read from {PYPROJECT}, and no "
            f"--expect-nautilus was given. This run's whole deliverable is the exact version it "
            f"bound to, so it will not guess one. Run from the worktree, or pass "
            f"--expect-nautilus {installed}."
        )
    print(f"nautilus-trader installed: {installed} (expected {args.expect_nautilus})")
    if installed != args.expect_nautilus:
        msg = f"installed nautilus-trader is {installed}, not the expected {args.expect_nautilus}"
        if not args.allow_version_mismatch:
            raise SystemExit(
                f"REFUSING: {msg}. The whole point of this run is which version it binds to.\n"
                f"The expectation comes from the pin in {PYPROJECT}; `uv sync` reconciles the two.\n"
                f"Pass --expect-nautilus {installed} if that is deliberate."
            )
        print(f"!! {msg} -- continuing because --allow-version-mismatch was given")

    if not args.no_exec:
        missing = [v for v in (API_KEY_VAR, API_SECRET_VAR) if not os.environ.get(v)]
        if missing:
            raise SystemExit(
                f"REFUSING: {' and '.join(missing)} not set in the environment.\n"
                f"Run through infra/scripts/probe-with-vaulted-key.sh, which puts the vaulted trade "
                f"key into this process's environment and nothing else -- it never reaches a file, a "
                f"shell you keep, or a command line. Or use --no-exec for a credential-free smoke "
                f"test.",
            )
        print(f"credentials: {API_KEY_VAR} and {API_SECRET_VAR} are present (their values are never printed)")

    if args.probe5 and not args.apply:
        raise SystemExit("REFUSING: --probe5 without --apply is meaningless. Both, or neither.")
    if args.max_notional > ABSOLUTE_MAX_NOTIONAL_EUR:
        raise SystemExit(
            f"REFUSING: --max-notional {args.max_notional} is above this harness's absolute ceiling {ABSOLUTE_MAX_NOTIONAL_EUR}"
        )
    if args.notional > args.max_notional:
        raise SystemExit(f"REFUSING: --notional {args.notional} is above --max-notional {args.max_notional}")
    if args.notional < 1.0:
        # Kraken's costmin on the EUR pairs is 0.45; anything near it turns a venue rejection into
        # something that reads like an adapter failure. Refuse here, where the cause is legible.
        raise SystemExit(f"REFUSING: --notional {args.notional} is too small to clear the venue's costmin floor")
    if args.away < MIN_AWAY_FRACTION:
        raise SystemExit(f"REFUSING: --away {args.away} is below the protocol's {MIN_AWAY_FRACTION}")
    if args.leverage < 1:
        raise SystemExit(f"REFUSING: --leverage {args.leverage} is not a leverage")

    print(f"mode: {'APPLY -- orders WILL reach the venue' if args.apply else 'DRY-RUN -- nothing will be submitted'}")
    print(f"probe 5 (spends money): {'ARMED' if args.probe5 else 'gated off'}")
    print(
        f"per-order ceiling: EUR {args.max_notional:.2f} (refuse, never clamp) | run filled ceiling: EUR {args.max_run_filled:.2f}"
    )
    print(f"client order id shape: O-<stamp>{PROBE_ORDER_ID_INFIX}<n>  (engine's is ...{ENGINE_ORDER_ID_INFIX}...)")
    print("reminder: the production engine reconciles this same account. Our orders reach it as")
    print("          events.order.EXTERNAL with no ledgered row -> its unmatched branch (counts, logs,")
    print("          returns). Anything left RESTING would be cancelled by its adopt pass at a restart.")


def final_read(node: LiveNode, state: RunState) -> LeftoverSplit:
    """The last word on what this run left behind, read from the Cache on this thread after the
    node has stopped. Every earlier read happened while orders could still change; this one cannot
    be overtaken, and it is what the exit code and the cancel-by-hand banner come from."""
    split = classify_submitted(state.submitted, lambda coid: node.cache.order(ClientOrderId(coid)))
    if split.unknown:
        print(f"\n!! {len(split.unknown)} submitted client order id(s) have NO cache record at all:")
        for coid in split.unknown:
            print(f"!!   {coid} -- submitted, never confirmed; treat it as possibly resting at the venue")
    if not state.sequence_complete:
        filled = [
            (coid, float(o.filled_qty))
            for coid in state.submitted
            if (o := node.cache.order(ClientOrderId(coid))) and float(o.filled_qty) > 0
        ]
        if filled:
            # Orders are only half the exposure. A buy that filled before the run ended is a
            # POSITION, and a run that stopped mid-sequence never got to close it -- nothing in the
            # order read can see that. Keyed on the sequence not finishing rather than on a signal
            # arriving: an exec client that dies takes the node down with no signal, and that path
            # leaves exactly the same open position.
            print("\n!! this run ended before its sequence finished, AFTER one or more of its orders filled:")
            for coid, qty in filled:
                print(f"!!   {coid} filled {qty}")
            print("!! a fill with no closing leg is an OPEN POSITION. Check Kraken -> Trade and flatten by hand.")
            state.notes.append("the run ended mid-sequence after a fill -- check Kraken for an open position and flatten by hand")
    stray = [
        o
        for o in node.cache.orders_open(venue=KRAKEN_VENUE)
        if PROBE_ORDER_ID_INFIX in str(o.client_order_id) and str(o.client_order_id) not in state.submitted
    ]
    for o in stray:
        # A probe-shaped id this process did not submit: a previous run's leftover the venue still
        # holds, adopted by this node's startup reconciliation.
        print(f"\n!! a probe-shaped order this run did not submit is OPEN at the venue: {o.client_order_id}")
        state.notes.append(f"an earlier run's probe order is still open: {o.client_order_id}")
        split.resting.append(str(o.client_order_id))
    return split


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()

    print("=" * 78)
    print("Kraken adapter order-semantics verification -- six-probe protocol")
    print("=" * 78)
    preflight(args)

    state = RunState()
    strategy = ProbeStrategy(args, state)
    try:
        node = build_node(args, strategy)
    except Refusal as exc:
        # A rail said no while the node was being assembled, so the sequence never began and
        # nothing was submitted. Reported as a refusal rather than as a traceback.
        print(f"\n!! REFUSED before the node was built: {exc}")
        return 2

    # The only thing that arms faulthandler here: a native abort -- a Rust panic in the adapter, or
    # the pyo3 assertion for an unsendable object touched off its own thread -- otherwise kills the
    # process with exit 134 and nothing on stderr. `file=2` is the process's real stderr, which a
    # signal-handler dump needs, and `disable()` first is what makes this call install the handlers
    # regardless of the state the process was already in.
    faulthandler.disable()
    faulthandler.enable(file=2)

    exit_code = 0
    try:
        # Returns on a clean shutdown and RAISES on a start it cannot complete -- a client that
        # never connects, a startup reconciliation that never finishes. Nothing was submitted in
        # that case, and the raise is the report.
        node.run()
    except BaseException as exc:  # noqa: BLE001 - the table and the leftover read are owed on every path
        print(f"\n!! the node stopped abnormally: {exc!r}")
        state.notes.append(f"the node stopped abnormally: {exc!r}")
        exit_code = 2

    leftovers = final_read(node, state)
    node.dispose()

    if state.aborted_by and exit_code == 0:
        exit_code = 2

    if leftovers.outstanding:
        exit_code = 3
        print("\n" + "!" * 78)
        print("!! ORDERS THIS HARNESS PLACED ARE STILL OPEN. Cancel them BY HAND at Kraken now:")
        for coid in leftovers.outstanding:
            order = node.cache.order(ClientOrderId(coid))
            if order is None:
                print(f"!!   client_order_id={coid} (no cache record -- look it up at the venue)")
            else:
                print(
                    f"!!   client_order_id={coid} venue_order_id={order.venue_order_id} "
                    f"{order.instrument_id} {order.side} {order.quantity} status={order.status.name}"
                )
        print("!! Kraken -> Trade -> Open Orders. Do NOT leave the terminal until they are gone.")
        print("!" * 78)

    print("\n" + "=" * 78)
    print(f"PROBE RESULTS -- paste these rows into {VERIFICATION_DOC_DIR}<version>.md")
    print("=" * 78)
    print(render_table(state.results))

    tally: dict[str, int] = {}
    for r in state.results:
        tally[r.verdict] = tally.get(r.verdict, 0) + 1
    print("\nverdict tally: " + (", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "(nothing ran)"))
    if tally.get(VERDICT_REVIEW):
        print("REVIEW rows need a human decision before this run can be written up as a pass.")

    if state.events:
        print(f"\n-- order event stream ({len(state.events)} events) --")
        for e in state.events:
            print(f"  {e.seq:3d} {e.ts} {e.kind:22s} {e.client_order_id or '-':32s} {e.venue_order_id or '-':20s} {e.detail}")

    if state.notes:
        print("\n-- notes requiring a human decision --")
        for n in state.notes:
            print(f"  * {n}")

    if exit_code == 0 and any(r.verdict in (VERDICT_FAIL, VERDICT_ERROR) for r in state.results):
        exit_code = 1
    if exit_code == 0 and any(r.verdict == VERDICT_REFUSED for r in state.results):
        exit_code = 2  # a probe that never ran must never read as a clean pass

    evidence = {
        "nautilus_version": nautilus_trader.__version__,
        "run_stamp": strategy.stamp,
        "argv": sys.argv[1:],
        "results": [asdict(r) for r in state.results],
        "planned_orders": [asdict(p) for p in state.planned],
        "submitted_client_order_ids": state.submitted,
        "events": [asdict(e) for e in state.events],
        "filled_notional_eur": state.filled_notional_eur,
        "notes": state.notes,
        "exit_code": exit_code,
    }
    try:
        out = Path(args.evidence_dir) / f"evidence-{evidence['run_stamp'] or 'norun'}.json"
        out.write_text(json.dumps(evidence, indent=2, default=str))
        print(f"\nevidence written to {out}")
    except Exception as exc:  # noqa: BLE001
        print(f"!! could not write evidence: {exc!r}")

    print(
        f"\nexit code {exit_code} "
        f"({ {0: 'all executed probes passed', 1: 'a probe FAILED', 2: 'refused/aborted', 3: 'SOMETHING WAS LEFT RESTING'}.get(exit_code, '?') })"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
