"""Shape and completeness of `docs/reference/change-index.md`.

The index is the only git-tracked map from a key — an `iter-NNN`, a 5-digit spec serial, a `T<NNNN>`
topic — to the pull request that carried it, so a broken row costs a reader the PR. It holds no file
path by construction, which is what keeps a rename sweep from ever having to edit it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INDEX = REPO / "docs" / "reference" / "change-index.md"

COLUMNS = ("PR", "date", "title", "iter", "spec", "topic")
TITLE_MAX = 72

# The key grammar the index is written from — the same three expressions `open-pr` reads a branch
# name, a title and a `## Spec / Plan` section with. A PR number is three digits, so it cannot
# collide with a 5-digit serial. A topic key is matched case-insensitively — a branch spells it
# `t0189` — and written with an upper-case T.
_ITER = re.compile(r"\biter-(\d{1,3})\b")
_SPEC = re.compile(r"\b(\d{5})\b")
_TOPIC = re.compile(r"\bT(\d{4})\b", re.IGNORECASE)

# A repo root followed by a slash, or two segments joined by a slash where the second carries a file
# extension — what a rename sweep greps for; a bare `long/flat` inside a title is not a path.
_PATH_LIKE = re.compile(r"(?:cli|tests|infra|docs|\.claude)/|[\w-]+/[\w-]+\.[a-z]+")

_MERGE_SUBJECT = re.compile(r"^Merge pull request #(\d+) from [^/]+/(.+)$")


def _keys(text: str) -> tuple[list[str], list[str], list[str]]:
    """The three key kinds a string carries, iterations zero-padded to three digits."""
    return (
        sorted({"iter-%03d" % int(m) for m in _ITER.findall(text)}),
        sorted(set(_SPEC.findall(text))),
        sorted({"T" + m for m in _TOPIC.findall(text)}),
    )


def _rows() -> list[tuple[int, list[str]]]:
    """Every table row as `(line number, six stripped cells)`."""
    rows = []
    for i, line in enumerate(INDEX.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.startswith("| #"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert len(cells) == len(COLUMNS), f"change-index.md:{i}: {len(cells)} cells, expected {len(COLUMNS)}"
        rows.append((i, cells))
    assert len(rows) > 100, "parsed suspiciously few rows — the row pattern is broken, not the index empty"
    return rows


def _header() -> str:
    """Everything above the table."""
    text = INDEX.read_text(encoding="utf-8")
    head, sep, _ = text.partition("| PR |")
    assert sep, "no `| PR |` header row — the table is gone or renamed"
    return head


def test_every_title_cell_fits_the_column() -> None:
    """A title cell is at most TITLE_MAX characters."""
    offenders = [(line, len(cells[2]), cells[2]) for line, cells in _rows() if len(cells[2]) > TITLE_MAX]
    assert not offenders, (
        f"a title cell longer than {TITLE_MAX} characters — truncate it when the row is written:\n  "
        + "\n  ".join(f"change-index.md:{line}: {n} chars: {t}" for line, n, t in offenders)
    )


def test_no_cell_carries_a_path_shaped_token() -> None:
    """No cell in a row matches a repo-root path or a slashed filename."""
    offenders = []
    for line, cells in _rows():
        for column, cell in zip(COLUMNS, cells):
            match = _PATH_LIKE.search(cell)
            if match:
                offenders.append((line, column, match.group(0)))
    assert not offenders, (
        "a path-shaped token in a cell — a rename sweep would have to edit this file; write the "
        "token's slash as a hyphen:\n  "
        + "\n  ".join(f"change-index.md:{line}: {column} cell carries {tok!r}" for line, column, tok in offenders)
    )


def test_pr_numbers_are_unique_and_ascending() -> None:
    """The PR column rises strictly from row to row."""
    numbers = []
    for line, cells in _rows():
        assert cells[0].startswith("#"), f"change-index.md:{line}: PR cell {cells[0]!r} does not start with '#'"
        numbers.append((line, int(cells[0][1:])))
    out_of_order = [(line, number, previous) for (line, number), (_, previous) in zip(numbers[1:], numbers) if number <= previous]
    assert not out_of_order, "the PR column is not strictly ascending — a duplicate or a misplaced row:\n  " + "\n  ".join(
        f"change-index.md:{line}: #{number} follows #{previous}" for line, number, previous in out_of_order
    )


def test_every_keyed_merge_on_develop_has_a_row() -> None:
    """Every first-parent merge whose branch name carries a key is a row in the index."""
    shallow = subprocess.run(
        ["git", "-C", str(REPO), "rev-parse", "--is-shallow-repository"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    if shallow == "true":
        pytest.skip("shallow clone: develop's merge history is absent here, so completeness is unmeasurable")
    ref = next(
        (
            candidate
            for candidate in ("develop", "origin/develop")
            if subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", candidate]).returncode == 0
        ),
        None,
    )
    if ref is None:
        pytest.skip("no develop ref in this checkout, so completeness is unmeasurable")
    subjects = subprocess.run(
        ["git", "-C", str(REPO), "log", "--merges", "--first-parent", "--format=%s", ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    # The positive trace: an empty or truncated log would otherwise report every row present.
    assert len(subjects) > 100, f"{len(subjects)} first-parent merges on {ref} — the log is truncated, not the history short"
    keyed = {}
    for subject in subjects:
        match = _MERGE_SUBJECT.match(subject)
        if not match:
            continue
        branch = match.group(2)
        if any(_keys(branch)):
            keyed[int(match.group(1))] = branch
    assert keyed, "no merge subject on this ref carries a key — the subject pattern is broken, not the history keyless"
    present = {int(cells[0][1:]) for _, cells in _rows()}
    missing = sorted(set(keyed) - present)
    assert not missing, "a keyed merge on develop with no row in the index:\n  " + "\n  ".join(
        f"PR #{number} (branch {keyed[number]})" for number in missing
    )


def test_the_header_names_the_skill_that_writes_a_row() -> None:
    """The header paragraph names `open-pr` as the writer."""
    assert "open-pr" in _header(), (
        "the header does not name `open-pr` — a reader cannot tell who writes a row, and the next PR-open improvises one"
    )
