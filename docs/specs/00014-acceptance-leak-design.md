# Acceptance Suite — Injected-Leak Detection (Phase 2)

**Iteration:** iter-022 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 ("a look-ahead bug deliberately injected must be caught by the leakage tests"), §9.1/§9.2 (purge + embargo), §12 Phase 2 exit bar. Extends `cli/validation/` (CPCV iter-013, synthetic iter-020).

## Problem & context

The recovery + null acceptance (iter-020) proved the harness scores signal vs noise, but its CPCV call exercised only **fold structure**, not the **purge/embargo** leak-prevention — the toy rule wasn't fit to data, so there was nothing to leak. This iteration adds the §9 leak check: a genuine, analytically-grounded data leak that CPCV's `label_horizon`+`embargo` **measurably removes**.

**Why a fixed rule can't leak, and the construction that can.** A leak requires *fitting* to samples whose labels overlap the test period. Construction (all analytically grounded):

- **Overlapping labels** `y_t = Σ_{k=0}^{H-1} e_{t+k}` (sum of `H` consecutive i.i.d. `N(0,1)` noise terms). Then `Cov(y_i, y_j) = H − |i−j|` for `|i−j| < H`, else `0` — adjacent labels share noise.
- **Feature `x_t = t`** (the index), so a **1-nearest-neighbor-by-feature** predictor picks the nearest *training index*. There is **no real signal** (x carries no information about the noise) — any apparent OOS skill is pure leakage.
- **Leak metric** for a split: `mean over test i of ŷ_i · y_i`, where `ŷ_i = y[j*]`, `j* = argmin_{j∈train} |i − j|`. If the nearest train index is `d+1` away and `d+1 < H`, `E[ŷ_i·y_i] = Cov = H−(d+1) > 0` — **fake skill from the leak**; if `≥ H` away, `E = 0`.

**The demonstration:** with `n=1000`, `n_groups=40` (block size 25), `n_test_groups=1`, `H=30`, the whole test block is within `H` of its edges, so the nearest *unpurged* train index (the group boundary, distance `d+1 ≤ 13 < H`) leaks — mean leak ≈ **23**. Applying `label_horizon=H` (purge before) **and** `embargo=H` (purge after) removes the `H` boundary indices on both sides, pushing every nearest-train distance `≥ H+1` → leak ≈ **0**. The harness catches the injected leak. (`n=1000` keeps the O(n²) metric ~1s; the leak metric itself is generic over `features`.)

## Goals

- **`cli/validation/synthetic.py`** gains `overlapping_label_series` (the generator) + `nn_leak_metric` (the 1-NN-by-index leak evaluator), stdlib, deterministic. **`tests/test_acceptance_leak.py`** asserts `leak(no purge)` is clearly positive and `leak(label_horizon=H, embargo=H)` ≈ 0.

## Non-goals

- No real strategy/model beyond the toy 1-NN; no `sklearn`; no CLI/README change; no new deps. This proves the *mechanism* (embargo removes a leak), not a production ML pipeline.

## Design

Add to `cli/validation/synthetic.py` (reuse `errors.ValidationError`):

- `overlapping_label_series(n: int, *, horizon: int, seed: int) -> tuple[list[float], list[float]]`
  Draw `e` = `n + horizon − 1` i.i.d. `N(0,1)` via `random.Random(seed)`; `y_t = sum(e[t : t + horizon])`; `x_t = float(t)`. Returns `(features, labels)`, each length `n`. Raises `ValidationError` if `n < 1`, `horizon` not a positive `int`, or `seed` not an `int`.

- `nn_leak_metric(features: list[float], labels: list[float], train_idx: list[int], test_idx: list[int]) -> float`
  For each `i` in `test_idx`, `j* = argmin_{j∈train_idx} |features[i] − features[j]|` (ties → smaller `|i−j|` then smaller `j`; with `x=index` this is the nearest train index); accumulate `labels[j*] * labels[i]`; return the mean over `test_idx`. Raises `ValidationError` if `features`/`labels` differ in length, `train_idx`/`test_idx` empty, any index out of range, or any value non-finite. (O(test·train) is fine at these sizes.)

**`cli/validation/__init__.py`** — export `overlapping_label_series`, `nn_leak_metric`.

## Testing

`tests/test_validation_synthetic.py` (append): `overlapping_label_series` reproducible + shaped (`len==n`); the empirical `Cov(y_i, y_{i+1}) ≈ horizon−1` and `Cov(y_i, y_{i+horizon}) ≈ 0` on a large sample (±10%); guards (`n<1`, non-positive/non-int `horizon`, non-int `seed`). `nn_leak_metric`: on a tiny hand-built case the nearest-index pick is correct; guards (length mismatch, empty idx, out-of-range idx, non-finite) raise.

`tests/test_acceptance_leak.py` — the leak acceptance check:

```python
import statistics
from cli.validation import cpcv_splits, nn_leak_metric, overlapping_label_series

N, H, N_GROUPS = 1000, 30, 40


def _mean_leak(*, label_horizon, embargo):
    x, y = overlapping_label_series(N, horizon=H, seed=11)
    splits = cpcv_splits(N, n_groups=N_GROUPS, n_test_groups=1, label_horizon=label_horizon, embargo=embargo)
    return statistics.mean(nn_leak_metric(x, y, s["train"], s["test"]) for s in splits)


def test_embargo_removes_the_injected_leak():
    leaked = _mean_leak(label_horizon=0, embargo=0)     # ~23 (fake skill = the leak)
    purged = _mean_leak(label_horizon=H, embargo=H)     # ~0  (purge+embargo remove it)
    assert leaked > 5.0
    assert abs(purged) < 2.0
    assert leaked > 5 * abs(purged)
```

Thresholds are one-sided with wide margins vs the derived `leaked ≈ 17`, `purged ≈ 0`. The implementer reports the actual `leaked`/`purged`; if either threshold fails, STOP + report BLOCKED (do not loosen) — a failure means the leak wasn't constructed as intended, which must be fixed, not hidden.

## Deferred / parked

Folding recovery+null + this leak check + the iter-019 registry-corruption test into a single named `acceptance` module/suite is cosmetic packaging (all three tests already run in CI) — optional follow-up. A production ML leak scenario is out of scope. The rest of §9/§12 Phase-2.

## Closeout (planned)

On merge: append the `iter-022` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-022]` entry stays in the running log (drained at Phase-2 close-out). With recovery+null (iter-020) + leak (this) + registry-corruption (iter-019), the §9 acceptance triad on synthetic data is complete — a Phase-2 exit-bar milestone (captured-spread cost validation remains T0003-gated).
