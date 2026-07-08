# Performance Statistics — Design (Phase 2)

**Iteration:** iter-018 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 (the number a strategy is judged on: Sharpe / maxDD / annualized return), §9.5 (bootstrap CIs *on Sharpe/maxDD*), §12 Phase 2. Extends `cli/validation/`.

## Problem & context

The harness can split (CPCV), deflate (DSR), detect overfit (PBO), band uncertainty (bootstrap), and cost trades (cost model) — but has **no performance statistics**, so it cannot yet compute the headline number a strategy is scored on, and the bootstrap/DSR were deliberately built to *consume* a `statistic` callable that doesn't exist yet. This iteration adds the core statistics over a per-period **returns** series: `sharpe`, `volatility`, `annualized_return`, `max_drawdown`. They are the `statistic` callables the acceptance suite's planted-signal recovery (a later iteration) will pass to CPCV + bootstrap.

Same integrity discipline (§7): **never NaN**. The two natural NaN traps are (a) zero-variance returns → `mean/std = x/0` and (b) a period return `≤ -100%` (`1 + r ≤ 0`) breaking geometric compounding — both raise `ValidationError`.

## Goals

- **`cli/validation/metrics.py`** — four pure functions over `list[float]` returns, stdlib (`statistics`, `math`). Per-period by default; optional annualization by `sqrt(periods_per_year)` (Sharpe/vol) or geometric scaling (return). Property-tested including the never-NaN traps.

## Non-goals

- No `sortino` / Calmar / Omega / tail metrics (YAGNI — add when a strategy needs them).
- No returns *estimation* from prices, no benchmark-relative (delta) metrics (a later helper), no annualization-factor auto-detection.
- No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

Add to `cli/validation/` (reuse `errors.ValidationError`).

**`cli/validation/metrics.py`:**

- `sharpe(returns: list[float], *, risk_free: float = 0.0, periods_per_year: int | None = None) -> float`
  `(mean(returns) - risk_free) / stdev(returns)`, using **sample** stdev (`statistics.stdev`, n−1). If `periods_per_year` is given, multiply by `sqrt(periods_per_year)`. Raises `ValidationError` if `len(returns) < 2`, any return non-finite, `risk_free` non-finite, `periods_per_year` given but not a positive `int`, or **`stdev == 0`** (zero-variance ⇒ undefined, not NaN).

- `volatility(returns: list[float], *, periods_per_year: int | None = None) -> float`
  `stdev(returns)`, optionally `× sqrt(periods_per_year)`. Raises `ValidationError` if `len(returns) < 2`, any return non-finite, or `periods_per_year` given but not a positive `int`.

- `annualized_return(returns: list[float], *, periods_per_year: int) -> float`
  Geometric: `prod(1 + r) ** (periods_per_year / len(returns)) - 1`. Raises `ValidationError` if `returns` empty, any return non-finite, `periods_per_year` not a positive `int`, or any `1 + r <= 0` (a `≤ -100%` period return ⇒ compounding undefined).

- `max_drawdown(returns: list[float]) -> float`
  Build the equity curve `e_t = prod_{i<=t}(1 + r_i)` and running peak `p_t`; drawdown `d_t = e_t / p_t - 1 ≤ 0`; return `max(-d_t) ≥ 0` (the worst peak-to-trough decline as a **non-negative fraction**; `0.0` for a monotonically non-decreasing curve). Raises `ValidationError` if `returns` empty, any return non-finite, or any `1 + r <= 0`.

**`cli/validation/__init__.py`** — additionally export `sharpe`, `volatility`, `annualized_return`, `max_drawdown`.

## Testing

`tests/test_validation_metrics.py` (pytest):

- **`sharpe`** — zero-mean `[0.02, -0.02, 0.02, -0.02]` → `0.0`; positive `[0.01, 0.03]` → `0.02 / stdev ≈ 1.4142` (±1e-4); annualized (`periods_per_year=252`) = per-period `× sqrt(252)`; `risk_free` shifts it down. Guards: `len < 2`, non-finite return, non-finite `risk_free`, `periods_per_year` = 0 / −1 / 2.5, and **zero-variance** `[0.01, 0.01, 0.01]` each raise `ValidationError`.
- **`volatility`** — `[0.01, 0.03]` → `stdev ≈ 0.014142`; annualized `× sqrt(252)`. Guards: `len < 2`, non-finite, bad `periods_per_year`.
- **`annualized_return`** — `[0.1, 0.1]` with `periods_per_year=2` → `1.21 - 1 = 0.21`; `[0.0]*252` with `periods_per_year=252` → `0.0`. Guards: empty, non-finite, bad `periods_per_year`, and a `≤ -100%` return (`[-1.5, 0.1]`) raise.
- **`max_drawdown`** — `[0.1, -0.5, 0.2]` → equity `1.1, 0.55, 0.66`, peak `1.1` → maxDD `0.5`; monotone `[0.1, 0.1, 0.1]` → `0.0`. Guards: empty, non-finite, `≤ -100%` return raise.
- **Never-NaN property** — none of the four returns NaN/inf for valid inputs; every degenerate input (zero-variance, `1 + r ≤ 0`) raises rather than returning NaN.

## Deferred / parked

`sortino`/Calmar/tail metrics; returns-from-prices; benchmark-relative (delta) metrics; the rest of §9/§12 Phase-2 (registry hash-chain, multi-seed, SPA, acceptance suite). `metrics.py`'s `risk_free` float param falls under the T0006 non-numeric-type-guard sweep.

## Closeout (planned)

On merge: append the `iter-018` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-018]` entry stays in the running log (drained at Phase-2 close-out).
