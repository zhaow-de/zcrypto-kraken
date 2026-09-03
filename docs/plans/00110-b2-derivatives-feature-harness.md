# B2 derivatives-positioning feature harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> ## ✅ The pin's eleven refutations are ADDRESSED (2026-09-03)
>
> A contract-pin run on 2026-09-02 graded 34 premises and refuted 11 before the auto-exec time-gate cut the loop. All eleven are now fixed in this pair; the review loop restarts at the pin against the corrected version. What changed, so a reader can check the fixes rather than trust them:
>
> - **Task 2's look-ahead guard was inert and is replaced.** The old form appended source rows *past the grid's last stamp*, which cannot move any value under any semantics — the pin showed it passing on a deliberate backward-fill defect. The new form truncates: recompute over `grid[:k]` from rows stamped `<= grid[k-1]` and demand the prefix match. **Re-verified here on both arms: old guard passes correct AND defect; new guard passes correct, trips defect.**
> - **Both planted-signal thresholds asserted `> 3.0`, which no window definition produces.** Spec D7 now pins the semantics (inclusive trailing window ending at `k`, sample stdev, `None` when short or null-bearing, `0.0` at zero variance) and both tests assert the pinned definition's exact value, `2.8460498941515410` — computed, not thresholded.
> - **Task 4 asked null propagation through `_validate_prices`, which raises on `None`.** Task 1 now adds `_validate_levels` (finite, `> 0`, or `None`).
> - **"Matching the convention exactly" was false about length.** The existing five return `len(prices) - 1`, aligned to `returns_from_prices`; these align to the input grid and return `len(input)`. Stated in both artefacts.
> - **Four spec facts corrected**: the 2022 hole is panel-wide (87.3 % in nine symbols, 87.0 % in XRP; panel null 18.4 %, not BTC's diluted 14.9 %); "none before 2022-01-30" is true only within 2022; the B2 quote is master-plan **§5**, not §12; B1's band is **4h only**, so D3's grid choice survives on a different and stated reason.
> - **Two bookkeeping errors**: the spec's claim about the catalog was already discharged by its own commit `523a4034`, and `T0023` is already `partial` so Task 6's flip was a no-op — its real work is the `## Done so far` entry and the next-steps trim.
>
> The pin's full fact file is at `.tmp/plan-review/00110/pin-facts.md` — gitignored, so this block is the durable record.


**Goal:** Build the funding + OI feature harness B2 will be measured with, proven on known answers before any verdict counts.

**Architecture:** Pure functions on plain Python lists in `cli/features/derivatives.py`, matching the existing `cli/features/` convention in the three traits that transfer — keyword-only params after the data, a docstring stating the causality property, `_validate_*` raising `FeatureError` — and **deliberately NOT in output length**: the existing five return `len(prices) - 1` because they align to `returns_from_prices`, while these align to the input grid and return `len(input)` with `None` where undefined (spec D7). No polars, no frames, no I/O — the substrate readers already exist in `cli/derivatives/`.

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
- Produces: `_validate_rates(name, values)` — finite floats of ANY sign, or `None`.
- Produces: `_validate_levels(name, values)` — finite floats `> 0`, or `None`. Needed because `_validate_prices` raises on `None` and OI features must propagate it (spec D5).

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
import pytest
from datetime import datetime, timezone

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

def test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit():
    """The look-ahead guard (spec D2/D10), in the form that actually bites.

    An earlier draft appended FUTURE source rows beyond the grid's last stamp and asserted the
    result was unchanged. The contract pin showed that test passes on a deliberate backward-fill
    defect (`if t >= g: return x`, which reads the NEXT source row) as readily as on the correct
    implementation, because rows past the grid's end cannot move any value under either semantics.

    This form truncates instead: recompute over `grid[:k]` using only source rows stamped at or
    before `grid[k-1]`, and demand the prefix match the full run's. The defect trips at k=1
    (`[None]` vs `[2.0]`); the correct implementation passes."""
    src_ts, src_v = [_t(0), _t(8)], [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8)]
    full = align_asof(src_ts, src_v, grid)
    for k in range(1, len(grid) + 1):
        cutoff = grid[k - 1]
        visible = [(t, v) for t, v in zip(src_ts, src_v) if t <= cutoff]
        prefix = align_asof([t for t, _ in visible], [v for _, v in visible], grid[:k])
        assert prefix == full[:k], f"prefix at k={k} disagrees with the full run"
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
    """Planted signal (spec D10) under D7's pinned window: inclusive trailing window ending at k,
    sample stdev. Nine identical prints then one outlier scores exactly 2.8460498941515410 --
    verified by computation, not asserted as a threshold. An earlier draft asserted `> 3.0`, which
    no window definition can produce: population stdev gives exactly 3.0, exclusive is undefined."""
    rates = [0.0001] * 10 + [0.0009]
    z = funding_zscore(rates, window=10)
    assert z[-1] == pytest.approx(2.8460498941515410)

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
- Produces: `oi_log_delta(levels)`, `oi_zscore(levels, *, window)`, `oi_momentum(levels, *, lookback)` — `list[float | None]`, null-propagating. OI is strictly positive **and nullable**, which `_validate_prices` cannot express — it raises `FeatureError` on `None` (verified). Task 1 therefore adds `_validate_levels` alongside `_validate_rates`: finite, `> 0`, or `None`.

- [ ] **Step 1: Write the failing tests**

```python
import math
from cli.features.derivatives import oi_log_delta, oi_momentum, oi_zscore

def test_oi_log_delta_is_the_log_ratio_and_starts_none():
    out = oi_log_delta([100.0, 110.0])
    assert out[0] is None
    assert out[1] == math.log(110.0 / 100.0)

def test_oi_zscore_recovers_a_planted_spike():
    """Same pinned definition, same arithmetic as the funding case."""
    out = oi_zscore([100.0] * 10 + [180.0], window=10)
    assert out[-1] == pytest.approx(2.8460498941515410)

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
- [ ] **Step 3:** `T0023` is ALREADY `partial` (set at iter-090) and its `ripe_when` — "the B2 derivatives-positioning family is picked for an iteration" — is satisfied by this branch, so there is no status flip to make. The real work is the `## Done so far` entry recording the harness and trimming `## Suggested next steps`, whose second bullet is exactly this harness, to the remainder (the family, the trials, liquidations).
- [ ] **Step 4:** Run `uv run pre-commit run -a` and the full reachable test set; commit.
