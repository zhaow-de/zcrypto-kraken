# Acceptance Suite (Injected-Leak) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `overlapping_label_series` + `nn_leak_metric` to `cli/validation/synthetic.py` + `tests/test_acceptance_leak.py` per `docs/specs/00014-acceptance-leak-design.md` — an analytically-grounded data leak that CPCV's `label_horizon`+`embargo` measurably removes.

**Architecture:** Extend `cli/validation/synthetic.py`; export the two functions; a synthetic unit-test addition + the leak acceptance test. TDD.

**Tech Stack:** Python 3.14, stdlib `random`, `math`, `statistics`, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only. Deterministic (`random.Random(seed)`). Guards raise `ValidationError`. Do NOT loosen the leak thresholds — if one fails, STOP + report BLOCKED with the measured `leaked`/`purged`. No CLI/README change.

---

### Task 1: `overlapping_label_series` + `nn_leak_metric` + unit tests

**Files:** Modify `cli/validation/synthetic.py`, `cli/validation/__init__.py`, `tests/test_validation_synthetic.py`.

- [ ] **Step 1: Append failing unit tests** to `tests/test_validation_synthetic.py`:

```python
def test_overlapping_label_series_reproducible_and_shaped():
    a = overlapping_label_series(50, horizon=5, seed=1)
    assert a == overlapping_label_series(50, horizon=5, seed=1)
    x, y = a
    assert len(x) == 50 and len(y) == 50 and x == [float(t) for t in range(50)]


def test_overlapping_label_covariance():
    _x, y = overlapping_label_series(20000, horizon=10, seed=2)
    import statistics as _st
    var = _st.variance(y)
    cov1 = _st.covariance(y[:-1], y[1:])          # |i-j|=1 -> ~ horizon-1 = 9
    cov_h = _st.covariance(y[:-10], y[10:])       # |i-j|=horizon -> ~0
    assert abs(var - 10) < 1.0
    assert abs(cov1 - 9) < 1.0
    assert abs(cov_h) < 0.5


@pytest.mark.parametrize(
    "kwargs",
    [{"n": 0, "horizon": 5, "seed": 1}, {"n": 10, "horizon": 0, "seed": 1}, {"n": 10, "horizon": 2.5, "seed": 1}, {"n": 10, "horizon": 5, "seed": "x"}],
)
def test_overlapping_label_series_guards(kwargs):
    with pytest.raises(ValidationError):
        overlapping_label_series(**kwargs)


def test_nn_leak_metric_nearest_pick():
    # features = index; test point 2's nearest train index is 1 (or 3). labels chosen so the pick is unambiguous.
    feats = [0.0, 1.0, 2.0, 3.0, 4.0]
    labels = [10.0, 5.0, 100.0, 5.0, 10.0]
    # train {0,1,3,4}, test {2}: nearest to index 2 is 1 or 3 (dist 1); tie -> smaller |i-j| equal -> smaller j = 1
    assert nn_leak_metric(feats, labels, [0, 1, 3, 4], [2]) == 5.0 * 100.0


@pytest.mark.parametrize(
    "args",
    [
        ([1.0], [1.0, 2.0], [0], [0]),          # length mismatch
        ([1.0, 2.0], [1.0, 2.0], [], [0]),      # empty train
        ([1.0, 2.0], [1.0, 2.0], [0], []),      # empty test
        ([1.0, 2.0], [1.0, 2.0], [5], [0]),     # out-of-range
        ([1.0, float("nan")], [1.0, 2.0], [0], [1]),  # non-finite
    ],
)
def test_nn_leak_metric_guards(args):
    with pytest.raises(ValidationError):
        nn_leak_metric(*args)
```

- [ ] **Step 2: Run, verify fail** — `uv run pytest tests/test_validation_synthetic.py -q` → ImportError on the new names.

- [ ] **Step 3: Append to `cli/validation/synthetic.py`:**

