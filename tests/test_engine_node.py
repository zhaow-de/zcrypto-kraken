"""The node wrapper (spec 00041 SS the node wrapper): pure boundary arithmetic, the
restart-inside-a-passable-window startup rule, the alert chain (schedule-next-first, run_cycle
exceptions contained), and the production-shape LiveNode assembly. Building a node is offline
(verified by the build tests, which construct both exec_enabled shapes without network); the one
test that RUNS a node is the instrument-arrival test, which needs Kraken's public endpoint and
skips loudly without it.
"""

import ast
import functools
import json
import logging
import os
import re
import signal
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nautilus_trader.adapters.kraken import (
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenExecutionClientFactory,
)
from nautilus_trader.common import LogLevel
from nautilus_trader.model import AccountType

from cli.config import EngineConfig
from cli.engine import ShadowStrategy, most_recent_boundary, next_boundary, node, startup_action
from cli.engine.cycle import run_cycle
from cli.engine.errors import EngineError
from cli.engine.node import _node_builder, on_alert_logic, on_start_logic

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


# --- the venue-visible identity (spec 00100 D8) --------------------------------------------------

# Registration is what fixes the identity the venue sees: `strategy_id` is re-derived there from
# the strategy's config, and the order factory that stamps the `order_id_tag` segment into every
# client order id does not exist before it. So this probe performs the real registration
# `build_shadow_node` performs, `LiveNode.add_strategy`, and reads back the id, the prefix an actual
# order carries, and the id the strategy already held BEFORE registration. The child process is
# deliberate -- a node build in-process would take the pytest session's faulthandler with it.
#
# `others` places a SECOND, tag-less strategy: `before` or `after` this one, or `alone` for none.
# A tag-less strategy is assigned its tag positionally at registration, so it is the construction
# that can contend for this strategy's prefix.
_IDENTITY_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from cli.config import EngineConfig
from cli.engine.node import ShadowStrategy, _node_builder
from nautilus_trader.model import InstrumentId, OrderSide, Price, Quantity
from nautilus_trader.trading import Strategy

root, others = Path(sys.argv[1]), sys.argv[2]
asyncio.set_event_loop(asyncio.new_event_loop())

config = EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
live_node = _node_builder(config).build()
facts = {}
if others == "before":
    live_node.add_strategy(Strategy())
strategy = ShadowStrategy(config)
facts["strategy_id_unregistered"] = str(strategy.strategy_id)
try:
    live_node.add_strategy(strategy)
except Exception as exc:
    facts["refusal"] = f"{type(exc).__name__}: {exc}"
else:
    if others == "after":
        live_node.add_strategy(Strategy())
    order = strategy.order_factory.limit(
        instrument_id=InstrumentId.from_str("BTC/EUR.KRAKEN"),
        order_side=OrderSide.BUY,
        quantity=Quantity.from_str("0.001"),
        price=Price.from_str("30000.0"),
    )
    facts["strategy_id"] = str(strategy.strategy_id)
    facts["client_order_id"] = str(order.client_order_id)
