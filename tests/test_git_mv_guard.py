"""Spec 00082: the PostToolUse[Bash] git-mv guard.

The trap: `git mv` after an unstaged edit stages a rename of the INDEX version, leaving the edits
unstaged -- porcelain `RM`. Repo-side pre-commit structurally cannot see it (the framework stashes
unstaged changes before hooks run), so the moment the trap forms is the only place to catch it.

The test boundary is the committed script run as a subprocess with synthetic hook JSON on stdin.
The script judges the repo the command NAMES -- `git -C <dir>` or a leading `cd <dir> &&` -- and
falls back to the PROCESS cwd only when the command names none (it never reads a `cwd` field in
the JSON), so a case pins both the subprocess cwd and the directory written into the command.
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


def init_repo(path: Path) -> Path:
    git(path, "init", "-q")
    git(path, "config", "user.email", "t@example.invalid")
    git(path, "config", "user.name", "t")
    return path


def new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    return init_repo(repo)


def run_hook(payload: dict | str, cwd: Path) -> subprocess.CompletedProcess:
    """Run the hook with `cwd` as the PROCESS cwd; dicts are JSON-encoded, strings pass through
    verbatim so the malformed-input cases can hand the hook something that is not JSON."""
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def hook_payload(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def make_rm_state_repo(path: Path) -> Path:
    """Put `path` into the exact trap state: committed file, EDITED unstaged, then `git mv`.

    Proves its own premise -- if porcelain does not actually report `RM`, every assertion built
    on it would be vacuous, so the state is asserted here rather than assumed.
    """
    init_repo(path)
    (path / "old.txt").write_text("original content\n")
    git(path, "add", "old.txt")
    git(path, "commit", "-qm", "init")
    (path / "old.txt").write_text("EDITED content\n")  # the unstaged edit that springs the trap
    git(path, "mv", "old.txt", "new.txt")
    assert git(path, "status", "--porcelain").startswith("RM "), "fixture failed to construct the RM state"
    return path


@pytest.fixture
def rm_state_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "scratch"
    repo.mkdir()
    return make_rm_state_repo(repo)


def test_hook_warns_on_rm_state_after_a_git_mv(rm_state_repo: Path):
    result = run_hook(hook_payload("git mv old.txt new.txt"), cwd=rm_state_repo)
    # stderr + rc 2 is the ONLY channel a PostToolUse hook reaches the model on: plain stdout with
    # exit 0 is transcript-only, so the agent that just ran `git mv` would never read the warning --
    # a guard nobody receives. On PostToolUse exit 2 cannot block the already-run command, which is
    # what keeps this warn-only.
    assert result.returncode == 2
    assert "WARNING" in result.stderr
    assert "new.txt" in result.stderr  # the operand of the fix must be named
    assert "git add" in result.stderr  # the fix itself
    assert "COMMITTED" in result.stderr  # verify against the committed tree, never the working tree


def test_hook_fires_on_a_git_mv_buried_in_a_compound_command(rm_state_repo: Path):
    # The hazard is the command CONTAINING `git mv`, not being exactly it -- a `&&` chain is the
    # common shape, and a guard that only matched a bare invocation would miss the real cases.
    result = run_hook(hook_payload("mkdir -p docs && git mv old.txt new.txt && echo done"), cwd=rm_state_repo)
    assert result.returncode == 2
    assert "WARNING" in result.stderr


def test_hook_is_silent_for_a_command_without_git_mv(rm_state_repo: Path):
    # Same RM state -- so this pins the COMMAND filter, not an absent condition.
    result = run_hook(hook_payload("git status"), cwd=rm_state_repo)
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
    result = run_hook(hook_payload("git mv old.txt new.txt"), cwd=repo)
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
    result = run_hook(payload, cwd=rm_state_repo)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_hook_is_silent_outside_a_git_repo(tmp_path: Path):
    # PostToolUse[Bash] fires on every Bash call, including ones whose cwd is not a repo; a guard
    # that leaked git's "not a git repository" error into every such call would be noise.
    outside = tmp_path / "plain"
    outside.mkdir()
    result = run_hook(hook_payload("git mv a b"), cwd=outside)
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_dash_c_form_warns_against_the_named_repo(tmp_path):
    """RM state lives in a DIFFERENT directory than the hook's cwd — `git -C <dir> mv` must be
    judged against <dir>, not the process cwd."""
    other = tmp_path / "other-repo"
    other.mkdir()
    make_rm_state_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    r = run_hook({"tool_input": {"command": f"git -C {other} mv old.txt new.txt"}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "new.txt" in r.stderr


def test_cd_prefix_form_warns_against_the_named_repo(tmp_path):
    other = tmp_path / "other-repo"
    other.mkdir()
    make_rm_state_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    r = run_hook({"tool_input": {"command": f"cd {other} && git mv old.txt new.txt"}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "new.txt" in r.stderr


def test_unspaced_cd_separator_form_warns_against_the_named_repo(tmp_path):
    """`cd <dir>;git mv` -- no space before the separator, which a shell accepts and people write.

    A dir class of "any non-space" swallows the `;` into the path, so the guard resolves a
    directory that does not exist and falls silent: a MISSED warning, not a wrong one.
    """
    other = tmp_path / "other-repo"
    other.mkdir()
    make_rm_state_repo(other)
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    r = run_hook({"tool_input": {"command": f"cd {other};git mv old.txt new.txt"}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "new.txt" in r.stderr


def test_unresolvable_dir_notes_instead_of_wrong_repo(tmp_path):
    clean_cwd = tmp_path / "clean"
    clean_cwd.mkdir()
    make_rm_state_repo(clean_cwd)  # RM state in the PROCESS cwd — the note must NOT warn from it
    r = run_hook({"tool_input": {"command": 'git -C "$WORKDIR" mv old.txt new.txt'}}, cwd=clean_cwd)
    assert r.returncode == 2
    assert "could not" in r.stderr.lower()
    assert "old.txt" not in r.stderr  # no porcelain from the wrong repo


def test_dash_c_to_a_non_repo_stays_silent(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    r = run_hook({"tool_input": {"command": f"git -C {empty} mv a b"}}, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stderr == "" and r.stdout == ""


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_posttooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PostToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("git-mv-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"
