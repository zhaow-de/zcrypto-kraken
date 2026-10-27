#!/usr/bin/env python3
"""Run the whole test suite from a checkout where the datasets are present, write the result as JSON, upload its coverage.

CI deselects the `retired` cases and skips every `skipif(not <data>.exists())` test, so this run, which
`infra/systemd/zcrypto-data-gated-tests.timer` fires nightly, is the one with the whole suite in scope and so the one
coverage report. The suite runs in a detached worktree at the checkout's HEAD as the run started, under
`<repo>/.tmp/data-gated-run/`, every entry of the checkout's `data/` symlinked into the worktree's: a pull or merge into
the checkout while the suite runs moves nothing under it, and `sha` names what ran. The worktree goes whatever happened;
one a night left behind is swept at the next start.
It writes `.local/data-gated-runs/<UTC stamp>.json` plus `latest.json` in the checkout. A run in which the whole family
skipped for want of data is exactly the night this exists to catch, so such a skip is a failure, and a checkout with no
dataset under `data/` is refused before pytest starts. A run whose summary cannot be parsed -- a usage error, a timeout,
an interrupted session -- still writes a result, because `zcrypto-daily-ops` has to tell an absent file from a failed
run. `-rfE` rather than the bare `-rf`: an error at setup is a test that did not run, and its id is as much a finding as
a failure's.

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
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Eight xdist workers: serial, the suite outgrew the three-hour bound. `--durations` feeds `parse_slowest`.
PYTEST_ARGS = ("-q", "-p", "no:cacheprovider", "-rfEs", "-n", "8", "--durations=25", "--durations-min=1.0")
# The data file only, `.coverage` at the worktree's root: the upload reads it there, and a report would only lengthen the journal.
COVERAGE_ARGS = ("--cov=cli", "--cov-report=")
WORKTREE_DIR = Path(".tmp") / "data-gated-run"
DEADLINE_FILE = ".deadline"
# A run's time outside its pytest bound -- worktree add, upload, teardown -- with room to spare.
SWEEP_SLACK_S = 600.0
DEVELOP_ENV = "ZCRYPTO_DATA_GATED_DEVELOP"
COVERALLS_SERVICE = "zcrypto-nightly"
UPLOAD_TIMEOUT_S = 120.0
# The ops role renders it at this path under its research user's home; tests/test_data_gated_run.py pins the two.
TOKEN_FILE = Path.home() / ".config" / "zcrypto" / "coveralls.env"
TOKEN_KEY = "COVERALLS_REPO_TOKEN"
_TOKEN_LINE = re.compile(rf"{TOKEN_KEY}=(?P<token>[^\s'\"]*)")
RESULT_DIR = Path(".local") / "data-gated-runs"
SCHEMA = 4
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
# `--durations` draws `==== slowest 25 durations ====` and then one `12.34s call     <node id>` line per phase.
_SLOWEST_RULE = re.compile(r"^=+ slowest (?:\d+ )?durations =+$")
_SLOWEST_LINE = re.compile(r"^(?P<seconds>\d+(?:\.\d+)?)s (?P<when>setup|call|teardown)\s+(?P<id>\S.*)$")


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


def parse_slowest(output: str) -> list[list]:
    """`[[seconds, phase, node id], ...]` from the last `slowest durations` block, in pytest's order; empty where pytest
    printed none, as a killed run does."""
    lines = output.splitlines()
    rule_at = next((i for i in range(len(lines) - 1, -1, -1) if _SLOWEST_RULE.match(lines[i].strip())), None)
    slowest: list[list] = []
    if rule_at is not None:
        for raw in lines[rule_at + 1 :]:
            m = _SLOWEST_LINE.match(raw.strip())
            if m is None:
                break
            slowest.append([float(m.group("seconds")), m.group("when"), m.group("id")])
    return slowest


def _id(rest: str) -> str:
    m = _ID.match(rest)
    return m.group("id") if m else rest.strip()


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def git_state(repo: Path) -> dict:
    head = _git(repo, "rev-parse", "HEAD")
    if head.returncode != 0:
        error = head.stderr.strip() or f"git rev-parse exited {head.returncode}"
        return {
            "sha": None,
            "dirty": None,
            "branch": None,
            "develop": None,
            "origin_develop": None,
            "behind_origin_develop": None,
            "git_error": error,
        }
    status = _git(repo, "status", "--porcelain", "--untracked-files=no")
    branch = _git(repo, "branch", "--show-current").stdout.strip()
    # The checkout's own `develop` before `origin/develop`: a fetch the checkout has not pulled past is no row or record
    # the frozen tree lacks.
    local = _git(repo, "rev-parse", "--verify", "--quiet", "develop").stdout.strip() or None
    origin_develop = _git(repo, "rev-parse", "--verify", "--quiet", "origin/develop").stdout.strip() or None
    develop = local or origin_develop
    behind = None
    if local and origin_develop:
        counted = _git(repo, "rev-list", "--count", "develop..origin/develop")
        behind = int(counted.stdout.strip()) if counted.returncode == 0 else None
    return {
        "sha": head.stdout.strip(),
        "dirty": bool(status.stdout.strip()),
        "branch": branch or None,
        "develop": develop,
        "origin_develop": origin_develop,
        "behind_origin_develop": behind,
        "git_error": None,
    }


def data_listing(repo: Path) -> list[list] | None:
    """Every directory and file under the checkout's `data/`, links not followed: `[repo-relative path, size, mtime_ns]`."""
    data = repo / "data"
    if not data.is_dir():
        return None
    listing = []
    for root, dirs, files in os.walk(data):
        for name in (*dirs, *files):
            path = Path(root) / name
            st = os.lstat(path)
            listing.append([path.relative_to(repo).as_posix(), st.st_size, st.st_mtime_ns])
    return sorted(listing)


