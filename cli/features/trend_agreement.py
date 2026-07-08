from __future__ import annotations

import statistics

from cli.features._validate import _validate_prices, _validate_window
from cli.features.errors import FeatureError
from cli.features.momentum import momentum


def _validate_lookbacks(lookbacks: list[int]) -> None:
    if not isinstance(lookbacks, list) or len(lookbacks) == 0:
        raise FeatureError(f"lookbacks must be a non-empty list of ints >= 2, got {lookbacks!r}")
    for lb in lookbacks:
        _validate_window("lookback", lb)


def _sign(x: float) -> float:
    if x > 0:
        return 1.0
    if x < 0:
        return -1.0
    return 0.0


def trend_agreement(prices: list[float], *, lookbacks: list[int]) -> list[float]:
    """Per-asset multi-horizon trend agreement: agreement[k] = mean(sign(momentum(prices,
    lookback=L)[k]) for L in lookbacks), in [-1, +1] (+1 every horizon up, -1 every horizon down, 0
    split or all warm-up). Reuses momentum, so causality is inherited: agreement[k] uses only
    prices[<= k]. Length len(prices)-1."""
    _validate_prices(prices)
    _validate_lookbacks(lookbacks)
    momenta = [momentum(prices, lookback=lb) for lb in lookbacks]
    return [statistics.mean(_sign(m[k]) for m in momenta) for k in range(len(prices) - 1)]
