import math
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import (
    B2Config,
    close_grid,
    derisk_scales,
    funding_grid_feature,
    net_of_cost,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    scale_positions,
)
from cli.alpha.errors import AlphaError

UTC = timezone.utc
DAY0 = datetime(2024, 3, 1, tzinfo=UTC)
# Under a window of 3 these score [None, None, 1.0, -1.0]: the last two prints' z are defined and differ.
RATES = [0.0001, 0.0002, 0.0003, 0.0001]


def _hours(*hours: int) -> list[datetime]:
    return [DAY0 + timedelta(hours=h) for h in hours]


def _feature(prints_ts, rates, union_ts, *, z_window=3, intervals=None):
    if intervals is None:
        intervals = [8] * len(rates)
    return funding_grid_feature(prints_ts, rates, intervals, union_ts, config=B2Config(z_window=z_window))


def test_a_print_30ms_past_its_hour_aligns_as_the_on_hour_print():
    union = _hours(8, 12, 16, 20, 24)
    on_hour = _feature(_hours(0, 8, 16, 24), RATES, union)
    late = _feature(_hours(0, 8, 16) + [DAY0 + timedelta(hours=24, milliseconds=30)], RATES, union)
    assert late[3] == pytest.approx(-1.0), "the 00:00 print's own z at the 00:00 close, not the 1.0 carried before it"
    assert late == on_hour == [None, pytest.approx(1.0), pytest.approx(1.0), pytest.approx(-1.0)]


def test_a_print_61s_past_its_hour_is_refused_by_name_and_one_60s_past_aligns_as_on_the_hour():
    union = _hours(8, 12, 16, 20, 24)
    on_hour = _feature(_hours(0, 8, 16, 24), RATES, union)
    with pytest.raises(AlphaError, match=re.escape("prints_ts[3] = 2024-03-02T00:01:01+00:00")):
        _feature(_hours(0, 8, 16) + [DAY0 + timedelta(hours=24, seconds=61)], RATES, union)
    assert _feature(_hours(0, 8, 16) + [DAY0 + timedelta(hours=24, seconds=60)], RATES, union) == on_hour


_PRINTS = _hours(0, 8, 16, 24)
_UNION = _hours(8, 12, 16, 20, 24)


@pytest.mark.parametrize(
    ("prints_ts", "union_ts", "named"),
    [
        pytest.param(_hours(0, 16, 8, 24), _UNION, "prints_ts", id="unsorted-prints"),
        pytest.param(_PRINTS, _hours(8, 16, 12, 20, 24), "union_ts", id="unsorted-union"),
        pytest.param(_PRINTS[:2] + [_PRINTS[2].replace(tzinfo=None)] + _PRINTS[3:], _UNION, "prints_ts", id="naive-print"),
        pytest.param(_PRINTS, _UNION[:2] + [_UNION[2].replace(tzinfo=None)] + _UNION[3:], "union_ts", id="naive-union"),
    ],
)
def test_unsorted_or_naive_stamps_are_refused(prints_ts, union_ts, named):
    with pytest.raises(AlphaError, match=named):
        _feature(prints_ts, RATES, union_ts)


def test_print_lists_of_unequal_length_are_refused():
    with pytest.raises(AlphaError, match="equal length"):
        _feature(_PRINTS, RATES, _UNION, intervals=[8, 8, 8])


def test_an_off_cadence_print_is_mapped_to_none_so_every_window_holding_it_is_none():
    rates = [0.0001, 0.0002, 0.0003, 0.0001, 0.0005, 0.0002, 0.0003, 0.0004, 0.0002]
    intervals = [8, 8, 8, 8, 4, 8, 8, 8, 8]
    feature = _feature(_hours(*range(0, 72, 8)), rates, _hours(*range(0, 72, 4)), intervals=intervals)
    # Return index j closes at 4(j + 1) h; the off-cadence print settles at 32 h, and the windows of
    # the prints at 32, 40 and 48 h hold it. Dropped instead of mapped, the 40 h print scores 0.0.
    assert feature == [None] * 3 + [pytest.approx(v) for v in (1.0, 1.0, -1.0, -1.0)] + [None] * 6 + [
        pytest.approx(v) for v in (1.0, 1.0, -1.0, -1.0)
    ]


def test_the_grid_is_the_close_stamp_neither_the_bar_open_nor_the_next_close():
    union = _hours(0, 4, 8)
    assert _feature(_hours(-16, -8, 0, 8), RATES, union) == [pytest.approx(1.0), pytest.approx(-1.0)]
    assert close_grid(union) == _hours(4, 8)


