from __future__ import annotations

from cli.features._validate import _validate_prices


def drawdown_state(prices: list[float]) -> list[float]:
    """Current drawdown from the running (expanding) peak, in [-1, 0] (0.0 at a new high, negative
    below the peak). Length len(prices)-1; uses only prices[<= k]."""
    _validate_prices(prices)
    out: list[float] = []
    peak = prices[0]
    for k in range(len(prices) - 1):
        if prices[k] > peak:
            peak = prices[k]
        out.append(prices[k] / peak - 1)
    return out
