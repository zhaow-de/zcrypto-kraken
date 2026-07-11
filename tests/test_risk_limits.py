import math

import pytest

from cli.risk import (
    RiskError,
    apply_gross_leverage_cap,
    apply_margin_floor,
    apply_net_exposure_band,
    apply_position_caps,
    margin_level,
)

INVALID_POSITIONS = [
    {},
    {"BTC": []},
    {"BTC": [0.1], "ETH": [0.1, 0.2]},  # ragged
    {"BTC": [float("nan")]},
    {"BTC": [float("inf")]},
    {"BTC": "not a list"},
    "not a dict",
]


def test_long_clip():
    out = apply_position_caps({"BTC": [0.35, 0.10, 0.20]})
    assert out == {"BTC": [0.20, 0.10, 0.20]}  # 0.20 exactly is NOT clipped (inclusive)


def test_short_clip():
    out = apply_position_caps({"ETH": [-0.25, -0.05, -0.10]})
    assert out == {"ETH": [-0.10, -0.05, -0.10]}


def test_mixed_and_multi_asset():
    out = apply_position_caps({"BTC": [0.5, -0.5], "ETH": [0.0, 0.19]})
    assert out == {"BTC": [0.20, -0.10], "ETH": [0.0, 0.19]}


def test_custom_caps():
    out = apply_position_caps({"BTC": [0.5, -0.5]}, long_cap=0.3, short_cap=0.4)
    assert out == {"BTC": [0.3, -0.4]}


def test_input_not_mutated():
    src = {"BTC": [0.35]}
    apply_position_caps(src)
    assert src == {"BTC": [0.35]}


def test_shape_preserved():
    out = apply_position_caps({"A": [0.01] * 5, "B": [0.02] * 5})
    assert set(out) == {"A", "B"}
    assert all(len(v) == 5 for v in out.values())


@pytest.mark.parametrize("positions", INVALID_POSITIONS)
def test_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_position_caps(positions)


@pytest.mark.parametrize("kwargs", [{"long_cap": 0.0}, {"long_cap": -0.2}, {"short_cap": 0.0}, {"short_cap": float("nan")}])
def test_invalid_caps(kwargs):
    with pytest.raises(RiskError):
        apply_position_caps({"BTC": [0.1]}, **kwargs)


# --- apply_gross_leverage_cap ---


def test_gross_pass_through_below_cap():
    src = {"BTC": [0.5, 0.3], "ETH": [-0.2, 0.1]}  # gross 0.7, 0.4
    assert apply_gross_leverage_cap(src) == src


def test_gross_at_cap_inclusive():
    src = {"BTC": [1.0], "ETH": [0.5]}  # gross exactly 1.5
    assert apply_gross_leverage_cap(src) == src


def test_gross_breach_scaled_to_cap():
    out = apply_gross_leverage_cap({"BTC": [1.2], "ETH": [-0.9]})  # gross 2.1
    gross = abs(out["BTC"][0]) + abs(out["ETH"][0])
    assert gross == pytest.approx(1.5, abs=1e-12)


def test_gross_proportionality():
    out = apply_gross_leverage_cap({"BTC": [1.2], "ETH": [-0.9]})
    assert out["BTC"][0] / out["ETH"][0] == pytest.approx(1.2 / -0.9, abs=1e-12)
    assert out["BTC"][0] > 0 > out["ETH"][0]


def test_gross_per_bar_independence():
    out = apply_gross_leverage_cap({"BTC": [0.5, 2.0], "ETH": [0.5, 1.0]})  # bar0 gross 1.0, bar1 gross 3.0
    assert out["BTC"][0] == 0.5 and out["ETH"][0] == 0.5  # untouched bar is bit-identical
    assert out == {"BTC": [0.5, 1.0], "ETH": [0.5, 0.5]}


def test_gross_custom_caps():
    out = apply_gross_leverage_cap({"BTC": [2.0]}, soft_cap=1.0, hard_cap=1.0)
    assert out == {"BTC": [1.0]}


def test_gross_idempotent():
    once = apply_gross_leverage_cap({"BTC": [2.0, 0.5], "ETH": [1.0, -0.25]})
    assert apply_gross_leverage_cap(once) == once


def test_gross_input_not_mutated():
    src = {"BTC": [3.0]}
    apply_gross_leverage_cap(src)
    assert src == {"BTC": [3.0]}


@pytest.mark.parametrize("positions", INVALID_POSITIONS)
def test_gross_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_gross_leverage_cap(positions)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"soft_cap": 0.0},
        {"soft_cap": -1.5},
        {"soft_cap": float("nan")},
        {"hard_cap": 0.0},
        {"hard_cap": float("inf")},
        {"soft_cap": 2.5},  # > default hard_cap 2.0
        {"soft_cap": 1.6, "hard_cap": 1.5},
    ],
)
def test_gross_invalid_caps(kwargs):
    with pytest.raises(RiskError):
        apply_gross_leverage_cap({"BTC": [0.1]}, **kwargs)


