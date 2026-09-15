"""The PostToolUse[Bash] cwd advisory, driven with synthetic stdin over a scratch checkout and a linked
worktree of it: a `git` call that neither `-C`, `--git-dir`/`--work-tree`, a GIT_DIR in its environment nor
an absolute `cd` pins is reported -- the directory it answered about and the `-C` spelling that would have
pinned it -- as hook JSON on stdout with rc 0, and every other shape is silent.

Two things decide a case and both are pinned in every one of them: the command, and the pair (the cwd the
call ran in, CLAUDE_PROJECT_DIR) the hook compares checkouts across. The command corpus is the one
`.claude/hooks/bash-guard.sh` taught -- a wrapper, a path-spelled git, a git word inside a quoted word, a
git in a substitution, a git in a heredoc body -- read here for whether git is the command word rather than
for its flags.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "git-cwd-advisory.sh"


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True)


@pytest.fixture
def checkouts(tmp_path: Path) -> tuple[Path, Path]:
    """`main`, a checkout with a subdirectory, and `wt`, a linked worktree of it with one of its own."""
    main = tmp_path / "main"
    main.mkdir()
    git(main, "init", "-q", "-b", "main")
    git(main, "config", "user.email", "t@example.invalid")
    git(main, "config", "user.name", "t")
    (main / "docs").mkdir()
    (main / "docs" / "base.md").write_text("x\n")
    git(main, "add", "docs/base.md")
    git(main, "commit", "-qm", "base")
    wt = tmp_path / "wt"
    git(main, "worktree", "add", "-q", "-b", "topic", str(wt))
    (wt / "sub").mkdir()
    return main, wt


def run_hook(command: str, cwd: Path, project: Path | None) -> subprocess.CompletedProcess:
    """Run the hook over `command` as a call made in `cwd`, with `project` as CLAUDE_PROJECT_DIR; None
    leaves the variable unset."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PROJECT_DIR"}
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)})
    return subprocess.run(["bash", str(HOOK)], input=payload, capture_output=True, text=True, env=env)


def advised(result: subprocess.CompletedProcess) -> str:
    """The systemMessage of a report; rc, clean stderr and the additionalContext copy on the way through."""
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout, "expected an advisory"
    out = json.loads(result.stdout)
    msg = out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert msg in out["hookSpecificOutput"]["additionalContext"]
    return msg


def assert_silent(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_a_bare_git_from_another_checkout_names_the_directory_and_the_pin(checkouts):
    main, wt = checkouts
    msg = advised(run_hook("git status", cwd=wt, project=main))
    assert f"`git status` ran in {wt}" in msg
    assert f"`git -C {wt} status`" in msg


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "timeout 5 git status",
        "/usr/bin/git status",
        "sudo -u other git status",
        "GIT_EDITOR=true git status",
        "ls -la && git status",
        "git status | grep -c modified",
        "git status > /tmp/out",
        "git status 2>/dev/null",
        "(git status)",
        "x=$(git status)",
        "x=`git status`",
        "git -c color.ui=never status",
        "git --no-pager status",
        'git commit -m "run git -C /elsewhere status later"',
    ],
    ids=[
        "bare",
        "wrapper",
        "path_spelled",
        "wrapper_with_an_option_and_its_value",
        "env_prefix",
        "after_another_command",
        "piped",
        "redirected",
        "fd_redirect",
        "subshell",
        "substitution",
        "backticks",
        "value_taking_global_option",
        "valueless_global_option",
        "a_git_word_inside_the_message",
    ],
)
def test_every_shape_where_git_is_the_command_word_is_advised(checkouts, command: str):
    main, wt = checkouts
    assert str(wt) in advised(run_hook(command, cwd=wt, project=main))


def test_a_relative_cd_moves_where_the_call_answered_about_and_does_not_pin_it(checkouts):
    main, wt = checkouts
    # Relative, so it resolves against the same drifting cwd the bare call did: still cwd-dependent.
    msg = advised(run_hook("cd sub && git status", cwd=wt, project=main))
    assert f"ran in {wt / 'sub'}" in msg
    assert f"`git -C {wt / 'sub'} status`" in msg


