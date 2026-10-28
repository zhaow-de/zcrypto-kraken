from collections import Counter
from datetime import datetime
from pathlib import Path

import pytest

from cli.registry.observed import ObservedReader
from cli.research import command as research_command
from cli.research import subjects
from tests.skip_gates import nothing_found_under

pytestmark = pytest.mark.data

# Literal-rooted, the form the skip-gate guard admits; the case's first assertion makes it the run's own root.
_DATA_ROOT = Path(__file__).resolve().parents[1] / "data"
SUBJECT = "c2-lead-lag-reading"


def _epoch(iso: str) -> int:
    return int(datetime.fromisoformat(iso).timestamp())


# Copied from spec 00150's measured basis, never from a run.
LEADER_BASIS = {
    "bars": 430_560,
    "first_stamp": _epoch("2013-09-10T23:45:00+00:00"),
    "last_stamp": _epoch("2026-03-31T23:45:00+00:00"),
    "non_15m_steps": 3_002,
    "sigma_warm_index": 2_831,
}
FOLLOWER_BASIS = {
    "ADA/EUR": (254_419, "2018-09-28T13:15:00+00:00", 254_419, 0),
    "AVAX/EUR": (133_305, "2021-12-21T15:30:00+00:00", 133_305, 0),
    "DOGE/EUR": (199_897, "2019-12-19T14:45:00+00:00", 199_897, 0),
    "DOT/EUR": (191_755, "2020-08-18T17:00:00+00:00", 191_754, 1),
    "ETH/EUR": (361_327, "2015-08-07T11:00:00+00:00", 361_286, 41),
    "LINK/EUR": (210_214, "2019-09-25T13:45:00+00:00", 210_213, 1),
    "LTC/EUR": (356_774, "2013-09-14T08:15:00+00:00", 356_211, 563),
    "SOL/EUR": (166_537, "2021-06-17T15:30:00+00:00", 166_537, 0),
    "XRP/EUR": (309_480, "2017-05-18T15:45:00+00:00", 309_477, 3),
    "ETH/BTC": (347_656, "2016-03-03T07:00:00+00:00", 347_616, 40),
    "SOL/BTC": (160_120, "2021-06-17T15:30:00+00:00", 160_120, 0),
}
SIGNAL_BASIS = {
    "L1|th1|up": [8, 358, 2_139, 4_026, 4_405, 3_399, 3_597, 4_147, 4_123, 3_630, 3_783, 4_328, 4_288, 965],
    "L1|th1|down": [5, 369, 2_068, 3_888, 3_956, 3_601, 3_474, 3_781, 4_135, 3_716, 3_590, 4_126, 4_296, 1_010],
    "L1|th2|up": [1, 93, 394, 745, 887, 697, 787, 837, 853, 821, 908, 1_021, 1_002, 229],
    "L1|th2|down": [1, 98, 476, 805, 985, 894, 819, 869, 872, 937, 862, 1_046, 1_030, 269],
    "L4|th1|up": [3, 291, 1_614, 2_691, 4_571, 3_387, 3_647, 4_032, 4_120, 3_666, 3_693, 4_339, 4_219, 930],
    "L4|th1|down": [4, 315, 1_464, 2_541, 3_795, 3_758, 3_361, 3_549, 4_147, 3_956, 3_376, 4_043, 4_265, 1_009],
    "L4|th2|up": [1, 46, 267, 469, 887, 744, 913, 973, 863, 865, 1_055, 1_048, 961, 210],
    "L4|th2|down": [1, 74, 291, 490, 932, 1_052, 933, 871, 986, 1_109, 900, 1_075, 1_097, 266],
}


@pytest.mark.skipif(
    nothing_found_under(_DATA_ROOT, "ohlc-15m/*/*/15.parquet"), reason="the frozen ohlc-15m set is absent under data/"
)
def test_the_inputs_half_reads_the_specs_measured_basis():
    assert _DATA_ROOT == research_command._DATA_ROOT
    inputs = subjects._c2_reading_inputs(subjects._c2_reads(ObservedReader(_DATA_ROOT), "ohlc-15m", SUBJECT), SUBJECT)
    assert inputs.leader == LEADER_BASIS
    basis = {f: (bars, _epoch(first), on, off) for f, (bars, first, on, off) in FOLLOWER_BASIS.items()}
    assert {f: (v["bars"], v["first_stamp"], v["on_grid"], v["off_grid"]) for f, v in inputs.followers.items()} == basis
    # Never the computes half here: D7's hash rule.
    for key, per_year in SIGNAL_BASIS.items():
        signal, side = key.rsplit("|", 1)
        want = 1 if side == "up" else -1
        counts = Counter(y for s, y in zip(inputs.signals[signal], inputs.years, strict=True) if s == want)
        assert [counts[y] for y in range(2013, 2027)] == per_year, key
