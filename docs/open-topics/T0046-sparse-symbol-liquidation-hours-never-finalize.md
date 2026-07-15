---
status: open
ripe_when: the liquidations recorder is deployed and running (spec 00051 Task 5), or before OPS-2 is declared complete — whichever comes first
---

# Sparse-symbol liquidation hours never finalize promptly

## Context — what

The Binance liquidations recorder (spec 00051 OPS-2, `cli/liquidations/`) reuses `SegmentWriter`, whose hour rotation is **event-driven**: an hour `H` is finalized (merged parts → `<HH>.parquet` + `.sha256` manifest) only when the *next* event for that same symbol crosses into `H+1`. That fits the Kraken capture feed it was built for — ~10 liquid pairs, each emitting continuously. But `!forceOrder@arr` carries **every** Binance USD-M perp (hundreds of symbols), and most liquidate rarely: in calm markets a large fraction of symbols go hours with no liquidation, so their hour segments linger indefinitely as `<HH>.part####.parquet` with **no manifest**, never finalized until that symbol's next event or a process `close()`.

## Why this matters

Three consequences, all on data that is **not backfillable** ([[T0023]]):

- **The manifest-per-segment integrity guarantee doesn't cover the long tail.** `.sha256` sidecars are written only at finalize (`_commit`), so a sparse symbol's hours have no manifest for as long as they linger — the very durability ceremony (T0036/T0038) that justifies the archive is absent exactly where events are rarest.
- **Wider RAM-dwell loss window.** A sparse symbol's rows sit in the writer's buffer (or as parts) until its next event; an unclean kill (OOM, power loss) before the next flush loses more than capture's continuous high-volume pairs ever would. `close()` on SIGTERM flushes to parts, so a *clean* stop is safe — the exposure is the hard-crash window.
- **Task 5's acceptance test will read as a failure.** Spec 00051 Task 5 Step 5 says "after the next hour boundary confirm `<SYM>/…/<HH>.parquet` finals appear." For sparse symbols they won't — the check must be scoped to liquid symbols (BTCUSDT/ETHUSDT) or this looks like a bug (now adjusted in the plan to expect this).

## Findings so far

- Root cause: `SegmentWriter` (`cli/capture/segment_writer.py`) assumes each `(pair, kind)` stream emits continuously enough that the next event promptly closes the prior hour. A sparse multi-symbol feed violates that. The recorder mints a writer per symbol lazily (`LiquidationRecorder.append`), so hundreds of independently-sparse writers each stall their own rotation.
- Data is **not lost** by this: parts are on disk, and `close()` flushes the buffer to parts on shutdown. The gap is finalization *latency* + manifest coverage + the hard-crash RAM window — not durability under a clean stop.

## Suggested next steps

- **Decide between:**
  - **(A) Accept + document.** Leave rotation event-driven; sparse symbols finalize on their next event or on restart recovery. Document the behavior in `infra/ops/README.md`, and scope Task 5's acceptance check to liquid symbols. Cheapest; leaves the manifest/RAM gaps for rare symbols.
  - **(B) Wall-clock finalization.** Add a periodic recorder task (e.g. every few minutes) that finalizes every hour strictly older than the current wall-clock hour, via a new **additive** `SegmentWriter` method (e.g. `finalize_completed_hours(now: datetime)` that merges+manifests any open hour `< now`'s hour). Additive means the live capture daemon that shares `SegmentWriter` never calls it → no behavior change there — but `SegmentWriter` is shared with the live **unbackfillable** capture daemon, so the change and its tests need the same care as any capture-writer edit.
- **Recommendation:** (B) before the recorder runs long in production (it closes all three gaps); (A) is acceptable only for an initial short soak. Implement (B) as its own small TDD task (SegmentWriter method + recorder tick + tests), reviewed like any shared-writer change.
