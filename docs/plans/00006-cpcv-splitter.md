# CPCV Splitter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Open the `cli/validation/` harness package with the CPCV (combinatorial purged cross-validation) splitter — contiguous grouping, `C(N,k)` train/test index sets, purge, embargo, backtest-path count — pure functions over integer positions, per `docs/specs/00006-cpcv-splitter-design.md`.

**Architecture:** New stdlib-only package `cli/validation/` (`errors.py`, `cpcv.py`, `__init__.py`) mirroring `cli/backfill/` style. Pure functions; no data, no strategy, no logging. TDD.

**Tech Stack:** Python 3.14, stdlib `itertools` + `math` only, pytest. Ruff line-length 132, double quotes.

## Global Constraints

- stdlib-only (no new deps); `itertools.combinations`, `math.comb`.
- Ruff: line length 132, double quotes, import sorting (`select = ["I"]`).
- Commit gate is `uv run pre-commit run -a` (per CLAUDE.md).
- Purge/embargo semantics are **exactly** as the spec defines: per contiguous test block `[a, b]`, purge drops train in `[a - label_horizon, a)`, embargo drops train in `(b, b + embargo]`, both clamped to `[0, n_samples)`.
- `make_groups` returns `[start, stop)` half-open blocks, first `n_samples % n_groups` one larger.
- `n_backtest_paths(N, k) = math.comb(N-1, k-1)`.
- No `zcrypto` CLI subcommand, no README change.

---

### Task 1: `cli/validation/` CPCV splitter (errors + grouping + splits)

**Files:**
- Create: `cli/validation/__init__.py`, `cli/validation/errors.py`, `cli/validation/cpcv.py`
- Test: `tests/test_validation_cpcv.py`

**Interfaces:**
- Produces (consumed by later Phase-2 iterations + the acceptance suite):
  - `ValidationError(Exception)`
  - `make_groups(n_samples: int, n_groups: int) -> list[tuple[int, int]]`
  - `n_backtest_paths(n_groups: int, n_test_groups: int) -> int`
  - `cpcv_splits(n_samples: int, *, n_groups: int = 10, n_test_groups: int = 2, label_horizon: int = 0, embargo: int = 0) -> list[dict]` returning `{"test_groups": tuple, "train": list[int], "test": list[int]}` per combination.

- [ ] **Step 1: Write failing tests** in `tests/test_validation_cpcv.py` covering the full spec Testing section:

