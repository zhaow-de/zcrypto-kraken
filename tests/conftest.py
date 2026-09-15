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
    alone -- and a recorded probe whose selector selects nothing is a verdict nothing earned.

    A wrapper, because both numbers exist only here -- what collection found, and what survived the deselection,
    which a plain hookimpl in this file runs before and a `trylast` one after. The line blames none of the selectors
    it names, because the two numbers do not say what emptied the run. Deliberately silent: a run with no `-k`,
    which has no expression to name and where pytest's own line already stands alone; `--collect-only`, where an
    empty selection is the answer to the question asked; and a run that collected nothing at all, where there was
    nothing to select and the run's own answer -- an ERRORS block, or an empty path -- already stands."""
    collected = len(items)
    result = yield
    expression = config.option.keyword
    if expression and collected and not items and not config.option.collectonly:
        given = [f"-k '{expression}'"]
        if config.option.markexpr:
            given.append(f"-m '{config.option.markexpr}'")
        for prefix in config.option.deselect or []:
            given.append(f"--deselect '{prefix}'")
        print(
            f"conftest: NO TEST SELECTED -- the selection left 0 of {collected} collected, so nothing ran "
            f"and this run's exit code is not a pass. Selectors this hook reads: {', '.join(given)}.",
            file=sys.stderr,
        )
    return result
