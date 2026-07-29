---
status: resolved
---

# Silence outside a fleet-dark window reaches no counter and no alert

## Context — what

Split out of [[T0103]] on 2026-07-28, found by an adversarial review of the counter work. Two classes of real primary silence now leave a ledger record but move **no counter and no alert**:

1. **`unwitnessed` gaps.** A pair whose primary went silent and whose secondary held no `update` row inside the window is ledgered `unwitnessed` and logged at WARNING, deliberately feeding no counter (`open-topics.md`-registered ruling: whenever the fleet was dark those seconds are already booked by `both_streams_silent`, and when it was not, one pair silent on both mirrors cannot be told from a quiet market). But that reasoning only holds **inside** a fleet-dark window. A single pair losing both mirrors while the rest of the fleet is healthy produces a record, a warning, and nothing else — `grep -rn unwitnessed infra/` returns zero hits, and only ERROR-level lines page.
2. **The remainder inside a real blackout.** Measured on 2026-07-27T07:00: ADA/EUR's `unwitnessed` window is 208.566668 s, and the fleet record booked it 198.820666 s — leaving seconds that reached no counter — **6.821701 s** under the booking that current code applies; see `## Resolution`, which settles which figure applies. See `## Done so far` for why subtracting these two is legitimate even though they were written by different code generations.

## Why this matters

It is the *reassuring* direction again — the direction this whole family of topics exists to eliminate. The system now records the loss faithfully in the ledger while its counters under-report it, so an operator reading `zcrypto_reconcile_residual_gap_seconds_total` sees less loss than the archive actually took.

It is strictly better than what preceded it: before [[T0103]]'s work these windows produced **no record at all**. So this is an exposure to size and decide, not a regression to revert.

## Findings so far

- The `unwitnessed` state was added on PR #223 and carries no `residual_seconds` key at all — inert by construction rather than by value, which is deliberate and correct for what it is.
- **Two figures, both valid, answering different questions** — an earlier revision withdrew them both, which was over-correction. **9.746002 s** is what the booking that actually ran left unbooked for ADA/EUR in that hour. **6.821701 s**, carried in [[T0103]], is what current containing-window booking *would* leave. History versus forward exposure; the decision this topic feeds wants the second.
- The competing risk is real and is why this is not simply "book it": a per-pair dual-silence with no fleet-wide corroboration is indistinguishable from a thin market, and booking it would move a false positive into a monotone counter that drives the CRITICAL permanent-loss page. `containing_dark_window`'s docstring records the measured basis — across 2026-07-26, all 12 pairs, both mirrors, maximum natural silence was **11.44 s** and there were **zero** windows over the 30 s threshold.

## Done so far

**The measurement ran 2026-07-28 against `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` (48 records). It does not answer the question, and why it doesn't is the finding.**

- **n = 1, and it counts RECORDS, not events.** Exactly one `unwitnessed` record has ever been written — ADA/EUR, hour `2026-07-27T07:00`, one window of 208.566668 s, spanning `07:01:04.071744` → `07:04:32.638412`; the fleet-dark window is `07:01:04.071744` → `07:04:22.892410`, so it sits wholly inside and containment is recorded rather than inferred from durations. The state was introduced on PR #223 the day before, and [[T0103]] records that already-minted hours inside the 48 h window get no retrospective record — so pre-deploy events are **structurally** absent, not merely rare. A population of one cannot distinguish "a footnote" from "a defect", which was this measurement's whole purpose.
- **The split.** The hour's `both_streams_silent` record holds a single window of 198.820666 s over 12 pairs, ADA/EUR among them, and the `unwitnessed` window is 208.566668 s (`07:01:04.071744` → `07:04:32.638412`, containing the fleet window `07:01:04.071744` → `07:04:22.892410`, so containment is recorded rather than inferred). Difference: **9.746002 s** booked by nothing.
- **Provenance, settled by schema — and reproducible from this repo alone.** `unwitnessed` records (`38f4e100`) and the `stream_windows` key (`ad0f84b4`) both reached `develop` in **PR #223** and are both ancestors of the converged revision `50fc4979`, so **no binary can write an `unwitnessed` record without also writing `stream_windows`**. The `unwitnessed` record therefore post-dates #223; the 2026-07-27T07:00 fleet record has keys `pairs`/`residual_seconds`/`windows` and no `stream_windows`, so it pre-dates it. Two generations, established without reference to any timestamp. Earlier revisions of this section argued it from the clock — first getting the direction backwards by reading the `unwitnessed` record's `at` as the fleet record's, then citing second-level times that exist only in an untracked file.
- **Why subtracting across the two generations is nonetheless sound.** They measure different kinds of thing. `gaps_unwitnessed` is derived from the raw mirror stamps — where the primary was silent and the secondary held no `update` row — so it measures the outage itself, and no booking-policy change alters it. The fleet record's window is a *booking decision*. Subtracting a booking from a measurement of reality is legitimate; what would not be is subtracting two booking outputs whose definitions changed between them, which is what an earlier revision of this file mistook this for.
- **[[T0103]] needs no correction.** Its 201.744967 s / 6.821701 s pair is a recomputation under the code as landed, not a ledger read, so the pre-fix provenance of this hour's fleet record does not touch it. An earlier revision here called that pair irreproducible, then withdrew it; both were wrong.
- **The trigger's premise was wrong, but not in the way this file last said.** It claimed the exposure was "computable from the ledger and the raw mirrors already on disk". For a **post-fix** record it is computable from the ledger *alone* — `stream_windows` records exactly what each stream was booked, so the remainder is `gaps_unwitnessed` minus that. It is only this **pre-fix** record, which lacks the field, that cannot be settled from the ledger. So the raw mirrors are needed for the historical case, not the general one.

