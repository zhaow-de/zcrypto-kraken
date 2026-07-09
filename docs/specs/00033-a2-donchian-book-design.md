# A2 — per-asset Donchian TSMOM ensemble book — Design

**Iteration:** iter-052 (build) · iter-053 (real-data verdict) · **Phase:** 4 (Alpha sprints, Bucket A)
**Refs:** `docs/research/08.phase4-a2-orientation.md` (the five A1 lessons binding this design), master-plan §5 (A2 definition + ranked queue), §9/§12 (validation protocol, kill bar, budgets). Reuses `cli/features/channel_position`, `cli/alpha/a1.py`'s inverse-vol/vol-target/backtest machinery, `cli/alpha/killbar.py` (`a1_kill_bar` **and** `net_of_cost_verdict`), `cli/costs/`, `cli/registry/`.

## Problem & context

A2 is the master plan's strongest published Bucket-A candidate: a **per-asset symmetric TSMOM ensemble with vol sizing** — a Donchian / multi-lookback ensemble per asset, long/flat/short, inverse-vol aggregated over the 10 majors. Per §5 it is an **A/B *inside* the A family**, not a new family: A1 (SMA-gate + trend-agreement) and A2 (Donchian breakout ensemble) are two parameterizations of one "vol-targeted per-asset trend book" hypothesis, sharing the **A = 40** trial budget (**24 spent on A1; 16 remain**).

A1's five-iteration arc ended in an honest kill: a real *zero-fee* edge that died net-of-cost (daily 10-asset reweighting + a ~5 %/yr short borrow carry), leaving **gated-B1 (net-of-cost Sharpe 1.047)** the deployable bar. A2's premise is precisely that a **Donchian breakout book is structurally lower-turnover** — positions persist until the opposite channel breaks — so it may keep its edge after the cost that killed A1. That is the hypothesis under test.

## Goals

1. **`cli/alpha/a2.py`** — `A2Config` + `a2_book_returns(prices_by_asset, *, config) -> dict`, a look-ahead-free A2 book:

   - **Per-lookback Donchian state machine** (the classic, and the low-turnover point). For asset `i`, window `w`, using `channel_position(prices_i, window=w)` ∈ [-1,+1] (already leak-free; `+1` exactly when `prices[k]` is the window max):
     `sig_w[k] = +1 if cp_w[k] >= band; -1 if cp_w[k] <= -band; else sig_w[k-1]` (hold), with `sig_w[k] = 0` before the first break. `band = 1.0` = the classic breakout. Strictly causal: depends only on `prices[<= k]` and the prior signal.
   - **Ensemble**: `d_i[k] = mean over w in lookbacks of sig_w[k]` ∈ [-1,+1].
   - **Short toggle**: `short="off"` → `d_i = max(d_i, 0)` (long/flat); `short="on"` → the negative part is scaled by `short_exposure = 0.5` (never a naked full short — A1's finding-2 discipline).
   - **Aggregation**: the same per-period **inverse-vol qualifying weights** A1 uses (asset qualifies iff its trailing `basket_lookback` return window is present, gap-free, positive-stdev; weight `1/stdev` renormalized), then `book_base_returns[k] = Σ_i w_i[k]·d_i[k]·ret_i[k]`, then `vol_target` → `run_backtest`. Base is always the equal-risk basket (§5: "inverse-vol aggregated").
   - Returns `{book_base_returns, vol_target_positions, net_returns, asset_positions, metrics}` — the same shape as `a1_book_returns`, so the iter-053 cost model (per-asset turnover + short margin carry) and both verdict tools plug in unchanged.

2. **Real-data verdict (iter-053)** — 8 registered trials, verdict net-of-cost-first (below).

## Toggles (8 trials; 8 of the 16 remaining held in reserve)

`lookbacks ∈ {fast=(10,20,40), slow=(20,50,100)}` × `short ∈ {off, on}` × `target_vol ∈ {0.10, 0.12}`. `band = 1.0` fixed (classic breakout). Frequency: **daily** — apples-to-apples with the frozen bar (gated-B1's net-of-cost 1.047 is daily) and with A1's whole cost arc; a 4h run needs its own benchmark and would confound "Donchian vs SMA-gate" with "4h vs 1d" — a clean, distinct follow-up.

## Verdict protocol (orientation lesson 1 — net-of-cost from the first verdict)

Every trial gets **both**:

- **`a1_kill_bar`** — the pre-registered legs, unchanged (DSR at the family trial count; SPA vs gated-B1; survives 1.5× cost stress; worst walk-forward regime slice not disqualifying). Unmodified: changing the pre-registered bar is a human Phase-5 call.
- **`net_of_cost_verdict`** — the honest net-of-cost head-to-head vs gated-B1's own net-of-cost series (the leg the pre-registered bar omits; `07`'s cost-asymmetry gap).

**Cost, charged from the first verdict**: per-asset net-position turnover × 1.5× Tier-1 maker (0.0060) **plus** short-leg margin carry (`margin_carry(|notional|, 24h, margin_rate(asset, band="high"))`). Also report the **turnover/drag decomposition vs A1** — the whole premise is that Donchian is cheaper.

**Registry**: `family="A1"` (the A-family key — a new key would restart `n_trials_in_family` and silently un-cap the shared A=40 budget), `n_trials_in_family` 25…32, `notes` carries `variant=A2-donchian`. Metrics numeric-only (no bool). An honest "A2 also loses net-of-cost / gated-B1 stays" is **success**.

## Non-goals

No 4h/1h run (follow-up). No change to `a1_kill_bar`'s pre-registered legs. No holdout touch (look budget 1, Phase-5, human-present). No budget expansion (8 trials, 8 reserved). No new benchmark — gated-B1 stays the frozen bar.

## Testing / done (distrust the instrument)

TDD on synthetic fixtures (`tests/test_alpha_a2_*.py`), before any real-data number:

- **Known-answer state machine**: a hand-built price path that makes a new `w`-high, drifts, then a new `w`-low → hand-computed `sig_w` (+1 held across the drift, flipping to −1 only at the low). Asserts the **hold** semantics, not just the breakout.
- **Look-ahead invariance (centerpiece)**: mutating `prices[k+1:]` for any asset leaves `net_returns[:k]` bit-identical; **verified to fail on a deliberately-peeking implementation** before being trusted.
- **Engagement**: each toggle (lookbacks / short / target_vol) demonstrably changes `net_returns`; `short="on"` produces negative `asset_positions` somewhere and `short="off"` never does.
- **Reduces-to-checks**: with a single lookback and `short="off"`, the book equals the hand-computed `Σ w_i·max(sig_w,0)·ret_i` vol-targeted; `asset_positions` dotted with per-asset returns reconstructs `net_returns` exactly (the A1 identity).
- **Low-turnover sanity (the premise)**: on the same synthetic universe, A2's per-asset position turnover is **materially lower** than an A1 book's — the structural claim, asserted in a test rather than assumed.
- Guards: bad enum/lookbacks/band/target_vol → `AlphaError`. `uv run pytest` green; `uv run pre-commit run -a` clean.

## Closeout

iter-052: merged `cli/alpha/a2.py` + tests, no verdict. iter-053: the 8-trial net-of-cost-first verdict → registry (25…32) + `docs/research/09.phase4-a2-results.md` + iterations-history. Deployment/holdout untouched.
