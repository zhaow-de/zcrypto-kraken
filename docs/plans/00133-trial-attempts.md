# The trial-attempts log — every ruled run counted, an abandoned branch included — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task: a fresh implementer per task and a fresh reviewer before the next. Execution is subagent-driven — the run's call, made unattended, nobody asked. Steps use checkbox (`- [ ]`) syntax for tracking. `zcrypto-plan-review` reviews this plan with its spec before Task 1.

**Goal:** every run of a subject with a verdict rule writes a `begin` line before its fit and an `end` line before its print into one hash-chained log per clone, the count reconciles that log with the landed records so an attempt whose branch never merged still counts against its family and bucket, the subject's deflated Sharpe and the hard budgets are enforced at register time, and CI holds every record past 48 to its count, family, budget, log and carry-forward.

**Architecture:** `cli/registry/attempts.py` owns the log (`AttemptLog`, chained, flock'd, copy-aside healing), the git reads (`main_checkout`, `current_branch`, `landed`, `allowed_log_ids`, each through `_git`, never a network call) and the pure count (`reconcile`); `cli/registry/budget.py` holds the two literals; the store (`record.py`, `store.py`) validates schema 6's `attempt` block by form alone, no git and no disk; the command (`cli/research/command.py`) is the one writer, ordering the refusals, the critical section, the build, the `end` line, the print and the locked post-check exactly as spec D2 lists them; the subjects declare `family` and `n_trials`; the checks are tests, ungated, over the committed files. Nothing under `cli/engine/` changes.

**Tech Stack:** Python 3.14 through uv; `fcntl`, `os`, `secrets`, `socket`, `subprocess` (git only, through the module so a spy sees every call); typer for the command; pytest, typer's `CliRunner`; `infra/scripts/mutate-probe.sh`, `infra/scripts/consumers.sh`, `infra/scripts/tier.py`.

**Spec:** `docs/specs/00133-t0222-trial-attempts-design.md` at the revision this plan is read at, its amendments `git log --oneline -- docs/specs/00133-t0222-trial-attempts-design.md` — binding; D1–D11, the formats section and the CI checks section are cited by name and not copied, so the two cannot disagree. **Branch:** `research/00133-t0222-abandoned-trials`, worktree `.claude/worktrees/t0222`. **Topic:** T0222.

## Global Constraints

- The log: `.local/trial-attempts.jsonl` in the main checkout, the parent of `git -C <code root> rev-parse --git-common-dir`, resolved against the code root when relative; refused when that parent is no checkout.
- Each line canonical JSON (`canonical_json`), `seq` contiguous from 1, `prev_hash` the previous line's `line_hash` (64 zeros on line 1), `line_hash` the `compute_hash` of the line without it; line 1 and only line 1 is the genesis line, `log_id` 32 lowercase hex from `secrets.token_hex(16)`, `host` `socket.gethostname()`; key sets exactly the formats section's for `genesis`, `begin` and `end`.
- Every read of the log holds its flock, so another session's line in flight is never taken for a torn one; every write of a line is one `os.write` whose count is checked, a short one refused as an `OSError`, since `os.write` returns what it wrote and raises nothing when a full disk cuts the line. A torn last line — any last line without its `\n`, parseable or not, which under the flock only a refused write or a writer that died leaves — is healed so: the whole file copied to `<log>.torn-<UTC stamp>` beside it, then truncated, then the chain re-verified over the file as read back from disk, the copy deleted only after that verification passes; a failing one keeps the copy and refuses naming it. The stamp is `datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")`, the copy made with an exclusive create. An `OSError` the log raises outside the two refusals spec D2 prints ends the command in a traceback: `attempts-init`'s genesis line; `locked()`'s read, after the print, where the run's `end` already stands and it counts as any run refused after its print; and the failed `end` one of Task 5's four exits writes, the build's error chained beneath it, nothing printed and the attempt left open, counting until a same-arguments retry absorbs it (spec D3).
- An `end` line: exactly one of `verdict` (`adopt`, `reject`, `park`), `stop` (the subject's `no_verdict`) and `failed` (`<class>: <message>`) non-null; `metrics` and `metrics_hash` (`compute_hash(metrics)`) null exactly when `failed` is not.
- `BUCKET_OF = {"A1": "A", "B1": "B", "B2": "B", "P1": None}` and `BUDGET = {"A": 40, "B": 25, "C": 10}`, in `cli/registry/budget.py`.
- `SCHEMA_VERSION = 6` adds `attempt`; `_ATTEMPT_FLOOR_TRIAL_ID = 48`; `READING_SCHEMA_VERSION = 2` adds `attempt`, floored at reading 1.
- The allowlist `docs/reference/trial-attempt-logs.txt`: one row per log, `<32 lowercase hex> <host>`, never removed.
- `b1-hourly-rv` declares `family="B1"` and `n_trials=_B1_HOURLY_RV_N_TRIALS` (3), frozen by record 48; `b2-funding-derisk` declares `family="B2"` and `n_trials=1`.
- A record's `counted` lists finished orphans only — an `end` that stored a verdict, landed by no record or reading; an open attempt counts in `required_n` and `spent` and is never listed.
- The register path makes no network call: no argv holding `fetch`, `ls-remote` or `gh`.
- No test writes the real log, and none reaches the real allowlist through `allowed_log_ids` — the literal checks of Tasks 3 and 8 read the committed file directly: from Task 4 the conftest fixture holds both in each test's `tmp_path`; before it, a test that reaches the log patches `cli.registry.attempts.log_path` itself. Code under `cli/` reaches `cli/registry/attempts.py` only as `attempts.<name>` through `from cli.registry import attempts`, read when the call runs: never a name imported from it, which Task 4's `test_no_module_under_cli_imports_a_name_from_the_attempts_module` refuses, and never `attempts.<name>` bound to another name at import time — a module-level assignment, a default argument — which that walk does not see, since either keeps the real function whatever a test patches.
- No trial is registered and no record or reading written on this branch; the one write outside this worktree is Task 3's single `zcrypto research attempts-init`, which creates the main checkout's log.
- String literals under `cli/` — refusals, help texts — and the README rows carry no `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or `D<N>` (`tests/test_internal_terms_not_operator_visible.py`, `tests/test_cli_help_hygiene.py`).
- Every pytest run is preceded by `mkdir -p .tmp/plan-00133` and carries `-q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`; before each commit the direct readers of each changed path run (`bash infra/scripts/consumers.sh --direct <paths>`), and beside them the three walkers that read what a task writes, which `--direct` lists for no path under `cli/` or `tests/` — `tests/test_internal_terms_not_operator_visible.py`, every string literal under `cli/`, for a task that changes a file there; `tests/test_cli_help_hygiene.py`, every command's help through the app, for one that changes a help string; `tests/test_config_selectors_are_parsed.py`, every test module's `in` comparisons over the text of a file under `infra/`, for one whose test reads such a file, its case for that module alone (`-k <the module's file name>`) — never the full suite, which is CI's; never `tests/test_grafana_push_sh.py`.
- Every new guard — a test, an assertion, a refusal — is proven with `infra/scripts/mutate-probe.sh` after its task's commit (the script refuses a dirty tree); the tier is `full` (`uv run python infra/scripts/tier.py --paths cli/registry/store.py`), so each guard through its own `-k` case, never through a case listed in `tests/slow-cases.txt`: the two cases of Task 6's DSR tie join that list, each build taking over 10 s, so their probes are recorded `probe skipped: slow case`, and no other test this plan adds joins it. Each probe: `infra/scripts/mutate-probe.sh --file <F> --control '<sed>' --mutation '<sed>' -- uv run pytest <test file> -k '<case>' -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`, expected `KILLED`; the mutation substitutes and never deletes a line (`if <cond>:` becomes `if False:`; a call `None`, or `True` where the call is a predicate a condition reads, so the mutated check accepts every value; a clause its neutral operand), each of its patterns one whose `grep -c` reads 1, or, where the text a row names repeats in its file — the flocks of Task 1 Step 4, the `.get` reads of its Step 5, a check written once before the fit and once after the print — its `s` command range-addressed, `/<start>/,/<end>/s/…/…/`, the start pattern one whose `grep -c` reads 1 and the range, from it through the first line after it that the end pattern matches, bounded to the one function or block the row names, `sed -n '/<start>/,/<end>/p' <F>` read before the probe; a `.py` file's sed is dry-run first with `sed '<expr>' <F> | uv run python -c 'import ast,sys; ast.parse(sys.stdin.read())'`, and a file of another kind is proven changed by mutate-probe's own refusal of a sed that changes nothing (rc 6); the control is the task's named one, never a variant of the mutation. Each verdict line goes in the PR body, naming `infra/scripts/mutate-probe.sh`.
- Commits: one per task, never an amend; `uv run pre-commit run -a` re-run until clean, staging what it rewrote by explicit path; the message says what changed and carries the test command's result line, and ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` — the executing model, so an implementer on another model names its own — and the executing session's `Claude-Session:` line.

## Review Focus

- Two sessions running the same arguments at once: a held attempt that another session lands between this run's `begin` and its append must be absorbed by no one twice — the post-check and the append run under the log's lock, reading `landed` afresh, so the record never repeats a landed (log, id) and CI's (xi) never fails a correct PR. Test: Task 7, `test_a_held_attempt_another_session_lands_mid_fit_is_absorbed_by_no_one_twice`.
- Two sessions running the same arguments while both still fit: an open attempt whose process runs may yet end with other numbers and print, so no count holds it out and no run absorbs it, and a second live run at a bucket's last slot is refused before its fit; one whose process is gone — a killed run, or one whose `end` the log refused — is held and absorbed whatever its numbers, as D2's remedy promises. Tests: Task 1, `test_an_open_attempt_is_held_or_absorbed_only_when_its_process_is_gone`; Task 7, `test_an_open_attempt_at_the_budgets_edge_is_held_only_when_its_process_is_gone`.
- Two sessions starting trials in one family at once: the count must read the log as re-read under the lock, so the second session sees the first's `begin`, never a stale instance's lines, and over `landed` re-read inside that lock, never the read before the data. Tests: Task 1, `test_begin_counts_over_the_lines_another_session_appended_after_this_log_was_read` — `begin` hands `admit` the re-read lines; Task 7, `test_what_lands_between_a_read_and_the_lock_its_count_takes_is_counted` — the command counts over them and over `landed` as `admit` re-reads it. The two counts read four inputs, each fresh under its lock, each with a case that writes after the last earlier read of it: the lines and `landed` inside `begin` (that test's rows `a-begin-in-the-window`, after the constructor's read, and `a-record-in-the-window`, after the read before the data), the lines inside `locked()` after the print (its row `a-begin-before-the-post-check`, after the `end` that refreshed `log.lines`), and `landed` inside `locked()` (`lands_mid_fit`, after both earlier reads).
- A read racing another session's append: every read holds the log's flock, so a line half written is never taken for a torn tail and truncated away, which would leave a printed attempt open for any retry to absorb. Test: Task 1, `test_a_torn_tail_another_session_is_still_writing_is_never_healed`.
- A torn last line that ends inside a multibyte UTF-8 character — a non-ASCII worktree path or branch name, which `canonical_json` writes raw — must heal like any torn line, never escape as a `UnicodeDecodeError` traceback. Test: Task 1, `test_a_torn_last_line_inside_a_multibyte_character_is_healed`.
- A registration from a detached HEAD — every scratch tree here is detached — must write `branch` null and name such an orphan "on a detached HEAD" in D4's refusal. Test: Task 1, `test_the_branch_is_none_on_a_detached_head_and_an_orphan_from_one_is_named_so`.
- A target registry or ledger not yet created, and a ref that holds no registry or ledger file, must read as no records, never a refusal or a traceback. Test: Task 1, `test_landed_reads_the_targets_head_and_origin_develop_each_record_once`.

## File structure

- Create `cli/registry/attempts.py` — the log, the reads of what landed, the count, the allowlist reader.
- Create `cli/registry/budget.py` — `BUCKET_OF`, `BUDGET`.
- Create `docs/reference/trial-attempt-logs.txt` — the allowlist.
- Create `tests/test_trial_attempts.py` — the log's, the count's and the hermetic fixture's tests.
- Modify `cli/registry/record.py`, `cli/registry/store.py` — schema 6, reading schema 2, the floors.
- Modify `cli/research/subjects.py` — `Subject.family`, `Subject.n_trials`, the declarations, the kill-bar counts.
- Modify `cli/research/command.py` — `attempts-init`; the register path's lines, count and refusals; the plain-eval refusal.
- Modify `tests/conftest.py` — the autouse fixture.
- Modify `tests/test_research_command.py`, `tests/test_registry_replay.py`, `tests/test_registry_store.py`, `tests/test_registry_record.py`, `tests/test_registry_conformance.py`, `tests/test_research_control.py`, `tests/test_trial_registry_provenance.py`, `tests/test_decisions_log_ties.py`.
- Modify `infra/scripts/workspace-transport.zsh`, `tests/test_workspace_transport.py` — the transport's two `.local/` rsyncs leave each machine's log and its heal's copies where they are (spec D6).
- Modify `README.md` — the `zcrypto research` section.
- Modify `tests/slow-cases.txt` — the DSR tie's two cases.
- Move `docs/open-topics/T0222-a-trial-on-an-unmerged-branch-spends-uncounted.md` into `docs/open-topics/archive/`, resolved; re-render `docs/open-topics/README.md`.

______________________________________________________________________

### Task 1: the attempts log and the count — `cli/registry/attempts.py` (D1, D3)

**Files:**
- Create: `cli/registry/attempts.py`
- Create: `tests/test_trial_attempts.py`

**Interfaces:**
- Consumes: `cli.registry.errors.RegistryError`; `cli.registry.record.GENESIS_HASH`, `canonical_json`, `compute_hash`, `loads_strict`, `VERDICTS`; `cli.registry.store._read_healing` imported by name, so a test wraps `attempts._read_healing`; `cli.registry.TrialRegistry`, `ReadingLedger`.
- Produces:

```python
LOG_RELPATH = Path(".local") / "trial-attempts.jsonl"
REGISTRY_RELPATH = "docs/reference/trial-registry.jsonl"
LEDGER_RELPATH = "docs/reference/reading-ledger.jsonl"
DEVELOP = "refs/remotes/origin/develop"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")

class AttemptLogError(RegistryError): ...

def _git(code_root: Path, *args: str) -> subprocess.CompletedProcess[str]: ...  # subprocess.run through the module
def _write_line(fd: int, line: bytes) -> None: ...  # one os.write through the module; fewer bytes written raises OSError
def main_checkout(code_root: Path) -> Path: ...
def log_path(code_root: Path) -> Path: ...
def current_branch(code_root: Path) -> str | None: ...  # None on a detached HEAD
def init_log(path: Path, *, host: str | None = None) -> str: ...  # the new log_id
def arguments(invocation: dict) -> dict: ...  # the invocation without "commit"
def _boot_id() -> str: ...  # BOOT_ID's text, stripped
def _process_marks() -> dict: ...  # {"pid": os.getpid(), "boot": _boot_id()}: what begin records of the running process
def _alive(begin: dict) -> bool: ...  # False when its boot is not _boot_id() or os.kill(its pid, 0) raises ProcessLookupError

@dataclass(frozen=True)
class Attempt:
    id: int
    begin: dict
    end: dict | None

def attempts_of(lines: Sequence[dict]) -> tuple[Attempt, ...]: ...

class AttemptLog:
    path: Path
    log_id: str
    host: str
    lines: tuple[dict, ...]
    def __init__(self, path: Path) -> None: ...
    def attempts(self) -> tuple[Attempt, ...]: ...
    def begin(self, admit: Callable[[tuple[dict, ...]], None], *, invocation: dict, spec_hash: str, family: str,
              bucket: str | None, n_trials: int, worktree: Path, branch: str | None, registry: Path, ledger: Path) -> int: ...
    def end(self, attempt: int, *, verdict: str | None = None, stop: str | None = None, failed: str | None = None,
            metrics: dict | None = None) -> None: ...
    @contextmanager
    def locked(self) -> Iterator[tuple[dict, ...]]: ...

@dataclass(frozen=True)
class Landed:
    records: tuple[dict, ...]
    readings: tuple[dict, ...]

def collect(records: Iterable[dict], readings: Iterable[dict]) -> Landed: ...
def files_landed(registry: Path, ledger: Path) -> Landed: ...
def landed(code_root: Path, registry: Path, ledger: Path) -> Landed: ...

@dataclass(frozen=True)
class Orphan:
    log: str
    id: int
    family: str
    subject: str
    spec_hash: str
    verdict: str | None  # None: open, no end
    metrics: dict | None
    timestamp: str | None = None
    branch: str | None = None
    listed_by: int | None = None  # the trial whose counted carried it
    def entry(self) -> dict: ...  # the counted entry: log, id, family, subject, spec_hash, verdict, metrics
    def describe(self) -> str: ...

@dataclass(frozen=True)
class Count:
    records: tuple[dict, ...]
    orphans: tuple[Orphan, ...]
    absorbs: tuple[int, ...]
    bucket_of: Mapping[str, str | None]
    def required_n(self, family: str) -> int: ...
    def spent(self, bucket: str) -> int: ...
    def counted(self, family: str) -> list[dict]: ...

def reconcile(lines: Sequence[dict], landed: Landed, *, log_id: str, bucket_of: Mapping[str, str | None],
              own: int | None = None, hold: tuple[str, dict, str] | None = None, hold_finished: bool = True) -> Count: ...
def lacking(lines: Sequence[dict], landed: Landed, log_id: str) -> list[tuple[str, int]]: ...
def _landed_ids(landed: Landed) -> set[tuple[str, int]]: ...
def _verify_chain(lines: list[dict], path: Path) -> None: ...
```

- [ ] **Step 1: Write the failing tests** — the module's helpers and the log's tests:

```python
# tests/test_trial_attempts.py
from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from cli.registry import TrialRegistry, attempts
from cli.registry.attempts import AttemptLog, AttemptLogError, collect, init_log, lacking, reconcile
from cli.registry.record import GENESIS_HASH, canonical_json, compute_hash, loads_strict

REPO = Path(__file__).resolve().parents[1]
_LOG, _OTHER = "a" * 32, "b" * 32
_SPEC = "c" * 64
_BUCKETS = {"A1": "A", "B1": "B", "B2": "B", "P1": None}
_GIT_IDENTITY = ("-c", "user.name=zcrypto-test", "-c", "user.email=zcrypto-test@example.invalid", "-c", "commit.gpgsign=false")
_REMEDY_TAIL = (
    "rename it aside, then restore it from a backup if one exists; otherwise create a new log with zcrypto research "
    "attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
)
# The real functions, kept before a fixture can replace them.
_real_log_path, _real_landed = attempts.log_path, attempts.landed


# By default begun before this boot, so its process is gone, as a killed run's is.
def _begin(attempt: int, *, subject="stub", family="B1", dataset="ohlc-full", spec_hash=_SPEC, branch="research/x",
           commit="d" * 40, pid=1, boot="another boot") -> dict:
    invocation = {"subject": subject, "dataset": dataset, "window": None, "as_of": None, "accept_holes": False,
                  "comparator_trial": None, "commit": commit}
    return {"kind": "begin", "attempt": attempt, "timestamp": f"2026-10-17T19:{attempt:02d}:00+00:00", "branch": branch,
            "invocation": invocation, "spec_hash": spec_hash, "family": family, "pid": pid, "boot": boot}


def _end(attempt: int, verdict: str | None = "reject", *, stop=None, failed=None, metrics=None) -> dict:
    if failed is None and metrics is None:
        metrics = {"sharpe": 0.3}
    return {"kind": "end", "attempt": attempt, "verdict": verdict, "stop": stop, "failed": failed, "metrics": metrics,
            "metrics_hash": None if metrics is None else compute_hash(metrics)}


def _record(trial_id: int, family: str = "B1", *, attempt: dict | None = None, subject: str = "other") -> dict:
    return {"trial_id": trial_id, "family": family, "record_hash": f"{trial_id:064x}", "n_trials_in_family": trial_id,
            "invocation": {"subject": subject}, "attempt": attempt}


def _count(lines, records=(), readings=(), **kw):
    return reconcile(lines, collect(records, readings), log_id=_LOG, bucket_of=_BUCKETS, **kw)


def _fields(tmp_path: Path, n: int) -> dict:
    return {"invocation": _begin(n)["invocation"], "spec_hash": _SPEC, "family": "B1", "bucket": "B", "n_trials": 4,
            "worktree": tmp_path, "branch": "research/x", "registry": tmp_path / "r.jsonl", "ledger": tmp_path / "l.jsonl"}


def _written_log(tmp_path: Path) -> Path:
    path = tmp_path / "trial-attempts.jsonl"
    init_log(path, host="zcrypto-ops")
    log = AttemptLog(path)
    for n in (1, 2):
        log.end(log.begin(lambda lines: None, **_fields(tmp_path, n)), verdict="reject", metrics={"sharpe": 0.3})
    return path


def _rewrite(path: Path, change) -> None:
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    change(lines)
    path.write_text("".join(canonical_json(line) + "\n" for line in lines))


def _seal(lines: list[dict], start: int) -> None:
    for i in range(start, len(lines)):
        lines[i]["prev_hash"] = GENESIS_HASH if i == 0 else lines[i - 1]["line_hash"]
        lines[i]["line_hash"] = compute_hash({k: v for k, v in lines[i].items() if k != "line_hash"})


def _repo(root: Path) -> Path:
    root.mkdir(parents=True)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *_GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", "fixture"], check=True, capture_output=True)
    return root


def _commit(root: Path, files: dict[str, str]) -> str:
    for relpath, text in files.items():
        (root / relpath).parent.mkdir(parents=True, exist_ok=True)
        (root / relpath).write_text(text)
    subprocess.run(["git", "-C", str(root), "add", "--", *files], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(root), *_GIT_IDENTITY, "commit", "-q", "-m", "fixture"], check=True, capture_output=True)
    return subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()


def _jsonl(*records: dict) -> str:
    return "".join(canonical_json(record) + "\n" for record in records)


def test_a_log_appends_chained_lines_from_its_genesis(tmp_path, monkeypatch):
    path = tmp_path / "trial-attempts.jsonl"
    log_id = init_log(path, host="zcrypto-ops")
    log = AttemptLog(path)
    monkeypatch.chdir(tmp_path)
    attempt = log.begin(lambda lines: None, **{**_fields(tmp_path, 1), "worktree": Path("."), "registry": Path("r.jsonl")})
    log.end(attempt, verdict="park", metrics={"sharpe": 0.2})

    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert attempt == 1 and [line["kind"] for line in lines] == ["genesis", "begin", "end"]
    assert [sorted(line) for line in lines] == [
        ["host", "kind", "line_hash", "log_id", "prev_hash", "seq", "timestamp"],
        ["attempt", "boot", "branch", "bucket", "family", "host", "invocation", "kind", "ledger", "line_hash", "n_trials", "pid",
         "prev_hash", "registry", "seq", "spec_hash", "timestamp", "worktree"],
        ["attempt", "failed", "kind", "line_hash", "metrics", "metrics_hash", "prev_hash", "seq", "stop", "timestamp", "verdict"],
    ]
    assert [line["seq"] for line in lines] == [1, 2, 3]
    assert re.fullmatch(r"[0-9a-f]{32}", log_id)
    assert (lines[0]["log_id"], lines[0]["host"], lines[0]["prev_hash"]) == (log_id, "zcrypto-ops", GENESIS_HASH)
    for prev, line in zip([None, *lines], lines):
        assert line["line_hash"] == compute_hash({k: v for k, v in line.items() if k != "line_hash"})
        assert line["prev_hash"] == (GENESIS_HASH if prev is None else prev["line_hash"])
    assert path.read_text().splitlines()[1] == canonical_json(lines[1])
    assert lines[1]["worktree"] == str(tmp_path.resolve()) and lines[1]["registry"] == str((tmp_path / "r.jsonl").resolve())
    assert (lines[1]["pid"], lines[1]["boot"]) == (os.getpid(), attempts._boot_id())
    assert lines[2]["metrics_hash"] == compute_hash({"sharpe": 0.2}) and AttemptLog(path).lines == tuple(lines)


def test_a_torn_last_line_is_healed_and_a_torn_middle_line_refused(tmp_path, monkeypatch):
    path = _written_log(tmp_path)
    whole = path.read_bytes()
    torn = whole + b'{"seq":6,"kind":"beg'
    path.write_bytes(torn)
    seen = []
    real = attempts._read_healing

    def spy(*args, **kwargs):
        copies = [(copy.name, copy.read_bytes()) for copy in sorted(tmp_path.glob("trial-attempts.jsonl.torn-*"))]
        seen.append((copies, path.read_bytes()))
        return real(*args, **kwargs)

    monkeypatch.setattr(attempts, "_read_healing", spy)

    assert len(AttemptLog(path).lines) == 5
    ((copies, at_verification),) = seen
    ((name, held),) = copies
    assert re.fullmatch(r"trial-attempts\.jsonl\.torn-\d{8}T\d{6}\.\d{6}Z", name) and held == torn
    assert at_verification == whole == path.read_bytes()
    assert list(tmp_path.glob("trial-attempts.jsonl.torn-*")) == []

    lines = whole.decode().splitlines()
    path.write_text("\n".join([*lines[:2], lines[2][:20], *lines[3:]]) + "\n")
    with pytest.raises(AttemptLogError, match="line 3"):
        AttemptLog(path)


def test_a_torn_tail_another_session_is_still_writing_is_never_healed(tmp_path, monkeypatch):
    path = _written_log(tmp_path)
    whole = path.read_bytes()
    cut = whole.rindex(b"\n", 0, -1) + 21
    path.write_bytes(whole[:cut])
    real = fcntl.flock

    def the_writer_finishes_before_releasing(fd, operation):
        real(fd, operation)
        if operation == fcntl.LOCK_EX and path.read_bytes() == whole[:cut]:
            with path.open("ab") as fh:
                fh.write(whole[cut:])

    monkeypatch.setattr(fcntl, "flock", the_writer_finishes_before_releasing)

    assert len(AttemptLog(path).lines) == 5 and path.read_bytes() == whole
    assert list(tmp_path.glob("trial-attempts.jsonl.torn-*")) == []


def test_a_heal_that_fails_its_chain_keeps_the_copy(tmp_path):
    path = _written_log(tmp_path)
    _rewrite(path, lambda lines: lines[2].update(line_hash="e" * 64))
    torn = path.read_bytes() + b'{"seq":6'
    path.write_bytes(torn)

    with pytest.raises(AttemptLogError, match=r"the healed log breaks at line 3 .*, and its bytes before the heal are kept at .*trial-attempts\.jsonl\.torn-") as refused:
        AttemptLog(path)

    (copy,) = tmp_path.glob("trial-attempts.jsonl.torn-*")
    assert copy.read_bytes() == torn and str(copy) in str(refused.value)
    assert path.read_bytes() == torn[: torn.rindex(b"\n") + 1]
    genesis = tmp_path / "torn-genesis.jsonl"
    genesis.write_bytes(torn[:30])
    with pytest.raises(AttemptLogError, match=r"the healed log breaks at line 1 is not a genesis line, and its bytes before the heal are kept at "):
        AttemptLog(genesis)
    (kept,) = tmp_path.glob("torn-genesis.jsonl.torn-*")
    assert kept.read_bytes() == torn[:30] and genesis.read_bytes() == b""


def test_a_torn_last_line_inside_a_multibyte_character_is_healed(tmp_path):
    path = _written_log(tmp_path)
    whole = path.read_bytes()
    path.write_bytes(whole + '{"seq":6,"branch":"research/ü'.encode()[:-1])

    assert len(AttemptLog(path).lines) == 5 and path.read_bytes() == whole
    assert list(tmp_path.glob("trial-attempts.jsonl.torn-*")) == []


def test_a_short_write_is_refused_and_the_line_it_left_without_its_newline_is_healed(tmp_path, monkeypatch):
    path = _written_log(tmp_path)
    whole = path.read_bytes()
    real = os.write

    with monkeypatch.context() as patch:
        patch.setattr(os, "write", lambda fd, data: real(fd, data[:-1]))
        with pytest.raises(OSError):
            AttemptLog(path).begin(lambda lines: None, **_fields(tmp_path, 3))

    left = path.read_bytes()
    assert left.startswith(whole) and json.loads(left[len(whole):])["kind"] == "begin"
    assert len(AttemptLog(path).lines) == 5 and path.read_bytes() == whole


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param(lambda ls: (ls.pop(0), ls.__setitem__(0, {**ls[0], "seq": 1}), _seal(ls, 0)), "line 1 is not a genesis line", id="no-genesis"),
        pytest.param(lambda ls: (ls.insert(3, {**ls[0], "seq": 4}), [line.update(seq=i + 1) for i, line in enumerate(ls)], _seal(ls, 0)), "line 4 is a second genesis line", id="second-genesis"),
        pytest.param(lambda ls: ls.clear(), "line 1 is not a genesis line", id="empty-log"),
    ],
)
def test_a_log_without_its_genesis_line_is_refused(tmp_path, change, match):
    path = _written_log(tmp_path)
    _rewrite(path, change)
    with pytest.raises(AttemptLogError, match=match):
        AttemptLog(path)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param(lambda ls: (ls[2].update(seq=4), _seal(ls, 2)), "line 3 seq", id="seq-skips"),
        pytest.param(lambda ls: (ls[2].update(prev_hash="e" * 64), ls[2].update(line_hash=compute_hash({k: v for k, v in ls[2].items() if k != "line_hash"})), _seal(ls, 3)), "line 3 prev_hash", id="prev-hash-breaks"),
        pytest.param(lambda ls: ls[2].update(line_hash="e" * 64), "line 3 line_hash", id="line-hash-breaks"),
        pytest.param(lambda ls: (ls[3].update(attempt=3), _seal(ls, 3)), "line 4 begins attempt 3", id="attempt-skips"),
        pytest.param(lambda ls: (ls[4].update(attempt=9), _seal(ls, 4)), "line 5 ends attempt 9", id="end-without-begin"),
        pytest.param(lambda ls: (ls[1].pop("family"), _seal(ls, 1)), r"line 2\b.*'family'", id="begin-without-family"),
    ],
)
def test_a_log_whose_chain_breaks_is_refused(tmp_path, change, match):
    path = _written_log(tmp_path)
    _rewrite(path, change)
    with pytest.raises(AttemptLogError, match=match):
        AttemptLog(path)


def test_attempts_init_refuses_an_existing_log(tmp_path):
    empty, written = tmp_path / "empty.jsonl", tmp_path / "written.jsonl"
    empty.write_bytes(b"")
    init_log(written, host="zcrypto-ops")
    before = written.read_bytes()
    for path in (empty, written):
        remedy = f"{path} exists: a log is created once, never beside the records that cite it; for a damaged one, {_REMEDY_TAIL}"
        with pytest.raises(AttemptLogError, match=re.escape(remedy)):
            init_log(path, host="zcrypto-ops")
    assert empty.read_bytes() == b"" and written.read_bytes() == before


def test_an_end_names_an_open_attempt_with_exactly_one_outcome(tmp_path):
    path = _written_log(tmp_path)
    log = AttemptLog(path)
    for attempt in (2, 9):
        with pytest.raises(AttemptLogError, match=f"attempt {attempt} is not open"):
            log.end(attempt, verdict="reject", metrics={"sharpe": 0.3})
    attempt = log.begin(lambda lines: None, **_fields(tmp_path, 3))
    for outcome, match in [
        ({"verdict": "reject", "stop": "a stop", "metrics": {"sharpe": 0.3}}, "exactly one of verdict, stop and failed"),
        ({"verdict": "reject"}, "metrics must be a non-empty dict exactly when failed is null"),
        ({"failed": "SubjectError: too short", "metrics": {"sharpe": 0.3}}, "metrics must be a non-empty dict exactly when failed is null"),
        ({"verdict": "maybe", "metrics": {"sharpe": 0.3}}, r"verdict must be one of \['adopt', 'park', 'reject'\]"),
    ]:
        with pytest.raises(AttemptLogError, match=match):
            log.end(attempt, **outcome)
    assert len(AttemptLog(path).lines) == 6
    log.end(attempt, stop="the stub's stop", metrics={"sharpe": 0.3})
    log.end(log.begin(lambda lines: None, **_fields(tmp_path, 4)), failed="SubjectError: too short")
    stopped, failed = (line for line in AttemptLog(path).lines[6:] if line["kind"] == "end")
    assert (stopped["stop"], stopped["verdict"], failed["failed"], failed["metrics"]) == ("the stub's stop", None, "SubjectError: too short", None)


def test_begin_counts_over_the_lines_another_session_appended_after_this_log_was_read(tmp_path):
    path = _written_log(tmp_path)
    mine, theirs = AttemptLog(path), AttemptLog(path)
    theirs.begin(lambda lines: None, **_fields(tmp_path, 3))
    seen = []

    attempt = mine.begin(seen.append, **_fields(tmp_path, 4))

    assert attempt == 4 and len(seen[0]) == 6 and seen[0][-1]["attempt"] == 3


def test_the_log_path_is_the_main_checkouts_from_any_worktree(tmp_path, monkeypatch):
    main = _repo(tmp_path / "main")
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "research/x", str(tmp_path / "wt")], check=True, capture_output=True)
    monkeypatch.chdir(tmp_path)

    expected = main.resolve() / ".local" / "trial-attempts.jsonl"
    assert _real_log_path(main) == _real_log_path(tmp_path / "wt") == expected


def test_a_common_dir_with_no_checkout_is_refused(tmp_path):
    work = tmp_path / "work"
    (tmp_path / "store").mkdir()
    subprocess.run(["git", "init", "-q", "--separate-git-dir", str(tmp_path / "store" / "repo.git"), str(work)], check=True, capture_output=True)

    with pytest.raises(AttemptLogError, match="no main checkout at .*, resolved from git rev-parse --git-common-dir: run from a clone with a working tree"):
        _real_log_path(work)


def test_the_branch_is_none_on_a_detached_head_and_an_orphan_from_one_is_named_so(tmp_path):
    main = _repo(tmp_path / "main")
    subprocess.run(["git", "-C", str(main), "checkout", "-q", "--detach"], check=True, capture_output=True)

    assert attempts.current_branch(main) is None
    (orphan,) = _count([_begin(1, branch=None)]).orphans
    assert orphan.describe() == f"{_LOG[:8]}#1 stub no end 2026-10-17T19:01:00+00:00 on a detached HEAD"
```

Expected: collection fails with `ImportError: cannot import name 'attempts' from 'cli.registry'` until Step 4.

- [ ] **Step 2: Write the count's failing tests**, one per D3 class, each fixing every input but one, the carry, the final class of a listed orphan, the hold, `lacking` and `landed`:

```python
# tests/test_trial_attempts.py
def test_an_attempt_a_record_carries_is_landed():
    record = _record(1, attempt={"log": _LOG, "id": 1, "absorbs": [], "counted": []})
    assert _count([_begin(1), _end(1)], [record]).required_n("B1") == 1 + 0 + 1
    assert _count([_begin(1), _end(1)]).required_n("B1") == 0 + 1 + 1


def test_an_attempt_in_an_absorbs_is_landed():
    record = _record(1, attempt={"log": _LOG, "id": 2, "absorbs": [1], "counted": []})
    lines = [_begin(1), _end(1, "park"), _begin(2), _end(2)]
    assert _count(lines, [record]).required_n("B1") == 1 + 0 + 1


def test_equal_arguments_spec_metrics_and_outcome_absorb_the_earlier_attempt():
    assert _count([_begin(1), _end(1), _begin(2), _end(2)]).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1), _end(1), _begin(2, dataset="ohlc-other"), _end(2)]).required_n("B1") == 0 + 2 + 1


def test_an_outcome_that_differs_on_equal_metrics_absorbs_nothing():
    assert _count([_begin(1), _end(1, "reject"), _begin(2), _end(2, "park")]).required_n("B1") == 0 + 2 + 1


def test_a_begin_only_attempt_is_absorbed_by_a_retry_with_its_arguments():
    assert _count([_begin(1), _begin(2), _end(2)]).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1), _begin(2, dataset="ohlc-other"), _end(2)]).required_n("B1") == 0 + 2 + 1
    assert _count([_begin(1), _begin(2)]).required_n("B1") == 0 + 2 + 1


def test_an_attempt_under_another_spec_is_never_absorbed():
    assert _count([_begin(1), _end(1), _begin(2, spec_hash="e" * 64), _end(2)]).required_n("B1") == 0 + 2 + 1
    assert _count([_begin(1), _begin(2, spec_hash="e" * 64), _end(2)]).required_n("B1") == 0 + 2 + 1
    hold = ("stub", attempts.arguments(_begin(1)["invocation"]), "e" * 64)
    assert _count([_begin(1), _end(1)], hold=hold).required_n("B1") == 0 + 1 + 1


def test_a_retry_at_another_commit_is_absorbed():
    assert _count([_begin(1), _end(1), _begin(2, commit="e" * 40), _end(2)]).required_n("B1") == 0 + 1 + 1


def test_a_begin_only_attempt_with_no_retry_is_an_orphan():
    count = _count([_begin(1)])
    assert (count.required_n("B1"), count.spent("B")) == (2, 1)
    assert count.counted("B1") == []


def test_a_stop_counts_zero():
    assert _count([_begin(1), _end(1, None, stop="the stub's stop")]).required_n("B1") == 1


def test_a_failed_attempt_counts_zero():
    assert _count([_begin(1), _end(1, None, failed="SubjectError: too short")]).required_n("B1") == 1


def test_an_orphan_counts_once_against_its_family_and_its_bucket():
    count = _count([_begin(1, family="B2"), _end(1)], [_record(1, "B1"), _record(2, "A1")])
    assert (count.required_n("B2"), count.required_n("B1")) == (0 + 1 + 1, 1 + 0 + 1)
    assert (count.spent("B"), count.spent("A")) == (2, 1)
    assert [(e["log"], e["id"], e["family"], e["verdict"]) for e in count.counted("B1")] == [(_LOG, 1, "B2", "reject")]
    elsewhere = _count([_begin(1, family="B2"), _end(1), _begin(2, family="A1", dataset="ohlc-other"), _end(2)])
    assert [e["id"] for e in elsewhere.counted("B1")] == [1]


_LISTED = {"log": _OTHER, "id": 7, "family": "B2", "subject": "b2-funding-derisk", "spec_hash": _SPEC, "verdict": "reject",
           "metrics": {"sharpe": 0.1}}


def test_an_orphan_a_landed_record_lists_is_carried_from_any_log():
    lister = _record(1, attempt={"log": _OTHER, "id": 8, "absorbs": [], "counted": [_LISTED]})
    count = _count([], [lister])
    assert count.required_n("B2") == 0 + 1 + 1 and count.counted("B1") == [_LISTED]
    assert count.orphans[0].describe() == f"{_OTHER[:8]}#7 b2-funding-derisk reject listed by trial 1"
    relister = _record(2, attempt={"log": _OTHER, "id": 9, "absorbs": [], "counted": [_LISTED]})
    twice = _count([], [lister, relister])
    assert (twice.required_n("B2"), twice.spent("B"), twice.counted("B1")) == (0 + 1 + 1, 2 + 1, [_LISTED])
    landing = _record(3, "B2", attempt={"log": _OTHER, "id": 10, "absorbs": [7], "counted": []})
    assert _count([], [lister, relister, landing]).required_n("B2") == 1 + 0 + 1


def test_a_listed_orphans_class_is_final():
    lines = [_begin(1), _end(1), _begin(2), _end(2)]
    entry = {"log": _LOG, "id": 1, "family": "B1", "subject": "stub", "spec_hash": _SPEC, "verdict": "reject", "metrics": {"sharpe": 0.3}}
    lister = _record(1, "B2", attempt={"log": _OTHER, "id": 1, "absorbs": [], "counted": [entry]})
    assert _count(lines).required_n("B1") == 0 + 1 + 1
    assert _count(lines, [lister]).required_n("B1") == 0 + 2 + 1
    landing = _record(2, "B1", attempt={"log": _LOG, "id": 3, "absorbs": [1], "counted": []})
    assert _count(lines, [lister, landing]).required_n("B1") == 1 + 1 + 1


def test_a_held_attempt_is_out_of_the_orphans_until_this_run_absorbs_it_or_not():
    hold = ("stub", attempts.arguments(_begin(1)["invocation"]), _SPEC)
    assert _count([_begin(1), _end(1)], hold=hold).required_n("B1") == 0 + 0 + 1
    other = ("stub", attempts.arguments(_begin(1, dataset="ohlc-other")["invocation"]), _SPEC)
    assert _count([_begin(1), _end(1)], hold=other).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1), _end(1)], hold=hold, hold_finished=False).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1)], hold=hold, hold_finished=False).required_n("B1") == 0 + 0 + 1
    same = _count([_begin(1), _end(1), _begin(2), _end(2)], own=2)
    assert (same.required_n("B1"), same.absorbs) == (1, (1,))
    moved = _count([_begin(1), _end(1), _begin(2), _end(2, metrics={"sharpe": 0.4})], own=2)
    assert (moved.required_n("B1"), moved.absorbs) == (2, ())


def _reaped_pid() -> int:
    child = subprocess.Popen(["true"])
    child.wait()
    return child.pid


@pytest.mark.parametrize(
    ("marks", "gone"),
    [
        pytest.param(lambda: {"pid": os.getpid(), "boot": attempts._boot_id()}, False, id="its-process-runs"),
        pytest.param(lambda: {"pid": _reaped_pid(), "boot": attempts._boot_id()}, True, id="its-pid-reaped"),
        pytest.param(lambda: {"pid": os.getpid(), "boot": "another boot"}, True, id="another-boot"),
    ],
)
def test_an_open_attempt_is_held_or_absorbed_only_when_its_process_is_gone(marks, gone):
    assert re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}", attempts._boot_id())
    open_x = {**_begin(1), **marks()}
    hold = ("stub", attempts.arguments(open_x["invocation"]), _SPEC)
    assert attempts._alive(open_x) is not gone
    for hold_finished in (True, False):
        assert _count([open_x], hold=hold, hold_finished=hold_finished).required_n("B1") == (1 if gone else 2)
    retried = _count([open_x, _begin(2), _end(2)], own=2)
    assert (retried.required_n("B1"), retried.absorbs) == ((1, (1,)) if gone else (2, ()))
    assert _count([open_x, _begin(2), _end(2)]).required_n("B1") == (2 if gone else 3)


def test_a_log_lacking_an_attempt_a_record_or_reading_names_is_found():
    record = _record(1, attempt={"log": _LOG, "id": 3, "absorbs": [2], "counted": []})
    reading = {"reading_id": 1, "record_hash": "9" * 64, "attempt": {"log": _LOG, "id": 5, "absorbs": []}}
    foreign = _record(2, attempt={"log": _OTHER, "id": 4, "absorbs": [], "counted": []})
    assert lacking([_begin(1), _begin(2), _begin(3)], collect([record, foreign], [reading]), _LOG) == [("reading 1", 5)]
    assert lacking([_begin(1)], collect([record], []), _LOG) == [("trial 1", 3), ("trial 1", 2)]
    lister = _record(3, attempt={"log": _OTHER, "id": 5, "absorbs": [], "counted": [{**_LISTED, "log": _LOG, "id": 3}, _LISTED]})
    assert lacking([_begin(1), _begin(2), _begin(3), _end(3)], collect([lister], []), _LOG) == []
    assert lacking([_begin(1), _begin(2), _begin(3)], collect([lister], []), _LOG) == [("trial 3", 3)]
    assert lacking([_begin(1), _begin(2)], collect([lister], []), _LOG) == [("trial 3", 3)]


def test_the_count_reads_records_1_to_48_and_reading_1_in_either_landed_shape(tmp_path):
    raw = (REPO / attempts.REGISTRY_RELPATH).read_text(encoding="utf-8").splitlines()[:48]
    raw_reading = (REPO / attempts.LEDGER_RELPATH).read_text(encoding="utf-8").splitlines()[:1]
    (tmp_path / "registry.jsonl").write_text("".join(line + "\n" for line in raw))
    (tmp_path / "ledger.jsonl").write_text("".join(line + "\n" for line in raw_reading))
    shapes = {
        "as git show reads them": collect([loads_strict(line) for line in raw], [loads_strict(line) for line in raw_reading]),
        "as the store loads them": attempts.files_landed(tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"),
    }

    for shape, landed in shapes.items():
        count = reconcile([], landed, log_id=_LOG, bucket_of=_BUCKETS)
        assert (count.required_n("B1"), count.spent("B"), count.spent("A"), count.required_n("P1")) == (4, 3, 40, 6), shape
        assert count.counted("B1") == [] and lacking([], landed, _LOG) == [], shape


def _append_one(path: Path) -> dict:
    block = {"ohlc-test": {"files": {"BTC/EUR/1440.parquet": "c" * 64}, "rows": 10, "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"]}}
    invocation = {"subject": "seed", "dataset": "ohlc-test", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None, "commit": "d" * 40}
    TrialRegistry(path).append(iteration="iter-001", family="B1", spec_hash="s", datasets=block, invocation=invocation, seeds=[0],
                               metrics={"sharpe": 0.3}, n_trials_in_family=1, verdict="reject", run_ref="cli/registry/record.py")
    return json.loads(path.read_text().splitlines()[-1])


def test_landed_reads_the_targets_head_and_origin_develop_each_record_once(tmp_path):
    root = _repo(tmp_path / "repo")
    target = _append_one(tmp_path / "target.jsonl")
    with_attempt = _record(2, attempt={"log": _LOG, "id": 1, "absorbs": [], "counted": []})
    rebased = {**with_attempt, "trial_id": 3, "record_hash": "8" * 64}
    develop_only = _record(4, attempt={"log": _OTHER, "id": 1, "absorbs": [], "counted": []})
    reading = {"reading_id": 1, "record_hash": "9" * 64, "attempt": {"log": _LOG, "id": 5, "absorbs": []}}
    committed = {attempts.REGISTRY_RELPATH: _jsonl(target, with_attempt, develop_only), attempts.LEDGER_RELPATH: _jsonl(reading)}
    develop = _commit(root, committed)
    subprocess.run(["git", "-C", str(root), "update-ref", attempts.DEVELOP, develop], check=True, capture_output=True)
    _commit(root, {attempts.REGISTRY_RELPATH: _jsonl(target, rebased)})

    found = _real_landed(root, tmp_path / "target.jsonl", tmp_path / "no-ledger.jsonl")

    assert sorted(record["record_hash"] for record in found.records) == sorted(
        [target["record_hash"], rebased["record_hash"], develop_only["record_hash"]]
    )
    assert found.readings == (reading,)
    empty = _repo(tmp_path / "empty")
    subprocess.run(["git", "-C", str(empty), "update-ref", attempts.DEVELOP, "HEAD"], check=True, capture_output=True)
    assert _real_landed(empty, tmp_path / "absent.jsonl", tmp_path / "absent-ledger.jsonl") == collect([], [])


def test_landed_refuses_an_unresolvable_develop(tmp_path):
    root = _repo(tmp_path / "repo")
    with pytest.raises(AttemptLogError, match=re.escape(f"origin/develop does not resolve in {root}: run git fetch origin develop, then run again")):
        _real_landed(root, tmp_path / "r.jsonl", tmp_path / "l.jsonl")
```

Expected: collection fails with `ImportError: cannot import name 'attempts' from 'cli.registry'`.

- [ ] **Step 3: Run them to verify they fail**

Run: `mkdir -p .tmp/plan-00133 && uv run pytest tests/test_trial_attempts.py -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `ERROR collecting tests/test_trial_attempts.py` — `ImportError: cannot import name 'attempts' from 'cli.registry'`.

- [ ] **Step 4: Implement the log in `cli/registry/attempts.py`** — the Interfaces block's names, and:
  - `main_checkout`: `_git(code_root, "rev-parse", "--git-common-dir")`, resolved against `code_root` when relative, its parent; refused unless `_git(parent, "rev-parse", "--show-toplevel")` prints that parent (both through `Path.resolve()`), with D1's remedy "no main checkout at <dir>, resolved from git rev-parse --git-common-dir: run from a clone with a working tree". `log_path` is `main_checkout(code_root) / LOG_RELPATH`. `current_branch`: `_git(code_root, "branch", "--show-current")`, empty output is `None`.
  - `_write_line`: `os.write(fd, line)` called through the module (`import os`), so a test wraps it, and an `OSError` naming the bytes written and the line's when it wrote fewer, so a writer returns only once its whole line, `\n` included, is written; every line the log gains — `init_log`'s genesis, `begin`'s, `end`'s — goes through it.
  - `_boot_id` reads `BOOT_ID` and strips it; `_process_marks` returns `{"pid": os.getpid(), "boot": _boot_id()}`, which `begin` calls through the module's namespace, so a test that patches `attempts._process_marks` stands a run's attempt for one whose process is gone; `_alive(begin)` — spec D3's liveness test — returns `False` when `begin["boot"]` is not `_boot_id()` or `os.kill(begin["pid"], 0)` raises `ProcessLookupError`, and `True` otherwise, a `PermissionError` being a live process another user owns.
  - `init_log`: an exclusive create (`os.O_WRONLY | os.O_CREAT | os.O_EXCL`), its line written through `_write_line`, `fsync`'d; an existing path, empty or not, raises D1's first remedy verbatim, "<path> exists: a log is created once, never beside the records that cite it; for a damaged one, rename it aside, then restore it from a backup if one exists; otherwise create a new log with zcrypto research attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost".
  - The read, one `_read_healing` call per read, always under the log's flock — `fcntl.flock(fd, fcntl.LOCK_EX)` called through the module (`import fcntl`), so a test wraps it, on an `os.open(path, os.O_WRONLY | os.O_APPEND)` descriptor: the constructor takes it for its own read, while `begin`, `end` and `locked()` read under the one they already hold and never open a second, whose flock would wait on the first; a writer holds the flock from its write through its `fsync`, so a read under it never sees another session's line half written: when the bytes are not empty and do not end in `\n` — a torn last line, parseable or not, decoded by nothing before the heal, since a tear can fall inside a multibyte character (Global Constraints) — copy the whole file aside, truncate it after its last `\n`, then `_read_healing(path, _validate_line, _verify_chain)` over the healed file, then unlink the copy; an empty result is refused by `_verify_chain([])` itself ("line 1 is not a genesis line"), called by the read, since `_read_healing` returns `[]` for an empty file without calling its check (`store.py:111-112`), and on the heal path before the copy is unlinked; every refusal of a read is an `AttemptLogError` reading "<path>: line <n> <what breaks>" — `_read_healing`'s malformed-JSON refusal re-raised as "line <n> is not JSON" — and, when a copy was made, D1's third form, "<path>: the healed log breaks at line <n> <what breaks>, and its bytes before the heal are kept at <copy>", the copy kept. `_validate_line` checks each kind's key set exactly — the formats section's, which `test_a_log_appends_chained_lines_from_its_genesis` lists — refusing as "<path>: line <n> keys must be exactly [...] (missing [...], unknown [...])", each list sorted; `_verify_chain` raises `AttemptLogError(f"{path}: line {n} {what breaks}")` for a line 1 that is no genesis or absent ("is not a genesis line"), a second genesis ("is a second genesis line"), a `seq` out of place, a `prev_hash` or `line_hash` that does not hold, a `begin` whose `attempt` is not the next ("begins attempt <a>"), an `end` naming no open attempt ("ends attempt <a>").
  - `AttemptLog.__init__` opens that descriptor first, an absent path (`FileNotFoundError`) refused as "no trial-attempts log at <path>", and releases the flock and closes the descriptor before it returns; `begin` and `end` take `fcntl.flock(LOCK_EX)` on an `os.open(path, os.O_WRONLY | os.O_APPEND)` descriptor (never `O_CREAT`), re-read the lines under the lock, set `seq`, `prev_hash`, `line_hash`, run `_verify_chain` over the lines plus the new one before writing, write one line through `_write_line`, `fsync`, unlock, and refresh `self.lines`; each of the four — the constructor, `begin`, `end` and `locked()` — releases the flock and closes the descriptor in a `finally`, since every one of them can raise under it (a broken chain, a short write, `admit`'s count and budget refusals, `end`'s refusals, the count, budget and store refusals inside `locked()`), and a raw descriptor left locked makes the process's next read wait on it forever; `begin` calls `admit(lines)` with the re-read lines before composing its line and stores `timestamp`, `host` (`socket.gethostname()`), the `pid` and `boot` `_process_marks()` returns, and `worktree`, `registry`, `ledger` as absolute strings (`Path.resolve()`); `end` refuses, before composing its line, an attempt with no `begin` or an earlier `end` ("attempt <a> is not open" — a wording `_verify_chain` never prints, so the test tells this check from the chain's), an outcome other than exactly one of the three ("exactly one of verdict, stop and failed"), `metrics` other than a non-empty dict while `failed` is null or other than null while it is set ("metrics must be a non-empty dict exactly when failed is null"), and a non-null `verdict` outside `VERDICTS` ("verdict must be one of [...]", sorted), a stop's and a failure's `verdict` being null — every rule the formats section gives an `end` line that composing it does not make true by itself: `metrics_hash` is computed here, `stop` and `failed` are the command's text, and the metric leaves are Task 5's check before the `end`; a verdict outside `VERDICTS` or a verdict with no metrics would otherwise be a finished orphan whose `counted` entry every later record of its bucket must carry and the store refuses. `locked()` holds the same flock over a re-read and yields the lines; nothing inside it calls `begin` or `end`.

- [ ] **Step 5: Implement the reads of what landed** — `collect` keeps each record once, by `("attempt", log, id)` when `record.get("attempt")` is set and else by `("hash", record_hash)`, the first seen kept, readings alike; `files_landed` reads the two target files through `TrialRegistry(registry).records` and `ReadingLedger(ledger).records` (`dataclasses.asdict`), an absent file reading as none; `landed` refuses unless `_git(code_root, "rev-parse", "--verify", "--quiet", f"{DEVELOP}^{{commit}}")` exits 0, with D3's remedy "origin/develop does not resolve in <root>: run git fetch origin develop, then run again", then merges, in this order, the target files, `HEAD` and `origin/develop` — the registry and the ledger at each ref, `REGISTRY_RELPATH` and `LEDGER_RELPATH` — each ref's file read only when `_git(code_root, "cat-file", "-e", f"{ref}:{path}")` exits 0, through `git show`, a line at a time through `loads_strict` — a `git show` that exits non-zero raises `AttemptLogError` naming the ref and the path, never reads as an empty file. The two shapes `landed` returns differ on records 1–48 and reading 1: as `git show` reads them they carry no `attempt` key (records 1–47 no `invocation` key either), as the store loads them `attempt` is null (`invocation` null on 1–47); so every read of a landed record's or reading's `attempt`, `absorbs`, `counted` or `invocation` — `collect`, `_landed_ids`, `listed` and `lacking` here, D4's frozen check in Task 7, `_attempt_findings` in Task 8 — goes through `.get`, an absent or null value reading as none.

- [ ] **Step 6: Implement the count** — `reconcile` is the algorithm D3 and its author's calls fix; with `landed_ids = _landed_ids(landed)` (every `attempt` (log, id) and every `absorbs` id of a landed record or reading) and `listed` the (log, id) every landed record's `attempt.counted` names, each local attempt X except `own`, in id order, is:
  1. landed — `(log_id, X.id)` in `landed_ids`;
  2. absorbed — by the earliest later attempt Y (Y may be `own`) whose `arguments(invocation)` and `spec_hash` equal X's and which, when X has an `end`, has an `end` with X's non-null `metrics_hash` and X's (`verdict`, `stop`), and, when X has none, has any `end` while `_alive(X.begin)` is false; for X in `listed`, only Y == `own` qualifies; `Count.absorbs` is the X whose absorber is `own`, ascending;
  3. stopped, or 4. failed — its `end` stored `stop`, or `failed`: counts 0 (skipped for X in `listed`, which counts as an orphan whatever its log says);
  5. held — `hold` given, `(X.begin.invocation.subject, arguments(...), spec_hash)` equals it, and X open with `_alive(X.begin)` false, or X finished and `hold_finished`: counts 0;
  6. orphan — every other, its `Orphan` from its `begin` and `end` (`verdict` and `metrics` None while open).
  Then every `listed` (log, id) neither landed nor a local attempt of `log_id` is a carried `Orphan` from its entry, `listed_by` the listing record's `trial_id`, each (log, id) once — an `if` that skips a (log, id) already carried, since once a record lists an orphan every later record of its bucket lists it too (CI check xii). `required_n(F)` = landed records of family F + orphans of F + 1; `spent(b)` = landed records whose `bucket_of.get(family)` is b + orphans whose family maps to b; `counted(F)` = the `entry()` of every orphan with a non-null `verdict` in F's bucket — family F itself when F is bucketless — sorted by (log, id). `describe()` is "<log8>#<id> <subject> <verdict, or no end> <timestamp> on <branch, or a detached HEAD>" for a local orphan and "<log8>#<id> <subject> <verdict> listed by trial <N>" for a carried one. `lacking` returns ("trial N" or "reading N", id) for each `attempt` id and then each `absorbs` id of this log that a landed entry names with no `begin` in `lines`, and then for each `counted` entry naming this log whose attempt has no `end` in `lines`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `uv run pytest tests/test_trial_attempts.py -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: all pass.

- [ ] **Step 8: Run the consumers, then commit**

Run: `bash infra/scripts/consumers.sh --direct cli/registry/attempts.py tests/test_trial_attempts.py`, then each listed test file under the same pytest flags, and the Global Constraints' walker for files under `cli/`.

```bash
git add cli/registry/attempts.py tests/test_trial_attempts.py
git commit -F - <<'EOF'
feat(registry): the trial-attempts log, hash-chained in the main checkout, and the count that reconciles it with the landed records

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 9: Probe each guard** — controls: `s/^def _verify_chain(/def _verify_chain_gone(/` for the log's cases, `s/^def init_log(/def init_log_gone(/` for `test_attempts_init_refuses_an_existing_log`, which reads no log, `s/^def _landed_ids(/def _landed_ids_gone(/` for the count's, `s/^def lacking(/def lacking_gone(/` for `test_a_log_lacking_an_attempt_a_record_or_reading_names_is_found`, which reaches no `_landed_ids`, `s/^def _git(/def _git_gone(/` for the git cases, each `--file cli/registry/attempts.py`; for the torn-middle row, `--file cli/registry/store.py` with control `s/^def _read_healing(/def _read_healing_gone(/`. Each row one probe, expected `KILLED`:

| `-k` case | mutation |
| -- | -- |
| `test_a_log_appends_chained_lines_from_its_genesis` | `begin`'s `resolve()` of `worktree` cut; apart, the genesis `timestamp` key cut from `init_log`'s line and from `_validate_line`'s genesis set, one sed of two substitutions; apart, `_process_marks`'s `os.getpid()` made `1`; apart, its `"boot": _boot_id()` made `"boot": ""` |
| `test_a_torn_last_line_is_healed_and_a_torn_middle_line_refused` | the copy-aside call made `None` |
| `test_a_torn_last_line_is_healed_and_a_torn_middle_line_refused` (store.py) | `if is_last and not ends_nl:` made `if True:` |
| `test_a_torn_tail_another_session_is_still_writing_is_never_healed` | the flock the constructor's read takes made `None`, range-addressed from `def __init__(` to the next `def` |
| `test_a_heal_that_fails_its_chain_keeps_the_copy` | the healed read's `_verify_chain` argument replaced by `lambda lines, path: None` |
| `test_a_torn_last_line_inside_a_multibyte_character_is_healed` | the heal's not-ending-in-`\n` condition made `False`, so `_read_healing` decodes the torn bytes |
| `test_a_short_write_is_refused_and_the_line_it_left_without_its_newline_is_healed` | `_write_line`'s short-write check made `if False:`; apart, the heal's not-ending-in-`\n` condition made `False` |
| `test_a_log_without_its_genesis_line_is_refused and no-genesis` | the line-1 genesis check made `if False:` |
| `test_a_log_without_its_genesis_line_is_refused and second-genesis` | the second-genesis check made `if False:` |
| `test_a_log_without_its_genesis_line_is_refused and empty-log` | the read's own `_verify_chain` call over an empty result made `None` |
| `test_a_log_whose_chain_breaks_is_refused and seq-skips` / `prev-hash-breaks` / `line-hash-breaks` / `attempt-skips` / `end-without-begin` | each check made `if False:`, one probe each |
| `test_a_log_whose_chain_breaks_is_refused and begin-without-family` | `_validate_line`'s key-set check made `if False:` |
| `test_attempts_init_refuses_an_existing_log` | `\| os.O_EXCL` cut |
| `test_an_end_names_an_open_attempt_with_exactly_one_outcome` | the open-attempt check made `if False:`; apart, the exactly-one check; apart, the metrics-exactly-when-not-failed check; apart, the `VERDICTS` check — each made `if False:`; apart, the `VERDICTS` check's non-null condition cut, so a stop's `end` is refused |
| `test_begin_counts_over_the_lines_another_session_appended_after_this_log_was_read` | `admit` called with `self.lines` in place of the re-read lines |
| `test_the_log_path_is_the_main_checkouts_from_any_worktree` | `"--git-common-dir"` made `"--git-dir"` |
| `test_a_common_dir_with_no_checkout_is_refused` | the show-toplevel comparison made `if False:` |
| `test_the_branch_is_none_on_a_detached_head_and_an_orphan_from_one_is_named_so` | `"a detached HEAD"` fallback made `str(self.branch)` |
| `test_an_attempt_a_record_carries_is_landed` | the `attempt` id cut from `_landed_ids` |
| `test_an_attempt_in_an_absorbs_is_landed` | the `absorbs` ids cut from `_landed_ids` |
| `test_equal_arguments_spec_metrics_and_outcome_absorb_the_earlier_attempt` | the absorbed class made `if False:`; apart, `arguments` equality cut from the clause a finished X meets |
| `test_an_outcome_that_differs_on_equal_metrics_absorbs_nothing` | the (`verdict`, `stop`) equality cut from the finished clause |
| `test_a_begin_only_attempt_is_absorbed_by_a_retry_with_its_arguments` | the open-X clause made `False`; apart, `arguments` equality cut from the clause an open X meets, one probe with the finished X's row when the two clauses share the condition; apart, the open-X clause's `end` requirement on Y made `True` |
| `test_an_attempt_under_another_spec_is_never_absorbed` | `spec_hash` equality cut from the clause a finished X meets; apart, from the clause an open X meets, one probe when the two clauses share the condition; apart, the held class's tuple compared without its `spec_hash` |
| `test_a_retry_at_another_commit_is_absorbed` | `arguments` returns the invocation whole |
| `test_a_begin_only_attempt_with_no_retry_is_an_orphan` | the `verdict` filter cut from `counted` |
| `test_a_stop_counts_zero` / `test_a_failed_attempt_counts_zero` | each class made `if False:` |
| `test_an_orphan_counts_once_against_its_family_and_its_bucket` | `spent`'s `bucket_of.get(...)` comparison made against the family; apart, `counted`'s bucket filter cut |
| `test_an_orphan_a_landed_record_lists_is_carried_from_any_log` | the carried loop made `if False:`; apart, its landed exemption cut; apart, its once-per-(log, id) `if` made `if False:` |
| `test_a_listed_orphans_class_is_final` | the listed restriction cut from the absorbed clause |
| `test_a_held_attempt_is_out_of_the_orphans_until_this_run_absorbs_it_or_not` | the held class made `if False:`; apart, `own` excluded from the absorbers; apart, the held class's tuple compared without its arguments; apart, its condition on X's `end` — open and gone, or finished and `hold_finished` — made `True`; apart, the same condition made `hold_finished` alone |
| `test_an_open_attempt_is_held_or_absorbed_only_when_its_process_is_gone and its-process-runs` | the held class's `_alive(X.begin)`-false conjunct made `True`; apart, the absorbed clause's, one probe when the two share the condition, each range-addressed to its clause; apart, `_boot_id`'s `.strip()` cut, range-addressed from `def _boot_id(` to the next `def` |
| `test_an_open_attempt_is_held_or_absorbed_only_when_its_process_is_gone and its-pid-reaped` | `_alive`'s `ProcessLookupError` branch made to return `True`, range-addressed from `def _alive(` to the next `def` |
| `test_an_open_attempt_is_held_or_absorbed_only_when_its_process_is_gone and another-boot` | `_alive`'s boot comparison made `if False:` |
| `test_a_log_lacking_an_attempt_a_record_or_reading_names_is_found` | the `absorbs` ids cut from `lacking`; apart, readings cut; apart, the `counted` entries cut; apart, the `counted` entries' `end` test made a `begin` test |
| `test_the_count_reads_records_1_to_48_and_reading_1_in_either_landed_shape` | `_landed_ids`'s `.get("attempt")` made `["attempt"]`; apart, `lacking`'s — each range-addressed from its `def` to the next `def` |
| `test_landed_reads_the_targets_head_and_origin_develop_each_record_once` | the attempt key in `collect` made the hash key; apart, `DEVELOP` cut from the refs; apart, the `cat-file -e` check made `if True:`; apart, `LEDGER_RELPATH` cut from the refs' paths |
| `test_landed_refuses_an_unresolvable_develop` | the develop check made `if False:` |

______________________________________________________________________

### Task 2: the budget table — `cli/registry/budget.py` (D5)

**Files:**
- Create: `cli/registry/budget.py`
- Modify: `tests/test_trial_registry_provenance.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BUCKET_OF: dict[str, str | None]`, `BUDGET: dict[str, int]`, read through the module (`budget.BUCKET_OF`) by the command; a test's `monkeypatch.setitem` mutates the one dict, whatever the import.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_trial_registry_provenance.py
from cli.registry import budget


def test_the_budgets_and_buckets_are_the_master_plans_literals():
    growth = (
        "an expansion is the owner's ruling and a new family joins with its bucket: each lands in a pull request that "
        "changes this literal and quotes the ruling"
    )
    assert budget.BUDGET == {"A": 40, "B": 25, "C": 10}, growth
    assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "P1": None}, growth
    assert {bucket for bucket in budget.BUCKET_OF.values() if bucket is not None} <= set(budget.BUDGET), growth
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_trial_registry_provenance.py::test_the_budgets_and_buckets_are_the_master_plans_literals -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `ImportError: cannot import name 'budget' from 'cli.registry'`.

- [ ] **Step 3: Implement `cli/registry/budget.py`** — the two literals of the Global Constraints, a comment citing the trial budgets of `docs/research/00.master-plan.md` §12 by section, never by line, and the ruling an expansion takes.

- [ ] **Step 4: Run it to verify it passes** — the Step 2 command, expected `1 passed`.

- [ ] **Step 5: Consumers, the Global Constraints' walker for files under `cli/` among them, then commit**

```bash
git add cli/registry/budget.py tests/test_trial_registry_provenance.py
git commit -F - <<'EOF'
feat(registry): the hard budgets and the bucket of each family, as literals CI asserts

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probe** — `--file cli/registry/budget.py`, control `s/^BUDGET\b/BUDGET_GONE/`, which matches the name annotated or not, mutation `"B": 25` made `"B": 26`, case `test_the_budgets_and_buckets_are_the_master_plans_literals`; and mutation `"B2": "B"` made `"B2": "C"`, the same case.

______________________________________________________________________

### Task 3: the allowlist, `zcrypto research attempts-init` and the transport's exclusion of the log (D6's file and transport call, D1's command)

**Files:**
- Create: `docs/reference/trial-attempt-logs.txt`
- Modify: `cli/registry/attempts.py`, `cli/research/command.py`, `README.md` (the `zcrypto research` section: a usage line and a paragraph for `attempts-init`), `infra/scripts/workspace-transport.zsh` (the log excluded from both `.local/` rsyncs)
- Test: `tests/test_trial_attempts.py`, `tests/test_research_command.py`, `tests/test_trial_registry_provenance.py`, `tests/test_workspace_transport.py`

**Interfaces:**
- Consumes: Task 1's `init_log`, `log_path`, `AttemptLogError`, `_git`, `DEVELOP`, `AttemptLog`.
- Produces:

```python
ALLOWLIST = "docs/reference/trial-attempt-logs.txt"
def parse_allowlist(text: str) -> dict[str, str]: ...  # log_id -> host; refuses a malformed or repeated row, naming its row
def allowed_log_ids(code_root: Path) -> frozenset[str]: ...  # the rows on origin/develop alone, through git show

@research_app.command("attempts-init")
def attempts_init() -> None: ...
```

and, in `infra/scripts/workspace-transport.zsh`, the array `LOCAL_EXCLUDES`, which both `.local/` rsyncs pass.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trial_attempts.py
_real_allowed = attempts.allowed_log_ids


@pytest.mark.parametrize(
    ("text", "match"),
    [
        pytest.param(f"{_LOG.upper()} zcrypto-ops\n", "row 1", id="uppercase-id"),
        pytest.param(f"{_LOG}\n", "row 1", id="no-host"),
        pytest.param(f"{_LOG} zcrypto-ops\n{_LOG} zcrypto-red\n", "row 2 repeats", id="repeated-id"),
    ],
)
def test_the_allowlist_refuses_a_malformed_or_repeated_row(text, match):
    assert attempts.parse_allowlist(f"{_LOG} zcrypto-ops\n{_OTHER} zcrypto-red\n") == {_LOG: "zcrypto-ops", _OTHER: "zcrypto-red"}
    with pytest.raises(AttemptLogError, match=match):
        attempts.parse_allowlist(text)


def test_the_allowed_ids_are_the_allowlists_on_origin_develop_never_a_branchs_own(tmp_path):
    root = _repo(tmp_path / "repo")
    develop = _commit(root, {attempts.ALLOWLIST: f"{_OTHER} zcrypto-red\n"})
    subprocess.run(["git", "-C", str(root), "update-ref", attempts.DEVELOP, develop], check=True, capture_output=True)
    _commit(root, {attempts.ALLOWLIST: f"{_OTHER} zcrypto-red\n{_LOG} zcrypto-ops\n"})

    assert _real_allowed(root) == {_OTHER}
    bare = _repo(tmp_path / "bare")
    subprocess.run(["git", "-C", str(bare), "update-ref", attempts.DEVELOP, "HEAD"], check=True, capture_output=True)
    assert _real_allowed(bare) == frozenset()
```

```python
# tests/test_research_command.py
from cli.registry import attempts


def test_attempts_init_writes_one_genesis_line_and_prints_its_allowlist_row(tmp_path, monkeypatch):
    path = tmp_path / "fresh-clone" / ".local" / "trial-attempts.jsonl"
    path.parent.mkdir(parents=True)
    monkeypatch.setattr(attempts, "log_path", lambda code_root: path)

    result = runner.invoke(app, ["research", "attempts-init"])

    assert result.exit_code == 0, result.output
    log = attempts.AttemptLog(path)
    assert len(log.lines) == 1 and f"{log.log_id} {log.host}" in result.output.splitlines()
    assert "docs/reference/trial-attempt-logs.txt" in result.output
    again = runner.invoke(app, ["research", "attempts-init"])
    assert again.exit_code == 1 and "exists: a log is created once" in again.output
    assert len(attempts.AttemptLog(path).lines) == 1
```

```python
# tests/test_trial_registry_provenance.py
from cli.registry.attempts import parse_allowlist

ALLOWLIST_FILE = REPO / "docs" / "reference" / "trial-attempt-logs.txt"


def test_the_allowlist_rows_are_ids_and_hosts_each_id_once():
    assert parse_allowlist(ALLOWLIST_FILE.read_text(encoding="utf-8")), (
        "the allowlist lists every trial-attempts log ever created, one row each, and no row is ever removed"
    )
```

```python
# tests/test_workspace_transport.py
_LOCAL_EXCLUDES = re.compile(r"^LOCAL_EXCLUDES=\(.*\)$", re.M)


def test_the_local_mirror_leaves_each_machines_trial_attempts_log_and_its_torn_copies_where_they_are(tmp_path):
    (line,) = _LOCAL_EXCLUDES.findall(SCRIPT.read_text())
    source, destination = tmp_path / "source", tmp_path / "destination"
    for root in (source, destination):
        root.mkdir()
        (root / "trial-attempts.jsonl").write_text(f"{root.name}\n")
        (root / f"trial-attempts.jsonl.torn-{root.name}").write_text(f"{root.name}\n")
    (source / "memo.md").write_text("memo\n")
    (destination / "retro.md").write_text("destination only\n")
    # `bash` runs the zsh script's array line, which means the same in both, so the suite needs no zsh.
    mirror = f'{line}\nrsync -a --delete "${{LOCAL_EXCLUDES[@]}}" "$1/" "$2/"'
    subprocess.run(["bash", "-c", mirror, "bash", str(source), str(destination)], check=True, capture_output=True)

    kept = sorted(path.name for path in destination.iterdir())
    assert kept == ["memo.md", "trial-attempts.jsonl", "trial-attempts.jsonl.torn-destination"], kept
    assert (destination / "trial-attempts.jsonl").read_text() == "destination\n"


def test_both_local_rsyncs_pass_the_exclusions():
    # config-selector-ok: an rsync command, not a setting; a comment line naming both moves the count off 2
    rsyncs = [line for line in SCRIPT.read_text().splitlines() if '"${RSYNC[@]}"' in line and '"$REPO_DIR/.local/"' in line]
    # config-selector-ok: each line is one of the two rsync commands selected above
    assert len(rsyncs) == 2 and all('"${LOCAL_EXCLUDES[@]}"' in line for line in rsyncs), (
        "the dry run that counts the plan's .local/ deletions and the .local/ mirror no longer both pass LOCAL_EXCLUDES",
        rsyncs,
    )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_trial_attempts.py tests/test_trial_registry_provenance.py -k "allowlist or allowed_ids" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`, `uv run pytest tests/test_research_command.py::test_attempts_init_writes_one_genesis_line_and_prints_its_allowlist_row -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt` and `uv run pytest tests/test_workspace_transport.py -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `AttributeError: module 'cli.registry.attempts' has no attribute 'allowed_log_ids'` collecting `tests/test_trial_attempts.py`, and `ImportError: cannot import name 'parse_allowlist'` collecting `tests/test_trial_registry_provenance.py` and again collecting `tests/test_research_command.py`, which imports the provenance module; in the transport module the exclusion case fails on `ValueError: not enough values to unpack (expected 1, got 0)`, the both-rsyncs case on its assertion, and the five cases already there pass.

- [ ] **Step 3: Implement** — `parse_allowlist` matches each non-empty row against `[0-9a-f]{32} \S+` and refuses with `AttemptLogError` naming "row <n>", a repeated id "row <n> repeats <id>"; `allowed_log_ids` reads the rows of `ALLOWLIST` at `DEVELOP` alone, so a branch that adds a fresh log's row admits nothing until that row merges (spec D6), develop lacking the file (`cat-file -e`) reading as none and a `git show` that exits non-zero raising, as in `landed`; `attempts-init` writes the genesis line at `attempts.log_path(_REPO_ROOT)` through `attempts.init_log`, prints "created <path>; add this row to docs/reference/trial-attempt-logs.txt by PR:" and then the row `<log_id> <host>` on its own line, and turns an `AttemptLogError` into exit 1 echoing its message. Its help: "Create this clone's trial-attempts log, once, and print the row its id takes in the committed allowlist." README: the usage line `zcrypto research attempts-init` and a paragraph saying it creates the clone's log in the main checkout's `.local/` once, refuses an existing one, and prints the allowlist row to add by PR. `infra/scripts/workspace-transport.zsh`: right after `CLAUDE_EXCLUDES`, a comment saying each machine keeps its own trial-attempts log and its heal's copies under its own id — a mirrored log drops the destination's attempts or leaves two machines appending under one id — and that an excluded path is also kept from `--delete` on the destination, then the line `LOCAL_EXCLUDES=(--exclude='/trial-attempts.jsonl*')`; `"${LOCAL_EXCLUDES[@]}"` is passed by the dry run that counts `.local/` deletions for the plan, right after its `--info=del`, and by the `.local/` mirror, right after its `--delete`.

- [ ] **Step 4: Run the Step 2 tests but the allowlist file's** — expected pass; `test_the_allowlist_rows_are_ids_and_hosts_each_id_once` still fails with `FileNotFoundError`.

- [ ] **Step 5: Create the workstation's log, once** — `ls /home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl` must exit 2 ("No such file"); if it exists, stop and report, never run the command over it. Then `uv run zcrypto research attempts-init` from this worktree; it prints the row. Write that row, verbatim, as the one line of `docs/reference/trial-attempt-logs.txt`. This step opens the window the spec's What stays prose names under a second workstation; the PR body names it for the owner, who runs the transport.

- [ ] **Step 6: Run all of Step 2's tests** — expected pass.

- [ ] **Step 7: Consumers, then commit** — `consumers.sh --direct` over the nine paths of the `git add` below, and all three of the Global Constraints' walkers: this task changes files under `cli/`, a help string, and a test that reads `infra/scripts/workspace-transport.zsh`.

```bash
git add docs/reference/trial-attempt-logs.txt cli/registry/attempts.py cli/research/command.py README.md infra/scripts/workspace-transport.zsh tests/test_trial_attempts.py tests/test_research_command.py tests/test_trial_registry_provenance.py tests/test_workspace_transport.py
git commit -F - <<'EOF'
feat(research): zcrypto research attempts-init, the committed allowlist of log ids, and a transport that leaves each machine's log where it is

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 8: Probe** — `--file cli/registry/attempts.py`, control `s/^def _git(/def _git_gone(/` (the allowlist cases reach it through `allowed_log_ids`; the parse rows take control `s/^def parse_allowlist(/def parse_allowlist_gone(/`): the row pattern widened to `[0-9a-fA-F]{32}` against `uppercase-id`; ` \S+` made ` ?\S*` against `no-host`; the repeat check made `if False:` against `repeated-id`; `DEVELOP` made `"HEAD"` against `test_the_allowed_ids_are_the_allowlists_on_origin_develop_never_a_branchs_own`; apart, the `cat-file -e` check `allowed_log_ids` reaches made `if True:` against the same case, its `bare` repository's failed `git show` then raising where the case reads none. `--file cli/research/command.py`, control `s/^def _abort(/def _abort_gone(/`: the row's echo made `None` against `test_attempts_init_writes_one_genesis_line_and_prints_its_allowlist_row`. `--file docs/reference/trial-attempt-logs.txt`, control `1p` (the row repeated): the id's last hex digit made `G` against `test_the_allowlist_rows_are_ids_and_hosts_each_id_once`. `--file infra/scripts/workspace-transport.zsh`, control `s/LOCAL_EXCLUDES/LOCAL_EXCLUDES_GONE/` for both cases: `--exclude='/trial-attempts` made `--include='/trial-attempts` against `test_the_local_mirror_leaves_each_machines_trial_attempts_log_and_its_torn_copies_where_they_are`; apart, `jsonl*'` made `jsonl'` against the same; the dry run's `--info=del "${LOCAL_EXCLUDES[@]}" ` made `--info=del ` against `test_both_local_rsyncs_pass_the_exclusions`; apart, the mirror's `--delete "${LOCAL_EXCLUDES[@]}"` made `--delete` against the same.

______________________________________________________________________

### Task 4: every test's log in its `tmp_path` — the conftest fixture (the tests section's hermetic rule)

**Files:**
- Modify: `tests/conftest.py`
- Test: `tests/test_trial_attempts.py`

**Interfaces:**
- Consumes: Task 1's `log_path`, Task 3's `allowed_log_ids` and `parse_allowlist`.
- Produces: the autouse fixture `_attempts_log_in_tmp_path(tmp_path)`, which a module fixture names as a parameter to run after it (Task 5), and its guard, the autouse `_attempts_log_kept_in_tmp_path(_attempts_log_in_tmp_path, monkeypatch, tmp_path)`; the helper `_allowlisted(path: Path) -> frozenset[str]` — the ids of a file's rows, none when it is absent.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trial_attempts.py
import ast

CONFTEST = REPO / "tests" / "conftest.py"


def test_the_attempts_log_resolves_under_the_tests_tmp_path(tmp_path):
    (tmp_path / "trial-attempt-logs.txt").write_text(f"{'1' * 32} zcrypto-test\n")
    assert attempts.log_path(REPO) == tmp_path / ".local" / "trial-attempts.jsonl"
    assert attempts.allowed_log_ids(REPO) == {"1" * 32}
    assert not (tmp_path / ".local").exists()


def test_no_module_under_cli_imports_a_name_from_the_attempts_module():
    by_name = [
        f"{path.relative_to(REPO)}:{node.lineno}"
        for path in sorted((REPO / "cli").rglob("*.py"))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[-1] == "attempts"
    ]
    assert by_name == [], (
        "code under cli/ reaches cli.registry.attempts as attempts.<name> through `from cli.registry import attempts`, so a "
        f"test's patch of the module's attribute reaches it; a name imported from the module keeps the real one: {by_name}"
    )


@pytest.mark.parametrize("name", ["log_path", "allowed_log_ids"])
def test_a_test_that_points_the_log_at_the_real_one_fails_its_teardown(tmp_path, name):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "conftest.py").write_text(CONFTEST.read_text())
    (tree / "test_scratch.py").write_text(
        f"from cli.registry import attempts\n\nREAL = attempts.{name}\n\n\n"
        f"def test_points_at_the_real_one(monkeypatch):\n    monkeypatch.setattr(attempts, {name!r}, REAL)\n"
    )

    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", "--rootdir", str(tree)], cwd=tree, capture_output=True, text=True)

    assert run.returncode == 1, run.stdout + run.stderr
    assert f"left cli.registry.attempts.{name} on the real" in run.stdout, run.stdout


def test_a_test_that_undoes_its_monkeypatch_keeps_the_log_in_its_tmp_path(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "conftest.py").write_text(CONFTEST.read_text())
    (tree / "test_scratch.py").write_text(
        "from cli.registry import attempts\n\n\n"
        "def test_undoes_its_patches(monkeypatch, tmp_path):\n    monkeypatch.undo()\n"
        "    assert attempts.log_path(tmp_path).is_relative_to(tmp_path)\n"
    )

    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", "--rootdir", str(tree)], cwd=tree, capture_output=True, text=True)

    assert run.returncode == 0, run.stdout + run.stderr
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_trial_attempts.py -k "tests_tmp_path or fails_its_teardown or undoes_its_monkeypatch or imports_a_name_from_the_attempts_module" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: the sentinel fails (`log_path(REPO)` is the main checkout's), each teardown case fails on `returncode == 0`, and the undo case fails on its scratch run's exit 1, the scratch test having called the real resolution, which refuses outside a repository; the import guard passes, Task 3 having imported the module by the Global Constraints' rule, and is proven by its probe.

- [ ] **Step 3: Implement the fixtures in `tests/conftest.py`** — `from cli.registry import attempts` beside the module's other `cli` import; `_REAL_LOG_PATH, _REAL_ALLOWED_LOG_IDS = attempts.log_path, attempts.allowed_log_ids` at import; `_allowlisted`; two autouse fixtures, because ten existing tests call `monkeypatch.undo()` on the shared instance mid-body (`tests/test_archive_checkpoint.py:89`, `tests/test_archive_replay_incremental.py:255` and `:429`, `tests/test_archive_scan_cache.py:247` and `:359`, `tests/test_capture_segment_writer.py:725` and `:2438`, `tests/test_engine_gate_cache.py:341`, `tests/test_engine_store.py:132`, `tests/test_ops_daily.py:1699`), which would put back patches made through it. `_attempts_log_in_tmp_path(tmp_path)`, its line `def _attempts_log_in_tmp_path(tmp_path):`, patches through a `pytest.MonkeyPatch()` of its own, `patch = pytest.MonkeyPatch()` on a line of its own, with a comment saying a test's `monkeypatch.undo()` never reaches these patches: `attempts.log_path` at `lambda code_root: tmp_path / ".local" / "trial-attempts.jsonl"` and `attempts.allowed_log_ids` at `lambda code_root: _allowlisted(tmp_path / "trial-attempt-logs.txt")`, which reads the file on every call — Task 5 writes it after this fixture has run and Task 7 rewrites it mid-test; it writes no file, and after its `yield` calls `patch.undo()`. `_attempts_log_kept_in_tmp_path(_attempts_log_in_tmp_path, monkeypatch, tmp_path)`, its parameters in that order, so the private patch is set up before the shared `monkeypatch` and undone after it, while this guard runs its teardown before that undo and so reads what a test patched through it; after its `yield` it asserts, in this order: `attempts.log_path is not _REAL_LOG_PATH` ("this test left cli.registry.attempts.log_path on the real resolution, which names the main checkout's trial-attempts log"), `attempts.allowed_log_ids is not _REAL_ALLOWED_LOG_IDS` ("this test left cli.registry.attempts.allowed_log_ids on the real allowlist"), and `attempts.log_path(TMP_ROOT.parent).is_relative_to(tmp_path)`.

- [ ] **Step 4: Run the Step 2 tests, then `tests/test_trial_attempts.py` whole** — expected pass; Task 1's `_real_log_path` and `_real_landed` cases still pass, since they call the functions read at import.

- [ ] **Step 5: Consumers, then commit** — `bash infra/scripts/consumers.sh --direct tests/conftest.py tests/test_trial_attempts.py`, then each listed test file under the same pytest flags, with the seven modules of Step 3's `monkeypatch.undo()` sites, and `tests/test_research_command.py`.

```bash
git add tests/conftest.py tests/test_trial_attempts.py
git commit -F - <<'EOF'
test: every test's trial-attempts log and allowlist in its tmp_path, the real ones refused at teardown

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probe** — `--file tests/conftest.py`, control `s/^TMP_ROOT = /TMP_ROOT_GONE = /`: the `log_path` patch prefixed `None and ` against `test_the_attempts_log_resolves_under_the_tests_tmp_path`; the file name the `allowed_log_ids` patch reads, `"trial-attempt-logs.txt"`, made `"elsewhere.txt"` against the same — the patch still in place, so the teardown guard passes and the sentinel's equality alone fails it; each teardown identity assertion made `assert True or …` against its `fails_its_teardown` row; `s/^def _attempts_log_in_tmp_path(tmp_path):/def _attempts_log_in_tmp_path(tmp_path, monkeypatch):/;s/^    patch = pytest.MonkeyPatch()$/    patch = monkeypatch/` against `test_a_test_that_undoes_its_monkeypatch_keeps_the_log_in_its_tmp_path`. `--file cli/research/command.py`, control `s/^def _abort(/def _abort(:/`, which leaves the file unparsable on purpose — the walk's known positive, so only the mutation is dry-run: `s/^_REPO_ROOT = /from cli.registry.attempts import log_path; _REPO_ROOT = /` against `test_no_module_under_cli_imports_a_name_from_the_attempts_module`.

______________________________________________________________________

### Task 5: schema 6 and reading schema 2 — the record carries the attempt its `begin` and `end` lines minted (D8, D2's lines)

The begin and end lines land here, with the block they mint, because `TrialRegistry.append` takes `attempt` as a required keyword (D8) and each commit leaves the suite green; Task 7 adds the count, the refusals and the absorption.

**Files:**
- Modify: `cli/registry/record.py`, `cli/registry/store.py`, `cli/research/command.py`
- Test: `tests/test_registry_record.py` (`:50`), `tests/test_registry_store.py`, `tests/test_registry_conformance.py` (`:161`, `:229`), `tests/test_research_control.py` (`:98`, `:122`), `tests/test_trial_registry_provenance.py` (`_forty_eight_trials`, the `ReadingLedger(ledger).append(` in `test_live_entries_holds_every_reading_beside_the_records_past_47`), `tests/test_trial_attempts.py` (`_append_one`), `tests/test_research_command.py`, `tests/test_registry_replay.py`

**Interfaces:**
- Consumes: Task 1's `AttemptLog`, `log_path`, `current_branch`; Task 2's `budget.BUCKET_OF`; Task 4's fixture.
- Produces:

```python
# cli/registry/record.py
SCHEMA_VERSION = 6
_LOADABLE_SCHEMA_VERSIONS = frozenset({2, 3, 4, 5, 6})
READING_SCHEMA_VERSION = 2
def validate_metrics(metrics, where: str) -> None: ...  # the one metric-leaf rule: a non-empty dict, then _assert_finite
def validate_record_attempt(attempt, where: str) -> None: ...
def validate_reading_attempt(attempt, where: str) -> None: ...
# TrialRecord.attempt: dict | None = None; ReadingRecord.attempt: dict | None = None

# cli/registry/store.py
_ATTEMPT_FLOOR_TRIAL_ID = 48
_ATTEMPT_FLOOR_READING_ID = 1
# TrialRegistry.append(..., attempt: dict) -> TrialRecord
# ReadingLedger.append(..., attempt: dict | None) -> ReadingRecord
```

`tests/test_research_command.py`'s autouse fixture below, which `tests/test_registry_replay.py` imports by name as it imports `_clean_tree`:

```python
# tests/test_research_command.py
@pytest.fixture(autouse=True)
def _attempts_log(tmp_path, monkeypatch, _attempts_log_in_tmp_path) -> Path: ...
```

- [ ] **Step 1: Write the store's failing tests**

```python
# tests/test_registry_store.py
_ATTEMPT_LOG = "f" * 32


def _entry(**over) -> dict:
    return {"log": "e" * 32, "id": 2, "family": "B2", "subject": "b2-funding-derisk", "spec_hash": "c" * 64,
            "verdict": "reject", "metrics": {"sharpe": 0.1}, **over}


def _attempt(**over) -> dict:
    return {"log": _ATTEMPT_LOG, "id": 3, "absorbs": [1], "counted": [_entry()], **over}


def test_a_schema_six_record_round_trips_its_attempt(tmp_path):
    reg = _new_registry(tmp_path)
    written = _append(reg, family="A", n_trials_in_family=1, attempt=_attempt())
    reloaded = _new_registry(tmp_path).records[-1]
    assert (reloaded.schema_version, reloaded.attempt) == (6, _attempt()) and written.attempt == _attempt()


def test_append_requires_an_attempt_explicitly(tmp_path):
    reg = TrialRegistry(tmp_path / "t.jsonl")
    datasets = {"ohlc-test": dict(_BLOCK)}
    with pytest.raises(TypeError, match="attempt"):
        reg.append(iteration="iter-001", family="A1", spec_hash="s", datasets=datasets, invocation=_invocation(datasets),
                   seeds=[0], metrics={"sharpe": 0.3}, n_trials_in_family=1, verdict="adopt", run_ref=COMMITTED_PATH)
    assert not reg.path.exists()


@pytest.mark.parametrize(
    ("attempt", "match"),
    [
        pytest.param(None, "attempt must be a dict", id="not-a-dict"),
        pytest.param({k: v for k, v in _attempt().items() if k != "counted"}, r"missing \['counted'\]", id="missing-key"),
        pytest.param(_attempt(log="f" * 31), "attempt log", id="attempt-log-31-hex"),
        pytest.param(_attempt(log="F" * 32), "attempt log", id="log-uppercase"),
        pytest.param(_attempt(id=0), "attempt id", id="attempt-id-zero"),
        pytest.param(_attempt(id=True), "attempt id", id="attempt-id-bool"),
        pytest.param(_attempt(absorbs=[1, 1]), "attempt absorbs", id="absorbs-repeated"),
        pytest.param(_attempt(absorbs=[3]), "attempt absorbs", id="absorbs-not-below-id"),
        pytest.param(_attempt(absorbs=[True]), "attempt absorbs", id="absorbs-bool"),
        pytest.param(_attempt(counted=[{**_entry(), "outcome": "reject"}]), "counted entry keys", id="entry-extra-key"),
        pytest.param(_attempt(counted=[_entry(log="e" * 31)]), "counted entry log", id="entry-log-31-hex"),
        pytest.param(_attempt(counted=[_entry(id=0)]), "counted entry id", id="entry-id-zero"),
        pytest.param(_attempt(counted=[_entry(id=True)]), "counted entry id", id="entry-id-bool"),
        pytest.param(_attempt(counted=[_entry(spec_hash="s")]), "counted entry spec_hash", id="entry-spec-hash-not-hex"),
        pytest.param(_attempt(counted=[_entry(family="")]), "counted entry family", id="entry-family-empty"),
        pytest.param(_attempt(counted=[_entry(subject="")]), "counted entry subject", id="entry-subject-empty"),
        pytest.param(_attempt(counted=[_entry(), _entry()]), "counted entries", id="entry-repeated"),
        pytest.param(_attempt(counted=[_entry(log=_ATTEMPT_LOG, id=3)]), "counted entries", id="entry-is-the-records-own"),
        pytest.param(_attempt(counted=[_entry(log=_ATTEMPT_LOG, id=1)]), "counted entries", id="entry-in-absorbs"),
        pytest.param(_attempt(counted=[_entry(verdict=None)]), "counted entry verdict", id="entry-open"),
        pytest.param(_attempt(counted=[_entry(metrics=None)]), "counted entry metrics must be a non-empty dict", id="entry-without-metrics"),
        pytest.param(_attempt(counted=[_entry(metrics={"sharpe": float("nan")})]), "non-finite", id="entry-metrics-nan"),
    ],
)
def test_an_ill_shaped_attempt_is_refused_before_the_write(tmp_path, attempt, match):
    reg = _new_registry(tmp_path)
    with pytest.raises(RegistryError, match=match):
        _append(reg, family="A", n_trials_in_family=1, attempt=attempt)
    assert not reg.path.exists()


def test_a_reading_at_schema_two_round_trips_its_attempt(tmp_path):
    path = tmp_path / "readings.jsonl"
    written = _append_reading(ReadingLedger(path), attempt={"log": "f" * 32, "id": 4, "absorbs": [2]})
    (reloaded,) = ReadingLedger(path).records
    assert (reloaded.schema_version, reloaded.attempt) == (2, {"log": "f" * 32, "id": 4, "absorbs": [2]}) and reloaded == written


@pytest.mark.parametrize(
    ("attempt", "match"),
    [
        pytest.param({"log": "f" * 32, "id": 4, "absorbs": [], "counted": []}, "reading attempt keys", id="reading-lists-nothing"),
        pytest.param({"log": "f" * 32, "id": 4, "absorbs": [4]}, "attempt absorbs", id="reading-absorbs-not-below-id"),
        pytest.param("f" * 32, "reading attempt must be null or a dict", id="reading-not-a-dict"),
    ],
)
def test_an_ill_shaped_reading_attempt_is_refused_before_the_write(tmp_path, attempt, match):
    path = tmp_path / "readings.jsonl"
    with pytest.raises(RegistryError, match=match):
        _append_reading(ReadingLedger(path), attempt=attempt)
    assert not path.exists()


def test_a_reading_past_the_first_must_declare_schema_two(tmp_path):
    first = _reading_line(1)
    with pytest.raises(RegistryCorruptionError, match="reading 2 declares schema_version 1; every reading past reading 1 must be schema_version 2"):
        ReadingLedger(_write(tmp_path, [first, _reading_line(2, prev_hash=_hash_of(first))]))
    second = _reading_line(2, prev_hash=_hash_of(first), schema_version=2, attempt=None)
    assert len(ReadingLedger(_write(tmp_path, [first, second]))) == 2
```

and migrate: `_append` gains `kw.setdefault("attempt", {"log": _ATTEMPT_LOG, "id": 1, "absorbs": [], "counted": []})`, `_append_reading` gains `attempt=None` in its defaults; `test_append_requires_run_ref_explicitly` and `test_append_requires_an_invocation_explicitly` pass an `attempt`; `test_a_schema_five_record_round_trips_through_disk` becomes `..._six_...` reading 6, and `test_an_appended_invocation_reloads_at_schema_five` becomes `..._at_schema_six`, its `(5, invocation)` read `(6, invocation)`; `test_a_reading_round_trips_through_disk` reads schema 2 and its key set gains `"attempt"`; `test_a_record_past_the_floors_must_declare_schema_five` becomes `test_a_record_past_the_floors_must_declare_schema_six`: `_line_next` builds schema 6 with `attempt=_attempt(id=1, absorbs=[], counted=[])` and loads, the same line at schema 5 with `attempt` removed and its hash recomputed is refused matching `f"trial {next_id} declares schema_version 5; every record past trial 48 must be schema_version 6"`, and the schema-4 case removes `attempt` too, its match unchanged (the floor at 47 fires before the one at 48), the schema-3 case likewise; and the load checks the block's form as the append does: `TrialRegistry(_write(tmp_path, [*real, _line_next(attempt=_attempt(id=1, absorbs=[], counted=[_entry(verdict=None)]))]))`, its line hash-correct at schema 6, raises under `pytest.raises(RegistryError, match="counted entry verdict")`. A schema-5 assertion this list missed reads 6 by the same rule.

- [ ] **Step 2: Write the command's failing tests**

```python
# tests/test_research_command.py
@pytest.fixture(autouse=True)
def _attempts_log(tmp_path, monkeypatch, _attempts_log_in_tmp_path) -> Path:
    path = attempts.log_path(_REPO)
    path.parent.mkdir(parents=True)
    log_id = attempts.init_log(path, host="zcrypto-test")
    (tmp_path / "trial-attempt-logs.txt").write_text(f"{log_id} zcrypto-test\n")
    return path


def _log_lines(path: Path) -> list[dict]:
    return list(attempts.AttemptLog(path).lines)


def test_a_clean_run_is_admitted_and_logged_begin_and_end(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(Path("registry.jsonl"), n_trials=1)])

    assert result.exit_code == 0, result.output
    record = json.loads(registry.read_text())
    log = attempts.AttemptLog(_attempts_log)
    assert record["schema_version"] == 6
    assert record["attempt"] == {"log": log.log_id, "id": 1, "absorbs": [], "counted": []}
    begin, end = log.lines[1:]
    assert (begin["kind"], begin["attempt"], end["kind"], end["attempt"]) == ("begin", 1, "end", 1)
    assert begin["registry"] == str(registry.resolve())
    assert (begin["invocation"], begin["spec_hash"], begin["family"]) == (record["invocation"], record["spec_hash"], "STUB")
    assert (end["verdict"], end["stop"], end["failed"]) == ("adopt", None, None)
    assert end["metrics_hash"] == compute_hash(record["metrics"])


def _raising_stub(monkeypatch, returned: dict | None = None, raised: type[Exception] = subjects.SubjectError) -> None:
    def build(reader, dataset, window, as_of=None, accept_holes=False):
        reader.read_series(dataset, "BTC/EUR/1440.parquet", window=window)
        if returned is None:
            raise raised("the stub's window is too short")
        return returned

    monkeypatch.setitem(subjects.SUBJECTS, "stub", subjects.Subject("stub", (1440,), ("BTC",), build, **_STUB_DECLARED))


@pytest.mark.parametrize(
    ("returned", "raised", "failed"),
    [
        pytest.param(None, subjects.SubjectError, "SubjectError: the stub's window is too short", id="the-build-raises"),
        pytest.param(None, ValidationError, "ValidationError: the stub's window is too short", id="a-compute-error"),
        pytest.param({"sharpe": 1.0, "extra": 2.0}, subjects.SubjectError, "SubjectError: stub's build returned keys other than the ones it declares", id="the-keys-differ"),
        pytest.param({"sharpe": None}, subjects.SubjectError, "RegistryError: metrics.sharpe: unsupported metric leaf type NoneType", id="a-leaf-the-registry-refuses"),
    ],
)
def test_a_failed_build_ends_its_attempt_with_its_class_and_message(tmp_path, monkeypatch, _attempts_log, returned, raised, failed):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _raising_stub(monkeypatch, returned, raised)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and not registry.exists() and '"metrics"' not in result.output, result.output
    end = _log_lines(_attempts_log)[-1]
    assert end["kind"] == "end" and end["failed"].startswith(failed)
    assert (end["verdict"], end["stop"], end["metrics"], end["metrics_hash"]) == (None, None, None, None)


def test_a_stop_ends_its_attempt_with_the_stop_and_its_reading_carries_it(tmp_path, monkeypatch, _attempts_log):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)])

    assert result.exit_code == 0, result.output
    log = attempts.AttemptLog(_attempts_log)
    (reading,) = _kept(ledger)
    assert (reading["schema_version"], reading["attempt"]) == (2, {"log": log.log_id, "id": 1, "absorbs": []})
    assert (log.lines[-1]["stop"], log.lines[-1]["verdict"]) == ("the stub's stop", None)


def test_a_ruleless_reading_writes_no_line_and_carries_no_attempt(tmp_path, monkeypatch, _attempts_log):
    ledger = tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None)

    result = runner.invoke(app, [*_stub_eval(), *_reading_args(ledger)])

    assert result.exit_code == 0, result.output
    assert _kept(ledger)[0]["attempt"] is None and len(_log_lines(_attempts_log)) == 1


def test_a_begin_the_log_refuses_ends_the_run_before_the_build(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)

    def refuse(self, admit, **fields):
        raise OSError("No space left on device")

    monkeypatch.setattr(attempts.AttemptLog, "begin", refuse)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and "refused the run's first line: No space left on device; nothing ran" in result.output
    assert calls == [] and not registry.exists()


def test_an_end_the_log_refuses_withholds_the_numbers(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, metrics={"sharpe": 1.2345})

    def refuse(self, attempt, **outcome):
        raise OSError("No space left on device")

    monkeypatch.setattr(attempts.AttemptLog, "end", refuse)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1
    assert (
        "refused the run's last line: No space left on device; the numbers are withheld and the attempt stays open: run again "
        "with the same arguments, which absorbs it"
    ) in result.output
    assert "1.2345" not in result.output and not registry.exists()
```

and migrate: the module's three `["schema_version"] == 5` assertions read 6; `tests/test_registry_replay.py` imports `_attempts_log` from `tests.test_research_command` beside `_clean_tree`, with the same `# noqa: F401` comment; the other append call sites pass `attempt` — `tests/test_registry_conformance.py:161` and `:229`, `tests/test_research_control.py:98` (its `:122` reads 6), `tests/test_trial_registry_provenance.py`'s `_forty_eight_trials` (`{"log": "e" * 32, "id": n, "absorbs": [], "counted": []}`) and its reading append (`attempt=None`), `tests/test_trial_attempts.py`'s `_append_one` (`attempt={"log": "e" * 32, "id": 1, "absorbs": [], "counted": []}`, a key no other record of its one caller carries) — `git grep -n -E "\.append\($|reg\.append\(|ledger\.append\(" -- tests/` lists them.

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_registry_store.py tests/test_research_command.py -k "attempt and not attempts_init or schema_six or schema_two or begin or end_the_log or stop_ends or ruleless_reading or clean_run or failed_build_ends" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `TypeError: TrialRegistry.append() got an unexpected keyword argument 'attempt'` and the command cases failing on `schema_version == 6`, a missing `begin` line, or — `a-leaf-the-registry-refuses` — the numbers printed before the store's refusal.

- [ ] **Step 4: Implement the store** — `record.py`: the Interfaces' constants; `validate_metrics(metrics, where)` raises `RegistryError(f"{where} must be a non-empty dict")` unless `metrics` is one, then runs `_assert_finite(metrics, where)` — the one metric-leaf rule, which `validate_caller_fields` (`where` `"metrics"`), `validate_reading_fields` (`f"{where}: metrics"`), each counted entry and Step 5's check before the `end` line call, so none can disagree, both existing callers' messages unchanged; `_EXPECTED_STORED_KEYS[6] = _EXPECTED_STORED_KEYS[5] | {"attempt"}`; `validate_stored_record` requires and checks `attempt` at 6, through `validate_record_attempt`, so a stored line is held to the form an append is; `validate_record_attempt` checks spec D8's form with the test table's messages — "attempt must be a dict", "attempt keys must be exactly [...] (missing [...], unknown [...])", "attempt log must be 32 lowercase hex", "attempt id must be an int >= 1" (`type(...) is int`), "attempt absorbs must be distinct ints >= 1 below the attempt's id" (each `type(...) is int`, the id check's), "counted entry keys must be exactly [...]", "counted entry log …", "counted entry id must be an int >= 1" (the id check's), "counted entry spec_hash must be 64 lowercase hex", "counted entry family …" and "… subject must be a non-empty str", "counted entry verdict must be one of ['adopt', 'park', 'reject']", "counted entry metrics must be a non-empty dict" then `_assert_finite` (`validate_metrics(entry["metrics"], "counted entry metrics")`), "counted entries must be distinct (log, id) pairs, none the record's own attempt or one it absorbs"; `validate_reading_attempt` takes `None` or the three keys, "reading attempt must be null or a dict", "reading attempt keys must be exactly ['absorbs', 'id', 'log']", the log, id and absorbs checks shared; `validate_stored_reading` reads `schema_version` (an int in `{1, 2}`) before the key set, the key set being `_READING_KEYS` at 1 and `_READING_KEYS | {"attempt"}` at 2. `store.py`: `_to_record` passes `attempt=rec.get("attempt")`; `_assert_cross_record` refuses a record past `_ATTEMPT_FLOOR_TRIAL_ID` below schema 6, after the floor at 47, naming the trial, its schema and "every record past trial 48 must be schema_version 6"; `_assert_reading_chain` refuses, after its link check, a reading past `_ATTEMPT_FLOOR_READING_ID` below schema 2 ("reading <n> declares schema_version <s>; every reading past reading 1 must be schema_version 2"); `TrialRegistry.append` takes `attempt: dict` with no default and validates it before the open, as `validate_caller_fields` runs; `ReadingLedger.append` takes `attempt: dict | None` with no default, validated in `validate_reading_fields` before the open.

- [ ] **Step 5: Implement the lines in `cli/research/command.py`** — for `--register` of a ruled subject, after the dataset checks and before the build: the invocation, built as today but here, then `log = attempts.AttemptLog(attempts.log_path(_REPO_ROOT))` and `attempt = log.begin(lambda lines: None, invocation=…, spec_hash=computed_spec_hash, family=family, bucket=budget.BUCKET_OF.get(family), n_trials=n_trials, worktree=_REPO_ROOT, branch=attempts.current_branch(_REPO_ROOT), registry=target, ledger=ledger_target)`, any `(OSError, RegistryError)` from either refused as D2's first remedy, "the trial-attempts log <path> refused the run's first line: <error>; nothing ran". Each of the four exits between the `begin` and the `end` line first writes `log.end(attempt, failed=f"{type(exc).__name__}: {exc}")`, then exits as today: the build's two except clauses, `(RegistryError, OSError, SubjectError)` and `EVALUATION_ERRORS`; the key-set refusal, its `failed` `SubjectError: ` and its refusal text; and the leaf check below — each a row of `test_a_failed_build_ends_its_attempt_with_its_class_and_message` and a probe of Step 8. Right after the key-set check, under the same `if records:`, `validate_metrics(metrics, "metrics")` — the leaf rule the store would apply after the print — and a `RegistryError` it raises is handled as the key-set refusal is: `failed` written as `RegistryError: <message>`, then the exit with the message, nothing printed. Every leaf the store refuses is caught here, before the `end` line: a None, a bool, a NaN or an infinity, a numpy scalar, a key that is not a str; an `end` holding one would be a finished orphan whose `counted` entry every later record in its bucket must carry and the store refuses, and a NaN would raise from the `end` line's own `canonical_json` as a traceback. After the rule and before the print, `log.end(attempt, verdict=ruled, metrics=metrics)` or, on a stop, `log.end(attempt, stop=known.no_verdict, metrics=metrics)`, an `(OSError, RegistryError)` refused as D2's second remedy, "the trial-attempts log <path> refused the run's last line: <error>; the numbers are withheld and the attempt stays open: run again with the same arguments, which absorbs it", printing nothing. The appends pass `attempt={"log": log.log_id, "id": attempt, "absorbs": [], "counted": []}` to the registry and `{"log": log.log_id, "id": attempt, "absorbs": []}` to the ledger on a stop; a ruleless `--reading` writes no line and passes `attempt=None`.

- [ ] **Step 6: Run the Step 3 tests and the migrated modules** — `uv run pytest tests/test_registry_store.py tests/test_registry_record.py tests/test_registry_conformance.py tests/test_research_control.py tests/test_trial_registry_provenance.py tests/test_trial_attempts.py -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`, then `tests/test_research_command.py` alone; expected all pass, the data-gated cases skipping without `data/`.

- [ ] **Step 7: Consumers, then commit** — `consumers.sh --direct` over the eleven paths of the `git add` below, the union under the pytest flags, and the Global Constraints' walker for files under `cli/`.

```bash
git add cli/registry/record.py cli/registry/store.py cli/research/command.py tests/test_registry_record.py tests/test_registry_store.py tests/test_registry_conformance.py tests/test_research_control.py tests/test_trial_registry_provenance.py tests/test_trial_attempts.py tests/test_research_command.py tests/test_registry_replay.py
git commit -F - <<'EOF'
feat(registry): schema 6 — a record past 48 and a reading past 1 carry the attempt the run's begin and end lines minted

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 8: Probe** — `--file cli/registry/record.py`, control `s/^def _assert_finite(/def _assert_finite_gone(/`: each check of `validate_record_attempt` made `if False:` against its row of `test_an_ill_shaped_attempt_is_refused_before_the_write` (one probe per row, twenty-two; a check shared through a helper — the id check, which `id`, `absorbs` and each entry's `id` reach — probed at its call for the row's field, that call made to accept every value, the Global Constraints' neutral call; for `entry-without-metrics` and `entry-metrics-nan` the check is `validate_metrics`'s, its dict check made `if False:` and its `_assert_finite` call made `None`), each of `validate_reading_attempt`'s against its row of the reading table; the version-6 key-set entry cut against `test_a_schema_six_record_round_trips_its_attempt`; `validate_stored_record`'s `validate_record_attempt` call made `None` against `test_a_record_past_the_floors_must_declare_schema_six`. `--file cli/registry/store.py`, control `s/^def _read_healing(/def _read_healing_gone(/`: `< 6` made `< 5` against `test_a_record_past_the_floors_must_declare_schema_six`; the reading floor's `< 2` made `< 1` against `test_a_reading_past_the_first_must_declare_schema_two`; `attempt: dict,` made `attempt: dict = None,` against `test_append_requires_an_attempt_explicitly`; the pre-open `validate_record_attempt` call made `None` against the `entry-metrics-nan` row; `_to_reading`'s `ReadingRecord(**rec)` made `ReadingRecord(**{**rec, "attempt": None})` against `test_a_reading_at_schema_two_round_trips_its_attempt`. `--file cli/research/command.py`, control `s/^def _no_file_there(/def _no_file_there_gone(/`: the begin's refusal made `None` against `test_a_begin_the_log_refuses_ends_the_run_before_the_build`; the end's refusal made `None` against `test_an_end_the_log_refuses_withholds_the_numbers`; the failed `end` in the `(RegistryError, OSError, SubjectError)` clause made `None` against `the-build-raises`, in the `EVALUATION_ERRORS` clause against `a-compute-error`, before the key-set exit against `the-keys-differ`, and before the leaf check's exit against `a-leaf-the-registry-refuses`; the leaf check's `validate_metrics` call made `None` against `a-leaf-the-registry-refuses`; the stop's reading `attempt` made `None` against `test_a_stop_ends_its_attempt_with_the_stop_and_its_reading_carries_it`; the condition that writes the `begin` made `True`, so a ruleless reading writes one, against `test_a_ruleless_reading_writes_no_line_and_carries_no_attempt`; the begin's `registry=target` made `registry=ledger_target` against `test_a_clean_run_is_admitted_and_logged_begin_and_end`.

______________________________________________________________________

### Task 6: the subjects declare their family and trial count (D4's subject side)

**Files:**
- Modify: `cli/research/subjects.py` (`Subject` `:83-93`, the B2 kill-bar sites `:324` and `:403`, `_b2_arm_a_bar`'s two callers `:370` and `:440`, the `SUBJECTS` entries for `b2-funding-derisk` and `b1-hourly-rv`), `tests/slow-cases.txt`
- Test: `tests/test_research_command.py` (`test_every_subject_declares_a_tracked_spec_its_keys_seeds_rule_and_incumbent`, and the pin `assert subjects._B1_HOURLY_RV_N_TRIALS == 3`)

**Interfaces:**
- Consumes: Task 2's `budget.BUCKET_OF`.
- Produces: `Subject.family: str | None = None`, `Subject.n_trials: int | None = None`; `_B2_N_TRIALS = 1`, declared by `b2-funding-derisk` with `family="B2"` and passed at both kill-bar sites its build reaches: `_b2_metrics`'s grid (`:403`) and `_b2_arm_a_bar`, which gains a keyword `n_trials` it passes at `:324` — `b2-funding-derisk`'s call (`:440`) passing `_B2_N_TRIALS`, the ruleless `b2-arm-a-bar`'s (`:370`) passing `1`, the count reading 1 was kept at, so raising `_B2_N_TRIALS` never moves that landed reading's replay; `b1-hourly-rv` declares `family="B1"` and `n_trials=_B1_HOURLY_RV_N_TRIALS`. No check at construction: the pairing with `verdict` is the test's, as `verdict`'s pairing with `no_verdict` is.

- [ ] **Step 1: Write the failing tests** — `_RULED_FIXTURES` and its two tests below `_b1_hourly_rv_dataset`, whose name it reads — and delete the bare pin `assert subjects._B1_HOURLY_RV_N_TRIALS == 3` from `test_the_b1_hourly_rv_dispersion_reads_records_45_and_46s_registered_sharpes_over_three_trials`, which the DSR tie replaces:

```python
# tests/test_research_command.py
from cli.registry import budget

_RULED_FIXTURES = {"b1-hourly-rv": _b1_hourly_rv_dataset, "b2-funding-derisk": _b2_dataset}


def test_the_ruled_subjects_declare_their_families_and_trial_counts():
    declared = {name: (s.family, s.n_trials) for name, s in subjects.SUBJECTS.items() if s.verdict is not None}
    assert declared == {"b1-hourly-rv": ("B1", 3), "b2-funding-derisk": ("B2", 1)}
    assert set(_RULED_FIXTURES) == set(declared)


@pytest.mark.parametrize("name", sorted(_RULED_FIXTURES))
def test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count(tmp_path, monkeypatch, name):
    counts = []

    def recorder(*args, n_trials, **kwargs):
        counts.append(n_trials)
        return _b1_hourly_rv_bar_sentinels("B", passes=True)

    monkeypatch.setattr(subjects, "a1_kill_bar", recorder)

    subjects.SUBJECTS[name].build(ObservedReader(_RULED_FIXTURES[name](tmp_path)), "ohlc-test", None)

    assert counts and set(counts) == {subjects.SUBJECTS[name].n_trials}
```

and extend `test_every_subject_declares_a_tracked_spec_its_keys_seeds_rule_and_incumbent` with:

```python
    if subject.verdict is None:
        assert subject.family is None and subject.n_trials is None
    else:
        assert subject.family in budget.BUCKET_OF and type(subject.n_trials) is int and subject.n_trials >= 1
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_research_command.py -k "families_and_trial_counts or kill_bar_deflates or declares_a_tracked_spec" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `AttributeError: 'Subject' object has no attribute 'family'`.

- [ ] **Step 3: Implement** — the two fields after `incumbent`, each with a comment naming the spec's D4; `_B2_N_TRIALS = 1` beside `_B2_COST_PER_SIDE`; `_b2_arm_a_bar`'s keyword `n_trials` and its two callers' counts (Interfaces); the two declarations.

- [ ] **Step 4: Run the Step 2 tests** — expected pass; then `uv run pytest tests/test_research_command.py -k "b1_hourly_rv_dispersion" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt` passes without its pin. Then add `tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b1-hourly-rv]` and `[b2-funding-derisk]` to `tests/slow-cases.txt` in its sorted order: each build takes over 10 s with `a1_kill_bar` replaced, the list's own bar.

- [ ] **Step 5: Consumers, then commit** — `consumers.sh --direct` over the three paths of the `git add` below, `tests/test_slow_cases.py` among them, and the Global Constraints' walker for files under `cli/`.

```bash
git add cli/research/subjects.py tests/test_research_command.py tests/slow-cases.txt
git commit -F - <<'EOF'
feat(research): each ruled subject declares its family and trial count, and its kill bar deflates at that count

<the task's pytest result line, pasted from its run>
probe skipped: slow case — tests/test_research_command.py::test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count[b1-hourly-rv] and [b2-funding-derisk]

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probe** — `--file cli/research/subjects.py`, control `s/^def _b2_verdict(/def _b2_verdict_gone(/` (the module's import builds `SUBJECTS` from it): the DSR tie's kill-bar sites — `_b2_metrics`'s grid, `_b2_arm_a_bar`'s, and `b1-hourly-rv`'s two — are probed only through `test_every_ruled_subjects_kill_bar_deflates_at_its_declared_count`, whose two cases are slow, so Step 5's commit records them `probe skipped: slow case`; `family="B1"` made `family=None` against `declares_a_tracked_spec and b1-hourly-rv and not preflight`; `family="B2"` made `family="B3"` against `test_the_ruled_subjects_declare_their_families_and_trial_counts`.

______________________________________________________________________

### Task 7: the register path counts — the refusals, the provisional absorption, the plain-eval refusal (D2–D7)

**Files:**
- Modify: `cli/research/command.py`, `README.md` (the `--register`, `--family`, `--n-trials` and `--registry` rows and the paragraph under the table)
- Test: `tests/test_research_command.py`, `tests/test_registry_replay.py` (its two register cases, if a migration rule below reaches them)

**Interfaces:**
- Consumes: Task 1's `landed`, `files_landed`, `reconcile`, `lacking`, `arguments`, `AttemptLog.locked`, `Count`, `Orphan.describe`, `DEVELOP`, and, in its tests, `_process_marks`, `_boot_id` and `_reaped_pid`; Task 2's `budget`; Task 3's `allowed_log_ids`; Task 5's lines; Task 6's declarations.
- Produces: nothing new for later tasks; the register path in D2's order:
  1. after the unknown-subject refusal, D7's: a subject whose `verdict` is set, run with neither `--register` nor `--reading`, refused before any read — "<subject> declares a verdict rule, so every run of it is a trial: run it with --register; a ruleless pre-flight subject reads the inputs without the trial's result";
  2. with today's refusals that need no data, for `--register`: D4's "--family <x> is not <F>, the family <subject> declares: pass --family <F>" and "--n-trials <x> is not <n>, the count <subject> declares and deflates at: pass --n-trials <n>"; D5's "family <F> is in no bucket of cli/registry/budget.py: add it with its bucket in a reviewed pull request"; D6's absent log, its broken chain (D1's line remedy appended to the `AttemptLogError`), its unlisted id (`attempts.allowed_log_ids(_REPO_ROOT)`), each with its remedy verbatim; `landed = attempts.landed(_REPO_ROOT, target, ledger_target)` (D3's develop refusal), a `RegistryError` it raises turned into `raise _abort(str(exc))`, its message D3's remedy or the store's own; `attempts.lacking(...)`, D6's third remedy for the first pair; and D4's frozen count — a landed record whose `invocation`, read through `.get` (Task 1 Step 5), names this subject and whose `n_trials_in_family` is not the declared `n_trials`, the highest such trial named — "<subject> declares n_trials <x>, and its trial <N> landed at n_trials <n>, which that record's deflated Sharpe used, so its n_trials is frozen: declare a new subject (a new name) for the further trial";
  3. the dataset checks;
  4. `log.begin(admit, …)`, `admit` re-reading `attempts.landed(...)` as step 2 reads it and raising each of its refusals as `raise _abort(...)` — a `typer.Exit`, which the `(OSError, RegistryError)` clause around `begin` (Task 5 Step 5) never catches, so a refusal of the count, the budget or the re-read is never reported as the log's — then `count = attempts.reconcile(lines, landed, log_id=log.log_id, bucket_of=budget.BUCKET_OF, hold=hold)`, `hold` being `(subject, attempts.arguments(invocation), computed_spec_hash)`, refusing when `known.n_trials < count.required_n(family)` with D4's split remedy, composed from `attempts.reconcile(lines, landed, log_id=log.log_id, bucket_of=budget.BUCKET_OF, hold=None if frozen else hold, hold_finished=False)`, `frozen` true when a landed record names the subject — its `required_n(family)` the `<m>` the remedy names and its orphans of the family listed through `describe()`: a raised run that leaves the spec file, so `spec_hash`, unchanged holds every open attempt this one held, each one whose process is gone and so can no longer end, and absorbs each whatever its numbers, and a finished one only on equal numbers; one whose spec file changed holds none and is refused before its fit naming the full count; a new subject absorbs no attempt of this one (spec D3) — then the "raise …" tail, or, when `frozen`, the "<subject>'s n_trials is frozen by its trial <N>: declare a new subject (a new name) for the further trial" tail — and when the bucket is set and `strict.spent(bucket) + 1 > budget.BUDGET[bucket]`, `strict` being `attempts.reconcile(lines, landed, log_id=log.log_id, bucket_of=budget.BUCKET_OF, hold=hold, hold_finished=False)`, which holds out only the open attempts `hold` names whose process is gone, since a finished one printed a look this run absorbs only on equal numbers and a live one may yet print one (spec D5), with D5's "bucket <b> has spent <s> of its <B> trials (<r> records, <k> attempts that never landed), so this trial would exceed it: an expansion is the owner's ruling, written into cli/registry/budget.py by a pull request that quotes it", its figures read from `strict`;
  5. the build, the key set, the rule, the `end` line (Task 5), the print;
  6. the tree check and the `--verdict` assertion as today; then one block under `with log.locked() as lines:` — `landed` re-read, `count = attempts.reconcile(lines, landed, log_id=log.log_id, bucket_of=budget.BUCKET_OF, own=attempt)` with no `hold`, since after the `end` a held attempt is classified as any other (spec D3), the same two refusals as step 4 on the new count (the run refused after its print, both attempts counting), the count's remedy composed as step 4's — over these lines, which hold this run's `end`, so a refused verdict counts itself among the attempts the next run must meet, and the remedy's `<this run>` reads "the next run" (spec D4) — then the append with `attempt={"log": log.log_id, "id": attempt, "absorbs": list(count.absorbs), "counted": count.counted(family)}`, or the stop's reading with `absorbs` alone.

- [ ] **Step 1: Migrate the module's fixtures and stubs** — `_STUB_DECLARED` gains `"family": "STUB"` and `"n_trials": 1`; `_attempts_log` gains `monkeypatch.setattr(attempts, "landed", lambda code_root, registry, ledger: attempts.files_landed(registry, ledger))` and `monkeypatch.setitem(budget.BUCKET_OF, "STUB", None)`; at module level `_unstubbed_landed, _unstubbed_log_path, _unstubbed_allowed = attempts.landed, attempts.log_path, attempts.allowed_log_ids`. Then, by rule, every case the new refusals reach: (a) a plain eval of a ruled stub (`_stub_subject`, `_rolling_subject`) declares it ruleless with `verdict=None, no_verdict=None` — `_rolling_subject` gains `**declared`, merged over `_STUB_DECLARED` as `_stub_subject`'s are, so its two `--register` callers stay ruled and its plain-eval callers pass the two keywords; (b) a plain eval of a ruled production subject — `_b2_eval`'s callers, the `b1-hourly-rv` row of `test_a_b1_hourly_rv_subject_refuses_as_of_before_any_read`, `test_b1_hourly_rv_names_an_hourly_file_it_cannot_read`, `test_b1_hourly_rv_refuses_a_build_whose_arm_a_never_trades_or_whose_weights_never_move`, `test_a_b1_hourly_rv_history_the_bar_cannot_read_is_refused_before_the_arms_and_the_hourly_reads`, and the `b1-hourly-rv` and `b2-funding-derisk` rows of `test_every_subject_evaluates_its_fixture_and_ends_an_input_it_cannot_evaluate_in_an_exit` — splices `_as_trial(name, tmp_path)` in at the invoke, `runner.invoke(app, [*args, *_as_trial(name, tmp_path)])`, `args` itself unchanged because four cases read the window back from its tail (`args[-2]`, `args[-1]`), a helper returning `[]` for a ruleless subject and for a ruled one `["--register", "--registry", str(tmp_path / "registry.jsonl"), "--ledger", str(tmp_path / "ledger.jsonl"), "--iteration", "iter-001", "--family", family, "--n-trials", str(n_trials)]` from its declaration, so the case keeps the command path and the build's refusal it tests (the spec's author's call); (c) a register run whose `--n-trials` is not 1 — `follower` in `test_a_registered_trial_is_the_comparator_only_of_a_subject_naming_its_subject` — declares that count on its stub, and a register run of a production subject types its declared family and count (`family="B2"` in `test_the_b2_subject_registers_each_metric_from_its_own_call`; `--family B1 --n-trials 3` in `test_the_b1_hourly_rv_subject_registers_each_metric_from_its_own_call`), a case refused before D4's checks (`test_a_subject_without_an_incumbent_is_refused_a_comparator_trial`) keeping its message; (d) `test_a_second_trial_in_a_family_needs_n_trials_above_the_recorded_count` registers its second trial as `stub-2` declaring 2, and its repeat at 1 asserts D4's message with the frozen tail in place of `n_trials_in_family`. Step 6's run of the two modules is where a case the list missed shows: it is migrated by the rule of (a)–(d) it falls under, and a failure under none of them is reported, never patched around.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_research_command.py
def _refused_before_the_fit(tmp_path, monkeypatch, *, registry: Path | None = None, flags: dict | None = None, **declared) -> str:
    registry = registry or tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch, **declared)
    typed = {"family": declared.get("family", "STUB"), "n_trials": declared.get("n_trials", 1), **(flags or {})}
    before = _log_lines(attempts.log_path(_REPO))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, **typed)])

    assert result.exit_code == 1 and isinstance(result.exception, SystemExit), result.output
    assert calls == [] and _log_lines(attempts.log_path(_REPO)) == before
    return result.output


def _planted(path: Path, *subjects_ended: tuple[str, str | None], family: str = "STUB") -> None:
    """Another session's attempts, each ended with its verdict, or left open for None."""
    log = attempts.AttemptLog(path)
    for subject, verdict in subjects_ended:
        invocation = {"subject": subject, "dataset": "ohlc-test", "window": None, "as_of": None, "accept_holes": False,
                      "comparator_trial": None, "commit": _CLEAN_HEAD}
        attempt = log.begin(lambda lines: None, invocation=invocation, spec_hash="c" * 64, family=family, bucket=None, n_trials=1,
                            worktree=path.parent, branch="research/elsewhere", registry=path.parent / "r.jsonl", ledger=path.parent / "l.jsonl")
        if verdict is not None:
            log.end(attempt, verdict=verdict, metrics={"sharpe": 0.5})


_SEED_BLOCK = {"ohlc-test": {"files": {"BTC/EUR/1440.parquet": "c" * 64}, "rows": 10, "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"]}}


def _seed(registry: Path, family: str, count: int, *, log: str = "e" * 32, first_id: int = 1, subject: str = "seed") -> None:
    for n in range(1, count + 1):
        TrialRegistry(registry).append(
            iteration="iter-001", family=family, spec_hash="s", datasets=_SEED_BLOCK, seeds=[0], metrics={"sharpe": 0.3},
            invocation={"subject": subject, "dataset": "ohlc-test", "window": None, "as_of": None, "accept_holes": False, "comparator_trial": None, "commit": _CLEAN_HEAD},
            n_trials_in_family=n, verdict="reject", run_ref="cli/registry/record.py",
            attempt={"log": log, "id": first_id + n - 1, "absorbs": [], "counted": []},
        )


def test_a_run_on_an_abandoned_branch_is_counted_by_the_next_registration(tmp_path, monkeypatch):
    main, worktree = tmp_path / "main", tmp_path / "wt"
    _git_repo(main, _STUB_SPEC)
    subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", "-b", "research/x", str(worktree)], check=True, capture_output=True)
    log = main / ".local" / "trial-attempts.jsonl"
    log.parent.mkdir()
    log_id = attempts.init_log(log, host="zcrypto-test")
    (tmp_path / "trial-attempt-logs.txt").write_text(f"{log_id} zcrypto-test\n")
    monkeypatch.setattr(attempts, "log_path", lambda root: _unstubbed_log_path(root) if Path(root).is_relative_to(tmp_path) else tmp_path / "stray.jsonl")
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch)
    monkeypatch.setattr(research_command, "_REPO_ROOT", worktree)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(worktree / "registry.jsonl", n_trials=1)]).exit_code == 0
    subprocess.run(["git", "-C", str(main), "worktree", "remove", "--force", str(worktree)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(main), "branch", "-q", "-D", "research/x"], check=True, capture_output=True)
    monkeypatch.setattr(research_command, "_REPO_ROOT", main)
    calls = _stub_subject(monkeypatch, "stub-2")

    refused = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(main / "registry.jsonl", n_trials=1)])

    assert refused.exit_code == 1 and f"{log_id[:8]}#1 stub adopt" in refused.output and "on research/x" in refused.output
    assert calls == []
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    admitted = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(main / "registry.jsonl", n_trials=2)])
    assert admitted.exit_code == 0, admitted.output
    spec_hash = hashlib.sha256((main / _STUB_SPEC).read_bytes()).hexdigest()
    assert json.loads((main / "registry.jsonl").read_text())["attempt"]["counted"] == [
        {"log": log_id, "id": 1, "family": "STUB", "subject": "stub", "spec_hash": spec_hash, "verdict": "adopt", "metrics": {"sharpe": 1.0}}
    ]


def test_a_run_refused_after_its_print_still_counts(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    refused = runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)])
    assert refused.exit_code == 1 and '"sharpe": 1.0' in refused.output and not registry.exists()
    assert _log_lines(_attempts_log)[-1]["verdict"] == "adopt"
    calls = _stub_subject(monkeypatch, "stub-2")
    assert runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1)]).exit_code == 1 and calls == []

    retry = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert retry.exit_code == 0, retry.output
    assert json.loads(registry.read_text())["attempt"]["absorbs"] == [1]


def test_a_retry_whose_numbers_moved_is_refused_after_its_print_and_both_count(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
    _stub_subject(monkeypatch, metrics={"sharpe": 2.0})

    retry = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    assert retry.exit_code == 1 and '"sharpe": 2.0' in retry.output and f"{log8}#1" in retry.output and not registry.exists()
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    third = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=2)])
    assert third.exit_code == 1 and f"{log8}#1" in third.output and f"{log8}#2" in third.output


def _end_refused(self, attempt, **outcome):
    raise OSError("No space left on device")


@pytest.mark.parametrize(
    ("refused", "figure"),
    [
        pytest.param("after-its-print", 3, id="after-its-print"),
        pytest.param("before-the-fit", 3, id="before-the-fit"),
        pytest.param("open-and-held", 2, id="open-and-held"),
        pytest.param("frozen", 3, id="frozen"),
    ],
)
def test_raising_n_trials_to_the_figure_a_refusal_names_admits_the_next_run(tmp_path, monkeypatch, _attempts_log, refused, figure):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    if refused == "after-its-print":
        stub = subjects.SUBJECTS["stub"]

        def build(reader, dataset, window, as_of=None, accept_holes=False):
            _planted(_attempts_log, ("elsewhere", None))
            return stub.build(reader, dataset, window, as_of, accept_holes)

        monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))
        first = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])
        assert '"sharpe": 1.0' in first.output, first.output
        assert "0 records, the next run, and 2 attempts that never landed" in first.output, first.output
    else:
        if refused == "before-the-fit":
            assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
        else:
            with monkeypatch.context() as patch:
                patch.setattr(attempts.AttemptLog, "end", _end_refused)
                # Its attempt stands for one whose process exited once its end was refused.
                patch.setattr(attempts, "_process_marks", lambda: {"pid": os.getpid(), "boot": "another boot"})
                assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1
        if refused == "frozen":
            _seed(registry, "STUB", 1, subject="stub")
        else:
            _planted(_attempts_log, ("elsewhere", "reject"))
        first = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])
        assert '"sharpe"' not in first.output, first.output
    named = re.search(r"family STUB needs at least (\d+)", first.output)
    assert first.exit_code == 1 and named and int(named.group(1)) == figure, first.output
    assert ("stub's n_trials is frozen by its trial 1" in first.output) == (refused == "frozen"), first.output
    n, subject = figure, "stub-2" if refused == "frozen" else "stub"
    # This stub's numbers move with its declared count and its spec file stays, the case where the figure is exact.
    _stub_subject(monkeypatch, subject, n_trials=n, metrics={"sharpe": 1.0 / n})

    retry = runner.invoke(app, [*_stub_eval(subject), *_register_args(registry, n_trials=n)])

    assert retry.exit_code == 0, retry.output


def test_a_retry_of_a_printed_attempt_at_the_budgets_edge_is_refused_before_its_fit(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1

    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=2, metrics={"sharpe": 2.0})

    assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in output
    assert len(registry.read_text().splitlines()) == 24


def test_a_bucket_filled_during_the_fit_refuses_the_run_after_its_print(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    stub = subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _planted(_attempts_log, ("elsewhere", None), family="OTHER")
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and '"sharpe": 1.0' in result.output, result.output
    assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in result.output
    assert len(registry.read_text().splitlines()) == 24


@pytest.mark.parametrize(
    ("marks", "admitted"),
    [
        pytest.param(lambda: None, False, id="its-process-runs"),
        pytest.param(lambda: {"pid": _reaped_pid(), "boot": attempts._boot_id()}, True, id="its-pid-reaped"),
        pytest.param(lambda: {"pid": os.getpid(), "boot": "another boot"}, True, id="another-boot"),
    ],
)
def test_an_open_attempt_at_the_budgets_edge_is_held_only_when_its_process_is_gone(tmp_path, monkeypatch, _attempts_log, marks, admitted):
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setitem(budget.BUCKET_OF, "STUB", "B")
    monkeypatch.setitem(budget.BUCKET_OF, "OTHER", "B")
    _seed(registry, "OTHER", 24)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    with monkeypatch.context() as patch:
        patch.setattr(attempts.AttemptLog, "end", _end_refused)
        if (planted := marks()) is not None:
            patch.setattr(attempts, "_process_marks", lambda: planted)
        assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1

    if not admitted:
        output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=2)
        assert "bucket B has spent 25 of its 25 trials (24 records, 1 attempts that never landed)" in output
        return
    _stub_subject(monkeypatch, n_trials=2)
    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)])
    assert result.exit_code == 0, result.output
    lines = registry.read_text().splitlines()
    assert len(lines) == 25 and json.loads(lines[-1])["attempt"]["absorbs"] == [1]


def test_a_stop_spends_nothing(tmp_path, monkeypatch, _attempts_log):
    registry, ledger = tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)]).exit_code == 0
    assert _kept(ledger)[0]["attempt"]["id"] == 1
    _stub_subject(monkeypatch, "stub-2")
    # The stop's reading landed in `ledger`; this registration reads another, so the stop is not landed here.
    elsewhere = tmp_path / "another-ledger.jsonl"
    admitted = runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1, ledger=elsewhere)])
    assert admitted.exit_code == 0, admitted.output


def test_a_failed_build_logs_a_failed_end_and_counts_nothing(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _raising_stub(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 1
    assert _log_lines(_attempts_log)[-1]["failed"] == "SubjectError: the stub's window is too short"
    _stub_subject(monkeypatch, "stub-2")
    assert runner.invoke(app, [*_stub_eval("stub-2"), *_register_args(registry, n_trials=1)]).exit_code == 0


def test_a_scratch_registry_run_is_an_orphan_once_the_committed_registry_is_the_target(tmp_path, monkeypatch, _attempts_log):
    scratch, committed = tmp_path / "scratch.jsonl", tmp_path / "committed.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), committed)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(scratch, n_trials=1)]).exit_code == 0
    calls = _stub_subject(monkeypatch, "stub-2")
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    base = ["--register", "--iteration", "iter-001", "--family", "STUB"]
    refused = runner.invoke(app, [*_stub_eval("stub-2"), *base, "--n-trials", "1"])
    assert refused.exit_code == 1 and f"{log8}#1" in refused.output and calls == []
    _stub_subject(monkeypatch, "stub-2", n_trials=2)
    assert runner.invoke(app, [*_stub_eval("stub-2"), *base, "--n-trials", "2"]).exit_code == 0
    assert [entry["id"] for entry in json.loads(committed.read_text())["attempt"]["counted"]] == [1]


def test_an_open_attempt_in_the_family_raises_the_count(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _planted(_attempts_log, ("elsewhere", None))
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    assert f"{log8}#1 elsewhere no end" in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    _stub_subject(monkeypatch, n_trials=2)

    admitted = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)])

    assert admitted.exit_code == 0, admitted.output
    assert json.loads(registry.read_text())["attempt"]["counted"] == []


def test_a_held_attempt_another_session_lands_mid_fit_is_absorbed_by_no_one_twice(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), "--verdict", "park", *_register_args(registry, n_trials=1)]).exit_code == 1
    log_id, stub = attempts.AttemptLog(_attempts_log).log_id, subjects.SUBJECTS["stub"]

    def build(reader, dataset, window, as_of=None, accept_holes=False):
        _seed(registry, "OTHER", 1, log=log_id)
        return stub.build(reader, dataset, window, as_of, accept_holes)

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(stub, build=build))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert json.loads(registry.read_text().splitlines()[-1])["attempt"]["absorbs"] == []


@pytest.mark.parametrize(
    ("planted", "method", "fitted", "figure"),
    [
        pytest.param("a-begin", "begin", False, 2, id="a-begin-in-the-window"),
        pytest.param("a-record", "begin", False, 2, id="a-record-in-the-window"),
        pytest.param("a-begin", "locked", True, 3, id="a-begin-before-the-post-check"),
    ],
)
def test_what_lands_between_a_read_and_the_lock_its_count_takes_is_counted(tmp_path, monkeypatch, _attempts_log, planted, method, fitted, figure):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    real = getattr(attempts.AttemptLog, method)

    def planting(self, *args, **kwargs):
        monkeypatch.setattr(attempts.AttemptLog, method, real)
        if planted == "a-begin":
            _planted(_attempts_log, ("elsewhere", None))
        else:
            _seed(registry, "STUB", 1)
        return real(self, *args, **kwargs)

    monkeypatch.setattr(attempts.AttemptLog, method, planting)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    named = re.search(r"family STUB needs at least (\d+)", result.output)
    assert result.exit_code == 1 and named and int(named.group(1)) == figure, result.output
    assert bool(calls) is fitted, result.output


def test_a_plain_eval_of_a_ruled_subject_is_refused_before_any_read(tmp_path, monkeypatch):
    _anchor(monkeypatch, tmp_path / "no-data")
    calls = _stub_subject(monkeypatch)

    result = runner.invoke(app, _stub_eval())

    assert result.exit_code == 1 and calls == []
    assert (
        "stub declares a verdict rule, so every run of it is a trial: run it with --register; a ruleless pre-flight subject "
        "reads the inputs without the trial's result"
    ) in result.output


def test_a_plain_eval_of_a_ruleless_subject_is_admitted(tmp_path, monkeypatch, _attempts_log):
    _anchor(monkeypatch, _stub_dataset(tmp_path))
    _stub_subject(monkeypatch, verdict=None, no_verdict=None, family=None, n_trials=None)
    assert runner.invoke(app, _stub_eval()).exit_code == 0 and len(_log_lines(_attempts_log)) == 1


def test_a_family_other_than_the_subjects_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, flags={"family": "OTHER"})
    assert "--family OTHER is not STUB, the family stub declares: pass --family STUB" in output


def test_an_n_trials_other_than_the_subjects_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, flags={"n_trials": 2})
    assert "--n-trials 2 is not 1, the count stub declares and deflates at: pass --n-trials 1" in output


def test_a_subject_counting_fewer_than_its_family_needs_is_refused_naming_each_orphan(tmp_path, monkeypatch, _attempts_log):
    _planted(_attempts_log, ("elsewhere", "reject"), ("elsewhere-too", "park"))
    log8 = attempts.AttemptLog(_attempts_log).log_id[:8]
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert "stub declares n_trials 1, and family STUB needs at least 3: 0 records, this run, and 2 attempts that never landed" in output
    assert f"{log8}#1 elsewhere reject" in output and f"{log8}#2 elsewhere-too park" in output
    assert "raise stub's n_trials, which its deflated Sharpe uses, commit, then run again" in output


def test_a_bucket_at_its_budget_is_refused(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "A1", 40)
    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, family="A1", n_trials=41)
    assert (
        "bucket A has spent 40 of its 40 trials (40 records, 0 attempts that never landed), so this trial would exceed it: an "
        "expansion is the owner's ruling, written into cli/registry/budget.py by a pull request that quotes it"
    ) in output


def test_a_bucket_one_below_its_budget_admits_its_last_trial(tmp_path, monkeypatch):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "A1", 39)
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch, family="A1", n_trials=40)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, family="A1", n_trials=40)])

    assert result.exit_code == 0, result.output
    assert len(registry.read_text().splitlines()) == 40


def test_a_family_in_no_bucket_is_refused(tmp_path, monkeypatch):
    output = _refused_before_the_fit(tmp_path, monkeypatch, family="ZZ")
    assert "family ZZ is in no bucket of cli/registry/budget.py: add it with its bucket in a reviewed pull request" in output


@pytest.mark.parametrize(
    ("n_trials", "message"),
    [
        pytest.param(2, "stub declares n_trials 2, and its trial 1 landed at n_trials 1, which that record's deflated Sharpe used, so its n_trials is frozen: declare a new subject (a new name) for the further trial", id="raised-count"),
        pytest.param(1, "stub's n_trials is frozen by its trial 1: declare a new subject (a new name) for the further trial", id="declared-count"),
    ],
)
def test_a_landed_subjects_n_trials_is_frozen(tmp_path, monkeypatch, n_trials, message):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)]).exit_code == 0

    assert message in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry, n_trials=n_trials)


def _repo_with_develop(tmp_path: Path, monkeypatch, *records: dict, develop_at: str = "head") -> Path:
    repo = tmp_path / "repo"
    head = _git_repo(repo)
    if records:
        (repo / "docs" / "reference").mkdir(parents=True)
        (repo / attempts.REGISTRY_RELPATH).write_text("".join(json.dumps(record) + "\n" for record in records))
        subprocess.run(["git", "-C", str(repo), "add", "--", attempts.REGISTRY_RELPATH], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(repo), *_GIT_IDENTITY, "commit", "-q", "-m", "landed"], check=True, capture_output=True)
        landed_at = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", "--detach", head], check=True, capture_output=True)
        head = landed_at if develop_at == "current" else head
    if develop_at != "none":
        subprocess.run(["git", "-C", str(repo), "update-ref", attempts.DEVELOP, head], check=True, capture_output=True)
    monkeypatch.setattr(attempts, "landed", lambda code_root, registry, ledger: _unstubbed_landed(repo, registry, ledger))
    return repo


def test_the_register_path_makes_no_network_call(tmp_path, monkeypatch):
    repo = _repo_with_develop(tmp_path, monkeypatch)
    log = repo / ".local" / "trial-attempts.jsonl"
    log.parent.mkdir()
    log_id = attempts.init_log(log, host="zcrypto-test")
    (repo / attempts.ALLOWLIST).parent.mkdir(parents=True, exist_ok=True)
    (repo / attempts.ALLOWLIST).write_text(f"{log_id} zcrypto-test\n")
    subprocess.run(["git", "-C", str(repo), "add", "--", attempts.ALLOWLIST], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *_GIT_IDENTITY, "commit", "-q", "-m", "allowlist"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "update-ref", attempts.DEVELOP, "HEAD"], check=True, capture_output=True)
    monkeypatch.setattr(attempts, "log_path", lambda code_root: _unstubbed_log_path(repo))
    monkeypatch.setattr(attempts, "allowed_log_ids", lambda code_root: _unstubbed_allowed(repo))
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    _stub_subject(monkeypatch)
    argvs, real_run = [], subprocess.run

    def spy(argv, *args, **kwargs):
        argvs.append([str(arg) for arg in argv])
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", spy)

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 0, result.output
    assert any("show" in argv or "cat-file" in argv for argv in argvs), argvs
    assert [argv for argv in argvs if {"fetch", "ls-remote", "gh"} & set(argv) or argv[0] == "gh"] == []


@pytest.mark.parametrize("develop_at", ["stale", "current"])
def test_a_stale_develop_requires_the_same_count(tmp_path, monkeypatch, _attempts_log, develop_at):
    _planted(_attempts_log, ("elsewhere", "reject"))
    log_id = attempts.AttemptLog(_attempts_log).log_id
    landed_record = {"trial_id": 1, "family": "STUB", "record_hash": "7" * 64, "n_trials_in_family": 1,
                     "invocation": {"subject": "elsewhere"}, "attempt": {"log": log_id, "id": 1, "absorbs": [], "counted": []}}
    # A legacy record: neither an invocation key nor an attempt key.
    legacy = {"trial_id": 2, "family": "A1", "record_hash": "6" * 64, "n_trials_in_family": 1}
    _repo_with_develop(tmp_path, monkeypatch, landed_record, legacy, develop_at=develop_at)
    registry = tmp_path / "registry.jsonl"

    assert "family STUB needs at least 2" in _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    _stub_subject(monkeypatch, n_trials=2)
    assert runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=2)]).exit_code == 0
    counted = [entry["id"] for entry in json.loads(registry.read_text())["attempt"]["counted"]]
    assert counted == ([1] if develop_at == "stale" else [])


def test_an_unresolvable_develop_is_refused(tmp_path, monkeypatch):
    repo = _repo_with_develop(tmp_path, monkeypatch, develop_at="none")
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert f"origin/develop does not resolve in {repo}: run git fetch origin develop, then run again" in output


def test_an_absent_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    _attempts_log.unlink()

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and calls == [] and not _attempts_log.exists()
    assert (
        f"no trial-attempts log at {_attempts_log}: restore it from a backup if one exists; otherwise create a new log with "
        "zcrypto research attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in result.output


def test_a_broken_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _anchor(monkeypatch, _stub_dataset(tmp_path), registry)
    calls = _stub_subject(monkeypatch)
    _attempts_log.write_text(_attempts_log.read_text().replace('"host":"zcrypto-test"', '"host":"elsewhere"'))

    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])

    assert result.exit_code == 1 and calls == [] and not registry.exists()
    assert f"{_attempts_log}: line 1 line_hash" in result.output
    assert (
        "rename it aside, then restore it from a backup if one exists; otherwise create a new log with zcrypto research "
        "attempts-init and add its id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in result.output


def test_an_unlisted_log_is_refused_with_its_remedy(tmp_path, monkeypatch, _attempts_log):
    (tmp_path / "trial-attempt-logs.txt").write_text("")
    log_id = attempts.AttemptLog(_attempts_log).log_id
    output = _refused_before_the_fit(tmp_path, monkeypatch)
    assert (
        f"the trial-attempts log {_attempts_log} has id {log_id}, which docs/reference/trial-attempt-logs.txt on origin/develop "
        "does not list: restore the listed log from a backup if one exists; otherwise add this id to "
        "docs/reference/trial-attempt-logs.txt by PR, saying what was lost, and run again once it has merged and "
        "origin/develop is fetched"
    ) in output


def test_a_log_lacking_a_landed_attempt_is_refused(tmp_path, monkeypatch, _attempts_log):
    registry = tmp_path / "registry.jsonl"
    _seed(registry, "STUB", 1, log=attempts.AttemptLog(_attempts_log).log_id, first_id=5)
    output = _refused_before_the_fit(tmp_path, monkeypatch, registry=registry)
    assert (
        f"{_attempts_log} lacks attempt 5, which trial 1 carries: the log was truncated or replaced; rename it aside, then "
        "restore it from a backup if one exists; otherwise create a new log with zcrypto research attempts-init and add its "
        "id to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
    ) in output
```

with `from dataclasses import replace`, `from cli.registry import TrialRegistry` and `from tests.test_trial_attempts import _reaped_pid` among the module's imports, and `_GIT_IDENTITY` the module's.

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run pytest tests/test_research_command.py -k "abandoned_branch or refused_after_its_print or numbers_moved or figure_a_refusal_names or budgets_edge or filled_during_the_fit or stop_spends or counts_nothing or scratch_registry or open_attempt or held_attempt or lands_between or plain_eval or other_than_the_subjects or fewer_than or at_its_budget or one_below_its_budget or no_bucket or landed_subjects_n_trials_is_frozen or network or stale_develop or unresolvable or absent_log or broken_log or unlisted_log or lacking" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt` — it selects no case that exists before this task.
Expected: each fails — the refusals absent (exit 0 where 1 is asserted), `counted` empty where the orphan is asserted — except five that pass until Step 4 and are proven by their probes: `test_a_plain_eval_of_a_ruleless_subject_is_admitted`, `test_a_stop_spends_nothing`, `test_a_failed_build_logs_a_failed_end_and_counts_nothing`, `test_a_held_attempt_another_session_lands_mid_fit_is_absorbed_by_no_one_twice` and `test_a_bucket_one_below_its_budget_admits_its_last_trial`, each an admission nothing refuses yet.

- [ ] **Step 4: Implement the register path** — the Interfaces block's six steps in `cli/research/command.py`, `budget` read through its module, every git call through `attempts`; D4's split remedy composed once and used before the fit and after the print.

- [ ] **Step 5: README and help** — the four `help=` strings of `--register`, `--family`, `--n-trials` and `--registry` in `cli/research/command.py` rewritten to say what their README rows below say, `--n-trials` no longer "must exceed the count already recorded"; then the README. `--register`: a ruled run's first line goes to the clone's trial-attempts log before the fit and its last before the print, so a run whose branch never merges still counts; refused for an absent, unlisted or damaged log; a plain eval of a subject with a rule is refused. `--family`: must equal the family the subject declares, which must be in a bucket of `cli/registry/budget.py`. `--n-trials`: must equal the count the subject declares, which must cover the family's records, this run and its attempts that never landed; frozen once a record of the subject has landed, when a further trial declares a new subject. `--registry`: a ruled run writes its attempt to the clone's trial-attempts log whatever file this names, and one whose record does not reach the committed registry counts, for every run into the committed registry, against its family and bucket as an attempt that never landed, so a rehearsal into another file spends a trial. The paragraph: the bucket budgets refuse a trial past them.

- [ ] **Step 6: Run the Step 3 tests, then the two modules whole** — `uv run pytest tests/test_research_command.py -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt` (its cases listed in `tests/slow-cases.txt` included, the run split by node id into parts each under 600 s) and `tests/test_registry_replay.py`; expected all pass.

- [ ] **Step 7: Consumers, then commit** — `consumers.sh --direct` over the four paths of the `git add` below, and the Global Constraints' walkers for files under `cli/` and for help strings.

```bash
git add cli/research/command.py README.md tests/test_research_command.py tests/test_registry_replay.py
git commit -F - <<'EOF'
feat(research): the register path counts every attempt — the family, count, budget and log refusals, the provisional absorption and the plain-eval refusal

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 8: Probe** — `--file cli/research/command.py`, control `s/^def _abort(/def _abort_gone(/` for a case that asserts a refusal's message, `s/^def _echo_replay_case(/def _echo_replay_case_gone(/` for one that asserts an append, and `s/^@research_app.command("eval")$/@research_app.command("eval-gone")/` for `ruleless_subject_is_admitted`, which asserts neither; `--file cli/registry/attempts.py`, control `s/^def _git(/def _git_gone(/`. Each row one probe, expected `KILLED`:

| `-k` case | file | mutation |
| -- | -- | -- |
| `test_a_plain_eval_of_a_ruled_subject_is_refused_before_any_read` | command.py | D7's `if` made `if False:` |
| `ruleless_subject_is_admitted` | command.py | D7's `verdict` condition cut, so every plain eval is refused |
| `test_a_family_other_than_the_subjects_is_refused` | command.py | the family assertion's `if` made `if False:` |
| `test_an_n_trials_other_than_the_subjects_is_refused` | command.py | the count assertion's `if` made `if False:` |
| `test_a_family_in_no_bucket_is_refused` | command.py | the bucket membership's `if` made `if False:` |
| `test_a_bucket_at_its_budget_is_refused` | command.py | the budget's `if` before the fit made `if False:` |
| `one_below_its_budget` | command.py | the budget's `>` before the fit made `>=` |
| `printed_attempt_at_the_budgets_edge` | command.py | `strict`'s `hold_finished=False` made `hold_finished=True`, so the budget holds out the finished attempt this retry shares its arguments with |
| `budgets_edge_is_held_only and its-pid-reaped` | command.py | `strict`'s `hold=hold` made `hold=None`, so the budget counts the open attempt whose process is gone |
| `budgets_edge_is_held_only and its-process-runs` | attempts.py | the held class's `_alive(X.begin)`-false conjunct made `True`, range-addressed to that class, so the budget holds out the attempt whose process runs |
| `budgets_edge_is_held_only and another-boot` | attempts.py | `_alive`'s boot comparison made `if False:` |
| `filled_during_the_fit` | command.py | the budget's `if` after the print made `if False:` |
| `fewer_than` | command.py | the count's `if` before the fit made `if False:` |
| `frozen and raised-count` | command.py | the frozen count's `if` made `if False:` |
| `frozen and declared-count` | command.py | the frozen tail's condition made `False` |
| `test_an_absent_log_is_refused_with_its_remedy` | command.py | the absent log's `if` made `if False:` |
| `broken_log` | command.py | the broken log's remedy suffix made `""` |
| `unlisted_log` | command.py | the unlisted id's `if` made `if False:` |
| `lacking` | command.py | `lacking`'s refusal `if` made `if False:` |
| `numbers_moved` | command.py | the post-print count's `if` made `if False:` |
| `figure_a_refusal_names and after-its-print` | command.py | the count the post-print remedy is composed from made that refusal's own `count`; apart, the post-print `<this run>`'s "the next run" made "this run" |
| `figure_a_refusal_names and before-the-fit` | command.py | the count the pre-fit remedy is composed from made that refusal's own `count` |
| `figure_a_refusal_names and open-and-held` | command.py | the remedy's raise-tail `hold` made `None` |
| `figure_a_refusal_names and frozen` | command.py | the remedy's frozen-tail `None` made `hold` |
| `still_counts` | command.py | the admission count's `hold=hold` made `hold=None`; apart, `list(count.absorbs)` made `[]` |
| `abandoned_branch` | command.py | `count.counted(family)` made `[]` |
| `lands_mid_fit` | command.py | the locked block's re-read of `landed` replaced by the one before the data |
| `lands_between and a-begin-in-the-window` | command.py | the admission count's `lines` argument made `log.lines`, the snapshot the constructor read |
| `lands_between and a-record-in-the-window` | command.py | `admit`'s re-read of `landed` replaced by the one before the data |
| `lands_between and a-begin-before-the-post-check` | command.py | the post-print count's `lines` argument made `log.lines`, as the `end` refreshed it |
| `stale_develop and current` | command.py | the frozen check's `.get("invocation")` made `["invocation"]` |
| `test_the_register_path_makes_no_network_call` | attempts.py | a `_git(` call prefixed `_git(code_root, "fetch", "--dry-run") and `, which runs the fetch and keeps the call's own result whatever the line's shape, a CompletedProcess being truthy: the develop check's (`_git(code_root, "rev-parse", "--verify"`); apart, `main_checkout`'s (`_git(code_root, "rev-parse", "--git-common-dir"`); apart, the `cat-file -e` call `allowed_log_ids` reaches |
| `stale_develop and current` | attempts.py | `DEVELOP` cut from `landed`'s refs |
| `open_attempt_in_the_family` | attempts.py | the `verdict` filter cut from `counted` |
| `scratch_registry` | attempts.py | the local orphan's append made `None` |
| `stop_spends` / `counts_nothing` | attempts.py | the stopped class, and apart the failed class, made `if False:` |

______________________________________________________________________

### Task 8: CI holds every record past 48 — checks (vii)–(xii) and the landed-subject literal (D9, D4's literal)

**Files:**
- Modify: `tests/test_trial_registry_provenance.py`

**Interfaces:**
- Consumes: Task 2's `BUCKET_OF`, `BUDGET`; Task 3's `parse_allowlist`, `ALLOWLIST_FILE`; Task 5's `attempt` on `TrialRecord` and `ReadingRecord`; Task 6's declarations.
- Produces:

```python
LANDED_N_TRIALS: dict[str, int] = {"b1-hourly-rv": 3}

def _attempt_findings(trials: dict[int, dict], readings: dict[int, dict], *, subjects: dict, bucket_of: Mapping[str, str | None],
                      budget: Mapping[str, int], allowlist: frozenset[str]) -> list[str]: ...
```

`_attempt_findings` implements the spec's CI checks section over the records past 48 and the readings past 1 (records from trial 1 counting in (ix) and (x)), each finding opening `<label> (<check>): ` — `trial-49 (vii): …` — and naming the figure it needed; a record past 48 or a reading past 1 whose subject `SUBJECTS` lacks yields nothing here, since `_findings`' (i) reports it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_trial_registry_provenance.py
from collections.abc import Mapping

from cli.registry.budget import BUCKET_OF, BUDGET

_L = "f" * 32
_FOLLOW = "b2-follow"
_B1_FOLLOW = "b1-follow"
_WITH_FOLLOWER = {
    **SUBJECTS,
    _FOLLOW: replace(SUBJECTS[_B2], name=_FOLLOW, n_trials=2),
    _B1_FOLLOW: replace(SUBJECTS["b1-hourly-rv"], name=_B1_FOLLOW, n_trials=4),
}


def _trial6(trial_id: int, *, family="B2", n=1, subject=_B2, attempt_id=1, absorbs=(), counted=()) -> dict:
    return {**_b2_trial(trial_id, subject), "schema_version": 6, "family": family, "n_trials_in_family": n,
            "attempt": {"log": _L, "id": attempt_id, "absorbs": list(absorbs), "counted": list(counted)}}


# By default the verdict and numbers a clean b2 trial records, so a record landing the attempt late matches its entry.
def _listed(attempt_id: int, family: str = "B2", log: str = _L, *, subject: str = _B2, metrics: dict | None = None) -> dict:
    return {"log": log, "id": attempt_id, "family": family, "subject": subject, "spec_hash": _spec_sha256(_B2_SPEC),
            "verdict": "reject", "metrics": _b2_trial(attempt_id)["metrics"] if metrics is None else metrics}


def _reading2(reading_id: int, subject: str, attempt: dict | None) -> dict:
    return {"reading_id": reading_id, "schema_version": 2, "invocation": {"subject": subject}, "attempt": attempt}


def _count_check(trials=(), readings=(), *, subjects=SUBJECTS, bucket_of=BUCKET_OF, budget=BUDGET, allowlist=frozenset({_L})) -> list[str]:
    committed_trials, committed_readings = _trials(), _readings()
    committed_trials.update({trial["trial_id"]: trial for trial in trials})
    committed_readings.update({reading["reading_id"]: reading for reading in readings})
    return _attempt_findings(committed_trials, committed_readings, subjects=subjects, bucket_of=bucket_of, budget=budget, allowlist=allowlist)


def test_every_record_past_48_holds_to_its_count_family_budget_log_and_carry_forward():
    allowlist = frozenset(parse_allowlist(ALLOWLIST_FILE.read_text(encoding="utf-8")))
    assert _attempt_findings(_trials(), _readings(), subjects=SUBJECTS, bucket_of=BUCKET_OF, budget=BUDGET, allowlist=allowlist) == []


def test_a_clean_schema_6_trial_yields_no_finding():
    assert _count_check([_trial6(49)]) == []


@pytest.mark.parametrize(
    ("trials", "readings", "over", "finding"),
    [
        pytest.param([_trial6(49)], [], {"subjects": {**SUBJECTS, _B2: replace(SUBJECTS[_B2], family="B1")}}, "trial-49 (vii):", id="family-off-the-subject"),
        pytest.param([_trial6(49, n=2)], [], {}, "trial-49 (viii):", id="n-off-the-subject"),
        pytest.param([_trial6(49, counted=[_listed(5)])], [], {}, "trial-49 (ix):", id="below-the-count"),
        pytest.param([_trial6(49), _trial6(50, attempt_id=2)], [], {}, "trial-50 (ix):", id="a-second-record-of-the-family"),
        pytest.param([_trial6(49)], [], {"budget": {"A": 40, "B": 3, "C": 10}}, "(x):", id="over-the-budget"),
        pytest.param([_trial6(49)], [], {"bucket_of": {k: v for k, v in BUCKET_OF.items() if k != "B2"}}, "(x):", id="a-family-in-no-bucket"),
        pytest.param([_trial6(49)], [], {"allowlist": frozenset()}, "trial-49 (xi):", id="a-log-off-the-allowlist"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1", "e" * 32)])], [], {}, "trial-49 (xi):", id="a-counted-log-off-the-allowlist"),
        pytest.param([_trial6(49, attempt_id=2, absorbs=[1])], [_reading2(2, _B2, {"log": _L, "id": 1, "absorbs": []})], {}, "(xi):", id="an-attempt-landed-twice"),
        pytest.param([_trial6(49)], [_reading2(2, _B2, None)], {}, "reading-2 (xi):", id="a-ruled-reading-without-its-attempt"),
        pytest.param([_trial6(49)], [_reading2(2, "b2-arm-a-bar", {"log": _L, "id": 3, "absorbs": []})], {}, "reading-2 (xi):", id="a-ruleless-reading-with-an-attempt"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2)], [], {"subjects": _WITH_FOLLOWER}, "trial-50 (xii):", id="a-listed-orphan-dropped"),
        pytest.param([_trial6(49, family="B1", n=4, subject=_B1_FOLLOW, counted=[_listed(5)]), _trial6(50, attempt_id=2)], [], {"subjects": _WITH_FOLLOWER}, "trial-50 (xii):", id="a-bucket-mates-orphan-dropped"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2, counted=[_listed(5, "B1")])], [], {"subjects": _WITH_FOLLOWER}, None, id="a-listed-orphan-carried"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW)]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=6, absorbs=[5])], [], {"subjects": _WITH_FOLLOWER}, None, id="a-listed-orphan-landed-since"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2, counted=[_listed(5, "B1")])], [], {"subjects": _WITH_FOLLOWER, "budget": {"A": 40, "B": 6, "C": 10}}, None, id="an-orphan-two-records-list-spends-once"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW)]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=6, absorbs=[5])], [], {"subjects": _WITH_FOLLOWER, "budget": {"A": 40, "B": 5, "C": 10}}, None, id="a-landed-orphan-spends-nothing-more"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW, metrics={"sharpe": 0.1})]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=5)], [], {"subjects": _WITH_FOLLOWER}, "trial-50 (xi):", id="a-listed-id-landed-with-other-numbers"),
        pytest.param([_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2)], [_reading2(2, _B2, {"log": _L, "id": 5, "absorbs": []})], {"subjects": _WITH_FOLLOWER}, "reading-2 (xi):", id="a-reading-landing-a-listed-orphan"),
    ],
)
def test_one_change_to_a_clean_schema_6_trial_yields_exactly_its_finding(trials, readings, over, finding):
    found = _count_check(trials, readings, **over)

    if finding is None:
        assert found == []
    else:
        assert len(found) == 1 and finding in found[0], found


def test_each_landed_subjects_n_trials_is_frozen_at_its_literal():
    growth = (
        "a subject's n_trials is frozen once a record of it lands: a further trial declares a new subject, and a subject's "
        "first landed record adds its row here in the PR that lands it"
    )
    landed: dict[str, set[int]] = {}
    for entry in _trials().values():
        if entry["invocation"] is not None:
            landed.setdefault(entry["invocation"]["subject"], set()).add(entry["n_trials_in_family"])
    assert LANDED_N_TRIALS == {"b1-hourly-rv": 3}, growth
    assert landed == {subject: {n} for subject, n in LANDED_N_TRIALS.items()}, growth
    assert all(SUBJECTS[subject].n_trials == n for subject, n in LANDED_N_TRIALS.items()), growth
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_trial_registry_provenance.py -k "past_48 or schema_6 or landed_subjects" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `NameError: name '_attempt_findings' is not defined`, and `name 'LANDED_N_TRIALS' is not defined`.

- [ ] **Step 3: Implement `_attempt_findings` and `LANDED_N_TRIALS`** — the six checks, read from `docs/specs/00133-t0222-trial-attempts-design.md`'s `## The CI checks` before writing them, every clause a condition the code holds, and every read of a record's or reading's `attempt`, `absorbs`, `counted` or `invocation` through `.get` (Task 1 Step 5), since `_trials()` and `_readings()` give records 1–48 and reading 1 `attempt: None` and records 1–47 `invocation: None`: (x) over the distinct (log, id) a bucket's `counted` entries name, less those landed, which the two rows at the budget's edge, `an-orphan-two-records-list-spends-once` (B = 6, five records and one distinct orphan) and `a-landed-orphan-spends-nothing-more` (B = 5, five records and none), tell from a sum of each record's entries; "landed" every (log, id) a record or reading carries as `attempt` or in `absorbs`; (x) once per bucket of `budget` plus one finding per family a record carries that `bucket_of` lacks, labelled with the first record carrying it; (xi)'s last clause once per (log, id) a record's `counted` lists and a record or reading lands, labelled with the entry that lands it, a record's `invocation` subject, `spec_hash`, `verdict` and `metrics` compared with the listed entry's and a reading landing one a finding by itself; (xii) per record past 48 against every earlier record of its bucket — of its family when bucketless.

- [ ] **Step 4: Run them to verify they pass** — the Step 2 command; expected pass, the live test over today's file holding no record past 48.

- [ ] **Step 5: Consumers, then commit**

```bash
git add tests/test_trial_registry_provenance.py
git commit -F - <<'EOF'
test(research): CI holds every record past 48 to its family, count, budget, log and carry-forward, and pins each landed subject's n_trials

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probe** — `--file tests/test_trial_registry_provenance.py`, control `s/^def _spec_sha256(/def _spec_sha256_gone(/`: each of the six checks made always-clean (`if False:` on its finding's condition), one probe per finding row of the table — (vii), (viii), (ix), (x) budget, (x) membership, (xi) attempt log, (xi) counted log, (xi) twice, (xi) ruled reading, (xi) ruleless reading, (xi) landed with other numbers, (xi) landed by a reading, (xii) — each against its row id; the `metrics` cut from (xi)'s comparison of a landing record with a listed entry against `a-listed-id-landed-with-other-numbers`, whose subject, `spec_hash` and verdict match its entry's; (ix)'s term for the records of its family before it cut against `a-second-record-of-the-family`; (xii)'s scope narrowed from the bucket to the family against `a-bucket-mates-orphan-dropped`; the landed exemption cut from (xii) against `a-listed-orphan-landed-since`; (x)'s distinct set made a count of every entry against `an-orphan-two-records-list-spends-once`; (x)'s landed exemption cut against `a-landed-orphan-spends-nothing-more`. `--file cli/research/subjects.py`, control `s/^def _b2_verdict(/def _b2_verdict_gone(/`: `_B1_HOURLY_RV_N_TRIALS = 3` made `= 4` against `test_each_landed_subjects_n_trials_is_frozen_at_its_literal`. The live test holds no record past 48 today, so its clauses are proven through the table, which calls the same function.

______________________________________________________________________

### Task 9: the decisions-log tie names every counted orphan (D10)

**Files:**
- Modify: `tests/test_decisions_log_ties.py`

**Interfaces:**
- Consumes: Task 5's `TrialRecord.attempt`.
- Produces: `tie_findings(entries: list[tuple[int, str]], trials: dict[int, str], readings: set[int], counted: dict[int, list[str]] | None = None) -> list[str]` — `counted` maps a trial id to its `<log8>#<id>` tokens; `_COUNTED = re.compile(r"\(attempts counted: ([0-9a-f]{8}#\d+(?:, [0-9a-f]{8}#\d+)*)\)")`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_decisions_log_ties.py
@pytest.mark.parametrize(
    ("line", "counted", "finding"),
    [
        pytest.param("[iter-180] B1 trial 4 — REJECT (registry trial 49).", {49: ["ffffffff#5"]}, "missing ['ffffffff#5']", id="a-counted-orphan-unnamed"),
        pytest.param("[iter-180] B1 trial 4 — REJECT (registry trial 49) (attempts counted: ffffffff#5, ffffffff#6).", {49: ["ffffffff#5"]}, "extra ['ffffffff#6']", id="an-orphan-the-record-does-not-count"),
    ],
)
def test_a_header_names_exactly_the_orphans_its_record_counted(line, counted, finding):
    found = tie_findings(_entries([line]), {49: "reject"}, set(), counted)

    assert len(found) == 1 and finding in found[0], found


@pytest.mark.parametrize(
    ("line", "counted"),
    [
        pytest.param("[iter-180] B1 trial 4 — REJECT (registry trial 49) (attempts counted: ffffffff#5, eeeeeeee#2).", {49: ["eeeeeeee#2", "ffffffff#5"]}, id="every-counted-orphan-named"),
        pytest.param("[iter-180] B1 trial 4 — REJECT (registry trial 49).", {49: []}, id="a-record-that-counted-none"),
        pytest.param("[iter-180] B1 trial 4 — REJECT against the incumbent (registry trial 47) (registry trial 49) (attempts counted: ffffffff#5).", {47: ["eeeeeeee#2"], 49: ["ffffffff#5"]}, id="an-incumbents-counted-orphan-unnamed"),
    ],
)
def test_a_header_naming_its_counted_orphans_is_no_finding(line, counted):
    assert tie_findings(_entries([line]), {47: "adopt", 49: "reject"}, set(), counted) == []
```

and the live test passes `counted={record.trial_id: [f"{entry['log'][:8]}#{entry['id']}" for entry in record.attempt["counted"]] for record in TrialRegistry(REGISTRY).records if record.attempt}`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_decisions_log_ties.py -k "counted" -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt`
Expected: `TypeError: tie_findings() takes 3 positional arguments but 4 were given`.

- [ ] **Step 3: Implement** — in `tie_findings`, for each header citing `(registry trial N` tokens: the `counted` tokens of its own trial, the highest id it cites, which `_verdict_findings` judges, against the union of its `(attempts counted: …)` tokens, one finding naming the record and `missing [...]` when any is absent and one naming `extra [...]` when any is not counted, each sorted.

- [ ] **Step 4: Run them to verify they pass** — the Step 2 command, then the module whole; expected pass.

- [ ] **Step 5: Consumers, then commit**

```bash
git add tests/test_decisions_log_ties.py
git commit -F - <<'EOF'
test(research): the decisions-log tie names every orphan a record counted

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

- [ ] **Step 6: Probe** — `--file tests/test_decisions_log_ties.py`, control `s/^def _header(/def _header_gone(/`: the missing finding's condition made `if False:` against `a-counted-orphan-unnamed`; the extra finding's against `an-orphan-the-record-does-not-count`; `_COUNTED`'s `{8}` made `{7}` against `every-counted-orphan-named`; the own trial's tokens made the union of every cited trial's against `an-incumbents-counted-orphan-unnamed`.

______________________________________________________________________

### Task 10: T0222 resolved (`topic-ops`)

**Files:** `docs/open-topics/T0222-a-trial-on-an-unmerged-branch-spends-uncounted.md` → `docs/open-topics/archive/`, `docs/open-topics/README.md`.

- [ ] **Step 1** — `status: resolved`, `ripe_when:` deleted, `## Suggested next steps` removed, `## Resolution` naming this branch's commits (the log and the count, the budgets, the allowlist and `attempts-init`, the conftest fixtures, schema 6, the declarations, the register path, the CI checks, the tie) and the spec and plan 00133; the measurement its first step asked for is the spec's measured basis, and the decision its second asked for is the owner's ruling of 2026-10-17 as the spec records it, option 1 taken unattended; `git mv` into `archive/`; `uv run python infra/scripts/topics-index.py`; `uv run pytest -q -p no:cacheprovider --basetemp=.tmp/plan-00133/pt tests/test_open_topics_frontmatter.py`.
- [ ] **Step 2** — the consumers of the two topic paths (`consumers.sh --direct`), then commit, staging the archived topic by its new path, since Step 1's `git mv` staged the rename with the topic's content before its edits:

```bash
git add docs/open-topics/archive/T0222-a-trial-on-an-unmerged-branch-spends-uncounted.md docs/open-topics/README.md
git commit -F - <<'EOF'
docs(open-topics): T0222 resolved — every ruled run is counted from the clone's trial-attempts log

<the task's pytest result line, pasted from its run>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: <the executing session's URL>
EOF
```

Decisions log: the [00133] entry in docs/research/10.phase4-decisions.md, written at spec time (88b5bc73d); no further decision on a phase's subject is made in the tasks.
