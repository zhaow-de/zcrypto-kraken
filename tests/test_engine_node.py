"""The node wrapper (spec 00041 SS the node wrapper): pure boundary arithmetic, the
restart-inside-a-passable-window startup rule, the alert chain (schedule-next-first, run_cycle
exceptions contained), and the iter-079-shaped TradingNode assembly. No live node is ever run --
the attended soak is the live smoke; node.build() itself is offline (verified by the build tests,
which construct both exec_enabled shapes without credentials or network).
"""

import functools
import json
import logging
import os
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nautilus_trader.model.enums import AccountType

from cli.config import EngineConfig
from cli.engine import ShadowStrategy, most_recent_boundary, next_boundary, node, startup_action
from cli.engine.cycle import run_cycle
from cli.engine.errors import EngineError
from cli.engine.node import _node_config, on_alert_logic, on_start_logic

UTC = timezone.utc
B08 = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
B12 = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)


def _config(tmp_path: Path, **overrides) -> EngineConfig:
    return EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal", **overrides)


# --- next_boundary / most_recent_boundary -------------------------------------------------------


def test_next_boundary_mid_window():
    assert next_boundary(datetime(2026, 7, 10, 9, 30, tzinfo=UTC)) == B12


def test_next_boundary_on_exact_boundary_is_strictly_after():
    assert next_boundary(B08) == B12
    assert next_boundary(B08 + timedelta(microseconds=1)) == B12


def test_next_boundary_rolls_over_midnight():
    assert next_boundary(datetime(2026, 7, 10, 20, 0, tzinfo=UTC)) == datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
    assert next_boundary(datetime(2026, 7, 10, 23, 59, 59, 999999, tzinfo=UTC)) == datetime(2026, 7, 11, 0, 0, tzinfo=UTC)


def test_next_boundary_normalizes_non_utc_aware_input():
    # 10:30+02:00 is 08:30 UTC; the result is the UTC boundary, in UTC.
    plus2 = timezone(timedelta(hours=2))
    result = next_boundary(datetime(2026, 7, 10, 10, 30, tzinfo=plus2))
    assert result == B12
    assert result.utcoffset() == timedelta(0)


def test_next_boundary_rejects_naive():
    with pytest.raises(EngineError, match="aware"):
        next_boundary(datetime(2026, 7, 10, 9, 30))


def test_most_recent_boundary_mid_window():
    assert most_recent_boundary(datetime(2026, 7, 10, 9, 30, tzinfo=UTC)) == B08
    assert most_recent_boundary(datetime(2026, 7, 10, 3, 59, tzinfo=UTC)) == datetime(2026, 7, 10, 0, 0, tzinfo=UTC)


def test_most_recent_boundary_on_exact_boundary_is_itself():
    assert most_recent_boundary(B08) == B08


def test_most_recent_boundary_rejects_naive():
    with pytest.raises(EngineError, match="aware"):
        most_recent_boundary(datetime(2026, 7, 10, 9, 30))


# --- startup_action -----------------------------------------------------------------------------


def test_startup_action_runs_boundary_inside_passable_window(tmp_path):
    # A node restarting at B+5min runs B's cycle instead of burning it.
    assert startup_action(B08 + timedelta(minutes=5), tmp_path / "journal") == B08


def test_startup_action_window_edge_is_inclusive(tmp_path):
    # The window matches run_cycle's 25-min refresh reserve, so a restarted cycle can complete.
    assert startup_action(B08 + timedelta(minutes=25), tmp_path / "journal") == B08
    assert startup_action(B08 + timedelta(minutes=25, seconds=1), tmp_path / "journal") is None


def test_startup_action_skips_boundary_with_success_record(tmp_path):
    journal = tmp_path / "journal"
    day = journal / "2026-07-10"
    day.mkdir(parents=True)
    (day / "cycle-08.json").write_text("{}")
    assert startup_action(B08 + timedelta(minutes=5), journal) is None


def test_startup_action_skips_boundary_with_failed_sidecar(tmp_path):
    # An already-attempted boundary is never re-run: the sidecar counts as attempted.
    journal = tmp_path / "journal"
    day = journal / "2026-07-10"
    day.mkdir(parents=True)
    (day / "failed-cycle-08.json").write_text("{}")
    assert startup_action(B08 + timedelta(minutes=5), journal) is None


def test_startup_action_rejects_naive(tmp_path):
    with pytest.raises(EngineError, match="aware"):
        startup_action(datetime(2026, 7, 10, 8, 5), tmp_path / "journal")


