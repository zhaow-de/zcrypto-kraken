# Benchmark Strategies B0 + B1 — Design (Phase 3)

**Iteration:** iter-025 · **Phase:** 3 (Benchmarks & the Bar to Beat) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 ("Benchmark family: B0 buy-and-hold BTC; B1 vol-targeted BTC (10–12%); …"), §12 Phase 3. Feeds the iter-024 backtester (`cli.backtest.run_backtest`). Opens `cli/benchmark/`.

## Problem & context

Phase 3 fixes the benchmark family — the bar every alpha idea must beat — as position generators fed to the backtester. This iteration builds the two **BTC** benchmarks: **B0 buy-and-hold** (constant long) and **B1 vol-targeted BTC** (scale exposure so realized vol ≈ a target). The generator pattern (a function `returns → positions`, look-ahead-free) is established here; the basket (B2), the 200-day gate (B3), the short extension (B4), and the real-data bar-to-beat dossier follow as their own iterations.

**The look-ahead-critical piece is B1's realized-vol window.** `position_t` must be computed from returns **strictly before** period `t` (the backtester then applies `position_t` to `return_t`). Using `return_t` in `position_t` would manufacture look-ahead — the exact defect the harness exists to catch. The window is fixed to `returns[t-lookback:t]` (excludes `t`), and a test asserts `position_t` is invariant to `returns[t]`.

## Goals

- **`cli/benchmark/`** — `buy_and_hold` (B0) + `vol_target` (B1) position generators, stdlib, deterministic, look-ahead-free. TDD on synthetic returns; degenerate inputs raise `BenchmarkError`.

## Non-goals

- No B2 (basket), B3 (gate), B4 (short); no real-data run / bar-to-beat dossier (deferred until the family is complete, for a consistent panel). No annualization inside the generators (the caller passes a per-period `target_vol`). No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

New package `cli/benchmark/` (module + `errors.py` + `__init__.py`), mirroring `cli/validation/` style.

**`cli/benchmark/errors.py`** — `class BenchmarkError(Exception)`.

**`cli/benchmark/strategies.py`:**

- `buy_and_hold(n_periods: int) -> list[float]`
  Returns `[1.0] * n_periods` (constant full long). Raises `BenchmarkError` if `n_periods` is not an `int ≥ 1`.

- `vol_target(returns: list[float], *, target_vol: float, lookback: int, max_leverage: float = 1.0) -> list[float]`
  Position that scales exposure toward a per-period `target_vol`, capped at `max_leverage`. For each `t` in `range(len(returns))`:
  - if `t < lookback`: `position_t = 0.0` (insufficient history);
  - else: `rv = stdev(returns[t-lookback:t])` (**sample** stdev over the `lookback` returns **strictly before `t`** — no look-ahead); `position_t = min(target_vol / rv, max_leverage)` if `rv > 0` else `0.0`.
  Returns `positions` (length `len(returns)`), where `position_t` is held during period `t` (the backtester applies it to `return_t`). Raises `BenchmarkError` if `returns` is empty or has a non-finite value, `target_vol` is not a finite number `> 0`, `lookback` is not an `int ≥ 2`, or `max_leverage` is not a finite number `> 0`.

**`cli/benchmark/__init__.py`** — export `BenchmarkError`, `buy_and_hold`, `vol_target`.

## Testing

`tests/test_benchmark_strategies.py`:

- **`buy_and_hold`** — `buy_and_hold(3) == [1.0, 1.0, 1.0]`; guards (`n_periods` = 0, non-int) raise.
- **`vol_target` warm-up** — the first `lookback` positions are `0.0`.
- **`vol_target` value** — on a hand-built series where `returns[0:lookback]` has a known stdev `s`, `position[lookback] == min(target_vol / s, max_leverage)` (computed via `statistics.stdev`).
- **`vol_target` no look-ahead (the crux)** — build `positions = vol_target(returns, …)`; then for a fixed `t ≥ lookback`, change `returns[t]` (a copy) and recompute; assert `position_t` is **unchanged** (it depends only on `returns[t-lookback:t]`), while some `position_{t'}` with `t' > t` (whose window includes `t`) **does** change (proving the window is real, not empty).
- **`vol_target` cap** — a tiny-vol window (`target_vol / rv > max_leverage`) → `position == max_leverage`.
- **`vol_target` zero-vol window** — a constant-return window (`rv == 0`) → `position == 0.0` (no NaN).
- **Guards** — empty `returns`; non-finite return; `target_vol` = 0 / negative / non-numeric; `lookback` = 1 / non-int; `max_leverage` = 0 / negative — each raises `BenchmarkError`.
- **Integration sanity** — `vol_target` positions fed to `cli.backtest.run_backtest` on a synthetic return series yield a finite result dict (the generator composes with the backtester).

## Deferred / parked

B2 (inverse-vol majors basket), B3 (B2 + 200-day long/flat gate), B4 (B3 + short); the real-data bar-to-beat dossier (all of B0–B4 through the backtester on the Phase-1 dataset, with DSR/PBO/SPA comparison — the deployment rule of §9); annualization helpers; a `zcrypto benchmark` CLI.

## Closeout (planned)

On merge: append the `iter-025` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-025]` entry stays in the running log (drained at the Phase-3 close-out).
