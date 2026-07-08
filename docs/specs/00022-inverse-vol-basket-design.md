# Inverse-Vol Majors Basket (B2 generator) — Design (Phase 3)

**Iteration:** iter-030 · **Phase:** 3 (Benchmarks & the Bar to Beat) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9 (B2 = inverse-vol majors basket), §10 (risk model), §12 Phase 3. Extends `cli/benchmark/`; the portfolio return series it produces feeds `cli.backtest.run_backtest`.

## Problem & context

The benchmark family (§9): B0 buy-and-hold BTC, B1 vol-targeted BTC, **B2 inverse-vol majors basket**, B3 = B2 + 200d gate, B4 = B3 + short. B2 is the first **multi-asset** benchmark — an equal-risk-contribution basket that inverse-vol-weights the majors so each contributes similar risk, the classic diversified crypto benchmark. This iteration builds the **generator** (a pure function producing the basket's daily portfolio return series); the real-data bar-to-beat (B2 vs the BTC benchmarks over a matched window) follows as its own iteration, mirroring iter-025 (B0/B1 generators) → iter-026 (report).

**Composition decision (`.tmp/decisions.md` [iter-030], Decision 2):** a **fixed 10-asset basket over the common window** (all 10 EUR majors present every day). The generator is pure and takes **pre-aligned equal-length price series** — the caller (the real-data run) does the loading + intersection alignment; the richer dynamic-composition variant is parked as open topic **T0007**.

**The look-ahead-critical piece is the vol→weight→return alignment.** Each day's inverse-vol weights must be computed from returns realized **strictly before** that day's return. The convention below fixes `weight_i[t]` to use `returns_i[t-lookback:t]` (excludes `t`), then applies it to `returns_i[t]` — a test asserts `weight_i[t]` (hence the portfolio return contribution's weighting) is invariant to `returns_i[t]`.

## Goals

- **`cli/benchmark/strategies.py`** gains `inverse_vol_basket(prices_by_asset, *, lookback)` → the basket's daily **net portfolio return series** (length `L-1`, aligned with `returns_from_prices`), inverse-vol weighted, look-ahead-free. Stdlib; TDD on synthetic prices; degenerate input raises `BenchmarkError`.

## Non-goals

- No data loading / calendar alignment (the caller supplies pre-aligned equal-length series). No dynamic composition (T0007). No rebalancing-cost / basket-turnover model (the intra-basket weight churn is not a single-asset position turnover, so `run_backtest`'s `fee_rate` can't see it — cost stress for B2 is a later iteration, like the B0/B1 → iter-029 sequence). No B3/B4. No `zcrypto` CLI subcommand; no README change. No new deps.

## Design

**`cli/benchmark/strategies.py`** (append; reuse `BenchmarkError`):

- `inverse_vol_basket(prices_by_asset: dict[str, list[float]], *, lookback: int) -> list[float]`

  Returns the basket's net portfolio return series of length `L-1`, where `L` is the common price-series length. For each asset, per-asset returns are `returns_from_prices(prices)` (element `k` = the return of `prices[k] → prices[k+1]`). For each return-period `t` in `range(L-1)`:
  - if `t < lookback`: `portfolio_return[t] = 0.0` (warm-up — no asset has `lookback` prior returns);
  - else: for each asset `i`, compute `vol_i = stdev(returns_i[t-lookback:t])` (sample stdev, the `lookback` returns ending **before** `t`; look-ahead-free). The **qualifying set** `Q` = assets with `vol_i > 0` (a zero-vol asset would take infinite inverse-vol weight — exclude it that day; insufficient-history is already handled by the global warm-up). Then:
    - if `Q` is empty: `portfolio_return[t] = 0.0` (nothing weightable that day → flat);
    - else: `inv_i = 1.0 / vol_i` for `i ∈ Q`; `weight_i = inv_i / sum(inv_j for j ∈ Q)` (weights sum to 1 over `Q`); `portfolio_return[t] = sum(weight_i * returns_i[t] for i ∈ Q)`.

  **Alignment / no look-ahead:** `weight_i[t]` uses `returns_i[t-lookback : t]` — all strictly `< t` — and is applied to `returns_i[t]`. The weight decision for period `t` uses only information realized before that period's return. A test asserts `weight_i[t]` (and thus the portfolio return, holding other assets fixed) is invariant to perturbing `returns_i[t]` (equivalently `prices_i[t+1]`).

  **Reuse:** use the **same sample-stdev** approach `vol_target` uses for its realized-vol window (stdlib `statistics.stdev` over the slice), for consistency across the benchmark family.

  Raises `BenchmarkError` if: `prices_by_asset` is empty; any value is not a list of finite positive numbers; the price lists are not **all the same length** `L`; `L < lookback + 2` (need at least `lookback` returns before the first weighted period, i.e. `L-1 > lookback`); or `lookback` is not an `int ≥ 2`.

**`cli/benchmark/__init__.py`** — export `inverse_vol_basket`.

## Testing

`tests/test_benchmark_strategies.py` (append):

- **Value (hand-built, two assets).** Construct two 4-or-5-length price series with hand-computable returns so that at the first weighted period the two assets have known unequal vols; assert the returned `portfolio_return[t]` equals the hand-computed inverse-vol-weighted combination (weights `∝ 1/vol`, normalized). Include at least one period and check the exact float (within a tight tolerance).
- **Equal-vol → equal-weight.** Two assets whose trailing windows have identical stdev → weights `0.5/0.5`; assert `portfolio_return[t] == 0.5*(r_a[t]+r_b[t])` (within tolerance).
- **Length + warm-up.** `len(inverse_vol_basket(...)) == L - 1`; the first `lookback` entries are exactly `0.0`.
- **No look-ahead (the crux).** For a fixed `t ≥ lookback`, perturb one asset's `prices[t+1]` (a copy) — which changes `returns[t]` but not the window `[t-lookback:t]` — and assert `portfolio_return[t]` is **unchanged**; then perturb a price **inside** the window and assert it **does** change (proving the window is real). Build with distinct values so the perturbation actually moves the weights.
- **Zero-vol asset excluded.** One asset with a constant price over the trailing window (vol 0) → it is dropped from `Q` that day and the remaining asset(s) carry weight 1 (renormalized); assert the zero-vol asset contributes nothing. All-assets-zero-vol day → `0.0`.
- **Single asset.** A one-asset dict → the basket return equals that asset's own returns after warm-up (weight 1); still length `L-1`, warm-up `0.0`.
- **Guards** — empty dict; unequal-length series; a series shorter than `lookback + 2`; non-finite / non-positive prices; `lookback` = 1 / non-int — each raises `BenchmarkError`.
- **Integration.** `run_backtest(inverse_vol_basket(prices_by_asset, lookback=w), buy_and_hold(L-1), fee_rate=0.0, periods_per_year=365)` on synthetic series yields a finite result dict (the basket return series composes with the backtester as a pre-aggregated single "asset").

## Deferred / parked

B3-proper (gate × basket) + B4 (short); B2 rebalancing/basket-turnover cost model + its §9.6 cost stress; the real-data B2 bar-to-beat + report (comparing B2 to BTC B0/B1 over the matched common window); the dynamic-composition full-history variant (open topic **T0007**). Data loading + intersection alignment live in the (throwaway) run script of the later report iteration, not in the generator.

## Closeout (planned)

On merge: append the `iter-030` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-030]` entry stays in the running log (drained at the Phase-3 close-out). Open topic **T0007** (dynamic-composition variant) was opened alongside this iteration.
