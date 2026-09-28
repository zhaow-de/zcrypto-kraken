#!/usr/bin/env bash
# PreToolUse[Bash] guard: a refusal is exit 2, the one code the harness blocks on, with the spelling found and
# what it costs on stderr; anything else exits 0 silently.
# `tests/test_bash_guard.py` drives every family in both directions and IS the list of what is refused and what
# is admitted; what follows is only what neither the code nor that corpus can say.
#
# Argv, not text. The command is cut of its heredoc bodies, split into pipelines and into stages, and tokenised,
# so a flag inside a quoted message, a heredoc or a comment is never an argv element. A substitution -- `$( .. )`,
# backticks, `<( .. )`, `>( .. )` -- is a command of its own wherever bash performs one, and nowhere else.
# A wrapper is transparent to the bypass arm and opaque to the cap arm: the first finds `git` at any position in a
# simple command, so `timeout 5 git commit -n` and `/usr/bin/git commit --no-verify` are that one call in its
# wrapper, path and option spellings; the second reads a stage's program as its first word alone, so
# `timeout 5 head -5 f | wc -l` holds no cap -- the direction that does not refuse ordinary work.
#
# git's own asymmetries, which the per-subcommand arms encode and a reader would otherwise "fix": `-n` is
# `--no-verify` on commit and on am, `--no-stat` on merge and rebase; a config SET of core.hooksPath bypasses the
# hooks and a read does not; an assignment reaches git only as a prefix of the command that runs it, or through
# `export`.
#
# Outside, deliberately: `git push --no-verify` (no hook runs at push here), the pre-commit framework's
# `SKIP=<hook>` door (used on purpose), an edit of `.git/hooks/` or of this file, a git alias, a shell string
# handed to `sh -c`, `eval` or a Python subprocess, a program, a flag or a vaulted path arriving through a variable,
# a substitution or an encoding, a cap first in its pipeline, which truncates what it opened rather than what the
# command computed (`head -1 VERSION`), a truncation that is neither head nor tail, and a vaulted file read by a
# program no family names (`grep` without `-c`, `diff`, `git log -p`, a Python script) or reached through `xargs`,
# `find -exec` or a copy of its whole directory -- none is an argv this guard judges; nor is a vaulted file the command
# makes before it reads it (`ln -s <vaulted file> x && cat x`), since a file's existence is read before anything runs.
# A vault tool's writing verb is admitted over a vaulted file: a key rotation runs `ansible-vault encrypt|rekey`.
# Refused deliberately, as a word is judged wherever it stands: an agent's `echo git push`, `echo cat <vaulted file>`.
#
# A stage's directory, for the vaulted-file family and the dispatched-agent family, is the payload's `cwd` moved by
# each pipeline before it that is one stage whose command word is `cd` or `pushd` with a literal first operand, or
# none, then by git's `-C`s. Every other change of directory is unfollowed: `builtin cd`, `command cd`, `{fd}>x cd`
# and a `cd` inside a pipeline leave the directory where the hook had it; `cd -`, `popd` and an operand through a
# variable or a substitution leave it unknown, a relative `cd` after them keeps it so, and the vaulted-file family
# reads an unknown directory as the payload's `cwd`. Scope is not tracked, so a `cd` outlives its subshell.
#
# The dispatched-agent family judges only a call whose payload carries `agent_id`, which the harness sets inside a
# subagent alone, so the main loop's pushes and merges never reach it. The main checkout is the parent of the git
# common dir of the repository this file lives in: the payload's `cwd` can sit in any repository. Outside it:
# `--git-dir`, `--work-tree` and `GIT_DIR`; a `.tmp/` directory that is no repository of its own, where git reaches the
# main checkout's; a `gh api` write through fields with no `-X` (its implicit POST, a GraphQL mutation) and every `gh`
# verb the family does not name.
#
# A failure of the hook's own -- stdin that is not the tool call's JSON, a command `shlex` cannot tokenise --
# admits with a note on stderr, never blocks: exit 2 would refuse every Bash call in the session. That second
# class is wider than an unbalanced quote: `shlex` does not parse `$( .. )`, so a quote inside a substitution
# pairs with one outside it, and a command bash accepts and runs can leave the whole guard unjudged. Past the
# tokeniser, an error or a judging over its budget admits the main loop's call the same way and refuses a dispatched
# agent's: this hook is that agent's fence, and a fence that fails is off.
set -euo pipefail
input="$(cat)"
prog="$(cat <<'PY'
import functools
import glob
import json
import os
import posixpath
import re
import shlex
import signal
import subprocess
import sys

