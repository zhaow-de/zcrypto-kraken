---
status: open
ripe_when: T0003's capture has ≥2 weeks of L2 data AND a synced (workstation/NAS) copy exists — clock started 2026-07-08, so ≈2026-07-22 at the earliest
---

# Captured-spread cost-model calibration

## Context — what

The Phase-2 and Phase-3 close-outs both carried forward the cost model's missing **spread term**: per-pair spread calibrated from our own captured depth-100 L2 (T0003's daemon), plus the combined spot+margin+spread cost helper deferred with it. It lived only in the closeouts' "carried forward" sections — backfilled here.

## Why this matters

Phase-4/5 verdicts currently charge Tier-1 maker fees + margin carry but assume zero spread. The A-family arcs showed cost realism is verdict-deciding (A1 and A2 both died or survived on cost terms); spread is the known-missing term, and it is largest exactly on the thin alts the basket holds.

## Findings so far

`cli/costs/` has the fee ladder + margin accrual (iter-017); the capture daemon has been recording depth-100 books since 2026-07-08 (hourly zstd-Parquet + manifests on the VPS). The workstation pull / NAS sync is a T0003 remainder — **this topic's analysis waits on that synced copy** (the dependency check marks it *waits-on*; never read from the VPS in a way that could disturb the daemon).

**First real-fill fee observation (iter-079, 2026-07-10, adapter-verification probe 5)**: taker fee **exactly 0.80 %/side** (€0.08000 on €9.99997, from `TradesHistory`) on the live account at zero 30-day volume, vs the modeled 0.6 %/side; spread cost on BTC/EUR ≈ 0.018 %. Within the pre-registered 2× band for the Stage-6b gate, but the tier discrepancy (fee ladder assumed Tier-1 maker-leaning rates) should be understood in this topic's calibration pass — see `docs/research/14.phase6-adapter-verification.md` §Observations.

## Suggested next steps

- From the synced captures: per-pair median/percentile top-of-book spread (and depth at our footprint), per session-time bucket.
- Add the spread term + a combined spot+margin+spread cost helper to `cli/costs/` (TDD).
- Robustness re-analysis (no new trials): re-read the A-family net-of-cost head-to-heads with spread included — does any conclusion move?
