from decimal import Decimal

import pytest

from cli.capture.book import OrderBook
from cli.capture.errors import CaptureError

# Kraken's own worked example from the WS v2 book-checksum guide
# (https://docs.kraken.com/api/docs/guides/spot-ws-book-v2): top-10 bids/asks for a BTC/USD book
# and its documented checksum.
_KRAKEN_BIDS = [
    {"price": "45283.5", "qty": "0.10000000"},
    {"price": "45283.4", "qty": "1.54582015"},
    {"price": "45282.1", "qty": "0.10000000"},
    {"price": "45281.0", "qty": "0.10000000"},
    {"price": "45280.3", "qty": "1.54592586"},
    {"price": "45279.0", "qty": "0.07990000"},
    {"price": "45277.6", "qty": "0.03310103"},
    {"price": "45277.5", "qty": "0.30000000"},
    {"price": "45277.3", "qty": "1.54602737"},
    {"price": "45276.6", "qty": "0.15445238"},
]
_KRAKEN_ASKS = [
    {"price": "45285.2", "qty": "0.00100000"},
    {"price": "45286.4", "qty": "1.54571953"},
    {"price": "45286.6", "qty": "1.54571109"},
    {"price": "45289.6", "qty": "1.54560911"},
    {"price": "45290.2", "qty": "0.15890660"},
    {"price": "45291.8", "qty": "1.54553491"},
    {"price": "45294.7", "qty": "0.04454749"},
    {"price": "45296.1", "qty": "0.35380000"},
    {"price": "45297.5", "qty": "0.09945542"},
    {"price": "45299.5", "qty": "0.18772827"},
]
_KRAKEN_CHECKSUM = 3310070434


def _decimal_levels(levels):
    return [{"price": Decimal(level["price"]), "qty": Decimal(level["qty"])} for level in levels]


def _snapshot(bids=_KRAKEN_BIDS, asks=_KRAKEN_ASKS, checksum=_KRAKEN_CHECKSUM):
    return {"bids": _decimal_levels(bids), "asks": _decimal_levels(asks), "checksum": checksum}


def test_checksum_matches_kraken_documented_example():
    book = OrderBook("BTC/USD", depth=10)
    book.bids = {Decimal(b["price"]): Decimal(b["qty"]) for b in _KRAKEN_BIDS}
    book.asks = {Decimal(a["price"]): Decimal(a["qty"]) for a in _KRAKEN_ASKS}
    assert book.checksum() == _KRAKEN_CHECKSUM


def test_ingest_snapshot_with_correct_checksum_is_in_sync():
    book = OrderBook("BTC/USD", depth=10)
    ok = book.ingest_snapshot(_snapshot())
    assert ok is True
    assert book.desynced is False


def test_ingest_snapshot_with_wrong_checksum_marks_desynced():
    book = OrderBook("BTC/USD", depth=10)
    ok = book.ingest_snapshot(_snapshot(checksum=1))
    assert ok is False
    assert book.desynced is True


def test_ingest_update_recovers_from_desync_once_checksum_matches_again():
    book = OrderBook("BTC/USD", depth=10)
    book.ingest_snapshot(_snapshot(checksum=1))
    assert book.desynced is True
    # A no-op update (no bid/ask changes) should reproduce the same, now-correct checksum.
    ok = book.ingest_update({"bids": [], "asks": [], "checksum": _KRAKEN_CHECKSUM})
    assert ok is True
    assert book.desynced is False


def test_ingest_update_with_corrupted_checksum_is_detected():
    book = OrderBook("BTC/USD", depth=10)
    book.ingest_snapshot(_snapshot())
    assert book.desynced is False
    # Change a qty without updating checksum to match -> corrupted/desynced.
    ok = book.ingest_update(
        {
            "bids": [{"price": Decimal("45283.5"), "qty": Decimal("999.0")}],
            "asks": [],
            "checksum": _KRAKEN_CHECKSUM,
        }
    )
    assert ok is False
    assert book.desynced is True


def test_qty_zero_removes_the_price_level():
    book = OrderBook("BTC/USD", depth=10)
    book.ingest_snapshot(_snapshot())
    assert Decimal("45283.5") in book.bids
    book._apply_side(book.bids, [{"price": Decimal("45283.5"), "qty": Decimal("0")}])
    assert Decimal("45283.5") not in book.bids


