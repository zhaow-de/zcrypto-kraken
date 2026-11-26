from __future__ import annotations

import json
import shlex
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / ".github" / "workflows" / "test-suite.yml"
HARNESS = "tests/test_cache_restart.py"
# The options these lines give a separate value, so the value is not read as a path to collect.
_VALUED = {"-n", "-m", "--markexpr", "--dist", "--maxschedchunk", "--durations", "-k", "-p", "--ignore", "--deselect"}


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


def _paths(argv: list[str]) -> list[str]:
    """What pytest is pointed at; none is the whole suite."""
    paths, words = [], iter(argv[3:])
    for arg in words:
        if arg in _VALUED:
            next(words)
        elif not arg.startswith("-"):
            paths.append(arg)
    return paths


def _ignored(argv: list[str]) -> list[str]:
    return [arg.split("=", 1)[1] for arg in argv if arg.startswith("--ignore=")] + [
        argv[i + 1] for i, arg in enumerate(argv) if arg == "--ignore"
    ]


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


def test_the_harness_and_the_rest_of_the_suite_are_the_two_steps_of_one_parallel_group_each_test_in_one():
    (group,) = [step["parallel"] for step in _job()["steps"] if "parallel" in step]
    names = [step.get("name") for step in group]
    assert len(names) == 2 and all(names) and len(set(names)) == 2, group
    assert not [step for step in group if step.get("continue-on-error")], group
    argvs = [shlex.split(step["run"]) for step in group]
    assert sorted(_pytest_argvs()) == sorted(argvs), _pytest_argvs()
    split = sorted((_paths(argv), _ignored(argv)) for argv in argvs)
    assert split == [([], [HARNESS]), ([HARNESS], [])], argvs
    assert (REPO / HARNESS).is_file()
