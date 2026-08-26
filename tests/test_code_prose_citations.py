"""Guard for `.claude/rules/code-prose.md`'s resolvable-citation rule.

A plan-local task number means nothing to a cold reader: the plan it indexes is a point-in-time
document, so the number outlives its referent by construction. Nineteen such citations had
accumulated in `tests/` alone before the 2026-08-26 sweep zeroed them; this keeps the count at
zero. Any task-number token in code prose must carry a 5-digit spec/plan serial on the same or the
immediately preceding line (the wrapped-citation form), which is what makes it resolvable.

Scoped to the code trees (`cli/`, `tests/`, `infra/`) on purpose: `docs/` specs and plans are
point-in-time records where a bare task number names the document's own structure — the genre, not
a defect. The match pattern is hyphen-or-space (the hyphenated and spaced forms alike): the sweep's edit
pattern was space-only and a broader verification pattern is what caught the hyphenated stragglers.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_TASK_TOKEN = re.compile(r"\btask[\s-]\d+", re.IGNORECASE)
_SERIAL = re.compile(r"\b\d{5}\b")
# `*.md` is in scope: `infra/`'s runbooks and READMEs are read DURING a deploy — one offender sat
# on an attended start step. Case-insensitive for the same reason the pattern takes a hyphen OR a
# space: a lowercase task number sat in `cli/` while a capital-only pattern reported the tree clean.
_GLOBS = ("*.py", "*.yml", "*.yaml", "*.sh", "*.j2", "*.alloy", "*.md")


def _candidate_files() -> list[Path]:
    out = {
        p
        for root in ("cli", "tests", "infra")
        for pattern in _GLOBS
        for p in (REPO / root).rglob(pattern)
        if "__pycache__" not in p.parts
    }
    assert len(out) > 100, "suspiciously few files — the walk is broken, not the tree clean"
    return sorted(out)


def test_every_plan_task_number_carries_its_serial():
    offenders = []
    for path in _candidate_files():
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue  # binary masquerading under a text glob
        for i, line in enumerate(lines):
            if _TASK_TOKEN.search(line) and not (_SERIAL.search(line) or (i > 0 and _SERIAL.search(lines[i - 1]))):
                offenders.append(f"{path.relative_to(REPO)}:{i + 1}: {line.strip()[:100]}")
    assert not offenders, (
        "a plan-task number with no resolving serial on the same or preceding line — a cold reader "
        "cannot follow it (write it as e.g. `spec 00053 Task 3`, or name the thing itself):\n  " + "\n  ".join(offenders)
    )