KEY = "core.hookspath"
NO_VERIFY = "--no-verify"
ANSI = "$'"
ANSI_SIMPLE = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
ASSIGN = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", re.S)
CONFIG_KEY_ENV = re.compile(r"^GIT_CONFIG_KEY_\d+$")
HEREDOC = re.compile(r"<<(-?)[ \t]*(?:'([^'\n]*)'|\"([^\"\n]*)\"|\\?([^\s'\"]+))")
GLOBAL_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env", "--attr-source"}
GLOBAL_TERMINAL = {"-v", "--version", "-h", "--help", "--exec-path", "--html-path", "--man-path", "--info-path", "--list-cmds"}
# Per subcommand: short options whose value is the rest of the bundle or else the next token; short options whose
# value is attached only; long options taking a value (=-attached or the next token).
VALUE = {
    "commit": ("mFCct", "uS", {"message", "file", "reuse-message", "reedit-message", "fixup", "squash", "author", "date", "template", "trailer", "cleanup", "pathspec-from-file"}),
    "merge": ("mFsX", "S", {"message", "file", "strategy", "strategy-option", "into-name", "cleanup"}),
    "rebase": ("sXx", "CS", {"onto", "strategy", "strategy-option", "exec", "whitespace", "empty"}),
    "am": ("", "CpS", {"whitespace", "directory", "exclude", "include", "patch-format", "quoted-cr", "empty"}),
}
HOOKS_SKIPPED = {
    "commit": "the pre-commit and commit-msg hooks (staged-kind, guidance-guard)",
    "merge": "the pre-merge-commit and commit-msg hooks (guidance-guard on the merge commit)",
    "rebase": "git's pre-rebase hook",
    "am": "git's pre-applypatch and applypatch-msg hooks",
}
CONFIG_READ = {"get", "get-all", "get-regexp", "get-urlmatch", "get-color", "get-colorbool", "unset", "unset-all", "list", "edit", "rename-section", "remove-section"}
CONFIG_SET = {"add", "replace-all"}
CONFIG_VALUE = {"file", "blob", "type", "default", "comment", "value", "url"}
CONFIG_VERBS = {"list", "get", "set", "unset", "rename-section", "remove-section", "edit"}
CAPS = {"head", "tail"}
GREPS = {"grep", "egrep", "fgrep", "rg"}
COUNT_FLAGS = {"--count", "--count-matches"}  # --count-matches is ripgrep's own: another number, capped the same
TESTS = {"[", "[[", "test"}
COMPARE = {"=", "==", "!="}
KEYWORDS = {"if", "elif", "else", "while", "until", "then", "do", "!", "{"}
TERMINATORS = {"]", "]]"} | COMPARE  # the test's own words an unquoted `$( .. )` inside it leaves glued to the last stage
OPS = ["&>>", ";;&", "<<<", "&&", "||", "|&", ";;", ";&", "<<", "<>", "<&", ">&", "&>", ">>", ">|", "|", "&", ";", "\n", "<", ">", "(", ")"]
SEP = {"&&", "||", "|&", ";;", ";&", ";;&", "|", "&", ";", "\n"}
PIPE = {"|", "|&"}  # one more stage of the same pipeline; every other separator starts a new one
REDIRECT = {"&>>", "<<<", "<<", "<>", "<&", ">&", "&>", ">>", ">|", "<", ">"}
PUNCT = set("();<>|&\n")
INPUT = {"<", "<>"}  # a redirect whose target is a file the stage reads
PRINTERS = {"cat", "head", "tail", "less", "more", "sed", "awk", "cut", "strings", "xxd", "od", "base64", "tac", "nl", "hexdump", "hd"}
COPIERS = {"cp", "scp", "rsync"}
INTERPRETER = re.compile(r"^python(\d+(\.\d+)?)?$")
KEYS_DIR = "/infra/ansible/files"
SOPS_VAULT = "/infra/ansible/vault-password.sops.yaml"
WILD = re.compile(r"[*?[]")
BRACE = re.compile(r"\{([^{}]*)\}")
SEQUENCE = re.compile(r"(-?\d+|[A-Za-z])\.\.(-?\d+|[A-Za-z])(?:\.\.(-?\d+))?")
VAULT_REMEDY = (
    "A vaulted value is read by `vault_var` through command substitution, never printed; a header or a count by "
    "`grep -c`, `sha256sum`, `wc`, `stat`, `ls` or `git log --`."
)
GH_PR_WRITES = {"create", "ready", "merge", "edit", "close", "comment", "review"}
GH_WRITE_METHODS = {"POST", "PATCH", "PUT", "DELETE"}
GH_VALUE = {"-R", "--repo"}
MAIN_READS = {
    "status", "log", "show", "diff", "diff-tree", "rev-parse", "rev-list", "ls-files", "ls-tree", "ls-remote", "cat-file",
    "grep", "blame", "describe", "name-rev", "merge-base", "merge-tree", "for-each-ref", "count-objects", "check-ignore",
}
BRANCH_LISTS = {"--list", "a", "r", "--show-current", "--contains", "--merged", "--no-merged"}
TAG_LISTS = {"l", "--list", "--contains"}
LIST_MODE = {"l", "--list", "--contains", "--merged", "--no-merged"}  # the options that make a branch or tag operand a pattern
FETCH_VALUE = (
    "jo",
    "",
    {"depth", "deepen", "shallow-since", "shallow-exclude", "upload-pack", "refmap", "negotiation-tip", "filter", "jobs",
     "server-option", "submodule-prefix", "recurse-submodules-default"},
)
FETCH_REWRITES = {"p", "P", "--prune", "--prune-tags", "--refmap"}
AGENT_DIRS = (".claude/worktrees/", ".tmp/")
PUSH_REMEDY = "The coordinator pushes and opens PRs after the read; a dispatched agent reports and stops."
CHECKOUT_REMEDY = (
    "A dispatched agent works in its worktree -- `git -C <worktree>` or `cd <worktree> &&`, a path under "
    ".claude/worktrees/ or .tmp/; the main checkout is the coordinator's, where an agent's git is held to a list of "
    "reads, `fetch` and `worktree list|add|remove`."
)
# Per subcommand: what it rewrites; its ref-writing options, short and long, each with its verb; then its valued
# options in VALUE's three kinds.
REF_OPTIONS = {
    "branch": (
        "a branch",
        {"d": "deletes", "D": "deletes", "m": "renames", "M": "renames", "c": "copies", "C": "copies", "f": "forces"},
        {"--delete": "deletes", "--move": "renames", "--copy": "copies", "--force": "forces"},
        "u",
        "t",
        {"set-upstream-to", "contains", "no-contains", "merged", "no-merged", "points-at", "sort", "format"},
    ),
    "tag": (
        "a tag",
        {"d": "deletes", "f": "forces"},
        {"--delete": "deletes", "--force": "forces"},
        "mFu",
        "n",
        {"message", "file", "trailer", "cleanup", "local-user", "contains", "no-contains", "merged", "no-merged",
         "points-at", "sort", "format"},
    ),
    "symbolic-ref": ("a symbolic ref", {"d": "deletes"}, {"--delete": "deletes"}, "m", "", set()),
}
REFLOG_WRITES = {"delete", "expire"}
REFS_REMEDY = "A dispatched agent creates the branches it needs and reports them."
WORKTREE_REMEDY = (
    "A dispatched agent removes only a scratch tree, named by a path and not a variable: one under the .tmp/ of this "
    "repository's main checkout or of one of its worktrees, whoever made it, or under its session's directory in "
    "Claude Code's temp root; a worktree, and another session's directory, are that session's."
)
HOOK_DIR = posixpath.dirname(os.path.abspath(sys.argv[1]))