(root / "identity.json").write_text(json.dumps(facts))
os._exit(0)
"""


def _identity_facts(tmp_path: Path, others: str) -> dict:
    result = subprocess.run(
        [sys.executable, "-c", _IDENTITY_PROBE, str(tmp_path), others],
        capture_output=True,
        text=True,
        timeout=120,
    )
    facts = tmp_path / "identity.json"
    assert facts.exists(), f"exit={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    return json.loads(facts.read_text())


@pytest.mark.parametrize(
    ("others", "registers"),
    [
        # Production's own shape: this is the only strategy the node carries.
        pytest.param("alone", True, id="the-only-strategy-registered"),
        # A second strategy behind this one cannot move a prefix already stamped.
        pytest.param("after", True, id="a-tagless-strategy-registered-after"),
        # The dangerous order: registered first, a tag-less strategy takes `000` positionally.
        # Registration then REFUSES this strategy rather than handing it a different prefix.
        pytest.param("before", False, id="a-tagless-strategy-registered-first"),
    ],
)
def test_the_registered_strategys_venue_visible_identity_is_pinned(tmp_path, others, registers):
    """The client-order-id prefix reaches Kraken on every order this engine places, so it is pinned
    against the value the engine holds today rather than derived from `_ORDER_ID_TAG` -- a test that
    read the constant would follow it anywhere.

    Pinned against the EFFECTIVE identity, three ways: the registered `strategy_id`, the prefix an
    order minted through the strategy's own factory actually carries, and the id the strategy holds
    before it is registered at all. The last is a separate property with a separate mechanism --
    `strategy_id` is derived at CONSTRUCTION from the config `__new__` receives, and registration
    re-derives it from the config `__init__` passed. Registration alone would therefore reach `000`
    even from a construction that reads `ShadowStrategy-None`, so without this third read nothing
    holds the construction to the identity it will end up with.

    Parametrised over the registration orders because the tag is what a tag-less strategy contends
    for: whichever order a second strategy arrives in, this one's prefix is `000` or the
    registration fails loudly. It is never quietly something else."""
    facts = _identity_facts(tmp_path, others)
    assert facts["strategy_id_unregistered"] == "ShadowStrategy-000"
    if not registers:
        assert "strategy_id" not in facts, f"the colliding registration was accepted: {facts}"
        assert "order_id_tag" in facts["refusal"] and "000" in facts["refusal"], facts["refusal"]
        return
    assert facts["strategy_id"] == "ShadowStrategy-000"
    # `O-<date>-<time>-<trader instance>-<order_id_tag>-<counter>`: the whole shape, so the tag's
    # position in it is pinned too and a re-segmented id cannot pass by carrying `000` elsewhere.
    assert re.fullmatch(r"O-\d+-\d+-\d+-000-\d+", facts["client_order_id"]), facts["client_order_id"]


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
        self.boundaries: list[datetime] = []

    def on_boundary(self, boundary):
        self.boundaries.append(boundary)

    def on_timer(self, now):
        self.timers.append(now)

    def on_quote(self, tick):
        self.quotes.append(tick)

    def on_order_event(self, event):
        self.events.append(event)

    def on_external_order_event(self, event):
        self.external_events.append(event)


def _exec_stub(config, clock, *, executor_factory=None, executor=None):
    """A ShadowStrategy stand-in driven through the unbound methods (the house pattern of
    test_schedule_alert_sets_state_and_timer): a real instance's `clock` is readonly until the
    nautilus registration this suite never performs."""
    stub = types.SimpleNamespace(
        clock=clock,
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
    strategy.on_quote(object())
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


def test_on_start_registers_no_exec_tick_without_a_factory(tmp_path):
    clock = FakeClock()
    stub = _exec_stub(_config(tmp_path), clock)
    ShadowStrategy.on_start(stub)
    assert clock.timers == []
    assert stub._executor is None


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
    strategy.on_quote(tick)
    strategy.on_order_event(event)
    assert executor.quotes == [tick]
    assert executor.events == [event]


def test_the_external_order_forwarder_passes_the_object_through_and_is_inert_unwired(tmp_path):
    # The fourth forwarder, in the shape of the other three: object through, and a no-op rather than
    # an AttributeError when no executor was wired -- the observer delivers to it regardless of what
    # this strategy was constructed with, and the forwarder must not be the thing that finds out.
    strategy = ShadowStrategy(_config(tmp_path))
    strategy._on_external_order_event(object())

    executor = RecordingExecutor()
    strategy._executor = executor
    event = object()
    strategy._on_external_order_event(event)
    assert executor.external_events == [event]
    # The filter is a SEPARATE entry point: nothing arrived on the own-order path the trip reads.
    assert executor.events == []


# --- the external order observer (spec 00100 D2) ------------------------------------------------


def test_the_observer_carries_the_venues_external_order_identity_and_claims_nothing():
    # `strategy_id` at construction; the registered one is measured against the real assembly by
    # test_the_registered_observers_identity_is_exactly_the_venues_external_order_id below, which is
    # where it counts. `order_id_tag` unset is the load-bearing half: a tag lands in the id and the
    # observer would receive nothing at all.
    observer = node.ExternalOrderObserver(lambda event: None)
    assert str(observer.strategy_id) == "EXTERNAL"
    assert observer.config.order_id_tag is None
    assert str(observer.config.strategy_id) == "EXTERNAL"


def test_the_observer_forwards_every_order_event_to_the_strategys_external_forwarder(tmp_path):
    # The delivery leg inside this process: whatever the observer is handed lands on the executor's
    # disposition filter and NOWHERE else -- never on on_order_event, whose unknown-order trip must
    # keep seeing only the orders this engine submitted.
    executor = RecordingExecutor()
    strategy = ShadowStrategy(_config(tmp_path))
    strategy._executor = executor
    observer = node.ExternalOrderObserver(strategy._on_external_order_event)

    event = object()
    observer.on_order_event(event)
    assert executor.external_events == [event]
    assert executor.events == []


def test_the_observer_drops_its_events_when_the_strategy_wired_no_executor(tmp_path):
    # The property the observer inherits from the forwarder it is given: the filter that scopes
    # these events is the executor's, so a strategy that wired none drops them rather than acting on
    # them unfiltered -- and drops them quietly, since raising here would land in the event loop.
    #
    # Differential, so the drop is the executor guard and not a dead wire: the SAME observer
    # delivers once an executor exists.
    strategy = ShadowStrategy(_config(tmp_path))
    assert strategy._executor is None
    observer = node.ExternalOrderObserver(strategy._on_external_order_event)
    observer.on_order_event(object())

    executor = RecordingExecutor()
    strategy._executor = executor
    delivered = object()
    observer.on_order_event(delivered)
    assert executor.external_events == [delivered]


# Read-only on `Strategy` and therefore deliberately NOT sealed: they submit, cancel and modify
# nothing. `query_account` and `query_order` reach the venue, but only to ask.
_OBSERVER_READ_ONLY_SURFACE = {
    "is_exiting",
    "order_factory",
    "portfolio",
    "query_account",
    "query_order",
    "strategy_id",
}


def _order_mutating_surface() -> set[str]:
    """The library's own order-mutating surface, DERIVED rather than restated: everything a
    `Strategy` has that a `DataActor` -- the order-less actor base -- does not, minus the `on_*`
    handlers (inputs, not powers) and the read-only queries above."""
    from nautilus_trader.common import DataActor
    from nautilus_trader.trading import Strategy

    surface = set(dir(Strategy)) - set(dir(DataActor))
    return {name for name in surface if not name.startswith("on_")} - _OBSERVER_READ_ONLY_SURFACE


def test_every_order_mutating_method_the_library_offers_is_sealed_on_the_observer():
    """The barrier D2 buys the observer's existence with. Registered under the venue's external
    order identity, this strategy's every order-scoping default points AT the account owner's book:
    `cancel_all_orders(strategy_only=True)` scopes to this strategy, whose orders are the
    operator's. So the whole surface raises.

    The set is derived from the installed library, not hand-listed: a hand-listed seal silently
    regains a hole the next time upstream adds a method -- the first draft of this seal listed eight
    and left `cancel_orders`, `modify_orders` and `post_market_exit` live. Derived, that addition is
    a red test naming the method."""
    surface = _order_mutating_surface()
    assert len(surface) >= 12, f"the derivation found only {sorted(surface)} -- the walk is broken"

    unsealed = sorted(name for name in surface if name not in vars(node.ExternalOrderObserver))
    assert not unsealed, (
        f"{unsealed} are order-mutating methods on the library's Strategy that this observer does "
        f"not override -- registered as EXTERNAL, they reach the account owner's own orders"
    )

    observer = node.ExternalOrderObserver(lambda event: None)
    for name in sorted(surface):
        with pytest.raises(EngineError, match=name):
            getattr(observer, name)()


def test_a_quote_for_another_instrument_does_not_disturb_the_running_intent(tmp_path):
    # The forwarder is instrument-blind by design -- the discrimination is the executor's, and this
    # drives the WHOLE path (strategy.on_quote -> the real factory's ProbeExecutor.on_quote)
    # so a wiring that handed the tick to the wrong place would show up here.
    from nautilus_trader.model import InstrumentId

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

    strategy.on_quote(types.SimpleNamespace(instrument_id=InstrumentId.from_str("ETH/EUR.KRAKEN"), bid_price=1.0, ask_price=2.0))
    assert (active.bid, active.ask, active.last_quote_at) == (None, None, None)

    strategy.on_quote(
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


def test_no_strategy_claims_external_orders(tmp_path):
    """The precondition the executor's unknown-order kill trip rests on: this strategy is
    subscribed to `events.order.<its own id>` and claims NOTHING beyond it. An `external_order_claims`
    entry would make the venue's reconciliation route the account owner's own hand-placed settling
    fills into on_order_event -- and the trip would latch the kill switch on the probe's sanctioned
    final act.

    The observer is held to it too: it is registered under the external identity precisely so that
    nothing has to be claimed to observe those orders, and a claim there would drag the account
    owner's orders onto the claiming strategy's own topic just the same.

    A strategy's config is the whole claim surface -- there is no second, derived list to read -- so
    `None` there IS the empty claim, on every construction."""
    strategies = (
        ShadowStrategy(_config(tmp_path)),
        ShadowStrategy(_config(tmp_path), executor_factory=lambda s: None),
        node.ExternalOrderObserver(lambda event: None),
    )
    for strategy in strategies:
        assert strategy.config.external_order_claims is None


# Each banned text mapped to the cli/ paths deliberately allowed to carry it, and HOW MANY times.
# Every entry is allowed NOWHERE, so the values are empty -- the shape stays a map because an
# allowance is exactly the thing that has to be spelled with a count rather than a path.
#
# `external_order_claims`: a claim is what would route the account owner's own hand-placed settling
# fills onto a strategy's OWN order topic and straight into the unknown-order trip.
#
# `msgbus`: nothing under cli/ reaches the raw message bus. The second order stream is a registered
# strategy whose events the library routes by identity, so there is no topic string to subscribe and
# no reason for any module here to hold a bus.
#
# `MessageBus`: constructing one registers it globally and REPLACES the engine's own (spec 00100
# D3). Submitted orders then freeze at INITIALIZED, no event ever fires, and nothing raises -- on
# the live trade path that is an order that never leaves and a kill trip that never runs. It is the
# CONSTRUCTOR alone that does this, so this ban is what the `msgbus` line above cannot express:
# `"MessageBus".count("msgbus")` is 0, and a `MessageBus(...)` in cli/ would pass every other check
# in this repo.
#
# What this walk counts is TEXT, not reaches -- an alias fans out from one occurrence -- so the
# wiring assertions EARLIER in this file, which pin the observer's handler and its identity by exact
# equality, are the other half of this guard rather than a duplicate of it.
_ORDER_STREAM_WIDENERS = {
    "external_order_claims": {},
    "msgbus": {},
    "MessageBus": {},
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


def test_the_observers_identity_is_the_one_the_library_reserves_for_orders_we_did_not_submit():
    """The library boundary the whole second order stream rests on, read off the library rather
    than restated. Nautilus stamps every order this process did not submit with one reserved
    `StrategyId` and routes those orders' events to whatever strategy is registered under it -- so
    the observer's identity has to BE the reserved one, and the feature is silent if it ever stops
    being: no exception, no log, an observer that receives nothing.

    `StrategyId` requires `<name>-<tag>` and refuses every tagless string except the reserved one,
    so the reservation is something the library still states about that exact literal. The value
    tested is the observer's OWN id, not a copy of it: what the production assembly registers is the
    thing under test, and a rename of the reserved identity makes the observer's own construction
    raise here.

    What this cannot reach is the join -- a genuine venue-sourced external order arriving on this
    observer -- which needs live reconciliation and belongs to the arming pass (T0152)."""
    from nautilus_trader.model import StrategyId

    reserved = str(node.ExternalOrderObserver(lambda event: None).strategy_id)
    # No tag, so the only way the library accepts it below is by reserving it.
    assert "-" not in reserved
    assert str(StrategyId(reserved)) == reserved
    with pytest.raises(ValueError, match="did not contain '-'"):
        StrategyId(reserved + "X")


# The observer handed to a REAL running engine. `BacktestEngine` is the only engine a test can run,
# and it produces no venue-sourced external order -- nothing here can originate one, since the seal
# is exactly what stops the observer submitting. So this probe measures the three things a running
# engine can settle, and the child interpreter keeps its engine-wide registrations out of the suite.
_EXTERNAL_DISPATCH_PROBE = """
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
from nautilus_trader.common import LoggerConfig
from nautilus_trader.model import (
    AccountType,
    Currency,
    CurrencyPair,
    InstrumentId,
    Money,
    OmsType,
    OrderSide,
    Price,
    Quantity,
    QuoteTick,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.trading import Strategy, StrategyConfig

import cli.engine.node as node

root = Path(sys.argv[1])
instrument_id = InstrumentId.from_str("BTC/EUR.SIM")
eur, btc = Currency.from_str("EUR"), Currency.from_str("BTC")
instrument = CurrencyPair(
    instrument_id=instrument_id,
    raw_symbol=Symbol("BTC/EUR"),
    base_currency=btc,
    quote_currency=eur,
    price_precision=1,
    size_precision=6,
    price_increment=Price(0.1, 1),
    size_increment=Quantity(0.000001, 6),
    ts_event=0,
    ts_init=0,
    maker_fee=Decimal("0"),
    taker_fee=Decimal("0"),
)


class Submitter(Strategy):
    # An ordinary identity, and the orders whose events the library must route to IT.
    events = []

    def __init__(self):
        super().__init__(StrategyConfig(order_id_tag="777"))
        self._quotes = 0

    def on_start(self):
        self.subscribe_quotes(instrument_id)

    def on_quote(self, quote):
        self._quotes += 1
        if self._quotes == 3:
            # Priced far below the book so it rests: an accepted order is a fuller event chain than
            # a rejected one, and resting needs no fill model.
            self.submit_order(
                self.order_factory.limit(instrument_id, OrderSide.BUY, Quantity.from_str("0.010000"), Price(25000.0, 1))
            )

    def on_order_event(self, event):
        type(self).events.append(type(event).__name__)


observed = []
engine = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("TESTER-001"), logging=LoggerConfig(bypass_logging=True)))
engine.add_venue(
    venue=Venue("SIM"),
    oms_type=OmsType.NETTING,
    account_type=AccountType.CASH,
    starting_balances=[Money(1_000_000, eur), Money(10, btc)],
)
engine.add_instrument(instrument)
t0 = 1_577_836_800_000_000_000
engine.add_data(
    [
        QuoteTick(
            instrument_id=instrument_id,
            bid_price=Price(30000.0 + i, 1),
            ask_price=Price(30001.0 + i, 1),
            bid_size=Quantity.from_str("10.0"),
            ask_size=Quantity.from_str("10.0"),
            ts_event=t0 + i * 1_000_000_000,
            ts_init=t0 + i * 1_000_000_000,
        )
        for i in range(10)
    ]
)

