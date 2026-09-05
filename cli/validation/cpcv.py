from __future__ import annotations

import math
from itertools import combinations

from cli.validation.errors import ValidationError


def make_groups(n_samples: int, n_groups: int) -> list[tuple[int, int]]:
    """Partition [0, n_samples) into n_groups contiguous [start, stop) blocks whose sizes differ by at most 1."""
    if n_groups < 2:
        raise ValidationError(f"n_groups must be >= 2, got {n_groups}")
    if n_samples < n_groups:
        raise ValidationError(f"n_samples ({n_samples}) must be >= n_groups ({n_groups})")
    base, extra = divmod(n_samples, n_groups)
    groups, start = [], 0
    for i in range(n_groups):
        stop = start + base + (1 if i < extra else 0)
        groups.append((start, stop))
        start = stop
    return groups


def n_backtest_paths(n_groups: int, n_test_groups: int) -> int:
    """Number of CPCV backtest paths = C(n_groups - 1, n_test_groups - 1)."""
    if n_groups < 2:
        raise ValidationError(f"n_groups must be >= 2, got {n_groups}")
    if not 1 <= n_test_groups < n_groups:
        raise ValidationError(f"n_test_groups must satisfy 1 <= k < n_groups, got {n_test_groups}")
    return math.comb(n_groups - 1, n_test_groups - 1)


def _contiguous_blocks(positions: list[int]) -> list[tuple[int, int]]:
    """Maximal contiguous runs [a, b] (inclusive) in an ascending list of positions."""
    blocks: list[tuple[int, int]] = []
    start = prev = None
    for p in positions:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            blocks.append((start, prev))
            start = prev = p
    if start is not None:
        blocks.append((start, prev))
    return blocks


def cpcv_splits(
    n_samples: int,
    *,
    n_groups: int = 10,
    n_test_groups: int = 2,
    label_horizon: int = 0,
    embargo: int = 0,
) -> list[dict]:
    """Combinatorial purged cross-validation splits (see docs/specs/00006)."""
    if label_horizon < 0:
        raise ValidationError(f"label_horizon must be >= 0, got {label_horizon}")
    if embargo < 0:
        raise ValidationError(f"embargo must be >= 0, got {embargo}")
    # make_groups + the n_test_groups bound raise ValidationError on the remaining invalid params.
    groups = make_groups(n_samples, n_groups)
    if not 1 <= n_test_groups < n_groups:
        raise ValidationError(f"n_test_groups must satisfy 1 <= k < n_groups, got {n_test_groups}")

    group_positions = [list(range(start, stop)) for start, stop in groups]
    splits: list[dict] = []
    for test_groups in combinations(range(n_groups), n_test_groups):
        test = sorted(p for gi in test_groups for p in group_positions[gi])
        removed = set(test)
        for a, b in _contiguous_blocks(test):
            removed.update(range(max(0, a - label_horizon), a))  # purge: forward-label leak
            removed.update(range(b + 1, min(n_samples, b + 1 + embargo)))  # embargo after block
        train = [p for p in range(n_samples) if p not in removed]
        splits.append({"test_groups": test_groups, "train": train, "test": test})
    return splits
