import sys

import pytest

import cli.engine.cycle as cycle


@pytest.fixture(autouse=True)
def _reset_metrics_sink():
    """A `command.run()` test that installs a sink and never clears it leaves a live closure -- an
    `ExecutionGate` on a deleted `tmp_path` -- firing in every later test of the same process, and
    `_update_metrics` logs what it raises instead of propagating, so the leak is silent: live HTTPS
    calls to api.kraken.com out of the unit suite. Clear it after every test, whatever the test did."""
    yield
    cycle.set_metrics_sink(None)


@pytest.fixture(autouse=True)
def _reset_executor_hooks():
    """The same hazard one module over: `command.run()` also installs `cli.engine.executor`'s
    module-level hooks, so a `run()` test leaves a live `_ExecutionMetrics` and an `_ExecGauges.update`
    bound to a dead registry firing inside every later test. Reached through `sys.modules` rather than
    an import so a run that never touches the executor does not pay nautilus-trader's import."""
    yield
    module = sys.modules.get("cli.engine.executor")
    if module is not None:
        module.set_executor_hooks()
