import copy
import math
from datetime import UTC, datetime

import pytest

from cli.alpha.b4 import (
    base_exposures,
    borrow_unavailable,
    limit_factors,
    per_year_counts,
    per_year_means,
    per_year_sums,
    quote_shortfall,
    ratio_eur_returns,
    scale_bars,
    shortfall_carry,
)
from cli.alpha.errors import AlphaError
from cli.portfolio.crossfreq_system import apply_whole_book_limits

_LEGS = {"ETH/BTC": ("ETH", "BTC"), "SOL/BTC": ("SOL", "BTC")}


def test_a_ratio_legs_eur_return_is_the_bases_return_less_the_quotes():
    eth = [100.0, 110.0, 99.0, 120.0, 132.0, 126.0]
    btc = [50.0, 52.0, 60.0, 54.0, 48.0, 50.0]
    ratio = [e / b for e, b in zip(eth, btc)]
    ratio[3] = None

    got = ratio_eur_returns(ratio, btc)

    assert [k for k, r in enumerate(got) if r is None] == [2, 3]
    for k in (0, 1, 4):
        assert math.isclose(0.3 * got[k], 0.3 * (eth[k + 1] / eth[k] - btc[k + 1] / btc[k]), rel_tol=1e-12, abs_tol=1e-15)


