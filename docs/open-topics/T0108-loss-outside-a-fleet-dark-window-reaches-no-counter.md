---
status: open
ripe_when: NOW for the measurement — the exposure is computable from the ledger and the raw mirrors already on disk. The DECISION it feeds (should a per-pair dual-silence book loss at all?) is ripe once that measurement exists, and not before
---

# Silence outside a fleet-dark window reaches no counter and no alert

## Context — what

Split out of [[T0103]] on 2026-07-28, found by an adversarial review of the counter work. Two classes of real primary silence now leave a ledger record but move **no counter and no alert**:

1. **`unwitnessed` gaps.** A pair whose primary went silent and whose secondary held no `update` row inside the window is ledgered `unwitnessed` and logged at WARNING, deliberately feeding no counter (`open-topics.md`-registered ruling: whenever the fleet was dark those seconds are already booked by `both_streams_silent`, and when it was not, one pair silent on both mirrors cannot be told from a quiet market). But that reasoning only holds **inside** a fleet-dark window. A single pair losing both mirrors while the rest of the fleet is healthy produces a record, a warning, and nothing else — `grep -rn unwitnessed infra/` returns zero hits, and only ERROR-level lines page.
2. **The remainder inside a real blackout.** Measured on 2026-07-27T07:00: of ADA/EUR's 208.566668 s unwitnessed window, **201.744967 s** is booked by the fleet record and **6.821701 s by nothing**.

## Why this matters

It is the *reassuring* direction again — the direction this whole family of topics exists to eliminate. The system now records the loss faithfully in the ledger while its counters under-report it, so an operator reading `zcrypto_reconcile_residual_gap_seconds_total` sees less loss than the archive actually took.

It is strictly better than what preceded it: before [[T0103]]'s work these windows produced **no record at all**. So this is an exposure to size and decide, not a regression to revert.

## Findings so far

- The `unwitnessed` state was added on PR #223 and carries no `residual_seconds` key at all — inert by construction rather than by value, which is deliberate and correct for what it is.
- The 6.821701 s figure is ADA/EUR's own dual-silence minus the fleet window it sits inside; the fleet record books each stream the silence window *containing* the intersection, and ADA's own window extends past it on both edges.
- The competing risk is real and is why this is not simply "book it": a per-pair dual-silence with no fleet-wide corroboration is indistinguishable from a thin market, and booking it would move a false positive into a monotone counter that drives the CRITICAL permanent-loss page. `containing_dark_window`'s docstring records the measured basis — across 2026-07-26, all 12 pairs, both mirrors, maximum natural silence was **11.44 s** and there were **zero** windows over the 30 s threshold.

## Suggested next steps

- *(autonomous, ripe NOW)* **Measure the exposure before deciding anything.** Sweep the reconcile ledger and the raw mirrors for every `unwitnessed` window ever recorded, and split them: seconds inside a `both_streams_silent` window (already booked) versus outside (booked nowhere). The answer decides whether this is worth a counter at all — a total of a few seconds is a footnote, minutes is a defect.
- *(decision, after that measurement)* Whether an `unwitnessed` window outside any fleet-dark window should book loss. Options: (a) leave it ledger-only and say so in the counter's HELP, (b) book it into a **separate** series so the CRITICAL page is unaffected while the loss is visible, (c) book it into `residual_gap_seconds_total` and accept thin-market false positives. (b) is the only one that surfaces the loss without touching the page's meaning.
- *(autonomous, small)* Whichever way that goes, `zcrypto_reconcile_residual_gap_seconds_total`'s HELP text should say plainly which classes of loss it does and does not count. It currently reads as though it counts all of them.
