"""The inbox checker's entry point: with no path it refuses, rather than reporting the clean it never looked for."""

import json
import pathlib
import subprocess
import sys

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "check-agent-lessons.py"

OK = {
    "ts": "2026-09-08T00:00:00Z",
    "session": "zcrypto-bravo",
    "branch": "fix/x",
    "kind": "self-correction",
    "cites": ["a.md"],
    "what": "a thing",
    "why": "a reason",
}


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(_SCRIPT), *args], capture_output=True, text=True, cwd=_ROOT)


def _inbox(tmp_path: pathlib.Path, *records: dict) -> str:
    path = tmp_path / "zcrypto-bravo.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return str(path)


def test_no_path_is_refused_not_reported_clean() -> None:
    # The defect: an empty glob or a forgotten argument exited 0 having opened nothing, and the
    # harvest reads that as an inbox it checked.
    done = _run()
    assert done.returncode != 0, "a bare invocation must refuse, not report a clean it never measured"
    assert "usage" in done.stderr.lower()


def test_an_unreadable_path_refuses_the_same_way_no_path_does(tmp_path: pathlib.Path) -> None:
    # bash's default passes an unmatched glob through as a literal, so a pattern that found no inbox
    # arrives here looking like a real path. Exiting 1 put it in the malformed-record class, and the
    # round's own instruction is that a malformed line is a finding -- so it sends a reader hunting a
    # bad record inside a file that does not exist.
    done = _run(str(tmp_path / "no-such-inbox.jsonl"))
    assert done.returncode == 2, "an unreadable path is a call error, not a bad inbox"
    assert "cannot read" in done.stderr
    # WHICH path and WHY: the round globs several inboxes, so a refusal naming neither leaves an
    # operator to work out which one failed.
    assert "no-such-inbox.jsonl" in done.stderr
    assert "No such file or directory" in done.stderr
    assert "Traceback" not in done.stderr


def test_a_file_whose_bytes_are_not_utf8_is_unreadable_not_malformed(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "zcrypto-bravo.jsonl"
    path.write_bytes(b"\xff\xfe not utf-8\n")
    done = _run(str(path))
    assert done.returncode == 2, "a file that cannot be decoded was never read, so no record is malformed"
    assert "Traceback" not in done.stderr


def test_an_unreadable_file_does_not_strand_the_paths_after_it(tmp_path: pathlib.Path) -> None:
    # The round checks every inbox in one invocation. A decode failure raised inside the loop
    # propagated out of the generator `max()` consumes, so every path after it went unopened while
    # the exit code reported a malformed record -- a clean over inboxes nothing had looked at.
    first = tmp_path / "a.jsonl"
    first.write_bytes(b"\xff\n")
    second = tmp_path / "b.jsonl"
    second.write_text(json.dumps({**OK, "kind": "bogus"}) + "\n")
    done = _run(str(first), str(second))
    assert "b.jsonl" in done.stdout, "the inbox after the unreadable one must still be checked"
    assert "kind must be one of" in done.stdout


def test_a_valid_inbox_still_passes(tmp_path: pathlib.Path) -> None:
    # The true positive beside the refusal: a guard that refused every invocation would ship green.
    done = _run(_inbox(tmp_path, OK))
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_malformed_record_still_fails_and_names_its_line(tmp_path: pathlib.Path) -> None:
    done = _run(_inbox(tmp_path, OK, {**OK, "kind": "rule-not-followed"}))
    assert done.returncode == 1
    assert ":2:" in done.stdout
