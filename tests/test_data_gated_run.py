"""The nightly runner's parser and result shape: pytest's own summary lines, then the runner driven
end to end over a synthetic checkout under `tmp_path` -- never this repo's suite or its `.local/` --
through a `uv` shim that records what it was handed and runs the suite with this test's interpreter.
The coverage upload is faked in this process; a run of the script goes through `_run`, which passes `--no-coverage`."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
import threading
import time
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.role_render import render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, truthy

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "data-gated-run.py"
_spec = importlib.util.spec_from_file_location("data_gated_run", _SCRIPT)
runner = importlib.util.module_from_spec(_spec)
sys.modules["data_gated_run"] = runner
_spec.loader.exec_module(runner)
_REAL_SEND = runner.send_coverage
_REAL_TOKEN_FILE = runner.TOKEN_FILE


@pytest.fixture(autouse=True)
def _no_token_file_and_no_upload(tmp_path, monkeypatch):
    """A raise here would be swallowed into a `failed` outcome by `coverage_upload`, so the double records each reach and
    the case fails at teardown."""
    monkeypatch.setattr(runner, "TOKEN_FILE", tmp_path / "no-token-file" / "coveralls.env")
    reached = []
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: reached.append(repo))
    yield
    assert not reached, f"the case reached the coverage upload without faking it, for {reached}"


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
    "/home/zhaow/Projects/zcrypto-kraken/data/ohlc-rolling/manifest.json absent -- the set is gitignored and not present on this machine",
    "data/ohlc-full absent — the canonical-host marker; the disk pass runs only where the data root is",
    "trade archive absent at /mnt/zhao-crypto/capture-segments — data-bearing workstation only",
    "no BTC/EUR trade segments under /mnt/zhao-crypto/capture-segments",
    "no heal-complete BTC/EUR day in the last 6 days under /mnt/zhao-crypto/capture-segments",
    "no local datasets (CI)",
    "data/ohlc-rolling absent — the staged base is on the data-bearing workstation only",
    "data/ohlc-rolling absent — the base's derivation is checked on the data-bearing workstation only",
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
    assert command[5:] == ["-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfEs", "-n", "8", "-k", "soak"]
    assert sys.executable not in command


# --- end to end over a synthetic checkout -----------------------------------------------------------

_GIT_IDENTITY = ("-c", "user.email=t@example.invalid", "-c", "user.name=t")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *_GIT_IDENTITY, *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _checkout(tmp_path: Path, body: str, *, data: bool = True, datasets: bool = True) -> Path:
    repo = tmp_path / "checkout"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests" / "test_synthetic.py").write_text(textwrap.dedent(body))
    if data:
        (repo / "data").mkdir()
        (repo / "data" / ".gitignore").write_text("*\n!.gitignore\n")
        if datasets:
            (repo / "data" / "ohlc-full").mkdir()
            (repo / "data" / "ohlc-full" / "manifest.json").write_text("{}\n")
    subprocess.run(["git", "init", "-q", "-b", "develop", str(repo)], check=True)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "synthetic")
    return repo


def _worktrees(repo: Path) -> list[str]:
    return [
        line.split(" ", 1)[1] for line in _git(repo, "worktree", "list", "--porcelain").splitlines() if line.startswith("worktree ")
    ]


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
    """`SYNTH_REPO` and `PROBE_OUT` are for the synthetic suite, which runs with the worktree as its cwd: the checkout it
    came from, and a file outside both trees to write what it saw."""
    shim = _fake_uv(tmp_path)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--repo", str(repo), "--no-coverage", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "UV": str(shim), "SYNTH_REPO": str(repo), "PROBE_OUT": str(tmp_path / "probe-out.txt"), **(env or {})},
    )


def _handed_to_uv(tmp_path: Path) -> list[str] | None:
    record = tmp_path / "uvbin" / "uv-argv"
    return record.read_text().splitlines() if record.is_file() else None


def _probe_out(tmp_path: Path) -> list[str]:
    return (tmp_path / "probe-out.txt").read_text().splitlines()


def _latest(repo: Path) -> dict:
    return json.loads((repo / ".local" / "data-gated-runs" / "latest.json").read_text())


def _no_worktree_left(repo: Path) -> None:
    assert _worktrees(repo) == [str(repo)], "the run's worktree is deregistered"
    left = sorted(p.name for p in (repo / runner.WORKTREE_DIR).iterdir()) if (repo / runner.WORKTREE_DIR).is_dir() else []
    assert left == [], f"the run's worktree directory is gone: {left}"


# What a synthetic test writes to PROBE_OUT, one value per line, read by `_probe_out`.
SEES_THE_TREE = """\
    import os
    from pathlib import Path
    def test_where(): Path(os.environ["PROBE_OUT"]).write_text(
        f"{os.getcwd()}\\n{os.path.realpath('data/ohlc-full')}\\n{Path('data/ohlc-full').is_symlink()}\\n"
        f"{os.environ.get('ZCRYPTO_DATA_GATED_DEVELOP', 'unset')}\\n")
    """


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
        "branch",
        "develop",
        "sha_at_end",
        "tree_moved",
        "worktree",
        "command",
        "exit_code",
        "summary_line",
        "counts",
        "failed",
        "errors",
        "data_gated_skipped",
        "swept",
        "sweep_left",
        "sweep_error",
        "teardown",
        "data_listing_intact",
        "data_listing",
        "error",
        "ok",
        "coverage_upload",
    }
    assert latest["schema"] == 4
    assert latest["coverage_upload"] == {"outcome": "skipped", "reason": "--no-coverage: the run measured none"}
    started, finished = (
        datetime.strptime(latest[k], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) for k in ("started", "finished")
    )
    assert before <= started <= finished
    head = _git(repo, "rev-parse", "HEAD")
    assert latest["sha"] == head and latest["dirty"] is False and latest["git_error"] is None
    assert latest["branch"] == "develop" and latest["develop"] is None, "the synthetic checkout has no origin/develop"
    assert latest["sha_at_end"] == head and latest["tree_moved"] is False
    assert latest["repo"] == str(repo) and latest["data_present"] is True
    worktree = latest["worktree"]
    assert worktree == str(repo / runner.WORKTREE_DIR / f"wt-{stamped[0].stem}")
    assert latest["command"] == [
        str(tmp_path / "uvbin" / "uv"),
        "run",
        "--directory",
        worktree,
        "python",
        "-m",
        "pytest",
        *runner.PYTEST_ARGS,
    ]
    assert latest["command"][1:] == _handed_to_uv(tmp_path), "the recorded command is the one uv was handed"
    assert sys.executable not in latest["command"]
    assert latest["teardown"] == {"worktree": worktree, "unlinked": ["ohlc-full"], "left": [], "removed": True, "error": None}
    assert latest["data_listing_intact"] is True and latest["data_listing"] is None
    _no_worktree_left(repo)
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
    # Sorted: eight workers report their skips in the order they finish.
    assert sorted(latest["data_gated_skipped"], key=lambda s: s["site"]) == [
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


def test_a_dirty_checkout_is_recorded_as_such_and_its_uncommitted_change_is_not_run(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    (repo / "tests" / "test_synthetic.py").write_text("def test_ok(): pass\ndef test_uncommitted(): assert False\n")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["dirty"] is True
    assert latest["ok"] is True and latest["counts"]["passed"] == 1 and latest["counts"]["failed"] == 0


def test_the_suite_runs_in_a_detached_worktree_at_the_start_sha_with_the_datasets_linked(tmp_path):
    repo = _checkout(tmp_path, SEES_THE_TREE)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    cwd, dataset, is_link, _ = _probe_out(tmp_path)
    assert cwd == latest["worktree"] != str(repo)
    assert cwd.startswith(str(repo / runner.WORKTREE_DIR / "wt-"))
    assert dataset == str(repo / "data" / "ohlc-full") and is_link == "True"
    assert "--directory" in _handed_to_uv(tmp_path) and str(repo) not in _handed_to_uv(tmp_path)


def test_a_head_that_moves_during_the_run_leaves_sha_at_the_start_and_reads_tree_moved(tmp_path):
    repo = _checkout(
        tmp_path,
        """\
        import os, subprocess
        def test_moves_the_tree():
            subprocess.run(["git", "-C", os.environ["SYNTH_REPO"], "-c", "user.email=t@example.invalid", "-c", "user.name=t",
                            "commit", "-q", "--allow-empty", "-m", "landed during the run"], check=True)
        """,
    )
    start = _git(repo, "rev-parse", "HEAD")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    end = _git(repo, "rev-parse", "HEAD")
    assert end != start
    latest = _latest(repo)
    assert latest["sha"] == start and latest["sha_at_end"] == end and latest["tree_moved"] is True
    assert latest["ok"] is True


def test_the_origin_develop_sha_at_start_is_handed_to_the_suite(tmp_path):
    repo = _checkout(tmp_path, SEES_THE_TREE)
    head = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/develop", head)
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _probe_out(tmp_path)[3] == head
    assert _latest(repo)["develop"] == head


def test_without_an_origin_develop_the_suite_sees_no_pin_not_an_inherited_one(tmp_path):
    repo = _checkout(tmp_path, SEES_THE_TREE)
    proc = _run(tmp_path, repo, env={runner.DEVELOP_ENV: "stale-from-the-runners-own-environment"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _probe_out(tmp_path)[3] == "unset"
    assert _latest(repo)["develop"] is None


def test_a_real_directory_under_the_worktrees_data_is_left_by_the_unlink_and_reported(tmp_path):
    repo = _checkout(
        tmp_path,
        """\
        import os
        def test_writes_under_data():
            os.mkdir("data/real-dir")
            open("data/real-dir/file", "w").write("x")
        """,
    )
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["teardown"]["unlinked"] == ["ohlc-full"] and latest["teardown"]["left"] == ["real-dir"]
    assert latest["teardown"]["removed"] is True and latest["teardown"]["error"] is None
    assert sorted(p.name for p in (repo / "data").iterdir()) == [".gitignore", "ohlc-full"]
    assert (repo / "data" / "ohlc-full" / "manifest.json").read_text() == "{}\n", "the dataset behind the link is whole"
    assert latest["data_listing_intact"] is True and latest["ok"] is True
    _no_worktree_left(repo)


def test_a_stale_worktree_from_a_night_that_never_tore_down_is_swept_at_start_and_recorded(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    stale = repo / runner.WORKTREE_DIR / "wt-20260101T000000Z"
    stale.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", "--detach", str(stale), "HEAD")
    os.symlink(repo / "data" / "ohlc-full", stale / "data" / "ohlc-full")
    assert len(_worktrees(repo)) == 2
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["swept"] == ["wt-20260101T000000Z"] and latest["sweep_left"] == [] and latest["sweep_error"] is None
    assert latest["ok"] is True and latest["worktree"] != str(stale)
    assert sorted(p.name for p in (repo / "data").iterdir()) == [".gitignore", "ohlc-full"]
    assert (repo / "data" / "ohlc-full" / "manifest.json").read_text() == "{}\n", "the dataset behind the swept link is whole"
    assert latest["data_listing_intact"] is True
    _no_worktree_left(repo)


def test_a_worktree_younger_than_the_bound_may_be_a_live_run_and_is_left_and_named(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    # A minute ago: inside the bound plus slack, and never the stamp the run picks for its own worktree.
    a_minute_ago = datetime.now(timezone.utc) - timedelta(seconds=60)
    young = repo / runner.WORKTREE_DIR / f"wt-{a_minute_ago.strftime('%Y%m%dT%H%M%SZ')}"
    young.parent.mkdir(parents=True)
    _git(repo, "worktree", "add", "--detach", str(young), "HEAD")
    os.symlink(repo / "data" / "ohlc-full", young / "data" / "ohlc-full")
    proc = _run(tmp_path, repo, "--timeout", "2")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["swept"] == [] and latest["sweep_left"] == [young.name] and latest["sweep_error"] is None
    assert latest["ok"] is True and latest["worktree"] != str(young)
    assert (young / "data" / "ohlc-full").is_symlink(), "the live run's link is untouched"
    assert sorted(_worktrees(repo)) == sorted([str(repo), str(young)])


def test_a_wt_directory_whose_name_is_not_a_stamp_is_left_and_named_not_removed(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    odd = repo / runner.WORKTREE_DIR / "wt-by-hand"
    odd.mkdir(parents=True)
    (odd / "keep").write_text("x")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["swept"] == [] and latest["sweep_left"] == ["wt-by-hand"] and latest["sweep_error"] is None
    assert latest["ok"] is True and (odd / "keep").read_text() == "x"


def test_a_clean_start_sweeps_nothing_and_records_the_empty_list(tmp_path):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["swept"] == [] and latest["sweep_left"] == [] and latest["sweep_error"] is None and latest["ok"] is True


def test_a_suite_that_writes_into_the_checkouts_data_is_caught_by_the_listing_and_fails_the_run(tmp_path):
    # One level down, as a write through the worktree's dataset link lands: a top-level listing would miss it.
    repo = _checkout(
        tmp_path,
        """\
        import os
        def test_intrudes():
            open(os.path.join(os.environ["SYNTH_REPO"], "data", "ohlc-full", "intruder.parquet"), "w").write("x")
        """,
    )
    proc = _run(tmp_path, repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["counts"]["passed"] == 1 and latest["exit_code"] == 0
    assert latest["data_listing_intact"] is False
    start, end = latest["data_listing"]["start"], latest["data_listing"]["end"]
    assert {entry[0] for entry in start} == {"data/.gitignore", "data/ohlc-full", "data/ohlc-full/manifest.json"}
    assert {entry[0] for entry in end} - {entry[0] for entry in start} == {"data/ohlc-full/intruder.parquet"}
    assert all(len(entry) == 3 and isinstance(entry[1], int) and isinstance(entry[2], int) for entry in start + end)
    assert latest["error"].startswith("the checkout's data/ listing changed during the run: ")
    assert "data/ohlc-full/intruder.parquet" in latest["error"]
    assert latest["ok"] is False
    assert proc.stdout.rstrip().splitlines()[-1].startswith("data-gated-run: FAIL exit=0 the checkout's data/ listing changed")


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


def test_a_timeout_writes_a_result_saying_so_with_no_exit_code_and_the_worktree_still_goes(tmp_path):
    repo = _checkout(tmp_path, "import time\ndef test_slow(): time.sleep(30)\n")
    proc = _run(tmp_path, repo, "--timeout", "2")
    assert proc.returncode == 1, proc.stdout + proc.stderr
    latest = _latest(repo)
    assert latest["exit_code"] is None
    assert latest["error"] == "timed out after 2 s; pytest was killed"
    assert latest["counts"] is None and latest["ok"] is False
    assert latest["duration_s"] < 10, "the kill reached pytest itself, not only the uv in front of it"
    assert latest["teardown"]["unlinked"] == ["ohlc-full"] and latest["teardown"]["removed"] is True
    assert sorted(p.name for p in (repo / "data").iterdir()) == [".gitignore", "ohlc-full"]
    _no_worktree_left(repo)


def test_an_exception_in_the_run_is_recorded_and_the_worktree_still_goes(tmp_path, monkeypatch):
    repo = _checkout(tmp_path, "def test_ok(): pass\n")

    def raises(worktree, uv, pytest_args, timeout, *, develop):
        assert Path(worktree).is_dir() and (Path(worktree) / "data" / "ohlc-full").is_symlink()
        raise RuntimeError("boom")

    monkeypatch.setattr(runner, "run_suite", raises)
    monkeypatch.setenv("UV", "/nonexistent/uv")
    code = runner.main(["--repo", str(repo), "--no-coverage"])
    latest = _latest(repo)
    assert code == 1 and latest["ok"] is False
    assert latest["error"] == "the runner raised RuntimeError: boom" and latest["exit_code"] is None
    assert latest["teardown"]["unlinked"] == ["ohlc-full"] and latest["teardown"]["removed"] is True
    _no_worktree_left(repo)


def test_the_uv_directory_is_put_on_the_suite_path(tmp_path):
    repo = _checkout(tmp_path, "import os\ndef test_path(): open(os.environ['PROBE_OUT'], 'w').write(os.environ['PATH'])\n")
    proc = _run(tmp_path, repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert _probe_out(tmp_path)[0].split(os.pathsep)[0] == str(tmp_path / "uvbin")


_STATE = {
    "sha": "a" * 40,
    "dirty": False,
    "git_error": None,
    "branch": "develop",
    "develop": None,
    "sha_at_end": "a" * 40,
    "tree_moved": False,
}
_LISTING = ([["data/.gitignore", 12, 1], ["data/ohlc-full", 4096, 1]], [["data/.gitignore", 12, 1], ["data/ohlc-full", 4096, 1]])


def _result(**overrides) -> dict:
    return runner.build_result(
        **{
            "started": datetime(2026, 9, 14, 2, 30, tzinfo=timezone.utc),
            "finished": datetime(2026, 9, 14, 2, 31, tzinfo=timezone.utc),
            "repo": _SCRIPT.parents[2],
            "data_present": True,
            "state": _STATE,
            "worktree": "/srv/main/.tmp/data-gated-run/wt-x",
            "command": ["pytest"],
            "exit_code": 0,
            "output": _PASSING,
            "run_error": None,
            "teardown": {
                "worktree": "/srv/main/.tmp/data-gated-run/wt-x",
                "unlinked": ["ohlc-full"],
                "left": [],
                "removed": True,
                "error": None,
            },
            "data_listing": _LISTING,
            "swept": [],
            "sweep_left": [],
            "sweep_error": None,
            **overrides,
        }
    )


def test_an_empty_summary_after_a_kill_never_reads_as_ok():
    result = _result(output="")
    assert result["ok"] is False and result["error"] == runner.NO_SUMMARY


def test_a_sweep_fault_is_the_runs_error_and_denies_ok():
    swept = _result(swept=["wt-20260101T000000Z"])
    assert swept["ok"] is True and swept["swept"] == ["wt-20260101T000000Z"] and swept["error"] is None
    faulted = _result(swept=["wt-20260101T000000Z"], sweep_error="wt-20260101T000000Z: git worktree remove exited 128: locked")
    assert faulted["ok"] is False and faulted["error"] == "sweep: wt-20260101T000000Z: git worktree remove exited 128: locked"


def test_a_teardown_fault_is_the_runs_error_beside_the_suites_own_and_fails_it():
    assert _result()["ok"] is True
    failed = _result(teardown={**_result()["teardown"], "removed": False, "error": "git worktree remove exited 128: locked"})
    assert failed["ok"] is False and failed["error"] == "teardown: git worktree remove exited 128: locked"
    both = _result(output=_FAILING, exit_code=1, teardown=failed["teardown"])
    assert both["error"] == "teardown: git worktree remove exited 128: locked" and both["failed"] == ["tests/t.py::t"]
    both = _result(run_error="timed out after 2 s; pytest was killed", output="", exit_code=None, teardown=failed["teardown"])
    assert both["error"] == "timed out after 2 s; pytest was killed; teardown: git worktree remove exited 128: locked"


# --- the coverage upload, its token file under `tmp_path` and the upload faked ------------------------------------------

TOKEN = "s3cret-repo-token"
JOB = {"message": "Job #7.1", "url": "https://coveralls.io/jobs/7"}
_HOLDS_THE_TOKEN = f"# the nightly's upload token\n\nCOVERALLS_REPO_TOKEN={TOKEN}\n"


def _token_file(tmp_path: Path, monkeypatch, body: str = _HOLDS_THE_TOKEN, mode: int = 0o600) -> Path:
    path = tmp_path / "coveralls.env"
    path.write_text(body)
    path.chmod(mode)
    monkeypatch.setattr(runner, "TOKEN_FILE", path)
    return path


def _absent(tmp_path: Path, monkeypatch) -> Path:
    path = tmp_path / "coveralls.env"
    monkeypatch.setattr(runner, "TOKEN_FILE", path)
    return path


def _a_directory(tmp_path: Path, monkeypatch) -> Path:
    path = _absent(tmp_path, monkeypatch)
    path.mkdir(mode=0o700)
    return path


def test_an_upload_records_the_url_coveralls_returns_for_the_token_files_token(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)
    sent = []
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: sent.append((repo, token)) or JOB)

    assert runner.coverage_upload(tmp_path, None) == {"outcome": "uploaded", "url": JOB["url"]}
    assert sent == [(tmp_path, TOKEN)]


@pytest.mark.parametrize(
    ("setup", "skip", "reason"),
    [
        pytest.param(_token_file, "a reason the run gives", "a reason the run gives", id="the-run-gives-a-reason"),
        pytest.param(_absent, None, "no token file at {path}", id="absent"),
        pytest.param(
            lambda t, m: _token_file(t, m, mode=0o640),
            None,
            "{path} has mode 0640: a group or other permission bit is refused",
            id="group-readable",
        ),
        pytest.param(
            lambda t, m: _token_file(t, m, mode=0o604),
            None,
            "{path} has mode 0604: a group or other permission bit is refused",
            id="other-readable",
        ),
        pytest.param(_a_directory, None, "{path} is not a regular file", id="a-directory"),
        pytest.param(
            lambda t, m: _token_file(t, m, "COVERALLS_REPO_TOKEN=\n"), None, "{path}'s COVERALLS_REPO_TOKEN is empty", id="empty"
        ),
        pytest.param(
            lambda t, m: _token_file(t, m, "# not yet\n\n"), None, "{path} holds no COVERALLS_REPO_TOKEN line", id="missing"
        ),
        pytest.param(
            lambda t, m: _token_file(t, m, f'# the nightly\'s upload token\nCOVERALLS_REPO_TOKEN="{TOKEN}"\n'),
            None,
            "{path} line 2 is not a COVERALLS_REPO_TOKEN=<token> line",
            id="malformed",
        ),
        pytest.param(
            lambda t, m: _token_file(t, m, f"COVERALLS_REPO_TOKEN={TOKEN}\nCOVERALLS_REPO_TOKEN=another\n"),
            None,
            "{path} line 2 is a second COVERALLS_REPO_TOKEN line",
            id="a-second-token-line",
        ),
    ],
)
def test_a_skipped_upload_says_why_and_sends_nothing(tmp_path, monkeypatch, setup, skip, reason):
    path = setup(tmp_path, monkeypatch)

    outcome = runner.coverage_upload(tmp_path, skip)

    assert outcome == {"outcome": "skipped", "reason": reason.format(path=path)}
    assert TOKEN not in json.dumps(outcome)


def test_a_token_file_another_uid_owns_is_refused(tmp_path, monkeypatch):
    path = _token_file(tmp_path, monkeypatch)
    mine = os.getuid()
    monkeypatch.setattr(os, "getuid", lambda: mine + 1)

    outcome = runner.coverage_upload(tmp_path, None)

    assert outcome == {"outcome": "skipped", "reason": f"{path} is owned by uid {mine}, not this run's uid {mine + 1}"}


def test_a_failed_upload_records_its_class_and_a_message_without_the_token(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)

    def refused(repo, token, branch):
        raise ConnectionError(f"coveralls.io answered 504 to repo_token={token}")

    monkeypatch.setattr(runner, "send_coverage", refused)

    outcome = runner.coverage_upload(tmp_path, None)

    assert outcome == {
        "outcome": "failed",
        "error_class": "ConnectionError",
        "message": "coveralls.io answered 504 to repo_token=<token>",
    }
    assert TOKEN not in json.dumps(outcome)


def test_an_answer_without_a_url_fails(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: {"message": "Job #7.1"})

    outcome = runner.coverage_upload(tmp_path, None)

    assert outcome["outcome"] == "failed" and outcome["error_class"] == "KeyError", outcome


def test_an_upload_with_no_answer_is_cut_off_and_fails(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)
    released = threading.Event()
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: released.wait(30) and JOB)
    monkeypatch.setattr(runner, "UPLOAD_TIMEOUT_S", 0.2)
    began = time.monotonic()
    try:
        outcome = runner.coverage_upload(tmp_path, None)
    finally:
        released.set()

    assert outcome == {"outcome": "failed", "error_class": "TimeoutError", "message": "no answer within 0.2 s"}
    assert time.monotonic() - began < 10


def test_the_upload_runs_coveralls_in_the_checkout_with_the_token_and_the_service(tmp_path, monkeypatch):
    seen = {}

    class Coveralls:
        def __init__(self, **config):
            seen["config"] = config

        def wear(self):
            seen["cwd"] = Path.cwd()
            seen["branch"] = os.environ.get("GIT_BRANCH")
            return JOB

    fake = types.ModuleType("coveralls")
    fake.Coveralls = Coveralls
    monkeypatch.setitem(sys.modules, "coveralls", fake)
    monkeypatch.delenv("GIT_BRANCH", raising=False)
    before = Path.cwd()

    assert _REAL_SEND(tmp_path, TOKEN, "develop") == JOB
    assert seen == {"config": {"repo_token": TOKEN, "service_name": runner.COVERALLS_SERVICE}, "cwd": tmp_path, "branch": "develop"}
    assert Path.cwd() == before and "GIT_BRANCH" not in os.environ


_PASSING = "..\n2 passed in 0.10s\n"
_FAILING = "===== short test summary info =====\nFAILED tests/t.py::t - x\n1 failed, 1 passed in 0.10s\n"


def _main(tmp_path: Path, monkeypatch, output: str, exit_code: int, *args: str) -> tuple[int, dict, list[list[str]]]:
    """`main` over a checkout holding a dataset, with pytest's run replaced by `output` and `exit_code`."""
    repo = tmp_path / "checkout" if (tmp_path / "checkout").is_dir() else _checkout(tmp_path, "def test_ok(): pass\n")
    handed = []

    def run_suite(worktree, uv, pytest_args, timeout, *, develop):
        handed.append(list(pytest_args))
        return ["pytest", *pytest_args], exit_code, output, None

    monkeypatch.setattr(runner, "run_suite", run_suite)
    monkeypatch.setenv("UV", "/nonexistent/uv")
    code = runner.main(["--repo", str(repo), *args])
    return code, json.loads((repo / ".local" / "data-gated-runs" / "latest.json").read_text()), handed


