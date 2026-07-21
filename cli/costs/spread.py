"""Captured-spread cost term (T0014, spec 00066).

The missing leg of the cost model: Phase-4/5 verdicts charged fees + margin carry and assumed ZERO
spread, on a basket whose thin alts are exactly where spread bites.

Calibrated from our own L2 capture (`l2-panel`, spec 00052), NOT from a vendor quote. Two
measured choices drive the shape of this module and are worth knowing before editing it:

  * The numbers are the **mean effective spread at a traded notional** (`fill_bps`), not the
    top-of-book spread. BTC/EUR is tick-quantised at EUR 0.10 and sits at exactly one tick 42-58%
    of the time; because that fraction straddles 50%, its MEDIAN top-of-book spread swings ~15x on
    a small change in the one-tick share (mean/median = 11.2x, against 0.9-1.3x for every other
    pair). The effective spread at size has no such instability -- walking the book averages over
    the quantisation -- and it is also what we actually pay. Never quote a median top-of-book
    spread for BTC/EUR; cite the mean, or these figures.
  * There is **no session term**. Mean effective spread across Asia/EU/US sessions varies by
    1.02x-1.08x per pair -- inside the noise of the thing being modelled.

Recalibration is a deliberate edit: change the table AND the provenance constants together, and
restamp `docs/reference/captured-spread-calibration.md`. tests/test_costs_spread.py pins both, so a
silent drift fails rather than quietly repricing every historical verdict.
"""

from __future__ import annotations

import math

from cli.costs.errors import CostModelError
from cli.costs.fees import round_trip_fee
from cli.costs.margin import margin_carry

# Provenance of the table below -- asserted by the tests so a new window cannot arrive unstamped.
CALIBRATION_WINDOW: tuple[str, str] = ("2026-07-08T13:47:33Z", "2026-07-21T15:59:59Z")
CALIBRATION_HOURS: int = 315
CALIBRATION_MIN_ROWS: int = 1_123_509

# Mean effective spread, **bps per side**, mid-relative, by EUR notional. 0.00% null rate at every
# size for every pair over the window, i.e. the visible book covered EUR 10k at all times.
# NOTE (standing caveat, capture-era data-hygiene map): at EUR 10k the fill walk passes rank 10 on
# the thin pairs, and ranks beyond 10 are venue-unverified in every era -- those figures rest on
# protocol congruence rather than on Kraken's own checksums.
SPREAD_CALIBRATION: dict[str, dict[int, float]] = {
    "BTC": {100: 0.266, 1_000: 0.392, 10_000: 0.635},
    "ETH": {100: 0.425, 1_000: 0.494, 10_000: 0.698},
    "XRP": {100: 0.768, 1_000: 1.121, 10_000: 2.076},
    "SOL": {100: 0.925, 1_000: 1.034, 10_000: 1.834},
    "DOGE": {100: 1.707, 1_000: 1.839, 10_000: 3.724},
    "LINK": {100: 2.102, 1_000: 2.275, 10_000: 3.677},
    "LTC": {100: 2.035, 1_000: 3.028, 10_000: 5.245},
    "ADA": {100: 2.174, 1_000: 2.452, 10_000: 5.324},
    "AVAX": {100: 2.438, 1_000: 2.886, 10_000: 5.916},
    "DOT": {100: 3.684, 1_000: 5.545, 10_000: 12.412},
}

_PINNED_SIZES: tuple[int, ...] = (100, 1_000, 10_000)


def effective_spread_bps(pair: str, notional_eur: float) -> float:
    """Mean effective spread in bps per side for `pair` at `notional_eur`.

    Interpolates linearly in LOG notional between the pinned sizes (cost is strongly convex in
    size on the thin pairs -- DOT runs 3.68 -> 5.55 -> 12.41 bps -- so a linear-in-notional reading
    would flatten exactly the curvature that matters). Clamps below EUR 100 to the EUR 100 value,
    and REFUSES above EUR 10k rather than extrapolating: on a convex curve an extrapolation
    understates cost precisely where the error is most expensive.
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

    The spread term is ADDITIVE to the fee term, never a substitute for it. At tier 1 fees are
    40-80 bps per side against 0.6-12.4 bps of spread, so an edit that swapped one for the other
    would be off by an order of magnitude -- there is a test guarding exactly that.
    """
    if not math.isfinite(notional) or notional < 0:
        raise CostModelError(f"notional must be finite and >= 0, got {notional}")

    fee = round_trip_fee(
        notional,
        maker_rate=maker_rate,
        taker_rate=taker_rate,
        taker_open=taker_open,
        taker_close=taker_close,
    )
    # Charged once per side: entering and exiting both cross the book.
    spread = 2.0 * notional * effective_spread_bps(pair, notional) / 10_000.0
    carry = 0.0
    if margin_rate_ is not None and hold_hours:
        carry = margin_carry(notional, hold_hours, margin_rate_)
    return {"fee": fee, "spread": spread, "carry": carry, "total": fee + spread + carry}
