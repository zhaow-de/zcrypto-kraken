"""B4 trial 2's inputs half against spec 00146's measured basis: positions, the BTC shortfall, the limits and turnover, and
no return of a book; over the return indices the rolling set shares with ohlc-full, arm A against record 58's and arm B
against reading 6's SOL/BTC no_borrow cell."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import per_year_positions_differ, per_year_turnover
from cli.alpha.b4 import per_year_counts
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _readings, _trials

pytestmark = pytest.mark.data

# Built from this file's path, never taken from the command: the skip-gate guard admits only a literal-rooted root, and the
# case's first assertion holds it equal to the command's.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_YEARS = dict.fromkeys(map(str, range(2013, 2027)), 0)
# Copied from the spec's measured basis, never from a run. AS_OF, BLOCK, VOUCHED, TURNOVER_A and ENGAGEMENT are what plan
# 00146's pre-flight and record checks import; RETURN_INDICES and SEEN are this case's own.
AS_OF = "2026-10-10"
BLOCK = "c05629c70826656ca225857f6b5b682bfc00a737a0feff91f78b57cf70c93295"
VOUCHED = {"ohlc-rolling": "chained (as of 2026-10-10, line fcb62a79fab7)"}
RETURN_INDICES = 28_495
SEEN = 27_337
TURNOVER_A = 155.62922308759553
ENGAGEMENT = {
    "ratio_first_weight": {"SOL/BTC": 17_079},
    "primary_returns": 11_416,
    "unseen_returns": 1_158,
    "ratio_held_per_year": {"SOL/BTC": _YEARS | {"2021": 514, "2022": 566, "2023": 1_104, "2024": 981, "2025": 705, "2026": 750}},
    "stamps_positions_differ": 9_904,
    "positions_differ_per_year": _YEARS | {"2021": 891, "2022": 1_830, "2023": 2_058, "2024": 1_871, "2025": 1_832, "2026": 1_422},
    "turnover_b": 156.02775785139957,
    "shortfall_stamps_per_year": _YEARS | {"2021": 3, "2022": 14, "2023": 1, "2024": 14, "2025": 6, "2026": 19},
    "shortfall_max": 6.938893903907228e-18,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}


def trial_inputs():
    """The trial's inputs half over the rolling set as of `AS_OF`, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    reads = subjects._b4_sol_reads("b4-sol-noborrow-rolling", reader, "ohlc-rolling", None, AS_OF, False)
    return reader, subjects._b4_sol_inputs(reads)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-rolling/index/2026/10/10.json"),
    reason="the rolling set's line for 2026-10-10 is absent under data/",
)
def test_the_sol_noborrow_inputs_reproduce_the_measured_basis_record_58s_arm_a_and_reading_6s_cell():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    assert compute_hash(reader.block()) == BLOCK and reader.vouched_status() == VOUCHED and reader.holes() == {}
    close = inputs.close
    assert len(close) == RETURN_INDICES and subjects._b4_sol_unseen(close) == SEEN
    record, reading = _trials()[58]["metrics"], _readings()[6]["metrics"]
    seen_a, seen_b = ({i: v[:SEEN] for i, v in book.items()} for book in (inputs.arm_a, inputs.arm_b))
    assert book_turnover(seen_a) == record["turnover_a"]
    assert per_year_turnover(seen_a, close[:SEEN]) == record["turnover_a_per_year"]
    keys = ("turnover", "held_per_year", "shortfall_stamps_per_year", "positions_differ_per_year")
    cell = {key: reading[key]["SOL/BTC"]["no_borrow"] for key in keys}
    assert book_turnover(seen_b) == cell["turnover"]
    assert per_year_counts([p != 0 for p in seen_b["SOL/BTC"]], close[:SEEN]) == cell["held_per_year"]
    shortfall = [s > 0 for s in subjects._b4_shortfall(seen_b)]
    assert per_year_counts(shortfall, close[:SEEN]) == cell["shortfall_stamps_per_year"]
    flat = seen_a | {"SOL/BTC": [0.0] * SEEN}
    assert per_year_positions_differ(flat, seen_b, close[:SEEN]) == cell["positions_differ_per_year"]
    start = ENGAGEMENT["ratio_first_weight"]["SOL/BTC"]
    assert all(inputs.arm_b[a][:start] == inputs.arm_a[a][:start] for a in subjects._ASSETS)
    assert not any(inputs.arm_b["SOL/BTC"][:start]) and inputs.no_borrow is inputs.arm_b
    assert book_turnover(inputs.arm_a) == TURNOVER_A
    engagement = subjects._b4_sol_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {year: round(v, 6) for year, v in engagement["carry_per_year"].items() if round(v, 6)} == {}
