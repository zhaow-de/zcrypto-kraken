"""`tests/conftest.py`'s ledger of passed slow cases, driven by running pytest over a scratch tree that carries a copy of
the shipped conftest and a fixture list, so no real slow case runs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parent / "conftest.py"
SLOW = "tests/test_scratch.py::test_slow_one"
DESELECTED = "conftest: 1 slow case(s) deselected"
_OVERRIDES = ("CI", "GITHUB_ACTIONS", "ZCRYPTO_RERUN_SLOW")
_ID = ("-c", "user.email=s@test", "-c", "user.name=s")


def _git(tree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(CONFTEST.read_text())
    (tmp_path / "tests" / "slow-cases.txt").write_text(f"# fixture\n{SLOW}\n")
    (tmp_path / "tests" / "test_scratch.py").write_text("def test_slow_one():\n    pass\n\n\ndef test_fast():\n    pass\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    slow: fixture\n")
    _git(tmp_path, "init", "-q", "-b", "develop")
    _git(tmp_path, *_ID, "commit", "-q", "--allow-empty", "-m", "seed")
    _git(tmp_path, "checkout", "-q", "-b", "scratch")
    return tmp_path


def run(tree: Path, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
    local = {k: v for k, v in os.environ.items() if k not in _OVERRIDES}
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-v", "-p", "no:cacheprovider", "--rootdir", str(tree), *args],
        cwd=tree,
        capture_output=True,
        text=True,
        env={**local, **env},
    )


def ledger(tree: Path, key: str = "") -> Path:
    key = key or f"scratch@{_git(tree, 'rev-parse', '--short', 'develop')}"
    return tree / ".tmp" / "slow-passed" / f"{key}.txt"


def _seed(tree: Path) -> None:
    ledger(tree).parent.mkdir(parents=True)
    ledger(tree).write_text(f"{SLOW}\n")


def test_a_passed_slow_case_is_deselected_on_the_second_local_run(tree):
    first = run(tree)
    assert first.returncode == 0 and SLOW in first.stdout, first.stdout + first.stderr
    assert ledger(tree).read_text().splitlines() == [SLOW]
    second = run(tree)
    assert second.returncode == 0, second.stdout + second.stderr
    assert SLOW not in second.stdout and "test_fast PASSED" in second.stdout, second.stdout
    assert DESELECTED in second.stdout and "ZCRYPTO_RERUN_SLOW=1" in second.stdout, second.stdout


@pytest.mark.parametrize("var", ["CI", "GITHUB_ACTIONS"])
def test_in_ci_a_passed_slow_case_runs_and_nothing_is_written(tree, var):
    _seed(tree)
    r = run(tree, **{var: "true"})
    assert r.returncode == 0 and f"{SLOW} PASSED" in r.stdout, r.stdout + r.stderr
    assert ledger(tree).read_text() == f"{SLOW}\n"


def test_the_override_runs_a_passed_slow_case_again_and_writes_nothing(tree):
    _seed(tree)
    r = run(tree, ZCRYPTO_RERUN_SLOW="1")
    assert r.returncode == 0 and f"{SLOW} PASSED" in r.stdout and DESELECTED not in r.stdout, r.stdout + r.stderr
    assert ledger(tree).read_text() == f"{SLOW}\n"


def test_a_detached_head_keeps_its_ledger_under_its_short_sha(tree):
    _git(tree, *_ID, "commit", "-q", "--allow-empty", "-m", "ahead")
    _git(tree, "checkout", "-q", "--detach")
    r = run(tree)
    assert r.returncode == 0, r.stdout + r.stderr
    assert ledger(tree, f"detached-{_git(tree, 'rev-parse', '--short', 'HEAD')}").read_text().splitlines() == [SLOW]


def test_under_xdist_the_pass_is_recorded_and_the_second_run_names_the_deselection(tree):
    first = run(tree, "-n", "2")
    assert first.returncode == 0 and SLOW in first.stdout, first.stdout + first.stderr
    assert set(ledger(tree).read_text().splitlines()) == {SLOW}
    second = run(tree, "-n", "2")
    assert second.returncode == 0 and SLOW not in second.stdout, second.stdout + second.stderr
    assert DESELECTED in second.stdout, second.stdout


@pytest.mark.parametrize("branch", ["develop", "main"])
def test_on_develop_and_main_no_slow_case_is_deselected_and_none_is_recorded(tree, branch):
    _git(tree, "checkout", "-q", "-B", branch)
    for _ in range(2):
        r = run(tree)
        assert r.returncode == 0 and f"{SLOW} PASSED" in r.stdout and DESELECTED not in r.stdout, r.stdout + r.stderr
    assert not (tree / ".tmp" / "slow-passed").exists()


def test_merging_develop_in_starts_a_fresh_ledger(tree):
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    before = ledger(tree)
    assert before.read_text().splitlines() == [SLOW]
    _git(tree, "checkout", "-q", "develop")
    _git(tree, *_ID, "commit", "-q", "--allow-empty", "-m", "develop moves")
    _git(tree, "checkout", "-q", "scratch")
    _git(tree, *_ID, "merge", "-q", "--no-ff", "-m", "merge develop", "develop")
    after = run(tree)
    assert after.returncode == 0 and f"{SLOW} PASSED" in after.stdout and DESELECTED not in after.stdout, after.stdout
    assert ledger(tree) != before and ledger(tree).read_text().splitlines() == [SLOW]
