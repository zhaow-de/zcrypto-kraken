from __future__ import annotations

import math
import statistics

from cli.validation.errors import ValidationError


def _check_returns(returns: list[float], *, min_len: int) -> None:
    if len(returns) < min_len:
        raise ValidationError(f"returns must have >= {min_len} values, got {len(returns)}")
    for r in returns:
        if not math.isfinite(r):
            raise ValidationError(f"returns must be finite, got {r}")


def _check_periods_per_year(periods_per_year: int | None, *, required: bool) -> None:
    if periods_per_year is None:
        if required:
            raise ValidationError("periods_per_year is required")
        return
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValidationError(f"periods_per_year must be a positive int, got {periods_per_year!r}")


def sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float:
    """Per-period Sharpe (sample stdev), optionally annualized by sqrt(periods_per_year). Never NaN."""
    _check_returns(returns, min_len=2)
    if not isinstance(risk_free, (int, float)):
        raise ValidationError(f"risk_free must be numeric, got {risk_free!r}")
    if not math.isfinite(risk_free):
        raise ValidationError(f"risk_free must be finite, got {risk_free}")
    _check_periods_per_year(periods_per_year, required=False)
    std = statistics.stdev(returns)
    if std == 0:
        raise ValidationError("returns have zero variance; Sharpe is undefined")
    ratio = (statistics.mean(returns) - risk_free) / std
    if periods_per_year is not None:
        ratio *= math.sqrt(periods_per_year)
    return ratio


def volatility(returns: list[float], *, periods_per_year: int | None = None) -> float:
    """Per-period sample stdev of returns, optionally annualized by sqrt(periods_per_year)."""
    _check_returns(returns, min_len=2)
    _check_periods_per_year(periods_per_year, required=False)
    vol = statistics.stdev(returns)
    if periods_per_year is not None:
        vol *= math.sqrt(periods_per_year)
    return vol


def annualized_return(returns: list[float], *, periods_per_year: int) -> float:
    """Geometric annualized return: prod(1 + r) ** (periods_per_year / n) - 1. Never NaN."""
    _check_returns(returns, min_len=1)
    _check_periods_per_year(periods_per_year, required=True)
    cumulative = 1.0
    for r in returns:
        growth = 1 + r
        if growth <= 0:
            raise ValidationError(f"a period return <= -100% (1+r={growth}) breaks compounding")
        cumulative *= growth
    return cumulative ** (periods_per_year / len(returns)) - 1


def max_drawdown(returns: list[float]) -> float:
    """Worst peak-to-trough decline on the equity curve, as a non-negative fraction. Never NaN."""
    _check_returns(returns, min_len=1)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        growth = 1 + r
        if growth <= 0:
            raise ValidationError(f"a period return <= -100% (1+r={growth}) breaks the equity curve")
        equity *= growth
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    return max_dd