def worktree_path(repo: Path, started: datetime) -> Path:
    return repo / WORKTREE_DIR / f"wt-{_stamp(_iso(started))}"


class WorktreeError(Exception):
    """The worktree could not be made whole: what `git worktree add` or a link said."""


def add_worktree(repo: Path, sha: str, worktree: Path) -> None:
    """The detached worktree at `sha`; a path already taken -- another run's, started in the same second -- is a raise."""
    worktree.parent.mkdir(parents=True, exist_ok=True)
    added = _git(repo, "worktree", "add", "--detach", str(worktree), sha)
    if added.returncode != 0:
        raise WorktreeError(f"git worktree add exited {added.returncode}: {added.stderr.strip()}")


def link_datasets(repo: Path, worktree: Path, deadline: datetime) -> list[str]:
    """The worktree's `.deadline`, and every entry of the checkout's `data/` but its tracked `.gitignore` symlinked into the
    worktree's; the names linked."""
    linked = []
    try:
        (worktree / DEADLINE_FILE).write_text(_iso(deadline) + "\n")
        (worktree / "data").mkdir(exist_ok=True)
        for entry in sorted(p for p in (repo / "data").iterdir() if p.name != ".gitignore"):
            os.symlink(entry, worktree / "data" / entry.name)
            linked.append(entry.name)
    except OSError as exc:
        raise WorktreeError(f"linking {repo / 'data'} into the worktree: {exc}") from None
    return linked


def remove_worktree(repo: Path, worktree: Path) -> dict:
    """Each symlink in the worktree's `data/` unlinked, another entry named in `left`, then the worktree removed; never a raise."""
    unlinked: list[str] = []
    left: list[str] = []
    faults: list[str] = []
    data = worktree / "data"
    if data.is_dir():
        for entry in sorted(p for p in data.iterdir() if p.name != ".gitignore"):
            if not entry.is_symlink():
                left.append(entry.name)
                continue
            try:
                entry.unlink()
                unlinked.append(entry.name)
            except OSError as exc:
                faults.append(f"unlink {entry.name}: {exc}")
    removed = _git(repo, "worktree", "remove", "--force", str(worktree))
    if removed.returncode != 0:
        faults.append(f"git worktree remove exited {removed.returncode}: {removed.stderr.strip()}")
    if worktree.exists():
        faults.append(f"{worktree} still exists")
    return {
        "worktree": str(worktree),
        "unlinked": unlinked,
        "left": left,
        "removed": not worktree.exists(),
        "error": "; ".join(faults) or None,
    }


def _deadline(worktree: Path) -> datetime | None:
    try:
        text = (worktree / DEADLINE_FILE).read_text().strip()
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except OSError, ValueError:
        return None


def sweep_stale_worktrees(repo: Path, now: datetime) -> tuple[list[str], list[str], str | None]:
    """Each `wt-*` under WORKTREE_DIR removed as the night's own is, then `git worktree prune`; one whose `.deadline` is
    still ahead may be a run going on, and one with no readable deadline is not this runner's, so both are left and named.
    `(swept, left, faults)`."""
    root = repo / WORKTREE_DIR
    swept: list[str] = []
    left: list[str] = []
    faults: list[str] = []
    if root.is_dir():
        for entry in sorted(p for p in root.iterdir() if p.name.startswith("wt-")):
            deadline = _deadline(entry)
            if deadline is None or deadline > now:
                left.append(entry.name)
                continue
            record = remove_worktree(repo, entry)
            if record["error"]:
                faults.append(f"{entry.name}: {record['error']}")
            if entry.exists():
                left.append(entry.name)
            else:
                swept.append(entry.name)
    pruned = _git(repo, "worktree", "prune")
    if pruned.returncode != 0:
        faults.append(f"git worktree prune exited {pruned.returncode}: {pruned.stderr.strip()}")
    return swept, left, "; ".join(faults) or None


