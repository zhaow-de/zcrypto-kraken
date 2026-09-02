---
status: partial
ripe_when: "the Kraken OHLCVT Google Drive listing carries a 2026 Q2 (or later) quarterly ZIP — read the LISTING, never the support article's prose, which lags; see `## Suggested next steps` for the check"
---

# Data-pipeline maturity for strategy research — assessment + dedicated-round backlog

## Context — what

A standing assessment (2026-07-18 clarification session) of whether the data pipeline is in good shape to support strategy research, together with the data-model clarifications that session established. Registered as an **umbrella to be worked in dedicated rounds** — several of the gaps are already tracked (OPS-6, [[T0063]], [[T0064]]); this topic holds the synthesis plus the not-yet-tracked rounds so the whole picture survives one place.

## Why this matters

The pipeline is in good shape for the strategy already researched (1d/4h) but has **connective-tissue** gaps that bite for the *next* research direction and for autonomous operation. It distinguishes "good enough to have produced a candidate" (true today) from "robust enough to run unattended and extend to new families." The **core** (data correctness + reproducibility) is strong; the **plumbing** (durability, an accurate map, fine-cadence reach, out-of-sample proof) is thin. Losing this synthesis to a chat window would mean re-deriving it before the next data-foundation round.

## Findings so far

**Strong core (confidence: high).** The deployed strategy's substrate (`ohlc-full`, 1d/4h, 2013 → 2026-Q1) is deep, multi-regime, frozen, hash-pinned, and drift-STOP-gated; the reconstruction is validated two ways (1.0000 vs REST; 100% tick-reconciliation on ~8M ticks); every trial pins a `dataset_hash` with a "== record 1's input else STOP" gate; 1d/4h coverage to *now* is solved via dumps + REST (`engine-store`). The current strategy is **not** data-constrained.

**Data-model taxonomy (clarified this session).** Frozen research canonicals (`ohlc-full` / `ohlc-15m` / `ohlc-holdout-*` — immutable; a re-freeze *mints a new sibling*, never mutates); refreshable substrates (`derivatives-funding` / `snapshots` / `universe`); dead v0 (`ohlc` — no consumer, deletion candidate); per-host never-synced (`engine-store` / `engine-journal`); accruing operational (L2 panel / canonical trades / liquidations — ops-primary + NAS replica, unbackfillable + short + growing). No live-WS OHLC — OHLC is batch (dumps/REST); the live WS streams are `book` (→ panel) and `trade`.

**Strategy provenance.** The deployable = registry **record 47** (record 44 until 2026-08-16 — the re-ratification moved the traded basket to twelve legs and the record id, not the model; metrics measured identical, max abs diff `0.0`). The MODEL still consumes the ten EUR pairs on the same cadences; the live engine now carries twelve, the two `/BTC` legs at structurally-zero targets and contracted out before the builder sees them.

**Three gaps, ranked by how much they bite.**

