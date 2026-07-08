# SPA / Reality Check — Design (Phase 2)

**Iteration:** iter-023 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9.4 ("a SPA/White reality check against the benchmark family … the deployment-relevant test: is anything here better than disciplined beta-timing?"), §12 Phase 2, §7. Extends `cli/validation/` (reuses the stationary bootstrap, iter-016).

## Problem & context

The deployment-relevant question (§9.4) is: across a whole family of candidate strategies, does the *best* one genuinely beat the benchmark, after correcting for the data-snooping that comes from trying many? **White's Reality Check** (2000) answers it: the statistic is the best strategy's mean outperformance over the benchmark; a stationary-bootstrap null distribution (recentered to impose "no strategy outperforms") gives a p-value. This iteration builds the machinery, proven on synthetic data now; the **benchmark family** it runs against is fixed in Phase 3.

**Why the Reality Check (not studentized Hansen SPA) for v1:** it's calibrated (White proved it), needs no per-strategy variance estimate, and — unlike the studentized `/ω_k` form — has **no NaN trap** (p ∈ (0,1] by construction). Hansen's studentized SPA + data-dependent recentering is a later refinement.

## Goals

- **`cli/validation/spa.py`** — `reality_check_pvalue` over a `T×K` outperformance matrix, reusing `stationary_bootstrap_indices`. **`cli/validation/synthetic.py`** gains `outperformance_matrix` (the scaffold). **`tests/test_acceptance_spa.py`** — a planted-superior family → low p, an all-null family → false-positive rate ≈ the nominal level.

## Non-goals

- No studentized Hansen SPA (SPA_c/SPA_l/SPA_u), no HAC variance estimator, no automatic `mean_block` selection — deferred. No real benchmark/strategy (Phase 3). No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

Add `cli/validation/spa.py` (reuse `errors.ValidationError`, `cli.validation.bootstrap.stationary_bootstrap_indices`):

- `reality_check_pvalue(perf_matrix: list[list[float]], *, mean_block: float, n_resamples: int = 1000, seed: int) -> dict`
  `perf_matrix` is `T×K` (rows = time, cols = strategies), entry `[t][k]` = strategy `k`'s **outperformance over the benchmark** at period `t`.
  1. Validate: non-empty, rectangular, `T = len ≥ 2`, `K = len(row) ≥ 1`, every cell finite. Else `ValidationError`. (`mean_block`/`n_resamples`/`seed` are validated by the `stationary_bootstrap_indices` call.)
  2. `dbar[k] = mean_t perf_matrix[t][k]`; `V_obs = max_k dbar[k]` (best strategy's mean outperformance).
  3. `rows_list = stationary_bootstrap_indices(T, mean_block=mean_block, n_resamples=n_resamples, seed=seed)`. For each resample's row indices: `dbar*[k] = mean over those rows of perf_matrix[row][k]`; `V* = max_k (dbar*[k] − dbar[k])` (recentered by the observed mean ⇒ imposes the least-favorable null). `count += (V* ≥ V_obs)`.
  4. `p_value = (1 + count) / (n_resamples + 1)` (small-sample-safe; `∈ (0, 1]`, never 0/NaN).
  5. Return `{"p_value": p_value, "statistic": V_obs, "best_strategy": argmax_k dbar[k], "n_resamples": n_resamples}`.

**`cli/validation/synthetic.py`** (append):
- `outperformance_matrix(n_periods: int, n_strategies: int, *, edge: float, seed: int, edge_col: int = 0) -> list[list[float]]`
  Deterministic `random.Random(seed)`: each row = `[rng.gauss(0,1) for _ in range(n_strategies)]`, then `row[edge_col] += edge`. `edge = 0` ⇒ all-null family; `edge > 0` ⇒ column `edge_col` outperforms by `edge`/period. Raises `ValidationError` if `n_periods < 1`, `n_strategies < 1`, `edge` non-numeric/non-finite, `seed` not `int`, or `edge_col` not `0 ≤ edge_col < n_strategies`.

**`cli/validation/__init__.py`** — export `reality_check_pvalue`, `outperformance_matrix`.

## Testing

`tests/test_validation_spa.py` + `tests/test_validation_synthetic.py` (append) + `tests/test_acceptance_spa.py`:

- **`outperformance_matrix`** — reproducible; shape `n_periods × n_strategies`; `edge > 0` makes `edge_col`'s column mean ≈ `edge` on large `n_periods` while others ≈ 0; guards raise.
- **`reality_check_pvalue`** — reproducible (same seed → same dict); `statistic == max(dbar)`, `best_strategy == argmax(dbar)`; `p_value ∈ (0, 1]`; on a hand-built matrix where one column dominates, `best_strategy` is that column and `p_value` is low. Guards: `T < 2`, `K < 1`, non-rectangular, non-finite cell raise.
- **Acceptance (`tests/test_acceptance_spa.py`):**
  - `test_spa_detects_a_superior_strategy` — `m = outperformance_matrix(500, 5, edge=0.2, seed=1)`; `r = reality_check_pvalue(m, mean_block=5, seed=2)`; assert `r["p_value"] < 0.05` and `r["best_strategy"] == 0`. (Derivation: `d̄_0 ≈ 0.2`, per-strategy SE ≈ `1/√500 ≈ 0.045`, so the recentered bootstrap max rarely reaches 0.2 ⇒ p ≈ 0.)
  - `test_spa_null_false_positive_rate_is_low` — for `seed in range(20)`: `m = outperformance_matrix(500, 5, edge=0.0, seed=seed)`; count `reality_check_pvalue(m, mean_block=5, seed=seed + 100)["p_value"] < 0.05`. Assert the count `<= 4` (nominal ≈ 5% ⇒ ~1 expected; `P(≥5)` tiny) — SPA does not over-declare superiority on noise.

Thresholds one-sided with wide margins; the implementer reports the actual planted p-value + the null false-positive count.

## Deferred / parked

Studentized Hansen SPA (SPA_c/l/u) + HAC variance; automatic `mean_block`; the multi-seed runner (§9.5 — YAGNI, the plan de-emphasizes stochastic learners; build when one is used); folding all acceptance tests into one named suite. The rest of §12 Phase-2. `outperformance_matrix`'s `edge` param is `isinstance`-guarded here (per the T0006 pattern).

## Closeout (planned)

On merge: append the `iter-023` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-023]` entry stays in the running log (drained at Phase-2 close-out). With this, §9.4's DSR + PBO + SPA are all in place — a Phase-2 exit-bar step (captured-spread cost validation remains T0003-gated).