# --- apply_net_exposure_band ---


def test_net_pass_through_within_band():
    src = {"BTC": [0.4, -0.3], "ETH": [-0.2, 0.1]}  # net 0.2, -0.2
    assert apply_net_exposure_band(src) == src


def test_net_at_long_bound_inclusive():
    src = {"BTC": [0.75], "ETH": [0.25]}  # net exactly 1.0
    assert apply_net_exposure_band(src) == src


def test_net_at_short_bound_inclusive():
    src = {"BTC": [-0.5]}  # net exactly -0.5
    assert apply_net_exposure_band(src) == src


def test_net_long_breach_scaled_to_bound():
    out = apply_net_exposure_band({"BTC": [0.8], "ETH": [0.6]})  # net 1.4
    assert out["BTC"][0] + out["ETH"][0] == pytest.approx(1.0, abs=1e-12)


def test_net_short_breach_scaled_to_bound():
    out = apply_net_exposure_band({"BTC": [-0.4], "ETH": [-0.3]})  # net -0.7
    assert out["BTC"][0] + out["ETH"][0] == pytest.approx(-0.5, abs=1e-12)


def test_net_mixed_book_scaled_whole_book():
    out = apply_net_exposure_band({"BTC": [1.4], "ETH": [-0.2]})  # net 1.2
    assert out["BTC"][0] + out["ETH"][0] == pytest.approx(1.0, abs=1e-12)
    assert out["BTC"][0] / out["ETH"][0] == pytest.approx(1.4 / -0.2, abs=1e-12)  # structure preserved
    assert out["ETH"][0] < 0  # the short leg shrinks but keeps its sign (gross shrinks too)


def test_net_zero_never_scales():
    src = {"BTC": [0.7], "ETH": [-0.7]}  # net exactly 0
    assert apply_net_exposure_band(src) == src


def test_net_custom_bounds():
    out = apply_net_exposure_band({"BTC": [0.8]}, short_bound=-1.0, long_bound=0.5)
    assert out == {"BTC": [0.5]}  # the whole net scales to the bound
    out = apply_net_exposure_band({"BTC": [-1.2]}, short_bound=-1.0, long_bound=0.5)
    assert out["BTC"][0] == pytest.approx(-1.0, abs=1e-12)


def test_net_idempotent():
    once = apply_net_exposure_band({"BTC": [1.5, -1.0], "ETH": [0.5, 0.0]})
    assert apply_net_exposure_band(once) == once


def test_net_input_not_mutated():
    src = {"BTC": [2.0]}
    apply_net_exposure_band(src)
    assert src == {"BTC": [2.0]}


@pytest.mark.parametrize("positions", INVALID_POSITIONS)
def test_net_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_net_exposure_band(positions)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"short_bound": 0.0},
        {"short_bound": 0.3},
        {"short_bound": float("nan")},
        {"long_bound": 0.0},
        {"long_bound": -1.0},
        {"long_bound": float("inf")},
    ],
)
def test_net_invalid_bounds(kwargs):
    with pytest.raises(RiskError):
        apply_net_exposure_band({"BTC": [0.1]}, **kwargs)


# --- margin_level ---


def test_margin_level_flat_book_is_inf():
    assert margin_level({"BTC": 0.0, "ETH": 0.0}) == math.inf


def test_margin_level_long_within_cash_is_inf():
    assert margin_level({"BTC": 0.5}) == math.inf  # no margin in use


def test_margin_level_levered_long():
    assert margin_level({"BTC": 1.5}) == 2.0  # m = 1.5 - 1.0 = 0.5


def test_margin_level_short_plus_long_at_floor():
    # m = 0.3 + max(0, 0.8 - max(0, 1 - 0.3)) = 0.4 -> level 2.5 (exact in the model; float puts it within 1e-12)
    assert margin_level({"BTC": -0.3, "ETH": 0.8}) == pytest.approx(2.5, abs=1e-12)


@pytest.mark.parametrize(
    "bar",
    [{}, {"BTC": float("nan")}, {"BTC": float("inf")}, {"BTC": "not a number"}, "not a dict"],
)
def test_margin_level_invalid(bar):
    with pytest.raises(RiskError):
        margin_level(bar)


# --- apply_margin_floor ---


def _brute_force_margin_scale(bar, floor):
    """Largest s on a 1e-6 grid keeping the scaled bar's margin level >= floor (scan down from 1)."""
    for k in range(1_000_000, -1, -1):
        s = k * 1e-6
        if margin_level({asset: w * s for asset, w in bar.items()}) >= floor:
            return s
    return 0.0


