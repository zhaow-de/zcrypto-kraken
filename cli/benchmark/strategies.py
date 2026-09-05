from __future__ import annotations

import math
import statistics

from cli.benchmark.errors import BenchmarkError


def buy_and_hold(n_periods: int) -> list[float]:
    """B0 — constant full long position."""
    if not isinstance(n_periods, int) or n_periods < 1:
        raise BenchmarkError(f"n_periods must be an int >= 1, got {n_periods!r}")
    return [1.0] * n_periods


def vol_target(returns: list[float], *, target_vol: float, lookback: int, max_leverage: float = 1.0) -> list[float]:
    """B1 — position[t] = min(target_vol / stdev(returns[t-lookback:t]), max_leverage), 0.0 for t < lookback or a zero-vol window.

    `target_vol` is per period, the unit of `returns`. The window excludes t, so position[t] never uses return[t] — no look-ahead
    when the backtester applies it to return[t]."""
    if not returns:
        raise BenchmarkError("returns must be non-empty")
    for r in returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r):
            raise BenchmarkError(f"returns must be finite numbers, got {r!r}")
    if not isinstance(target_vol, (int, float)) or not math.isfinite(target_vol) or target_vol <= 0:
        raise BenchmarkError(f"target_vol must be a finite number > 0, got {target_vol!r}")
    if not isinstance(lookback, int) or lookback < 2:
        raise BenchmarkError(f"lookback must be an int >= 2, got {lookback!r}")
    if not isinstance(max_leverage, (int, float)) or not math.isfinite(max_leverage) or max_leverage <= 0:
        raise BenchmarkError(f"max_leverage must be a finite number > 0, got {max_leverage!r}")

    positions: list[float] = []
    for t in range(len(returns)):
        if t < lookback:
            positions.append(0.0)
            continue
        rv = statistics.stdev(returns[t - lookback : t])
        positions.append(min(target_vol / rv, max_leverage) if rv > 0 else 0.0)
    return positions


def returns_from_prices(prices: list[float]) -> list[float]:
    """Close-to-close simple returns: r[t] = prices[t] / prices[t-1] - 1. Prices must be finite and positive."""
    if not isinstance(prices, list) or len(prices) < 2:
        raise BenchmarkError(f"prices must be a list of >= 2 values, got {prices!r}")
    for p in prices:
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
            raise BenchmarkError(f"prices must be finite positive numbers, got {p!r}")
    return [prices[t] / prices[t - 1] - 1 for t in range(1, len(prices))]


def sma_gate(prices: list[float], *, window: int) -> list[float]:
    """Long/flat regime gate: signal[k] = 1.0 iff k >= window-1 and prices[k] > SMA(prices[k-window+1:k+1]), else 0.0.

    Length len(prices)-1, aligned with returns_from_prices (element k = the move prices[k] -> prices[k+1]); signal[k]
    reads only prices[<= k], never prices[k+1] — no look-ahead."""
    if not isinstance(prices, list) or len(prices) < 2:
        raise BenchmarkError(f"prices must be a list of >= 2 values, got {prices!r}")
    for p in prices:
        if not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0:
            raise BenchmarkError(f"prices must be finite positive numbers, got {p!r}")
    if not isinstance(window, int) or window < 2:
        raise BenchmarkError(f"window must be an int >= 2, got {window!r}")
    signal: list[float] = []
    for k in range(len(prices) - 1):
        if k < window - 1:
            signal.append(0.0)
            continue
        sma = statistics.mean(prices[k - window + 1 : k + 1])
        signal.append(1.0 if prices[k] > sma else 0.0)
    return signal


def _inverse_vol_weight(window: list[float]) -> float | None:
    """1 / stdev(window) if the window has positive stdev, else None (not weightable)."""
    vol = statistics.stdev(window)
    return 1.0 / vol if vol > 0.0 else None


