#!/usr/bin/env bash
# PostToolUse[Bash] advisory: after a command that invokes `git` as a shell command with nothing
# pinning its directory -- no `-C`, no `--git-dir`/`--work-tree`, no GIT_DIR in its environment, no
# absolute `cd` before it -- REPORT which checkout the call answered about and the `-C` spelling that
# would have said so. It refuses nothing: a PostToolUse hook sees a command that has already run, and
# the trap is not the command but the reader's belief about it -- the Bash tool's cwd drifts between
# calls, a worktree on one and the main checkout on the next, so a bare `git status` answers about
# whichever happens to be current and reads as an answer about the one the reader had in mind.
# WHERE it ran is the tool call's own `cwd` field, the directory the command was given; the hook
# process's cwd is the fallback and is not always that directory.
# It fires only where the belief can be wrong: where the call resolves to a DIFFERENT checkout from
# $CLAUDE_PROJECT_DIR's. A call from the project directory or any subdirectory of it has one possible
# answer; advising there speaks on every bare git a session runs, and an advisory that speaks that
# often is trained away. With CLAUDE_PROJECT_DIR unset there is no default to differ from, and the
# hook is silent rather than guessing one. A repository NESTED under the project directory resolves
# to its own toplevel and is advised: a bare git there answers about the nested checkout, which is
# the belief this exists to correct, whatever the path prefix suggests.
# Which command shapes count as a git call at all, and which stay silent, is driven shape by shape in
# `tests/test_git_cwd_advisory.py`.
# `gh` is outside this hook by decision, not by oversight: `gh pr create`, `gh pr merge` and `gh pr
# view` lean on the cwd's repository the same way, but gh has no `-C`, and its `-R owner/repo` names
# the remote -- which a checkout and a linked worktree of it SHARE. There is no gh spelling that pins
# the directory, so there is nothing this advisory could hand a reader.
# The judgement is one python3 program that prints the finished hook JSON or nothing, so no field
# crosses back into the shell and no byte a command can hold -- a tab, a newline -- can be re-read as
# a separator. `set -e` is deliberately absent and the last statement is `exit 0`: a PostToolUse arm
# that exits non-zero reports a failure against a Bash call it was never meant to judge. The price is
# that the reader's own stderr is discarded, so a bug in it is silence -- which the cases expecting an
# advisory catch and the ones expecting silence cannot tell from a correct answer, and is why every
# silent shape is driven beside the nearest shape that must speak.
set -uo pipefail
prog="$(cat <<'PY'
import json
import os
import re
import shlex
import subprocess
import sys

ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
DURATION = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
HEREDOC = re.compile(r"<<(-?)\s*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([\w./-]+))")
WRAPPERS = {"sudo", "doas", "env", "timeout", "nice", "ionice", "stdbuf", "setsid", "nohup", "command", "time"}
# The shell words that can stand immediately BEFORE a command word inside one simple command, and so
# would otherwise be read as one: `if git diff --quiet; then`, `do git status`, `{ git status; }`.
# `for`, `select`, `case`, `[[` and `function` are deliberately outside the set: what follows those is
# a variable name or a word list, never a command word, so skipping one would attribute a git call to
# the wrong command -- `for f in git log` invokes no git, and that, not the word `in`, is what keeps
# it silent.
KEYWORDS = {"if", "elif", "while", "until", "then", "else", "do", "{", "!"}
# Of those, the ones that head a condition or a body which may run no times, or many: a command word
# reached past one of them may never have been reached at all. `{` and `!` neither branch nor loop --
# what follows them runs, in this shell, exactly once -- so they are not in here. The distinction
# decides nothing for a git call (the hook judges a command that has already run) and everything for a
# `cd`, whose effect on the next call depends on whether the branch was taken.
BRANCHING = KEYWORDS - {"{", "!"}
PIN_ENV = {"GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR"}
PIN_OPT = {"-C", "--git-dir", "--work-tree"}
GLOBAL_VALUE = {"-c", "--config-env", "--namespace", "--super-prefix", "--attr-source", "--exec-path"}
TERMINAL = {"-v", "--version", "-h", "--help", "--exec-path", "--html-path", "--man-path", "--info-path", "--list-cmds"}
CWD_FREE = {"help", "version"}
BREAK = " \t\n;&|()"


def cut_heredocs(text):
    # A heredoc body is data, not commands: `python3 - <<'PY' ... git ... PY` invokes no git. Line by
    # line, since the delimiter is what ends a body and a `<<` inside a quote is rare enough to spend
    # no scanner on.
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            delim, dash = m.group(2) or m.group(3) or m.group(4), bool(m.group(1))
            while i < len(lines):
                cur = lines[i].lstrip("\t") if dash else lines[i]
                i += 1
                if cur == delim:
                    break
    return "\n".join(out)


