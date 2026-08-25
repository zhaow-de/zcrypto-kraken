#!/usr/bin/env python3
"""Kraken adapter order-semantics verification -- the spec 00039 six-probe protocol, re-run
against a NEW nautilus-trader version (the memo's "Version re-check rule": a bump must re-run
the order-semantics probes before the engine trades on it).

Committed because the obligation recurs: every nautilus bump owes this run before the engine
may be armed on it, and the probes are only comparable across versions if they are the SAME
probes. Rebuilding them from prose each time silently drifts the comparison.

THIS PLACES REAL ORDERS ON A LIVE KRAKEN ACCOUNT WITH REAL MONEY.

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
  * Nothing is left resting: every order this harness mints is tracked, cancelled in the
    teardown block (normal exit, exception, and SIGINT alike), and the run ends with a venue
    re-read that FAILS loudly if any of ours is still open.
  * Cancels are always BY CLIENT ORDER ID. `cancel_all_orders` is never called: the live
    production engine trades this same account, and a venue-wide cancel would reach its orders.

KNOWN BLOCKER -- read before scheduling an attended pass. This harness drives the node's hosted
run (`run_async`) because its probe sequence is asynchronous and must share a thread with the
strategy: `Strategy` is pyo3-unsendable, so touching it from any other thread aborts the process
with an uncatchable SIGABRT, and the blocking `run()` owns the thread that built it. A hosted run
with a Python strategy registered has been measured to hang at "Connecting data clients"
indefinitely. `--ready-timeout` bounds that -- the run aborts having submitted nothing -- but until
a hosted-run shape that works is established, expect this harness to reach `await_ready`'s refusal
rather than a probe table.

Probe 6's venue re-read needs a SECOND invocation. Nothing in the library makes the venue answer
again mid-run -- the node hands out no execution engine, so there is no whole-venue mass status to
request. What DOES read the venue is a node START, whose startup reconciliation asks for open
orders and positions; so after the main run, run `--probes 6` on its own and read THAT row. Probe 6
refuses to report PASS in an invocation that submitted anything, because there its cache's venue
anchor predates the orders.

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
import asyncio
import json
import math
import os
import signal
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import nautilus_trader
from nautilus_trader.adapters.kraken import (
    KRAKEN,
    KRAKEN_VENUE,
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenExecutionClientConfig,
    KrakenExecutionClientFactory,
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

EXPECTED_NAUTILUS = "2.0.0rc4.dev20260825"

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


class Refusal(Exception):
    """A pre-submit rail said no. Never clamp, never retry -- report and stop the probe."""


class Aborted(Exception):
    """SIGINT/SIGTERM observed, or the node died. Unwinds into the teardown block."""


# --------------------------------------------------------------------------------------------
# Pure helpers (exercised by --selftest; no network, no venue, no credentials)
# --------------------------------------------------------------------------------------------


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


# --------------------------------------------------------------------------------------------
# Strategy
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
    """The data/order handle.

    It owns no probe logic: the sequence is driven from `_run_probes`, which lives on the same
    event loop and therefore may call these methods directly. That is deliberate -- the probe
    sequence's `finally` block must be able to cancel orders while the exec client is STILL
    connected, which a strategy-internal state machine cannot guarantee. It is also mandatory:
    `Strategy` is pyo3-unsendable, so a sequence driven from any other thread would abort the
    process on its first attribute read.
    """

    def __new__(cls, *args, **kwargs):
        """`Strategy` is a pyo3 class, so construction hands `__new__` this subclass's own
        arguments and the base rejects every one it does not know -- `state` among them. Swallowing
        them is what makes this class constructible at all, and passing the config here is what
        keeps `strategy_id` and `config` saying the same thing from construction onward."""
        return super().__new__(cls, _probe_strategy_config())

    def __init__(self, state: RunState) -> None:
        super().__init__(config=_probe_strategy_config())
        self._state = state
        self.subscribed: list[InstrumentId] = []
        self.first_quote_ns: dict[str, int] = {}
        self.subscribe_ns: int = 0

    def on_start(self) -> None:
        self.subscribe_ns = self.clock.timestamp_ns()
        for iid in self.subscribed:
            try:
                self.subscribe_quotes(iid)
            except Exception as exc:  # noqa: BLE001 - a failed subscribe is probe-3 evidence
                self.log.error(f"subscribe_quotes({iid}) raised: {exc}")

    def on_quote(self, tick) -> None:
        key = str(tick.instrument_id)
        if key not in self.first_quote_ns:
            self.first_quote_ns[key] = self.clock.timestamp_ns()

    def on_order_event(self, event) -> None:
        self._state.events.append(
            EventRecord(
                seq=len(self._state.events) + 1,
                ts=datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                kind=type(event).__name__,
                client_order_id=str(getattr(event, "client_order_id", "") or "") or None,
                venue_order_id=str(getattr(event, "venue_order_id", "") or "") or None,
                detail=_event_detail(event),
            ),
        )

    def on_stop(self) -> None:
        # Deliberately empty. Cancels happen in the sequence's teardown, BEFORE the node is
        # stopped -- a cancel issued here races the exec client's disconnect and may never flush.
        self.log.info("ProbeStrategy stopping (teardown already ran)")


def is_post_only_rejection(detail: str) -> bool:
    """True only when the venue rejected the order BECAUSE it would have crossed as post-only.

    Matching the bare substring "post_only" is WRONG and was a live defect: `_event_detail` emits
    the attribute NAME, so an insufficient-funds rejection carries `due_post_only=False` and
    matched it -- making every REJECTED a PASS on the one probe that exists to test protection.
    """
    return "due_post_only=True" in detail or "POST_ONLY_REJECTED" in detail or "postWouldExecute" in detail


def _event_detail(event) -> str:
    bits = []
    for attr in ("reason", "last_qty", "last_px", "commission", "due_post_only"):
        val = getattr(event, attr, None)
        if val is not None:
            bits.append(f"{attr}={val}")
    return " ".join(bits)


# --------------------------------------------------------------------------------------------
# Harness
# --------------------------------------------------------------------------------------------


class Harness:
    def __init__(self, args, state: RunState) -> None:
        self.args = args
        self.state = state
        self.node: LiveNode | None = None
        self.handle = None
        self.trader_id: str = PROBE_TRADER_ID
        self.strategy: ProbeStrategy | None = None
        self.abort = asyncio.Event()
        self.run_task: asyncio.Task | None = None
        self.stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        self.seq = 0
        self.tracked: list = []  # every Order object this harness submitted
        self.pair_id = InstrumentId.from_str(f"{args.pair}.KRAKEN")

    # -- infrastructure ------------------------------------------------------------------

    def _credentials(self) -> tuple[str, str]:
        """The trade key and secret, or a refusal naming whichever variable is missing. The values
        go straight into `_exec_client_config` and are never stored on this object."""
        api_key = os.environ.get(API_KEY_VAR, "")
        api_secret = os.environ.get(API_SECRET_VAR, "")
        missing = [name for name, value in ((API_KEY_VAR, api_key), (API_SECRET_VAR, api_secret)) if not value]
        if missing:
            raise Refusal(f"{' and '.join(missing)} not set in the environment; refusing to build an exec client")
        return api_key, api_secret

    def _exec_client_config(self) -> KrakenExecutionClientConfig:
        """The exec client, in the production engine's own shape: MARGIN spot account reporting in
        ZEUR, under this harness's own account id. Both currency fields read ZEUR because that is
        the `quote_currency.code` every EUR pair carries -- "EUR" would match nothing."""
        api_key, api_secret = self._credentials()
        return KrakenExecutionClientConfig(
            account_id=AccountId(PROBE_ACCOUNT_ID),
            api_key=api_key,
            api_secret=api_secret,
            spot_account_type=AccountType.MARGIN,
            margin_balance_asset="ZEUR",
            spot_positions_quote_currency="ZEUR",
            # Explicit, not inherited: the library default is True, which would move order
            # submission from REST to WebSocket. The engine submits over REST, and a probe run
            # that verified a different transport from the one production uses verifies nothing.
            use_ws_trade=False,
        )

    def _builder(self) -> LiveNodeBuilder:
        """The assembled builder: trader identity, logging, the two exec-engine knobs, the Kraken
        data client, and -- unless `--no-exec` -- the Kraken exec client. Every call takes the
        builder the previous one returned; the chain's value is the whole state.

        The adapter loads the venue's instrument universe itself on connect, so nothing here
        selects it. `filter_unclaimed_external_orders=False` keeps venue-tagged unclaimed orders in
        the cache, which is what lets probe 6 see state this harness did not place."""
        builder = (
            LiveNode.builder(name=PROBE_NODE_NAME, trader_id=TraderId(PROBE_TRADER_ID), environment=Environment.LIVE)
            .with_logging(LoggerConfig(stdout_level=LogLevel(self.args.log_level)))
            .with_exec_engine_config(LiveExecutionEngineConfig(reconciliation=True, filter_unclaimed_external_orders=False))
            .add_data_client(name=KRAKEN, factory=KrakenDataClientFactory(), config=KrakenDataClientConfig())
        )
        if not self.args.no_exec:
            builder = builder.add_exec_client(
                name=KRAKEN, factory=KrakenExecutionClientFactory(), config=self._exec_client_config()
            )
        return builder

    def build(self) -> LiveNode:
        loop = asyncio.get_running_loop()
        node = self._builder().build()
        strategy = ProbeStrategy(self.state)
        symbols = list(EUR_UNIVERSE) + (list(BTC_QUOTED_LEGS) if self.args.probe3_basket else [])
        strategy.subscribed = [InstrumentId.from_str(f"{s}.KRAKEN") for s in symbols]
        if self.pair_id not in strategy.subscribed:
            strategy.subscribed.append(self.pair_id)
        node.add_strategy(strategy)
        # Both captured HERE, before the hosted run takes the node: `trader_id` is read only to be
        # printed, and reading a node attribute while its run owns it raises.
        self.handle = node.handle()
        self.trader_id = str(node.trader_id)
        # The harness's OWN signal handlers, installed last so they win. They unwind the probe
        # sequence into its teardown block, so an interrupted run still cancels what it placed;
        # a handler that stopped the node outright would not.
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self._on_signal, sig)
            except NotImplementedError:  # pragma: no cover - non-POSIX
                pass
        self.node = node
        self.strategy = strategy
        return node

    def _on_signal(self, sig) -> None:
        print(f"\n!! {getattr(sig, 'name', sig)} received -- unwinding into the cancel-everything teardown.")
        print("!! Further Ctrl-C is IGNORED so this sweep always completes; kill -9 from another")
        print("!! terminal only if you are prepared to cancel leftovers by hand at Kraken.")
        self.abort.set()

    def _tick(self) -> None:
        if self.abort.is_set():
            raise Aborted("interrupted by signal")
        if self.run_task is not None and self.run_task.done():
            exc = self.run_task.exception()
            raise Aborted(f"the trading node stopped unexpectedly: {exc!r}")

    async def sleep(self, secs: float) -> None:
        end = time.monotonic() + secs
        while time.monotonic() < end:
            self._tick()
            await asyncio.sleep(min(0.1, max(0.0, end - time.monotonic())))

    async def wait_for(self, predicate, timeout: float, poll: float = 0.1) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self._tick()
            try:
                if predicate():
                    return True
            except Exception:  # noqa: BLE001 - a predicate raising mid-startup is normal
                pass
            await asyncio.sleep(poll)
        self._tick()
        try:
            return bool(predicate())
        except Exception:  # noqa: BLE001
            return False

    async def await_ready(self, timeout: float) -> None:
        """The strategy starts LAST -- after every client connects, after startup reconciliation.
        So `strategy.is_running()` plus the traded instrument being in the cache is the precise
        readiness gate; the node reports itself running before either is true."""
        ok = await self.wait_for(
            lambda: self.strategy.is_running() and self.strategy.cache.instrument(self.pair_id) is not None,
            timeout,
        )
        if not ok:
            raise Aborted(
                f"the node did not reach a ready state within {timeout:.0f}s. NOTHING was submitted.\n"
                f"    First check the hosted-run blocker in this file's header: a hosted run with a "
                f"Python strategy registered has been measured to hang at 'Connecting data clients'. "
                f"If the log stops there, this is that, not your setup.\n"
                f"    Otherwise: credentials, the key's IP allowlist, and connectivity.",
            )

    # -- reporting -----------------------------------------------------------------------

    def record(self, label: str, name: str, expected: str, observed: str, verdict: str) -> None:
        self.state.results.append(ProbeResult(label, name, expected, observed, verdict))
        print(f"  [{verdict:8s}] probe {label}: {observed}")

    # -- order plumbing ------------------------------------------------------------------

    def next_client_order_id(self) -> ClientOrderId:
        self.seq += 1
        coid = mint_client_order_id(self.stamp, self.seq)
        assert_collision_free(coid, self.state.minted)
        if self.strategy is not None and self.strategy.cache.order(ClientOrderId(coid)) is not None:
            raise Refusal(f"client order id {coid} already exists in the cache -- refusing to reuse")
        self.state.minted.add(coid)
        return ClientOrderId(coid)

    def live_quote(self) -> tuple[float, float, float]:
        """(bid, ask, mid) from the latest cached quote, freshness-checked. Refuses rather than
        guesses -- spec requirement, and a stale mid is how a 25 %-away order becomes a fill."""
        tick = self.strategy.cache.quote(self.pair_id)
        if tick is None:
            raise Refusal(
                f"no quote for {self.pair_id} has arrived -- refusing to price probe orders "
                f"(the protocol forbids guessing a price)",
            )
        bid, ask = float(tick.bid_price), float(tick.ask_price)
        age = quote_age_secs(tick.ts_event, self.strategy.clock.timestamp_ns())
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
        instrument = self.strategy.cache.instrument(self.pair_id)
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
        order = self.strategy.order_factory.limit(
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
    ):
        instrument = self.strategy.cache.instrument(self.pair_id)
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
        order = self.strategy.order_factory.market(
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

    async def submit(self, order, leverage: int | None = None) -> None:
        params = {"leverage": int(leverage)} if leverage is not None else None
        self.tracked.append(order)
        self.state.submitted.append(str(order.client_order_id))
        self.strategy.submit_order(order, params=params)

    async def await_status(self, order, wanted: set, timeout: float) -> bool:
        return await self.wait_for(lambda: order.status in wanted, timeout)

    async def cancel_and_confirm(self, order, timeout: float) -> bool:
        """Cancel BY CLIENT ORDER ID -- never `cancel_all_orders`, which would reach the production
        engine's own resting orders on this same account."""
        if order.is_closed:
            return True
        try:
            self.strategy.cancel_order(order.client_order_id)
        except Exception as exc:  # noqa: BLE001
            print(f"  !! cancel of {order.client_order_id} raised: {exc!r}")
            return False
        return await self.wait_for(lambda: order.is_closed, timeout)

    # -- probes --------------------------------------------------------------------------

    async def probe1(self) -> None:
        expected = "AccountState via the exec client; the account's actual balances"
        if self.args.no_exec:
            self.record("1", "Auth + account read", expected, "skipped: --no-exec", VERDICT_SKIP)
            return
        ok = await self.wait_for(lambda: self.strategy.portfolio.account(KRAKEN_VENUE) is not None, self.args.settle)
        account = self.strategy.portfolio.account(KRAKEN_VENUE)
        if not ok or account is None:
            self.record("1", "Auth + account read", expected, "no AccountState arrived", VERDICT_FAIL)
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
        self.record("1", "Auth + account read", expected, observed, VERDICT_PASS)

    async def probe2(self) -> None:
        expected = "Open orders + positions empty-or-actual, no spurious entries"
        if self.args.no_exec:
            self.record("2", "Reconciliation at node start", expected, "skipped: --no-exec", VERDICT_SKIP)
            return
        orders = self.strategy.cache.orders_open(venue=KRAKEN_VENUE)
        positions = self.strategy.cache.positions_open(venue=KRAKEN_VENUE)
        for o in orders:
            print(
                f"      pre-existing open order: {o.client_order_id} {o.instrument_id} {o.side} {o.quantity} @ {getattr(o, 'price', None)}"
            )
        for p in positions:
            print(f"      pre-existing open position: {p.instrument_id} {p.side} {p.quantity}")
        observed = f"open orders {len(orders)}, open positions {len(positions)}"
        if orders or positions:
            observed += " -- PRE-EXISTING venue state, listed above; adjudicate before ordering"
            self.state.notes.append("probe 2 found pre-existing venue state; see the printed list")
            self.record("2", "Reconciliation at node start", expected, observed, VERDICT_REVIEW)
        else:
            self.record("2", "Reconciliation at node start", expected, observed + " (both empty)", VERDICT_PASS)

    async def probe3(self) -> None:
        expected = f"Quotes for all {len(self.strategy.subscribed)} pairs within seconds; clean unsubscribe"
        deadline = self.args.probe3_timeout
        want = {str(i) for i in self.strategy.subscribed}
        await self.wait_for(lambda: want.issubset(self.strategy.first_quote_ns.keys()), deadline)
        got = {k: (v - self.strategy.subscribe_ns) / 1e9 for k, v in self.strategy.first_quote_ns.items() if k in want}
        missing = sorted(want - set(got))
        slowest = max(got.values()) if got else float("nan")
        for k in sorted(got):
            print(f"      first quote {k:22s} at {got[k]:5.2f}s")
        clean = True
        for iid in list(self.strategy.subscribed):
            if iid == self.pair_id:
                continue  # probes 4/5 price against this one; it stays subscribed
            try:
                self.strategy.unsubscribe_quotes(iid)
            except Exception as exc:  # noqa: BLE001
                clean = False
                print(f"      !! unsubscribe {iid} raised: {exc!r}")
        instruments = len(self.strategy.cache.instruments(venue=KRAKEN_VENUE))
        if missing:
            observed = f"{len(got)}/{len(want)} pairs ticked within {deadline:.0f}s; missing {missing}"
            self.record("3", "WS market data", expected, observed, VERDICT_FAIL)
            return
        observed = (
            f"first tick on all {len(want)} pairs by {slowest:.1f}s after subscribe; "
            f"{instruments} instruments loaded; unsubscribe {'clean' if clean else 'RAISED'}"
        )
        self.record("3", "WS market data", expected, observed, VERDICT_PASS if clean else VERDICT_REVIEW)

    async def _run_resting(self, label: str, name: str, expected: str, side: str, leverage: int | None) -> None:
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
            return

        await self.submit(order, leverage=leverage)
        accepted = await self.await_status(order, {OrderStatus.ACCEPTED}, self.args.order_timeout)
        if not accepted:
            observed = f"terminal-without-accept: status={order.status.name} events={[e.kind for e in self.state.events[-6:]]}"
            await self.cancel_and_confirm(order, self.args.order_timeout)
            self.record(label, name, expected, observed, VERDICT_FAIL)
            return
        venue_id = str(order.venue_order_id)
        canceled = await self.cancel_and_confirm(order, self.args.order_timeout)
        filled = float(order.filled_qty)
        if filled:
            self.state.notes.append(f"{label}: UNEXPECTED FILL of {filled} -- a reportable finding (probe 4)")
        observed = (
            f"accepted ({venue_id}), rested, cancel {'confirmed' if canceled else 'NOT confirmed'}; "
            f"status={order.status.name}; filled_qty={filled}"
        )
        verdict = VERDICT_PASS if (canceled and filled == 0.0 and order.status == OrderStatus.CANCELED) else VERDICT_FAIL
        self.record(label, name, expected, observed, verdict)

    async def probe4(self) -> None:
        """The four sub-probes are independently guarded: a refusal on 4a (a stale quote, a size
        under the venue minimum) must not silently cost us 4b-4d, which are the margin/short
        semantics the whole entry criterion turns on."""
        subprobes = (
            lambda: self._run_resting(
                "4a",
                "Spot post-only limit, resting",
                "Accept -> rest -> cancel confirmed",
                "BUY",
                None,
            ),
            self._probe4b,
            lambda: self._run_resting(
                "4c",
                f"Margin long (leverage {self.args.leverage}), resting",
                "Accept with leverage -> rest -> cancel",
                "BUY",
                self.args.leverage,
            ),
            lambda: self._run_resting(
                "4d",
                f"Margin short (leverage {self.args.leverage}), resting",
                "Accept (short via leveraged sell) -> rest -> cancel",
                "SELL",
                self.args.leverage,
            ),
        )
        for label, fn in zip(("4a", "4b", "4c", "4d"), subprobes, strict=True):
            try:
                await fn()
            except Refusal as exc:
                self.record(label, f"probe {label}", "-", f"REFUSED: {exc}", VERDICT_REFUSED)
                print("   (a refusal is a rail doing its job -- nothing was submitted for this sub-probe)")
            except Aborted:
                raise
            except Exception as exc:  # noqa: BLE001
                self.record(label, f"probe {label}", "-", f"ERROR: {exc!r}", VERDICT_ERROR)

    async def _probe4b(self) -> None:
        label, name = "4b", "Crossing post-only"
        # The requirement is post-only protection with no fill. WHICH terminal event the adapter
        # surfaces that as -- OrderCanceled or a post-only OrderRejected -- is an adapter mapping
        # this run OBSERVES; the verdict logic below accepts either. It is stated as owed rather
        # than carried over from an earlier reading, because a reading taken on one adapter build
        # and matched against another turns agreement into evidence of nothing.
        expected = "Venue post-only protection, no fill; RECORD which terminal event it arrives as (OrderCanceled or a post-only OrderRejected -- either passes)"
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
            return

        await self.submit(order)
        # A protected post-only ends terminal on its own. If it instead RESTS, it did not cross:
        # a protocol artifact (the quote moved), not an adapter failure -- and it must be cancelled.
        got_terminal = await self.await_status(order, set(TERMINAL_STATUSES), self.args.order_timeout)
        filled = float(order.filled_qty)
        if not got_terminal:
            canceled = await self.cancel_and_confirm(order, self.args.order_timeout)
            if filled:
                # It rested AND filled, so it did cross and post-only did not protect it. That is
                # the defect this probe exists to catch -- never the benign quote-moved artifact.
                self.state.notes.append(f"{label}: post-only protection did NOT hold; filled {filled} while resting")
                self.record(
                    label,
                    name,
                    expected,
                    f"order RESTED and FILLED {filled} (status={order.status.name}) -- post-only did NOT protect it; "
                    f"cancel {'confirmed' if canceled else 'NOT confirmed'}",
                    VERDICT_FAIL,
                )
                return
            observed = (
                f"order RESTED instead of being protected (status={order.status.name}) -- the quote moved "
                f"between pricing and submission, so it never crossed; cancel "
                f"{'confirmed' if canceled else 'NOT confirmed'}. Protocol artifact: re-run 4b."
            )
            self.record(label, name, expected, observed, VERDICT_REVIEW)
            return
        kinds = [e.kind for e in self.state.events if e.client_order_id == str(order.client_order_id)]
        observed = f"status={order.status.name} via {kinds}; filled_qty={filled}"
        reason = next(
            (e.detail for e in self.state.events if e.client_order_id == str(order.client_order_id) and e.detail),
            "",
        )
        if reason:
            observed += f"; {reason}"
        if filled:
            observed += " -- UNEXPECTED FILL"
            self.state.notes.append(f"{label}: post-only protection did NOT hold; filled {filled}")
        # What this probe verifies is that KRAKEN protected a crossing post-only. DENIED is a LOCAL
        # refusal the venue never saw, and a REJECTED for insufficient funds says nothing about
        # post-only -- both used to record as a passed verification.
        post_only_reason = is_post_only_rejection(reason)
        if order.status == OrderStatus.DENIED:
            verdict = VERDICT_ERROR
            observed += " -- DENIED locally; the venue never saw it, so post-only was never exercised"
        elif filled != 0.0:
            verdict = VERDICT_FAIL
        elif order.status == OrderStatus.CANCELED:
            verdict = VERDICT_PASS
        elif order.status == OrderStatus.REJECTED and post_only_reason:
            verdict = VERDICT_PASS
        elif order.status == OrderStatus.REJECTED:
            verdict = VERDICT_FAIL
            observed += " -- REJECTED for a reason other than post-only; protection was not exercised"
        else:
            verdict = VERDICT_FAIL
        self.record(label, name, expected, observed, verdict)

    async def probe5(self) -> None:
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
            return
        if not self.args.apply:
            # Backstop, not a reachable state: preflight refuses --probe5 without --apply, so a dry
            # run reaches the GATED branch above. Kept so probe 5 still cannot submit if that
            # preflight rail is ever relaxed.
            self.record(
                label, name, expected, f"DRY-RUN, would submit: {planned.describe()} then sell the filled qty back", VERDICT_DRY
            )
            return

        print("      >>> THIS SPENDS MONEY <<<")
        await self.submit(buy)
        if not await self.await_status(buy, {OrderStatus.FILLED}, self.args.fill_timeout):
            observed = (
                f"buy did not fill within {self.args.fill_timeout:.0f}s: status={buy.status.name}, filled_qty={buy.filled_qty}"
            )
            await self.cancel_and_confirm(buy, self.args.order_timeout)
            if float(buy.filled_qty) > 0:
                self.state.notes.append(f"{label}: PARTIAL BUY of {buy.filled_qty} left on the books -- sell it by hand")
                observed += " -- PARTIAL POSITION LEFT; see the manual-cleanup block"
            self.record(label, name, expected, observed, VERDICT_FAIL)
            return

        bought_qty = float(buy.filled_qty)
        buy_px = float(buy.avg_px)
        self.state.filled_notional_eur += bought_qty * buy_px
        print(f"      BUY filled {bought_qty} @ {buy_px} (EUR {bought_qty * buy_px:.5f}); commissions={buy.commissions()}")

        positions = self.strategy.cache.positions_open(venue=KRAKEN_VENUE)
        account = self.strategy.portfolio.account(KRAKEN_VENUE)
        post_buy_balances = {str(c): str(b.total) for c, b in account.balances().items()} if account else {}
        print(f"      post-buy: open positions={len(positions)}, balances={post_buy_balances}")
        print("      note: a SPOT buy under spot_account_type=MARGIN opens no OpenPositions row --")
        print("            the adapter reports MARGIN positions there. Wallet truth is the raw Balance endpoint.")

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
            return
        print(f"      PLAN {planned_sell.describe()}")
        await self.submit(sell)
        if not await self.await_status(sell, {OrderStatus.FILLED}, self.args.fill_timeout):
            observed = (
                f"BUY filled {bought_qty} @ {buy_px} but the closing SELL did not fill "
                f"(status={sell.status.name}, filled={sell.filled_qty}) -- POSITION LEFT OPEN"
            )
            self.state.notes.append(f"{label}: closing sell incomplete -- flatten {self.args.pair} by hand at Kraken")
            self.record(label, name, expected, observed, VERDICT_FAIL)
            return
        sell_px = float(sell.avg_px)
        self.state.filled_notional_eur += float(sell.filled_qty) * sell_px
        gross = (sell_px - buy_px) * bought_qty
        observed = (
            f"market buy {bought_qty} @ {buy_px} filled ({buy.venue_order_id}); "
            f"market sell @ {sell_px} filled ({sell.venue_order_id}); flat; "
            f"gross spread P&L EUR {gross:+.5f}; commissions buy={buy.commissions()} sell={sell.commissions()}"
        )
        self.record(label, name, expected, observed, VERDICT_PASS)

    async def probe6(self) -> None:
        label, name = "6", "Post-run reconciliation"
        expected = "No open orders/positions; balances reflect only probe 5"
        if self.args.no_exec:
            self.record(label, name, expected, "skipped: --no-exec", VERDICT_SKIP)
            return
        venue_anchored = self._venue_anchored()
        orders = self.strategy.cache.orders_open(venue=KRAKEN_VENUE)
        positions = self.strategy.cache.positions_open(venue=KRAKEN_VENUE)
        # Match the probe INFIX, not this process's minted set. A fresh `--probes 6` invocation --
        # the documented recovery read -- has an empty minted set, so a crashed run's own leftovers
        # would classify as somebody else's and downgrade a FAIL to a REVIEW. The infix also
        # survives Kraken's 18-char client-order-id truncation.
        ours = [o for o in orders if PROBE_ORDER_ID_INFIX in str(o.client_order_id)]
        foreign = [o for o in orders if PROBE_ORDER_ID_INFIX not in str(o.client_order_id)]
        account = self.strategy.portfolio.account(KRAKEN_VENUE)
        balances = {str(c): str(b.total) for c, b in account.balances().items()} if account else {}
        for o in orders:
            print(f"      open order: {o.client_order_id} {o.instrument_id} {o.side} {o.quantity} status={o.status.name}")
        for p in positions:
            print(f"      open position: {p.instrument_id} {p.side} {p.quantity}")
        observed = (
            f"venue re-read ({'startup reconciliation, nothing submitted since' if venue_anchored else 'NOT re-read -- this run submitted after its only venue read'}): "
            f"open orders {len(orders)} (ours {len(ours)}, other {len(foreign)}), "
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
                "run `--probes 6` as a SEPARATE invocation and read THAT row for the verdict"
            )
        if ours:
            verdict = VERDICT_FAIL
            self.state.notes.append(f"probe 6: {len(ours)} of OUR orders are still open -- cancel them by hand")
        elif foreign or positions:
            verdict = VERDICT_REVIEW
            self.state.notes.append("probe 6: venue state that is not ours is open -- adjudicate before signing off")
        self.record(label, name, expected, observed, verdict)

    def _venue_anchored(self) -> bool:
        """Whether probe 6's cache read still stands for VENUE truth.

        The node's start is the only thing that asks the venue what is open: startup reconciliation
        requests open orders and positions and populates the cache from the answer. The library
        exposes no way to ask again -- the node hands out no execution engine -- so an invocation
        that submitted orders AFTER its start is reading a cache whose venue answer predates them.
        Such a run cannot report a clean venue; a separate `--probes 6` invocation, which submits
        nothing, can.

        `self.state.submitted` is the test rather than `self.tracked`: it holds exactly the ids
        handed to `submit_order`, which is the conservative set -- an order whose submission raised
        is still counted as possibly having reached the venue."""
        if self.state.submitted:
            print("      !! this invocation submitted orders after its only venue read, so what follows is")
            print("      !! the CACHE. Run `--probes 6` as a SEPARATE invocation for a true venue read.")
            return False
        return True

    # -- teardown ------------------------------------------------------------------------

    async def teardown(self) -> list:
        """Cancel everything this harness placed that is still open, and report what survived.
        Runs on every path: success, refusal, exception, SIGINT."""
        # INITIALIZED means `submit_order` never published the command (it publishes on the local
        # message bus and cannot half-reach the venue), so there is nothing at Kraken to cancel --
        # but it is printed, never silently dropped.
        never_sent = [o for o in self.tracked if o.status == OrderStatus.INITIALIZED]
        for order in never_sent:
            print(f"   (never submitted, nothing at the venue: {order.client_order_id})")
        leftovers = [o for o in self.tracked if not o.is_closed and o.status != OrderStatus.INITIALIZED]
        if not leftovers:
            return []
        print("\n-- teardown: cancelling orders this harness placed --")
        for order in leftovers:
            print(f"   cancelling {order.client_order_id} (status={order.status.name})")
            try:
                self.strategy.cancel_order(order.client_order_id)
            except Exception as exc:  # noqa: BLE001
                print(f"   !! cancel raised for {order.client_order_id}: {exc!r}")
        deadline = time.monotonic() + self.args.order_timeout
        while time.monotonic() < deadline and any(not o.is_closed for o in leftovers):
            await asyncio.sleep(0.2)
        still = [o for o in leftovers if not o.is_closed]
        for order in still:
            print(f"   !! STILL OPEN after cancel: {order.client_order_id} status={order.status.name}")
        return still

    # -- sequence ------------------------------------------------------------------------

    async def run_probes(self, probes: set[int]) -> None:
        print(f"\n== settling {self.args.settle:.0f}s (instrument load, reconciliation, first quotes) ==")
        await self.sleep(self.args.settle)
        for n in sorted(probes):
            print(f"\n== probe {n} ==")
            fn = getattr(self, f"probe{n}")
            try:
                await fn()
            except Refusal as exc:
                self.record(str(n), f"probe {n}", "-", f"REFUSED: {exc}", VERDICT_REFUSED)
                if n in (4, 5):
                    print("   (a refusal is a rail doing its job -- nothing was submitted for this probe)")
            except Aborted:
                raise
            except Exception as exc:  # noqa: BLE001
                self.record(str(n), f"probe {n}", "-", f"ERROR: {exc!r}", VERDICT_ERROR)


