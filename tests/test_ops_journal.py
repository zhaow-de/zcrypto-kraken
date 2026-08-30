"""The journal is greppable, not a schema: two rules, and nothing about the prose."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

JOURNAL = Path(__file__).resolve().parents[1] / "docs/reference/ops-journal"
_HEADING = re.compile(r"^## (\d{4}-\d{2}-\d{2}) — (all-clear|attention|incident)$")


def _month_files() -> list[Path]:
    return sorted(JOURNAL.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9].md"))


def test_every_entry_heading_is_a_date_with_one_of_the_three_verdicts():
    """A heading the pass cannot parse is an entry nobody can count -- "how many all-clear days"
    is the one question the journal exists to answer."""
    for path in _month_files():
        for line in path.read_text().splitlines():
            if line.startswith("## "):
                assert _HEADING.match(line), f"{path.name}: unparseable heading {line!r}"


def test_dates_increase_within_a_file_and_match_its_name():
    for path in _month_files():
        dates = [date.fromisoformat(m.group(1)) for line in path.read_text().splitlines() if (m := _HEADING.match(line))]
        assert dates == sorted(dates), f"{path.name}: entries out of order"
        assert len(dates) == len(set(dates)), f"{path.name}: a day appears twice"
        assert all(f"{d:%Y-%m}" == path.stem for d in dates), f"{path.name}: an entry from another month"
