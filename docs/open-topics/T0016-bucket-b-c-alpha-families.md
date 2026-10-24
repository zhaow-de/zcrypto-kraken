---
status: partial
ripe_when: 'per family — C3: go-live is settled (otherwise ripe; re-deferred 2026-08-23, see `## Done so far`); B4: an activity, the owner picks B4''s next step after trial 1 — a further trial or closing the family — recorded in the decisions log, check: `grep -c -E ''^\[iter-[0-9]+\] B4.s next step after trial 1'' docs/research/10.phase4-decisions.md` prints at least 1; B3: the §10 portfolio-limits code lands; C2: a tick catalog exists; C1: weeks of captured L2 exist'
---

# Bucket-B/C alpha families — the un-started remainder of the §5 queue

## Context — what

Phase 4 closed (2026-07-09, human time-box call) with the **A family fully verdicted** (A1+A2, 32/40 trials — an honest net-of-cost kill; the benchmark family itself won and B3+vt-dynamic was adopted as the frozen bar) and the rest of the master-plan §5 ranked queue **not started**: **B1** (intraday trend + time-of-day/day-of-week seasonality, 1h/4h, budget B=25 shared across Bucket B), **B2** (derivatives-positioning features — funding/OI/liquidations from free Coinalyze/Binance data), **B3** (cross-sectional long-only rank tilt + A1-short overlay — low prior, kill quickly), **B4** (relative-value trend on ETH/BTC, SOL/BTC ratio legs), **C1** (short-term reversal, needs captured-L2 maker realism), **C2** (BTC→alt intraday lead-lag, low prior), **C3** (on-chain regime features as gate inputs, free tiers). This topic keeps the queue durably registered now that master-plan §5 is no longer the current-phase pick-source.

## Why this matters

Buckets B (intraday band) and C (long shots) are where the master plan's residual-alpha probability is concentrated after the A-family kill — especially B1, whose economics live or die on maker-fill realism + turnover control, exactly the cost discipline the A-family arc built the tooling for (`net_of_cost_verdict`, per-asset turnover + margin-carry model, offset-averaged cadence method).

## Findings so far

- The A-family arc's binding lessons transfer wholesale: judge net-of-cost from the first verdict; the short's borrow carry is a structural ~5 %/yr drag; benchmark warm-up asymmetries must be windowed out.
- Prerequisites: T0009 resolved (protocol legs → revised kill bar, iter-072); **T0012 resolved (iter-085): the 15m substrate exists** — `data/ohlc-15m`, basket_sha256 `0fed24a6…`, tick-reconciled bit-exact. The tick catalog was dropped with T0012 — C2 must re-open it as its own topic. T0003 (captured L2 → C1) and T0014 (the spread term) resolved; maker-fill realism stays unmeasured.
- Budgets pre-registered: **B = 25**, shared across Bucket B (B1 spent 5, B2 spent 7, B4 spent 1, 12 remain), and **C = 10**, untouched; A is spent, 40 of 40.
- Two rulings bind every B and C pre-registration (the owner, 2026-10-15, `10.phase4-decisions.md` `[iter-176]`): the DSR leg binds at every `n_trials`, `var_trials` 0.0 included, as the ratified bar has it; and a search may read the spent holdout's window, 2026-04-01 → 2026-07-09, through `ohlc-rolling`, but no result there is reported as holdout or out-of-sample evidence.
- **B4 trial 1 REJECT (iter-189, spec 00144, registry trial 58).** Matrix row 5 fired: arm A passed its bar and arm B, the ETH/BTC and SOL/BTC legs added to the A2-4h ensemble, passed the kill bar, but its head-to-head against arm A from the first ratio weight was negative; both legs held a position and the book borrowed the BTC they sold beyond its own — the figures in `10.phase4-decisions.md` `[iter-189] Verdict — B4 trial 1 REJECT`.

## Done so far

- **B1 split out (iter-086)** as [T0022](archive/T0022-b1-intraday-seasonality-family.md), spec/plan `00045`; trial 3 (iter-177, spec/plan `00132`, registry trial 48) PARK; trial 4 (iter-178, spec/plan `00134`, registry trial 49) REJECT; trial 5 (iter-179, spec/plan `00135`, registry trial 50) REJECT; **closed as attributed out at iter-180** on the owner's pick, T0022 resolved.

- **B2 opened (iter-175, spec/plan `00128`)** on the owner's word of 2026-10-12, its trial 1 stopped unspent at the pre-flight; trials 2–8 (iter-181 to iter-187, registry trials 51–57) each REJECT, readings 2–5 beside them, no slot spent; **closed at iter-188** on the owner's word of 2026-10-23, [T0023](archive/T0023-b2-derivatives-data-sourcing.md) resolved.

- **B4 opened (iter-189, spec/plan `00144`)** on the owner's family pick of 2026-10-23, its trial 1 the loop's pick under the owner's run instruction: the module `cli/alpha/b4.py`, the subjects `b4-ratio-legs` and `b4-ratio-legs-preflight`, the data-gated basis test `tests/test_research_b4_ratio_legs_basis.py`, the family key `B4` in bucket B. Trial 1 (registry trial 58) REJECT.

- **C3 is ripe and deliberately NOT picked up (re-deferred 2026-08-23, owner's call).** C3's sourcing has been unblocked since iter-072; the reason is contention: the active front is the Phase-6b go-live run-up ([[T0085]]), and opening an alpha family competes with it for the same attention while the live path is being armed. This is a decision, not an oversight, recorded here so the ripe state stops reading as a miss.

## Standing prerequisites for any short-carrying or levered family (registered here because this topic's families fire them)

- **§10 portfolio limits — code DELIVERED (iter-088, spec/plan `00046`)**: `apply_gross_leverage_cap` (1.5×/2.0×), `apply_net_exposure_band` (−0.5…+1.0×), `margin_level` + `apply_margin_floor` (≥ 250 %, closed-form scaling, floor ≥ 1 domain) in `cli/risk/limits.py`, the `apply_position_caps` idiom throughout. **Wiring DELIVERED (iter-189, spec/plan `00144`)**: B4's harness, `cli/alpha/b4.py`'s `limit_factors`, passes a book's per-base exposures through gross → net → margin floor at §10's values as one factor per bar and records each limit's engaged bars; per-asset position caps, which the A2 ensemble does not carry, are not wired.
- **Re-run the borrow-unavailable stress rung** on any combined system containing a short sleeve — dispositioned N/A-with-evidence for the long-only book in `docs/research/11.phase5-stress-suite.md` (iter-060); §12's stress list makes it mandatory again the moment shorts exist. B4 trial 1 records the rung for its BTC shortfall (the `no_borrow_*` keys of registry trial 58).

## Suggested next steps

- (owner) B4's next step after trial 1's REJECT — a further trial (ETH/BTC alone; the symmetric legs, short the pairs at an ETH or SOL borrow; a further leg or pair; the legs' own vol target or weight cap) or closing the family — recorded as a `[iter-NNN] B4's next step after trial 1` entry; then per §5 ranking: B3 → C2 → C3 → C1 (C1 last: taker economics near-certainly kill it without L2 maker realism).
