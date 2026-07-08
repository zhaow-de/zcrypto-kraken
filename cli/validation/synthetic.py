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
    if not math.isfinite(beta):
        raise ValidationError(f"beta must be finite, got {beta}")
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
