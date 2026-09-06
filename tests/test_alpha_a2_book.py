import math

import pytest

from cli.alpha import A1Config, A2Config, AlphaError, a1_book_returns, a2_book_returns
from cli.alpha.a1 import _asset_returns
from cli.benchmark.strategies import returns_from_prices

BASE_KWARGS = dict(vol_lookback=20, basket_lookback=20)


def _synthetic_universe(n=260):
    # Three legs per asset (trend / chop / drawdown), phase-shifted across BTC/ETH/SOL so each asset's
    # own Donchian breakouts and inverse-vol qualification windows land at different periods -- every
    # toggle (lookbacks/short/target_vol) gets a genuine chance to engage, and the multi-asset ensemble
    # is exercised rather than degenerating to a single-asset book.
    btc, eth, sol = [], [], []
    for i in range(n):
        if i < 90:
            btc.append(100.0 * (1.012**i))
        elif i < 170:
            btc.append(btc[89] * (1 + 0.01 * math.sin(i / 3.0)))
        else:
            btc.append(btc[169] * (0.99 ** (i - 169)))
        if i < 100:
            eth.append(50.0 * (1.01**i))
        elif i < 180:
            eth.append(eth[99] * (1 + 0.012 * math.sin(i / 4.0 + 1)))
        else:
            eth.append(eth[179] * (0.988 ** (i - 179)))
        if i < 70:
            sol.append(20.0 * (1.015**i))
        elif i < 160:
            sol.append(sol[69] * (1 + 0.015 * math.sin(i / 5.0 + 2)))
        else:
            sol.append(sol[159] * (0.985 ** (i - 159)))
    return {"BTC": btc, "ETH": eth, "SOL": sol}


def _synthetic_universe_with_absent_asset(n=260):
    # _synthetic_universe plus ALT: absent (None) for a leading pre-listing stretch and dropping one
    # mid-series point. BTC stays gap-free, which `_validate_prices_by_asset` requires; the mode this
    # fixture answers is the union calendar's per-asset cost model, which the gap-free one cannot.
    universe = _synthetic_universe(n)
    listing_at = 40
    gap_at = 150
    alt: list[float | None] = [None] * listing_at
    alt.append(15.0)
    for i in range(listing_at + 1, n):
        alt.append(alt[-1] * (1 + 0.02 * math.sin(i / 6.0 + 3)))
    alt[gap_at] = None
    universe["ALT"] = alt
    return universe


def _mean_turnover(asset_positions: dict[str, list[float]]) -> float:
    n = len(next(iter(asset_positions.values())))
    prev = {asset: 0.0 for asset in asset_positions}
    total = 0.0
    for k in range(n):
        step = 0.0
        for asset, positions in asset_positions.items():
            step += abs(positions[k] - prev[asset])
            prev[asset] = positions[k]
        total += step
    return total / n


def test_a2_book_returns_no_lookahead():
    # Prices identical through index 199 (200 elements); SOL diverges from index 200 on. A return at
    # period t needs prices[t]/prices[t+1], so only t <= 198 is guaranteed invariant -> [:199].
    n, k_common = 260, 199
    prices_a = _synthetic_universe(n)
    prices_b = {a: list(p) for a, p in prices_a.items()}
    # Anchor the divergent replacement to the actual boundary price (not an unrelated fixed magnitude)
    # so run_backtest's degenerate-equity-curve guard isn't tripped by an unrealistic jump -- same
    # deviation as test_a1_book_returns_no_lookahead, noted there and here.
    base_val = prices_b["SOL"][k_common]
    for j in range(k_common + 1, n):
        prices_b["SOL"][j] = base_val * (1 + 0.3 * math.sin(j))
    cfg = A2Config(lookbacks=(10, 20, 40), short="on", target_vol=0.10, **BASE_KWARGS)
    out_a = a2_book_returns(prices_a, config=cfg)
    out_b = a2_book_returns(prices_b, config=cfg)
    assert out_a["net_returns"][:k_common] == out_b["net_returns"][:k_common]
    for asset in prices_a:
        assert out_a["asset_positions"][asset][:k_common] == out_b["asset_positions"][asset][:k_common]


