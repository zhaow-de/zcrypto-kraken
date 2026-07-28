"""TDD for `cli/panel/primitives.py` -- the pure 1s L2 panel primitive math (spec 00052 D2).

All values here are hand-computed from the book fixtures per the exact formulas in spec 00052 D2:
microprice = (ask_qty*bid + bid_qty*ask)/(bid_qty+ask_qty); imbalance_l1 = bid_qty/(bid_qty+ask_qty);
fill_bps walks price-ordered levels (asks ascending for a buy, bids descending for a sell)
accumulating price*qty EUR until the notional is filled (partial last level), then compares the
resulting VWAP ("effective" price) to mid in bps -- None if the visible side is too shallow.
"""

from __future__ import annotations

from decimal import Decimal

import polars as pl
import pytest

from cli.panel.primitives import NOTIONALS_EUR, PANEL_SCHEMA, sample_row

# --- schema / constants -----------------------------------------------------------------------------

_EXPECTED_COLUMNS = {
    "ts",
    "updates",
    "stale_seconds",  # T0104: seconds since the last applied message; null = unknown
    "spread",
    "spread_bps",
    "mid",
    "microprice",
    "imbalance_l1",
    "fill_bps_bid_100",
    "fill_bps_ask_100",
    "fill_bps_bid_1k",
    "fill_bps_ask_1k",
    "fill_bps_bid_10k",
    "fill_bps_ask_10k",
    "depth_qty_bid_l1",
    "depth_qty_bid_l5",
    "depth_qty_bid_l10",
    "depth_qty_ask_l1",
    "depth_qty_ask_l5",
    "depth_qty_ask_l10",
}


def test_panel_schema_columns_and_types():
    assert set(PANEL_SCHEMA) == _EXPECTED_COLUMNS
    assert PANEL_SCHEMA["ts"] == pl.Datetime("us", "UTC")
    assert PANEL_SCHEMA["updates"] == pl.Int64
    for col in _EXPECTED_COLUMNS - {"ts", "updates"}:
        assert PANEL_SCHEMA[col] == pl.Float64, col


def test_notionals_eur():
    assert NOTIONALS_EUR == (100.0, 1_000.0, 10_000.0)


# --- sample_row: basic values (hand-computed) + K > available levels --------------------------------


def test_sample_row_basic_values_and_shallow_depth_levels():
    # best bid = 100 (max key), best ask = 101 (min key); bid_qty=2, ask_qty=1.
    bids = {Decimal("100"): Decimal("2"), Decimal("99"): Decimal("3")}
    asks = {Decimal("101"): Decimal("1"), Decimal("102"): Decimal("4")}

    row = sample_row(bids, asks, updates=5)

    assert row is not None
    assert set(row) == _EXPECTED_COLUMNS - {"ts"}
    assert row["updates"] == 5
    assert isinstance(row["updates"], int)
    assert isinstance(row["spread"], float)  # Decimal inputs -> float outputs
    assert row["spread"] == pytest.approx(101.0 - 100.0)
    assert row["mid"] == pytest.approx((100.0 + 101.0) / 2)
    assert row["spread_bps"] == pytest.approx((101.0 - 100.0) / 100.5 * 1e4)
    assert row["microprice"] == pytest.approx((1 * 100.0 + 2 * 101.0) / (2 + 1))
    assert row["imbalance_l1"] == pytest.approx(2 / (2 + 1))
    # only 2 price levels per side exist -> K=5 and K=10 both fall back to summing everything.
    assert row["depth_qty_bid_l1"] == pytest.approx(2.0)
    assert row["depth_qty_bid_l5"] == pytest.approx(2.0 + 3.0)
    assert row["depth_qty_bid_l10"] == pytest.approx(2.0 + 3.0)
    assert row["depth_qty_ask_l1"] == pytest.approx(1.0)
    assert row["depth_qty_ask_l5"] == pytest.approx(1.0 + 4.0)
    assert row["depth_qty_ask_l10"] == pytest.approx(1.0 + 4.0)


# --- fill_bps: exact single-level (partial) fill on both sides --------------------------------------


def test_fill_bps_single_level_partial_fill_both_sides():
    # One level per side -- also covers K > available levels (K=1/5/10 all equal the single level).
    bids = {Decimal("100"): Decimal("10")}
    asks = {Decimal("101"): Decimal("10")}
    mid = (100.0 + 101.0) / 2  # 100.5

    row = sample_row(bids, asks, updates=0)

    assert row is not None
    # buy €100: ask level notional = 101*10 = 1010 >= 100 -> only a fraction of the level is eaten;
    # effective = 100 / (100/101) = 101 (the level's own price, since it's a partial single-level fill).
    expected_ask_100 = (101.0 - mid) / mid * 1e4
    assert row["fill_bps_ask_100"] == pytest.approx(expected_ask_100)
    # sell €100: bid level notional = 100*10 = 1000 >= 100 -> effective = 100 / (100/100) = 100.
    expected_bid_100 = (mid - 100.0) / mid * 1e4
    assert row["fill_bps_bid_100"] == pytest.approx(expected_bid_100)
    for side in ("bid", "ask"):
        for level in ("l1", "l5", "l10"):
            assert row[f"depth_qty_{side}_{level}"] == pytest.approx(10.0)


