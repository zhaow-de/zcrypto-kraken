"""Spec 00082: the PostToolUse[Bash] git-mv guard.

The trap: `git mv` after an unstaged edit stages a rename of the INDEX version, leaving the edits
unstaged -- porcelain `RM`. Repo-side pre-commit structurally cannot see it (the framework stashes
unstaged changes before hooks run), so the moment the trap forms is the only place to catch it.

The test boundary is the committed script run as a subprocess with synthetic hook JSON on stdin.
The script reads the PROCESS cwd, not any `cwd` field in the JSON, so every case sets the
subprocess cwd to a scratch repo built in the state under test.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "git-mv-guard.sh"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "t@example.invalid")
    git(repo, "config", "user.name", "t")
    return repo


def run_hook(repo: Path, payload: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        cwd=repo,
    )


def hook_json(command: str) -> str:
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})


@pytest.fixture
def rm_state_repo(tmp_path: Path) -> Path:
    """A repo in the exact trap state: committed file, EDITED unstaged, then `git mv`.

    The fixture proves its own premise -- if porcelain does not actually report `RM`, every
    assertion built on it would be vacuous, so the state is asserted here rather than assumed.
    """
    repo = new_repo(tmp_path)
    (repo / "old.txt").write_text("original content\n")
    git(repo, "add", "old.txt")
    git(repo, "commit", "-qm", "init")
    (repo / "old.txt").write_text("EDITED content\n")  # the unstaged edit that springs the trap
    git(repo, "mv", "old.txt", "new.txt")
    assert git(repo, "status", "--porcelain").startswith("RM "), "fixture failed to construct the RM state"
    return repo


def test_hook_warns_on_rm_state_after_a_git_mv(rm_state_repo: Path):
    result = run_hook(rm_state_repo, hook_json("git mv old.txt new.txt"))
    assert result.returncode == 0  # a guard that breaks the Bash call is worse than the trap
    assert "WARNING" in result.stdout
    assert "new.txt" in result.stdout  # the operand of the fix must be named
    assert "git add" in result.stdout  # the fix itself
    assert "COMMITTED" in result.stdout  # verify against the committed tree, never the working tree


def test_hook_fires_on_a_git_mv_buried_in_a_compound_command(rm_state_repo: Path):
    # The hazard is the command CONTAINING `git mv`, not being exactly it -- a `&&` chain is the
    # common shape, and a guard that only matched a bare invocation would miss the real cases.
    result = run_hook(rm_state_repo, hook_json("mkdir -p docs && git mv old.txt new.txt && echo done"))
    assert result.returncode == 0
    assert "WARNING" in result.stdout


def test_hook_is_silent_for_a_command_without_git_mv(rm_state_repo: Path):
    # Same RM state -- so this pins the COMMAND filter, not an absent condition.
    result = run_hook(rm_state_repo, hook_json("git status"))
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_is_silent_for_a_clean_git_mv(tmp_path: Path):
    repo = new_repo(tmp_path)
    (repo / "old.txt").write_text("original content\n")
    git(repo, "add", "old.txt")
    git(repo, "commit", "-qm", "init")
    git(repo, "mv", "old.txt", "new.txt")  # no prior edit -> `R ` not `RM `
    assert git(repo, "status", "--porcelain").startswith("R  "), "fixture failed to construct the clean rename"
    result = run_hook(repo, hook_json("git mv old.txt new.txt"))
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


@pytest.mark.parametrize(
    "payload",
    [
        "",  # empty stdin
        "not json at all",
        "{",  # truncated object
        "[]",  # valid JSON, wrong shape
        '{"tool_input": {}}',  # right shape, no command key
    ],
)
def test_hook_never_breaks_the_bash_call_on_bad_input(rm_state_repo: Path, payload: str):
    # RM state present, so a hook that mis-parses into a truthy command would warn here.
    result = run_hook(rm_state_repo, payload)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_is_silent_outside_a_git_repo(tmp_path: Path):
    # PostToolUse[Bash] fires on every Bash call, including ones whose cwd is not a repo; a guard
    # that leaked git's "not a git repository" error into every such call would be noise.
    outside = tmp_path / "plain"
    outside.mkdir()
    result = run_hook(outside, hook_json("git mv a b"))
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_posttooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PostToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("git-mv-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"
