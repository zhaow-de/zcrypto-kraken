"""The nightly runner's parser and result shape: pytest's own summary lines, then the runner driven
end to end over a synthetic checkout under `tmp_path` -- never this repo's suite or its `.local/` --
through a `uv` shim that records what it was handed and runs the suite with this test's interpreter."""

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

# The tail of `pytest -q -p no:cacheprovider -rfEs` over one pass, one fail, three skips, one xfail and
# one fixture error, as pytest printed it; the message on a -q short-summary line is cut to the
# terminal width, the id never is. The two lines above the rule are a test's own captured output.
MIXED = textwrap.dedent("""\
    ERROR    cli.engine:cycle.py:12 a captured log line above the rule is not an id
    SKIPPED [9] tests/test_shapes.py:1: canonical dataset not present -- printed by a test, above the rule
    E   AssertionError: one is not two
    E   assert 1 == 2

    tests/test_shapes.py:3: AssertionError
    =========================== short test summary info ============================
    FAILED tests/test_shapes.py::test_fail - AssertionError: one...
    ERROR tests/test_shapes.py::test_err - RuntimeError: fixture...
    SKIPPED [1] tests/test_shapes.py:9: root bypasses directory permissions
    SKIPPED [2] tests/test_shapes.py:12: canonical dataset not present
    1 failed, 1 passed, 3 skipped, 1 xfailed, 1 error in 0.01s
    """)


def test_the_mixed_summary_line_yields_every_count_and_the_ids():
    parsed = runner.parse_summary(MIXED)
    assert parsed["error"] is None
    assert parsed["summary_line"] == "1 failed, 1 passed, 3 skipped, 1 xfailed, 1 error in 0.01s"
    assert parsed["counts"] == {
        "passed": 1,
        "failed": 1,
        "skipped": 3,
        "errors": 1,
        "xfailed": 1,
        "xpassed": 0,
        "deselected": 0,
        "warnings": 0,
    }
    assert parsed["failed"] == ["tests/test_shapes.py::test_fail"]
    assert parsed["errors"] == ["tests/test_shapes.py::test_err"]


def test_only_the_skips_whose_reason_says_data_was_absent_are_data_gated():
    parsed = runner.parse_summary(MIXED)
    assert parsed["data_gated_skipped"] == [
        {"site": "tests/test_shapes.py:12", "reason": "canonical dataset not present", "count": 2}
    ]


def test_a_captured_line_starting_with_error_or_skipped_above_the_rule_is_not_a_finding():
    parsed = runner.parse_summary(MIXED)
    assert all("captured log line" not in i for i in parsed["errors"])
    assert all("above the rule" not in s["reason"] for s in parsed["data_gated_skipped"])


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
    assert parsed["failed"] == [] and parsed["errors"] == [] and parsed["data_gated_skipped"] == []


@pytest.mark.parametrize(
    "line,expected",
    [
        ("FAILED tests/t.py::test_dash[a - b] - AssertionError: x", "tests/t.py::test_dash[a - b]"),
        ("FAILED tests/t.py::test_dash[a - b]", "tests/t.py::test_dash[a - b]"),
        ("FAILED tests/t.py::test_nested[k[0]] - KeyError: 'k'", "tests/t.py::test_nested[k[0]]"),
        ("FAILED tests/t.py::test_plain - AssertionError: row[0] - 1 != 2", "tests/t.py::test_plain"),
        ("FAILED tests/test_x.py::test_long_name_cut_before_the_dash", "tests/test_x.py::test_long_name_cut_before_the_dash"),
        ("ERROR tests/test_bad.py - ImportError: no module", "tests/test_bad.py"),
    ],
)
def test_an_id_is_kept_whole_through_a_spaced_dash_in_its_parameter_or_a_cut_message(line, expected):
    text = "===== short test summary info =====\n" + line + "\n1 failed in 0.01s\n"
    parsed = runner.parse_summary(text)
    assert parsed["failed"] + parsed["errors"] == [expected]


