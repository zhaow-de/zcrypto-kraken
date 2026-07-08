from __future__ import annotations

from cli.features._validate import _validate_prices, _validate_window


def momentum(prices: list[float], *, lookback: int) -> list[float]:
    """Causal past-return feature: m[k] = prices[k]/prices[k-lookback] - 1 for k >= lookback, else
    0.0. Length len(prices)-1, aligned to returns_from_prices (element k = the move prices[k] ->
    prices[k+1]); m[k] uses only prices[<= k] -> no look-ahead."""
    _validate_prices(prices)
    _validate_window("lookback", lookback)
    out: list[float] = []
    for k in range(len(prices) - 1):
        out.append(prices[k] / prices[k - lookback] - 1 if k >= lookback else 0.0)
    return out
