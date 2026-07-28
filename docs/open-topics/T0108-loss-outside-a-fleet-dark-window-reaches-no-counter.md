---
status: open
ripe_when: the measurement was RUN 2026-07-28 and came back n=1 — see `## Done so far`. It is ripe again once the ledger holds `unwitnessed` records written by the post-fix reconciler (the ops image converged 2026-07-28 ~18:00Z; the single existing record predates it at 16:12:06Z and uses the superseded intersection×count arithmetic, so it is not representative). The DECISION it feeds stays blocked on that re-measurement
---

# Silence outside a fleet-dark window reaches no counter and no alert

## Context — what

Split out of [[T0103]] on 2026-07-28, found by an adversarial review of the counter work. Two classes of real primary silence now leave a ledger record but move **no counter and no alert**:

1. **`unwitnessed` gaps.** A pair whose primary went silent and whose secondary held no `update` row inside the window is ledgered `unwitnessed` and logged at WARNING, deliberately feeding no counter (`open-topics.md`-registered ruling: whenever the fleet was dark those seconds are already booked by `both_streams_silent`, and when it was not, one pair silent on both mirrors cannot be told from a quiet market). But that reasoning only holds **inside** a fleet-dark window. A single pair losing both mirrors while the rest of the fleet is healthy produces a record, a warning, and nothing else — `grep -rn unwitnessed infra/` returns zero hits, and only ERROR-level lines page.
2. **The remainder inside a real blackout.** Measured on 2026-07-27T07:00: of ADA/EUR's 208.566668 s unwitnessed window, **198.820666 s** is booked by the fleet record and **9.746002 s by nothing** — 4.6728%. (An earlier draft of this topic said 201.744967 s / 6.821701 s; that pair could not be reproduced against the ledger and is corrected here — see `## Done so far`.)

## Why this matters

It is the *reassuring* direction again — the direction this whole family of topics exists to eliminate. The system now records the loss faithfully in the ledger while its counters under-report it, so an operator reading `zcrypto_reconcile_residual_gap_seconds_total` sees less loss than the archive actually took.

It is strictly better than what preceded it: before [[T0103]]'s work these windows produced **no record at all**. So this is an exposure to size and decide, not a regression to revert.

## Findings so far

- The `unwitnessed` state was added on PR #223 and carries no `residual_seconds` key at all — inert by construction rather than by value, which is deliberate and correct for what it is.
- The unbooked figure is ADA/EUR's own dual-silence minus the fleet window it sits inside. The *containing-window* booking that an earlier draft assumed here is the *post-fix* behaviour — the record that actually exists predates it, so the subtraction is against the raw intersection.
- The competing risk is real and is why this is not simply "book it": a per-pair dual-silence with no fleet-wide corroboration is indistinguishable from a thin market, and booking it would move a false positive into a monotone counter that drives the CRITICAL permanent-loss page. `containing_dark_window`'s docstring records the measured basis — across 2026-07-26, all 12 pairs, both mirrors, maximum natural silence was **11.44 s** and there were **zero** windows over the 30 s threshold.

## Done so far

**The measurement ran 2026-07-28 against `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` (48 records). It does not answer the question, and why it doesn't is the finding.**

- **n = 1.** Exactly one `unwitnessed` record has ever been written — ADA/EUR, hour `2026-07-27T07:00`, one window of 208.566668 s. The state was introduced on PR #223 the day before, so the ledger carries roughly one day of label history that happens to contain one blackout. **A population of one cannot distinguish "a footnote" from "a defect"**, which was this measurement's whole purpose.
- **The split, measured**: the hour's `both_streams_silent` record holds a single window of 198.820666 s over 12 pairs, and ADA/EUR **is** among them. Overlap with the unwitnessed window is 198.820666 s, leaving **9.746002 s booked nowhere — 4.6728%**.
- **The existing record is unrepresentative.** Its `residual_seconds` is 2385.847992, which is 198.820666 × 12 to the microsecond — the superseded `intersection × count` arithmetic. It was written at 16:12:06Z, before the ops converge that shipped per-stream containing-window booking. Any exposure derived from it describes code no longer running.
- **This corrects the topic's own earlier numbers.** The 201.744967 s / 6.821701 s pair does not reproduce; it is consistent with post-fix containing-window booking, not with the record on disk. Recorded per `agent-ops.md`: a number is unmeasured until reproduced at full precision.
- **The trigger's premise was wrong.** This topic claimed the exposure was "computable from the ledger and the raw mirrors already on disk". The ledger's fleet record itemises `pairs` + `windows` + one aggregate `residual_seconds` — it does **not** record per-stream booked spans, so under post-fix booking the per-pair unbooked remainder is not derivable from the ledger at all. It needs the raw mirrors.

## Suggested next steps

- *(autonomous, once post-fix records exist)* **Re-run the measurement** over `unwitnessed` records written by the current reconciler. Because the ledger no longer suffices (see above), the per-pair booked span must come from the raw mirrors — schedule it clear of any panel regeneration, which saturates the same NFS reads.
- *(decision, after that measurement)* Whether an `unwitnessed` window outside any fleet-dark window should book loss. Options: (a) leave it ledger-only and say so in the counter's HELP, (b) book it into a **separate** series so the CRITICAL page is unaffected while the loss is visible, (c) book it into `residual_gap_seconds_total` and accept thin-market false positives. (b) is the only one that surfaces the loss without touching the page's meaning.
- *(autonomous, small)* Whichever way that goes, `zcrypto_reconcile_residual_gap_seconds_total`'s HELP text should say plainly which classes of loss it does and does not count. It currently reads as though it counts all of them.
