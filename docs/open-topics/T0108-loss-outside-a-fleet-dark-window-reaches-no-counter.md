---
status: partial
ripe_when: the measurement RAN 2026-07-28 and returned n=1 — see `## Done so far`. Two things are ripe NOW and neither waits on new records: settling which booking basis applied to ADA/EUR in that hour (the ledger and [[T0103]] disagree, 9.746002 s vs 6.821701 s), which needs the raw mirrors and should be scheduled clear of any panel regeneration; and the HELP-text clarification. The DECISION stays blocked on a population larger than one
---

# Silence outside a fleet-dark window reaches no counter and no alert

## Context — what

Split out of [[T0103]] on 2026-07-28, found by an adversarial review of the counter work. Two classes of real primary silence now leave a ledger record but move **no counter and no alert**:

1. **`unwitnessed` gaps.** A pair whose primary went silent and whose secondary held no `update` row inside the window is ledgered `unwitnessed` and logged at WARNING, deliberately feeding no counter (`open-topics.md`-registered ruling: whenever the fleet was dark those seconds are already booked by `both_streams_silent`, and when it was not, one pair silent on both mirrors cannot be told from a quiet market). But that reasoning only holds **inside** a fleet-dark window. A single pair losing both mirrors while the rest of the fleet is healthy produces a record, a warning, and nothing else — `grep -rn unwitnessed infra/` returns zero hits, and only ERROR-level lines page.
2. **The remainder inside a real blackout.** Measured on 2026-07-27T07:00: of ADA/EUR's 208.566668 s unwitnessed window, **198.820666 s** is booked by the fleet record and **9.746002 s by nothing** — 4.6728%. (This is the **ledger** basis. [[T0103]] carries 201.744967 s / 6.821701 s, the **containing-window** basis, re-measured there under the code as landed. Both reproduce from their own basis; they disagree, and `## Done so far` records what settles it.)

## Why this matters

It is the *reassuring* direction again — the direction this whole family of topics exists to eliminate. The system now records the loss faithfully in the ledger while its counters under-report it, so an operator reading `zcrypto_reconcile_residual_gap_seconds_total` sees less loss than the archive actually took.

It is strictly better than what preceded it: before [[T0103]]'s work these windows produced **no record at all**. So this is an exposure to size and decide, not a regression to revert.

## Findings so far

- The `unwitnessed` state was added on PR #223 and carries no `residual_seconds` key at all — inert by construction rather than by value, which is deliberate and correct for what it is.
- The unbooked figure is ADA/EUR's own dual-silence minus the fleet window it sits inside. The *containing-window* booking that an earlier draft assumed here is the *post-fix* behaviour — the record that actually exists predates it, so the subtraction is against the raw intersection.
- The competing risk is real and is why this is not simply "book it": a per-pair dual-silence with no fleet-wide corroboration is indistinguishable from a thin market, and booking it would move a false positive into a monotone counter that drives the CRITICAL permanent-loss page. `containing_dark_window`'s docstring records the measured basis — across 2026-07-26, all 12 pairs, both mirrors, maximum natural silence was **11.44 s** and there were **zero** windows over the 30 s threshold.

## Done so far

**The measurement ran 2026-07-28 against `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` (48 records). It does not answer the question, and why it doesn't is the finding.**

- **n = 1, and it counts RECORDS, not events.** Exactly one `unwitnessed` record has ever been written — ADA/EUR, hour `2026-07-27T07:00`, one window of 208.566668 s, spanning `07:01:04.071744` → `07:04:32.638412`; the fleet-dark window is `07:01:04.071744` → `07:04:22.892410`, so it sits wholly inside and containment is recorded rather than inferred from durations. The state was introduced on PR #223 the day before, and [[T0103]] records that already-minted hours inside the 48 h window get no retrospective record — so pre-deploy events are **structurally** absent, not merely rare. A population of one cannot distinguish "a footnote" from "a defect", which was this measurement's whole purpose.
- **The split, measured**: the hour's `both_streams_silent` record holds a single window of 198.820666 s over 12 pairs, and ADA/EUR **is** among them. Overlap with the unwitnessed window is 198.820666 s, leaving **9.746002 s booked nowhere — 4.6728%**.
- **The record is POST-fix, not pre-fix — an earlier version of this section had the timeline backwards.** It claimed the ops converge was "~18:00Z" so the 16:12:06Z record predated it. `docs/reference/fleet-pins.md`, on this same branch, records the converge as **15:58:39 → 15:59:07Z**, and the per-stream containing-window commit is an ancestor of the converged revision. The record was written **13 minutes after** the converge, by a binary that already had the fix. The `residual_seconds = 198.820666 × 12` exactness therefore is **not** evidence of superseded arithmetic: `cli/archive/command.py`'s fleet-dark block falls back to the raw intersection whenever `both_mirrors` is false or a stream has no stamps, which reproduces `intersection × count` under the current code. So the measurement below describes the code that is running.
- **Two bases, not a wrong number — and this file previously said otherwise.** The 201.744967 s / 6.821701 s pair is live in [[T0103]], re-measured there under the code as landed on ADA/EUR's **containing-window** share. It reproduces from that basis; it simply cannot be derived from the ledger, whose fleet record carries no per-stream booked spans. The ledger basis gives 198.820666 s booked / 9.746002 s unbooked. **The two disagree and one measurement settles it** — which booking the reconciler actually applied for ADA/EUR in that hour. Until then every figure here carries its basis, and [[T0103]] carries the other half of the story.
- **The trigger's premise was wrong.** This topic claimed the exposure was "computable from the ledger and the raw mirrors already on disk". The ledger's fleet record itemises `pairs` + `windows` + one aggregate `residual_seconds` and records **no per-stream booked spans**, so the per-pair unbooked remainder is not derivable from it. The raw mirrors are required.

## Suggested next steps

- *(autonomous, once post-fix records exist)* **Re-run the measurement** over `unwitnessed` records written by the current reconciler. Because the ledger no longer suffices (see above), the per-pair booked span must come from the raw mirrors — schedule it clear of any panel regeneration, which saturates the same NFS reads.
- *(decision, after that measurement)* Whether an `unwitnessed` window outside any fleet-dark window should book loss. Options: (a) leave it ledger-only and say so in the counter's HELP, (b) book it into a **separate** series so the CRITICAL page is unaffected while the loss is visible, (c) book it into `residual_gap_seconds_total` and accept thin-market false positives. (b) is the only one that surfaces the loss without touching the page's meaning.
- *(autonomous, small)* Whichever way that goes, `zcrypto_reconcile_residual_gap_seconds_total`'s HELP text should say plainly which classes of loss it does and does not count. It currently reads as though it counts all of them.