def test_the_coverage_upload_runs_in_the_worktree_before_it_goes(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)
    seen = []
    monkeypatch.setattr(
        runner, "send_coverage", lambda repo, token, branch: seen.append((repo, Path(repo).is_dir(), branch)) or JOB
    )

    code, result, _ = _main(tmp_path, monkeypatch, _PASSING, 0)

    assert code == 0 and result["coverage_upload"] == {"outcome": "uploaded", "url": JOB["url"]}
    assert seen == [(Path(result["worktree"]), True, "develop")]
    assert result["worktree"] != str(tmp_path / "checkout") and not Path(result["worktree"]).exists()


@pytest.mark.parametrize(("output", "exit_code"), [(_PASSING, 0), (_FAILING, 1)], ids=["passing", "failing"])
def test_an_upload_that_raises_leaves_the_verdict_and_the_exit_status(tmp_path, monkeypatch, output, exit_code):
    _token_file(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: JOB)
    code_up, uploaded, _ = _main(tmp_path, monkeypatch, output, exit_code)

    def raises(repo, token, branch):
        raise RuntimeError("coveralls.io is down")

    monkeypatch.setattr(runner, "send_coverage", raises)
    code_down, failed, _ = _main(tmp_path, monkeypatch, output, exit_code)

    assert uploaded["coverage_upload"]["outcome"] == "uploaded" and failed["coverage_upload"]["outcome"] == "failed"
    assert code_down == code_up == exit_code
    verdict = ("ok", "error", "exit_code", "counts", "failed", "errors")
    assert {k: failed[k] for k in verdict} == {k: uploaded[k] for k in verdict}


