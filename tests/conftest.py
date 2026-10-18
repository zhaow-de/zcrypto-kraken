import logging
import os
import re
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
from cli.registry import attempts

_REAL_LOG_PATH, _REAL_ALLOWED_LOG_IDS = attempts.log_path, attempts.allowed_log_ids
SLOW_CASES = Path(__file__).resolve().parent / "slow-cases.txt"
CONSUMERS = TMP_ROOT.parent / "infra" / "scripts" / "consumers.sh"
_SLOW_DESELECTED = pytest.StashKey[int]()


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(TMP_ROOT.parent), *args], capture_output=True, text=True)


def _slow_ledger() -> Path | None:
    """Where this branch's passed slow cases are recorded; None where every slow case runs and none is recorded."""
    if "CI" in os.environ or "GITHUB_ACTIONS" in os.environ or os.environ.get("ZCRYPTO_RERUN_SLOW") == "1":
        return None
    branch = _git("branch", "--show-current").stdout.strip()
    if branch in ("develop", "main"):
        return None
    if not branch:
        sha = _git("rev-parse", "--short", "HEAD").stdout.strip()
        return TMP_ROOT / "slow-passed" / f"detached-{sha}.txt" if sha else None
    return TMP_ROOT / "slow-passed" / f"{branch}.txt"


def _tree_is_head() -> bool:
    status = _git("status", "--porcelain")
    return status.returncode == 0 and not status.stdout


def _recorded(ledger: Path) -> dict[str, str | None]:
    records: dict[str, str | None] = {}
    for line in filter(None, (line.strip() for line in ledger.read_text().splitlines())):
        node, _, sha = line.rpartition(" ")
        if node and re.fullmatch(r"[0-9a-f]{40}([0-9a-f]{24})?", sha):
            records[node] = sha
        else:
            records[line] = None
    return records


def _direct_readers(paths: list[str]) -> dict[str, set[str]] | None:
    """Each path's `consumers.sh --direct` test readers; None when the script is absent or fails, so every case with a
    changed file runs."""
    if not CONSUMERS.is_file():
        return None
    run = subprocess.run(["bash", str(CONSUMERS), "--direct", *paths], cwd=TMP_ROOT.parent, capture_output=True, text=True)
    if run.returncode != 0:
        return None
    readers: dict[str, set[str]] = {}
    current: set[str] | None = None
    for line in run.stdout.splitlines():
        if line.startswith("## "):
            current = readers.setdefault(line[3:], set())
        elif current is not None and line and not line.startswith("#"):
            current.add(line)
    return readers


def _still_passed(slow: list[pytest.Item], records: dict[str, str | None]) -> set[str]:
    changed: dict[str, set[str] | None] = {}
    for sha in {records[item.nodeid] for item in slow if records.get(item.nodeid)}:
        diff = _git("diff", "--name-only", "--no-renames", "-z", sha, "--")
        changed[sha] = set(diff.stdout.split("\0")) - {""} if diff.returncode == 0 else None
    paths = sorted(set().union(*(files for files in changed.values() if files)))
    readers = _direct_readers(paths) if paths else {}
    fresh = set()
    for item in slow:
        files = changed.get(records.get(item.nodeid) or "")
        if files is None or (files and readers is None):
            continue
        try:
            test_file = item.path.resolve().relative_to(TMP_ROOT.parent).as_posix()
        except ValueError:
            continue
        if test_file not in files and not any(test_file in readers.get(path, ()) for path in files):
            fresh.add(item.nodeid)
    return fresh


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


def _allowlisted(path: Path) -> frozenset[str]:
    return frozenset(attempts.parse_allowlist(path.read_text())) if path.is_file() else frozenset()


@pytest.fixture(autouse=True)
def _attempts_log_in_tmp_path(tmp_path):
    # A patcher of its own, so a test's `monkeypatch.undo()` never reaches these patches. The allowlist is read on
    # every call: a test writes or rewrites it after this fixture has run.
    patch = pytest.MonkeyPatch()
    patch.setattr(attempts, "log_path", lambda code_root: tmp_path / ".local" / "trial-attempts.jsonl")
    patch.setattr(attempts, "allowed_log_ids", lambda code_root: _allowlisted(tmp_path / "trial-attempt-logs.txt"))
    yield
    patch.undo()


@pytest.fixture(autouse=True)
def _attempts_log_kept_in_tmp_path(_attempts_log_in_tmp_path, monkeypatch, tmp_path):
    # Torn down before `monkeypatch` is undone, so it reads what the test patched through it.
    yield
    assert attempts.log_path is not _REAL_LOG_PATH, (
        "this test left cli.registry.attempts.log_path on the real resolution, which names the main checkout's trial-attempts log"
    )
    assert attempts.allowed_log_ids is not _REAL_ALLOWED_LOG_IDS, (
        "this test left cli.registry.attempts.allowed_log_ids on the real allowlist"
    )
    assert attempts.log_path(TMP_ROOT.parent).is_relative_to(tmp_path), (
        "this test left cli.registry.attempts.log_path resolving outside its tmp_path"
    )


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
    result = yield
    # After the yield, so a run whose `-m` or `-k` left no slow case pays for no `git diff` and no consumers.sh call.
    kept = [item for item in items if item.nodeid in listed]
    ledger = _slow_ledger() if kept else None
    if ledger is not None and ledger.is_file():
        done = _still_passed(kept, _recorded(ledger))
        if done:
            config.hook.pytest_deselected(items=[item for item in items if item.nodeid in done])
            items[:] = [item for item in items if item.nodeid not in done]
        config.stash[_SLOW_DESELECTED] = len(done)
        if hasattr(config, "workeroutput"):
            config.workeroutput["slow_deselected"] = len(done)
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
        if ledger is not None and _tree_is_head() and (head := _git("rev-parse", "HEAD").stdout.strip()):
            ledger.parent.mkdir(parents=True, exist_ok=True)
            with ledger.open("a") as f:
                f.write(f"{item.nodeid} {head}\n")
    return report


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    # Under xdist only the workers collect, and each deselects the same cases: one worker's count is the run's.
    count = getattr(node, "workeroutput", {}).get("slow_deselected", 0)
    node.config.stash[_SLOW_DESELECTED] = max(count, node.config.stash.get(_SLOW_DESELECTED, 0))


def pytest_terminal_summary(terminalreporter, config):
    if count := config.stash.get(_SLOW_DESELECTED, 0):
        terminalreporter.write_line(
            f"conftest: {count} slow case(s) deselected -- each passed at a commit since which no file its test file "
            f"names (consumers.sh --direct) has changed, per {_slow_ledger()}; ZCRYPTO_RERUN_SLOW=1 runs them again"
        )
