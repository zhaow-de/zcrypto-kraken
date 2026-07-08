# Explicit-Cost Vectorized Backtester — Design (Phase 3)

**Iteration:** iter-024 · **Phase:** 3 (Benchmarks & the Bar to Beat) · **Status:** design approved (unattended loop)
**Master-plan refs:** §7 (the lean custom core includes "a small explicit-cost vectorized backtester"), §9.6 (cost stress at 1.5×/2×), §12 Phase 3 (the benchmark family). Composes `cli/costs/` (iter-017) + `cli/validation/metrics.py` (iter-018). Opens `cli/backtest/`.

## Problem & context

Phase 3 fixes the benchmark family (B0 buy-and-hold BTC … B4 + short) that DSR/PBO/SPA judge against. B1–B4 (vol-targeting, basket, 200-day gate, short) all need an **engine that turns a strategy's target positions into a net-return series after explicit costs**, then scores it. This iteration builds that engine — minimal v1, on synthetic positions/returns (real benchmark runs are later iterations).

**The correctness-critical decision is the timing / look-ahead convention.** A backtester that lets `position[t]` be informed by `return[t]` silently manufactures look-ahead — the exact class of error the whole validation harness exists to catch. The convention here (below) is fixed and documented so the caller's obligation is explicit.

## Goals

- **`cli/backtest/`** — `run_backtest(asset_returns, positions, *, fee_rate, periods_per_year)` → `{net_returns, total_return, sharpe, max_drawdown, annualized_return, n_periods}`, reusing `cli.validation.metrics`. Stdlib-only; never-NaN (degenerate/blown-up backtests raise, never silently NaN). TDD.

## Non-goals

- **No margin carry / spread / borrow in v1** — `fee_rate` (per unit turnover) only; margin (`cli.costs.margin_carry`) + spread (T0003-gated) fold in as parameters in a follow-up. No multi-asset/portfolio (single return series; the basket benchmark composes per-asset backtests later). No position-*generation* (the caller supplies positions; strategies are later iterations). No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

New package `cli/backtest/` (module + `errors.py` + `__init__.py`), mirroring `cli/validation/` style.

**`cli/backtest/errors.py`** — `class BacktestError(Exception)`.

**`cli/backtest/engine.py`:**

- `run_backtest(asset_returns: list[float], positions: list[float], *, fee_rate: float = 0.0, periods_per_year: int) -> dict`

  **Timing convention (fixed):** `positions[t]` is the position **held during period `t`** and earns period `t`'s return. The caller MUST set `positions[t]` using only information available **before** period `t` (i.e. ≤ `t−1`) — the engine does not (cannot) enforce this; look-ahead is the strategy's responsibility, and the CPCV/validation harness is what catches a leaky strategy. There is no index shift: `positions` and `asset_returns` are aligned, same length.

  1. Validate: `asset_returns` and `positions` are the same length `n ≥ 2`; every value finite; `fee_rate` a finite number `≥ 0`; `periods_per_year` a positive `int`. Else `BacktestError`.
  2. `turnover[t] = |positions[t] − positions[t−1]|`, with `positions[−1] = 0` (the initial entry from flat is charged).
  3. `net[t] = positions[t] * asset_returns[t] − turnover[t] * fee_rate`.
  4. Metrics via the harness (reuse, do not reimplement) — wrapped so a degenerate result surfaces as `BacktestError`: `try: sharpe(net, periods_per_year=periods_per_year); max_drawdown(net); annualized_return(net, periods_per_year=periods_per_year) except ValidationError as e: raise BacktestError(f"degenerate backtest: {e}") from e`. (This is where a **flat strategy** — zero-variance `net`, Sharpe undefined — and a **blow-up** — some `1 + net[t] ≤ 0`, maxDD/return undefined — are turned into a clear error rather than a NaN.)
  5. `total_return = prod(1 + net[t]) − 1` (reached only after the metrics validated the series).
  6. Return `{"net_returns": net, "total_return": total_return, "sharpe": ..., "max_drawdown": ..., "annualized_return": ..., "n_periods": n}`.

**`cli/backtest/__init__.py`** — export `BacktestError`, `run_backtest`.

## Testing

`tests/test_backtest_engine.py`:

- **Buy-and-hold (timing + entry cost).** `asset_returns = [0.10, -0.05, 0.20]`, `positions = [1.0, 1.0, 1.0]`, `fee_rate = 0.01`, `ppy = 252`: `turnover = [1.0, 0.0, 0.0]`, so `net = [0.10 − 0.01, −0.05, 0.20] = [0.09, −0.05, 0.20]`; `total_return == (1.09·0.95·1.20) − 1`. Assert `net_returns` and `total_return` exactly; `n_periods == 3`.
- **Zero fee, constant position ⇒ net = position·returns.** `positions = [0.5]*4`, `fee_rate = 0`: `net[t] == 0.5·asset_returns[t]`.
- **Turnover cost on a position change (incl. sign flip).** `positions = [1.0, 1.0, −1.0]`, `asset_returns = [r0, r1, r2]`, `fee_rate = 0.01`: `turnover = [1.0, 0.0, 2.0]`; `net[2] == −1.0·r2 − 2.0·0.01`.
- **Metrics match the harness.** For a hand-built `net`, `run_backtest(...)`'s `sharpe`/`max_drawdown`/`annualized_return` equal `cli.validation.{sharpe,max_drawdown,annualized_return}(net, periods_per_year=ppy)` called directly (so the engine genuinely reuses them).
- **Never-NaN / degenerate raises `BacktestError`:** a flat strategy (`positions = [0.0]*5` ⇒ zero-variance net ⇒ Sharpe undefined); a blow-up (`positions=[3.0,3.0]`, `asset_returns=[0.0, -0.4]` ⇒ `net[1] = -1.2`, `1+net ≤ 0`). Guards: length mismatch; `n < 2`; non-finite return/position; `fee_rate < 0`; non-numeric `fee_rate`; `periods_per_year` = 0 / −1 / 2.5 — each raises `BacktestError`.
- **Sanity — positive-drift buy-and-hold.** On `asset_returns` from `cli.validation.linear_signal(500, beta=…, seed=…)`'s targets (or a simple positive-mean synthetic series), buy-and-hold gives `total_return > 0` and a finite positive `sharpe` — the first end-to-end position→net→metric path.

## Deferred / parked

Margin carry + spread + borrow parameters (fold `cli.costs.margin_carry` in next; spread T0003-gated); multi-asset/portfolio backtest (the basket benchmark); cost-stress multipliers (§9.6 — apply `fee_rate×1.5/×2` at benchmark-evaluation time); position-generation (the benchmark strategies B0–B4, next iterations); a `zcrypto backtest` CLI.

## Closeout (planned)

On merge: append the `iter-024` `docs/iterations-history.md` entry (first Phase-3 iteration). No dataset artifacts. The `.tmp/decisions.md` `[iter-024]` entry stays in the running log (drained at the Phase-3 close-out).