def inverse_vol_basket(prices_by_asset: dict[str, list[float]], *, lookback: int) -> list[float]:
    """B2 — net return series of an inverse-vol-weighted basket over price series pre-aligned to one length.

    For t >= lookback, weight asset i by 1 / stdev(returns_i[t-lookback:t]) — the window strictly before t, so no look-ahead —
    normalized over the assets with positive trailing vol, applied to returns_i[t]; t < lookback and days with none are 0.0."""
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 2:
        raise BenchmarkError(f"lookback must be an int >= 2, got {lookback!r}")
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise BenchmarkError("prices_by_asset must be a non-empty dict of price series")

    returns_by_asset: dict[str, list[float]] = {}
    lengths: set[int] = set()
    for asset, prices in prices_by_asset.items():
        returns_by_asset[asset] = returns_from_prices(prices)  # validates finite/positive/len>=2
        lengths.add(len(prices))
    if len(lengths) != 1:
        raise BenchmarkError(f"all price series must have equal length, got {sorted(lengths)}")
    length = lengths.pop()
    if length < lookback + 2:
        raise BenchmarkError(f"price series length {length} too short for lookback {lookback} (need >= {lookback + 2})")

    n_returns = length - 1
    portfolio: list[float] = []
    for t in range(n_returns):
        if t < lookback:
            portfolio.append(0.0)
            continue
        inv_weights: dict[str, float] = {}
        for asset, rets in returns_by_asset.items():
            weight = _inverse_vol_weight(rets[t - lookback : t])
            if weight is not None:
                inv_weights[asset] = weight
        if not inv_weights:
            portfolio.append(0.0)
            continue
        total = sum(inv_weights.values())
        portfolio.append(sum((inv / total) * returns_by_asset[asset][t] for asset, inv in inv_weights.items()))
    return portfolio


def dynamic_inverse_vol_basket(prices_by_asset: dict[str, list[float | None]], *, lookback: int) -> list[float]:
    """`inverse_vol_basket` over a union calendar: equal-length series, `None` where an asset is absent (pre-listing or a gap).
    ret_i[t] = prices_i[t+1]/prices_i[t] - 1, `None` if either price is. For t >= lookback, asset i qualifies iff ret_i[t] and its
    window ret_i[t-lookback:t] (strictly before t — no look-ahead) are `None`-free and the window's stdev is positive; qualifiers
    are weighted 1 / stdev, renormalized over the qualifying set; t < lookback and periods with no qualifier are 0.0."""
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 2:
        raise BenchmarkError(f"lookback must be an int >= 2, got {lookback!r}")
    if not isinstance(prices_by_asset, dict) or not prices_by_asset:
        raise BenchmarkError("prices_by_asset must be a non-empty dict of price series")

    lengths: set[int] = set()
    for asset, prices in prices_by_asset.items():
        if not isinstance(prices, list):
            raise BenchmarkError(f"prices for {asset!r} must be a list, got {type(prices)!r}")
        for p in prices:
            if p is not None and (not isinstance(p, (int, float)) or not math.isfinite(p) or p <= 0):
                raise BenchmarkError(f"prices must be None or finite positive numbers, got {p!r}")
        lengths.add(len(prices))
    if len(lengths) != 1:
        raise BenchmarkError(f"all price series must have equal length, got {sorted(lengths)}")
    length = lengths.pop()

    returns_by_asset: dict[str, list[float | None]] = {}
    for asset, prices in prices_by_asset.items():
        rets: list[float | None] = []
        for t in range(length - 1):
            p0, p1 = prices[t], prices[t + 1]
            rets.append(p1 / p0 - 1 if p0 is not None and p1 is not None else None)
        returns_by_asset[asset] = rets

    portfolio: list[float] = []
    for t in range(length - 1):
        inv_weights: dict[str, float] = {}
        if t >= lookback:
            for asset, rets in returns_by_asset.items():
                if rets[t] is None:
                    continue
                window = rets[t - lookback : t]
                if any(r is None for r in window):
                    continue
                weight = _inverse_vol_weight(window)
                if weight is not None:
                    inv_weights[asset] = weight
        if not inv_weights:
            portfolio.append(0.0)
            continue
        total = sum(inv_weights.values())
        portfolio.append(sum((inv / total) * returns_by_asset[asset][t] for asset, inv in inv_weights.items()))
    return portfolio
