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