1. **Validation evidence — [[T0064]] (most important).** The deployable (trial 44) has no out-of-time holdout: the one budgeted look tested a *superseded* system in a degenerate zero-exposure window. Paper trading is its only real out-of-sample test.
2. **Reach — the fine-cadence ceiling (not yet its own topic).** Below 4h, the 2026-03-31 → 2026-07-08 hole is unfilled (the Q2/Q3 OHLCVT dumps are not yet ingested) and the **live-trades→bars producer is unbuilt** — though the components exist and are proven (`ticks_to_bars` at 100% vs OHLCVT; live trades captured + healed). This blocks any intraday/microstructure strategy family; irrelevant to the current 1d/4h one. **It is also no longer irrelevant to the universe**: [[T0093]] showed the universe rebuild reads `ohlc-full` and now fails closed on its 2026-03-31 frontier, so a pre-live refresh ([[T0025]]) needs a live tail. Note ingesting the dumps does **not** discharge that — they are quarterly, so a just-closed quarter still leaves the frontier weeks stale; the **live-trades→bars** half is the one that matters here, and per [[T0092]] it feeds EUR pairs only, leaving the two BTC-quoted legs without a live tail (they have dump data through 2026-03-31, just nothing current).
3. **Bookkeeping / reproducibility.** ~~Catalog stale + incomplete~~ (**closed** — OPS-6 rewrote it, iter-103 2026-07-18); ~~the deployable's identity is mis-recorded in the closeout/runbook~~ (**closed** — [[T0063]] resolved 2026-07-19: supersession pointers + the one-lookup runbook line); some dataset-hash *recipes* live only in gitignored scratchpad drivers (record 1's `ba47e37e` is **not** reproducible from committed code + manifest alone); there is **no committed backtest command** — research runs via gitignored scratchpad scripts with literal paths; ~~the compiled datasets are single-copy on the workstation~~ (**closed** — OPS-6's `hot/` replication, iter-103).

**What OPS-6 closed, and what it didn't.** OPS-6 (spec 00056, landed iter-103 2026-07-18) **closed durability** (the `hot/` replication is live) and **bookkeeping** (catalog rewritten + data-model reclassification + dead-config cleanup). It did **not** close **reach** (trades→bars + Q2/Q3 dumps), **validation** ([[T0064]]), or **execution-reproducibility** (a committed backtest command + committed hash recipes) — those remain this topic's live rounds below.

## Done so far

- **The live-trades→bars materializer landed 2026-08-10 (spec/plan `00087`, iter-134) — REACH's autonomous half is closed.** `tape-bars` publishes 15m OHLCV daily finals from the captured trade tape, with 60/240/1440 derived exactly from the base. It is the only fine-cadence source whose reach does not expire: REST's window recedes and the dumps are quarterly, while the tape accrues.

  **The design's load-bearing choice was made by measurement, and the first draft had it wrong.** Publishing was originally gated on wall-clock — `now - day_end >= 26 h`, derived from the healer's nominal cadence. Cold review killed it: a clock is a *proxy* for "the backfill has run", and the healer's designed delay modes (the fail-closed NAS gate, a stamp written before the run so one failure costs the day's attempt, a leftover container extending an outage by up to 24 h) exceed that buffer by an order of magnitude. With no rewrite path, a proxy failure is silent, permanent, and indistinguishable from a quiet market. Heal-completeness is now **measured** by `cli/trades/gaps.py::detect` over `trade_id` contiguity — reading the day plus the nearest present segment each side, because `detect` treats first and last observed ids as endpoints and a one-day span is blind to a boundary hole.

  **A second premise fell the same way**: a rule refusing any day short of 24 hours would have made every day containing a *quiet* hour permanently unpublishable — the capture writer commits no final for an hour with no events, and zero-print trades hours are production-measured. Withdrawing it simplified the design, because `trade_id` contiguity already distinguishes a missing hour from a quiet one and file presence never could.

  **Verified against an independent witness, while one still exists.** The tape starts 2026-07-08 and `ohlc-full` ends 2026-03-31, so they do not overlap and there is no canonical to check against. Kraken REST at 15m does overlap — for ~7.5 days — and the control passed on real tape (BTC/EUR 2026-08-09, 96 bars, OHLC and trade count exact, volume to 6.6e-16). It also surfaced a durable fact about the venue: **Kraken publishes `vwap` truncated to the pair's price precision** (96/96 bars match under ROUND_DOWN to 0.1; 53/96 under round-half-even), so the assertion is the exact half-open tick identity rather than a widened tolerance. The control expires as the window recedes and skips honestly when it does — and skips distinctly on a network failure, so downtime never indicts the data.

  All eleven mutation probes killed their named guard. **Deployed 2026-08-10 14:49:08Z**: the attended ops converge landed, so the timer, its gauges and the two alert rules are live — `zcrypto_tapebars_exit_code` 0, `zcrypto_tapebars_days_gap` 0, last publish 2026-08-16T02:52:10Z.

