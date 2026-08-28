---
status: resolved
---

# REST trade-backfill for the capture daemon

## Context — what

The capture daemon records trade gaps but never fills them. Master-plan §8 specifies the daemon as *"systemd, NTP, hourly hashed segments, ≥7-day ring buffer, gap monitoring, **REST trade-backfill**"* — every clause shipped in iter-038 except the last, which was deferred with the note *"gaps are logged, not backfilled"*. This topic carries that remainder forward as its own item, split out of [[T0003]] at that topic's close (iter-099) so it is not lost in an archived file.

**Self-contained by design:** T0003 is archived, and archived topics are never re-read. Everything below that came from it is restated here rather than cross-referenced.

## Why this matters

**Trades are the one capture stream that is recoverable.** L2 books are unbackfillable — a lost book second is lost forever, which is why the whole pipeline is built around never losing one. Trades are different: Kraken's public REST `/Trades` endpoint serves history, keylessly (Phases 1–5 run with no API keys). So a trade gap is a *choice* to leave recoverable data unrecovered, not an unavoidable loss.

Three concrete consumers of the capability:

- **[[T0026]] cannot be finished without it.** A reconnect trade-snapshot silently overwrites an already-finalized trade hour **and regenerates its manifest**, so the segment hash-verifies while being shrunk. Its next step — quantifying the real loss from the 2026-07-11 reboot by pulling REST `/Trades` for BTC/ETH/DOGE 2026-07-11 02:00–04:00 UTC and diffing against the overwritten segments — is the same REST machinery this topic builds. Build them together.
- **The exit bar's "all hashes match" leg gives false assurance for trade segments** (the same T0026 mechanism: manifest regenerated after the overwrite). The Phase-1 exit bar was met **without** trade-backfill and does not depend on it (`docs/research/02.phase1-capture-exit-bar-report.md`), because the bar's gap measurement is a *book* measurement by design — for trades, silence is not downtime, so a quiet pair legitimately prints nothing and trades cannot measure uptime. Backfill is what would make trade completeness provable rather than assumed.
- **[[T0043]]** — a trades segment lost on both mirrors while its book sibling survives is currently invisible; a backfill pass that reconciles against REST would surface exactly that.

## Findings so far

Carried forward from [[T0003]] and the iter-099 exit-bar verification:

- **Gaps are logged, not filled.** `cli/capture/gap_monitor.py` tracks per-pair gap time (WS reconnect windows, checksum resyncs) and derives the gap ratios; nothing consumes those windows to re-fetch. Note its in-process limitation: `GapMonitor` state resets on restart, so it under-counts restart damage (it scored the 2026-07-13 crash at ~5.5 s against an actual 270 s loss) — it is a liveness signal, not a reliable backfill work-list.
- **Known trade-affecting windows in the current archive**: the 2026-07-11 04:00 UTC kernel reboot (~83 s) and the 2026-07-13 07:00 UTC WS-503 crash + restart clobber (~270 s). Interesting wrinkle from [[T0026]]: after the reboot, BTC `trades` hour-04 *starts at 04:00:00.11* — inside the window where capture was down — because the reconnect snapshot carried those trades. So the snapshot mechanism both **backfills** (good) and **overwrites** (bad); a design here must keep the first property while killing the second.
- **Cross-mirror trade differences are already detected**: the reconciler (spec `00050`) ledgers a `trade_deficit` state, and `trade_id` is globally unique across hosts — which is why its trade healing is row-level (merge/dedupe by `trade_id`) while book healing is whole-window. The same dedupe key applies to REST-sourced rows.
- **Not an exit-bar blocker.** The ≥7-day clean run passed on 2026-07-16 (worst stream 0.0624 % of the \<0.1 % bar, zero missing hours, 3738/3738 hashes) with no backfill in place.

## Resolution (2026-07-16, iter-100 — spec `00053`, plan `00053`)

**Delivered, and verified on the live archive.** The last unshipped §8 capture-daemon clause is shipped — as an offline pass that never touches the daemon at all.

| | before | after |
| -- | --: | --: |
| gaps | 194 | **0** |
| trades missing | 17,362 (3.60 %) | **0** |
| duplicate rows | 10,986 | **0** |

Worst-hit were the thin alts (AVAX 13.2 %, DOT 13.0 %, DOGE 9.8 %) — precisely the names where each print carries the most information, and the pairs [[T0014]]/[[T0024]] will calibrate against.

**What made it possible** — a property verified, not assumed: Kraken's `trade_id` is **dense** per pair (probed across a liquid pair, a thin pair, a crash window, and 18-month-old data). So the archive proves its own loss with no REST call, and REST repairs it. This gives trades what [[T0045]] denies books: provable completeness *and* a repair path.

**It closed the reconciler's stated blind spot.** *"When both streams are dark there is no witness to heal with, so the loss is permanent."* For trades that is now false — and it was not academic: the largest gap (974 BTC trades, 2026-07-08 18:59:57 → 19:50:42) **predates the secondary host entirely**, so no mirror could ever have healed it. It also corrected [[T0003]]'s archived claim that that window left "trades unaffected" — it did not.

**Verified by outcome, not by exit code:** the canonical (reconciled-first) view re-detects `gaps=0 missing=0 duplicates=0`; 391/391 minted hours verify against their manifests; the raw mirrors are **byte-identical** to their pre-mint baseline (1908 finals, aggregate sha `6093eede…`; books untouched at 1910); the 07-08 BTC window is contiguous `107998884..107999859`. A rate-limited gap of 34 trades failed on the first pass and was recovered exactly by the idempotent re-run — proving the retry path on real data.

Runs daily on the NAS beside the reconciler, minting into the existing overlay, so consumers changed nothing. [[T0033]]'s OPS-5 now relocates the reconciler **and** this backfill as one unit.

**Registered residuals** (none of them block this topic): [[T0052]] the metrics have no dashboard/alert/dead-man; [[T0053]] a permanent error degrades the daily gate to hourly-forever, and the live run showed Kraken rate-limits at 1.5 s spacing; [[T0054]] reconcile's `already_minted` skip vs backfill-minted hours, to check before the [[T0039]]-gated `--mint` flip.

## Superseded next steps

_(kept for the record; discharged above)_



- **(autonomous, read-only — do this first, it needs no design)** Quantify the real loss: pull Kraken REST `/Trades` for BTC/ETH/DOGE over 2026-07-11 02:00–04:00 UTC and diff against the current (snapshot-overwritten) segments. This both sizes [[T0026]] and proves the REST client against real data before any daemon change.
- **(autonomous, design)** Decide where backfill runs. It does **not** have to live in the daemon: an offline reconciliation pass over the archive (the ops node's compute tier, beside the panel/verify-replay timers) can fetch and merge without touching the live unbackfillable capture process at all — likely the lower-risk half of the design space.
- **(autonomous, design)** Merge semantics, informed by [[T0026]]'s lesson: **never overwrite a finalized `<HH>.parquet`** — merge and dedupe by `trade_id`. Provenance-tag REST-sourced rows so backfilled trades are distinguishable from live-captured ones (the archive's provenance convention already exists for reconciled hours: `<HH>.provenance.json`).
- **(autonomous)** Kraken REST `/Trades` specifics: pagination (`since` cursor), rate limits, and the retention horizon — confirm how far back the endpoint actually serves, since that bounds what is recoverable at all.
- **(human-gated, only if the design touches the daemon)** Any change to the running capture process is an attended deploy under the canary rule (`.claude/rules/fleet-deploys.md`): secondary bake ≥24 h before the primary re-pin. An offline/ops-node design avoids this gate entirely.