# One reason per shape this tree's skip gates give, each in the direction the runner must read it:
# the first block is a dataset that is not on this machine, the second the suite's own gates. What
# may enter: the line as the runner reads it on a `SKIPPED` line -- a template's rendered line,
# never its source, a host path spelled as this workstation renders it (the mount from
# zcrypto.toml, the checkout's absolute path), a run-time date as one run printed it -- and only a
# skip's reason, never an event's or a verdict's `reason=`.
_DATA_ABSENT_REASONS = [
    "canonical dataset not present",
    "gitignored snapshots dataset absent",
    "generated (gitignored) universe JSON absent — see docs/universe/*.md",
    "derivatives-oi substrate absent",
    "derivatives-funding substrate absent",
    "needs the hot hub mounted",
    "needs the local reach sibling",
    "no local datasets (CI); the writers are covered separately",
    "canonical data/ohlc-full absent",
    "ops journal mirror absent",
    "data/ohlc-full absent — the record-44 control runs on the data-bearing workstation only",
    "panel tree not mounted",
    "no refdata snapshot present (gitignored data root)",
    "data/ohlc-15m/manifest.json absent — off-workstation; the 15m byte anchor is data-gated",
    "ohlc-full not present on this node",
    "ohlc-15m not on this host — data-bearing workstation only",
    "gitignored refdata snapshot absent",
    "engine journal mount not present",
    "/home/zhaow/Projects/zcrypto-kraken/data/ohlc-reach-20260813/manifest.json absent -- the set is gitignored and not present on this machine",
    "data/ohlc-full absent — the canonical-host marker; the disk pass runs only where the data root is",
    "trade archive absent at /mnt/zhao-crypto/capture-segments — data-bearing workstation only",
    "no BTC/EUR trade segments under /mnt/zhao-crypto/capture-segments",
    "no heal-complete BTC/EUR day in the last 6 days under /mnt/zhao-crypto/capture-segments",
    "no local datasets (CI)",
]
_OWN_GATE_REASONS = [
    "needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it",
    "root bypasses directory permissions",
    "root ignores the directory's write bit",
    "main() refuses a checkout with no develop ref before any entry runs",
    "jq not available, so the push's own payload program cannot be run",
    "bash not available",
    "no schema-4 records yet — nothing in the registry cites observed bytes",
    "could not import 'jinja2': No module named 'jinja2'",
    "five counts read the develop ref by name, and this checkout has none",
    "reaches Kraken's public listing endpoint -- set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it",
    "root bypasses file permissions",
    "sed not available",
    "ZCRYPTO_LIVE_VENUE_TESTS=1 not set; this reaches the live venue",
    "ZCRYPTO_LIVE_VENUE_TESTS=1 deliberately opens the doors this asserts are shut",
]


@pytest.mark.parametrize("reason", _DATA_ABSENT_REASONS)
def test_a_reason_naming_an_absent_dataset_is_data_gated(reason):
    assert runner.is_data_absence(reason)


@pytest.mark.parametrize("reason", _OWN_GATE_REASONS)
def test_a_reason_from_the_suites_own_gates_is_not(reason):
    assert not runner.is_data_absence(reason)


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


def test_the_command_runs_through_the_target_checkouts_environment_not_this_one():
    command = runner.pytest_command(Path("/srv/main"), "/opt/uv", ["-k", "soak"])
    assert command[:5] == ["/opt/uv", "run", "--directory", "/srv/main", "python"]
    assert command[5:] == ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfEs", "-k", "soak"]
    assert sys.executable not in command


# --- end to end over a synthetic checkout -----------------------------------------------------------


def _checkout(tmp_path: Path, body: str, *, data: bool = True, datasets: bool = True) -> Path:
    """`data=False` leaves no `data/` at all; `datasets=False` gives it the `.gitignore` git tracks and nothing
    else, which is what a fresh worktree of the real repo carries."""
    repo = tmp_path / "checkout"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_synthetic.py").write_text(textwrap.dedent(body))
    if data:
        (repo / "data").mkdir()
        (repo / "data" / ".gitignore").write_text("*\n!.gitignore\n")
        if datasets:
            (repo / "data" / "ohlc-full").mkdir()
    git = ["git", "-C", str(repo), "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-q", "-m", "synthetic"], check=True)
    return repo


