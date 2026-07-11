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


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_trial34_verdict_regression():
    # Registry trial 34 (A1-lf weekly v0.12, adopt, iter-072) reproduced through the ratified kill bar —
    # the regression the spec (docs/specs/00037) names. Construction per the iter-049/069 method.
    import statistics

    from cli.alpha import A1Config, a1_book_returns, a1_kill_bar
    from cli.alpha.a1 import _asset_returns
    from cli.ohlc.dataset import read_parquet
    from cli.registry import TrialRegistry
    from cli.validation import sharpe

    assets = ["ADA", "AVAX", "BTC", "DOGE", "DOT", "ETH", "LINK", "LTC", "SOL", "XRP"]
    frames = {a: read_parquet(DATA_ROOT / a / "EUR" / "1440.parquet") for a in assets}
    union_ts = sorted(set().union(*[set(f["ts"].to_list()) for f in frames.values()]))
    prices = {}
    for a in assets:
        m = dict(zip(frames[a]["ts"].to_list(), frames[a]["close"].to_list()))
        prices[a] = [m.get(t) for t in union_ts]
    n = len(union_ts) - 1
    years = [union_ts[k + 1].year for k in range(n)]
    btc = list(prices["BTC"])
    last = None
    for i in range(len(btc)):
        if btc[i] is None:
            btc[i] = last
        else:
            last = btc[i]
    prices_ff = dict(prices)
    prices_ff["BTC"] = btc
    ret_i = {a: [r if r is not None else 0.0 for r in _asset_returns(prices_ff[a])] for a in assets}

    cfg = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    ap = a1_book_returns(prices_ff, btc, config=cfg)["asset_positions"]
    cadence = 7

    def block_start(k, o):
        return 0 if k < o else o + cadence * ((k - o) // cadence)

    noc_offsets, turn_offsets = [], []
    for o in range(cadence):
        held = {a: [ap[a][block_start(k, o)] for k in range(n)] for a in assets}
        net = [sum(held[a][k] * ret_i[a][k] for a in assets) for k in range(n)]
        turn = [sum(abs(held[a][k] - (held[a][k - 1] if k > 0 else 0.0)) for a in assets) for k in range(n)]
        noc_offsets.append([net[k] - turn[k] * 0.006 for k in range(n)])
        turn_offsets.append(turn)
    book = [statistics.mean(noc_offsets[o][k] for o in range(cadence)) for k in range(n)]
    stress15 = [book[k] - statistics.mean(turn_offsets[o][k] for o in range(cadence)) * 0.003 for k in range(n)]
    bench = build_combined_system(prices).benchmark_net_of_cost

    reg = TrialRegistry(Path(__file__).resolve().parents[1] / "docs" / "reference" / "trial-registry.jsonl")
    pps = [r.metrics["per_period_sharpe"] for r in reg.records if r.family == "A1" and "per_period_sharpe" in r.metrics]
    var_trials = statistics.variance(pps[:32])

    def by_year(series):
        out = {}
        for k in range(n):
            if years[k] in (2013, 2026):
                continue
            out.setdefault(str(years[k]), []).append(series[k])
        return out

    result = a1_kill_bar(
        book,
        bench,
        n_trials=33,
        var_trials=var_trials,
        mean_block=17,
        seed=42,
        cost_stressed_returns=stress15,
        regime_slices=by_year(book),
        benchmark_slices=by_year(bench),
        decisive_start=230,
        n_resamples=2000,
    )
    assert result["passes"] is True  # trial 34's recorded adopt verdict
    assert result["dsr"] > 0.95
    assert result["spa_p_value"] == pytest.approx(0.0070, abs=0.002)
    assert result["worst_slice_pass"] is True
    assert sharpe(book, periods_per_year=365) == pytest.approx(1.3798, abs=0.005)