## Resolution

**Measured 2026-07-29, decided (a): leave it ledger-only and say so in the counter's HELP.**

A `--detect-only` reconcile over a 400 h window — the full overlap of both mirrors, the secondary's history beginning 2026-07-14 — run with the post-fix code, so every `both_streams_silent` record it produced carries `stream_windows` and the split is a pure ledger read with no mirror access:

| | |
| --- | --- |
| unwitnessed events in ~15 days | **1** |
| ADA/EUR 2026-07-27T07:00, unwitnessed window | 208.566668 s |
| booked by the fleet-wide record | 201.744967 s |
| **reaching no counter** | **6.821701 s (3.2708%)** |

**Deciding on n=1 is defensible here, and this file's earlier objection to it needs answering rather than ignoring.** The objection was that one record cannot separate a footnote from a defect. What settles it is not the count but the bound: the sweep covered ~15 days of BOTH mirrors and found one event, whose entire unbooked remainder is 6.821701 s, with zero instances of the isolated-pair class the topic feared most. A defect would have to hide in a population that produced one 6.8-second miss in a fortnight.

**Six point eight seconds in fifteen days is a footnote, not a defect** — which is the question this topic existed to settle. Booking it would move a thin-market false positive into the monotone counter that drives the CRITICAL permanent-loss page, for an exposure three orders of magnitude below the gap the page already reports.

**This also settles the 9.746002 vs 6.821701 dispute this file went back and forth on twice.** Both were correct for their own code generation: 9.746002 s subtracts the raw intersection a pre-fix fleet record booked; 6.821701 s subtracts the containing window current code books, and matches [[T0103]]'s independently derived figure exactly. The live answer is 6.821701 s, and T0103 needed no correction.

`zcrypto_reconcile_residual_gap_seconds_total`'s HELP now states plainly that it does not count the `unwitnessed` state, that those seconds reach no counter at all, that the number is therefore **a floor on permanent loss rather than the whole of it**, and what the measured exposure was.

**A caveat that belongs with the number**: this ran today's code over historical data, so it measures what current booking *would* classify — the right basis for a forward-looking decision, the wrong one for reconstructing what was booked at the time. Reading it the other way is what produced the two earlier contradictory figures.

**A scare that was not real**: the raw sweep ledger showed 47 of 48 keys duplicated exactly twice, including a counter-bearing record. That was two of my own concurrent sweep processes writing one scratch ledger, not the reconciler double-ledgering. Production was never involved. The exactness of the duplication was the tell.

## Suggested next steps

*(All discharged — see `## Resolution`, which decided **(a)**. Retained so the archived file shows the options that were weighed; the recommendation below is superseded.)*

- ~~Measure the exposure before deciding anything~~ — done: 1 event in ~15 days, 6.821701 s reaching no counter.
- ~~Decide whether an unwitnessed window outside a fleet-dark window should book loss~~ — **decided (a)**: leave it ledger-only. The earlier note preferring (b), a separate series, was written before the exposure was known; at 6.8 s in 15 days a new series is not worth the surface.
- ~~State plainly in the counter's HELP which classes of loss it does and does not count~~ — done; it now says it is a floor, not the whole.