```python
def overlapping_label_series(n: int, *, horizon: int, seed: int) -> tuple[list[float], list[float]]:
    """Feature x_t = t (index); label y_t = sum of `horizon` consecutive N(0,1) noise terms (overlapping labels).

    Cov(y_i, y_j) = horizon - |i-j| for |i-j| < horizon, else 0. x carries no signal — any OOS skill is leakage.
    """
    if not isinstance(n, int) or n < 1:
        raise ValidationError(f"n must be an int >= 1, got {n!r}")
    if not isinstance(horizon, int) or horizon < 1:
        raise ValidationError(f"horizon must be an int >= 1, got {horizon!r}")
    if not isinstance(seed, int):
        raise ValidationError(f"seed must be an int, got {seed!r}")
    rng = random.Random(seed)
    noise = [rng.gauss(0.0, 1.0) for _ in range(n + horizon - 1)]
    features = [float(t) for t in range(n)]
    labels = [sum(noise[t : t + horizon]) for t in range(n)]
    return features, labels


def nn_leak_metric(
    features: list[float], labels: list[float], train_idx: list[int], test_idx: list[int]
) -> float:
    """Mean over test of labels[j*]*labels[i], where j* is the nearest train index by feature (ties: smaller
    |i-j|, then smaller j). With features=index this is a 1-NN-by-index leak probe."""
    if len(features) != len(labels):
        raise ValidationError(f"features and labels must match in length ({len(features)} != {len(labels)})")
    if not train_idx or not test_idx:
        raise ValidationError("train_idx and test_idx must be non-empty")
    size = len(features)
    for name, idxs in (("train_idx", train_idx), ("test_idx", test_idx)):
        for j in idxs:
            if not isinstance(j, int) or not (0 <= j < size):
                raise ValidationError(f"{name} contains an out-of-range/non-int index {j!r}")
    for v in (*features, *labels):
        if not math.isfinite(v):
            raise ValidationError(f"non-finite value {v}")
    train = list(train_idx)
    total = 0.0
    for i in test_idx:
        xi = features[i]
        best_j = min(train, key=lambda j: (abs(features[j] - xi), abs(j - i), j))
        total += labels[best_j] * labels[i]
    return total / len(test_idx)
```

  (The `min(..., key=lambda j: ...)` closure reads the current `xi`/`i`; `min` completes each iteration before they rebind — correct.)

- [ ] **Step 4: Export** in `cli/validation/__init__.py` — add `nn_leak_metric`, `overlapping_label_series` (keep all existing; `__all__` alphabetized).

- [ ] **Step 5: Run unit tests, verify pass** — `uv run pytest tests/test_validation_synthetic.py -q`.

---

### Task 2: `tests/test_acceptance_leak.py`

- [ ] **Step 1: Write the leak acceptance test:**

```python
import statistics

from cli.validation import cpcv_splits, nn_leak_metric, overlapping_label_series

N, H, N_GROUPS = 1000, 30, 40


def _mean_leak(*, label_horizon, embargo):
    x, y = overlapping_label_series(N, horizon=H, seed=11)
    splits = cpcv_splits(N, n_groups=N_GROUPS, n_test_groups=1, label_horizon=label_horizon, embargo=embargo)
    return statistics.mean(nn_leak_metric(x, y, s["train"], s["test"]) for s in splits)


def test_embargo_removes_the_injected_leak():
    # Without purge/embargo the 1-NN-by-index predictor picks an overlapping-label boundary neighbor -> fake
    # OOS skill (the leak, ~23). With label_horizon=H (purge before) + embargo=H (purge after) the H boundary
    # indices on both sides are removed -> nearest train >= H away -> no overlap -> ~0. The harness catches it.
    leaked = _mean_leak(label_horizon=0, embargo=0)
    purged = _mean_leak(label_horizon=H, embargo=H)
    assert leaked > 5.0
    assert abs(purged) < 2.0
    assert leaked > 5 * abs(purged)
```

- [ ] **Step 2: Run, verify pass** — `uv run pytest tests/test_acceptance_leak.py -q`. If ANY assertion fails, STOP + report BLOCKED with the actual `leaked` and `purged` — do NOT loosen. (A failure means the leak wasn't constructed as intended.)

- [ ] **Step 3: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green. Note the runtime of `test_acceptance_leak.py` (should be ~1-2s).

- [ ] **Step 4: Commit** — `test(validation): add injected-leak acceptance test (embargo removes the leak)`.

---

### Task 3: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append `## 2026-07-08 — iter-022: acceptance suite — injected-leak detection (Phase 2)`: `cli/validation/synthetic.py` gains `overlapping_label_series` (labels = H-sum of noise → `Cov(y_i,y_j)=H-|i-j|`) + `nn_leak_metric` (1-NN-by-index leak probe); `tests/test_acceptance_leak.py` shows CPCV's `label_horizon`+`embargo` **removes** a genuine leak (unpurged mean ŷ·y ≈ REPORTED, purged ≈ REPORTED). Report the actual measured `leaked`/`purged`. Completes the §9 acceptance triad (recovery iter-020 + this leak + registry-corruption iter-019) on synthetic data — a Phase-2 exit-bar milestone (captured-spread cost validation remains T0003-gated). Spec/plan `00014`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-022 closeout — injected-leak acceptance test`.
