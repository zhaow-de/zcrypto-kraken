# Backtester Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open `cli/backtest/` with `run_backtest` per `docs/specs/00016-backtester-engine-design.md` — positions → net-return series (explicit per-turnover fee) → metrics, reusing `cli.validation`. Never NaN.

**Architecture:** New package `cli/backtest/` (`errors.py`, `engine.py`, `__init__.py`); reuses `cli.validation.{sharpe,max_drawdown,annualized_return,ValidationError}`. TDD.

**Tech Stack:** Python 3.14, stdlib `math`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only; reuse `cli.validation` metrics (do NOT reimplement Sharpe/maxDD/return). Guards raise `BacktestError`; degenerate/blown-up backtests raise (never NaN). **Timing convention (fixed):** `positions[t]` earns `asset_returns[t]`; `turnover[t] = |positions[t] − positions[t−1]|` with `positions[−1]=0`. No CLI/README change.

---

### Task 1: `cli/backtest/` — errors + engine

**Files:** Create `cli/backtest/__init__.py`, `cli/backtest/errors.py`, `cli/backtest/engine.py`; Test `tests/test_backtest_engine.py`.

**Interfaces:** Produces `BacktestError`; `run_backtest(asset_returns, positions, *, fee_rate=0.0, periods_per_year) -> dict`. Consumes `cli.validation.{sharpe,max_drawdown,annualized_return,ValidationError}`.

- [ ] **Step 1: Write failing tests** in `tests/test_backtest_engine.py`:

```python
import math

import pytest

from cli.backtest import BacktestError, run_backtest
from cli.validation import annualized_return, max_drawdown, sharpe


def test_buy_and_hold_timing_and_entry_cost():
    r = run_backtest([0.10, -0.05, 0.20], [1.0, 1.0, 1.0], fee_rate=0.01, periods_per_year=252)
    assert r["net_returns"] == pytest.approx([0.09, -0.05, 0.20])
    assert r["total_return"] == pytest.approx(1.09 * 0.95 * 1.20 - 1)
    assert r["n_periods"] == 3


def test_zero_fee_constant_position():
    ar = [0.01, 0.02, -0.03, 0.04]
    r = run_backtest(ar, [0.5] * 4, fee_rate=0.0, periods_per_year=252)
    assert r["net_returns"] == pytest.approx([0.5 * x for x in ar])


def test_turnover_cost_on_sign_flip():
    r = run_backtest([0.02, 0.01, 0.03], [1.0, 1.0, -1.0], fee_rate=0.01, periods_per_year=252)
    assert r["net_returns"][2] == pytest.approx(-1.0 * 0.03 - 2.0 * 0.01)


def test_metrics_reuse_the_harness():
    ar = [0.01, -0.02, 0.03, 0.00, 0.02]
    pos = [1.0, 0.5, 1.0, 0.5, 1.0]
    r = run_backtest(ar, pos, fee_rate=0.0, periods_per_year=252)
    net = r["net_returns"]
    assert r["sharpe"] == pytest.approx(sharpe(net, periods_per_year=252))
    assert r["max_drawdown"] == pytest.approx(max_drawdown(net))
    assert r["annualized_return"] == pytest.approx(annualized_return(net, periods_per_year=252))


def test_flat_strategy_raises():
    with pytest.raises(BacktestError):
        run_backtest([0.01, -0.02, 0.03, 0.01, 0.0], [0.0] * 5, periods_per_year=252)


def test_blowup_raises():
    with pytest.raises(BacktestError):
        run_backtest([0.0, -0.4], [3.0, 3.0], periods_per_year=252)


@pytest.mark.parametrize(
    "ar,pos,kwargs",
    [
        ([0.01], [1.0, 1.0], {"periods_per_year": 252}),
        ([0.01], [1.0], {"periods_per_year": 252}),
        ([0.01, float("nan")], [1.0, 1.0], {"periods_per_year": 252}),
        ([0.01, 0.02], [1.0, float("inf")], {"periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"fee_rate": -0.01, "periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"fee_rate": "x", "periods_per_year": 252}),
        ([0.01, 0.02], [1.0, 1.0], {"periods_per_year": 0}),
        ([0.01, 0.02], [1.0, 1.0], {"periods_per_year": 2.5}),
    ],
)
def test_run_backtest_guards(ar, pos, kwargs):
    with pytest.raises(BacktestError):
        run_backtest(ar, pos, **kwargs)


def test_positive_drift_buy_and_hold():
    ar = [0.01 + 0.005 * ((i % 3) - 1) for i in range(300)]  # mean 0.01, non-zero variance
    r = run_backtest(ar, [1.0] * 300, fee_rate=0.0, periods_per_year=252)
    assert r["total_return"] > 0 and math.isfinite(r["sharpe"]) and r["sharpe"] > 0
```

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Implement `cli/backtest/errors.py`:**
```python
class BacktestError(Exception):
    """Raised on invalid backtest inputs or a degenerate/blown-up backtest."""
```

