"""The drill log's heading shape and entry order (spec 00105 D2)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

LOG = Path(__file__).resolve().parents[1] / "docs/reference/drill-log.md"

# The alphabet admits `′`, `+` and `-` because `C′`, `P+R` and `C-ops` are all scenario ids, and it is
# open rather than a closed alternation because a run mints its own sub-drill ids. A hyphen inside an
# id is unambiguous: the field separator is the em dash ` — `, never a bare `-`.
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — ([A-Za-z0-9′+-]+) — (pass|fail|partial|blocked)$")


# Depth is matched without requiring the space: `startswith("## ")` silently DROPS a
# `##2026-09-02 — K — pass` from both assertions, so a typo'd entry would read as absent rather than
# as malformed. The `(?!#)` keeps `###` subsections out of the entry set.
_ENTRY_LEVEL = re.compile(r"^##(?!#)")


def _entry_headings() -> list[str]:
    return [line for line in LOG.read_text(encoding="utf-8").splitlines() if _ENTRY_LEVEL.match(line)]


def test_every_entry_heading_carries_a_date_an_id_and_one_of_four_statuses():
    """Every entry heading parses as date — id — status, `blocked` among the four because it is the
    outcome when the induction never landed at all."""
    for line in _entry_headings():
        assert _HEADING.match(line), f"unparseable drill-log heading {line!r}"


def test_dates_do_not_decrease():
    """Entry dates never decrease. A heading the shape rejects contributes no date, deliberately: it is
    already the assertion above's failure, and would otherwise fail here for carrying no parseable date."""
    dates = [date.fromisoformat(m.group(1)) for line in _entry_headings() if (m := _HEADING.match(line))]
    assert dates == sorted(dates), f"drill-log entries out of chronological order: {[str(d) for d in dates]}"