def test_a2_book_returns_no_lookahead_with_absent_asset():
    # Sibling of test_a2_book_returns_no_lookahead, run on the absent-asset universe so the book-level
    # no-look-ahead property is checked in the presence of a pre-listing gap + a mid-series gap, not
    # just the gap-free BTC/ETH/SOL universe.
    n, k_common = 260, 199
    prices_a = _synthetic_universe_with_absent_asset(n)
    prices_b = {a: list(p) for a, p in prices_a.items()}
    base_val = prices_b["SOL"][k_common]
    for j in range(k_common + 1, n):
        prices_b["SOL"][j] = base_val * (1 + 0.3 * math.sin(j))
    cfg = A2Config(lookbacks=(10, 20, 40), short="on", target_vol=0.10, **BASE_KWARGS)
    out_a = a2_book_returns(prices_a, config=cfg)
    out_b = a2_book_returns(prices_b, config=cfg)
    assert out_a["net_returns"][:k_common] == out_b["net_returns"][:k_common]
    for asset in prices_a:
        assert out_a["asset_positions"][asset][:k_common] == out_b["asset_positions"][asset][:k_common]


def test_a2_book_returns_asset_positions_reconstruct_net_returns():
    prices = _synthetic_universe(260)
    cfg = A2Config(lookbacks=(10, 20, 40), short="on", target_vol=0.10, **BASE_KWARGS)
    out = a2_book_returns(prices, config=cfg)
    rets = {asset: returns_from_prices(p) for asset, p in prices.items()}
    for k in range(len(out["net_returns"])):
        reconstructed = sum(out["asset_positions"][asset][k] * rets[asset][k] for asset in prices)
        assert reconstructed == pytest.approx(out["net_returns"][k], abs=1e-9)


def test_a2_book_returns_reconstruct_identity_with_absent_asset():
    # The identity must hold with ret_i[k] treated as 0.0 wherever it is None, which the gap-free
    # sibling never exercises. `returns_from_prices` refuses a None-containing series, so the
    # reference returns come from `_asset_returns` -- the helper `a2_book_returns` itself uses.
    prices = _synthetic_universe_with_absent_asset(260)
    cfg = A2Config(lookbacks=(10, 20, 40), short="on", target_vol=0.10, **BASE_KWARGS)
    out = a2_book_returns(prices, config=cfg)
    rets = {asset: _asset_returns(p) for asset, p in prices.items()}
    for k in range(len(out["net_returns"])):
        reconstructed = sum(out["asset_positions"][asset][k] * (rets[asset][k] or 0.0) for asset in prices)
        assert reconstructed == pytest.approx(out["net_returns"][k], abs=1e-9)
    # No phantom exposure: wherever ALT's own return is None (pre-listing or the mid-series gap), its
    # book position must be exactly 0.0, not just close to it.
    for k in range(len(rets["ALT"])):
        if rets["ALT"][k] is None:
            assert out["asset_positions"]["ALT"][k] == 0.0


