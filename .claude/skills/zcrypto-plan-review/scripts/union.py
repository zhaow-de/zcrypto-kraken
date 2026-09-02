#!/usr/bin/env python3
"""Mechanical union of review reports for the `zcrypto-plan-review` skill.

Reads N reports, clusters findings on their `<path>:<line>` heading key and keeps the MAXIMUM
severity across reports — never a vote, never an average, never a consolidating judgement: the
same defect graded Critical by one reviewer and Important by another ships as Important under any
other rule (`docs/research/90.spec-plan-review-protocol.md`). Counts are derived from the parsed
headings, never from a reviewer's own summary line, which under-reports.

Usage: union.py OUT.md REPORT.md [REPORT.md ...]

A heading candidate is any run of three or more `#`, indented, blockquoted or list-prefixed or not — a reviewer that
nests its findings under a `### Findings` title writes them as `####`, and a parser keyed on exactly
`### ` absorbs every one of them into the previous body. Exit 0 on success. Exit 2 when any candidate
fails the shape below: those are listed under `## Unparsed` in OUT.md and MUST be read — an unparsed
finding is a finding, not noise (a bare section title lands there too, as does a finding written at one or
two hashes). Two reports naming one line two
ways are two keys — the safe direction, the fixer reads both — and the script does not try to merge them.
A fenced block is body whatever it contains — fences follow CommonMark (backtick or tilde, closed only by
the same character at the same length or longer inside the same blockquote or list item as the opener, or
by the end of that container; tabs count four columns) and a fence still open at end of file is surfaced under
`## Unparsed`, since everything after it was read as body; a blockquoted heading is a heading; a sub-heading inside
a finding is surfaced under `## Unparsed` without closing that finding's body.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path

SEVERITY_RANK = {"Critical": 0, "Important": 1, "Minor": 2}
ORIGIN_RANK = {"last-fix": 0, "earlier-fix": 1, "in-original": 2}  # most recent origin wins the cluster
_PREFIX = r"^\s*(?:>\s*)?(?:[-*+]\s+|\d+[.)]\s+)?"  # blockquote, indentation, list marker: not part of the heading
CANDIDATE = re.compile(_PREFIX + r"#{3,}")  # no space / seven hashes still surface, never sink into a body
SECTION = re.compile(_PREFIX + r"#{1,2}\s")
# A finding written at one or two hashes is a typo of the required form, not a section. Without this it
# matches SECTION, closes the open block and vanishes with exit 0 — the one failure this script exists to
# prevent. Surfaced instead, so the round's counts are never silently short.
MALFORMED = re.compile(_PREFIX + r"#{1,2}\s+\[?(?:Critical|Important|Minor)\]? · ")
# The brackets are optional on read: reviewers routinely drop them (the template once showed them as
# choose-one notation), and a finding whose severity is plain is still a finding — parsing it is the
# safe direction, since the alternative is a real Critical counted as zero.
HEADING = re.compile(
    _PREFIX + r"#{3,6}\s+\[?(Critical|Important|Minor)\]? · \[?(in-original|earlier-fix|last-fix)\]? · (\S.*?)\s*$"
)
# CommonMark fences. An opener may sit inside a blockquote and/or a list item; it closes on a bare run of the
# same character at the same length or longer, indented at most three columns or no deeper than its own opener, INSIDE that
# same container — or when the container itself ends. A `> ```` line inside a column-0 fence is content, not
# a closer. Tabs are expanded to four columns once, at the fence layer; the body keeps the raw line. Decision:
# an opener indented four or more columns past its container is still read as a fence — its container may
# be a list item the union does not track — where CommonMark outside a list would read indented code.
BLOCKQUOTE = re.compile(r"^\s*> ?")
OPENER = re.compile(r"^(?P<indent> *)(?P<li>[-*+] +|\d+[.)] +)?(?P<run>`{3,}|~{3,})")
CLOSER = re.compile(r"^( *)(`{3,}|~{3,})\s*$")


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip(" "))


@dataclass(frozen=True)
class _Fence:
    char: str
    length: int
    line: int
    blockquote: bool
    indent: int  # a markerless opener's own indent inside its container; 0 for a list fence
    item_col: int | None  # content column of the list item holding the opener, measured inside any blockquote

    def _inner(self, line: str) -> str | None:
        """The line's text inside this fence's blockquote — None when the blockquote has ended."""
        if not self.blockquote:
            return line
        m = BLOCKQUOTE.match(line)
        return line[m.end() :] if m else None

    def container_ended(self, line: str) -> bool:
        inner = self._inner(line)
        if inner is None:
            return True
        return self.item_col is not None and bool(inner.strip()) and _indent(inner) < self.item_col

    def closes(self, line: str) -> bool:
        inner = self._inner(line)
        if inner is None:
            return False
        if self.item_col is not None:
            inner = inner[self.item_col :]  # container_ended ran first, so a non-blank line is indented this far
        m = CLOSER.match(inner)
        return bool(m) and len(m[1]) <= max(3, self.indent) and m[2][0] == self.char and len(m[2]) >= self.length


def _open_fence(line: str, lineno: int) -> _Fence | None:
    bq = BLOCKQUOTE.match(line)
    inner = line[bq.end() :] if bq else line
    m = OPENER.match(inner)
    if not m:
        return None
    item_col = len(m["indent"]) + len(m["li"]) if m["li"] else None
    return _Fence(m["run"][0], len(m["run"]), lineno, bool(bq), 0 if m["li"] else len(m["indent"]), item_col)


def parse(path: Path) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    unparsed: list[str] = []
    current: dict | None = None
    fence: _Fence | None = None
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        probe = line.expandtabs(4)  # the fence layer sees columns; the body keeps the raw line
        if fence is not None and fence.container_ended(probe):
            fence = None  # the line that ended the container is then read as an ordinary line
        if fence is not None:
            if fence.closes(probe):
                fence = None
        elif opened := _open_fence(probe, lineno):
            fence = opened
        elif CANDIDATE.match(line):
            m = HEADING.match(line)
            if m:
                current = {"sev": m[1], "origin": m[2], "key": m[3], "body": [], "src": path.name}
                findings.append(current)
                continue
            unparsed.append(f"{path.name}: {line.strip()}")  # surfaced, and the open finding keeps its body
        elif SECTION.match(line):
            if MALFORMED.match(line):
                unparsed.append(f"{path.name}: {line.strip()}")
            current = None  # a section heading ends the finding block
            continue
        if current is not None:
            current["body"].append(line)
    if fence is not None:
        unparsed.append(f"{path.name}: unclosed fence opened at line {fence.line} — every heading after it was read as body")
    return findings, unparsed


def main(out: str, reports: list[str]) -> int:
    findings: list[dict] = []
    unparsed: list[str] = []
    for r in reports:
        f, u = parse(Path(r))
        findings += f
        unparsed += u

    clusters: dict[str, list[dict]] = {}
    for f in findings:
        clusters.setdefault(f["key"], []).append(f)

    counts = {"Critical": 0, "Important": 0, "Minor": 0}
    lines = ["# Union", ""]
    ordered = sorted(clusters.items(), key=lambda kv: (min(SEVERITY_RANK[f["sev"]] for f in kv[1]), kv[0]))
    for key, members in ordered:
        top = min(members, key=lambda f: SEVERITY_RANK[f["sev"]])
        origin = min(members, key=lambda f: ORIGIN_RANK[f["origin"]])["origin"]
        counts[top["sev"]] += 1
        lines.append(f"### [{top['sev']}] · [{origin}] · {key}")
        for f in members:
            lines.append(f"<!-- {f['src']} graded {f['sev']} -->")
            lines.extend(f["body"])
        lines.append("")
    if unparsed:
        lines += ["## Unparsed", ""] + [f"- {u}" for u in unparsed] + [""]

    summary = (
        f"counts (from headings): Critical {counts['Critical']} · Important {counts['Important']} · "
        f"Minor {counts['Minor']} · keys {len(clusters)} · raw findings {len(findings)} · unparsed {len(unparsed)}"
    )
    Path(out).write_text("\n".join([*lines, summary, ""]), encoding="utf-8")
    print(summary)
    return 2 if unparsed else 0


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: union.py OUT.md REPORT.md [REPORT.md ...]")
    sys.exit(main(sys.argv[1], sys.argv[2:]))
