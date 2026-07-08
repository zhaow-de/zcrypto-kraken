# Regime Gate (200-day SMA long/flat) — Design (Phase 3)

**Iteration:** iter-027 · **Phase:** 3 (Benchmarks & the Bar to Beat) · **Status:** design approved (unattended loop)
**Master-plan refs:** §5 (the 200-day long/flat trend gate = the *prior survivor*), §9 (B3 = B2 + a 200-day long/flat gate), §12 Phase 3. Extends `cli/benchmark/`; feeds the backtester.

## Problem & context

§5 names a **200-day long/flat regime gate** as the prior phase's best-performing rule ("the prior survivor"). It's the mechanism B3 layers on the basket, and it composes with any base strategy (gated buy-and-hold = gate × B0; gated vol-target = gate × B1). This iteration builds the reusable gate as a look-ahead-free long/flat signal.

**The look-ahead-critical piece is the price↔return↔position alignment.** The gate signal for a return period must be decided from prices observed **before** that period's return is realized. The convention (below) is fixed so `signal[k]` uses only `prices[≤ k]` and never `prices[k+1]` — a test asserts `signal[k]` is invariant to `prices[k+1]`.

## Goals

- **`cli/benchmark/strategies.py`** gains `sma_gate(prices, *, window)` — a long/flat (`1.0`/`0.0`) signal aligned with `returns_from_prices(prices)`, look-ahead-free. Stdlib; TDD on synthetic prices; degenerate input raises `BenchmarkError`.

## Non-goals

- No basket / B2 / B3-proper (gate × basket) — the reusable gate is here; B3 composes it with B2 once B2 exists. No EMA / other filters. No annualization. No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

**`cli/benchmark/strategies.py`** (append; reuse `BenchmarkError`):

- `sma_gate(prices: list[float], *, window: int) -> list[float]`
  Returns a long/flat signal of length `len(prices) - 1`, aligned with `returns_from_prices(prices)` (whose element `k` is the return of the move `prices[k] → prices[k+1]`). For each return-period `k` in `range(len(prices) - 1)`:
  - if `k < window - 1`: `signal[k] = 0.0` (warm-up — fewer than `window` prices end at index `k`);
  - else: `sma = mean(prices[k - window + 1 : k + 1])` (the `window` prices ending **at index `k`**, inclusive); `signal[k] = 1.0 if prices[k] > sma else 0.0`.

  **Alignment / no look-ahead:** `signal[k]` uses `prices[k-window+1 .. k]` — all `≤ k`, i.e. up to and including `prices[k]`, the last price observed at the **start** of return-period `k`. It never uses `prices[k+1]` (the price that realizes period `k`'s return). So the gate decision for period `k` is made from information available before that return — look-ahead-free. The backtester then applies `signal[k]` (a position) to `returns[k]`.

  **Composition:** `sma_gate(prices)` is itself the gated-buy-and-hold position vector (long when the gate is on, flat when off). Gated vol-target = the elementwise product `[g * v for g, v in zip(sma_gate(prices, window=w), vol_target(returns_from_prices(prices), ...))]` (both are length `len(prices) - 1`).

  Raises `BenchmarkError` if `prices` is not a list of `≥ 2` finite positive numbers, or `window` is not an `int ≥ 2`.

**`cli/benchmark/__init__.py`** — export `sma_gate`.

## Testing

`tests/test_benchmark_strategies.py` (append):

- **Value (hand-built).** `prices = [10, 11, 12, 9, 8, 13]`, `window = 3` → returns length 5; `signal = [0.0, 0.0, 1.0, 0.0, 0.0]` (k=2: `prices[2]=12 > mean(10,11,12)=11` → 1; k=3: `9 > mean(11,12,9)=10.67` → 0; k=4: `8 > mean(12,9,8)=9.67` → 0). Assert exactly.
- **Length + warm-up.** `len(sma_gate(prices, window=w)) == len(prices) - 1`; the first `window - 1` signals are `0.0`.
- **No look-ahead (the crux).** For a fixed `k ≥ window - 1`, perturb `prices[k+1]` (a copy) and recompute; assert `signal[k]` is **unchanged** (its window `[k-window+1 : k+1]` excludes `k+1`), while `signal[k+1]` (whose window includes `k+1`) **does** change (proving the window is real). Construct with distinct prices so the perturbation actually flips/moves the SMA.
- **All-flat when never above SMA / insufficient length.** A strictly-declining series → mostly `0.0`; `len(prices) <= window` → all `0.0` (all warm-up), no error.
- **Guards** — `prices` shorter than 2, non-finite, non-positive; `window` = 1 / non-int — each raises `BenchmarkError`.
- **Integration.** `run_backtest(returns_from_prices(prices), sma_gate(prices, window=w), fee_rate=0.0, periods_per_year=252)` on a synthetic price series yields a finite result (gated buy-and-hold composes with the backtester); and a gated-vol-target (elementwise product with `vol_target`) also composes.

## Deferred / parked

B2 (inverse-vol basket) + B3-proper (gate × basket) + B4 (short); an EMA variant; a `gated(base_positions, gate_signal)` compose helper (the elementwise product is trivial — YAGNI). The real-data gated-BTC bar-to-beat run folds into the full B0–B4 panel dossier.

## Closeout (planned)

On merge: append the `iter-027` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-027]` entry stays in the running log (drained at the Phase-3 close-out).
