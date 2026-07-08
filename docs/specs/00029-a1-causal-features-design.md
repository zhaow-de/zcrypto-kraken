# A1 causal feature primitives (`cli/features/`) — Design

**Iteration:** iter-040 · **Phase:** 4 (Alpha Research Sprints — the A1/A2 feature substrate) · **Status:** design approved (unattended loop)
**Refs:** `docs/research/05.phase4-orientation.md` ("Leak-free feature construction … multi-horizon momentum, breakout/channel distance, realized-vol state"; §6 causal rules), master-plan §5/§6. Reuses the reviewed causal conventions of `cli/benchmark/strategies.py` (`sma_gate`, `vol_target`).

## Problem & context

Phase 4's alpha families (A1 long/flat/short trend book, A2 TSMOM ensemble, and the Bucket-B intraday families) are all built from **strictly causal** per-asset features. None exist yet — `cli/benchmark/strategies.py` has only the Phase-3 benchmark primitives (`vol_target`, `sma_gate`, `returns_from_prices`, `inverse_vol_basket`). The single worst failure mode for an alpha sprint is a **look-ahead leak** in feature construction that mints a false edge (the master-plan's "distrust the instrument" note). So the first Phase-4 iteration builds the leak-prone part first — a small, TDD'd, leak-verified feature library — rather than a whole family whose verdict a hidden leak could invalidate.

## Goals

New `cli/features/` package (pure stdlib `math`/`statistics`, `list[float]` in/out, mirroring `cli/benchmark/strategies.py`), with a `FeatureError` for validation. Three causal features, **all sharing `sma_gate`'s alignment** so they are drop-in signals for the existing backtester:

**Alignment convention (identical to `sma_gate`).** A feature over `prices` (length `L`) returns a list of length `L-1`, aligned to `returns_from_prices(prices)`: element `k` corresponds to the move `prices[k] → prices[k+1]`, and `feature[k]` is computed from **only `prices[≤k]`** (through `prices[k]`, the price at the *start* of return-period `k`) — never `prices[k+1]`. Warm-up positions (insufficient history) are `0.0`.

1. **`momentum(prices, *, lookback)`** — `m[k] = prices[k] / prices[k-lookback] - 1` for `k >= lookback`; warm-up (`k < lookback`) → `0.0`. Multi-horizon momentum is obtained by calling it with different `lookback`s (4h→90d in bars).
2. **`channel_position(prices, *, window)`** — Donchian breakout/channel distance: with `hi = max(prices[k-window+1 : k+1])`, `lo = min(...)`, `channel_position[k] = 2*(prices[k]-lo)/(hi-lo) - 1` ∈ `[-1, +1]` (+1 at the channel high = upside breakout, −1 at the low). Degenerate flat window (`hi == lo`) → `0.0`; warm-up (`k < window-1`) → `0.0`.
3. **`realized_vol(prices, *, lookback)`** — the per-period realized-vol **state**: `rv[k] = stdev(returns[k-lookback+1 : k+1])` where `returns = returns_from_prices(prices)` and the window is the `lookback` returns **ending at the move into `k`** (i.e. uses `prices[k-lookback .. k]`, all `≤ k`). Warm-up (fewer than `lookback` returns available, `k < lookback`) → `0.0`; a zero-vol window → `0.0`. (Distinct from `vol_target`, which consumes returns for *sizing*; this exposes vol as a feature/state and keeps the whole library price-in for one consistent alignment.)

Validation (every function): `prices` a `list` of `>= 2` finite positive floats (else `FeatureError`); `lookback`/`window` an `int >= 2` (reject `bool`), else `FeatureError`. Never emits `NaN`/`inf`.

## Non-goals

No trend-agreement / drawdown-state features this pass (add when A1's book needs them — the library is extensible). No DataFrame/polars API (list-based, matching the benchmark primitives; a vectorized layer is a later optimization). No feature *selection*, no A1 book assembly, no backtest/verdict here — this is the substrate only. No CLI subcommand (features are a library consumed by later Phase-4 code).

## Testing / done

TDD on synthetic fixtures (`tests/test_features_*.py`), per feature:

- **Known-answer:** hand-built prices → hand-computed feature values (momentum ratio; channel position = +1 at a fresh high, −1 at a fresh low, 0 at mid; realized_vol = `statistics.stdev` of the known return window).
- **Warm-up:** the leading warm-up region is exactly `0.0` and the output length is `len(prices)-1`.
- **Look-ahead / leak test (the centerpiece):** for each feature, mutating `prices[k+1:]` must leave `feature[0..k]` bit-identical — a planted future change cannot reach a past feature value. This is the regression guard against the leak class that invalidates alpha verdicts.
- **Degenerate/guards:** flat window → `channel_position` 0.0; zero-vol window → `realized_vol` 0.0; non-positive/non-finite price, `bool` or `<2` lookback → `FeatureError`.

`uv run pytest` green; `uv run pre-commit run -a` clean.

## Closeout (planned)

iter-040 iterations-history entry. Engineering/tooling iteration (feature substrate) — the *scoping* decision is logged in `.tmp/decisions.md` (`[iter-040]`), but no A/B verdict (no strategy is measured here). The features become the inputs to the A1 spec of the next iteration.
