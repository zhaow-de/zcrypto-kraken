"""The node wrapper (spec 00041 SS the node wrapper): pure 4h-boundary arithmetic, the
restart-inside-a-passable-window startup rule, the ShadowStrategy that owns only timer arithmetic
(schedule the next alert FIRST, then invoke the cycle core -- a hung or raising cycle can never
stall the alert chain), and the production-shape TradingNode assembly mirroring the iter-079
verified adapter configuration (docs/research/14.phase6-adapter-verification.md SS Harness). No
catch-up: a boundary whose window has lapsed is a missed cycle, recorded by the journal's absence
and honestly scored by the gate. Pure UTC throughout -- DST is structurally irrelevant.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nautilus_trader.adapters.kraken.config import KrakenDataClientConfig, KrakenExecClientConfig
from nautilus_trader.adapters.kraken.constants import KRAKEN
from nautilus_trader.adapters.kraken.factories import KrakenLiveDataClientFactory, KrakenLiveExecClientFactory
from nautilus_trader.config import InstrumentProviderConfig, LiveExecEngineConfig, LoggingConfig, TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.identifiers import StrategyId
from nautilus_trader.trading.strategy import Strategy

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
# The probe executor's tick cadence. Restated here rather than imported because
# `cli.engine.executor` is imported lazily (inside `_probe_executor_factory`) while this is needed
# at on_start time; tests/test_engine_node.py pins the two equal.
_TICK_SECONDS = 5.0
_EXEC_TIMER_NAME = "exec-probe-tick"
# The topic nautilus publishes a reconciled order's events on. Built the way the execution engine
# builds it -- a StrategyId through the same f-string -- rather than spelled as a literal, so a
# library rename surfaces in tests/test_engine_node.py's library-boundary test instead of as an
# unsubscribed topic and total silence in production.
_EXTERNAL_ORDER_TOPIC = f"events.order.{StrategyId('EXTERNAL')}"


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
    `events.order.<this strategy's id>` subscription `Strategy.register` installs, and this class
    passes no `StrategyConfig`, so the strategy's external-order claim list stays empty: an order
    the engine did not submit -- the account owner settling a position by hand mid-probe -- keeps
    nautilus's `EXTERNAL` strategy id and structurally never arrives on that topic. That scoping is
    the precondition the executor's unknown-order kill trip rests on; widening it would latch the
    kill switch on a sanctioned act.

    `events.order.EXTERNAL` is ADDITIONALLY subscribed (spec 00098 D1), and neither half of that
    scoping moves. The claim list stays empty, so the own topic still carries only orders this
    engine submitted and the unknown-order trip still runs only there. The new topic reaches
    `_on_external_order_event` -> the executor's disposition filter, which acts only on the orders
    this engine's own ledger vouches for -- the rows the adopt pass re-attached and this session's
    own submissions -- and everything else it counts, logs, and drops before any row write, cancel,
    or trip arithmetic. So the hand settle remains
    structurally unable to reach the trip: it matches no ledgered row, and no widening of the claim
    list is what admits it. tests/test_engine_node.py pins each of these.
    """

    def __init__(
        self,
        config: EngineConfig,
        *,
        run_cycle_fn: Callable = run_cycle,
        clock: Callable = _utc_now,
        executor_factory: Callable | None = None,
    ) -> None:
        super().__init__()
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
            # The second order stream (spec 00098 D1). Wired WITH the executor, never with the
            # strategy: the filter that scopes this topic is the executor's, so a construction that
            # has no executor must not be subscribed to it either.
            self.msgbus.subscribe(topic=_EXTERNAL_ORDER_TOPIC, handler=self._on_external_order_event)

    def _on_cycle_alert(self, event) -> None:
        on_alert_logic(
            boundary=self._next_cycle_ts,
            config=self._engine_config,
            schedule_alert=self._schedule_alert,
            run_cycle_fn=self._run_cycle_fn,
            snapshot_fn=self._snapshot_venue_state,
        )

    # --- the probe executor's four inputs ------------------------------------------------------

    def _on_exec_tick(self, event) -> None:
        if self._executor is not None:
            self._executor.on_timer(self._now())

    def on_quote_tick(self, tick) -> None:
        if self._executor is not None:
            self._executor.on_quote(tick)

    def on_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_order_event(event)

    def _on_external_order_event(self, event) -> None:
        if self._executor is not None:
            self._executor.on_external_order_event(event)


def _node_config(config: EngineConfig) -> TradingNodeConfig:
    """The iter-079-verified adapter configuration: instrument provider load_all, and -- only when
    exec_enabled -- the exec client with MARGIN spot account reporting in ZEUR (the trade key is
    IP-bound to the VPS, so local runs are keyless). Both currency fields read ZEUR: margin summary
    figures are denominated in it, and spot position reports cover the ZEUR-quoted instruments."""
    exec_clients = {}
    if config.exec_enabled:
        exec_clients[KRAKEN] = KrakenExecClientConfig(
            instrument_provider=InstrumentProviderConfig(load_all=True),
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
    return TradingNodeConfig(
        trader_id=_TRADER_ID,
        logging=LoggingConfig(log_level="INFO"),
        # Explicit (it is the library default) because the iter-079 memo names reconciliation as
        # part of the verified harness shape — live exactly when exec_enabled flips on at deployment.
        exec_engine=LiveExecEngineConfig(reconciliation=True),
        data_clients={KRAKEN: KrakenDataClientConfig(instrument_provider=InstrumentProviderConfig(load_all=True))},
        exec_clients=exec_clients,
    )


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


def build_shadow_node(config: EngineConfig) -> TradingNode:
    """Assemble (never run here) the production-shape shadow TradingNode: both Kraken factories
    registered, the ShadowStrategy attached (with the probe executor wired), clients built.
    node.build() only constructs clients -- no credentials required and no network until
    node.run()."""
    node = TradingNode(config=_node_config(config))
    node.add_data_client_factory(KRAKEN, KrakenLiveDataClientFactory)
    node.add_exec_client_factory(KRAKEN, KrakenLiveExecClientFactory)
    node.trader.add_strategy(ShadowStrategy(config, executor_factory=_probe_executor_factory(config)))
    node.build()
    return node
