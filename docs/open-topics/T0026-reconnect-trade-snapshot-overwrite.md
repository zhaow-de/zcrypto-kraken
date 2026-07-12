---
status: open
ripe_when: the next attended capture-maintenance window (any daemon code change deploys there) — the read-only loss-quantification + the fix design are autonomous now
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
- **Net loss is PLAUSIBLE but unquantified.** BTC hours 02/03 trades are sparse and cluster in the last minutes of each hour; that *suggests* degradation, but overnight BTC/EUR is genuinely low-volume, so it is not proof. Quantifying requires a REST `/Trades` comparison for the affected windows (the pre-reboot live segments are already gone).

## Suggested next steps

- **(autonomous, read-only) Quantify the actual loss** from the 2026-07-11 reboot: pull Kraken REST `/Trades` for BTC/ETH/DOGE 2026-07-11 02:00–04:00 UTC and diff against the current (snapshot-overwritten) segments.
- **(autonomous, design + TDD on a branch) Fix the overwrite.** Options: (a) never overwrite an existing finalized `<HH>.parquet` — merge + dedupe by `trade_id` instead of replacing; (b) drop snapshot trades with `ts` older than process start except for backfilling the immediately-adjacent hour; (c) write snapshot-sourced rows to a provenance-tagged path and reconcile offline. Add a regression test: a fake reconnect snapshot spanning a finalized hour must not silently shrink it.
- Deploy any daemon change only via the attended capture-maintenance window (never disturb the running daemon unattended).
