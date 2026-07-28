---
status: partial
ripe_when: the sweep RAN 2026-07-28 and returned n=1. The two figures below are both valid and answer different questions, so nothing waits on re-deriving them. Ripe NOW: the same split over any FURTHER `unwitnessed` records, which is a pure ledger read wherever the matching fleet record carries `stream_windows`. The DECISION stays blocked on a population larger than one
---

# Silence outside a fleet-dark window reaches no counter and no alert

## Context — what

Split out of [[T0103]] on 2026-07-28, found by an adversarial review of the counter work. Two classes of real primary silence now leave a ledger record but move **no counter and no alert**:

1. **`unwitnessed` gaps.** A pair whose primary went silent and whose secondary held no `update` row inside the window is ledgered `unwitnessed` and logged at WARNING, deliberately feeding no counter (`open-topics.md`-registered ruling: whenever the fleet was dark those seconds are already booked by `both_streams_silent`, and when it was not, one pair silent on both mirrors cannot be told from a quiet market). But that reasoning only holds **inside** a fleet-dark window. A single pair losing both mirrors while the rest of the fleet is healthy produces a record, a warning, and nothing else — `grep -rn unwitnessed infra/` returns zero hits, and only ERROR-level lines page.
2. **The remainder inside a real blackout.** Measured on 2026-07-27T07:00: ADA/EUR's `unwitnessed` window is 208.566668 s and the fleet-dark window it sits inside is 198.820666 s. **No exposure figure is derived from that pair here** — see `## Done so far`: the two records were written by different code generations a day apart, so the difference is not a measurement of anything.

## Why this matters

It is the *reassuring* direction again — the direction this whole family of topics exists to eliminate. The system now records the loss faithfully in the ledger while its counters under-report it, so an operator reading `zcrypto_reconcile_residual_gap_seconds_total` sees less loss than the archive actually took.

It is strictly better than what preceded it: before [[T0103]]'s work these windows produced **no record at all**. So this is an exposure to size and decide, not a regression to revert.

## Findings so far

- The `unwitnessed` state was added on PR #223 and carries no `residual_seconds` key at all — inert by construction rather than by value, which is deliberate and correct for what it is.
- **Two figures, both valid, answering different questions** — an earlier revision of this file wrongly withdrew them both. **9.746002 s** is what the booking that actually ran left unbooked for ADA/EUR in that hour (its 208.566668 s dark window minus the 198.820666 s the fleet record booked it). **6.821701 s**, carried in [[T0103]], is what current containing-window booking *would* leave. History versus forward exposure; the decision this topic feeds wants the second.
- The competing risk is real and is why this is not simply "book it": a per-pair dual-silence with no fleet-wide corroboration is indistinguishable from a thin market, and booking it would move a false positive into a monotone counter that drives the CRITICAL permanent-loss page. `containing_dark_window`'s docstring records the measured basis — across 2026-07-26, all 12 pairs, both mirrors, maximum natural silence was **11.44 s** and there were **zero** windows over the 30 s threshold.

## Done so far

**The measurement ran 2026-07-28 against `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` (48 records). It does not answer the question, and why it doesn't is the finding.**

- **n = 1, and it counts RECORDS, not events.** Exactly one `unwitnessed` record has ever been written — ADA/EUR, hour `2026-07-27T07:00`, one window of 208.566668 s, spanning `07:01:04.071744` → `07:04:32.638412`; the fleet-dark window is `07:01:04.071744` → `07:04:22.892410`, so it sits wholly inside and containment is recorded rather than inferred from durations. The state was introduced on PR #223 the day before, and [[T0103]] records that already-minted hours inside the 48 h window get no retrospective record — so pre-deploy events are **structurally** absent, not merely rare. A population of one cannot distinguish "a footnote" from "a defect", which was this measurement's whole purpose.
- **The split, as far as it goes.** The hour's `both_streams_silent` record holds a single window of 198.820666 s over 12 pairs, ADA/EUR among them, and the `unwitnessed` window is 208.566668 s (`07:01:04.071744` → `07:04:32.638412`, containing the fleet window `07:01:04.071744` → `07:04:22.892410`, so containment is recorded rather than inferred). The naive difference is 9.746002 s. **That number is withdrawn** for the provenance reason below; it is kept here only so a future reader recognises it.
- **Provenance, settled by schema — and reproducible from this repo alone.** `unwitnessed` records (`38f4e100`) and the `stream_windows` key (`ad0f84b4`) both reached `develop` in **PR #223** and are both ancestors of the converged revision `50fc4979`, so **no binary can write an `unwitnessed` record without also writing `stream_windows`**. The `unwitnessed` record therefore post-dates #223; the 2026-07-27T07:00 fleet record has keys `pairs`/`residual_seconds`/`windows` and no `stream_windows`, so it pre-dates it. Two generations, established without reference to any timestamp. Earlier revisions of this section argued it from the clock — first getting the direction backwards by reading the `unwitnessed` record's `at` as the fleet record's, then citing second-level times that exist only in an untracked file.
- **[[T0103]] needs no correction.** Its 201.744967 s / 6.821701 s pair is a recomputation under the code as landed, not a ledger read, so the pre-fix provenance of this hour's fleet record does not touch it. An earlier revision here called that pair irreproducible, then withdrew it; both were wrong.
- **The trigger's premise was wrong, but not in the way this file last said.** It claimed the exposure was "computable from the ledger and the raw mirrors already on disk". For a **post-fix** record it is computable from the ledger *alone* — `stream_windows` records exactly what each stream was booked, so the remainder is `gaps_unwitnessed` minus that. It is only this **pre-fix** record, which lacks the field, that cannot be settled from the ledger. So the raw mirrors are needed for the historical case, not the general one.

## Suggested next steps

- *(autonomous, ripe NOW)* **Re-measure over records that share a code generation.** Select `unwitnessed` records whose matching `both_streams_silent` record carries `stream_windows`; for those the split is a ledger read with no mirror access at all. Only records predating that field need the raw mirrors, and those should be reported separately rather than mixed in.
- *(decision, after that measurement)* Whether an `unwitnessed` window outside any fleet-dark window should book loss. Options: (a) leave it ledger-only and say so in the counter's HELP, (b) book it into a **separate** series so the CRITICAL page is unaffected while the loss is visible, (c) book it into `residual_gap_seconds_total` and accept thin-market false positives. (b) is the only one that surfaces the loss without touching the page's meaning.
- *(autonomous, small)* Whichever way that goes, `zcrypto_reconcile_residual_gap_seconds_total`'s HELP text should say plainly which classes of loss it does and does not count. It currently reads as though it counts all of them.