observer = node.ExternalOrderObserver(observed.append)
engine.add_strategy(observer)
engine.add_strategy(Submitter())
engine.run()
(root / "facts.json").write_text(
    json.dumps(
        {
            # Read after add_strategy: registration is what re-derives the id.
            "observer_id_registered": str(observer.strategy_id),
            "submitter_events": Submitter.events,
            "observer_events": [type(event).__name__ for event in observed],
        }
    )
)
engine.dispose()
os._exit(0)
"""


def test_a_really_registered_observer_takes_no_event_the_library_routes_to_another_strategy(tmp_path):
    """The real-registration half of the boundary above, and the only place in this suite where the
    sealed observer meets a running nautilus engine instead of a direct call.

    Three things it settles that no stub can. `add_strategy` accepts this class -- every
    order-mutating method overridden to raise -- and the run completes, so the seal does not cost
    the registration. The library's own dispatch really calls `on_order_event` on a registered
    strategy. And the observer, holding the reserved external identity, receives NONE of the events
    the library routes to the other strategy: that is D2's scope property, measured rather than
    argued, and read as a differential so the empty list is an absence and not a run that never
    happened."""
    result = subprocess.run(
        [sys.executable, "-c", _EXTERNAL_DISPATCH_PROBE, str(tmp_path)], capture_output=True, text=True, timeout=120
    )
    recorded = tmp_path / "facts.json"
    detail = f"exit={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    assert recorded.exists(), f"the external-dispatch probe produced no result: {detail}"
    facts = json.loads(recorded.read_text())

    assert facts["observer_id_registered"] == "EXTERNAL", detail
    assert facts["submitter_events"] == ["OrderInitialized", "OrderSubmitted", "OrderAccepted"], detail
    assert facts["observer_events"] == [], detail


# --- the handler-existence guard (a renamed library handler is invisible to every test above) ----


def test_every_handler_our_strategy_overrides_exists_on_the_library_base_class():
    """The silent-rename guard. A handler the framework no longer dispatches to is not an error in
    Python -- it is a method nobody calls, and a stub-driven suite cannot see the difference. This
    turns the whole class of handler renames into one red test.

    It is deliberately general rather than named after `on_quote_tick`: the next rename will be a
    different handler.
    """
    from nautilus_trader.trading import Strategy

    overridden = {name for name in vars(ShadowStrategy) if name.startswith("on_") and callable(getattr(ShadowStrategy, name, None))}
    assert overridden, "found no handlers to check -- the walk is broken, not the strategy"
    missing = sorted(name for name in overridden if not hasattr(Strategy, name))
    assert not missing, (
        f"{missing} are overridden here but do not exist on the library's Strategy -- the framework "
        f"will never call them, and nothing else in this suite would notice"
    )


# --- build_shadow_node (assembled, never run; node.build() is offline) --------------------------


# The built node exposes no client registry and no config readback, so the assembly is pinned where
# it is decided: on the calls `_node_builder` makes and the config objects it hands over. The
# recorder below stands in for `LiveNodeBuilder`, so `test_every_builder_call_exists_on_the_library`
# checks each recorded name against the real class -- a stub is a contract restatement, and an
# unverified restatement drifts silently.
class RecordingBuilder:
    def __init__(self):
        self.calls = []

    def _record(self, _call, **kwargs):
        self.calls.append((_call, kwargs))
        return self

    def with_logging(self, logging):
        return self._record("with_logging", logging=logging)

    def with_exec_engine_config(self, config):
        return self._record("with_exec_engine_config", config=config)

    def add_data_client(self, name, factory, config):
        return self._record("add_data_client", name=name, factory=factory, config=config)

    def add_exec_client(self, name, factory, config):
        return self._record("add_exec_client", name=name, factory=factory, config=config)

    def named(self, call_name):
        return [kwargs for name, kwargs in self.calls if name == call_name]


class RecordingLiveNode:
    """`LiveNode.builder(...)` only, recorded with the identity arguments it was given."""

    def __init__(self):
        self.builder_kwargs = None
        self.recorder = RecordingBuilder()

    def builder(self, **kwargs):
        self.builder_kwargs = kwargs
        return self.recorder


def _record_assembly(tmp_path, monkeypatch, **overrides) -> RecordingLiveNode:
    live_node = RecordingLiveNode()
    monkeypatch.setattr(node, "LiveNode", live_node)
    _node_builder(_config(tmp_path, **overrides))
    return live_node


def test_the_builder_is_given_the_pinned_trader_identity(tmp_path, monkeypatch):
    from nautilus_trader.common import Environment

    live_node = _record_assembly(tmp_path, monkeypatch)
    assert str(live_node.builder_kwargs["trader_id"]) == node._TRADER_ID
    assert live_node.builder_kwargs["environment"] == Environment.LIVE
    assert live_node.builder_kwargs["name"] == node._NODE_NAME


def test_the_builder_is_given_the_production_client_and_engine_configs(tmp_path, monkeypatch):
    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    recorder = _record_assembly(tmp_path, monkeypatch, exec_enabled=True).recorder

    assert recorder.named("with_logging")[0]["logging"].stdout_level == LogLevel.INFO

    # The two exec-engine knobs the adopted-order path rests on. `filter_unclaimed_external_orders`
    # is the quiet one: flipped, reconciliation returns None for VENUE-tagged unclaimed orders, so
    # the adopted order never enters the cache -- the startup pass neither attaches nor cancels a
    # previous process's resting order, the kill sweep cannot reach it, and nothing logs above
    # WARNING. The stub-cache tests cannot see it (they never run reconciliation), so the pin is
    # the only guard, and it is aimed at a future upstream default flip.
    exec_engine = recorder.named("with_exec_engine_config")[0]["config"]
    assert exec_engine.reconciliation is True
    assert exec_engine.filter_unclaimed_external_orders is False

    data_client = recorder.named("add_data_client")[0]
    assert data_client["name"] == "KRAKEN"
    assert isinstance(data_client["factory"], KrakenDataClientFactory)
    assert isinstance(data_client["config"], KrakenDataClientConfig)

    exec_client = recorder.named("add_exec_client")[0]
    assert exec_client["name"] == "KRAKEN"
    assert isinstance(exec_client["factory"], KrakenExecutionClientFactory)
    exec_config = exec_client["config"]
    # The issuer half must be the venue: the Cache indexes accounts by it, and the venue-state
    # reader looks the account up by Venue("KRAKEN").
    assert str(exec_config.account_id) == "KRAKEN-001"
    assert exec_config.spot_account_type == AccountType.MARGIN
    assert exec_config.margin_balance_asset == "ZEUR"
    # Matched literally against the loaded instrument's `quote_currency.code`. Measured against the
    # live public Kraken spot instrument set (1592 instruments): 546 carry code "ZEUR" and ZERO
    # carry "EUR" -- BTC/EUR.KRAKEN, ETH/EUR.KRAKEN, ADA/EUR.KRAKEN et al all report "ZEUR", since
    # only the instrument ID is normalized, not the quote Currency. So "EUR" would match nothing,
    # as would the adapter's own "USDT" default. Pinned so neither an upstream default change nor
    # a plausible-looking "EUR" correction can silently empty spot position reporting.
    assert exec_config.spot_positions_quote_currency == "ZEUR"
    # D10: submission stays on REST. The library default is True; `_KRAKEN_ERROR_MARKERS` and
    # `_on_rejected`'s three-way verdict in cli/engine/executor.py are derived against REST
    # rejections, so this must be set explicitly rather than inherited.
    assert exec_config.use_ws_trade is False


def test_the_builder_is_given_no_exec_client_by_default(tmp_path, monkeypatch):
    recorder = _record_assembly(tmp_path, monkeypatch).recorder
    assert recorder.named("add_exec_client") == []
    assert [call["name"] for call in recorder.named("add_data_client")] == ["KRAKEN"]


def test_every_builder_call_exists_on_the_library(tmp_path, monkeypatch):
    # The recorder above is a restatement of `LiveNodeBuilder`; this is what keeps it honest. A
    # renamed or removed builder method fails here instead of passing every recorder-backed test
    # and then raising at the first real assembly, in production.
    from nautilus_trader.live import LiveNodeBuilder

    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    recorder = _record_assembly(tmp_path, monkeypatch, exec_enabled=True).recorder
    called = {name for name, _ in recorder.calls}
    assert called, "the recorder saw no builder calls -- it is no longer standing in for anything"
    for name in sorted(called):
        assert hasattr(LiveNodeBuilder, name), f"LiveNodeBuilder.{name} is gone -- node assembly breaks"


# --- the exec credentials (spec 00100 D13) ------------------------------------------------------


def test_the_default_config_builds_a_data_only_node_and_never_reads_the_credentials(tmp_path, monkeypatch):
    # Keyless is what a local run has always been -- the trade key is IP-bound to the engine host.
    # With execution off the environment is not consulted at all, so a host that happens to carry
    # the key still cannot build an executing node by accident.
    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    read = []

    def _tracking_credentials():
        read.append(True)
        return "a-key", "a-secret"

    monkeypatch.setattr(node, "_credentials", _tracking_credentials)
    recorder = _record_assembly(tmp_path, monkeypatch).recorder
    assert recorder.named("add_exec_client") == []
    assert read == []


def test_execution_enabled_with_an_empty_environment_refuses(tmp_path, monkeypatch):
    # Never a placeholder credential: a node that looks armed and is not defers the failure from
    # construction to the first submission, at a live venue.
    monkeypatch.delenv(node._API_KEY_VAR, raising=False)
    monkeypatch.delenv(node._API_SECRET_VAR, raising=False)
    with pytest.raises(EngineError) as excinfo:
        _node_builder(_config(tmp_path, exec_enabled=True))
    message = str(excinfo.value)
    assert node._API_KEY_VAR in message and node._API_SECRET_VAR in message


@pytest.mark.parametrize("present_var", ["_API_KEY_VAR", "_API_SECRET_VAR"])
def test_the_refusal_never_carries_a_credential_VALUE(tmp_path, monkeypatch, present_var):
    # The half-set environment is the case that tempts an implementation into saying which value it
    # DID find. Whichever half is present is a live trade credential, and this message reaches a
    # log, a traceback and the container's stderr.
    secret = "kraken-live-credential-sentinel"
    monkeypatch.delenv(node._API_KEY_VAR, raising=False)
    monkeypatch.delenv(node._API_SECRET_VAR, raising=False)
    monkeypatch.setenv(getattr(node, present_var), secret)
    with pytest.raises(EngineError) as excinfo:
        _node_builder(_config(tmp_path, exec_enabled=True))
    assert secret not in str(excinfo.value)
    assert secret not in repr(excinfo.value)


def test_an_empty_credential_is_treated_as_absent(tmp_path, monkeypatch):
    # An env_file rendered with a blank value is indistinguishable from an unset one at the venue;
    # it must refuse here rather than authenticate as nobody.
    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "")
    with pytest.raises(EngineError):
        _node_builder(_config(tmp_path, exec_enabled=True))


def test_the_exec_client_config_does_not_carry_the_credentials_back_out(tmp_path, monkeypatch, caplog):
    # The credentials go in and are never readable again -- no attribute, no repr, no str. That is
    # what keeps the config object safe to hand to a logger or an exception, and it is a property
    # of the library, so it is measured rather than assumed.
    secret = "kraken-live-credential-sentinel"
    monkeypatch.setenv(node._API_KEY_VAR, secret + "-key")
    monkeypatch.setenv(node._API_SECRET_VAR, secret + "-secret")
    with caplog.at_level(logging.DEBUG):
        recorder = _record_assembly(tmp_path, monkeypatch, exec_enabled=True).recorder
    exec_config = recorder.named("add_exec_client")[0]["config"]
    assert secret not in repr(exec_config)
    assert secret not in str(exec_config)
    assert not [name for name in dir(exec_config) if secret in str(getattr(exec_config, name, ""))]
    # And nothing on the assembly path logged them.
    assert secret not in caplog.text


# The node is assembled in a CHILD interpreter, one node per child. `zcrypto engine run` builds one
# node per process, so a suite that built several in its own would be testing a shape production
# never runs -- and a node holds Rust-side state whose teardown order is not ours to reason about.
# A child gives each build a fresh interpreter and lets process exit release everything at once,
# which releases strictly more than a dispose() would.
# A native abort in the child can therefore only fail these two tests, never the suite. It also
# arrives mute unless faulthandler is re-armed after the build -- see the abort-diagnosability test
# below, which is what makes such an abort readable rather than a bare exit 134.
_BUILD_PROBE = """
import asyncio, json, os, sys
from pathlib import Path

