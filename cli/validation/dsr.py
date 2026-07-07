from __future__ import annotations

import math
from statistics import NormalDist

from cli.validation.errors import ValidationError

_EULER_MASCHERONI = 0.5772156649015329
_NORM = NormalDist()


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """Expected maximum of `n_trials` i.i.d. N(0, var_trials) trial Sharpes (Bailey & Lopez de Prado)."""
    if n_trials < 1:
        raise ValidationError(f"n_trials must be >= 1, got {n_trials}")
    if not math.isfinite(var_trials) or var_trials < 0:
        raise ValidationError(f"var_trials must be finite and >= 0, got {var_trials}")
    if n_trials == 1 or var_trials == 0:
        return 0.0
    g = _EULER_MASCHERONI
    sr0 = math.sqrt(var_trials) * ((1 - g) * _NORM.inv_cdf(1 - 1 / n_trials) + g * _NORM.inv_cdf(1 - 1 / (n_trials * math.e)))
    return sr0


def probabilistic_sharpe_ratio(
    sr: float,
    n_obs: int,
    *,
    benchmark_sr: float = 0.0,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Probability the true Sharpe exceeds `benchmark_sr` (Bailey & Lopez de Prado PSR). Never returns NaN."""
    if n_obs < 2:
        raise ValidationError(f"n_obs must be >= 2, got {n_obs}")
    for name, value in (("sr", sr), ("benchmark_sr", benchmark_sr), ("skew", skew), ("kurtosis", kurtosis)):
        if not math.isfinite(value):
            raise ValidationError(f"{name} must be finite, got {value}")
    denom = 1 - skew * sr + (kurtosis - 1) / 4 * sr**2
    if denom <= 0:
        raise ValidationError(f"non-positive Sharpe-SE denominator ({denom}); degenerate skew/kurtosis")
    z = (sr - benchmark_sr) * math.sqrt(n_obs - 1) / math.sqrt(denom)
    return _NORM.cdf(z)


def deflated_sharpe_ratio(
    sr: float,
    n_obs: int,
    n_trials: int,
    var_trials: float,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Deflated Sharpe Ratio: PSR with the benchmark set to the expected max Sharpe over `n_trials`."""
    benchmark = expected_max_sharpe(n_trials, var_trials)
    return probabilistic_sharpe_ratio(sr, n_obs, benchmark_sr=benchmark, skew=skew, kurtosis=kurtosis)