MARGIN_FIXTURES = {
    "long-levered": {"BTC": [1.0], "ETH": [0.5]},  # L=1.5, S=0 -> m=0.5, level 2.0
    "short-heavy": {"BTC": [-0.9], "ETH": [-0.3], "SOL": [0.2]},  # L=0.2, S=1.2 -> m=1.4
    "mixed": {"BTC": [1.0], "ETH": [-0.8]},  # L=1.0, S=0.8 -> m=1.6
}


def test_margin_floor_pass_through_no_margin():
    src = {"BTC": [0.6, 0.0], "ETH": [0.3, 0.2]}  # long-only within cash: m = 0, level inf
    assert apply_margin_floor(src) == src


def test_margin_floor_pass_through_above_floor():
    src = {"BTC": [1.1]}  # m = 0.1 -> level ~10 > 2.5
    assert apply_margin_floor(src) == src


def test_margin_floor_at_floor_inclusive():
    src = {"BTC": [-0.25], "ETH": [0.5]}  # m = S = 0.25 exactly -> level exactly 4.0
    assert apply_margin_floor(src, floor=4.0) == src
    src = {"BTC": [1.5]}  # m = 0.5 exactly -> level exactly 2.0
    assert apply_margin_floor(src, floor=2.0) == src


@pytest.mark.parametrize("name", sorted(MARGIN_FIXTURES))
def test_margin_floor_scaled_to_exactly_the_floor(name):
    positions = MARGIN_FIXTURES[name]
    out = apply_margin_floor(positions)
    assert margin_level({asset: series[0] for asset, series in out.items()}) == pytest.approx(2.5, abs=1e-12)


@pytest.mark.parametrize("name", sorted(MARGIN_FIXTURES))
def test_margin_floor_proportionality(name):
    positions = MARGIN_FIXTURES[name]
    out = apply_margin_floor(positions)
    assets = list(positions)
    factors = [out[a][0] / positions[a][0] for a in assets if positions[a][0] != 0.0]
    assert all(f == pytest.approx(factors[0], abs=1e-12) for f in factors)
    assert 0.0 < factors[0] < 1.0


@pytest.mark.parametrize("name", sorted(MARGIN_FIXTURES))
def test_margin_floor_closed_form_matches_brute_force(name):
    positions = MARGIN_FIXTURES[name]
    out = apply_margin_floor(positions)
    bar = {asset: series[0] for asset, series in positions.items()}
    anchor = next(a for a in positions if positions[a][0] != 0.0)
    s_closed = out[anchor][0] / positions[anchor][0]
    assert abs(s_closed - _brute_force_margin_scale(bar, 2.5)) <= 1e-6


def test_margin_floor_per_bar_independence():
    out = apply_margin_floor({"BTC": [0.5, 1.0], "ETH": [0.25, 0.5]})  # bar0 unlevered, bar1 = long-levered fixture
    assert out["BTC"][0] == 0.5 and out["ETH"][0] == 0.25  # untouched bar is bit-identical
    assert margin_level({"BTC": out["BTC"][1], "ETH": out["ETH"][1]}) == pytest.approx(2.5, abs=1e-12)


def test_margin_floor_custom_floor():
    out = apply_margin_floor({"BTC": [1.5]}, floor=5.0)  # t = 0.2, S = 0 -> s = 1.2/1.5 = 0.8
    assert out["BTC"][0] == pytest.approx(1.2, abs=1e-12)
    assert margin_level({"BTC": out["BTC"][0]}) == pytest.approx(5.0, abs=1e-12)


def test_margin_floor_idempotent():
    once = apply_margin_floor({"BTC": [3.0, 0.5]}, floor=2.0)  # s = 1.5/3.0 = 0.5 exactly -> level exactly at floor
    assert apply_margin_floor(once, floor=2.0) == once


def test_margin_floor_input_not_mutated():
    src = {"BTC": [3.0]}
    apply_margin_floor(src)
    assert src == {"BTC": [3.0]}


@pytest.mark.parametrize("positions", INVALID_POSITIONS)
def test_margin_floor_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_margin_floor(positions)


@pytest.mark.parametrize("floor", [0.0, -2.5, 0.5, 0.99, float("nan"), float("inf")])
def test_margin_floor_invalid_floor(floor):
    with pytest.raises(RiskError):
        apply_margin_floor({"BTC": [0.1]}, floor=floor)


def test_margin_floor_floor_of_one_accepted():
    out = apply_margin_floor({"BTC": [3.0]}, floor=1.0)  # t = 1, s = 2/3 -> L' = 2.0 -> m = 1.0 -> level 1.0
    assert margin_level({"BTC": out["BTC"][0]}) == pytest.approx(1.0, abs=1e-12)