def test_a_truncated_prefix_of_the_inputs_reproduces_the_full_run_bit_for_bit():
    rates = [r * 1e-4 for r in (3, -1, 4, 0, 9, -2, 11, 5, -4, 7, 2, -6, 10, 1, -3)]
    prints_ts = [DAY0 + timedelta(hours=8 * i, milliseconds=7 * (i % 3)) for i in range(len(rates))]
    union_ts = _hours(*range(12, 116, 4))
    full = _feature(prints_ts, rates, union_ts)
    assert len(full) == len(union_ts) - 1 and None not in full
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(prints_ts) if t.replace(minute=0, second=0, microsecond=0) <= cutoff]
        prefix = _feature([prints_ts[i] for i in visible], [rates[i] for i in visible], union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


def test_a_planted_two_sigma_print_lifts_the_feature_from_its_hours_close_until_the_next_prints():
    rates = [0.0001] * 10 + [0.0009, 0.0001]
    feature = _feature(_hours(*range(0, 96, 8)), rates, _hours(68, 72, 76, 80, 84, 88), z_window=10)
    spike = pytest.approx(9 / math.sqrt(10))
    assert feature == [0.0, 0.0, spike, spike, pytest.approx(-1 / math.sqrt(10))]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("z_threshold", 0),
        ("z_threshold", -1.0),
        ("z_threshold", math.nan),
        ("z_threshold", math.inf),
        ("z_threshold", True),
        ("derisk_scale", 0),
        ("derisk_scale", 1.5),
        ("derisk_scale", math.nan),
        ("derisk_scale", True),
        ("z_window", 1),
        ("z_window", 2.5),
        ("z_window", True),
    ],
)
def test_b2config_refuses_an_out_of_range_or_bool_field(field, value):
    with pytest.raises(AlphaError, match=field):
        B2Config(**{field: value})


def test_b2config_accepts_a_full_scale():
    assert B2Config(derisk_scale=1.0).derisk_scale == 1.0


def test_b2config_defaults_are_the_pre_registered_constants():
    assert (B2Config().z_threshold, B2Config().derisk_scale, B2Config().z_window) == (2.0, 0.5, 90)


def test_a_planted_crossing_scales_exactly_its_stamps_and_neither_a_z_of_2_nor_one_below_minus_2():
    z = {"BTC": [0.5, 2.5, 3.1, 2.0, 1.9], "ETH": [2.0, -3.0, 2.0001, -2.5, 4.0]}
    assert derisk_scales(z, config=B2Config()) == {"BTC": [1.0, 0.5, 0.5, 1.0, 1.0], "ETH": [1.0, 1.0, 0.5, 1.0, 0.5]}


def test_a_none_z_leaves_the_scale_at_one():
    z = {"BTC": [None, 2.5, None], "ETH": [None, None, None]}
    assert derisk_scales(z, config=B2Config()) == {"BTC": [1.0, 0.5, 1.0], "ETH": [1.0, 1.0, 1.0]}


def test_derisk_scales_refuses_a_config_other_than_b2config():
    with pytest.raises(AlphaError, match="B2Config"):
        derisk_scales({"BTC": [2.5]}, config=None)


def test_funding_grid_feature_refuses_a_config_other_than_b2config():
    unvalidated = SimpleNamespace(z_threshold=2.0, derisk_scale=0.5, z_window=3)
    with pytest.raises(AlphaError, match="B2Config"):
        funding_grid_feature(_PRINTS, RATES, [8] * len(RATES), _UNION, config=unvalidated)


def test_scale_positions_pairs_each_assets_scales_by_key_not_by_order():
    positions = {"BTC": [0.4, 0.2, 0.1], "ETH": [0.3, 0.6, 0.5]}
    scales = {"ETH": [1.0, 0.5, 0.5], "BTC": [0.5, 1.0, 1.0]}
    assert scale_positions(positions, scales) == {"BTC": [0.2, 0.2, 0.1], "ETH": [0.3, 0.3, 0.25]}


def test_net_of_cost_charges_the_de_risk_and_the_re_risk_and_reads_a_none_return_as_zero():
    returns = {"ETH": [0.01, None, -0.02, 0.03], "BTC": [0.02, -0.01, 0.04, None]}
    arm_a = {"BTC": [0.5, 0.5, 0.5, 0.5], "ETH": [0.2, 0.2, 0.2, 0.2]}
    arm_b = {"BTC": [0.5, 0.5, 0.25, 0.5], "ETH": [0.2, 0.2, 0.2, 0.2]}
    net_a = net_of_cost(arm_a, returns, cost_per_side=0.006)
    net_b = net_of_cost(arm_b, returns, cost_per_side=0.006)
    # Index 0 opens both legs from flat: 0.5 * 0.02 + 0.2 * 0.01 - 0.006 * (0.5 + 0.2).
    assert net_a == pytest.approx([0.0078, -0.005, 0.016, 0.006])
    assert net_b == pytest.approx([0.0078, -0.005, 0.0045, 0.0045])
    assert sum(net_a) - sum(net_b) == pytest.approx(0.5 * 0.5 * 0.04 + 0.006 * 0.5)


