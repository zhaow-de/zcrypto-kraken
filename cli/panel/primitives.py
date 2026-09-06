"""Pure 1s L2 panel primitive math over `OrderBook` state (`cli/capture/book.py`), no I/O (spec 00052 D2). The
Decimal->float narrowing is deliberate: the raw-side CRC-precision concern (T0045, resolved) binds the raw wire
strings, not derived Float64 research columns."""

from __future__ import annotations

from decimal import Decimal

import polars as pl

from cli.panel.errors import PanelError  # errors.py imports nothing, so this is safe

# Rungs are denominated per quote (spec 00085 D1): otherwise a BTC-quoted pair asks for 100 BTC where
# EUR 100 is meant.
NOTIONALS_EUR: tuple[float, float, float] = (100.0, 1_000.0, 10_000.0)

# The frozen BTC/EUR rate for the BTC rungs -- mean `mid` over `BTC_EUR_REFERENCE_WINDOW`, never a live rate, so they buy
# the same EUR value as the EUR rungs and `SPREAD_CALIBRATION`'s inner keys stay EUR notionals. It defines what every BTC
# `fill_bps_*` in the tree MEANS: a recalibration moves `cli/costs/spread.py`'s `CALIBRATION_WINDOW`, never this one, and
# a later measurement that disagrees means regenerate the tree or explain the divergence, never update this constant.
BTC_EUR_REFERENCE: float = 55876.28413495087  # the measurement, verbatim
BTC_EUR_REFERENCE_WINDOW: tuple[str, str] = ("2026-07-23T14:00:00Z", "2026-08-06T06:00:00Z")

NOTIONALS_BY_QUOTE: dict[str, tuple[float, float, float]] = {
    "EUR": NOTIONALS_EUR,
    "BTC": (
        NOTIONALS_EUR[0] / BTC_EUR_REFERENCE,
        NOTIONALS_EUR[1] / BTC_EUR_REFERENCE,
        NOTIONALS_EUR[2] / BTC_EUR_REFERENCE,
    ),
}

# Keyed by rung index, not by value: rung values differ per quote, and a float key can fail to round-trip.
_FILL_SUFFIXES: tuple[str, str, str] = ("100", "1k", "10k")


def notionals_for(quote: str) -> tuple[float, float, float]:
    """The ladder for `quote`, refusing rather than defaulting -- a silent EUR fallback is the wrong-number failure this
    ladder exists to prevent."""
    try:
        return NOTIONALS_BY_QUOTE[quote]
    except KeyError:
        raise PanelError(f"no notional ladder for quote {quote!r}: add one to NOTIONALS_BY_QUOTE") from None


_DEPTH_LEVELS: tuple[int, int, int] = (1, 5, 10)

PANEL_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "updates": pl.Int64,
    # Seconds from the last message APPLIED to the book to this boundary (T0104, resolved), since
    # `updates == 0` cannot tell a quiet second from a hole in the archive. Null is "unknown", never
    # 0.0, which would assert a freshness the panel cannot know.
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
    """The VWAP of filling `notional` (quote currency) against `levels`, vs `mid` in bps and signed so cost is positive
    on both sides; `levels` must arrive best-price-first, and a visible side that sums to less than `notional` returns
    None rather than an extrapolation."""
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
    """Cumulative base qty over the best `k` price levels, or over what exists when there are fewer."""
    return float(sum(qty for _, qty in levels[:k]))


def sample_row(
    bids: dict[Decimal, Decimal],
    asks: dict[Decimal, Decimal],
    *,
    quote: str,
    updates: int,
    stale_seconds: float | None = None,
) -> dict | None:
    """One second's primitive row -- every `PANEL_SCHEMA` column but `ts`, which the caller stamps -- or None iff a side
    is empty; a crossed or locked book (spread <= 0) is transient and computed as it stands, not filtered here."""
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
    # strict=True: a ladder of a different length must refuse here, never truncate silently.
    for suffix, notional in zip(_FILL_SUFFIXES, notionals_for(quote), strict=True):
        row[f"fill_bps_bid_{suffix}"] = _fill_bps(bid_levels, notional, mid, buy=False)
        row[f"fill_bps_ask_{suffix}"] = _fill_bps(ask_levels, notional, mid, buy=True)
    for side, levels in (("bid", bid_levels), ("ask", ask_levels)):
        for k in _DEPTH_LEVELS:
            row[f"depth_qty_{side}_l{k}"] = _depth_qty(levels, k)
    return row
