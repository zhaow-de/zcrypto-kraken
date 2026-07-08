# Acceptance Suite (Recovery + Null) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `cli/validation/synthetic.py` + `tests/test_acceptance.py` per `docs/specs/00013-acceptance-recovery-null-design.md` — the first end-to-end acceptance test of the harness (recover a planted signal, reject a null).

**Architecture:** New module `cli/validation/synthetic.py` (generator + toy strategy) reusing `errors.ValidationError`; export both; a synthetic unit-test file + the acceptance-test file that composes CPCV + metrics + PSR. TDD.

**Tech Stack:** Python 3.14, stdlib `random`, `math`, `statistics`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. `random.Random(seed)` for reproducibility (seed required, `int`). Never crash weirdly: raise `ValidationError` on `n<1`, non-int seed/n, non-finite `beta`/`noise_sd`, `noise_sd<0`, length mismatch, empty, non-finite series values.
- Thresholds are **one-sided with wide margins** vs the spec's derived values (planted per-period Sharpe ≈ 0.38, PSR ≈ 1; null FP rate ≈ 5%). Do NOT loosen a threshold to force a pass — if one fails, STOP and report BLOCKED with the actual computed values.
- No CLI/README change.

---

### Task 1: `cli/validation/synthetic.py` + unit tests

**Files:**
- Create: `cli/validation/synthetic.py`; Test: `tests/test_validation_synthetic.py`
- Modify: `cli/validation/__init__.py` (export `linear_signal`, `sign_strategy_returns`)

- [ ] **Step 1: Write failing unit tests** in `tests/test_validation_synthetic.py`:

```python
import math
import statistics

import pytest

from cli.validation import ValidationError, linear_signal, sign_strategy_returns


def test_linear_signal_reproducible():
    a = linear_signal(50, beta=0.5, noise_sd=1.0, seed=1)
    b = linear_signal(50, beta=0.5, noise_sd=1.0, seed=1)
    assert a == b
    assert a != linear_signal(50, beta=0.5, noise_sd=1.0, seed=2)


def test_linear_signal_shape():
    x, r = linear_signal(100, beta=0.5, noise_sd=1.0, seed=3)
    assert len(x) == 100 and len(r) == 100
    assert all(math.isfinite(v) for v in [*x, *r])


def test_linear_signal_null_low_correlation():
    x, r = linear_signal(5000, beta=0.0, noise_sd=1.0, seed=4)
    assert abs(statistics.correlation(x, r)) < 0.1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n": 0, "beta": 0.5, "noise_sd": 1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": 1.0, "seed": "x"},
        {"n": 10, "beta": float("nan"), "noise_sd": 1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": -1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": float("inf"), "seed": 1},
    ],
)
def test_linear_signal_guards(kwargs):
    with pytest.raises(ValidationError):
        linear_signal(**kwargs)


def test_sign_strategy_returns_basic():
    assert sign_strategy_returns([1.0, -1.0, 0.5], [2.0, 3.0, 4.0]) == [2.0, -3.0, 4.0]
    assert sign_strategy_returns([0.0], [5.0]) == [5.0]  # sign at 0 -> +1


@pytest.mark.parametrize("features,targets", [([1.0], [1.0, 2.0]), ([], []), ([1.0, float("nan")], [1.0, 2.0])])
def test_sign_strategy_returns_guards(features, targets):
    with pytest.raises(ValidationError):
        sign_strategy_returns(features, targets)
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/test_validation_synthetic.py -q` → ImportError.

- [ ] **Step 3: Implement `cli/validation/synthetic.py`:**

```python
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
```

- [ ] **Step 4: Export** in `cli/validation/__init__.py` — add `linear_signal`, `sign_strategy_returns` (keep all existing exports; keep `__all__` alphabetized).

- [ ] **Step 5: Run unit tests, verify pass** — `uv run pytest tests/test_validation_synthetic.py -q`.

---

### Task 2: `tests/test_acceptance.py` — recovery + null

**Files:** Create: `tests/test_acceptance.py`

- [ ] **Step 1: Write the acceptance tests:**

```python
import statistics

from cli.validation import (
    cpcv_splits,
    linear_signal,
    probabilistic_sharpe_ratio,
    sharpe,
    sign_strategy_returns,
)

N = 2000


def _strategy_psr(*, beta, seed):
    x, r = linear_signal(N, beta=beta, noise_sd=1.0, seed=seed)
    return probabilistic_sharpe_ratio(sharpe(sign_strategy_returns(x, r)), N)


def test_planted_signal_recovered():
    x, r = linear_signal(N, beta=0.5, noise_sd=1.0, seed=42)
    s = sign_strategy_returns(x, r)
    sr = sharpe(s)
    assert sr > 0.25
    assert probabilistic_sharpe_ratio(sr, N) > 0.99
    path_sharpes = [sharpe([s[i] for i in split["test"]]) for split in cpcv_splits(N, n_groups=10, n_test_groups=2)]
    assert statistics.median(path_sharpes) > 0.1


def test_null_false_positive_rate_is_low():
    flagged = sum(1 for seed in range(20) if _strategy_psr(beta=0.0, seed=seed) > 0.95)
    assert flagged <= 4


def test_signal_beats_null_median():
    planted = _strategy_psr(beta=0.5, seed=42)
    null_median = statistics.median(_strategy_psr(beta=0.0, seed=seed) for seed in range(20))
    assert planted > null_median
```

- [ ] **Step 2: Run, verify pass** — `uv run pytest tests/test_acceptance.py -q`. If ANY assertion fails, STOP and report BLOCKED with the actual `sr`, `probabilistic_sharpe_ratio`, `median(path_sharpes)`, and `flagged` count — do NOT loosen a threshold.

- [ ] **Step 3: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 4: Commit** — `test(validation): add recovery + null acceptance suite on synthetic data`.

---

### Task 3: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-020: acceptance suite — recovery + null (Phase 2)`: `cli/validation/synthetic.py` (`linear_signal` generator + `sign_strategy_returns` toy strategy) + `tests/test_acceptance.py` — the first end-to-end composition of CPCV + metrics + PSR: a planted signal (beta>0) is recovered (Sharpe ≈ 0.38, PSR ≈ 1, positive median OOS path-Sharpe) and a null (beta=0) is rejected at ≈ the nominal 5% false-positive rate. Report the actual measured values (`sr`, `flagged`/20, median OOS). §12 exit-bar step; injected-leak + registry-corruption folded into the full suite next (iter-021). Spec/plan `00013`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-020 closeout — acceptance suite (recovery + null)`.