from cli.config import EngineConfig
import cli.engine.node as node_module

root = Path(sys.argv[1])
# Nautilus wants a current event loop and refuses to create one itself.
asyncio.set_event_loop(asyncio.new_event_loop())

# The built node exposes no strategy registry, so the strategy is captured on its way in -- these
# are the real objects `build_shadow_node` assembled, not restatements of them.
built = []
observers = []
observer_ids_at_construction = []
original_strategy = node_module.ShadowStrategy
original_observer = node_module.ExternalOrderObserver


def capturing(*args, **kwargs):
    strategy = original_strategy(*args, **kwargs)
    built.append(strategy)
    return strategy


def capturing_observer(*args, **kwargs):
    observer = original_observer(*args, **kwargs)
    observers.append(observer)
    observer_ids_at_construction.append(str(observer.strategy_id))
    return observer


node_module.ShadowStrategy = capturing
node_module.ExternalOrderObserver = capturing_observer
node = node_module.build_shadow_node(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=sys.argv[2] == "1")
)
(root / "facts.json").write_text(
    json.dumps(
        {
            "trader_id": str(node.trader_id),
            "environment": str(node.environment),
            "is_running": node.is_running,
            "strategies": [type(s).__name__ for s in built],
            "executor_wired": [s._executor_factory is not None for s in built],
            "observers": [type(o).__name__ for o in observers],
            # Read AFTER build_shadow_node returned, so after add_strategy: registration is what
            # re-derives the id, and an id read at construction proves nothing about the one the
            # library will route events to.
            "observer_ids_registered": [str(o.strategy_id) for o in observers],
            "observer_ids_at_construction": observer_ids_at_construction,
            "strategy_ids_registered": [str(s.strategy_id) for s in built],
            # The handler each observer holds, identified: bound-method equality is same function
            # AND same instance, so this is the executor-wired strategy's own forwarder or nothing.
            "observer_handler_is_the_strategys_forwarder": [
                o._handler == s._on_external_order_event for o, s in zip(observers, built)
            ],
        }
    )
)
os._exit(0)
"""


def _run_build_probe(tmp_path: Path, *, exec_enabled: bool, credentials: tuple[str, str] | None = None):
    """Assemble the node in a child interpreter. The child's environment carries exactly the
    credentials this call names and nothing inherited, so what the build does with them is the
    only thing under test."""
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    if credentials is not None:
        env["KRAKEN_SPOT_API_KEY"], env["KRAKEN_SPOT_API_SECRET"] = credentials
    return subprocess.run(
        [sys.executable, "-c", _BUILD_PROBE, str(tmp_path), "1" if exec_enabled else "0"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )


def _node_build_facts(tmp_path: Path, **kwargs) -> dict:
    result = _run_build_probe(tmp_path, **kwargs)
    facts = tmp_path / "facts.json"
    detail = f"exit={result.returncode}\n--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    assert facts.exists(), f"the node build probe produced no result: {detail}"
    assert result.returncode == 0, f"the node build probe did not exit cleanly: {detail}"
    return json.loads(facts.read_text())


def test_build_shadow_node_without_exec_client(tmp_path):
    # Building constructs clients without credentials or network (no connect until run()).
    facts = _node_build_facts(tmp_path, exec_enabled=False)
    assert facts["trader_id"] == node._TRADER_ID
    assert facts["is_running"] is False
    assert facts["strategies"] == ["ShadowStrategy"]
    # The assembled node's strategy really carries the executor factory -- the only place the whole
    # tick/quote/order-event chain is proven to be armed in production rather than only in a stub.
    assert facts["executor_wired"] == [True]


def test_the_registered_observers_identity_is_exactly_the_venues_external_order_id(tmp_path):
    """The single fact the whole second order stream rests on, measured through the real
    registration rather than at construction (spec 00100 D2).

    Nautilus adopts an order this process did not submit under `StrategyId("EXTERNAL")` and routes
    its events to the strategy registered under that exact id. An `order_id_tag` on the observer's
    config would make the registered id `EXTERNAL-<tag>` -- measured -- and the observer would then
    receive NOTHING, with no exception, no log and no other failing test in this suite. So the id is
    read back off the object the production assembly actually registered.

    The handler is pinned in the same breath: it is the forwarder of the strategy carrying the
    executor factory, which is what keeps this stream wired WITH the executor whose disposition
    filter scopes it."""
    facts = _node_build_facts(tmp_path, exec_enabled=False)
    assert facts["observers"] == ["ExternalOrderObserver"]
    assert facts["observer_ids_registered"] == ["EXTERNAL"]
    # Registration re-derives the id from the config, so a construction reading something else would
    # still register correctly -- but then `strategy_id` and the config would disagree for the whole
    # pre-registration window. Both ends pinned, as they are for the main strategy.
    assert facts["observer_ids_at_construction"] == ["EXTERNAL"]
    # The main strategy's own venue-visible identity is untouched by the second registration.
    assert facts["strategy_ids_registered"] == ["ShadowStrategy-000"]
    assert facts["observer_handler_is_the_strategys_forwarder"] == [True]


def test_build_shadow_node_with_exec_client_when_enabled(tmp_path):
    # The real builder accepts the exec-client leg of the chain; the recorder-backed tests above
    # pin what that leg is handed.
    facts = _node_build_facts(tmp_path, exec_enabled=True, credentials=("a-key", "a-secret"))
    assert facts["strategies"] == ["ShadowStrategy"]


def test_build_shadow_node_refuses_execution_with_an_empty_environment(tmp_path):
    # D13's refusal against the real assembly, not only against the recorder.
    result = _run_build_probe(tmp_path, exec_enabled=True)
    assert result.returncode != 0, f"the build should have refused; stdout={result.stdout!r}"
    assert "KRAKEN_SPOT_API_KEY" in result.stderr and "KRAKEN_SPOT_API_SECRET" in result.stderr
    assert not (tmp_path / "facts.json").exists()


def test_a_real_build_never_prints_the_credentials(tmp_path):
    # The whole assembly, library included: nothing the build writes to stdout or stderr carries a
    # credential value. The library's own logger opens at INFO here, which is what the engine runs.
    secret = "kraken-live-credential-sentinel"
    result = _run_build_probe(tmp_path, exec_enabled=True, credentials=(secret + "-key", secret + "-secret"))
    assert result.returncode == 0, f"exit={result.returncode} stderr={result.stderr[-2000:]}"
    assert secret not in result.stdout
    assert secret not in result.stderr


# --- the twelve instruments reach the Cache before the trader starts (spec 00100 D5) ------------

# Nothing in the node configuration selects instruments: the Kraken data client loads the venue's
# whole spot universe itself, during the connect the kernel awaits before it starts the trader. So
# by the time a strategy's on_start runs -- which is where a restart inside a passable window runs
# a boundary's cycle, the earliest venue-state read there is -- the Cache already holds them.
# Measured, and this is the test that keeps it true: `venue_state_from_cache` raises when any of
# INSTRUMENT_IDS is absent, and that raise degrades the snapshot to None rather than failing loudly,
# so a universe that quietly stopped covering a leg would cost venue truth on every cycle with
# nothing red anywhere.
#
# It RUNS a node against Kraken's public endpoint, so it is the one test here that needs the
# network. It is opt-in: without ZCRYPTO_LIVE_VENUE_TESTS=1 it skips regardless of network, and
# with the flag set an unreachable endpoint FAILS rather than skips.
_INSTRUMENT_ARRIVAL_PROBE = """
import json, os, sys, threading, time
from pathlib import Path

