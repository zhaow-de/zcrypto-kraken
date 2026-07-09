# Drawdown Governor (§10 Risk Layer) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Master-plan §10's drawdown-governance ladder as a tested, pure returns-overlay in a new `cli/risk/` package, plus the pre-registered threshold backtest on the frozen candidate B3+vt-dynamic.

**Architecture:** One pure function `drawdown_governor(returns, *, config)` with governed-equity feedback — the multiplier for bar t is fixed from the governed path through t−1, no look-ahead by construction. Semantics fully settled in `docs/specs/00034-drawdown-governor-design.md` (§Semantics 1–7). The threshold backtest is a scratchpad driver (not committed), QA-gated on the frozen reference figures.

**Tech Stack:** Python 3.14, stdlib only (`math`, `dataclasses`), mirroring `cli/benchmark/` style; pytest.

## Global Constraints

- Stdlib only in `cli/risk/` — no numpy/polars (match `cli/benchmark/strategies.py`).
- Ruff: line length 132, double quotes; commit gate is `uv run pre-commit run -a` (re-run until clean, re-stage rewrites).
- Defaults are the D1-ratified §10 constants exactly: `daily_loss_limit=0.03`, `daily_loss_multiplier=0.5`, `daily_loss_cooldown=5`, `ladder=((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))`, `restart_after=30`.
- Bar 0 always gets multiplier 1.0. Boundaries inclusive: DD ≥ threshold selects the rung; governed return ≤ −daily_loss_limit triggers the daily rule.
- Composition is `min(ladder_mult, daily_mult)`. A ladder rung of exactly 0.0 is terminal (stand-down + re-arm with HWM reset); a 0.0 *daily* multiplier is NOT terminal.
- Validation raises `RiskError`; no silent coercion. Every commit ends with the `Co-Authored-By: Claude <model> <noreply@anthropic.com>` + `Claude-Session:` trailers naming the actual model.

______________________________________________________________________

### Task 1: `cli/risk/` package — the governor, TDD

**Files:**

- Create: `cli/risk/__init__.py`, `cli/risk/errors.py`, `cli/risk/governor.py`
- Test: `tests/test_risk_governor.py`

**Interfaces:**

- Consumes: nothing from other tasks.
- Produces: `from cli.risk import GovernorConfig, GovernorResult, RiskError, drawdown_governor` — `drawdown_governor(returns: list[float], *, config: GovernorConfig = GovernorConfig()) -> GovernorResult`; `GovernorResult` fields `multipliers: list[float]`, `governed_returns: list[float]`, `daily_loss_triggers: int`, `rung_bars: dict[float, int]`, `breaches: int`, `rung_transitions: int`. Task 2's driver relies on exactly these names.

- [ ] **Step 1: Write the failing tests** — full file:

```python
import math

import pytest

from cli.risk import GovernorConfig, GovernorResult, RiskError, drawdown_governor

# Configs that isolate one rule by disabling the other.
LADDER_ONLY = GovernorConfig(daily_loss_limit=0.5, restart_after=2)  # daily rule can't trigger on these paths
DAILY_ONLY = GovernorConfig(ladder=((0.99, 0.5),))  # ladder can't trigger on these paths

# Hand-computed ladder walk (spec §TDD): dd path 0 -> 5% -> 9.75% -> 12.01% -> 16.41% (breach) -> re-arm.
WALK_RETURNS = [-0.05, -0.05, -0.05, -0.2, 0.1, 0.1, -0.05, 0.0]
WALK_MULTS = [1.0, 1.0, 0.5, 0.25, 0.0, 0.0, 1.0, 1.0]


def test_planted_ladder_walk():
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    assert res.multipliers == WALK_MULTS
    assert res.breaches == 1
    assert res.rung_bars == {1.0: 4, 0.5: 1, 0.25: 1, 0.0: 2}
    assert res.rung_transitions == 4


def test_ladder_boundary_inclusive():
    # Exact binary numbers: E = 0.75 exactly, dd = 0.25 exactly; DD >= threshold selects the rung.
    cfg = GovernorConfig(daily_loss_limit=0.5, ladder=((0.25, 0.5),))
    res = drawdown_governor([-0.25, 0.0], config=cfg)
    assert res.multipliers == [1.0, 0.5]


def test_no_lookahead():
    base = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    perturbed = list(WALK_RETURNS)
    t = 3
    perturbed[t] = perturbed[t] + 0.5
    pert = drawdown_governor(perturbed, config=LADDER_ONLY)
    assert pert.multipliers[: t + 1] == base.multipliers[: t + 1]


def test_governed_feedback_prevents_breach():
    # Ungoverned this path breaches 15%; damped by the rungs, governed stays above -15%.
    returns = [-0.07, -0.05, -0.05, -0.05]
    equity = 1.0
    for r in returns:
        equity *= 1.0 + r
    assert 1.0 - equity > 0.15  # ungoverned breaches
    res = drawdown_governor(returns, config=GovernorConfig(daily_loss_limit=0.99, restart_after=None))
    assert res.breaches == 0
    assert res.multipliers == [1.0, 1.0, 0.25, 0.25]


def test_daily_loss_trigger_cooldown_and_renewal():
    # Trigger at bar 0 (governed -3%, inclusive), renewal at bar 3 (governed 0.5 * -0.08 = -4%).
    returns = [-0.03, 0.0, 0.0, -0.08, 0.0, 0.0, 0.0, 0.0, 0.0, 0.01]
    res = drawdown_governor(returns, config=DAILY_ONLY)
    assert res.multipliers == [1.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 1.0]
    assert res.daily_loss_triggers == 2


def test_daily_loss_strict_boundary():
    res = drawdown_governor([-0.0299, 0.0, 0.0], config=DAILY_ONLY)
    assert res.multipliers == [1.0, 1.0, 1.0]
    assert res.daily_loss_triggers == 0


def test_min_composition_not_product():
    # Bar 1: ladder says 0.5 (dd 6% >= 5%) AND daily rule says 0.5 -> min is 0.5, not 0.25.
    cfg = GovernorConfig(ladder=((0.05, 0.5),))
    res = drawdown_governor([-0.06, 0.0], config=cfg)
    assert res.multipliers[1] == 0.5


def test_terminal_no_restart():
    res = drawdown_governor(WALK_RETURNS, config=GovernorConfig(daily_loss_limit=0.5, restart_after=None))
    assert res.multipliers == [1.0, 1.0, 0.5, 0.25, 0.0, 0.0, 0.0, 0.0]
    assert res.breaches == 1


def test_rearm_resets_hwm():
    # After the 2-bar stand-down the HWM resets to current equity: bar 6's fresh -5% dip
    # is measured from the new base (dd 5% < 7.5%), so bar 7 stays at 1.0.
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    assert res.multipliers[6] == 1.0
    assert res.multipliers[7] == 1.0


def test_identity_and_occupancy():
    res = drawdown_governor(WALK_RETURNS, config=LADDER_ONLY)
    for t in range(len(WALK_RETURNS)):
        assert res.governed_returns[t] == pytest.approx(res.multipliers[t] * WALK_RETURNS[t])
    assert sum(res.rung_bars.values()) == len(WALK_RETURNS)


def test_all_positive_inert():
    res = drawdown_governor([0.01] * 10)
    assert res.multipliers == [1.0] * 10
    assert res.daily_loss_triggers == 0
    assert res.breaches == 0
    assert res.rung_bars == {1.0: 10}
    assert res.rung_transitions == 0


def test_result_type():
    assert isinstance(drawdown_governor([0.01, 0.02]), GovernorResult)


@pytest.mark.parametrize(
    "returns",
    [[], [0.01, float("nan")], [0.01, float("inf")], [0.01, -1.0], [0.01, -1.5], "not a list"],
)
def test_invalid_returns(returns):
    with pytest.raises(RiskError):
        drawdown_governor(returns)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"daily_loss_limit": 0.0},
        {"daily_loss_limit": -0.03},
        {"daily_loss_limit": float("nan")},
        {"daily_loss_multiplier": -0.1},
        {"daily_loss_multiplier": 1.5},
        {"daily_loss_cooldown": 0},
        {"daily_loss_cooldown": 2.5},
        {"ladder": ()},
        {"ladder": ((0.11, 0.5), (0.075, 0.25))},  # not ascending
        {"ladder": ((0.0, 0.5),)},  # threshold must be > 0
        {"ladder": ((0.075, 1.5),)},  # multiplier out of [0, 1]
        {"ladder": ((0.075, 0.5, 0.1),)},  # not a pair
        {"restart_after": 0},
        {"restart_after": -5},
        {"restart_after": 2.5},
    ],
)
def test_invalid_config(kwargs):
    with pytest.raises(RiskError):
        drawdown_governor([0.01, 0.02], config=GovernorConfig(**kwargs))


def test_daily_multiplier_zero_is_not_terminal():
    # A 0.0 daily multiplier flattens for the cooldown but is NOT a breach and re-arms without HWM reset.
    cfg = GovernorConfig(ladder=((0.99, 0.5),), daily_loss_multiplier=0.0, daily_loss_cooldown=2)
    res = drawdown_governor([-0.03, 0.0, 0.0, 0.01], config=cfg)
    assert res.multipliers == [1.0, 0.0, 0.0, 1.0]
    assert res.breaches == 0
```