@pytest.mark.parametrize(
    ("ratio", "quote", "match"),
    [
        pytest.param([0.5, 0.0, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-ratio-close-of-0"),
        pytest.param([0.5, -0.5, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-negative-ratio-close"),
        pytest.param([0.5, math.nan, 0.5], [1.0, 1.0, 1.0], "the ratio's closes", id="a-nan-ratio-close"),
        pytest.param([0.5, 0.5, 0.5], [1.0, None, 1.0], "the quote's EUR closes", id="a-missing-quote-close"),
        pytest.param([0.5, 0.5, 0.5], [1.0, 0.0, 1.0], "the quote's EUR closes", id="a-quote-close-of-0"),
        pytest.param([0.5, 0.5, 0.5], [1.0, math.inf, 1.0], "the quote's EUR closes", id="an-infinite-quote-close"),
        pytest.param([0.5, 0.5], [1.0, 1.0, 1.0], "equal in number", id="unequal-lengths"),
    ],
)
def test_ratio_eur_returns_refuses_a_close_it_cannot_divide_by(ratio, quote, match):
    with pytest.raises(AlphaError, match=match):
        ratio_eur_returns(ratio, quote)


def test_base_exposures_nets_each_leg_into_its_base_and_its_quote():
    book = {"BTC": [0.5, 0.125, 0.0], "ETH": [0.25, 0.0, 0.0], "SOL": [0.0, 0.25, 0.0]}
    legs = {"ETH/BTC": [0.125, 0.25, 0.0], "SOL/BTC": [0.0625, 0.0, 0.0]}
    positions = book | legs
    unchanged = copy.deepcopy(positions)

    assert base_exposures(positions, _LEGS) == {
        "BTC": [0.3125, -0.125, 0.0],
        "ETH": [0.375, 0.25, 0.0],
        "SOL": [0.0625, 0.25, 0.0],
    }
    assert positions == unchanged
    assert base_exposures(book, _LEGS) == book


@pytest.mark.parametrize(
    ("positions", "match"),
    [
        pytest.param({"BTC": [0.5], "ETH": [0.5], "ETH/BTC": [0.25]}, "SOL/BTC's base SOL", id="a-legs-base-absent"),
        pytest.param({"ETH": [0.5], "SOL": [0.5], "ETH/BTC": [0.25]}, "ETH/BTC's base ETH and quote BTC", id="the-quote-absent"),
        pytest.param({"BTC": [0.5, 0.5], "ETH": [0.5], "SOL": [0.5]}, "equal in number", id="unequal-lengths"),
    ],
)
def test_base_exposures_refuses_a_book_it_cannot_decompose(positions, match):
    with pytest.raises(AlphaError, match=match):
        base_exposures(positions, _LEGS)


def test_limit_factors_leave_an_untouched_bar_at_one_and_engage_each_limit_in_its_order():
    exposures = {
        "BTC": [0.5, 1.0, 0.5, -0.5, -0.9],
        "ETH": [0.25, 0.5, 0.375, 0.5, 1.05],
        "SOL": [0.0, 0.5, 0.375, 0.5, 1.05],
    }

    factors, engaged = limit_factors(exposures)

    assert factors[0] == 1.0
    for got, want in zip(factors[1:], (0.5, 0.8, 0.7, 0.5 * 1.4 / 1.95)):
        assert math.isclose(got, want, rel_tol=1e-12)
    assert engaged == {
        "gross": [False, True, False, False, True],
        "net": [False, True, True, False, False],
        "margin": [False, False, False, True, True],
    }
    scaled, stack = scale_bars(exposures, factors), apply_whole_book_limits(exposures)
    assert [scaled[a][0] for a in exposures] == [exposures[a][0] for a in exposures]
    assert all(math.isclose(scaled[a][k], stack[a][k], rel_tol=1e-12) for a in exposures for k in range(5))


def test_scale_bars_refuses_factors_of_another_length_than_the_positions():
    with pytest.raises(AlphaError, match="factors for positions of another length"):
        scale_bars({"BTC": [0.5, 0.5], "ETH": [0.25, 0.25]}, [1.0])


def test_the_shortfall_and_its_carry_charge_each_rollover_and_each_increase():
    exposures = {"BTC": [0.25, -0.5, -0.25, -0.75, 0.0], "ETH": [0.5] * 5}

    shortfall = quote_shortfall(exposures, "BTC")

    assert shortfall == [0.0, 0.5, 0.25, 0.75, 0.0]
    assert shortfall_carry(shortfall, rate=0.0002) == [0.0, 0.0002 * 1.0, 0.0002 * 0.25, 0.0002 * 1.25, 0.0]
    assert shortfall_carry([0.5, 0.5], rate=0.0002) == [0.0002 * 1.0, 0.0002 * 0.5]


@pytest.mark.parametrize("rate", [-0.0002, math.nan], ids=["negative", "nan"])
def test_shortfall_carry_refuses_a_rate_it_cannot_charge(rate):
    with pytest.raises(AlphaError, match="rate must be"):
        shortfall_carry([0.5], rate=rate)


def test_borrow_unavailable_holds_the_legs_short_to_the_books_own_quote():
    book = {"BTC": [0.5, 0.25, 0.0, 0.5, 0.5], "ETH": [0.125] * 5, "SOL": [0.0] * 5}
    legs = {"ETH/BTC": [0.25, 0.25, 0.25, 0.0, 0.125], "SOL/BTC": [0.25, 0.25, 0.0, 0.0, 0.125]}

    held = borrow_unavailable(book | legs, _LEGS, "BTC")

    assert held == book | {"ETH/BTC": [0.25, 0.125, 0.0, 0.0, 0.125], "SOL/BTC": [0.25, 0.125, 0.0, 0.0, 0.125]}
    assert quote_shortfall(base_exposures(held, _LEGS), "BTC") == [0.0] * 5
    assert quote_shortfall(base_exposures(book | legs, _LEGS), "BTC") == [0.0, 0.25, 0.25, 0.0, 0.0]


def test_borrow_unavailable_refuses_a_book_without_the_quote():
    with pytest.raises(AlphaError, match="holds no BTC instrument"):
        borrow_unavailable({"ETH": [0.5], "ETH/BTC": [0.25]}, _LEGS, "BTC")


_CLOSES = [datetime(2015, 12, 31, 16, tzinfo=UTC), datetime(2015, 12, 31, 20, tzinfo=UTC), datetime(2016, 1, 1, tzinfo=UTC)]


def test_the_per_year_helpers_key_each_value_by_its_close_year():
    assert per_year_counts([False, False, True], _CLOSES) == {"2015": 0, "2016": 1}
    assert per_year_sums([0.25, 0.5, 2.0], _CLOSES) == {"2015": 0.75, "2016": 2.0}
    assert per_year_means([0.25, 0.5, 2.0], _CLOSES) == {"2015": 0.375, "2016": 2.0}


@pytest.mark.parametrize(
    ("helper", "values"),
    [(per_year_counts, [True, False]), (per_year_sums, [0.5, 0.5]), (per_year_means, [0.5, 0.5])],
    ids=["counts", "sums", "means"],
)
def test_the_per_year_helpers_refuse_values_and_closes_of_unequal_length(helper, values):
    with pytest.raises(AlphaError, match="for 3 closes"):
        helper(values, _CLOSES)
