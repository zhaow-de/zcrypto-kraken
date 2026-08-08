"""Captured-spread cost term (T0014, spec 00066).

The missing leg of the cost model: Phase-4/5 verdicts charged fees + margin carry and assumed ZERO
spread, on a basket whose thin alts are exactly where spread bites.

Calibrated from our own L2 capture (`l2-panel`, spec 00052), NOT from a vendor quote. Two
measured choices drive the shape of this module and are worth knowing before editing it:

  * The numbers are the **mean effective spread at a traded notional** (`fill_bps`), not the
    top-of-book spread. BTC/EUR is tick-quantised at EUR 0.10 and sits at exactly one tick 42-58%
    of the seconds on complete UTC days (41.4% including the two partial edge days, 49.5% pooled);
    because that fraction straddles 50%, its MEDIAN top-of-book spread swings ~15x on
    a small change in the one-tick share (mean/median = 11.2x, against 0.9-1.3x for every other
    pair). The effective spread at size has no such instability -- walking the book averages over
    the quantisation -- and it is also what we actually pay. Never quote a median top-of-book
    spread for BTC/EUR; cite the mean, or these figures.
  * There is **no session term**. Mean effective spread at EUR 1k across Asia/EU/US sessions
    varies by 1.01x-1.10x across the ten pairs (widest LTC 1.098x). The reason to omit the
    dimension is MATERIALITY, not absence: a <=10% modulation of a 2-4 bps term against a 40-80 bps
    fee does not earn one. A paired day-level test does detect a consistently-signed Asia-wider
    effect (t = -1.9 to -2.3 on BTC/ETH/LTC; 7/10 pairs Asia-wider), so "inside the noise" would be
    the wrong reason to give.

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
CALIBRATION_WINDOW: tuple[str, str] = ("2026-07-23T14:00:00Z", "2026-08-07T19:00:00Z")
CALIBRATION_HOURS: int = 365
CALIBRATION_MIN_ROWS: int = 1_314_000

# Mean effective spread, **bps per side**, mid-relative, by EUR notional. Nulls over the window:
# exactly 2 across 10 pairs x 3 sizes x 2 sides (XRP fill_bps_ask_10k, 2026-07-13 07:04:31-32Z), so
# the visible book covered EUR 10k effectively always; those 2 rows drop out of XRP's @10k mean.
# NOTE (standing caveat, capture-era data-hygiene map): at EUR 10k the fill walk passes rank 10 on
# the thin pairs, and ranks beyond 10 are venue-unverified in every era -- those figures rest on
# protocol congruence rather than on Kraken's own checksums.
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
    40-80 bps per side against 0.6-12.4 bps of spread at EUR 10k, so an edit that swapped them
    would be off by an order of magnitude -- there is a test guarding exactly that.
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
    # `and hold_hours` would be wrong: margin_carry's contract is
    # notional * rate * (1 opening + floor(hold_hours/4) rollovers) -- the OPENING charge is
    # unconditional, so gating on hold_hours silently dropped it for a position opened and closed
    # inside one 4h window. Cost-UNDERSTATING, i.e. the exact direction this module exists to fix.
    carry = 0.0
    if margin_rate_ is not None:
        carry = margin_carry(notional, hold_hours, margin_rate_)
    return {"fee": fee, "spread": spread, "carry": carry, "total": fee + spread + carry}
