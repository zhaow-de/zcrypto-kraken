"""B4 trial 1's inputs half against spec 00144's measured basis: positions, exposures, the shortfall, its carry and
turnover, and no return of a book."""

from __future__ import annotations

from pathlib import Path

import pytest

from cli.alpha.b1 import book_turnover
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under
from tests.test_trial_registry_provenance import _trials

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
_YEARS = dict.fromkeys(map(str, range(2013, 2027)), 0)
# Copied from the spec's measured basis, never from a run.
BLOCK = "9e0fc8e51ace8ac710c08ea3381eb930e2ca43cbedb258e9b5a155f39182d7df"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
ENGAGEMENT = {
    "ratio_first_weight": {"ETH/BTC": 5_442, "SOL/BTC": 17_079},
    "primary_returns": 21_895,
    "ratio_held_per_year": {
        "ETH/BTC": _YEARS
        | {
            "2016": 644,
            "2017": 1_443,
            "2018": 696,
            "2019": 1_010,
            "2020": 1_376,
            "2021": 1_582,
            "2022": 1_141,
            "2023": 1_115,
            "2024": 939,
            "2025": 1_127,
            "2026": 324,
        },
        "SOL/BTC": _YEARS | {"2021": 764, "2022": 920, "2023": 1_401, "2024": 1_240, "2025": 1_072, "2026": 285},
    },
    "stamps_positions_differ": 19_648,
    "positions_differ_per_year": _YEARS
    | {
        "2016": 1_434,
        "2017": 2_160,
        "2018": 1_432,
        "2019": 2_001,
        "2020": 2_060,
        "2021": 2_097,
        "2022": 1_919,
        "2023": 2_155,
        "2024": 2_031,
        "2025": 1_962,
        "2026": 397,
    },
    "shortfall_stamps_per_year": _YEARS
    | {
        "2016": 192,
        "2017": 582,
        "2018": 544,
        "2019": 582,
        "2020": 903,
        "2021": 1_430,
        "2022": 1_273,
        "2023": 973,
        "2024": 920,
        "2025": 1_025,
        "2026": 355,
    },
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}
# Arm B's turnover at two decimals, and the carry per close year at six.
TURNOVER_B = 157.65
CARRY_PER_YEAR = {
    "2016": 0.001688,
    "2017": 0.003143,
    "2018": 0.006144,
    "2019": 0.006081,
    "2020": 0.007869,
    "2021": 0.009872,
    "2022": 0.011097,
    "2023": 0.013902,
    "2024": 0.010192,
    "2025": 0.007084,
    "2026": 0.006064,
}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b4_inputs(subjects._b4_reads("b4-ratio-legs", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "ohlc-full/*/BTC/240.parquet"),
    reason="the frozen ohlc-full set or its two ratio legs are absent under data/",
)
def test_the_ratio_legs_inputs_reproduce_the_measured_basis_and_record_57s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    block = reader.block()
    assert compute_hash(block) == BLOCK and reader.vouched_status() == VOUCHED
    assert len(inputs.close) == RETURN_INDICES
    # Arm A is record 57's: the same ten files, and its turnover to the last bit.
    record = _trials()[57]
    assert {p: h for p, h in block["ohlc-full"]["files"].items() if "/EUR/" in p} == record["datasets"]["ohlc-full"]["files"]
    assert book_turnover(inputs.arm_a) == record["metrics"]["turnover_a"]
    start = min(ENGAGEMENT["ratio_first_weight"].values())
    assert all(inputs.arm_b[a][:start] == inputs.arm_a[a][:start] for a in subjects._ASSETS)
    engagement = subjects._b4_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert round(engagement["turnover_b"], 2) == TURNOVER_B
    assert {year: round(v, 6) for year, v in engagement["carry_per_year"].items() if v} == CARRY_PER_YEAR
