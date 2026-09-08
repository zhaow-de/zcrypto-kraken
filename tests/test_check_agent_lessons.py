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
    assert done.returncode == 2, "the checker could not read it, so no record in it is malformed"
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


def test_two_records_spliced_onto_one_physical_line_are_one_line(tmp_path: pathlib.Path) -> None:
    # `str.splitlines()` breaks on NEL, LS and PS where iterating the file does not, so a splice that
    # put two records on one line read as two clean ones and the file was certified. The tool's whole
    # output is `path:line`, so it has to agree with the file about where the lines are.
    path = tmp_path / "zcrypto-bravo.jsonl"
    path.write_text(json.dumps(OK) + chr(0x85) + json.dumps(OK) + "\n", encoding="utf-8")
    done = _run(str(path))
    assert done.returncode == 1, "one physical line carrying two records is not a record"
    assert ":1:" in done.stdout, "and the coordinate must be the line the file actually has"


def test_an_unreadable_path_outranks_a_bad_record(tmp_path: pathlib.Path) -> None:
    # `max()` over the per-path codes. This is also why an exit-code mutation cannot serve as a
    # control for the cases that assert stdout: it does not move what they read.
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({**OK, "kind": "bogus"}) + "\n")
    done = _run(str(tmp_path / "gone.jsonl"), str(bad))
    assert done.returncode == 2


def test_a_bad_record_before_an_unreadable_path_still_exits_2(tmp_path: pathlib.Path) -> None:
    # The other order. With only the unreadable-first case pinned, rewriting the aggregation to the
    # first non-zero code passes -- and which of 1 and 2 comes back is this branch's whole subject.
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({**OK, "kind": "bogus"}) + "\n")
    done = _run(str(bad), str(tmp_path / "gone.jsonl"))
    assert done.returncode == 2


def test_a_valid_inbox_still_passes(tmp_path: pathlib.Path) -> None:
    # The true positive beside the refusal: a guard that refused every invocation would ship green.
    done = _run(_inbox(tmp_path, OK))
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_malformed_record_still_fails_and_names_its_line(tmp_path: pathlib.Path) -> None:
    done = _run(_inbox(tmp_path, OK, {**OK, "kind": "rule-not-followed"}))
    assert done.returncode == 1
    assert ":2:" in done.stdout
