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


@pytest.hookimpl(wrapper=True)
def pytest_collection_modifyitems(config, items):
    """A `-k` that matches no test exits 5, "no tests ran", which reads green to anything judging a run by its code
    alone -- and a recorded probe whose selector selects nothing is a verdict nothing earned. This names the
    expression on stderr and changes no exit code: pytest's 5 is still the run's answer, the naming is the addition.

    A wrapper, because both numbers exist only here -- what collection found, and what survived the deselection,
    which a plain hookimpl in this file runs before and a `trylast` one after. Deliberately silent: a run with no
    `-k`, which has no expression to name and where pytest's own line already stands alone; and `--collect-only`,
    where an empty selection is the answer to the question asked."""
    collected = len(items)
    result = yield
    expression = config.option.keyword
    if expression and not items and not config.option.collectonly:
        print(
            f"conftest: NO TEST SELECTED -- `-k '{expression}'` left 0 of {collected} collected, so nothing ran "
            f"and the exit 5 this run ends with is not a pass. Fix the expression, or drop the -k.",
            file=sys.stderr,
        )
    return result