from cli.config import EngineConfig
from cli.engine.instruments import INSTRUMENT_IDS
from cli.engine.node import _node_builder
from nautilus_trader.model import InstrumentId
from nautilus_trader.trading import Strategy, StrategyConfig

root = Path(sys.argv[1])
seen = {}


class ArrivalProbe(Strategy):
    def on_start(self):
        seen["total"] = len(self.cache.instruments())
        seen["present"] = sorted(
            symbol
            for symbol, instrument_id in INSTRUMENT_IDS.items()
            if self.cache.instrument(InstrumentId.from_str(instrument_id)) is not None
        )


node = _node_builder(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
).build()
node.add_strategy(ArrivalProbe(config=StrategyConfig()))


def watcher():
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline and not seen:
        time.sleep(0.2)
    (root / "arrival.json").write_text(json.dumps(seen))
    os._exit(0)


threading.Thread(target=watcher, daemon=True).start()
node.run()
"""


def _kraken_public_reachable() -> bool:
    import urllib.request

    try:
        with urllib.request.urlopen("https://api.kraken.com/0/public/Time", timeout=10) as response:
            return response.status == 200
    except Exception:
        return False


def test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts(tmp_path):
    from cli.engine.instruments import INSTRUMENT_IDS

    # Opt-in, not reachability-gated: CI has network, so a reachability gate would run this against a
    # live venue on every PR (a flake source), and would skip silently and permanently if Kraken ever
    # blocked the runner -- an outage indistinguishable from coverage. Set ZCRYPTO_LIVE_VENUE_TESTS=1
    # to run it; the closeout runs it deliberately.
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    if not _kraken_public_reachable():
        pytest.fail("ZCRYPTO_LIVE_VENUE_TESTS=1 was set but Kraken's public endpoint is unreachable")
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", _INSTRUMENT_ARRIVAL_PROBE, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    arrival = tmp_path / "arrival.json"
    detail = f"exit={result.returncode}\n--- stderr ---\n{result.stderr[-4000:]}"
    assert arrival.exists(), f"the instrument-arrival probe produced no result: {detail}"
    facts = json.loads(arrival.read_text())
    assert facts, f"on_start never ran -- the node did not reach a started trader: {detail}"
    missing = sorted(set(INSTRUMENT_IDS) - set(facts["present"]))
    assert not missing, (
        f"{missing} were absent from the Cache when the strategy started, out of {facts['total']} "
        f"instruments loaded -- every cycle's venue-state read would degrade to None"
    )


# --- what the supervision watchdog reads (spec 00042) -------------------------------------------


def test_the_node_start_timeouts_are_the_budget_the_assembled_node_applies():
    """The supervision watchdog waits these two out before it calls a start failed, and nothing else
    bounds how long a legitimate connect-and-reconcile may take. Fired short, it force-exits an
    engine that is still starting normally -- a crash loop against a healthy node -- so a change in
    either value has to surface here rather than silently shortening the wait."""
    assert node.node_start_timeouts() == (60.0, 30.0)


# Why `_start_watchdog` takes `node.handle()` on the thread that built the node and its timer
# callback touches nothing else. pyo3 marks `LiveNode` unsendable, and the assertion that catches a
# cross-thread read is a panic that ABORTS the process: SIGABRT, no Python exception, nothing an
# `except` can intercept and nothing logged. Both halves are measured -- the node's abort and the
# handle's normal answer -- because guessing either way costs the engine.
_UNSENDABLE_PROBE = """
import os, sys, threading

