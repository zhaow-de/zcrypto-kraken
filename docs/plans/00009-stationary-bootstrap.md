# Stationary Block Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `stationary_bootstrap_indices` + `bootstrap_ci` to `cli/validation/` per `docs/specs/00009-stationary-bootstrap-design.md` — seeded/reproducible, never-NaN percentile CIs.

**Architecture:** New module `cli/validation/bootstrap.py` reusing `errors.ValidationError`; export both from `__init__.py`. TDD.

**Tech Stack:** Python 3.14, stdlib `random` (seeded), `math`, `collections.abc.Callable`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. `random.Random(seed)` for reproducibility (seed required, `int`).
- **Never crash weirdly:** raise `ValidationError` on non-finite series value, `mean_block < 1`/`inf`, `n_resamples < 1`, `alpha ∉ (0,1)`, empty series, non-`int` seed, a `statistic` that returns non-finite OR raises.
- Stationary bootstrap exactly per spec: restart prob `p = 1/mean_block`; start at `rng.randrange(n)`; else advance `(i+1) % n`. Percentile via linear interpolation.
- Return `{"point", "lower", "upper", "n_resamples", "mean_block"}` with `lower <= upper`. No CLI/README change.

---

### Task 1: `cli/validation/bootstrap.py`

**Files:**
- Create: `cli/validation/bootstrap.py`
- Modify: `cli/validation/__init__.py` (add 2 exports)
- Test: `tests/test_validation_bootstrap.py`

**Interfaces:**
- Produces: `stationary_bootstrap_indices(n_obs, *, mean_block, n_resamples, seed) -> list[list[int]]`; `bootstrap_ci(series, statistic, *, mean_block, n_resamples=1000, alpha=0.05, seed) -> dict`.
- Consumes: `cli.validation.errors.ValidationError`.

- [ ] **Step 1: Write failing tests** in `tests/test_validation_bootstrap.py`:

```python
import math
import statistics

import pytest

from cli.validation import ValidationError, bootstrap_ci, stationary_bootstrap_indices


def test_indices_reproducible_and_bounded():
    a = stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed=1)
    b = stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed=1)
    assert a == b
    assert len(a) == 5 and all(len(r) == 10 for r in a)
    assert all(0 <= i < 10 for r in a for i in r)


def test_indices_different_seed_differs():
    a = stationary_bootstrap_indices(50, mean_block=5, n_resamples=3, seed=1)
    b = stationary_bootstrap_indices(50, mean_block=5, n_resamples=3, seed=2)
    assert a != b


def test_indices_mean_block_one_is_valid():
    a = stationary_bootstrap_indices(8, mean_block=1, n_resamples=4, seed=1)
    assert len(a) == 4 and all(len(r) == 8 and all(0 <= i < 8 for i in r) for r in a)


def test_ci_reproducible():
    kw = dict(mean_block=4, n_resamples=200, seed=7)
    assert bootstrap_ci([float(i % 5) for i in range(40)], statistics.mean, **kw) == bootstrap_ci(
        [float(i % 5) for i in range(40)], statistics.mean, **kw
    )


def test_ci_constant_series_is_exact():
    r = bootstrap_ci([5.0] * 20, statistics.mean, mean_block=4, seed=7)
    assert r["point"] == 5.0 and r["lower"] == 5.0 and r["upper"] == 5.0
    assert r["n_resamples"] == 1000 and r["mean_block"] == 4


def test_ci_varied_series_has_positive_width():
    r = bootstrap_ci([float(i) for i in range(50)], statistics.mean, mean_block=5, n_resamples=500, seed=3)
    assert math.isfinite(r["lower"]) and math.isfinite(r["upper"]) and math.isfinite(r["point"])
    assert r["lower"] < r["upper"]


@pytest.mark.parametrize(
    "series,kwargs",
    [
        ([], {"mean_block": 3, "seed": 1}),
        ([1.0, float("nan"), 2.0], {"mean_block": 3, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 0.5, "seed": 1}),
        ([1.0, 2.0], {"mean_block": float("inf"), "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "n_resamples": 0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "alpha": 0.0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "alpha": 1.0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "seed": "x"}),
    ],
)
def test_ci_guards(series, kwargs):
    with pytest.raises(ValidationError):
        bootstrap_ci(series, statistics.mean, **kwargs)


def test_ci_statistic_returning_nan_raises():
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: float("nan"), mean_block=2, seed=1)


def test_ci_statistic_that_raises_is_validation_error():
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: xs[10**9], mean_block=2, seed=1)


def test_indices_guards():
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(0, mean_block=3, n_resamples=5, seed=1)
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed="x")
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_validation_bootstrap.py -q` → ImportError.

- [ ] **Step 3: Implement `cli/validation/bootstrap.py`:**

```python
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
    if n_obs < 1:
        raise ValidationError(f"n_obs must be >= 1, got {n_obs}")
    if not math.isfinite(mean_block) or mean_block < 1:
        raise ValidationError(f"mean_block must be finite and >= 1, got {mean_block}")
    if n_resamples < 1:
        raise ValidationError(f"n_resamples must be >= 1, got {n_resamples}")
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
    if n_resamples < 1:
        raise ValidationError(f"n_resamples must be >= 1, got {n_resamples}")
    if not 0 < alpha < 1:
        raise ValidationError(f"alpha must be in (0, 1), got {alpha}")

    def _stat(values: list[float]) -> float:
        try:
            s = statistic(values)
        except Exception as exc:
            raise ValidationError(f"statistic raised: {exc!r}") from exc
        if not math.isfinite(s):
            raise ValidationError(f"statistic returned a non-finite value ({s})")
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
```

- [ ] **Step 4: Extend `cli/validation/__init__.py`** — add `bootstrap_ci`, `stationary_bootstrap_indices` to imports + `__all__` (keep all existing exports; keep `__all__` alphabetized).

- [ ] **Step 5: Run tests, verify they pass** — `uv run pytest tests/test_validation_bootstrap.py -q`.

- [ ] **Step 6: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 7: Commit** — `feat(validation): add stationary block bootstrap CIs`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-016: stationary block bootstrap CIs (Phase 2)`: `cli/validation/bootstrap.py` — Politis & Romano resampling (geometric blocks, wrap-around) → seeded/reproducible percentile CI of a caller-supplied statistic; never-NaN (raises on non-finite series/statistic or a raising statistic); property-tested (reproducibility, index bounds, constant-series exact, guards); §9.5 uncertainty layer; spec/plan `00009`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-016 closeout — stationary block bootstrap`.