Hand-verified traces behind the vectors (for the reviewer, not code): WALK with `LADDER_ONLY` — E: 1.0 → 0.95 (dd 5 %, mult 1.0) → 0.9025 (dd 9.75 %, mult 0.5) → 0.87994 (dd 12.01 %, mult 0.25) → 0.83595 (dd 16.41 %, breach, 2 flat bars) → re-arm HWM 0.83595 → bar 6 mult 1.0, g −0.05 → dd 5 % from the new base → bar 7 mult 1.0. Daily renewal — cooldown 5 set at bar 0, decremented bars 1–2 (4, 3), renewed to 5 at bar 3's −4 % governed loss, released at bar 9.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_risk_governor.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'cli.risk'`.

- [ ] **Step 3: Implement the package**

`cli/risk/errors.py`:

```python
class RiskError(Exception):
    """Raised on invalid risk-governor inputs."""
```

`cli/risk/governor.py`:

```python
"""Drawdown governor — master-plan §10's drawdown-governance ladder as a pure returns overlay.

The multiplier for bar t is fixed from the GOVERNED path through bar t-1 (the live book only ever
sees its own equity), then governed_returns[t] = multipliers[t] * returns[t] — no look-ahead by
construction. Semantics per docs/specs/00034-drawdown-governor-design.md: a pure threshold ladder
on drawdown from the governed high-water mark (inclusive boundaries, no hysteresis); a daily-loss
rule (governed return <= -daily_loss_limit) holding daily_loss_multiplier for daily_loss_cooldown
bars, renewed by each new trigger bar; min-composition of the two (the most restrictive control
governs); a ladder rung of exactly 0.0 is terminal — flat for restart_after bars, then re-arm with
the HWM reset to current governed equity (a flat book's drawdown is frozen, so re-arm cannot key
on recovery); restart_after=None stays flat to the end of the series.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from cli.risk.errors import RiskError


@dataclass(frozen=True)
class GovernorConfig:
    """The D1-ratified §10 constants as defaults; the knobs exist for test isolation + the sensitivity read."""

    daily_loss_limit: float = 0.03
    daily_loss_multiplier: float = 0.5
    daily_loss_cooldown: int = 5
    ladder: tuple[tuple[float, float], ...] = ((0.075, 0.5), (0.11, 0.25), (0.15, 0.0))
    restart_after: int | None = 30


@dataclass(frozen=True)
class GovernorResult:
    multipliers: list[float]
    governed_returns: list[float]
    daily_loss_triggers: int
    rung_bars: dict[float, int]
    breaches: int
    rung_transitions: int


def _validate(returns: list[float], config: GovernorConfig) -> None:
    if not isinstance(returns, list) or not returns:
        raise RiskError(f"returns must be a non-empty list, got {returns!r}")
    for r in returns:
        if not isinstance(r, (int, float)) or not math.isfinite(r) or r <= -1.0:
            raise RiskError(f"returns must be finite numbers > -1, got {r!r}")
    c = config
    if not isinstance(c.daily_loss_limit, (int, float)) or not math.isfinite(c.daily_loss_limit) or c.daily_loss_limit <= 0:
        raise RiskError(f"daily_loss_limit must be a finite number > 0, got {c.daily_loss_limit!r}")
    if (
        not isinstance(c.daily_loss_multiplier, (int, float))
        or not math.isfinite(c.daily_loss_multiplier)
        or not 0.0 <= c.daily_loss_multiplier <= 1.0
    ):
        raise RiskError(f"daily_loss_multiplier must be a finite number in [0, 1], got {c.daily_loss_multiplier!r}")
    if not isinstance(c.daily_loss_cooldown, int) or c.daily_loss_cooldown < 1:
        raise RiskError(f"daily_loss_cooldown must be an int >= 1, got {c.daily_loss_cooldown!r}")
    if not isinstance(c.ladder, tuple) or not c.ladder:
        raise RiskError(f"ladder must be a non-empty tuple of (threshold, multiplier) pairs, got {c.ladder!r}")
    prev_threshold = 0.0
    for rung in c.ladder:
        if not isinstance(rung, tuple) or len(rung) != 2:
            raise RiskError(f"each ladder rung must be a (threshold, multiplier) pair, got {rung!r}")
        threshold, rung_mult = rung
        if not isinstance(threshold, (int, float)) or not math.isfinite(threshold) or threshold <= prev_threshold:
            raise RiskError(f"ladder thresholds must be finite, > 0, and strictly ascending, got {c.ladder!r}")
        if not isinstance(rung_mult, (int, float)) or not math.isfinite(rung_mult) or not 0.0 <= rung_mult <= 1.0:
            raise RiskError(f"ladder multipliers must be finite numbers in [0, 1], got {rung_mult!r}")
        prev_threshold = threshold
    if c.restart_after is not None and (not isinstance(c.restart_after, int) or c.restart_after < 1):
        raise RiskError(f"restart_after must be None or an int >= 1, got {c.restart_after!r}")


def drawdown_governor(returns: list[float], *, config: GovernorConfig = GovernorConfig()) -> GovernorResult:
    """Apply the §10 governor to a (net-of-cost) returns series; see the module docstring for semantics."""
    _validate(returns, config)
    multipliers: list[float] = []
    governed: list[float] = []
    equity = 1.0
    hwm = 1.0
    daily_loss_triggers = 0
    breaches = 0
    rung_bars: dict[float, int] = {}
    cooldown_left = 0
    flat_left = 0
    flat_forever = False

    for r in returns:
        if flat_forever or flat_left > 0:
            mult = 0.0
        else:
            drawdown = 1.0 - equity / hwm
            ladder_mult = 1.0
            for threshold, rung_mult in config.ladder:
                if drawdown >= threshold:
                    ladder_mult = rung_mult
            if ladder_mult == 0.0:
                breaches += 1
                if config.restart_after is None:
                    flat_forever = True
                else:
                    flat_left = config.restart_after
                mult = 0.0
            else:
                daily_mult = config.daily_loss_multiplier if cooldown_left > 0 else 1.0
                mult = min(ladder_mult, daily_mult)
        multipliers.append(mult)
        g = mult * r
        governed.append(g)
        rung_bars[mult] = rung_bars.get(mult, 0) + 1
        equity *= 1.0 + g
        if flat_left > 0:
            flat_left -= 1
            if flat_left == 0:
                hwm = equity  # re-arm: fresh drawdown budget after the stand-down
                cooldown_left = 0
        elif not flat_forever:
            hwm = max(hwm, equity)
            if cooldown_left > 0:
                cooldown_left -= 1
            if g <= -config.daily_loss_limit:
                daily_loss_triggers += 1
                cooldown_left = config.daily_loss_cooldown

    transitions = sum(1 for t in range(1, len(multipliers)) if multipliers[t] != multipliers[t - 1])
    return GovernorResult(
        multipliers=multipliers,
        governed_returns=governed,
        daily_loss_triggers=daily_loss_triggers,
        rung_bars=rung_bars,
        breaches=breaches,
        rung_transitions=transitions,
    )
```

