"""Pure 1s L2 panel primitive math (spec 00052 D2) -- no I/O, no host state. Consumes `OrderBook`
state (`cli/capture/book.py`: `dict[Decimal, Decimal]` price->qty per side) and produces one wide
row of Float64 primitives per second. The Decimal->float conversion here is deliberate: the panel is
Float64 (the raw-side CRC-precision concern, T0045, does not apply to derived research columns).
"""

from __future__ import annotations

from decimal import Decimal

import polars as pl

# The depth-at-notional ladder (spec 00052 D2): walk a side accumulating price*qty EUR until the
# notional is filled, then compare the resulting VWAP to mid in bps. Column-name suffixes below are
# keyed off these exact values -- extending the ladder means extending `_FILL_SUFFIXES` too.
NOTIONALS_EUR: tuple[float, float, float] = (100.0, 1_000.0, 10_000.0)
_FILL_SUFFIXES: dict[float, str] = {100.0: "100", 1_000.0: "1k", 10_000.0: "10k"}

# Cumulative-depth price levels (spec 00052 D2).
_DEPTH_LEVELS: tuple[int, int, int] = (1, 5, 10)

PANEL_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "updates": pl.Int64,
    "spread": pl.Float64,
    "spread_bps": pl.Float64,
    "mid": pl.Float64,
    "microprice": pl.Float64,
    "imbalance_l1": pl.Float64,
    "fill_bps_bid_100": pl.Float64,
    "fill_bps_ask_100": pl.Float64,
    "fill_bps_bid_1k": pl.Float64,
    "fill_bps_ask_1k": pl.Float64,
    "fill_bps_bid_10k": pl.Float64,
    "fill_bps_ask_10k": pl.Float64,
    "depth_qty_bid_l1": pl.Float64,
    "depth_qty_bid_l5": pl.Float64,
    "depth_qty_bid_l10": pl.Float64,
    "depth_qty_ask_l1": pl.Float64,
    "depth_qty_ask_l5": pl.Float64,
    "depth_qty_ask_l10": pl.Float64,
}


def _fill_bps(levels: list[tuple[Decimal, Decimal]], notional: float, mid: float, *, buy: bool) -> float | None:
    """Walk `levels` (pre-sorted ascending for a buy / descending for a sell), accumulating
    price*qty EUR until `notional` is filled (the last level may be partial). Returns the VWAP
    ("effective" price) vs `mid` in bps -- positive is cost on both sides -- or None if the whole
    visible side sums to less than `notional` (never extrapolated)."""
    remaining = notional
    base_qty = 0.0
    for price, qty in levels:
        price_f, qty_f = float(price), float(qty)
        level_notional = price_f * qty_f
        if level_notional >= remaining:
            base_qty += remaining / price_f
            remaining = 0.0
            break
        remaining -= level_notional
        base_qty += qty_f
    if remaining > 0:
        return None
    effective = notional / base_qty
    return (effective - mid) / mid * 1e4 if buy else (mid - effective) / mid * 1e4


def _depth_qty(levels: list[tuple[Decimal, Decimal]], k: int) -> float:
    """Cumulative base qty over the best `k` price levels; fewer than `k` levels -> sum over what
    exists."""
    return float(sum(qty for _, qty in levels[:k]))


def sample_row(bids: dict[Decimal, Decimal], asks: dict[Decimal, Decimal], *, updates: int) -> dict | None:
    """One second's wide primitive row (spec 00052 D2) from `OrderBook` state, or None iff either
    side is empty (no quotable market that second). A crossed/locked book (spread <= 0) is still
    computed honestly -- it happens transiently and is not filtered here. Returns every `PANEL_SCHEMA`
    column except `ts` (the caller stamps the second boundary)."""
    if not bids or not asks:
        return None

    best_bid, best_ask = max(bids), min(asks)
    bid, ask = float(best_bid), float(best_ask)
    bid_qty, ask_qty = float(bids[best_bid]), float(asks[best_ask])

    spread = ask - bid
    mid = (bid + ask) / 2
    spread_bps = spread / mid * 1e4
    microprice = (ask_qty * bid + bid_qty * ask) / (bid_qty + ask_qty)
    imbalance_l1 = bid_qty / (bid_qty + ask_qty)

    bid_levels = sorted(bids.items(), reverse=True)  # best (highest) price first -- a sell's walk
    ask_levels = sorted(asks.items())  # best (lowest) price first -- a buy's walk

    row: dict[str, float | int | None] = {
        "updates": updates,
        "spread": spread,
        "spread_bps": spread_bps,
        "mid": mid,
        "microprice": microprice,
        "imbalance_l1": imbalance_l1,
    }
    for notional in NOTIONALS_EUR:
        suffix = _FILL_SUFFIXES[notional]
        row[f"fill_bps_bid_{suffix}"] = _fill_bps(bid_levels, notional, mid, buy=False)
        row[f"fill_bps_ask_{suffix}"] = _fill_bps(ask_levels, notional, mid, buy=True)
    for side, levels in (("bid", bid_levels), ("ask", ask_levels)):
        for k in _DEPTH_LEVELS:
            row[f"depth_qty_{side}_l{k}"] = _depth_qty(levels, k)
    return row