def _fake_uv(tmp_path: Path) -> Path:
    """A `uv` that writes its argv to `uv-argv` beside itself, then does what `uv run --directory
    <repo> python ...` does through this test's own interpreter -- no second venv, no network."""
    uv_dir = tmp_path / "uvbin"
    uv_dir.mkdir(exist_ok=True)
    shim = uv_dir / "uv"
    shim.write_text(
        textwrap.dedent(f"""\
            #!/usr/bin/env bash
            printf '%s\\n' "$@" > "{uv_dir / "uv-argv"}"
            [[ $1 == run && $2 == --directory && $4 == python ]] || {{ echo "fake uv: unexpected argv: $*" >&2; exit 97; }}
            cd "$3" || exit 98
            shift 4
            exec "{sys.executable}" "$@"
            """)
    )
    shim.chmod(0o755)
    return shim


def _run(tmp_path: Path, repo: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    shim = _fake_uv(tmp_path)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo", str(repo), *args],
        capture_output=True,
        text=True,
        env={**os.environ, "UV": str(shim), **(env or {})},
    )


def _handed_to_uv(tmp_path: Path) -> list[str] | None:
    record = tmp_path / "uvbin" / "uv-argv"
    return record.read_text().splitlines() if record.is_file() else None


def _latest(repo: Path) -> dict:
    return json.loads((repo / ".local" / "data-gated-runs" / "latest.json").read_text())


MIXED_SUITE = """\
    import pytest
    def test_ok(): pass
    def test_fail(): assert 1 == 2, "one is not two"
    @pytest.mark.skipif(True, reason="root bypasses directory permissions")
    def test_skip(): pass
    """

OWN_GATE_SUITE = """\
    import pytest
    def test_ok(): pass
    @pytest.mark.skipif(True, reason="root bypasses directory permissions")
    def test_skip(): pass
    """

DATA_GATED_SUITE = """\
    import pytest
    from pathlib import Path
    @pytest.mark.skipif(not Path("data/ohlc-full/BTC/EUR/240.parquet").exists(), reason="canonical dataset not present")
    def test_needs_the_dataset(): pass
    @pytest.mark.skipif(not Path("data/ohlc-full/BTC/EUR/240.parquet").exists(), reason="canonical dataset not present")
    def test_needs_it_too(): pass
    def test_ok(): pass
    """


