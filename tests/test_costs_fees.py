import pytest

from cli.costs import CostModelError, round_trip_fee, spot_fee_rates


@pytest.mark.parametrize(
    "vol,tier,maker,taker",
    [
        (0, 1, 0.0040, 0.0080),
        (2_499, 1, 0.0040, 0.0080),
        (2_500, 2, 0.0030, 0.0060),
        (9_999, 2, 0.0030, 0.0060),
        (10_000, 3, 0.0022, 0.0038),
        (25_000, 4, 0.0020, 0.0035),
        (1e12, 17, 0.0000, 0.0005),
    ],
)
def test_spot_fee_rates(vol, tier, maker, taker):
    r = spot_fee_rates(vol)
    assert r == {"tier": tier, "maker": maker, "taker": taker}


def test_spot_fee_rates_monotonic():
    vols = [0, 2_500, 10_000, 25_000, 50_000, 100_000, 1_000_000, 10_000_000, 1e12]
    makers = [spot_fee_rates(v)["maker"] for v in vols]
    takers = [spot_fee_rates(v)["taker"] for v in vols]
    assert makers == sorted(makers, reverse=True)
    assert takers == sorted(takers, reverse=True)


@pytest.mark.parametrize("vol", [-1.0, float("nan"), float("inf")])
def test_spot_fee_rates_guards(vol):
    with pytest.raises(CostModelError):
        spot_fee_rates(vol)


def test_round_trip_fee_maker_taker_mixed():
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080) == pytest.approx(8.0)
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080, taker_open=True, taker_close=True) == pytest.approx(16.0)
    assert round_trip_fee(1000, maker_rate=0.0040, taker_rate=0.0080, taker_close=True) == pytest.approx(12.0)


@pytest.mark.parametrize(
    "notional,kwargs",
    [
        (-1.0, {"maker_rate": 0.004, "taker_rate": 0.008}),
        (1000, {"maker_rate": -0.004, "taker_rate": 0.008}),
        (1000, {"maker_rate": 0.004, "taker_rate": float("nan")}),
    ],
)
def test_round_trip_fee_guards(notional, kwargs):
    with pytest.raises(CostModelError):
        round_trip_fee(notional, **kwargs)
