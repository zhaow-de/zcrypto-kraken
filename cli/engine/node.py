"""The node wrapper (spec 00041 SS the node wrapper): pure 4h-boundary arithmetic, the
restart-inside-a-passable-window startup rule, the ShadowStrategy that owns only timer arithmetic
(schedule the next alert FIRST, then invoke the cycle core -- a hung or raising cycle can never
stall the alert chain), and the production-shape LiveNode assembly. No catch-up: a boundary whose
window has lapsed is a missed cycle, recorded by the journal's absence and honestly scored by the
gate. Pure UTC throughout -- DST is structurally irrelevant.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nautilus_trader.adapters.kraken import (
    KRAKEN,
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenExecutionClientConfig,
    KrakenExecutionClientFactory,
)
from nautilus_trader.common import Environment, LogLevel
from nautilus_trader.config import LiveExecutionEngineConfig, LoggerConfig
from nautilus_trader.live import LiveNode, LiveNodeBuilder
from nautilus_trader.model import AccountId, AccountType, StrategyId, TraderId
from nautilus_trader.trading import Strategy, StrategyConfig

from cli.config import EngineConfig

# The startup window is run_cycle's own refresh reserve (25 min): a boundary is restart-runnable
# exactly while a restarted cycle can still complete inside the ratified 30-min gate window.
from cli.engine.cycle import _REFRESH_RESERVE, run_cycle
from cli.engine.errors import EngineError
from cli.engine.venuestate import VenueState, venue_state_from_cache
from cli.logging import get_logger

logger = get_logger("engine.node")

_H4 = timedelta(hours=4)
_TRADER_ID = "SHADOW-001"
# The node's own name, which nautilus prefixes its log components with (`SHADOW-001.<name>`).
_NODE_NAME = "zcrypto-shadow"
# The account the exec client reports under. The issuer half must be the venue -- the Cache indexes
# accounts by it, and `venue_state_from_cache` looks the account up by Venue("KRAKEN").
_ACCOUNT_ID = "KRAKEN-001"
# The two variables carrying the trade credentials, rendered onto the engine host. Named here so
# the refusal below can say WHICH is missing without ever touching a value.
_API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
_API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
# The client-order-id tag, a venue-visible identifier: registration stamps it into `strategy_id`
# and into every client order id this strategy mints. Tag-less, registration assigns it
# positionally off the strategies already registered, so a second strategy registered ahead of this
# one would silently take this prefix. Stated explicitly instead, at the value this strategy holds
# today; tests/test_engine_node.py pins the registered identity and the minted prefix.
_ORDER_ID_TAG = "000"
# The probe executor's tick cadence. Restated here rather than imported because
# `cli.engine.executor` is imported lazily (inside `_probe_executor_factory`) while this is needed
# at on_start time; tests/test_engine_node.py pins the two equal.
_TICK_SECONDS = 5.0
_EXEC_TIMER_NAME = "exec-probe-tick"
# The identity nautilus stamps on an order this process did not submit: reconciliation adopts a
# venue-resting unclaimed order under this strategy id and routes its events to whichever strategy
# is registered under it. `ExternalOrderObserver` is that strategy. Taken from the library's own
# `StrategyId` rather than spelled as a literal, so a rename surfaces in tests/test_engine_node.py
# instead of as an observer nothing ever reaches and total silence in production.
_EXTERNAL_STRATEGY_ID = StrategyId("EXTERNAL")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(now: datetime) -> datetime:
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise EngineError(f"now must be an aware datetime, got {now!r}")
    return now.astimezone(timezone.utc)


def most_recent_boundary(now: datetime) -> datetime:
    """The most recent 00/04/08/12/16/20 UTC boundary <= now (aware-UTC in, aware-UTC out)."""
    now = _require_aware(now)
    return now.replace(hour=now.hour - now.hour % 4, minute=0, second=0, microsecond=0)


def next_boundary(now: datetime) -> datetime:
    """The next 00/04/08/12/16/20 UTC boundary strictly after now (aware-UTC in, aware-UTC out)."""
    return most_recent_boundary(now) + _H4


def startup_action(now: datetime, journal_dir: Path) -> datetime | None:
    """The restart-inside-a-passable-window rule: return B = most_recent_boundary(now) iff no
    journal artifact exists for B (neither a success record nor a failed-cycle sidecar) and
    now <= B + 25 min (run_cycle's refresh reserve, so the restarted cycle can actually complete);
    else None. A node restarting at B+5min runs B's cycle instead of burning it; a lapsed or
    already-attempted boundary is never re-run (no catch-up)."""
    now = _require_aware(now)
    boundary = most_recent_boundary(now)
    if now > boundary + _REFRESH_RESERVE:
        return None
    day_dir = journal_dir / f"{boundary:%Y-%m-%d}"
    if (day_dir / f"cycle-{boundary:%H}.json").exists() or (day_dir / f"failed-cycle-{boundary:%H}.json").exists():
        return None
    return boundary


def _invoke_cycle(run_cycle_fn: Callable, cycle_ts: datetime, config: EngineConfig, snapshot_fn: Callable) -> None:
    """Invoke run_cycle, catching and logging any exception -- the node must survive; an
    evidence-less boundary is honestly scored missing by the gate. `snapshot_fn` is called in its
    OWN try first (00089 D7): venue-truth availability can never cost the engine a boundary, so a
    raising snapshot logs and degrades to venue_state=None rather than skipping the cycle -- run_cycle
    still runs and journals an error venue record."""
    try:
        venue_state = snapshot_fn()
    except Exception:
        logger.exception("shadow node: snapshot_fn() raised; the cycle proceeds with venue_state=None")
        venue_state = None
    try:
        run_cycle_fn(cycle_ts, config=config, venue_state=venue_state)
    except Exception:
        logger.exception("shadow node: run_cycle(%s) raised; the boundary stays journal-absent", cycle_ts.isoformat())


def on_start_logic(
    *,
    now: datetime,
    config: EngineConfig,
    schedule_alert: Callable,
    run_cycle_fn: Callable,
    snapshot_fn: Callable = lambda: None,
) -> datetime:
    """Startup: schedule the upcoming boundary's alert FIRST (the alert chain must never depend on
    a cycle completing), then run the startup boundary's cycle if startup_action grants one.
    Returns the upcoming boundary whose alert was scheduled."""
    upcoming = next_boundary(now)
    schedule_alert(upcoming, upcoming + timedelta(seconds=config.settle_delay_secs))
    pending = startup_action(now, config.journal_dir)
    if pending is not None:
        logger.info("shadow node: restart inside %s's passable window; running its cycle now", pending.isoformat())
        _invoke_cycle(run_cycle_fn, pending, config, snapshot_fn)
    return upcoming


def on_alert_logic(
    *,
    boundary: datetime,
    config: EngineConfig,
    schedule_alert: Callable,
    run_cycle_fn: Callable,
    snapshot_fn: Callable = lambda: None,
) -> datetime:
    """One alert: FIRST schedule the following boundary's alert, THEN invoke run_cycle for the
    boundary this alert belongs to -- the exact 00/04/.../20 grid stamp, never the alert time
    (boundary + settle delay), which run_cycle's grid check would reject. Returns the following
    boundary whose alert was scheduled."""
    following = next_boundary(boundary)
    schedule_alert(following, following + timedelta(seconds=config.settle_delay_secs))
    _invoke_cycle(run_cycle_fn, boundary, config, snapshot_fn)
    return following


class ShadowStrategy(Strategy):
    """The thin strategy owning ONLY timer arithmetic and the probe executor's wiring: on_start
    applies the startup rule and seeds the alert chain; each alert schedules its successor before
    invoking the cycle core. The logic lives in the pure module functions (on_start_logic /
    on_alert_logic); run_cycle_fn and clock are injectable for tests.

    The four executor forwarders below are the ONLY inputs the order path has, and each carries
    exactly what nautilus routes to this strategy. `on_order_event` in particular is the
    `events.order.<this strategy's id>` subscription `Strategy.register` installs, and this class's
    `StrategyConfig` claims no instruments, so the strategy's external-order claim list stays
    empty: an order the engine did not submit -- the account owner settling a position by hand
    mid-probe -- keeps nautilus's `EXTERNAL` strategy id and structurally never arrives on that
    topic. That scoping is the precondition the executor's unknown-order kill trip rests on;
    widening it would latch the kill switch on a sanctioned act.

    A SECOND order stream reaches this strategy from the side (spec 00098 D1, 00100 D2), and
    neither half of that scoping moves. The claim list stays empty, so the own topic still carries
    only orders this engine submitted and the unknown-order trip still runs only there. The second
    stream is `ExternalOrderObserver`, a separate strategy registered under the venue's external
    order identity, and it forwards into `_on_external_order_event` -> the executor's disposition
    filter, which acts only on the orders this engine's own ledger vouches for -- the rows the adopt
    pass re-attached and this session's own submissions -- and everything else it counts, logs, and
    drops before any row write, cancel, or trip arithmetic. So the hand settle remains structurally
    unable to reach the trip: it matches no ledgered row, and no widening of the claim list is what
    admits it. tests/test_engine_node.py pins each of these.
    """

    def __new__(cls, *args, **kwargs):
        """`Strategy` is a pyo3 class, so construction hands `__new__` this subclass's own
        arguments and the base rejects every one it does not know -- `executor_factory` among them.
        Swallowing them is what makes this class constructible at all.

        The config goes with them because `strategy_id` is derived at construction from `__new__`'s
        config alone: without one it reads `ShadowStrategy-None` until registration re-derives it
        from `__init__`'s. Registration is what fixes the venue-visible identity, so the two forms
        agree on every client order id -- but only this one keeps `strategy_id` and `config` saying
        the same thing for the whole of the object's life, including the window before the strategy
        is registered. tests/test_engine_node.py pins both ends."""
        return super().__new__(cls, StrategyConfig(order_id_tag=_ORDER_ID_TAG))

    def __init__(
        self,
        config: EngineConfig,
        *,
        run_cycle_fn: Callable = run_cycle,
        clock: Callable = _utc_now,
        executor_factory: Callable | None = None,
    ) -> None:
        super().__init__(config=StrategyConfig(order_id_tag=_ORDER_ID_TAG))
        self._engine_config = config
        self._run_cycle_fn = run_cycle_fn
        self._now = clock
        self._next_cycle_ts: datetime | None = None
        # None (the default) wires nothing at all: no executor, no tick, every forwarder inert.
        # build_shadow_node passes the real factory; every other construction stays a pure
        # timer-arithmetic strategy.
        self._executor_factory = executor_factory
        self._executor = None

    def _schedule_alert(self, boundary: datetime, alert_time: datetime) -> None:
        self._next_cycle_ts = boundary
        self.clock.set_time_alert(f"shadow-cycle-{boundary:%Y-%m-%dT%H}", alert_time, self._on_cycle_alert)

    def _snapshot_venue_state(self) -> VenueState | None:
        """venue_state_from_cache(self.cache, ...) wrapped so ANY exception logs and degrades to
        None (00089 D7): venue-truth availability can never cost the engine a boundary."""
        try:
            return venue_state_from_cache(self.cache, clock=self._now)
        except Exception:
            logger.exception("shadow node: venue_state_from_cache raised; snapshot degrades to None")
            return None

    def on_start(self) -> None:
        on_start_logic(
            now=self._now(),
            config=self._engine_config,
            schedule_alert=self._schedule_alert,
            run_cycle_fn=self._run_cycle_fn,
            snapshot_fn=self._snapshot_venue_state,
        )
        if self._executor_factory is not None:
            # After the cycle wiring, deliberately: the alert chain is the engine's research
            # obligation and must be seeded even if the executor's construction were to raise.
            self._executor = self._executor_factory(self)
            self.clock.set_timer(_EXEC_TIMER_NAME, timedelta(seconds=_TICK_SECONDS), callback=self._on_exec_tick)

    def _on_cycle_alert(self, event) -> None:
        # Read BEFORE on_alert_logic, whose FIRST act is schedule_alert -- which overwrites this
        # field with the FOLLOWING boundary. Read after, the executor would score the wrong week.
        boundary = self._next_cycle_ts
        try:
            on_alert_logic(
                boundary=boundary,
                config=self._engine_config,
                schedule_alert=self._schedule_alert,
                run_cycle_fn=self._run_cycle_fn,
                snapshot_fn=self._snapshot_venue_state,
            )
        finally:
            # The weekly tracking-error trip's ONLY call site (spec 00091 component C), in a
            # `finally` so a boundary whose cycle raised is still scored -- and after the cycle, so
            # the boundary it reads has already journaled. `on_boundary` carries its own total
            # catch, so it can neither raise onto the alert chain nor replace an in-flight exception.
            if self._executor is not None:
                self._executor.on_boundary(boundary)

    # --- the probe executor's four inputs ------------------------------------------------------

    def _on_exec_tick(self, event) -> None:
        if self._executor is not None:
            self._executor.on_timer(self._now())

    def on_quote(self, tick) -> None:
        if self._executor is not None:
            self._executor.on_quote(tick)

    def on_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_order_event(event)

    def _on_external_order_event(self, event) -> None:
        """The second order stream's landing point, handed to `ExternalOrderObserver` by
        `build_shadow_node`. The guard keeps that stream wired WITH the executor and never with the
        strategy alone: the filter that scopes these events is the executor's, so a construction
        that wired none drops them here rather than acting on them unfiltered."""
        if self._executor is not None:
            self._executor.on_external_order_event(event)


def _external_observer_config() -> StrategyConfig:
    """The observer's whole configuration: the external order identity, and nothing else.

    `order_id_tag` is left unset DELIBERATELY. A tag is appended to the id -- measured, a tag "EXT"
    yields `EXTERNAL-EXT` -- and events for orders the venue reports under the plain external
    identity would then reach no strategy at all: no exception, no log, no failing test, the whole
    stream simply dark. Unset, the id reads exactly `EXTERNAL` both at construction and after
    registration, which is where tests/test_engine_node.py measures it.

    The claim list stays at its `None` default here as it does on the main strategy: a claim is what
    would route the account owner's own hand-placed settling fills onto a claiming strategy's own
    order topic and into the unknown-order kill trip.

    The three management flags are set rather than inherited. They arm order management INSIDE the
    library, which reaches the venue without calling any of the sealed methods -- and on this
    identity every order it could manage belongs to the account owner. Inherited, a default flip
    would arm them silently; stated, a flip is visible in this call."""
    return StrategyConfig(
        strategy_id=_EXTERNAL_STRATEGY_ID,
        manage_contingent_orders=False,
        manage_gtd_expiry=False,
        manage_stop=False,
    )


class ExternalOrderObserver(Strategy):
    """The second order stream (spec 00098 D1, 00100 D2): registered under the venue's external
    order identity, it receives the order events of everything this process did not submit --
    a previous process's resting order the startup pass adopted, and the account owner's own
    hand-placed settling orders alike -- and forwards each to `handler`, which is the shadow
    strategy's `_on_external_order_event` and through it the executor's disposition filter. That
    filter acts only on rows this engine's own ledger vouches for; the hand settle matches none,
    so it is counted and dropped before any row write, cancel, or trip arithmetic.

    **Every order-mutating method is sealed to raise.** This class holds a strategy's full
    submit/cancel/modify/close powers, and registered under this id every one of their scoping
    defaults points AT the account owner's book: `cancel_all_orders(strategy_only=True)` scopes to
    this strategy, whose orders are the operator's. The barrier is explicit rather than structural
    because the structural alternative -- `DataActor`, which has no order surface at all -- cannot
    receive order events. tests/test_engine_node.py derives the mutating surface from the library
    itself and asserts every member of it is sealed here, so a method a future release adds is a
    red test and not a quiet hole.

    The read-only surface is deliberately left live rather than sealed -- `query_account` and
    `query_order` reach the venue only to ask, and `order_factory` mints an id without sending
    anything. Nothing here calls them; the seal covers exactly what could act.
    """

    def __new__(cls, *args, **kwargs):
        """`Strategy` is a pyo3 class, so construction hands `__new__` this subclass's own
        arguments and the base rejects every one it does not know -- `handler` among them.
        Swallowing them is what makes this class constructible at all, and passing the config here
        is what makes `strategy_id` read `EXTERNAL` from construction rather than
        `ExternalOrderObserver-None` until registration re-derives it."""
        return super().__new__(cls, _external_observer_config())

    def __init__(self, handler: Callable) -> None:
        super().__init__(config=_external_observer_config())
        self._handler = handler

    def on_order_event(self, event) -> None:
        self._handler(event)

    # --- the seal: the order surface, refused ---------------------------------------------------

    def _refuse(self, method: str) -> None:
        raise EngineError(
            f"{method} is sealed on the external-order observer: this strategy carries the venue's "
            f"own external order identity, so the orders every scoping default here reaches are the "
            f"account owner's. It observes and never acts."
        )

    def submit_order(self, *args, **kwargs) -> None:
        self._refuse("submit_order")

    def submit_order_list(self, *args, **kwargs) -> None:
        self._refuse("submit_order_list")

    def cancel_order(self, *args, **kwargs) -> None:
        self._refuse("cancel_order")

    def cancel_orders(self, *args, **kwargs) -> None:
        self._refuse("cancel_orders")

    def cancel_all_orders(self, *args, **kwargs) -> None:
        self._refuse("cancel_all_orders")

    def cancel_gtd_expiry(self, *args, **kwargs) -> None:
        self._refuse("cancel_gtd_expiry")

    def modify_order(self, *args, **kwargs) -> None:
        self._refuse("modify_order")

    def modify_orders(self, *args, **kwargs) -> None:
        self._refuse("modify_orders")

    def close_position(self, *args, **kwargs) -> None:
        self._refuse("close_position")

    def close_all_positions(self, *args, **kwargs) -> None:
        self._refuse("close_all_positions")

    def market_exit(self, *args, **kwargs) -> None:
        self._refuse("market_exit")

    def post_market_exit(self, *args, **kwargs) -> None:
        self._refuse("post_market_exit")


def _logging_config() -> LoggerConfig:
    """Stdout at INFO, stated explicitly: it is the engine's only log sink and docker collects it."""
    return LoggerConfig(stdout_level=LogLevel.INFO)