- **EXECUTION-REPRODUCIBILITY is done in full (2026-08-09, spec `00086`) — recipe, command and ruling together, which is why this round leaves nothing parked.**

  The gap this closed: the registry validated `dataset_hash` as "a non-empty str" and nothing more, so whatever an uncommitted scratchpad driver passed became permanent provenance — and for 44 of 46 records it can no longer be resolved to anything.

  - **Identity is now what a run READ, not what a manifest declares.** `cli/registry/observed.py`'s `ObservedReader` hashes each parquet's bytes at read time, applies any window itself so rows-used cannot drift from rows-recorded, and accumulates the `{files, rows, span}` block. No manifest is parsed anywhere in the identity path — so [[T0132]]'s uncontracted writer zoo, which killed two earlier designs across nine review rounds, cannot reach it, and a new dataset backing a trial needs **zero** provenance code.
  - **`dataset_hash` is derived and unsuppliable**: `compute_hash(datasets)` through the registry's own hashing, so the derivation cannot be lost without breaking `record_hash` itself. `append()` has no argument through which to pass one.
  - **Enforced where it binds** — at load, for `schema_version >= 4`: block present, shaped, digest re-derives; plus a hard floor making every record past trial 46 declare schema 4, since nothing else compels a *new* record to say 4. The 46 committed records are exempt by trial id (they predate the block and are unrepairable) and load untouched.
  - **The door exists and is used**: `zcrypto research eval --subject … --dataset … [--register]` is the first production caller of `append()` in this project's history. Registration requires a committed subject, which turns the discipline record 44 already followed into the paved path.
  - **The legacy ruling is executed, not narrated**: `docs/reference/legacy-dataset-pins.jsonl` carries one row per pre-schema-4 hash with the epistemics **in the referent value** — `81dc9b44` unrecoverable with a null referent, `ba47e37e`/`45275ebe` marked INFERRED inline, `cccb8d17` reproduced by an executing test that names its unrecoverable operand. `ba47e37e` and `81dc9b44` are accepted as unverifiable; no further reconstruction is owed.

  **What it does not do, stated because a provenance claim that overreaches is worse than none**: it does not verify the freeze itself ([[T0133]]), does not see reads that bypass the loader, and cannot stop someone importing the code and lying to it — the fences there are the reviewed PR diff and the conformance pass, not a mechanism.

- **The REST leg of the REACH round landed 2026-07-23** (`zcrypto data rebuild ohlc-reach`, `cli/ohlc/reach.py`). It carries the live `ohlc-full` set forward from Kraken's public REST OHLC window instead of waiting on the dumps, and it exists because the dump timetable does not fit the data's expiry: the **Q2 dump had not yet published**, and the Q3 dump — the only source for 2026-07-01 → 07-08 — does not arrive until ~October.

  Measured on the real run (30 series = 10 symbols × 3 intervals):

  | grid | outcome | extent after the round |
  |---|---|---|
  | daily | **continuous**, seam overlap 607 bars, +113 appended | 2013-09-10 → **2026-07-22** |
  | 4h | **continuous**, seam overlap 38 bars, +682 appended | 2013-09-10 → **2026-07-23 12:00** |
  | 1h | **detached** (gap 2,009 bars ≈ 83.7 d) | a standalone 720-bar segment, 2026-06-23 → 2026-07-23 |

  So **daily and 4h are already whole to the present** — the 2026-03-31 → 07-08 hole is closed at both, without any dump. Verified: **zero irregular steps after the seam across all 20 continuous series** (the 62 irregular steps in BTC 4h are historical, newest 2025-11-01, well before the seam).

- **The receding-window asymmetry is the design driver, and it is why "detached" exists.** REST serves ~720 bars per interval, so its reach is set by the interval: ~720 d daily, ~120 d at 4h, ~30 d at 1h. The 1h window no longer reaches the canonical tail, so those bars cannot be *joined* — but a REST bar is retrievable only while the window still reaches it, so capturing it now is the only way to hold it now. **Be precise about what that buys here**: the Q2+Q3 dumps *will* cover 2026-06-23 → 07-23 at 1h, so this segment is a **bridge** (1h can go continuous months before Q3 lands) plus an independent REST-vs-dump cross-check — it is not preventing a permanent loss. The same applies to 15m: Q2+Q3 cover 2026-07-01 → 07-08, so that grid is October-**delayed**, not lost. They are written as `<interval>.detached.parquet`: kept, but under a filename no `ohlc-full` reader globs, so a detached segment cannot be silently spliced across the gap. Refusing to write them would have discarded perishable data; writing them as `<interval>.parquet` would have manufactured a series with an invisible hole.

