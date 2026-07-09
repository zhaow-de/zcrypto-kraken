---
status: open
ripe_when: per family — B1/B2/B4-legs/B3 after T0009's protocol legs are decided (the revised kill bar governs new trials) and, for B1, T0012's 15m/tick substrate; C1 additionally after weeks of captured L2 (T0003 pipeline mature); C2 after the tick archive is query-ready (T0012); C3 anytime after T0009
---

# Bucket-B/C alpha families — the un-started remainder of the §5 queue

## Context — what

Phase 4 closed (2026-07-09, human time-box call) with the **A family fully verdicted** (A1+A2, 32/40 trials — an honest net-of-cost kill; the benchmark family itself won and B3+vt-dynamic was adopted as the frozen bar) and the rest of the master-plan §5 ranked queue **not started**: **B1** (intraday trend + time-of-day/day-of-week seasonality, 1h/4h, budget B=25 shared across Bucket B), **B2** (derivatives-positioning features — funding/OI/liquidations from free Coinalyze/Binance data), **B3** (cross-sectional long-only rank tilt + A1-short overlay — low prior, kill quickly), **B4** (relative-value trend on ETH/BTC, SOL/BTC ratio legs), **C1** (short-term reversal, needs captured-L2 maker realism), **C2** (BTC→alt intraday lead-lag, low prior), **C3** (on-chain regime features as gate inputs, free tiers). This topic keeps the queue durably registered now that master-plan §5 is no longer the current-phase pick-source.

## Why this matters

Buckets B (intraday band) and C (long shots) are where the master plan's residual-alpha probability is concentrated after the A-family kill — especially B1, whose economics live or die on maker-fill realism + turnover control, exactly the cost discipline the A-family arc built the tooling for (`net_of_cost_verdict`, per-asset turnover + margin-carry model, offset-averaged cadence method).

## Findings so far

- The A-family arc's binding lessons transfer wholesale: judge net-of-cost from the first verdict; the short's borrow carry is a structural ~5 %/yr drag; benchmark warm-up asymmetries must be windowed out; the worst-slice leg is exposure-blind pending T0009.
- Prerequisites already tracked elsewhere: T0009 (protocol legs → revised kill bar), T0012 (15m/tick storage for B1/C2), T0003 (captured L2 accumulating since 2026-07-08 → C1), T0014 (captured-spread cost term — directly upgrades B1's maker-fill realism).
- Budgets pre-registered and untouched: **B = 25, C = 10**; A retains 8 reserved trials (T0009/T0011).

## Standing prerequisites for any short-carrying or levered family (registered here because this topic's families fire them)

- **Implement the remaining §10 portfolio limits as tested code first** — gross leverage 1.5×/2.0×, net-exposure band −0.5…+1.0×, margin-level floor ≥ 250 % — deferred in iter-059 because they never bind on the long-only P1 book (max gross 0.68×); any B4-leg/short/levered sleeve makes them binding (§10 mandates them "hard, enforced in code pre-trade").
- **Re-run the borrow-unavailable stress rung** on any combined system containing a short sleeve — dispositioned N/A-with-evidence for the long-only book in `docs/research/11.phase5-stress-suite.md` (iter-060); §12's stress list makes it mandatory again the moment shorts exist.

## Suggested next steps

- When the first prerequisite set fires, split the family being started into its own topic/spec (per family, one hypothesis + kill-bar plan) — this umbrella then goes `partial`/`resolved` per the lifecycle.
- Order per §5 ranking: B1 → B2 → B4-legs → B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).
