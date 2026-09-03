from __future__ import annotations

import math

from cli.features.errors import FeatureError


def _validate_prices(prices: list[float]) -> None:
    if not isinstance(prices, list) or len(prices) < 2:
        raise FeatureError(f"prices must be a list of >= 2 values, got {prices!r}")
    for p in prices:
        if not isinstance(p, (int, float)) or isinstance(p, bool) or not math.isfinite(p) or p <= 0:
            raise FeatureError(f"prices must be finite positive numbers, got {p!r}")


def _validate_window(name: str, value: int) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 2:
        raise FeatureError(f"{name} must be an int >= 2, got {value!r}")


def _validate_rates(name: str, values: list[float | None]) -> None:
    """Signed-value validator: funding rates go negative, so `_validate_prices` (which rejects
    <= 0) must not be used for them. `None` is allowed and propagates (spec 00110 D5)."""
    if not isinstance(values, list) or len(values) < 2:
        raise FeatureError(f"{name} must be a list of >= 2 values, got {values!r}")
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise FeatureError(f"{name} must be finite numbers or None, got {v!r}")


def _validate_levels(name: str, values: list[float | None]) -> None:
    """Positive-and-nullable: an OI LEVEL is strictly positive, but `_validate_prices` raises on
    `None` and these features must propagate it (spec 00110 D5). The substrate's `0.0` open-interest
    rows are venue holes, not levels; `oi_levels_from_raw` maps them to `None` before this runs, so
    a `0.0` here is a caller that skipped that step. Ratios are NOT levels -- a ratio may
    legitimately be zero, so they are gated by `_validate_rates`."""
    if not isinstance(values, list) or len(values) < 2:
        raise FeatureError(f"{name} must be a list of >= 2 values, got {values!r}")
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or v <= 0:
            raise FeatureError(f"{name} must be finite positive numbers or None, got {v!r}")
