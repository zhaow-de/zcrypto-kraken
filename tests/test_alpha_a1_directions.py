import math

from cli.alpha.a1 import A1Config, _asset_directions, _map_to_union_index

BTC_PRICES = [100.0, 110.0, 90.0, 130.0, 60.0, 200.0]
# sma_gate(window=2): warm-up k=0 -> 0; k=1: mean([100,110])=105, 110>105 -> 1;
# k=2: mean([110,90])=100, 90 not>100 -> 0; k=3: mean([90,130])=110, 130>110 -> 1;
# k=4: mean([130,60])=95, 60 not>95 -> 0.  g_btc = [0,1,0,1,0].
# trend_agreement(lookbacks=[2]) = sign(momentum(lookback=2)): k=0,1 warm-up -> 0;
# k=2: 90/100-1=-0.10 -> -1; k=3: 130/110-1=+0.18 -> +1; k=4: 60/90-1=-0.33 -> -1.
# ta = [0,0,-1,1,-1].


def _cfg(*, regime, short):
    return A1Config(base="btc_only", regime=regime, short=short, target_vol=0.10, gate_window=2, trend_lookbacks=(2,))


def _btc_only():
    union_ts = list(range(6))
    return {"BTC": list(BTC_PRICES)}, list(BTC_PRICES), union_ts, {"BTC": union_ts}


def test_asset_directions_known_answer_single_gate_short_off():
    prices, btc, union_ts, asset_ts = _btc_only()
    d = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
    assert d["BTC"] == [0.0, 1.0, 0.0, 1.0, 0.0]


def test_asset_directions_ensemble_differs_from_single_gate():
    # At k=1 the gate is on but ta[1]==0 (still warm-up), so ensemble's AND-with-trend drops it to flat
    # while single_gate stays long.
    prices, btc, union_ts, asset_ts = _btc_only()
    single = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
    ensemble = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="ensemble", short="off"))
    assert single["BTC"][1] == 1.0
    assert ensemble["BTC"][1] == 0.0
    assert single["BTC"] != ensemble["BTC"]


def test_asset_directions_confirmed_bear_short_engages():
    # gate==0 & ta<0 at k=2 and k=4 -> confirmed_bear shorts there; short=off stays flat there.
    prices, btc, union_ts, asset_ts = _btc_only()
    off = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="off"))
    bear = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="single_gate", short="confirmed_bear"))
    assert off["BTC"] == [0.0, 1.0, 0.0, 1.0, 0.0]
    assert bear["BTC"] == [0.0, 1.0, -0.5, 1.0, -0.5]
    assert bear["BTC"][1] == 1.0 and bear["BTC"][3] == 1.0  # never short while gate==1


def test_asset_directions_ensemble_confirmed_bear_combo():
    prices, btc, union_ts, asset_ts = _btc_only()
    d = _asset_directions(prices, btc, union_ts, asset_ts, config=_cfg(regime="ensemble", short="confirmed_bear"))
    assert d["BTC"] == [0.0, 0.0, -0.5, 1.0, -0.5]


def test_asset_directions_short_band_narrows_short_set():
    # Uptrend, then a mild pullback (~3.5% below the recent SMA each step, inside a 10% band) before a
    # ~15%/step drawdown (well outside it): at short_band=0.0 the pullback already qualifies as
    # confirmed-bear (price < SMA), at 0.10 it does not (price stays above SMA*0.90), so the banded run
    # shorts in fewer periods (spec 00031 finding 2).
    btc = [100.0]
    for _ in range(10):
        btc.append(btc[-1] * 1.02)
    for i in range(10):
        btc.append(btc[-1] * (0.965 if i % 2 == 0 else 1.01))
    for _ in range(6):
        btc.append(btc[-1] * 0.85)
    union_ts = list(range(len(btc)))
    prices = {"BTC": btc}
    asset_ts = {"BTC": union_ts}

    def _band_cfg(short_band):
        return A1Config(
            base="btc_only",
            regime="single_gate",
            short="confirmed_bear",
            target_vol=0.10,
            gate_window=5,
            trend_lookbacks=(2,),
            short_band=short_band,
        )

    no_band = _asset_directions(prices, btc, union_ts, asset_ts, config=_band_cfg(0.0))
    banded = _asset_directions(prices, btc, union_ts, asset_ts, config=_band_cfg(0.10))

    count_no_band = sum(1 for d in no_band["BTC"] if d == -0.5)
    count_banded = sum(1 for d in banded["BTC"] if d == -0.5)
    assert count_banded < count_no_band


def test_map_to_union_index_gap_and_adjacency():
    # Day 13 is missing from own_ts but present in union_ts (some OTHER asset has it): transitions
    # touching it map to None, and the own-adjacent 12->14 move must not be read as a union move either.
    own_ts = [10, 11, 12, 14, 15, 16]
    own_values = [1.0, 2.0, 3.0, 4.0, 5.0]
    union_ts = [10, 11, 12, 13, 14, 15, 16]
    mapped = _map_to_union_index(own_ts, own_values, union_ts)
    assert mapped == [1.0, 2.0, None, None, 4.0, 5.0]


def test_asset_directions_absent_asset_is_none():
    btc = [100.0, 105.0, 102.0, 108.0, 103.0, 110.0, 107.0, 115.0]
    alt = [50.0, 51.0, 52.0, None, 54.0, 55.0, 56.0, 57.0]
    union_ts = list(range(8))
    asset_ts = {"BTC": union_ts, "ALT": [0, 1, 2, 4, 5, 6, 7]}
    cfg = A1Config(
        base="equal_risk_basket",
        regime="single_gate",
        short="off",
        target_vol=0.10,
        gate_window=2,
        trend_lookbacks=(2,),
    )
    d = _asset_directions({"BTC": btc, "ALT": alt}, btc, union_ts, asset_ts, config=cfg)
    assert d["ALT"][2] is None and d["ALT"][3] is None
    for k in (0, 1, 4, 5, 6):
        assert d["ALT"][k] is not None and math.isfinite(d["ALT"][k])


def test_asset_directions_no_lookahead():
    # A direction at union period t reads prices[t+1] for presence plus causal features of prices[<=t],
    # so only t <= 3 is invariant to a divergence starting at index 5 -- t=4 already reads prices[5].
    btc_base = [100.0, 108.0, 96.0, 121.0, 70.0]
    btc_1 = btc_base + [200.0, 90.0, 250.0]
    btc_2 = btc_base + [40.0, 500.0, 12.0]
    union_ts = list(range(8))
    asset_ts = {"BTC": union_ts}
    cfg = A1Config(base="btc_only", regime="ensemble", short="confirmed_bear", target_vol=0.10, gate_window=2, trend_lookbacks=(2,))
    d1 = _asset_directions({"BTC": btc_1}, btc_1, union_ts, asset_ts, config=cfg)
    d2 = _asset_directions({"BTC": btc_2}, btc_2, union_ts, asset_ts, config=cfg)
    assert d1["BTC"][:4] == d2["BTC"][:4]
