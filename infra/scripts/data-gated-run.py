#!/usr/bin/env python3
"""Run the whole test suite from a checkout where the datasets are present, write the result as JSON, upload its coverage.

CI deselects the `retired` cases and skips every `skipif(not <data>.exists())` test, so this run, which
`infra/systemd/zcrypto-data-gated-tests.timer` fires nightly, is the one with the whole suite in scope and so the one
coverage report. It runs pytest with no path through the TARGET checkout's own environment (`uv run --directory
<repo>`), never the interpreter that launched it: a hand run from a worktree would otherwise import the worktree's `cli`
under the main checkout's tests. It writes `.local/data-gated-runs/<UTC stamp>.json` plus `latest.json`. A run in which
the whole family skipped for want of data is exactly the night this exists to catch, so such a skip is a failure, and a
checkout with no dataset under `data/` is refused before pytest starts. A run whose summary cannot be parsed -- a usage
error, a timeout, an interrupted session -- still writes a result, because `zcrypto-daily-ops` has to tell an absent
file from a failed run. `-rfE` rather than the bare `-rf`: an error at setup is a test that did not run, and its id is
as much a finding as a failure's.

The coverage upload is cut off after UPLOAD_TIMEOUT_S: the unit is a oneshot, and a run that never ends writes no result
and holds off the next night's.

Python rather than shell because the parser is the substance and `tests/test_data_gated_run.py` imports it; a JSON
writer in bash is a hand-rolled serialiser.

Usage: data-gated-run.py [--repo <checkout>] [--timeout <seconds>] [--no-coverage] [-- <extra pytest args>]
The unit passes nothing: the extra args are for a hand run (`-- -k soak`), never the nightly one.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

PYTEST_ARGS = ("-q", "-p", "no:cacheprovider", "-rfEs")
# The data file only, `.coverage` at the checkout's root: the upload reads it, and a report would only lengthen the journal.
COVERAGE_ARGS = ("--cov=cli", "--cov-report=")
COVERAGE_TOKEN_VAR = "coveralls_repo_token"
COVERALLS_SERVICE = "zcrypto-nightly"
UPLOAD_TIMEOUT_S = 120.0
_AUTH = Path(__file__).resolve().parent / "grafana_auth.py"
RESULT_DIR = Path(".local") / "data-gated-runs"
SCHEMA = 3
# `1 failed, 2 passed, 1 error in 0.01s`, `no tests ran in 0.00s`, `3 passed in 65.12s (0:01:05)` --
# with or without the `=` rule a non-quiet run draws around the line.
_SUMMARY = re.compile(r"^=*\s*(?P<body>\d+ [a-z]+(?:, \d+ [a-z]+)*|no tests ran) in \d+(?:\.\d+)?s(?: \([\d:]+\))?\s*=*$")
_COUNT = re.compile(r"(\d+) ([a-z]+)")
_SHORT_SUMMARY_RULE = "short test summary info"
# A `-rfE` line is `FAILED <id> - <message>`, the message cut to the terminal width or absent. The id
# is a run of non-space characters plus the `[...]` a parametrized id carries -- which may hold a
# spaced dash of its own -- so it is not cut at the first ` - `.
_ID = re.compile(r"^(?P<id>[^\s\[]+(?:\[.*?\])?)(?: - |$)")
# A `-rs` line: `SKIPPED [2] tests/test_x.py:12: canonical dataset not present`, one per (site, reason).
_SKIPPED = re.compile(r"^SKIPPED \[(?P<count>\d+)\] (?P<site>\S+?):(?: (?P<reason>.*))?$")
# The reasons this tree's gates give for a dataset that is not on this machine (`grep -rn skipif
# tests/*.py`, `grep -rn 'pytest.skip(' tests/*.py`), matched by their vocabulary so a new gate in the
# same voice is caught without a list to keep.
_DATA_ABSENCE = re.compile(
    r"dataset|\bdata[/ -]|substrate|snapshot|refdata|universe JSON|manifest|\bhub\b|mount|"
    r"archive|segments|journal mirror|gitignored|off-workstation|on this (?:node|host|machine)",
    re.IGNORECASE,
)
# pytest writes one `error`/`warning` in the singular; the result keys are plural whatever the count.
_PLURAL = {"error": "errors", "warning": "warnings"}
COUNT_KEYS = ("passed", "failed", "skipped", "errors", "xfailed", "xpassed", "deselected", "warnings")
NO_SUMMARY = "no pytest summary line in the output"


def is_data_absence(reason: str) -> bool:
    return _DATA_ABSENCE.search(reason) is not None


def parse_summary(output: str) -> dict:
    """Counts, ids and data-gated skips from pytest's tail, or `error` naming what was missing.

    The summary line is the LAST line the pattern matches; the ids and skips are the `FAILED`,
    `ERROR` and `SKIPPED` lines between the last `short test summary info` rule and that line, so a
    captured log line that starts with `ERROR` above the rule is never read as a test id."""
    lines = output.splitlines()
    summary_at = next((i for i in range(len(lines) - 1, -1, -1) if _SUMMARY.match(lines[i].strip())), None)
    empty = {"summary_line": None, "counts": None, "failed": [], "errors": [], "data_gated_skipped": [], "error": NO_SUMMARY}
    if summary_at is None:
        return empty
    line = lines[summary_at].strip()
    counts = dict.fromkeys(COUNT_KEYS, 0)
    for n, word in _COUNT.findall(_SUMMARY.match(line).group("body")):
        counts[_PLURAL.get(word, word)] = int(n)
    rule_at = next((i for i in range(summary_at - 1, -1, -1) if _SHORT_SUMMARY_RULE in lines[i]), None)
    failed: list[str] = []
    errors: list[str] = []
    data_gated: list[dict] = []
    if rule_at is not None:
        for raw in lines[rule_at + 1 : summary_at]:
            for prefix, bucket in (("FAILED ", failed), ("ERROR ", errors)):
                if raw.startswith(prefix):
                    bucket.append(_id(raw[len(prefix) :]))
            skip = _SKIPPED.match(raw)
            if skip and is_data_absence(skip.group("reason") or ""):
                data_gated.append(
                    {"site": skip.group("site"), "reason": skip.group("reason") or "", "count": int(skip.group("count"))}
                )
    return {
        "summary_line": line,
        "counts": counts,
        "failed": failed,
        "errors": errors,
        "data_gated_skipped": data_gated,
        "error": None,
    }


def _id(rest: str) -> str:
    m = _ID.match(rest)
    return m.group("id") if m else rest.strip()


def git_state(repo: Path) -> dict:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        return {"sha": None, "dirty": None, "git_error": head.stderr.strip() or f"git rev-parse exited {head.returncode}"}
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"sha": head.stdout.strip(), "dirty": bool(status.stdout.strip()), "git_error": None}


def pytest_command(repo: Path, uv: str, extra_args: list[str]) -> list[str]:
    """Through the target checkout's own environment -- `uv run --directory` enters and syncs that
    checkout's `.venv` -- never `sys.executable`, which is whatever environment launched this runner."""
    return [uv, "run", "--directory", str(repo), "python", "-m", "pytest", *PYTEST_ARGS, *extra_args]