def simple_commands(text):
    # Words, not text: a `git` inside a quoted word is an argument and never a command word, and a
    # `$( .. )`, backtick or `( .. )` body is a command of its own -- bash runs it in the same cwd, so
    # a bare git there is as unpinned as one outside, and the `$(` test runs ahead of the
    # enclosing-quote branch, so a substitution inside a double quote is opened too. A redirect and
    # its target are dropped. Each command is returned with the nesting depth it was read at, which is
    # what lets `read()` undo a `cd` the subshell it stood in did not outlive.
    cmds, word, started, stack, i, n = [[0, []]], [], False, [["top", None]], 0, len(text)

    def flush():
        nonlocal word, started
        if started:
            if not cmds[-1][1]:
                cmds[-1][0] = len(stack)
            cmds[-1][1].append("".join(word))
        word, started = [], False

    def sep():
        flush()
        if cmds[-1][1]:
            cmds.append([0, []])

    while i < n:
        ch, quote = text[i], stack[-1][1]
        if quote == "'":
            if ch == "'":
                stack[-1][1] = None
            else:
                word.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            if text[i + 1] != "\n":
                word.append(text[i + 1])
                started = True
            i += 2
            continue
        if text.startswith("$(", i):
            stack.append(["sub", None])
            sep()
            i += 2
            continue
        if ch == "`":
            if stack[-1][0] == "bq":
                stack.pop()
            else:
                stack.append(["bq", None])
            sep()
            i += 1
            continue
        if ch == "(":
            stack.append(["paren", None])
            sep()
            i += 1
            continue
        if ch == ")":
            if stack[-1][0] in ("sub", "paren"):
                stack.pop()
            sep()
            i += 1
            continue
        if quote == '"':
            if ch == '"':
                stack[-1][1] = None
            else:
                word.append(ch)
                started = True
            i += 1
            continue
        if ch in "'\"":
            stack[-1][1] = ch
            started = True
            i += 1
            continue
        if ch in " \t\r":
            flush()
            i += 1
            continue
        if ch in "\n;":
            sep()
            i += 1
            continue
        if ch in "|&":
            sep()
            i += 2 if text[i : i + 2] in ("&&", "||") else 1
            continue
        if ch == "#" and not started and (i == 0 or text[i - 1] in BREAK):
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        if ch in "<>":
            if started and all(c.isdigit() for c in word):
                word, started = [], False  # a file descriptor prefix is part of the redirect, not a word
            flush()
            while i < n and text[i] in "<>&":
                i += 1
            while i < n and text[i] in " \t":
                i += 1
            while i < n and text[i] not in BREAK:
                i += 1
            continue
        word.append(ch)
        started = True
        i += 1
    flush()
    return [(level, c) for level, c in cmds if c]


def is_git(w):
    return w == "git" or ("/" in w and w.rpartition("/")[2] == "git")


def head(words):
    """Where the command word is, after the shell keywords, the assignments and the wrappers; whether
    git's directory is already pinned in the environment; and whether a BRANCHING keyword was stepped
    over on the way, which decides nothing for a git call and everything for a `cd`."""
    i, pinned, branched = 0, False, False
    while i < len(words):
        if words[i] in KEYWORDS:
            branched = branched or words[i] in BRANCHING
            i += 1
            continue
        m = ASSIGN.match(words[i])
        if m:
            pinned = pinned or m.group(1) in PIN_ENV
            i += 1
            continue
        if words[i].rpartition("/")[2] in WRAPPERS:
            i += 1
            while i < len(words) and (words[i].startswith("-") or DURATION.match(words[i])):
                # A two-letter short option is read as taking the next token, so `sudo -u <user>` and
                # `timeout -s <signal>` do not end the walk on their own value. Over-skipping here can
                # only lose an advisory, never invent one -- what follows is then no git word.
                short = len(words[i]) == 2 and words[i].startswith("-") and words[i][1] != "-"
                i += 2 if short else 1
            continue
        break
    return i, pinned, branched


