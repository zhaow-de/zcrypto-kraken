#!/usr/bin/env python3
"""Run the whole test suite from a checkout where `data/` is present and write the result as JSON.

Every `skipif(not <data>.exists())` test skips in CI, so the data-gated family runs nowhere unless a
workstation runs it: this is the runner `infra/systemd/zcrypto-data-gated-tests.timer` fires nightly.
It `cd`s to the checkout, runs `pytest -q -p no:cacheprovider -rfE` with no path -- the suite CI runs --
through the interpreter the outer `uv run` already resolved and synced, and writes
`.local/data-gated-runs/<UTC stamp>.json` plus `latest.json`: the started/finished stamps, the git sha,
the exit code, the counts parsed from pytest's summary line, and the ids the `-rfE` lines name. A run
whose summary cannot be parsed -- a usage error, a timeout, an interrupted session -- writes a result
that says so rather than nothing, because `zcrypto-daily-ops` has to tell an absent file from a failed
run. `-rfE` rather than the bare `-rf`: an error at setup is a test that did not run, and its id is as
much a finding as a failure's.

Python rather than shell because the parser is the substance and `tests/test_data_gated_run.py`
imports it; a JSON writer in bash is a hand-rolled serialiser.

Usage: data-gated-run.py [--repo <checkout>] [--timeout <seconds>] [-- <extra pytest args>]
The unit passes nothing: the extra args are for a hand run (`-- -k soak`), never the nightly one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PYTEST_ARGS = ("-q", "-p", "no:cacheprovider", "-rfE")
RESULT_DIR = Path(".local") / "data-gated-runs"
SCHEMA = 1
# `1 failed, 2 passed, 1 error in 0.01s`, `no tests ran in 0.00s`, `3 passed in 65.12s (0:01:05)` --
# with or without the `=` rule a non-quiet run draws around the line.
_SUMMARY = re.compile(r"^=*\s*(?P<body>\d+ [a-z]+(?:, \d+ [a-z]+)*|no tests ran) in \d+(?:\.\d+)?s(?: \([\d:]+\))?\s*=*$")
_COUNT = re.compile(r"(\d+) ([a-z]+)")
_SHORT_SUMMARY_RULE = "short test summary info"
# pytest writes one `error`/`warning` in the singular; the result keys are plural whatever the count.
_PLURAL = {"error": "errors", "warning": "warnings"}
COUNT_KEYS = ("passed", "failed", "skipped", "errors", "xfailed", "xpassed", "deselected", "warnings")
NO_SUMMARY = "no pytest summary line in the output"


def parse_summary(output: str) -> dict:
    """Counts and ids from pytest's tail, or `error` naming what was missing.

    The summary line is the LAST line the pattern matches; the ids are the `FAILED`/`ERROR` lines
    between the last `short test summary info` rule and that line, so a captured log line that
    starts with `ERROR` above the rule is never read as a test id."""
    lines = output.splitlines()
    summary_at = next((i for i in range(len(lines) - 1, -1, -1) if _SUMMARY.match(lines[i].strip())), None)
    if summary_at is None:
        return {"summary_line": None, "counts": None, "failed": [], "errors": [], "error": NO_SUMMARY}
    line = lines[summary_at].strip()
    counts = dict.fromkeys(COUNT_KEYS, 0)
    for n, word in _COUNT.findall(_SUMMARY.match(line).group("body")):
        counts[_PLURAL.get(word, word)] = int(n)
    rule_at = next((i for i in range(summary_at - 1, -1, -1) if _SHORT_SUMMARY_RULE in lines[i]), None)
    failed: list[str] = []
    errors: list[str] = []
    if rule_at is not None:
        for raw in lines[rule_at + 1 : summary_at]:
            for prefix, bucket in (("FAILED ", failed), ("ERROR ", errors)):
                if raw.startswith(prefix):
                    bucket.append(raw[len(prefix) :].split(" - ", 1)[0].strip())
    return {"summary_line": line, "counts": counts, "failed": failed, "errors": errors, "error": None}


def git_state(repo: Path) -> dict:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)

    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        return {"sha": None, "dirty": None, "git_error": head.stderr.strip() or f"git rev-parse exited {head.returncode}"}
    status = git("status", "--porcelain", "--untracked-files=no")
    return {"sha": head.stdout.strip(), "dirty": bool(status.stdout.strip()), "git_error": None}


def run_suite(repo: Path, extra_args: list[str], timeout: float | None) -> tuple[list[str], int | None, str, str | None]:
    """`(command, exit code, combined output, why there is no exit code)`.

    A user unit carries the manager's bare PATH, and `uv run` exports its own binary as `UV`: its
    directory is prepended so a test that shells out to `uv` finds the same one the unit ran."""
    env = dict(os.environ, PY_COLORS="0")
    uv_dir = os.path.dirname(os.environ.get("UV", ""))
    if uv_dir and uv_dir not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = uv_dir + os.pathsep + env.get("PATH", "")
    command = [sys.executable, "-m", "pytest", *PYTEST_ARGS, *extra_args]
    try:
        proc = subprocess.run(
            command, cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or b""
        if isinstance(partial, bytes):
            partial = partial.decode(errors="replace")
        return command, None, partial, f"timed out after {timeout:g} s; pytest was killed"
    return command, proc.returncode, proc.stdout, None


def build_result(
    *,
    started: datetime,
    finished: datetime,
    repo: Path,
    command: list[str],
    exit_code: int | None,
    output: str,
    run_error: str | None,
) -> dict:
    parsed = parse_summary(output)
    counts = parsed["counts"]
    error = run_error or parsed["error"]
    return {
        "schema": SCHEMA,
        "started": _iso(started),
        "finished": _iso(finished),
        "duration_s": round((finished - started).total_seconds(), 1),
        "repo": str(repo),
        **git_state(repo),
        "command": command,
        "exit_code": exit_code,
        "summary_line": parsed["summary_line"],
        "counts": counts,
        "failed": parsed["failed"],
        "errors": parsed["errors"],
        "error": error,
        "ok": error is None and exit_code == 0 and counts["failed"] == 0 and counts["errors"] == 0,
    }


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
    parser.add_argument("extra", nargs="*", help="extra pytest args, after `--`")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    os.chdir(repo)
    started = datetime.now(timezone.utc)
    command, exit_code, output, run_error = run_suite(repo, args.extra, args.timeout)
    finished = datetime.now(timezone.utc)
    result = build_result(
        started=started, finished=finished, repo=repo, command=command, exit_code=exit_code, output=output, run_error=run_error
    )
    stamped, latest = write_result(repo / RESULT_DIR, result)
    sys.stdout.write(output)
    if output and not output.endswith("\n"):
        sys.stdout.write("\n")
    verdict = "ok" if result["ok"] else "FAIL"
    print(f"data-gated-run: {verdict} exit={exit_code} {result['summary_line'] or result['error']} -> {stamped} and {latest}")
    sys.stdout.flush()
    if result["ok"]:
        return 0
    return exit_code if exit_code else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
