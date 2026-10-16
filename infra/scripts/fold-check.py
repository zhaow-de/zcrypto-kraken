#!/usr/bin/env python3
"""A fold made of a pre-review's ship texts alone, checked in place of a fresh pre-review of its tip.

Run from the repository; <base> in --range is the tip the pre-review read, where each row's site line is counted, and
the report dir's ledger holds that pre-review's row at <base>. Every line a hunk deletes is prose at <base>: in a Python
file a comment, a docstring or a blank line, as tokenized; in a shell or YAML file a `#` comment or a blank line; in a JS
file a `//` or `/* */` comment or a blank line; a `#!` first line never; a Markdown or other text file whole. A `.j2`
template is read as the file it renders; a file with no known suffix by its `#!` line.
Not read: which prose a hunk deletes beside a site -- a row gives a site's first line, not its extent.
Exit: 0 passed and recorded; 1 a row or a change fails, or no pre-review row at <base>, each printed, nothing written;
2 usage, or git refused.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import json
import pathlib
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field

SURVIVES = ("trim", "cut", "fix", "keep")
SHIPS = ("trim", "fix")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
LANGUAGES = {
    **dict.fromkeys((".py", ".pyi"), "python"),
    **dict.fromkeys((".sh", ".bash", ".zsh"), "shell"),
    **dict.fromkeys((".yml", ".yaml"), "yaml"),
    **dict.fromkeys((".js", ".mjs", ".cjs"), "js"),
}
INTERPRETERS = ((re.compile(r"python[0-9.]*"), "python"), (re.compile(r"(?:ba|da|k|z)?sh"), "shell"), (re.compile(r"node"), "js"))
LAYOUT = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER, tokenize.COMMENT}
# A `/` after one of these opens a regex literal; after anything else it divides.
REGEX_AFTER = {
    "",
    *"(,=:[!&|?{};+-*%<>~^",
    *"return typeof case do else in of new delete void throw yield await instanceof".split(),
}


def _load_ledger():
    spec = importlib.util.spec_from_file_location("review_ledger", pathlib.Path(__file__).resolve().with_name("review-ledger.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ledger = _load_ledger()


class Usage(Exception):
    pass


@dataclass(frozen=True)
class Row:
    site: str
    survives: str
    ship: str
    path: str
    line: int


@dataclass
class Hunk:
    old: int  # with nothing deleted, the <base> line the insertion follows
    old_count: int
    new: int  # with nothing added, the <tip> line the deletion follows
    new_count: int
    added: list[str] = field(default_factory=list)


def _git(*args: str) -> bytes:
    done = subprocess.run(["git", *args], capture_output=True)
    if done.returncode:
        raise Usage(f"git {' '.join(args)}: {done.stderr.decode(errors='replace').strip() or f'rc {done.returncode}'}")
    return done.stdout


def _commit(rev: str) -> str:
    done = subprocess.run(["git", "rev-parse", "--verify", "--quiet", "--end-of-options", f"{rev}^{{commit}}"], capture_output=True)
    if done.returncode:
        raise Usage(f"{rev!r} names no commit here")
    return done.stdout.decode().strip()


def _lines(rev: str, path: str) -> list[str] | None:
    kind = subprocess.run(["git", "cat-file", "-t", f"{rev}:{path}"], capture_output=True)
    if kind.returncode or kind.stdout.strip() != b"blob":
        return None
    text = _git("cat-file", "blob", f"{rev}:{path}").decode("utf-8", "surrogateescape")
    return text.removesuffix("\n").split("\n") if text else []


def _changed(base: str, tip: str) -> list[str]:
    out = _git("diff", "--name-only", "-z", "--no-renames", "--no-relative", base, tip)
    return [p for p in out.decode("utf-8", "surrogateescape").split("\0") if p]


def _hunks(base: str, tip: str, path: str) -> tuple[list[Hunk], list[str]]:
    """The hunks, and what the file's header changes that no line of text carries."""
    diff = ["--literal-pathspecs", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-relative", "-U0"]
    hunks: list[Hunk] = []
    beyond: list[str] = []
    for line in _git(*diff, base, tip, "--", path).decode("utf-8", "surrogateescape").split("\n"):
        if m := HUNK.match(line):
            a, b, c, d = m.groups()
            hunks.append(Hunk(int(a), 1 if b is None else int(b), int(c), 1 if d is None else int(d)))
        elif not hunks:
            if line.startswith("Binary files ") or line == "GIT binary patch":
                beyond.append("a binary change")
            elif line.startswith("new mode "):
                beyond.append("a mode change")
            elif line.startswith("deleted file mode "):
                beyond.append("the file is deleted")
        elif line.startswith("+"):
            hunks[-1].added.append(line[1:])
    return hunks, beyond


def _deleted(hunks: list[Hunk]) -> set[int]:
    return {n for h in hunks for n in range(h.old, h.old + h.old_count)}


def _to_tip(line: int, hunks: list[Hunk]) -> int:
    """A <base> line no hunk deletes, numbered at <tip>."""
    return line + sum(h.new_count - h.old_count for h in hunks if line >= h.old + max(h.old_count, 1))


def _ship_lines(ship: str) -> list[str]:
    lines = [line.strip() for line in ship.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def _occurrences(lines: list[str], ship: list[str]) -> list[tuple[int, int]]:
    """The first and last <tip> line of each place the ship's lines stand in a row."""
    stripped = [line.strip() for line in lines]
    n = len(ship)
    return [(i + 1, i + n) for i in range(len(stripped) - n + 1) if stripped[i : i + n] == ship] if n else []


def _touches(hunk: Hunk, spans: list[tuple[int, int]], lines: list[str]) -> bool:
    first, last = (hunk.new, hunk.new + hunk.new_count - 1) if hunk.new_count else (hunk.new + 1, hunk.new)
    lo, hi = first - 1, last + 1
    while lo >= 1 and not lines[lo - 1].strip():
        lo -= 1
    while hi <= len(lines) and not lines[hi - 1].strip():
        hi += 1
    return any(s <= hi and e >= lo for s, e in spans)


def _language(path: str, lines: list[str]) -> str:
    if suffix := LANGUAGES.get(pathlib.PurePosixPath(path.removesuffix(".j2")).suffix):
        return suffix
    if lines and lines[0].startswith("#!"):
        names = [word.rsplit("/", 1)[-1] for word in lines[0][2:].split()]
        for pattern, language in INTERPRETERS:
            if any(pattern.fullmatch(name) for name in names):
                return language
    return "text"


def _python_code(text: str) -> set[int]:
    """The lines a token other than a comment or a docstring touches; every line when the file does not parse."""
    try:
        tree = ast.parse(text)
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except SyntaxError, ValueError, tokenize.TokenError:
        return set(range(1, text.count("\n") + 2))
    docs = [
        (node.body[0].lineno, node.body[0].end_lineno)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    ]
    code: set[int] = set()
    for tok in tokens:
        if tok.type in LAYOUT or (tok.type == tokenize.STRING and any(a <= tok.start[0] and tok.end[0] <= b for a, b in docs)):
            continue
        code.update(range(tok.start[0], tok.end[0] + 1))
    return code


def _js_code(text: str) -> set[int]:
    """The lines code or a string's text touches, a blank line inside a string or template included; every line when
    the file ends inside a string, a template, a regex or a block comment."""
    code: set[int] = set()
    state, prev, klass, depth, holes = "code", "", False, 0, []  # holes: the depth each open `${` returns to its template at
    i, line, n = 0, 1, len(text)
    while i < n:
        c = text[i]
        if state == "line":
            state = "code" if c == "\n" else state
        elif state == "block":
            if text.startswith("*/", i):
                state, i = "code", i + 1
        elif state in ("'", '"', "`", "regex"):
            code.add(line)
            if c == "\\":
                i += 1
                line += i < n and text[i] == "\n"
            elif state == "`" and text.startswith("${", i):
                depth += 1
                holes.append(depth)
                state, prev, i = "code", "{", i + 1
            elif state == "regex" and c in "[]":
                klass = c == "["  # inside a class `/` does not close the literal
            elif c == ("/" if state == "regex" else state) and not klass:
                state, prev = "code", ")" if state == "regex" else c
            elif c == "\n" and state != "`":
                state = "code"  # an unterminated literal ends at its line, as the engine refuses it
        elif text.startswith("//", i):
            state, i = "line", i + 1
        elif text.startswith("/*", i):
            state, i = "block", i + 1
        elif not c.isspace():
            code.add(line)
            if c in "'\"`" or (c == "/" and prev in REGEX_AFTER):
                state, klass = ("regex" if c == "/" else c), False
            elif c == "}" and holes and holes[-1] == depth:
                holes.pop()
                depth -= 1
                state = "`"
            elif c.isalnum() or c in "_$":
                j = i
                while j + 1 < n and (text[j + 1].isalnum() or text[j + 1] in "_$"):
                    j += 1
                prev, i = text[i : j + 1], j
            else:
                depth += (c == "{") - (c == "}")
                prev = c
        line += c == "\n"
        i += 1
    return code if state in ("code", "line") else set(range(1, line + 1))


def _prose(path: str, lines: list[str]) -> set[int]:
    """The <base> lines a fold may delete."""
    language = _language(path, lines)
    text = "\n".join(lines) + "\n"
    if language == "python":
        prose = set(range(1, len(lines) + 1)) - _python_code(text)
    elif language == "js":
        prose = set(range(1, len(lines) + 1)) - _js_code(text)
    elif language in ("shell", "yaml"):
        prose = {k for k, t in enumerate(lines, 1) if not t.strip() or t.lstrip().startswith("#")}
    else:
        return set(range(1, len(lines) + 1))
    return prose - {1} if lines and lines[0].startswith("#!") else prose


def _clip(text: str) -> str:
    text = text.strip()
    return text if len(text) <= 120 else text[:117] + "..."


def read_rows(path: pathlib.Path) -> list[Row]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Usage(f"{path} is not a readable JSON file ({exc})") from exc
    if not isinstance(data, list):
        raise Usage(f"{path} is not a JSON array: it holds the `prose` array the pre-review returned")
    rows = []
    for i, item in enumerate(data):
        if not (
            isinstance(item, dict)
            and isinstance(item.get("site"), str)
            and item.get("survives") in SURVIVES
            and isinstance(item.get("ship"), str)
        ):
            raise Usage(
                f"{path}[{i}] is not a prose row: a string `site`, `survives` one of {', '.join(SURVIVES)}, a string `ship`"
            )
        where, _, line = item["site"].rpartition(":")
        if item["survives"] == "keep":
            rows.append(Row(item["site"], "keep", item["ship"], "", 0))
            continue
        if not (where and line.isascii() and line.isdigit() and int(line) > 0):
            raise Usage(f"{path}[{i}]: site {item['site']!r} is not `path:line`")
        rows.append(Row(item["site"], item["survives"], item["ship"], where.removeprefix("./"), int(line)))
    return rows


def check(rows: list[Row], base: str, tip: str) -> list[str]:
    at_base, at_tip = base[:9], tip[:9]
    changed = _changed(base, tip)
    if not changed:
        return [f"the range changes no file: there is no fold at {at_tip}"]
    fails: list[str] = []
    answered = [r for r in rows if r.survives != "keep"]
    named = {r.path for r in answered}
    tip_lines = {p: _lines(tip, p) for p in named | set(changed)}
    base_lines = {p: _lines(base, p) for p in named}
    hunks: dict[str, list[Hunk]] = {p: [] for p in named}
    for p in changed:
        hunks[p], beyond = _hunks(base, tip, p)
        fails += [f"{p}: {what}, which no ship text carries" for what in beyond]
    spans = {r: _occurrences(tip_lines[r.path] or [], _ship_lines(r.ship)) for r in answered if r.survives in SHIPS}
    at_site: dict[Row, list[tuple[int, int]]] = {}

    for r in answered:
        tag = f"{r.site} [{r.survives}]"
        if r.survives == "cut" and _ship_lines(r.ship):
            fails.append(f"{tag}: a cut ships nothing, and this row carries text")
        if r.survives in SHIPS and not _ship_lines(r.ship):
            fails.append(f"{tag}: ships no text")
            continue
        if r.survives in SHIPS and not spans[r]:
            fails.append(f"{tag}: its text is not verbatim in {r.path} at {at_tip}, whole lines compared without indentation")
        if base_lines[r.path] is None:
            fails.append(f"{tag}: {r.path} is not at {at_base}, the tip the rows were read at")
            continue
        if r.line > len(base_lines[r.path]):
            fails.append(f"{tag}: {r.path} has {len(base_lines[r.path])} lines at {at_base}, the tip the rows were read at")
            continue
        if r.line in _deleted(hunks[r.path]):
            if r.survives in SHIPS and spans[r]:
                [h] = [h for h in hunks[r.path] if r.line in _deleted([h])]
                at_site[r] = [span for span in spans[r] if _touches(h, [span], tip_lines[r.path] or [])]
                if not at_site[r]:
                    where = h.new if h.new_count else h.new + 1
                    fails.append(f"{tag}: its text does not stand where its line at {at_base} was, {r.path}:{where} at {at_tip}")
            continue
        now = _to_tip(r.line, hunks[r.path])
        if r.survives == "cut":
            fails.append(f"{tag}: the cut is not made: its line at {at_base} stands at {r.path}:{now} at {at_tip}")
        elif spans[r]:
            at_site[r] = [(s, e) for s, e in spans[r] if s <= now <= e]
            if not at_site[r]:
                fails.append(f"{tag}: its line at {at_base} stands at {r.path}:{now} at {at_tip}, outside its text")

    for p in changed:
        if p not in named:
            fails.append(f"{p}: changed by the range, named by no trim, fix or cut row")
            continue
        texts = [span for r in answered if r.survives in SHIPS and r.path == p for span in at_site.get(r, [])]
        sites = {r.line for r in answered if r.path == p}
        old = base_lines[p] or []
        prose = _prose(p, old)
        fails += [
            f"{p}:{n}: deleted at {at_base}, where it is no comment, docstring or blank line: {_clip(old[n - 1])}"
            for n in sorted(_deleted(hunks[p]) - prose)
        ]
        for h in hunks[p]:
            outside = [
                (h.new + k, t) for k, t in enumerate(h.added) if t.strip() and not any(s <= h.new + k <= e for s, e in texts)
            ]
            fails += [
                f"{p}:{n}: added at {at_tip} outside every trim or fix text standing at its site: {_clip(t)}" for n, t in outside
            ]
            if any(t.strip() for t in h.added) or _deleted([h]) & sites or _touches(h, texts, tip_lines[p] or []):
                continue
            fails.append(
                f"{p}: the hunk at {at_base} line {h.old} ({h.old_count} deleted, {h.new_count} added) touches no row's site or text"
            )
    return fails


def unread(report_dir: pathlib.Path, base: str) -> list[str]:
    entries = ledger.read(report_dir, base, pathlib.Path("."))
    if any(e.get("kind") == "pre-review" and ledger.SHA.match(str(e.get("tip"))) and base.startswith(e["tip"]) for e in entries):
        return []
    return [f"{report_dir / 'ledger.jsonl'} holds no pre-review row at {base[:9]}, the tip the rows were read at"]


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows", type=pathlib.Path, help="the `prose` array the pre-review returned, as JSON")
    parser.add_argument("--range", required=True, type=ledger._range, help="<base>..<tip>, <base> the tip the pre-review read")
    parser.add_argument("--report-dir", required=True, type=pathlib.Path, help="the reportDir whose ledger.jsonl takes the row")
    args = parser.parse_args(argv)
    try:
        rows = read_rows(args.rows)
        base, tip = (_commit(rev) for rev in args.range.split(".."))
        ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", base, tip], capture_output=True)
        if ancestry.returncode:
            raise Usage(f"{args.range}: {base[:9]} is not an ancestor of {tip[:9]}, so the range is no fold of it")
        if not args.report_dir.is_dir():
            raise Usage(f"{args.report_dir} is not a directory: the reportDir the pre-review at {base[:9]} was recorded in")
        fails = unread(args.report_dir, base) + check(rows, base, tip)
    except (Usage, ledger.LedgerError) as exc:
        print(f"fold-check: {exc}", file=sys.stderr)
        return 2
    if fails:
        print("\n".join(f"fold-check: FAIL {line}" for line in fails))
        print(f"fold-check: {len(fails)} failure(s) at {tip[:9]}, nothing written: a fold beyond its ship texts takes a pre-review")
        return 1
    try:
        ledger.append(args.report_dir, ledger.stamped("fold-check", f"{base}..{tip}", tip), None, [])
    except (ledger.LedgerError, OSError) as exc:
        print(f"fold-check: {exc}", file=sys.stderr)
        return 2
    shipped = sum(r.survives in SHIPS for r in rows)
    print(
        f"fold-check: passed at {tip[:9]}, {shipped} text(s) verbatim; a fold-check row appended to {args.report_dir / 'ledger.jsonl'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
