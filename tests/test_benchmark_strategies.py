import math
import statistics

import pytest

from cli.backtest import run_backtest
from cli.benchmark import BenchmarkError, buy_and_hold, vol_target


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
