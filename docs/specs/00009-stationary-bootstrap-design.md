# Stationary Block Bootstrap CIs — Design (Phase 2)

**Iteration:** iter-016 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9.5 (stationary block bootstrap CIs on Sharpe, maxDD, and delta-vs-benchmark), §12 Phase 2, §7 (never NaN). Extends `cli/validation/` (CPCV/DSR/PBO — iter-013/14/15).

## Problem & context

The point metrics (DSR, PBO) say *whether* an edge is real; §9.5 wants the *uncertainty* around a headline statistic. The **stationary block bootstrap** (Politis & Romano, 1994) resamples a time series by concatenating blocks of **geometrically-distributed** length (wrapping around the series) — preserving short-range serial dependence that an i.i.d. bootstrap would destroy — to produce a distribution of any statistic and hence a percentile confidence interval. This is the harness's uncertainty layer, applied to Sharpe / max-drawdown / delta-vs-benchmark in later reporting.

Same integrity discipline (§7): reproducible given a seed, and **never NaN** — a non-finite series value, or a `statistic` that returns non-finite or raises, raises `ValidationError`.

## Goals

- **`cli/validation/bootstrap.py`** — `stationary_bootstrap_indices` (the resampling index generator) and `bootstrap_ci` (percentile CI of a caller-supplied statistic). Stdlib `random` (seeded) + `math`; pure/deterministic given the seed. Property-tested including reproducibility, index bounds, the constant-series exact case, and never-NaN.

## Non-goals

- No specific statistics (Sharpe/maxDD) baked in — the caller passes a `statistic` callable; a Sharpe/maxDD helper library is a later iteration.
- No bias-corrected/accelerated (BCa) intervals — plain percentile CI for v1 (BCa deferred).
- No automatic `mean_block` selection (Politis–White) — caller supplies it; auto-selection deferred.
- No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

Add to `cli/validation/` (reuse `errors.ValidationError`).

**`cli/validation/bootstrap.py`:**

- `stationary_bootstrap_indices(n_obs: int, *, mean_block: float, n_resamples: int, seed: int) -> list[list[int]]`
  Generate `n_resamples` index sequences, each length `n_obs`, via the stationary bootstrap with restart probability `p = 1 / mean_block`, using `random.Random(seed)`:
  start each resample at `rng.randrange(n_obs)`; for each subsequent position, with prob `p` jump to a fresh `rng.randrange(n_obs)`, else advance `i = (i + 1) % n_obs` (wrap). Deterministic given `seed`. Raises `ValidationError` unless `n_obs >= 1`, `mean_block >= 1` (finite), `n_resamples >= 1`, and `seed` is an `int`.

- `bootstrap_ci(series: list[float], statistic: Callable[[list[float]], float], *, mean_block: float, n_resamples: int = 1000, alpha: float = 0.05, seed: int) -> dict`
  1. Validate: `series` non-empty and all finite; `mean_block >= 1`; `n_resamples >= 1`; `0 < alpha < 1`; `seed` is `int`. Else `ValidationError`.
  2. `point = statistic(series)` — wrap the call in try/except → `ValidationError` (a raising statistic), and require `point` finite.
  3. For each of `stationary_bootstrap_indices(len(series), mean_block=mean_block, n_resamples=n_resamples, seed=seed)`: `stat = statistic([series[i] for i in idx])` (same try/except + finite guard).
  4. Sort the `n_resamples` stats; `lower = _percentile(stats, alpha/2)`, `upper = _percentile(stats, 1 - alpha/2)` via linear-interpolation percentile (`q ∈ [0,1]`: `pos = q·(m-1)`, interpolate between the floor/ceil order statistics).
  5. Return `{"point": point, "lower": lower, "upper": upper, "n_resamples": n_resamples, "mean_block": mean_block}` (`lower <= upper`).

**`cli/validation/__init__.py`** — additionally export `stationary_bootstrap_indices`, `bootstrap_ci`.

## Testing

`tests/test_validation_bootstrap.py` (pytest; `statistics.mean`, fixed seeds):

- **Reproducibility.** Two `bootstrap_ci(...)` calls with the same `seed` return identical dicts; `stationary_bootstrap_indices(...)` twice with the same seed returns identical index lists; a different seed generally differs.
- **Index shape/bounds.** `stationary_bootstrap_indices(n, mean_block=3, n_resamples=5, seed=1)` → 5 lists each of length `n`, every index in `[0, n)`.
- **`mean_block = 1` ≈ i.i.d.** — with `mean_block = 1`, `p = 1` so every position is a fresh random draw (no advance); still valid indices/length (a behavioral sanity check, not a distributional assertion).
- **Constant series (exact).** `bootstrap_ci([5.0] * 20, statistics.mean, mean_block=4, seed=7)` → `point == lower == upper == 5.0` (every resample mean is 5).
- **Varied series.** For a non-constant series, `lower <= point <= upper` is not asserted, but `lower <= upper`, all three finite, and `upper > lower` (positive width).
- **Never-NaN / guards** — each raises `ValidationError`: empty series; a non-finite series value (`float("nan")`); `mean_block < 1`; `mean_block = inf`; `n_resamples < 1`; `alpha <= 0`; `alpha >= 1`; a `statistic` returning `float("nan")`; a `statistic` that raises (`lambda xs: xs[10**9]`).

## Deferred / parked

Sharpe/maxDD/delta statistics helpers; BCa intervals; automatic `mean_block` selection; the rest of §9 (registry hash-chain, cost model, acceptance suite) as their own iterations.

## Closeout (planned)

On merge: append the `iter-016` `docs/iterations-history.md` entry. No dataset/report artifacts. The `.tmp/decisions.md` `[iter-016]` entry stays in the running log (drained at Phase-2 close-out).
