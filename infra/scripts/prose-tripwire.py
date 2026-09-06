#!/usr/bin/env python3
"""Flag prose over the repo's bars: comment blocks, prose-heavy files, long table rows, long sections, long changelog entries.
Usage: prose-tripwire.py [--since REV | --write-baseline PATH | --check-baseline PATH] [PATH ...] — default scope cli/ tests/ infra/ (py sh yml yaml) and docs/reference/ docs/universe/ infra/runbooks/ docs/iterations-history*.md docs/open-topics/*.md infra/README.md README.md; never docs/specs/ docs/plans/ docs/research/ docs/open-topics/archive/ docs/reference/ops-journal/.
An offender's identity in the baseline is its path, its kind and its anchor — a block's first line, or a row's or heading's first cell, whitespace-normalised — never its line number, which every edit above it moves."""

from __future__ import annotations

import argparse
import ast
import collections
import fnmatch
import glob
import io
import os
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass

COMMENT_BLOCK_LINES = 4
FILE_PROSE_PERCENT = 20
# Code lines below which the percentage is unreachable by construction: one class statement under its
# one-sentence docstring is already half its file, and no edit short of deleting the sentence moves it.
FILE_PROSE_FLOOR = 4
TABLE_ROW_CHARS = 200
SECTION_BYTES = 2048
CHANGELOG_BULLETS = 5

KINDS = ("comment-block", "file-prose", "table-row", "section", "changelog-entry")
CODE_ROOTS = ("cli", "tests", "infra")
CODE_SUFFIXES = (".py", ".sh", ".yml", ".yaml")
DOC_ROOTS = ("docs/reference", "docs/universe", "infra/runbooks")
DOC_GLOBS = ("docs/iterations-history*.md", "docs/open-topics/*.md", "infra/README.md", "README.md")
EXCLUDED = ("docs/specs/", "docs/plans/", "docs/research/", "docs/open-topics/archive/", "docs/reference/ops-journal/", ".claude/")
# A topic file and its index gain a registry section per registration, so only the section bar is dropped.
EXEMPT = {"docs/open-topics/*.md": ("section",)}

_HEADING = re.compile(r"^(#{1,6})\s+\S")
# Whole-file or per-value ansible-vault content: a prose pass never edits it, so it is never reported.
_VAULT = re.compile(r"^[ \t]*\$ANSIBLE_VAULT;", re.MULTILINE)
_CHANGELOG = re.compile(r"iterations-history-phase\d+\.md")
_SKIP_TOKENS = {tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING, tokenize.ENDMARKER}


@dataclass(frozen=True, order=True)
class Offender:
    path: str
    line: int
    kind: str
    measured: float
    threshold: int
    anchor: str

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.path, self.kind, self.anchor)


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    anchor: str


def _docstring_starts(src: str) -> set[int] | None:
    """The line of every AST docstring: the first statement of a module, class or function, and nowhere else."""
    try:
        tree = ast.parse(src)
    except SyntaxError, ValueError:
        return None
    starts = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            starts.add(first.value.lineno)
    return starts


def _tokenize(src: str):
    starts = _docstring_starts(src)
    if starts is None:
        return None
    prose, code, comments, docstrings = set(), set(), set(), []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                prose.add(tok.start[0])
                comments.add(tok.start[0])
            elif tok.type == tokenize.STRING and tok.string.lstrip("rbuRBU").startswith(('"""', "'''")):
                span = range(tok.start[0], tok.end[0] + 1)
                if tok.start[0] in starts:
                    prose.update(span)
                    docstrings.append((tok.start[0], tok.end[0]))
                else:
                    code.update(span)
            elif tok.type not in _SKIP_TOKENS:
                code.add(tok.start[0])
    except tokenize.TokenError, SyntaxError:
        return None
    return prose, code, comments, docstrings


def measure_python(src: str) -> tuple[int, int, int] | None:
    """The reference count: total lines, prose lines, code lines that carry no prose."""
    parsed = _tokenize(src)
    if parsed is None:
        return None
    prose, code, _, _ = parsed
    return src.count("\n"), len(prose), len(code - prose)


def _anchor(text: str) -> str:
    return " ".join(text.split())