def _exec_engine_config() -> LiveExecutionEngineConfig:
    """Both knobs explicit (both are library defaults) because both are load-bearing here.
    Reconciliation is live exactly when exec_enabled flips on at deployment.
    filter_unclaimed_external_orders: filtering would drop VENUE-tagged unclaimed orders out of the
    cache entirely, so the startup pass would neither attach nor CANCEL a previous process's
    resting order, the kill switch's cancel sweep could not reach it either, and the whole
    external-events path would go dark without one ERROR anywhere. Pinned by the config-shape
    test."""
    return LiveExecutionEngineConfig(reconciliation=True, filter_unclaimed_external_orders=False)


def _data_client_config() -> KrakenDataClientConfig:
    """The Kraken data client. The adapter loads the venue's instrument universe itself on connect;
    nothing here selects it, and `test_engine_node.py`'s live instrument-arrival test is what proves
    the twelve `INSTRUMENT_IDS` still land in the Cache."""
    return KrakenDataClientConfig()


def _credentials() -> tuple[str, str] | None:
    """The trade key and secret read from the environment, or None when either is absent or empty.

    The values are handed straight to `_exec_client_config` and are never stored on a module-level
    object, logged, or interpolated into a message -- including the refusal below, which names the
    variables and never their contents."""
    api_key = os.environ.get(_API_KEY_VAR, "")
    api_secret = os.environ.get(_API_SECRET_VAR, "")
    if not api_key or not api_secret:
        return None
    return api_key, api_secret


