# B2 derivatives-positioning feature harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ## ⛔ NOT EXECUTION-READY — the contract pin refuted 11 premises (2026-09-03)
>
> The review loop was cut at the pin by its time-gate; lenses, union, fix and the three floor passes never ran. **Do not execute this plan as written.** The pin's refutations, each verified by running code, and every one of them a defect in the pair rather than in the tree:
>
> 1. **The look-ahead guard in Task 2 does not work.** The pin built a deliberate backward-fill defect (`if t >= g: return x` — reads the NEXT source row) and ran the plan's own test against it: correct implementation and defect **both PASS**, because the appended stamps `_t(16), _t(20)` sit beyond the grid's last stamp `_t(8)` and cannot move any value under either semantics. **The working guard it verified**: recompute over `grid[:k]` using only source rows with `ts <= grid[k-1]` and compare to the full run's prefix — correct as-of passes, the defect trips at `k=1` (`[None]` vs `[2.0]`). This is the plan's load-bearing test and it was inert.
> 2. **Both planted-signal assertions are unachievable.** `funding_zscore` and `oi_zscore` both assert `> 3.0`; the true value is **2.8460498941515410** (inclusive window, sample stdev) or **exactly 3.0** (population stdev), and undefined under a strictly-past window. No definition returns `> 3.0`, and the docstring's own "2 sd above" contradicts the assertion.
> 3. **Task 4 is self-contradictory as executed.** "OI is strictly positive, so these use `_validate_prices`" cannot hold beside "null-propagating": `_validate_prices([100.0, None, 110.0])` raises `FeatureError`. An OI feature cannot both call it and propagate a null.
> 4. **"Matching the existing convention exactly" is false about length.** All five existing feature functions return `len(prices) - 1`, aligned to `returns_from_prices`; every test in this plan requires `len(input)`. The three traits the sentence's parenthesis names — keyword-only params, a causality docstring, `_validate_*`/`FeatureError` — do all hold.
> 5. **The 2022 hole is panel-wide, not a BTCUSDT property.** It is 87.3 % for nine symbols and 87.0 % for XRP — identical. Panel-wide null is **18.4 %** (921,890/5,010,882); BTCUSDT's 14.9 % is lower only because it has 15 more months of dense history diluting it. The spec's D5 presents 14.9 % as the figure.
> 6. **`none before 2022-01-30` is false read absolutely** — the column is populated from 2020-09-01, the series' first row. The true statement is 2022-scoped.
> 7. **The §12 attribution is wrong**: the B2 quote is verbatim at master-plan line 156, inside **§5** (Strategy Design Space). §12 begins at line 307. T0023 cites it as §5 correctly. Separately, §9 line 261 uses "B2" for an unrelated *benchmark*.
> 8. **B1's band is 4h only**, not 1h/4h — spec `00045` conditions on the adopted A2-**4h** ensemble over `hour ∈ {0,4,8,12,16,20}`; its 15m substrate feeds the vol scaler, not a decision grid. Both grids are buildable (`60/240/1440.parquet` all present), so D3's *choice* survives; its stated *reason* does not.
> 9. **The spec's claim about the catalog is stale against its own commit** — `523a4034` already replaced the "early metrics" wording, so "the catalog is corrected in the same change" is discharged and the present-tense premise no longer matches the tree.
> 10. **T0023 is already `partial`** (set at iter-090); Task 6's status flip is a no-op. The `## Done so far` entry and the next-steps trim are the real work.
>
> Full graded fact file: 34 claims, at `.tmp/plan-review/00110/pin-facts.md` — **gitignored, so it will not survive a clean**; this block is the durable record.

**Goal:** Build the funding + OI feature harness B2 will be measured with, proven on known answers before any verdict counts.

**Architecture:** Pure functions on plain Python lists in `cli/features/derivatives.py`, matching the existing `cli/features/` convention exactly (see `momentum.py`: keyword-only params, a docstring stating the causality property, `_validate_*` helpers raising `FeatureError`). No polars, no frames, no I/O — the substrate readers already exist in `cli/derivatives/`.

**Tech Stack:** Python 3.14, stdlib only for the feature math; pytest.

**Spec:** `docs/specs/00110-b2-derivatives-feature-harness-design.md`

## Global Constraints

- **Causality is the product.** Every feature at index `k` reads only inputs at index `<= k`. Each function's docstring states this in the house form (`… uses only x[<= k] -> no look-ahead`), and Task 2's property test enforces it by construction.
- **No imputation, ever.** A null input yields a null output (`float | None`). Never 0.0, never a trailing mean. Spec D5.
- **Windows are pre-registered at 30 days.** They are function parameters with no defaults baked into the math; the 30-day pre-registration lives in the spec, not in the code. Tuning one is a trial (spec D7).
- **Funding rates are SIGNED.** `_validate_prices` rejects `<= 0` and must not be used for funding. Task 1 adds `_validate_rates`.
- **Emitted column names are prefixed `binperp_`** (spec D8) — these describe Binance perpetuals, not Kraken spot.
- **This harness spends no trial budget.** It registers nothing.

