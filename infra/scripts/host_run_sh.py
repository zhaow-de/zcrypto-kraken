"""The judge behind infra/scripts/host-run.sh, the one door through which a session runs a block on a fleet host.

The block is read as shell text: quoting, variables, command substitutions, the wrappers that change who runs a
command (`sudo`, `env`, `nohup`, `bash -c`, `xargs`, `docker exec`), pipes, chains and here-documents are seen
through to the commands that would run, and every command is put to each rule in `RULES`. What the judge cannot
resolve -- code computed at run time, a script piped into a shell -- it refuses as unresolvable: the door fails
closed. `fleet_ssh_aliases` is the one parse of docs/reference/fleet.md's host table; tests/test_ops_daily.py
reads the table through it too.

Usage: host_run_sh.py judge --repo <checkout> --alias <alias> [--record --ts <stamp> --timeout <s>]  < block
rc 0 admitted | rc 65 refused | rc 64 a block that is not text.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import os
import re
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

ANY = "\x00"  # an unknown string, slashes included: a variable's value, a command's output
SEG = "\x01"  # an unquoted glob: any string inside one path segment
WILD = ANY + SEG
_ALT_CAP = 16

FLEET_TABLE = Path("docs/reference/fleet.md")
_FLEET_ROW = re.compile(r"^\| `([^`]+)` \| `ssh ([a-z0-9-]+)` \|", re.M)

PRIMARY, SECONDARY, WORKSTATION = "zcrypto", "zcrypto-red", "zcrypto-ops"
MAX_BLOCK = 64 * 1024
HOME = "/home/zcrypto-deploy"

OWNER = "the owner's line"
OWNER_TERMINAL = "the owner's line, at a terminal"
OWNER_WINDOW = "the owner's line, in an attended window"
RESPELL = "yours to respell with what it runs spelled out"


def fleet_ssh_aliases(text: str) -> dict[str, str]:
    """Each host of docs/reference/fleet.md's host table, mapped to the alias of its `ssh <alias>` cell."""
    return dict(_FLEET_ROW.findall(text))


@dataclass(frozen=True)
class Refusal:
    rule: str
    reason: str
    whose: str

    def line(self) -> str:
        return f"host-run: REFUSED ({self.rule}) — {self.reason}; {self.whose}"


class Refused(Exception):
    def __init__(self, refusal: Refusal):
        super().__init__(refusal.line())
        self.refusal = refusal


class Unparsable(Exception):
    pass


def _w(text: str) -> frozenset[str]:
    return frozenset(text.split())


def _unresolvable(reason: str) -> Refused:
    return Refused(Refusal("unresolvable", reason, RESPELL))


def _show(s: str) -> str:
    return s.replace(ANY, "…").replace(SEG, "*")


# ---------------------------------------------------------------- matching with wildcards


def could(a: str, b: str) -> bool:
    """Whether one concrete string matches both `a` and `b`, each a literal carrying ANY and SEG wildcards."""
    seen: set[tuple[int, int]] = set()
    stack = [(0, 0)]
    while stack:
        i, j = stack.pop()
        if (i, j) in seen:
            continue
        seen.add((i, j))
        if i == len(a) and j == len(b):
            return True
        x = a[i] if i < len(a) else None
        y = b[j] if j < len(b) else None
        if x is not None and x in WILD:
            stack.append((i + 1, j))
        if y is not None and y in WILD:
            stack.append((i, j + 1))
        if x is None or y is None:
            continue
        if x in WILD:
            if y not in WILD and (x == ANY or y != "/"):
                stack.append((i, j + 1))
        elif y in WILD:
            if y == ANY or x != "/":
                stack.append((i + 1, j))
        elif x == y:
            stack.append((i + 1, j + 1))
    return False


def does(a: str, b: str) -> bool:
    """`could`, with `a`'s own wildcards standing for nothing in particular: what `a` names outright."""
    return could(a.replace(ANY, "\x05").replace(SEG, "\x05"), b)


def _ancestors(path: str) -> list[str]:
    parts = path.strip("/").split("/")
    return ["/"] + ["/" + "/".join(parts[:k]) for k in range(1, len(parts))]


def could_cover(w: str, path: str) -> bool:
    """Whether `w` could be `path` or an ancestor of it: what removing `w` could take with it."""
    return could(w, path) or any(could(w, a) for a in _ancestors(path))


def could_tree(w: str, root: str) -> bool:
    """Whether `w` could be `root`, an ancestor of it, or a path under it."""
    return could_cover(w, root) or could(w, root + "/" + ANY)


def norm(path: str, cwd: str) -> str:
    """`path` made absolute against `cwd`, its `.`, `..` and doubled slashes folded; wildcards stay put."""
    if not path:
        return path
    if path[0] not in "/" + ANY:
        path = cwd.rstrip("/") + "/" + path
    lead = ANY if path[0] == ANY else ""
    out: list[str] = []
    for seg in path[len(lead) :].split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if out and not any(c in out[-1] for c in WILD):
                out.pop()
            elif out:
                out = [ANY]
            continue
        out.append(seg)
    if lead and not out:
        return lead
    return lead + "/" + "/".join(out)


# ---------------------------------------------------------------- the shell lexer

_OPS = ("&>>", ";;&", "<<<", "<<-", "&&", "||", ";;", ";&", "|&", "&>", "<<", "<>", "<&", ">&", ">>", ">|")
_OPS1 = "|&;()<>"
_REDIR = {"<", ">", ">>", ">|", "<>", "<<", "<<-", "<<<", "&>", "&>>", "<&", ">&"}
_FD = re.compile(r"\d+(?=[<>])")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_ASSIGN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(\[[^]]*\])?\+?=")


@dataclass
class Lit:
    text: str
    quoted: bool


@dataclass
class Var:
    name: str
    quoted: bool
    inner: str = ""


@dataclass
class Sub:
    script: str
    quoted: bool


@dataclass
class Arith:
    text: str


@dataclass
class Proc:
    script: str


@dataclass
class Word:
    parts: list

    def literal(self) -> str | None:
        """The word's text when it is one unquoted literal, as a keyword must be."""
        if len(self.parts) == 1 and isinstance(self.parts[0], Lit) and not self.parts[0].quoted:
            return self.parts[0].text
        return None


@dataclass
class Heredoc:
    delim: str
    strip: bool
    quoted: bool
    body: str = ""


@dataclass
class Redir:
    fd: str
    op: str
    target: Word | None
    heredoc: Heredoc | None = None


def _ansi_c(s: str) -> str:
    out, i = [], 0
    simple = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "v": "\v"}
    while i < len(s):
        c = s[i]
        if c != "\\" or i + 1 >= len(s):
            out.append(c)
            i += 1
            continue
        n = s[i + 1]
        if n in simple:
            out.append(simple[n])
            i += 2
        elif n == "x":
            m = re.match(r"[0-9A-Fa-f]{1,2}", s[i + 2 :])
            out.append(chr(int(m.group(0), 16)) if m else "x")
            i += 2 + (len(m.group(0)) if m else 0)
        elif n in "uU":
            m = re.match(r"[0-9A-Fa-f]{1,8}", s[i + 2 :])
            out.append(chr(int(m.group(0), 16)) if m else n)
            i += 2 + (len(m.group(0)) if m else 0)
        elif n in "01234567":
            m = re.match(r"[0-7]{1,3}", s[i + 1 :])
            out.append(chr(int(m.group(0), 8)))
            i += 1 + len(m.group(0))
        else:
            out.append(n)
            i += 2
    return "".join(out)


class Lexer:
    def __init__(self, text: str):
        self.s = text
        self.i = 0
        self.tokens: list[tuple[str, object]] = []
        self.pending: list[Heredoc] = []

    def run(self) -> list[tuple[str, object]]:
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c in " \t":
                self.i += 1
            elif s.startswith("\\\n", self.i):
                self.i += 2
            elif c == "#":
                while self.i < len(s) and s[self.i] != "\n":
                    self.i += 1
            elif c == "\n":
                self.i += 1
                self.tokens.append(("op", "\n"))
                self._bodies()
            elif s.startswith(("<(", ">("), self.i):
                self.tokens.append(("w", self._word()))
            else:
                fd = ""
                m = _FD.match(s, self.i)
                if m:
                    fd, self.i = m.group(0), m.end()
                op = next((o for o in _OPS if s.startswith(o, self.i)), None)
                if op is None and s[self.i] in _OPS1:
                    op = s[self.i]
                if op is None:
                    self.tokens.append(("w", self._word()))
                    continue
                self.i += len(op)
                if op in _REDIR:
                    self._redir(fd, op)
                else:
                    self.tokens.append(("op", op))
        self._bodies()
        return self.tokens

    def _redir(self, fd: str, op: str) -> None:
        while self.i < len(self.s) and self.s[self.i] in " \t":
            self.i += 1
        if self.i >= len(self.s) or self.s[self.i] in "\n" + _OPS1:
            raise Unparsable(f"a redirection {op} has no target")
        target = self._word()
        doc = None
        if op in ("<<", "<<-"):
            raw = self.s[self._word_start : self.i]
            delim = "".join(p.text if isinstance(p, Lit) else "$" + p.name if isinstance(p, Var) else "" for p in target.parts)
            doc = Heredoc(delim, op == "<<-", any(q in raw for q in "'\"\\"))
            self.pending.append(doc)
        self.tokens.append(("r", Redir(fd, op, target, doc)))

    def _bodies(self) -> None:
        """The bodies of the here-documents the line just ended opened, in order; one the block never closes runs to
        its end, as bash reads it."""
        for doc in self.pending:
            lines = []
            while self.i < len(self.s):
                end = self.s.find("\n", self.i)
                end = len(self.s) if end < 0 else end
                line = self.s[self.i : end]
                self.i = end + 1
                if doc.strip:
                    line = line.lstrip("\t")
                if line == doc.delim:
                    break
                lines.append(line + "\n")
            doc.body = "".join(lines)
        self.pending.clear()

    def _word(self) -> Word:
        s = self.s
        self._word_start = self.i
        parts: list = []
        buf: list[str] = []

        def flush() -> None:
            if buf:
                parts.append(Lit("".join(buf), False))
                buf.clear()

        while self.i < len(s):
            c = s[self.i]
            if s.startswith(("<(", ">("), self.i) and not buf and not parts:
                end = _match_paren(s, self.i + 2)
                parts.append(Proc(s[self.i + 2 : end]))
                self.i = end + 1
                continue
            if c in " \t\n" or c in _OPS1:
                break
            if c == "'":
                end = s.find("'", self.i + 1)
                if end < 0:
                    raise Unparsable("a single quote is not closed")
                flush()
                parts.append(Lit(s[self.i + 1 : end], True))
                self.i = end + 1
            elif c == '"':
                flush()
                self.i += 1
                parts.extend(self._dquote())
            elif c == "\\":
                if s.startswith("\\\n", self.i):
                    self.i += 2
                    continue
                flush()
                parts.append(Lit(s[self.i + 1 : self.i + 2], True))
                self.i += 2
            elif c == "$" and s.startswith('$"', self.i):
                self.i += 1
            elif c == "$":
                flush()
                parts.append(self._dollar(False))
            elif c == "`":
                flush()
                parts.append(self._backtick(False))
            else:
                buf.append(c)
                self.i += 1
        flush()
        return Word(parts)

    def _dquote(self) -> list:
        s = self.s
        parts: list = []
        buf: list[str] = []
        while True:
            if self.i >= len(s):
                raise Unparsable("a double quote is not closed")
            c = s[self.i]
            if c == '"':
                self.i += 1
                break
            if c == "\\" and self.i + 1 < len(s) and s[self.i + 1] in '$`"\\\n':
                if s[self.i + 1] != "\n":
                    buf.append(s[self.i + 1])
                self.i += 2
            elif c == "$":
                if buf:
                    parts.append(Lit("".join(buf), True))
                    buf = []
                parts.append(self._dollar(True))
            elif c == "`":
                if buf:
                    parts.append(Lit("".join(buf), True))
                    buf = []
                parts.append(self._backtick(True))
            else:
                buf.append(c)
                self.i += 1
        if buf:
            parts.append(Lit("".join(buf), True))
        if not parts:
            parts.append(Lit("", True))
        return parts

    def _backtick(self, quoted: bool) -> Sub:
        s = self.s
        j = self.i + 1
        out = []
        while j < len(s) and s[j] != "`":
            if s[j] == "\\" and j + 1 < len(s) and s[j + 1] in "`$\\":
                out.append(s[j + 1])
                j += 2
                continue
            out.append(s[j])
            j += 1
        if j >= len(s):
            raise Unparsable("a backtick is not closed")
        self.i = j + 1
        return Sub("".join(out), quoted)

    def _dollar(self, quoted: bool):
        s = self.s
        i = self.i
        nxt = s[i + 1 : i + 2]
        if s.startswith("$((", i):
            end = _match_paren(s, i + 2)
            if s[end - 1] == ")":
                self.i = end + 1
                return Arith(s[i + 3 : end - 1])
        if nxt == "(":
            end = _match_paren(s, i + 2)
            self.i = end + 1
            return Sub(s[i + 2 : end], quoted)
        if nxt == "{":
            end = _match_brace(s, i + 2)
            self.i = end + 1
            inner = s[i + 2 : end]
            m = re.match(r"(#?)([A-Za-z_][A-Za-z0-9_]*|[0-9]+|[@*#?$!-])(.*)", inner, re.S)
            if not m:
                return Var("", quoted, inner)
            if m.group(1) and m.group(2):
                return Var("", quoted, inner)
            return Var(m.group(2), quoted, m.group(3))
        if nxt == "'" and not quoted:
            j = i + 2
            while j < len(s) and s[j] != "'":
                j += 2 if s[j] == "\\" else 1
            if j >= len(s):
                raise Unparsable("a $'...' string is not closed")
            self.i = j + 1
            return Lit(_ansi_c(s[i + 2 : j]), True)
        m = _NAME.match(s, i + 1)
        if m:
            self.i = m.end()
            return Var(m.group(0), quoted)
        if nxt and (nxt.isdigit() or nxt in "@*#?$!-"):
            self.i = i + 2
            return Var(nxt, quoted)
        self.i = i + 1
        return Lit("$", True)