```python
import math

import pytest

from cli.validation import ValidationError, cpcv_splits, make_groups, n_backtest_paths


def _blocks(sorted_positions):
    """Contiguous runs [a, b] (inclusive) in an ascending list of ints."""
    blocks, start, prev = [], None, None
    for p in sorted_positions:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            blocks.append((start, prev))
            start = prev = p
    if start is not None:
        blocks.append((start, prev))
    return blocks


@pytest.mark.parametrize("n,g", [(10, 10), (23, 5), (100, 7), (12, 4)])
def test_make_groups_tiles_exactly(n, g):
    groups = make_groups(n, g)
    assert len(groups) == g
    assert groups[0][0] == 0 and groups[-1][1] == n
    for (s0, e0), (s1, e1) in zip(groups, groups[1:]):
        assert e0 == s1  # contiguous, no gaps/overlaps
    sizes = [e - s for s, e in groups]
    assert max(sizes) - min(sizes) <= 1
    assert sum(sizes) == n


@pytest.mark.parametrize("n,g", [(1, 2), (3, 5)])
def test_make_groups_guard(n, g):
    with pytest.raises(ValidationError):
        make_groups(n, g)


def test_make_groups_guard_too_few_groups():
    with pytest.raises(ValidationError):
        make_groups(100, 1)


@pytest.mark.parametrize("N,k,expected", [(6, 2, 5), (10, 2, 9), (10, 3, 36), (5, 1, 1)])
def test_n_backtest_paths(N, k, expected):
    assert n_backtest_paths(N, k) == expected


@pytest.mark.parametrize("N,k", [(10, 0), (10, 10), (1, 1)])
def test_n_backtest_paths_guard(N, k):
    with pytest.raises(ValidationError):
        n_backtest_paths(N, k)


def test_cpcv_split_count_and_test_groups():
    splits = cpcv_splits(100, n_groups=10, n_test_groups=2)
    assert len(splits) == math.comb(10, 2)
    from itertools import combinations

    assert [s["test_groups"] for s in splits] == list(combinations(range(10), 2))


def test_cpcv_disjoint_sorted_and_test_matches_groups():
    n, N = 100, 10
    groups = make_groups(n, N)
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2):
        assert set(s["train"]).isdisjoint(s["test"])
        assert s["train"] == sorted(s["train"])
        assert s["test"] == sorted(s["test"])
        expected_test = sorted(p for gi in s["test_groups"] for p in range(*groups[gi]))
        assert s["test"] == expected_test


def test_cpcv_coverage_no_purge():
    n, N, k = 60, 6, 2
    splits = cpcv_splits(n, n_groups=N, n_test_groups=k)
    counts = [0] * n
    for s in splits:
        assert sorted(s["train"] + s["test"]) == list(range(n))  # train ∪ test = all
        for p in s["test"]:
            counts[p] += 1
    assert set(counts) == {math.comb(N - 1, k - 1)}  # each position tested C(N-1,k-1) times


def test_cpcv_purge_removes_forward_leak():
    n, N, H = 100, 10, 3
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2, label_horizon=H):
        train = set(s["train"])
        for a, _b in _blocks(s["test"]):
            assert not (set(range(max(0, a - H), a)) & train)  # nothing in [a-H, a)


def test_cpcv_embargo_removes_after_test():
    n, N, E = 100, 10, 4
    for s in cpcv_splits(n, n_groups=N, n_test_groups=2, embargo=E):
        train = set(s["train"])
        for _a, b in _blocks(s["test"]):
            assert not (set(range(b + 1, min(n, b + 1 + E))) & train)  # nothing in (b, b+E]


def test_cpcv_non_adjacent_test_groups_two_blocks():
    # groups {0,2} of 10 over 100 samples -> two disjoint test blocks
    s = next(s for s in cpcv_splits(100, n_groups=10, n_test_groups=2) if s["test_groups"] == (0, 2))
    assert len(_blocks(s["test"])) == 2
    # adjacent groups {0,1} -> one merged block
    s2 = next(s for s in cpcv_splits(100, n_groups=10, n_test_groups=2) if s["test_groups"] == (0, 1))
    assert len(_blocks(s2["test"])) == 1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_groups": 1},
        {"n_test_groups": 0},
        {"n_test_groups": 10},
        {"label_horizon": -1},
        {"embargo": -1},
    ],
)
def test_cpcv_guards(kwargs):
    with pytest.raises(ValidationError):
        cpcv_splits(100, **kwargs)


def test_cpcv_guard_samples_below_groups():
    with pytest.raises(ValidationError):
        cpcv_splits(5, n_groups=10)
```

- [ ] **Step 2: Run tests, verify they fail** — `uv run pytest tests/test_validation_cpcv.py -q` → ImportError / failures.

- [ ] **Step 3: Implement `cli/validation/errors.py`:**

```python
class ValidationError(Exception):
    """Raised on invalid validation-harness inputs."""
```

- [ ] **Step 4: Implement `cli/validation/cpcv.py`** per the spec. Reference implementation:

```python
from __future__ import annotations

import math
from itertools import combinations

from cli.validation.errors import ValidationError


def make_groups(n_samples: int, n_groups: int) -> list[tuple[int, int]]:
    """Partition [0, n_samples) into n_groups contiguous [start, stop) blocks of near-equal size.

    The first `n_samples % n_groups` blocks are one larger, so sizes differ by at most 1 and the
    blocks exactly tile [0, n_samples).
    """
    if n_groups < 2:
        raise ValidationError(f"n_groups must be >= 2, got {n_groups}")
    if n_samples < n_groups:
        raise ValidationError(f"n_samples ({n_samples}) must be >= n_groups ({n_groups})")
    base, extra = divmod(n_samples, n_groups)
    groups, start = [], 0
    for i in range(n_groups):
        stop = start + base + (1 if i < extra else 0)
        groups.append((start, stop))
        start = stop
    return groups


def n_backtest_paths(n_groups: int, n_test_groups: int) -> int:
    """Number of CPCV backtest paths = C(n_groups - 1, n_test_groups - 1)."""
    if n_groups < 2:
        raise ValidationError(f"n_groups must be >= 2, got {n_groups}")
    if not 1 <= n_test_groups < n_groups:
        raise ValidationError(f"n_test_groups must satisfy 1 <= k < n_groups, got {n_test_groups}")
    return math.comb(n_groups - 1, n_test_groups - 1)


def _contiguous_blocks(positions: list[int]) -> list[tuple[int, int]]:
    """Maximal contiguous runs [a, b] (inclusive) in an ascending list of positions."""
    blocks: list[tuple[int, int]] = []
    start = prev = None
    for p in positions:
        if start is None:
            start = prev = p
        elif p == prev + 1:
            prev = p
        else:
            blocks.append((start, prev))
            start = prev = p
    if start is not None:
        blocks.append((start, prev))
    return blocks


def cpcv_splits(
    n_samples: int,
    *,
    n_groups: int = 10,
    n_test_groups: int = 2,
    label_horizon: int = 0,
    embargo: int = 0,
) -> list[dict]:
    """Combinatorial purged cross-validation splits (see docs/specs/00006)."""
    if label_horizon < 0:
        raise ValidationError(f"label_horizon must be >= 0, got {label_horizon}")
    if embargo < 0:
        raise ValidationError(f"embargo must be >= 0, got {embargo}")
    # make_groups + the n_test_groups bound raise ValidationError on the remaining invalid params.
    groups = make_groups(n_samples, n_groups)
    if not 1 <= n_test_groups < n_groups:
        raise ValidationError(f"n_test_groups must satisfy 1 <= k < n_groups, got {n_test_groups}")

    group_positions = [list(range(start, stop)) for start, stop in groups]
    splits: list[dict] = []
    for test_groups in combinations(range(n_groups), n_test_groups):
        test = sorted(p for gi in test_groups for p in group_positions[gi])
        test_set = set(test)
        removed = set(test)
        for a, b in _contiguous_blocks(test):
            removed.update(range(max(0, a - label_horizon), a))  # purge: forward-label leak
            removed.update(range(b + 1, min(n_samples, b + 1 + embargo)))  # embargo after block
        train = [p for p in range(n_samples) if p not in removed]
        splits.append({"test_groups": test_groups, "train": train, "test": test})
        del test_set  # (kept intentionally explicit; test disjointness enforced by `removed ⊇ test`)
    return splits
```

  Note: drop the `test_set`/`del` lines if ruff flags the unused local — they are illustrative; the operative guarantee is `removed ⊇ set(test)`, so `train` excludes every test index. Implement cleanly (no unused variables).

- [ ] **Step 5: Implement `cli/validation/__init__.py`:**

```python
from cli.validation.cpcv import cpcv_splits, make_groups, n_backtest_paths
from cli.validation.errors import ValidationError

__all__ = ["ValidationError", "cpcv_splits", "make_groups", "n_backtest_paths"]
```

- [ ] **Step 6: Run tests, verify they pass** — `uv run pytest tests/test_validation_cpcv.py -q` → all pass.

- [ ] **Step 7: Full gate** — `uv run pre-commit run -a` clean; `uv run pytest -q` (whole suite) green.

- [ ] **Step 8: Commit** — `feat(validation): add CPCV splitter with purge + embargo`.

---

### Task 2: iterations-history closeout

**Files:** Modify: `docs/iterations-history.md`

- [ ] **Step 1:** Append a `## 2026-07-08 — iter-013: CPCV splitter (Phase 2)` section: `cli/validation/` opened; `make_groups` / `n_backtest_paths` / `cpcv_splits` with purge (`[a-H, a)`) + embargo (`(b, b+E]`); property-tested (coverage `C(N-1,k-1)`, no leak); stdlib-only; first Phase-2 harness component (§9.2); spec/plan `00006`. Note the whole-branch review verdict.

- [ ] **Step 2: Commit** — `docs: iter-013 closeout — CPCV splitter`.