- **A deadline this was once thought to create — and it was an overstatement, corrected 2026-07-23; the item it gated was dropped 2026-08-10.** The 1h segment can only be *promoted* to continuous once an intervening dump closes the gap — i.e. after the Q2 ingest. But the 1h REST window keeps receding: once the canonical tail is 2026-06-30 (post-Q2), a ≥6-bar seam requires the promotion run to happen **before ~2026-07-30**. Q2 was expected "late next week" as of 2026-07-23, so **the window between Q2 landing and the 1h seam closing may be empty**. If it is, 1h for 2026-06-23 → 07-08 waits for Q3 in October — which is exactly why the segment was captured now rather than deferred to the Q2 round.

- **15m is out of reach and stays that way.** The 15m REST window spans only ~7.5 days, so it stopped reaching 2026-07-08 on that date. 2026-07-01 → 07-08 at 15m is recoverable **only** from the Q3 dump (~October), or not at all. It sits after the frozen canonical's 2026-03-31 end, so it does not touch any trial sample — it is a seam to mark when extending forward, not a blocker.

- **The 1h early-promotion window closed UNMET and was consciously dropped.** 1h for 2026-06-23 → 07-08 now waits for Q3 exactly as 15m does. Q2 stays hard-required for fine-grain history inside its own quarter: 1h across 04-01 → 06-22 and 15m across 04-01 → 06-30 have no other source, since REST cannot reach back that far and the tape starts 2026-07-08. Verified absent 2026-08-10 and again 2026-08-23 — the newest 2026 dump on the NAS is Q1.

## Findings — the execution-reproducibility gap, measured 2026-08-08

**Two of the four `dataset_hash` values are unresolved; one reproduces exactly; one inherits.** A first pass here claimed *all* of them were unresolvable and that no recipe was recoverable from the repo. A cold second assessment refuted that, and the refutation was reproduced before being accepted. Corrected:

| hash | records | status |
|---|---|---|
| `ba47e37e` | ×38 — A1 (36) **and P1 (2)** | **unresolved**, and hardest-tested |
| `81dc9b44` | ×4, iter-074 | **unresolved** (4h primitive) |
| `45275ebe` | ×2, record 44 — the deployable | **inherits** from the two above |
| `cccb8d17` | ×2, iter-086/087 | **RESOLVES — recipe is committed** |

**`cccb8d17` reproduces from committed text**: `sha256(hex_4h + ":" + hex_15m)` = `cccb8d175d20…`, verbatim in `docs/specs/00045-b1-seasonality-conditioning-design.md` and restated in the registry's own `notes` for those records. Its 15m operand is `data/ohlc-15m`'s `basket_sha256` on disk, so half of it is anchored to bytes; its 4h operand is `81dc9b44` carried as a literal, so it is fully **reproducible** but only half **traceable to bytes**.

**What genuinely resists**: `ba47e37e` and `81dc9b44`, against ~226,000 candidate hashes — all 4096 pair subsets × intervals × orders × separators, parquet file bytes as components, union-calendar price matrices from `load_union` (what the driver actually fed the model), the deleted v0 `data/ohlc` catalog, and cross-dataset combinations. **Method validated on two independent controls** (`ohlc-full`'s own `basket_sha256` `70c2728e` and the universe artifact's `407d2ed8`), and all 36 per-series `sha256` re-derive today under the current polars, so frame-hash negatives are real rather than version drift. **Git history is clean** — no driver, notebook or helper was ever committed and deleted.

**The data did not move, proven by content rather than by a self-reported field.** All 36 per-series `sha256` in `ohlc-full`'s manifest reproduce from the parquet files today, and every parquet mtime is 2026-07-07 21:18–21:22, predating every registry record (07-09 → 07-11). The NAS replica is byte-identical. So modification-without-a-manifest-change is ruled out.

**Record 44 is NOT an unidentifiable dataset — that framing was wrong and is withdrawn.** Its hash cannot be recomputed, but committed state identifies its dataset precisely and redundantly: `tests/test_crossfreq_system.py` pins per-asset bar counts at 1440 and 240 plus last bar-start stamps behind a "canonical dataset drifted — STOP" assertion, `tests/test_record44_legs.py` pins the union bar counts, and `cli/portfolio/record44_legs.py` re-derives the registered legs. They pass against `data/ohlc-full` today. The accurate, narrow statement: **the hash cannot serve as an independent cross-check** — not that the dataset is unknown. [[T0125]] (resolved 2026-08-03) already worked this ground and re-grounded the go/no-go on a reproducible basis.

