import pytest

from cli.alpha.a1 import _inverse_vol_weights
from cli.benchmark.strategies import dynamic_inverse_vol_basket

# The hand-verified fixture of test_dynamic_basket_known_answer_two_assets_entry (tests/test_benchmark_dynamic_basket.py).
A = [100, 102, 99.96, 109.956, 112.15512, 109.9120176]  # retA = [.02,-.02,.10,.02,-.02]
B = [None, None, 100, 118, 110.92, 116.466]  # retB = [None,None,.18,-.06,.05]


def test_inverse_vol_weights_known_answer():
    weights = _inverse_vol_weights({"A": A, "B": B}, lookback=2)
    assert weights[0] == {} and weights[1] == {}  # warm-up
    assert weights[2] == pytest.approx({"A": 1.0})  # only A qualifies
    assert weights[3] == pytest.approx({"A": 1.0})  # only A qualifies
    assert weights[4] == pytest.approx({"A": 0.75, "B": 0.25})  # both qualify, A's window 1/3 B's vol


def test_inverse_vol_weights_reduces_to_basket():
    prices = {"A": A, "B": B}
    lookback = 2
    weights = _inverse_vol_weights(prices, lookback=lookback)
    basket = dynamic_inverse_vol_basket(prices, lookback=lookback)
    for k in range(len(basket)):
        combo = 0.0
        for asset, w in weights[k].items():
            p0, p1 = prices[asset][k], prices[asset][k + 1]
            combo += w * (p1 / p0 - 1)
        assert abs(combo - basket[k]) < 1e-12


def test_inverse_vol_weights_no_look_ahead():
    # Mirrors test_dynamic_basket_no_look_ahead's future-leak check exactly (same fixture).
    common_a = [100, 101, 102, 103, 104, 105, 106]
    common_b = [100, 99, 101, 100, 102, 101, 103]
    a1, a2 = common_a + [107, 108, 109], common_a + [500, 2, 777]
    b1, b2 = common_b + [104, 105, 106], common_b + [3, 900, 12]
    w1 = _inverse_vol_weights({"A": a1, "B": b1}, lookback=2)
    w2 = _inverse_vol_weights({"A": a2, "B": b2}, lookback=2)
    assert w1[:6] == w2[:6]
