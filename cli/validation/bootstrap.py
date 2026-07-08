from __future__ import annotations

import math
import random
from collections.abc import Callable

from cli.validation.errors import ValidationError


def _percentile(sorted_vals: list[float], q: float) -> float:
    m = len(sorted_vals)
    if m == 1:
        return sorted_vals[0]
    pos = q * (m - 1)
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def stationary_bootstrap_indices(n_obs: int, *, mean_block: float, n_resamples: int, seed: int) -> list[list[int]]:
    """Stationary-bootstrap (Politis & Romano) resample index sequences; deterministic given `seed`."""
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    if not isinstance(n_obs, int) or n_obs < 1:
        raise ValidationError(f"n_obs must be an int >= 1, got {n_obs!r}")
    if not math.isfinite(mean_block) or mean_block < 1:
        raise ValidationError(f"mean_block must be finite and >= 1, got {mean_block}")
    if not isinstance(n_resamples, int) or n_resamples < 1:
        raise ValidationError(f"n_resamples must be an int >= 1, got {n_resamples!r}")
    rng = random.Random(seed)
    p = 1 / mean_block
    resamples: list[list[int]] = []
    for _ in range(n_resamples):
        idx = [rng.randrange(n_obs)]
        for _ in range(n_obs - 1):
            idx.append(rng.randrange(n_obs) if rng.random() < p else (idx[-1] + 1) % n_obs)
        resamples.append(idx)
    return resamples


def bootstrap_ci(
    series: list[float],
    statistic: Callable[[list[float]], float],
    *,
    mean_block: float,
    n_resamples: int = 1000,
    alpha: float = 0.05,
    seed: int,
) -> dict:
    """Percentile CI of `statistic` under the stationary block bootstrap (see docs/specs/00009). Never NaN."""
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    if not series:
        raise ValidationError("series must be non-empty")
    for x in series:
        if not math.isfinite(x):
            raise ValidationError(f"series values must be finite, got {x}")
    if not math.isfinite(mean_block) or mean_block < 1:
        raise ValidationError(f"mean_block must be finite and >= 1, got {mean_block}")
    if not isinstance(n_resamples, int) or n_resamples < 1:
        raise ValidationError(f"n_resamples must be an int >= 1, got {n_resamples!r}")
    if not 0 < alpha < 1:
        raise ValidationError(f"alpha must be in (0, 1), got {alpha}")

    def _stat(values: list[float]) -> float:
        try:
            s = statistic(values)
            if not math.isfinite(s):
                raise ValidationError(f"statistic returned a non-finite value ({s})")
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError(f"statistic raised: {exc!r}") from exc
        return s

    point = _stat(series)
    resamples = stationary_bootstrap_indices(len(series), mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    stats = sorted(_stat([series[i] for i in idx]) for idx in resamples)
    return {
        "point": point,
        "lower": _percentile(stats, alpha / 2),
        "upper": _percentile(stats, 1 - alpha / 2),
        "n_resamples": n_resamples,
        "mean_block": mean_block,
    }
