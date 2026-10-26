"""B3 trial 3's inputs half against spec 00149's measured basis."""

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
_NONE = dict.fromkeys(_YEARS, 0.0)
# Copied from the spec's measured basis, never from a run.
BLOCK = "ff2e5700695b3fbc9e077a3d4bc2c4618720f61cd9c1a024430fbf7501719a69"
VOUCHED = {"ohlc-full": "checked (36 vouched hashes)"}
RETURN_INDICES = 27_337
# Trial 1's tilt, unchanged: its engagement is record 60's stored figures, read off the record.
TILT = ("tilted_per_year", "ranked_assets_histogram", "ranked_assets_mean")
ENGAGEMENT = {
    "tilt_first_engaged": 1_230,
    "primary_returns": 26_107,
    "stamps_positions_differ": 12_493,
    "positions_differ_per_year": _YEARS
    | {
        "2014": 332,
        "2015": 457,
        "2018": 801,
        "2019": 668,
        "2020": 419,
        "2021": 1_934,
        "2022": 1_826,
        "2023": 2_021,
        "2024": 1_848,
        "2025": 1_792,
        "2026": 395,
    },
    "turnover_b": 216.05774709807375,
    "limit_engaged_per_year": dict.fromkeys(("gross", "net", "margin"), _YEARS),
    "arm_a_limit_engaged": dict.fromkeys(("gross", "net", "margin"), 0),
    "short_state_per_year": _YEARS
    | {
        "2014": 1_038,
        "2015": 1_096,
        "2018": 1_522,
        "2019": 806,
        "2020": 331,
        "2021": 421,
        "2022": 1_900,
        "2023": 270,
        "2024": 414,
        "2025": 660,
        "2026": 495,
    },
    "overlay_per_year": _YEARS
    | {
        "2014": 332,
        "2015": 457,
        "2018": 801,
        "2019": 668,
        "2020": 248,
        "2021": 252,
        "2022": 1_540,
        "2023": 194,
        "2024": 307,
        "2025": 421,
        "2026": 350,
    },
    "overlay_first_engaged": 1_230,
    "shortfall_stamps_per_year": _YEARS
    | {"2018": 623, "2019": 544, "2020": 217, "2021": 199, "2022": 1_437, "2023": 178, "2024": 307, "2025": 415, "2026": 339},
    "shortfall_mean_per_year": _NONE
    | {
        "2018": 0.008849321558105853,
        "2019": 0.009562699914014232,
        "2020": 0.004447907274989879,
        "2021": 0.0011967031387723332,
        "2022": 0.02383134038097913,
        "2023": 0.0037384793611536823,
        "2024": 0.009359009965511707,
        "2025": 0.005135563259268716,
        "2026": 0.05735237611576036,
    },
    "shortfall_max": 0.2907872334820236,
    "carry_per_year": _NONE
    | {
        "2018": 0.004150086469044866,
        "2019": 0.004381962309770746,
        "2020": 0.0021500975698908443,
        "2021": 0.0005914662643196171,
        "2022": 0.010977979120356715,
        "2023": 0.001849522542579138,
        "2024": 0.004532077251367467,
        "2025": 0.0024507149403084714,
        "2026": 0.006488353705264844,
    },
}
NO_BORROW = {"differ_from_arm_b": 4_259, "turnover": 191.899092913884}


def trial_inputs():
    """The trial's inputs half over the real set, with the reader that read it."""
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b3_overlay_inputs(subjects._b3_reads("b3-btc-overlay", reader, "ohlc-full", None, False))


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet"),
    reason="the frozen ohlc-full set is absent under data/",
)
def test_the_btc_overlay_inputs_reproduce_the_measured_basis_record_60s_tilt_and_record_58s_arm_a():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = trial_inputs()
    trial = inputs.trial
    block = reader.block()
    assert compute_hash(block) == BLOCK == _trials()[60]["dataset_hash"] and reader.vouched_status() == VOUCHED
    assert len(trial.close) == RETURN_INDICES
    record = _trials()[58]
    assert block["ohlc-full"]["files"] == {p: h for p, h in record["datasets"]["ohlc-full"]["files"].items() if "/EUR/" in p}
    assert book_turnover(trial.arm_a) == record["metrics"]["turnover_a"]
    engagement = subjects._b3_engagement(trial) | subjects._b3_overlay_engagement(inputs)
    assert {key: engagement[key] for key in ENGAGEMENT} == ENGAGEMENT
    assert {key: engagement[key] for key in TILT} == {key: _trials()[60]["metrics"][key] for key in TILT}
    differ = sum(any(inputs.no_borrow[a][k] != trial.arm_b[a][k] for a in trial.arm_b) for k in range(RETURN_INDICES))
    assert {"differ_from_arm_b": differ, "turnover": book_turnover(inputs.no_borrow)} == NO_BORROW
    assert min(inputs.no_borrow["BTC"]) == 0.0 and all(min(v) >= 0.0 for a, v in trial.arm_b.items() if a != "BTC")
    before = range(_trials()[60]["metrics"]["tilt_first_engaged"])
    assert sum(any(trial.arm_b[a][k] != trial.arm_a[a][k] for a in trial.arm_a) for k in before) == 2_506
    net = [math.fsum(v[k] for v in trial.arm_b.values()) for k in range(RETURN_INDICES)]
    gross = [math.fsum(abs(v[k]) for v in trial.arm_b.values()) for k in range(RETURN_INDICES)]
    assert (min(net), round(max(net), 6), round(max(gross), 6)) == (0.0, 0.9983, 0.9983)
