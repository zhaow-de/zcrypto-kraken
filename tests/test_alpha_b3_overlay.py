import copy

import pytest

from cli.alpha.b3_overlay import btc_short_state, overlay_short, with_btc_short
from cli.alpha.b4 import quote_shortfall, shortfall_carry
from cli.alpha.errors import AlphaError

# On a 4-close SMA with trend agreement over 2 and 3 closes: the close at 3 above its SMA with its trend down, at 5 on its
# SMA, at 6 and 7 below it with the trend down — 7 within a band of 0.1 of it — and at 8 below it with the trend split.
_BTC = [20.0, 19.0, 5.0, 15.0, 16.0, 12.0, 8.0, 11.0, 9.0, 11.0, 12.0, 13.0]
_STATE = [False] * 6 + [True] * 2 + [False] * 3
_BOOK = {
    "BTC": [0.125, 0.25, 0.0, 0.375],
    "ETH": [0.25, 0.0, 0.0, 0.125],
    "SOL": [0.125, 0.25, 0.0, 0.0],
    "XRP": [-0.0625, 0.0, 0.0, 0.0],
}


@pytest.mark.parametrize(
    ("band", "state"),
    [
        pytest.param(0.0, _STATE, id="band-0"),
        pytest.param(0.1, [False] * 6 + [True] + [False] * 4, id="band-0.1-drops-the-close-within-it"),
    ],
)
def test_the_state_holds_where_btc_closes_below_its_sma_by_the_band_and_its_trend_agreement_is_negative(band, state):
    assert btc_short_state(_BTC, window=4, band=band, lookbacks=(2, 3)) == state


def test_the_state_at_a_close_reads_no_later_close():
    full = btc_short_state(_BTC, window=4, band=0.0, lookbacks=(2, 3))
    for cut in range(1, len(_BTC)):
        planted = _BTC[:cut] + [100.0] * (len(_BTC) - cut)
        assert btc_short_state(planted, window=4, band=0.0, lookbacks=(2, 3))[:cut] == full[:cut]


@pytest.mark.parametrize(
    ("window", "band", "match"),
    [
        pytest.param(1, 0.0, "window must be an int >= 2", id="window-1"),
        pytest.param(4, -0.01, "band must be a number in", id="band-below-0"),
        pytest.param(4, 1.0, "band must be a number in", id="band-1"),
        pytest.param(4, False, "band must be a number in", id="band-a-bool"),
        pytest.param(4, "0.1", "band must be a number in", id="band-a-string"),
    ],
)
def test_btc_short_state_refuses_a_window_or_band_a1_would_refuse(window, band, match):
    with pytest.raises(AlphaError, match=match):
        btc_short_state(_BTC, window=window, band=band, lookbacks=(2, 3))


def test_the_short_is_the_fraction_of_the_books_long_gross_where_the_state_holds_and_0_elsewhere():
    # Long gross 0.5, 0.5, 0.0 and 0.5, XRP's short not counted; the state holds at 0, 2 and 3, the book flat at 2.
    assert overlay_short(_BOOK, [True, False, True, True], fraction=0.5) == [0.25, 0.0, 0.0, 0.25]
    assert overlay_short(_BOOK, [True, False, True, True], fraction=0.25) == [0.125, 0.0, 0.0, 0.125]


@pytest.mark.parametrize(
    ("fraction", "state", "match"),
    [
        pytest.param(0, [True] * 4, "fraction must be a number in", id="fraction-0"),
        pytest.param(0.51, [True] * 4, "fraction must be a number in", id="fraction-above-half"),
        pytest.param("0.5", [True] * 4, "fraction must be a number in", id="fraction-a-string"),
        pytest.param(0.5, [True] * 3, "3 states for positions of 4 return indices", id="a-state-short"),
    ],
)
def test_overlay_short_refuses_a_fraction_above_half_or_a_state_of_another_length(fraction, state, match):
    with pytest.raises(AlphaError, match=match):
        overlay_short(_BOOK, state, fraction=fraction)


def test_the_short_is_netted_against_the_books_btc_and_no_alt_is_shorted():
    unchanged = copy.deepcopy(_BOOK)

    borrowed = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=True)
    held = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=False)

    assert borrowed == _BOOK | {"BTC": [-0.125, 0.25, 0.0, 0.125]}
    assert held == _BOOK | {"BTC": [0.0, 0.25, 0.0, 0.125]}
    assert _BOOK == unchanged and all(borrowed[a] is not _BOOK[a] and held[a] is not _BOOK[a] for a in _BOOK)


def test_only_the_btc_the_book_does_not_hold_is_borrowed_and_carried():
    borrowed = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=True)
    held = with_btc_short(_BOOK, [0.25, 0.0, 0.0, 0.25], borrow=False)

    # At 0 the short outweighs the book's 0.125 of BTC by 0.125; at 3 the book's 0.375 covers it.
    assert quote_shortfall(borrowed, "BTC") == [0.125, 0.0, 0.0, 0.0]
    assert shortfall_carry(quote_shortfall(borrowed, "BTC"), rate=0.0002) == [0.0002 * 0.25, 0.0, 0.0, 0.0]
    assert quote_shortfall(held, "BTC") == [0.0] * 4


@pytest.mark.parametrize(
    ("book", "short", "match"),
    [
        pytest.param({a: v for a, v in _BOOK.items() if a != "BTC"}, [0.0] * 4, "the book holds no BTC", id="no-btc"),
        pytest.param(_BOOK, [0.0] * 3, "3 shorts for positions of another length", id="a-short-short"),
    ],
)
def test_with_btc_short_refuses_a_book_without_btc_or_a_short_of_another_length(book, short, match):
    with pytest.raises(AlphaError, match=match):
        with_btc_short(book, short, borrow=True)