def pytest_command(repo: Path, uv: str, extra_args: list[str]) -> list[str]:
    """Through the target tree's own environment -- `uv run --directory` enters and syncs that tree's `.venv` -- never
    `sys.executable`, which is whatever environment launched this runner."""
    return [uv, "run", "--directory", str(repo), "python", "-m", "pytest", *PYTEST_ARGS, *extra_args]


def run_suite(
    worktree: Path, uv: str, extra_args: list[str], timeout: float | None, *, develop: str | None
) -> tuple[list[str], int | None, str, str | None]:
    """`(command, exit code, combined output, why there is no exit code)`.

    A user unit carries the manager's bare PATH, so the directory of the `uv` this run goes through is
    prepended for a test that shells out to `uv`. The suite runs in its own process group: `uv` sits
    between this runner and pytest, and a kill that reached only `uv` would leave pytest running."""
    env = dict(os.environ, PY_COLORS="0")
    # An inherited `VIRTUAL_ENV` names the environment that launched this runner; `uv` ignores it for
    # the target's own and says so on every run -- dropped, so the journal carries the suite alone.
    env.pop("VIRTUAL_ENV", None)
    env.pop(DEVELOP_ENV, None)
    if develop is not None:
        env[DEVELOP_ENV] = develop
    uv_dir = os.path.dirname(uv)
    if uv_dir and uv_dir not in env.get("PATH", "").split(os.pathsep):
        env["PATH"] = uv_dir + os.pathsep + env.get("PATH", "")
    command = pytest_command(worktree, uv, extra_args)
    proc = subprocess.Popen(
        command, cwd=worktree, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True
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
    state: dict,
    worktree: str | None,
    command: list[str] | None,
    exit_code: int | None,
    output: str,
    run_error: str | None,
    teardown: dict | None,
    data_listing: tuple[list[list] | None, list[list] | None],
    swept: list[str],
    sweep_left: list[str],
    sweep_error: str | None,
) -> dict:
    """`state` is `git_state` at the start plus `sha_at_end` and `tree_moved`; `data_listing` the two `data_listing()` reads."""
    parsed = parse_summary(output)
    counts = parsed["counts"]
    skipped_for_data = sum(entry["count"] for entry in parsed["data_gated_skipped"])
    faults = [
        run_error or parsed["error"] or (f"{skipped_for_data} data-gated tests skipped: data absent" if skipped_for_data else None)
    ]
    if sweep_error:
        faults.append(f"sweep: {sweep_error}")
    if teardown is not None and teardown["error"]:
        faults.append(f"teardown: {teardown['error']}")
    listing_start, listing_end = data_listing
    intact = listing_start == listing_end
    if not intact:
        differing = {tuple(e) for e in listing_start or []} ^ {tuple(e) for e in listing_end or []}
        faults.append(f"the checkout's data/ listing changed during the run: {sorted({e[0] for e in differing})}")
    error = "; ".join(f for f in faults if f) or None
    return {
        "schema": SCHEMA,
        "started": _iso(started),
        "finished": _iso(finished),
        "duration_s": round((finished - started).total_seconds(), 1),
        "repo": str(repo),
        "data_present": data_present,
        "sha": state["sha"],
        "dirty": state["dirty"],
        "git_error": state["git_error"],
        "branch": state["branch"],
        "develop": state["develop"],
        "origin_develop": state["origin_develop"],
        "behind_origin_develop": state["behind_origin_develop"],
        "sha_at_end": state["sha_at_end"],
        "tree_moved": state["tree_moved"],
        "worktree": worktree,
        "command": command,
        "exit_code": exit_code,
        "summary_line": parsed["summary_line"],
        "counts": counts,
        "failed": parsed["failed"],
        "errors": parsed["errors"],
        "data_gated_skipped": parsed["data_gated_skipped"],
        "slowest": parse_slowest(output),
        "swept": swept,
        "sweep_left": sweep_left,
        "sweep_error": sweep_error,
        "teardown": teardown,
        "data_listing_intact": intact,
        "data_listing": None if intact else {"start": listing_start, "end": listing_end},
        "error": error,
        "ok": error is None and exit_code == 0 and counts["failed"] == 0 and counts["errors"] == 0,
    }


class NoToken(Exception):
    """Why the upload is skipped: the message names the file, never the token or a line's text."""