def git_call(words):
    """The argv of an unpinned git invocation whose answer depends on the cwd, or None."""
    i, pinned, _ = head(words)
    if pinned or i >= len(words) or not is_git(words[i]):
        return None
    argv, j = words[i:], 1
    while j < len(argv) and argv[j].startswith("-") and len(argv[j]) > 1:
        name, eq, _ = argv[j].partition("=")
        if name in TERMINAL and not eq:
            return None
        if name in PIN_OPT:
            return None
        if name in GLOBAL_VALUE:
            j += 1 if eq else 2
            continue
        j += 1
    if j >= len(argv) or argv[j] in CWD_FREE:
        return None
    return argv


def cd_target(words):
    """Where a leading `cd` or `pushd` moves to and which verb moved there, or ("", "") for anything
    else; `popd` names its verb and no target, since what it moves to is on the stack. A verb reached
    only past a BRANCHING keyword is ("", "?"), a directory change this reader cannot place: `then cd
    sub` is one branch of a condition it did not evaluate and has no way to."""
    i, _, branched = head(words)
    if i >= len(words):
        return "", ""
    verb = words[i].rpartition("/")[2]
    if verb not in ("cd", "pushd", "popd"):
        return "", ""
    if branched:
        return "", "?"
    if verb == "popd":
        return "", "popd"
    return next((w for w in words[i + 1 :] if not w.startswith("-")), "~"), verb


def read(command, cwd):
    # A `cd` to an absolute path, or to one this reader cannot resolve, is the author pinning the
    # directory by another spelling and silences the rest of the command; a relative one leaves the
    # answer as cwd-dependent as it was and only moves where it points. `pushd` saves what it leaves
    # and `popd` restores it, because a git call after the pop ran where the command started: naming
    # the pushed directory there would be a WRONG answer, which costs more than a missing one. Two
    # more directory changes are not the command's to keep, and cost the same if kept: one the reader
    # cannot place -- `then cd sub`, a branch it did not evaluate -- silences the rest rather than
    # guess which way it went; and one made inside a subshell, which bash discards when the subshell
    # closes, so every level keeps its own (base, pinned, pushd stack) and gets it back on the way out.
    base, pinned, stack, frames = cwd, False, [], []
    for level, words in simple_commands(cut_heredocs(command)):
        while level > len(frames) + 1:
            frames.append((base, pinned, stack))
            stack = list(stack)
        while level < len(frames) + 1:
            base, pinned, stack = frames.pop()
        target, verb = cd_target(words)
        if verb == "?":
            pinned = True
            continue
        if verb == "popd":
            if stack:
                base, pinned = stack.pop()
            continue
        if verb:
            if verb == "pushd":
                stack.append((base, pinned))
            if target.startswith(("/", "~")) or any(ch in target for ch in "$`"):
                pinned = True
            else:
                base = os.path.normpath(os.path.join(base, target))
            continue
        argv = git_call(words)
        if argv is None or pinned:
            continue
        return base, shlex.join(argv), shlex.join([argv[0], "-C", base, *argv[1:]])
    return None


def toplevel(directory):
    """The work-tree root a directory belongs to, as git itself answers it -- a linked worktree's root
    is not a path prefix of the checkout it belongs to, so no comparison of paths stands in for it.

    3s per call, and a judgement makes two of them, so the reader bounds itself at 6s: under the 10s
    `timeout` the registration in `.claude/settings.json` gives this hook, which is what would kill it
    otherwise. Raise one number and raise the other -- a reader killed by the harness is a PostToolUse
    arm that reports nothing and says nothing about why, while a timeout here returns "" and is the
    silence the rest of this file means by it."""
    try:
        done = subprocess.run(
            ["git", "-C", directory, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


try:
    call = json.load(sys.stdin)
    command = call.get("tool_input", {}).get("command", "")
    cwd = call.get("cwd") or os.getcwd()
    if not isinstance(command, str) or not isinstance(cwd, str):
        raise ValueError
except Exception:
    sys.exit(0)
project = os.environ.get("CLAUDE_PROJECT_DIR", "")
found = read(command, cwd) if project else None
if not found:
    sys.exit(0)
dirname, ran, fix = found
here, there = toplevel(dirname), toplevel(project)
if not here or not there or here == there:
    sys.exit(0)
# systemMessage reaches the user, additionalContext the model; exit 0, since a PostToolUse hook has
# nothing left to block and the next command is what the report is for.
msg = "git-cwd-advisory: `%s` ran in %s, a different checkout from the project directory — pin it: `%s`" % (ran, dirname, fix)
print(
    json.dumps(
        {
            "systemMessage": msg,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": msg
                + " -- the tool cwd drifts between calls, so read this answer as that checkout's, not the project directory's.",
            },
        }
    )
)
PY
)"
python3 -c "$prog" 2>/dev/null || true
exit 0