# Return indices 0-2 close in 2020 and 3-5 in 2021; index 3 opens 2020-12-31T20:00Z.
_CLOSE = close_grid([datetime(2020, 12, 31, 8, tzinfo=UTC) + timedelta(hours=4 * i) for i in range(7)])
_ARM_A = {"BTC": [0.4, 0.4, 0.0, 0.0, 0.3, 0.3], "ETH": [0.2, 0.2, 0.2, 0.5, 0.5, 0.0]}
# BTC at indices 2 and 3 and ETH at index 5 are flat under a 0.5 scale: not engaged stamps.
_SCALES = {"ETH": [1.0, 1.0, 1.0, 0.5, 0.5, 0.5], "BTC": [1.0, 1.0, 0.5, 0.5, 0.5, 1.0]}
_ARM_B = {"ETH": [0.2, 0.2, 0.2, 0.25, 0.25, 0.0], "BTC": [0.4, 0.4, 0.0, 0.0, 0.15, 0.3]}


def test_per_year_engaged_counts_counts_long_de_risked_asset_stamps_and_never_a_flat_one():
    assert per_year_engaged_counts(_ARM_A, _SCALES, _CLOSE) == {"2020": 0, "2021": 3}


def test_per_year_positions_differ_counts_a_return_index_once_however_many_assets_differ():
    assert per_year_positions_differ(_ARM_A, _ARM_B, _CLOSE) == {"2020": 0, "2021": 2}


def test_per_year_turnover_charges_each_change_from_flat_in_its_index_year():
    assert per_year_turnover(_ARM_A, _CLOSE) == {"2020": pytest.approx(1.0), "2021": pytest.approx(1.1)}
    assert per_year_turnover(_ARM_B, _CLOSE) == {"2020": pytest.approx(1.0), "2021": pytest.approx(0.6)}
    assert sum(per_year_turnover(_ARM_A, _CLOSE).values()) == pytest.approx(book_turnover(_ARM_A))


def test_per_year_max_drawdown_reads_each_year_from_its_own_peak():
    returns = [0.10, -0.20, 0.05, -0.10, 0.10, -0.05]
    assert per_year_max_drawdown(returns, _CLOSE) == {"2020": pytest.approx(0.2), "2021": pytest.approx(0.1)}


_POS = {"BTC": [0.4, 0.2], "ETH": [0.3, 0.6]}


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(
            lambda: derisk_scales({"BTC": [1.0, 2.5], "ETH": [1.0]}, config=B2Config()),
            r"z_by_asset\['ETH'\] has length 1, expected 2",
            id="derisk-scales-unequal-lengths",
        ),
        pytest.param(
            lambda: scale_positions(_POS, {"BTC": [1.0, 1.0], "SOL": [1.0, 1.0]}), "same assets", id="scale-positions-key-sets"
        ),
        pytest.param(
            lambda: scale_positions(_POS, {"BTC": [1.0, 1.0], "ETH": [1.0]}),
            r"scales\['ETH'\] has length 1, expected 2",
            id="scale-positions-unequal-lengths",
        ),
        pytest.param(
            lambda: net_of_cost(_POS, {"BTC": [0.01, 0.02], "SOL": [0.01, 0.02]}, cost_per_side=0.006),
            "same assets",
            id="net-of-cost-key-sets",
        ),
        pytest.param(
            lambda: net_of_cost(_POS, {"BTC": [0.01, 0.02], "ETH": [0.01]}, cost_per_side=0.006),
            r"asset_returns\['ETH'\] has length 1, expected 2",
            id="net-of-cost-unequal-lengths",
        ),
        pytest.param(
            lambda: per_year_engaged_counts(_ARM_A, {"BTC": [1.0] * 6, "SOL": [1.0] * 6}, _CLOSE),
            "same assets",
            id="engaged-counts-key-sets",
        ),
        pytest.param(
            lambda: per_year_engaged_counts(_ARM_A, _SCALES, _CLOSE[:5]), "has length 6, expected 5", id="engaged-counts-close-ts"
        ),
        pytest.param(
            lambda: per_year_positions_differ(_ARM_A, {"BTC": [0.0] * 6, "SOL": [0.0] * 6}, _CLOSE),
            "same assets",
            id="positions-differ-key-sets",
        ),
        pytest.param(
            lambda: per_year_positions_differ(_ARM_A, _ARM_B, _CLOSE[:5]),
            "has length 6, expected 5",
            id="positions-differ-close-ts",
        ),
        pytest.param(lambda: per_year_turnover(_ARM_A, _CLOSE[:5]), "has length 6, expected 5", id="turnover-close-ts"),
        pytest.param(lambda: per_year_max_drawdown([0.0] * 6, _CLOSE[:5]), "has length 6, expected 5", id="max-drawdown-close-ts"),
    ],
)
def test_a_mismatched_input_is_refused(call, match):
    with pytest.raises(AlphaError, match=match):
        call()
