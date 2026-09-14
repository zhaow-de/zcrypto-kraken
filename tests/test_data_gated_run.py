"""The nightly runner's parser and result shape: pytest's own summary lines, then the runner driven
end to end over a synthetic checkout under `tmp_path` -- never this repo's suite or its `.local/`."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "data-gated-run.py"
_spec = importlib.util.spec_from_file_location("data_gated_run", _SCRIPT)
runner = importlib.util.module_from_spec(_spec)
sys.modules["data_gated_run"] = runner
_spec.loader.exec_module(runner)

# The tail of `pytest -q -p no:cacheprovider -rfE` over one pass, one fail, one skip, one xfail and one
# fixture error, as pytest printed it; the message on a -q short-summary line is cut to the terminal
# width, the id never is.
MIXED = textwrap.dedent("""\
    ERROR    cli.engine:cycle.py:12 a captured log line above the rule is not an id
    E   AssertionError: one is not two
    E   assert 1 == 2

    tests/test_shapes.py:3: AssertionError
    =========================== short test summary info ============================
    FAILED tests/test_shapes.py::test_fail - AssertionError: one...
    ERROR tests/test_shapes.py::test_err - RuntimeError: fixture...
    1 failed, 1 passed, 1 skipped, 1 xfailed, 1 error in 0.01s
    """)


def test_the_mixed_summary_line_yields_every_count_and_the_ids():
    parsed = runner.parse_summary(MIXED)
    assert parsed["error"] is None
    assert parsed["summary_line"] == "1 failed, 1 passed, 1 skipped, 1 xfailed, 1 error in 0.01s"
    assert parsed["counts"] == {
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "errors": 1,
        "xfailed": 1,
        "xpassed": 0,
        "deselected": 0,
        "warnings": 0,
    }
    assert parsed["failed"] == ["tests/test_shapes.py::test_fail"]
    assert parsed["errors"] == ["tests/test_shapes.py::test_err"]


def test_a_captured_log_line_starting_with_error_above_the_rule_is_not_an_id():
    parsed = runner.parse_summary(MIXED)
    assert all("captured log line" not in i for i in parsed["errors"])


@pytest.mark.parametrize(
    "line,expected",
    [
        ("3 passed, 2 warnings in 65.12s (0:01:05)", {"passed": 3, "warnings": 2}),
        ("5 deselected in 0.00s", {"deselected": 5}),
        ("no tests ran in 0.00s", {}),
        ("============ 1 passed in 0.10s ============", {"passed": 1}),
        ("2 errors in 0.03s", {"errors": 2}),
    ],
)
def test_every_summary_line_shape_reads_as_counts_with_the_rest_zero(line, expected):
    parsed = runner.parse_summary("some output\n" + line + "\n")
    assert parsed["error"] is None
    assert parsed["counts"] == {**dict.fromkeys(runner.COUNT_KEYS, 0), **expected}
    assert parsed["failed"] == [] and parsed["errors"] == []


def test_a_failed_line_without_a_message_keeps_its_id():
    text = "===== short test summary info =====\nFAILED tests/test_x.py::test_long_name_cut_before_the_dash\n1 failed in 0.01s\n"
    assert runner.parse_summary(text)["failed"] == ["tests/test_x.py::test_long_name_cut_before_the_dash"]


def test_output_without_a_summary_line_is_an_error_not_a_zero():
    usage = "ERROR: usage: pytest [options] [file_or_dir] [...]\npytest: error: unrecognized arguments: --no-such-flag\n"
    parsed = runner.parse_summary(usage)
    assert parsed["counts"] is None
    assert parsed["summary_line"] is None
    assert parsed["error"] == runner.NO_SUMMARY


def test_the_last_matching_line_is_the_summary_even_when_a_test_printed_one():
    text = "1 passed in 9.99s\n===== short test summary info =====\nFAILED tests/t.py::t - x\n1 failed in 0.01s\n"
    parsed = runner.parse_summary(text)
    assert parsed["summary_line"] == "1 failed in 0.01s"
    assert parsed["failed"] == ["tests/t.py::t"]


# --- end to end over a synthetic checkout -----------------------------------------------------------


def _checkout(tmp_path: Path, body: str) -> Path:
    repo = tmp_path / "checkout"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_synthetic.py").write_text(textwrap.dedent(body))
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "synthetic"], check=True)
    return repo


def _run(repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        env={**os.environ, **(env or {})},
    )


def _latest(repo: Path) -> dict:
    return json.loads((repo / ".local" / "data-gated-runs" / "latest.json").read_text())


MIXED_SUITE = """\
    import pytest
    def test_ok(): pass
    def test_fail(): assert 1 == 2, "one is not two"
    @pytest.mark.skipif(True, reason="gated")
    def test_skip(): pass
    """


def test_the_runner_writes_the_stamped_file_and_latest_with_the_full_shape(tmp_path):
    repo = _checkout(tmp_path, MIXED_SUITE)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    proc = _run(repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    stamped = sorted(p for p in (repo / ".local" / "data-gated-runs").iterdir() if p.name != "latest.json")
    assert len(stamped) == 1 and stamped[0].suffix == ".json", stamped
    assert json.loads(stamped[0].read_text()) == latest
    assert stamped[0].stem == latest["started"].replace("-", "").replace(":", "")
    assert set(latest) == {
        "schema",
        "started",
        "finished",
        "duration_s",
        "repo",
        "sha",
        "dirty",
        "git_error",
        "command",
        "exit_code",
        "summary_line",
        "counts",
        "failed",
        "errors",
        "error",
        "ok",
    }
    started, finished = (
        datetime.strptime(latest[k], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for k in ("started", "finished")
    )
    assert before <= started <= finished
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert latest["sha"] == head and latest["dirty"] is False and latest["git_error"] is None
    assert latest["repo"] == str(repo)
    assert latest["command"][1:] == ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE"]
    assert latest["exit_code"] == 1
    assert latest["counts"]["passed"] == 1 and latest["counts"]["failed"] == 1 and latest["counts"]["skipped"] == 1
    assert latest["failed"] == ["tests/test_synthetic.py::test_fail"]
    assert latest["errors"] == [] and latest["error"] is None
    assert latest["ok"] is False
    assert "one is not two" in proc.stdout, "pytest's own output is re-emitted for the journal"
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: FAIL exit=1 ")


def test_a_passing_suite_reads_ok_and_the_runner_exits_zero(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    proc = _run(repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["ok"] is True and latest["exit_code"] == 0 and latest["failed"] == []
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: ok exit=0 1 passed in ")


def test_a_dirty_checkout_is_recorded_as_such(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    (repo / "tests" / "test_synthetic.py").write_text("def test_ok(): pass\ndef test_two(): pass\n")
    _run(repo)
    assert _latest(repo)["dirty"] is True


def test_a_run_that_cannot_parse_its_summary_writes_a_result_saying_so(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    proc = _run(repo, "--", "--no-such-flag")
    assert proc.returncode == 4, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] == 4
    assert latest["counts"] is None and latest["summary_line"] is None
    assert latest["error"] == runner.NO_SUMMARY
    assert latest["ok"] is False
    assert latest["command"][-1] == "--no-such-flag"


def test_a_timeout_writes_a_result_saying_so_with_no_exit_code(tmp_path):
    repo = _checkout(tmp_path, "import time\ndef test_slow(): time.sleep(30)\n")
    proc = _run(repo, "--timeout", "2")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] is None
    assert latest["error"] == "timed out after 2 s; pytest was killed"
    assert latest["counts"] is None and latest["ok"] is False


def test_the_uv_directory_is_put_on_the_suite_path(tmp_path):
    uv_dir = tmp_path / "uvbin"
    uv_dir.mkdir()
    repo = _checkout(tmp_path, "import os\ndef test_path(): open('path.txt', 'w').write(os.environ['PATH'])\n")
    proc = _run(repo, env={"UV": str(uv_dir / "uv")})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / "path.txt").read_text().split(os.pathsep)[0] == str(uv_dir)


def test_an_empty_summary_after_a_kill_never_reads_as_ok():
    result = runner.build_result(
        started=datetime(2026, 9, 14, 2, 30, tzinfo=timezone.utc),
        finished=datetime(2026, 9, 14, 2, 31, tzinfo=timezone.utc),
        repo=_SCRIPT.parents[2],
        command=["pytest"],
        exit_code=0,
        output="",
        run_error=None,
    )
    assert result["ok"] is False and result["error"] == runner.NO_SUMMARY
