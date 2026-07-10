---
status: resolved
---

# P1 fixed-weight combination variant

## Context — what

Trial 43's verification pass (iter-080) ran a fixed-⅓-weights counterfactual of the adopted cross-frequency combination and it scored **higher** than the pre-registered adaptive inverse-vol weighting — governed net-of-cost Sharpe **1.5609 vs 1.5366**. The adaptive 180-bar inverse-vol layer costs a little (turnover + timing) and delivered no benefit on this history. The counterfactual was diagnostics only; swapping the adopted construction post-hoc would be post-selection, so the simplification is parked here as a candidate **pre-registered P1 trial**.

## Why this matters

If a pre-registered trial confirms it, the deployable system gets *simpler* (one less stateful mechanism to build, journal, and reconcile in the Phase-6 engine) at equal-or-better performance — simplicity is an operational-risk win, not just an aesthetic one. If it fails, the adaptive layer's value is established honestly.

## Findings so far

Trial 43 (registry, family P1 n=3, adopt): adaptive 1.5366 / fixed-⅓ counterfactual 1.5609 on identical sleeves, cap, costing, and governor (`stage1b_verify.py`, iter-080; decisions log `[iter-080]`). Sleeve correlations B–A2 0.563, A1–A2 0.592 — the win is three-way diversification, robust to removing the weighting entirely.

## Done so far

- **Trial run — iter-081** (human-ordered, same session as trial 43): pre-registered rule in the decisions log `[iter-081]`, then **registry trial 44 — ADOPT**: Sharpe 1.5609/1.5583 decisive, maxDD 13.57 %, every ratified leg passing (SPA grid max p 0.0060; DSR ≈ 1.0 at n=4; worst-slice pass; stress ×1.5/×2 1.3029/1.2106). The same driver reproduced trial 43 bit-identically before the weight change (cross-check gate).
- **Fold-in**: trial 44 supersedes trial 43 as the deployable-system candidate; T0018's engine scope now targets record 44 (the adaptive-weighting mechanism is gone from the build).

## Suggested next steps

_(none — resolved)_
