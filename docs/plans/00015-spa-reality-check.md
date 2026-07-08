# SPA / Reality Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `reality_check_pvalue` (`cli/validation/spa.py`) + `outperformance_matrix` (`cli/validation/synthetic.py`) per `docs/specs/00015-spa-reality-check-design.md` — White's Reality Check reusing the stationary bootstrap; never NaN.

**Architecture:** New module `cli/validation/spa.py` reusing `stationary_bootstrap_indices` + `errors.ValidationError`; append a generator to `synthetic.py`; export both; a unit-test file + an acceptance-test file. TDD.

**Tech Stack:** Python 3.14, stdlib `math`, `random`, `statistics`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only; reuse `cli.validation.bootstrap.stationary_bootstrap_indices`. Guards raise `ValidationError`; `p_value = (1+count)/(n_resamples+1) ∈ (0,1]` (never NaN, never 0). Do NOT loosen acceptance thresholds — STOP + report BLOCKED with actuals. No CLI/README change.

---

### Task 1: `outperformance_matrix` generator + unit tests

**Files:** Modify `cli/validation/synthetic.py`, `cli/validation/__init__.py`, `tests/test_validation_synthetic.py`.

- [ ] **Step 1: Append failing unit tests** to `tests/test_validation_synthetic.py`:

```python
def test_outperformance_matrix_reproducible_and_shaped():
    a = outperformance_matrix(30, 4, edge=0.5, seed=1)
    assert a == outperformance_matrix(30, 4, edge=0.5, seed=1)
    assert len(a) == 30 and all(len(r) == 4 for r in a)


def test_outperformance_matrix_edge_column_leads():
    m = outperformance_matrix(5000, 4, edge=0.5, seed=2, edge_col=1)
    means = [statistics.mean(row[k] for row in m) for k in range(4)]
    assert means[1] == pytest.approx(0.5, abs=0.1)
    assert all(abs(means[k]) < 0.1 for k in (0, 2, 3))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_periods": 0, "n_strategies": 3, "edge": 0.1, "seed": 1},
        {"n_periods": 10, "n_strategies": 0, "edge": 0.1, "seed": 1},
        {"n_periods": 10, "n_strategies": 3, "edge": "x", "seed": 1},
        {"n_periods": 10, "n_strategies": 3, "edge": 0.1, "seed": "x"},
        {"n_periods": 10, "n_strategies": 3, "edge": 0.1, "seed": 1, "edge_col": 3},
    ],
)
def test_outperformance_matrix_guards(kwargs):
    with pytest.raises(ValidationError):
        outperformance_matrix(**kwargs)
```

(`outperformance_matrix` must be added to the existing `from cli.validation import ...` line in that test file.)

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Append to `cli/validation/synthetic.py`:**

```python
def outperformance_matrix(
    n_periods: int, n_strategies: int, *, edge: float, seed: int, edge_col: int = 0
) -> list[list[float]]:
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
```

- [ ] **Step 4: Export** `outperformance_matrix` in `cli/validation/__init__.py` (keep existing; `__all__` alphabetized).
- [ ] **Step 5: Run unit tests, verify pass.**

---

### Task 2: `cli/validation/spa.py` + unit tests

**Files:** Create `cli/validation/spa.py`, `tests/test_validation_spa.py`; modify `cli/validation/__init__.py`.

- [ ] **Step 1: Write failing tests** in `tests/test_validation_spa.py`:

```python
import pytest

from cli.validation import ValidationError, outperformance_matrix, reality_check_pvalue


def test_reality_check_reproducible():
    m = outperformance_matrix(200, 4, edge=0.0, seed=1)
    a = reality_check_pvalue(m, mean_block=5, n_resamples=100, seed=9)
    b = reality_check_pvalue(m, mean_block=5, n_resamples=100, seed=9)
    assert a == b


def test_reality_check_shape_and_best():
    # column 2 dominates deterministically
    m = [[0.0, 0.0, 5.0, 0.0] for _ in range(50)]
    r = reality_check_pvalue(m, mean_block=4, n_resamples=100, seed=1)
    assert r["best_strategy"] == 2
    assert r["statistic"] == pytest.approx(5.0)
    assert 0.0 < r["p_value"] <= 1.0
    assert r["n_resamples"] == 100


@pytest.mark.parametrize(
    "matrix",
    [
        [[1.0, 2.0]],                       # T < 2
        [[], []],                           # K < 1
        [[1.0, 2.0], [3.0]],                # non-rectangular
        [[1.0, 2.0], [float("nan"), 3.0]],  # non-finite
    ],
)
def test_reality_check_guards(matrix):
    with pytest.raises(ValidationError):
        reality_check_pvalue(matrix, mean_block=2, n_resamples=50, seed=1)
```

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Implement `cli/validation/spa.py`:**

```python
from __future__ import annotations

import math

from cli.validation.bootstrap import stationary_bootstrap_indices
from cli.validation.errors import ValidationError


def reality_check_pvalue(
    perf_matrix: list[list[float]], *, mean_block: float, n_resamples: int = 1000, seed: int
) -> dict:
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
```

- [ ] **Step 4: Export** `reality_check_pvalue` in `cli/validation/__init__.py`.
- [ ] **Step 5: Run unit tests, verify pass.**

---

### Task 3: `tests/test_acceptance_spa.py`

- [ ] **Step 1: Write the acceptance tests:**

```python
from cli.validation import outperformance_matrix, reality_check_pvalue

T, K, N_RESAMPLES, MB = 300, 5, 200, 5


def test_spa_detects_a_superior_strategy():
    m = outperformance_matrix(T, K, edge=0.3, seed=1)
    r = reality_check_pvalue(m, mean_block=MB, n_resamples=N_RESAMPLES, seed=2)
    assert r["best_strategy"] == 0
    assert r["p_value"] < 0.05


def test_spa_null_false_positive_rate_is_low():
    flagged = 0
    for seed in range(20):
        m = outperformance_matrix(T, K, edge=0.0, seed=seed)
        if reality_check_pvalue(m, mean_block=MB, n_resamples=N_RESAMPLES, seed=seed + 100)["p_value"] < 0.05:
            flagged += 1
    assert flagged <= 4
```

- [ ] **Step 2: Run, verify pass** — `uv run pytest tests/test_acceptance_spa.py -q`. If any fails, STOP + report BLOCKED with the actual planted `p_value` and the null `flagged` count — do NOT loosen.

- [ ] **Step 3: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` green. Note the SPA acceptance runtime.

- [ ] **Step 4: Commit** — `feat(validation): add SPA / White reality-check p-value`.

---

### Task 4: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-023: SPA / reality check (Phase 2)`: `cli/validation/spa.py` — `reality_check_pvalue` (White's Reality Check: statistic = best strategy's mean outperformance vs benchmark; stationary-bootstrap recentered null → p-value ∈ (0,1], never NaN; reuses iter-016's bootstrap) + `outperformance_matrix` scaffold; acceptance: a planted-superior family → p < 0.05 (report actual), an all-null family → FP rate ≈ nominal (report flagged/20). Completes §9.4's DSR+PBO+SPA; the benchmark family it runs against is Phase 3. Spec/plan `00015`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-023 closeout — SPA reality check`.
