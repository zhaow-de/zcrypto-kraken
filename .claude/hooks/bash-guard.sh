#!/usr/bin/env bash
# PreToolUse[Bash] guard: a command whose argv would skip the repo's commit-time hooks, or believe a number or a
# word that an earlier stage of its own pipeline capped, is refused before it runs -- exit 2, the one code the
# harness blocks on, with the spelling found and what it costs on stderr; anything else exits 0 silently.
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
# handed to `sh -c`, `eval` or a Python subprocess, a program or a flag arriving through a variable or a
# substitution, a cap first in its pipeline, which truncates what it opened rather than what the command computed
# (`head -1 VERSION`), and a truncation that is neither head nor tail -- none is an argv this guard judges.
#
# A failure of the hook's own -- stdin that is not the tool call's JSON, a command `shlex` cannot tokenise --
# admits with a note on stderr, never blocks: exit 2 would refuse every Bash call in the session. That second
# class is wider than an unbalanced quote: `shlex` does not parse `$( .. )`, so a quote inside a substitution
# pairs with one outside it, and a command bash accepts and runs can leave the whole guard unjudged.
set -euo pipefail
input="$(cat)"
prog="$(cat <<'PY'
import json
import re
import shlex
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
KEYWORDS = {"if", "elif", "while", "until", "then", "do", "!", "{"}
TERMINATORS = {"]", "]]"} | COMPARE  # the test's own words an unquoted `$( .. )` inside it leaves glued to the last stage
OPS = ["&>>", ";;&", "<<<", "&&", "||", "|&", ";;", ";&", "<<", "<>", "<&", ">&", "&>", ">>", ">|", "|", "&", ";", "\n", "<", ">", "(", ")"]
SEP = {"&&", "||", "|&", ";;", ";&", ";;&", "|", "&", ";", "\n"}
PIPE = {"|", "|&"}  # one more stage of the same pipeline; every other separator starts a new one
REDIRECT = {"&>>", "<<<", "<<", "<>", "<&", ">&", "&>", ">>", ">|", "<", ">"}
PUNCT = set("();<>|&\n")


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
    # The escapes bash decodes inside $'..' -- \xHH, \NNN, \uHHHH, \UHHHHHHHH and the letter escapes -- so
    # $'\x2dn' reaches the judge as the -n bash hands git; an escape this decoder does not know (`\cX`, a control
    # character, never a `-`) stays as written.
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
            out.append(chr(int(m.group(), 16)))
            i += 2 + m.end()
        else:
            out.append(raw[i : i + 2])
            i += 2
    return "".join(out)


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
    pipes, skip = [[[]]], False
    for tok in lex:
        if skip:
            skip = False
            continue
        if not tok or not set(tok) <= PUNCT:
            pipes[-1][-1].append(tok)
            continue
        last = ""
        while tok:
            last = next(op for op in OPS if tok.startswith(op))
            if last in PIPE and pipes[-1][-1]:
                pipes[-1].append([])
            elif last in SEP and pipes[-1][-1]:
                pipes.append([[]])
            tok = tok[len(last) :]
        skip = last in REDIRECT
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


try:
    call = json.load(sys.stdin)
    command = call.get("tool_input", {}).get("command", "")
    if not isinstance(command, str):
        raise ValueError("command is not a string")
except (ValueError, AttributeError) as exc:
    print(f"stdin is not the tool call's JSON ({exc})")
    sys.exit(3)
try:
    commands = pipelines(command)
except ValueError as exc:
    print(f"the command does not tokenise ({exc})")
    sys.exit(3)
raw = clip(" ".join(command.split()))
for pipe in commands:
    for words in pipe:
        judge(words)
    judge_cap(pipe, raw)
PY
)"
if out="$(printf '%s' "$input" | python3 -c "$prog" 2>/dev/null)"; then
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
