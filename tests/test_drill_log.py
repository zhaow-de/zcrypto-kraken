"""The drill log's heading shape and entry order (spec 00105 D2), and nothing about the prose beneath a heading."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "docs/reference/drill-log.md"

# The id alphabet is letters, digits, `′`, `+` and `-`: `C′`, `P+R` and `C-ops` are all scenario ids,
# so `[A-Za-z0-9]+` rejects real entries and a closed alternation of the ids named up front rejects
# every sub-drill id a run mints. A hyphen inside an id is unambiguous because the field separator is
# the em dash ` — `, never a bare `-`.
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — ([A-Za-z0-9′+-]+) — (pass|fail|partial|blocked)$")


# Depth is matched without requiring the space, because `startswith("## ")` silently DROPS a
# `##2026-09-02 — K — pass` from both assertions below: the shape check never sees it to reject it,
# and its date never joins the ordering list. A typo'd entry would read as absent rather than as
# malformed. The `(?!#)` keeps `###` subsections out of the entry set.
_ENTRY_LEVEL = re.compile(r"^##(?!#)")


def _entry_headings() -> list[str]:
    return [line for line in LOG.read_text(encoding="utf-8").splitlines() if _ENTRY_LEVEL.match(line)]


def test_every_entry_heading_carries_a_date_an_id_and_one_of_four_statuses():
    """`blocked` is admitted alongside `pass`, `fail` and `partial` because it is the outcome when the
    induction never landed at all. A three-value alternation here does not make such a run go away; it
    makes the writer either loosen this guard or relabel the run `fail` — asserting that a guard did not
    fire when nothing exercised it — and both leave a false record behind."""
    for line in _entry_headings():
        assert _HEADING.match(line), f"unparseable drill-log heading {line!r}"


def test_dates_do_not_decrease():
    """The dates come from the shape match, so a heading the shape rejects contributes none here.
    That is deliberate: such a heading is already the assertion above's failure, and parsing the date
    field before checking the shape would report an ordering failure for a heading carrying no
    parseable date — leaving a reader of a single red run unable to tell which defect landed."""
    dates = [date.fromisoformat(m.group(1)) for line in _entry_headings() if (m := _HEADING.match(line))]
    assert dates == sorted(dates), f"drill-log entries out of chronological order: {[str(d) for d in dates]}"
