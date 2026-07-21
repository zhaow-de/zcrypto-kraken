---
status: partial
ripe_when: T0003's capture has ≥2 weeks of L2 data — clock started 2026-07-08, so ≈2026-07-22; the compute home already exists (the ops-node 1s panel, iter-098), so the analysis is a one-query start when the window fills
---

# Captured-spread cost-model calibration

## Context — what

The Phase-2 and Phase-3 close-outs both carried forward the cost model's missing **spread term**: per-pair spread calibrated from our own captured depth-100 L2 (T0003's daemon), plus the combined spot+margin+spread cost helper deferred with it. It lived only in the closeouts' "carried forward" sections — backfilled here.

## Why this matters

Phase-4/5 verdicts currently charge Tier-1 maker fees + margin carry but assume zero spread. The A-family arcs showed cost realism is verdict-deciding (A1 and A2 both died or survived on cost terms); spread is the known-missing term, and it is largest exactly on the thin alts the basket holds.

## Findings so far

`cli/costs/` has the fee ladder + margin accrual (iter-017); the capture daemon has been recording depth-100 books since 2026-07-08 (hourly zstd-Parquet + manifests on the VPS). ~~The workstation pull / NAS sync is a T0003 remainder — this topic's analysis waits on that synced copy~~ *\[superseded by iter-098: the compute home is the **ops-node 1s L2 panel** (`l2-panel/`, spread + effective-spread-at-size for all pairs) — the analysis reads that, never the VPS\]*.

**First real-fill fee observation (iter-079, 2026-07-10, adapter-verification probe 5)**: taker fee **exactly 0.80 %/side** (€0.08000 on €9.99997, from `TradesHistory`) on the live account at zero 30-day volume, vs the modeled 0.6 %/side; spread cost on BTC/EUR ≈ 0.018 %. Within the pre-registered 2× band for the Stage-6b gate, but the tier discrepancy (fee ladder assumed Tier-1 maker-leaning rates) should be understood in this topic's calibration pass — see `docs/research/14.phase6-adapter-verification.md` §Observations.

## Done so far

- **The compute home exists** (2026-07-15, iter-098 / spec 00052): the 1-second L2 primitive panel on the ops node (NAS replica) carries per-second `spread`/`spread_bps` and effective-spread-at-size (`fill_bps_{bid,ask}_{100,1k,10k}`) for all 10 pairs over the full capture window — this topic's per-pair/per-session-bucket percentile analysis is now a one-query start over `l2-panel/` (see `docs/reference/data-catalog-full.md` → Live-accruing datasets). First-look medians (whole window, bps): BTC 0.18, ETH 0.83, SOL 1.48, XRP 1.36, LTC 2.60, DOGE 2.97, LINK 3.00, AVAX 3.40, ADA 3.73, DOT 5.33 — coherent with the iter-079 live observation.

## Suggested next steps

- **Read `docs/reference/capture-era-data-hygiene-map.md` FIRST** (T0071, built 2026-07-21). Its verdict: **read the full capture window** (from 2026-07-08 13:00) for both the spread and depth legs — the old "post-07-13 only (~9 days)" fallback is superseded; the desync-era archive was never contaminated (in-memory bug only; the panel replays through the fixed book). Honor the two standing caveats: completeness questions go to `continuity.py` / the panel's gap accounting, **never manifests** (T0036 truncation is hash-invisible); and if depth-beyond-rank-10 values are load-bearing, state the protocol-congruence caveat once (those ranks are venue-unverified in every era).
- From the synced captures: per-pair median/percentile top-of-book spread (and depth at our footprint), per session-time bucket.
- Add the spread term + a combined spot+margin+spread cost helper to `cli/costs/` (TDD).
- Robustness re-analysis (no new trials): re-read the A-family net-of-cost head-to-heads with spread included — does any conclusion move?
- **(optional falsification probe, cheap — run alongside the calibration if desired)** The map predicts **no** discontinuity in a depth-sensitive metric (`fill_bps` at a size whose fill walk passes rank 10) across matched clock-hours straddling 2026-07-14 04:00 UTC; finding one would contradict the map's soundness conclusion and reopen T0071.