`cli/risk/__init__.py`:

```python
from cli.risk.errors import RiskError
from cli.risk.governor import GovernorConfig, GovernorResult, drawdown_governor

__all__ = ["GovernorConfig", "GovernorResult", "RiskError", "drawdown_governor"]
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `uv run pytest tests/test_risk_governor.py -q` — Expected: all pass (34 tests: 13 named + 21 parametrized cases).
Run: `uv run pytest -q` — Expected: full suite passes (849 existing + new).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a   # re-run until clean; re-stage anything it rewrites
git add cli/risk/ tests/test_risk_governor.py
git commit -m "feat(risk): drawdown governor — §10 ladder as a pure returns overlay

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01A7RnbvMKGoUqnZaE48acVN"
```

______________________________________________________________________

### Task 2 (orchestrator-run, no commit): threshold backtest on B3+vt-dynamic

Scratchpad driver `governor_backtest_run.py` (session scratchpad dir, NOT committed) extending `b3b4_dynamic_run.py`'s verified construction. Protocol per spec §threshold-backtest:

1. **QA gate first**: rebuild B3+vt-dynamic net-of-cost exactly (dynamic inverse-vol basket lookback 30, union calendar; 200d `sma_gate` on the basket's own equity index; `vol_target` 10 %/yr 30d max 1.0× on the RAW basket, gate applied after; per-asset turnover costs). Must reproduce net-of-cost Sharpe 1.245 full / 1.278 k≥230 and maxDD 21.9 % before any governed number is read. Mismatch = instrument bug — stop, fix, do not proceed. *\[Correction, iter-071 audit: 21.9 % is the ZERO-FEE maxDD (net-of-cost maxDD is 25.53 %); the executed driver gated on the correct attribution — see the iter-058 history entry.\]*
2. Governed vs ungoverned (default config): Sharpe, ann. return, ann. vol, maxDD, worst calendar year (P&L + DD), full window and k≥230.
3. Engagement evidence (mandatory): rung occupancy, daily-loss triggers, breaches, transitions — a governor inert on a 21.9 %-maxDD series is a bug, not a result.
4. `restart_after=None` diagnostic variant.
5. Sensitivity: one-at-a-time ±25 % on daily limit, each rung threshold, cooldown, restart; Sharpe/maxDD per variant. Knife-edge ⇒ register an open topic, don't tune.

### Task 3 (orchestrator-run, closeout): iterations-history entry + decisions log

Append the iter-058 section to `docs/iterations-history.md` (governor built, test count, backtest verdict numbers, engagement evidence, sensitivity read) and the results/interpretation decision entry to `.tmp/decisions.md`. Commit as a closeout-docs commit (review-exempt per `commit-messages.md`).
