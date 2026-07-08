from __future__ import annotations

import math
import random

from cli.validation.errors import ValidationError


def linear_signal(n: int, *, beta: float, noise_sd: float, seed: int) -> tuple[list[float], list[float]]:
    """Deterministic (x, r) with r = beta*x + noise_sd*eps; beta == 0 is a null. x, eps ~ N(0,1)."""
    if not isinstance(n, int) or n < 1:
        raise ValidationError(f"n must be an int >= 1, got {n!r}")
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    if not isinstance(beta, (int, float)):
        raise ValidationError(f"beta must be numeric, got {beta!r}")
    if not math.isfinite(beta):
        raise ValidationError(f"beta must be finite, got {beta}")
    if not isinstance(noise_sd, (int, float)):
        raise ValidationError(f"noise_sd must be numeric, got {noise_sd!r}")
    if not math.isfinite(noise_sd) or noise_sd < 0:
        raise ValidationError(f"noise_sd must be finite and >= 0, got {noise_sd}")
    rng = random.Random(seed)
    features: list[float] = []
    targets: list[float] = []
    for _ in range(n):
        x = rng.gauss(0.0, 1.0)
        features.append(x)
        targets.append(beta * x + noise_sd * rng.gauss(0.0, 1.0))
    return features, targets


def sign_strategy_returns(features: list[float], targets: list[float]) -> list[float]:
    """Toy strategy: position = sign(feature) (>=0 -> +1), return = position * target."""
    if len(features) != len(targets):
        raise ValidationError(f"features and targets must match in length ({len(features)} != {len(targets)})")
    if not features:
        raise ValidationError("features/targets must be non-empty")
    out: list[float] = []
    for x, r in zip(features, targets):
        if not math.isfinite(x) or not math.isfinite(r):
            raise ValidationError(f"non-finite value (x={x}, r={r})")
        out.append((1.0 if x >= 0 else -1.0) * r)
    return out


def overlapping_label_series(n: int, *, horizon: int, seed: int) -> tuple[list[float], list[float]]:
    """Feature x_t = t (index); label y_t = sum of `horizon` consecutive N(0,1) noise terms (overlapping labels).

    Cov(y_i, y_j) = horizon - |i-j| for |i-j| < horizon, else 0. x carries no signal — any OOS skill is leakage.
    """
    if not isinstance(n, int) or n < 1:
        raise ValidationError(f"n must be an int >= 1, got {n!r}")
    if not isinstance(horizon, int) or horizon < 1:
        raise ValidationError(f"horizon must be an int >= 1, got {horizon!r}")
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    rng = random.Random(seed)
    noise = [rng.gauss(0.0, 1.0) for _ in range(n + horizon - 1)]
    features = [float(t) for t in range(n)]
    labels = [sum(noise[t : t + horizon]) for t in range(n)]
    return features, labels


def nn_leak_metric(features: list[float], labels: list[float], train_idx: list[int], test_idx: list[int]) -> float:
    """Mean over test of labels[j*]*labels[i], where j* is the nearest train index by feature (ties: smaller
    |i-j|, then smaller j). With features=index this is a 1-NN-by-index leak probe."""
    if len(features) != len(labels):
        raise ValidationError(f"features and labels must match in length ({len(features)} != {len(labels)})")
    if not train_idx or not test_idx:
        raise ValidationError("train_idx and test_idx must be non-empty")
    size = len(features)
    for name, idxs in (("train_idx", train_idx), ("test_idx", test_idx)):
        for j in idxs:
            if not isinstance(j, int) or not (0 <= j < size):
                raise ValidationError(f"{name} contains an out-of-range/non-int index {j!r}")
    for v in (*features, *labels):
        if not math.isfinite(v):
            raise ValidationError(f"non-finite value {v}")
    train = list(train_idx)
    total = 0.0
    for i in test_idx:
        xi = features[i]
        best_j = min(train, key=lambda j: (abs(features[j] - xi), abs(j - i), j))
        total += labels[best_j] * labels[i]
    return total / len(test_idx)


def outperformance_matrix(n_periods: int, n_strategies: int, *, edge: float, seed: int, edge_col: int = 0) -> list[list[float]]:
    """T x K per-period outperformance-vs-benchmark matrix; column `edge_col` outperforms by `edge`/period."""
    if not isinstance(n_periods, int) or n_periods < 1:
        raise ValidationError(f"n_periods must be an int >= 1, got {n_periods!r}")
    if not isinstance(n_strategies, int) or n_strategies < 1:
        raise ValidationError(f"n_strategies must be an int >= 1, got {n_strategies!r}")
    if not isinstance(edge, (int, float)) or not math.isfinite(edge):
        raise ValidationError(f"edge must be a finite number, got {edge!r}")
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    if not isinstance(edge_col, int) or not (0 <= edge_col < n_strategies):
        raise ValidationError(f"edge_col must be an int in [0, {n_strategies}), got {edge_col!r}")
    rng = random.Random(seed)
    matrix: list[list[float]] = []
    for _ in range(n_periods):
        row = [rng.gauss(0.0, 1.0) for _ in range(n_strategies)]
        row[edge_col] += edge
        matrix.append(row)
    return matrix
