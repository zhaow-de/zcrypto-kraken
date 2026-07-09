import pytest

from cli.alpha import AlphaError
from cli.alpha.a2 import A2Config, _asset_directions_a2, _donchian_signal

# window=3: warm-up k=0,1 (k < window-1=2) -> 0.0.
# k=2: window=prices[0:3]=[100,101,102], hi=102,lo=100,p=102 -> pos=1.0 -> NEW HIGH, held=+1.
# k=3: window=[101,102,101.5], hi=102,lo=101,p=101.5 -> pos=2*(0.5/1)-1=0.0 -> interior, HOLD +1.
# k=4: window=[102,101.5,101.8], hi=102,lo=101.5,p=101.8 -> pos=2*(0.3/0.5)-1=0.2 -> interior, HOLD +1.
# k=5: window=[101.5,101.8,101.6], hi=101.8,lo=101.5,p=101.6 -> pos=2*(0.1/0.3)-1=-1/3 -> interior, HOLD +1.
# k=6: window=[101.8,101.6,95], hi=101.8,lo=95,p=95 -> pos=-1.0 -> NEW LOW, held=-1.
# k=7: window=[101.6,95,94], hi=101.6,lo=94,p=94 -> pos=-1.0 -> NEW LOW again, held stays -1.
HOLD_PRICES = [100.0, 101.0, 102.0, 101.5, 101.8, 101.6, 95.0, 94.0, 93.0]
HOLD_SIGNAL = [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, -1.0, -1.0]


def test_donchian_signal_known_answer_holds_across_drift():
    # The whole point of A2: the signal HOLDS +1 across the sideways drift (k=3,4,5) between the
    # break-high (k=2) and the break-low (k=6) -- it must not go flat just because cp isn't at an
    # extreme every period.
    assert _donchian_signal(HOLD_PRICES, window=3, band=1.0) == HOLD_SIGNAL


def test_donchian_signal_band_fires_exactly_at_new_high():
    # k=2: cp=0.714 (close to, but not, a new max) -> must NOT fire. k=3: cp=1.0 (genuine new max
    # over the trailing window) -> fires +1 exactly there, not one step early or late.
    prices = [98.0, 105.0, 104.0, 110.0, 111.0]
    assert _donchian_signal(prices, window=3, band=1.0) == [0.0, 0.0, 0.0, 1.0]


def test_donchian_signal_no_lookahead():
    prices_a = list(HOLD_PRICES)
    prices_b = list(HOLD_PRICES)
    k_common = 6
    for j in range(k_common + 1, len(prices_b)):
        prices_b[j] = prices_b[j] * 7.3 + 40.0  # unrelated divergent tail
    sig_a = _donchian_signal(prices_a, window=3, band=1.0)
    sig_b = _donchian_signal(prices_b, window=3, band=1.0)
    # k_common itself is invariant too: sig[k_common] only reads cp[k_common], which only reads
    # prices[<= k_common] -- so the bound extends through k_common inclusive, not just up to it.
    # A 1-step peek (reading cp[k+1] instead of cp[k]) first corrupts exactly this index, so leaving
    # it unchecked would make this test blind to the most likely real bug.
    assert sig_a[: k_common + 1] == sig_b[: k_common + 1]


def _cfg(*, lookbacks=(3,), short="off", band=1.0, short_exposure=0.5):
    return A2Config(lookbacks=lookbacks, short=short, target_vol=0.10, band=band, short_exposure=short_exposure)


def test_asset_directions_a2_ensemble_is_mean_of_signals():
    # window=2 breaks down to -1 at k=6 (a twitchy fast lookback) while window=5 is still holding +1
    # from its own earlier breakout at k=4 (the mild dip at k=6 doesn't break the 5-bar low) ->
    # ensemble mean(-1, +1) == 0.0 at k=6, demonstrating d_i[k] == mean over lookbacks.
    prices = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 108.0, 107.0]
    union_ts = list(range(len(prices)))
    asset_ts = {"BTC": union_ts}
    cfg = _cfg(lookbacks=(2, 5))
    d = _asset_directions_a2({"BTC": prices}, union_ts, asset_ts, config=cfg)
    assert d["BTC"][6] == pytest.approx(0.0, abs=1e-12)


