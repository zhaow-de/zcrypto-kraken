"""`tests/conftest.py`'s ledger of passed slow cases, driven by running pytest over a scratch tree (`tree`), so no real
slow case runs."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONFTEST = ROOT / "tests" / "conftest.py"
CONSUMERS = ROOT / "infra" / "scripts" / "consumers.sh"
SLOW = "tests/test_scratch.py::test_slow_one"
SUBJECT = "lib/subject.txt"
DESELECTED = "conftest: 1 slow case(s) deselected"
_OVERRIDES = ("CI", "GITHUB_ACTIONS", "ZCRYPTO_RERUN_SLOW")
_ID = ("-c", "user.email=s@test", "-c", "user.name=s")


def _git(tree: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(tree), *args], check=True, capture_output=True, text=True).stdout.strip()


def _scratch_test(body: str) -> str:
    return f'SUBJECT = "{SUBJECT}"\n\n\ndef test_slow_one():\n    {body}\n\n\ndef test_fast():\n    pass\n'


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / ".gitignore").write_text(".tmp/\n__pycache__/\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "conftest.py").write_text(CONFTEST.read_text())
    (tmp_path / "tests" / "slow-cases.txt").write_text(f"# fixture\n{SLOW}\n")
    (tmp_path / "tests" / "test_scratch.py").write_text(_scratch_test("pass"))
    (tmp_path / "infra" / "scripts").mkdir(parents=True)
    (tmp_path / "infra" / "scripts" / "consumers.sh").write_text(CONSUMERS.read_text())
    (tmp_path / "lib").mkdir()
    (tmp_path / SUBJECT).write_text("subject\n")
    (tmp_path / "lib" / "other.txt").write_text("other\n")
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    slow: fixture\n")
    _git(tmp_path, "init", "-q", "-b", "develop")
    _git(tmp_path, "add", ".gitignore", "tests", "infra", "lib", "pytest.ini")
    _git(tmp_path, *_ID, "commit", "-q", "-m", "seed")
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
    key = key or "scratch"
    return tree / ".tmp" / "slow-passed" / f"{key}.txt"


def head(tree: Path) -> str:
    return _git(tree, "rev-parse", "HEAD")


def change(tree: Path, path: str, *, commit: bool = True) -> None:
    (tree / path).write_text((tree / path).read_text() + "changed\n")
    if commit:
        _git(tree, "add", path)
        _git(tree, *_ID, "commit", "-q", "-m", f"change {path}")


def _seed(tree: Path) -> None:
    ledger(tree).parent.mkdir(parents=True)
    ledger(tree).write_text(f"{SLOW} {head(tree)}\n")


def test_a_passed_slow_case_is_deselected_on_the_second_local_run(tree):
    first = run(tree)
    assert first.returncode == 0 and SLOW in first.stdout, first.stdout + first.stderr
    assert ledger(tree).read_text().splitlines() == [f"{SLOW} {head(tree)}"]
    second = run(tree)
    assert second.returncode == 0, second.stdout + second.stderr
    assert SLOW not in second.stdout and "test_fast PASSED" in second.stdout, second.stdout
    assert DESELECTED in second.stdout and "ZCRYPTO_RERUN_SLOW=1" in second.stdout, second.stdout


def test_a_passed_slow_case_runs_again_once_after_a_commit_changes_a_file_its_test_names(tree):
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    change(tree, SUBJECT)
    second = run(tree)
    assert f"{SLOW} PASSED" in second.stdout and DESELECTED not in second.stdout, second.stdout + second.stderr
    assert ledger(tree).read_text().splitlines()[-1] == f"{SLOW} {head(tree)}"
    third = run(tree)
    assert f"{SLOW} PASSED" not in third.stdout and DESELECTED in third.stdout, third.stdout + third.stderr


def test_an_uncommitted_edit_to_a_file_its_test_names_runs_a_passed_slow_case_again(tree):
    run(tree)
    change(tree, SUBJECT, commit=False)
    r = run(tree)
    assert f"{SLOW} PASSED" in r.stdout and DESELECTED not in r.stdout, r.stdout + r.stderr


def test_a_slow_case_passing_with_an_uncommitted_edit_leaves_no_ledger_line_and_runs_on_the_next_run(tree):
    change(tree, SUBJECT, commit=False)
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    assert not ledger(tree).exists()
    _git(tree, "checkout", "--", SUBJECT)
    second = run(tree)
    assert f"{SLOW} PASSED" in second.stdout and DESELECTED not in second.stdout, second.stdout + second.stderr


def test_a_slow_case_passing_beside_an_untracked_file_leaves_no_ledger_line(tree):
    (tree / "lib" / "scratch.txt").write_text("untracked\n")
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    assert not ledger(tree).exists()


def test_a_passed_slow_case_stays_deselected_after_a_commit_changes_an_unrelated_file(tree):
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    change(tree, "lib/other.txt")
    second = run(tree)
    assert f"{SLOW} PASSED" not in second.stdout and DESELECTED in second.stdout, second.stdout + second.stderr


def test_a_failing_slow_case_is_not_recorded_and_runs_again(tree):
    (tree / "tests" / "test_scratch.py").write_text(_scratch_test("assert False"))
    _git(tree, "add", "tests/test_scratch.py")
    _git(tree, *_ID, "commit", "-q", "-m", "the slow case fails")
    for _ in range(2):
        r = run(tree, "-m", "slow")
        assert r.returncode == 1 and f"{SLOW} FAILED" in r.stdout, r.stdout + r.stderr
    assert not ledger(tree).exists()


def test_a_ledger_line_without_a_sha_is_stale_and_the_case_runs(tree):
    ledger(tree).parent.mkdir(parents=True)
    ledger(tree).write_text(f"{SLOW}\n")
    r = run(tree)
    assert f"{SLOW} PASSED" in r.stdout and DESELECTED not in r.stdout, r.stdout + r.stderr
    assert ledger(tree).read_text().splitlines() == [SLOW, f"{SLOW} {head(tree)}"]


@pytest.mark.parametrize("var", ["CI", "GITHUB_ACTIONS"])
def test_in_ci_a_passed_slow_case_runs_and_nothing_is_written(tree, var):
    _seed(tree)
    r = run(tree, **{var: "true"})
    assert r.returncode == 0 and f"{SLOW} PASSED" in r.stdout, r.stdout + r.stderr
    assert ledger(tree).read_text() == f"{SLOW} {head(tree)}\n"


def test_the_override_runs_a_passed_slow_case_again_and_writes_nothing(tree):
    _seed(tree)
    r = run(tree, ZCRYPTO_RERUN_SLOW="1")
    assert r.returncode == 0 and f"{SLOW} PASSED" in r.stdout and DESELECTED not in r.stdout, r.stdout + r.stderr
    assert ledger(tree).read_text() == f"{SLOW} {head(tree)}\n"


def test_a_detached_head_keeps_its_ledger_under_its_short_sha(tree):
    _git(tree, *_ID, "commit", "-q", "--allow-empty", "-m", "ahead")
    _git(tree, "checkout", "-q", "--detach")
    r = run(tree)
    assert r.returncode == 0, r.stdout + r.stderr
    key = f"detached-{_git(tree, 'rev-parse', '--short', 'HEAD')}"
    assert ledger(tree, key).read_text().splitlines() == [f"{SLOW} {head(tree)}"]


def test_under_xdist_the_pass_is_recorded_and_the_second_run_names_the_deselection(tree):
    first = run(tree, "-n", "2")
    assert first.returncode == 0 and SLOW in first.stdout, first.stdout + first.stderr
    assert set(ledger(tree).read_text().splitlines()) == {f"{SLOW} {head(tree)}"}
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


def test_merging_develop_in_keeps_a_passed_slow_case_deselected(tree):
    first = run(tree)
    assert first.returncode == 0 and f"{SLOW} PASSED" in first.stdout, first.stdout + first.stderr
    before = ledger(tree)
    recorded = before.read_text().splitlines()
    assert recorded == [f"{SLOW} {head(tree)}"]
    _git(tree, "checkout", "-q", "develop")
    _git(tree, *_ID, "commit", "-q", "--allow-empty", "-m", "develop moves")
    _git(tree, "checkout", "-q", "scratch")
    _git(tree, *_ID, "merge", "-q", "--no-ff", "-m", "merge develop", "develop")
    after = run(tree)
    assert f"{SLOW} PASSED" not in after.stdout and DESELECTED in after.stdout, after.stdout + after.stderr
    assert ledger(tree) == before and ledger(tree).read_text().splitlines() == recorded