class Stage(list):
    # A stage's words, and the files its `<` redirects feed it, which are no word of its argv.
    def __init__(self):
        super().__init__()
        self.inputs = []


def expansions(body):
    # Every `$( .. )` and backtick body inside a span bash expands: the lines of a heredoc whose delimiter is
    # unquoted, and a word the main scan kept whole (`"$( .. )"`). Quotes and `#` are text in both, so the main
    # scan's rules would close a body at the wrong place.
    found, stack, i, n = [], [], 0, len(body)
    while i < n:
        ch, st = body[i], stack[-1][0] if stack else "top"
        if ch == "\\":
            i += 2
            continue
        if st == "bq":
            if ch == "`":
                found.append(body[stack.pop()[1] : i])
        elif ch == "`":
            stack.append(("bq", i + 1))
        elif body.startswith("$(", i):
            stack.append(("sub", i + 2))
            i += 1
        elif ch == "(" and st != "top":
            stack.append(("paren", i))
        elif ch == ")" and st == "paren":
            stack.pop()
        elif ch == ")" and st == "sub":
            found.append(body[stack.pop()[1] : i])
        i += 1
    return found


def ansi_decode(raw):
    # The escapes bash decodes inside $'..' -- \xHH, \NNN, \uHHHH, \UHHHHHHHH, \cX and the letter escapes -- so
    # $'\x2dn' reaches the judge as the -n bash hands git, and the text ends at its first NUL, as bash's does:
    # `vault$'\0'.yml` is `vault.yml`. An escape this decoder does not know stays as written.
    out, i, n = [], 0, len(raw)
    while i < n:
        ch = raw[i]
        if ch != "\\" or i + 1 >= n:
            out.append(ch)
            i += 1
            continue
        nxt = raw[i + 1]
        if nxt in ANSI_SIMPLE:
            out.append(ANSI_SIMPLE[nxt])
            i += 2
        elif nxt == "x" and (m := re.match(r"[0-9A-Fa-f]{1,2}", raw[i + 2 : i + 4])):
            out.append(chr(int(m.group(), 16)))
            i += 2 + m.end()
        elif nxt in "01234567" and (m := re.match(r"[0-7]{1,3}", raw[i + 1 : i + 4])):
            out.append(chr(int(m.group(), 8) & 0xFF))
            i += 1 + m.end()
        elif nxt in "uU" and (m := re.match(r"[0-9A-Fa-f]{1,%d}" % (4 if nxt == "u" else 8), raw[i + 2 : i + 10])):
            code = int(m.group(), 16)
            out.append(chr(code) if code <= sys.maxunicode else "")  # past Unicode, where chr() raises: read as nothing
            i += 2 + m.end()
        elif nxt == "c" and i + 2 < n:
            ctl = raw[i + 2]
            out.append(chr(0x7F if ctl == "?" else ctl.encode("utf-8", "surrogatepass")[0] & 0x1F))
            i += 3
        else:
            out.append(raw[i : i + 2])
            i += 2
    return "".join(out).partition("\0")[0]


def cut_heredocs(text):
    # A scan that knows quotes and $(...) -- the heredoc inside the documented `-m "$(cat <<'EOF' ... EOF)"` is a
    # heredoc, and its body carries whatever the message says. Returns the cut text and the command substitutions
    # it closed -- `$( .. )` and backticks, each a command of its own; an unclosed one is bash's to refuse.
    out, bodies, pending, stack, i, n, sub_close = [], [], [], [("top", 0)], 0, len(text), -1
    while i < n:
        ch, st = text[i], stack[-1][0]
        if st == "sq":
            if ch == "'":
                stack.pop()
            out.append(ch)
            i += 1
            continue
        if st == "ansi":
            # shlex has no $'..': the span reaches it as one double-quoted word -- bare inside a double quote, where
            # a `"` would close it.
            if ch == "\\":
                i += 2
                continue
            if ch == "'":
                body = ansi_decode(text[stack.pop()[1] : i]).replace("\\", "\\\\").replace('"', '\\"')
                out.append(body if any(s == "dq" for s, _ in stack) else f'"{body}"')
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            if text[i + 1] != "\n":
                out.append(text[i : i + 2])
            i += 2
            continue
        if st != "dq" and text.startswith(ANSI, i):
            stack.append(("ansi", i + 2))
            i += 2
            continue
        if st != "dq" and text.startswith('$"', i):
            i += 1
            continue
        if st == "bq":
            if ch == "`":
                bodies.append(text[stack.pop()[1] : i])
            out.append(ch)
            i += 1
            continue
        if ch == "`":
            stack.append(("bq", i + 1))
            out.append(ch)
            i += 1
            continue
        if text.startswith("$(", i):
            stack.append(("sub", i + 2))
            out.append("$(")
            i += 2
            continue
        if st != "dq" and text[i : i + 2] in ("<(", ">("):
            # a process substitution: a command of its own, and its `)` ends a word (bash: `<(true)#x` is one word)
            stack.append(("sub", i + 2))
            out.append(text[i : i + 2])
            i += 2
            continue
        if st == "dq":
            if ch == '"':
                stack.pop()
            out.append(ch)
            i += 1
            continue
        if ch.isdigit() and (i == 0 or text[i - 1] in " \t\n;&|()"):
            j = i
            while j < n and text[j].isdigit():
                j += 1
            if j < n and text[j] in "<>":
                # an fd number is its redirection's, no word of the stage
                i = j
                continue
        if ch == "'" or ch == '"':
            stack.append(("sq" if ch == "'" else "dq", i))
        elif ch == "(" and st in ("sub", "paren"):
            stack.append(("paren", i))
        elif ch == ")" and st == "paren":
            stack.pop()
        elif ch == ")" and st == "sub":
            bodies.append(text[stack.pop()[1] : i])
            sub_close = i
        elif ch == "#" and (i == 0 or text[i - 1] in " \t\n;&|(" or (text[i - 1] == ")" and sub_close != i - 1)):
            # after a subshell's `)` bash starts a comment; after the `)` that closes `$( .. )` it continues the word
            end = text.find("\n", i)
            i = n if end == -1 else end
            continue
        elif ch == "<" and text.startswith("<<", i) and not text.startswith("<<<", i):
            m = HEREDOC.match(text, i)
            if m:
                # A backslash anywhere in the delimiter quotes it (`<<\EOF`): no expansion, like `<<'EOF'`.
                expands = m.group(4) is not None and "\\" not in m.group(0)
                pending.append((m.group(2) or m.group(3) or m.group(4), bool(m.group(1)), expands))
                out.append(m.group(0))
                i = m.end()
                continue
        elif ch == "\n" and pending:
            out.append("\n")
            i += 1
            for delim, dash, expands in pending:
                lines = []
                while i < n:
                    end = text.find("\n", i)
                    line = text[i : n if end == -1 else end]
                    i = n if end == -1 else end + 1
                    if (line.lstrip("\t") if dash else line) == delim:
                        break
                    lines.append(line)
                if expands:
                    bodies.extend(expansions("\n".join(lines)))
            pending = []
            continue
        out.append(ch)
        i += 1
    return "".join(out), bodies