def run_suite(repo: Path, uv: str, extra_args: list[str], timeout: float | None) -> tuple[list[str], int | None, str, str | None]:
    """`(command, exit code, combined output, why there is no exit code)`.

    A user unit carries the manager's bare PATH, so the directory of the `uv` this run goes through is
    prepended for a test that shells out to `uv`. The suite runs in its own process group: `uv` sits
    between this runner and pytest, and a kill that reached only `uv` would leave pytest running."""
    env = dict(os.environ, PY_COLORS="0")
    # An inherited `VIRTUAL_ENV` names the environment that launched this runner; `uv` ignores it for
    # the target's own and says so on every run -- dropped, so the journal carries the suite alone.
    env.pop("VIRTUAL_ENV", None)
    uv_dir = os.path.dirname(uv)
    if uv_dir and uv_dir not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = uv_dir + os.pathsep + env.get("PATH", "")
    command = pytest_command(repo, uv, extra_args)
    proc = subprocess.Popen(
        command, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True
    )
    try:
        output, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        output, _ = proc.communicate()
        return command, None, output, f"timed out after {timeout:g} s; pytest was killed"
    except KeyboardInterrupt:  # the group may already be gone; nothing to forward then
        # Its own session, so the terminal's SIGINT reached this runner alone: forwarded, and pytest's
        # own interrupt summary is what gets recorded.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGINT)
        output, _ = proc.communicate()
    return command, proc.returncode, output, None


def build_result(
    *,
    started: datetime,
    finished: datetime,
    repo: Path,
    data_present: bool,
    command: list[str] | None,
    exit_code: int | None,
    output: str,
    run_error: str | None,
) -> dict:
    parsed = parse_summary(output)
    counts = parsed["counts"]
    skipped_for_data = sum(entry["count"] for entry in parsed["data_gated_skipped"])
    error = (
        run_error or parsed["error"] or (f"{skipped_for_data} data-gated tests skipped: data absent" if skipped_for_data else None)
    )
    return {
        "schema": SCHEMA,
        "started": _iso(started),
        "finished": _iso(finished),
        "duration_s": round((finished - started).total_seconds(), 1),
        "repo": str(repo),
        "data_present": data_present,
        **git_state(repo),
        "command": command,
        "exit_code": exit_code,
        "summary_line": parsed["summary_line"],
        "counts": counts,
        "failed": parsed["failed"],
        "errors": parsed["errors"],
        "data_gated_skipped": parsed["data_gated_skipped"],
        "error": error,
        "ok": error is None and exit_code == 0 and counts["failed"] == 0 and counts["errors"] == 0,
    }


def read_coverage_token() -> str:
    """`grafana_auth` is loaded here rather than at import, so a load that fails is the upload's failure, never the run's."""
    spec = importlib.util.spec_from_file_location("grafana_auth", _AUTH)
    auth = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(auth)
    return auth.vault_var(COVERAGE_TOKEN_VAR)


