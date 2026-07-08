import math

import pytest

from cli.features import FeatureError, momentum


def test_momentum_known_answer():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    m = momentum(prices, lookback=2)
    assert m == pytest.approx([0.0, 0.0, 12 / 10 - 1, 13 / 11 - 1])


def test_momentum_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    m = momentum(prices, lookback=2)
    assert len(m) == len(prices) - 1
    assert m[:2] == [0.0, 0.0]


def test_momentum_short_series_all_warmup():
    assert momentum([10.0, 11.0], lookback=5) == [0.0]


def test_momentum_no_lookahead():
    base_prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0, 14.0]
    lookback, k = 2, 3
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = momentum(base_prices, lookback=lookback)
    pert = momentum(perturbed, lookback=lookback)
    assert pert[: k + 1] == base[: k + 1]  # values through k unchanged despite the future mutation


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_momentum_prices_guards(prices):
    with pytest.raises(FeatureError):
        momentum(prices, lookback=2)


@pytest.mark.parametrize("lookback", [True, False, 1, 0, -1, 2.5, "x"])
def test_momentum_lookback_guards(lookback):
    with pytest.raises(FeatureError):
        momentum([10.0, 11.0, 12.0, 13.0], lookback=lookback)


def test_momentum_rejects_nonfinite_price():
    with pytest.raises(FeatureError):
        momentum([10.0, float("inf"), 12.0], lookback=2)


def test_momentum_output_is_finite():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0]
    m = momentum(prices, lookback=2)
    assert all(math.isfinite(v) for v in m)