def pipelines(text):
    # Each pipeline as its stages, in order: the second arm judges what one stage hands the next, and the first
    # arm reads every stage on its own.
    cut, bodies = cut_heredocs(text)
    lex = shlex.shlex(cut, posix=True, punctuation_chars="".join(sorted(PUNCT)))
    lex.commenters = ""  # bash's comments are cut above; a `#` inside a word (issue#42) is text
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    pipes, skip = [[Stage()]], ""
    for tok in lex:
        if skip:
            if skip in INPUT:
                pipes[-1][-1].inputs.append(tok)
            skip = ""
            continue
        if not tok or not set(tok) <= PUNCT:
            pipes[-1][-1].append(tok)
            continue
        last = ""
        while tok:
            last = next(op for op in OPS if tok.startswith(op))
            if last in PIPE and pipes[-1][-1]:
                pipes[-1].append(Stage())
            elif last in SEP and pipes[-1][-1]:
                pipes.append([Stage()])
            tok = tok[len(last) :]
        skip = last if last in REDIRECT else ""
    out = [[stage for stage in pipe if stage] for pipe in pipes]
    out = [pipe for pipe in out if pipe]
    for body in bodies:
        out.extend(pipelines(body))
    return out


def refuse(text):
    print("bash-guard: BLOCKED — " + text)
    sys.exit(2)


def clip(line):
    return line if len(line) <= 120 else line[:117] + "..."


def spelled(words):
    return clip(shlex.join(words))


def stage_name(words):
    out = []
    for w in words:
        if w in TERMINATORS:
            break
        out.append(w)
    return spelled(out)


def judge_options(sub, rest, words):
    short_value, short_attached, long_value = VALUE[sub]
    j = 0
    while j < len(rest):
        tok = rest[j]
        if tok == "--":
            return
        if tok.startswith("--"):
            name = tok.partition("=")[0]
            if len(name) >= len("--no-v") and NO_VERIFY.startswith(name):
                refuse(f"`git {sub} {tok}` skips {HOOKS_SKIPPED[sub]}; in `{spelled(words)}`. Run it without the flag: the hooks are the gate, and what they refuse is fixed, not skipped.")
            if "=" not in tok and len(name) > 2 and any(o.startswith(name[2:]) for o in long_value):
                j += 2
                continue
            j += 1
            continue
        if tok.startswith("-") and len(tok) > 1:
            consume_next = False
            for k, ch in enumerate(tok[1:], 1):
                if ch == "n" and sub in ("commit", "am"):
                    refuse(f"`git {sub} {tok}` carries -n, git's short --no-verify, which skips {HOOKS_SKIPPED[sub]}; in `{spelled(words)}`. Run it without the flag: the hooks are the gate, and what they refuse is fixed, not skipped.")
                if ch in short_value:
                    consume_next = k == len(tok) - 1
                    break
                if ch in short_attached:
                    break
            j += 2 if consume_next else 1
            continue
        j += 1


def judge_config(rest, words):
    read, positional, j = False, [], 0
    while j < len(rest):
        tok = rest[j]
        if tok == "--":
            positional.extend(rest[j + 1 :])
            break
        if tok.startswith("--"):
            name, eq, _ = tok.partition("=")
            n = name[2:]
            reads = n in CONFIG_READ or (n and any(a.startswith(n) for a in CONFIG_READ))
            sets = n in CONFIG_SET or (n and any(a.startswith(n) for a in CONFIG_SET))
            if reads and not sets:
                read = True
            elif not eq and not sets and n and any(o.startswith(n) for o in CONFIG_VALUE):
                j += 2
                continue
            j += 1
            continue
        if tok.startswith("-") and len(tok) > 1:
            consume_next = False
            for k, ch in enumerate(tok[1:], 1):
                if ch in "le":
                    read = True
                if ch == "f":
                    consume_next = k == len(tok) - 1
                    break
            j += 2 if consume_next else 1
            continue
        positional.append(tok)
        j += 1
    if read:
        return
    if positional and positional[0] in CONFIG_VERBS:
        if positional[0] != "set" or len(positional) < 3 or positional[1].lower() != KEY:
            return
        value = positional[2]
    elif len(positional) < 2 or positional[0].lower() != KEY:
        return
    else:
        value = positional[1]
    refuse(f"`{spelled(words)}` sets core.hooksPath to `{value}`, which points git away from .git/hooks so the repo's hooks never run. Read it with `git config --get core.hooksPath`; undo it with `git config --unset core.hooksPath`.")


def argv_of(words):
    # A stage's program and its arguments: leading NAME=value assignments and shell keywords stepped over, the
    # program path-stripped. A word in any other position is never the program.
    i = 0
    while i < len(words) and (ASSIGN.match(words[i]) or words[i] in KEYWORDS):
        i += 1
    if i == len(words):
        return "", []
    return words[i].rpartition("/")[2], words[i + 1 :]