# --- fill_bps: multi-level walk crossing 2 levels with a partial last level --------------------------


def test_fill_bps_multi_level_walk_with_partial_last_level():
    # Buy €1,000 walking the ask side: level1 (100x2=200) and level2 (101x3=303) are fully consumed
    # (503 total), leaving 497 to eat from level3 (200x100=20000, deep) -- a partial fill of level3.
    asks = {Decimal("100"): Decimal("2"), Decimal("101"): Decimal("3"), Decimal("200"): Decimal("100")}
    bids = {Decimal("99"): Decimal("50")}
    mid = (99.0 + 100.0) / 2  # 99.5

    row = sample_row(bids, asks, updates=0)

    assert row is not None
    remaining_after_two_levels = 1_000.0 - (100.0 * 2) - (101.0 * 3)  # 497.0
    base_qty = 2.0 + 3.0 + remaining_after_two_levels / 200.0
    effective = 1_000.0 / base_qty
    expected = (effective - mid) / mid * 1e4
    assert row["fill_bps_ask_1k"] == pytest.approx(expected)
    # K > available (only 3 ask levels) -> l5/l10 both sum all three.
    assert row["depth_qty_ask_l5"] == pytest.approx(2.0 + 3.0 + 100.0)
    assert row["depth_qty_ask_l10"] == pytest.approx(2.0 + 3.0 + 100.0)


# --- fill_bps: shallow book -> None at 10k but numeric at 100 ----------------------------------------


def test_fill_bps_none_when_side_too_shallow_but_numeric_at_smaller_notional():
    # Ask side: total visible notional = 100*1 + 101*2 = 302 -- covers 100, falls short of 1k and 10k.
    asks = {Decimal("100"): Decimal("1"), Decimal("101"): Decimal("2")}
    # Bid side: deep enough (99*200=19,800 EUR) to fill even the 10k rung, for contrast.
    bids = {Decimal("99"): Decimal("200")}
    mid = (99.0 + 100.0) / 2  # 99.5

    row = sample_row(bids, asks, updates=0)

    assert row is not None
    # notional=100 exactly equals level1's own notional (100*1) -> fully "filled", not None.
    assert row["fill_bps_ask_100"] == pytest.approx((100.0 - mid) / mid * 1e4)
    assert row["fill_bps_ask_1k"] is None
    assert row["fill_bps_ask_10k"] is None
    # the deep bid side fills all three rungs -- a single-price book, so effective == price exactly.
    assert row["fill_bps_bid_100"] == pytest.approx((mid - 99.0) / mid * 1e4)
    assert row["fill_bps_bid_1k"] == pytest.approx((mid - 99.0) / mid * 1e4)
    assert row["fill_bps_bid_10k"] == pytest.approx((mid - 99.0) / mid * 1e4)


# --- sample_row: empty side -> None (no quotable market that second) --------------------------------


@pytest.mark.parametrize(
    "bids,asks",
    [
        ({}, {Decimal("101"): Decimal("1")}),
        ({Decimal("100"): Decimal("1")}, {}),
        ({}, {}),
    ],
    ids=["empty_bids", "empty_asks", "both_empty"],
)
def test_sample_row_empty_side_returns_none(bids, asks):
    assert sample_row(bids, asks, updates=0) is None


# --- sample_row: crossed/locked book still computes honestly -----------------------------------------


@pytest.mark.parametrize(
    "bid_price,ask_price,expected_spread",
    [(101.0, 100.0, -1.0), (100.0, 100.0, 0.0)],
    ids=["crossed", "locked"],
)
def test_sample_row_crossed_or_locked_book_computes_spread_honestly(bid_price, ask_price, expected_spread):
    bids = {Decimal(str(bid_price)): Decimal("2")}
    asks = {Decimal(str(ask_price)): Decimal("3")}

    row = sample_row(bids, asks, updates=0)

    assert row is not None
    assert row["spread"] == pytest.approx(expected_spread)
    assert row["spread_bps"] == pytest.approx(expected_spread / row["mid"] * 1e4)


def test_fill_bps_bid_multi_level_walk_with_partial():
    # Review minor #2 (f7a2e4d review): the multi-level partial walk tested directly on the BID
    # side (a sell). Bids 100x2, 99x3, 98x200; asks 101x1 -> mid = 100.5. Selling EUR 1000 consumes
    # 100*2=200, 99*3=297, then a partial 503/98 base at 98.
    bids = {Decimal("100"): Decimal("2"), Decimal("99"): Decimal("3"), Decimal("98"): Decimal("200")}
    asks = {Decimal("101"): Decimal("1")}
    row = sample_row(bids, asks, updates=1)
    assert row is not None
    mid = (100.0 + 101.0) / 2
    base_consumed = 2.0 + 3.0 + 503.0 / 98.0
    effective = 1000.0 / base_consumed
    expected = (mid - effective) / mid * 1e4  # positive sell cost
    assert row["fill_bps_bid_1k"] == pytest.approx(expected)
    assert expected > 0
