from __future__ import annotations

import ast
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
CONFTEST = REPO / "tests" / "conftest.py"
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
_real_allowed = attempts.allowed_log_ids


def _begin_hash(attempt: int) -> str:
    return f"{attempt:064x}"


def _ref(attempt: int) -> dict:
    return {"id": attempt, "begin": _begin_hash(attempt)}


# By default begun before this boot, so its process is gone, as a killed run's is.
def _begin(
    attempt: int,
    *,
    subject="stub",
    family="B1",
    dataset="ohlc-full",
    spec_hash=_SPEC,
    branch="research/x",
    commit="d" * 40,
    pid=1,
    boot="another boot",
    line_hash=None,
) -> dict:
    invocation = {
        "subject": subject,
        "dataset": dataset,
        "window": None,
        "as_of": None,
        "accept_holes": False,
        "comparator_trial": None,
        "commit": commit,
    }
    return {
        "kind": "begin",
        "attempt": attempt,
        "timestamp": f"2026-10-17T19:{attempt:02d}:00+00:00",
        "branch": branch,
        "invocation": invocation,
        "spec_hash": spec_hash,
        "family": family,
        "pid": pid,
        "boot": boot,
        "line_hash": line_hash or _begin_hash(attempt),
    }


def _end(attempt: int, verdict: str | None = "reject", *, stop=None, failed=None, metrics=None) -> dict:
    if failed is None and metrics is None:
        metrics = {"sharpe": 0.3}
    return {
        "kind": "end",
        "attempt": attempt,
        "verdict": verdict,
        "stop": stop,
        "failed": failed,
        "metrics": metrics,
        "metrics_hash": None if metrics is None else compute_hash(metrics),
    }


def _record(trial_id: int, family: str = "B1", *, attempt: dict | None = None, subject: str = "other") -> dict:
    return {
        "trial_id": trial_id,
        "family": family,
        "record_hash": f"{trial_id:064x}",
        "n_trials_in_family": trial_id,
        "invocation": {"subject": subject},
        "attempt": attempt,
    }


def _count(lines, records=(), readings=(), **kw):
    return reconcile(lines, collect(records, readings), log_id=_LOG, bucket_of=_BUCKETS, **kw)


def _fields(tmp_path: Path, n: int) -> dict:
    return {
        "invocation": _begin(n)["invocation"],
        "spec_hash": _SPEC,
        "family": "B1",
        "bucket": "B",
        "n_trials": 4,
        "worktree": tmp_path,
        "branch": "research/x",
        "registry": tmp_path / "r.jsonl",
        "ledger": tmp_path / "l.jsonl",
    }


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
    subprocess.run(
        ["git", "-C", str(root), *_GIT_IDENTITY, "commit", "-q", "--allow-empty", "-m", "fixture"], check=True, capture_output=True
    )
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
        [
            "attempt",
            "boot",
            "branch",
            "bucket",
            "family",
            "host",
            "invocation",
            "kind",
            "ledger",
            "line_hash",
            "n_trials",
            "pid",
            "prev_hash",
            "registry",
            "seq",
            "spec_hash",
            "timestamp",
            "worktree",
        ],
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

    with pytest.raises(
        AttemptLogError,
        match=r"the healed log breaks at line 3 .*, and its bytes before the heal are kept at .*trial-attempts\.jsonl\.torn-",
    ) as refused:
        AttemptLog(path)

    (copy,) = tmp_path.glob("trial-attempts.jsonl.torn-*")
    assert copy.read_bytes() == torn and str(copy) in str(refused.value)
    assert path.read_bytes() == torn[: torn.rindex(b"\n") + 1]
    genesis = tmp_path / "torn-genesis.jsonl"
    genesis.write_bytes(torn[:30])
    with pytest.raises(
        AttemptLogError, match=r"the healed log breaks at line 1 is not a genesis line, and its bytes before the heal are kept at "
    ):
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
    assert left.startswith(whole) and json.loads(left[len(whole) :])["kind"] == "begin"
    assert len(AttemptLog(path).lines) == 5 and path.read_bytes() == whole


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param(
            lambda ls: (ls.pop(0), ls.__setitem__(0, {**ls[0], "seq": 1}), _seal(ls, 0)),
            "line 1 is not a genesis line",
            id="no-genesis",
        ),
        pytest.param(
            lambda ls: (ls.insert(3, {**ls[0], "seq": 4}), [line.update(seq=i + 1) for i, line in enumerate(ls)], _seal(ls, 0)),
            "line 4 is a second genesis line",
            id="second-genesis",
        ),
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
        pytest.param(
            lambda ls: (
                ls[2].update(prev_hash="e" * 64),
                ls[2].update(line_hash=compute_hash({k: v for k, v in ls[2].items() if k != "line_hash"})),
                _seal(ls, 3),
            ),
            "line 3 prev_hash",
            id="prev-hash-breaks",
        ),
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
        (
            {"failed": "SubjectError: too short", "metrics": {"sharpe": 0.3}},
            "metrics must be a non-empty dict exactly when failed is null",
        ),
        ({"verdict": "maybe", "metrics": {"sharpe": 0.3}}, r"verdict must be one of \['adopt', 'park', 'reject'\]"),
    ]:
        with pytest.raises(AttemptLogError, match=match):
            log.end(attempt, **outcome)
    assert len(AttemptLog(path).lines) == 6
    log.end(attempt, stop="the stub's stop", metrics={"sharpe": 0.3})
    log.end(log.begin(lambda lines: None, **_fields(tmp_path, 4)), failed="SubjectError: too short")
    stopped, failed = (line for line in AttemptLog(path).lines[6:] if line["kind"] == "end")
    assert (stopped["stop"], stopped["verdict"], failed["failed"], failed["metrics"]) == (
        "the stub's stop",
        None,
        "SubjectError: too short",
        None,
    )