def send_coverage(repo: Path, token: str) -> dict:
    """coveralls reads the data file, the files' names and the git head from the working directory, so it runs in `repo`."""
    from coveralls import Coveralls

    with contextlib.chdir(repo):
        return Coveralls(repo_token=token, service_name=COVERALLS_SERVICE).wear()


def _bounded(call, timeout: float):
    """`call()` in a daemon thread, so an answer that never comes ends at `timeout` and the process can still exit."""
    box: dict = {}

    def run() -> None:
        try:
            box["value"] = call()
        except BaseException as exc:  # handed to the caller, which decides what it means
            box["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"no answer within {timeout:g} s")
    error = box.get("error")
    if isinstance(error, Exception):
        raise error
    if error is not None:
        raise RuntimeError(f"{type(error).__name__}: {error}")
    return box["value"]


def coverage_upload(repo: Path, skip: str | None) -> dict:
    """`{"outcome": "uploaded", "url"}`, `{"outcome": "skipped", "reason"}` or `{"outcome": "failed", "error_class",
    "message"}` -- never a raise, so no upload decides a verdict."""
    if skip is not None:
        return {"outcome": "skipped", "reason": skip}
    token = ""

    def upload() -> dict:
        nonlocal token
        try:
            token = read_coverage_token()
        except KeyError as exc:
            if exc.args != (COVERAGE_TOKEN_VAR,):
                raise
            return {"outcome": "skipped", "reason": f"the vault holds no {COVERAGE_TOKEN_VAR}"}
        if not token:
            return {"outcome": "skipped", "reason": f"the vault's {COVERAGE_TOKEN_VAR} is empty"}
        return {"outcome": "uploaded", "url": send_coverage(repo, token)["url"]}

    try:
        return _bounded(upload, UPLOAD_TIMEOUT_S)
    except Exception as exc:
        message = str(exc).replace(token, "<token>") if token else str(exc)
        return {"outcome": "failed", "error_class": type(exc).__name__, "message": message[:500]}


def write_result(result_dir: Path, result: dict) -> tuple[Path, Path]:
    """The stamped file, then `latest.json`, each through a rename so a reader never sees a half-written one."""
    result_dir.mkdir(parents=True, exist_ok=True)
    stamped = result_dir / (_stamp(result["started"]) + ".json")
    latest = result_dir / "latest.json"
    text = json.dumps(result, indent=2) + "\n"
    for path in (stamped, latest):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text)
        os.replace(tmp, path)
    return stamped, latest


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stamp(iso: str) -> str:
    return iso.replace("-", "").replace(":", "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--repo", type=Path, default=Path(__file__).resolve().parents[2], help="the checkout to run in (default: this file's)"
    )
    parser.add_argument("--timeout", type=float, default=3 * 3600, help="seconds before pytest is killed and the result says so")
    parser.add_argument("--no-coverage", action="store_true", help="measure and upload no coverage")
    parser.add_argument("extra", nargs="*", help="extra pytest args, after `--`; a run given them measures no coverage")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not repo.is_dir():
        parser.error(f"--repo {repo} is not a directory")
    data_dir = repo / "data"
    # Not `is_dir()`: `data/.gitignore` is tracked, so git materialises `data/` in every checkout --
    # a worktree with nothing linked in included, which is exactly the tree this refusal is for.
    data_present = data_dir.is_dir() and any(p.name != ".gitignore" for p in data_dir.iterdir())
    uv = os.environ.get("UV") or shutil.which("uv")
    if args.no_coverage:
        coverage_off = "--no-coverage: the run measured none"
    elif args.extra:
        coverage_off = "extra pytest args: the run measured none, since a part of the suite is not the whole"
    else:
        coverage_off = None
    started = datetime.now(timezone.utc)
    command, exit_code, output, run_error = None, None, "", None
    if not data_present:
        run_error = f"data absent: {data_dir} holds no dataset; nothing ran"
    elif uv is None:
        run_error = "uv not found: set UV or put it on PATH; nothing ran"
    else:
        pytest_args = args.extra if coverage_off else list(COVERAGE_ARGS)
        command, exit_code, output, run_error = run_suite(repo, uv, pytest_args, args.timeout)
    finished = datetime.now(timezone.utc)
    result = build_result(
        started=started,
        finished=finished,
        repo=repo,
        data_present=data_present,
        command=command,
        exit_code=exit_code,
        output=output,
        run_error=run_error,
    )
    # pytest's own output first, so the journal holds it while the upload runs.
    sys.stdout.write(output)
    if output and not output.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    unparsed = None if result["counts"] is not None else f"no parsed pytest summary ({result['error']})"
    result["coverage_upload"] = coverage_upload(repo, coverage_off or unparsed)
    stamped, latest = write_result(repo / RESULT_DIR, result)
    verdict = "ok" if result["ok"] else "FAIL"
    outcome = result["coverage_upload"]["outcome"]
    print(
        f"data-gated-run: {verdict} exit={exit_code} {result['error'] or result['summary_line']} -> {stamped} and {latest};"
        f" coverage {outcome}"
    )
    sys.stdout.flush()
    if result["ok"]:
        return 0
    return exit_code if exit_code else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
