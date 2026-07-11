from __future__ import annotations

import math

from cli.costs.errors import CostModelError

# Base crypto -> (low, high) fraction, charged per open AND per 4h rollover (docs/reference/kraken-fee-schedule.md).
MARGIN_RATES: dict[str, tuple[float, float]] = {
    "BTC": (0.0001, 0.0002),
    "ETH": (0.0002, 0.0004),
    "SOL": (0.0002, 0.0004),
    "XRP": (0.0002, 0.0004),
    "ADA": (0.0002, 0.0004),
    "LINK": (0.0002, 0.0004),
    "DOGE": (0.0002, 0.0004),
    "LTC": (0.0002, 0.0004),
    "DOT": (0.0002, 0.0004),
    "AVAX": (0.0002, 0.0004),
}


def margin_rate(base: str, *, band: str = "high") -> float:
    """The low/high per-open-and-rollover margin rate fraction for `base`."""
    if band not in ("low", "high"):
        raise CostModelError(f"band must be 'low' or 'high', got {band!r}")
    if base not in MARGIN_RATES:
        raise CostModelError(f"unknown margin base {base!r}; known: {sorted(MARGIN_RATES)}")
    low, high = MARGIN_RATES[base]
    return low if band == "low" else high


def margin_carry(notional: float, hold_hours: float, rate: float) -> float:
    """Margin carry = notional * rate * (1 opening + floor(hold_hours / 4) rollovers)."""
    for name, value in (("notional", notional), ("hold_hours", hold_hours), ("rate", rate)):
        if not math.isfinite(value) or value < 0:
            raise CostModelError(f"{name} must be finite and >= 0, got {value}")
    n_rollovers = math.floor(hold_hours / 4)
    return notional * rate * (1 + n_rollovers)
