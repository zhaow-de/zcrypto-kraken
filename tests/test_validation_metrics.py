import math
import statistics

import pytest

from cli.validation import ValidationError, annualized_return, max_drawdown, sharpe, volatility


def test_sharpe_zero_mean():
    assert sharpe([0.02, -0.02, 0.02, -0.02]) == pytest.approx(0.0)


def test_sharpe_positive():
    assert sharpe([0.01, 0.03]) == pytest.approx(0.02 / statistics.stdev([0.01, 0.03]))
    assert sharpe([0.01, 0.03]) == pytest.approx(1.4142, abs=1e-4)


def test_sharpe_annualized():
    assert sharpe([0.01, 0.03], periods_per_year=252) == pytest.approx(sharpe([0.01, 0.03]) * math.sqrt(252))


def test_sharpe_risk_free_lowers():
    assert sharpe([0.01, 0.03], risk_free=0.01) < sharpe([0.01, 0.03])


@pytest.mark.parametrize(
    "returns,kwargs",
    [
        ([0.01], {}),
        ([0.01, float("nan")], {}),
        ([0.01, 0.03], {"risk_free": float("inf")}),
        ([0.01, 0.03], {"periods_per_year": 0}),
        ([0.01, 0.03], {"periods_per_year": -1}),
        ([0.01, 0.03], {"periods_per_year": 2.5}),
        ([0.01, 0.01, 0.01], {}),
    ],
)
def test_sharpe_guards(returns, kwargs):
    with pytest.raises(ValidationError):
        sharpe(returns, **kwargs)


def test_volatility():
    assert volatility([0.01, 0.03]) == pytest.approx(0.0141421356, abs=1e-7)
    assert volatility([0.01, 0.03], periods_per_year=252) == pytest.approx(statistics.stdev([0.01, 0.03]) * math.sqrt(252))


@pytest.mark.parametrize("returns,kwargs", [([0.01], {}), ([0.01, float("nan")], {}), ([0.01, 0.03], {"periods_per_year": -1})])
def test_volatility_guards(returns, kwargs):
    with pytest.raises(ValidationError):
        volatility(returns, **kwargs)


def test_annualized_return():
    assert annualized_return([0.1, 0.1], periods_per_year=2) == pytest.approx(0.21)
    assert annualized_return([0.0] * 252, periods_per_year=252) == pytest.approx(0.0)
    # n != periods_per_year and cumulative != 1: pins the exponent direction (ppy/n, not n/ppy).
    # (1.01**10) ** (252/10) - 1 == 1.01**252 - 1; the inverted n/ppy exponent gives ~0.004, far off.
    assert annualized_return([0.01] * 10, periods_per_year=252) == pytest.approx(1.01**252 - 1)


@pytest.mark.parametrize(
    "returns,ppy",
    [([], 252), ([0.01, float("inf")], 252), ([0.01], 0), ([0.01], 2.5), ([-1.5, 0.1], 252)],
)
def test_annualized_return_guards(returns, ppy):
    with pytest.raises(ValidationError):
        annualized_return(returns, periods_per_year=ppy)


def test_max_drawdown():
    assert max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(0.5)
    assert max_drawdown([0.1, 0.1, 0.1]) == pytest.approx(0.0)


@pytest.mark.parametrize("returns", [[], [0.1, float("nan")], [-1.5, 0.1]])
def test_max_drawdown_guards(returns):
    with pytest.raises(ValidationError):
        max_drawdown(returns)