@pytest.mark.parametrize(
    ("output", "args", "pytest_args", "reason"),
    [
        pytest.param(
            "pytest: error: no such thing\n",
            [],
            list(runner.COVERAGE_ARGS),
            f"no parsed pytest summary ({runner.NO_SUMMARY})",
            id="no-parsed-summary",
        ),
        pytest.param(
            _PASSING,
            ["--", "-k", "soak"],
            ["-k", "soak"],
            "extra pytest args: the run measured none, since a part of the suite is not the whole",
            id="extra-args",
        ),
        pytest.param(_PASSING, ["--no-coverage"], [], "--no-coverage: the run measured none", id="no-coverage"),
    ],
)
def test_the_run_measures_coverage_whole_and_uploads_only_a_parsed_runs(tmp_path, monkeypatch, output, args, pytest_args, reason):
    _token_file(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: JOB)

    _, result, handed = _main(tmp_path, monkeypatch, output, 0, *args)

    assert handed == [pytest_args]
    assert result["coverage_upload"] == {"outcome": "skipped", "reason": reason}


def test_a_whole_parsed_run_measures_coverage_and_uploads_it(tmp_path, monkeypatch):
    _token_file(tmp_path, monkeypatch)
    monkeypatch.setattr(runner, "send_coverage", lambda repo, token, branch: JOB)

    code, result, handed = _main(tmp_path, monkeypatch, _PASSING, 0)

    assert handed == [["--cov=cli", "--cov-report="]]
    assert code == 0 and result["ok"] is True
    assert result["coverage_upload"] == {"outcome": "uploaded", "url": JOB["url"]}


