import math
import statistics

import pytest

from cli.benchmark.strategies import returns_from_prices
from cli.features import FeatureError, realized_vol


def test_realized_vol_known_answer():
    prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    lookback = 3
    returns = returns_from_prices(prices)
    rv = realized_vol(prices, lookback=lookback)
    assert len(rv) == len(prices) - 1
    for k in range(lookback, len(prices) - 1):
        expected = statistics.stdev(returns[k - lookback : k])
        assert rv[k] == pytest.approx(expected)


def test_realized_vol_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    rv = realized_vol(prices, lookback=3)
    assert len(rv) == len(prices) - 1
    assert rv[:3] == [0.0, 0.0, 0.0]  # k < lookback


def test_realized_vol_short_series_all_warmup():
    assert realized_vol([10.0, 11.0], lookback=5) == [0.0]


def test_realized_vol_zero_vol_window():
    prices = [10.0, 10.0, 10.0, 10.0, 10.0]
    rv = realized_vol(prices, lookback=2)
    assert rv == [0.0, 0.0, 0.0, 0.0]


def test_realized_vol_no_lookahead():
    # The last return used for rv[k] must be returns[k-1] (move prices[k-1]->prices[k]), never
    # returns[k] (which uses prices[k+1]). Mutating prices[k+1] must not change rv[k].
    base_prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    lookback, k = 3, 4
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = realized_vol(base_prices, lookback=lookback)
    pert = realized_vol(perturbed, lookback=lookback)
    assert pert[: k + 1] == base[: k + 1]


def test_realized_vol_window_bound_is_exclusive_of_return_k():
    # The off-by-one window returns[k-lookback+1:k+1] would take returns[k] (= prices[k+1]/prices[k] - 1)
    # and let prices[k+1] move rv[k].
    base_prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    lookback, k = 3, 4
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = realized_vol(base_prices, lookback=lookback)
    pert = realized_vol(perturbed, lookback=lookback)
    assert pert[k] == base[k]


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_realized_vol_prices_guards(prices):
    with pytest.raises(FeatureError):
        realized_vol(prices, lookback=2)


@pytest.mark.parametrize("lookback", [True, False, 1, 0, -1, 2.5, "x"])
def test_realized_vol_lookback_guards(lookback):
    with pytest.raises(FeatureError):
        realized_vol([10.0, 11.0, 12.0, 13.0], lookback=lookback)


def test_realized_vol_output_is_finite_and_nonnegative():
    prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    rv = realized_vol(prices, lookback=3)
    assert all(math.isfinite(v) and v >= 0.0 for v in rv)
