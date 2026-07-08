from __future__ import annotations

import math

from cli.costs.errors import CostModelError

# (min_30d_volume_usd, maker, taker) as fractions — Kraken spot schedule effective 2026-07-09
# (docs/kraken-fee-schedule.md). Ascending by volume; tier is 1-based on this order.
SPOT_FEE_TIERS: tuple[tuple[float, float, float], ...] = (
    (0, 0.0040, 0.0080),
    (2_500, 0.0030, 0.0060),
    (10_000, 0.0022, 0.0038),
    (25_000, 0.0020, 0.0035),
    (50_000, 0.0015, 0.0030),
    (100_000, 0.0012, 0.0025),
    (250_000, 0.0010, 0.0022),
    (500_000, 0.0008, 0.0020),
    (1_000_000, 0.0006, 0.0018),
    (2_500_000, 0.0004, 0.0015),
    (5_000_000, 0.0002, 0.0012),
    (10_000_000, 0.0000, 0.0010),
    (50_000_000, 0.0000, 0.0009),
    (100_000_000, 0.0000, 0.0008),
    (250_000_000, 0.0000, 0.0007),
    (400_000_000, 0.0000, 0.0006),
    (500_000_000, 0.0000, 0.0005),
)


def spot_fee_rates(thirty_day_volume_usd: float) -> dict:
    """Maker/taker fee fractions + 1-based tier for a 30-day USD spot volume (Kraken, 2026-07-09 schedule)."""
    if not math.isfinite(thirty_day_volume_usd) or thirty_day_volume_usd < 0:
        raise CostModelError(f"thirty_day_volume_usd must be finite and >= 0, got {thirty_day_volume_usd}")
    idx = 0
    for i, (min_vol, _maker, _taker) in enumerate(SPOT_FEE_TIERS):
        if thirty_day_volume_usd >= min_vol:
            idx = i
        else:
            break
    _min_vol, maker, taker = SPOT_FEE_TIERS[idx]
    return {"tier": idx + 1, "maker": maker, "taker": taker}


def round_trip_fee(
    notional: float,
    *,
    maker_rate: float,
    taker_rate: float,
    taker_open: bool = False,
    taker_close: bool = False,
) -> float:
    """Open+close fee cost on `notional`; each leg is taker if flagged, else maker (default maker-first)."""
    for name, value in (("notional", notional), ("maker_rate", maker_rate), ("taker_rate", taker_rate)):
        if not math.isfinite(value) or value < 0:
            raise CostModelError(f"{name} must be finite and >= 0, got {value}")
    open_rate = taker_rate if taker_open else maker_rate
    close_rate = taker_rate if taker_close else maker_rate
    return notional * (open_rate + close_rate)
