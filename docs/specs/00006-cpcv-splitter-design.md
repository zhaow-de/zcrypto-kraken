# CPCV Splitter (Combinatorial Purged Cross-Validation) — Design (Phase 2)

**Iteration:** iter-013 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 (validation methodology — "the harness is the product", esp. §9.2 CPCV + purge/embargo, §9.1 leak-free labeling), §12 Phase 2. **Opens** the validation-harness package `cli/validation/`.

## Problem & context

Phase 2 builds the first-class validation harness **before any strategy exists**, proven on synthetic data (§12). Its backbone (§9.2) is **combinatorial purged cross-validation (CPCV)**: partition the time-ordered sample into `N` contiguous groups, use every combination of `k` groups as the test set (`C(N, k)` splits; N=10, k=2 → 45), and report the *distribution* of path performance rather than a single train/test estimate. Two leakage defenses (§9.1) are intrinsic to the splitter:

- **Purge** — a training observation whose forward-label window reaches into the test span leaks the test outcome into training and must be dropped.
- **Embargo** — training observations immediately *after* a test block are dropped as a serial-correlation buffer (set ≥ label horizon + feature lookback, §9.1), since features there can peek back into the test period.

This is the encode-the-lesson deliverable: the PoC's leakage came from validation that let labels bleed across the train/test boundary. The splitter makes purge+embargo structural, and the acceptance suite (a later Phase-2 iteration) will inject a deliberate look-ahead bug and require these to catch it.

## Goals

- **`cli/validation/`** — a new, lean, stdlib-only package opening the §9 harness. This iteration delivers the CPCV **splitter** only: contiguous grouping, the `C(N, k)` combinatorial train/test index sets, purge, embargo, and the backtest-path count. Pure functions over integer positions (no data, no strategy) — ideal unattended TDD.
- Faithful to §9.1/§9.2 and property-tested: no train index leaks into any test block after purge/embargo; every group is in the test set exactly `C(N-1, k-1)` times.

## Non-goals

- No backtest-path *reconstruction* (assembling per-path prediction series from the split predictions) — a follow-up once a model produces predictions; the split enumeration + path count here is its foundation.
- No DSR / PBO / bootstrap / SPA / multi-seed / cost model / registry hash-chain — each is its own Phase-2 iteration.
- No feature-lookback parameter as a distinct knob — per §9.1 the caller folds lookback into `embargo` (`embargo ≥ label horizon + feature lookback`); adding a separate knob is deferred (YAGNI).
- No `zcrypto` CLI subcommand — the harness is a library package (like `cli/backfill/`, `cli/universe/`), invoked by later harness code and tests, not an end-user command. No README Usage change.
- No new third-party deps (stdlib `itertools`, `math` only; pytest for tests).

## Design

New package `cli/validation/` mirroring the style of `cli/backfill/` / `cli/universe/` (module + `errors.py` + `__init__.py`; logger names `get_logger("validation.<module>")` if any logging is added — the splitter is pure and needs none).

**`cli/validation/errors.py`** — `class ValidationError(Exception)`.

**`cli/validation/cpcv.py`:**

- `make_groups(n_samples: int, n_groups: int) -> list[tuple[int, int]]`
  Partition `[0, n_samples)` into `n_groups` contiguous `[start, stop)` half-open blocks of near-equal size; the first `n_samples % n_groups` blocks are one larger, so sizes differ by at most 1 and the blocks exactly tile `[0, n_samples)`. Raises `ValidationError` if `n_groups < 2` or `n_samples < n_groups`.

- `n_backtest_paths(n_groups: int, n_test_groups: int) -> int`
  The number of CPCV backtest paths through the data `= C(n_groups - 1, n_test_groups - 1)` (equivalently `k/N · C(N, k)`; = the number of test combinations each fixed group participates in). Raises `ValidationError` unless `n_groups ≥ 2` and `1 ≤ n_test_groups < n_groups`.

