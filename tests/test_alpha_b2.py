import math
import re
import weakref
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cli.alpha import b2
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import (
    B2Config,
    close_grid,
    daily_zscore_grid_feature,
    derisk_scales,
    event_contrast,
    event_contrast_blocks,
    event_contrast_chunked,
    full_long_sizes,
    funding_carry_grid_feature,
    funding_grid_feature,
    funding_sign_grid_feature,
    liquidation_grid_features,
    liquidation_hourly_totals,
    net_of_cost,
    oi_grid_levels,
    oi_log_delta_grid_feature,
    oi_log_delta_zscore_grid_feature,
    oi_momentum_grid_feature,
    oi_momentum_zscore_grid_feature,
    oi_zscore_grid_feature,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    ratio_grid_features,
    ratio_max_signal,
    ratio_zscore_grid_features,
    reentry_counts_per_year,
    reentry_positions,
    scale_positions,
    stationary_bootstrap_blocks,
)
from cli.alpha.errors import AlphaError
from cli.features.errors import FeatureError
from cli.validation import ValidationError, stationary_bootstrap_indices
from cli.validation.bootstrap import _percentile

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


def test_full_long_sizes_is_the_shared_weight_times_the_mean_of_the_arms_levels():
    # The arms' levels average to 0.6, 0.4 (its median 0.3) and 0.6; ETH carries no weight at index 1, and no asset at index 2.
    weights = [{"BTC": 0.6, "ETH": 0.4}, {"BTC": 1.0}, {}]
    levels = [[0.9, 0.3, 0.6], [0.6, 0.9, 0.6], [0.3, 0.0, 0.6]]
    sizes = full_long_sizes(weights, levels, ("BTC", "ETH"))
    assert sizes == {"BTC": pytest.approx([0.36, 0.4, 0.0]), "ETH": pytest.approx([0.24, 0.0, 0.0])}


_REENTRY_ARM_A = {"BTC": [0.4, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0, 0.3], "ETH": [0.2, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0]}
_REENTRY_FULL = {"BTC": [0.5, 0.5, 0.45, 0.55, 0.5, 0.6, 0.4, 0.5], "ETH": [0.6, 0.6, 0.0, 0.6, 0.6, 0.6, 0.0, 0.6]}
_REENTRY_FIRES = {
    "BTC": [False, True, True, True, False, False, False, True],
    "ETH": [False, True, False, True, False, False, True, False],
}


@pytest.mark.parametrize(
    ("hold", "expected"),
    [
        pytest.param(
            1,
            {"BTC": [0.4, 0.4, 0.45, 0.55, 0.0, 0.0, 0.0, 0.3], "ETH": [0.2, 0.6, 0.0, 0.5, 0.0, 0.0, 0.0, 0.0]},
            id="hold-1-open-only-where-it-fires",
        ),
        pytest.param(
            3,
            {"BTC": [0.4, 0.4, 0.45, 0.55, 0.5, 0.6, 0.0, 0.3], "ETH": [0.2, 0.6, 0.0, 0.5, 0.0, 0.0, 0.0, 0.6]},
            id="hold-3-open-three-closes-from-the-last-firing",
        ),
    ],
)
def test_reentry_positions_take_the_full_long_size_where_arm_a_is_flat_through_the_hold(hold, expected):
    # A firing while long opens nothing, a re-entry takes the size of its own close, a zero full-long size takes nothing and
    # still counts toward the hold, a second firing restarts the hold, and arm A turning long closes a re-entry.
    assert reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=hold) == expected


def test_reentry_counts_per_year_counts_flat_asset_stamps_arm_b_holds_and_never_a_long_one():
    reentered = {"BTC": [0.4, 0.4, 0.5, 0.0, 0.3, 0.3], "ETH": [0.2, 0.2, 0.2, 0.5, 0.5, 0.6]}
    assert reentry_counts_per_year(_ARM_A, reentered, _CLOSE) == {"2020": 1, "2021": 1}


@pytest.mark.parametrize(
    ("call", "match"),
    [
        pytest.param(lambda: full_long_sizes([{}], [], ("BTC",)), "at least one arm", id="no-levels"),
        pytest.param(
            lambda: full_long_sizes([{}, {}], [[0.5]], ("BTC",)), r"levels\[0\] has length 1, expected 2", id="levels-length"
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=0),
            "hold must be an int >= 1",
            id="hold-0",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, _REENTRY_FIRES, hold=True),
            "hold must be an int >= 1",
            id="hold-bool",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL, {"BTC": _REENTRY_FIRES["BTC"]}, hold=1),
            "same assets",
            id="fires-assets",
        ),
        pytest.param(
            lambda: reentry_positions(_REENTRY_ARM_A, _REENTRY_FULL | {"ETH": [0.6] * 7}, _REENTRY_FIRES, hold=1),
            r"full_long\['ETH'\] has length 7, expected 8",
            id="full-long-length",
        ),
        pytest.param(lambda: reentry_counts_per_year(_ARM_A, _ARM_B, _CLOSE[:5]), "expected 5", id="counts-close-length"),
    ],
)
def test_the_reentry_functions_refuse_inputs_they_cannot_pair(call, match):
    with pytest.raises(AlphaError, match=match):
        call()


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


# The sign runs these prints score are 1, 2, 1, 1, 2, 1, 2; 13 return indices close every 4 h from 04:00.
_SIGN_PRINTS = _hours(0, 8, 16, 24, 32, 40, 48)
_SIGN_RATES = [1e-4, 2e-4, 0.0, -1e-4, -3e-4, 2e-4, 1e-4]
_SIGN_UNION = _hours(*range(0, 56, 4))
# The carry over the 90 prints ending at the 90th, 91st and 92nd print is 4095e-6, 4185e-6 and 4275e-6.
_CARRY_PRINTS = _hours(*range(0, 8 * 92, 8))
_CARRY_RATES = [(i + 1) * 1e-6 for i in range(92)]
_CARRY_UNION = _hours(*range(704, 736, 4))


def test_the_sign_run_counts_prints_never_bars_as_of_each_close():
    # Fed the aligned grid instead, each print would count once per bar it carries across: 1, 2, 3, 1, 2, 1, 2, 3, 4, ...
    assert funding_sign_grid_feature(_SIGN_PRINTS, _SIGN_RATES, [8] * 7, _SIGN_UNION) == [1, 2, 2, 1, 1, 1, 1, 2, 2, 1, 1, 2, 2]


def test_an_off_cadence_print_breaks_the_sign_run_and_is_none_while_it_is_the_latest_print():
    intervals = [8, 8, 8, 4, 8, 8, 8]
    rates = _SIGN_RATES[:4] + [0.0] + _SIGN_RATES[5:]
    # Dropped instead of mapped, the 32 h and 36 h closes would continue the 16 h print's zero run, 2.
    expected = [1, 2, 2, 1, 1, None, None, 1, 1, 1, 1, 2, 2]
    assert funding_sign_grid_feature(_SIGN_PRINTS, rates, intervals, _SIGN_UNION) == expected


def test_the_accrued_carry_sums_the_latest_90_prints_as_of_each_close():
    feature = funding_carry_grid_feature(_CARRY_PRINTS, _CARRY_RATES, [8] * 92, _CARRY_UNION)
    # The 704 h print is the 89th, its window one print short.
    assert feature == [None] + [pytest.approx(v * 1e-6) for v in (4095, 4095, 4185, 4185, 4275, 4275)]


def test_an_off_cadence_print_leaves_every_carry_window_holding_it_none():
    intervals = [8, 4] + [8] * 90
    # Dropped instead of mapped, the 720 h print would sum the 90 prints left before it, 4184e-6.
    expected = [None] * 5 + [pytest.approx(4275e-6)] * 2
    assert funding_carry_grid_feature(_CARRY_PRINTS, _CARRY_RATES, intervals, _CARRY_UNION) == expected


