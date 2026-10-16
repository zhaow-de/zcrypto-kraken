#!/usr/bin/env python3
"""A fold made of a pre-review's ship texts alone, checked in place of a fresh pre-review of its tip.

Usage: fold-check.py <rows.json> --range <base>..<tip> --report-dir <dir>, run from the repository. `rows.json` is the
`prose` array the pre-review returned, and <base> is the tip it read: a row's site line is counted there.
A pass needs each `trim` or `fix` text verbatim at <tip> in its site's file -- whole lines, each compared without its
indentation -- with the site's line at <base> deleted or inside that text; each `cut` site's line deleted and its
`ship` empty; every file the range changes named by a non-`keep` row; every hunk touching a row's site line or a
`trim` or `fix` text, blank lines between them counting as touching; and every non-blank line the range adds inside
a `trim` or `fix` text of its own file. What a hunk deletes beside a site it touches is not read: a site's extent at
<base> is not in the rows.
A pass appends a `fold-check` row through `review-ledger.py`'s `append`; review.js and re-review.js admit it at its
own tip alone.
Exit: 0 passed and recorded; 1 a row or a change fails, each printed, nothing written; 2 usage, or git refused.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass, field

SURVIVES = ("trim", "cut", "fix", "keep")
SHIPS = ("trim", "fix")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


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


def _hunks(base: str, tip: str, path: str) -> list[Hunk] | None:
    """None for a binary change."""
    diff = ["--literal-pathspecs", "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--no-renames", "--no-relative", "-U0"]
    hunks: list[Hunk] = []
    for line in _git(*diff, base, tip, "--", path).decode("utf-8", "surrogateescape").split("\n"):
        if m := HUNK.match(line):
            a, b, c, d = m.groups()
            hunks.append(Hunk(int(a), 1 if b is None else int(b), int(c), 1 if d is None else int(d)))
        elif not hunks:
            if line.startswith("Binary files ") or line == "GIT binary patch":
                return None
        elif line.startswith("+"):
            hunks[-1].added.append(line[1:])
    return hunks


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
        found = _hunks(base, tip, p)
        if found is None:
            fails.append(f"{p}: a binary change, which no ship text carries")
        hunks[p] = found or []
    spans = {r: _occurrences(tip_lines[r.path] or [], _ship_lines(r.ship)) for r in answered if r.survives in SHIPS}

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
            continue
        now = _to_tip(r.line, hunks[r.path])
        if r.survives == "cut":
            fails.append(f"{tag}: the cut is not made: its line at {at_base} stands at {r.path}:{now} at {at_tip}")
        elif spans[r] and not any(s <= now <= e for s, e in spans[r]):
            fails.append(f"{tag}: its line at {at_base} stands at {r.path}:{now} at {at_tip}, outside its text")

    for p in changed:
        if p not in named:
            fails.append(f"{p}: changed by the range, named by no trim, fix or cut row")
            continue
        texts = [span for r in answered if r.survives in SHIPS and r.path == p for span in spans[r]]
        sites = {r.line for r in answered if r.path == p}
        for h in hunks[p]:
            outside = [
                (h.new + k, t) for k, t in enumerate(h.added) if t.strip() and not any(s <= h.new + k <= e for s, e in texts)
            ]
            fails += [f"{p}:{n}: added at {at_tip} outside every trim or fix text of the file: {_clip(t)}" for n, t in outside]
            if any(t.strip() for t in h.added) or _deleted([h]) & sites or _touches(h, texts, tip_lines[p] or []):
                continue
            fails.append(
                f"{p}: the hunk at {at_base} line {h.old} ({h.old_count} deleted, {h.new_count} added) touches no row's site or text"
            )
    return fails


def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("rows", type=pathlib.Path, help="the `prose` array the pre-review returned, as JSON")
    parser.add_argument("--range", required=True, type=ledger._range, help="<base>..<tip>, <base> the tip the pre-review read")
    parser.add_argument("--report-dir", required=True, type=pathlib.Path, help="the reportDir whose ledger.jsonl takes the row")
    args = parser.parse_args(argv)
    try:
        if not args.report_dir.is_dir():
            raise Usage(f"{args.report_dir} is not a directory: the reportDir the reads were given")
        rows = read_rows(args.rows)
        base, tip = (_commit(rev) for rev in args.range.split(".."))
        ancestry = subprocess.run(["git", "merge-base", "--is-ancestor", base, tip], capture_output=True)
        if ancestry.returncode:
            raise Usage(f"{args.range}: {base[:9]} is not an ancestor of {tip[:9]}, so the range is no fold of it")
        fails = check(rows, base, tip)
    except Usage as exc:
        print(f"fold-check: {exc}", file=sys.stderr)
        return 2
    if fails:
        print("\n".join(f"fold-check: FAIL {line}" for line in fails))
        print(f"fold-check: {len(fails)} failure(s) at {tip[:9]}, nothing written: a fold beyond its ship texts takes a pre-review")
        return 1
    try:
        ledger.append(args.report_dir, ledger.stamped("fold-check", args.range, tip), None, [])
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