def test_a2_book_returns_toggles_engage():
    prices = _synthetic_universe(260)
    cfg_fast = A2Config(lookbacks=(10, 20, 40), short="off", target_vol=0.10, **BASE_KWARGS)
    cfg_slow = A2Config(lookbacks=(20, 50, 100), short="off", target_vol=0.10, **BASE_KWARGS)
    cfg_short = A2Config(lookbacks=(10, 20, 40), short="on", target_vol=0.10, **BASE_KWARGS)
    cfg_vol12 = A2Config(lookbacks=(10, 20, 40), short="off", target_vol=0.12, **BASE_KWARGS)

    r_fast = a2_book_returns(prices, config=cfg_fast)
    r_slow = a2_book_returns(prices, config=cfg_slow)
    r_short = a2_book_returns(prices, config=cfg_short)
    r_vol12 = a2_book_returns(prices, config=cfg_vol12)

    assert r_fast["net_returns"] != r_slow["net_returns"]  # lookbacks toggle engages
    assert r_fast["net_returns"] != r_short["net_returns"]  # short toggle engages
    assert r_fast["net_returns"] != r_vol12["net_returns"]  # target_vol toggle engages

    assert any(v < 0.0 for positions in r_short["asset_positions"].values() for v in positions)
    assert all(v >= 0.0 for positions in r_fast["asset_positions"].values() for v in positions)


A2_LOOKBACK = 20


def test_a2_turnover_below_a1_at_matched_horizon():
    """At a matched horizon (A2 lookback == A1 gate_window) the Donchian hold churns less than the
    SMA-gate flip, because a position persists until the opposite channel breaks instead of flipping
    on every gate crossing. It does NOT generalize: A1 at a longer gate_window turns over less than
    A2 does here, so which book is cheaper in production is a question for the real-data run."""
    prices = _synthetic_universe(260)
    cfg_a2 = A2Config(lookbacks=(A2_LOOKBACK,), short="off", target_vol=0.10, **BASE_KWARGS)
    out_a2 = a2_book_returns(prices, config=cfg_a2)

    cfg_a1 = A1Config(
        base="equal_risk_basket",
        regime="single_gate",
        short="off",
        target_vol=0.10,
        gate_window=A2_LOOKBACK,
        **BASE_KWARGS,
    )
    # Matched-horizon precondition, asserted in code so the test can't silently drift into comparing
    # A2 against an unmatched A1 gate_window.
    assert cfg_a1.gate_window == A2_LOOKBACK
    out_a1 = a1_book_returns(prices, prices["BTC"], config=cfg_a1)

    a2_turnover = _mean_turnover(out_a2["asset_positions"])
    a1_turnover = _mean_turnover(out_a1["asset_positions"])
    assert a2_turnover < a1_turnover, f"A2 turnover {a2_turnover} not below A1 turnover {a1_turnover}"


def test_a2_book_returns_planted_signal_positive_sharpe():
    n = 150
    btc = [100.0 * (1.01**i) for i in range(n)]
    eth = [50.0 * (1.008**i) * (1 + 0.02 * math.sin(i / 3)) for i in range(n)]
    sol = [20.0 * (1.009**i) * (1 + 0.02 * math.sin(i / 4 + 1)) for i in range(n)]
    prices = {"BTC": btc, "ETH": eth, "SOL": sol}
    cfg = A2Config(lookbacks=(10, 20, 40), short="off", target_vol=0.10, **BASE_KWARGS)
    out = a2_book_returns(prices, config=cfg)
    assert out["metrics"]["sharpe"] > 0


def test_a2_book_returns_guards():
    prices = _synthetic_universe(150)
    cfg = A2Config(lookbacks=(10, 20, 40), short="off", target_vol=0.10, **BASE_KWARGS)
    with pytest.raises(AlphaError):
        a2_book_returns(prices, config="not a config")
    with pytest.raises(AlphaError):
        a2_book_returns({"ETH": prices["ETH"]}, config=cfg)  # missing BTC
    with pytest.raises(AlphaError):
        a2_book_returns({"BTC": prices["BTC"], "ETH": prices["ETH"][:-1]}, config=cfg)  # unequal lengths
    with pytest.raises(AlphaError):
        a2_book_returns({"BTC": [-1.0] + prices["BTC"][1:], "ETH": prices["ETH"]}, config=cfg)  # non-positive price
    gapped = {"BTC": [None] + prices["BTC"][1:], "ETH": prices["ETH"]}
    with pytest.raises(AlphaError):
        a2_book_returns(gapped, config=cfg)  # BTC must have full coverage
