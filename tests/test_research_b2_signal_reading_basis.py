"""B2's signal reading's inputs against spec 00140's measured basis; no forward return."""

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
# Per signal, the first return index every asset's signal holds, and its close.
SIGNAL_FROM = {
    "binperp_funding_z30d": (15_419, datetime(2020, 10, 22, 8, tzinfo=UTC)),
    "binperp_oi_z30d": (18_026, datetime(2021, 12, 30, 20, tzinfo=UTC)),
    "binperp_ratio_max_z30d": (20_298, datetime(2023, 1, 13, 12, tzinfo=UTC)),
    "binperp_liq_long_z30d": (19_731, datetime(2022, 10, 11, tzinfo=UTC)),
}
# Arm A's long and flat asset-stamps, and below them each cell's events and others, per asset in `subjects._ASSETS`' order.
ARM_A_LONG = (8_938, 4_680, 17_169, 6_766, 6_640, 13_428, 7_954, 11_958, 6_024, 9_905)
ARM_A_FLAT = (18_399, 22_657, 10_168, 20_571, 20_697, 13_909, 19_383, 15_379, 21_313, 17_432)
EVENTS = {
    "binperp_funding_z30d": {
        "above": {"long": (372, 164, 402, 326, 347, 454, 336, 458, 210, 417), "flat": (56, 192, 14, 48, 5, 10, 42, 68, 62, 47)},
        "below": {
            "long": (159, 115, 191, 147, 85, 141, 184, 151, 101, 141),
            "flat": (397, 347, 279, 321, 335, 305, 386, 311, 396, 357),
        },
    },
    "binperp_oi_z30d": {
        "above": {
            "long": (455, 410, 586, 771, 351, 540, 604, 515, 380, 644),
            "flat": (362, 406, 283, 103, 616, 271, 179, 212, 426, 178),
        },
        "below": {"long": (64, 88, 219, 21, 147, 64, 68, 78, 129, 58), "flat": (310, 224, 319, 359, 129, 318, 328, 332, 156, 267)},
    },
    "binperp_ratio_max_z30d": {
        "above": {
            "long": (782, 827, 1_020, 816, 865, 550, 893, 817, 875, 748),
            "flat": (327, 290, 518, 301, 303, 439, 283, 409, 252, 400),
        },
        "below": {"long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
    "binperp_liq_long_z30d": {
        "above": {
            "long": (226, 301, 236, 359, 298, 239, 254, 282, 270, 278),
            "flat": (157, 172, 171, 156, 241, 169, 165, 197, 179, 154),
        },
        "below": {"long": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0), "flat": (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)},
    },
}
OTHERS = {
    "binperp_funding_z30d": {
        "above": {
            "long": (6_936, 4_516, 7_887, 6_401, 6_286, 7_723, 7_432, 7_449, 5_789, 6_777),
            "flat": (6_036, 7_046, 5_209, 5_589, 5_480, 5_325, 5_604, 5_487, 5_680, 6_239),
        },
        "below": {
            "long": (7_149, 4_565, 8_098, 6_580, 6_548, 8_036, 7_584, 7_756, 5_898, 7_053),
            "flat": (5_695, 6_891, 4_944, 5_316, 5_150, 5_030, 5_260, 5_244, 5_346, 5_929),
        },
    },
    "binperp_oi_z30d": {
        "above": {
            "long": (3_498, 3_805, 5_892, 3_778, 3_838, 3_951, 4_016, 4_066, 4_250, 3_425),
            "flat": (4_269, 4_148, 4_364, 4_117, 3_964, 3_827, 3_970, 3_777, 3_527, 4_342),
        },
        "below": {
            "long": (3_889, 4_127, 6_259, 4_528, 4_042, 4_427, 4_552, 4_503, 4_501, 4_011),
            "flat": (4_321, 4_330, 4_328, 3_861, 4_451, 3_780, 3_821, 3_657, 3_797, 4_253),
        },
    },
    "binperp_ratio_max_z30d": {
        "above": {
            "long": (2_040, 2_367, 4_439, 2_383, 2_118, 2_656, 2_504, 2_564, 2_705, 2_395),
            "flat": (2_810, 2_655, 2_717, 2_639, 2_673, 2_314, 2_459, 2_349, 2_307, 2_596),
        },
        "below": {
            "long": (2_822, 3_194, 5_459, 3_199, 2_983, 3_206, 3_397, 3_381, 3_580, 3_143),
            "flat": (3_137, 2_945, 3_235, 2_940, 2_976, 2_753, 2_742, 2_758, 2_559, 2_996),
        },
    },
    "binperp_liq_long_z30d": {
        "above": {
            "long": (3_560, 3_583, 4_352, 3_817, 3_714, 4_020, 3_938, 3_919, 4_121, 3_565),
            "flat": (3_669, 3_382, 2_847, 3_280, 3_455, 3_178, 3_255, 3_046, 3_048, 3_609),
        },
        "below": {
            "long": (3_786, 3_884, 4_588, 4_176, 4_012, 4_259, 4_192, 4_201, 4_391, 3_843),
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
    return reader, subjects._b2_reading_inputs("b2-signal-reading", reader, "ohlc-full", None, False)


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-full/*/EUR/240.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-funding/*/funding.parquet")
    or nothing_found_under(_DATA_ROOT, "derivatives-oi/*/oi.parquet")
    or nothing_found_under(_DATA_ROOT, "liquidations-daily/*/daily.parquet"),
    reason="the frozen ohlc-full set, the derivatives-funding or derivatives-oi set or the frozen daily liquidations block is absent "
    "under data/",
)
def test_the_signal_readings_inputs_reproduce_the_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    reader, inputs = reading_inputs()
    assert compute_hash(reader.block()) == BLOCK
    assert reader.vouched_status() == VOUCHED
    assert len(inputs.close) == _RETURN_INDICES
    for key, (index, first) in SIGNAL_FROM.items():
        signal = inputs.signals[key]
        assert next(k for k in range(_RETURN_INDICES) if all(signal[a][k] is not None for a in subjects._ASSETS)) == index, key
        assert inputs.close[index] == first, key
    assert tuple(sum(p > 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_LONG
    assert tuple(sum(p == 0 for p in inputs.arm_a[a]) for a in subjects._ASSETS) == ARM_A_FLAT
    assert subjects._b2_reading_counts(inputs) == {"events_per_asset": per_asset(EVENTS), "others_per_asset": per_asset(OTHERS)}
