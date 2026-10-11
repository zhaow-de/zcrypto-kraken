"""The read-guard over `.local/memo.md`, driven with synthetic stdin JSON on a scratch memo -- never
the real one -- with TMPDIR pointed at the scratch directory so the read-stamp lands there too."""

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "memo-guard.sh"


@pytest.fixture
def memo(tmp_path: Path) -> Path:
    local = tmp_path / ".local"
    local.mkdir()
    return local / "memo.md"


@pytest.fixture
def hook(tmp_path: Path):
    def run(mode: str, payload: dict | str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(HOOK), mode],
            input=payload if isinstance(payload, str) else json.dumps(payload),
            capture_output=True,
            text=True,
            env={**os.environ, "TMPDIR": str(tmp_path)},
        )

    return run


def call(tool: str, path: Path) -> dict:
    return {"tool_name": tool, "tool_input": {"file_path": str(path)}}


def test_a_write_of_the_existing_memo_is_refused_even_after_a_fresh_read(hook, memo: Path):
    memo.write_text("# memo\n")
    hook("post-read", call("Read", memo))
    r = hook("pre-write", call("Write", memo))
    assert r.returncode == 2
    assert "BLOCKED" in r.stderr
    assert "use Edit" in r.stderr


def test_an_edit_after_a_fresh_read_is_admitted(hook, memo: Path):
    memo.write_text("# memo\n")
    hook("post-read", call("Read", memo))
    r = hook("pre-write", call("Edit", memo))
    assert r.returncode == 0
    assert r.stderr == ""


def test_an_edit_without_a_fresh_read_is_refused(hook, memo: Path):
    memo.write_text("# memo\n")
    r = hook("pre-write", call("Edit", memo))
    assert r.returncode == 2
    assert "Read" in r.stderr


def test_a_write_invalidates_the_read_so_the_next_edit_needs_another(hook, memo: Path):
    memo.write_text("# memo\n")
    hook("post-read", call("Read", memo))
    assert hook("pre-write", call("Edit", memo)).returncode == 0
    landed = hook("post-write", call("Edit", memo))
    assert landed.returncode == 0
    assert "additionalContext" in landed.stdout
    assert hook("pre-write", call("Edit", memo)).returncode == 2


def test_a_hand_edit_after_the_read_stales_the_stamp(hook, memo: Path):
    # The stamp is the content hash, not a time: a file changed outside the session since the read
    # is refused exactly like one never read.
    memo.write_text("# memo\n")
    hook("post-read", call("Read", memo))
    memo.write_text("# memo\n- a line the user typed\n")
    assert hook("pre-write", call("Edit", memo)).returncode == 2


def test_the_write_that_creates_an_absent_memo_is_admitted(hook, memo: Path):
    assert not memo.exists()
    r = hook("pre-write", call("Write", memo))
    assert r.returncode == 0
    assert r.stderr == ""


def test_a_path_other_than_the_memo_is_ignored(hook, tmp_path: Path):
    other = tmp_path / "notes.md"
    other.write_text("x\n")
    r = hook("pre-write", call("Write", other))
    assert r.returncode == 0
    assert r.stderr == ""


@pytest.mark.parametrize("payload", ["", "not json at all", "{", "[]", '{"tool_input": {}}'])
def test_unreadable_input_never_blocks(hook, payload: str):
    # Exit 2 is the one code that blocks the tool call; a hook that blocked on input it cannot read
    # would refuse every Edit and Write in the session, the memo's included.
    assert hook("pre-write", payload).returncode != 2


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111


def test_hook_is_wired_pre_write_on_edit_and_write():
    # The Write arm reads `tool_name` off stdin; it is only there because the matcher admits both tools.
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PreToolUse"] if entry["matcher"] == "Edit|Write" for hook in entry["hooks"]
    ]
    assert any("memo-guard.sh pre-write" in c for c in commands)


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("received 12:1xZ (the owner's read)", "12:1x"),
        ("at 08:5xZ", "08:5x"),
        ("about 03:0x", "03:0x"),
        ("at 12:xxZ", "12:xx"),
        ("at 1x:30Z", "1x:30"),
        ("at 12:3X", "12:3X"),
        ("at 12:3?Z", "12:3?"),
        ("at 2026-10-11T12:3xZ", "12:3x"),
        ("at ?2:30Z", "?2:30"),
        ("at ??:??Z", "??:??"),
    ],
)
def test_a_placeholder_stamp_is_refused_in_any_edit(hook, tmp_path: Path, text: str, named: str):
    other = tmp_path / "ledger.md"
    other.write_text("- a line\n")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(other), "new_string": text}}
    r = hook("pre-write", payload)
    assert r.returncode == 2 and "placeholder stamp" in r.stderr and f"'{named}'" in r.stderr


@pytest.mark.parametrize(
    "text", ["received 12:15Z", "the fetch at 13:18:04Z", "0x1F and 2026-10-11T12:02:30Z", "slice buf[16:0x20]"]
)
def test_a_stamp_pasted_from_the_clock_is_admitted(hook, tmp_path: Path, text: str):
    other = tmp_path / "ledger.md"
    other.write_text("- a line\n")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(other), "new_string": text}}
    assert hook("pre-write", payload).returncode == 0


def test_a_placeholder_in_a_directory_merely_named_tests_is_refused(hook, tmp_path: Path):
    target = tmp_path / "data" / "tests" / "notes.md"
    target.parent.mkdir(parents=True)
    target.write_text("x\n")
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target), "new_string": "received 12:1xZ"}}
    assert hook("pre-write", payload).returncode == 2


def test_a_placeholder_in_a_test_file_or_a_hook_is_admitted(hook, tmp_path: Path):
    for rel in ("tests/test_memo_guard.py", "tests/conftest.py", ".claude/hooks/memo-guard.sh"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n")
        payload = {"tool_name": "Edit", "tool_input": {"file_path": str(target), "new_string": "a case: 12:1xZ"}}
        assert hook("pre-write", payload).returncode == 0