def _exec_client_config(credentials: tuple[str, str]) -> KrakenExecutionClientConfig:
    """The exec client: MARGIN spot account reporting in ZEUR, under this engine's own account id.
    Both currency fields read ZEUR: margin summary figures are denominated in it, and spot position
    reports cover the ZEUR-quoted instruments."""
    api_key, api_secret = credentials
    return KrakenExecutionClientConfig(
        account_id=AccountId(_ACCOUNT_ID),
        api_key=api_key,
        api_secret=api_secret,
        spot_account_type=AccountType.MARGIN,
        margin_balance_asset="ZEUR",
        # Matched literally against the loaded instrument's `quote_currency.code`, which for
        # every EUR pair is "ZEUR" -- Kraken's AssetPairs returns quote "ZEUR" for modern
        # (ADAEUR) and legacy (XETHZEUR) alike, and the code survives into the Currency object
        # unchanged. Measured against the live public instrument set: 546 instruments carry
        # code ZEUR and ZERO carry EUR. Only the instrument ID is normalized (ADA/EUR.KRAKEN),
        # and that ID-vs-Currency split is the trap -- "EUR" here would match nothing, as would
        # the adapter's own "USDT" default.
        # NOT a tradeability constraint -- measured 2026-08-14 against the installed adapter
        # (T0137's survey). `margin_balance_asset` has exactly ONE call site,
        # `_update_account_state` -> `request_account_state_with_metrics`: it selects the
        # currency the ACCOUNT SUMMARY is denominated in, and appears nowhere in order
        # submission, instrument handling, or position reporting. The OpenPositions branch this
        # config takes is quote-agnostic -- it reports side and net base quantity only -- so this
        # single client already SEES the XXBT-quoted ETH/BTC and SOL/BTC. Both legs are now IN
        # the basket (spec 00094), and what holds them at zero is engine-side and structural:
        # `CrossfreqSystemConfig.assets` stays the ten EUR bases so no sleeve ever computes a
        # /BTC weight, and `cli/engine/cycle.py::_expand_to_basket` emits exactly 0.0 for every
        # basket member the model produced no output for. Order emission is delta-driven, so a
        # 0.0 target against a 0.0 predecessor writes no row at all. The mechanisms earlier
        # revisions of this comment named -- first "this field can never cover them alongside
        # the EUR book", then base-keyed PAIR_KEYS / the root/<base>/EUR store path / a
        # EUR-only cost floor -- are each gone. Rewritten in place rather than annotated, twice
        # now: an inherited wrong mechanism is exactly what keeps going wrong here.
        # Currently unread: the adapter consults it only when spot_account_type is NOT MARGIN
        # AND use_spot_position_reports is True; under MARGIN it takes the OpenPositions branch.
        spot_positions_quote_currency="ZEUR",
    )