def _skip_quoted(s: str, j: int) -> int:
    """The index past the quoted string or escape that opens at `j`."""
    c = s[j]
    if c == "\\":
        return j + 2
    if c == "'":
        end = s.find("'", j + 1)
        if end < 0:
            raise Unparsable("a single quote is not closed")
        return end + 1
    k = j + 1
    while k < len(s) and s[k] != '"':
        k += 2 if s[k] == "\\" else 1
    if k >= len(s):
        raise Unparsable("a double quote is not closed")
    return k + 1


def _match_paren(s: str, j: int) -> int:
    depth = 1
    while j < len(s):
        c = s[j]
        if c in "\\'\"":
            j = _skip_quoted(s, j)
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise Unparsable("a parenthesis is not closed")


def _match_brace(s: str, j: int) -> int:
    depth = 1
    while j < len(s):
        c = s[j]
        if c in "\\'\"":
            j = _skip_quoted(s, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise Unparsable("a ${ is not closed")


def heredoc_parts(body: str) -> list:
    """An unquoted here-document's body as word parts: only `$`, backticks and their escapes are special in it."""
    lx = Lexer(body)
    parts: list = []
    buf: list[str] = []
    while lx.i < len(body):
        c = body[lx.i]
        if c == "\\" and lx.i + 1 < len(body) and body[lx.i + 1] in "$`\\\n":
            if body[lx.i + 1] != "\n":
                buf.append(body[lx.i + 1])
            lx.i += 2
        elif c in "$`":
            if buf:
                parts.append(Lit("".join(buf), True))
                buf = []
            parts.append(lx._dollar(True) if c == "$" else lx._backtick(True))
        else:
            buf.append(c)
            lx.i += 1
    if buf:
        parts.append(Lit("".join(buf), True))
    return parts


# ---------------------------------------------------------------- the parser


@dataclass
class Simple:
    words: list[Word] = field(default_factory=list)
    assigns: list[tuple[str, Word, bool]] = field(default_factory=list)
    redirs: list[Redir] = field(default_factory=list)
    piped: bool = False


@dataclass
class ForBind:
    name: str
    words: list[Word] | None


@dataclass
class Group:
    opens: bool


_SKIP = {"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "{", "}", "!", "coproc"}
_SEPARATORS = {"\n", ";", "&", "&&", "||", "|", "|&", ";;", ";&", ";;&"}


def _assignment(word: Word) -> tuple[str, Word, bool] | None:
    first = word.parts[0] if word.parts else None
    if not isinstance(first, Lit) or first.quoted:
        return None
    m = _ASSIGN.match(first.text)
    if not m:
        return None
    name = m.group(0).rstrip("=").rstrip("+")
    name = name.split("[", 1)[0]
    rest = [Lit(first.text[m.end() :], False)] if first.text[m.end() :] else []
    return name, Word(rest + word.parts[1:] or [Lit("", True)]), m.group(0).endswith("+=")


def parse(text: str) -> list:
    tokens = Lexer(text).run()
    nodes: list = []
    cur: Simple | None = None
    piped = False
    cases = 0
    pattern = False
    i = 0

    def finish() -> None:
        nonlocal cur
        if cur is not None:
            nodes.append(cur)
            cur = None

    def word_at(k: int) -> str | None:
        return tokens[k][1].literal() if k < len(tokens) and tokens[k][0] == "w" else None

    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "op":
            if pattern:
                if val == ")":
                    pattern = False
                i += 1
                continue
            if val in _SEPARATORS:
                finish()
                piped = val in ("|", "|&")
                if val in (";;", ";&", ";;&") and cases:
                    pattern = True
                i += 1
                continue
            if val == "(":
                if cur is None:
                    if i + 1 < len(tokens) and tokens[i + 1] == ("op", "("):
                        depth, i = 0, i + 2
                        while i < len(tokens) and not (tokens[i] == ("op", ")") and depth == 0):
                            depth += {("op", "("): 1, ("op", ")"): -1}.get(tokens[i], 0)
                            i += 1
                        i += 2
                        continue
                    nodes.append(Group(True))
                    i += 1
                    continue
                if len(cur.words) == 1 and not cur.assigns and i + 1 < len(tokens) and tokens[i + 1] == ("op", ")"):
                    cur = None
                    i += 2
                    continue
                if cur.assigns and not cur.words and i > 0 and tokens[i - 1][0] == "w":
                    name, _, append = cur.assigns[-1]
                    cur.assigns[-1] = (name, Word([Var("", False)]), append)
                    depth = 1
                    i += 1
                    while i < len(tokens) and depth:
                        depth += {("op", "("): 1, ("op", ")"): -1}.get(tokens[i], 0)
                        i += 1
                    continue
                raise Unparsable("a ( where a word was expected")
            if val == ")":
                finish()
                nodes.append(Group(False))
                i += 1
                continue
            raise Unparsable(f"an unexpected {val}")
        if pattern:
            if kind == "w" and val.literal() == "esac":
                pattern = False
                cases = max(cases - 1, 0)
            i += 1
            continue
        if kind == "r":
            if cur is None:
                cur = Simple(piped=piped)
                piped = False
            cur.redirs.append(val)
            i += 1
            continue
        lit = val.literal()
        if cur is None:
            if lit in _SKIP:
                i += 1
                continue
            if lit == "esac":
                cases = max(cases - 1, 0)
                i += 1
                continue
            if lit == "time":
                i += 2 if word_at(i + 1) == "-p" else 1
                continue
            if lit in ("for", "select"):
                name = word_at(i + 1)
                if name is None and i + 1 < len(tokens) and tokens[i + 1] == ("op", "("):
                    i += 1
                    depth = 0
                    while i < len(tokens):
                        depth += {("op", "("): 1, ("op", ")"): -1}.get(tokens[i], 0)
                        i += 1
                        if depth == 0:
                            break
                    continue
                i += 2
                words = None
                if word_at(i) == "in":
                    words = []
                    i += 1
                    while i < len(tokens) and tokens[i][0] == "w" and word_at(i) != "do":
                        words.append(tokens[i][1])
                        i += 1
                nodes.append(ForBind(name or "", words))
                continue
            if lit == "case":
                if i + 1 < len(tokens) and tokens[i + 1][0] == "w":
                    nodes.append(Simple(words=[Word([Lit(":", False)]), tokens[i + 1][1]]))
                i += 3 if word_at(i + 2) == "in" else 2
                cases += 1
                pattern = True
                continue
            if lit == "function":
                i += 2
                if i + 1 < len(tokens) and tokens[i] == ("op", "(") and tokens[i + 1] == ("op", ")"):
                    i += 2
                continue
            if lit == "[[":
                words = [val]
                i += 1
                while i < len(tokens) and word_at(i) != "]]":
                    k, v = tokens[i]
                    if k == "w":
                        words.append(v)
                    elif k == "op":
                        words.append(Word([Lit(v, True)]))
                    i += 1
                nodes.append(Simple(words=words + [Word([Lit("]]", False)])], piped=piped))
                piped = False
                i += 1
                continue
            cur = Simple(piped=piped)
            piped = False
        if not cur.words and (a := _assignment(val)) is not None:
            cur.assigns.append(a)
        else:
            cur.words.append(val)
        i += 1
    finish()
    return nodes


# ---------------------------------------------------------------- the commands a block would run


@dataclass
class Scope:
    vars: dict[str, list[str]] = field(default_factory=dict)
    cwd: str = HOME
    saved: list[str] = field(default_factory=list)

    def child(self) -> Scope:
        return Scope(dict(self.vars), self.cwd, [])


@dataclass(frozen=True)
class Ctx:
    alias: str
    container: str | None = None
    depth: int = 0


@dataclass
class Cmd:
    argv: list[str]
    alias: str
    cwd: str
    container: str | None = None
    redirs: list[tuple[str, str]] = field(default_factory=list)
    layer: str = "command"
    code: str | None = None
    lang: str | None = None
    env_reads: tuple[str, ...] = ()
    rest: list[str] = field(default_factory=list)
    flags: frozenset[str] = frozenset()

    @property
    def name(self) -> str:
        return self.argv[0].rsplit("/", 1)[-1] if self.argv else ""

    @property
    def args(self) -> list[str]:
        return self.argv[1:]

    def path(self, s: str) -> str:
        return norm(s, self.cwd)


_LINE_FILTERS = {"head", "tail", "sort", "uniq", "grep"}
_NO_SLASH_OUTPUT = {"date", "hostname", "id", "whoami", "uname", "nproc", "seq", "expr", "basename", "uuidgen", "pidof", "pgrep"}
_SAFE_VARS = _w(
    "HOME PATH PWD OLDPWD HOSTNAME USER LOGNAME SHELL TERM IFS RANDOM SECONDS LINENO BASH BASHPID PPID UID EUID REPLY"
) | {""}
_SHELLS = {"bash", "sh", "dash", "zsh", "ksh", "mksh", "ash"}
_PY = re.compile(r"(python[0-9.]*|pypy[0-9.]*)$")
_INTERPRETERS = {"perl": "-e", "ruby": "-e", "node": "-e", "nodejs": "-e", "php": "-r"}
_AWKS = {"awk", "gawk", "mawk", "nawk"}
_COPIERS = {"cp", "mv", "install", "ln", "tee", "touch", "dd", "rsync", "curl", "wget"}
_CODE_DIRS = _w(
    "/etc/systemd /lib/systemd /usr/lib/systemd /etc/cron.d /etc/cron.daily /etc/cron.hourly /etc/crontab "
    "/var/spool/cron /etc/init.d /etc/rc.local /etc/profile.d /etc/profile /etc/bash.bashrc /etc/sudoers "
    "/etc/sudoers.d /usr/local/bin /usr/local/sbin /etc/udev/rules.d /etc/ld.so.preload /root/.bashrc /root/.profile "
    f"{HOME}/.bashrc {HOME}/.profile"
)


def _opts(
    args: list[str], short_value: str = "", long_value: frozenset[str] | set[str] = frozenset(), stop_at_operand: bool = False
) -> tuple[list[tuple[str, str | None]], list[str]]:
    """Split `args` into options (each with its value, if it takes one) and operands."""
    opts: list[tuple[str, str | None]] = []
    operands: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            operands.extend(args[i + 1 :])
            break
        if a.startswith("--") and len(a) > 2:
            key, eq, val = a.partition("=")
            if not eq and key in long_value:
                i += 1
                val = args[i] if i < len(args) else ""
            opts.append((key, val if (eq or key in long_value) else None))
        elif a.startswith("-") and len(a) > 1 and a[1] != ANY:
            j = 1
            while j < len(a):
                ch = a[j]
                if ch in short_value:
                    val = a[j + 1 :]
                    if not val:
                        i += 1
                        val = args[i] if i < len(args) else ""
                    opts.append(("-" + ch, val))
                    break
                opts.append(("-" + ch, None))
                j += 1
        else:
            operands.append(a)
            if stop_at_operand:
                operands.extend(args[i + 1 :])
                break
        i += 1
    return opts, operands


def _has(opts: list[tuple[str, str | None]], *names: str) -> bool:
    return any(k in names for k, _ in opts)


def _values(opts: list[tuple[str, str | None]], *names: str) -> list[str]:
    return [v for k, v in opts if k in names and v is not None]


class Judge:
    def __init__(self, alias: str, aliases: dict[str, str]):
        self.alias = alias
        self.primary = aliases.get(PRIMARY)
        self.secondary = aliases.get(SECONDARY)
        self.workstation = aliases.get(WORKSTATION)
        self.created: list[str] = []
        self._parsed: dict[str, list] = {}

    # -- entry

    def block(self, text: str) -> Refusal | None:
        try:
            self.script(text, Ctx(self.alias), Scope())
        except Refused as r:
            return r.refusal
        except Unparsable as e:
            return Refusal("unresolvable", f"the block does not parse as shell: {e}", RESPELL)
        except RecursionError:
            return Refusal("unresolvable", "the block nests too deep to read", RESPELL)
        return None

    def parsed(self, text: str) -> list:
        if text not in self._parsed:
            self._parsed[text] = parse(text)
        return self._parsed[text]

    def script(self, text: str, ctx: Ctx, scope: Scope) -> None:
        if ctx.depth > 16:
            raise _unresolvable("scripts nest deeper than 16")
        for node in self.parsed(text):
            if isinstance(node, Group):
                if node.opens:
                    scope.saved.append(scope.cwd)
                elif scope.saved:
                    scope.cwd = scope.saved.pop()
            elif isinstance(node, ForBind):
                vals = [v for w in node.words for v in self.expand(w, ctx, scope)] if node.words is not None else [ANY]
                scope.vars[node.name] = vals[:_ALT_CAP] if len(vals) <= _ALT_CAP else [ANY]
            else:
                self.simple(node, ctx, scope)

    def nested(self, text: str, ctx: Ctx, scope: Scope) -> None:
        if ANY in text:
            raise _unresolvable(f"it runs a script built from a value the block does not hold ({_show(text)[:80]})")
        self.script(text.replace(SEG, "*"), replace(ctx, depth=ctx.depth + 1), scope)

    # -- expansion

    def expand(self, word: Word, ctx: Ctx, scope: Scope, reads: list[str] | None = None) -> list[str]:
        alts = [""]
        for k, part in enumerate(word.parts):
            if isinstance(part, Lit):
                text = part.text
                if not part.quoted:
                    if k == 0 and text.startswith("~"):
                        user, slash, rest = text[1:].partition("/")
                        text = (HOME if not user else "/root" if user == "root" else "/home/" + user) + slash + rest
                    text = re.sub(r"\[[^]/]+\]|[*?]", SEG, text)
                    text = text.replace("{", "\x02").replace("}", "\x03").replace(",", "\x04")
                vals = [text]
            elif isinstance(part, Var):
                if "$(" in part.inner or "`" in part.inner:
                    for p in heredoc_parts(part.inner):
                        if isinstance(p, Sub):
                            self.nested(p.script, ctx, scope.child())
                if part.name in scope.vars and not part.inner.startswith(("#", "%", "/", "^", ",")):
                    vals = scope.vars[part.name]
                elif part.name == "HOME":
                    vals = [HOME]
                elif part.name == "PWD":
                    vals = [scope.cwd]
                else:
                    vals = [ANY]
                    if (
                        reads is not None
                        and part.name not in scope.vars
                        and part.name not in _SAFE_VARS
                        and not re.fullmatch(r"[0-9@*#?$!-]", part.name)
                    ):
                        reads.append(part.name)
            elif isinstance(part, Sub):
                vals = self.substitution(part.script, ctx, scope)
            elif isinstance(part, Proc):
                self.nested(part.script, ctx, scope.child())
                vals = ["/dev/fd/" + ANY]
            else:
                for p in heredoc_parts(part.text):
                    if isinstance(p, Sub):
                        self.nested(p.script, ctx, scope.child())
                vals = [SEG]
            alts = [a + v for a in alts for v in vals]
            if len(alts) > _ALT_CAP:
                alts = [ANY]
        out: list[str] = []
        for a in alts:
            out.extend(_braces(a))
        if len(out) > _ALT_CAP:
            return [ANY]
        return [o.replace("\x02", "{").replace("\x03", "}").replace("\x04", ",") for o in out]

    def substitution(self, script: str, ctx: Ctx, scope: Scope) -> list[str]:
        """Judge a command substitution's script; its output modelled where the command only echoes paths."""
        inner = scope.child()
        self.nested(script, ctx, inner)
        nodes = [n for n in self.parsed(script) if isinstance(n, Simple)]
        if (
            not nodes
            or not nodes[0].words
            or not all(n.piped and n.words and n.words[0].literal() in _LINE_FILTERS for n in nodes[1:])
        ):
            return [ANY]
        argv = [a[0] for a in (self.expand(w, ctx, inner.child()) for w in nodes[0].words)]
        while argv and argv[0].rsplit("/", 1)[-1] in ("sudo", "command", "nohup"):
            argv = [a for a in argv[1:] if not a.startswith("-")] if argv[0].endswith("sudo") else argv[1:]
        if not argv:
            return [ANY]
        name, args = argv[0].rsplit("/", 1)[-1], [a for a in argv[1:] if not a.startswith("-")]
        if name == "pwd":
            return [inner.cwd]
        if name == "echo" and args:
            return args[:_ALT_CAP]
        if name in _NO_SLASH_OUTPUT or name == "printf" and args and not re.search(r"%[-0-9.]*[sbq]", args[0]):
            return [SEG]
        if name in ("ls", "realpath", "readlink") and args and all(SEG in a for a in args):
            return [norm(a, inner.cwd) for a in args][:_ALT_CAP]
        if name == "find" and args:
            return [norm(a, inner.cwd) + "/" + ANY for a in args[:1]]
        if name == "dirname" and args:
            return [norm(args[0], inner.cwd).rsplit("/", 1)[0] or "/"]
        return [ANY]

    def text_of(self, body: str, ctx: Ctx, scope: Scope) -> str:
        """An unquoted here-document's body after the expansions the calling shell makes."""
        vals = self.expand(Word(heredoc_parts(body)), ctx, scope)
        return vals[0] if len(vals) == 1 else ANY

    def argvs(self, words: list[Word], ctx: Ctx, scope: Scope, reads: list[str]) -> list[list[str]]:
        per = [self.expand(w, ctx, scope, reads) for w in words]
        per = [[a for a in alts if a != ""] or [""] for alts in per]
        total = 1
        for alts in per:
            total *= len(alts)
        if total > _ALT_CAP:
            per = [alts if len(alts) == 1 else [ANY] for alts in per]
        out = []
        for combo in itertools.product(*per):
            argv = [a for a, w in zip(combo, words) if a != "" or _quoted(w)]
            out.append(argv)
        return out

    # -- one simple command

    def simple(self, node: Simple, ctx: Ctx, scope: Scope) -> None:
        reads: list[str] = []
        for name, value, append in node.assigns:
            vals = self.expand(value, ctx, scope, reads)
            if node.words:
                continue
            if append:
                vals = [p + v for p in scope.vars.get(name, [""]) for v in vals][:_ALT_CAP]
            scope.vars[name] = vals
            if name == "PATH":
                self.path_check(vals)
        redirs, stdin = self.redirections(node, ctx, scope, reads)
        if redirs:
            self.apply(Cmd([], ctx.alias, scope.cwd, ctx.container, redirs=redirs))
        if not node.words:
            if ctx.container and reads:
                self.apply(Cmd(["export"], ctx.alias, scope.cwd, ctx.container, env_reads=tuple(reads)))
            return
        alts = self.argvs(node.words, ctx, scope, reads)
        for argv in alts:
            if argv:
                self.command(argv, stdin, ctx, scope, tuple(reads))
        if alts and alts[0]:
            self.builtin(alts, ctx, scope)

    def redirections(self, node: Simple, ctx: Ctx, scope: Scope, reads: list[str]):
        out: list[tuple[str, str]] = []
        stdin: tuple[str, str | None] | None = ("pipe", None) if node.piped else None
        for r in node.redirs:
            if r.heredoc is not None:
                body = r.heredoc.body if r.heredoc.quoted else self.text_of(r.heredoc.body, ctx, scope)
                if r.fd in ("", "0"):
                    stdin = ("heredoc", body)
                continue
            if r.op == "<<<":
                vals = self.expand(r.target, ctx, scope, reads)
                stdin = ("herestring", vals[0] if len(vals) == 1 else ANY)
                continue
            vals = self.expand(r.target, ctx, scope, reads)
            if r.op in (">&", "<&") and all(re.fullmatch(r"\d+-?|-", v) for v in vals):
                continue
            for v in vals:
                p = norm(v, scope.cwd)
                op = ">" if r.op == ">&" else r.op
                out.append((op, p))
                if op in ("<", "<>") and r.fd in ("", "0"):
                    stdin = ("file", p)
        return out, stdin

    def path_check(self, vals: list[str]) -> None:
        for v in vals:
            for d in v.split(":"):
                if any(could(c, norm(d, "/") + "/" + SEG) for c in self.created):
                    raise _unresolvable(f"PATH goes through {_show(d)}, where this block wrote a file it may then run")

    def executes(self, path: str, what: str) -> None:
        if any(could(path, c) for c in self.created):
            raise _unresolvable(f"{what} {_show(path)}, a file this block wrote: what it runs is not in the block")

    def builtin(self, alts: list[list[str]], ctx: Ctx, scope: Scope) -> None:
        argv = alts[0]
        name = argv[0]
        args = argv[1:]
        if name in ("cd", "pushd"):
            dests = set()
            for alt in alts:
                o = [a for a in alt[1:] if not a.startswith("-") or a == "-"]
                dest = o[0] if o else (HOME if name == "cd" else ANY)
                dests.add(ANY if dest == "-" else norm(dest, scope.cwd))
            if name == "pushd":
                scope.saved.append(scope.cwd)
            scope.cwd = dests.pop() if len(dests) == 1 else ANY
        elif name == "popd":
            scope.cwd = scope.saved.pop() if scope.saved else ANY
        elif name in ("export", "declare", "typeset", "local", "readonly"):
            for a in args:
                if "=" in a and _NAME.fullmatch(a.split("=", 1)[0].rstrip("+")):
                    k, _, v = a.partition("=")
                    scope.vars[k.rstrip("+")] = [v]
                    if k == "PATH":
                        self.path_check([v])
        elif name in ("read", "mapfile", "readarray"):
            _, operands = _opts(args, "dpntua" if name == "read" else "dnOsuC")
            for a in operands or ["REPLY"]:
                if _NAME.fullmatch(a):
                    scope.vars[a] = [ANY]
        elif name == "unset":
            for a in args:
                scope.vars.pop(a, None)
        elif name == "alias":
            for a in args:
                if "=" in a:
                    self.nested(a.split("=", 1)[1], ctx, scope.child())
        elif name == "trap" and args and not args[0].startswith("-"):
            self.nested(args[0], ctx, scope.child())

    def apply(self, cmd: Cmd) -> None:
        """Put one command to every rule; record what it writes, for a later command that would run it."""
        for rule in RULES:
            refusal = rule(cmd, self)
            if refusal is not None:
                raise Refused(refusal)
        writes = [p for op, p in cmd.redirs if op != "<"]
        if cmd.layer != "wrapper" and cmd.name in _COPIERS:
            writes += [p for effect, p in _gate_effects(cmd) if effect == "create"]
        for p in writes:
            if any(could_tree(p, d) for d in _CODE_DIRS):
                raise _unresolvable(f"it writes {_show(p)}, code that runs later outside the block")
            self.created.append(p)

    # -- what a command is, through its wrappers

    def command(self, argv: list[str], stdin, ctx: Ctx, scope: Scope, reads: tuple[str, ...] = ()) -> None:
        first = argv[0]
        if any(c in first for c in WILD):
            raise _unresolvable(f"the command's name is computed at run time ({_show(first)})")
        if "/" in first:
            self.executes(norm(first, scope.cwd), "it runs")
        name = first.rsplit("/", 1)[-1]
        args = argv[1:]
        base = Cmd(argv, ctx.alias, scope.cwd, ctx.container, env_reads=reads if ctx.container else ())

        if name == "eval":
            raise _unresolvable("eval runs text the block computes at run time")
        if name in ("sudo", "doas"):
            opts, rest = _opts(
                args,
                "ugCDhpRTUrt",
                _w("--user --group --chdir --host --prompt --close-from --chroot --command-timeout --other-user --role --type"),
                stop_at_operand=True,
            )
            flags = {k for k, _ in opts}
            longs = {"--login": "-i", "--shell": "-s", "--stdin": "-S", "--edit": "-e"}
            flags |= {longs[k] for k in flags if k in longs}
            while rest and _ASSIGN.match(rest[0]):
                rest = rest[1:]
            self.apply(replace(base, layer="wrapper", rest=rest, flags=frozenset(flags)))
            if not rest or "-e" in flags:
                return
            inner = scope.child() if "-i" in flags or _values(opts, "-D", "--chdir") else scope
            if "-i" in flags:
                inner.cwd = "/root"
            for d in _values(opts, "-D", "--chdir"):
                inner.cwd = norm(d, scope.cwd)
            self.command(rest, stdin, ctx, inner)
            return
        if name == "env":
            opts, rest = _opts(args, "uCS", {"--unset", "--chdir", "--split-string"}, stop_at_operand=True)
            split = _values(opts, "-S", "--split-string")
            while rest and _ASSIGN.match(rest[0]):
                rest = rest[1:]
            if split:
                rest = split[0].split() + rest
            self.apply(replace(base, layer="wrapper" if rest else "command", rest=rest))
            if rest:
                inner = scope.child() if _values(opts, "-C", "--chdir") else scope
                for d in _values(opts, "-C", "--chdir"):
                    inner.cwd = norm(d, scope.cwd)
                self.command(rest, stdin, ctx, inner)
            return
        wrapped = self.unwrap(name, args)
        if wrapped is not None:
            rest, script = wrapped
            self.apply(replace(base, layer="wrapper", rest=rest))
            if script is not None:
                self.nested(script, ctx, scope.child())
            if rest:
                self.command(rest, stdin, ctx, scope)
            return
        if name == "busybox" and args:
            self.command(args, stdin, ctx, scope)
            return
        if name in _SHELLS:
            self.shell(base, stdin, ctx, scope)
            return
        if _PY.fullmatch(name) or name in _INTERPRETERS:
            self.interpreter(base, stdin, ctx, scope)
            return
        if name in _AWKS:
            opts, operands = _opts(args, "fvFiE", {"--file", "--assign", "--field-separator", "--include"})
            if not _values(opts, "-f", "--file") and operands:
                _no_spawn(name, operands[0])
                base = replace(base, code=operands[0], lang="awk")
            self.apply(base)
            return
        if name == "sed":
            opts, operands = _opts(args, "eflsS", {"--expression", "--file", "--line-length"})
            code = _values(opts, "-e", "--expression")
            if not code and not _values(opts, "-f", "--file") and operands:
                code = [operands[0]]
            if any(_SED_EXEC.search(c) for c in code):
                raise _unresolvable("its sed script runs a command (the e command or flag)")
            self.apply(replace(base, code="\n".join(code) or None, lang="sed"))
            return
        if name in (".", "source"):
            target = norm(args[0], scope.cwd) if args else ANY
            if not args or target.startswith("/dev/fd/") or target in ("/dev/stdin", "/proc/self/fd/0"):
                raise _unresolvable("it sources a script that is not in the block")
            self.executes(target, "it sources")
            self.apply(base)
            return
        if name == "find":
            self.find(base, ctx, scope)
            return
        if name == "xargs":
            opts, rest = _opts(
                args,
                "adEILnPs",
                _w("--arg-file --delimiter --eof --replace --max-lines --max-args --max-procs --max-chars --process-slot-var"),
                stop_at_operand=True,
            )
            self.apply(replace(base, layer="wrapper", rest=rest, flags=frozenset(k for k, _ in opts)))
            rest = rest or ["echo"]
            repl = _values(opts, "-I", "--replace") or (["{}"] if _has(opts, "-i") else [])
            inner = [a.replace(repl[0], ANY) for a in rest] if repl else rest + [ANY]
            if inner[0].rsplit("/", 1)[-1] in _SHELLS and any("c" in a[1:] for a in inner[1:] if a.startswith("-")):
                raise _unresolvable("xargs feeds its input into a shell's script")
            self.command(inner, None, ctx, scope)
            return
        if name in ("at", "batch"):
            opts, _ = _opts(args, "qfmMt")
            files = _values(opts, "-f")
            if files:
                self.executes(norm(files[0], scope.cwd), "it schedules")
            elif stdin and stdin[0] in ("heredoc", "herestring") and stdin[1] is not None:
                self.nested(stdin[1], ctx, scope.child())
            elif stdin is not None:
                raise _unresolvable("at reads its script from another command's output")
            self.apply(base)
            return
        if name == "crontab" and args and not any(a in ("-l", "-r", "-e") for a in args):
            raise _unresolvable("a crontab installed from a file or a pipe runs what the block does not show")
        if name == "chroot":
            raise _unresolvable("paths inside a chroot cannot be matched to the host's")
        if name in ("docker", "docker-compose"):
            self.docker(base, ctx, scope)
            return
        self.apply(base)

    def unwrap(self, name: str, args: list[str]) -> tuple[list[str], str | None] | None:
        """A wrapper that runs another command as itself: the command, and a script it takes as a string."""
        if name in ("nohup", "builtin", "unbuffer", "chronic", "catchsegv", "caffeinate"):
            return args, None
        if name == "command":
            return ([] if any(a in ("-v", "-V") for a in args) else [a for a in args if a != "-p"]), None
        if name == "exec":
            return _opts(args, "a", stop_at_operand=True)[1], None
        if name == "setsid":
            return _opts(args, "", stop_at_operand=True)[1], None
        if name == "nice":
            return _opts([a for a in args if not re.fullmatch(r"-\d+", a)], "n", {"--adjustment"}, True)[1], None
        if name == "ionice":
            opts, rest = _opts(args, "cnp", {"--class", "--classdata", "--pid"}, True)
            return ([] if _has(opts, "-p", "--pid") else rest), None
        if name == "stdbuf":
            return _opts(args, "ioe", {"--input", "--output", "--error"}, True)[1], None
        if name == "time":
            return _opts(args, "fo", {"--format", "--output"}, True)[1], None
        if name == "timeout":
            rest = _opts(args, "sk", {"--signal", "--kill-after"}, True)[1]
            return rest[1:], None
        if name in ("chrt", "taskset"):
            _, rest = _opts(args, "cT" if name == "chrt" else "", {"--cpu-list"}, True)
            return rest[1:], None
        if name == "flock":
            _, rest = _opts(args, "Ew", {"--conflict-exit-code", "--timeout", "--wait"}, True)
            rest = rest[1:]
            if rest[:1] in (["-c"], ["--command"]):
                return [], rest[1] if len(rest) > 1 else ""
            return rest, None
        if name in ("su", "sg"):
            opts, rest = _opts(
                ["-l" if a == "-" else a for a in args],
                "c" if name == "sg" else "cgGs",
                {"--command", "--session-command", "--group", "--supp-group", "--shell"},
            )
            script = (_values(opts, "-c", "--command", "--session-command") or [None])[0]
            if name == "sg" and script is None:
                return rest[1:], None
            return [], script
        if name == "runuser":
            opts, rest = _opts(
                args, "ugGsc", {"--user", "--group", "--supp-group", "--shell", "--command", "--session-command"}, True
            )
            script = (_values(opts, "-c", "--command", "--session-command") or [None])[0]
            return (rest if _has(opts, "-u", "--user") else []), script
        if name == "systemd-run":
            opts, rest = _opts(
                args,
                "upEMHG",
                _w(
                    "--unit --property --setenv --machine --host --uid --gid --nice --working-directory --slice "
                    "--description --service-type --on-active --on-boot --on-startup --on-unit-active "
                    "--on-unit-inactive --on-calendar --on-clock-change --on-timezone-change --timer-property "
                    "--path-property --socket-property --expand-environment --slice-inherit"
                ),
                True,
            )
            return rest, None
        if name == "nsenter":
            return _opts(args, "tSGrwW", {"--target", "--setuid", "--setgid", "--root", "--wd"}, True)[1], None
        if name == "unshare":
            return _opts(args, "S", {"--setuid", "--setgid", "--map-user", "--map-group"}, True)[1], None
        if name == "ip" and args[:2] == ["netns", "exec"]:
            return args[3:], None
        if name == "watch":
            return _opts(args, "nd", {"--interval", "--differences"}, True)[1], None
        return None

    def shell(self, base: Cmd, stdin, ctx: Ctx, scope: Scope) -> None:
        opts, operands = _opts(base.args, "oO", {"--rcfile", "--init-file"}, stop_at_operand=True)
        flags = frozenset(k for k, _ in opts)
        cmd = replace(base, flags=flags)
        if "-c" in flags:
            self.apply(cmd)
            if not operands:
                raise _unresolvable("a shell's -c has no script")
            self.nested(operands[0], ctx, scope.child())
            return
        if operands and operands[0] != "-":
            script = norm(operands[0], scope.cwd)
            if script.startswith("/dev/fd/"):
                raise _unresolvable("a shell reads its script from another command's output")
            if script not in ("/dev/stdin", "/proc/self/fd/0"):
                self.executes(script, "it runs")
                self.apply(replace(cmd, layer="script", rest=operands))
                return
        self.apply(cmd)
        self.stdin_script(stdin, ctx, scope, "a shell")

    def stdin_script(self, stdin, ctx: Ctx, scope: Scope, who: str) -> str | None:
        if stdin is None:
            return None
        kind, text = stdin
        if kind in ("heredoc", "herestring"):
            self.nested(text, ctx, scope.child())
            return text
        if kind == "file":
            self.executes(text, f"{who} reads its script from")
            return None
        raise _unresolvable(f"{who} reads its script from another command's output")

    def interpreter(self, base: Cmd, stdin, ctx: Ctx, scope: Scope) -> None:
        name = base.name
        flag = _INTERPRETERS.get(name, "-c")
        value = "WXm" if _PY.fullmatch(name) else ("ImMxCFE" if name == "perl" else "IrSE")
        long_value = {"--eval", "--print", "--require", "--import", "--input-type"}
        if name in ("node", "nodejs"):
            value = "er"
        opts, operands = _opts(base.args, value + flag[1], long_value, stop_at_operand=True)
        code = _values(opts, flag, "-E", "--eval", "--print", "-p") if name != "php" else _values(opts, "-r")
        flags = frozenset(k for k, _ in opts)
        cmd = replace(base, flags=flags, lang=name, layer="script")
        if code and ANY in code[0]:
            raise _unresolvable(f"{name}'s code is built from a value the block does not hold")
        if code:
            _no_spawn(name, code[0])
            self.apply(replace(cmd, code=code[0], rest=operands))
            return
        if _has(opts, "-m"):
            self.apply(replace(cmd, rest=operands))
            return
        if operands and operands[0] != "-":
            if norm(operands[0], scope.cwd).startswith("/dev/fd/"):
                raise _unresolvable(f"{name} reads its script from another command's output")
            self.executes(norm(operands[0], scope.cwd), "it runs")
            self.apply(replace(cmd, rest=operands))
            return
        if stdin is None:
            self.apply(replace(cmd, rest=operands[1:]))
            return
        kind, text = stdin
        if kind in ("heredoc", "herestring"):
            if ANY in text:
                raise _unresolvable(f"{name}'s code is built from a value the block does not hold")
            _no_spawn(name, text)
            self.apply(replace(cmd, code=text, rest=operands[1:]))
            return
        if kind == "file":
            self.executes(text, "it reads its script from")
            self.apply(cmd)
            return
        raise _unresolvable(f"{name} reads its script from another command's output")

    def find(self, base: Cmd, ctx: Ctx, scope: Scope) -> None:
        args = base.args
        i = 0
        while i < len(args) and (args[i] in ("-H", "-L", "-P") or args[i].startswith("-O")):
            i += 1
        if i < len(args) and args[i] == "-D":
            i += 2
        starts = []
        while i < len(args) and not args[i].startswith(("-", "(", "!", ")")):
            starts.append(norm(args[i], scope.cwd))
            i += 1
        starts = starts or [scope.cwd]
        names = [args[k + 1] for k in range(i, len(args) - 1) if args[k] in ("-name", "-iname")]
        if len(names) == 1 and not {"-o", "-or"} & set(args[i:]):
            found = [s + ANY + "/" + re.sub(r"\[[^]/]+\]|[*?]", SEG, names[0]) for s in starts]
        else:
            found = [s + "/" + ANY for s in starts]
        writes: list[tuple[str, str]] = []
        while i < len(args):
            a = args[i]
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                j = i + 1
                while j < len(args) and args[j] not in (";", "+"):
                    j += 1
                inner = args[i + 1 : j]
                if not inner:
                    raise _unresolvable("find's -exec names no command")
                for f in found:
                    self.command([x.replace("{}", f) for x in inner], None, ctx, scope)
                i = j + 1
                continue
            if a == "-delete":
                writes.extend(("rm", f) for f in found)
            if a in ("-fprint", "-fprint0", "-fprintf", "-fls") and i + 1 < len(args):
                writes.append((">", norm(args[i + 1], scope.cwd)))
            i += 1
        self.apply(replace(base, redirs=[(">", p) for op, p in writes if op == ">"], rest=[p for op, p in writes if op == "rm"]))

    def docker(self, base: Cmd, ctx: Ctx, scope: Scope) -> None:
        self.apply(base)
        d = docker_parse(base)
        if d.verb in ("exec", "run", "create") and d.inner:
            if ctx.container is not None:
                raise _unresolvable("a docker call inside a container")
            self.command(d.inner, None, replace(ctx, container=d.target or ANY), scope.child())


def _no_spawn(name: str, code: str) -> None:
    if m := _SPAWN_CODE.search(code):
        raise _unresolvable(f"its {name} code starts another process ({m.group(0)}), which the judge cannot read")


def _quoted(word: Word) -> bool:
    return any(getattr(p, "quoted", False) for p in word.parts)


def _braces(s: str) -> list[str]:
    m = re.search(r"\x02([^\x02\x03]*)\x03", s)
    if not m or "\x04" not in m.group(1):
        return [s]
    pre, post = s[: m.start()], s[m.end() :]
    out: list[str] = []
    for opt in m.group(1).split("\x04"):
        out.extend(_braces(pre + opt + post))
        if len(out) > _ALT_CAP:
            return [ANY]
    return out


# ---------------------------------------------------------------- docker's own grammar

_DOCKER_GLOBAL = {"-H", "--host", "-c", "--context", "--config", "-l", "--log-level", "--tlscacert", "--tlscert", "--tlskey"}
_RUN_VALUE = _w(
    "-a --attach --add-host --annotation --blkio-weight --blkio-weight-device --cap-add --cap-drop --cgroup-parent "
    "--cgroupns --cidfile --cpu-period --cpu-quota --cpu-rt-period --cpu-rt-runtime -c --cpu-shares --cpus "
    "--cpuset-cpus --cpuset-mems --device --device-cgroup-rule --device-read-bps --device-read-iops "
    "--device-write-bps --device-write-iops --dns --dns-option --dns-search --domainname --entrypoint -e --env "
    "--env-file --expose --gpus --group-add --health-cmd --health-interval --health-retries --health-start-interval "
    "--health-start-period --health-timeout -h --hostname --ip --ip6 --ipc --isolation --kernel-memory -l --label "
    "--label-file --link --link-local-ip --log-driver --log-opt --mac-address -m --memory --memory-reservation "
    "--memory-swap --memory-swappiness --mount --name --network --net --network-alias --oom-score-adj --pid "
    "--pids-limit --platform -p --publish --pull --restart --runtime --security-opt --shm-size --stop-signal "
    "--stop-timeout --storage-opt --sysctl --tmpfs --ulimit -u --user --userns --uts -v --volume --volumes-from -w "
    "--workdir --detach-keys --env-from-file --index"
)
_EXEC_VALUE = {"-e", "--env", "--env-file", "-u", "--user", "-w", "--workdir", "--detach-keys", "--index"}
_VERB_VALUE = _w(
    "--format --filter --since --until --tail --time --timeout --signal --type --platform --index --driver --opt "
    "--subnet --gateway --alias --ip --restart --cpus --memory --memory-swap --cpu-shares --pids-limit"
)
_VERB_SHORT_VALUE = {
    "inspect": {"-f"},
    "stop": {"-t", "-s"},
    "restart": {"-t", "-s"},
    "kill": {"-s"},
    "logs": {"-n"},
    "ps": {"-f", "-n"},
    "images": {"-f"},
    "ls": {"-f"},
    "update": {"-m", "-c"},
    "down": {"-t"},
    "up": {"-t"},
}
_COMPOSE_GLOBAL = _w("-f --file -p --project-name --project-directory --env-file --profile --ansi --progress --parallel")
_MANAGED = _w(
    "container image network volume system builder buildx context plugin node service stack secret config trust "
    "manifest swarm checkpoint"
)


@dataclass
class DockerCall:
    verb: str = ""
    group: str = ""
    args: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    values: dict[str, list[str]] = field(default_factory=dict)
    target: str | None = None
    inner: list[str] = field(default_factory=list)
    compose: bool = False


def _split_known(args: list[str], value: set[str]) -> tuple[set[str], dict[str, list[str]], list[str]]:
    """Options from `value` take a value; every other option is a flag, its short clusters split."""
    flags: set[str] = set()
    values: dict[str, list[str]] = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            return flags, values, args[i + 1 :]
        if a.startswith("--"):
            key, eq, val = a.partition("=")
            if key in value:
                if not eq:
                    i += 1
                    val = args[i] if i < len(args) else ""
                values.setdefault(key, []).append(val)
            else:
                flags.add(key if not eq or val.lower() not in ("false", "0") else key + "=false")
        elif a.startswith("-") and len(a) > 1:
            if a in value:
                i += 1
                values.setdefault(a, []).append(args[i] if i < len(args) else "")
            else:
                for j, ch in enumerate(a[1:], 1):
                    if "-" + ch in value:
                        val = a[j + 1 :]
                        if not val:
                            i += 1
                            val = args[i] if i < len(args) else ""
                        values.setdefault("-" + ch, []).append(val)
                        break
                    flags.add("-" + ch)
        else:
            return flags, values, args[i:]
        i += 1
    return flags, values, []


def docker_parse(cmd: Cmd) -> DockerCall:
    args = list(cmd.args)
    call = DockerCall()
    if cmd.name == "docker-compose":
        args = ["compose", *args]
    else:
        _, _, args = _split_known(args, _DOCKER_GLOBAL)
    if not args:
        return call
    if args[0] == "compose":
        call.compose = True
        _, values, rest = _split_known(args[1:], _COMPOSE_GLOBAL)
        call.values.update(values)
        if not rest:
            return call
        call.verb, args = rest[0], rest[1:]
    elif args[0] in _MANAGED and len(args) > 1:
        call.group, call.verb, args = args[0], args[1], args[2:]
        if call.group == "container" and call.verb in ("ls", "list"):
            call.verb = "ps"
        if call.group == "image" and call.verb in ("rm", "remove"):
            call.verb = "rmi"
    else:
        call.verb, args = args[0], args[1:]
    if call.verb in ("run", "create", "exec"):
        flags, values, rest = _split_known(args, _RUN_VALUE if call.verb != "exec" else _EXEC_VALUE)
        call.flags |= flags
        for k, v in values.items():
            call.values.setdefault(k, []).extend(v)
        if rest:
            call.target = rest[0]
            call.inner = rest[1:]
            entry = call.values.get("--entrypoint")
            if entry and entry[-1]:
                call.inner = [entry[-1], *call.inner]
        call.args = rest
        return call
    value = _VERB_VALUE | _VERB_SHORT_VALUE.get(call.verb, set())
    while args:
        flags, values, rest = _split_known(args, value)
        call.flags |= flags
        for k, v in values.items():
            call.values.setdefault(k, []).extend(v)
        if not rest:
            break
        call.args.append(rest[0])
        args = rest[1:]
    return call


# ---------------------------------------------------------------- the rules

ENGINE_EXEC = "/var/lib/zcrypto-engine/exec"
ARMED = ENGINE_EXEC + "/armed"
HOLD = ENGINE_EXEC + "/restart-hold"
KILL = ENGINE_EXEC + "/kill"
PLAN = ENGINE_EXEC + "/probe-plan.json"

SECRET_FILES = (
    ANY + ".env",
    ANY + "_ed25519",
    ANY + "/id_" + SEG,
    ANY + "/ssh_host_" + SEG + "_key",
    ANY + ".vault",
    ANY + "vault.yml",
    ANY + "/.netrc",
    ANY + ".pem",
    ANY + ".key",
    ANY + "/haproxy.cfg",
    ANY + "/hc.sqlite" + SEG,
    ANY + "/hc-" + SEG + ".sqlite" + SEG,
    ANY + "/config.v2.json",
    "/etc/wireguard/" + ANY,
    "/etc/default/alloy",
    "/etc/default/" + SEG + "selfcheck",
    "/var/lib/docker/containers/" + ANY,
    "/var/lib/zcrypto-cache/conf/" + ANY,
    "/proc/" + ANY + "/environ",
)
SECRET_ROOTS = tuple(
    "/etc/wireguard /etc/default /etc/ssh /etc/zcrypto-capture /etc/zcrypto-ops /opt/zcrypto-engine /opt/zcrypto-capture "
    "/opt/zcrypto-cache /opt/zcrypto-hc /var/lib/docker /var/lib/zcrypto-cache/conf /var/backups/zcrypto-hc "
    f"/volume1/docker /root /home/{SEG}/.ssh /home/{SEG}/.config /proc".split()
)
_SECRET_CODE = re.compile(
    r"\.env\b|_ed25519|/etc/wireguard|\.vault\b|vault\.yml|\.netrc|\.pem\b|/etc/default/alloy"
    r"|haproxy\.cfg|hc(-[^\s'\"/]*)?\.sqlite|config\.v2\.json|/proc/[^\s'\"]*environ"
)
_ENV_CODE = re.compile(r"environ|getenv|\bENV\b|process\.env|%ENV|ENVIRON")
_SPAWN_CODE = re.compile(
    r"subprocess|os\.system|os\.popen|os\.exec|os\.spawn|\bpty\b|Popen|child_process"
    r"|\bsystem\s*\(|\bexec\s*\(|\beval\s*\(|\bqx\b|`|\|\s*getline|\|\s*\"|__import__"
)
_SED_EXEC = re.compile(r"(^|[;\n{}]\s*)e(\s|$|;)|(^|[;\n{}]\s*)s(.)(?:\\.|(?!\4).)*\4(?:\\.|(?!\4).)*\4[gpIiMm0-9w]*e")
_GATE_CODE = re.compile(r"zcrypto-engine/exec|[\"'/](armed|restart-hold|kill|probe-plan\.json)[\"']")
_WRITE_CODE = re.compile(
    r"open\s*\([^)]*,\s*['\"][^'\"]*[wax+]|O_CREAT|O_WRONLY|O_RDWR|\.write|write_text|write_bytes"
    r"|touch|rename|replace|unlink|remove|rmtree|symlink|link\s*\(|copy|move|mknod|truncate"
)

READERS = _w(
    "cat tac nl less more most head tail od hexdump xxd strings base64 base32 basenc uuencode grep egrep fgrep zgrep "
    "zegrep zfgrep rg ag ack zcat bzcat xzcat zstdcat lzcat zless zmore cut sort uniq paste join column fold fmt pr "
    "expand unexpand diff cmp sdiff diff3 colordiff comm rev shuf tsort split csplit iconv look cp scp rsync install "
    "tar zip gzip bzip2 xz zstd lz4 cpio pax dd openssl jq yq xmllint source . mail mailx sendmail nc ncat netcat "
    "socat gpg age awk gawk mawk nawk sed perl ruby node nodejs php bash sh dash zsh ksh mksh ash xargs curl wget tee"
)
METADATA = _w(
    "ls stat test [ [[ file du wc sha256sum sha1sum sha512sum sha224sum sha384sum md5sum b2sum cksum sum readlink "
    "realpath basename dirname namei getfacl lsattr chmod chown chgrp touch rm unlink mv ln mkdir rmdir echo printf "
    "true false : find shred"
)
_READER_VALUES = {
    "head": "nc",
    "tail": "ncs",
    "cut": "dfbc",
    "sort": "ktSTo",
    "uniq": "fsw",
    "grep": "efmABCdD",
    "egrep": "efmABCdD",
    "fgrep": "efmABCdD",
    "zgrep": "efmABCdD",
    "rg": "efgtTmABCM",
    "xxd": "slcgo",
    "od": "AjNtw",
    "hexdump": "nsefC",
    "base64": "w",
    "strings": "nte",
    "nl": "bnsvwi",
    "diff": "UCxXI",
    "jq": "f",
    "tar": "CfTXbHKLNV",
    "cp": "tS",
    "mv": "tS",
    "install": "tSmog",
    "ln": "tS",
    "rsync": "efBTM",
    "split": "lbna",
    "paste": "d",
    "fold": "w",
    "column": "tsco",
    "xargs": "adEILnPs",
    "curl": "oTdFKHAeuxXrwmEbcyY",
    "wget": "OoaPiTt",
    "gzip": "S",
    "zip": "x",
    "awk": "fvF",
    "gawk": "fvF",
    "mawk": "fvF",
    "nawk": "fvF",
    "sed": "efl",
    "openssl": "",
    "dd": "",
    "tee": "",
}
_LONG_VALUES = _w(
    "--file --regexp --exclude --include --exclude-dir --directory --target-directory --suffix --mode --owner --group "
    "--lines --bytes --fields --delimiter --key --field-separator --output --max-count --after-context "
    "--before-context --context --label --files-from --exclude-from --rsh --filter --chmod --chown --log-file "
    "--password-file --temp-dir --data --data-binary --data-raw --data-urlencode --form --upload-file --config "
    "--header --user --post-file --input-file --output-document --slurpfile --rawfile --arg --argjson --expression"
)
_PATTERN_FIRST = _w("grep egrep fgrep zgrep zegrep zfgrep rg ag ack awk gawk mawk nawk sed jq yq")


def _secret(w: str, match=could) -> str | None:
    """The credential pattern `w` could name, or None."""
    for pat in SECRET_FILES:
        if match(w, pat):
            if pat.endswith("/id_" + SEG) and w.endswith(".pub") and not any(c in w[-5:] for c in WILD):
                continue
            return _show(pat)
    return None


def _maybe(path: str) -> str:
    return "which could be " if any(c in path for c in WILD) else ""


def _file_operands(cmd: Cmd) -> tuple[list[str], bool]:
    """What a reader reads, as absolute paths, and whether it reads them recursively."""
    name = cmd.name
    if name in ("source", "."):
        return [cmd.path(a) for a in cmd.args[:1]], False
    if name == "dd":
        return [cmd.path(a[3:]) for a in cmd.args if a.startswith("if=")], False
    if name in ("curl", "wget"):
        opts, _ = _opts(cmd.args, _READER_VALUES[name], _LONG_VALUES)
        files = [v.lstrip("@").split("=@", 1)[-1] for k, v in opts if v and (v.startswith("@") or "=@" in v)]
        files += _values(opts, "-T", "--upload-file", "-K", "--config", "--post-file", "-i", "--input-file")
        return [cmd.path(f) for f in files], False
    if name == "tee":
        return [], False
    opts, operands = _opts(cmd.args, _READER_VALUES.get(name, ""), _LONG_VALUES)
    keys = {k for k, _ in opts}
    if name in _PATTERN_FIRST and operands and not ({"-e", "-f", "--regexp", "--file", "--expression"} & keys):
        operands = operands[1:]
    if name in ("awk", "gawk", "mawk", "nawk"):
        operands = [o for o in operands if not _ASSIGN.match(o)]
    files = list(operands)
    files += _values(
        opts, "-f", "--file", "--files-from", "--exclude-from", "--password-file", "--slurpfile", "--rawfile", "-a", "--arg-file"
    )
    if name in ("scp", "rsync", "cp", "docker"):
        files = [f.split(":", 1)[1] if ":" in f and "/" not in f.split(":", 1)[0] else f for f in files]
    if name in ("cp", "mv", "install", "ln", "scp", "rsync") and len(files) > 1 and not _values(opts, "-t", "--target-directory"):
        files = files[:-1]
    base = cmd.cwd
    if name == "tar":
        for d in _values(opts, "-C", "--directory"):
            base = norm(d, cmd.cwd)
        tar_mode = "".join(k[1:] for k in keys if len(k) == 2) + (
            cmd.args[0] if cmd.args and not cmd.args[0].startswith("-") else ""
        )
        files = (
            files
            if any(m in tar_mode for m in "cru") or keys & {"--create", "--append", "--update"}
            else _values(opts, "-f", "--file")
        )
    files = [f for f in files if f not in ("-", "")]
    recursive = (
        name in ("rg", "ag", "ack", "tar", "zip", "cpio", "pax")
        or bool(keys & {"-r", "-R", "--recursive", "--dereference-recursive", "-a", "--archive"})
        or "recurse" in _values(opts, "-d", "--directories")
    )
    return [norm(f, base) for f in files], recursive


def rule_secrets(cmd: Cmd, j: Judge) -> Refusal | None:
    def no(reason: str, whose: str = OWNER) -> Refusal:
        return Refusal("secrets", reason, whose)

    name = cmd.name
    if name == "kraken" or any(re.search(r"kraken[-_]cli", a) for a in cmd.argv):
        return no(
            "kraken, the venue CLI, is workstation-only and never runs or installs on a fleet host",
            "a workstation line, never a host's",
        )
    for op, p in cmd.redirs:
        if op in ("<", "<>") and (hit := _secret(p)):
            return no(f"it feeds {_show(p)} into a command, {_maybe(p)}a credential file ({hit})")
        if re.search(r"/proc/.*/environ", p):
            return no(f"it redirects a process's environment ({_show(p)})")
    if cmd.layer == "wrapper":
        return None
    if any(re.search(r"/proc/[^/]+/environ", a.replace(ANY, "x").replace(SEG, "x")) for a in cmd.args):
        return no("it reads a process's environment through /proc/<pid>/environ")
    if cmd.container is not None:
        bare = [a for a in cmd.args if not a.startswith("-")]
        if (
            name == "printenv"
            or name == "env"
            and not bare
            or name == "export"
            and (not cmd.args or cmd.args == ["-p"])
            and not cmd.env_reads
            or name in ("set", "declare", "typeset", "compgen")
            and (not cmd.args or set(cmd.args) & {"-p", "-x", "-e", "-v"})
        ):
            return no(f"{name} inside a container prints its environment, the live keys with it")
        if cmd.env_reads:
            return no(f"it expands the container's own ${cmd.env_reads[0]}, a value from its environment")
        if cmd.code is not None and _ENV_CODE.search(cmd.code):
            return no("its code reads the container's environment")
    if cmd.code is not None and (m := _SECRET_CODE.search(cmd.code)):
        return no(f"its {cmd.lang} code names a credential file ({m.group(0)})")
    if name == "wg" and cmd.args and (cmd.args[0] == "showconf" or {"private-key", "preshared-keys"} & set(cmd.args)):
        return no("wg prints the interface's private key")
    if name in ("docker", "docker-compose"):
        d = docker_parse(cmd)
        if d.verb == "inspect" and d.group in ("", "container", "image"):
            formats = d.values.get("-f", []) + d.values.get("--format", [])
            if not formats:
                return no("docker inspect with no --format prints the whole object, the container's environment with it")
            for f in formats:
                if any(c in f for c in WILD):
                    return no("docker inspect's --format is computed at run time")
                if "{{" not in f:
                    return no(f"docker inspect --format {f} prints the whole object")
                if re.search(r"\.Config(?![.\w])|\.Config\.Env|[\s{(|]\.(?=[\s})|])|\{\{\s*\.\s*\}\}|\$(?![\w.])", f):
                    return no(f"docker inspect's template {f} reaches .Config.Env or prints the whole object")
        if d.compose and d.verb == "config":
            return no("compose's config verb prints the stack with its environment interpolated")
        if d.verb == "cp":
            for a in d.args:
                path = a.split(":", 1)[1] if ":" in a and "/" not in a.split(":", 1)[0] else a
                if hit := _secret(cmd.path(path)):
                    return no(f"docker cp copies {_show(path)}, which could be a credential file ({hit})")
        return None
    if name == "systemctl":
        opts, operands = _opts(
            cmd.args,
            "pPtsnoHM",
            _w(
                "--property --type --signal --lines --output --host --machine --state --job-mode --kill-whom --root "
                "--timestamp --what --legend"
            ),
        )
        verb = operands[0] if operands else ""
        props = ",".join(_values(opts, "-p", "-P", "--property"))
        if verb == "show-environment":
            return no("systemctl show-environment prints the manager's environment")
        if verb == "show" and (not props or "Environment" in props or any(c in props for c in WILD)):
            return no("systemctl show prints a unit's Environment unless it names a property other than Environment")
        if verb == "cat":
            units = operands[1:] or [ANY]
            for u in units:
                u = u.removesuffix(".service")
                if any(could(u, pat) for pat in ("alloy", "zcrypto-grafana-watchdog", SEG + "-selfcheck")):
                    return no(f"systemctl cat {_show(u)} shows a unit that loads an EnvironmentFile")
        return None
    if name in METADATA:
        return None
    if name in _SHELLS or _PY.fullmatch(name) or name in _INTERPRETERS:
        if cmd.layer != "script":
            return None
        files, recursive = [cmd.path(a) for a in cmd.rest], False
    elif name in READERS:
        files, recursive = _file_operands(cmd)
    else:
        files = None
    if files is not None:
        for f in files:
            if hit := _secret(f):
                return no(f"{name} would read or copy {_show(f)}, {_maybe(f)}a credential file ({hit})")
            if recursive and (root := next((r for r in SECRET_ROOTS if could_tree(f, r)), None)):
                return no(f"{name} reads {_show(f)} whole, and credential files live under {_show(root)}")
        return None
    for a in cmd.args:
        if a.startswith("/") or "." in a:
            if hit := _secret(cmd.path(a.split("=", 1)[-1]), does):
                return no(f"{name} is handed {_show(a)}, a credential file ({hit})")
    return None


def _gate_effects(cmd: Cmd) -> list[tuple[str, str]]:
    """What a command does to the files it names: ("create" | "remove" | "link", absolute path) pairs."""
    out = [("create", p) for op, p in cmd.redirs if op not in ("<",)]
    name = cmd.name
    if cmd.layer == "wrapper":
        if name == "flock":
            ops = _opts(cmd.args, "Ew", {"--conflict-exit-code", "--timeout", "--wait"}, True)[1]
            out += [("create", cmd.path(ops[0]))] if ops and not ops[0].isdigit() else []
        return out
    if name == "find":
        return out + [("remove", p) for p in cmd.rest]
    opts, ops = _opts(cmd.args, _READER_VALUES.get(name, "") + ("t" if name in ("cp", "mv", "ln", "install") else ""), _LONG_VALUES)
    keys = {k for k, _ in opts}
    paths = [cmd.path(o) for o in ops]
    if name in ("touch", "truncate", "mkdir", "mknod", "mkfifo", "tee") and "-c" not in keys:
        out += [("create", p) for p in paths]
    elif name in ("cp", "mv", "install", "ln", "rsync", "scp"):
        if name == "install" and "-d" in keys:
            return out + [("create", p) for p in paths]
        target = _values(opts, "-t", "--target-directory")
        srcs = paths if target else paths[:-1]
        dest = cmd.path(target[0]) if target else (paths[-1] if paths else "")
        if dest:
            out.append(("create", dest))
            out += [("create", dest + "/" + s.rsplit("/", 1)[-1]) for s in srcs]
            if keys & {"-r", "-R", "-a", "--recursive", "--archive"}:
                out.append(("create", dest + "/" + ANY))
        if name == "mv":
            out += [("remove", s) for s in srcs]
        if name == "ln":
            out += [("link", s) for s in srcs]
    elif name in ("rm", "unlink", "shred", "rmdir"):
        out += [("remove", p) for p in paths]
    elif name == "dd":
        out += [("create", cmd.path(a[3:])) for a in cmd.args if a.startswith("of=")]
    elif name in ("sed", "perl") and any(k == "-i" or k.startswith("--in-place") for k in keys):
        out += [("create", p) for p in paths[0 if _values(opts, "-e", "--expression") else 1 :]]
    elif name == "tar" and (any("x" in k for k in keys) or (cmd.args and "x" in cmd.args[0] and not cmd.args[0].startswith("-"))):
        dirs = _values(opts, "-C", "--directory")
        out.append(("create", (cmd.path(dirs[-1]) if dirs else cmd.cwd) + "/" + ANY))
    elif name in ("curl", "wget"):
        o = _opts(cmd.args, _READER_VALUES[name], _LONG_VALUES)[0]
        out += [("create", cmd.path(v)) for v in _values(o, "-o", "--output", "-O", "--output-document") if v != "-"]
    elif name == "sort":
        out += [("create", cmd.path(v)) for v in _values(opts, "-o", "--output")]
    elif name == "docker" and (d := docker_parse(cmd)).verb == "cp" and d.args:
        dst = d.args[-1]
        out.append(("create", cmd.path(dst.split(":", 1)[1] if ":" in dst.split("/", 1)[0] else dst)))
    elif name == "mount" and keys & {"--bind", "--rbind", "-B"} | ({"-o"} if "bind" in ",".join(_values(opts, "-o")) else set()):
        out += [("link", p) for p in paths]
    elif name not in READERS and name not in METADATA:
        out += [("unknown", cmd.path(a)) for a in cmd.args if a.startswith("/")]
    return out


def rule_money_path(cmd: Cmd, j: Judge) -> Refusal | None:
    def no(reason: str) -> Refusal:
        return Refusal("money-path", reason, "the owner's line, always")

    argv = cmd.argv
    words = [a.rsplit("/", 1)[-1] for a in argv]
    execute = any(a == "--execute" or a.startswith("--execute=") for a in argv)
    if execute and ("zcrypto-flatten" in words or "flatten" in argv):
        return no("the red button's --execute cancels and closes on the live account")
    if any("order-semantics-probe" in w or "probe-with-vaulted-key" in w for w in words) and "--apply" in argv:
        return no("the order-semantics probe's --apply places real orders")
    if any("fixture-mint" in w or "mint-with-vaulted-key" in w for w in words) and execute:
        return no("the fixture minter's --execute sends orders")
    if cmd.code is not None and _GATE_CODE.search(cmd.code) and (cmd.lang in ("sed", "awk") or _WRITE_CODE.search(cmd.code)):
        return no(f"its {cmd.lang} code writes or moves the engine's gate files")
    for effect, p in _gate_effects(cmd):
        match = could if effect != "unknown" else does

        def which(target: str) -> str:
            return target if p == target else f"{_show(p)}, which could be {target} or hold it,"

        if effect in ("create", "unknown") and match(p, ARMED):
            return no(f"creating {which(ARMED)} opens the trading gate")
        if effect in ("create", "unknown") and match(p, PLAN):
            return no(f"writing {which(PLAN)} places a plan the engine acts on")
        for target, why in ((HOLD, "lets a restarted engine trade"), (KILL, "lets a tripped engine trade again")):
            if effect in ("remove", "unknown") and (could_cover(p, target) if effect == "remove" else does(p, target)):
                return no(f"removing {which(target)} {why}")
        if effect == "link" and could_tree(p, ENGINE_EXEC):
            return no(f"a link onto {ENGINE_EXEC} hides a later write to the gate files")
    return None


def rule_terminal(cmd: Cmd, j: Judge) -> Refusal | None:
    def no(reason: str) -> Refusal:
        return Refusal("terminal", reason, OWNER_TERMINAL)

    name = cmd.name
    if name in ("converge.sh", "ansible-playbook", "ansible-vault", "vault-append-secret.sh"):
        return no(f"{name} takes a typed confirm or a passphrase")
    if name in _w("vi vim nvim view vimdiff nano pico emacs emacsclient joe mcedit micro sudoedit visudo vipw vigr"):
        return no(f"{name} is an editor")
    if name in ("ssh-add", "passwd", "chsh", "chfn", "zcrypto-panel-regenerate", "watch", "top", "htop", "login"):
        if not (name == "top" and "-b" in cmd.args):
            return no(f"{name} reads a terminal")
    if name in ("ssh", "scp", "sftp", "slogin", "autossh", "mosh"):
        return no(f"{name} reaches a further host from the remote side")
    if name == "rsync" and any(":" in a and "/" not in a.split(":", 1)[0] for a in cmd.args if not a.startswith("-")):
        return no("rsync to a further host from the remote side")
    if name == "zcrypto-flatten":
        return no("the red button's wrapper runs its container with a terminal")
    if name in ("sudo", "doas"):
        if "-S" in cmd.flags:
            return no("sudo -S reads a password from stdin")
        if "-e" in cmd.flags:
            return no("sudo -e opens an editor")
        if not cmd.rest and cmd.flags & {"-i", "-s"}:
            return no("sudo -i or -s with no command opens an interactive shell")
    if name == "su" and not any(
        a == "-c"
        or a.startswith(("--command", "--session-command"))
        or (a.startswith("-") and not a.startswith("--") and "c" in a[1:])
        for a in cmd.args
    ):
        return no("su without -c opens an interactive shell")
    if name in _SHELLS | {"python", "python3"} and "-i" in cmd.flags:
        return no(f"{name} -i is interactive")
    if name == "systemd-run" and any(a in ("-t", "--pty", "-S", "--shell") for a in cmd.args):
        return no("systemd-run --pty attaches a terminal")
    if name == "systemctl" and "edit" in cmd.args:
        return no("systemctl edit opens an editor")
    if name == "crontab" and "-e" in cmd.args:
        return no("crontab -e opens an editor")
    if name == "xargs" and cmd.flags & {"-p", "-o", "--interactive", "--open-tty"}:
        return no("xargs -p or -o reads the terminal")
    if (
        name == "tmux"
        and cmd.args
        and cmd.args[0] not in _w("ls list-sessions list-windows list-panes has-session display-message capture-pane show-options")
    ):
        return no("tmux attaches or opens a terminal session")
    if name == "screen" and not set(cmd.args) & {"-ls", "-list"}:
        return no("screen attaches or opens a terminal session")
    if name in ("docker", "docker-compose"):
        d = docker_parse(cmd)
        tty = {"-i", "-t", "--interactive", "--tty"}
        if d.verb in ("run", "exec", "create") and not d.compose and d.flags & tty:
            return no(f"docker {d.verb} with -i or -t attaches a terminal")
        if d.verb == "attach" or d.verb == "start" and d.flags & {"-i", "--interactive", "-a", "--attach"}:
            return no(f"docker {d.verb} attaches a terminal")
    return None


def rule_capture_primary(cmd: Cmd, j: Judge) -> Refusal | None:
    on_primary = cmd.alias == j.primary
    capture_hosts = {j.primary, j.secondary} - {None}

    def no(reason: str, whose: str = OWNER_WINDOW) -> Refusal:
        return Refusal("capture-primary", reason, whose)

    name = cmd.name
    capture = ("zcrypto-capture", "grafana-alloy", "alloy")
    if name in ("docker", "docker-compose"):
        d = docker_parse(cmd)
        prune = d.verb == "rmi" or d.verb == "prune" and d.group in ("image", "system")
        if prune and cmd.alias in capture_hosts:
            return no(
                f"docker {d.group + ' ' if d.group else ''}{d.verb} on a capture host",
                "infra/scripts/prune-host-images.py's line, at pins-update time",
            )
        if not on_primary:
            return None
        if d.compose and d.verb in ("stop", "down", "restart", "kill", "rm", "pause"):
            places = d.values.get("-f", []) + d.values.get("--file", []) + d.values.get("--project-directory", [])
            places = [cmd.path(p) for p in places] or [cmd.cwd]
            names = d.values.get("-p", []) + d.values.get("--project-name", [])
            if any(could_tree(p, root) for p in places for root in ("/opt/zcrypto-capture", "/etc/zcrypto-capture")) or any(
                could(n, c) for n in names for c in capture
            ):
                return no(f"docker compose {d.verb} of the primary's capture stack")
        stopping = {"stop", "restart", "kill", "rm", "pause", "update", "rename"}
        if d.verb in stopping or d.group == "network" and d.verb == "disconnect":
            targets = [a for a in d.args if not a.startswith("-")]
            if d.group == "network":
                targets = targets[1:]
            for t in targets or [ANY]:
                if any(could(t, c) for c in capture) or re.fullmatch(r"[0-9a-f]{6,64}", t):
                    return no(f"docker {d.verb} {_show(t)} could stop the primary's capture or its Alloy")
        return None
    if not on_primary:
        return None
    if cmd.container is not None and name in ("kill", "pkill", "killall"):
        if any(could(cmd.container, c) for c in capture):
            return no("a kill inside the primary's capture or Alloy container")
        return None
    if name == "systemctl":
        _, operands = _opts(
            cmd.args,
            "pPtsnoHM",
            _w("--property --type --signal --lines --output --host --machine --state --job-mode --kill-whom"),
        )
        verb, units = (operands[0], operands[1:]) if operands else ("", [])
        if verb == "isolate":
            return no("systemctl isolate on the primary stops every unit its target does not pull, capture with it")
        if verb in _w(
            "stop restart kill disable mask try-restart reload-or-restart try-reload-or-restart condrestart force-reload freeze"
        ):
            for u in units or [ANY]:
                base_unit = u.removesuffix(".service")
                if any(could(base_unit, c) for c in (*capture, "docker", "docker.socket", "containerd")):
                    return no(f"systemctl {verb} {_show(u)} on the primary stops capture or its Alloy")
    if name in ("pkill", "killall", "kill"):
        if name == "kill" and any(a in ("-0", "-s0", "--signal=0") for a in cmd.args):
            return None
        pats = [a for a in cmd.args if not a.startswith("-")]
        if name == "kill" or not pats or any(could(p.lower(), ANY + c + ANY) for p in pats for c in ("capture", "alloy")):
            return no(f"{name} on the primary could signal capture or its Alloy")
    return None


def rule_workstation(cmd: Cmd, j: Judge) -> Refusal | None:
    if cmd.alias != j.workstation:
        return None

    def no(reason: str) -> Refusal:
        return Refusal("workstation", reason, "the owner's line, at this machine")

    name = cmd.name
    if name in ("reboot", "shutdown", "poweroff", "halt"):
        return no(f"{name} on {cmd.alias}, the machine this session runs on")
    if name in ("init", "telinit") and any(a in ("0", "6", "1", "s", "S") for a in cmd.args):
        return no(f"{name} changes this machine's runlevel")
    if name == "kexec" and any(a in ("-e", "--exec") for a in cmd.args):
        return no("kexec reboots this machine")
    if name in ("systemctl", "loginctl"):
        ops = [a for a in cmd.args if not a.startswith("-")]
        verb = ops[0] if ops else ""
        if verb in _w(
            "reboot poweroff halt kexec isolate rescue emergency suspend hibernate hybrid-sleep "
            "suspend-then-hibernate soft-reboot default exit"
        ):
            return no(f"{name} {verb} on the machine this session runs on")
        if verb in ("start", "restart") and any(
            could(u, t + ".target")
            for u in ops[1:]
            for t in _w("reboot poweroff halt kexec rescue emergency shutdown suspend hibernate soft-reboot")
        ):
            return no(f"{name} {verb} of a target that takes this machine down")
    if any(could(p, "/proc/sysrq-trigger") for op, p in cmd.redirs if op != "<") or (
        name == "tee" and any(could(cmd.path(a), "/proc/sysrq-trigger") for a in cmd.args)
    ):
        return no("a write to /proc/sysrq-trigger")
    return None


def rule_hazards(cmd: Cmd, j: Judge) -> Refusal | None:
    def no(reason: str, whose: str) -> Refusal:
        return Refusal("hazards", reason, whose)

    name = cmd.name
    if cmd.layer == "wrapper":
        return None
    if name in ("apt", "apt-get", "aptitude"):
        opts, operands = _opts(cmd.args, "otca", {"--option", "--target-release", "--config-file"})
        keys = {k for k, _ in opts}
        yes = keys & {"-y", "--yes", "--assume-yes"} or any(
            "Assume-Yes=true" in v or "assume-yes=true" in v.lower() for v in _values(opts, "-o", "--option")
        )
        if operands and operands[0] in ("upgrade", "dist-upgrade", "full-upgrade", "install") and not yes:
            return no(f"{name} {operands[0]} without -y stops at a prompt", f"yours to respell: {name} -y {operands[0]}")
    if name == "rm":
        opts, operands = _opts(cmd.args)
        keys = {k for k, _ in opts}
        if keys & {"-r", "-R", "--recursive"} and keys & {"-f", "--force"}:
            for o in operands:
                p = cmd.path(o)
                if not re.sub(r"[\x00\x01/*.]", "", o):
                    return no(f"rm -rf {_show(o)}: the operand is / or a bare variable", "yours to respell with the path")
                if (
                    could(p, "/")
                    or could(p, "/var/lib/zcrypto-" + SEG)
                    or could(p, "/var/lib/zcrypto-" + SEG + "/" + SEG)
                    or could(p, "/var")
                    or could(p, "/var/lib")
                ):
                    return no(f"rm -rf {_show(o)} removes a data root or a directory directly under one", "the owner's line")
    if name.startswith("mkfs") or name == "wipefs" or name == "dd" and any(a.startswith("of=/dev/") for a in cmd.args):
        return no(f"{name} overwrites a device", "the owner's line")
    return None


RULES = (
    rule_secrets,
    rule_hazards,
    rule_money_path,
    rule_terminal,
    rule_capture_primary,
    rule_workstation,
)


# ---------------------------------------------------------------- the command line


def judge_block(block: str, alias: str, aliases: dict[str, str]) -> Refusal | None:
    if alias not in aliases.values():
        known = ", ".join(sorted(aliases.values()))
        return Refusal("alias", f"{alias!r} is no `ssh <alias>` cell of {FLEET_TABLE}'s host table", f"a line for one of: {known}")
    return Judge(alias, aliases).block(block)


def _record(kind: str, ts: str, alias: str, block: str, **extra) -> str:
    line = {
        "kind": kind,
        "ts": ts,
        "alias": alias,
        "session": os.environ.get("ZCRYPTO_SESSION") or "unknown",
        "sha256": hashlib.sha256(block.encode("utf-8")).hexdigest(),
        "block": block,
        **extra,
    }
    return json.dumps(line, ensure_ascii=False)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="host_run_sh.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    j.add_argument("--repo", required=True)
    j.add_argument("--alias", required=True)
    j.add_argument("--record", action="store_true")
    j.add_argument("--ts", default="")
    j.add_argument("--timeout", type=int, default=0)
    a = ap.parse_args(argv)
    raw = sys.stdin.buffer.read()
    if len(raw) > MAX_BLOCK:
        print(f"host-run: the block is {len(raw)} bytes, over the {MAX_BLOCK} a remote command line carries", file=sys.stderr)
        return 64
    try:
        block = raw.decode("utf-8")
    except UnicodeDecodeError:
        print("host-run: the block is not UTF-8 text", file=sys.stderr)
        return 64
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", block):
        print("host-run: the block carries control characters", file=sys.stderr)
        return 64
    try:
        aliases = fleet_ssh_aliases((Path(a.repo) / FLEET_TABLE).read_text(encoding="utf-8"))
    except OSError as e:
        aliases = {}
        print(f"host-run: the fleet table is unreadable: {e}", file=sys.stderr)
    try:
        refusal = judge_block(block, a.alias, aliases)
    except Exception as e:  # the door fails closed on its own fault too
        refusal = Refusal("unresolvable", f"the judge failed on this block ({type(e).__name__}: {e})", RESPELL)
    if refusal is not None:
        print(refusal.line(), file=sys.stderr)
        if a.record:
            print(_record("refused", a.ts, a.alias, block, rule=refusal.rule, reason=refusal.reason))
        return 65
    print(_record("begin", a.ts, a.alias, block, timeout_s=a.timeout) if a.record else "ADMITTED")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
