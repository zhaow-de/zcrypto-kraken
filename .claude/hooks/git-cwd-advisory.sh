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
# hook is silent rather than guessing one.
# Silent, deliberately: a bare git made from the project directory's own checkout, even where the
# reader meant a worktree -- that is the default cwd, the case above; a git reached through a
# variable or an alias, or through a string handed to `sh -c`, `eval` or a heredoc -- none is an argv
# of git in this command; a substitution inside a double quote, which bash expands and this reader
# does not open; a call whose answer does not depend on the cwd (`git --version`, `git help`); and a
# `cd` whose target holds a substitution, read as a pin rather than as the process cwd.
set -euo pipefail
input="$(cat)"
prog="$(cat <<'PY'
import json
import os
import re
import shlex
import sys

ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
DURATION = re.compile(r"^\d+(?:\.\d+)?[smhd]?$")
HEREDOC = re.compile(r"<<(-?)\s*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([\w./-]+))")
WRAPPERS = {"sudo", "doas", "env", "timeout", "nice", "ionice", "stdbuf", "setsid", "nohup", "command", "time"}
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
    # `$( .. )` or backtick body is a command of its own -- bash runs it in the same cwd, so a bare
    # git there is as unpinned as one outside. A redirect and its target are dropped.
    cmds, word, started, stack, i, n = [[]], [], False, [["top", None]], 0, len(text)

    def flush():
        nonlocal word, started
        if started:
            cmds[-1].append("".join(word))
        word, started = [], False

    def sep():
        flush()
        if cmds[-1]:
            cmds.append([])

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
    return [c for c in cmds if c]


def is_git(w):
    return w == "git" or ("/" in w and w.rpartition("/")[2] == "git")


def head(words):
    """Where the command word is, after the assignments and wrappers, and whether git's directory is
    already pinned in the environment."""
    i, pinned = 0, False
    while i < len(words):
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
    return i, pinned


def git_call(words):
    """The argv of an unpinned git invocation whose answer depends on the cwd, or None."""
    i, pinned = head(words)
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
    i, _ = head(words)
    if i >= len(words) or words[i].rpartition("/")[2] not in ("cd", "pushd"):
        return ""
    return next((w for w in words[i + 1 :] if not w.startswith("-")), "~")


def read(command, cwd):
    # A `cd` to an absolute path, or to one this reader cannot resolve, is the author pinning the
    # directory by another spelling and silences the rest of the command; a relative one leaves the
    # answer as cwd-dependent as it was and only moves where it points.
    base, pinned = cwd, False
    for words in simple_commands(cut_heredocs(command)):
        target = cd_target(words)
        if target:
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


try:
    call = json.load(sys.stdin)
    command = call.get("tool_input", {}).get("command", "")
    cwd = call.get("cwd") or os.getcwd()
    if not isinstance(command, str) or not isinstance(cwd, str):
        raise ValueError
except Exception:
    sys.exit(0)
found = read(command, cwd)
if found:
    print("\t".join(found))
PY
)"
found="$(printf '%s' "$input" | python3 -c "$prog" 2>/dev/null || true)"
[[ -z "$found" ]] && exit 0
IFS=$'\t' read -r dir ran fix <<<"$found"
[[ -z "${CLAUDE_PROJECT_DIR:-}" ]] && exit 0
here="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
there="$(git -C "$CLAUDE_PROJECT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
[[ -z "$here" || -z "$there" || "$here" == "$there" ]] && exit 0
# systemMessage reaches the user, additionalContext the model; exit 0, since a PostToolUse hook has
# nothing left to block and the next command is what the report is for.
printf '%s\t%s\t%s' "$dir" "$ran" "$fix" | python3 -c '
import json, sys

dirname, ran, fix = sys.stdin.read().split("\t")
msg = "git-cwd-advisory: `%s` ran in %s, a different checkout from the project directory — pin it: `%s`" % (ran, dirname, fix)
print(json.dumps({
    "systemMessage": msg,
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg + " -- the tool cwd drifts between calls, so read this answer as that checkout'"'"'s, not the project directory'"'"'s.",
    },
}))
'
exit 0
