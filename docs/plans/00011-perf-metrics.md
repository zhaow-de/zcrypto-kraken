# Performance Statistics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `sharpe` / `volatility` / `annualized_return` / `max_drawdown` to `cli/validation/` per `docs/specs/00011-perf-metrics-design.md` — pure returns-series statistics that never return NaN.

**Architecture:** New module `cli/validation/metrics.py` reusing `errors.ValidationError`; export the four from `__init__.py`. TDD.

**Tech Stack:** Python 3.14, stdlib `statistics`, `math`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. Sample stdev (`statistics.stdev`, n−1) for Sharpe/volatility.
- **Never NaN:** zero-variance returns (Sharpe) and any `1 + r <= 0` (annualized_return / max_drawdown) raise `ValidationError`, not NaN. Also guard: `len < 2` (Sharpe/vol), empty (return/maxDD), non-finite returns/`risk_free`, `periods_per_year` not a positive `int`.
- `max_drawdown` returns a non-negative fraction. No CLI/README change.

---

### Task 1: `cli/validation/metrics.py`

**Files:**
- Create: `cli/validation/metrics.py`
- Modify: `cli/validation/__init__.py` (add 4 exports)
- Test: `tests/test_validation_metrics.py`

**Interfaces:**
- Produces: `sharpe(returns, *, risk_free=0.0, periods_per_year=None)`, `volatility(returns, *, periods_per_year=None)`, `annualized_return(returns, *, periods_per_year)`, `max_drawdown(returns)`.
- Consumes: `cli.validation.errors.ValidationError`.

- [ ] **Step 1: Write failing tests** in `tests/test_validation_metrics.py`:

```python
import math
import statistics

import pytest

from cli.validation import ValidationError, annualized_return, max_drawdown, sharpe, volatility


def test_sharpe_zero_mean():
    assert sharpe([0.02, -0.02, 0.02, -0.02]) == pytest.approx(0.0)


def test_sharpe_positive():
    assert sharpe([0.01, 0.03]) == pytest.approx(0.02 / statistics.stdev([0.01, 0.03]))
    assert sharpe([0.01, 0.03]) == pytest.approx(1.4142, abs=1e-4)


def test_sharpe_annualized():
    assert sharpe([0.01, 0.03], periods_per_year=252) == pytest.approx(sharpe([0.01, 0.03]) * math.sqrt(252))


def test_sharpe_risk_free_lowers():
    assert sharpe([0.01, 0.03], risk_free=0.01) < sharpe([0.01, 0.03])


@pytest.mark.parametrize(
    "returns,kwargs",
    [
        ([0.01], {}),
        ([0.01, float("nan")], {}),
        ([0.01, 0.03], {"risk_free": float("inf")}),
        ([0.01, 0.03], {"periods_per_year": 0}),
        ([0.01, 0.03], {"periods_per_year": -1}),
        ([0.01, 0.03], {"periods_per_year": 2.5}),
        ([0.01, 0.01, 0.01], {}),
    ],
)
def test_sharpe_guards(returns, kwargs):
    with pytest.raises(ValidationError):
        sharpe(returns, **kwargs)


def test_volatility():
    assert volatility([0.01, 0.03]) == pytest.approx(0.0141421356, abs=1e-7)
    assert volatility([0.01, 0.03], periods_per_year=252) == pytest.approx(statistics.stdev([0.01, 0.03]) * math.sqrt(252))


@pytest.mark.parametrize("returns,kwargs", [([0.01], {}), ([0.01, float("nan")], {}), ([0.01, 0.03], {"periods_per_year": -1})])
def test_volatility_guards(returns, kwargs):
    with pytest.raises(ValidationError):
        volatility(returns, **kwargs)


def test_annualized_return():
    assert annualized_return([0.1, 0.1], periods_per_year=2) == pytest.approx(0.21)
    assert annualized_return([0.0] * 252, periods_per_year=252) == pytest.approx(0.0)


@pytest.mark.parametrize(
    "returns,ppy",
    [([], 252), ([0.01, float("inf")], 252), ([0.01], 0), ([0.01], 2.5), ([-1.5, 0.1], 252)],
)
def test_annualized_return_guards(returns, ppy):
    with pytest.raises(ValidationError):
        annualized_return(returns, periods_per_year=ppy)


def test_max_drawdown():
    assert max_drawdown([0.1, -0.5, 0.2]) == pytest.approx(0.5)
    assert max_drawdown([0.1, 0.1, 0.1]) == pytest.approx(0.0)


@pytest.mark.parametrize("returns", [[], [0.1, float("nan")], [-1.5, 0.1]])
def test_max_drawdown_guards(returns):
    with pytest.raises(ValidationError):
        max_drawdown(returns)
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_validation_metrics.py -q` → ImportError.

