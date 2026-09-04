#!/usr/bin/env python3
"""Flag prose over the repo's bars: comment blocks, prose-heavy files, long table rows, long sections, long changelog entries.
Usage: prose-tripwire.py [--since REV] [PATH ...] — default scope cli/ tests/ infra/ (py sh yml yaml) and docs/reference/ docs/universe/ infra/runbooks/ docs/iterations-history*.md docs/open-topics/*.md README.md; never docs/specs/ docs/plans/ docs/research/ docs/open-topics/archive/ docs/reference/ops-journal/."""

from __future__ import annotations

import argparse
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
TABLE_ROW_CHARS = 200
SECTION_BYTES = 2048
CHANGELOG_BULLETS = 5

KINDS = ("comment-block", "file-prose", "table-row", "section", "changelog-entry")
CODE_ROOTS = ("cli", "tests", "infra")
CODE_SUFFIXES = (".py", ".sh", ".yml", ".yaml")
DOC_ROOTS = ("docs/reference", "docs/universe", "infra/runbooks")
DOC_GLOBS = ("docs/iterations-history*.md", "docs/open-topics/*.md", "README.md")
EXCLUDED = ("docs/specs/", "docs/plans/", "docs/research/", "docs/open-topics/archive/", "docs/reference/ops-journal/", ".claude/")

_HEADING = re.compile(r"^(#{1,6})\s+\S")
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


def _tokenize(src: str):
    prose, code, comments, docstrings = set(), set(), set(), []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                prose.add(tok.start[0])
                comments.add(tok.start[0])
            elif tok.type == tokenize.STRING and tok.string.lstrip("rbuRBU").startswith(('"""', "'''")):
                prose.update(range(tok.start[0], tok.end[0] + 1))
                docstrings.append((tok.start[0], tok.end[0]))
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
    return [Block(s, e, text[s - 1].strip()) for s, e in sorted(spans)]


def hash_blocks(src: str) -> list[Block]:
    text = src.splitlines()
    marked = {i for i, line in enumerate(text, 1) if line.lstrip().startswith("#") and not (i == 1 and line.startswith("#!"))}
    return [Block(s, e, text[s - 1].strip()) for s, e in _runs(marked)]


def _block_offenders(path: str, blocks: list[Block]) -> list[Offender]:
    return [
        Offender(path, b.start, "comment-block", b.end - b.start + 1, COMMENT_BLOCK_LINES, b.anchor)
        for b in blocks
        if b.end - b.start + 1 > COMMENT_BLOCK_LINES
    ]


def python_offenders(path: str, src: str) -> list[Offender]:
    out = _block_offenders(path, python_blocks(src))
    measured = measure_python(src)
    if measured and measured[0] and measured[1] * 100 > FILE_PROSE_PERCENT * measured[0]:
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
                out.append(Offender(path, i, "table-row", width, TABLE_ROW_CHARS, line.split("|")[1].strip()))
        m = _HEADING.match(line)
        if m:
            headings.append((i, len(m.group(1))))
    starts = [1] + [s for s, _ in headings if s > 1]
    for n, start in enumerate(starts):
        end = starts[n + 1] if n + 1 < len(starts) else len(text) + 1
        size = sum(len(line.encode()) + 1 for line in text[start - 1 : end - 1])
        if size > SECTION_BYTES:
            out.append(Offender(path, start, "section", size, SECTION_BYTES, text[start - 1].strip()))
    for n, (start, level) in enumerate(headings):
        if changelog and level == 2:
            end = next((s for s, lv in headings[n + 1 :] if lv <= 2), len(text) + 1)
            body = text[start - 1 : end - 1]
            bullets = sum(1 for k, line in enumerate(body, start) if line.startswith("- ") and not fenced[k - 1])
            if bullets > CHANGELOG_BULLETS:
                out.append(Offender(path, start, "changelog-entry", bullets, CHANGELOG_BULLETS, text[start - 1].strip()))
    return out


def offenders_for(path: str, src: str) -> list[Offender]:
    suffix = os.path.splitext(path)[1]
    if suffix == ".py":
        return python_offenders(path, src)
    if suffix in (".sh", ".yml", ".yaml"):
        return _block_offenders(path, hash_blocks(src))
    if suffix == ".md":
        return markdown_offenders(path, src, bool(_CHANGELOG.fullmatch(os.path.basename(path))))
    return []


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


def render(offenders: list[Offender]) -> str:
    lines = [f"{o.path}:{o.line}: {o.kind} {o.measured:.10g} > {o.threshold}" for o in offenders]
    counts = " ".join(f"{kind}={sum(1 for o in offenders if o.kind == kind)}" for kind in KINDS)
    lines.append(f"offenders: {counts} (total {len(offenders)})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    thresholds = " ".join(
        f"{name}={globals()[name]}"
        for name in ("COMMENT_BLOCK_LINES", "FILE_PROSE_PERCENT", "TABLE_ROW_CHARS", "SECTION_BYTES", "CHANGELOG_BULLETS")
    )
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog=f"thresholds: {thresholds}")
    parser.add_argument("paths", nargs="*", help="files or directories to scan; default: the repo's live prose")
    parser.add_argument("--since", metavar="REV", help="report only offenders absent at REV")
    args = parser.parse_args(argv)
    paths = expand_paths(args.paths) if args.paths else default_paths()
    offenders = scan(paths)
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
