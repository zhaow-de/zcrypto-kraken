from __future__ import annotations

from cli.features._validate import _validate_prices, _validate_window


def channel_position(prices: list[float], *, window: int) -> list[float]:
    """Donchian channel position in [-1, +1]: with hi/lo = max/min(prices[k-window+1:k+1]),
    pos[k] = 2*(prices[k]-lo)/(hi-lo) - 1 (+1 at the channel high, -1 at the low). Flat window
    (hi==lo) and warm-up (k<window-1) -> 0.0. Length len(prices)-1; uses only prices[<= k]."""
    _validate_prices(prices)
    _validate_window("window", window)
    out: list[float] = []
    for k in range(len(prices) - 1):
        if k < window - 1:
            out.append(0.0)
            continue
        w = prices[k - window + 1 : k + 1]
        hi, lo = max(w), min(w)
        out.append(2 * (prices[k] - lo) / (hi - lo) - 1 if hi > lo else 0.0)
    return out
