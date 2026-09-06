"""Captured-spread cost term (spec 00066), calibrated from our own L2 capture (`l2-panel`, spec 00052)
rather than from a vendor quote. Recalibration moves the table AND the provenance constants together, restamping
`docs/reference/captured-spread-calibration.md`; `tests/test_costs_spread.py` pins both.
"""

from __future__ import annotations

import math

from cli.costs.errors import CostModelError
from cli.costs.fees import round_trip_fee
from cli.costs.margin import margin_carry

CALIBRATION_WINDOW: tuple[str, str] = ("2026-07-23T14:00:00Z", "2026-08-07T19:00:00Z")
CALIBRATION_HOURS: int = 365
CALIBRATION_MIN_ROWS: int = 1_314_000

# Mean effective spread, bps per side, mid-relative, at the EUR notional rungs; on a BTC-quoted pair the rung is the
# BTC quantity worth that many EUR at `BTC_EUR_REFERENCE` (`cli/panel/primitives.py`). Effective spread at size, never
# top-of-book -- BTC/EUR's top-of-book median is unstable under its EUR 0.10 tick quantisation -- and no session
# dimension, omitted on materiality rather than on absence.
SPREAD_CALIBRATION: dict[str, dict[int, float]] = {
    "ADA/EUR": {100: 2.383, 1_000: 2.686, 10_000: 5.389},
    "AVAX/EUR": {100: 2.417, 1_000: 2.838, 10_000: 6.031},
    "BTC/EUR": {100: 0.198, 1_000: 0.299, 10_000: 0.533},
    "DOGE/EUR": {100: 1.635, 1_000: 1.787, 10_000: 3.539},
    "DOT/EUR": {100: 2.812, 1_000: 4.053, 10_000: 10.054},
    "ETH/BTC": {100: 0.748, 1_000: 1.112, 10_000: 1.564},
    "ETH/EUR": {100: 0.344, 1_000: 0.404, 10_000: 0.619},
    "LINK/EUR": {100: 2.382, 1_000: 2.555, 10_000: 4.021},
    "LTC/EUR": {100: 2.103, 1_000: 2.908, 10_000: 5.124},
    "SOL/BTC": {100: 1.343, 1_000: 1.685, 10_000: 2.757},
    "SOL/EUR": {100: 0.927, 1_000: 1.041, 10_000: 1.798},
    "XRP/EUR": {100: 0.603, 1_000: 0.945, 10_000: 1.924},
}

_PINNED_SIZES: tuple[int, ...] = (100, 1_000, 10_000)


def effective_spread_bps(pair: str, notional_eur: float) -> float:
    """Mean effective spread in bps per side for `pair` at `notional_eur`: interpolated linearly in LOG notional
    between the pinned sizes because cost is convex in size, clamped below the first rung, refused above the last.
    """
    table = SPREAD_CALIBRATION.get(pair.upper() if isinstance(pair, str) else pair)
    if table is None:
        raise CostModelError(f"unknown pair {pair!r}; calibrated pairs: {sorted(SPREAD_CALIBRATION)}")
    if not isinstance(notional_eur, (int, float)) or not math.isfinite(notional_eur) or notional_eur <= 0:
        raise CostModelError(f"notional_eur must be finite and > 0, got {notional_eur}")

    lo_size, hi_size = _PINNED_SIZES[0], _PINNED_SIZES[-1]
    if notional_eur <= lo_size:
        return table[lo_size]
    if notional_eur > hi_size:
        raise CostModelError(
            f"notional_eur {notional_eur} exceeds the calibrated grid (max {hi_size}); the cost "
            "curve is convex, so extrapolating would understate it -- recalibrate with a larger "
            "pinned size instead"
        )

    for left, right in zip(_PINNED_SIZES, _PINNED_SIZES[1:]):
        if left <= notional_eur <= right:
            if notional_eur == left:
                return table[left]
            if notional_eur == right:
                return table[right]
            frac = (math.log(notional_eur) - math.log(left)) / (math.log(right) - math.log(left))
            return table[left] + frac * (table[right] - table[left])
    raise CostModelError(f"could not place notional_eur {notional_eur} on the calibrated grid")


def round_trip_cost(
    notional: float,
    *,
    pair: str,
    maker_rate: float,
    taker_rate: float,
    taker_open: bool = False,
    taker_close: bool = False,
    hold_hours: float = 0.0,
    margin_rate_: float | None = None,
) -> dict:
    """Open+close cost on `notional`: exchange fee + spread (both sides) + optional margin carry.

    The spread term is ADDITIVE to the fee term, never a substitute for it.
    """
    if not math.isfinite(notional) or notional <= 0:
        raise CostModelError(f"notional must be finite and > 0, got {notional}")

    fee = round_trip_fee(
        notional,
        maker_rate=maker_rate,
        taker_rate=taker_rate,
        taker_open=taker_open,
        taker_close=taker_close,
    )
    # Charged once per side: entering and exiting both cross the book.
    spread = 2.0 * notional * effective_spread_bps(pair, notional) / 10_000.0
    # Never gate the carry leg on `hold_hours`: `margin_carry`'s opening charge is unconditional, so a position
    # opened and closed inside one 4h window would silently lose it -- cost-understating.
    carry = 0.0
    if margin_rate_ is not None:
        carry = margin_carry(notional, hold_hours, margin_rate_)
    return {"fee": fee, "spread": spread, "carry": carry, "total": fee + spread + carry}
