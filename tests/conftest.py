import sys

import pytest

import cli.engine.cycle as cycle


@pytest.fixture(autouse=True)
def _reset_metrics_sink():
    """`cycle._metrics_sink` is module-level global state -- leaking a test's sink into the next
    test (or into an unrelated test file sharing this process) would be a real isolation bug of
    its own. Reset it unconditionally after every test in the whole suite: a `run()` test that
    installs a sink and never resets it leaves a live closure behind -- holding a real
    `ExecutionGate` pointed at a `tmp_path` that no longer exists -- for every later test in the
    same pytest process to fire. `cycle.py`'s own sink guard swallows a raising sink by design, so
    the leak is silent: live HTTPS calls to api.kraken.com from the unit suite, plus `exec-*.json`
    written into directories that were deleted with the test that created them.
    """
    yield
    cycle.set_metrics_sink(None)


@pytest.fixture(autouse=True)
def _reset_executor_hooks():
    """The same hazard one module over: `run()` now installs `cli.engine.executor`'s telemetry hooks
    too, which are module-level globals, so a `run()` test anywhere leaves a live `_ExecutionMetrics`
    (and an `_ExecGauges.update` bound to a dead registry) firing inside every later test in the same
    process -- measured, not hypothetical. Reached through `sys.modules` rather than an import so a
    run that never touches the executor does not pay nautilus-trader's ~1 s import at collection."""
    yield
    module = sys.modules.get("cli.engine.executor")
    if module is not None:
        module.set_executor_hooks()
