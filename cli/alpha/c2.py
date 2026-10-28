"""C2's lead-lag reading: the pure functions (docs/specs/00150-c2-lead-lag-reading-design.md D3, D4, D6)."""

from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta

import polars as pl

from cli.alpha.errors import AlphaError
from cli.validation.spa import reality_check_pvalue

STEP = timedelta(minutes=15)
LAGS = (1, 4)
THRESHOLDS = (1, 2)
HORIZONS = (1, 4)
SIDES = ("up", "down")
COST_ROUND_TRIP = 0.012
SIGMA_WINDOW = 96
MEAN_BLOCK = 30
N_RESAMPLES = 4000
SEED = 42
LEADER = "BTC/EUR"
FOLLOWERS = (
    "ADA/EUR",
    "AVAX/EUR",
    "DOGE/EUR",
    "DOT/EUR",
    "ETH/EUR",
    "LINK/EUR",
    "LTC/EUR",
    "SOL/EUR",
    "XRP/EUR",
    "ETH/BTC",
    "SOL/BTC",
)


def log_returns(ts: list[datetime], close: list[float]) -> list[float | None]:
    if len(ts) != len(close):
        raise AlphaError(f"the {len(ts)} stamps and the {len(close)} closes must be equal in number")
    out: list[float | None] = [None] * len(ts)
    for i in range(1, len(ts)):
        if ts[i] - ts[i - 1] == STEP:
            out[i] = math.log(close[i] / close[i - 1])
    return out


def trailing_std(values: list[float | None], *, window: int = SIGMA_WINDOW) -> list[float | None]:
    """`min_samples=window` counts present values only, so a None anywhere inside the window gives None."""
    series = pl.Series(values, dtype=pl.Float64)
    return series.rolling_std(window_size=window, min_samples=window).to_list()


def moves(returns: list[float | None], *, lag: int) -> list[float | None]:
    out: list[float | None] = [None] * len(returns)
    for t in range(lag - 1, len(returns)):
        window = returns[t - lag + 1 : t + 1]
        out[t] = None if None in window else math.fsum(window)
    return out


def signals(moves_l: list[float | None], sigma: list[float | None], *, lag: int, threshold: float) -> list[int]:
    out: list[int] = []
    for x, s in zip(moves_l, sigma, strict=True):
        if x is None or s is None:
            out.append(0)
        elif x > threshold * s * math.sqrt(lag):
            out.append(1)
        elif x < -threshold * s * math.sqrt(lag):
            out.append(-1)
        else:
            out.append(0)
    return out


def on_grid(grid: list[datetime], ts: list[datetime], close: list[float]) -> tuple[list[float | None], int, int]:
    index: dict[datetime, int] = {}
    for i, stamp in enumerate(grid):
        if stamp in index:
            raise AlphaError(f"the leader's grid holds a duplicate stamp {stamp.isoformat()}, at indices {index[stamp]} and {i}")
        index[stamp] = i
    placed: list[float | None] = [None] * len(grid)
    n_on = n_off = 0
    for stamp, c in zip(ts, close, strict=True):
        k = index.get(stamp)
        if k is None:
            n_off += 1
        else:
            placed[k] = c
            n_on += 1
    return placed, n_on, n_off


def forward_returns(grid: list[datetime], close_on_grid: list[float | None], *, horizon: int) -> list[float | None]:
    if len(grid) != len(close_on_grid):
        raise AlphaError(f"the {len(grid)} grid stamps and the {len(close_on_grid)} closes must be equal in number")
    out: list[float | None] = [None] * len(grid)
    for t in range(len(grid) - horizon):
        if not all(grid[k + 1] - grid[k] == STEP for k in range(t, t + horizon)):
            continue
        if any(close_on_grid[k] is None for k in range(t, t + horizon + 1)):
            continue
        out[t] = math.log(close_on_grid[t + horizon] / close_on_grid[t])
    return out


def _means(gross: list[float], cost: float) -> dict:
    if not gross:
        return {"n": 0}
    return {"n": len(gross), "mean_gross": statistics.fmean(gross), "mean_net": statistics.fmean([g - cost for g in gross])}


def cell_reads(
    signal: list[int],
    side: str,
    forward: list[float | None],
    years: list[int],
    *,
    cost: float = COST_ROUND_TRIP,
    mean_block: float = MEAN_BLOCK,
    n_resamples: int = N_RESAMPLES,
    seed: int = SEED,
) -> dict:
    """A figure that cannot be read is an absent key, never None: the registry refuses a null leaf (spec D6)."""
    if side not in SIDES:
        raise AlphaError(f"side must be one of {SIDES}, got {side!r}")
    if not len(signal) == len(forward) == len(years):
        raise AlphaError(
            f"the {len(signal)} signals, {len(forward)} forward returns and {len(years)} years must be equal in number"
        )
    want = 1 if side == "up" else -1
    gross_at: list[float | None] = [None] * len(signal)
    for i, s in enumerate(signal):
        if s == want and forward[i] is not None:
            gross_at[i] = forward[i] if side == "up" else -forward[i]
    gross = [g for g in gross_at if g is not None]
    out = {"per_year": {year: _means(gs, cost) for year, gs in per_year(gross_at, years).items()}, **_means(gross, cost)}
    if len(gross) >= 2:
        matrix = [[g - cost] for g in gross]
        out["p"] = reality_check_pvalue(matrix, mean_block=mean_block, n_resamples=n_resamples, seed=seed)["p_value"]
    return out


def rank_ic(x: list[float | None], y: list[float | None]) -> float | None:
    """None where `statistics.correlation` refuses: fewer than 2 pairs, or a side with no variance."""
    pairs = [(a, b) for a, b in zip(x, y, strict=True) if a is not None and b is not None]
    try:
        return statistics.correlation([a for a, _ in pairs], [b for _, b in pairs], method="ranked")
    except statistics.StatisticsError:
        return None


def per_year(values: list[float | None], years: list[int]) -> dict[str, list[float]]:
    out: dict[str, list[float]] = {str(year): [] for year in sorted(set(years))}
    for v, year in zip(values, years, strict=True):
        if v is not None:
            out[str(year)].append(v)
    return out


def cell_name(follower: str, lag: int, threshold: int, horizon: int, side: str) -> str:
    return f"{follower}|L{lag}|th{threshold}|H{horizon}|{side}"
