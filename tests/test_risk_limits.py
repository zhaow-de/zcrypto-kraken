import pytest

from cli.risk import RiskError, apply_position_caps


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


@pytest.mark.parametrize(
    "positions",
    [
        {},
        {"BTC": []},
        {"BTC": [0.1], "ETH": [0.1, 0.2]},  # ragged
        {"BTC": [float("nan")]},
        {"BTC": [float("inf")]},
        {"BTC": "not a list"},
        "not a dict",
    ],
)
def test_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_position_caps(positions)


@pytest.mark.parametrize("kwargs", [{"long_cap": 0.0}, {"long_cap": -0.2}, {"short_cap": 0.0}, {"short_cap": float("nan")}])
def test_invalid_caps(kwargs):
    with pytest.raises(RiskError):
        apply_position_caps({"BTC": [0.1]}, **kwargs)