def test_asset_directions_a2_short_toggle():
    union_ts = list(range(len(HOLD_PRICES)))
    asset_ts = {"BTC": union_ts}
    off = _asset_directions_a2({"BTC": HOLD_PRICES}, union_ts, asset_ts, config=_cfg(short="off"))
    on = _asset_directions_a2({"BTC": HOLD_PRICES}, union_ts, asset_ts, config=_cfg(short="on"))
    # short="off": ensemble negative periods (k=6,7, where the raw signal is -1.0) are clipped to 0.
    assert off["BTC"] == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0]
    assert all(v >= 0.0 for v in off["BTC"])
    # short="on": the negative part is scaled by short_exposure -> -1.0 * 0.5 == -0.5, not a naked -1.0.
    assert on["BTC"] == [0.0, 0.0, 1.0, 1.0, 1.0, 1.0, -0.5, -0.5]


def test_asset_directions_a2_no_lookahead():
    prices_a = list(HOLD_PRICES)
    prices_b = list(HOLD_PRICES)
    k_common = 6
    for j in range(k_common + 1, len(prices_b)):
        prices_b[j] = prices_b[j] * 5.1 + 12.0
    union_ts = list(range(len(HOLD_PRICES)))
    asset_ts = {"BTC": union_ts}
    cfg = _cfg()
    d_a = _asset_directions_a2({"BTC": prices_a}, union_ts, asset_ts, config=cfg)
    d_b = _asset_directions_a2({"BTC": prices_b}, union_ts, asset_ts, config=cfg)
    # k_common itself is invariant too: direction[k_common] only reads prices[<= k_common] (via
    # _donchian_signal / channel_position), so the bound extends through k_common inclusive -- same
    # reasoning as _donchian_signal's own no-look-ahead test.
    assert d_a["BTC"][: k_common + 1] == d_b["BTC"][: k_common + 1]


def test_asset_directions_a2_union_none_and_warmup():
    # ALT is absent (None) only at union index 4 -> the two transitions touching it (k=3, k=4) must
    # be None; every other ALT transition stays a real (non-None) float. BTC at k=0 is present but
    # still warming up (before its first break) -> 0.0, not None.
    btc = list(HOLD_PRICES)
    alt = list(HOLD_PRICES)
    alt[4] = None
    union_ts = list(range(len(HOLD_PRICES)))
    asset_ts = {"BTC": union_ts, "ALT": [k for k in union_ts if alt[k] is not None]}
    cfg = _cfg()
    d = _asset_directions_a2({"BTC": btc, "ALT": alt}, union_ts, asset_ts, config=cfg)
    assert d["ALT"][3] is None
    assert d["ALT"][4] is None
    for k in (0, 1, 2, 5, 6, 7):
        assert d["ALT"][k] is not None
    assert d["BTC"][0] == 0.0


@pytest.mark.parametrize("lookbacks", [(), (2, "x"), (2, 1), (2, True)])
def test_a2config_bad_lookbacks(lookbacks):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=lookbacks, short="off", target_vol=0.10)


@pytest.mark.parametrize("band", [0.0, -0.1, 1.1, float("nan"), True])
def test_a2config_bad_band(band):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=0.10, band=band)


@pytest.mark.parametrize("short", ["confirmed_bear", "", None])
def test_a2config_bad_short(short):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short=short, target_vol=0.10)


@pytest.mark.parametrize("target_vol", [0.0, -0.1, float("nan"), float("inf")])
def test_a2config_bad_target_vol(target_vol):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=target_vol)


@pytest.mark.parametrize("vol_lookback", [1, 0, -5, 2.5, True])
def test_a2config_bad_vol_lookback(vol_lookback):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=0.10, vol_lookback=vol_lookback)


@pytest.mark.parametrize("basket_lookback", [1, 0, -5, 2.5, True])
def test_a2config_bad_basket_lookback(basket_lookback):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=0.10, basket_lookback=basket_lookback)


@pytest.mark.parametrize("max_leverage", [0.0, -0.1, float("nan"), float("inf")])
def test_a2config_bad_max_leverage(max_leverage):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=0.10, max_leverage=max_leverage)


@pytest.mark.parametrize("periods_per_year", [0, -1, 2.5, True])
def test_a2config_bad_periods_per_year(periods_per_year):
    with pytest.raises(AlphaError):
        A2Config(lookbacks=(20,), short="off", target_vol=0.10, periods_per_year=periods_per_year)


def test_a2config_valid_defaults():
    cfg = A2Config(lookbacks=(10, 20, 40), short="off", target_vol=0.10)
    assert cfg.band == 1.0
    assert cfg.short_exposure == 0.5
    assert cfg.vol_lookback == 30
    assert cfg.basket_lookback == 30
    assert cfg.max_leverage == 1.0
    assert cfg.periods_per_year == 365