from nautilus_trader.common import Environment, LogLevel
from nautilus_trader.config import LoggerConfig
from nautilus_trader.live import LiveNode, NodeState
from nautilus_trader.model import TraderId

reach = sys.argv[1]
built = (
    LiveNode.builder(name="probe", trader_id=TraderId("PROBE-001"), environment=Environment.LIVE)
    .with_logging(LoggerConfig(stdout_level=LogLevel.ERROR))
    .build()
)
handle = built.handle()


def off_thread():
    if reach == "node":
        print("read", built.is_running, flush=True)
    else:
        print("read", handle.state is NodeState.RUNNING, flush=True)


thread = threading.Thread(target=off_thread)
thread.start()
thread.join()
os._exit(0)
"""


@pytest.mark.parametrize(
    ("reach", "survives"),
    [
        pytest.param("node", False, id="reading-the-node-off-thread-aborts-the-process"),
        pytest.param("handle", True, id="reading-its-handle-off-thread-answers-normally"),
    ],
)
def test_the_live_node_is_unsendable_and_only_its_handle_may_be_read_off_thread(reach, survives):
    result = subprocess.run([sys.executable, "-c", _UNSENDABLE_PROBE, reach], capture_output=True, text=True, timeout=120)
    detail = f"exit={result.returncode}\n--- stdout ---\n{result.stdout[-2000:]}\n--- stderr ---\n{result.stderr[-2000:]}"

    if survives:
        # os._exit(0) ends the child, so a nonzero code here can only be the abort this arm denies.
        assert result.returncode == 0, detail
        assert "read False" in result.stdout, detail  # an unstarted node: answered, and not RUNNING
    else:
        assert result.returncode == -signal.SIGABRT, detail
        assert "unsendable" in result.stderr, detail
        assert "read" not in result.stdout, detail  # the read never came back with a value at all


# The property that makes `NodeState.RUNNING` a health read rather than a liveness one: a node is
# RUNNING only once every client has connected AND startup reconciliation has completed. Both of
# those phases read STARTING, so the read cannot come true while the node is still starting -- and a
# start watchdog whose read comes true early is defeated entirely. Measured against Kraken's public
# endpoint: a clientless node crosses the connect phase too fast to prove anything about it. Opt-in
# on the same flag as the instrument-arrival probe, and for the same reasons.
_START_SEQUENCE_PROBE = """
import json, os, sys, threading, time
from pathlib import Path

