import math
from pathlib import Path

import pytest

from cli.portfolio import CombinedSystemConfig, CombinedSystemResult, PortfolioError, build_combined_system
from cli.risk import GovernorConfig

# Small-window config so ~40 synthetic bars exercise every stage (defaults need 200+ bars).
SMALL = dict(basket_lookback=3, gate_window=5, vol_lookback=3)
# Overlay-disabling knobs: a cap that can never clip and a governor whose rules cannot fire.
NO_CAP = dict(long_cap=100.0, short_cap=100.0)
NO_GOV = GovernorConfig(daily_loss_limit=0.9, ladder=((0.95, 0.5),))


def rising_prices(n: int, *, start: float, step: float, wobble: float = 0.0) -> list[float]:
    # Deterministic gently-rising series; wobble keeps realized vol > 0 without randomness.
    return [start * (1 + step) ** k * (1 + wobble * math.sin(k)) for k in range(n)]


def three_assets(n: int = 40) -> dict[str, list[float]]:
    return {
        "AAA": rising_prices(n, start=100.0, step=0.004, wobble=0.01),
        "BBB": rising_prices(n, start=50.0, step=0.003, wobble=0.02),
        "CCC": rising_prices(n, start=10.0, step=0.005, wobble=0.015),
    }


def test_result_shape_and_identities():
    res = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    assert isinstance(res, CombinedSystemResult)
    n = res.n_periods
    assert n == 39  # len(prices) - 1
    for series in (res.net_of_cost, res.benchmark_net_of_cost, res.capped_net_of_cost, res.multipliers):
        assert len(series) == n
    assert set(res.positions) == {"AAA", "BBB", "CCC"}
    assert res.net_of_cost == res.governor.governed_returns
    # positions are the capped book scaled by the multiplier stream: where mult == 0.0 the position
    # is exactly 0.0; everywhere the position respects the cap scaled by the multiplier.
    for a, series in res.positions.items():
        assert len(series) == n
        for k in range(n):
            if res.multipliers[k] == 0.0:
                assert series[k] == 0.0
            else:
                assert series[k] <= 0.20 * res.multipliers[k] + 1e-12
    res2 = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    assert res2.positions == res.positions  # deterministic


def test_disable_degeneracy_overlays_compose_to_identity():
    cfg = CombinedSystemConfig(**SMALL, **NO_CAP, governor=NO_GOV)
    res = build_combined_system(three_assets(), config=cfg)
    assert res.cap_breach_bars == 0
    assert res.multipliers == [1.0] * res.n_periods
    for k in range(res.n_periods):
        assert res.net_of_cost[k] == pytest.approx(res.benchmark_net_of_cost[k], rel=1e-9, abs=1e-12)


def test_cap_engages_on_concentration():
    # One near-zero-vol asset draws ~all inverse-vol weight -> pre-cap position >> 0.20.
    prices = {
        "CALM": rising_prices(40, start=100.0, step=0.0001, wobble=0.0002),
        "WILD": rising_prices(40, start=100.0, step=0.004, wobble=0.06),
    }
    res = build_combined_system(prices, config=CombinedSystemConfig(**SMALL))
    assert res.cap_breach_bars > 0
    assert max(max(s) for s in res.positions.values()) <= 0.20 + 1e-12


def test_warmup_flat():
    res = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    for a in res.positions:
        assert all(p == 0.0 for p in res.positions[a][:3])  # gate warm-up (window 5 -> k < 4 flat, first 3 certainly)


def test_no_lookahead():
    base = build_combined_system(three_assets(), config=CombinedSystemConfig(**SMALL))
    prices = three_assets()
    prices["AAA"][-1] *= 1.5
    pert = build_combined_system(prices, config=CombinedSystemConfig(**SMALL))
    n = base.n_periods
    for a in base.positions:
        assert pert.positions[a][: n - 1] == base.positions[a][: n - 1]


@pytest.mark.parametrize(
    "prices,kwargs",
    [
        ({}, {}),
        ("not a dict", {}),
        (None, {}),
        ({"AAA": [100.0, 101.0] * 20}, {"spot_fee_per_side": 0.0}),
        ({"AAA": [100.0, 101.0] * 20}, {"spot_fee_per_side": float("nan")}),
        ({"AAA": [100.0, 101.0] * 20}, {"target_vol_annual": -0.1}),
        ({"AAA": [100.0, 101.0] * 20}, {"periods_per_year": 0}),
    ],
)
def test_invalid_inputs(prices, kwargs):
    with pytest.raises(PortfolioError):
        build_combined_system(prices, config=CombinedSystemConfig(**SMALL, **kwargs))


DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_frozen_figures_regression():
    # Registry record 33's figures, reproduced through the committed pipeline (the drivers' QA gates, made permanent).
    from cli.ohlc.dataset import read_parquet
    from cli.validation import sharpe

    assets = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
    frames = {a: read_parquet(DATA_ROOT / a / "EUR" / "1440.parquet") for a in assets}
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in assets:
        m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
        prices[a] = [m.get(t) for t in union_ts]
    res = build_combined_system(prices)

    def max_dd(rs):
        eq, peak, dd = 1.0, 1.0, 0.0
        for r in rs:
            eq *= 1 + r
            peak = max(peak, eq)
            dd = max(dd, 1 - eq / peak)
        return dd

    assert sharpe(res.net_of_cost, periods_per_year=365) == pytest.approx(1.3263, abs=0.005)
    assert max_dd(res.net_of_cost) == pytest.approx(0.1449, abs=0.003)
    assert sharpe(res.benchmark_net_of_cost, periods_per_year=365) == pytest.approx(1.2455, abs=0.005)
    assert res.cap_breach_bars == 100
    assert res.governor.rung_bars == {1.0: 2476, 0.5: 1711, 0.25: 394}