def read_coverage_token() -> str:
    path = TOKEN_FILE
    try:
        st = os.stat(path)
    except FileNotFoundError:
        raise NoToken(f"no token file at {path}") from None
    if not stat.S_ISREG(st.st_mode):
        raise NoToken(f"{path} is not a regular file")
    if st.st_uid != os.getuid():
        raise NoToken(f"{path} is owned by uid {st.st_uid}, not this run's uid {os.getuid()}")
    if st.st_mode & 0o077:
        raise NoToken(f"{path} has mode {stat.S_IMODE(st.st_mode):04o}: a group or other permission bit is refused")
    token = None
    for number, raw in enumerate(path.read_text().splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _TOKEN_LINE.fullmatch(line)
        if match is None:
            raise NoToken(f"{path} line {number} is not a {TOKEN_KEY}=<token> line")
        if token is not None:
            raise NoToken(f"{path} line {number} is a second {TOKEN_KEY} line")
        token = match.group("token")
    if token is None:
        raise NoToken(f"{path} holds no {TOKEN_KEY} line")
    if not token:
        raise NoToken(f"{path}'s {TOKEN_KEY} is empty")
    return token


@contextlib.contextmanager
def _environ(**values: str):
    before = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in before.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def send_coverage(repo: Path, token: str, branch: str | None) -> dict:
    """coveralls reads the data file, the files' names and the git head from the working directory, so it runs in `repo`, the
    detached worktree, whose HEAD names no branch: the checkout's is handed over as `GIT_BRANCH`, read before coveralls's own
    `git rev-parse`."""
    from coveralls import Coveralls

    with contextlib.chdir(repo), _environ(**({} if branch is None else {"GIT_BRANCH": branch})):
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


def coverage_upload(repo: Path, skip: str | None, branch: str | None = None) -> dict:
    """`{"outcome": "uploaded", "url"}`, `{"outcome": "skipped", "reason"}` or `{"outcome": "failed", "error_class",
    "message"}` -- never a raise, so no upload decides a verdict."""
    if skip is not None:
        return {"outcome": "skipped", "reason": skip}
    token = ""

    def upload() -> dict:
        nonlocal token
        try:
            token = read_coverage_token()
        except NoToken as why:
            return {"outcome": "skipped", "reason": str(why)}
        return {"outcome": "uploaded", "url": send_coverage(repo, token, branch)["url"]}

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
    state = git_state(repo)
    listing_start = data_listing(repo)
    swept, sweep_left, sweep_error = sweep_stale_worktrees(repo, started)
    deadline = started + timedelta(seconds=args.timeout + SWEEP_SLACK_S)
    command, exit_code, output, run_error = None, None, "", None
    worktree = teardown = None
    created = False
    if not data_present:
        run_error = f"data absent: {data_dir} holds no dataset; nothing ran"
    elif uv is None:
        run_error = "uv not found: set UV or put it on PATH; nothing ran"
    elif state["sha"] is None:
        run_error = f"git: {state['git_error']}; nothing ran"
    else:
        worktree = worktree_path(repo, started)
    try:
        if worktree is not None:
            try:
                add_worktree(repo, state["sha"], worktree)
                created = True
                link_datasets(repo, worktree, deadline)
                pytest_args = args.extra if coverage_off else list(COVERAGE_ARGS)
                command, exit_code, output, run_error = run_suite(worktree, uv, pytest_args, args.timeout, develop=state["develop"])
            except Exception as exc:
                run_error = f"the runner raised {type(exc).__name__}: {exc}"
        finished = datetime.now(timezone.utc)
        end = git_state(repo)
        # pytest's own output first, so the journal holds it while the upload runs.
        sys.stdout.write(output)
        if output and not output.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()
        parsed = parse_summary(output)
        unparsed = None if parsed["counts"] is not None else f"no parsed pytest summary ({run_error or parsed['error']})"
        upload = coverage_upload(worktree if worktree is not None else repo, coverage_off or unparsed, state["branch"])
    finally:
        # Only a worktree this run made: a path another run holds is that run's to remove.
        if created and worktree.exists():
            teardown = remove_worktree(repo, worktree)
    result = build_result(
        started=started,
        finished=finished,
        repo=repo,
        data_present=data_present,
        state={**state, "sha_at_end": end["sha"], "tree_moved": None if state["sha"] is None else state["sha"] != end["sha"]},
        worktree=None if worktree is None else str(worktree),
        command=command,
        exit_code=exit_code,
        output=output,
        run_error=run_error,
        teardown=teardown,
        data_listing=(listing_start, data_listing(repo)),
        swept=swept,
        sweep_left=sweep_left,
        sweep_error=sweep_error,
    )
    result["coverage_upload"] = upload
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
