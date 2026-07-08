import math

import pytest

from cli.backtest import BacktestError, run_backtest
from cli.validation import annualized_return, max_drawdown, sharpe


def test_buy_and_hold_timing_and_entry_cost():
    r = run_backtest([0.10, -0.05, 0.20], [1.0, 1.0, 1.0], fee_rate=0.01, periods_per_year=252)
    assert r["net_returns"] == pytest.approx([0.09, -0.05, 0.20])
    assert r["total_return"] == pytest.approx(1.09 * 0.95 * 1.20 - 1)
    assert r["n_periods"] == 3


def test_zero_fee_constant_position():
    ar = [0.01, 0.02, -0.03, 0.04]
    r = run_backtest(ar, [0.5] * 4, fee_rate=0.0, periods_per_year=252)
    assert r["net_returns"] == pytest.approx([0.5 * x for x in ar])


def test_turnover_cost_on_sign_flip():
    r = run_backtest([0.02, 0.01, 0.03], [1.0, 1.0, -1.0], fee_rate=0.01, periods_per_year=252)
    assert r["net_returns"][2] == pytest.approx(-1.0 * 0.03 - 2.0 * 0.01)


def test_metrics_reuse_the_harness():
    ar = [0.01, -0.02, 0.03, 0.00, 0.02]
    pos = [1.0, 0.5, 1.0, 0.5, 1.0]
    r = run_backtest(ar, pos, fee_rate=0.0, periods_per_year=252)
    net = r["net_returns"]
    assert r["sharpe"] == pytest.approx(sharpe(net, periods_per_year=252))
    assert r["max_drawdown"] == pytest.approx(max_drawdown(net))
    assert r["annualized_return"] == pytest.approx(annualized_return(net, periods_per_year=252))


def test_flat_strategy_raises():
    with pytest.raises(BacktestError):
        run_backtest([0.01, -0.02, 0.03, 0.01, 0.0], [0.0] * 5, periods_per_year=252)


def test_blowup_raises():
    with pytest.raises(BacktestError):
        run_backtest([0.0, -0.4], [3.0, 3.0], periods_per_year=252)


@pytest.mark.parametrize(
    "ar,pos,kwargs",
    [
        ([0.01], [1.0, 1.0], {"periods_per_year": 252}),
        ([0.01], [1.0], {"periods_per_year": 252}),
        ([0.01, float("nan")], [1.0, 1.0], {"periods_per_year": 252}),
        ([0.01, 0.02], [1.0, float("inf")], {"periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"fee_rate": -0.01, "periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"fee_rate": "x", "periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"periods_per_year": 0}),
        ([0.01, 0.02], [1.0, 1.0], {"periods_per_year": 2.5}),
    ],
)
def test_run_backtest_guards(ar, pos, kwargs):
    with pytest.raises(BacktestError):
        run_backtest(ar, pos, **kwargs)


def test_positive_drift_buy_and_hold():
    ar = [0.01 + 0.005 * ((i % 3) - 1) for i in range(300)]  # mean 0.01, non-zero variance
    r = run_backtest(ar, [1.0] * 300, fee_rate=0.0, periods_per_year=252)
    assert r["total_return"] > 0 and math.isfinite(r["sharpe"]) and r["sharpe"] > 0