# --------------------------------------------------------------------------------------------
# Selftest (no network, no venue, no credentials)
# --------------------------------------------------------------------------------------------


def selftest() -> int:
    failures: list[str] = []

    def check(name: str, fn) -> None:
        try:
            fn()
            print(f"  ok   {name}")
        except AssertionError as exc:
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
        "over-size notional is refused", lambda: _true("exceeds the ceiling" in refuses(lambda: check_notional(15.01, 15.0, "t")))
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

    # --- the constants themselves ---------------------------------------------------------
    check("engine infix is what the engine emits", lambda: _eq(ENGINE_TRADER_ID.split("-")[1], "001"))
    check("default notional is under the default ceiling", lambda: _true(DEFAULT_NOTIONAL_EUR < DEFAULT_MAX_NOTIONAL_EUR))
    check("default away clears the protocol floor", lambda: _true(DEFAULT_AWAY_FRACTION >= MIN_AWAY_FRACTION))
    check("EUR quote is accepted", lambda: _true(require_eur_quote(_Instrument("EUR", "BTC/EUR"), "t") is None))
    check("ZEUR quote is accepted", lambda: _true(require_eur_quote(_Instrument("ZEUR", "XBT/ZEUR"), "t") is None))

    print()
    if failures:
        print(f"SELFTEST FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("SELFTEST PASSED")
    return 0


def _eq(a, b):
    assert a == b, f"{a!r} != {b!r}"


def _close(a, b, tol=1e-9):
    assert abs(a - b) <= tol, f"{a!r} !~ {b!r}"


class _Instrument:
    """Minimal stand-in for the selftest's EUR-quote checks: the guard reads these two only."""

    def __init__(self, quote_currency: str, ident: str) -> None:
        self.quote_currency = quote_currency
        self.id = ident


def _true(v):
    assert v, "expected truthy"


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
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
    p.add_argument("--order-timeout", type=float, default=30.0, help="seconds to wait for an accept/cancel (default: 30)")
    p.add_argument("--fill-timeout", type=float, default=60.0, help="seconds to wait for a probe-5 fill (default: 60)")
    p.add_argument(
        "--probe3-timeout", type=float, default=30.0, help="seconds to wait for the first quote on every pair (default: 30)"
    )
    p.add_argument(
        "--probe3-basket",
        action="store_true",
        help="also subscribe the two BTC-quoted basket legs (protocol says the 10 EUR pairs)",
    )
    p.add_argument("--ready-timeout", type=float, default=180.0, help="seconds to wait for the node to start (default: 180)")
    p.add_argument(
        "--no-exec",
        action="store_true",
        help="build no exec client: a credential-free, order-free smoke test of the harness itself",
    )
    p.add_argument(
        "--log-level", default="WARNING", help="nautilus log level (default: WARNING; use INFO to see the adapter's own narration)"
    )
    p.add_argument(
        "--expect-nautilus", default=EXPECTED_NAUTILUS, help=f"required nautilus-trader version (default: {EXPECTED_NAUTILUS})"
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
    print(f"nautilus-trader installed: {installed} (expected {args.expect_nautilus})")
    if installed != args.expect_nautilus:
        msg = f"installed nautilus-trader is {installed}, not the expected {args.expect_nautilus}"
        if not args.allow_version_mismatch:
            raise SystemExit(
                f"REFUSING: {msg}. The whole point of this run is which version it binds to.\n"
                f"Pass --expect-nautilus {installed} if that is deliberate."
            )
        print(f"!! {msg} -- continuing because --allow-version-mismatch was given")

    if not args.no_exec:
        missing = [v for v in (API_KEY_VAR, API_SECRET_VAR) if not os.environ.get(v)]
        if missing:
            raise SystemExit(
                f"REFUSING: {' and '.join(missing)} not set in the environment.\n"
                f"Export the trade key into THIS shell only (never into a file), or use --no-exec "
                f"for a credential-free smoke test.",
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


async def _amain(args, state: RunState, holder: dict) -> int:
    probes = args.selected_probes
    harness = Harness(args, state)
    holder["harness"] = harness
    node = harness.build()
    holder["node"] = node

    harness.run_task = asyncio.create_task(node.run_async())
    leftovers: list = []
    exit_code = 0
    try:
        await harness.await_ready(args.ready_timeout)
        print(f"node ready: trader_id={harness.trader_id}, run stamp {harness.stamp}")
        await harness.run_probes(probes)
    except Aborted as exc:
        print(f"\n!! ABORTED: {exc}")
        state.notes.append(f"run aborted: {exc}")
        exit_code = 2
    except Refusal as exc:
        print(f"\n!! REFUSED: {exc}")
        state.notes.append(f"run refused: {exc}")
        exit_code = 2
    finally:
        try:
            leftovers = await harness.teardown()
        except Exception as exc:  # noqa: BLE001
            print(f"!! teardown itself raised: {exc!r}")
            leftovers = [o for o in harness.tracked if not o.is_closed]
        try:
            # Through the HANDLE, which is the supported way to stop a hosted run and stays valid
            # for the node's whole lifetime. The node itself is off-limits while its run owns it.
            harness.handle.stop()
        except Exception as exc:  # noqa: BLE001
            print(f"!! stopping the node raised: {exc!r}")
        if harness.run_task is not None and not harness.run_task.done():
            # The hosted run does not return the instant the stop is requested; give it a grace
            # window, then cancel so `asyncio.run` does not complain about a pending task.
            try:
                await asyncio.wait_for(asyncio.shield(harness.run_task), timeout=15.0)
            except Exception:  # noqa: BLE001 - a timeout or the run's own error; the cancel follows
                pass
            if not harness.run_task.done():
                harness.run_task.cancel()
                await asyncio.sleep(0.5)

    if leftovers:
        exit_code = 3
        print("\n" + "!" * 78)
        print("!! ORDERS THIS HARNESS PLACED ARE STILL OPEN. Cancel them BY HAND at Kraken now:")
        for o in leftovers:
            print(
                f"!!   client_order_id={o.client_order_id} venue_order_id={o.venue_order_id} "
                f"{o.instrument_id} {o.side} {o.quantity} status={o.status.name}"
            )
        print("!! Kraken -> Trade -> Open Orders. Do NOT leave the terminal until they are gone.")
        print("!" * 78)

    if exit_code == 0 and any(r.verdict in (VERDICT_FAIL, VERDICT_ERROR) for r in state.results):
        exit_code = 1
    if exit_code == 0 and any(r.verdict == VERDICT_REFUSED for r in state.results):
        exit_code = 2  # a probe that never ran must never read as a clean pass
    return exit_code


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.selftest:
        return selftest()

    print("=" * 78)
    print("Kraken adapter order-semantics verification -- six-probe protocol")
    print("=" * 78)
    preflight(args)

    state = RunState()
    holder: dict = {}
    try:
        exit_code = asyncio.run(_amain(args, state, holder))
    except Refusal as exc:
        # A rail said no while the node was being assembled, so the probe sequence never began and
        # nothing was submitted. Reported as a refusal rather than as a traceback.
        print(f"\n!! REFUSED before the node was built: {exc}")
        state.notes.append(f"run refused during assembly: {exc}")
        exit_code = 2
    except KeyboardInterrupt:
        print("\n!! hard KeyboardInterrupt -- the teardown may not have completed.")
        print("!! CHECK KRAKEN OPEN ORDERS BY HAND before doing anything else.")
        exit_code = 3
    finally:
        node = holder.get("node")
        if node is not None:
            try:
                node.dispose()
            except Exception as exc:  # noqa: BLE001
                print(f"!! node.dispose raised: {exc!r}")

    print("\n" + "=" * 78)
    print("PROBE RESULTS -- paste these rows into this version's docs/research/ verification doc")
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

    evidence = {
        "nautilus_version": nautilus_trader.__version__,
        "run_stamp": getattr(holder.get("harness"), "stamp", None),
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