from cli.config import EngineConfig
from cli.engine.node import _node_builder

root = Path(sys.argv[1])
built = _node_builder(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
).build()
handle = built.handle()
transitions = []


def watcher():
    started = time.monotonic()
    seen = None
    while time.monotonic() - started < 90:
        state = str(handle.state).rsplit(".", 1)[-1]
        if state != seen:
            transitions.append([round(time.monotonic() - started, 4), state])
            seen = state
        if state == "RUNNING":
            break
        time.sleep(0.002)
    (root / "start-sequence.json").write_text(json.dumps(transitions))
    os._exit(0)


threading.Thread(target=watcher, daemon=True).start()
built.run()
"""


def test_a_node_reaches_running_only_after_its_clients_connect_and_it_reconciles(tmp_path):
    # Opt-in for the same reasons as the instrument-arrival probe above: CI has network, so a
    # reachability gate would run this against a live venue on every PR and would skip silently and
    # permanently if Kraken ever blocked the runner.
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    if not _kraken_public_reachable():
        pytest.fail("ZCRYPTO_LIVE_VENUE_TESTS=1 was set but Kraken's public endpoint is unreachable")
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", _START_SEQUENCE_PROBE, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    recorded = tmp_path / "start-sequence.json"
    detail = f"exit={result.returncode}\n--- stderr ---\n{result.stderr[-4000:]}"
    assert recorded.exists(), f"the start-sequence probe produced no result: {detail}"
    transitions = json.loads(recorded.read_text())

    assert [state for _, state in transitions] == ["IDLE", "STARTING", "RUNNING"], f"{transitions} {detail}"
    # STARTING has to SPAN the connect, not flicker past it: the watchdog's whole health read rests
    # on the connect-and-reconcile window being reportable as something other than RUNNING.
    (_, _), (entered_starting, _), (entered_running, _) = transitions
    assert entered_running - entered_starting >= 0.2, f"{transitions} {detail}"
    assert "All engine clients connected" in result.stdout, detail
    assert "Startup reconciliation completed" in result.stdout, detail


# --- abort diagnosability (T0115) ---------------------------------------------------------------

# A native abort prints a stack only while faulthandler is armed, and nothing sets
# `PYTHONFAULTHANDLER` anywhere in the deployed engine -- so the arming is `cli/engine/command.py`'s
# own `faulthandler.disable(); faulthandler.enable(file=2)` after the node is built, and the
# parameters below are the measurement that justifies it. This is the class of death T0115 spent a
# month on with no stack to read, and the one an unsendable-node attribute read off the building
# thread takes. Asserting on `signal.getsignal(SIGABRT)` instead would prove NOTHING -- it reads
# identical on both sides, because faulthandler installs its handler below CPython's cache of
# Python-level handlers.
_ABORT_PROBE = """
import faulthandler, os, sys

pre_armed, build, mode = sys.argv[1] == "1", sys.argv[2] == "1", sys.argv[3]
if pre_armed:
    faulthandler.enable()
if build:
    import asyncio, tempfile
    from pathlib import Path

    from cli.config import EngineConfig
    from cli.engine import build_shadow_node

    asyncio.set_event_loop(asyncio.new_event_loop())
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        build_shadow_node(
            EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
        )
if mode == "rearm":
    faulthandler.disable()
    faulthandler.enable()
os.abort()
"""


@pytest.mark.parametrize(
    ("args", "dumps"),
    [
        # The true positive: faulthandler armed, no node in the picture, and the dump must appear.
        # Without this arm, the silent result below could be a probe that never armed at all.
        pytest.param(("1", "0", "none"), True, id="an-armed-faulthandler-dumps"),
        # The same arming carried THROUGH a node build, which is where the arming can be taken away:
        # a build that registers SIGABRT with asyncio would install CPython's own no-op C handler
        # over faulthandler's, and every abort after it would die with empty stderr. This arm is that
        # tripwire, and its differential against the one above is the build itself.
        pytest.param(("1", "1", "none"), True, id="a-node-build-leaves-an-armed-faulthandler-armed"),
        # The engine's own starting point -- nothing arms faulthandler for it: exit 134 and silence.
        pytest.param(("0", "1", "none"), False, id="engine-run-without-the-re-arm-is-mute"),
        # And the shape `cli/engine/command.py` runs, which is what buys the stack back.
        pytest.param(("0", "1", "rearm"), True, id="engine-run-with-the-re-arm-dumps"),
    ],
)
def test_a_native_abort_after_a_node_build_is_readable_only_where_faulthandler_is_armed(args, dumps):
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run([sys.executable, "-c", _ABORT_PROBE, *args], capture_output=True, timeout=120, env=env)

    # Every arm must actually reach os.abort(); a child that died some other way tested nothing.
    assert result.returncode == -signal.SIGABRT, f"exit={result.returncode} stderr={result.stderr[:2000]!r}"
    assert (b"Fatal Python error: Aborted" in result.stderr) is dumps, f"stderr={result.stderr[:2000]!r}"
    if not dumps:
        # The symptom exactly as production and CI showed it: a signal death with an empty stderr.
        assert result.stderr == b"", f"expected a silent abort, got stderr={result.stderr[:2000]!r}"


def test_the_cycle_alert_hands_the_executor_the_boundary_it_fired_for(tmp_path):
    """`on_alert_logic`'s FIRST act is schedule_alert, which overwrites `_next_cycle_ts` with the
    FOLLOWING boundary -- so the value the executor is given has to be read before that call, not
    after it. Read after, the weekly tracking trip would score its week off a boundary the cycle
    behind this alert never ran.

    Order matters too: the executor is told AFTER the cycle, so the boundary it reads has already
    journaled its record."""
    executor = RecordingExecutor()
    stub = _exec_stub(_config(tmp_path), FakeClock(), executor=executor)
    stub._next_cycle_ts = B12

    stub._on_cycle_alert(None)

    assert executor.boundaries == [B12]
    assert stub._next_cycle_ts == B12 + timedelta(hours=4)  # the chain moved on, as it must


def test_the_executor_is_told_the_boundary_even_when_the_alert_logic_raises(tmp_path):
    """The call sits in a `finally`: a boundary whose alert chain broke is still a boundary the
    engine lived through, and the trip's whole point is to fire when the ordinary path is not
    working. The original exception must survive unchanged -- `on_boundary` carries its own total
    catch, so nothing from a measurement can replace it."""
    executor = RecordingExecutor()
    stub = _exec_stub(_config(tmp_path), FakeClock(), executor=executor)
    stub._next_cycle_ts = B12

    def boom(boundary, alert_time):
        raise RuntimeError("the alert chain broke")

    stub._schedule_alert = boom
    with pytest.raises(RuntimeError, match="the alert chain broke"):
        stub._on_cycle_alert(None)

    assert executor.boundaries == [B12]


def test_a_strategy_with_no_executor_still_takes_the_alert(tmp_path):
    """The default construction wires no executor at all, and every forwarder stays inert -- the
    alert chain is the engine's research obligation and must not depend on one existing."""
    events: list = []
    schedule_alert, run_fn = _recorders(events)
    strategy = ShadowStrategy(_config(tmp_path), run_cycle_fn=run_fn, clock=lambda: B08 + timedelta(minutes=5))
    strategy._schedule_alert = schedule_alert
    strategy._next_cycle_ts = B12

    strategy._on_cycle_alert(None)

    assert [e[0] for e in events] == ["schedule", "run"]


