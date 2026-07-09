# Combination Trial (P1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the §10 per-asset cap as tested code and run + register the §12 combination trial (B3+vt-dynamic + cap + governor) as registry family P1.

**Architecture:** One committed pure function (`cli/risk/limits.py`), then an orchestrator-run scratchpad driver implementing the spec's construction (cap-then-govern on the frozen candidate) with QA gates and the pre-registered verdict criteria, a registry append (family P1, first schema-v3 `variant` use), and the closeout entry.

**Tech Stack:** Python 3.14, stdlib only in `cli/risk/`; pytest; existing `cli` machinery (`net_of_cost_verdict`, `benchmark_relative_worst_slice`, `reality_check_pvalue`, `TrialRegistry`).

## Global Constraints

- Stdlib only in `cli/risk/`; ruff line 132, double quotes; commit gate `uv run pre-commit run -a`.
- Cap defaults are the §10 constants exactly: `long_cap=0.20`, `short_cap=0.10`; clip only, **no redistribution**; inclusive (a position of exactly 0.20 is NOT clipped).
- Validation raises `RiskError`; no silent coercion.
- The trial's verdict criteria are pre-registered in the spec §trial-protocol and `.tmp/decisions.md` `[iter-059]` — the driver reports against them; the orchestrator does not move the bar after seeing numbers.
- SPA params: `mean_block=17, seed=42, n_resamples=2000`; seed-stability at 42/7/1234. `dataset_hash` must equal registry record 1's, else STOP.
- Commits end with `Co-Authored-By:` (actual model) + `Claude-Session:` trailers.

______________________________________________________________________

### Task 1: `cli/risk/limits.py` — `apply_position_caps`, TDD

**Files:**

- Create: `cli/risk/limits.py`
- Modify: `cli/risk/__init__.py`
- Test: `tests/test_risk_limits.py`

**Interfaces:**

- Consumes: `cli.risk.errors.RiskError` (exists).
- Produces: `apply_position_caps(positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10) -> dict[str, list[float]]`, re-exported from `cli.risk`. Task 2's driver relies on exactly this signature.

- [ ] **Step 1: Write the failing tests** — full file `tests/test_risk_limits.py`:

```python
import pytest

from cli.risk import RiskError, apply_position_caps


def test_long_clip():
    out = apply_position_caps({"BTC": [0.35, 0.10, 0.20]})
    assert out == {"BTC": [0.20, 0.10, 0.20]}  # 0.20 exactly is NOT clipped (inclusive)


def test_short_clip():
    out = apply_position_caps({"ETH": [-0.25, -0.05, -0.10]})
    assert out == {"ETH": [-0.10, -0.05, -0.10]}


def test_mixed_and_multi_asset():
    out = apply_position_caps({"BTC": [0.5, -0.5], "ETH": [0.0, 0.19]})
    assert out == {"BTC": [0.20, -0.10], "ETH": [0.0, 0.19]}


def test_custom_caps():
    out = apply_position_caps({"BTC": [0.5, -0.5]}, long_cap=0.3, short_cap=0.4)
    assert out == {"BTC": [0.3, -0.4]}


def test_input_not_mutated():
    src = {"BTC": [0.35]}
    apply_position_caps(src)
    assert src == {"BTC": [0.35]}


def test_shape_preserved():
    out = apply_position_caps({"A": [0.01] * 5, "B": [0.02] * 5})
    assert set(out) == {"A", "B"}
    assert all(len(v) == 5 for v in out.values())


@pytest.mark.parametrize(
    "positions",
    [
        {},
        {"BTC": []},
        {"BTC": [0.1], "ETH": [0.1, 0.2]},  # ragged
        {"BTC": [float("nan")]},
        {"BTC": [float("inf")]},
        {"BTC": "not a list"},
        "not a dict",
    ],
)
def test_invalid_positions(positions):
    with pytest.raises(RiskError):
        apply_position_caps(positions)


@pytest.mark.parametrize("kwargs", [{"long_cap": 0.0}, {"long_cap": -0.2}, {"short_cap": 0.0}, {"short_cap": float("nan")}])
def test_invalid_caps(kwargs):
    with pytest.raises(RiskError):
        apply_position_caps({"BTC": [0.1]}, **kwargs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_risk_limits.py -q`
Expected: FAIL — `ImportError: cannot import name 'apply_position_caps' from 'cli.risk'`.

- [ ] **Step 3: Implement**

