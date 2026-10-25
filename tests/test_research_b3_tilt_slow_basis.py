"""B3 trial 2's inputs half against spec 00148's measured basis."""

from __future__ import annotations

import math
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
_SHORT = "20-50-100@0.12"
_LONG = ("60-120-240@0.1", "60-120-240@0.12")
# Copied from the spec's measured basis, never from a run.
BLOCK = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
_ARMS = (_SHORT, *_LONG)
# The basket is the same at every arm: its weights and scores read no direction.
HISTOGRAM = dict.fromkeys(
    _ARMS,
    {
        "0": 540,
        "1": 4_124,
        "2": 3_062,
        "3": 1_098,
        "4": 2_790,
        "5": 2_596,
        "6": 1_401,
        "7": 249,
        "8": 1_714,
        "9": 1_303,
        "10": 8_460,
    },
)
ENGAGEMENT = {
    "tilt_first_engaged": 15_672,
    "primary_returns": 11_665,
    "stamps_positions_differ": 9_687,
    "positions_differ_per_year": _YEARS
    | {"2020": 171, "2021": 1_904, "2022": 1_762, "2023": 1_940, "2024": 1_805, "2025": 1_717, "2026": 388},
    "tilted_per_year": {
        _SHORT: _YEARS | {"2020": 144, "2021": 1_597, "2022": 1_286, "2023": 1_634, "2024": 1_415, "2025": 1_343, "2026": 315},
        **dict.fromkeys(
            _LONG, _YEARS | {"2020": 170, "2021": 1_684, "2022": 1_215, "2023": 1_661, "2024": 1_444, "2025": 1_304, "2026": 342}
        ),
    },
    "ranked_assets_histogram": HISTOGRAM,
    "ranked_assets_mean": {
        arm: math.fsum(int(m) * c for m, c in counts.items()) / RETURN_INDICES for arm, counts in HISTOGRAM.items()
    },
    "turnover_b": 171.84195562051642,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
}


def trial_inputs():
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b3_slow_inputs(subjects._b3_reads("b3-tilt-slow", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set is absent under data/",
)
def test_the_tilt_slow_inputs_reproduce_the_measured_basis_and_record_58s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    block = reader.block()
    assert compute_hash(block) == BLOCK == _trials()[60]["dataset_hash"] and reader.vouched_status() == VOUCHED
    assert len(inputs.close) == RETURN_INDICES
    record = _trials()[58]
    assert block["ohlc-full"]["files"] == {p: h for p, h in record["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    assert book_turnover(inputs.arm_a) == record["metrics"]["turnover_a"]
    engagement = subjects._b3_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {arm: round(mean, 4) for arm, mean in engagement["ranked_assets_mean"].items()} == dict.fromkeys(_ARMS, 5.775)
