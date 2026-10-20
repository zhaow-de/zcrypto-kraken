from __future__ import annotations

import json
import shlex
from pathlib import Path

import yaml

SUITE = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "test-suite.yml"


def _steps() -> list[dict]:
    (job,) = yaml.safe_load(SUITE.read_text(encoding="utf-8"))["jobs"].values()
    return job["steps"]


def _pytest_argv() -> list[str]:
    (run,) = [step["run"] for step in _steps() if "pytest" in str(step.get("run", ""))]
    return shlex.split(run)


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


def test_the_pytest_step_deselects_the_retired_cases():
    argv = _pytest_argv()
    assert argv[:3] == ["uv", "run", "pytest"], argv
    assert _markexpr(argv) == "not retired", argv


def test_the_pytest_step_measures_no_coverage():
    argv = _pytest_argv()
    assert not [arg for arg in argv if arg.startswith("--cov")], argv


def test_no_step_reaches_coveralls():
    assert not [step for step in _steps() if "coveralls" in json.dumps(step).lower()]
