from __future__ import annotations

import copy
import json
import shlex
from pathlib import Path

import pytest
import yaml
from _pytest.config.findpaths import determine_setup

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / ".github" / "workflows" / "test-suite.yml"
HARNESS = "tests/test_cache_restart.py"
# Each test runs in one of the two steps as far as the steps' command lines, PYTEST_ADDOPTS in the workflow's env and
# the ini file pytest reads decide it, each held by a case below; tests/conftest.py's slow-case deselection is held by
# tests/test_slow_ledger.py, not here.
# The dests of the options that select no test. Any other option a step gives but the split case's expected `-m` and
# `--ignore` fails that case, until a reader who has judged it selects nothing adds its dest here.
_SELECTS_NOTHING = {"numprocesses", "dist", "maxschedchunk", "maxfail", "durations"}
# The ini keys that select no test. Any other key but `addopts`, which the ini case holds whole, fails that case
# until a reader who has judged it selects nothing adds it here.
_INI_SELECTS_NOTHING = {"markers"}


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
    names, and the step's paths as `file_or_dir`, sorted. The parse is pytest's, so a spelling is read as pytest reads
    it and an option pytest does not define raises its UsageError; a copy of the parser records each option as it
    takes it, so an `-m` that a later one overrides is still seen."""
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


def _naming(node: object, name: str, at: str = "") -> list[str]:
    """Each place in a parsed YAML document whose key is `name` or whose string value contains it, as a path."""
    if isinstance(node, dict):
        found = []
        for key, value in node.items():
            here = f"{at}.{key}"
            found += [here] if key == name else []
            found += _naming(value, name, here)
        return found
    if isinstance(node, list):
        return [place for i, item in enumerate(node) for place in _naming(item, name, f"{at}[{i}]")]
    return [at] if isinstance(node, str) and name in node else []


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


def test_the_harness_and_the_rest_of_the_suite_are_the_two_steps_of_one_parallel_group_whose_command_lines_put_each_test_in_one(
    pytestconfig,
):
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


def test_the_workflow_sets_no_pytest_addopts_on_itself_its_job_or_any_step():
    # A string naming it counts too: a `run` that writes it to `$GITHUB_ENV` sets it for every later step.
    found = _naming(yaml.safe_load(SUITE.read_text(encoding="utf-8")), "PYTEST_ADDOPTS")
    assert not found, f"PYTEST_ADDOPTS gives a step's pytest options the split case never reads, at {found}"


def test_each_step_reads_its_ini_from_pyproject_whose_addopts_is_strict_markers_alone(pytestconfig):
    for argv in _pytest_argvs():
        paths = dict(_selections(pytestconfig, argv))["file_or_dir"]
        # pytest's own search, as `Config.parse` calls it; `-c`, `-o` and `--rootdir` on a step fail the split case.
        _, inipath, inicfg, _ = determine_setup(
            inifile=None, override_ini=None, args=[str(REPO / path) for path in paths], rootdir_cmd_arg=None, invocation_dir=REPO
        )
        assert inipath == REPO / "pyproject.toml", (
            f"{argv}: pytest reads its ini from {inipath}, so pyproject.toml's addopts and keys held here no longer reach that step"
        )
        held = {key: value.value for key, value in inicfg.items() if key not in _INI_SELECTS_NOTHING}
        assert held == {"addopts": ["--strict-markers"]}, (
            f"{argv}: the ini's addopts reach the step's pytest ahead of its argv, and a key outside `_INI_SELECTS_NOTHING` "
            f"may change what it collects: {held}"
        )
