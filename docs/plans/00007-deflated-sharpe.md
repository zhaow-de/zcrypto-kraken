# Deflated & Probabilistic Sharpe Ratio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PSR / expected-max-Sharpe / DSR to `cli/validation/` per `docs/specs/00007-deflated-sharpe-design.md` — pure scalar functions, stdlib-only, that **never return NaN** (raise on degenerate input — the §7 PoC lesson).

**Architecture:** New module `cli/validation/dsr.py` reusing `cli/validation/errors.ValidationError`; export the three functions from `cli/validation/__init__.py`. TDD.

**Tech Stack:** Python 3.14, stdlib `statistics.NormalDist` (Φ = `.cdf`, Φ⁻¹ = `.inv_cdf`) + `math`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only; no scipy/numpy. `statistics.NormalDist`, `math.e`, `math.isfinite`, `math.comb` (n/a here).
- **NaN-refusal is the point:** any non-finite `sr/benchmark_sr/skew/kurtosis/var_trials`, `n_obs < 2`, `n_trials < 1`, `var_trials < 0`, or `denom <= 0` raises `ValidationError`. A valid call always returns a finite float in `[0, 1]` (PSR/DSR) or `≥ 0` (SR0).
- Formulas exactly as the spec: `SR0 = sqrt(V)·[(1-γ)·Φ⁻¹(1-1/N) + γ·Φ⁻¹(1-1/(N·e))]`, `γ = 0.5772156649015329`, `n_trials==1 → 0.0`; `PSR = Φ((sr-benchmark)·sqrt(T-1)/sqrt(1 - skew·sr + (kurtosis-1)/4·sr²))`; `DSR = PSR(benchmark = SR0)`.
- No CLI subcommand, no README change.

---

### Task 1: `cli/validation/dsr.py` (PSR + expected-max-Sharpe + DSR)

**Files:**
- Create: `cli/validation/dsr.py`
- Modify: `cli/validation/__init__.py` (add 3 exports)
- Test: `tests/test_validation_dsr.py`

**Interfaces:**
- Produces: `expected_max_sharpe(n_trials: int, var_trials: float) -> float`, `probabilistic_sharpe_ratio(sr: float, n_obs: int, *, benchmark_sr=0.0, skew=0.0, kurtosis=3.0) -> float`, `deflated_sharpe_ratio(sr: float, n_obs: int, n_trials: int, var_trials: float, *, skew=0.0, kurtosis=3.0) -> float`.
- Consumes: `cli.validation.errors.ValidationError`.

- [ ] **Step 1: Write failing tests** in `tests/test_validation_dsr.py`:

```python
import math

import pytest
from statistics import NormalDist

from cli.validation import (
    ValidationError,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)


def test_emp_single_trial_is_zero():
    assert expected_max_sharpe(1, 1.0) == 0.0


@pytest.mark.parametrize("n", [2, 10])
def test_emp_zero_variance_is_zero(n):
    assert expected_max_sharpe(n, 0.0) == 0.0


def test_emp_increases_with_trials():
    vals = [expected_max_sharpe(n, 1.0) for n in (2, 5, 10, 50)]
    assert vals == sorted(vals) and len(set(vals)) == 4


def test_emp_scales_with_sqrt_var():
    assert expected_max_sharpe(10, 4.0) == pytest.approx(2 * expected_max_sharpe(10, 1.0), rel=1e-12)


def test_emp_known_value():
    assert expected_max_sharpe(10, 1.0) == pytest.approx(1.574, abs=0.01)


@pytest.mark.parametrize("n,v", [(0, 1.0), (2, -1.0), (2, float("inf"))])
def test_emp_guards(n, v):
    with pytest.raises(ValidationError):
        expected_max_sharpe(n, v)


def test_psr_at_benchmark_is_half():
    assert probabilistic_sharpe_ratio(0.5, 100, benchmark_sr=0.5) == pytest.approx(0.5)


def test_psr_increasing_in_sr():
    a = probabilistic_sharpe_ratio(0.0, 100)
    b = probabilistic_sharpe_ratio(0.1, 100)
    c = probabilistic_sharpe_ratio(0.5, 100)
    assert a == pytest.approx(0.5) and a < b < c


def test_psr_bounded_and_high_sr_near_one():
    p = probabilistic_sharpe_ratio(2.0, 1000)
    assert 0.0 <= p <= 1.0 and p > 0.999


def test_psr_matches_normaldist_cdf():
    sr, t = 0.3, 250
    denom = 1 - 0.0 * sr + (3.0 - 1) / 4 * sr**2
    z = (sr - 0.0) * math.sqrt(t - 1) / math.sqrt(denom)
    assert probabilistic_sharpe_ratio(sr, t) == pytest.approx(NormalDist().cdf(z), rel=1e-12)


@pytest.mark.parametrize(
    "args,kwargs",
    [
        ((0.5, 1), {}),                       # n_obs < 2
        ((float("nan"), 100), {}),            # non-finite sr
        ((1.0, 100), {"skew": 5.0}),          # denom = 1 - 5 + 0.5 = -3.5 <= 0
    ],
)
def test_psr_guards_never_nan(args, kwargs):
    with pytest.raises(ValidationError):
        probabilistic_sharpe_ratio(*args, **kwargs)


def test_dsr_equals_psr_with_emp_benchmark():
    sr, t, n, v = 1.5, 250, 50, 1.0
    expected = probabilistic_sharpe_ratio(sr, t, benchmark_sr=expected_max_sharpe(n, v))
    assert deflated_sharpe_ratio(sr, t, n, v) == pytest.approx(expected, rel=1e-12)


def test_dsr_deflation_reduces_significance():
    assert deflated_sharpe_ratio(2.0, 250, 100, 1.0) < probabilistic_sharpe_ratio(2.0, 250)


def test_dsr_finite_in_unit_interval():
    d = deflated_sharpe_ratio(1.8, 500, 200, 1.0, skew=-0.5, kurtosis=6.0)
    assert math.isfinite(d) and 0.0 <= d <= 1.0


@pytest.mark.parametrize("args", [(float("nan"), 250, 100, 1.0), (1.5, 250, 100, float("nan"))])
def test_dsr_nan_refusal(args):
    with pytest.raises(ValidationError):
        deflated_sharpe_ratio(*args)
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_validation_dsr.py -q` → ImportError.

- [ ] **Step 3: Implement `cli/validation/dsr.py`:**

```python
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
    sr0 = math.sqrt(var_trials) * (
        (1 - g) * _NORM.inv_cdf(1 - 1 / n_trials) + g * _NORM.inv_cdf(1 - 1 / (n_trials * math.e))
    )
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
```

- [ ] **Step 4: Extend `cli/validation/__init__.py`** — add the three functions to imports and `__all__` (keep existing CPCV exports):

```python
from cli.validation.cpcv import cpcv_splits, make_groups, n_backtest_paths
from cli.validation.dsr import deflated_sharpe_ratio, expected_max_sharpe, probabilistic_sharpe_ratio
from cli.validation.errors import ValidationError

__all__ = [
    "ValidationError",
    "cpcv_splits",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "make_groups",
    "n_backtest_paths",
    "probabilistic_sharpe_ratio",
]
```

- [ ] **Step 5: Run tests, verify they pass** — `uv run pytest tests/test_validation_dsr.py -q`.

- [ ] **Step 6: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 7: Commit** — `feat(validation): add deflated + probabilistic Sharpe ratio`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-014: deflated & probabilistic Sharpe ratio (Phase 2)`: `cli/validation/dsr.py` — PSR, `expected_max_sharpe` (Bailey & LdP), DSR = PSR deflated by the expected-max-under-null benchmark; stdlib `NormalDist`; **NaN-refusal encodes the §7 PoC lesson** (raises on degenerate input, never returns NaN — the integrity the trial registry asserts); property-tested; §9.4; spec/plan `00007`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-014 closeout — deflated Sharpe ratio`.