- [ ] **Step 3: Implement `cli/validation/metrics.py`:**

```python
from __future__ import annotations

import math
import statistics

from cli.validation.errors import ValidationError


def _check_returns(returns: list[float], *, min_len: int) -> None:
    if len(returns) < min_len:
        raise ValidationError(f"returns must have >= {min_len} values, got {len(returns)}")
    for r in returns:
        if not math.isfinite(r):
            raise ValidationError(f"returns must be finite, got {r}")


def _check_periods_per_year(periods_per_year: int | None, *, required: bool) -> None:
    if periods_per_year is None:
        if required:
            raise ValidationError("periods_per_year is required")
        return
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValidationError(f"periods_per_year must be a positive int, got {periods_per_year!r}")


def sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float:
    """Per-period Sharpe (sample stdev), optionally annualized by sqrt(periods_per_year). Never NaN."""
    _check_returns(returns, min_len=2)
    if not math.isfinite(risk_free):
        raise ValidationError(f"risk_free must be finite, got {risk_free}")
    _check_periods_per_year(periods_per_year, required=False)
    std = statistics.stdev(returns)
    if std == 0:
        raise ValidationError("returns have zero variance; Sharpe is undefined")
    ratio = (statistics.mean(returns) - risk_free) / std
    if periods_per_year is not None:
        ratio *= math.sqrt(periods_per_year)
    return ratio


def volatility(returns: list[float], *, periods_per_year: int | None = None) -> float:
    """Per-period sample stdev of returns, optionally annualized by sqrt(periods_per_year)."""
    _check_returns(returns, min_len=2)
    _check_periods_per_year(periods_per_year, required=False)
    vol = statistics.stdev(returns)
    if periods_per_year is not None:
        vol *= math.sqrt(periods_per_year)
    return vol


def annualized_return(returns: list[float], *, periods_per_year: int) -> float:
    """Geometric annualized return: prod(1 + r) ** (periods_per_year / n) - 1. Never NaN."""
    _check_returns(returns, min_len=1)
    _check_periods_per_year(periods_per_year, required=True)
    cumulative = 1.0
    for r in returns:
        growth = 1 + r
        if growth <= 0:
            raise ValidationError(f"a period return <= -100% (1+r={growth}) breaks compounding")
        cumulative *= growth
    return cumulative ** (periods_per_year / len(returns)) - 1


def max_drawdown(returns: list[float]) -> float:
    """Worst peak-to-trough decline on the equity curve, as a non-negative fraction. Never NaN."""
    _check_returns(returns, min_len=1)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        growth = 1 + r
        if growth <= 0:
            raise ValidationError(f"a period return <= -100% (1+r={growth}) breaks the equity curve")
        equity *= growth
        peak = max(peak, equity)
        max_dd = max(max_dd, 1 - equity / peak)
    return max_dd
```

- [ ] **Step 4: Extend `cli/validation/__init__.py`** — add `annualized_return`, `max_drawdown`, `sharpe`, `volatility` to imports + `__all__` (keep all existing exports; keep `__all__` alphabetized).

- [ ] **Step 5: Run tests, verify they pass** — `uv run pytest tests/test_validation_metrics.py -q`.

- [ ] **Step 6: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 7: Commit** — `feat(validation): add performance statistics (sharpe, vol, return, maxdd)`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-018: performance statistics (Phase 2)`: `cli/validation/metrics.py` — `sharpe` / `volatility` (sample stdev, optional sqrt-annualization) / `annualized_return` (geometric) / `max_drawdown` (equity-curve peak-to-trough); the `statistic` callables the bootstrap/DSR/acceptance-suite consume; never-NaN (zero-variance Sharpe and `1+r<=0` raise); property-tested; §9; spec/plan `00011`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-018 closeout — performance statistics`.