def capping(words):
    p, rest = argv_of(words)
    if p not in CAPS:
        return False
    # `tail +2`, `-n +2`, `-n+2`, `--lines=+2`: the stream from line 2 on, which caps nothing.
    return p == "head" or not any(a.startswith(("+", "-n+", "--lines=+")) for a in rest)


def counting(words):
    p, rest = argv_of(words)
    if p == "wc":
        return True
    if p not in GREPS:
        return False
    for a in rest:
        if a == "--":
            break  # a pattern, not a flag: `grep -- -c` searches for `-c`
        if a in COUNT_FLAGS or (a.startswith("-") and not a.startswith("--") and "c" in a[1:]):
            return True
    return False


def testing(words):
    return argv_of(words)[0] in TESTS


def comparing(words):
    # The words of a test, in the order the shell hands them: a `=`, `==` or `!=` -- COMPARE holds no other
    # operator -- against a non-empty operand, which is the verdict a cap can change. An emptiness test (`-z`,
    # `-n`, `= ""`, `!= ""`) reads a capped stream and an uncapped one alike, because `$( .. )` strips the trailing
    # newlines and `head -1` of a non-empty stream is non-empty. A numeric comparison (`-eq`, `-gt`) is in neither
    # class and is admitted: over a substitution it almost always holds a count the count arm already refuses.
    return any(w in COMPARE and 0 < j < len(words) - 1 and words[j - 1] and words[j + 1] for j, w in enumerate(words))


def capped_stage(body):
    # The stage of a substitution body that caps a stream it did not open, or None -- None too for a body that does
    # not tokenise on its own, which the quote around it can hide from the top-level scan (`$(git log
    # --grep=doesn't)` holds one apostrophe). Skipping such a body leaves every other stage and the first arm
    # judged; letting the error out of here fails the whole hook open instead, and with it the bypass arm.
    try:
        subs = pipelines(body)
    except ValueError:
        return None
    return next((stage for sub in subs for i, stage in enumerate(sub) if i and capping(stage)), None)


def refuse_capped_test(cap, test, raw):
    refuse(
        f"`{stage_name(cap)}` caps the stream a `{argv_of(test)[0]}` then compares -- the verdict is the cap's line, "
        f"not what the whole stream holds; in `{raw}`. Compare the whole stream, or keep the cap and read the lines "
        f"instead of comparing them."
    )


def judge_cap(pipe, raw):
    capped = [i for i, stage in enumerate(pipe) if i and capping(stage)]
    tested = [i for i, stage in enumerate(pipe) if testing(stage)]
    for i in capped:
        for stage in pipe[i + 1 :]:
            if counting(stage):
                refuse(
                    f"`{stage_name(pipe[i])}` caps the stream `{argv_of(stage)[0]}` then counts -- the number can only "
                    f"be the cap, not what the tree holds; in `{raw}`. Count the whole stream, or keep the cap and read "
                    f"the lines instead of counting them."
                )
        # An unquoted `$( .. )` leaves the test's own words spread over the stages after it, so the comparison is
        # read over the pipeline from the test on, not over that first stage alone.
        if tested and i > tested[0] and comparing([w for stage in pipe[tested[0] :] for w in stage]):
            refuse_capped_test(pipe[i], pipe[tested[0]], raw)
    for stage in pipe:
        if not testing(stage):
            continue
        for w in stage:
            for body in expansions(w):
                inner = capped_stage(body)
                if inner and comparing(stage):
                    refuse_capped_test(inner, stage, raw)


def is_git(w):
    return w == "git" or (w.endswith("/git") and not ASSIGN.match(w))


def vault_path(path):
    # The vaulted set, read from a path whose every directory is spelled: a realpath, or `/` and a path under a
    # repository.
    head, _, name = path.rpartition("/")
    keys = name.endswith("_ed25519") and head.endswith(KEYS_DIR)
    return name == "vault.yml" or name.endswith(".vault") or keys or path.endswith(SOPS_VAULT)


def held(path, where):
    return os.path.isfile(posixpath.join(where, path)) and vault_path(os.path.realpath(posixpath.join(where, path)))


def alternatives(text):
    # A brace group's words -- its comma list, or its `..` sequence of numbers or letters with an optional step, `*`
    # for a sequence past 256 words, counted from its ends and step -- and whether it is that `*`; None for a group bash
    # leaves as text.
    if "," in text:
        return text.split(","), False
    seq = SEQUENCE.fullmatch(text)
    if not seq or seq[1].isalpha() != seq[2].isalpha():
        return None
    a, b = (ord(seq[1]), ord(seq[2])) if seq[1].isalpha() else (int(seq[1]), int(seq[2]))
    step = abs(int(seq[3] or 1)) or 1
    if abs(b - a) // step >= 256:
        return ["*"], True
    sign = 1 if a <= b else -1
    return [chr(v) if seq[1].isalpha() else str(v) for v in range(a, b + sign, sign * step)], False


def starred(word):
    # The word with every brace group, a nested one whole, read as `*`.
    out, opens = [], []
    for ch in word:
        if ch == "}" and opens:
            del out[opens.pop() :]
            ch = "*"
        elif ch == "{":
            opens.append(len(out))
        out.append(ch)
    return "".join(out)


def braces(word):
    # The words bash's brace expansion makes of one, innermost group first, each with whether a group was read as `*`
    # on the way to it: a group with a comma or a `..` sequence expands, and `{x}` stays. A sequence past 256 words,
    # counted from its ends and step, reads as `*`; past 256 words in all, every group does, a nested one whole. Such a
    # `*` is no glob bash sees and can sit inside an option's value (`--file=`), so the caller globs every tail of the
    # word, a leading dot included: that refuses more than bash's words name, and only on a word past 256 as counted
    # here -- one bash expands past 256 ways, the same quoted, or one with a sequence bash leaves as text for its size.
    # A `*` stays inside a path component, so where every group reads as `*`, an alternative with a `/` is read short.
    todo, done = [(word, False)], []
    while todo:
        w, star = todo.pop()
        group = next(((m, alt) for m in BRACE.finditer(w) if (alt := alternatives(m[1]))), None)
        if group is None:
            done.append((w, star))
            continue
        m, (items, read_as_star) = group
        if len(items) + len(todo) + len(done) > 256:
            return [(starred(word), True)]
        todo.extend((w[: m.start()] + item + w[m.end() :], star or read_as_star) for item in reversed(items))
    return done


