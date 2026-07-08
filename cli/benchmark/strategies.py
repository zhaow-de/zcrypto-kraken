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