- [ ] **Step 4: Implement `cli/backtest/engine.py`:**
```python
from __future__ import annotations

import math

from cli.backtest.errors import BacktestError
from cli.validation import ValidationError, annualized_return, max_drawdown, sharpe


def run_backtest(
    asset_returns: list[float], positions: list[float], *, fee_rate: float = 0.0, periods_per_year: int
) -> dict:
    """Turn a strategy's target positions into a net-return series (explicit per-turnover fee) + metrics.

    Timing (fixed): positions[t] is held during period t and earns asset_returns[t]; the caller must set
    positions[t] from information available before period t. turnover[t] = |positions[t] - positions[t-1]|
    (positions[-1] = 0). See docs/specs/00016. Never returns NaN — a degenerate/blown-up backtest raises.
    """
    if len(asset_returns) != len(positions):
        raise BacktestError(f"asset_returns and positions must match in length ({len(asset_returns)} != {len(positions)})")
    n = len(asset_returns)
    if n < 2:
        raise BacktestError(f"need >= 2 periods, got {n}")
    for name, seq in (("asset_returns", asset_returns), ("positions", positions)):
        for v in seq:
            if not isinstance(v, (int, float)) or not math.isfinite(v):
                raise BacktestError(f"{name} must be finite numbers, got {v!r}")
    if not isinstance(fee_rate, (int, float)) or not math.isfinite(fee_rate) or fee_rate < 0:
        raise BacktestError(f"fee_rate must be a finite number >= 0, got {fee_rate!r}")
    if not isinstance(periods_per_year, int) or periods_per_year < 1:
        raise BacktestError(f"periods_per_year must be a positive int, got {periods_per_year!r}")

    net: list[float] = []
    prev = 0.0
    for t in range(n):
        turnover = abs(positions[t] - prev)
        net.append(positions[t] * asset_returns[t] - turnover * fee_rate)
        prev = positions[t]

    try:
        sr = sharpe(net, periods_per_year=periods_per_year)
        mdd = max_drawdown(net)
        ann = annualized_return(net, periods_per_year=periods_per_year)
    except ValidationError as exc:
        raise BacktestError(f"degenerate backtest: {exc}") from exc

    total_return = 1.0
    for r in net:
        total_return *= 1 + r
    total_return -= 1

    return {
        "net_returns": net,
        "total_return": total_return,
        "sharpe": sr,
        "max_drawdown": mdd,
        "annualized_return": ann,
        "n_periods": n,
    }
```

- [ ] **Step 5: Implement `cli/backtest/__init__.py`:**
```python
from cli.backtest.engine import run_backtest
from cli.backtest.errors import BacktestError

__all__ = ["BacktestError", "run_backtest"]
```

- [ ] **Step 6: Run tests, verify pass** — `uv run pytest tests/test_backtest_engine.py -q`.

- [ ] **Step 7: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 8: Commit** — `feat(backtest): add explicit-cost vectorized backtester engine`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-024: explicit-cost backtester engine (Phase 3)`: `cli/backtest/` opened — `run_backtest(asset_returns, positions, *, fee_rate, periods_per_year)`: positions → net-return series (timing `positions[t]` earns `return[t]`; turnover `|Δposition|·fee_rate` from a flat start) → equity + Sharpe/maxDD/annualized via `cli.validation.metrics` (reused, not reimplemented). Never-NaN (a flat strategy or a `1+net≤0` blow-up raises `BacktestError`). Margin/spread deferred. First Phase-3 iteration (the engine the benchmark family B0–B4 is built on). Spec/plan `00016`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-024 closeout — backtester engine`.