def globbed(pattern, where, hidden=False):
    return glob.glob(posixpath.join(glob.escape(where), posixpath.expanduser(pattern)), include_hidden=hidden)


def vaulted(word, where):
    # The word, or the first tail of it -- an option's attached value, a `name=value`'s value -- that names an existing
    # file in the vaulted set from `where`, or None: no option or program is parsed, so a pattern names no file and the
    # operand beside it does. The word expands as bash expands it: braces, then a glob, which is the files it matches,
    # or its own text where it matches none; a word braces() read a group of as `*` has every tail globbed instead.
    for w, star in braces(word):
        tails = (w[k:] for k in range(len(w)))
        if star:
            hit = next((t for t in tails if any(held(p, where) for p in globbed(t, where, hidden=True))), None)
        elif WILD.search(w) and (found := globbed(w, where)):
            hit = w if any(held(p, where) for p in found) else None
        else:
            hit = next((t for t in tails if held(posixpath.expanduser(t), where)), None)
        if hit:
            return hit
    return None


def composed(parts, where):
    # The paths a program's words compose, each joined under a directory the words name or compose.
    dirs, out = [""], []
    for d in dirs:
        for part in parts:
            path = posixpath.normpath(posixpath.join(d, part)) if d else part
            out.append(path)
            if path not in dirs and len(dirs) < 16 and os.path.isdir(posixpath.join(where, path)):
                dirs.append(path)
    return out[len(parts) :]


def at_revision(where, operand):
    # Whether a `<rev>:<path>` operand is a vaulted file in the tree at that revision: git resolves it from `where`, and
    # the path is read under the repository, a `./` or `../` one from the directory git runs in.
    done = subprocess.run(["git", "-C", where, "cat-file", "-t", operand], capture_output=True, text=True)
    if done.returncode or done.stdout.strip() != "blob":
        return False
    path = operand.rpartition(":")[2]
    if path.startswith(("./", "../")):
        prefix = subprocess.run(["git", "-C", where, "rev-parse", "--show-prefix"], capture_output=True, text=True)
        path = posixpath.normpath(prefix.stdout.strip() + path)
    return vault_path("/" + path)


def operands(args):
    out, ended = [], False
    for a in args:
        if a == "--" and not ended:
            ended = True
        elif ended or a == "-" or not a.startswith("-"):
            out.append(a)
    return out


def among(flag, names):
    # A short option's letter, or a long option's name or the prefix getopt takes for it, is one of names.
    if flag[:2] != "--":
        return flag in names
    return len(flag) > 2 and any(n.startswith(flag) for n in names if n[:2] == "--")


def git_sub(words):
    # The subcommand, its arguments, and the `-C` paths before it in the order git chdirs through them.
    at = next((i for i, w in enumerate(words) if is_git(w)), None)
    if at is None:
        return None, [], []
    argv, i, chdirs = words[at:], 1, []
    while i < len(argv) and argv[i].startswith("-") and len(argv[i]) > 1:
        name, eq, _ = argv[i].partition("=")
        if name == "-C" and not eq and i + 1 < len(argv):
            chdirs.append(argv[i + 1])
        i += 2 if name in GLOBAL_VALUE and not eq else 1
    return (argv[i], argv[i + 1 :], chdirs) if i < len(argv) else (None, [], chdirs)


def refuse_vault(words, what, raw):
    refuse(f"`{spelled(words)}` {what}; in `{raw}`. {VAULT_REMEDY}")


def first_vaulted(args, where):
    return next((hit for a in args if (hit := vaulted(a, where))), None)


def judge_vault(words, raw, where):
    for i, w in enumerate(words):
        p, rest = w.rpartition("/")[2], words[i + 1 :]
        if p == "ansible-vault" and any(a in ("view", "decrypt") for a in rest):
            refuse_vault(words, "decrypts a vaulted file to the terminal", raw)
        if p == "sops" and any(a in ("-d", "--decrypt", "decrypt", "exec-env", "exec-file") for a in rest):
            refuse_vault(words, "decrypts a sops file to the terminal or a command", raw)
        if p == "sed" and any(a.startswith("--in-place") or (a[:1] == "-" and a[1:2] != "-" and "i" in a) for a in rest):
            continue  # in place: sed writes the file back and prints nothing
        if p in PRINTERS:
            hit = first_vaulted(rest + getattr(words, "inputs", []), where)
            if hit:
                refuse_vault(words, f"prints the vaulted file `{hit}`", raw)
        if p in COPIERS:
            ops = operands(rest)
            sources = ops if p == "cp" and any(a == "-t" or a.startswith("--target-directory") for a in rest) else ops[:-1]
            hit = first_vaulted(sources, where)
            if hit:
                refuse_vault(words, f"copies the vaulted file `{hit}` to another path", raw)
        if INTERPRETER.match(p):
            code = next((rest[j + 1] for j, a in enumerate(rest[:-1]) if re.fullmatch(r"-[A-Za-z]*c", a)), "")
            parts = re.findall(r"[^\s'\"(),;]+", code)
            hit = first_vaulted(parts, where) or next((path for path in composed(parts, where) if held(path, where)), None)
            if hit:
                refuse_vault(words, f"opens the vaulted file `{hit}`", raw)
    sub, rest, chdirs = git_sub(words)
    for d in chdirs:
        where = resolve(where, d)
    if sub in ("show", "cat-file") and where:
        hit = next((a for a in rest if ":" in a and a[:1] != "-" and at_revision(where, a)), None)
        if hit:
            refuse_vault(words, f"prints the vaulted file `{hit.rpartition(':')[2]}` at a revision", raw)


def is_gh(w):
    return w == "gh" or (w.endswith("/gh") and not ASSIGN.match(w))


