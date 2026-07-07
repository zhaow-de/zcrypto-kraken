from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from itertools import combinations

from cli.validation.cpcv import make_groups
from cli.validation.errors import ValidationError


def pbo(
    perf_matrix: list[list[float]],
    *,
    n_splits: int = 16,
    metric: Callable[[list[float]], float] = statistics.mean,
) -> dict:
    """Probability of Backtest Overfitting via CSCV (see docs/specs/00008). Never returns NaN."""
    if n_splits < 2 or n_splits % 2 != 0:
        raise ValidationError(f"n_splits must be an even integer >= 2, got {n_splits}")
    if not perf_matrix:
        raise ValidationError("perf_matrix must be non-empty")
    n_cols = len(perf_matrix[0])
    if n_cols < 2:
        raise ValidationError(f"perf_matrix needs >= 2 configs (columns), got {n_cols}")
    for row in perf_matrix:
        if len(row) != n_cols:
            raise ValidationError("perf_matrix must be rectangular")
        for x in row:
            if not math.isfinite(x):
                raise ValidationError(f"perf_matrix cells must be finite, got {x}")

    groups = make_groups(len(perf_matrix), n_splits)  # raises if T < n_splits
    block_rows = [list(range(start, stop)) for start, stop in groups]

    overfit = 0
    total = 0
    for is_blocks in combinations(range(n_splits), n_splits // 2):
        is_set = set(is_blocks)
        is_rows = [i for b in is_blocks for i in block_rows[b]]
        oos_rows = [i for b in range(n_splits) if b not in is_set for i in block_rows[b]]
        is_perf = [metric([perf_matrix[i][j] for i in is_rows]) for j in range(n_cols)]
        oos_perf = [metric([perf_matrix[i][j] for i in oos_rows]) for j in range(n_cols)]
        for p in (*is_perf, *oos_perf):
            if not math.isfinite(p):
                raise ValidationError(f"metric returned a non-finite value ({p})")
        n_star = is_perf.index(max(is_perf))  # first argmax on ties
        v = oos_perf[n_star]
        less = sum(1 for p in oos_perf if p < v)
        equal = sum(1 for p in oos_perf if p == v)
        rank = less + (equal + 1) / 2
        w = rank / (n_cols + 1)
        if math.log(w / (1 - w)) < 0:
            overfit += 1
        total += 1
    return {"pbo": overfit / total, "n_combinations": total}
