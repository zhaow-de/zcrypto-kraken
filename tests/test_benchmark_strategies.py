import math
import statistics

import pytest

from cli.backtest import run_backtest
from cli.benchmark import BenchmarkError, buy_and_hold, returns_from_prices, sma_gate, vol_target


def test_buy_and_hold():
    assert buy_and_hold(3) == [1.0, 1.0, 1.0]


@pytest.mark.parametrize("n", [0, -1, 2.5])
def test_buy_and_hold_guards(n):
    with pytest.raises(BenchmarkError):
        buy_and_hold(n)


def test_vol_target_warmup_zero():
    pos = vol_target([0.01, -0.02, 0.03, 0.01, -0.01], target_vol=0.02, lookback=3)
    assert pos[:3] == [0.0, 0.0, 0.0]


def test_vol_target_value_and_cap():
    returns = [0.01, -0.01, 0.02, 0.0, 0.0]
    s = statistics.stdev(returns[0:3])
    pos = vol_target(returns, target_vol=0.02, lookback=3, max_leverage=5.0)
    assert pos[3] == pytest.approx(min(0.02 / s, 5.0))
    capped = vol_target(returns, target_vol=1.0, lookback=3, max_leverage=1.5)
    assert capped[3] == pytest.approx(1.5)


def test_vol_target_no_lookahead():
    returns = [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.0]
    lookback, t = 3, 4
    base = vol_target(returns, target_vol=0.02, lookback=lookback)
    perturbed = list(returns)
    perturbed[t] = perturbed[t] + 0.5
    pert = vol_target(perturbed, target_vol=0.02, lookback=lookback)
    assert pert[t] == base[t]  # position_t does NOT use return_t
    assert pert[t + 1] != base[t + 1]  # position_{t+1}'s window includes t -> changes (window is real)


def test_vol_target_zero_vol_window():
    pos = vol_target([0.0, 0.0, 0.0, 0.0, 0.01], target_vol=0.02, lookback=3)
    assert pos[3] == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_vol": 0.0, "lookback": 3},
        {"target_vol": -0.1, "lookback": 3},
        {"target_vol": "x", "lookback": 3},
        {"target_vol": 0.02, "lookback": 1},
        {"target_vol": 0.02, "lookback": 2.5},
        {"target_vol": 0.02, "lookback": 3, "max_leverage": 0.0},
    ],
)
def test_vol_target_guards(kwargs):
    with pytest.raises(BenchmarkError):
        vol_target([0.01, -0.02, 0.03, 0.01], **kwargs)


def test_vol_target_empty_and_nonfinite():
    with pytest.raises(BenchmarkError):
        vol_target([], target_vol=0.02, lookback=3)
    with pytest.raises(BenchmarkError):
        vol_target([0.01, float("nan"), 0.03, 0.01], target_vol=0.02, lookback=3)


def test_vol_target_composes_with_backtester():
    returns = [0.01 + 0.01 * ((i % 4) - 1.5) for i in range(200)]
    pos = vol_target(returns, target_vol=0.015, lookback=20, max_leverage=2.0)
    r = run_backtest(returns, pos, fee_rate=0.0, periods_per_year=252)
    assert math.isfinite(r["sharpe"]) and r["n_periods"] == 200


def test_returns_from_prices():
    assert returns_from_prices([100.0, 110.0, 99.0]) == pytest.approx([0.10, -0.10])


@pytest.mark.parametrize(
    "prices",
    [[100.0], [], [100.0, float("nan")], [100.0, -5.0], [100.0, 0.0], "not a list"],
)
def test_returns_from_prices_guards(prices):
    with pytest.raises(BenchmarkError):
        returns_from_prices(prices)


def test_sma_gate_value():
    assert sma_gate([10.0, 11.0, 12.0, 9.0, 8.0, 13.0], window=3) == [0.0, 0.0, 1.0, 0.0, 0.0]


def test_sma_gate_length_and_warmup():
    prices = [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]
    g = sma_gate(prices, window=3)
    assert len(g) == len(prices) - 1
    assert g[:2] == [0.0, 0.0]


def test_sma_gate_no_lookahead():
    prices = [10.0, 11.0, 12.0, 9.0, 8.0, 13.0, 14.0]
    window, k = 3, 2
    base = sma_gate(prices, window=window)
    perturbed = list(prices)
    perturbed[k + 1] = 100.0
    pert = sma_gate(perturbed, window=window)
    assert pert[k] == base[k]  # signal[k]'s window excludes prices[k+1]
    assert pert[k + 1] != base[k + 1]  # signal[k+1]'s window includes k+1 -> changes (window is real)


def test_sma_gate_declining_mostly_flat():
    g = sma_gate([100.0, 90.0, 80.0, 70.0, 60.0, 50.0], window=3)
    assert all(s == 0.0 for s in g)


def test_sma_gate_short_series_all_flat():
    assert sma_gate([10.0, 11.0], window=5) == [0.0]


@pytest.mark.parametrize(
    "prices,window",
    [([10.0], 3), ([10.0, float("nan")], 3), ([10.0, -5.0], 3), ([10.0, 11.0, 12.0], 1), ([10.0, 11.0, 12.0], 2.5)],
)
def test_sma_gate_guards(prices, window):
    with pytest.raises(BenchmarkError):
        sma_gate(prices, window=window)


def test_sma_gate_composes_with_backtester():
    prices = [100.0 * (1.003**i) * (1 + 0.02 * ((i % 5) - 2)) for i in range(300)]
    rets = returns_from_prices(prices)
    gate = sma_gate(prices, window=50)
    r0 = run_backtest(rets, gate, fee_rate=0.0, periods_per_year=252)  # gated buy-and-hold
    assert math.isfinite(r0["sharpe"]) and r0["n_periods"] == len(rets)
    gv = [g * v for g, v in zip(gate, vol_target(rets, target_vol=0.01, lookback=20, max_leverage=1.0))]
    r1 = run_backtest(rets, gv, fee_rate=0.0, periods_per_year=252)  # gated vol-target
    assert math.isfinite(r1["sharpe"])