- `cpcv_splits(n_samples: int, *, n_groups: int = 10, n_test_groups: int = 2, label_horizon: int = 0, embargo: int = 0) -> list[dict]`
  For each combination `test_groups` of `n_test_groups` group-indices out of `n_groups` (in `itertools.combinations(range(n_groups), n_test_groups)` order), the **test** index set is the union of those groups' positions; the **train** index set is every other position, minus purged and embargoed positions. Returns one dict per combination, ascending by combination order:
  `{"test_groups": tuple[int, ...], "train": list[int], "test": list[int]}` (both index lists sorted ascending).

  **Purge + embargo** are applied per **contiguous test block** `[a, b]` (a maximal run of adjacent test positions — with `k ≥ 2` the test groups may be non-adjacent, giving several disjoint blocks; adjacent test groups merge into one block):
  - **purge (before the block):** drop training indices in `[a - label_horizon, a)` — their forward label window `[j, j + label_horizon]` reaches into the test block.
  - **embargo (after the block):** drop training indices in `(b, b + embargo]` — serial-correlation buffer; the caller sets `embargo ≥ label_horizon + feature lookback` per §9.1.

  Removal ranges are clamped to `[0, n_samples)`. Test positions are inherently excluded from train. `label_horizon = embargo = 0` ⇒ no purge/embargo (train = complement of test). Raises `ValidationError` if `n_groups < 2`, not `1 ≤ n_test_groups < n_groups`, `n_samples < n_groups`, `label_horizon < 0`, or `embargo < 0`.

**`cli/validation/__init__.py`** — export `ValidationError`, `make_groups`, `n_backtest_paths`, `cpcv_splits`.

## Testing

`tests/test_validation_cpcv.py` (pytest; property-style via parametrization + fixed-seed randomized loops, no `hypothesis` dep):

- **`make_groups`** — for several `(n_samples, n_groups)`: exactly `n_groups` blocks; contiguous and half-open tiling `[0, n_samples)` with no gaps/overlaps; sizes differ by ≤ 1; raises on `n_groups < 2` and `n_samples < n_groups`.
- **`n_backtest_paths`** — known values: `(6,2)→5`, `(10,2)→9`, `(10,3)→36`, `(5,1)→1`; raises on `n_test_groups = 0`, `n_test_groups = n_groups`, `n_groups = 1`.
- **`cpcv_splits` count** — number of splits `= C(n_groups, n_test_groups)`; `test_groups` tuples are exactly the combinations.
- **Disjointness** — every split has `set(train) ∩ set(test) == ∅`; both lists sorted ascending; `test` equals the union of its groups' positions.
- **Coverage (property)** — with `label_horizon = embargo = 0`, across all splits each position `0..n-1` appears in `test` exactly `C(n_groups-1, n_test_groups-1)` times, and `train ∪ test == all positions` per split.
- **Purge (property)** — with `label_horizon = H > 0`, for every split and every contiguous test block `[a, b]`, no train index lies in `[a - H, a)`; equivalently no train `j` has `[j, j+H]` overlapping a test position.
- **Embargo (property)** — with `embargo = E > 0`, for every split and test block ending at `b`, no train index lies in `(b, b + E]`.
- **Combined + non-adjacent test groups** — a case with `n_test_groups = 2` picking non-adjacent groups yields two blocks, each independently purged/embargoed; a case with adjacent test groups yields one merged block.
- **Guards** — each invalid parameter raises `ValidationError`.

## Deferred / parked

Backtest-path reconstruction; a distinct feature-lookback knob; timestamp/label-interval inputs (v1 is fixed-horizon integer positions, matching our forward-return labels); all other §9 harness components (DSR, PBO, bootstrap, SPA, multi-seed, registry hash-chain, cost model, acceptance suite) as their own iterations.

## Closeout (planned)

On merge: append the `iter-013` `docs/iterations-history.md` entry. No dataset/report artifacts (pure library). The `.tmp/decisions.md` `[iter-013]` entry stays in the running log (drained at the Phase-2 close-out, not now).
