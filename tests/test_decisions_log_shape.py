"""The post-close shape `.claude/skills/iteration-closeout/SKILL.md` routing step 4 gives a phase's
decisions log, checked mechanically: at most one `**Continuation` divider, and only in a phase whose
closeout or exit-bar report is tracked."""

from __future__ import annotations

import re
import subprocess
from fnmatch import fnmatch
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "docs" / "research"
LOGS = sorted(RESEARCH.glob("*-decisions.md"))
_LOG_NAME = re.compile(r"^(?P<serial>\d+(?:\.\d+)*)\.phase(?P<phase>\d+)-decisions\.md$")


def _divider_lines(path: Path) -> list[int]:
    return [i for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1) if line.startswith("**Continuation")]


def _tracked_research_names() -> list[str]:
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "docs/research"], capture_output=True, text=True, check=True)
    return [Path(rel).name for rel in listed.stdout.split()]


def test_the_log_glob_matches_something():
    assert LOGS, "no decisions logs found -- the glob is wrong, not the tree"


@pytest.mark.parametrize("path", LOGS, ids=lambda p: p.name)
def test_a_log_carries_at_most_one_continuation_divider(path: Path):
    found = _divider_lines(path)
    assert len(found) <= 1, (
        f"{path.name}: `**Continuation` dividers at lines {found} -- one marks where the post-close backlog "
        f"begins, and a phase closes once; keep the first and remove the rest"
    )


@pytest.mark.parametrize("path", LOGS, ids=lambda p: p.name)
def test_a_divider_marks_a_phase_whose_closeout_is_tracked(path: Path):
    found = _divider_lines(path)
    if not found:
        return
    m = _LOG_NAME.match(path.name)
    assert m, f"{path.name}: not a `<serial>.phase<N>-decisions.md` name, so its phase cannot be read"
    n = m.group("phase")
    closers = [
        name
        for name in _tracked_research_names()
        if fnmatch(name, f"*.phase{n}-*closeout*.md") or fnmatch(name, f"*.phase{n}-*exit-bar-report.md")
    ]
    assert closers, (
        f"{path.name}:{found[0]}: a `**Continuation` divider, but no tracked `*.phase{n}-*closeout*.md` or "
        f"`*.phase{n}-*exit-bar-report.md` -- the divider marks the backlog after a close that has not happened"
    )