def test_begin_counts_over_the_lines_another_session_appended_after_this_log_was_read(tmp_path):
    path = _written_log(tmp_path)
    mine, theirs = AttemptLog(path), AttemptLog(path)
    theirs.begin(lambda lines: None, **_fields(tmp_path, 3))
    seen = []

    attempt = mine.begin(seen.append, **_fields(tmp_path, 4))

    assert attempt == 4 and len(seen[0]) == 6 and seen[0][-1]["attempt"] == 3


def test_the_log_path_is_the_main_checkouts_from_any_worktree(tmp_path, monkeypatch):
    main = _repo(tmp_path / "main")
    subprocess.run(
        ["git", "-C", str(main), "worktree", "add", "-q", "-b", "research/x", str(tmp_path / "wt")], check=True, capture_output=True
    )
    monkeypatch.chdir(tmp_path)

    expected = main.resolve() / ".local" / "trial-attempts.jsonl"
    assert _real_log_path(main) == _real_log_path(tmp_path / "wt") == expected


def test_a_common_dir_with_no_checkout_is_refused(tmp_path):
    work = tmp_path / "work"
    (tmp_path / "store").mkdir()
    subprocess.run(
        ["git", "init", "-q", "--separate-git-dir", str(tmp_path / "store" / "repo.git"), str(work)],
        check=True,
        capture_output=True,
    )

    with pytest.raises(
        AttemptLogError,
        match="no main checkout at .*, resolved from git rev-parse --git-common-dir: run from a clone with a working tree",
    ):
        _real_log_path(work)


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

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", "--rootdir", str(tree)],
        cwd=tree,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 1, run.stdout + run.stderr
    assert f"left cli.registry.attempts.{name} on the real" in run.stdout, run.stdout


def test_a_test_that_points_the_log_outside_its_tmp_path_fails_its_teardown(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "conftest.py").write_text(CONFTEST.read_text())
    (tree / "test_scratch.py").write_text(
        "from cli.registry import attempts\n\n\n"
        "def test_points_outside_its_tmp_path(monkeypatch):\n"
        '    monkeypatch.setattr(attempts, "log_path", lambda code_root: code_root / ".local" / "trial-attempts.jsonl")\n'
    )

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", "--rootdir", str(tree)],
        cwd=tree,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 1, run.stdout + run.stderr
    assert "left cli.registry.attempts.log_path resolving outside its tmp_path" in run.stdout, run.stdout


def test_a_test_that_undoes_its_monkeypatch_keeps_the_log_in_its_tmp_path(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "conftest.py").write_text(CONFTEST.read_text())
    (tree / "test_scratch.py").write_text(
        "from cli.registry import attempts\n\n\n"
        "def test_undoes_its_patches(monkeypatch, tmp_path):\n    monkeypatch.undo()\n"
        "    assert attempts.log_path(tmp_path).is_relative_to(tmp_path)\n"
    )

    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=line", "--rootdir", str(tree)],
        cwd=tree,
        capture_output=True,
        text=True,
    )

    assert run.returncode == 0, run.stdout + run.stderr