def test_the_carry_window_is_the_pre_registered_90_prints():
    assert b2._CARRY_WINDOW == 90


# Each emitter's fixture, the print a test moves, and the return index its own hour closes, where its value differs from
# the one carried before it.
_NEW_FUNDING_EMITTERS = [
    pytest.param(funding_sign_grid_feature, _SIGN_PRINTS, _SIGN_RATES, _SIGN_UNION, 4, 7, id="sign"),
    pytest.param(funding_carry_grid_feature, _CARRY_PRINTS, _CARRY_RATES, _CARRY_UNION, 90, 3, id="carry"),
]


@pytest.mark.parametrize(("emitter", "prints", "rates", "union", "moved", "at"), _NEW_FUNDING_EMITTERS)
def test_every_new_funding_emitter_reads_a_print_30ms_past_its_hour_as_that_hours_settlement(
    emitter, prints, rates, union, moved, at
):
    late = [t + timedelta(milliseconds=30) if i == moved else t for i, t in enumerate(prints)]
    on_hour = emitter(prints, rates, [8] * len(rates), union)
    assert on_hour[at] != on_hour[at - 1]
    assert emitter(late, rates, [8] * len(rates), union) == on_hour


@pytest.mark.parametrize(("emitter", "prints", "rates", "union", "moved", "at"), _NEW_FUNDING_EMITTERS)
def test_every_new_funding_emitter_refuses_a_print_61s_past_its_hour_by_name(emitter, prints, rates, union, moved, at):
    late = [t + timedelta(seconds=61) if i == moved else t for i, t in enumerate(prints)]
    with pytest.raises(AlphaError, match=re.escape(f"prints_ts[{moved}] = {late[moved].isoformat()}")):
        emitter(late, rates, [8] * len(rates), union)


@pytest.mark.parametrize("emitter", [funding_sign_grid_feature, funding_carry_grid_feature], ids=["sign", "carry"])
def test_a_truncated_prefix_of_the_print_inputs_reproduces_every_new_funding_emitter_bit_for_bit(emitter):
    rates = [((7 * i) % 11 - 5) * 1e-5 for i in range(120)]
    prints_ts = [DAY0 + timedelta(hours=8 * i, milliseconds=7 * (i % 3)) for i in range(len(rates))]
    union_ts = _hours(*range(764, 900, 4))
    full = emitter(prints_ts, rates, [8] * len(rates), union_ts)
    assert len(full) == len(union_ts) - 1 and None not in full
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(prints_ts) if t.replace(minute=0, second=0, microsecond=0) <= cutoff]
        prefix = emitter([prints_ts[i] for i in visible], [rates[i] for i in visible], [8] * len(visible), union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


_FUNDING_EMITTERS = [
    pytest.param(lambda *inputs: funding_grid_feature(*inputs, config=B2Config()), id="zscore"),
    pytest.param(funding_sign_grid_feature, id="sign"),
    pytest.param(funding_carry_grid_feature, id="carry"),
]


@pytest.mark.parametrize("emitter", _FUNDING_EMITTERS)
def test_every_funding_emitter_reads_none_from_the_close_a_settlement_past_its_last_print(emitter):
    # The last print settles at 728 h: the 732 h close still reads it, and from 736 h the next settlement is due and absent.
    feature = emitter(_CARRY_PRINTS, _CARRY_RATES, [8] * 92, _hours(*range(720, 748, 4)))
    assert None not in feature[:3] and feature[2] == feature[1] and feature[3:] == [None] * 3


@pytest.mark.parametrize("emitter", _FUNDING_EMITTERS)
@pytest.mark.parametrize(
    ("prints_ts", "intervals", "union_ts", "named"),
    [
        pytest.param(_PRINTS, [8] * 5, _UNION, "equal length", id="longer-intervals"),
        pytest.param(_hours(0, 8, 8, 24), [8] * 4, _UNION, "prints_ts", id="duplicate-prints"),
        pytest.param(_PRINTS, [8] * 4, _hours(8, 12, 12, 16, 20), "union_ts", id="duplicate-union"),
    ],
)
def test_every_funding_emitter_refuses_a_shape_it_would_otherwise_read_silently(emitter, prints_ts, intervals, union_ts, named):
    with pytest.raises(AlphaError, match=named):
        emitter(prints_ts, RATES, intervals, union_ts)


def test_a_level_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read():
    union = _hours(0, 4, 8, 12)
    assert oi_grid_levels(_hours(4, 12), [100.0, 110.0], union) == [100.0, None, 110.0]
    younger = [DAY0 + timedelta(hours=4, seconds=1), DAY0 + timedelta(hours=12)]
    # The rows' span opens at the 08:00 mark, the first at or after the younger row: the 04:00 close lies before it.
    assert oi_grid_levels(younger, [100.0, 110.0], union) == [None, 100.0, 110.0]


def test_a_late_stamped_row_is_read_from_its_own_stamp_never_from_its_mark():
    oi_ts = [DAY0 + timedelta(hours=4, seconds=-22), DAY0 + timedelta(hours=4, seconds=30)]
    assert oi_grid_levels(oi_ts, [100.0, 110.0], _hours(0, 4, 8)) == [100.0, 110.0]


def test_a_zero_placeholder_is_none_at_the_close_it_reaches_never_the_level_before_it():
    oi_ts = [DAY0 + timedelta(hours=4, minutes=-10), DAY0 + timedelta(hours=4, minutes=-5), DAY0 + timedelta(hours=8, minutes=-5)]
    assert oi_grid_levels(oi_ts, [100.0, 0.0, 105.0], _hours(0, 4, 8)) == [None, 105.0]


def test_a_union_close_before_or_after_the_rows_span_or_of_an_empty_series_reads_none():
    oi_ts = [DAY0 + timedelta(hours=12, minutes=-5), DAY0 + timedelta(hours=16, minutes=-5)]
    assert oi_grid_levels(oi_ts, [100.0, 110.0], _hours(*range(0, 28, 4))) == [None, None, 100.0, 110.0, None, None]
    assert oi_grid_levels([], [], _hours(0, 4)) == [None]


def test_a_union_stamp_off_a_4h_mark_is_refused_by_name():
    with pytest.raises(AlphaError, match=re.escape("union_ts[2] = 2024-03-01T09:00:00+00:00 is not on a 4 h mark")):
        oi_grid_levels(_hours(1, 5, 9), [100.0, 101.0, 102.0], _hours(0, 4, 9))


@pytest.mark.parametrize(
    ("oi_ts", "union_ts", "named"),
    [
        pytest.param(_hours(5, 1, 9), _hours(0, 4, 8), "oi_ts", id="unsorted-rows"),
        pytest.param(_hours(1, 5, 5), _hours(0, 4, 8), "oi_ts", id="duplicate-rows"),
        pytest.param(_hours(1, 5, 9), _hours(0, 8, 4), "union_ts", id="unsorted-union"),
        pytest.param([DAY0.replace(hour=1, tzinfo=None)] + _hours(5, 9), _hours(0, 4, 8), "oi_ts", id="naive-row"),
        pytest.param(_hours(1, 5, 9), [DAY0.replace(tzinfo=None)] + _hours(4, 8), "union_ts", id="naive-union"),
    ],
)
def test_oi_grid_levels_refuses_unsorted_or_naive_stamps(oi_ts, union_ts, named):
    with pytest.raises(AlphaError, match=named):
        oi_grid_levels(oi_ts, [100.0, 101.0, 102.0], union_ts)


@pytest.mark.parametrize("oi_values", [[100.0, 101.0], [100.0, 101.0, 102.0, 103.0]], ids=["shorter", "longer"])
def test_oi_grid_levels_refuses_lists_of_unequal_length(oi_values):
    with pytest.raises(AlphaError, match="equal length"):
        oi_grid_levels(_hours(1, 5, 9), oi_values, _hours(0, 4, 8))


def _oi_prefix_fixture() -> tuple[list[datetime], list[float], list[datetime]]:
    """Two rows for each of 240 bars but 37 and 38; a union opening at bar 30, missing bar 100's open and closing one
    bar past the rows; and the substrate's shapes planted inside it: a close's own row stamped 30 s late at bar 33, a
    `0.0` placeholder as bar 35's last row, and no row in bars 37 and 38, whose closes find a level 4 h 5 min and
    8 h 5 min old."""
    oi_ts, oi_values = [], []
    for k in range(240):
        close = DAY0 + timedelta(hours=4 * (k + 1))
        if k in (37, 38):
            continue
        last = close + timedelta(seconds=30) if k == 33 else close - timedelta(minutes=5)
        oi_ts += [close - timedelta(minutes=10), last]
        oi_values += [100.0 + (37 * k) % 23, 0.0 if k == 35 else 100.5 + (53 * k) % 29]
    union_ts = [t for t in _hours(*range(4 * 30, 4 * 242, 4)) if t != DAY0 + timedelta(hours=4 * 100)]
    return oi_ts, oi_values, union_ts


def test_a_truncated_prefix_of_the_rows_reproduces_the_grid_levels_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    full = oi_grid_levels(oi_ts, oi_values, union_ts)
    # Return index j closes bar 30 + j up to the missing open, bar 31 + j after it: bars 35, 37 and 38 read None, and so
    # does bar 240, past the rows.
    assert len(full) == len(union_ts) - 1 and [j for j, v in enumerate(full) if v is None] == [5, 7, 8, len(full) - 1]
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = oi_grid_levels([oi_ts[i] for i in visible], [oi_values[i] for i in visible], union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


def _oi_on_the_grid(levels: list[float]) -> tuple[list[datetime], list[float], list[datetime]]:
    """Each level the later of two rows inside its bar, the earlier 1.5 times it: a feature over the raw rows and one
    over the grid disagree."""
    union_ts = _hours(*range(0, 4 * (len(levels) + 1), 4))
    oi_ts, oi_values = [], []
    for k, level in enumerate(levels):
        close = union_ts[k] + timedelta(hours=4)
        oi_ts += [close - timedelta(minutes=10), close - timedelta(minutes=5)]
        oi_values += [1.5 * level, level]
    return oi_ts, oi_values, union_ts


def test_the_oi_log_delta_is_bar_to_bar_on_the_grid_never_row_to_row():
    # Over the raw rows it would read each bar's last five minutes, log(1 / 1.5), at every close.
    assert oi_log_delta_grid_feature(*_oi_on_the_grid([100.0, 110.0, 121.0, 133.1])) == [None] + [pytest.approx(math.log(1.1))] * 3


def test_the_oi_zscore_recovers_a_spike_over_180_grid_bars():
    expected = [None] * 179 + [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_zscore_grid_feature(*_oi_on_the_grid([100.0] * 180 + [200.0])) == expected


def test_the_oi_momentum_reads_its_base_180_grid_bars_back():
    expected = [None] * 180 + [pytest.approx(1.8), pytest.approx(281 / 101 - 1)]
    assert oi_momentum_grid_feature(*_oi_on_the_grid([100.0 + k for k in range(182)])) == expected


def test_the_oi_windows_are_the_pre_registered_180_bars():
    assert (b2._OI_ZSCORE_WINDOW, b2._OI_MOMENTUM_LOOKBACK) == (180, 180)


def test_a_union_hole_leaves_the_next_oi_log_delta_a_single_4h_step():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0 * 1.1**k for k in range(6)])
    del union_ts[3]
    # The union has no close at 16 h; over its own closes the 20 h log-delta would span 8 h, log(1.21).
    assert oi_log_delta_grid_feature(oi_ts, oi_values, union_ts) == [None] + [pytest.approx(math.log(1.1))] * 4


def test_a_union_opening_inside_the_rows_span_reads_the_oi_zscore_warm():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0] * 180 + [200.0])
    # Two return indices closing on the spike fixture's last two marks; over their own two closes both would be None.
    assert oi_zscore_grid_feature(oi_ts, oi_values, union_ts[179:]) == [0.0, pytest.approx(179 / math.sqrt(180))]