def test_the_runner_writes_the_stamped_file_and_latest_with_the_full_shape(tmp_path):
    repo = _checkout(tmp_path, MIXED_SUITE)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    proc = _run(tmp_path, repo)
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
        "data_present",
        "sha",
        "dirty",
        "git_error",
        "command",
        "exit_code",
        "summary_line",
        "counts",
        "failed",
        "errors",
        "data_gated_skipped",
        "error",
        "ok",
    }
    started, finished = (
        datetime.strptime(latest[k], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for k in ("started", "finished")
    )
    assert before <= started <= finished
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert latest["sha"] == head and latest["dirty"] is False and latest["git_error"] is None
    assert latest["repo"] == str(repo) and latest["data_present"] is True
    assert latest["command"] == [
        str(tmp_path / "uvbin" / "uv"),
        "run",
        "--directory",
        str(repo),
        "python",
        "-m",
        "pytest",
        *runner.PYTEST_ARGS,
    ]
    assert latest["command"][1:] == _handed_to_uv(tmp_path), "the recorded command is the one uv was handed"
    assert sys.executable not in latest["command"]
    assert latest["exit_code"] == 1
    assert latest["counts"]["passed"] == 1 and latest["counts"]["failed"] == 1 and latest["counts"]["skipped"] == 1
    assert latest["failed"] == ["tests/test_synthetic.py::test_fail"]
    assert latest["errors"] == [] and latest["data_gated_skipped"] == [] and latest["error"] is None
    assert latest["ok"] is False
    assert "one is not two" in proc.stdout, "pytest's own output is re-emitted for the journal"
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: FAIL exit=1 ")


def test_a_passing_suite_reads_ok_and_the_runner_exits_zero(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["ok"] is True and latest["exit_code"] == 0 and latest["failed"] == []
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: ok exit=0 1 passed in ")


def test_a_data_gated_skip_fails_the_run_and_names_its_sites(tmp_path):
    """The night this exists to catch: pytest exits 0 with the whole family skipped for want of data."""
    repo = _checkout(tmp_path, DATA_GATED_SUITE)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] == 0 and latest["counts"]["skipped"] == 2 and latest["counts"]["passed"] == 1
    assert latest["data_gated_skipped"] == [
        {"site": "tests/test_synthetic.py:3", "reason": "canonical dataset not present", "count": 1},
        {"site": "tests/test_synthetic.py:5", "reason": "canonical dataset not present", "count": 1},
    ]
    assert latest["error"] == "2 data-gated tests skipped: data absent"
    assert latest["ok"] is False
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: FAIL exit=0 2 data-gated tests skipped: data absent")


def test_a_skip_by_the_suites_own_gate_is_not_a_finding(tmp_path):
    repo = _checkout(tmp_path, OWN_GATE_SUITE)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["counts"]["skipped"] == 1 and latest["data_gated_skipped"] == []
    assert latest["error"] is None and latest["ok"] is True


def test_a_checkout_without_data_is_refused_before_anything_runs(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n", data=False)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["data_present"] is False
    assert latest["command"] is None and latest["exit_code"] is None and latest["counts"] is None
    assert latest["error"] == f"data absent: {repo / 'data'} holds no dataset; nothing ran"
    assert latest["ok"] is False
    assert _handed_to_uv(tmp_path) is None, "uv was never called"
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: FAIL exit=None data absent: ")


def test_a_checkout_whose_data_holds_only_its_gitignore_is_refused_too(tmp_path):
    """The shape a worktree of this repo actually has: `data/.gitignore` is tracked, so git materialises `data/`
    everywhere and `is_dir()` would call an empty worktree data-bearing and run the whole family into skips."""
    repo = _checkout(tmp_path, "def test_ok(): pass\n", datasets=False)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["data_present"] is False and latest["ok"] is False
    assert latest["error"] == f"data absent: {repo / 'data'} holds no dataset; nothing ran"
    assert _handed_to_uv(tmp_path) is None, "uv was never called"


def test_a_repo_that_is_not_a_directory_is_a_usage_error_and_writes_nothing(tmp_path):
    proc = _run(tmp_path, tmp_path / "nowhere")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert not (tmp_path / "nowhere").exists(), "a typo in --repo must not create a tree"


def test_a_dirty_checkout_is_recorded_as_such(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    (repo / "tests" / "test_synthetic.py").write_text("def test_ok(): pass\ndef test_two(): pass\n")
    _run(tmp_path, repo)
    assert _latest(repo)["dirty"] is True


def test_a_run_that_cannot_parse_its_summary_writes_a_result_saying_so(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    proc = _run(tmp_path, repo, "--", "--no-such-flag")
    assert proc.returncode == 4, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] == 4
    assert latest["counts"] is None and latest["summary_line"] is None
    assert latest["error"] == runner.NO_SUMMARY
    assert latest["ok"] is False
    assert latest["command"][-1] == "--no-such-flag"


def test_a_timeout_writes_a_result_saying_so_with_no_exit_code(tmp_path):
    repo = _checkout(tmp_path, "import time\ndef test_slow(): time.sleep(30)\n")
    proc = _run(tmp_path, repo, "--timeout", "2")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] is None
    assert latest["error"] == "timed out after 2 s; pytest was killed"
    assert latest["counts"] is None and latest["ok"] is False
    assert latest["duration_s"] < 10, "the kill reached pytest itself, not only the uv in front of it"


def test_the_uv_directory_is_put_on_the_suite_path(tmp_path):
    repo = _checkout(tmp_path, "import os\ndef test_path(): open('path.txt', 'w').write(os.environ['PATH'])\n")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert (repo / "path.txt").read_text().split(os.pathsep)[0] == str(tmp_path / "uvbin")


def test_an_empty_summary_after_a_kill_never_reads_as_ok():
    result = runner.build_result(
        started=datetime(2026, 9, 14, 2, 30, tzinfo=timezone.utc),
        finished=datetime(2026, 9, 14, 2, 31, tzinfo=timezone.utc),
        repo=_SCRIPT.parents[2],
        data_present=True,
        command=["pytest"],
        exit_code=0,
        output="",
        run_error=None,
    )
    assert result["ok"] is False and result["error"] == runner.NO_SUMMARY
