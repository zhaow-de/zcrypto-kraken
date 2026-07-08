# Benchmark Strategies B0 + B1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open `cli/benchmark/` with `buy_and_hold` (B0) + `vol_target` (B1) position generators per `docs/specs/00017-benchmark-b0-b1-design.md` — look-ahead-free, feeding the backtester.

**Architecture:** New package `cli/benchmark/` (`errors.py`, `strategies.py`, `__init__.py`); `vol_target` uses `statistics.stdev` over `returns[t-lookback:t]` (strictly before `t`). TDD.

**Tech Stack:** Python 3.14, stdlib `math`, `statistics`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. **B1's realized-vol window is `returns[t-lookback:t]` — excludes `t` (no look-ahead).** Guards raise `BenchmarkError`; a zero-vol window → position `0.0` (no NaN). No CLI/README change.

---

### Task 1: `cli/benchmark/` — errors + strategies

**Files:** Create `cli/benchmark/__init__.py`, `cli/benchmark/errors.py`, `cli/benchmark/strategies.py`; Test `tests/test_benchmark_strategies.py`.

**Interfaces:** Produces `BenchmarkError`; `buy_and_hold(n_periods) -> list[float]`; `vol_target(returns, *, target_vol, lookback, max_leverage=1.0) -> list[float]`.

- [ ] **Step 1: Write failing tests** in `tests/test_benchmark_strategies.py`:

```python
import math
import statistics

import pytest

from cli.backtest import run_backtest
from cli.benchmark import BenchmarkError, buy_and_hold, vol_target


def test_buy_and_hold():
    assert buy_and_hold(3) == [1.0, 1.0, 1.0]


@pytest.mark.parametrize("n", [0, -1, 2.5])
def test_buy_and_hold_guards(n):
    with pytest.raises(BenchmarkError):
        buy_and_hold(n)


def test_vol_target_warmup_zero():
    pos = vol_target([0.01, -0.02, 0.03, 0.01, -0.01], target_vol=0.02, lookback=3)
    assert pos[:3] == [0.0, 0.0, 0.0]


def test_vol_target_value_and_cap():
    returns = [0.01, -0.01, 0.02, 0.0, 0.0]
    s = statistics.stdev(returns[0:3])
    pos = vol_target(returns, target_vol=0.02, lookback=3, max_leverage=5.0)
    assert pos[3] == pytest.approx(min(0.02 / s, 5.0))
    capped = vol_target(returns, target_vol=1.0, lookback=3, max_leverage=1.5)
    assert capped[3] == pytest.approx(1.5)


def test_vol_target_no_lookahead():
    returns = [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, 0.0]
    lookback, t = 3, 4
    base = vol_target(returns, target_vol=0.02, lookback=lookback)
    perturbed = list(returns)
    perturbed[t] = perturbed[t] + 0.5
    pert = vol_target(perturbed, target_vol=0.02, lookback=lookback)
    assert pert[t] == base[t]            # position_t does NOT use return_t
    assert pert[t + 1] != base[t + 1]    # position_{t+1}'s window includes t -> changes (window is real)


def test_vol_target_zero_vol_window():
    pos = vol_target([0.0, 0.0, 0.0, 0.0, 0.01], target_vol=0.02, lookback=3)
    assert pos[3] == 0.0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"target_vol": 0.0, "lookback": 3},
        {"target_vol": -0.1, "lookback": 3},
        {"target_vol": "x", "lookback": 3},
        {"target_vol": 0.02, "lookback": 1},
        {"target_vol": 0.02, "lookback": 2.5},
        {"target_vol": 0.02, "lookback": 3, "max_leverage": 0.0},
    ],
)
def test_vol_target_guards(kwargs):
    with pytest.raises(BenchmarkError):
        vol_target([0.01, -0.02, 0.03, 0.01], **kwargs)


def test_vol_target_empty_and_nonfinite():
    with pytest.raises(BenchmarkError):
        vol_target([], target_vol=0.02, lookback=3)
    with pytest.raises(BenchmarkError):
        vol_target([0.01, float("nan"), 0.03, 0.01], target_vol=0.02, lookback=3)


def test_vol_target_composes_with_backtester():
    returns = [0.01 + 0.01 * ((i % 4) - 1.5) for i in range(200)]
    pos = vol_target(returns, target_vol=0.015, lookback=20, max_leverage=2.0)
    r = run_backtest(returns, pos, fee_rate=0.0, periods_per_year=252)
    assert math.isfinite(r["sharpe"]) and r["n_periods"] == 200
```