# --- the ops role renders the file the runner reads -------------------------------------------------------------------

_OPS = _SCRIPT.parents[1] / "ansible" / "roles" / "ops"
_OPS_TASKS = _OPS / "tasks" / "main.yml"
_TOKEN_DIR_TASK = "ensure the research user's zcrypto config directory exists (owner-only)"
_TOKEN_RENDER_TASK = "render the nightly's Coveralls token env file (owner-only)"
_RESEARCH_HOME = "~{{ ops_research_user }}"


def test_the_ops_role_renders_the_token_file_where_the_runner_reads_it():
    tasks = load_tasks(_OPS_TASKS)
    in_home = _REAL_TOKEN_FILE.relative_to(Path.home())

    assert find_task(tasks, _TOKEN_RENDER_TASK)["ansible.builtin.template"]["dest"] == f"{_RESEARCH_HOME}/{in_home.as_posix()}"
    assert find_task(tasks, _TOKEN_DIR_TASK)["ansible.builtin.file"]["path"] == f"{_RESEARCH_HOME}/{in_home.parent.as_posix()}"


@pytest.mark.parametrize(
    ("name", "module", "mode"),
    [(_TOKEN_DIR_TASK, "ansible.builtin.file", "0700"), (_TOKEN_RENDER_TASK, "ansible.builtin.template", "0600")],
    ids=["directory", "file"],
)
def test_the_token_file_and_its_directory_are_the_research_users_alone(name, module, mode):
    args = find_task(load_tasks(_OPS_TASKS), name)[module]

    assert (args["owner"], args["group"], args["mode"]) == ("{{ ops_research_user }}", "{{ ops_research_user }}", mode)


