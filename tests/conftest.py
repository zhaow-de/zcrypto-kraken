import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

# This process's temporary files, and a child's that inherits TMPDIR, go under the checkout's gitignored `.tmp/`,
# not the inode-bounded tmpfs; set before the first `tmp_path`. The ceiling keeps them outside any repository for git.
TMP_ROOT = Path(__file__).resolve().parents[1] / ".tmp"
TMP_ROOT.mkdir(exist_ok=True)
tempfile.tempdir = str(TMP_ROOT)
os.environ["TMPDIR"] = str(TMP_ROOT)
os.environ["GIT_CEILING_DIRECTORIES"] = str(TMP_ROOT)

import cli.engine.cycle as cycle

SLOW_CASES = Path(__file__).resolve().parent / "slow-cases.txt"
_SLOW_DESELECTED = pytest.StashKey[int]()


def _slow_ledger() -> Path | None:
    """Where this branch's passed slow cases are recorded; None where every slow case runs and none is recorded."""
    if "CI" in os.environ or "GITHUB_ACTIONS" in os.environ or os.environ.get("ZCRYPTO_RERUN_SLOW") == "1":
        return None

    def git(*args: str) -> str:
        return subprocess.run(["git", "-C", str(TMP_ROOT.parent), *args], capture_output=True, text=True).stdout.strip()

    branch = git("branch", "--show-current")
    if branch in ("develop", "main"):
        return None
    if not branch:
        sha = git("rev-parse", "--short", "HEAD")
        return TMP_ROOT / "slow-passed" / f"detached-{sha}.txt" if sha else None
    return TMP_ROOT / "slow-passed" / f"{branch}.txt"


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


@pytest.fixture(autouse=True)
def _restore_zcrypto_logger():
    """`cli.logging.config.configure`, which the app's callback runs on every `CliRunner` invoke, gives the `zcrypto`
    logger a handler of its own -- stdout without `-l`, the invoke's captured stream -- and turns `propagate` off, and
    nothing undoes either: a later test's record then writes to a closed stream, and `caplog` never sees it. Put back
    what the test found."""
    logger = logging.getLogger("zcrypto")
    handlers, level, propagate = list(logger.handlers), logger.level, logger.propagate
    yield
    for handler in logger.handlers:
        if handler not in handlers:
            handler.close()
    logger.handlers[:] = handlers
    logger.setLevel(level)
    logger.propagate = propagate


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
    # `slow` is a case's mark, named only in the list beside this file; set before the yield, so `-m` deselects on it.
    # A scratch tree that copies this file alone (tests/test_empty_k_guard.py) has no list, and nothing there is slow.
    lines = SLOW_CASES.read_text().splitlines() if SLOW_CASES.is_file() else []
    listed = {line.strip() for line in lines if line.strip() and not line.startswith("#")}
    slow = [item for item in items if item.nodeid in listed]
    for item in slow:
        item.add_marker(pytest.mark.slow)
    collected = len(items)
    ledger = _slow_ledger() if slow else None
    if ledger is not None and ledger.is_file():
        passed = set(ledger.read_text().splitlines())
        done = {item.nodeid for item in slow if item.nodeid in passed}
        if done:
            config.hook.pytest_deselected(items=[item for item in items if item.nodeid in done])
            items[:] = [item for item in items if item.nodeid not in done]
        config.stash[_SLOW_DESELECTED] = len(done)
        if hasattr(config, "workeroutput"):
            config.workeroutput["slow_deselected"] = len(done)
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


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    report = yield
    if report.when == "call" and report.passed and item.get_closest_marker("slow"):
        ledger = _slow_ledger()
        if ledger is not None:
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a") as f:
                f.write(f"{item.nodeid}\n")
    return report


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    # Under xdist only the workers collect, and each deselects the same cases: one worker's count is the run's.
    count = getattr(node, "workeroutput", {}).get("slow_deselected", 0)
    node.config.stash[_SLOW_DESELECTED] = max(count, node.config.stash.get(_SLOW_DESELECTED, 0))


def pytest_terminal_summary(terminalreporter, config):
    if count := config.stash.get(_SLOW_DESELECTED, 0):
        terminalreporter.write_line(
            f"conftest: {count} slow case(s) deselected -- each passed earlier on this branch, per {_slow_ledger()}; "
            f"ZCRYPTO_RERUN_SLOW=1 runs them again"
        )
