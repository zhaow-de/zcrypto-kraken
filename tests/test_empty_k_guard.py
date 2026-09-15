"""`tests/conftest.py`'s empty-selector arm, driven by running pytest over a scratch tree.

The conftest that ships is copied into the tree and pytest is run there as a subprocess, so what is driven is the
file itself -- a mutation of it moves these cases -- and nothing here imports the hook.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

CONFTEST = Path(__file__).resolve().parent / "conftest.py"
THREE_TESTS = "def test_alpha():\n    assert True\n\n\ndef test_beta():\n    assert True\n\n\ndef test_gamma():\n    assert True\n"
BANNER = "conftest: NO TEST SELECTED"


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "conftest.py").write_text(CONFTEST.read_text())
    (tmp_path / "test_scratch.py").write_text(THREE_TESTS)
    return tmp_path


def run(tree: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=tree,
        capture_output=True,
        text=True,
    )


def test_a_selector_that_matches_no_test_is_named_on_stderr(tree: Path):
    r = run(tree, "-k", "nosuchtest")
    assert r.returncode == 5, r.stdout + r.stderr
    assert BANNER in r.stderr, r.stdout + r.stderr
    assert "-k 'nosuchtest'" in r.stderr, r.stderr


def test_the_message_counts_what_collection_found(tree: Path):
    r = run(tree, "-k", "nosuchtest")
    assert "0 of 3 collected" in r.stderr, r.stderr


def test_a_selector_with_spaces_is_named_whole(tree: Path):
    r = run(tree, "-k", "delta or epsilon")
    assert "-k 'delta or epsilon'" in r.stderr, r.stderr


def test_a_selector_that_matches_is_silent(tree: Path):
    r = run(tree, "-k", "alpha")
    assert r.returncode == 0, r.stdout + r.stderr
    assert BANNER not in r.stderr, r.stderr


def test_a_mark_that_empties_a_matched_selection_is_named_beside_the_k(tree: Path):
    r = run(tree, "-k", "alpha", "-m", "nosuchmark")
    assert r.returncode == 5, r.stdout + r.stderr
    assert "0 of 3 collected" in r.stderr, r.stderr
    assert "Selectors this hook reads: -k 'alpha', -m 'nosuchmark'." in r.stderr, r.stderr


def test_a_deselect_that_empties_a_matched_selection_is_named_beside_the_k(tree: Path):
    r = run(tree, "-k", "alpha", "--deselect", "test_scratch.py::test_alpha")
    assert r.returncode == 5, r.stdout + r.stderr
    assert "0 of 3 collected" in r.stderr, r.stderr
    assert "Selectors this hook reads: -k 'alpha', --deselect 'test_scratch.py::test_alpha'." in r.stderr, r.stderr


def test_a_run_with_no_selector_is_silent(tree: Path):
    # Emptied by a mark over the three collected, not by collecting nothing: only the missing `-k` keeps this silent.
    r = run(tree, "-m", "nosuchmark")
    assert r.returncode == 5, r.stdout + r.stderr
    assert BANNER not in r.stderr, r.stderr


def test_a_run_whose_collection_found_nothing_is_silent(tree: Path):
    (tree / "test_scratch.py").write_text("import nosuchmodule\n")
    r = run(tree, "-k", "nosuchtest")
    assert r.returncode == 2, r.stdout + r.stderr  # the code a banner claiming 5 would have contradicted
    assert BANNER not in r.stderr, r.stderr


def test_a_collect_only_run_with_a_dead_selector_is_silent(tree: Path):
    r = run(tree, "--collect-only", "-k", "nosuchtest")
    assert r.returncode == 5, r.stdout + r.stderr
    assert BANNER not in r.stderr, r.stderr


def test_the_arm_changes_no_exit_code(tree: Path, tmp_path_factory: pytest.TempPathFactory):
    bare = tmp_path_factory.mktemp("no_conftest")
    (bare / "test_scratch.py").write_text(THREE_TESTS)
    assert run(bare, "-k", "nosuchtest").returncode == run(tree, "-k", "nosuchtest").returncode == 5
    assert run(bare, "-k", "alpha").returncode == run(tree, "-k", "alpha").returncode == 0