# --- the assembly recorders and the clock stub, checked against the library ----------------------
#
# tests/test_engine_stub_fidelity.py classifies every test double in the engine suite and names the
# guards below; the reasoning that makes them worth having lives there.


# What each recorder carries for the harness's own sake, modelling nothing on the real type: the
# call log and the readback helpers. Listed one by one on purpose -- a blanket "underscore-prefixed
# names are plumbing" rule would exempt exactly the shape that has slipped through this suite once.
_BUILDER_PLUMBING = frozenset({"calls", "_record", "named"})
_LIVE_NODE_PLUMBING = frozenset({"builder_kwargs", "recorder"})
_CLOCK_PLUMBING = frozenset({"alerts", "timers"})


def test_no_stub_in_this_file_offers_a_name_its_real_library_type_lacks():
    """`test_every_builder_call_exists_on_the_library` covers the calls production MAKES; this
    covers the direction nothing else does. A recorder missing a method production calls raises the
    first time a test runs it. A recorder OFFERING a method the real type lacks fails NOTHING --
    every assembly test believes it, and the first real `build()` is where it comes back wrong.

    `RecordingLiveNode` is the half the builder-call test never reaches at all: it stands in for
    `LiveNode` itself, and only `builder` is read off it."""
    from nautilus_trader.common import Clock
    from nautilus_trader.live import LiveNode, LiveNodeBuilder

    live_node = RecordingLiveNode()
    for label, obj, real, plumbing in (
        ("RecordingBuilder", live_node.recorder, LiveNodeBuilder, _BUILDER_PLUMBING),
        ("RecordingLiveNode", live_node, LiveNode, _LIVE_NODE_PLUMBING),
        ("FakeClock", FakeClock(), Clock, _CLOCK_PLUMBING),
    ):
        offered = {name for name in dir(obj) if not name.startswith("__")} - plumbing
        assert offered, f"{label} offers nothing outside its plumbing list -- the check is vacuous"
        stale = sorted(name for name in plumbing if hasattr(real, name))
        assert stale == [], f"{label}'s plumbing list exempts {stale}, which {real.__name__} DOES carry -- check them instead"
        extra = sorted(name for name in offered if not hasattr(real, name))
        assert extra == [], f"{label} offers {extra}, which the real {real.__name__} does not carry"


def test_the_builder_arguments_the_assembly_passes_bind_against_the_real_live_node(tmp_path, monkeypatch):
    """`RecordingLiveNode.builder(**kwargs)` agrees with every keyword, including one the real
    `LiveNode.builder` would reject -- so the identity pin above it can pass against arguments no
    real assembly would accept. Binding the recorded call against the REAL signature is what makes
    the keyword names checkable at all."""
    import inspect

    from nautilus_trader.live import LiveNode

    monkeypatch.setenv(node._API_KEY_VAR, "a-key")
    monkeypatch.setenv(node._API_SECRET_VAR, "a-secret")
    recorded = _record_assembly(tmp_path, monkeypatch, exec_enabled=True).builder_kwargs
    assert recorded, "the recorder saw no builder call -- it is no longer standing in for anything"
    # Placeholders, not the recorded values: `bind` checks arity and keyword names, never types.
    inspect.signature(LiveNode.builder).bind(**dict.fromkeys(recorded))


def _clock_calls_the_strategy_makes() -> list[tuple[str, int, set[str]]]:
    """(method, positional count, keyword names) for every `self.clock.<method>(...)` call in the
    node wrapper, read off production's own source. Derived rather than listed: `FakeClock` spells
    its own parameters, so nothing else can tell an argument the real Clock takes in that position
    from one it does not."""
    tree = ast.parse(Path(node.__file__).read_text())
    calls = []
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and isinstance(n.func.value, ast.Attribute)
            and n.func.value.attr == "clock"
        ):
            calls.append((n.func.attr, len(n.args), {kw.arg for kw in n.keywords if kw.arg is not None}))
    return calls


def test_every_clock_call_the_strategy_makes_lands_on_the_same_parameters_as_the_real_clock():
    """`FakeClock` restates two `Clock` methods with its OWN parameter order: its third positional is
    `callback`, where the real `set_timer`'s is `start_time`. Arity alone cannot see that -- three
    positional arguments bind cleanly against both -- so production's call is bound against BOTH
    signatures and the parameters it LANDS ON are compared. A call that lands on `callback` here and
    `start_time` on a live node schedules no executor tick at all, with every test above green."""
    import inspect

    from nautilus_trader.common import Clock

    calls = _clock_calls_the_strategy_makes()
    assert len(calls) >= 2, f"the walk found only {calls} -- vacuous"
    for method, positional, names in calls:
        assert hasattr(Clock, method), f"the strategy calls clock.{method}, which the real Clock does not carry"
        assert hasattr(FakeClock, method), f"FakeClock does not restate clock.{method} at all"
        # Placeholders, not the real arguments: `bind` reports which parameter each lands on, never types.
        bound = [
            set(inspect.signature(getattr(cls, method)).bind(None, *[None] * positional, **dict.fromkeys(names)).arguments)
            for cls in (Clock, FakeClock)
        ]
        assert bound[0] == bound[1], (
            f"clock.{method}(...) lands on {sorted(bound[0])} on the real Clock and {sorted(bound[1])} on FakeClock"
        )
