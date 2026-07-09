import pytest

from cli.alpha import A1Config, AlphaError


def test_a1config_valid_defaults():
    cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
    assert cfg.gate_window == 200
    assert cfg.vol_lookback == 30
    assert cfg.basket_lookback == 30
    assert cfg.trend_lookbacks == (20, 60, 120)
    assert cfg.short_exposure == 0.5
    assert cfg.short_band == 0.0
    assert cfg.max_leverage == 1.0
    assert cfg.periods_per_year == 365


def test_a1config_is_frozen():
    cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
    with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
        cfg.target_vol = 0.20


@pytest.mark.parametrize("base", ["btc", "BTC_ONLY", "", None, 1])
def test_a1config_bad_base(base):
    with pytest.raises(AlphaError):
        A1Config(base=base, regime="single_gate", short="off", target_vol=0.10)


@pytest.mark.parametrize("regime", ["gate", "", None])
def test_a1config_bad_regime(regime):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime=regime, short="off", target_vol=0.10)


@pytest.mark.parametrize("short", ["bear", "", None])
def test_a1config_bad_short(short):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short=short, target_vol=0.10)


@pytest.mark.parametrize("target_vol", [0.0, -0.1, float("nan"), float("inf"), "x", True])
def test_a1config_bad_target_vol(target_vol):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=target_vol)


@pytest.mark.parametrize("field", ["gate_window", "vol_lookback", "basket_lookback"])
@pytest.mark.parametrize("bad", [1, 1.5, True, "2", 0, -3])
def test_a1config_bad_windows(field, bad):
    kwargs = dict(base="btc_only", regime="single_gate", short="off", target_vol=0.10)
    kwargs[field] = bad
    with pytest.raises(AlphaError):
        A1Config(**kwargs)


@pytest.mark.parametrize("trend_lookbacks", [(), (1,), (2, True), [20, 60], (2.5,)])
def test_a1config_bad_trend_lookbacks(trend_lookbacks):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, trend_lookbacks=trend_lookbacks)


@pytest.mark.parametrize("short_exposure", [0.0, -0.1, 1.1, float("nan"), True])
def test_a1config_bad_short_exposure(short_exposure):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, short_exposure=short_exposure)


@pytest.mark.parametrize("short_band", [-0.1, 1.0, True])
def test_a1config_bad_short_band(short_band):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, short_band=short_band)


def test_a1config_valid_short_band():
    cfg = A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, short_band=0.05)
    assert cfg.short_band == 0.05


@pytest.mark.parametrize("max_leverage", [0.0, -1.0, float("nan"), "x"])
def test_a1config_bad_max_leverage(max_leverage):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, max_leverage=max_leverage)


@pytest.mark.parametrize("periods_per_year", [0, -1, 2.5, True, "x"])
def test_a1config_bad_periods_per_year(periods_per_year):
    with pytest.raises(AlphaError):
        A1Config(base="btc_only", regime="single_gate", short="off", target_vol=0.10, periods_per_year=periods_per_year)
