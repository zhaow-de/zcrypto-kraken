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
    """B1 — scale exposure toward `target_vol` (per period) from the realized vol of the prior `lookback` returns.

    position[t] = min(target_vol / stdev(returns[t-lookback:t]), max_leverage), or 0.0 for t < lookback or a
    zero-vol window. The window `returns[t-lookback:t]` excludes t, so position[t] never uses return[t]
    (no look-ahead); the backtester then applies position[t] to return[t].
    """
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
    """Long/flat 200-day-style regime gate: signal[k] = 1.0 if prices[k] > SMA(prices[k-window+1:k+1]) else 0.0.

    Returns length len(prices)-1, aligned with returns_from_prices(prices) (element k = the move prices[k] ->
    prices[k+1]). signal[k] uses only prices[<= k] (through prices[k], the price at the start of return-period
    k) and never prices[k+1] -> no look-ahead. Warm-up (k < window-1) is 0.0.
    """
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
    """Inverse-vol-weighted basket net return series (B2), look-ahead-free.

    Each price series must be pre-aligned to the same length L. For return-period
    t >= lookback, weight asset i by 1 / stdev(returns_i[t-lookback:t]) (the window
    strictly before t), normalized over assets with positive trailing vol, and apply
    to returns_i[t]. Warm-up (t < lookback) and days with no positive-vol asset are 0.0.
    """
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
    """Dynamic-composition inverse-vol basket over a union calendar, look-ahead-free.

    Generalizes `inverse_vol_basket` to a union calendar where a day is `None` when an asset is absent
    (pre-listing or a data gap). Each series must be pre-aligned to the same length L; every element is
    either `None` or a finite positive float. Per asset, ret_i[t] = prices_i[t+1]/prices_i[t] - 1 iff both
    are present and positive, else `None`. For return-period t, asset i qualifies iff (a) ret_i[t] is
    present, (b) its trailing window ret_i[t-lookback:t] (strictly before t) is fully populated (no `None`),
    and (c) that window has positive stdev; qualifying assets are weighted 1/stdev and renormalized over the
    qualifying set for that period. No qualifier -> 0.0. Strictly causal: period t's weights use only
    returns strictly before t.
    """
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
