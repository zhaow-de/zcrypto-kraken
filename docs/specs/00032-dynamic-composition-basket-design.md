# T0007 — full-history dynamic-composition inverse-vol basket — Design

**Iteration:** iter-044 · **Phase:** 4 (Alpha sprints — the honest B2 base for A1's finding-1) · **Status:** design approved (unattended loop)
**Refs:** open topic `docs/open-topics/archive/T0007-dynamic-composition-basket.md`, master-plan §9 (B2), `docs/research/05.phase4-orientation.md` finding 1, `docs/research/04.phase3-benchmark-b2-basket-report.md` (the fixed-window B2). Reuses `cli/benchmark/strategies.py` (`inverse_vol_basket`, `vol_target`, `returns_from_prices`) + `cli/backtest/engine.py` (`run_backtest`).

## Problem & context

The B2 benchmark (iter-030) is a **fixed 10-asset basket over the common window** 2021-12-21 → 2026-03-31 (AVAX-limited, ~4.3 yr, one bull→bear→recovery). Over that window it *underperformed* single-asset BTC (0.68×, Sharpe 0.194) — but the window is BTC-unfavorable and the Phase-3 bootstrap CIs showed it lacks the power to say whether the basket's weakness is **structural** (alt-vs-BTC beta) or a **window artifact**. A1's premise is a "vol-targeted majors basket," and finding-1 (does that base beat a BTC-anchored book?) can only be answered honestly over the **full 2013→2026 universe** — which needs a **dynamic-composition** basket that grows 2 → 10 assets as they list. This iteration builds it and runs the definitive finding-1 comparison.

## Goals

1. **`dynamic_inverse_vol_basket(prices_by_asset, *, lookback)`** in `cli/benchmark/strategies.py` — the look-ahead-free dynamic basket net-return series. Input: a dict of per-asset price series **pre-aligned to one union calendar** of length `L`, where a day is `None` when the asset is **absent** (pre-listing or a data gap). Definition, matching `inverse_vol_basket`'s look-ahead convention:
   - Per asset, a return exists for period `t` (0-indexed, `ret_i[t] = prices_i[t+1]/prices_i[t] - 1`, length `L-1`) **only when both `prices_i[t]` and `prices_i[t+1]` are present and positive**; otherwise `ret_i[t] = None`.
   - At period `t`, asset `i` **qualifies** iff: (a) `ret_i[t]` is present (tradeable this period), **and** (b) the trailing window `ret_i[t-lookback:t]` (strictly before `t`) is **fully populated** — all `lookback` entries present (the asset has a complete, gap-free `lookback` of returns), **and** (c) `stdev` of that window `> 0`.
   - Weight qualifying assets by `1/stdev(trailing window)`, **renormalize over that period's qualifying set**, and `portfolio[t] = Σ wᵢ·ret_i[t]`. No qualifying asset (all-absent / warm-up / zero-vol) → `0.0`.
   - This is strictly causal: a period's weights use only returns **before** `t`, so they are invariant to that period's realized returns. Validation mirrors `inverse_vol_basket` (`BenchmarkError` on bad `lookback`/empty dict/unequal lengths; `None` is the only allowed non-finite).

2. **Full-history run + report** (`docs/research/04.phase3-benchmark-b2-dynamic-report.md`, driven by a scratchpad script — mirroring the fixed-window B2 report): build the union-calendar `prices_by_asset` from `data/ohlc-full/<BASE>/EUR/1440.parquet` (10 majors; the union = the sorted union of all `ts`, `None` where an asset has no bar), run `dynamic_inverse_vol_basket` (raw + vol-targeted to 10%/yr) and compare, over the **full 2013→2026 horizon**, against single-asset BTC B0 (buy-hold) and B1 (vol-target) — plus, for apples-to-apples, the same over the fixed AVAX-limited window. Record composition growth (n-assets over time) and the **finding-1 verdict**: does the full-history dynamic basket (raw and/or vol-targeted) beat single-asset BTC risk-adjusted?

## Non-goals

Not an alpha trial — this is a **B2 benchmark variant** (report + decision-log verdict, **no** trial-registry entry; the registry is for A/B/C alpha families). No dynamic B3 (gate × basket) / B4 (basket + short) this pass — noted as a follow-up once the basket base is characterized. No new metrics/backtester (reuse the stack). No cost model beyond what the B2 report used (benchmark idealization, zero-fee, consistent with `docs/research/04.phase3-benchmark-b2-basket-report.md`; A1's kill bar applies costs).

## Testing / done (distrust the instrument)

TDD on **synthetic union-calendar fixtures** (`tests/test_benchmark_dynamic_basket.py`):

- **Known-answer**: a small hand-built 2-asset case (one entering mid-window as `None`→present) → hand-computed weights + basket returns.
- **Composition edge cases**: an asset entering mid-window contributes `0` weight until it has a full `lookback` of returns, then joins; a **data gap** (`None` mid-series) disqualifies the asset until `lookback` clean returns re-accrue; the 2→N growth boundary renormalizes correctly (weights sum to 1 over the qualifying set each period); an all-absent / all-warm-up period → `0.0`.
- **Look-ahead invariance (the centerpiece)**: mutating `prices_i[t+1:]` (a period's realized return and everything after) leaves `portfolio[:t]` bit-identical — a period's weights can't see its own or future returns. Verify it genuinely fails on a deliberately-broken (peeking) implementation.
- **Reduces to the fixed basket**: with no `None`s and equal-length series, `dynamic_inverse_vol_basket` produces the **same** series as `inverse_vol_basket` (a cross-check that the dynamic layer is a strict generalization).
- `uv run pytest` green; `uv run pre-commit run -a` clean. The full-history run is plausibility-gated (finite metrics, non-degenerate, composition grows 2→10 as expected) before the verdict is recorded.

## Closeout (planned)

Finding-1 verdict recorded in `.tmp/decisions.md` (`[iter-044]`) + the report. iter-044 iterations-history entry. **Flip T0007 → `resolved`** (index sync). Suggest the next step (A1 execution, iter-045, consuming this basket as its `equal_risk_basket` base). Engineering + benchmark iteration — the benchmark verdict is logged (subject-matter), no alpha-registry entry.