def test_the_branch_is_none_on_a_detached_head_and_an_orphan_from_one_is_named_so(tmp_path):
    main = _repo(tmp_path / "main")
    subprocess.run(["git", "-C", str(main), "checkout", "-q", "--detach"], check=True, capture_output=True)

    assert attempts.current_branch(main) is None
    (orphan,) = _count([_begin(1, branch=None)]).orphans
    assert orphan.describe() == f"{_LOG[:8]}#1 stub no end 2026-10-17T19:01:00+00:00 on a detached HEAD"


def test_an_attempt_a_record_carries_is_landed():
    record = _record(1, attempt={"log": _LOG, "id": 1, "begin": _begin_hash(1), "absorbs": [], "counted": []})
    assert _count([_begin(1), _end(1)], [record]).required_n("B1") == 1 + 0 + 1
    assert _count([_begin(1), _end(1)]).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1, line_hash="e" * 64), _end(1)], [record]).required_n("B1") == 1 + 1 + 1


def test_an_attempt_in_an_absorbs_is_landed():
    record = _record(1, attempt={"log": _LOG, "id": 2, "begin": _begin_hash(2), "absorbs": [_ref(1)], "counted": []})
    lines = [_begin(1), _end(1, "park"), _begin(2), _end(2)]
    assert _count(lines, [record]).required_n("B1") == 1 + 0 + 1
    assert _count([_begin(1, line_hash="e" * 64), *lines[1:]], [record]).required_n("B1") == 1 + 1 + 1


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


_LISTED = {
    "log": _OTHER,
    "id": 7,
    "begin": _begin_hash(7),
    "family": "B2",
    "subject": "b2-funding-derisk",
    "spec_hash": _SPEC,
    "verdict": "reject",
    "metrics": {"sharpe": 0.1},
}


def test_an_orphan_a_landed_record_lists_is_carried_from_any_log():
    lister = _record(1, attempt={"log": _OTHER, "id": 8, "begin": _begin_hash(8), "absorbs": [], "counted": [_LISTED]})
    count = _count([], [lister])
    assert count.required_n("B2") == 0 + 1 + 1 and count.counted("B1") == [_LISTED]
    assert count.orphans[0].describe() == f"{_OTHER[:8]}#7 b2-funding-derisk reject listed by trial 1"
    relister = _record(2, attempt={"log": _OTHER, "id": 9, "begin": _begin_hash(9), "absorbs": [], "counted": [_LISTED]})
    twice = _count([], [lister, relister])
    assert (twice.required_n("B2"), twice.spent("B"), twice.counted("B1")) == (0 + 1 + 1, 2 + 1, [_LISTED])
    forked = _record(2, attempt={**relister["attempt"], "counted": [{**_LISTED, "begin": "e" * 64}]})
    assert _count([], [lister, forked]).required_n("B2") == 0 + 2 + 1
    landing = _record(3, "B2", attempt={"log": _OTHER, "id": 10, "begin": _begin_hash(10), "absorbs": [_ref(7)], "counted": []})
    assert _count([], [lister, relister, landing]).required_n("B2") == 1 + 0 + 1
    elsewhere = _record(3, "B2", attempt={**landing["attempt"], "absorbs": [{"id": 7, "begin": "e" * 64}]})
    assert _count([], [lister, relister, elsewhere]).required_n("B2") == 1 + 1 + 1


def test_a_listed_orphans_class_is_final():
    lines = [_begin(1), _end(1), _begin(2), _end(2)]
    entry = {
        "log": _LOG,
        "id": 1,
        "begin": _begin_hash(1),
        "family": "B1",
        "subject": "stub",
        "spec_hash": _SPEC,
        "verdict": "reject",
        "metrics": {"sharpe": 0.3},
    }
    lister = _record(1, "B2", attempt={"log": _OTHER, "id": 1, "begin": _begin_hash(1), "absorbs": [], "counted": [entry]})
    assert _count(lines).required_n("B1") == 0 + 1 + 1
    assert _count(lines, [lister]).required_n("B1") == 0 + 2 + 1
    landing = _record(2, "B1", attempt={"log": _LOG, "id": 3, "begin": _begin_hash(3), "absorbs": [_ref(1)], "counted": []})
    assert _count(lines, [lister, landing]).required_n("B1") == 1 + 1 + 1


