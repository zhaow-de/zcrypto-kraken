"""The marks are read off a real collection in a subprocess, so what is measured is the hook `tests/conftest.py` ships."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

from cli.research.subjects import SUBJECTS
from tests.retired_subjects import RETIRED_SUBJECTS

REPO = Path(__file__).resolve().parents[1]
KEPT = ("record33-combined", "record44-crossfreq")
SUBJECT_TESTS = "tests/test_research_command.py"
# A provenance case whose parameter is a retired subject's name, as the record the checker reads.
PROVENANCE_CASE = (
    "tests/test_trial_registry_provenance.py::"
    "test_a_reading_carries_the_outcome_its_subjects_rule_gives_and_no_other[a-ruled-subjects-clean-stop]"
)


def _collected(selection: str) -> set[str]:
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-m", selection]
        + [SUBJECT_TESTS, PROVENANCE_CASE.split("::")[0]],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ, "ZCRYPTO_RERUN_SLOW": "1"},
    )
    assert run.returncode == 0, run.stdout + run.stderr
    return {line for line in run.stdout.splitlines() if "::" in line}


@pytest.fixture(scope="module")
def collections() -> tuple[set[str], set[str]]:
    return _collected("retired"), _collected("not retired")


def _cases_of(names, ids: set[str]) -> set[str]:
    def names_one(param: str) -> bool:
        return any(param == name or param.startswith(f"{name}-") for name in names)

    return {i for i in ids if i.startswith(f"{SUBJECT_TESTS}::") and "[" in i and names_one(i.split("[", 1)[1][:-1])}


def test_every_retired_name_is_a_registered_subject():
    assert RETIRED_SUBJECTS <= set(SUBJECTS), sorted(RETIRED_SUBJECTS - set(SUBJECTS))


def test_neither_kept_subject_is_retired():
    assert not RETIRED_SUBJECTS & set(KEPT)


def test_a_retired_subjects_cases_are_marked_and_deselected_under_not_retired(collections):
    retired, kept = collections
    cases = _cases_of(RETIRED_SUBJECTS, retired | kept)
    assert f"{SUBJECT_TESTS}::test_every_subjects_metrics_hold_when_the_shared_defaults_move[b1-conditioning]" in cases
    assert cases <= retired and not cases & kept


def _kept_subject_functions() -> set[str]:
    source = (REPO / SUBJECT_TESTS).read_text()
    return {
        node.name
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(name in ast.get_source_segment(source, part) for part in (*node.decorator_list, node) for name in KEPT)
    }


def test_the_kept_subjects_cases_stay_under_not_retired(collections):
    """A case whose id opens with a retired name keeps its mark: a function naming a kept subject may be parametrised over
    SUBJECTS."""
    retired, kept = collections
    functions = _kept_subject_functions()
    assert {
        "test_record44_refuses_a_grid_it_cannot_feed_naming_the_file_or_the_rolling_pair_and_grid",
        "test_a_production_subject_honours_window_all_the_way_down_to_the_reads",
    } <= functions
    cases = {i for i in retired | kept if i.split("::", 1)[1].split("[", 1)[0] in functions} | _cases_of(KEPT, retired | kept)
    assert f"{SUBJECT_TESTS}::test_every_subjects_metrics_hold_when_the_shared_defaults_move[record44-crossfreq]" in cases
    marked = (cases & retired) - _cases_of(RETIRED_SUBJECTS, retired)
    assert not marked, sorted(marked)


def test_a_retired_name_in_another_files_parameter_leaves_its_case_unmarked(collections):
    retired, kept = collections
    assert PROVENANCE_CASE in kept and PROVENANCE_CASE not in retired
