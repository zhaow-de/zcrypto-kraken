import math

import pytest

from cli.features import FeatureError, channel_position


def test_channel_position_known_answer():
    # window=3; k ranges over indices where the trailing 3-price window is prices[k-2:k+1].
    # prices: 10, 11, 12, 9, 8, 13 (indices 0..5) -> len(prices)-1 = 5 feature values (k=0..4).
    # k=2: window prices[0:3]=[10,11,12], hi=12, lo=10, P=12 -> fresh high -> 2*(12-10)/(12-10)-1 = +1.0
    # k=3: window prices[1:4]=[11,12,9], hi=12, lo=9, P=9 -> fresh low -> 2*(9-9)/(12-9)-1 = -1.0
    # k=4: window prices[2:5]=[12,9,8], hi=12, lo=8, P=8 -> fresh low -> -1.0
    prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0]
    cp = channel_position(prices, window=3)
    assert len(cp) == len(prices) - 1
    assert cp[:2] == [0.0, 0.0]  # warm-up: k < window-1 = 2
    assert cp[2] == pytest.approx(1.0)
    assert cp[3] == pytest.approx(-1.0)
    assert cp[4] == pytest.approx(-1.0)


def test_channel_position_midpoint():
    # window=3, prices where P sits exactly at the midpoint of hi/lo for a window.
    # window prices[0:3] = [10, 12, 14] -> hi=14, lo=10, P at k=2 is 14 -> not midpoint, use k where
    # P is the middle value instead: window = [10, 14, 12], hi=14, lo=10, P=12 -> 2*(12-10)/(14-10)-1 = 0.0
    prices = [10.0, 14.0, 12.0, 20.0]
    cp = channel_position(prices, window=3)
    assert cp[2] == pytest.approx(0.0)


def test_channel_position_flat_window():
    assert channel_position([5.0, 5.0, 5.0, 5.0], window=3) == [0.0, 0.0, 0.0]


def test_channel_position_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    cp = channel_position(prices, window=4)
    assert len(cp) == len(prices) - 1
    assert cp[:3] == [0.0, 0.0, 0.0]  # k < window-1 = 3


def test_channel_position_short_series_all_warmup():
    assert channel_position([10.0, 11.0], window=5) == [0.0]


def test_channel_position_no_lookahead():
    base_prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0, 14.0]
    window, k = 3, 3
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = channel_position(base_prices, window=window)
    pert = channel_position(perturbed, window=window)
    assert pert[: k + 1] == base[: k + 1]  # values through k unchanged despite the future mutation


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_channel_position_prices_guards(prices):
    with pytest.raises(FeatureError):
        channel_position(prices, window=2)


@pytest.mark.parametrize("window", [True, False, 1, 0, -1, 2.5, "x"])
def test_channel_position_window_guards(window):
    with pytest.raises(FeatureError):
        channel_position([10.0, 11.0, 12.0, 13.0], window=window)


def test_channel_position_output_is_finite():
    prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0]
    cp = channel_position(prices, window=3)
    assert all(math.isfinite(v) for v in cp)