def _node_builder(config: EngineConfig) -> LiveNodeBuilder:
    """The assembled builder: trader identity, logging, the two exec-engine knobs, the Kraken data
    client, and -- only when `exec_enabled` -- the Kraken exec client.

    Every call takes the builder the previous one returned; the chain's value is the whole state.

    `exec_enabled` alone decides whether this engine may reach the venue's private side. With it
    off the credentials are never even read and the node is data-only, which is what a keyless run
    has always been: the trade key is IP-bound to the engine host, so a run anywhere else observes
    and cannot trade. With it ON and either variable absent, this REFUSES rather than building a
    node that looks armed and is not -- a substituted placeholder would defer the failure from here
    to the first submission."""
    builder = (
        LiveNode.builder(name=_NODE_NAME, trader_id=TraderId(_TRADER_ID), environment=Environment.LIVE)
        .with_logging(_logging_config())
        .with_exec_engine_config(_exec_engine_config())
        .add_data_client(name=KRAKEN, factory=KrakenDataClientFactory(), config=_data_client_config())
    )
    if config.exec_enabled:
        credentials = _credentials()
        if credentials is None:
            # Variable NAMES only. Whichever of the two is present is a live trade credential, and
            # this message reaches a log, a traceback and the container's stderr.
            raise EngineError(
                f"execution is enabled but the trade credentials are missing: {_API_KEY_VAR} and "
                f"{_API_SECRET_VAR} must both be set and non-empty; refusing to build the node"
            )
        builder = builder.add_exec_client(
            name=KRAKEN, factory=KrakenExecutionClientFactory(), config=_exec_client_config(credentials)
        )
    return builder


