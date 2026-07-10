"""The node wrapper (spec 00041 SS the node wrapper): pure boundary arithmetic, the
restart-inside-a-passable-window startup rule, the alert chain (schedule-next-first, run_cycle
exceptions contained), and the iter-079-shaped TradingNode assembly. No live node is ever run --
the attended soak is the live smoke; node.build() itself is offline (verified by the build tests,
which construct both exec_enabled shapes without credentials or network).
"""

import asyncio
import functools
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from nautilus_trader.model.enums import AccountType

from cli.config import EngineConfig
from cli.engine import ShadowStrategy, build_shadow_node, most_recent_boundary, next_boundary, startup_action
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
    between scheduling and invocation is directly observable."""

    def schedule_alert(boundary, alert_time):
        events.append(("schedule", boundary, alert_time))

    def run_fn(cycle_ts, *, config):
        events.append(("run", cycle_ts, config))
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
    assert events[1][1:] == (B08, config)


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
    assert events[1][1:] == (B08, config)


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
    """Captures set_time_alert calls -- the strategy's only clock interaction."""

    def __init__(self):
        self.alerts: list[tuple[str, datetime, object]] = []

    def set_time_alert(self, name, alert_time, callback):
        self.alerts.append((name, alert_time, callback))


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

    def run_fn(cycle_ts, *, config):
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


# --- build_shadow_node (assembled, never run; node.build() is offline) --------------------------


def test_node_config_mirrors_iter_079_probe_shape(tmp_path):
    config = _node_config(_config(tmp_path, exec_enabled=True))
    assert config.logging.log_level == "INFO"
    assert config.data_clients["KRAKEN"].instrument_provider.load_all is True
    exec_config = config.exec_clients["KRAKEN"]
    assert exec_config.instrument_provider.load_all is True
    assert exec_config.spot_account_type == AccountType.MARGIN
    assert exec_config.margin_balance_asset == "ZEUR"


def test_node_config_has_no_exec_client_by_default(tmp_path):
    config = _node_config(_config(tmp_path))
    assert config.exec_clients == {}
    assert list(config.data_clients) == ["KRAKEN"]


@pytest.fixture
def node_event_loop():
    # TradingNode wants a current event loop, and nautilus refuses to create one under pytest;
    # the node's dispose() closes it.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    asyncio.set_event_loop(None)
    if not loop.is_closed():
        loop.close()


def test_build_shadow_node_without_exec_client(tmp_path, monkeypatch, node_event_loop):
    # node.build() constructs clients without credentials or network (no connect until run()).
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    node = build_shadow_node(_config(tmp_path))
    try:
        assert [str(c) for c in node.kernel.data_engine.registered_clients] == ["KRAKEN"]
        assert list(node.kernel.exec_engine.registered_clients) == []
        assert [type(s).__name__ for s in node.trader.strategies()] == ["ShadowStrategy"]
    finally:
        node.dispose()


def test_build_shadow_node_with_exec_client_when_enabled(tmp_path, monkeypatch, node_event_loop):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    node = build_shadow_node(_config(tmp_path, exec_enabled=True))
    try:
        assert [str(c) for c in node.kernel.exec_engine.registered_clients] == ["KRAKEN"]
    finally:
        node.dispose()
