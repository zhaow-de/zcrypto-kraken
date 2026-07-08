# A1 feature substrate, round 2 (`trend_agreement`, `drawdown_state`) — Design

**Iteration:** iter-041 · **Phase:** 4 (Alpha Research Sprints — completing the A1/A2 feature layer) · **Status:** design approved (unattended loop)
**Refs:** `docs/research/05.phase4-orientation.md` (A1 features: "per-asset trend agreement … drawdown state"; findings 2–3), extends iter-040's `cli/features/` (`docs/specs/00029-a1-causal-features-design.md`).

## Problem & context

iter-040 built the first three causal features (`momentum`, `channel_position`, `realized_vol`). The A1 book (orientation memo) also needs two more per-asset features it names: **trend agreement** (the ensemble-regime input — finding 3 wants the ensemble to beat the single BTC gate, and per-asset multi-horizon agreement is its signal) and **drawdown state** (a risk state for the book). Building them now completes A1's per-asset feature layer, on the same strictly-causal, leak-tested footing, so the next iteration can spec the A1 book with all its inputs in hand.

## Goals

Two more functions in `cli/features/`, reusing the shared `_validate.py` and the **identical `sma_gate` causal alignment** (return length `len(prices)-1`; `feature[k]` uses only `prices[≤k]`; warm-up → `0.0`):

1. **`trend_agreement(prices, *, lookbacks)`** — per-asset multi-horizon trend agreement: the average sign of momentum across the given `lookbacks`. For each `k`, `agreement[k] = mean(sign(momentum(prices, lookback=L)[k]) for L in lookbacks)` ∈ `[-1, +1]` (+1 = every horizon trending up, −1 = every horizon down, 0 = split / all warm-up), where `sign(x)` is `+1/−1/0` and a warm-up momentum (`0.0`) contributes `0`. Reuses `momentum` (so causality is inherited). `lookbacks` a non-empty list of `int ≥ 2` (reject `bool`), else `FeatureError`.
2. **`drawdown_state(prices)`** — current drawdown from the running (expanding) peak: `dd[k] = prices[k] / max(prices[0..k]) - 1` ∈ `[-1, 0]` (0 at a new high, negative below the peak). Length `len(prices)-1`, `dd[k]` uses only `prices[≤k]` (running max through `k`). No lookback (expanding window); no warm-up region beyond the natural `dd[0]` case.

Validation and the never-NaN/inf guarantee as in iter-040.

## Non-goals

No cross-asset features (the BTC-regime state is the existing `sma_gate`; a multi-asset ensemble aggregator belongs to the A1 book assembly, not the per-asset feature layer). No rolling-window variant of drawdown (expanding peak matches the "max drawdown" convention; a rolling variant is added only if A1 needs it). No A1 book, backtest, or verdict here.

## Testing / done

TDD on synthetic fixtures (`tests/test_features_trend_agreement.py`, `tests/test_features_drawdown.py`), per feature:

- **Known-answer:** `trend_agreement` — a series rising on all horizons → `+1.0` once all lookbacks are warm; a split (one horizon up, one down) → the hand-computed mean sign. `drawdown_state` — a series making a new high → `0.0`; a series `[10, 8]` → `dd = -0.2`; recovery back to a new high → `0.0`.
- **Warm-up / length:** output length `len(prices)-1`; `trend_agreement` neutral (`0.0`) while all horizons are in warm-up.
- **Look-ahead / leak test (centerpiece):** mutating `prices[k+1:]` leaves `feature[0..k]` bit-identical — the regression guard for both. For `trend_agreement` this follows from `momentum`'s causality; assert it directly anyway.
- **Guards:** `trend_agreement` empty/`bool`/`<2` lookback, non-positive price → `FeatureError`; `drawdown_state` short/non-positive/non-finite price → `FeatureError`.

`uv run pytest` green; `uv run pre-commit run -a` clean.

## Closeout (planned)

iter-041 iterations-history entry (folds into the iter-040 feature-substrate line of work). No strategy verdict (feature layer only). Scoping decision logged in `.tmp/decisions.md` `[iter-041]`.