- [ ] **Step 2: Run, verify fail** → ImportError.

- [ ] **Step 3: Implement `cli/benchmark/errors.py`:**
```python
class BenchmarkError(Exception):
    """Raised on invalid benchmark-strategy inputs."""
```

- [ ] **Step 4: Implement `cli/benchmark/strategies.py`:**
```python
from __future__ import annotations

import math
import statistics

from cli.benchmark.errors import BenchmarkError


def buy_and_hold(n_periods: int) -> list[float]:
    """B0 — constant full long position."""
    if not isinstance(n_periods, int) or n_periods < 1:
        raise BenchmarkError(f"n_periods must be an int >= 1, got {n_periods!r}")
    return [1.0] * n_periods


def vol_target(returns: list[float], *, target_vol: float, lookback: int, max_leverage: float = 1.0) -> list[float]:
    """B1 — scale exposure toward `target_vol` (per period) from the realized vol of the prior `lookback` returns.

    position[t] = min(target_vol / stdev(returns[t-lookback:t]), max_leverage), or 0.0 for t < lookback or a
    zero-vol window. The window `returns[t-lookback:t]` excludes t, so position[t] never uses return[t]
    (no look-ahead); the backtester then applies position[t] to return[t].
    """
    if not returns:
        raise BenchmarkError("returns must be non-empty")
    for r in returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r):
            raise BenchmarkError(f"returns must be finite numbers, got {r!r}")
    if not isinstance(target_vol, (int, float)) or not math.isfinite(target_vol) or target_vol <= 0:
        raise BenchmarkError(f"target_vol must be a finite number > 0, got {target_vol!r}")
    if not isinstance(lookback, int) or lookback < 2:
        raise BenchmarkError(f"lookback must be an int >= 2, got {lookback!r}")
    if not isinstance(max_leverage, (int, float)) or not math.isfinite(max_leverage) or max_leverage <= 0:
        raise BenchmarkError(f"max_leverage must be a finite number > 0, got {max_leverage!r}")

    positions: list[float] = []
    for t in range(len(returns)):
        if t < lookback:
            positions.append(0.0)
            continue
        rv = statistics.stdev(returns[t - lookback : t])
        positions.append(min(target_vol / rv, max_leverage) if rv > 0 else 0.0)
    return positions
```

- [ ] **Step 5: Implement `cli/benchmark/__init__.py`:**
```python
from cli.benchmark.errors import BenchmarkError
from cli.benchmark.strategies import buy_and_hold, vol_target

__all__ = ["BenchmarkError", "buy_and_hold", "vol_target"]
```

- [ ] **Step 6: Run tests, verify pass** — `uv run pytest tests/test_benchmark_strategies.py -q`.

- [ ] **Step 7: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 8: Commit** — `feat(benchmark): add B0 buy-and-hold + B1 vol-target strategies`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-025: benchmark strategies B0 + B1 (Phase 3)`: `cli/benchmark/` opened — `buy_and_hold` (B0, constant long) + `vol_target` (B1, `position[t] = min(target_vol / stdev(returns[t-lookback:t]), max_leverage)`, 0 for warm-up/zero-vol); look-ahead-free (the vol window `returns[t-lookback:t]` excludes `t`; a test asserts `position[t]` is invariant to `return[t]`); composes with the iter-024 backtester. `BenchmarkError` guards. First benchmark strategies of the family (B2 basket / B3 gate / B4 short + the real-data dossier follow). Spec/plan `00017`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-025 closeout — benchmark B0 + B1`.
