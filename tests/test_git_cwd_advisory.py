"""The PostToolUse[Bash] cwd advisory, driven with synthetic stdin over a scratch checkout and a linked
worktree of it: a `git` call that neither `-C`, `--git-dir`/`--work-tree`, a GIT_DIR in its environment nor
an absolute `cd` pins is reported -- the directory it answered about and the `-C` spelling that would have
pinned it -- as hook JSON on stdout with rc 0, and every other shape is silent.

Two things decide a case and both are written into every one: the command, and the pair (the cwd the call
ran in, CLAUDE_PROJECT_DIR) the hook compares checkouts across. The command corpus is
`.claude/hooks/bash-guard.sh`'s, read here only for whether git is the command word.
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
    """The systemMessage of a report, with rc and the additionalContext copy checked on the way through.

    Neither helper asserts on stderr: the hook silences its reader (`python3 -c "$prog" 2>/dev/null`), so no
    input a case can write reaches stderr and such an assertion could not fail. `assert result.stdout` here is
    what catches a reader that died -- which is why a shape whose expectation is silence is driven beside the
    nearest shape that must speak, and never alone.
    """
    assert result.returncode == 0
    assert result.stdout, "expected an advisory"
    out = json.loads(result.stdout)
    msg = out["systemMessage"]
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert msg in out["hookSpecificOutput"]["additionalContext"]
    return msg


def assert_silent(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0
    assert result.stdout == ""


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
        'x="$(git status)"',
        'echo "$(git rev-parse HEAD)"',
        "if git diff --quiet; then echo clean; fi",
        "for d in a b; do git status; done",
        "{ git status; }",
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
        "a_substitution_inside_a_double_quote",
        "a_substitution_inside_a_double_quoted_argument",
        "a_git_word_after_if",
        "a_git_word_in_a_for_body",
        "a_git_word_in_a_brace_group",
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


def test_a_literal_tab_in_a_quoted_argument_reaches_the_report_whole(checkouts):
    main, wt = checkouts
    msg = advised(run_hook('git commit -m "a\tb"', cwd=wt, project=main))
    assert "a\tb" in msg
    assert f"pin it: `git -C {wt} commit -m 'a\tb'`" in msg


def test_a_multi_line_command_reports_all_of_it_and_a_pin(checkouts):
    main, wt = checkouts
    # The shape every commit in this repository takes.
    msg = advised(run_hook('git commit -m "feat: x\n\nbody line"', cwd=wt, project=main))
    assert "body line" in msg.split("pin it:")[1]
    assert f"pin it: `git -C {wt} commit -m 'feat: x\n\nbody line'`" in msg


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


def test_a_popd_returns_the_call_to_where_the_command_started(checkouts):
    main, wt = checkouts
    msg = advised(run_hook("pushd sub && popd && git status", cwd=wt, project=main))
    assert f"ran in {wt}," in msg
    assert f"`git -C {wt} status`" in msg


@pytest.mark.parametrize(
    "command",
    [
        "if false; then cd sub; fi\ngit status",
        "while false; do cd sub; done\ngit status",
        "if true; then :; else cd sub; fi\ngit status",
        "if [ ! -d build ]; then pushd sub; fi\ngit status",
        "if [ ! -d build ]; then cd /tmp; fi\ngit status",
    ],
    ids=[
        "an_if_body",
        "a_loop_body",
        "an_else_branch",
        "a_pushd_in_an_if_body",
        "an_absolute_cd_in_an_if_body",
    ],
)
def test_a_cd_the_command_may_never_have_reached_silences_the_rest(checkouts, command: str):
    main, wt = checkouts
    # Every command here ends in the same bare `git status` the row below reports, and the only
    # difference is the keyword: the reader did not evaluate the condition and cannot, so naming
    # either directory would be a coin toss printed as an answer.
    assert_silent(run_hook(command, cwd=wt, project=main))


def test_the_same_cd_reached_by_no_branch_moves_the_directory(checkouts):
    main, wt = checkouts
    msg = advised(run_hook("cd sub\ngit status", cwd=wt, project=main))
    assert f"ran in {wt / 'sub'}," in msg


def test_a_brace_group_is_not_a_branch_and_its_cd_is_kept(checkouts):
    main, wt = checkouts
    # `{ ... }` runs in this shell and exactly once, which is why it is a keyword the walk steps over
    # but not one that makes the `cd` unplaceable.
    msg = advised(run_hook("{ cd sub; }\ngit status", cwd=wt, project=main))
    assert f"ran in {wt / 'sub'}," in msg


def test_a_cd_inside_a_subshell_does_not_outlive_it(checkouts):
    main, wt = checkouts
    msg = advised(run_hook("(cd docs && true) && git status", cwd=wt, project=main))
    assert f"ran in {wt}," in msg
    assert f"`git -C {wt} status`" in msg


def test_a_git_call_inside_the_subshell_answers_from_where_its_cd_moved(checkouts):
    main, wt = checkouts
    # The other direction of the same rule: inside the parentheses the `cd` is in force.
    msg = advised(run_hook("(cd sub && git status)", cwd=wt, project=main))
    assert f"ran in {wt / 'sub'}," in msg
    assert f"`git -C {wt / 'sub'} status`" in msg


def test_an_absolute_cd_inside_a_subshell_pins_only_that_subshell(checkouts):
    main, wt = checkouts
    # An absolute `cd` is read as a pin, and the pin is undone with the subshell that held it.
    msg = advised(run_hook("(cd /tmp && true) && git status", cwd=wt, project=main))
    assert f"ran in {wt}," in msg


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
        "echo '$(git status)'",
        "echo if git status",
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
        "a_substitution_inside_a_single_quote",
        "a_keyword_word_as_an_argument",
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
    if where == "wt":
        assert str(wt) in advised(result)
    else:
        assert_silent(result)


def test_a_repository_nested_under_the_project_directory_is_another_checkout(checkouts):
    main, _ = checkouts
    vendored = main / "vendored"
    vendored.mkdir()
    git(vendored, "init", "-q", "-b", "main")
    assert f"ran in {vendored}," in advised(run_hook("git status", cwd=vendored, project=main))


@pytest.mark.parametrize(
    "command",
    ["gh pr view 1", "gh pr create --fill", "gh pr merge --squash"],
    ids=["view", "create", "merge"],
)
def test_a_gh_call_is_outside_this_advisory_and_stays_silent(checkouts, command: str):
    main, wt = checkouts
    assert_silent(run_hook(command, cwd=wt, project=main))


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
