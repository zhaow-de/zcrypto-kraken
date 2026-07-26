---
status: partial
ripe_when: worked in dedicated rounds, so per round — (a) REACH is **partially done**: its REST leg landed 2026-07-23 (`zcrypto data rebuild ohlc-reach`), closing the 2026-03-31 → 07-08 hole at **daily and 4h** without any dump. Its remainder has three parts, each with its own trigger: the **live-trades→bars materializer** (autonomous, ripe now); the **Q2 OHLCVT ingest** (ripe when the Q2 dump publishes, expected late 2026-07); and the **1h promotion** — re-running the reach round after the Q2 ingest so the detached 1h segment gains a seam, which is only possible **before ~2026-07-30**, after which 1h for 2026-06-23 → 07-08 waits for the Q3 dump (~October). 15m for 2026-07-01 → 07-08 is already beyond REST's ~7.5-day window and is Q3-only; (b) EXECUTION-REPRODUCIBILITY (a committed backtest command + committed dataset-hash recipes) is ripe now and autonomous — research currently runs from gitignored scratchpad scripts with literal paths, and record 1's `ba47e37e` is not reproducible from committed code + manifest alone; (c) VALIDATION is [[T0064]]'s round and stays human-gated
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
2. **Reach — the fine-cadence ceiling (not yet its own topic).** Below 4h, the 2026-03-31 → 2026-07-08 hole is unfilled (the Q2/Q3 OHLCVT dumps are not yet ingested) and the **live-trades→bars producer is unbuilt** — though the components exist and are proven (`ticks_to_bars` at 100% vs OHLCVT; live trades captured + healed). This blocks any intraday/microstructure strategy family; irrelevant to the current 1d/4h one. **It is also no longer irrelevant to the universe**: [[T0093]] showed the universe rebuild reads `ohlc-full` and now fails closed on its 2026-03-31 frontier, so a pre-live refresh ([[T0025]]) needs a live tail. Note ingesting the dumps does **not** discharge that — they are quarterly, so a just-closed quarter still leaves the frontier weeks stale; the **live-trades→bars** half is the one that matters here, and per [[T0092]] it feeds EUR pairs only, leaving the two BTC-quoted legs without a live tail (they have dump data through 2026-03-31, just nothing current).
3. **Bookkeeping / reproducibility.** ~~Catalog stale + incomplete~~ (**closed** — OPS-6 rewrote it, iter-103 2026-07-18); ~~the deployable's identity is mis-recorded in the closeout/runbook~~ (**closed** — [[T0063]] resolved 2026-07-19: supersession pointers + the one-lookup runbook line); some dataset-hash *recipes* live only in gitignored scratchpad drivers (record 1's `ba47e37e` is **not** reproducible from committed code + manifest alone); there is **no committed backtest command** — research runs via gitignored scratchpad scripts with literal paths; ~~the compiled datasets are single-copy on the workstation~~ (**closed** — OPS-6's `hot/` replication, iter-103).

**What OPS-6 closed, and what it didn't.** OPS-6 (spec 00056, landed iter-103 2026-07-18) **closed durability** (the `hot/` replication is live) and **bookkeeping** (catalog rewritten + data-model reclassification + dead-config cleanup). It did **not** close **reach** (trades→bars + Q2/Q3 dumps), **validation** ([[T0064]]), or **execution-reproducibility** (a committed backtest command + committed hash recipes) — those remain this topic's live rounds below.

## Done so far

- **The REST leg of the REACH round landed 2026-07-23** (`zcrypto data rebuild ohlc-reach`, `cli/ohlc/reach.py`). It carries the live `ohlc-full` set forward from Kraken's public REST OHLC window instead of waiting on the dumps, and it exists because the dump timetable does not fit the data's expiry: the **Q2 dump had not yet published**, and the Q3 dump — the only source for 2026-07-01 → 07-08 — does not arrive until ~October.

  Measured on the real run (30 series = 10 symbols × 3 intervals):

  | grid | outcome | extent after the round |
  |---|---|---|
  | daily | **continuous**, seam overlap 607 bars, +113 appended | 2013-09-10 → **2026-07-22** |
  | 4h | **continuous**, seam overlap 38 bars, +682 appended | 2013-09-10 → **2026-07-23 12:00** |
  | 1h | **detached** (gap 2,009 bars ≈ 83.7 d) | a standalone 720-bar segment, 2026-06-23 → 2026-07-23 |

  So **daily and 4h are already whole to the present** — the 2026-03-31 → 07-08 hole is closed at both, without any dump. Verified: **zero irregular steps after the seam across all 20 continuous series** (the 62 irregular steps in BTC 4h are historical, newest 2025-11-01, well before the seam).

- **The receding-window asymmetry is the design driver, and it is why "detached" exists.** REST serves ~720 bars per interval, so its reach is set by the interval: ~720 d daily, ~120 d at 4h, ~30 d at 1h. The 1h window no longer reaches the canonical tail, so those bars cannot be *joined* — but a REST bar is retrievable only while the window still reaches it, so capturing it now is the only way to hold it now. **Be precise about what that buys here**: the Q2+Q3 dumps *will* cover 2026-06-23 → 07-23 at 1h, so this segment is a **bridge** (1h can go continuous months before Q3 lands) plus an independent REST-vs-dump cross-check — it is not preventing a permanent loss. The same applies to 15m: Q2+Q3 cover 2026-07-01 → 07-08, so that grid is October-**delayed**, not lost. They are written as `<interval>.detached.parquet`: kept, but under a filename no `ohlc-full` reader globs, so a detached segment cannot be silently spliced across the gap. Refusing to write them would have discarded perishable data; writing them as `<interval>.parquet` would have manufactured a series with an invisible hole.

- **A hard deadline this created, and it may already be unmeetable.** The 1h segment can only be *promoted* to continuous once an intervening dump closes the gap — i.e. after the Q2 ingest. But the 1h REST window keeps receding: once the canonical tail is 2026-06-30 (post-Q2), a ≥6-bar seam requires the promotion run to happen **before ~2026-07-30**. Q2 is expected "late next week", so **the window between Q2 landing and the 1h seam closing may be empty**. If it is, 1h for 2026-06-23 → 07-08 waits for Q3 in October — which is exactly why the segment was captured now rather than deferred to the Q2 round.

- **15m is out of reach and stays that way.** The 15m REST window spans only ~7.5 days, so it stopped reaching 2026-07-08 on that date. 2026-07-01 → 07-08 at 15m is recoverable **only** from the Q3 dump (~October), or not at all. It sits after the frozen canonical's 2026-03-31 end, so it does not touch any trial sample — it is a seam to mark when extending forward, not a blocker.

## Suggested next steps (dedicated rounds — pick when ripe; split into own specs when taken)

- **Fine-cadence reach round.** Build the live-trades→bars materializer (the `book → L2-panel` analogue for the trade tape; reuses `ticks_to_bars`), and ingest the 2026 Q2 (+ early Q3) OHLCVT dumps to extend the frozen canonicals past 2026-03-31 — together these lift the intraday ceiling. Ripe now (capture tape ≈10 days deep; the Q2 dump is likely published). Grid/watermark/catalog design belongs to its own spec. **Settle discipline (moved here from [[T0066]] 2026-07-19):** the materializer's spec MUST answer the settle-vs-heal-complete question explicitly — trades are heal-complete only after the *next day's* REST backfill (≤ ~28 h), a chasm not a race, so a settle-lag ≥ the daily trade-backfill (or ledger-driven invalidation) is required; do NOT copy the panel's original D6 "no settle margin needed" shape (which T0066 corrected).
- **Execution-reproducibility round.** A committed `zcrypto` research-run/backtest command (so a verdict is reproducible from the repo, not a gitignored driver), plus committing the dataset-hash recipes that currently live only in scratchpad (esp. record 1's `ba47e37e`).
- **Already tracked — do NOT duplicate here:** durability + catalog rewrite → **OPS-6 / spec 00056 (done, iter-103)**; deployable doc drift → **[[T0063]] (resolved 2026-07-19)**; deployable out-of-sample validation → **[[T0064]]**.