def test_the_token_render_is_never_logged_and_runs_on_a_digestless_converge_once_the_user_and_the_token_exist():
    tasks = load_tasks(_OPS_TASKS)
    render_task = find_task(tasks, _TOKEN_RENDER_TASK)
    gates = {task.get("name"): list(gated) for task, gated in iter_tasks(tasks)}
    present = {"ops_research_probe": {"rc": 0}, "coveralls_repo_token": TOKEN}

    assert render_task.get("no_log") is True and render_task.get("diff") is False
    assert truthy(gates[_TOKEN_DIR_TASK], present) and truthy(gates[_TOKEN_RENDER_TASK], present)
    assert not truthy(gates[_TOKEN_RENDER_TASK], {**present, "ops_research_probe": {"rc": 2}})
    assert not truthy(gates[_TOKEN_RENDER_TASK], {"ops_research_probe": {"rc": 0}})


def test_the_rendered_token_file_is_one_line_the_runner_reads_the_token_from(tmp_path, monkeypatch):
    rendered = render(_OPS, "coveralls.env.j2", {"coveralls_repo_token": TOKEN})

    assert [line for line in rendered.splitlines() if not line.startswith("#")] == [f"COVERALLS_REPO_TOKEN={TOKEN}"]
    _token_file(tmp_path, monkeypatch, rendered)
    assert runner.read_coverage_token() == TOKEN