def test_checksum_ignores_levels_beyond_top_10():
    book = OrderBook("BTC/USD", depth=10)
    book.bids = {Decimal(b["price"]): Decimal(b["qty"]) for b in _KRAKEN_BIDS}
    book.asks = {Decimal(a["price"]): Decimal(a["qty"]) for a in _KRAKEN_ASKS}
    baseline = book.checksum()
    # An 11th bid, priced below all existing top-10 bids, must not affect the checksum.
    book.bids[Decimal("40000.0")] = Decimal("1.0")
    assert book.checksum() == baseline == _KRAKEN_CHECKSUM


def test_format_level_strips_decimal_point_and_leading_zeros():
    from cli.capture.book import _format_level

    assert _format_level(Decimal("0.00100000")) == "100000"
    assert _format_level(Decimal("45283.5")) == "452835"
    assert _format_level(Decimal("0.30000000")) == "30000000"
    assert _format_level(Decimal("0")) == "0"


def test_missing_price_raises_capture_error():
    book = OrderBook("BTC/USD", depth=10)
    with pytest.raises(CaptureError):
        book.ingest_snapshot({"bids": [{"qty": Decimal("1")}], "asks": [], "checksum": 0})


def test_non_decimal_value_raises_capture_error():
    book = OrderBook("BTC/USD", depth=10)
    with pytest.raises(CaptureError):
        book.ingest_snapshot({"bids": [{"price": "not-a-number", "qty": "1"}], "asks": [], "checksum": 0})


# --- T0008: the book must stay congruent with Kraken's depth window ---------------------------
#
# Kraken only sends deltas for levels INSIDE the subscribed depth-N window: a level retained beyond
# it goes stale, and re-enters our top-10 as a PHANTOM when the window shifts back -- checksum fails.


def test_book_never_exceeds_its_subscribed_depth():
    book = OrderBook("BTC/USD", depth=2)
    book.ingest_snapshot(
        {
            "bids": [],
            "asks": [
                {"price": Decimal("100.0"), "qty": Decimal("1")},
                {"price": Decimal("101.0"), "qty": Decimal("1")},
            ],
            "checksum": 0,
        }
    )
    # Two better asks arrive. Kraken's window is now {98.0, 99.0}; 100.0/101.0 have fallen out of
    # it, and Kraken will never mention them again.
    book.ingest_update(
        {
            "bids": [],
            "asks": [
                {"price": Decimal("99.0"), "qty": Decimal("1")},
                {"price": Decimal("98.0"), "qty": Decimal("1")},
            ],
            "checksum": 0,
        }
    )
    assert len(book.asks) <= 2
    assert set(book.asks) == {Decimal("98.0"), Decimal("99.0")}


def test_a_level_pushed_out_of_the_window_cannot_re_enter_as_a_phantom():
    """The exact live failure: a stale out-of-window level resurfacing in the top of book."""
    book = OrderBook("BTC/USD", depth=2)
    book.ingest_snapshot(
        {
            "bids": [],
            "asks": [
                {"price": Decimal("100.0"), "qty": Decimal("1")},
                {"price": Decimal("101.0"), "qty": Decimal("1")},
            ],
            "checksum": 0,
        }
    )
    # A better ask enters -> Kraken's window becomes {99.5, 100.0}; 101.0 drops out of it.
    book.ingest_update({"bids": [], "asks": [{"price": Decimal("99.5"), "qty": Decimal("1")}], "checksum": 0})
    # While 101.0 sits OUTSIDE the window it is cancelled in the real book, and Kraken never tells
    # us. Now 99.5 is consumed and the window back-fills with 102.0: a book that kept stale 101.0
    # would report {100.0, 101.0} -- a phantom top of book.
    book.ingest_update(
        {
            "bids": [],
            "asks": [
                {"price": Decimal("99.5"), "qty": Decimal("0")},
                {"price": Decimal("102.0"), "qty": Decimal("1")},
            ],
            "checksum": 0,
        }
    )
    assert set(book.asks) == {Decimal("100.0"), Decimal("102.0")}, (
        "a level pushed out of the depth window went stale and resurfaced in the top of book"
    )