**THE REFERENT IS IDENTIFIED, even though the digest is not — and that is the property master-plan §8 actually wants.** §8 asks that a verdict reference the data it was fitted on rather than "latest". That is a question about *which data*, not about *which digest*, and it is answerable from committed state:

- **The runbook already pins the span.** `docs/research/12.phase5-system-spec-runbook.md` records `ba47e37e` with span **2013-09-10 → 2026-03-31**.
- **`data/ohlc-full` matches it exactly** — BTC/EUR daily is **4581 rows, 2013-09-10 → 2026-03-31**, measured.
- **Record 1's own `run_ref` agrees arithmetically.** `docs/research/06.phase4-a1-results.md` headlines "**2013→2026, 4581 returns**"; 4582 daily union stamps yield 4581 returns, and `UNION_BARS = {1440: 4582, 240: 27338}` is pinned in `tests/test_record44_legs.py`.
- **The only other daily dataset could not have produced it.** The v0 REST seed `data/ohlc` (retired 2026-07-18, absent from disk and the NAS) held **721 daily bars from 2024-07-17** — structurally incapable of a 2013→2026 walk-forward, and `data-catalog.md` states outright it was not to serve real backtests. Its per-series hashes also share **zero** overlap with `ohlc-full`'s.

**So: the `ba47e37e` records were fitted on the daily series that survives as `data/ohlc-full`.** State that as **identification by extent, not verification by digest** — it is an inference from an exact arithmetic match plus an exclusion, not a recomputation, and it must not be written up as though the hash had been reproduced. It is the same class of evidence that already carries record 44, whose extent pins run green.

**What stays genuinely lost**, and should be said wherever these hashes are cited: the *independent cross-check*. The digest can no longer be recomputed to catch a case where the data changed but the extent did not.

**A new defect this surfaced, worth its own attention.** `docs/research/12.phase5-system-spec-runbook.md` states `45275ebe = sha256(daily manifest ‖ 4h manifest)`. Read literally as those two digests it **does not reproduce** across ~100 tested forms. So a committed doc states a recipe that does not verify — it is describing semantics, not an executable rule, and a forward-fix must not treat it as one.

## Suggested next steps

_Dedicated rounds — pick when ripe; split into own specs when taken._

- **Fine-cadence reach round — the ingest half only.** Ingest the 2026 Q2 (+ early Q3) OHLCVT dumps to extend the frozen canonicals past 2026-03-31 and to supply the 1h/15m history inside Q2 that no other source can. **The check.** Kraken distributes OHLCVT as **Google Drive** ZIPs — one full archive plus per-quarter incrementals — linked from *Downloadable historical OHLCVT (Open, High, Low, Close, Volume, Trades) data* on `support.kraken.com`. The article is the entry point because no stable Drive URL is recorded here; if a future editor replaces it with one, verify that URL still resolves before trusting it. **Read availability off the DRIVE LISTING, never off the article's prose**: its coverage sentence read "currently end of Q3 2024" on 2026-09-02 while `ohlc-full` already ended 2026-03-31 — **547 days stale**, so a reader trusting it concludes the opposite of the truth.

  **Check history, and the two kinds are not equivalent.** 2026-08-10 and 2026-08-23 read the **NAS mirror** (newest 2026 dump there is Q1) — that shows what somebody downloaded, not what Kraken published, and is the weaker evidence this trigger was rewritten to replace. **2026-09-02 is the first check of the source itself** (owner): still absent. **And it is overdue** — the article says incrementals publish *at the end of each quarter*, Q2 2026 closed 2026-06-30, so it is ~2 months late. Read the trigger as *may not fire on schedule* rather than imminent; nothing here perishes and no escalation is owed.
- **Already tracked — do NOT duplicate here:** durability + catalog rewrite → **OPS-6 / spec 00056 (done, iter-103)**; deployable doc drift → **[[T0063]] (resolved 2026-07-19)**; deployable out-of-sample validation → **[[T0064]]**.