def _probe_executor_factory(config: EngineConfig) -> Callable:
    """The production executor factory: `factory(strategy) -> ProbeExecutor`, with the strategy
    itself as the client handle and a gate reading the deployed control-file tree beside the
    journal. `venue_reader` is passed explicitly (rather than relying on the class default) so a
    test can substitute it, mirroring `command.run`'s own gate construction.

    Local import: `cli.engine.executor` reaches `cli.engine.venuestate`, and keeping it here means
    nothing pays it until a node is actually assembled."""
    from cli.engine.execgate import ExecutionGate
    from cli.engine.executor import ProbeExecutor
    from cli.engine.venue import read_system_status

    return lambda strategy: ProbeExecutor(
        client=strategy,
        gate=ExecutionGate(
            armed_in_config=config.exec_armed,
            state_dir=config.journal_dir.parent,
            venue_reader=read_system_status,
        ),
        config=config,
    )


def build_shadow_node(config: EngineConfig) -> LiveNode:
    """Assemble (never run here) the production-shape shadow LiveNode: the builder's clients
    constructed, then the ShadowStrategy attached with the probe executor wired, then the external
    order observer attached onto that strategy's own external forwarder. Building constructs clients
    only -- no network until node.run().

    The observer takes the forwarder of THIS strategy, the one carrying the executor factory: the
    filter that scopes external events is the executor's, so the second stream is wired with an
    executor or its events are dropped unacted-on."""
    node = _node_builder(config).build()
    strategy = ShadowStrategy(config, executor_factory=_probe_executor_factory(config))
    node.add_strategy(strategy)
    node.add_strategy(ExternalOrderObserver(strategy._on_external_order_event))
    return node
