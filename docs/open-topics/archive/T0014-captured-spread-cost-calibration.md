---
status: resolved
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

## Resolution (2026-07-22, iter-114, spec `00066`)

**The spread term exists and is charged.** `cli/costs/spread.py` holds a calibrated per-pair table plus `effective_spread_bps()` and `round_trip_cost()` (fee + spread both sides + optional carry), calibrated from `l2-panel` over the **full window** per [[T0071]]'s map — 10 pairs × 315 hourly files, `2026-07-08T13:47:33Z … 2026-07-21T15:59:59Z`, 1,123,509–1,123,514 rows/pair, 0.00 % null rate at every size. Reference: [`captured-spread-calibration.md`](../reference/captured-spread-calibration.md). Span recorded as its measured **13.1 days**, not rounded to the nominal 14 (the panel trails capture by the ~7 h settle watermark).

How each of the topic's steps disposed:

- *Read the hygiene map first* — done, and its falsification probe was **run**: `fill_bps@10k` across the 2026-07-14 04:00 capture-fix boundary moved −13 %…+1 % on seven pairs, scattered both ways. An artifact would move every pair the same way. The map survived a test that could have refuted it.
- *Per-pair percentiles per session bucket* — the percentiles are in the reference doc; the **session bucket was measured and rejected** (1.02×–1.08× across Asia/EU/US, inside the noise). One constant per pair per size.
- *Add the spread term to `cli/costs/` (TDD)* — done, 48 tests, table **and** provenance pinned so a recalibration cannot be silent.
- *A-family robustness re-read* — **no verdict moves, on a measured bracket**: the calibrated basket spread is ×1.035–1.069 on trial 44's 0.006/side, and even the worst realistic stack (×1.403) sits strictly inside the already-registered ×1.5 anchor whose governed 1.3029 still clears the frozen benchmark 1.2455. Sharpe is monotone in cost, so everything below ×1.5 clears. No new trial registered.

**The measurement that mattered most was not the one the topic expected.** The topic's own Findings flagged the iter-079 tier discrepancy as something to "understand in this calibration pass". Understood, and it is **six times larger than the spread term**: modeled 0.60 %/side against an observed tier-1 taker fill of 0.80 % (×1.333, versus spread's ×1.035–1.069). No verdict changes, but the deployable record's headline 1.5609 is a ×1.0-cost figure. Split out as [[T0090]] — the residual is the *presentation* of the record and the maker-vs-taker execution decision, both of which belong to the 6b brief, not here.

A second durable finding, recorded in the code, the reference doc and the data catalog: **never quote a median top-of-book spread for BTC/EUR** — it is tick-quantised at €0.10 and sits at one tick 42–58 % of the time, so the median swings ~15 × on a small change in that share (mean ÷ median 11.2×, against 0.9–1.3× for every other pair).

## Suggested next steps

_(none — resolved. The remaining cost-realism work is [[T0090]] (re-quote the record at the realistic stack; decide maker vs taker) and [[T0024]], which reads the same panel window.)_