def gh_writes(words):
    at = next((i for i, w in enumerate(words) if is_gh(w)), None)
    if at is None:
        return False
    rest, pos, j = words[at + 1 :], [], 0
    while j < len(rest):
        if rest[j] in GH_VALUE:
            j += 2
            continue
        if not rest[j].startswith("-"):
            pos.append(rest[j])
        j += 1
    if pos[:1] == ["pr"]:
        return pos[1:2] != [] and pos[1] in GH_PR_WRITES
    if pos[:2] == ["cache", "delete"]:
        return True
    if pos[:1] != ["api"]:
        return False
    for j, a in enumerate(rest):
        name, eq, value = a.partition("=")
        if a in ("-X", "--method"):
            value = rest[j + 1] if j + 1 < len(rest) else ""
        elif a.startswith("-X"):
            value = a[2:].removeprefix("=")
        elif name != "--method" or not eq:
            continue
        if value.upper() in GH_WRITE_METHODS:
            return True
    return False


def main_admits(sub, rest):
    if sub in MAIN_READS:
        return True
    positional = [a for a in rest if not a.startswith("-")]
    if sub == "config":
        return any(a in ("--get", "--list", "-l") for a in rest) or positional[:1] in (["get"], ["list"])
    if sub == "remote":
        return positional[:1] in ([], ["show"])
    if sub in ("branch", "tag"):
        flags, _, ops = option_walk(rest, *REF_OPTIONS[sub][3:])
        return set(flags) <= (BRANCH_LISTS if sub == "branch" else TAG_LISTS) and (not ops or bool(set(flags) & LIST_MODE))
    if sub == "stash":
        return rest[:1] in (["list"], ["show"])
    if sub == "reflog":
        return rest[:1] in ([], ["show"])
    if sub == "symbolic-ref":
        return not ref_write(sub, rest)
    if sub == "fetch":
        flags, _, ops = option_walk(rest, *FETCH_VALUE)
        return not any(among(f, FETCH_REWRITES) for f in flags) and not any(":" in a for a in ops[1:])
    if sub == "worktree":
        return rest[:1] in (["list"], ["add"], ["remove"])
    return False


def option_walk(rest, short_value, short_attached, long_value):
    # A subcommand's options -- a short one as its letter, a long one as its name -- each with its value or None, and
    # its operands; an option's value is no operand.
    flags, values, ops, j = [], [], [], 0
    while j < len(rest):
        tok = rest[j]
        j += 1
        if tok == "--":
            ops.extend(rest[j:])
            break
        if tok.startswith("--"):
            name, eq, value = tok.partition("=")
            takes = not eq and any(o.startswith(name[2:]) for o in long_value)
            flags.append(name)
            values.append(value if eq else rest[j] if takes and j < len(rest) else None)
            j += takes
        elif tok.startswith("-") and len(tok) > 1:
            for k, ch in enumerate(tok[1:], 1):
                flags.append(ch)
                if ch not in short_value and ch not in short_attached:
                    values.append(None)
                    continue
                value = tok[k + 1 :]
                if not value and ch in short_value and j < len(rest):
                    value, j = rest[j], j + 1
                values.append(value)
                break
        else:
            ops.append(tok)
    return flags, values, ops


def ref_write(sub, rest):
    if sub == "update-ref":
        return "rewrites a ref"
    if sub == "reflog" and rest[:1] and rest[0] in REFLOG_WRITES:
        return f"{rest[0]}s reflog entries"
    if sub == "worktree" and rest[:1] == ["move"]:
        return "moves a worktree"
    if sub not in REF_OPTIONS:
        return None
    what, shorts, longs, *values = REF_OPTIONS[sub]
    flags, _, ops = option_walk(rest, *values)
    for f in flags:
        verb = next((v for o, v in longs.items() if o.startswith(f)), None) if f.startswith("--") else shorts.get(f)
        if verb:
            return f"{verb} {what}"
    return f"rewrites {what}" if sub == "symbolic-ref" and len(ops) > 1 else None


def resolve(here, target):
    # The directory `cd <target>` or `git -C <target>` leaves from `here`, None where the hook cannot know it.
    if target == "":
        return here
    if target == "-" or "$" in target or "`" in target:
        return None
    if target.startswith("~"):
        target = posixpath.expanduser(target)
    if target.startswith("/"):
        return posixpath.normpath(target)
    return posixpath.normpath(posixpath.join(here, target)) if here else None


def moved(words, here):
    p, args = argv_of(words)
    if p == "popd":
        return None
    if p not in ("cd", "pushd"):
        return here
    ops = [a for a in args if a == "-" or not a.startswith(("-", "+"))]
    return resolve(here, ops[0] if ops else "~")


