"""B2's second signal reading's inputs against spec 00141's measured basis; no forward return."""

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
BLOCK = "bfbaff14b7aaa0d673fb0ab2012fc0d5c2d2118d258ad720e9ef6120c6ca8f6a"
VOUCHED = {
    "ohlc-full": "checked (36 vouched hashes)",
    "derivatives-oi": "checked (10 vouched hashes)",
    "liquidations-daily": "checked (10 vouched hashes)",
}
_RETURN_INDICES = 27_337
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_oi_log_delta_z30d": (18_027, datetime(2021, 12, 31, tzinfo=UTC)),
    "binperp_oi_momentum_z30d": (18_206, datetime(2022, 1, 29, 20, tzinfo=UTC)),
    "binperp_count_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_sum_toptrader_long_short_ratio_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_count_long_short_ratio_z30d": (18_324, datetime(2022, 2, 18, 12, tzinfo=UTC)),
    "binperp_sum_taker_long_short_vol_ratio_z30d": (18_994, datetime(2022, 6, 10, 4, tzinfo=UTC)),
    "binperp_liq_short_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
    "binperp_liq_total_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, and below them each cell's events and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
EVENTS = {
    "binperp_oi_log_delta_z30d": {
        "above": {
            "long": (135, 149, 168, 170, 105, 129, 170, 147, 138, 125),
            "flat": (118, 116, 104, 90, 131, 97, 91, 83, 112, 78),
        },
        "below": {
            "long": (97, 101, 182, 95, 100, 107, 103, 82, 108, 95),
            "flat": (104, 82, 116, 83, 86, 112, 90, 85, 84, 99),
        },
    },
    "binperp_oi_momentum_z30d": {
        "above": {
            "long": (369, 316, 496, 620, 307, 280, 515, 441, 274, 456),
            "flat": (324, 347, 242, 347, 457, 307, 256, 197, 386, 284),
        },
        "below": {
            "long": (143, 97, 243, 63, 197, 152, 123, 94, 172, 135),
            "flat": (254, 243, 259, 238, 173, 310, 199, 209, 149, 271),
        },
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (289, 316, 398, 217, 286, 113, 271, 236, 194, 127),
            "flat": (73, 77, 297, 80, 60, 204, 52, 170, 94, 139),
        },
        "below": {
            "long": (96, 77, 127, 105, 66, 124, 130, 131, 249, 153),
            "flat": (93, 83, 30, 93, 81, 20, 132, 29, 62, 96),
        },
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (504, 503, 457, 525, 569, 362, 594, 516, 507, 517),
            "flat": (82, 99, 98, 63, 57, 147, 78, 120, 28, 87),
        },
        "below": {
            "long": (32, 30, 195, 27, 92, 107, 56, 63, 85, 23),
            "flat": (241, 149, 172, 206, 155, 213, 252, 221, 207, 191),
        },
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {
            "long": (272, 340, 420, 247, 240, 168, 252, 218, 244, 171),
            "flat": (127, 128, 359, 84, 177, 228, 119, 198, 135, 221),
        },
        "below": {
            "long": (206, 184, 101, 215, 166, 132, 232, 225, 203, 278),
            "flat": (134, 144, 23, 86, 125, 29, 192, 33, 120, 92),
        },
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {
            "long": (129, 152, 278, 158, 149, 177, 175, 201, 223, 155),
            "flat": (233, 167, 180, 175, 214, 170, 196, 152, 138, 194),
        },
        "below": {
            "long": (0, 6, 1, 2, 1, 1, 4, 0, 4, 1),
            "flat": (2, 3, 4, 0, 1, 3, 1, 0, 5, 2),
        },
    },
    "binperp_liq_short_z30d": {
        "above": {
            "long": (321, 341, 318, 348, 320, 275, 381, 366, 312, 281),
            "flat": (134, 139, 120, 138, 142, 187, 111, 102, 132, 109),
        },
        "below": {
            "long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
            "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        },
    },
    "binperp_liq_total_z30d": {
        "above": {
            "long": (249, 259, 238, 383, 250, 220, 267, 267, 305, 285),
            "flat": (128, 154, 145, 162, 229, 194, 122, 152, 180, 141),
        },
        "below": {
            "long": (0, 0, 0, 0, 0, 6, 0, 0, 0, 0),
            "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        },
    },
}
OTHERS = {
    "binperp_oi_log_delta_z30d": {
        "above": {
            "long": (3_814, 4_063, 6_306, 4_376, 4_080, 4_359, 4_447, 4_431, 4_489, 3_943),
            "flat": (4_512, 4_437, 4_541, 4_129, 4_449, 3_999, 4_057, 3_904, 3_839, 4_438),
        },
        "below": {
            "long": (3_852, 4_111, 6_292, 4_451, 4_085, 4_381, 4_514, 4_496, 4_519, 3_973),
            "flat": (4_526, 4_471, 4_529, 4_136, 4_494, 3_984, 4_058, 3_902, 3_867, 4_417),
        },
    },
    "binperp_oi_momentum_z30d": {
        "above": {
            "long": (3_314, 3_691, 5_266, 3_482, 3_488, 3_841, 3_815, 3_790, 3_911, 3_390),
            "flat": (3_678, 3_696, 4_042, 3_601, 3_798, 3_262, 3_464, 3_243, 3_113, 3_560),
        },
        "below": {
            "long": (3_540, 3_910, 5_519, 4_039, 3_598, 3_969, 4_207, 4_137, 4_013, 3_711),
            "flat": (3_748, 3_800, 4_025, 3_710, 4_082, 3_259, 3_521, 3_231, 3_350, 3_573),
        },
    },
    "binperp_count_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (2_796, 2_937, 5_104, 3_020, 2_943, 3_138, 3_162, 3_214, 3_470, 3_076),
            "flat": (3_161, 2_989, 3_075, 3_002, 3_030, 2_684, 2_834, 2_699, 2_561, 2_977),
        },
        "below": {
            "long": (2_989, 3_176, 5_375, 3_132, 3_163, 3_127, 3_303, 3_319, 3_415, 3_050),
            "flat": (3_141, 2_983, 3_342, 2_989, 3_009, 2_868, 2_754, 2_840, 2_593, 3_020),
        },
    },
    "binperp_sum_toptrader_long_short_ratio_z30d": {
        "above": {
            "long": (2_705, 2_884, 5_228, 2_925, 2_814, 3_254, 3_070, 3_162, 3_298, 2_823),
            "flat": (3_208, 3_013, 3_271, 2_986, 3_059, 2_736, 2_757, 2_701, 2_666, 3_072),
        },
        "below": {
            "long": (3_177, 3_357, 5_490, 3_423, 3_291, 3_509, 3_608, 3_615, 3_720, 3_317),
            "flat": (3_049, 2_963, 3_197, 2_843, 2_961, 2_670, 2_583, 2_600, 2_487, 2_968),
        },
    },
    "binperp_count_long_short_ratio_z30d": {
        "above": {
            "long": (3_741, 3_906, 6_257, 4_294, 3_959, 4_288, 4_310, 4_473, 4_552, 4_122),
            "flat": (4_513, 4_279, 4_172, 4_028, 4_277, 3_789, 3_972, 3_764, 3_722, 4_139),
        },
        "below": {
            "long": (3_807, 4_062, 6_576, 4_326, 4_033, 4_324, 4_330, 4_466, 4_593, 4_015),
            "flat": (4_506, 4_263, 4_508, 4_026, 4_329, 3_988, 3_899, 3_929, 3_737, 4_268),
        },
    },
    "binperp_sum_taker_long_short_vol_ratio_z30d": {
        "above": {
            "long": (3_641, 3_974, 6_249, 4_142, 3_769, 4_354, 4_343, 4_421, 4_495, 3_984),
            "flat": (3_980, 3_690, 4_011, 3_508, 3_671, 3_462, 3_449, 3_389, 3_307, 3_830),
        },
        "below": {
            "long": (3_770, 4_120, 6_526, 4_298, 3_917, 4_530, 4_514, 4_622, 4_714, 4_138),
            "flat": (4_211, 3_854, 4_187, 3_683, 3_884, 3_629, 3_644, 3_541, 3_440, 4_022),
        },
    },
    "binperp_liq_short_z30d": {
        "above": {
            "long": (3_465, 3_543, 4_270, 3_828, 3_692, 3_984, 3_811, 3_835, 4_079, 3_562),
            "flat": (3_692, 3_415, 2_898, 3_298, 3_554, 3_160, 3_309, 3_141, 3_095, 3_654),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_259, 4_192, 4_201, 4_391, 3_843),
            "flat": (3_826, 3_554, 3_018, 3_436, 3_696, 3_347, 3_420, 3_243, 3_227, 3_763),
        },
    },
    "binperp_liq_total_z30d": {
        "above": {
            "long": (3_537, 3_625, 4_350, 3_793, 3_762, 4_039, 3_925, 3_934, 4_086, 3_558),
            "flat": (3_698, 3_400, 2_873, 3_274, 3_467, 3_153, 3_298, 3_091, 3_047, 3_622),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_253, 4_192, 4_201, 4_391, 3_843),
            "flat": (3_826, 3_554, 3_018, 3_436, 3_696, 3_347, 3_420, 3_243, 3_227, 3_763),
        },
    },
}


def per_asset(cells: dict) -> dict:
    """A cell table keyed by asset, as `_b2_reading_counts` returns it."""
    return {
        key: {
            tail: {state: dict(zip(subjects._ASSETS, counts)) for state, counts in by_state.items()}
            for tail, by_state in by_tail.items()
        }
        for key, by_tail in cells.items()
    }


def reading_inputs():
    reader = ObservedReader(_DATA_ROOT)
    return reader, subjects._b2_reading_2_inputs("b2-second-signal-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-oi set or the frozen daily liquidations block is absent under data/",
)
def test_the_second_signal_readings_inputs_reproduce_the_measured_basis():
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
    assert tuple(sum(p > 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert subjects._b2_reading_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
