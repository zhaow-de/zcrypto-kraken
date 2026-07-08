from __future__ import annotations

import statistics

from cli.benchmark.strategies import returns_from_prices
from cli.features._validate import _validate_prices, _validate_window


def realized_vol(prices: list[float], *, lookback: int) -> list[float]:
    """Realized-vol state: stdev of the trailing `lookback` returns ending at the move into k,
    using only prices[<= k]. Warm-up (k < lookback) and zero-vol windows -> 0.0. Length
    len(prices)-1; aligned to returns_from_prices."""
    _validate_prices(prices)
    _validate_window("lookback", lookback)
    returns = returns_from_prices(prices)  # length len(prices)-1
    out: list[float] = []
    for k in range(len(prices) - 1):
        if k < lookback:
            out.append(0.0)
            continue
        window = returns[k - lookback : k]  # returns[j] uses prices[j],prices[j+1]; j<=k-1 -> prices[<=k]
        rv = statistics.stdev(window)
        out.append(rv if rv > 0 else 0.0)
    return out
