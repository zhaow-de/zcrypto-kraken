# Probability of Backtest Overfitting (PBO via CSCV) — Design (Phase 2)

**Iteration:** iter-015 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9.4 (multiple-testing control — DSR **and** PBO), §12 Phase 2, §7 (integrity by construction — never NaN). Extends `cli/validation/` (CPCV iter-013, DSR iter-014).

## Problem & context

DSR (iter-014) answers "is the *best* Sharpe real, given N trials?". **PBO** answers the complementary question: "does the *selection process itself* overfit?" — i.e., when you pick the in-sample-best configuration, how often does it land below the median out-of-sample? PBO (Bailey, Borwein, López de Prado & Zhu) estimates this via **CSCV (combinatorial symmetric cross-validation)**: split the performance record into `S` time blocks, and over **every** balanced way to assign `S/2` blocks to in-sample (IS) and the rest to out-of-sample (OOS), measure the OOS rank of the IS-best config. PBO is the fraction of splits where that rank is below the OOS median. A high PBO (→1) means the backtest's config selection is overfitting; low (→0) means it generalizes.

Like DSR, this is a purely combinatorial/statistical function that **must never return NaN** (§7). Its logit is bounded by construction — the OOS rank normalizes to `r/(N+1) ∈ (0,1)` — so `logit` is always finite; degenerate *inputs* (non-rectangular matrix, non-finite cells, odd `S`, a metric that returns non-finite) raise `ValidationError`.

## Goals

- **`cli/validation/pbo.py`** — a `pbo(...)` function over a `T×N` performance matrix (rows = time observations, cols = strategy configs), reusing `cli.validation.cpcv.make_groups` for the block partition. Stdlib-only; pure; property-tested including the exact PBO=0 / PBO=1 constructions and the never-NaN discipline.

## Non-goals

- No performance-degradation / probabilistic-stochastic-dominance plots or the OOS-vs-IS scatter (the paper's other CSCV outputs) — PBO scalar only; the logit distribution is a cheap later add if a report needs it.
- No estimation of the perf matrix from strategies/returns — the caller supplies it.
- No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

Add to `cli/validation/` (reuse `errors.ValidationError`, `cpcv.make_groups`).

**`cli/validation/pbo.py`:**

- `pbo(perf_matrix: list[list[float]], *, n_splits: int = 16, metric: Callable[[list[float]], float] = statistics.mean) -> dict`

  1. **Validate:** `perf_matrix` non-empty and rectangular; `T = len(perf_matrix)` rows, `N = len(perf_matrix[0])` cols with `N >= 2`; every cell finite; `n_splits >= 2` and **even**; `T >= n_splits`. Else `ValidationError`. (`make_groups(T, n_splits)` also enforces `T >= n_splits`.)
  2. **Blocks:** `groups = make_groups(T, n_splits)` — `S = n_splits` contiguous `[start, stop)` row-blocks.
  3. For each `is_blocks` in `itertools.combinations(range(n_splits), n_splits // 2)` (so `C(S, S/2)` splits):
     - IS rows = union of those blocks' row ranges; OOS rows = the complement.
     - For each config `j`: `is_perf[j] = metric([perf_matrix[i][j] for i in IS rows])`, `oos_perf[j] = metric(... OOS rows ...)`. If any `is_perf`/`oos_perf` is non-finite → `ValidationError` (a custom `metric` that blew up; preserves never-NaN).
     - `n_star = argmax(is_perf)` (first max on ties).
     - `v = oos_perf[n_star]`; **average rank** `r = #{j: oos_perf[j] < v} + (#{j: oos_perf[j] == v} + 1) / 2` (so `r ∈ [1, N]`, includes `n_star` itself in the equality count).
     - `w = r / (N + 1)` (∈ `(0, 1)`); `lam = log(w / (1 - w))`. The split is **overfit** iff `lam < 0` (⟺ `w < 0.5` ⟺ IS-best below OOS median).
  4. `pbo = (# overfit splits) / (# splits)`.
  5. Return `{"pbo": float, "n_combinations": int}` (`n_combinations = C(n_splits, n_splits // 2)`).

**`cli/validation/__init__.py`** — additionally export `pbo`.

## Testing

`tests/test_validation_pbo.py` (pytest):

- **PBO = 0 (dominant config, exact).** `perf_matrix = [[10, 0]] * 4`, `n_splits=2` → the IS-best config is also OOS-best in both splits → `pbo == 0.0`; `n_combinations == 2`.
- **PBO = 1 (reversed, exact).** `[[5, 1], [5, 1], [1, 5], [1, 5]]`, `n_splits=2` → config 0 wins IS block 0 but loses OOS block 1, and vice-versa, in both splits → `pbo == 1.0`.
- **Bounds.** For a hand-fixed larger matrix (`T >= 16`, `N` several configs), `0.0 <= pbo <= 1.0` and `n_combinations == math.comb(16, 8)`.
- **`n_combinations`** equals `C(n_splits, n_splits // 2)` for `n_splits ∈ {2, 4, 16}`.
- **Custom metric.** A non-default `metric` is accepted and used: `pbo(matrix, metric=statistics.median)` on the bounds matrix returns a valid dict (`0.0 <= pbo <= 1.0`, correct `n_combinations`). (A `metric` returning non-finite is covered under guards below.)
- **Never-NaN / guards** — each raises `ValidationError`: odd `n_splits` (3); `n_splits < 2` (1); `T < n_splits`; single-config matrix (`N < 2`, e.g. `[[1], [2], [3], [4]]`); non-rectangular (`[[1, 2], [3]]`); a non-finite cell (`float("nan")`); a `metric` that returns `float("nan")`.

## Deferred / parked

The CSCV logit distribution + performance-degradation/PSD plots; perf-matrix construction from strategies; the rest of §9 (bootstrap, SPA, multi-seed, registry hash-chain, cost model, acceptance suite) as their own iterations.

## Closeout (planned)

On merge: append the `iter-015` `docs/iterations-history.md` entry. No dataset/report artifacts. The `.tmp/decisions.md` `[iter-015]` entry stays in the running log (drained at Phase-2 close-out).