@functools.cache
def main_checkout():
    done = subprocess.run(
        ["git", "-C", HOOK_DIR, "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True, text=True
    )
    common = done.stdout.strip()
    return os.path.realpath(posixpath.dirname(common)) if done.returncode == 0 and posixpath.basename(common) == ".git" else None


def in_main_checkout(path):
    main = main_checkout()
    if not path or not main:
        return False
    p = os.path.realpath(path)
    if p != main and not p.startswith(main + "/"):
        return False
    return not p.startswith(tuple(f"{main}/{d}" for d in AGENT_DIRS))


@functools.cache
def top_and_common(where):
    done = subprocess.run(
        ["git", "-C", where, "rev-parse", "--path-format=absolute", "--show-toplevel", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    return tuple(os.path.realpath(line) for line in done.stdout.splitlines()) if done.returncode == 0 else None


def worktree_top(path):
    main = main_checkout()
    if not main:
        return None
    ours, here = os.path.realpath(f"{main}/.git"), path
    while here != "/":
        here = posixpath.dirname(here)
        if top_and_common(here) == (here, ours):
            return here
    return None


def scratch_tree(path, session):
    # A temp root holds `claude-<uid>/<project>/<session_id>/`; only the payload's session directory is scratch, not the
    # whole root, because a payload session's worktree is cut in it too (docs/reference/multi-agent-protocol.md).
    if not path:
        return False
    p = os.path.realpath(path)
    for root in {"/tmp", os.environ.get("CLAUDE_CODE_TMPDIR") or "/tmp"}:
        base = os.path.realpath(f"{root}/claude-{os.getuid()}") + "/"
        parts = p[len(base) :].split("/") if p.startswith(base) else []
        if len(parts) > 2 and parts[1] == session:
            return True
    top = worktree_top(p)
    return top is not None and p.startswith(os.path.realpath(f"{top}/.tmp") + "/")


def judge_agent(words, here, raw, session):
    sub, rest, chdirs = git_sub(words)
    if sub == "push":
        refuse(f"`{spelled(words)}` pushes from a dispatched agent; in `{raw}`. {PUSH_REMEDY}")
    if gh_writes(words):
        refuse(f"`{spelled(words)}` writes to GitHub from a dispatched agent; in `{raw}`. {PUSH_REMEDY}")
    if not sub:
        return
    for d in chdirs:
        here = resolve(here, d)
    writes = ref_write(sub, rest)
    if writes:
        refuse(f"`{spelled(words)}` {writes} from a dispatched agent, whatever directory it runs in; in `{raw}`. {REFS_REMEDY}")
    if sub == "worktree" and rest[:1] == ["remove"]:
        hit = next((a for a in operands(rest[1:]) if not scratch_tree(resolve(here, a), session)), None)
        if hit is not None:
            refuse(
                f"`{spelled(words)}` removes the worktree `{hit}` from a dispatched agent, whatever directory it runs in; "
                f"in `{raw}`. {WORKTREE_REMEDY}"
            )
    if in_main_checkout(here) and not main_admits(sub, rest):
        refuse(
            f"`{spelled(words)}` runs `git {sub}` in the main checkout, at `{here}`, from a dispatched agent; in "
            f"`{raw}`. {CHECKOUT_REMEDY}"
        )


def env_assignments(words):
    at = next((i for i, w in enumerate(words) if is_git(w)), None)
    prefix = words[:at] if at is not None else []
    seen = [w for w in prefix if ASSIGN.match(w)]
    program = next((w for w in words if not ASSIGN.match(w)), "")
    if program.rpartition("/")[2] == "export":
        seen.extend(w for w in words[1:] if ASSIGN.match(w))
    return seen


def judge(words):
    for w in env_assignments(words):
        m = ASSIGN.match(w)
        if (CONFIG_KEY_ENV.match(m.group(1)) and m.group(2).lower() == KEY) or (m.group(1) == "GIT_CONFIG_PARAMETERS" and KEY in m.group(2).lower()):
            refuse(f"`{w}` sets core.hooksPath through git's environment, which points git away from .git/hooks so the repo's hooks never run; in `{spelled(words)}`.")
    at = next((i for i, w in enumerate(words) if is_git(w)), None)
    if at is None:
        return
    argv = words[at:]
    i = 1
    while i < len(argv) and argv[i].startswith("-") and len(argv[i]) > 1:
        name, eq, attached = argv[i].partition("=")
        if name in ("-c", "--config-env"):
            value = attached if eq else (argv[i + 1] if i + 1 < len(argv) else "")
            i += 1 if eq else 2
            if value.partition("=")[0].lower() == KEY:
                refuse(f"`git {name} {value}` sets core.hooksPath for this one command, which points git away from .git/hooks so the repo's hooks never run; in `{spelled(words)}`.")
            continue
        if name in GLOBAL_VALUE:
            i += 1 if eq else 2
            continue
        if name in GLOBAL_TERMINAL and not eq:
            return
        i += 1
    if i >= len(argv):
        return
    sub, rest = argv[i], argv[i + 1 :]
    if sub == "config":
        judge_config(rest, words)
    elif sub in VALUE:
        judge_options(sub, rest, words)


def overrun(*_):
    raise TimeoutError(f"the judging ran past {BUDGET} seconds")


BUDGET = 5  # under the 10 seconds .claude/settings.json gives this hook: a hook the harness ends has not refused
sys.stdout.reconfigure(errors="backslashreplace")  # a refusal naming a lone surrogate (`$'\uD800'`) still prints
sys.set_int_max_str_digits(0)  # a `..` sequence's ends are read whatever their length
try:
    call = json.load(sys.stdin)
    command = call.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        raise ValueError("command is not a string")
except (ValueError, AttributeError) as exc:
    print(f"stdin is not the tool call's JSON ({exc})")
    sys.exit(3)
command = command.replace("\0", "")  # as bash reads a command from stdin; no argv carries a NUL
raw = clip(" ".join(command.split()))
agent = bool(call.get("agent_id"))
signal.signal(signal.SIGALRM, overrun)
signal.alarm(BUDGET)
try:
    try:
        commands = pipelines(command)
    except ValueError as exc:
        print(f"the command does not tokenise ({exc})")
        sys.exit(3)
    cwd = call.get("cwd") if isinstance(call.get("cwd"), str) and call.get("cwd") else os.getcwd()
    here = cwd
    for pipe in commands:
        for words in pipe:
            judge(words)
            judge_vault(words, raw, here or cwd)
            if agent:
                judge_agent(words, here, raw, call.get("session_id"))
        judge_cap(pipe, raw)
        if len(pipe) == 1:
            here = moved(pipe[0], here)
except Exception as exc:
    if agent:
        refuse(
            f"the hook could not judge the command ({type(exc).__name__}: {clip(str(exc))}), and a dispatched agent's "
            f"command it cannot judge is refused; in `{raw}`. Run it as simpler calls, or report it and stop."
        )
    raise
finally:
    signal.alarm(0)
PY
)"
if out="$(printf '%s' "$input" | python3 -c "$prog" "${BASH_SOURCE[0]}" 2>/dev/null)"; then
  exit 0
else
  rc=$?
fi
if [[ $rc -eq 2 ]]; then
  echo "$out" >&2
  exit 2
fi
echo "bash-guard: NOTE — ${out:-the hook failed on its own (rc $rc)}; the command runs unjudged." >&2
exit 0
