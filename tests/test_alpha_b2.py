import math
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from cli.alpha import b2
from cli.alpha.b1 import book_turnover
from cli.alpha.b2 import (
    B2Config,
    close_grid,
    derisk_scales,
    funding_carry_grid_feature,
    funding_grid_feature,
    funding_sign_grid_feature,
    liquidation_grid_features,
    net_of_cost,
    oi_grid_levels,
    oi_log_delta_grid_feature,
    oi_momentum_grid_feature,
    oi_zscore_grid_feature,
    per_year_engaged_counts,
    per_year_max_drawdown,
    per_year_positions_differ,
    per_year_turnover,
    ratio_grid_features,
    scale_positions,
)
from cli.alpha.errors import AlphaError
from cli.features.errors import FeatureError

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
    # The fixture's `0.0`, bar 35's last row, is a null in three columns and a reading in the taker ratio.
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


# BTC holds a bucket in each hour from 00:00 to 15:00, DOT one at 00:10 and one at 15:00; the caller asserts every hour
# of the union's bars covered but 09:00.
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
    assert liquidation_grid_features(*_buckets(_LIQUIDATIONS["DOT"]), _LIQUIDATION_UNION, _LIQUIDATION_COVERED) == {
        "binperp_liq_lowerbound_long_usd": [0.0, 0.0, None, 9.0],
        "binperp_liq_lowerbound_short_usd": [40.0, 0.0, None, 0.0],
        "binperp_liq_lowerbound_total_usd": [40.0, 0.0, None, 9.0],
        "binperp_liq_imbalance": [-1.0, None, None, 1.0],
    }


def test_a_bar_holding_an_hour_not_asserted_covered_reads_none_even_over_its_buckets():
    # BTC holds a bucket at 09:05; read as covered, BTC's bar 2 would sum to 10.0 long and 8.0 short.
    for coin in ("BTC", "DOT"):
        features = liquidation_grid_features(*_buckets(_LIQUIDATIONS[coin]), _LIQUIDATION_UNION, _LIQUIDATION_COVERED)
        assert [values[2] for values in features.values()] == [None] * 4


def test_liquidation_grid_features_refuses_bucket_lists_of_unequal_length():
    bucket_ts, long_usd, short_usd = _buckets(_LIQUIDATIONS["DOT"])
    with pytest.raises(AlphaError, match=re.escape("bucket_ts, long_usd and short_usd must be equal length, got 2, 2 and 3")):
        liquidation_grid_features(bucket_ts, long_usd, short_usd + [1.0], _LIQUIDATION_UNION, _LIQUIDATION_COVERED)


def test_liquidation_grid_features_refuses_an_empty_read_by_name():
    with pytest.raises(AlphaError, match=re.escape("bucket_ts is empty: read anyway, every covered bar would sum to zero")):
        liquidation_grid_features([], [], [], _LIQUIDATION_UNION, _LIQUIDATION_COVERED)


@pytest.mark.parametrize("bucket_ts", [_hours(0, 2, 1), _hours(0, 1, 1)], ids=["unsorted", "repeated"])
def test_liquidation_grid_features_refuses_unsorted_or_repeated_bucket_stamps(bucket_ts):
    # Read anyway, a repeated bucket is summed twice and an unsorted one can fall outside its bar's slice.
    with pytest.raises(AlphaError, match=re.escape("bucket_ts must be strictly increasing, violated at index 2")):
        liquidation_grid_features(bucket_ts, [1.0, 2.0, 3.0], [0.0, 0.0, 0.0], _hours(0, 4), _hours(0, 1, 2, 3))


def test_a_liquidation_union_stamp_off_a_4h_mark_is_refused_by_name():
    with pytest.raises(AlphaError, match=re.escape("union_ts[1] = 2024-03-01T05:00:00+00:00 is not on a 4 h mark")):
        liquidation_grid_features(*_buckets(_LIQUIDATIONS["BTC"]), _hours(0, 5, 9), _LIQUIDATION_COVERED)


def test_a_truncated_prefix_of_the_buckets_reproduces_every_liquidation_column_bit_for_bit():
    # BTC holds a bucket in each of the 56 hours from DAY0 but the 13th and the 26th, DOT in eight of them, the 13th among
    # them; every hour is asserted covered but the 18th.
    btc = [(60 * h + (17 * h) % 60, float(h % 3), float(h % 4 + 1)) for h in range(56) if h not in (13, 26)]
    dot = [(60 * h + 30, 2.0, 0.0) for h in (0, 7, 13, 14, 21, 35, 42, 49)]
    rows = {"BTC": _buckets(btc), "DOT": _buckets(dot)}
    covered = [t for t in _hours(*range(56)) if t != DAY0 + timedelta(hours=18)]
    # Return index j opens bar j + 1 up to the missing open of bar 7, bar j + 2 after it; the last closes on the last hour.
    union_ts = [t for t in _hours(*range(4, 60, 4)) if t != DAY0 + timedelta(hours=28)]
    full = {coin: liquidation_grid_features(*columns, union_ts, covered) for coin, columns in rows.items()}
    # Exact: bar 4 holds the 18th hour, not asserted, and DOT holds no bucket in bars 2, 6, 9, 11 and 13. Bar 6, before the
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
