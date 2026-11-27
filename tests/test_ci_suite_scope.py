from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / ".github" / "workflows" / "test-suite.yml"
HARNESS = "tests/test_cache_restart.py"
# The dests of the options a step may give pytest that select no test. Any other option a step gives (`-k`, `--deselect`,
# `--ignore-glob`, `-o`, `-p`, a plugin's) fails the split case until a reader who has judged it selects nothing adds it here.
_SELECTS_NOTHING = {"numprocesses", "dist", "maxschedchunk", "maxfail", "durations"}


def _job() -> dict:
    (job,) = yaml.safe_load(SUITE.read_text(encoding="utf-8"))["jobs"].values()
    return job


def _steps() -> list[dict]:
    """The job's steps, each `parallel:` group's own steps in its place."""
    return [inner for step in _job()["steps"] for inner in step.get("parallel", [step])]


def _pytest_argvs() -> list[list[str]]:
    return [shlex.split(step["run"]) for step in _steps() if "pytest" in str(step.get("run", ""))]


def _markexpr(argv: list[str]) -> str | None:
    """The expression pytest applies: the last of its `-m`/`--markexpr` spellings."""
    found = None
    for i, arg in enumerate(argv):
        if arg in ("-m", "--markexpr"):
            found = argv[i + 1]
        elif arg.startswith("--markexpr="):
            found = arg.split("=", 1)[1]
        elif arg.startswith("-m") and not arg.startswith("--") and len(arg) > 2:
            found = arg[2:]
    return found


def _selections(pytestconfig: pytest.Config, argv: list[str]) -> list[tuple[str, object]]:
    """What pytest's own parser takes from a step's argv: each option as (dest, value), but those `_SELECTS_NOTHING`
    names, and the step's paths as `file_or_dir`, sorted. The parse is pytest's, so a spelling it admits is read as it
    reads it (`-kEXPR`, `-k=EXPR`, `-xk EXPR`, `--ignore-glob=`, an `@file`) and one it does not raises its UsageError;
    a copy of the parser records each option as it takes it, so an `-m` that a later one overrides is still seen."""
    taken: list[tuple[str, object]] = []
    parser = copy.copy(pytestconfig._parser.optparser)
    convert = parser._get_values

    def take(action, strings):
        value = convert(action, strings)
        taken.append((action.dest, value))
        return value

    parser._get_values = take
    parser.parse_intermixed_args(argv[3:])
    return sorted(((dest, value) for dest, value in taken if dest not in _SELECTS_NOTHING), key=repr)


def test_each_pytest_step_deselects_the_retired_cases():
    argvs = _pytest_argvs()
    assert argvs, _steps()
    for argv in argvs:
        assert argv[:3] == ["uv", "run", "pytest"], argv
        assert _markexpr(argv) == "not retired", argv


def test_no_pytest_step_measures_coverage():
    for argv in _pytest_argvs():
        assert not [arg for arg in argv if arg.startswith("--cov")], argv


def test_no_step_reaches_coveralls():
    assert not [step for step in _steps() if "coveralls" in json.dumps(step).lower()]


def test_the_harness_and_the_rest_of_the_suite_are_the_two_steps_of_one_parallel_group_each_test_in_one(pytestconfig):
    (outer,) = [step for step in _job()["steps"] if "parallel" in step]
    # No other key on the group or on either step: an `if:` or a `continue-on-error` there passes the job with a
    # step unrun or red.
    assert set(outer) == {"parallel"}, outer
    group = outer["parallel"]
    names = [step.get("name") for step in group]
    assert len(names) == 2 and all(names) and len(set(names)) == 2, group
    assert all(set(step) <= {"name", "run"} for step in group), group
    argvs = [shlex.split(step["run"]) for step in group]
    assert sorted(_pytest_argvs()) == sorted(argvs), _pytest_argvs()
    split = sorted((_selections(pytestconfig, argv) for argv in argvs), key=repr)
    assert split == [
        [("file_or_dir", [HARNESS]), ("markexpr", "not retired")],
        [("file_or_dir", []), ("ignore", HARNESS), ("markexpr", "not retired")],
    ], argvs
    assert (REPO / HARNESS).is_file()
