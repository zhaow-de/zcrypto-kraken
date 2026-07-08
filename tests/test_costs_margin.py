import pytest

from cli.costs import CostModelError, margin_carry, margin_rate


def test_margin_rate_lookup():
    assert margin_rate("BTC", band="high") == 0.0002
    assert margin_rate("BTC", band="low") == 0.0001
    assert margin_rate("ETH", band="high") == 0.0004
    assert margin_rate("AVAX", band="low") == 0.0002


@pytest.mark.parametrize("base,band", [("XBT", "high"), ("BTC", "mid"), ("FOO", "low")])
def test_margin_rate_guards(base, band):
    with pytest.raises(CostModelError):
        margin_rate(base, band=band)


@pytest.mark.parametrize(
    "notional,hours,rate,expected",
    [
        (1000, 3, 0.0002, 0.2),  # < 4h -> opening only (floor=0 rollovers)
        (1000, 4, 0.0002, 0.4),  # 1 rollover + opening
        (1000, 24, 0.0002, 1.4),  # floor(24/4)=6 rollovers + opening = 7 units
        (1000, 0, 0.0002, 0.2),  # opening only
        (1000, 120, 0.0002, 6.2),  # 5 days: 30 rollovers + opening = 31 units
    ],
)
def test_margin_carry(notional, hours, rate, expected):
    assert margin_carry(notional, hours, rate) == pytest.approx(expected)


@pytest.mark.parametrize(
    "args",
    [(-1.0, 4, 0.0002), (1000, -4, 0.0002), (1000, 4, -0.0002), (1000, float("inf"), 0.0002), (1000, 4, float("nan"))],
)
def test_margin_carry_guards(args):
    with pytest.raises(CostModelError):
        margin_carry(*args)