def _runs(lines: set[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for n in sorted(lines):
        if out and out[-1][1] == n - 1:
            out[-1] = (out[-1][0], n)
        else:
            out.append((n, n))
    return out


def python_blocks(src: str) -> list[Block]:
    """Comment-only runs and triple-quoted strings, each its own block, in source order."""
    parsed = _tokenize(src)
    if parsed is None:
        return []
    _, code, comments, docstrings = parsed
    text = src.splitlines()
    spans = _runs(comments - code) + docstrings
    return [Block(s, e, _anchor(text[s - 1])) for s, e in sorted(spans)]


def hash_blocks(src: str) -> list[Block]:
    text = src.splitlines()
    marked = {i for i, line in enumerate(text, 1) if line.lstrip().startswith("#") and not (i == 1 and line.startswith("#!"))}
    return [Block(s, e, _anchor(text[s - 1])) for s, e in _runs(marked)]


def _block_offenders(path: str, blocks: list[Block]) -> list[Offender]:
    return [
        Offender(path, b.start, "comment-block", b.end - b.start + 1, COMMENT_BLOCK_LINES, b.anchor)
        for b in blocks
        if b.end - b.start + 1 > COMMENT_BLOCK_LINES
    ]


def python_offenders(path: str, src: str) -> list[Offender]:
    out = _block_offenders(path, python_blocks(src))
    measured = measure_python(src)
    if measured and measured[0] and measured[2] >= FILE_PROSE_FLOOR and measured[1] * 100 > FILE_PROSE_PERCENT * measured[0]:
        percent = round(100 * measured[1] / measured[0], 1)
        out.append(Offender(path, 1, "file-prose", percent, FILE_PROSE_PERCENT, ""))
    return out


def markdown_offenders(path: str, src: str, changelog: bool) -> list[Offender]:
    text = src.splitlines()
    if not text:
        return []
    fenced, inside = [], False
    for line in text:
        if line.lstrip().startswith("```"):
            inside = not inside
            fenced.append(True)
        else:
            fenced.append(inside)
    out: list[Offender] = []
    headings = []
    for i, line in enumerate(text, 1):
        if fenced[i - 1]:
            continue
        if line.startswith("|"):
            width = len(line.rstrip())
            if width > TABLE_ROW_CHARS:
                out.append(Offender(path, i, "table-row", width, TABLE_ROW_CHARS, _anchor(line.split("|")[1])))
        m = _HEADING.match(line)
        if m:
            headings.append((i, len(m.group(1))))
    starts = [1] + [s for s, _ in headings if s > 1]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(text) + 1
        size = sum(len(line.encode()) + 1 for line in text[start - 1 : end - 1])
        if size > SECTION_BYTES:
            out.append(Offender(path, start, "section", size, SECTION_BYTES, _anchor(text[start - 1])))
    for n, (start, level) in enumerate(headings):
        if changelog and level == 2:
            end = next((s for s, lv in headings[n + 1 :] if lv <= 2), len(text) + 1)
            body = text[start - 1 : end - 1]
            bullets = sum(1 for k, line in enumerate(body, start) if line.startswith("- ") and not fenced[k - 1])
            if bullets > CHANGELOG_BULLETS:
                out.append(Offender(path, start, "changelog-entry", bullets, CHANGELOG_BULLETS, _anchor(text[start - 1])))
    return out


def _exempt_kinds(path: str) -> tuple[str, ...]:
    """A glob's `*` never crosses a directory separator, so a nested path is not the exempted one."""
    for pattern, kinds in EXEMPT.items():
        if os.path.dirname(path) == os.path.dirname(pattern) and fnmatch.fnmatchcase(
            os.path.basename(path), os.path.basename(pattern)
        ):
            return kinds
    return ()


def offenders_for(path: str, src: str) -> list[Offender]:
    if _VAULT.search(src):
        return []
    suffix = os.path.splitext(path)[1]
    if suffix == ".py":
        found = python_offenders(path, src)
    elif suffix in (".sh", ".yml", ".yaml"):
        found = _block_offenders(path, hash_blocks(src))
    elif suffix == ".md":
        found = markdown_offenders(path, src, bool(_CHANGELOG.fullmatch(os.path.basename(path))))
    else:
        return []
    exempt = _exempt_kinds(path)
    return [o for o in found if o.kind not in exempt]


def _norm(path: str) -> str:
    return os.path.normpath(os.path.relpath(path)).replace(os.sep, "/")


def _excluded(path: str) -> bool:
    return path.startswith(EXCLUDED)


def _walk(root: str, suffixes: tuple[str, ...]) -> list[str]:
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "__pycache__")
        found += [_norm(os.path.join(dirpath, f)) for f in sorted(filenames) if f.endswith(suffixes)]
    return found


def default_paths() -> list[str]:
    found = [p for root in CODE_ROOTS for p in _walk(root, CODE_SUFFIXES)]
    found += [p for root in DOC_ROOTS for p in _walk(root, (".md",))]
    found += [_norm(p) for pattern in DOC_GLOBS for p in sorted(glob.glob(pattern)) if os.path.isfile(p)]
    return sorted({p for p in found if not _excluded(p)})


def expand_paths(args: list[str]) -> list[str]:
    found = []
    for arg in args:
        if os.path.isdir(arg):
            found += [p for p in _walk(arg, CODE_SUFFIXES + (".md",)) if not _excluded(p)]
        else:
            found.append(_norm(arg))
    return sorted(set(found))


def scan(paths: list[str]) -> list[Offender]:
    out: list[Offender] = []
    for path in paths:
        with open(path, encoding="utf-8", errors="replace") as fh:
            out += offenders_for(path, fh.read())
    return out


def baseline(rev: str, paths: list[str]) -> dict[tuple[str, str, str], list[float]]:
    known: dict[tuple[str, str, str], list[float]] = {}
    for path in paths:
        shown = subprocess.run(["git", "show", f"{rev}:./{path}"], capture_output=True, encoding="utf-8", errors="replace")
        if shown.returncode == 0:
            for o in offenders_for(path, shown.stdout):
                known.setdefault(o.key, []).append(o.measured)
    return known


def new_since(offenders: list[Offender], known: dict[tuple[str, str, str], list[float]]) -> list[Offender]:
    """Each offender consumes one baseline entry -- its exact size first, else the smallest at least as large."""
    fresh, pending = [], []
    for o in sorted(offenders):
        pool = known.get(o.key, [])
        if o.measured in pool:
            pool.remove(o.measured)
        else:
            pending.append(o)
    for o in pending:
        pool = known.get(o.key, [])
        match = next((m for m in sorted(pool) if m >= o.measured), None)
        if match is None:
            fresh.append(o)
        else:
            pool.remove(match)
    return fresh


def _line(o: Offender) -> str:
    return f"{o.path}:{o.line}: {o.kind} {o.measured:.10g} > {o.threshold}"


def baseline_text(offenders: list[Offender]) -> str:
    """The report line plus a tab and the anchor, one per offender, sorted -- generated, never hand-edited.

    An empty anchor leaves the tab off, so no line ends in whitespace a formatting hook would strip.
    """
    return "".join(_line(o) + (f"\t{o.anchor}" if o.anchor else "") + "\n" for o in sorted(offenders))


def read_baseline(path: str) -> collections.Counter:
    known: collections.Counter = collections.Counter()
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            row = raw.rstrip("\n")
            if not row:
                continue
            head, _, anchor = row.partition("\t")
            path_field, _, rest = head.partition(":")
            known[(path_field, rest.split(":", 1)[1].split()[0], anchor)] += 1
    return known


def against_baseline(offenders: list[Offender], known: collections.Counter):
    """New: a path+kind+anchor the baseline does not record. Grown: more of one kind in one file than it records."""
    current = collections.Counter(o.key for o in offenders)
    new = [o for o in sorted(offenders) if not known[o.key]]
    grown = []
    for path, kind in sorted({(p, k) for p, k, _ in current} | {(p, k) for p, k, _ in known}):
        now = sum(n for (p, k, _), n in current.items() if (p, k) == (path, kind))
        was = sum(n for (p, k, _), n in known.items() if (p, k) == (path, kind))
        if now > was:
            grown.append((path, kind, now, was))
    retired = sum(max(0, n - current[key]) for key, n in known.items())
    return new, grown, retired


def render(offenders: list[Offender]) -> str:
    lines = [_line(o) for o in offenders]
    counts = " ".join(f"{kind}={sum(1 for o in offenders if o.kind == kind)}" for kind in KINDS)
    lines.append(f"offenders: {counts} (total {len(offenders)})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    thresholds = " ".join(
        f"{name}={globals()[name]}"
        for name in (
            "COMMENT_BLOCK_LINES",
            "FILE_PROSE_PERCENT",
            "FILE_PROSE_FLOOR",
            "TABLE_ROW_CHARS",
            "SECTION_BYTES",
            "CHANGELOG_BULLETS",
        )
    )
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog=f"thresholds: {thresholds}")
    parser.add_argument("paths", nargs="*", help="files or directories to scan; default: the repo's live prose")
    parser.add_argument("--since", metavar="REV", help="report only offenders absent at REV")
    parser.add_argument("--write-baseline", metavar="PATH", help="write today's offenders to PATH as the ratchet's baseline")
    parser.add_argument("--check-baseline", metavar="PATH", help="fail only on an offender PATH does not record")
    args = parser.parse_args(argv)
    paths = expand_paths(args.paths) if args.paths else default_paths()
    offenders = scan(paths)
    if args.write_baseline:
        with open(args.write_baseline, "w", encoding="utf-8") as fh:
            fh.write(baseline_text(offenders))
        return 0
    if args.check_baseline:
        if not os.path.isfile(args.check_baseline):
            print(f"{args.check_baseline}: no such baseline -- write one with --write-baseline", file=sys.stderr)
            return 2
        new, grown, retired = against_baseline(offenders, read_baseline(args.check_baseline))
        for o in new:
            print(_line(o))
        for path, kind, now, was in grown:
            print(f"grown: {path} {kind} {now} > {was} recorded")
        print(f"new: {len(new)} grown: {len(grown)} retired: {retired}")
        return 1 if new or grown else 0
    if args.since:
        if subprocess.run(["git", "rev-parse", "--verify", "--quiet", args.since], capture_output=True).returncode != 0:
            print(f"{args.since}: not a revision this repository knows", file=sys.stderr)
            return 2
        offenders = new_since(offenders, baseline(args.since, paths))
    offenders.sort()
    print(render(offenders))
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
