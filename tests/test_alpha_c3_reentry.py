import math
import statistics

import pytest

from cli.alpha.a1 import A1Config
from cli.alpha.c3 import a1_daily_positions
from cli.alpha.c3_reentry import SLEEVE, full_long_positions, reentry_fires
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

ASSETS = CrossfreqSystemConfig().assets
N = 150
# Every close moves the five assets at even places by _move(k) and the five at odd places by twice it, so the calm ones
# weigh 2/15 each and the wild ones 1/15, and the equal-risk basket moves by 4/3 of _move(k).
CALM, WILD = ASSETS[0::2], ASSETS[1::2]


def _move(k: int) -> float:
    return (0.01 + 0.0001 * k) * (1 if k % 2 == 0 else -1)


def _prices(n: int = N) -> dict[str, list[float | None]]:
    prices = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(n - 1):
            closes.append(closes[-1] * (1 + (2 if asset in WILD else 1) * _move(k)))
        prices[asset] = closes
    return prices


def _own_daily(weight: float) -> list[float]:
    """The size before the cadence, by hand."""
    target = 0.12 / math.sqrt(365)
    basket = [0.0 if t < 30 else 4 / 3 * _move(t) for t in range(N)]
    daily = []
    for t in range(N):
        deviation = statistics.stdev(basket[t - 30 : t]) if t >= 30 else 0.0
        daily.append(weight * min(target / deviation, 1.0) if deviation > 0 else 0.0)
    return daily


def _block_start(k: int, offset: int) -> int:
    return 0 if k < offset else offset + 7 * ((k - offset) // 7)


def test_the_sleeve_is_records_44s_and_47s_configuration():
    assert SLEEVE == A1Config(base="equal_risk_basket", regime="ensemble", short="off", target_vol=0.12)
    assert (SLEEVE.basket_lookback, SLEEVE.vol_lookback, SLEEVE.periods_per_year, SLEEVE.max_leverage) == (30, 30, 365, 1.0)


def test_the_size_is_the_inverse_vol_weight_times_the_baskets_vol_target_through_the_seven_block_starts():
    size = full_long_positions(_prices())
    assert tuple(size) == ASSETS and {len(rows) for rows in size.values()} == {N}
    for assets, weight in ((CALM, 2 / 15), (WILD, 1 / 15)):
        daily = _own_daily(weight)
        expected = [statistics.mean(daily[_block_start(k, o)] for o in range(7)) for k in range(N)]
        for asset in assets:
            assert size[asset] == pytest.approx(expected, rel=1e-9, abs=1e-15), asset
    # The cap binds on the first sized rows, whose 30 basket returns are nearly all the warm-up's zeros, and not later.
    assert _own_daily(2 / 15)[31] == 2 / 15 and 0 < _own_daily(2 / 15)[100] < 0.5 * 2 / 15


def test_the_size_is_the_sleeves_own_position_once_it_has_been_long_in_every_asset_through_its_windows():
    # Every asset climbs on an alternating step of its own size, so the sleeve turns long in all ten; from row 240 every
    # block start's 30 base returns are a fully long book's, the basket's own.
    prices = {}
    for i, asset in enumerate(ASSETS):
        closes = [10.0 * (i + 1)]
        for k in range(299):
            closes.append(closes[-1] * (1.004 + 0.003 * (1 + i / 10) * (1 if k % 2 == 0 else -1)))
        prices[asset] = closes
    sleeve, size = a1_daily_positions(prices), full_long_positions(prices)
    for asset in ASSETS:
        assert sleeve[asset][150] == 0 < size[asset][150]
        assert all(p > 0 for p in sleeve[asset][240:])
        assert size[asset][240:] == pytest.approx(sleeve[asset][240:], rel=1e-9)


@pytest.mark.parametrize("cut", [61, 97, 149])
def test_a_row_of_the_size_reads_no_later_close(cut):
    prices = _prices()
    planted = {a: closes[:cut] + [3 * c for c in closes[cut:]] for a, closes in prices.items()}
    whole, moved = full_long_positions(prices), full_long_positions(planted)
    assert all(moved[a][:cut] == whole[a][:cut] for a in ASSETS)
    assert all(moved[a][cut:] != whole[a][cut:] for a in ASSETS)


def test_an_asset_the_basket_does_not_weight_yet_takes_no_size():
    prices = _prices()
    prices["SOL"] = [None] * 40 + prices["SOL"][40:]
    size = full_long_positions(prices)
    # SOL's first return is at row 40, so its first 30-return window ends at row 70.
    assert set(size["SOL"][:70]) == {0.0} and all(s > 0 for s in size["SOL"][70:])
    assert all(size[a][69] > 0 for a in ASSETS if a != "SOL")


def test_btc_is_sized_across_a_missing_close_on_its_forward_fill():
    prices = _prices()
    prices["BTC"][100] = None
    size = full_long_positions(prices)
    assert all(s > 0 for s in size["BTC"][100:137])


def test_the_size_refuses_an_order_other_than_the_builders():
    prices = _prices()
    reordered = {"BTC": prices["BTC"], **{a: closes for a, closes in prices.items() if a != "BTC"}}
    with pytest.raises(ValueError) as refused:
        full_long_positions(reordered)
    assert str(ASSETS) in str(refused.value) and str(tuple(reordered)) in str(refused.value)


def test_an_event_is_a_flat_close_under_the_low_band():
    band = ["low", "low", "low", "mid", "high", None, "low"]
    states = {
        "BTC": ["flat", "long", None, "flat", "flat", "flat", "flat"],
        "ETH": ["long", "flat", "flat", "flat", "long", None, None],
    }
    assert reentry_fires(band, states) == {
        "BTC": [True, False, False, False, False, False, True],
        "ETH": [False, True, True, False, False, False, False],
    }
