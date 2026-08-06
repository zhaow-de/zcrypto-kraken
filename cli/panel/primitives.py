"""Pure 1s L2 panel primitive math (spec 00052 D2) -- no I/O, no host state. Consumes `OrderBook`
state (`cli/capture/book.py`: `dict[Decimal, Decimal]` price->qty per side) and produces one wide
row of Float64 primitives per second. The Decimal->float conversion here is deliberate: the panel is
Float64 (the raw-side CRC-precision concern, T0045, does not apply to derived research columns).
"""

from __future__ import annotations

from decimal import Decimal

import polars as pl

from cli.panel.errors import PanelError  # errors.py imports nothing, so this is safe

# The depth-at-notional ladder (spec 00052 D2, made quote-aware by spec 00085 D1): walk a side
# accumulating price*qty in the pair's QUOTE currency until the notional is filled, then compare the
# resulting VWAP to mid in bps. The rungs therefore have to be denominated per quote, or a BTC-quoted
# pair asks for 100 BTC where it means EUR 100 -- which is why every `fill_bps_*` on those pairs was
# null before this.
NOTIONALS_EUR: tuple[float, float, float] = (100.0, 1_000.0, 10_000.0)
# The ladder walks `price * qty`, which is denominated in the pair's QUOTE currency -- so these are
# EUR notionals only for EUR-quoted pairs. The panel is scoped to those (T0092). On a BTC-quoted
# pair the rungs read as 100/1k/10k BTC: at the 2026-03-31 BTC/EUR close (EUR 58,968.90) the @100
# rung alone asks EUR 5.9 M, which is ~10x ETH/BTC's and ~25x SOL/BTC's ENTIRE daily volume, so
# `_fill_bps` returns None on insufficient depth and all six `fill_bps_*` columns go null. The harm
# is therefore a dead EUR-labelled ladder and an out-of-scope tree, not a wrong number -- which is
# still worth excluding, and is why the calibration reads `<BASE>/EUR/**` by design.
PANEL_QUOTE = "EUR"

# The BTC/EUR rate the BTC rungs are pinned to. EUR-EQUIVALENCE is the point (spec 00085 D1): the
# BTC rungs buy the same EUR value as the EUR rungs, so `SPREAD_CALIBRATION`'s inner keys stay EUR
# notionals and one shared interpolation grid serves all twelve legs. Derived from this repo's own
# BTC/EUR panel mids over the calibration window by `cli/costs/calibrate.py`, and restamped with the
# table -- never a live rate, or the column meaning would drift hour to hour.
BTC_EUR_REFERENCE: float = 55876.28413495087
BTC_EUR_REFERENCE_WINDOW: tuple[str, str] = ("2026-07-23T14:00:00Z", "2026-08-06T06:00:00Z")

NOTIONALS_BY_QUOTE: dict[str, tuple[float, float, float]] = {
    "EUR": NOTIONALS_EUR,
    "BTC": tuple(n / BTC_EUR_REFERENCE for n in NOTIONALS_EUR),  # type: ignore[dict-item]
}

# Keyed by rung INDEX, not by value: the values now differ per quote, so a value-keyed map would
# need a lookup per quote and would silently miss on a float that did not round-trip.
_FILL_SUFFIXES: tuple[str, str, str] = ("100", "1k", "10k")


def notionals_for(quote: str) -> tuple[float, float, float]:
    """The ladder for `quote`, refusing rather than defaulting -- a silent EUR fallback on an
    unknown quote is exactly the wrong-number failure this ladder exists to prevent."""
    try:
        return NOTIONALS_BY_QUOTE[quote]
    except KeyError:
        raise PanelError(f"no notional ladder for quote {quote!r}: add one to NOTIONALS_BY_QUOTE") from None


# Cumulative-depth price levels (spec 00052 D2).
_DEPTH_LEVELS: tuple[int, int, int] = (1, 5, 10)

PANEL_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "updates": pl.Int64,
    # T0104: seconds from the last message APPLIED to the book to this boundary. `updates == 0` is
    # ambiguous -- a quiet second and a hole in the archive look identical -- so the panel says which.
    # Null means "unknown" (a carried state that predates this column); never 0.0, which would
    # assert a freshness we cannot know.
    "stale_seconds": pl.Float64,
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


def sample_row(
    bids: dict[Decimal, Decimal],
    asks: dict[Decimal, Decimal],
    *,
    quote: str,
    updates: int,
    stale_seconds: float | None = None,
) -> dict | None:
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
        "stale_seconds": stale_seconds,
        "spread": spread,
        "spread_bps": spread_bps,
        "mid": mid,
        "microprice": microprice,
        "imbalance_l1": imbalance_l1,
    }
    for index, notional in enumerate(notionals_for(quote)):
        suffix = _FILL_SUFFIXES[index]
        row[f"fill_bps_bid_{suffix}"] = _fill_bps(bid_levels, notional, mid, buy=False)
        row[f"fill_bps_ask_{suffix}"] = _fill_bps(ask_levels, notional, mid, buy=True)
    for side, levels in (("bid", bid_levels), ("ask", ask_levels)):
        for k in _DEPTH_LEVELS:
            row[f"depth_qty_{side}_l{k}"] = _depth_qty(levels, k)
    return row
