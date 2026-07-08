# Acceptance Suite — Recovery + Null (Phase 2)

**Iteration:** iter-020 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 ("the harness … must itself pass acceptance tests on synthetic data (a planted signal must be recovered; a null strategy must fail …)"), §12 Phase 2 exit bar ("acceptance suite green in CI"). Extends `cli/validation/`.

## Problem & context

The harness now has all statistical pieces (CPCV, metrics, DSR/PBO, bootstrap) unit-tested in isolation, plus the tamper-evident registry. The §12 exit bar wants them proven **as a system on synthetic data**: recover a planted signal, reject a null. This iteration builds a synthetic scaffold + the two cleanest acceptance checks — the first end-to-end composition of CPCV + metrics + PSR. **"A wrong acceptance test is worse than none,"** so the thresholds below are derived, not guessed.

The **injected-leak** check (embargo demonstrably removes a serial-correlation leak) and the **registry-corruption** check (already delivered as a unit test in iter-019) join the full §12 suite in a follow-up (iter-021) — the leak scenario is subtle enough to warrant its own careful design.

## Goals

- **`cli/validation/synthetic.py`** — a deterministic linear-signal generator + a toy strategy, stdlib (`random`, `math`), reusable by every harness acceptance/regression test.
- **`tests/test_acceptance.py`** — the recovery + null acceptance checks composing `linear_signal` → `sign_strategy_returns` → `sharpe`/`probabilistic_sharpe_ratio` and CPCV OOS path-Sharpes, with thresholds derived below.

## Non-goals

- No injected-leak end-to-end test (iter-021), no registry-corruption re-test (iter-019 covers it), no real strategy/data. No stochastic learner (deterministic toy rule). No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

**`cli/validation/synthetic.py`** (reuse `errors.ValidationError`):

- `linear_signal(n: int, *, beta: float, noise_sd: float, seed: int) -> tuple[list[float], list[float]]`
  Deterministic via `random.Random(seed)`: `x_t = rng.gauss(0, 1)`; `r_t = beta * x_t + noise_sd * rng.gauss(0, 1)`. Returns `(features, targets)`, each length `n`. `beta == 0` ⇒ a **null** (targets independent of features). Raises `ValidationError` if `n < 1`, `seed` not an `int`, or `beta`/`noise_sd` non-finite or `noise_sd < 0`.

- `sign_strategy_returns(features: list[float], targets: list[float]) -> list[float]`
  The toy strategy: go long/short by the feature's sign — `s_t = (1.0 if x_t >= 0 else -1.0) * r_t`. Raises `ValidationError` if the lists differ in length, are empty, or contain a non-finite value.

**Derived behavior (why the thresholds hold):** for `x ~ N(0,1)`, `r = beta·x + noise·ε`, the strategy `s = sign(x)·r` has `E[s] = beta·E|x| = beta·√(2/π)` and `Var(s) = E[r²] − E[s]² = (beta² + noise²) − (beta·√(2/π))²`. At `beta=0.5, noise=1`: `E[s] ≈ 0.399`, `std ≈ 1.044`, so **per-period Sharpe ≈ 0.382** (→ `PSR ≈ 1` over `n=2000`). At `beta=0` (null): `E[s]=0`, per-period Sharpe ≈ 0 with SE `≈ 1/√n`, so a one-sided `PSR > 0.95` fires at the nominal **≈ 5%** rate — the calibrated false-positive rate we assert against.

**`tests/test_acceptance.py`** — the acceptance checks:

- **`test_planted_signal_recovered`** — `x, r = linear_signal(2000, beta=0.5, noise_sd=1.0, seed=42)`; `s = sign_strategy_returns(x, r)`. Assert `sharpe(s) > 0.25` and `probabilistic_sharpe_ratio(sharpe(s), len(s)) > 0.99` (signal recovered). Then via CPCV: over `cpcv_splits(2000, n_groups=10, n_test_groups=2)`, the **median** of `sharpe([s[i] for i in split["test"]])` is `> 0.1` (positive OOS path performance).
- **`test_null_false_positive_rate_is_low`** — for `seed in range(20)`: `x, r = linear_signal(2000, beta=0.0, noise_sd=1.0, seed=seed)`; count seeds where `probabilistic_sharpe_ratio(sharpe(sign_strategy_returns(x, r)), 2000) > 0.95`. Assert the count `<= 4` (expected ≈ 1 at the nominal 5% rate; ≥ 5 has binomial probability ≈ 0.003, so this is robust while proving the harness does **not** over-declare significance on noise).
- **`test_signal_beats_null_median`** — the planted single-seed `PSR` (≈ 1) is `>` the **median** null `PSR` across the 20 null seeds (which sits near 0.5–0.8): a direct signal-vs-noise contrast.

**`cli/validation/synthetic.py` unit tests** (`tests/test_validation_synthetic.py`):
- `linear_signal` is reproducible (same seed → identical output; different seed differs), returns two length-`n` lists, `beta=0` gives near-zero feature/target correlation on a large `n`. Guards: `n<1`, non-int seed, non-finite `beta`/`noise_sd`, `noise_sd<0` raise.
- `sign_strategy_returns([1,-1,0.5],[2,3,4]) == [2,-3,4]` (sign at 0 ⇒ +1). Guards: length mismatch, empty, non-finite raise.

**`cli/validation/__init__.py`** — export `linear_signal`, `sign_strategy_returns`.

## Testing

Both test files above. The acceptance tests are the deliverable (they compose the harness end-to-end); the synthetic unit tests pin the generator. All thresholds are one-sided with wide margins vs the derived values, so they are robust to RNG variation at `n=2000`.

## Deferred / parked

Injected-leak end-to-end (iter-021) + folding the iter-019 registry-corruption test into a single named acceptance suite; a stochastic-learner multi-seed path; `synthetic.py`'s `beta`/`noise_sd` float params under the T0006 type-guard sweep. The rest of §9/§12 Phase-2.

## Closeout (planned)

On merge: append the `iter-020` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-020]` entry stays in the running log (drained at Phase-2 close-out).
