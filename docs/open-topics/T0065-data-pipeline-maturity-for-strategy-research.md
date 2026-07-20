---
status: open
ripe_when: worked in dedicated rounds, so per round — (a) REACH (ingest the Q2/Q3 OHLCVT dumps for the 2026-03-31 → 2026-07-08 hole, and build the live-trades→bars producer) is ripe NOW per the index, and is autonomous: both components already exist and are proven (`ticks_to_bars` at 100% vs OHLCVT; live trades captured + healed). It blocks every intraday/microstructure family and nothing in the deployed 1d/4h system; (b) EXECUTION-REPRODUCIBILITY (a committed backtest command + committed dataset-hash recipes) is likewise ripe now and autonomous — research currently runs from gitignored scratchpad scripts with literal paths, and record 1's `ba47e37e` is not reproducible from committed code + manifest alone; (c) VALIDATION is [[T0064]]'s round and stays human-gated
---

# Data-pipeline maturity for strategy research — assessment + dedicated-round backlog

## Context — what

A standing assessment (2026-07-18 clarification session) of whether the data pipeline is in good shape to support strategy research, together with the data-model clarifications that session established. Registered as an **umbrella to be worked in dedicated rounds** — several of the gaps are already tracked (OPS-6, [[T0063]], [[T0064]]); this topic holds the synthesis plus the not-yet-tracked rounds so the whole picture survives one place.

## Why this matters

The pipeline is in good shape for the strategy already researched (1d/4h) but has **connective-tissue** gaps that bite for the *next* research direction and for autonomous operation. It distinguishes "good enough to have produced a candidate" (true today) from "robust enough to run unattended and extend to new families." The **core** (data correctness + reproducibility) is strong; the **plumbing** (durability, an accurate map, fine-cadence reach, out-of-sample proof) is thin. Losing this synthesis to a chat window would mean re-deriving it before the next data-foundation round.

## Findings so far

**Strong core (confidence: high).** The deployed strategy's substrate (`ohlc-full`, 1d/4h, 2013 → 2026-Q1) is deep, multi-regime, frozen, hash-pinned, and drift-STOP-gated; the reconstruction is validated two ways (1.0000 vs REST; 100% tick-reconciliation on ~8M ticks); every trial pins a `dataset_hash` with a "== record 1's input else STOP" gate; 1d/4h coverage to *now* is solved via dumps + REST (`engine-store`). The current strategy is **not** data-constrained.

**Data-model taxonomy (clarified this session).** Frozen research canonicals (`ohlc-full` / `ohlc-15m` / `ohlc-holdout-*` — immutable; a re-freeze *mints a new sibling*, never mutates); refreshable substrates (`derivatives-funding` / `snapshots` / `universe`); dead v0 (`ohlc` — no consumer, deletion candidate); per-host never-synced (`engine-store` / `engine-journal`); accruing operational (L2 panel / canonical trades / liquidations — ops-primary + NAS replica, unbackfillable + short + growing). No live-WS OHLC — OHLC is batch (dumps/REST); the live WS streams are `book` (→ panel) and `trade`.

**Strategy provenance.** The deployable = registry **record 44** (P1 cross-frequency, fixed 1/3 weights), on `ohlc-full` daily (1440) + 4h (240), span 2013-09-10 → 2026-03-31, 10 EUR pairs, `dataset_hash 45275ebe`. The live engine consumes the identical cadences/pairs (`engine-store` `GRID_INTERVALS=(1440,240)`). No 1h/15m in the deployed system (15m was the exploratory B1 sideline).

**Three gaps, ranked by how much they bite.**

1. **Validation evidence — [[T0064]] (most important).** The deployable (trial 44) has no out-of-time holdout: the one budgeted look tested a *superseded* system in a degenerate zero-exposure window. Paper trading is its only real out-of-sample test.
2. **Reach — the fine-cadence ceiling (not yet its own topic).** Below 4h, the 2026-03-31 → 2026-07-08 hole is unfilled (the Q2/Q3 OHLCVT dumps are not yet ingested) and the **live-trades→bars producer is unbuilt** — though the components exist and are proven (`ticks_to_bars` at 100% vs OHLCVT; live trades captured + healed). This blocks any intraday/microstructure strategy family; irrelevant to the current 1d/4h one.
3. **Bookkeeping / reproducibility.** ~~Catalog stale + incomplete~~ (**closed** — OPS-6 rewrote it, iter-103 2026-07-18); ~~the deployable's identity is mis-recorded in the closeout/runbook~~ (**closed** — [[T0063]] resolved 2026-07-19: supersession pointers + the one-lookup runbook line); some dataset-hash *recipes* live only in gitignored scratchpad drivers (record 1's `ba47e37e` is **not** reproducible from committed code + manifest alone); there is **no committed backtest command** — research runs via gitignored scratchpad scripts with literal paths; ~~the compiled datasets are single-copy on the workstation~~ (**closed** — OPS-6's `hot/` replication, iter-103).

**What OPS-6 closed, and what it didn't.** OPS-6 (spec 00056, landed iter-103 2026-07-18) **closed durability** (the `hot/` replication is live) and **bookkeeping** (catalog rewritten + data-model reclassification + dead-config cleanup). It did **not** close **reach** (trades→bars + Q2/Q3 dumps), **validation** ([[T0064]]), or **execution-reproducibility** (a committed backtest command + committed hash recipes) — those remain this topic's live rounds below.

## Suggested next steps (dedicated rounds — pick when ripe; split into own specs when taken)

- **Fine-cadence reach round.** Build the live-trades→bars materializer (the `book → L2-panel` analogue for the trade tape; reuses `ticks_to_bars`), and ingest the 2026 Q2 (+ early Q3) OHLCVT dumps to extend the frozen canonicals past 2026-03-31 — together these lift the intraday ceiling. Ripe now (capture tape ≈10 days deep; the Q2 dump is likely published). Grid/watermark/catalog design belongs to its own spec. **Settle discipline (moved here from [[T0066]] 2026-07-19):** the materializer's spec MUST answer the settle-vs-heal-complete question explicitly — trades are heal-complete only after the *next day's* REST backfill (≤ ~28 h), a chasm not a race, so a settle-lag ≥ the daily trade-backfill (or ledger-driven invalidation) is required; do NOT copy the panel's original D6 "no settle margin needed" shape (which T0066 corrected).
- **Execution-reproducibility round.** A committed `zcrypto` research-run/backtest command (so a verdict is reproducible from the repo, not a gitignored driver), plus committing the dataset-hash recipes that currently live only in scratchpad (esp. record 1's `ba47e37e`).
- **Already tracked — do NOT duplicate here:** durability + catalog rewrite → **OPS-6 / spec 00056 (done, iter-103)**; deployable doc drift → **[[T0063]] (resolved 2026-07-19)**; deployable out-of-sample validation → **[[T0064]]**.
