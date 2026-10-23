"""B2's re-risk reading's inputs against spec 00142's measured basis; no forward return."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
# Copied from the spec's measured basis, never from a run.
BLOCK = "ad140b62ac72cfd6b4931dbe4f529f29d4dd34ef49d86e791c37764d2cf8eee1"
VOUCHED = {
    "ohlc-full": "checked (36 vouched hashes)",
    "derivatives-funding": "checked (10 vouched hashes)",
    "derivatives-oi": "checked (10 vouched hashes)",
    "liquidations-daily": "checked (10 vouched hashes)",
}
_RETURN_INDICES = 27_337
_TOLERANCE = 1e-12
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_funding_z30d": (15_419, datetime(2020, 10, 22, 8, tzinfo=UTC)),
    "binperp_oi_z30d": (18_026, datetime(2021, 12, 30, 20, tzinfo=UTC)),
    "binperp_ratio_max_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_liq_long_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_oi_log_delta_z30d": (18_027, datetime(2021, 12, 31, tzinfo=UTC)),
    "binperp_oi_momentum_z30d": (18_206, datetime(2022, 1, 29, 20, tzinfo=UTC)),
    "binperp_count_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_sum_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_count_long_short_ratio_z30d": (18_324, datetime(2022, 2, 18, 12, tzinfo=UTC)),
    "binperp_sum_taker_long_short_vol_ratio_z30d": (18_994, datetime(2022, 6, 10, 4, tzinfo=UTC)),
    "binperp_liq_short_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_liq_total_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, its long ones below its full-long size and at it, and below them each cell's events
# and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
BELOW_FULL = (6_075, 3_289, 10_781, 4_874, 4_884, 8_260, 5_483, 8_296, 4_104, 6_784)
AT_FULL = (2_863, 1_391, 6_388, 1_892, 1_756, 5_168, 2_471, 3_662, 1_920, 3_121)
EVENTS = {
    "binperp_funding_z30d": {
        "above": {"below_full": (98, 44, 97, 157, 102, 86, 97, 159, 58, 161)},
        "below": {"below_full": (130, 106, 151, 116, 80, 128, 145, 142, 85, 127)},
    },
    "binperp_oi_z30d": {
        "above": {"below_full": (272, 170, 292, 370, 279, 296, 261, 239, 219, 250)},
        "below": {"below_full": (24, 72, 134, 21, 73, 46, 68, 58, 123, 58)},
    },
    "binperp_ratio_max_z30d": {
        "above": {"below_full": (421, 472, 587, 512, 650, 369, 557, 491, 547, 430)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_long_z30d": {
        "above": {"below_full": (124, 150, 125, 181, 194, 128, 142, 162, 128, 149)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_oi_log_delta_z30d": {
        "above": {"below_full": (88, 92, 98, 111, 75, 77, 94, 74, 92, 75)},
        "below": {"below_full": (67, 63, 102, 74, 72, 70, 69, 57, 72, 54)},
    },
    "binperp_oi_momentum_z30d": {
        "above": {"below_full": (196, 161, 306, 313, 257, 163, 249, 243, 169, 177)},
        "below": {"below_full": (94, 93, 96, 51, 84, 99, 116, 86, 131, 95)},
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (185, 206, 253, 130, 206, 111, 164, 173, 154, 106)},
        "below": {"below_full": (62, 36, 72, 46, 51, 81, 102, 83, 144, 48)},
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (183, 220, 177, 289, 385, 170, 294, 241, 243, 217)},
        "below": {"below_full": (20, 30, 147, 24, 63, 90, 53, 59, 69, 23)},
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {"below_full": (193, 231, 303, 180, 165, 163, 196, 176, 210, 159)},
        "below": {"below_full": (159, 109, 67, 105, 144, 89, 161, 150, 131, 126)},
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {"below_full": (105, 128, 184, 132, 137, 129, 152, 170, 172, 127)},
        "below": {"below_full": (0, 3, 1, 1, 1, 1, 2, 0, 2, 0)},
    },
    "binperp_liq_short_z30d": {
        "above": {"below_full": (167, 156, 116, 124, 196, 137, 208, 201, 106, 106)},
        "below": {"below_full": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_total_z30d": {
        "above": {"below_full": (106, 85, 69, 131, 129, 80, 134, 121, 92, 107)},
        "below": {"below_full": (0, 0, 0, 0, 0, 6, 0, 0, 0, 0)},
    },
}
OTHERS = {
    "binperp_funding_z30d": {
        "above": {"below_full": (4_902, 3_245, 5_031, 4_717, 4_775, 4_973, 5_223, 5_433, 4_021, 4_789)},
        "below": {"below_full": (4_870, 3_183, 4_977, 4_758, 4_797, 4_931, 5_175, 5_450, 3_994, 4_823)},
    },
    "binperp_oi_z30d": {
        "above": {"below_full": (2_711, 2_930, 3_733, 3_181, 3_180, 2_861, 3_190, 3_120, 3_136, 2_712)},
        "below": {"below_full": (2_959, 3_028, 3_891, 3_530, 3_386, 3_111, 3_383, 3_301, 3_232, 2_904)},
    },
    "binperp_ratio_max_z30d": {
        "above": {"below_full": (1_630, 1_802, 2_604, 1_854, 1_825, 1_832, 1_976, 2_032, 1_896, 1_786)},
        "below": {"below_full": (2_051, 2_274, 3_191, 2_366, 2_475, 2_201, 2_533, 2_523, 2_443, 2_216)},
    },
    "binperp_liq_long_z30d": {
        "above": {"below_full": (2_591, 2_577, 2_776, 2_801, 3_017, 2_689, 2_977, 2_899, 2_836, 2_608)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_817, 3_119, 3_061, 2_964, 2_757)},
    },
    "binperp_oi_log_delta_z30d": {
        "above": {"below_full": (2_892, 3_006, 3_923, 3_438, 3_381, 3_078, 3_354, 3_282, 3_262, 2_886)},
        "below": {"below_full": (2_913, 3_035, 3_919, 3_475, 3_384, 3_085, 3_379, 3_299, 3_282, 2_907)},
    },
    "binperp_oi_momentum_z30d": {
        "above": {"below_full": (2_579, 2_802, 3_280, 2_836, 2_841, 2_735, 2_952, 2_825, 2_841, 2_589)},
        "below": {"below_full": (2_681, 2_870, 3_490, 3_098, 3_014, 2_799, 3_085, 2_982, 2_879, 2_671)},
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (2_041, 2_127, 2_981, 2_274, 2_426, 2_135, 2_405, 2_419, 2_363, 2_124)},
        "below": {"below_full": (2_164, 2_297, 3_162, 2_358, 2_581, 2_165, 2_467, 2_509, 2_373, 2_182)},
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {"below_full": (2_127, 2_223, 3_152, 2_289, 2_386, 2_301, 2_416, 2_486, 2_375, 2_184)},
        "below": {"below_full": (2_290, 2_413, 3_182, 2_554, 2_708, 2_381, 2_657, 2_668, 2_549, 2_378)},
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {"below_full": (2_804, 2_847, 3_768, 3_322, 3_231, 2_931, 3_196, 3_271, 3_183, 2_853)},
        "below": {"below_full": (2_838, 2_969, 4_004, 3_397, 3_252, 3_005, 3_231, 3_297, 3_262, 2_886)},
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {"below_full": (2_686, 2_756, 3_794, 3_115, 3_043, 2_981, 3_187, 3_198, 3_114, 2_826)},
        "below": {"below_full": (2_791, 2_881, 3_977, 3_246, 3_179, 3_109, 3_337, 3_368, 3_284, 2_953)},
    },
    "binperp_liq_short_z30d": {
        "above": {"below_full": (2_548, 2_571, 2_785, 2_858, 3_015, 2_680, 2_911, 2_860, 2_858, 2_651)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_817, 3_119, 3_061, 2_964, 2_757)},
    },
    "binperp_liq_total_z30d": {
        "above": {"below_full": (2_609, 2_642, 2_832, 2_851, 3_082, 2_737, 2_985, 2_940, 2_872, 2_650)},
        "below": {"below_full": (2_715, 2_727, 2_901, 2_982, 3_211, 2_811, 3_119, 3_061, 2_964, 2_757)},
    },
}


def per_asset(cells: dict) -> dict:
    """A cell table keyed by asset, as `_b2_rerisk_counts` returns it."""
    return {
        key: {
            tail: {state: dict(zip(subjects._ASSETS, counts)) for state, counts in by_state.items()}
            for tail, by_state in by_tail.items()
        }
        for key, by_tail in cells.items()
    }


def reading_inputs():
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_rerisk_inputs("b2-rerisk-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-funding or derivatives-oi set or the frozen daily liquidations block is absent "
    "under data/",
)
def test_the_rerisk_readings_inputs_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert reader.vouched_status() == VOUCHED
    assert len(inputs.close) == _RETURN_INDICES
    assert list(inputs.signals) == list(SIGNAL_FROM)
    for key, (index, first) in SIGNAL_FROM.items():
        signal = inputs.signals[key]
        assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == index, key
        assert inputs.close[index] == first, key
    pairs = {a: list(zip(inputs.arm_a[a], inputs.full_long[a], strict=True)) for a in subjects._ASSETS}
    assert tuple(sum(p > 0 for p, _ in pairs[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p, _ in pairs[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert tuple(sum(0 < p < f - _TOLERANCE for p, f in pairs[a]) for a in subjects._ASSETS) == BELOW_FULL
    assert tuple(sum(p > 0 and abs(f - p) <= _TOLERANCE for p, f in pairs[a]) for a in subjects._ASSETS) == AT_FULL
    assert not any(p > f + _TOLERANCE for a in subjects._ASSETS for p, f in pairs[a])
    assert subjects._b2_rerisk_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