def test_a_held_attempt_is_out_of_the_orphans_until_this_run_absorbs_it_or_not():
    hold = ("stub", attempts.arguments(_begin(1)["invocation"]), _SPEC)
    assert _count([_begin(1), _end(1)], hold=hold).required_n("B1") == 0 + 0 + 1
    other = ("stub", attempts.arguments(_begin(1, dataset="ohlc-other")["invocation"]), _SPEC)
    assert _count([_begin(1), _end(1)], hold=other).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1), _end(1)], hold=hold, hold_finished=False).required_n("B1") == 0 + 1 + 1
    assert _count([_begin(1)], hold=hold, hold_finished=False).required_n("B1") == 0 + 0 + 1
    same = _count([_begin(1), _end(1), _begin(2), _end(2)], own=2)
    assert (same.required_n("B1"), same.absorbs) == (1, (_ref(1),))
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
        # Where pid 1 is root's, a run by any other user gets PermissionError signalling it: a live process another user owns.
        pytest.param(lambda: {"pid": 1, "boot": attempts._boot_id()}, False, id="another-users-process"),
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
    assert (retried.required_n("B1"), retried.absorbs) == ((1, (_ref(1),)) if gone else (2, ()))
    assert _count([open_x, _begin(2), _end(2)]).required_n("B1") == (2 if gone else 3)


def test_a_log_lacking_an_attempt_a_record_or_reading_names_is_found():
    record = _record(1, attempt={"log": _LOG, "id": 3, "begin": _begin_hash(3), "absorbs": [_ref(2)], "counted": []})
    reading = {"reading_id": 1, "record_hash": "9" * 64, "attempt": {"log": _LOG, "id": 5, "begin": _begin_hash(5), "absorbs": []}}
    foreign = _record(2, attempt={"log": _OTHER, "id": 4, "begin": _begin_hash(4), "absorbs": [], "counted": []})
    assert lacking([_begin(1), _begin(2), _begin(3)], collect([record, foreign], [reading]), _LOG) == [("reading 1", 5)]
    assert lacking([_begin(1)], collect([record], []), _LOG) == [("trial 1", 3), ("trial 1", 2)]
    assert lacking([_begin(1), _begin(2), _begin(3, line_hash="e" * 64)], collect([record], []), _LOG) == [("trial 1", 3)]
    assert lacking([_begin(1), _begin(2, line_hash="e" * 64), _begin(3)], collect([record], []), _LOG) == [("trial 1", 2)]
    entry = {**_LISTED, "log": _LOG, "id": 3, "begin": _begin_hash(3)}
    lister = _record(3, attempt={"log": _OTHER, "id": 5, "begin": _begin_hash(5), "absorbs": [], "counted": [entry, _LISTED]})
    assert lacking([_begin(1), _begin(2), _begin(3), _end(3)], collect([lister], []), _LOG) == []
    assert lacking([_begin(1), _begin(2), _begin(3, line_hash="e" * 64), _end(3)], collect([lister], []), _LOG) == [("trial 3", 3)]
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
    block = {
        "ohlc-test": {
            "files": {"BTC/EUR/1440.parquet": "c" * 64},
            "rows": 10,
            "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
        }
    }
    invocation = {
        "subject": "seed",
        "dataset": "ohlc-test",
        "window": None,
        "as_of": None,
        "accept_holes": False,
        "comparator_trial": None,
        "commit": "d" * 40,
    }
    TrialRegistry(path).append(
        iteration="iter-001",
        family="B1",
        spec_hash="s",
        datasets=block,
        invocation=invocation,
        seeds=[0],
        metrics={"sharpe": 0.3},
        n_trials_in_family=1,
        verdict="reject",
        run_ref="cli/registry/record.py",
    )
    return json.loads(path.read_text().splitlines()[-1])


def test_landed_reads_the_targets_head_and_origin_develop_each_record_once(tmp_path):
    root = _repo(tmp_path / "repo")
    target = _append_one(tmp_path / "target.jsonl")
    with_attempt = _record(2, attempt={"log": _LOG, "id": 1, "begin": _begin_hash(1), "absorbs": [], "counted": []})
    rebased = {**with_attempt, "trial_id": 3, "record_hash": "8" * 64}
    develop_only = _record(4, attempt={"log": _OTHER, "id": 1, "begin": _begin_hash(1), "absorbs": [], "counted": []})
    reading = {"reading_id": 1, "record_hash": "9" * 64, "attempt": {"log": _LOG, "id": 5, "begin": _begin_hash(5), "absorbs": []}}
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
    with pytest.raises(
        AttemptLogError, match=re.escape(f"origin/develop does not resolve in {root}: run git fetch origin develop, then run again")
    ):
        _real_landed(root, tmp_path / "r.jsonl", tmp_path / "l.jsonl")


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
