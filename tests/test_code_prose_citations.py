"""Guard for `.claude/rules/prose.md`'s resolvable-citation rule.

A plan-local task number outlives the point-in-time plan it indexes, so it means nothing to a cold
reader. `docs/` is out of scope on purpose — there a bare task number names the document's own
structure — and the preceding-line excuse is deliberately loose: requiring the serial to be the
citation's own would reject the wrapped form."""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Case-insensitive and hyphen-or-space: a capital-and-space-only pattern reports every other
# spelling clean.
_TASK_TOKEN = re.compile(r"\btask[\s-]\d+", re.IGNORECASE)
_SERIAL = re.compile(r"\b\d{5}\b")
# `*.md` is in scope because `infra/`'s runbooks and READMEs are read DURING a deploy, where an
# unresolvable citation costs an operator mid-converge.
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
