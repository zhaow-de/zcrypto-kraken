---
status: partial
ripe_when: "per family — C3: go-live is settled (otherwise ripe; re-deferred 2026-08-23, see `## Done so far`); B4-legs and B3: the §10 portfolio-limits code lands; C2: a tick catalog exists; C1: weeks of captured L2 exist"
---

# Bucket-B/C alpha families — the un-started remainder of the §5 queue

## Context — what

Phase 4 closed (2026-07-09, human time-box call) with the **A family fully verdicted** (A1+A2, 32/40 trials — an honest net-of-cost kill; the benchmark family itself won and B3+vt-dynamic was adopted as the frozen bar) and the rest of the master-plan §5 ranked queue **not started**: **B1** (intraday trend + time-of-day/day-of-week seasonality, 1h/4h, budget B=25 shared across Bucket B), **B2** (derivatives-positioning features — funding/OI/liquidations from free Coinalyze/Binance data), **B3** (cross-sectional long-only rank tilt + A1-short overlay — low prior, kill quickly), **B4** (relative-value trend on ETH/BTC, SOL/BTC ratio legs), **C1** (short-term reversal, needs captured-L2 maker realism), **C2** (BTC→alt intraday lead-lag, low prior), **C3** (on-chain regime features as gate inputs, free tiers). This topic keeps the queue durably registered now that master-plan §5 is no longer the current-phase pick-source.

## Why this matters

Buckets B (intraday band) and C (long shots) are where the master plan's residual-alpha probability is concentrated after the A-family kill — especially B1, whose economics live or die on maker-fill realism + turnover control, exactly the cost discipline the A-family arc built the tooling for (`net_of_cost_verdict`, per-asset turnover + margin-carry model, offset-averaged cadence method).

## Findings so far

- The A-family arc's binding lessons transfer wholesale: judge net-of-cost from the first verdict; the short's borrow carry is a structural ~5 %/yr drag; benchmark warm-up asymmetries must be windowed out.
- Prerequisites: T0009 resolved (protocol legs → revised kill bar, iter-072); **T0012 resolved (iter-085): the 15m substrate exists** — `data/ohlc-15m`, basket_sha256 `0fed24a6…`, tick-reconciled bit-exact. The tick catalog was dropped with T0012 — C2 must re-open it as its own topic. T0003 (captured L2 → C1) and T0014 (the spread term) resolved; maker-fill realism stays unmeasured.
- Budgets pre-registered: **B = 25**, shared across Bucket B (B1 spent 5, B2 spent 6, 14 remain), and **C = 10**, untouched; A is spent, 40 of 40.
- Two rulings bind every B and C pre-registration (the owner, 2026-10-15, `10.phase4-decisions.md` `[iter-176]`): the DSR leg binds at every `n_trials`, `var_trials` 0.0 included, as the ratified bar has it; and a search may read the spent holdout's window, 2026-04-01 → 2026-07-09, through `ohlc-rolling`, but no result there is reported as holdout or out-of-sample evidence.

## Done so far

- **B1 split out (iter-086)** as [T0022](archive/T0022-b1-intraday-seasonality-family.md), spec/plan `00045`; trial 3 (iter-177, spec/plan `00132`, registry trial 48) PARK; trial 4 (iter-178, spec/plan `00134`, registry trial 49) REJECT; trial 5 (iter-179, spec/plan `00135`, registry trial 50) REJECT; **closed as attributed out at iter-180** on the owner's pick, T0022 resolved.

- **B2 opened (iter-175, spec/plan `00128`)** on the owner's word of 2026-10-12, its trial 1 stopped unspent at the pre-flight; B2 trial 2 (iter-181, spec/plan `00137`, registry trial 51) REJECT; B2 trials 3–5 (iter-182, spec/plan `00138`, registry trials 52, 53 and 54) each REJECT, and reading 2 beside them; B2 trials 6–7 (iter-183, spec/plan `00139`, registry trials 55 and 56) each REJECT; B2's signal reading (iter-184, spec/plan `00140`, reading 3), no slot spent; B2's second signal reading (iter-185, spec/plan `00141`, reading 4), no slot spent; B2's re-risk reading (iter-186, spec/plan `00142`, reading 5), no slot spent; the family's state and the trigger of its next trial are [T0023](T0023-b2-derivatives-data-sourcing.md)'s.

- **C3 is ripe and deliberately NOT picked up (re-deferred 2026-08-23, owner's call).** C3's sourcing has been unblocked since iter-072; the reason is contention: the active front is the Phase-6b go-live run-up ([[T0085]]), and opening an alpha family competes with it for the same attention while the live path is being armed. This is a decision, not an oversight, recorded here so the ripe state stops reading as a miss.

## Standing prerequisites for any short-carrying or levered family (registered here because this topic's families fire them)

- **§10 portfolio limits — code DELIVERED (iter-088, spec/plan `00046`)**: `apply_gross_leverage_cap` (1.5×/2.0×), `apply_net_exposure_band` (−0.5…+1.0×), `margin_level` + `apply_margin_floor` (≥ 250 %, closed-form scaling, floor ≥ 1 domain) in `cli/risk/limits.py`, the `apply_position_caps` idiom throughout. **Remainder: wiring** into whichever family harness binds them first (B4-legs/B3's opening iteration) — composition order caps → gross → net → margin floor per the module docstring.
- **Re-run the borrow-unavailable stress rung** on any combined system containing a short sleeve — dispositioned N/A-with-evidence for the long-only book in `docs/research/11.phase5-stress-suite.md` (iter-060); §12's stress list makes it mandatory again the moment shorts exist.

## Suggested next steps

- Order per §5 ranking (B1 done, B2 open): B4-legs → B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).
