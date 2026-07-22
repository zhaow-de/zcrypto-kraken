# Capture-era data-hygiene map

Consumer-side verdicts for the live-capture-derived datasets across the early-capture bug era ([T0071](../open-topics/archive/T0071-capture-era-data-hygiene-map.md), built 2026-07-21). A pipeline claim ("files complete, manifests verify") is not a research claim; this map states what research may read and with which caveats, so nothing is trained or calibrated on the bug-era tape unknowingly. Verdicts change only with new repair or measurement evidence — record any revision here with the measurement that justifies it.

## The headline finding — the content is sound in every era; the real risks are structural

The topic that commissioned this map assumed the desync-era archived book hours "contain whatever the unpruned book wrote." **That assumption is false, by the fix topic's own evidence and by the capture code:**

- The archive stores **Kraken's wire messages verbatim** — `cli/capture/command.py` writes each message's own `bids`/`asks` levels; the in-memory `OrderBook` is consulted only for CRC/desync *detection* and never writes its state into the archive. The famous contamination measurement (the unpruned book holding **810 bids / 468 asks against Kraken's 100-level window**) describes that in-memory book only. T0008 states the consequence in bold: "**No data was ever lost.** … replaying them with the fix yields a perfect book, zero failures. Only the *in-memory* reconstruction was wrong. So the archive is sound."
- Every book-*state* product is **replay-built through the fixed (pruning) book**: the L2 1s panel (first materialized 2026-07-15, iter-098) walks canonical hours through `OrderBook(pair, depth)` from the fixed `cli/capture/book.py`. (Canonical trades and the reconciled book are derived by union/splice of the sound wire messages, so they inherit soundness directly.) Phantom levels never existed in any panel row, in any era. The 482/117/398 → **0** CRC replay result is precisely the proof that replay-with-prune reconstructs cleanly from the desync-era tape.

So there is **no era-boundary for content**. What varies by era is *structural* quality — gap density, truncation exposure, redundancy — and one content caveat applies uniformly to all eras.

## Content caveats (era-independent)

| Dataset | Verdict | Basis |
|---|---|---|
| Canonical trades | **KEEP, no caveat** | Kraken's `trade_id` is dense per pair, so the archive proves its own completeness: `gaps=0 missing=0 duplicates=0` archive-wide, 391/391 minted hours verified, raw mirrors byte-identical to the pre-mint baseline ([T0050], 2026-07-16). |
| Book / panel, ranks 1–10 | **KEEP** | Venue-CRC-verified on every update, in every era. |
| Book / panel, ranks > 10 | **KEEP, with a stated caveat** | Never venue-verified in ANY era (Kraken's checksum covers ranks 1–10). Correctness rests on protocol congruence, corroborated by the full CRC verify-replay — 2,190/2,190 hours coherent with venue checksums (iter-096) — but conclusions that lean hard on depth-beyond-10 should say so once. This caveat is uniform: it does not distinguish the desync era from today. |
| Liquidations (Coinalyze) | **KEEP** | Independent pipeline (OPS-2, iter-097); no capture bug touches it. Coverage floor ≈ 2026-07-14T12Z (the 1,878-bucket first-cycle catch-up). |

## Structural windows (era-dependent)

| Window (UTC) | What happened | Consumer guidance |
|---|---|---|
| **2026-07-08 13:00 → 07-09 00:00** — launch day | First hour truncated at 2,852 s ("capture's first hour — *not* loss"); launch-evening crash-loop, 38 restarts 20:33–21:31 (0 since); the largest-ever trade gap (974 BTC trades, 18:59:57 → 19:50:42) — since healed *exactly* by REST ([T0050]) and predating the secondary host entirely. | FLAG for continuity-sensitive analyses; fine for level/aggregate reads that honor the panel's gap accounting. |
| **07-09 → 07-14 04:00:42** — desync-heal era | ~200 self-inflicted desyncs/day, each healed at median ≈ 0.1 s (aggregate gap-time ≈ 0.005%); the T0036 truncation class (20 standing truncated hours, worst stream 0.0856%); the T0037 short-hour class (an exposure — never observed in production); one T0035 crash (07-13 07:04). | FLAG for event-sequence / continuity-sensitive microstructure studies (the tape is gap-pocked, not biased). Level and aggregate reads: KEEP. |
| **07-14 04:00:42 → secondary bring-up (~07-14 evening; exact moment unrecorded)** | The fix image (`sha256:63708539…`, depth-prune + T0036/T0035/T0037 fixes) reached the primary at 04:00:42 with 1 s downtime; desyncs 16/h → 0 at T+1h. The secondary **never ran a pre-fix image** — it was brought up afterward on the same digest — so this window is single-host, not mixed-content. | Redundancy note only: no cross-host healing exists for this window. Content: KEEP. |
| **≥ secondary bring-up** — two-host era | All fixes live fleet-wide; cross-host reconciliation active. | KEEP. |

**The completeness instrument is `continuity.py` + the panel's own gap/anchoring accounting — NOT manifests.** T0036-class truncation is hash-invisible by construction: the manifest is regenerated over the truncated file and verifies clean (the data catalog says it plainly: "Do not trust the `.sha256`"). A reader that checks completeness via manifests inherits exactly the silent risk this map exists to prevent.

## What the T0014 / T0024 calibration must do

- **Read the full capture window** — from 2026-07-08 13:00 wherever hours exist and anchor — for both the top-of-book spread leg and the depth legs (`fill_bps_*`). No era cut is warranted: the informal "post-07-13 only (~9 days)" fallback was needlessly restrictive and is superseded.
- Rely on the panel's anchoring/settle/gap machinery for completeness, never on manifests; state the ranks-beyond-10 protocol-congruence caveat once in the write-up if depth-beyond-10 values are load-bearing.
- Optionally down-weight or sensitivity-check the launch day (07-08), which is gap-dense.

## Falsification probe — RUN 2026-07-22, and INCONCLUSIVE (see [T0014](../open-topics/archive/T0014-captured-spread-cost-calibration.md))

The design was: compare a depth-sensitive panel metric (`fill_bps` at a size whose fill walk passes rank 10) over matched clock-hours straddling 2026-07-14 04:00. The fix changed only in-memory reconstruction and the panel replays through the fixed book, so **no discontinuity should exist**; finding one would contradict this map and reopen [T0071].

**Run 2026-07-22, and it settles nothing.** Across all ten pairs `fill_bps@10k` moved **−17.2 %…+4.5 %** over the boundary (7/10 down). But the identical statistic at **seven non-event dates** gives −26.6…+17.3, −12.2…+22.2, −22.5…+8.6, −22.2…+55.2, −19.1…+51.2, −8.1…+12.1 and −24.2…+19.1, with 4–8 of 10 pairs down at every one — the real boundary is the *least* remarkable of the eight. Day-to-day drift at this window size swamps any effect the probe could detect, so **it has no discriminating power: it could not have refuted the map, and it does not corroborate it.**

This map's conclusion therefore rests **entirely on its mechanism argument** (the archive stores wire messages; every book-state product replays through the fixed book) — which is the strong evidence and always was. A probe with power would need a longer matched window, a trend control, and a size whose fill walk provably passes rank 10 on the pair being tested (€10k does so on only five of the ten). Worth building only if the mechanism argument is ever doubted.

## Physical excision: none

Nothing here warrants excision, reader-side or physical. The archives stay untouched — custody is immutable by convention, and T0050's byte-identity guarantees would be destroyed by deletion.
