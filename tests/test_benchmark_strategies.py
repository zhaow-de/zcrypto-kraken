import math
import statistics

import pytest

from cli.backtest import run_backtest
from cli.benchmark import BenchmarkError, buy_and_hold, inverse_vol_basket, returns_from_prices, sma_gate, vol_target


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


def test_inverse_vol_basket_value_two_assets():
    # A has 1/3 the trailing vol of B at t=2 -> weights 0.75 / 0.25.
    # returns_A[:2]=[0.02,-0.02] (stdev s), returns_B[:2]=[0.06,-0.06] (stdev 3s).
    # portfolio[2] = 0.75*returns_A[2] + 0.25*returns_B[2] = 0.75*0.10 + 0.25*(-0.20) = 0.025.
    a = [100, 102, 99.96, 109.956]
    b = [100, 106, 99.64, 79.712]
    out = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    assert out[0] == 0.0 and out[1] == 0.0
    assert abs(out[2] - 0.025) < 1e-9


def test_inverse_vol_basket_equal_vol_equal_weight():
    # C and D share the same trailing window -> equal vol -> 0.5/0.5.
    # portfolio[2] = 0.5*(0.10 + 0.04) = 0.07.
    c = [100, 102, 99.96, 109.956]
    d = [100, 102, 99.96, 103.9584]
    out = inverse_vol_basket({"C": c, "D": d}, lookback=2)
    assert abs(out[2] - 0.07) < 1e-9


def test_inverse_vol_basket_length_and_warmup():
    prices = {"A": [100, 101, 102, 103, 104, 105], "B": [100, 99, 101, 98, 102, 97]}
    out = inverse_vol_basket(prices, lookback=2)
    assert len(out) == 6 - 1  # L - 1
    assert out[0] == 0.0 and out[1] == 0.0  # first `lookback` are warm-up


def test_inverse_vol_basket_no_look_ahead():
    # Perturbing an asset's LAST price changes only the last return; it must not
    # alter any earlier portfolio return (a future price cannot leak backward).
    a = [100, 101, 102, 101, 103, 104]
    b = [100, 99, 101, 100, 102, 101]
    base = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    a2 = a.copy()
    a2[-1] = 130.0  # very different last price -> changes returns_A[-1] only
    perturbed = inverse_vol_basket({"A": a2, "B": b}, lookback=2)
    assert base[:-1] == perturbed[:-1]  # all earlier periods identical (no leak)
    assert base[-1] != perturbed[-1]  # the last period does use the last price


def test_inverse_vol_basket_window_is_real():
    # Perturbing the FIRST price moves returns[0], which is inside the vol window
    # of the first weighted period (t=lookback) -> its weight, hence its return, changes.
    a = [100, 101, 102, 101, 103, 104]
    b = [100, 99, 101, 100, 102, 101]
    base = inverse_vol_basket({"A": a, "B": b}, lookback=2)
    a2 = a.copy()
    a2[0] = 60.0  # changes returns_A[0] (in the window [0:2] of period t=2)
    perturbed = inverse_vol_basket({"A": a2, "B": b}, lookback=2)
    assert perturbed[0] == 0.0 and perturbed[1] == 0.0  # warm-up unchanged
    assert base[2] != perturbed[2]  # first weighted period's weight moved


def test_inverse_vol_basket_zero_vol_asset_excluded():
    # E is constant over the trailing window (vol 0) -> dropped at t=2;
    # F carries weight 1, so portfolio[2] == F's own return[2].
    e = [100, 100, 100, 110]
    f = [100, 102, 99.96, 105]
    out = inverse_vol_basket({"E": e, "F": f}, lookback=2)
    assert abs(out[2] - (105 / 99.96 - 1)) < 1e-9


def test_inverse_vol_basket_all_zero_vol_day_is_flat():
    # Both assets constant over the window -> nothing weightable -> 0.0.
    e = [100, 100, 100, 110]
    g = [50, 50, 50, 40]
    out = inverse_vol_basket({"E": e, "G": g}, lookback=2)
    assert out[2] == 0.0


def test_inverse_vol_basket_single_asset():
    # One asset -> weight 1 after warm-up -> basket return == that asset's returns.
    a = [100, 101, 102, 103, 104, 105]
    out = inverse_vol_basket({"A": a}, lookback=2)
    rets = returns_from_prices(a)
    assert len(out) == len(rets)
    for t in range(2):
        assert out[t] == 0.0
    for t in range(2, len(rets)):
        assert abs(out[t] - rets[t]) < 1e-12


def test_inverse_vol_basket_guards():
    good = [100, 101, 102, 103]
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({}, lookback=2)  # empty dict
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good, "B": [100, 101, 102]}, lookback=2)  # unequal lengths
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, 101, 102]}, lookback=2)  # L=3 < lookback+2=4
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, -1, 102, 103]}, lookback=2)  # non-positive price
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": [100, float("nan"), 102, 103]}, lookback=2)  # non-finite
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good}, lookback=1)  # lookback < 2
    with pytest.raises(BenchmarkError):
        inverse_vol_basket({"A": good}, lookback=True)  # bool, not int


def test_inverse_vol_basket_integrates_with_backtester():
    a = [100, 101, 102, 101, 103, 104, 105, 106]
    b = [100, 99, 101, 100, 102, 101, 103, 102]
    pr = inverse_vol_basket({"A": a, "B": b}, lookback=3)
    result = run_backtest(pr, buy_and_hold(len(pr)), fee_rate=0.0, periods_per_year=365)
    assert math.isfinite(result["sharpe"])
    assert math.isfinite(result["max_drawdown"])
