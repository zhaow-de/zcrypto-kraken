import math

import pytest

from cli.features import FeatureError, drawdown_state


def test_drawdown_state_new_high_is_zero():
    prices = [10.0, 11.0, 12.0]  # monotonically rising -> always at a new high
    assert drawdown_state(prices) == [0.0, 0.0]


def test_drawdown_state_known_answer_below_peak():
    # peak = 10 set at index 0; price drops to 8 at index 1 -> dd[1] = 8/10 - 1 = -0.2
    prices = [10.0, 8.0, 9.0]
    dd = drawdown_state(prices)
    assert dd[0] == pytest.approx(0.0)
    assert dd[1] == pytest.approx(-0.2)


def test_drawdown_state_recovery_to_new_high():
    # peak = 10, dips to 8, recovers to 12 (a fresh high) -> dd back to 0.0
    prices = [10.0, 8.0, 12.0, 11.0]
    dd = drawdown_state(prices)
    assert dd[2] == pytest.approx(0.0)


def test_drawdown_state_length_and_first_value():
    prices = [10.0, 11.0, 12.0, 13.0]
    dd = drawdown_state(prices)
    assert len(dd) == len(prices) - 1
    assert dd[0] == 0.0  # a price is trivially its own running peak


def test_drawdown_state_short_series():
    assert drawdown_state([10.0, 8.0]) == [0.0]


def test_drawdown_state_no_lookahead():
    base_prices = [10.0, 8.0, 12.0, 9.0, 14.0, 7.0]
    k = 3
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = drawdown_state(base_prices)
    pert = drawdown_state(perturbed)
    assert pert[: k + 1] == base[: k + 1]  # values through k unchanged despite the future mutation


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_drawdown_state_prices_guards(prices):
    with pytest.raises(FeatureError):
        drawdown_state(prices)


def test_drawdown_state_output_is_finite_and_bounded():
    prices = [10.0, 8.0, 12.0, 9.0, 14.0, 7.0]
    dd = drawdown_state(prices)
    assert all(math.isfinite(v) and -1.0 <= v <= 0.0 for v in dd)