def test_a_zero_placeholder_leaves_every_oi_zscore_window_holding_its_mark_none():
    oi_ts, oi_values, union_ts = _oi_on_the_grid([100.0] * 181)
    oi_values[1] = 0.0
    # Bar 0's later row is the placeholder: fallen back to its earlier row, 150.0, the first window would score.
    assert oi_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 180 + [0.0]


@pytest.mark.parametrize(
    ("emitter", "defined"),
    [(oi_log_delta_grid_feature, 204), (oi_zscore_grid_feature, 22), (oi_momentum_grid_feature, 57)],
    ids=["log-delta", "zscore", "momentum"],
)
def test_a_truncated_prefix_of_the_rows_reproduces_every_oi_trio_emitter_bit_for_bit(emitter, defined):
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    full = emitter(oi_ts, oi_values, union_ts)
    # Exact: a stale level the feature reads in place of None defines more closes, and so does a placeholder's fall-back,
    # save the z-score's, which the placeholder case carries.
    assert len(full) == len(union_ts) - 1 and sum(v is not None for v in full) == defined
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = emitter([oi_ts[i] for i in visible], [oi_values[i] for i in visible], union_ts[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


_RATIO_COLUMNS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def _each_ratio(values: list[float | None]) -> dict[str, list[float | None]]:
    return {name: list(values) for name in _RATIO_COLUMNS}


def _binperp(values: list[float | None]) -> dict[str, list[float | None]]:
    return {f"binperp_{name}": list(values) for name in _RATIO_COLUMNS}


def test_each_ratio_reads_its_bars_last_row_at_the_close_under_its_binperp_name():
    oi_ts = [DAY0 + timedelta(hours=4 * k + 4, minutes=m) for k in range(3) for m in (-10, -5)]
    ratios = {name: [i + 1.0 + r / 10 for r in range(6)] for i, name in enumerate(_RATIO_COLUMNS)}
    # Each bar's later row, from its own column: an earlier row, or a column read in another's place, differs.
    expected = {f"binperp_{name}": [i + 1.0 + r / 10 for r in (1, 3, 5)] for i, name in enumerate(_RATIO_COLUMNS)}
    assert ratio_grid_features(oi_ts, ratios, _hours(0, 4, 8, 12)) == expected


def test_a_ratio_row_exactly_4h_old_at_a_mark_is_none_and_one_a_second_younger_is_read():
    union = _hours(0, 4, 8, 12)
    assert ratio_grid_features(_hours(4, 12), _each_ratio([1.5, 2.5]), union) == _binperp([1.5, None, 2.5])
    younger = [DAY0 + timedelta(hours=4, seconds=1), DAY0 + timedelta(hours=12)]
    assert ratio_grid_features(younger, _each_ratio([1.5, 2.5]), union) == _binperp([None, 1.5, 2.5])


_TWO_BARS = [DAY0 + timedelta(hours=4, minutes=-10), DAY0 + timedelta(hours=4, minutes=-5), DAY0 + timedelta(hours=8, minutes=-5)]


def test_a_zero_taker_ratio_as_a_bars_last_row_is_read_never_mapped_to_none():
    ratios = _each_ratio([1.2, 1.3, 1.4]) | {"sum_taker_long_short_vol_ratio": [1.2, 0.0, 0.0]}
    # Mapped as an OI placeholder is, both closes would read None.
    assert ratio_grid_features(_TWO_BARS, ratios, _hours(0, 4, 8))["binperp_sum_taker_long_short_vol_ratio"] == [0.0, 0.0]


def test_a_null_ratio_as_a_bars_last_row_is_none_at_its_close_never_the_row_before_it():
    assert ratio_grid_features(_TWO_BARS, _each_ratio([1.2, None, 1.4]), _hours(0, 4, 8)) == _binperp([None, 1.4])


def test_ratio_grid_features_refuses_a_missing_ratio_column():
    with pytest.raises(FeatureError, match="missing ratio column"):
        ratio_grid_features(_hours(1, 5, 9), {name: [1.0, 1.1, 1.2] for name in _RATIO_COLUMNS[:3]}, _hours(0, 4, 8))


def test_ratio_grid_features_refuses_a_ratio_longer_than_the_rows_by_its_name():
    ratios = _each_ratio([1.0, 1.1, 1.2]) | {"count_long_short_ratio": [1.0, 1.1, 1.2, 1.3]}
    with pytest.raises(AlphaError, match="oi_ts and binperp_count_long_short_ratio must be equal length, got 3 and 4"):
        ratio_grid_features(_hours(1, 5, 9), ratios, _hours(0, 4, 8))


def test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_columns_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    ratios = _each_ratio([None if v == 0.0 else v / 100 for v in oi_values]) | {
        "sum_taker_long_short_vol_ratio": [v / 100 for v in oi_values]
    }
    full = ratio_grid_features(oi_ts, ratios, union_ts)
    # Return index j closes bar 30 + j up to the missing open: bars 37 and 38 are stale and bar 240 lies past the rows in
    # every column; bar 35 reads None where its last row is null and 0.0 in the taker ratio.
    last = len(union_ts) - 2
    assert {name: [j for j, v in enumerate(values) if v is None] for name, values in full.items()} == {
        f"binperp_{name}": [7, 8, last] if name == "sum_taker_long_short_vol_ratio" else [5, 7, 8, last] for name in _RATIO_COLUMNS
    }
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = ratio_grid_features(
            [oi_ts[i] for i in visible], {name: [values[i] for i in visible] for name, values in ratios.items()}, union_ts[: n + 1]
        )
        assert prefix == {name: values[:n] for name, values in full.items()}, f"prefix at n={n} disagrees with the full run"


def _buckets(rows: list[tuple[int, float, float]]) -> tuple[list[datetime], list[float], list[float]]:
    """`rows` holds `(minute after DAY0, long_usd, short_usd)` in order: one coin's bucket stamps and its two legs."""
    return [DAY0 + timedelta(minutes=m) for m, _, _ in rows], [lo for _, lo, _ in rows], [sh for _, _, sh in rows]


# BTC holds a bucket in each hour from 00:00 to 15:00, DOT one at 00:10 and one at 15:00.
_LIQUIDATIONS = {
    "BTC": [
        (5, 100.0, 0.0),
        (65, 0.0, 300.0),
        (130, 25.0, 25.0),
        (239, 50.0, 0.0),
        (240, 0.0, 80.0),
        (300, 20.0, 0.0),
        (370, 10.0, 0.0),
        (479, 0.0, 10.0),
        (485, 5.0, 0.0),
        (545, 2.0, 1.0),
        (610, 0.0, 7.0),
        (700, 3.0, 0.0),
        (725, 1.0, 0.0),
        (790, 0.0, 2.0),
        (850, 4.0, 4.0),
        (950, 0.0, 6.0),
    ],
    "DOT": [(10, 0.0, 40.0), (900, 9.0, 0.0)],
}
_LIQUIDATION_UNION = _hours(0, 4, 8, 12, 16)
_LIQUIDATION_COVERED = [t for t in _hours(*range(16)) if t != DAY0 + timedelta(hours=9)]


def test_each_liquidation_column_sums_its_bars_buckets_under_its_provenance_name():
    # The 03:59 bucket closes at 04:00 and is bar 0's; the 04:00 bucket is bar 1's. Bar 2 holds 09:00, not asserted.
    assert liquidation_grid_features(*_buckets(_LIQUIDATIONS["BTC"]), _LIQUIDATION_UNION, _LIQUIDATION_COVERED) == {
        "binperp_liq_lowerbound_long_usd": [175.0, 30.0, None, 5.0],
        "binperp_liq_lowerbound_short_usd": [325.0, 90.0, None, 12.0],
        "binperp_liq_lowerbound_total_usd": [500.0, 120.0, None, 17.0],
        "binperp_liq_imbalance": [-0.3, -0.5, None, -7 / 17],
    }


def test_a_covered_bar_with_no_bucket_for_the_coin_reads_zero_notional_and_no_imbalance():
    # DOT holds no bucket from 01:00 to 14:00: the assertion is what says the poller covered bar 1.
    features = liquidation_grid_features(*_buckets(_LIQUIDATIONS["DOT"]), _LIQUIDATION_UNION, _LIQUIDATION_COVERED)
    assert features == {
        "binperp_liq_lowerbound_long_usd": [0.0, 0.0, None, 9.0],
        "binperp_liq_lowerbound_short_usd": [40.0, 0.0, None, 0.0],
        "binperp_liq_lowerbound_total_usd": [40.0, 0.0, None, 9.0],
        "binperp_liq_imbalance": [-1.0, None, None, 1.0],
    }
    # The int 0 compares equal to 0.0 above: an empty bar's sums are floats, as every other bar's are.
    notionals = ("binperp_liq_lowerbound_long_usd", "binperp_liq_lowerbound_short_usd", "binperp_liq_lowerbound_total_usd")
    assert [type(features[name][1]) for name in notionals] == [float] * 3


def test_a_bar_holding_an_hour_not_asserted_covered_reads_none_even_over_its_buckets():
    # BTC holds a bucket at 09:05; read as covered, BTC's bar 2 would sum to 10.0 long and 8.0 short.
    for coin in ("BTC", "DOT"):
        features = liquidation_grid_features(*_buckets(_LIQUIDATIONS[coin]), _LIQUIDATION_UNION, _LIQUIDATION_COVERED)
        assert [values[2] for values in features.values()] == [None] * 4


@pytest.mark.parametrize("hour", [8, 11], ids=["first", "last"])
def test_a_bar_whose_first_or_last_hour_is_not_asserted_covered_reads_none(hour):
    # Bar 2 is [08:00, 12:00): hours 8 and 11 are its first and last.
    covered = [t for t in _hours(*range(16)) if t != DAY0 + timedelta(hours=hour)]
    for coin in ("BTC", "DOT"):
        features = liquidation_grid_features(*_buckets(_LIQUIDATIONS[coin]), _LIQUIDATION_UNION, covered)
        assert [values[2] for values in features.values()] == [None] * 4, coin


def test_liquidation_grid_features_refuses_bucket_lists_of_unequal_length():
    bucket_ts, long_usd, short_usd = _buckets(_LIQUIDATIONS["DOT"])
    with pytest.raises(AlphaError, match=re.escape("bucket_ts, long_usd and short_usd must be equal length, got 2, 2 and 3")):
        liquidation_grid_features(bucket_ts, long_usd, short_usd + [1.0], _LIQUIDATION_UNION, _LIQUIDATION_COVERED)


def test_liquidation_grid_features_refuses_an_empty_read_by_name():
    with pytest.raises(AlphaError, match=re.escape("bucket_ts is empty: every covered bar would sum to zero")):
        liquidation_grid_features([], [], [], _LIQUIDATION_UNION, _LIQUIDATION_COVERED)


@pytest.mark.parametrize("bucket_ts", [_hours(0, 2, 1), _hours(0, 1, 1)], ids=["unsorted", "repeated"])
def test_liquidation_grid_features_refuses_unsorted_or_repeated_bucket_stamps(bucket_ts):
    # Read anyway, a repeated bucket is summed twice and an unsorted one can fall outside its bar's slice.
    with pytest.raises(AlphaError, match=re.escape("bucket_ts must be strictly increasing, violated at index 2")):
        liquidation_grid_features(bucket_ts, [1.0, 2.0, 3.0], [0.0, 0.0, 0.0], _hours(0, 4), _hours(0, 1, 2, 3))


def test_liquidation_grid_features_refuses_a_naive_bucket_stamp_by_name():
    bucket_ts = _hours(0, 1) + [(DAY0 + timedelta(hours=2)).replace(tzinfo=None)]
    with pytest.raises(AlphaError, match=re.escape("bucket_ts must be tz-aware datetimes, bucket_ts[2] = ")):
        liquidation_grid_features(bucket_ts, [1.0, 2.0, 3.0], [0.0, 0.0, 0.0], _hours(0, 4), _hours(0, 1, 2, 3))


@pytest.mark.parametrize(
    "stamp",
    [
        (DAY0 + timedelta(hours=5)).replace(tzinfo=None),
        DAY0 + timedelta(hours=5, minutes=31),
        DAY0.replace(hour=10, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ],
    ids=["naive", "off-hour", "half-hour-zone"],
)
def test_liquidation_grid_features_refuses_a_naive_or_off_hour_covered_stamp_by_name(stamp):
    covered = [stamp if t == DAY0 + timedelta(hours=5) else t for t in _LIQUIDATION_COVERED]
    with pytest.raises(AlphaError, match=re.escape(f"covered must be tz-aware hour starts, got {stamp.isoformat()}")):
        liquidation_grid_features(*_buckets(_LIQUIDATIONS["BTC"]), _LIQUIDATION_UNION, covered)


def test_a_liquidation_union_stamp_off_a_4h_mark_is_refused_by_name():
    with pytest.raises(AlphaError, match=re.escape("union_ts[1] = 2024-03-01T05:00:00+00:00 is not on a 4 h mark")):
        liquidation_grid_features(*_buckets(_LIQUIDATIONS["BTC"]), _hours(0, 5, 9), _LIQUIDATION_COVERED)


def test_a_truncated_prefix_of_the_buckets_reproduces_every_liquidation_column_bit_for_bit():
    btc = [(60 * h + (17 * h) % 60, float(h % 3), float(h % 4 + 1)) for h in range(56) if h not in (13, 26)]
    dot = [(60 * h + 30, 2.0, 0.0) for h in (0, 7, 13, 14, 21, 35, 42, 49)]
    rows = {"BTC": _buckets(btc), "DOT": _buckets(dot)}
    covered = [t for t in _hours(*range(56)) if t != DAY0 + timedelta(hours=18)]
    # Return index j opens bar j + 1 up to the missing open of bar 7, bar j + 2 after it; the last closes on the last hour.
    union_ts = [t for t in _hours(*range(4, 60, 4)) if t != DAY0 + timedelta(hours=28)]
    full = {coin: liquidation_grid_features(*columns, union_ts, covered) for coin, columns in rows.items()}
    # Exact: bar 4 holds h = 18, not asserted, and DOT holds no bucket in bars 2, 6, 9, 11 and 13. Bar 6, before the
    # missing open, is covered: stretched across the hole, it would sum hours its prefix at n = 6 neither holds nor asserts.
    assert [j for j, v in enumerate(full["BTC"]["binperp_liq_lowerbound_total_usd"]) if v is None] == [3]
    assert [j for j, v in enumerate(full["DOT"]["binperp_liq_lowerbound_total_usd"]) if v is None] == [3]
    assert [j for j, v in enumerate(full["DOT"]["binperp_liq_imbalance"]) if v is None] == [1, 3, 5, 7, 9, 11]
    for n in range(1, len(union_ts)):
        # The buckets and the assertion truncated alike at the cutoff, a bucket closing a minute after its stamp.
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        prefix_covered = [t for t in covered if t + timedelta(hours=1) <= cutoff]
        for coin, (bucket_ts, long_usd, short_usd) in rows.items():
            k = sum(t + timedelta(minutes=1) <= cutoff for t in bucket_ts)
            prefix = liquidation_grid_features(bucket_ts[:k], long_usd[:k], short_usd[:k], union_ts[: n + 1], prefix_covered)
            assert prefix == {name: values[:n] for name, values in full[coin].items()}, f"{coin} prefix at n={n} disagrees"


def _ratios_on_the_grid(marks: int) -> tuple[list[datetime], dict[str, list[float | None]], list[datetime]]:
    """Column i holds 1.0 at every mark but mark 180 + i, where it holds 2.0, each level the later of two rows inside its
    bar, the earlier 1.5 times it: a z-score over the raw rows, or a column read in another's place, differs."""
    union_ts = _hours(*range(0, 4 * (marks + 1), 4))
    oi_ts, ratios = [], {name: [] for name in _RATIO_COLUMNS}
    for k in range(marks):
        close = union_ts[k] + timedelta(hours=4)
        oi_ts += [close - timedelta(minutes=10), close - timedelta(minutes=5)]
        for i, name in enumerate(_RATIO_COLUMNS):
            level = 2.0 if k == 180 + i else 1.0
            ratios[name] += [1.5 * level, level]
    return oi_ts, ratios, union_ts


def test_each_ratio_zscore_scores_its_own_columns_level_over_180_grid_marks():
    spike, after = pytest.approx(179 / math.sqrt(180)), pytest.approx(-1 / math.sqrt(180))
    expected = {
        f"binperp_{name}_z30d": [None] * 179 + [0.0] * (1 + i) + [spike] + [after] * (3 - i)
        for i, name in enumerate(_RATIO_COLUMNS)
    }
    assert ratio_zscore_grid_features(*_ratios_on_the_grid(184)) == expected


def test_a_zero_taker_ratio_is_scored_where_an_oi_level_gate_would_refuse_it():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["sum_taker_long_short_vol_ratio"] = [0.0] * len(oi_ts)
    features = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    assert features["binperp_sum_taker_long_short_vol_ratio_z30d"] == [None] * 179 + [0.0, 0.0]


def test_a_null_ratio_leaves_every_zscore_window_holding_its_mark_none():
    oi_ts, ratios, union_ts = _ratios_on_the_grid(181)
    ratios["count_long_short_ratio"][1] = None
    # Bar 0's later row is null: fallen back to its earlier row, 1.5, the first window would score.
    assert ratio_zscore_grid_features(oi_ts, ratios, union_ts)["binperp_count_long_short_ratio_z30d"] == [None] * 180 + [0.0]


def test_the_ratio_and_daily_windows_are_the_pre_registered_180_marks_and_30_days():
    assert (b2._RATIO_ZSCORE_WINDOW, b2._DAILY_ZSCORE_WINDOW) == (180, 30)


def test_a_truncated_prefix_of_the_rows_reproduces_the_ratio_zscores_bit_for_bit():
    oi_ts, oi_values, union_ts = _oi_prefix_fixture()
    ratios = _each_ratio([None if v == 0.0 else v / 100 for v in oi_values]) | {
        "sum_taker_long_short_vol_ratio": [v / 100 for v in oi_values]
    }
    full = ratio_zscore_grid_features(oi_ts, ratios, union_ts)
    # Exact: a stale level read in place of None, or a null fallen back to its row's predecessor, defines more closes.
    assert {name: sum(v is not None for v in values) for name, values in full.items()} == {
        f"binperp_{name}_z30d": 22 for name in _RATIO_COLUMNS
    }
    for n in range(1, len(union_ts)):
        cutoff = union_ts[n - 1] + timedelta(hours=4)
        visible = [i for i, t in enumerate(oi_ts) if t <= cutoff]
        prefix = ratio_zscore_grid_features(
            [oi_ts[i] for i in visible], {name: [values[i] for i in visible] for name, values in ratios.items()}, union_ts[: n + 1]
        )
        assert prefix == {name: values[:n] for name, values in full.items()}, f"prefix at n={n} disagrees with the full run"


def test_the_ratio_signal_is_the_columns_maximum_where_every_column_is_read():
    columns = {"a": [1.0, 3.0, None, -0.5], "b": [2.0, -1.0, 4.0, None], "c": [0.0, 0.0, 0.0, 0.0]}
    # Their mean reads 1.0 and 0.667 at the first two, their minimum 0.0 and -1.0, the read ones' maximum 4.0 and 0.0 at
    # the last two.
    assert ratio_max_signal(columns) == [2.0, 3.0, None, None]


@pytest.mark.parametrize(
    ("columns", "match"),
    [({}, "z_columns is empty"), ({"a": [1.0], "b": [1.0, 2.0]}, "b has length 2, expected 1")],
    ids=["no-column", "unequal-length"],
)
def test_ratio_max_signal_refuses_no_column_or_columns_of_unequal_length(columns, match):
    with pytest.raises(AlphaError, match=match):
        ratio_max_signal(columns)


def _days(*days: int) -> list[datetime]:
    return [DAY0 + timedelta(days=d) for d in days]


def test_a_daily_zscore_reaches_a_close_only_once_its_day_has_ended():
    # Day 30 doubles the 1.0 of days 0-29. Union closes run from day 30 20:00 to day 32 04:00.
    union = [DAY0 + timedelta(days=30, hours=16 + 4 * k) for k in range(10)]
    feature = daily_zscore_grid_feature(_days(*range(31)), [1.0] * 30 + [2.0], union)
    # Day 30 20:00 reads day 29, flat; day 31 00:00 to 20:00 read day 30; day 32 reads day 31, which the series lacks.
    assert feature == [0.0] + [pytest.approx(29 / math.sqrt(30))] * 6 + [None] * 2


def test_a_day_the_series_lacks_darkens_every_window_holding_it():
    days = [d for d in range(62) if d != 10]
    union = [DAY0 + timedelta(days=d + 1) for d in range(62)]
    feature = daily_zscore_grid_feature(_days(*days), [1.0] * len(days), union)
    # Each close at day d + 1 00:00 reads day d: day 10 is absent, so windows over days 0..39 hold it, and day 40's opens clean.
    assert [d for d, v in enumerate(feature) if v is not None] == list(range(40, 61))


@pytest.mark.parametrize(
    ("day_ts", "named"),
    [
        (_days(0, 1)[:1] + [DAY0 + timedelta(days=1, hours=1)], "day_ts[1] = 2024-03-02T01:00:00+00:00 is not a UTC day's start"),
        (_days(0) + [DAY0.replace(day=2, tzinfo=timezone(timedelta(hours=5)))], "is not a UTC day's start"),
        (_days(1, 0), "day_ts must be strictly increasing, violated at index 1"),
        ([DAY0.replace(tzinfo=None), DAY0.replace(day=2, tzinfo=None)], "day_ts must be tz-aware datetimes"),
    ],
    ids=["off-midnight", "a-zone-midnight", "unsorted", "naive"],
)
def test_daily_zscore_refuses_a_stamp_off_a_utc_day_start_by_name(day_ts, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        daily_zscore_grid_feature(day_ts, [1.0, 2.0], _hours(0, 4))


@pytest.mark.parametrize(
    ("day_ts", "values", "named"),
    [(_days(0, 1), [1.0], "day_ts and values must be equal length, got 2 and 1"), ([], [], "day_ts is empty")],
    ids=["unequal-length", "empty"],
)
def test_daily_zscore_refuses_unequal_lengths_and_an_empty_series(day_ts, values, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        daily_zscore_grid_feature(day_ts, values, _hours(0, 4))


def test_a_truncated_prefix_of_the_days_reproduces_the_daily_zscore_bit_for_bit():
    days = [d for d in range(70) if d not in (12, 33)]
    values = [100.0 + (37 * d) % 23 for d in days]
    # A union with a hole at day 40's first bar, opening a bar before day 0 ends.
    union = [t for t in (DAY0 + timedelta(hours=20 + 4 * k) for k in range(6 * 70)) if t != DAY0 + timedelta(days=40)]
    full = daily_zscore_grid_feature(_days(*days), values, union)
    # Exact: day 33 is absent, so no window before day 63 is whole; day 63's value enters at day 64's first close.
    assert [j for j, v in enumerate(full) if v is not None][0] == union.index(DAY0 + timedelta(days=63, hours=20))
    for n in range(1, len(union)):
        cutoff = union[n - 1] + timedelta(hours=4)
        # Two days at least: the z-score reads a list of two or more.
        k = sum(DAY0 + timedelta(days=d + 1) <= cutoff for d in days)
        if k < 2:
            continue
        prefix = daily_zscore_grid_feature(_days(*days[:k]), values[:k], union[: n + 1])
        assert prefix == full[:n], f"prefix at n={n} disagrees with the full run"


def test_each_covered_hour_sums_both_legs_of_its_buckets_and_any_other_hour_reads_none():
    bucket_ts, long_usd, short_usd = _buckets(_LIQUIDATIONS["BTC"])
    # Hour 9 is not asserted covered; hour 16 is, and holds no bucket.
    hours = _hours(0, 1, 2, 9, 15, 16)
    covered = [t for t in _hours(*range(17)) if t != DAY0 + timedelta(hours=9)]
    totals = liquidation_hourly_totals(bucket_ts, long_usd, short_usd, hours, covered)
    assert totals == [100.0, 300.0, 50.0, None, 6.0, 0.0] and type(totals[-1]) is float


@pytest.mark.parametrize(
    ("hours", "covered", "named"),
    [
        (_hours(0, 1) + [DAY0 + timedelta(hours=2, minutes=5)], _hours(0, 1, 2), "hour_ts must be tz-aware hour starts, got"),
        (_hours(0, 1, 2), _hours(0, 1) + [DAY0 + timedelta(hours=2, minutes=5)], "covered must be tz-aware hour starts, got"),
    ],
    ids=["an-hour-off-its-start", "a-covered-stamp-off-its-start"],
)
def test_liquidation_hourly_totals_refuses_a_stamp_off_an_hour_start_by_name(hours, covered, named):
    with pytest.raises(AlphaError, match=re.escape(named)):
        liquidation_hourly_totals(*_buckets(_LIQUIDATIONS["BTC"]), hours, covered)


def _reference_contrast(rows: list[tuple[list, list]], draws: list[list[int]]) -> list[float]:
    """The contrast's row by hand: point means over the read indices, and the percentile bounds over the resamples that
    hold an event and another."""
    events = [v for flags, values in rows for f, v in zip(flags, values) if f is True and v is not None]
    others = [v for flags, values in rows for f, v in zip(flags, values) if f is False and v is not None]
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    point = sum(events) / len(events) - sum(others) / len(others)
    return [
        len(events),
        len(others),
        sum(events) / len(events),
        sum(others) / len(others),
        point,
        _percentile(diffs, 0.025),
        _percentile(diffs, 0.975),
    ]


def test_the_event_contrast_compares_the_means_after_events_and_after_the_others_with_shared_bootstrap_bounds():
    flags = {
        "BTC": [True, False, False, True, None, False, True, False, False, False, True, False],
        "ETH": [False, True, False, False, True, False, None, True, False, False, False, True],
        "DOT": [True, False, False, False, False, False, False, False, False, False, False, False],
    }
    values = {
        "BTC": [0.03, 0.01, -0.02, 0.05, 9.0, 0.0, 0.04, 0.02, -0.01, 0.01, None, 0.00],
        "ETH": [0.01, -0.03, 0.02, 0.00, -0.02, 0.01, 9.0, -0.04, 0.03, 0.01, 0.02, -0.01],
        "DOT": [0.07, 0.01, 0.0, 0.01, 0.02, 0.0, 0.01, 0.0, 0.02, 0.01, 0.0, 0.03],
    }
    out = event_contrast(flags, {"ret": values}, mean_block=3, n_resamples=200, seed=7)
    draws = stationary_bootstrap_indices(12, mean_block=3, n_resamples=200, seed=7)
    # DOT holds one event and is left out; BTC's fourth event has no forward value, and an unread flag reads nothing.
    assert set(out["ret"]) == {"BTC", "ETH", "pooled"}
    for name, rows in (("BTC", [(flags["BTC"], values["BTC"])]), ("ETH", [(flags["ETH"], values["ETH"])])):
        assert out["ret"][name] == pytest.approx(_reference_contrast(rows, draws)), name
    pooled = [(flags[a], values[a]) for a in ("BTC", "ETH")]
    assert out["ret"]["pooled"] == pytest.approx(_reference_contrast(pooled, draws))
    assert out["ret"]["BTC"][:2] == [3, 7] and [type(x) for x in out["ret"]["BTC"]] == [int, int] + [float] * 5


def test_event_contrast_refuses_a_forward_series_of_another_length():
    with pytest.raises(AlphaError, match=re.escape("forwards['ret']['BTC'] has length 2, expected 3")):
        event_contrast({"BTC": [True, False, True]}, {"ret": {"BTC": [0.1, 0.2]}}, mean_block=2, n_resamples=10, seed=1)


# Sixteen indices and two series: ETH holds two events and two others after "ret", so that some resamples draw neither
# other, and one event after "late", which lacks its second event's forward, so the series keep different assets; DOT
# holds one event in either, LTC two events and one other, and neither series keeps them.
_CHUNKED_FLAGS = {
    "BTC": [True, False, False, True, None, False, True, False, False, False, True, False, False, True, False, False],
    "ETH": [False, None, False, None, True, None, None, None, None, None, None, True, None, None, None, None],
    "DOT": [True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False],
    "LTC": [True, None, None, True, None, None, None, None, None, None, None, None, None, None, False, None],
}
_CHUNKED_RET = {
    "BTC": [0.03, 0.01, -0.02, 0.05, 9.0, 0.0, 0.04, 0.02, -0.01, 0.01, None, 0.0, 0.02, -0.03, 0.01, 0.0],
    "ETH": [0.01, -0.03, 0.02, 0.0, -0.02, 0.01, 9.0, -0.04, 0.03, 0.01, 0.02, -0.01, 0.0, 0.02, -0.02, 0.01],
    "DOT": [0.07, 0.01, 0.0, 0.01, 0.02, 0.0, 0.01, 0.0, 0.02, 0.01, 0.0, 0.03, 0.01, 0.0, 0.02, 0.01],
    "LTC": [0.04, 0.02, -0.01, 0.06, 0.01, 0.0, 0.03, -0.02, 0.01, 0.0, 0.02, 0.01, -0.01, 0.03, 0.05, 0.0],
}
_CHUNKED_LATE = {
    "BTC": [*_CHUNKED_RET["BTC"][1:], None],
    "ETH": [*_CHUNKED_RET["ETH"][1:12], None, *_CHUNKED_RET["ETH"][13:], None],
    "DOT": [*_CHUNKED_RET["DOT"][1:], None],
    "LTC": [*_CHUNKED_RET["LTC"][1:], None],
}


def _far_bounds(rows: list[tuple[list, list]], draws: list[list[int]]) -> list[float]:
    """The 0.05 % and 99.95 % percentiles, by hand, of the differences over the resamples holding an event and another."""
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    return [_percentile(diffs, 0.0005), _percentile(diffs, 0.9995)]


@pytest.mark.parametrize("chunk", [1, 7, 10, 200, 500], ids=lambda chunk: f"chunk-{chunk}")
def test_the_chunked_contrast_is_the_event_contrasts_rows_over_the_same_resamples_each_with_its_far_bounds_after_it(
    chunk, monkeypatch
):
    forwards = {"ret": _CHUNKED_RET, "late": _CHUNKED_LATE, "none": {a: [None] * 16 for a in _CHUNKED_FLAGS}}
    chunks, draw = [], b2._bootstrap_chunks
    monkeypatch.setattr(b2, "_bootstrap_chunks", lambda n_obs, **kwargs: chunks.append(kwargs["chunk"]) or draw(n_obs, **kwargs))

    out = event_contrast_chunked(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7, chunk=chunk)

    whole = event_contrast(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7)
    assert {series: {name: row[:7] for name, row in rows.items()} for series, rows in out.items()} == whole
    assert (list(out["ret"]), list(out["late"]), out["none"]) == (["BTC", "ETH", "pooled"], ["BTC", "pooled"], {})
    assert {type(v) for rows in out.values() for row in rows.values() for v in row} <= {int, float}
    assert (chunks, event_contrast_chunked.__kwdefaults__["chunk"]) == ([chunk], 10)
    draws = stationary_bootstrap_indices(16, mean_block=3, n_resamples=200, seed=7)
    for name, members in (("ETH", ["ETH"]), ("pooled", ["BTC", "ETH"])):
        rows = [(_CHUNKED_FLAGS[a], _CHUNKED_RET[a]) for a in members]
        assert out["ret"][name][7:] == pytest.approx(_far_bounds(rows, draws)), name


def test_the_chunked_draw_yields_at_most_chunk_resamples_at_a_time_and_together_the_whole_draws_resamples():
    yielded = list(b2._bootstrap_chunks(30, mean_block=3, n_resamples=25, seed=7, chunk=7))

    assert [rows.shape for rows in yielded] == [(7, 30), (7, 30), (7, 30), (4, 30)]
    whole = stationary_bootstrap_indices(30, mean_block=3, n_resamples=25, seed=7)
    assert [row for rows in yielded for row in rows.tolist()] == whole


def test_no_chunk_but_the_last_is_alive_when_the_chunked_contrast_draws_the_next(monkeypatch):
    refs, alive, draw = [], [], b2._bootstrap_chunks

    def counted(n_obs, **kwargs):
        for rows in draw(n_obs, **kwargs):
            refs.append(weakref.ref(rows))
            yield rows
            alive.append(sum(ref() is not None for ref in refs))

    monkeypatch.setattr(b2, "_bootstrap_chunks", counted)

    event_contrast_chunked(_CHUNKED_FLAGS, {"ret": _CHUNKED_RET}, mean_block=3, n_resamples=50, seed=7, chunk=7)

    assert len(alive) == len(refs) == 8
    assert max(alive) <= 1


@pytest.mark.parametrize(
    ("change", "error", "match"),
    [
        pytest.param({"chunk": 0}, AlphaError, "chunk must be an int >= 1, got 0", id="chunk-0"),
        pytest.param({"chunk": True}, AlphaError, "chunk must be an int >= 1, got True", id="chunk-bool"),
        pytest.param({"n_resamples": 0}, ValidationError, "n_resamples must be an int >= 1, got 0", id="no-resample"),
        pytest.param({"mean_block": 0.5}, ValidationError, "mean_block must be finite and >= 1, got 0.5", id="block-under-1"),
        pytest.param({"flags": {"BTC": []}, "forwards": {}}, ValidationError, "n_obs must be an int >= 1, got 0", id="no-index"),
        pytest.param(
            {"forwards": {"ret": {"BTC": [0.1, 0.2]}}},
            AlphaError,
            re.escape("forwards['ret']['BTC'] has length 2, expected 3"),
            id="forward-length",
        ),
    ],
)
def test_the_chunked_contrast_refuses_what_the_event_contrast_refuses_and_a_chunk_below_1(change, error, match):
    arguments = {"flags": {"BTC": [True, False, True]}, "forwards": {"ret": {"BTC": [0.1, 0.2, 0.3]}}}
    arguments |= {"mean_block": 2, "n_resamples": 10, "seed": 1} | change
    with pytest.raises(error, match=match):
        event_contrast_chunked(**arguments)
    if "chunk" not in change:
        with pytest.raises(error, match=match):
            event_contrast(**arguments)


def test_the_oi_log_delta_zscore_is_taken_over_180_grid_log_deltas_and_reads_warm_at_a_late_union():
    # Each level twice the last, then four times it: every grid log-delta log(2), then log(4).
    oi_ts, oi_values, union_ts = _oi_on_the_grid([2.0**k for k in range(181)] + [2.0**182])
    spike = [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_log_delta_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 180 + spike
    assert oi_log_delta_zscore_grid_feature(oi_ts, oi_values, union_ts[180:]) == spike


def test_the_oi_momentum_zscore_is_taken_over_180_grid_momenta_and_reads_warm_at_a_late_union():
    # Each level twice the last, then four times it: every 180-bar momentum the same, then the last about twice it.
    oi_ts, oi_values, union_ts = _oi_on_the_grid([2.0**k for k in range(360)] + [2.0**361])
    spike = [0.0, pytest.approx(179 / math.sqrt(180))]
    assert oi_momentum_zscore_grid_feature(oi_ts, oi_values, union_ts) == [None] * 359 + spike
    assert oi_momentum_zscore_grid_feature(oi_ts, oi_values, union_ts[359:]) == spike


@pytest.mark.parametrize(
    ("n_obs", "mean_block", "n_resamples", "seed"),
    [(30, 3, 25, 7), (16, 1, 4, 2), (1, 2, 3, 5), (40, 1000, 6, 9)],
    ids=["short-blocks", "every-index-fresh", "one-index", "long-blocks-wrapping"],
)
def test_the_block_draw_holds_each_stationary_bootstrap_resample_as_its_blocks(n_obs, mean_block, n_resamples, seed):
    blocks = stationary_bootstrap_blocks(n_obs, mean_block=mean_block, n_resamples=n_resamples, seed=seed)

    bounds = [*blocks.firsts.tolist(), len(blocks.starts)]
    spans = [zip(blocks.starts[a:b].tolist(), blocks.lengths[a:b].tolist()) for a, b in zip(bounds, bounds[1:])]
    resamples = [[(start + step) % n_obs for start, length in span for step in range(length)] for span in spans]
    assert blocks.n_obs == n_obs
    assert resamples == stationary_bootstrap_indices(n_obs, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    # Four bytes an entry: the reading's draw holds about 10.8 million blocks.
    assert {values.dtype.itemsize for values in (blocks.starts, blocks.lengths, blocks.firsts)} == {4}


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param({"n_obs": 0}, "n_obs must be an int >= 1, got 0", id="no-index"),
        pytest.param({"mean_block": 0.5}, "mean_block must be finite and >= 1, got 0.5", id="block-under-1"),
        pytest.param({"n_resamples": 0}, "n_resamples must be an int >= 1, got 0", id="no-resample"),
    ],
)
def test_the_block_draw_refuses_what_the_stationary_bootstrap_refuses(change, match):
    arguments = {"n_obs": 3, "mean_block": 2, "n_resamples": 10, "seed": 1} | change
    with pytest.raises(ValidationError, match=match):
        stationary_bootstrap_blocks(**arguments)
    with pytest.raises(ValidationError, match=match):
        stationary_bootstrap_indices(**arguments)


def _bounds_at(rows: list[tuple[list, list]], draws: list[list[int]], low: float, high: float) -> list[float]:
    """The percentiles `low` and `high`, as fractions, by hand, of the differences over the resamples holding an event and
    another."""
    diffs = []
    for idx in draws:
        ev = [values[k] for flags, values in rows for k in idx if flags[k] is True and values[k] is not None]
        ot = [values[k] for flags, values in rows for k in idx if flags[k] is False and values[k] is not None]
        if ev and ot:
            diffs.append(sum(ev) / len(ev) - sum(ot) / len(ot))
    diffs.sort()
    return [_percentile(diffs, low), _percentile(diffs, high)]


def test_the_block_contrast_is_the_chunked_contrasts_rows_with_its_far_bounds_at_the_percentiles_it_is_given():
    forwards = {"ret": _CHUNKED_RET, "late": _CHUNKED_LATE, "none": {a: [None] * 16 for a in _CHUNKED_FLAGS}}
    blocks = stationary_bootstrap_blocks(16, mean_block=3, n_resamples=200, seed=7)

    out = event_contrast_blocks(_CHUNKED_FLAGS, forwards, blocks, far=(0.05, 99.95))

    chunked = event_contrast_chunked(_CHUNKED_FLAGS, forwards, mean_block=3, n_resamples=200, seed=7)
    assert {series: list(rows) for series, rows in out.items()} == {series: list(rows) for series, rows in chunked.items()}
    for series, rows in out.items():
        for name, row in rows.items():
            assert row[:5] == chunked[series][name][:5], (series, name)
            assert row[5:] == pytest.approx(chunked[series][name][5:], rel=1e-12, abs=1e-15), (series, name)
    assert {type(v) for rows in out.values() for row in rows.values() for v in row} <= {int, float}
    draws = stationary_bootstrap_indices(16, mean_block=3, n_resamples=200, seed=7)
    at_one = event_contrast_blocks(_CHUNKED_FLAGS, forwards, blocks, far=(1, 99))
    for name, members in (("ETH", ["ETH"]), ("pooled", ["BTC", "ETH"])):
        rows = [(_CHUNKED_FLAGS[a], _CHUNKED_RET[a]) for a in members]
        assert at_one["ret"][name][7:] == pytest.approx(_bounds_at(rows, draws, 0.01, 0.99), rel=1e-12, abs=1e-15), name


@pytest.mark.parametrize(
    ("change", "match"),
    [
        pytest.param({"n_obs": 4}, "blocks draw over 4 indices and the flags hold 3", id="another-draw"),
        pytest.param({"far": [0.05, 99.95]}, "got [0.05, 99.95]", id="far-a-list"),
        pytest.param({"far": (0.05, 50, 99.95)}, "got (0.05, 50, 99.95)", id="far-three"),
        pytest.param({"far": (False, 99.95)}, "got (False, 99.95)", id="far-a-bool"),
        pytest.param({"far": (-0.05, 99.95)}, "got (-0.05, 99.95)", id="far-below-0"),
        pytest.param({"far": (99.95, 99.95)}, "got (99.95, 99.95)", id="far-not-rising"),
        pytest.param({"far": (0.05, 100.05)}, "got (0.05, 100.05)", id="far-above-100"),
        pytest.param({"forwards": {"ret": {"BTC": [0.1]}}}, "forwards['ret']['BTC'] has length 1, expected 3", id="forward-length"),
    ],
)
def test_the_block_contrast_refuses_a_draw_over_other_indices_far_bounds_it_cannot_read_and_an_unpaired_forward(change, match):
    arguments = {"flags": {"BTC": [True, False, True]}, "forwards": {"ret": {"BTC": [0.1, 0.2, 0.3]}}, "far": (0.05, 99.95)}
    arguments |= {key: value for key, value in change.items() if key != "n_obs"}
    blocks = stationary_bootstrap_blocks(change.get("n_obs", 3), mean_block=2, n_resamples=10, seed=1)
    with pytest.raises(AlphaError, match=re.escape(match)):
        event_contrast_blocks(blocks=blocks, **arguments)
