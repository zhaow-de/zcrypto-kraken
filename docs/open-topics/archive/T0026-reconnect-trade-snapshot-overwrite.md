---
status: resolved
---

# Reconnect trade-snapshot silently overwrites finalized trade segments

## Context — what

On a **full** WS (re)connect (reboot, WS drop — not the frequent book-only resubscribe), Kraken replays a **trade snapshot** of recent trades whose timestamps span several **past** hours. The fresh `SegmentWriter` (no orphan-part recovery on startup — `command.py:167-203`) walks those trades and finalizes each spanned hour; `_finalize_hour` (`segment_writer.py:108-122`) **overwrites** any already-finalized `<HH>.parquet` (both `rename` and `sink_parquet` replace the destination) and then **regenerates the `.sha256` manifest to match**. So the finalized trade segments for the hours the snapshot spans are silently replaced by the snapshot's coverage, and the hash check can't see it.

## Why this matters

Silent trade-data overwrite on **every** full reconnect. The effect is asymmetric:

- **Can backfill** the outage window (good): after the 2026-07-11 04:00 reboot, BTC `trades` hour-04 starts at **04:00:00.11** — inside the ~83 s window where live capture (and the book) was down — because the snapshot carried those trades.
- **Can degrade** a fully-captured pre-reboot hour (bad): the new process rewrote `trades` hours 02, 03, … at 04:01:23; BTC `trades` hour-03 is now `[03:54:04 .. 03:59:54]` (17 rows, a snapshot tail), whereas the **same-window book segment is the untouched full live hour** `[03:00:00 .. 03:59:59]` (237 985 rows). If the live original held trades before 03:54 that the snapshot omitted, they are gone — and the regenerated manifest still verifies.

Books are unaffected (book snapshots carry *current* ts, so the book writer never rewrites a past hour). Trades are the **secondary** stream and are **REST-backfillable** (`/Trades`), so severity is low — but this is a real silent-data-integrity hole, and it means the ≥7-day exit-bar's "all hashes match" gives **false assurance for trade segments**. Related: [[T0008]] (reconnect recovery), [[T0003]] (the capture pipeline + its deferred REST trade-backfill).

## Findings so far

- **Overwrite CONFIRMED** (2026-07-11 04:00 UTC kernel-reboot forensics): the post-boot process logged `segment written … kind=trades …/02.parquet` and `…/03.parquet` (and back to Jul-10 19:00 for low-volume AVAX) at 04:01:23 — i.e. it rewrote pre-reboot trade hours from the reconnect snapshot. Book past-hours were **not** in that burst.
- **~~Net loss is PLAUSIBLE but unquantified.~~ QUANTIFIED AND REPAIRED (2026-07-16, iter-100, spec `00053`).** It was not just plausible — it was real, and bigger than this window. Kraken's `trade_id` is **dense per pair** (verified empirically), so the archive proves its own loss with no REST call: **17,362 trades (3.60 %) were missing across 194 gaps**, worst on the thin alts (AVAX 13.2 %, DOT 13.0 %, DOGE 9.8 %), alongside **10,986 duplicate rows** — the reconnect-replay duplicates this topic predicted. The overnight-BTC-is-thin objection is settled: REST showed BTC hour-02 trades from 02:00:00 where the archive started at 02:56. **All of it is recovered**: the canonical trade stream now re-detects `gaps=0 missing=0 duplicates=0`, 391/391 minted hours verify, and the raw mirrors are byte-identical. The comparison this bullet asked for is now a standing command (`zcrypto archive backfill-trades --detect-only`), not a one-off.

## Resolution (2026-07-16, iter-100)

Both halves are discharged, by two different iterations that met here:

- **The CAUSE is fixed** — not by this topic's own options list, but by [[T0036]]'s committed-final invariant (landed iter-095, deployed 2026-07-14): `<HH>.parquet` on disk is now *always* a committed, complete final, and the writer refuses to reopen one. A reconnect snapshot's rows for an already-closed hour are DROPPED with a `dropping late event` warning (`cli/capture/segment_writer.py`, whose comment cites this topic by name) instead of rewriting the hour. This is option (a) in spirit, reached from the other direction.
- **The EFFECT is repaired** — spec `00053` (iter-100). The damage this topic could only call "plausible but unquantified" was measured from `trade_id` density and then healed from Kraken's public REST: 17,362 trades recovered archive-wide, the canonical trade stream now re-detects `gaps=0 missing=0 duplicates=0`.

Note the trade-off the fix creates, since it is not free: the snapshot both *backfilled* (BTC hour-04 from 04:00:00.11, inside the down window) and *overwrote*. Dropping late rows kills the overwrite and forfeits the backfill — and the REST pass is what restores that benefit, with provenance, without touching the live daemon. So the pair of changes is complete only together.

**One deliberate residual, registered not dropped:** the exit bar's "all hashes match" leg still gives *false assurance for trade segments* in principle — a regenerated manifest verifies a shrunken file — which is why the `trade_id` invariant, not the hash, is the check. That reasoning is recorded in `docs/research/02.phase1-capture-exit-bar-report.md` and enforced by the backfill's post-mint re-check; it needs no separate topic because no mechanism can now shrink a finalized trade hour unseen.

## Superseded next steps

_(kept for the record; all discharged above)_



- **(autonomous, read-only) Quantify the actual loss** from the 2026-07-11 reboot: pull Kraken REST `/Trades` for BTC/ETH/DOGE 2026-07-11 02:00–04:00 UTC and diff against the current (snapshot-overwritten) segments.
- **(autonomous, design + TDD on a branch) Fix the overwrite.** Options: (a) never overwrite an existing finalized `<HH>.parquet` — merge + dedupe by `trade_id` instead of replacing; (b) drop snapshot trades with `ts` older than process start except for backfilling the immediately-adjacent hour; (c) write snapshot-sourced rows to a provenance-tagged path and reconcile offline. Add a regression test: a fake reconnect snapshot spanning a finalized hour must not silently shrink it.
- Deploy any daemon change only via the attended capture-maintenance window (never disturb the running daemon unattended).