# --- the alert-chain logic (pure functions) -----------------------------------------------------


def _recorders(events: list, *, raise_on_run: Exception | None = None):
    """A schedule recorder and a run_cycle stub appending into one shared list, so ordering
    between scheduling and invocation is directly observable. run_fn captures venue_state too, so
    a test can read back what snapshot_fn's product (or its None degrade) reached run_cycle_fn."""

    def schedule_alert(boundary, alert_time):
        events.append(("schedule", boundary, alert_time))

    def run_fn(cycle_ts, *, config, venue_state=None):
        events.append(("run", cycle_ts, config, venue_state))
        if raise_on_run is not None:
            raise raise_on_run

    return schedule_alert, run_fn


def test_on_alert_logic_schedules_following_alert_before_invoking_run_cycle(tmp_path):
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    following = on_alert_logic(boundary=B08, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert following == B12
    assert [e[0] for e in events] == ["schedule", "run"]
    assert events[0][1:] == (B12, B12 + timedelta(seconds=config.settle_delay_secs))
    # cycle_ts is the BOUNDARY (exact grid stamp), never the alert time (boundary + settle delay).
    # venue_state is None here: no snapshot_fn was passed, so on_alert_logic's default (lambda: None) ran.
    assert events[1][1:] == (B08, config, None)


def test_on_alert_logic_respects_settle_delay(tmp_path):
    config = _config(tmp_path, settle_delay_secs=30)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    on_alert_logic(boundary=B08, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert events[0][2] == B12 + timedelta(seconds=30)


def test_on_alert_logic_rolls_over_midnight(tmp_path):
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    b20 = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)
    assert on_alert_logic(boundary=b20, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn) == datetime(
        2026, 7, 11, 0, 0, tzinfo=UTC
    )


def test_on_alert_logic_contains_run_cycle_exception(tmp_path):
    # A raising cycle can never stall the alert chain: the next alert is ALREADY scheduled before
    # the raise, and the exception does not propagate (the node must survive; the evidence-less
    # boundary is honestly scored missing by the gate).
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events, raise_on_run=RuntimeError("boom"))
    following = on_alert_logic(boundary=B08, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert following == B12
    assert [e[0] for e in events] == ["schedule", "run"]


def test_on_alert_logic_passes_snapshot_product_as_venue_state(tmp_path):
    # The Cache snapshot taken at the boundary crosses into run_cycle_fn as venue_state -- this is
    # the loop that gives run_cycle real venue truth instead of the None it always got before.
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    sentinel = object()
    on_alert_logic(boundary=B08, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn, snapshot_fn=lambda: sentinel)
    assert events[1][1:] == (B08, config, sentinel)


def test_on_alert_logic_raising_snapshot_fn_degrades_to_none_and_still_runs_the_cycle(tmp_path, caplog):
    # 00089 D7: venue-truth availability can never cost the engine a boundary. A raising snapshot_fn
    # is caught in its OWN try (separate from run_cycle_fn's), logged, and run_cycle_fn still runs --
    # with venue_state=None, so it journals an error venue record instead of skipping the boundary.
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)

    def raising_snapshot_fn():
        raise RuntimeError("cache blew up")

    with caplog.at_level(logging.ERROR, logger="zcrypto.engine.node"):
        following = on_alert_logic(
            boundary=B08, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn, snapshot_fn=raising_snapshot_fn
        )
    assert following == B12
    assert [e[0] for e in events] == ["schedule", "run"]
    assert events[1][1:] == (B08, config, None)
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_on_start_logic_runs_startup_boundary_after_scheduling(tmp_path):
    # Restart at B+5min with no journal artifact: the upcoming alert is scheduled FIRST (the alert
    # chain never depends on a cycle completing), then B's cycle runs immediately.
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    now = B08 + timedelta(minutes=5)
    upcoming = on_start_logic(now=now, config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert upcoming == B12
    assert [e[0] for e in events] == ["schedule", "run"]
    assert events[0][1:] == (B12, B12 + timedelta(seconds=config.settle_delay_secs))
    # venue_state is None here: no snapshot_fn was passed, so on_start_logic's default (lambda: None) ran.
    assert events[1][1:] == (B08, config, None)


def test_on_start_logic_no_catch_up_for_lapsed_boundary(tmp_path):
    # A lapsed window (now > B + 25 min) only schedules ahead: the boundary is a missed cycle,
    # recorded by the journal's absence.
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    on_start_logic(now=B08 + timedelta(minutes=40), config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert [e[0] for e in events] == ["schedule"]


def test_on_start_logic_skips_attempted_boundary(tmp_path):
    config = _config(tmp_path)
    day = config.journal_dir / "2026-07-10"
    day.mkdir(parents=True)
    (day / "failed-cycle-08.json").write_text("{}")
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    on_start_logic(now=B08 + timedelta(minutes=5), config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert [e[0] for e in events] == ["schedule"]


def test_on_start_logic_contains_startup_run_cycle_exception(tmp_path):
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events, raise_on_run=RuntimeError("boom"))
    upcoming = on_start_logic(now=B08 + timedelta(minutes=5), config=config, schedule_alert=schedule_alert, run_cycle_fn=run_fn)
    assert upcoming == B12
    assert [e[0] for e in events] == ["schedule", "run"]


# --- ShadowStrategy delegation (no live node; bare construction + a minimal stub) ---------------


class FakeClock:
    """Captures the strategy's two clock interactions: the per-boundary alert and the repeating
    executor tick."""

    def __init__(self):
        self.alerts: list[tuple[str, datetime, object]] = []
        self.timers: list[tuple[str, timedelta, object]] = []

    def set_time_alert(self, name, alert_time, callback):
        self.alerts.append((name, alert_time, callback))

    def set_timer(self, name, interval, callback=None):
        self.timers.append((name, interval, callback))


def test_shadow_strategy_bare_construction_defaults(tmp_path):
    config = _config(tmp_path)
    strategy = ShadowStrategy(config)
    assert strategy._engine_config is config
    assert strategy._run_cycle_fn is run_cycle
    assert strategy._now().tzinfo is not None
    assert strategy._next_cycle_ts is None


def test_schedule_alert_sets_state_and_timer(tmp_path):
    # _schedule_alert against a minimal stub: unique per-boundary timer name, the alert time as
    # given, the strategy's own handler as callback, and the boundary recorded for the handler.
    stub = types.SimpleNamespace(clock=FakeClock(), _next_cycle_ts=None)
    stub._on_cycle_alert = functools.partial(ShadowStrategy._on_cycle_alert, stub)
    ShadowStrategy._schedule_alert(stub, B12, B12 + timedelta(seconds=90))
    assert stub._next_cycle_ts == B12
    assert stub.clock.alerts == [("shadow-cycle-2026-07-10T12", B12 + timedelta(seconds=90), stub._on_cycle_alert)]
    b16 = B12 + timedelta(hours=4)
    ShadowStrategy._schedule_alert(stub, b16, b16 + timedelta(seconds=90))
    assert stub.clock.alerts[1][0] == "shadow-cycle-2026-07-10T16"


def test_shadow_strategy_on_start_and_alert_delegate(tmp_path):
    # A real (unregistered) ShadowStrategy with injected clock/run_cycle_fn; _schedule_alert is
    # overridden on the instance (the nautilus clock is readonly pre-registration) but mimics its
    # state update, so the full on_start -> alert -> next-alert chain is exercised.
    config = _config(tmp_path)
    events: list = []

    def run_fn(cycle_ts, *, config, venue_state=None):
        events.append(("run", cycle_ts))

    now = B08 + timedelta(minutes=5)
    strategy = ShadowStrategy(config, run_cycle_fn=run_fn, clock=lambda: now)

    def schedule_alert(boundary, alert_time):
        strategy._next_cycle_ts = boundary
        events.append(("schedule", boundary, alert_time))

    strategy._schedule_alert = schedule_alert
    strategy.on_start()
    assert events == [
        ("schedule", B12, B12 + timedelta(seconds=config.settle_delay_secs)),
        ("run", B08),
    ]
    strategy._on_cycle_alert(None)  # the B12 alert fires
    assert events[2:] == [
        ("schedule", B12 + timedelta(hours=4), B12 + timedelta(hours=4, seconds=config.settle_delay_secs)),
        ("run", B12),
    ]


def test_shadow_strategy_wires_its_own_snapshot_hook(tmp_path):
    # on_start / _on_cycle_alert must pass ShadowStrategy._snapshot_venue_state as snapshot_fn --
    # proven by overriding it with a sentinel-returning stub and reading the sentinel back off
    # run_cycle_fn's captured venue_state kwarg.
    config = _config(tmp_path)
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    sentinel = object()
    now = B08 + timedelta(minutes=5)
    strategy = ShadowStrategy(config, run_cycle_fn=run_fn, clock=lambda: now)
    strategy._schedule_alert = schedule_alert
    strategy._snapshot_venue_state = lambda: sentinel
    strategy.on_start()
    assert events[1][1:] == (B08, config, sentinel)

    strategy._next_cycle_ts = B12
    strategy._on_cycle_alert(None)  # the B12 alert fires
    assert events[3][1:] == (B12, config, sentinel)


def test_snapshot_venue_state_logs_and_returns_none_on_any_exception(tmp_path, monkeypatch, caplog):
    # ShadowStrategy._snapshot_venue_state wraps venue_state_from_cache itself (00089 D7), on top of
    # _invoke_cycle's own catch -- so its own contract (log + None) holds even called directly.
    config = _config(tmp_path)
    strategy = ShadowStrategy(config)

    def boom(cache, *, clock):
        raise RuntimeError("cache blew up")

    monkeypatch.setattr(node, "venue_state_from_cache", boom)
    with caplog.at_level(logging.ERROR, logger="zcrypto.engine.node"):
        result = strategy._snapshot_venue_state()
    assert result is None
    assert any(r.levelno == logging.ERROR for r in caplog.records)


# --- the probe-executor wiring (spec 00090 Task 9) ----------------------------------------------


class RecordingExecutor:
    """Stands in for ProbeExecutor at the wiring seam: records what each forwarder handed it."""

    def __init__(self):
        self.timers: list[datetime] = []
        self.quotes: list[object] = []
        self.events: list[object] = []
        self.external_events: list[object] = []

    def on_timer(self, now):
        self.timers.append(now)

    def on_quote(self, tick):
        self.quotes.append(tick)

    def on_order_event(self, event):
        self.events.append(event)

    def on_external_order_event(self, event):
        self.external_events.append(event)


class RecordingMsgBus:
    """The strategy's `self.msgbus` at the wiring seam: records every (topic, handler) pair the
    strategy subscribed. Deliberately a stub and not the real bus, so these wiring tests carry no
    assumption about the bus's own behaviour, only about what we ask of it -- the two
    library-boundary tests below use a REAL MessageBus (one constructed directly, one reached
    through an actual nautilus registration) to pin the parts a stub cannot speak for."""

    def __init__(self):
        self.subscriptions: list[tuple[str, object]] = []

    def subscribe(self, topic, handler):
        self.subscriptions.append((topic, handler))


def _exec_stub(config, clock, *, executor_factory=None, executor=None):
    """A ShadowStrategy stand-in driven through the unbound methods (the house pattern of
    test_schedule_alert_sets_state_and_timer): a real instance's `clock` is readonly until the
    nautilus registration this suite never performs."""
    stub = types.SimpleNamespace(
        clock=clock,
        msgbus=RecordingMsgBus(),
        _engine_config=config,
        _now=lambda: B08 + timedelta(minutes=5),
        _run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None,
        _snapshot_venue_state=lambda: None,
        _next_cycle_ts=None,
        _executor_factory=executor_factory,
        _executor=executor,
    )
    stub._schedule_alert = functools.partial(ShadowStrategy._schedule_alert, stub)
    stub._on_cycle_alert = functools.partial(ShadowStrategy._on_cycle_alert, stub)
    stub._on_exec_tick = functools.partial(ShadowStrategy._on_exec_tick, stub)
    stub._on_external_order_event = functools.partial(ShadowStrategy._on_external_order_event, stub)
    return stub


def test_bare_construction_wires_no_executor_and_the_forwarders_no_op(tmp_path):
    # The default executor_factory=None leaves every existing construction (and every existing
    # test) untouched: no executor, and the two event forwarders are inert rather than raising.
    strategy = ShadowStrategy(_config(tmp_path))
    assert strategy._executor_factory is None
    assert strategy._executor is None
    strategy.on_quote_tick(object())
    strategy.on_order_event(object())


def test_on_start_builds_the_executor_and_registers_the_exec_tick(tmp_path):
    config = _config(tmp_path)
    built: list[object] = []
    executor = RecordingExecutor()

    def factory(strategy):
        built.append(strategy)
        return executor

    clock = FakeClock()
    stub = _exec_stub(config, clock, executor_factory=factory)
    ShadowStrategy.on_start(stub)

    # The factory is handed the strategy itself -- ProbeExecutor's `client` IS the strategy handle.
    assert built == [stub]
    assert stub._executor is executor
    # The alert chain is untouched by the wiring; the executor tick is a SECOND, repeating timer.
    assert [name for name, _, _ in clock.alerts] == ["shadow-cycle-2026-07-10T12"]
    assert clock.timers == [("exec-probe-tick", timedelta(seconds=5), stub._on_exec_tick)]
    # The tick cadence the executor's own deadlines are written against -- pinned equal rather than
    # restated on faith, since node.py cannot import the constant at module scope.
    from cli.engine.executor import _TICK_SECONDS

    assert node._TICK_SECONDS == _TICK_SECONDS


def test_on_start_subscribes_the_external_order_topic_and_the_handler_reaches_the_filter(tmp_path):
    # The second, filtered order stream (spec 00098 D1): exactly ONE subscription, to exactly the
    # external strategy's order topic, whose handler lands on the executor's disposition filter --
    # never on on_order_event, whose unknown-order trip must keep seeing only the strategy's own
    # orders.
    executor = RecordingExecutor()
    stub = _exec_stub(_config(tmp_path), FakeClock(), executor_factory=lambda strategy: executor)
    ShadowStrategy.on_start(stub)

    assert stub.msgbus.subscriptions == [(node._EXTERNAL_ORDER_TOPIC, stub._on_external_order_event)]
    ((_topic, handler),) = stub.msgbus.subscriptions
    sentinel = object()
    handler(sentinel)
    assert executor.external_events == [sentinel]
    # and nothing leaked onto the own-order path the trip reads.
    assert executor.events == []


def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None


def test_on_start_subscribes_nothing_without_a_factory(tmp_path):
    # The subscription is wired with the executor, not with the strategy: a construction that wires
    # no executor reaches the message bus not at all, so every non-production ShadowStrategy stays
    # the pure timer-arithmetic object it was.
    stub = _exec_stub(_config(tmp_path), FakeClock())
    ShadowStrategy.on_start(stub)
    assert stub.msgbus.subscriptions == []


def test_exec_tick_forwards_the_strategys_own_clock_reading(tmp_path):
    executor = RecordingExecutor()
    stub = _exec_stub(_config(tmp_path), FakeClock(), executor=executor)
    stub._on_exec_tick(None)
    # The strategy's injected clock, never a wall-clock read inside the forwarder.
    assert executor.timers == [B08 + timedelta(minutes=5)]


def test_quote_and_order_event_forwarders_pass_the_object_through(tmp_path):
    executor = RecordingExecutor()
    strategy = ShadowStrategy(_config(tmp_path))
    strategy._executor = executor
    tick, event = object(), object()
    strategy.on_quote_tick(tick)
    strategy.on_order_event(event)
    assert executor.quotes == [tick]
    assert executor.events == [event]


def test_the_external_order_forwarder_passes_the_object_through_and_is_inert_unwired(tmp_path):
    # The fourth forwarder, in the shape of the other three: object through, and a no-op rather than
    # an AttributeError when no executor was wired (the bus can deliver before/without one only in
    # constructions that never subscribe, but the forwarder must not be the thing that finds out).
    strategy = ShadowStrategy(_config(tmp_path))
    strategy._on_external_order_event(object())

    executor = RecordingExecutor()
    strategy._executor = executor
    event = object()
    strategy._on_external_order_event(event)
    assert executor.external_events == [event]
    # The filter is a SEPARATE entry point: nothing arrived on the own-order path the trip reads.
    assert executor.events == []


def test_a_quote_for_another_instrument_does_not_disturb_the_running_intent(tmp_path):
    # The forwarder is instrument-blind by design -- the discrimination is the executor's, and this
    # drives the WHOLE path (strategy.on_quote_tick -> the real factory's ProbeExecutor.on_quote)
    # so a wiring that handed the tick to the wrong place would show up here.
    from nautilus_trader.model.identifiers import InstrumentId

    from cli.engine.executor import _ActiveIntent
    from cli.engine.probeplan import ProbeIntent
    from cli.engine.venuestate import InstrumentConstraints

    config = _config(tmp_path)
    strategy = ShadowStrategy(config)
    strategy._executor = node._probe_executor_factory(config)(strategy)
    now = B08 + timedelta(minutes=5)
    active = _ActiveIntent(
        index=0,
        intent=ProbeIntent(symbol="BTC/EUR", side="buy", action="open", mode="execute", notional_eur=20.0, qty=None, leverage=None),
        raw_intent={},
        instrument_id=InstrumentId.from_str("BTC/EUR.KRAKEN"),
        constraints=InstrumentConstraints(
            symbol="BTC/EUR",
            instrument_id="BTC/EUR.KRAKEN",
            ordermin=0.0001,
            costmin=0.45,
            costmin_quote="EUR",
            lot_step=1e-08,
            tick_size=0.1,
        ),
        phase="resting",
        started_at=now,
        quote_deadline=now + timedelta(seconds=30),
        timebox_at=now + timedelta(minutes=15),
    )
    strategy._executor._active = active

    strategy.on_quote_tick(
        types.SimpleNamespace(instrument_id=InstrumentId.from_str("ETH/EUR.KRAKEN"), bid_price=1.0, ask_price=2.0)
    )
    assert (active.bid, active.ask, active.last_quote_at) == (None, None, None)

    strategy.on_quote_tick(
        types.SimpleNamespace(instrument_id=InstrumentId.from_str("BTC/EUR.KRAKEN"), bid_price=100.0, ask_price=101.0)
    )
    assert (active.bid, active.ask) == (100.0, 101.0)
    assert active.last_quote_at is not None


def test_probe_executor_factory_shape(tmp_path):
    # Constructed, never run -- the way _node_config is pinned. The gate this executor evaluates has
    # to be the one reading the deployed control-file tree, or every submission would consult a gate
    # pointed somewhere else.
    from cli.engine.execgate import exec_dir
    from cli.engine.executor import ProbeExecutor
    from cli.engine.venue import read_system_status

    config = _config(tmp_path, exec_armed=True)
    client = object()
    executor = node._probe_executor_factory(config)(client)
    assert isinstance(executor, ProbeExecutor)
    assert executor._client is client
    assert executor._config is config
    assert executor._gate._armed_in_config is True
    assert executor._gate._dir == exec_dir(config.journal_dir.parent)
    assert executor._gate._venue_reader is read_system_status


# --- the own-strategy order stream (the unknown-order kill trip's scoping) -----------------------


def test_the_strategy_claims_no_external_orders(tmp_path):
    """The precondition the executor's unknown-order kill trip rests on: this strategy is
    subscribed to `events.order.<its own id>` and claims NOTHING beyond it. An `external_order_claims`
    entry would make the venue's reconciliation route the account owner's own hand-placed settling
    fills into on_order_event -- and the trip would latch the kill switch on the probe's sanctioned
    final act."""
    for strategy in (ShadowStrategy(_config(tmp_path)), ShadowStrategy(_config(tmp_path), executor_factory=lambda s: None)):
        assert strategy.external_order_claims == []
        assert strategy.config.external_order_claims is None


# Each banned text mapped to the cli/ paths deliberately allowed to carry it, and HOW MANY times.
# `external_order_claims`: allowed NOWHERE. A claim is what would route the account owner's own
# hand-placed settling fills onto the strategy's OWN order topic and straight into the trip.
# `msgbus`: allowed exactly ONCE, in node.py, for the `events.order.EXTERNAL` subscription (spec
# 00098 D1) -- a SECOND, filtered stream whose handler acts only on rows the engine's ledger vouches
# for. A count rather than a path, because a file-level allowlist admits any further reach inside
# the same file: one more `self.msgbus.subscribe` there, on a wildcard topic, would route EVERY
# strategy's order events into the filter and nothing would say so.
_ORDER_STREAM_WIDENERS = {
    "external_order_claims": {},
    "msgbus": {"cli/engine/node.py": 1},
}


def test_no_module_widens_the_engines_order_event_stream():
    """The structural half of the same property, as a text walk (the D4 pin's shape): nothing under
    cli/ may claim external orders, nor reach past the strategy's own subscription onto the raw
    message bus beyond the one allowlisted occurrence. Text, not imports -- a reference in a comment
    is one a refactor can activate. The allowance is a COUNT, so a second reach inside the
    allowlisted file is an offender like any other; and the walk asserts it found the tree at all,
    since `Path("cli").rglob` off-root yields nothing and would pass everything."""
    offenders = []
    files = sorted(Path("cli").rglob("*.py"))
    assert len(files) > 100, f"the walk found only {len(files)} files -- vacuous"
    for path in files:
        text = path.read_text()
        for name, allowed in _ORDER_STREAM_WIDENERS.items():
            n = text.count(name)
            if n > allowed.get(path.as_posix(), 0):
                offenders.append(f"{path.as_posix()}: {name} x{n}")
    assert offenders == []


def test_the_external_topic_string_matches_the_installed_engines_format():
    """The library boundary, proven with a REAL message bus rather than a mock of our own
    assumption: nautilus reconciles a venue-resting order this process did not submit under
    `StrategyId("EXTERNAL")` and publishes its events on `f"events.order.{strategy_id}"`
    (execution/engine.pyx `_get_order_events_topic`). `_EXTERNAL_ORDER_TOPIC` is that string, and
    the whole feature is silent -- no exception, no log, just an unsubscribed topic -- if it ever
    stops being. This is therefore the tripwire for the pending nautilus bump: a renamed topic or a
    renamed external strategy id fails HERE, not in production."""
    from nautilus_trader.common.component import MessageBus, TestClock
    from nautilus_trader.core.uuid import UUID4
    from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderType
    from nautilus_trader.model.events import OrderFilled
    from nautilus_trader.model.identifiers import (
        AccountId,
        ClientOrderId,
        InstrumentId,
        StrategyId,
        TradeId,
        TraderId,
        VenueOrderId,
    )
    from nautilus_trader.model.objects import Currency, Money, Price, Quantity

    external = StrategyId("EXTERNAL")
    # The library still calls this exact id external -- the predicate reconciliation routes on.
    assert external.is_external()
    assert node._EXTERNAL_ORDER_TOPIC == "events.order.EXTERNAL"

    trader_id = TraderId("SHADOW-001")
    bus = MessageBus(trader_id=trader_id, clock=TestClock())
    received: list[object] = []
    bus.subscribe(topic=node._EXTERNAL_ORDER_TOPIC, handler=received.append)

    eur = Currency.from_str("EUR")
    fill = OrderFilled(
        trader_id=trader_id,
        strategy_id=external,
        instrument_id=InstrumentId.from_str("BTC/EUR.KRAKEN"),
        client_order_id=ClientOrderId("SHADOW-001-0-1"),
        venue_order_id=VenueOrderId("OABCDE-12345-67890"),
        account_id=AccountId("KRAKEN-001"),
        trade_id=TradeId("TFGHIJ-12345-67890"),
        position_id=None,
        order_side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        last_qty=Quantity.from_str("0.00100000"),
        last_px=Price.from_str("30000.0"),
        currency=eur,
        commission=Money(0.012, eur),
        liquidity_side=LiquiditySide.MAKER,
        event_id=UUID4(),
        ts_event=0,
        ts_init=0,
        reconciliation=True,
    )
    # Published through the engine's OWN f-string shape, off the event's own strategy_id -- the
    # derivation under test, not a second copy of our literal.
    bus.publish(topic=f"events.order.{fill.strategy_id}", msg=fill)
    assert received == [fill]


def test_a_really_registered_strategy_subscribes_the_external_topic_the_library_itself_derives(tmp_path):
    """The other half of that boundary. Every other `on_start` test here drives a stub, so
    `self.msgbus` existing at `on_start` is read off the library's source rather than observed: this
    one performs the nautilus registration the suite otherwise never performs and reads the REAL bus
    back. Two properties, both of which a stub cannot carry: our (topic, handler) pair is actually
    installed on the bus, and the topic we build is the one the LIBRARY's own register-time
    subscription derives -- the strategy's own order topic with its id swapped for `EXTERNAL`. A
    changed `events.order.` prefix therefore fails here, where comparing our f-string to a literal
    would pass."""
    from nautilus_trader.cache.cache import Cache
    from nautilus_trader.common.component import MessageBus, TestClock
    from nautilus_trader.model.identifiers import TraderId
    from nautilus_trader.portfolio import Portfolio

    executor = RecordingExecutor()
    strategy = ShadowStrategy(
        _config(tmp_path),
        run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None,
        clock=lambda: B08 + timedelta(minutes=5),
        executor_factory=lambda s: executor,
    )
    trader_id = TraderId("SHADOW-001")
    clock = TestClock()
    bus = MessageBus(trader_id=trader_id, clock=clock)
    cache = Cache()
    strategy.register(trader_id, Portfolio(bus, cache, clock), bus, cache, clock)
    # The registration is what puts `self.msgbus` there: without it on_start raises AttributeError
    # on the subscribe line. (The startup cycle's snapshot logs one contained EngineError -- the
    # Cache holds no instruments -- which is by design and not what this test reads.)
    strategy.on_start()

    subs = bus.subscriptions()
    assert (node._EXTERNAL_ORDER_TOPIC, strategy._on_external_order_event) in [(s.topic, s.handler) for s in subs]
    # The topic taken from the library's OWN subscription rather than restated: `Strategy.register`
    # subscribes `handle_event` to this strategy's order topic, and ours is that topic with the id
    # replaced by the external one.
    own = {s.topic for s in subs if s.handler == strategy.handle_event}
    assert node._EXTERNAL_ORDER_TOPIC in {t.replace(str(strategy.id), "EXTERNAL") for t in own}


# --- build_shadow_node (assembled, never run; node.build() is offline) --------------------------


def test_node_config_mirrors_iter_079_probe_shape(tmp_path):
    config = _node_config(_config(tmp_path, exec_enabled=True))
    assert config.logging.log_level == "INFO"
    assert config.data_clients["KRAKEN"].instrument_provider.load_all is True
    exec_config = config.exec_clients["KRAKEN"]
    assert exec_config.instrument_provider.load_all is True
    assert exec_config.spot_account_type == AccountType.MARGIN
    assert exec_config.margin_balance_asset == "ZEUR"
    # Matched literally against the loaded instrument's `quote_currency.code`. Measured against the
    # live public Kraken spot instrument set (1592 instruments): 546 carry code "ZEUR" and ZERO
    # carry "EUR" -- BTC/EUR.KRAKEN, ETH/EUR.KRAKEN, ADA/EUR.KRAKEN et al all report "ZEUR", since
    # only the instrument ID is normalized, not the quote Currency. So "EUR" would match nothing,
    # as would the adapter's own "USDT" default. Pinned so neither an upstream default change nor
    # a plausible-looking "EUR" correction can silently empty spot position reporting.
    assert exec_config.spot_positions_quote_currency == "ZEUR"


def test_node_config_has_no_exec_client_by_default(tmp_path):
    config = _node_config(_config(tmp_path))
    assert config.exec_clients == {}
    assert list(config.data_clients) == ["KRAKEN"]


# The node is assembled in a CHILD interpreter, and the child never disposes it. Two reasons, both
# about teardown rather than about what is asserted:
#   - TradingNode.dispose() on a never-run node closes the event loop as its LAST act, while the
#     adapter's Rust machinery is still unwinding on its own threads (measurable: the io_uring
#     poller thread the build starts outlives dispose() by ~0.5 s). That race is inside the library,
#     unreachable from here, and when it goes wrong it SIGABRTs the whole pytest process -- 27 green
#     tests and no traceback, because the abort comes off a non-Python thread.
#   - Process exit releases strictly more than dispose() would, and os._exit skips interpreter
#     finalization, so no Rust drop runs while anything else is live. Production never takes this
#     path anyway: a node that was actually run stops its loop instead of closing it.
# A native abort in the child can therefore only fail these two tests, never the suite.
_BUILD_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from cli.config import EngineConfig
from cli.engine import build_shadow_node

root = Path(sys.argv[1])
# TradingNode wants a current event loop and nautilus refuses to create one itself.
asyncio.set_event_loop(asyncio.new_event_loop())
node = build_shadow_node(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=sys.argv[2] == "1")
)
(root / "facts.json").write_text(
    json.dumps(
        {
            "data_clients": [str(c) for c in node.kernel.data_engine.registered_clients],
            "exec_clients": [str(c) for c in node.kernel.exec_engine.registered_clients],
            "strategies": [type(s).__name__ for s in node.trader.strategies()],
            "executor_wired": [s._executor_factory is not None for s in node.trader.strategies()],
            "external_order_claims": [list(s.external_order_claims) for s in node.trader.strategies()],
        }
    )
)
os._exit(0)
"""


def _node_build_facts(tmp_path: Path, *, exec_enabled: bool) -> dict:
    """Assemble the node in a child interpreter and return what it registered. The child gets the
    credentials stripped from its environment, so the build is proven keyless and offline."""
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", _BUILD_PROBE, str(tmp_path), "1" if exec_enabled else "0"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    facts = tmp_path / "facts.json"
    detail = f"exit={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    assert facts.exists(), f"the node build probe produced no result: {detail}"
    assert result.returncode == 0, f"the node build probe did not exit cleanly: {detail}"
    return json.loads(facts.read_text())


def test_build_shadow_node_without_exec_client(tmp_path):
    # node.build() constructs clients without credentials or network (no connect until run()).
    facts = _node_build_facts(tmp_path, exec_enabled=False)
    assert facts["data_clients"] == ["KRAKEN"]
    assert facts["exec_clients"] == []
    assert facts["strategies"] == ["ShadowStrategy"]
    # The assembled node's strategy really carries the executor factory -- the only place the whole
    # tick/quote/order-event chain is proven to be armed in production rather than only in a stub.
    assert facts["executor_wired"] == [True]
    # And it claims no external orders once the trader has registered it with the execution engine.
    assert facts["external_order_claims"] == [[]]


def test_build_shadow_node_with_exec_client_when_enabled(tmp_path):
    assert _node_build_facts(tmp_path, exec_enabled=True)["exec_clients"] == ["KRAKEN"]
