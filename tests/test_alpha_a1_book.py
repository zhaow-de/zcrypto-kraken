import math

import pytest

from cli.alpha import A1Config, AlphaError, a1_book_returns
from cli.benchmark.strategies import dynamic_inverse_vol_basket, returns_from_prices, sma_gate

BASE_KWARGS = dict(gate_window=20, vol_lookback=20, basket_lookback=20, trend_lookbacks=(5, 10, 20))


def _synthetic_universe(n=150):
    # Three legs (rally / drawdown / recovery) for BTC and a phase-shifted ETH -- guarantees the SMA
    # gate and trend_agreement both flip regimes for real (not a same-signed drift throughout), so
    # every toggle has a genuine chance to engage.
    btc, eth = [], []
    for i in range(n):
        if i < 50:
            btc.append(100.0 * (1.01**i))
        elif i < 100:
            btc.append(btc[49] * (0.99 ** (i - 49)))
        else:
            btc.append(btc[99] * (1.008 ** (i - 99)))
        if i < 60:
            eth.append(50.0 * (1.012**i))
        elif i < 110:
            eth.append(eth[59] * (0.985 ** (i - 59)))
        else:
            eth.append(eth[109] * (1.01 ** (i - 109)))
    return {"BTC": btc, "ETH": eth}, btc


def test_a1_book_returns_no_lookahead():
    # Prices identical through index 99 (100 elements); ETH diverges from index 100 on. A return at
    # period t needs prices[t]/prices[t+1], so only t <= 98 is guaranteed invariant -> [:99].
    n, k_common = 150, 99
    prices_a, btc = _synthetic_universe(n)
    prices_b = {a: list(p) for a, p in prices_a.items()}
    # Anchor the divergent replacement to the actual boundary price (not an unrelated fixed magnitude
    # like 999.0) so the first divergent return isn't an unrealistic multi-hundred-percent jump that
    # would trip run_backtest's degenerate-equity-curve guard -- deviation from the plan's literal
    # fixture, noted in the iter report; the look-ahead property under test is unaffected.
    base_val = prices_b["ETH"][k_common]
    for j in range(k_common + 1, n):
        prices_b["ETH"][j] = base_val * (1 + 0.3 * math.sin(j))
    cfg = A1Config(base="equal_risk_basket", regime="ensemble", short="confirmed_bear", target_vol=0.10, **BASE_KWARGS)
    out_a = a1_book_returns(prices_a, btc, config=cfg)
    out_b = a1_book_returns(prices_b, btc, config=cfg)
    assert out_a["book_base_returns"][:k_common] == out_b["book_base_returns"][:k_common]
    assert out_a["net_returns"][:k_common] == out_b["net_returns"][:k_common]


def test_a1_book_returns_toggles_engage():
    prices, btc = _synthetic_universe(150)
    cfg_btc = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    cfg_basket = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    cfg_ensemble = A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.10, **BASE_KWARGS)
    cfg_short = A1Config(base="equal_risk_basket", regime="single_gate", short="confirmed_bear", target_vol=0.10, **BASE_KWARGS)
    cfg_vol12 = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.12, **BASE_KWARGS)

    r_btc = a1_book_returns(prices, btc, config=cfg_btc)
    r_basket = a1_book_returns(prices, btc, config=cfg_basket)
    r_ensemble = a1_book_returns(prices, btc, config=cfg_ensemble)
    r_short = a1_book_returns(prices, btc, config=cfg_short)
    r_vol12 = a1_book_returns(prices, btc, config=cfg_vol12)

    assert r_btc["net_returns"] != r_basket["net_returns"]  # base toggle engages
    assert r_basket["net_returns"] != r_ensemble["net_returns"]  # regime toggle engages
    assert r_basket["net_returns"] != r_short["net_returns"]  # short toggle engages
    assert r_basket["net_returns"] != r_vol12["net_returns"]  # vol_target toggle engages


def test_a1_book_returns_reduces_to_gated_btc():
    prices, btc = _synthetic_universe(150)
    cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    out = a1_book_returns(prices, btc, config=cfg)
    gate = sma_gate(btc, window=20)
    ret = returns_from_prices(btc)
    expected = [g * r for g, r in zip(gate, ret)]
    assert out["book_base_returns"] == pytest.approx(expected)


def test_a1_book_returns_reduces_to_basket_when_always_long():
    # A strictly rising BTC keeps sma_gate at 1.0 for every post-warmup period (all-long, single_gate,
    # short=off) -> every present asset's direction is +1.0, so the weighted directional book
    # collapses to the plain dynamic_inverse_vol_basket over those gate-on periods -- an end-to-end
    # cross-check (through the public API) that the inline weights match the reviewed basket.
    n = 100
    btc = [100.0 * (1.01**i) for i in range(n)]
    eth = [50.0 * (1.008**i) * (1 + 0.02 * math.sin(i / 3)) for i in range(n)]
    prices = {"BTC": btc, "ETH": eth}
    cfg = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    out = a1_book_returns(prices, btc, config=cfg)
    basket = dynamic_inverse_vol_basket(prices, lookback=20)
    gate = sma_gate(btc, window=20)
    for k in range(len(basket)):
        if gate[k] == 1.0:
            assert out["book_base_returns"][k] == pytest.approx(basket[k], abs=1e-9)


def test_a1_book_returns_planted_signal_positive_sharpe():
    prices, btc = _synthetic_universe(150)
    cfg = A1Config(base="equal_risk_basket", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    out = a1_book_returns(prices, btc, config=cfg)
    assert out["metrics"]["sharpe"] > 0


def test_a1_book_returns_guards():
    prices, btc = _synthetic_universe(150)
    cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, **BASE_KWARGS)
    with pytest.raises(AlphaError):
        a1_book_returns(prices, btc, config="not a config")
    with pytest.raises(AlphaError):
        a1_book_returns({"ETH": prices["ETH"]}, btc, config=cfg)  # missing BTC
    with pytest.raises(AlphaError):
        a1_book_returns({"BTC": btc, "ETH": prices["ETH"][:-1]}, btc, config=cfg)  # unequal lengths
    with pytest.raises(AlphaError):
        a1_book_returns(prices, btc[:-1], config=cfg)  # btc_prices wrong length
    gapped = {"BTC": [None] + btc[1:], "ETH": prices["ETH"]}
    with pytest.raises(AlphaError):
        a1_book_returns(gapped, btc, config=cfg)  # BTC must have full coverage
