---
status: partial
ripe_when: per family — B2 and C3 are RIPE NOW and consciously re-deferred (see `## Done so far`); B4-legs and B3 need the §10 portfolio-limits code; C1 needs weeks of captured L2
---

# Bucket-B/C alpha families — the un-started remainder of the §5 queue

## Context — what

Phase 4 closed (2026-07-09, human time-box call) with the **A family fully verdicted** (A1+A2, 32/40 trials — an honest net-of-cost kill; the benchmark family itself won and B3+vt-dynamic was adopted as the frozen bar) and the rest of the master-plan §5 ranked queue **not started**: **B1** (intraday trend + time-of-day/day-of-week seasonality, 1h/4h, budget B=25 shared across Bucket B), **B2** (derivatives-positioning features — funding/OI/liquidations from free Coinalyze/Binance data), **B3** (cross-sectional long-only rank tilt + A1-short overlay — low prior, kill quickly), **B4** (relative-value trend on ETH/BTC, SOL/BTC ratio legs), **C1** (short-term reversal, needs captured-L2 maker realism), **C2** (BTC→alt intraday lead-lag, low prior), **C3** (on-chain regime features as gate inputs, free tiers). This topic keeps the queue durably registered now that master-plan §5 is no longer the current-phase pick-source.

## Why this matters

Buckets B (intraday band) and C (long shots) are where the master plan's residual-alpha probability is concentrated after the A-family kill — especially B1, whose economics live or die on maker-fill realism + turnover control, exactly the cost discipline the A-family arc built the tooling for (`net_of_cost_verdict`, per-asset turnover + margin-carry model, offset-averaged cadence method).

## Findings so far

- The A-family arc's binding lessons transfer wholesale: judge net-of-cost from the first verdict; the short's borrow carry is a structural ~5 %/yr drag; benchmark warm-up asymmetries must be windowed out; the worst-slice leg is exposure-blind pending T0009.
- Prerequisites: T0009 resolved (protocol legs → revised kill bar, iter-072); **T0012 resolved (iter-085): the 15m substrate exists** — `data/ohlc-15m`, basket_sha256 `0fed24a6…`, tick-reconciled bit-exact; note for B1 design: AVAX/LINK/DOT recent-year 15m density is 88–97% (real omitted no-trade slots — fill/skip policy is a B1 design decision). The tick catalog was dropped with T0012 — C2 must re-open it as its own topic. T0003 (captured L2 → C1) and T0014 (spread term → B1 maker realism, ripe ≈ 2026-07-22) unchanged.
- Budgets pre-registered and untouched: **B = 25, C = 10**; A retains 8 reserved trials (T0009/T0011).

## Done so far

- **B1 split out (iter-086)**: the family opened as its own topic [T0022](T0022-b1-intraday-seasonality-family.md) with spec/plan `00045` — per this umbrella's own split rule. The umbrella's remainder is B2/B3/B4 and C1–C3.

- **B2 and C3 are ripe and deliberately NOT picked up (re-deferred 2026-08-23, owner's call).** B2's sourcing has been unblocked since 2026-07-24 and C3 since iter-072, so neither waits on anything technical. The reason is contention, not readiness: the active front is the Phase-6b go-live run-up ([[T0085]]), and opening an alpha family competes with it for the same attention while the live path is being armed. Re-evaluate once go-live is settled — this is a decision, not an oversight, and it is recorded here so the ripe state stops reading as a miss.

## Standing prerequisites for any short-carrying or levered family (registered here because this topic's families fire them)

- **§10 portfolio limits — code DELIVERED (iter-088, spec/plan `00046`)**: `apply_gross_leverage_cap` (1.5×/2.0×), `apply_net_exposure_band` (−0.5…+1.0×), `margin_level` + `apply_margin_floor` (≥ 250 %, closed-form scaling, floor ≥ 1 domain) in `cli/risk/limits.py`, the `apply_position_caps` idiom throughout. **Remainder: wiring** into whichever family harness binds them first (B4-legs/B3's opening iteration) — composition order caps → gross → net → margin floor per the module docstring.
- **Re-run the borrow-unavailable stress rung** on any combined system containing a short sleeve — dispositioned N/A-with-evidence for the long-only book in `docs/research/11.phase5-stress-suite.md` (iter-060); §12's stress list makes it mandatory again the moment shorts exist.

## Suggested next steps

- Next family to split out when picked: B2 (ripe), then B4-legs/B3 (need the §10 portfolio-limits code first), then C3/C2/C1 per ranking.
- Order per §5 ranking (B1 done): B2 → B4-legs → B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).
