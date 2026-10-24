"""B4's leg reading's inputs half against spec 00145's measured basis: positions, the shortfall, its carry, the limits and
turnover, and no return of a book."""

from __future__ import annotations

from pathlib import Path

import pytest

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
FIRST_WEIGHT = {"ETH/BTC": 5_442, "SOL/BTC": 17_079}
ENGAGEMENT = {
    "first_weight": FIRST_WEIGHT,
    "primary_returns": {"ETH/BTC": 21_895, "SOL/BTC": 10_258},
    "held_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
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
            "no_borrow": _YEARS
            | {
                "2016": 527,
                "2017": 1_196,
                "2018": 505,
                "2019": 672,
                "2020": 1_099,
                "2021": 970,
                "2022": 685,
                "2023": 648,
                "2024": 655,
                "2025": 726,
                "2026": 298,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 764, "2022": 920, "2023": 1_401, "2024": 1_240, "2025": 1_072, "2026": 285},
            "no_borrow": _YEARS | {"2021": 514, "2022": 566, "2023": 1_104, "2024": 981, "2025": 705, "2026": 234},
        },
    },
    "positions_differ_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
            | {
                "2016": 1_434,
                "2017": 2_160,
                "2018": 1_432,
                "2019": 2_001,
                "2020": 2_060,
                "2021": 2_097,
                "2022": 1_820,
                "2023": 2_155,
                "2024": 1_997,
                "2025": 1_926,
                "2026": 395,
            },
            "no_borrow": _YEARS
            | {
                "2016": 1_428,
                "2017": 2_115,
                "2018": 1_401,
                "2019": 1_902,
                "2020": 2_042,
                "2021": 1_958,
                "2022": 1_757,
                "2023": 2_058,
                "2024": 1_871,
                "2025": 1_832,
                "2026": 395,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 934, "2022": 1_867, "2023": 2_100, "2024": 1_964, "2025": 1_880, "2026": 397},
            "no_borrow": _YEARS | {"2021": 891, "2022": 1_830, "2023": 2_058, "2024": 1_871, "2025": 1_832, "2026": 395},
        },
    },
    "shortfall_stamps_per_year": {
        "ETH/BTC": {
            "carried": _YEARS
            | {
                "2016": 192,
                "2017": 582,
                "2018": 544,
                "2019": 582,
                "2020": 903,
                "2021": 1_255,
                "2022": 983,
                "2023": 727,
                "2024": 477,
                "2025": 621,
                "2026": 292,
            },
            # The twin's shortfall here is float rounding (the basis).
            "no_borrow": _YEARS
            | {
                "2016": 1,
                "2017": 9,
                "2018": 23,
                "2019": 4,
                "2020": 30,
                "2021": 30,
                "2022": 26,
                "2023": 9,
                "2024": 16,
                "2025": 6,
                "2026": 24,
            },
        },
        "SOL/BTC": {
            "carried": _YEARS | {"2021": 330, "2022": 591, "2023": 370, "2024": 620, "2025": 482, "2026": 173},
            "no_borrow": _YEARS | {"2021": 3, "2022": 14, "2023": 1, "2024": 14, "2025": 6, "2026": 8},
        },
    },
    "limit_engaged": {
        leg: {funding: dict.fromkeys(("gross", "net", "margin"), 0) for funding in ("carried", "no_borrow")} for leg in FIRST_WEIGHT
    },
    "turnover": {
        "ETH/BTC": {"carried": 156.66817821488746, "no_borrow": 145.97954113038912},
        "SOL/BTC": {"carried": 147.95819177005933, "no_borrow": 146.4464868776143},
    },
    "context_carry_by_leg": {"ETH/BTC": 0.06755582258742332, "SOL/BTC": 0.015580070714425956},
    "context_turnover_by_leg": {"ETH/BTC": 23.912564023957138, "SOL/BTC": 6.077390770007466, "EUR": 127.65832014316521},
}
# Each carried book's carry per close year at six decimals; the twins' rounds to none.
CARRY_PER_YEAR = {
    "ETH/BTC": {
        "carried": {
            "2016": 0.001688,
            "2017": 0.003143,
            "2018": 0.006144,
            "2019": 0.006081,
            "2020": 0.007869,
            "2021": 0.008174,
            "2022": 0.007188,
            "2023": 0.012772,
            "2024": 0.006037,
            "2025": 0.004446,
            "2026": 0.003996,
        },
        "no_borrow": {},
    },
    "SOL/BTC": {
        "carried": {"2021": 0.001128, "2022": 0.003365, "2023": 0.001298, "2024": 0.004224, "2025": 0.002188, "2026": 0.00119},
        "no_borrow": {},
    },
}


def reading_inputs():
    """The reading's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b4_leg_inputs(subjects._b4_reads("b4-leg-reading", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "ohlc-full/*/BTC/240.parquet"),
    reason="the frozen ohlc-full set or its two ratio legs are absent under data/",
)
def test_the_leg_readings_inputs_reproduce_the_measured_basis_and_record_58s_books():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK and reader.vouched_status() == VOUCHED
    trial, n = inputs.trial, len(inputs.trial.close)
    assert n == RETURN_INDICES
    record = _trials()[58]["metrics"]
    assert subjects._b4_engagement(trial) == {key: record[key] for key in subjects._B4_ENGAGEMENT_KEYS}
    assert inputs.first_weight == trial.first_weight == FIRST_WEIGHT

    def first_differ(book: dict, other: dict) -> int:
        return next((k for k in range(n) if any(book[i][k] != other.get(i, [0.0] * n)[k] for i in book)), n)

    for leg, first in FIRST_WEIGHT.items():
        assert [first_differ(book, trial.arm_a) for book in inputs.books[leg].values()] == [first, first]
    sol = FIRST_WEIGHT["SOL/BTC"]
    for funding, trial_book in (("carried", trial.arm_b), ("no_borrow", trial.no_borrow)):
        assert first_differ(inputs.books["ETH/BTC"][funding], trial_book) == sol and not any(trial_book["SOL/BTC"][:sol])
    engagement = subjects._b4_leg_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert (engagement["turnover_a"], engagement["turnover_b"]) == (record["turnover_a"], record["turnover_b"])
    carry = {
        leg: {funding: {year: round(v, 6) for year, v in years.items() if round(v, 6)} for funding, years in by_funding.items()}
        for leg, by_funding in engagement["carry_per_year"].items()
    }
    assert carry == CARRY_PER_YEAR