---

### Task 1: A signed-value validator

**Files:**
- Modify: `cli/features/_validate.py`
- Test: `tests/test_features_validate.py`

**Interfaces:**
- Produces: `_validate_rates(name: str, values: list[float | None]) -> None` — accepts finite floats of ANY sign and `None`; rejects non-finite, bool, non-numeric, and lists shorter than 2.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from cli.features._validate import _validate_rates
from cli.features.errors import FeatureError

def test_validate_rates_accepts_negative_and_none():
    _validate_rates("funding", [-0.0003, 0.0, None, 0.0007])

def test_validate_rates_rejects_nonfinite_and_bool():
    for bad in ([1.0, float("nan")], [1.0, float("inf")], [1.0, True]):
        with pytest.raises(FeatureError):
            _validate_rates("funding", bad)
```

- [ ] **Step 2: Run it, expect ImportError / failure**

Run: `uv run pytest tests/test_features_validate.py -v`

- [ ] **Step 3: Implement**

```python
def _validate_rates(name: str, values: list[float | None]) -> None:
    """Signed-value validator: funding rates go negative, so `_validate_prices` (which rejects
    <= 0) must not be used for them. `None` is allowed and propagates (spec 00110 D5)."""
    if not isinstance(values, list) or len(values) < 2:
        raise FeatureError(f"{name} must be a list of >= 2 values, got {values!r}")
    for v in values:
        if v is None:
            continue
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v):
            raise FeatureError(f"{name} must be finite numbers or None, got {v!r}")
```

- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): a signed validator, because funding rates go negative`

---

### Task 2: As-of alignment, and the look-ahead property test

**Files:**
- Create: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `align_asof(source_ts, source_values, grid_ts) -> list[float | None]` — for each grid stamp `g`, the value of the latest source row with `ts <= g`, else `None`. Both inputs must be sorted ascending; forward-fill only, never interpolate (spec D2).

- [ ] **Step 1: Write the failing tests — including the guard the spec exists for**

```python
from datetime import datetime, timedelta, timezone
from cli.features.derivatives import align_asof

UTC = timezone.utc
def _t(h): return datetime(2022, 1, 1, h, tzinfo=UTC)

def test_align_asof_forward_fills_and_never_interpolates():
    src_ts = [_t(0), _t(8)]
    src_v = [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8), _t(12)]
    assert align_asof(src_ts, src_v, grid) == [1.0, 1.0, 2.0, 2.0]

def test_align_asof_is_none_before_the_first_source_row():
    assert align_asof([_t(8)], [2.0], [_t(0), _t(8)]) == [None, 2.0]

def test_appending_future_source_rows_cannot_change_any_earlier_value():
    """The look-ahead guard (spec D2/D10). Recomputing with future rows appended must be
    bit-identical over the original grid, or a feature is reading its own future."""
    src_ts, src_v = [_t(0), _t(8)], [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8)]
    before = align_asof(src_ts, src_v, grid)
    after = align_asof(src_ts + [_t(16), _t(20)], src_v + [99.0, -99.0], grid)
    assert before == after
```

- [ ] **Step 2: Run, expect failure**

Run: `uv run pytest tests/test_features_derivatives.py -v`

- [ ] **Step 3: Implement**

```python
from __future__ import annotations

from datetime import datetime

from cli.features.errors import FeatureError


def align_asof(
    source_ts: list[datetime],
    source_values: list[float | None],
    grid_ts: list[datetime],
) -> list[float | None]:
    """As-of forward fill onto a decision grid: out[k] is the value of the latest source row with
    ts <= grid_ts[k], or None before the first such row. Uses only source rows at or before each
    grid stamp -> no look-ahead. Never interpolates: an interpolated value is a number the venue
    never showed (spec 00110 D2)."""
    if len(source_ts) != len(source_values):
        raise FeatureError(
            f"source_ts and source_values must be equal length, got {len(source_ts)} and {len(source_values)}"
        )
    if any(b < a for a, b in zip(source_ts, source_ts[1:])):
        raise FeatureError("source_ts must be sorted ascending")
    if any(b < a for a, b in zip(grid_ts, grid_ts[1:])):
        raise FeatureError("grid_ts must be sorted ascending")
    out: list[float | None] = []
    i = 0
    carried: float | None = None
    for g in grid_ts:
        while i < len(source_ts) and source_ts[i] <= g:
            carried = source_values[i]
            i += 1
        out.append(carried)
    return out
```

- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): as-of alignment, with the look-ahead guard as a property test`

---

### Task 3: Funding features

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Consumes: `_validate_rates` from Task 1.
- Produces: `funding_zscore(rates, *, window)`, `funding_sign_persistence(rates)`, `funding_accrued_carry(rates, *, window)` — all `list[float | None]`, same length as input, null-propagating.

- [ ] **Step 1: Write the failing tests**

```python
from cli.features.derivatives import funding_accrued_carry, funding_sign_persistence, funding_zscore

def test_funding_zscore_recovers_a_planted_value():
    """Planted signal (spec D10): a constant series then one print 2 sd above it."""
    rates = [0.0001] * 10 + [0.0009]
    z = funding_zscore(rates, window=10)
    assert z[-1] is not None and z[-1] > 3.0

def test_funding_zscore_of_a_constant_series_is_zero_not_spurious():
    z = funding_zscore([0.0001] * 12, window=10)
    assert z[-1] == 0.0

def test_funding_zscore_propagates_null():
    z = funding_zscore([0.0001] * 10 + [None], window=10)
    assert z[-1] is None

def test_sign_persistence_counts_consecutive_same_sign_prints():
    assert funding_sign_persistence([0.1, 0.2, 0.3, -0.1, -0.2]) == [1, 2, 3, 1, 2]

def test_accrued_carry_sums_the_window():
    assert funding_accrued_carry([1.0, 2.0, 3.0, 4.0], window=2)[-1] == 7.0
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement all three, each with a causality docstring in the house form**
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): funding level, z-score, sign persistence and accrued carry`

---

### Task 4: OI features

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `oi_log_delta(levels)`, `oi_zscore(levels, *, window)`, `oi_momentum(levels, *, lookback)` — `list[float | None]`, null-propagating. OI is strictly positive, so these use `_validate_prices`.

- [ ] **Step 1: Write the failing tests**

```python
import math
from cli.features.derivatives import oi_log_delta, oi_momentum, oi_zscore

def test_oi_log_delta_is_the_log_ratio_and_starts_none():
    out = oi_log_delta([100.0, 110.0])
    assert out[0] is None
    assert out[1] == math.log(110.0 / 100.0)

def test_oi_zscore_recovers_a_planted_spike():
    out = oi_zscore([100.0] * 10 + [180.0], window=10)
    assert out[-1] is not None and out[-1] > 3.0

def test_oi_momentum_is_causal_over_the_lookback():
    assert oi_momentum([100.0, 100.0, 100.0, 125.0], lookback=3)[-1] == 0.25
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): OI log-delta, z-score and momentum`

---

### Task 5: Per-year coverage, so a trial cannot run blind

**Files:**
- Modify: `cli/features/derivatives.py`
- Test: `tests/test_features_derivatives.py`

**Interfaces:**
- Produces: `coverage_by_year(ts, values) -> dict[int, tuple[int, int]]` — year -> (non_null, total). Spec D6.

- [ ] **Step 1: Write the failing test, built on the real defect this exists to surface**

```python
from datetime import datetime, timezone
from cli.features.derivatives import coverage_by_year

def test_coverage_by_year_exposes_a_single_bad_year():
    """The shape that motivated D6: an overall null rate reads as a nuisance while one year is
    almost entirely missing. Coverage must show the year, not the aggregate."""
    UTC = timezone.utc
    ts = ([datetime(2021, 6, 1, tzinfo=UTC)] * 10
          + [datetime(2022, 6, 1, tzinfo=UTC)] * 10
          + [datetime(2023, 6, 1, tzinfo=UTC)] * 10)
    vals = [1.0] * 10 + [None] * 9 + [1.0] + [1.0] * 10
    cov = coverage_by_year(ts, vals)
    assert cov[2021] == (10, 10)
    assert cov[2022] == (1, 10)
    assert cov[2023] == (10, 10)
```

- [ ] **Step 2: Run, expect failure**
- [ ] **Step 3: Implement**
- [ ] **Step 4: Run, expect pass**
- [ ] **Step 5: Commit** — `feat(features): per-year coverage, because an aggregate null rate hides a missing year`

---

### Task 6: Closeout

- [ ] **Step 1:** Append the iterations-history entry to `docs/iterations-history-phase4.md` (B-family is Phase 4 subject matter) via the `iteration-closeout` skill.
- [ ] **Step 2:** Append the Phase-4 decisions-log entry to `docs/research/10.phase4-decisions.md` for the subject-matter decisions this iteration made (the 2022 coverage finding and its consequence for feature selection).
- [ ] **Step 3:** Update `T0023` to `partial` with a `## Done so far` recording the harness, and trim its next steps to the remainder (the family, the trials, liquidations).
- [ ] **Step 4:** Run `uv run pre-commit run -a` and the full reachable test set; commit.
