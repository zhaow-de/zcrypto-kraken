"""The PreToolUse[Bash] guard over the git hook bypasses, driven with synthetic stdin JSON.

The hook is `.claude/hooks/bash-guard.sh`; its header states what the arm refuses and what it leaves. Every family
is driven in both directions: the spelling the arm refuses (exit 2, `BLOCKED` and the spelling on stderr) beside the
ordinary shape nearest to it that it must admit (exit 0, silent) -- the flag as message text, in a heredoc body, in a
comment, after `--`, or on a subcommand where it means something else.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "bash-guard.sh"

HEREDOC_MESSAGE = (
    "$(cat <<'EOF'\nclaude(settings): --no-verify and -n are refused\n\n-n in a bundle too, and \"--no-verify\" quoted\nEOF\n)"
)

# (command, the spelling the message must name)
REFUSED = [
    # commit: the flag in any position, an abbreviation, a bundle
    ("git commit --no-verify", "--no-verify"),
    ("git commit -m msg --no-verify", "--no-verify"),
    ("git commit --amend --no-verify", "--no-verify"),
    ("git commit --no-veri -am msg", "--no-veri"),
    ("git commit --no-v -m msg", "--no-v"),  # ambiguous to git; refused all the same
    ("git commit -n", "-n"),
    ("git commit -n -m msg", "-n"),
    ("git commit -nm msg", "-nm"),
    ("git commit -an -m msg", "-an"),
    ("git commit -qn -m msg", "-qn"),
    ("git commit -anm msg", "-anm"),
    ("git commit -am msg -n", "-n"),
    # an option before the subcommand, a path to git, an env prefix, a wrapper
    ("git -C /repo commit --no-verify -m msg", "--no-verify"),
    ("git -C /repo commit -n -m msg", "-n"),
    ('git -C "$WORKDIR" commit -n -m msg', "-n"),
    ("git --git-dir=.git --work-tree=. commit --no-verify", "--no-verify"),
    ("git --git-dir .git commit -n", "-n"),
    ("git --no-pager -c color.ui=never commit -n", "-n"),
    ("/usr/bin/git commit --no-verify", "--no-verify"),
    ("GIT_EDITOR=true git commit --no-verify", "--no-verify"),
    ("sudo git commit -n", "-n"),
    ("PATH=/opt/git git commit -n", "-n"),
    ("GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x timeout 5 git commit -m x", "GIT_CONFIG_KEY_0"),
    ("GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/x'\" setsid git commit -m x", "GIT_CONFIG_PARAMETERS"),
    ("nice env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m x", "GIT_CONFIG_KEY_0"),
    ("git commit -m x $'\\x2dn'", "-n"),
    ("git commit -m x $'\\055n'", "-n"),
    ("git commit -n && (echo x)# don't", "-n"),
    ("git commit -m $(date)#x -n", "-n"),
    ("git add . && git commit -m $(date)#msg --no-verify", "--no-verify"),
    ("echo $(date)#c; git commit -n", "-n"),
    ("git commit -m <(date)#x -n", "-n"),
    ("git commit -m <(date)#x --no-verify", "--no-verify"),
    ("echo >(true)#c; git commit --no-verify", "--no-verify"),
    ("cat <(git commit -n)", "-n"),
    # a compound command, a redirect, a heredoc message beside the flag
    ("cd /repo && git commit --no-verify -m msg", "--no-verify"),
    ("git add . ; git commit -n -m msg", "-n"),
    ("git add x\ngit commit -n -m x", "-n"),
    ("git commit -m msg --no-verify >/dev/null 2>&1", "--no-verify"),
    (f'git commit -m "{HEREDOC_MESSAGE}" --no-verify', "--no-verify"),
    (f'git commit --no-verify -m "{HEREDOC_MESSAGE}"', "--no-verify"),
    # an unquoted # inside a word is text to bash, not a comment
    ("git commit -m issue#42 -n", "-n"),
    ("git commit -m fix#123 --no-verify", "--no-verify"),
    ("echo a#b; git commit -n", "-n"),
    ("cd /repo#1 && git commit -n", "-n"),
    ("git -C /repo commit -m x#y -n", "-n"),
    # an ANSI-C quoted message beside the flag
    ("git commit --amend -n -m $'it\\'s'", "-n"),
    ("git -C . commit -n -m $'don\\'t'", "-n"),
    ("git commit --no-veri -m $'don\\'t'", "--no-veri"),
    # a command substitution: $( .. ) and backticks, bare, assigned, double-quoted, inside a heredoc bash expands
    ("x=$(git commit -n)", "-n"),
    ('echo "$(git commit -n)"', "-n"),
    ("x=`git commit -n`", "-n"),
    ("`git commit --no-verify`", "--no-verify"),
    ('echo "`git commit -n`"', "-n"),
    ("cat <<EOF\n$(git commit -n)\nEOF", "-n"),
    ("cat <<EOF\n`git commit --no-verify`\nEOF", "--no-verify"),
    # merge, rebase, am; -n is --no-verify on am
    ("git merge --no-verify feature", "--no-verify"),
    ("git merge --no-veri feature", "--no-veri"),
    ("git rebase --no-verify main", "--no-verify"),
    ("git am --no-verify < patch", "--no-verify"),
    ("git am -n", "-n"),
    ("git am -n patch.mbox", "-n"),
    ("git am -3n patch.mbox", "-3n"),
    ("git -C /repo merge --no-verify feature", "--no-verify"),
    # core.hooksPath on the command line, in the environment, through config
    ("git -c core.hooksPath=/dev/null commit -m msg", "core.hooksPath"),
    ("git -c core.hookspath=/dev/null log -1", "core.hookspath"),
    ("git -C /repo -c core.hooksPath=/dev/null commit -m msg", "core.hooksPath"),
    ("git --config-env=core.hooksPath=HP commit -m msg", "core.hooksPath"),
    ("git --config-env core.hooksPath=HP commit -m msg", "core.hooksPath"),
    ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit -m msg", "GIT_CONFIG_KEY_0"),
    ("export GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/dev/null'\"; git commit -m msg", "GIT_CONFIG_PARAMETERS"),
    ("env GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x git commit -m msg", "GIT_CONFIG_KEY_0"),
    ("sudo GIT_CONFIG_PARAMETERS=\"'core.hooksPath=/x'\" git commit -m msg", "GIT_CONFIG_PARAMETERS"),
    ("git config core.hooksPath /dev/null", "core.hooksPath"),
    ("git config --local core.hooksPath /tmp/none", "core.hooksPath"),
    ("git config --global core.hooksPath /x", "core.hooksPath"),
    ("git config --worktree core.hooksPath /x", "core.hooksPath"),
    ("git config --file .git/config core.hooksPath /x", "core.hooksPath"),
    ("git config -f .git/config core.hooksPath /x", "core.hooksPath"),
    ("git config --add core.hooksPath /x", "core.hooksPath"),
    ("git config --replace-all core.hooksPath /x", "core.hooksPath"),
    ("git config set core.hooksPath /x", "core.hooksPath"),
    ("git config set --local core.hooksPath /x", "core.hooksPath"),
    ("git config core.HooksPath /x", "core.HooksPath"),
    ("git config core.hooksPath ''", "core.hooksPath"),
    ("git -C /repo config core.hooksPath /x", "core.hooksPath"),
]

ADMITTED = [
    # commit without the flag; the flag as message text, in a heredoc, in a comment, after --
    "git commit -m msg",
    "git commit -am msg",
    "git commit --amend -m msg",
    "git commit -a -q -m msg",
    'git commit -m "docs: never --no-verify"',
    'git commit -m "chore: drop the -n door"',
    "git commit -m 'refuse -n and --no-verify'",
    f'git commit -m "{HEREDOC_MESSAGE}"',
    "git commit -F .tmp/msg.txt",
    "git commit -m -n",  # the message is `-n`
    "git commit -am -n",
    "git commit --message -n",
    "git commit -m msg -- -n",
    "git commit -m msg # not --no-verify",
    'git commit -m "a#b"',
    "git commit -m $'it\\'s -n'",  # the flag inside an ANSI-C quoted value
    "git commit -m $'plain' -m more",
    "git commit -m $'a\\tb\\x21'",
    "(echo hi)# git commit -n",
    "echo $(date)#c; git status",
    "echo >(true)#c; git status",
    'echo "<(git commit -n)"',
    "echo GIT_CONFIG_KEY_0=core.hooksPath",
    "git commit -uno -m msg",  # -u<mode>: `no` is the mode, not a bundle carrying n
    "git commit --no-status -m msg",
    "git commit -m msg && git push",
    'git commit -m "a && git commit -n"',
    "git commit -m 'see `git commit -n`'",
    'git commit -m "see \\`git commit -n\\`"',  # an escaped backtick is text
    "cat <<'EOF'\n$(git commit -n)\nEOF",  # a quoted delimiter expands nothing
    'echo "$(git rev-parse HEAD)"',
    # -n and --no-verify where they mean something else, and outside git
    "git merge -n feature",
    "git rebase -n main",
    "git am -3 patch.mbox",
    "git log --oneline -n 5",
    "git grep -n -- no-verify",
    "git push --no-verify",
    "sed -n 1,5p file",
    "ls -n",
    "grep -rn -- --no-verify docs/",
    'echo "git commit -n"',
    "cat <<'EOF' > notes.txt\ngit commit --no-verify\nEOF",
    "uv run pytest tests/test_bash_guard.py -k no_verify",
    # core.hooksPath read or unset, and other keys set
    "git config --get core.hooksPath",
    "git config core.hooksPath",
    "git config --unset core.hooksPath",
    "git config --unset-all core.hooksPath",
    "git config --get-all core.hooksPath",
    "git config --local --get core.hooksPath",
    "git config get core.hooksPath",
    "git config unset core.hooksPath",
    "git config --list",
    "git config user.name x",
    "git config --local user.email x@example.invalid",
    "git -c color.ui=never log -1",
    "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.name GIT_CONFIG_VALUE_0=t git commit -m msg",
    # an assignment-shaped word where git never sees it: a search, a note, a bare assignment
    "grep -rn 'GIT_CONFIG_KEY_0=core.hooksPath' docs/",
    "rg -n 'GIT_CONFIG_PARAMETERS=.*core.hooksPath' .",
    "echo \"GIT_CONFIG_PARAMETERS='core.hooksPath=/dev/null' is the env door\" >> notes.md",
    "GIT_CONFIG_KEY_0=core.hooksPath; git commit -m msg",
    "git -C /repo status",
    "git status",
    "which git",
    "git --version",
]


def run_hook(payload: dict | str, cwd: Path) -> subprocess.CompletedProcess:
    """Dicts are JSON-encoded; strings pass through verbatim so the malformed-input cases can hand the hook
    something that is not JSON."""
    return subprocess.run(
        ["bash", str(HOOK)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
    )


def call(command: str) -> dict:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


@pytest.mark.parametrize(("command", "spelling"), REFUSED, ids=[c for c, _ in REFUSED])
def test_a_hook_bypass_is_refused_and_the_message_names_it(tmp_path: Path, command: str, spelling: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 2, r.stderr
    assert "BLOCKED" in r.stderr
    # Where the message names the spelling: a flag as a word of the first backtick pair (`git <sub> <tok>`), never the
    # later echo of the whole command; a key or a variable before " sets ".
    named = r.stderr.partition("`")[2].partition("`")[0]
    if spelling.startswith("-"):
        assert spelling in named.split(), r.stderr
    else:
        assert spelling in r.stderr.partition(" sets ")[0], r.stderr
    assert "hooks" in r.stderr  # what the spelling bypasses
    assert r.stdout == ""


@pytest.mark.parametrize("command", ADMITTED)
def test_an_ordinary_command_is_admitted_silently(tmp_path: Path, command: str):
    r = run_hook(call(command), cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert r.stdout == ""
    assert r.stderr == ""


@pytest.mark.parametrize("payload", ["", "not json at all", "{", "[]", '{"tool_input": "x"}'])
def test_stdin_that_is_not_the_call_admits_with_a_note(tmp_path: Path, payload: str):
    r = run_hook(payload, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == ""
    assert "bash-guard: NOTE" in r.stderr
    assert "unjudged" in r.stderr


def test_a_call_with_no_command_is_admitted_silently(tmp_path: Path):
    r = run_hook({"tool_name": "Bash", "tool_input": {}}, cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout == "" and r.stderr == ""


def test_a_command_that_does_not_tokenise_admits_with_a_note(tmp_path: Path):
    # An unbalanced quote fails in the shell too; the hook's own parse failure is never a block.
    r = run_hook(call('git commit -n -m "unterminated'), cwd=tmp_path)
    assert r.returncode == 0
    assert "bash-guard: NOTE" in r.stderr


def test_hook_is_executable():
    assert HOOK.stat().st_mode & 0o111, "the hook must be executable -- settings.json invokes it directly"


def test_hook_is_wired_as_a_pretooluse_bash_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text())
    commands = [
        hook["command"] for entry in settings["hooks"]["PreToolUse"] if entry["matcher"] == "Bash" for hook in entry["hooks"]
    ]
    assert any("bash-guard.sh" in c for c in commands), "the hook is inert unless settings.json wires it"
