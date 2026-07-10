---
status: open
ripe_when: the next research loop picks packages (P1 family has trial budget headroom and the finding is one clean A/B)
---

# P1 fixed-weight combination variant

## Context — what

Trial 43's verification pass (iter-080) ran a fixed-⅓-weights counterfactual of the adopted cross-frequency combination and it scored **higher** than the pre-registered adaptive inverse-vol weighting — governed net-of-cost Sharpe **1.5609 vs 1.5366**. The adaptive 180-bar inverse-vol layer costs a little (turnover + timing) and delivered no benefit on this history. The counterfactual was diagnostics only; swapping the adopted construction post-hoc would be post-selection, so the simplification is parked here as a candidate **pre-registered P1 trial**.

## Why this matters

If a pre-registered trial confirms it, the deployable system gets *simpler* (one less stateful mechanism to build, journal, and reconcile in the Phase-6 engine) at equal-or-better performance — simplicity is an operational-risk win, not just an aesthetic one. If it fails, the adaptive layer's value is established honestly.

## Findings so far

Trial 43 (registry, family P1 n=3, adopt): adaptive 1.5366 / fixed-⅓ counterfactual 1.5609 on identical sleeves, cap, costing, and governor (`stage1b_verify.py`, iter-080; decisions log `[iter-080]`). Sleeve correlations B–A2 0.563, A1–A2 0.592 — the win is three-way diversification, robust to removing the weighting entirely.

## Suggested next steps

- Pre-register and run a P1 trial: identical construction to trial 43 with weights fixed at ⅓ (degenerate-window convention then moot); verdict vs trial 43's 1.5366 under the ratified bar + the `[iter-073]` DD-aware criterion. One arm, cheap (~15 min compute with the iter-080 caches' methods).
- If adopted, fold the simplification into the Phase-6 deployable record before the engine's builder work hardens (coordinate with T0018).