`cli/risk/limits.py`:

```python
"""§10 portfolio limits — the per-asset cap as a pure pre-trade clip.

Clip only, no redistribution (a §10 limit is a pre-trade governor, not an optimizer; the excess
sits in cash). Inclusive: a position exactly at the cap passes unclipped. The gross/net/margin-floor
limits are deliberately absent — they never bind on the current long-only book (see
docs/specs/00035-combination-trial-design.md) and return with a short-carrying or levered sleeve.
"""

from __future__ import annotations

import math

from cli.risk.errors import RiskError


def apply_position_caps(
    positions: dict[str, list[float]], *, long_cap: float = 0.20, short_cap: float = 0.10
) -> dict[str, list[float]]:
    """Clip each asset's per-bar position to [-short_cap, +long_cap]; §10 defaults 20%/10% NAV."""
    if not isinstance(positions, dict) or not positions:
        raise RiskError(f"positions must be a non-empty dict, got {positions!r}")
    for cap_name, cap in (("long_cap", long_cap), ("short_cap", short_cap)):
        if not isinstance(cap, (int, float)) or not math.isfinite(cap) or cap <= 0:
            raise RiskError(f"{cap_name} must be a finite number > 0, got {cap!r}")
    lengths = set()
    for asset, series in positions.items():
        if not isinstance(series, list) or not series:
            raise RiskError(f"positions[{asset!r}] must be a non-empty list, got {series!r}")
        for p in series:
            if not isinstance(p, (int, float)) or not math.isfinite(p):
                raise RiskError(f"positions[{asset!r}] must contain finite numbers, got {p!r}")
        lengths.add(len(series))
    if len(lengths) != 1:
        raise RiskError(f"all assets must have equal-length series, got lengths {sorted(lengths)}")
    return {asset: [min(p, long_cap) if p >= 0 else max(p, -short_cap) for p in series] for asset, series in positions.items()}
```

`cli/risk/__init__.py` (full new content):

```python
from cli.risk.errors import RiskError
from cli.risk.governor import GovernorConfig, GovernorResult, drawdown_governor
from cli.risk.limits import apply_position_caps

__all__ = ["GovernorConfig", "GovernorResult", "RiskError", "apply_position_caps", "drawdown_governor"]
```

- [ ] **Step 4: Run the new tests, then the full suite**

Run: `uv run pytest tests/test_risk_limits.py -q` — Expected: 17 pass (6 named + 11 parametrized).
Run: `uv run pytest -q` — Expected: 900 pass (883 + 17).

- [ ] **Step 5: Commit**

```bash
uv run pre-commit run -a   # until clean; re-stage rewrites
git add cli/risk/limits.py cli/risk/__init__.py tests/test_risk_limits.py
git commit -m "feat(risk): apply_position_caps — §10 per-asset cap as a pure pre-trade clip

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01A7RnbvMKGoUqnZaE48acVN"
```

______________________________________________________________________

### Task 2 (orchestrator-run, no commit): the combination-trial driver

Scratchpad `combination_trial_run.py` per spec §construction + §trial-protocol: QA-1 (frozen reference reproduction), QA-2 (iter-058 governed figures through this code path), QA-3 (cap engagement: max pre-cap 34.8 % → post ≤ 20 %, breach bars ≈ 100), then the verdict legs — both-direction `net_of_cost_verdict` (seeds 42/7/1234), `benchmark_relative_worst_slice` + literal absolute worst-slice, ×1.5/×2 cost stress (both sides, governor re-run per stressed series), full + k≥230 windows. STOP on any QA failure.

### Task 3 (orchestrator-run): registry append

Scratchpad append driver mirroring `a2_registry_write.py`: `family="P1"`, `variant="B3vtdyn+gov+cap"`, `n_trials_in_family=1`, `spec_hash=sha256(docs/specs/00035-…)`, `dataset_hash` verified == record 1's (STOP on mismatch), `seeds=[42, 7, 1234]`, metrics from Task 2, verdict per the pre-registered criteria, notes carrying the two governor properties + cap stats. Commit the updated `docs/research/trial-registry.jsonl` (registry data commit; reviewed as part of the branch).

### Task 4 (orchestrator-run, closeout): iterations-history + decisions log

Append the iter-059 entry to `docs/iterations-history.md` (cap code, trial construction, QA evidence, verdict + numbers, registry record); append the verdict decision entry to `.tmp/decisions.md`. Closeout-docs commit (review-exempt).