def test_the_advisory_names_the_first_unpinned_call_of_a_compound_command(checkouts):
    main, wt = checkouts
    msg = advised(run_hook(f"git -C {main} log -1 && git status && git diff", cwd=wt, project=main))
    assert "`git status`" in msg
    assert "git log" not in msg and "git diff" not in msg


@pytest.mark.parametrize(
    "command",
    [
        "git -C {main} status",
        "git -C {wt} status",
        "git --git-dir={main}/.git --work-tree={main} status",
        "git --work-tree {main} status",
        "GIT_DIR={main}/.git git status",
        "cd {main} && git status",
        "cd ~/anywhere && git status",
        'cd "$SOMEWHERE" && git status',
        "git -c color.ui=never -C {main} status",
    ],
    ids=[
        "dash_C",
        "dash_C_to_the_same_directory",
        "git_dir_and_work_tree",
        "work_tree_spaced",
        "git_dir_in_the_environment",
        "absolute_cd",
        "tilde_cd",
        "cd_through_a_variable",
        "global_option_then_dash_C",
    ],
)
def test_a_command_that_pins_its_directory_is_silent(checkouts, command: str):
    main, wt = checkouts
    assert_silent(run_hook(command.format(main=main, wt=wt), cwd=wt, project=main))


def test_an_absolute_cd_into_another_checkout_pins_it(checkouts):
    main, wt = checkouts
    # From the project directory, so the resolved directory differs from it and only the `cd` being read as a
    # pin keeps the hook quiet: the rows above `cd` to the project's own checkout, where resolving the path
    # and honouring the pin reach the same silence and neither tells the other apart.
    assert_silent(run_hook(f"cd {wt} && git status", cwd=main, project=main))


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        'echo "git status"',
        "echo git status",
        'grep -rn "git status" docs/',
        "sh -c 'git status'",
        'bash -c "cd /elsewhere && git status"',
        "python3 - <<'PY'\nimport subprocess\nsubprocess.run(['git', 'status'])\nPY",
        "cat <<EOF\ngit status\nEOF",
        "git",
        "git --version",
        "git -v",
        "git help log",
    ],
    ids=[
        "no_git_at_all",
        "a_git_word_in_a_quoted_argument",
        "a_git_word_as_an_argument",
        "a_git_word_in_a_search_pattern",
        "a_string_handed_to_sh_c",
        "a_string_handed_to_bash_c",
        "a_python_heredoc",
        "a_heredoc_body",
        "git_alone",
        "version",
        "version_short",
        "help",
    ],
)
def test_a_command_that_invokes_no_cwd_dependent_git_is_silent(checkouts, command: str):
    main, wt = checkouts
    # Same cwd and the same project directory as the advised cases, so this pins the COMMAND reader.
    assert_silent(run_hook(command, cwd=wt, project=main))


@pytest.mark.parametrize(
    "where",
    ["main", "main/docs", "wt"],
    ids=["the_project_directory", "a_subdirectory_of_it", "another_checkout"],
)
def test_only_a_call_from_another_checkout_is_advised(checkouts, where: str):
    main, wt = checkouts
    cwd = wt if where == "wt" else main / "docs" if where.endswith("docs") else main
    result = run_hook("git status", cwd=cwd, project=main)
    # The subdirectory row is the reason the comparison is between checkouts and not between
    # directories: `cd docs && git status` answers about the project's own repository.
    if where == "wt":
        assert str(wt) in advised(result)
    else:
        assert_silent(result)


def test_with_no_project_directory_there_is_no_default_to_differ_from(checkouts):
    main, wt = checkouts
    assert_silent(run_hook("git status", cwd=wt, project=None))


def test_a_cwd_that_is_no_repository_is_silent(checkouts, tmp_path):
    main, _ = checkouts
    outside = tmp_path / "outside"
    outside.mkdir()
    assert_silent(run_hook("git status", cwd=outside, project=main))


def test_stdin_that_is_not_the_tool_calls_json_is_silent(checkouts):
    main, wt = checkouts
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(main)}
    result = subprocess.run(["bash", str(HOOK)], input="not json at all", capture_output=True, text=True, env=env, cwd=wt)
    assert_silent(result)


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_posttooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PostToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("git-cwd-advisory.sh" in c for c in commands), "the hook is inert unless settings.json wires it"
