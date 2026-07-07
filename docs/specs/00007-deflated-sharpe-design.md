# Deflated & Probabilistic Sharpe Ratio — Design (Phase 2)

**Iteration:** iter-014 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9.4 (multiple-testing control: DSR against the family's full trial count), §12 Phase 2, §7 (encodes the PoC lesson: a broken trial register produced a **NaN deflated-Sharpe** and minted a fake winner). Extends `cli/validation/` (opened iter-013).

## Problem & context

CPCV (iter-013) produces the *distribution* of trial/path Sharpe ratios. §9.4 requires turning an observed best Sharpe — chosen after `N` trials — into a **deflated significance verdict**: is it better than the best you'd expect from `N` draws of noise? The **Deflated Sharpe Ratio (DSR)** (Bailey & López de Prado) is that verdict, built on the **Probabilistic Sharpe Ratio (PSR)**:

- **PSR** — the probability that a strategy's true Sharpe exceeds a benchmark Sharpe, given the observed Sharpe over `T` observations and the returns' skew/kurtosis (non-normal SE correction).
- **DSR** — PSR with the benchmark set to `SR0`, the **expected maximum Sharpe under the null** across `N` independent trials with trial-Sharpe variance `V`. More trials ⇒ higher `SR0` ⇒ harder to clear.

The **defining requirement (§7 PoC lesson):** this code must **never silently return NaN**. The PoC minted a fake winner because a broken register fed a NaN DSR through as if valid. Here, any degenerate/non-finite input or a non-positive SE denominator **raises `ValidationError`** — the same integrity the trial registry (`cli/registry/`) asserts on the read path.

## Goals

- **`cli/validation/dsr.py`** — three pure functions (PSR, expected-max-Sharpe, DSR) over scalars, stdlib-only (`statistics.NormalDist` for Φ and Φ⁻¹, `math`). Property-tested, including the NaN-refusal.

## Non-goals

- No estimation of `sr` / `skew` / `kurtosis` / `var_trials` from a return series — callers pass the moments (a return-series → moments helper is a later iteration; keeps this pure + testable). No annualization (Sharpe is per-observation).
- No PBO, bootstrap, SPA, multi-seed, registry hash-chain, cost model (each its own iteration).
- No `zcrypto` CLI subcommand; no README change (library package, per iter-013).
- No new deps.

## Design

Add to the `cli/validation/` package (reuse `cli/validation/errors.ValidationError`).

**`cli/validation/dsr.py`:**

- `expected_max_sharpe(n_trials: int, var_trials: float) -> float`
  Expected maximum of `n_trials` independent trial Sharpes drawn from `N(0, var_trials)` (Bailey & López de Prado approximation):
  `SR0 = sqrt(V) · [ (1 - γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ]`, with `γ` = Euler–Mascheroni ≈ `0.5772156649015329`, `e = math.e`, `Φ⁻¹ = NormalDist().inv_cdf`.
  Special case `n_trials == 1 → 0.0` (a single draw from a zero-mean null has expected max 0; the formula's `Φ⁻¹(0)` is undefined there). Raises `ValidationError` if `n_trials < 1`, `var_trials < 0`, or `var_trials` is not finite.

- `probabilistic_sharpe_ratio(sr: float, n_obs: int, *, benchmark_sr: float = 0.0, skew: float = 0.0, kurtosis: float = 3.0) -> float`
  `PSR = Φ( (sr - benchmark_sr)·sqrt(n_obs - 1) / sqrt(denom) )`, where `denom = 1 - skew·sr + (kurtosis - 1)/4 · sr²` (the Sharpe estimator's variance factor; `kurtosis` is the full fourth standardized moment, normal = 3, so normal returns give `denom = 1 + sr²/2`). Returns a probability in `[0, 1]`.
  Raises `ValidationError` if `n_obs < 2`; if any of `sr, benchmark_sr, skew, kurtosis` is not finite; or if `denom <= 0` (degenerate — would yield NaN/complex). Never returns NaN.

- `deflated_sharpe_ratio(sr: float, n_obs: int, n_trials: int, var_trials: float, *, skew: float = 0.0, kurtosis: float = 3.0) -> float`
  `= probabilistic_sharpe_ratio(sr, n_obs, benchmark_sr=expected_max_sharpe(n_trials, var_trials), skew=skew, kurtosis=kurtosis)`. Inherits all guards. A probability in `[0, 1]`, always finite for valid inputs.

**`cli/validation/__init__.py`** — additionally export `expected_max_sharpe`, `probabilistic_sharpe_ratio`, `deflated_sharpe_ratio`.

## Testing

`tests/test_validation_dsr.py` (pytest; `math.isnan`/`isfinite`, `statistics.NormalDist` for cross-checks):

- **`expected_max_sharpe`** — `(1, V) → 0.0`; `(N, 0.0) → 0.0` for `N ∈ {2, 10}`; strictly increasing in `N` for fixed `V > 0` (`N = 2 < 5 < 10 < 50`); scales as `sqrt(V)` (`emp(N,4) ≈ 2·emp(N,1)`); known value `emp(10, 1.0) ≈ 1.574` (±0.01). Guards: `n_trials = 0`, `var_trials = -1`, `var_trials = inf` raise.
- **`probabilistic_sharpe_ratio`** — `sr == benchmark_sr → 0.5`; strictly increasing in `sr`; bounded `[0, 1]`; large `sr` (e.g. `psr(2.0, 1000) → > 0.999`); a hand-computed value cross-checked against `NormalDist().cdf`. Guards: `n_obs = 1`; `sr = float("nan")`; a `denom <= 0` case (`sr = 1.0, skew = 5.0` → `denom = 1 - 5 + 0.5 = -3.5`) — each raises `ValidationError` (assert **no NaN** is returned).
- **`deflated_sharpe_ratio`** — equals `probabilistic_sharpe_ratio` with `benchmark_sr = expected_max_sharpe(N, V)` (exact); **deflation reduces significance**: `dsr(2.0, 250, 100, 1.0) < probabilistic_sharpe_ratio(2.0, 250)` (more trials ⇒ lower DSR); result is finite and in `[0, 1]`. NaN-refusal: `dsr(nan, …)` and `var_trials = nan` raise `ValidationError`.
- **Integrity property (the §7 lesson):** for a grid of valid inputs, `deflated_sharpe_ratio` returns a finite float in `[0, 1]` — never NaN/inf — and every degenerate input raises rather than returning NaN.

## Deferred / parked

Return-series → (sr, skew, kurtosis, T) moment estimator; PSR-based minimum-track-record length; the rest of §9 (PBO, bootstrap, SPA, multi-seed, registry hash-chain, cost model, acceptance suite) as their own iterations.

## Closeout (planned)

On merge: append the `iter-014` `docs/iterations-history.md` entry. No dataset/report artifacts (pure library). The `.tmp/decisions.md` `[iter-014]` entry stays in the running log (drained at Phase-2 close-out).
