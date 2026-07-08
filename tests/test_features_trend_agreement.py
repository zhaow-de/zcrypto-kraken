import math

import pytest

from cli.features import FeatureError, trend_agreement


def test_trend_agreement_known_answer_all_rising():
    # Monotonically rising prices -> momentum is positive on every lookback once warm, so the mean
    # sign across lookbacks=[2, 3] reaches +1.0 once the largest lookback (3) is warm (k >= 3).
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    ta = trend_agreement(prices, lookbacks=[2, 3])
    assert ta[3] == pytest.approx(1.0)
    assert ta[4] == pytest.approx(1.0)


def test_trend_agreement_known_answer_split():
    # At k=5 (all of lookbacks=[2, 3, 5] warm): momentum(lookback=2)[5] and momentum(lookback=3)[5]
    # are positive (60 > 50), momentum(lookback=5)[5] is negative (60 < 100) -> mean sign = 1/3.
    prices = [100.0, 90.0, 50.0, 50.0, 55.0, 60.0, 65.0]
    ta = trend_agreement(prices, lookbacks=[2, 3, 5])
    assert ta[5] == pytest.approx(1 / 3)


def test_trend_agreement_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    ta = trend_agreement(prices, lookbacks=[2, 4])
    assert len(ta) == len(prices) - 1
    assert ta[:2] == [0.0, 0.0]  # k < min(lookbacks) -> every momentum is still 0.0 -> agreement 0.0


def test_trend_agreement_short_series_all_warmup():
    assert trend_agreement([10.0, 11.0], lookbacks=[5, 8]) == [0.0]


def test_trend_agreement_no_lookahead():
    base_prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    lookbacks, k = [2, 3], 3
    perturbed = list(base_prices)
    perturbed[k + 1] = 999.0
    base = trend_agreement(base_prices, lookbacks=lookbacks)
    pert = trend_agreement(perturbed, lookbacks=lookbacks)
    assert pert[: k + 1] == base[: k + 1]  # values through k unchanged despite the future mutation


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_trend_agreement_prices_guards(prices):
    with pytest.raises(FeatureError):
        trend_agreement(prices, lookbacks=[2, 3])


@pytest.mark.parametrize(
    "lookbacks",
    [[], [1], [0], [-1], [2.5], ["x"], [True], [False], [2, True], "not a list", None],
)
def test_trend_agreement_lookbacks_guards(lookbacks):
    with pytest.raises(FeatureError):
        trend_agreement([10.0, 11.0, 12.0, 13.0], lookbacks=lookbacks)


def test_trend_agreement_output_is_finite_and_bounded():
    prices = [10.0, 11.0, 9.0, 12.0, 8.0, 14.0, 13.0]
    ta = trend_agreement(prices, lookbacks=[2, 3])
    assert all(math.isfinite(v) and -1.0 <= v <= 1.0 for v in ta)
