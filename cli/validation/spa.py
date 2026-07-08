from __future__ import annotations

import math

from cli.validation.bootstrap import stationary_bootstrap_indices
from cli.validation.errors import ValidationError


def reality_check_pvalue(perf_matrix: list[list[float]], *, mean_block: float, n_resamples: int = 1000, seed: int) -> dict:
    """White's Reality Check: p-value that the best strategy's mean outperformance vs the benchmark is real.

    `perf_matrix` is T x K (rows = time, cols = strategies), each cell = strategy's outperformance vs the
    benchmark at that period. Reuses the stationary bootstrap. p_value in (0, 1], never NaN. See docs/specs/00015.
    """
    if not perf_matrix:
        raise ValidationError("perf_matrix must be non-empty")
    n_periods = len(perf_matrix)
    if n_periods < 2:
        raise ValidationError(f"perf_matrix needs >= 2 periods (rows), got {n_periods}")
    n_strats = len(perf_matrix[0])
    if n_strats < 1:
        raise ValidationError(f"perf_matrix needs >= 1 strategy (column), got {n_strats}")
    for row in perf_matrix:
        if len(row) != n_strats:
            raise ValidationError("perf_matrix must be rectangular")
        for v in row:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise ValidationError(f"perf_matrix cells must be finite numbers, got {v!r}")

    dbar = [sum(perf_matrix[t][k] for t in range(n_periods)) / n_periods for k in range(n_strats)]
    v_obs = max(dbar)
    resamples = stationary_bootstrap_indices(n_periods, mean_block=mean_block, n_resamples=n_resamples, seed=seed)
    count = 0
    for rows in resamples:
        m = len(rows)
        dbar_star = [sum(perf_matrix[t][k] for t in rows) / m for k in range(n_strats)]
        if max(dbar_star[k] - dbar[k] for k in range(n_strats)) >= v_obs:
            count += 1
    return {
        "p_value": (1 + count) / (n_resamples + 1),
        "statistic": v_obs,
        "best_strategy": dbar.index(v_obs),
        "n_resamples": n_resamples,
    }
