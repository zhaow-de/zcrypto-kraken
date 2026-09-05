from __future__ import annotations

import math

from cli.backtest.errors import BacktestError
from cli.validation import ValidationError, annualized_return, max_drawdown, sharpe


def run_backtest(asset_returns: list[float], positions: list[float], *, fee_rate: float = 0.0, periods_per_year: int) -> dict:
    """Net returns and metrics from target positions, less fee_rate per unit of turnover from a flat start (spec 00016).

    positions[t] is held during period t and must be set from pre-t information; a degenerate or blown-up run raises, never NaN.
    """
    if len(asset_returns) != len(positions):
        raise BacktestError(f"asset_returns and positions must match in length ({len(asset_returns)} != {len(positions)})")
    n = len(asset_returns)
    if n < 2:
        raise BacktestError(f"need >= 2 periods, got {n}")
    for name, seq in (("asset_returns", asset_returns), ("positions", positions)):
        for v in seq:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise BacktestError(f"{name} must be finite numbers, got {v!r}")
    if not isinstance(fee_rate, (int, float)) or not math.isfinite(fee_rate) or fee_rate < 0:
        raise BacktestError(f"fee_rate must be a finite number >= 0, got {fee_rate!r}")
    if not isinstance(periods_per_year, int) or periods_per_year < 1:
        raise BacktestError(f"periods_per_year must be a positive int, got {periods_per_year!r}")

    net: list[float] = []
    prev = 0.0
    for t in range(n):
        turnover = abs(positions[t] - prev)
        net.append(positions[t] * asset_returns[t] - turnover * fee_rate)
        prev = positions[t]

    try:
        sr = sharpe(net, periods_per_year=periods_per_year)
        mdd = max_drawdown(net)
        ann = annualized_return(net, periods_per_year=periods_per_year)
    except ValidationError as exc:
        raise BacktestError(f"degenerate backtest: {exc}") from exc

    total_return = 1.0
    for r in net:
        total_return *= 1 + r
    total_return -= 1

    return {
        "net_returns": net,
        "total_return": total_return,
        "sharpe": sr,
        "max_drawdown": mdd,
        "annualized_return": ann,
        "n_periods": n,
    }
