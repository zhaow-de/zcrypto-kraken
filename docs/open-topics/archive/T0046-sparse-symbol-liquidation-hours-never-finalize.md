---
status: resolved
ripe_when: n/a — resolved 2026-07-15 (wall-clock finalization landed + tested; ships to the running poller with the next ops-node image re-pin)
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

## Resolution (2026-07-15)

Option (B) — wall-clock finalization — landed, with one correction to this topic's own sketch: the naive `finalize_completed_hours(now)` (merge anything `< now`'s hour) would finalize an hour the instant it is merely over, which is unsafe for a re-fetching poller (see below); the shipped design instead takes an explicit `cutoff` the caller derives with its own safety margin.

- **`SegmentWriter.finalize_completed_hours(cutoff: datetime) -> int`** (`cli/capture/segment_writer.py`, purely additive — no existing method's signature or behavior changed) finalizes every hour strictly older than `cutoff`: (a) the writer's own open hour, if any and if older than `cutoff` — flushed and merged via the existing `_finalize_hour` path, leaving the writer with no open hour; (b) any crash-leftover part-hours already on disk older than `cutoff`, via the existing `_merge_hour` path (the same one `_sweep` uses). Hours `>= cutoff` are never touched, so a genuinely live pair rotates exactly as before — the live capture daemon never calls this method, so its own paths are provably unaffected. One subtlety this topic's sketch missed: clearing `_current_hour` to `None` is new for this class (ordinary rotation only ever advances it forward via `_open_hour`, which re-anchors the late-event floor for free as a side effect); with no such call here, the method re-anchors `self._floor` itself for every hour it actually finalizes, so a late replay for a finalized hour is still correctly dropped instead of silently reopening it.
- **The 31h cutoff.** `cli/liquidations/coinalyze.py` calls `writer.finalize_completed_hours(now - _FINALIZE_LAG_SECONDS)` per writer after each successful poll cycle, `_FINALIZE_LAG_SECONDS = 31 * 3600` — strictly greater than both the poller's own 30h re-fetch catch-up window and Coinalyze's ~25–33h bucket retention. Finalizing an hour any earlier would drop a post-outage re-fetch of it below the writer's late-event floor once closed — silently discarding data that was still recoverable. At 31h nothing recoverable remains (Coinalyze itself has already purged it), so finalization forecloses nothing genuinely retrievable; sparse-symbol manifests now appear at most ~31h late instead of never.
- **Poller-vs-recorder scoping.** This topic was originally scoped against the Binance forceOrder WS recorder (`cli/liquidations/recorder.py`/`command.py`), which is now **shelved** (Binance geo-fences the WS from every egress this project owns) and gets no tick. The live producer is the Coinalyze REST poller instead — same underlying `SegmentWriter` sparseness problem (10 coins, several liquidating rarely), but a materially different risk profile: the recorder's RAM-dwell concern (an unclean kill losing more than a flush interval, since Binance never redelivers a past force-order) does not carry over, because the poller's rows are always re-fetchable from Coinalyze's own REST history within its retention window — a crash loses at most one cycle's fetch, not the data itself.
- **Activation.** The code lands and is tested in this PR (`SegmentWriter` unit tests + poller-level integration tests, `tests/test_capture_segment_writer.py` / `tests/test_liquidations_coinalyze.py`); it takes effect on the running ops-node poller once the ops-node image is rebuilt with this change and re-pinned — deploy is part of this PR's lifecycle, not a separate follow-up.
