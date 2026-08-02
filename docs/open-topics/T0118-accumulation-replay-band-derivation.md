---
status: open
---

# Replay the accumulation policy over the 6a journal → the honest tracking band

## Context — what

Stage 6b's pre-registered go/no-go band (weekly |live−sim| ≤ 10 bps of sleeve NAV = €1/week at €1,000) is structurally unmeetable at tiny size: under the accumulation delta formula ([[T0119]]) each asset's live-vs-sim mismatch is bounded by ~`ordermin` (€30–80 across the active book), which exceeds the ~€54 the €1,000 book actually deploys. The honest band can be pre-derived offline: replay the accumulation policy over the existing 20-day 6a journal (read-only, data in hand) and measure the drift floor the venue minimums impose — that measured floor, not a round number, becomes the re-registered band in [[T0116]]'s amendment.

## Why this matters

A gate band that cannot be met measures Kraken's minimums, not our execution — the go/no-go would open on a criterion known in advance to fail, forcing either a false NO-GO or an ad-hoc waiver at exactly the moment the process must be mechanical. Deriving the band from replayed data before rung 3 keeps the gate pre-registered in substance, not just in form.

## Findings so far

- The bound argument (2026-07-30): an unplaced delta persists as a growing gap that places itself when it crosses `ordermin`, so per-asset drift oscillates in `[0, ~ordermin)`; the book-level floor is the sum over active assets of the expected resting gap, which the replay measures directly rather than estimates.
- Inputs in hand: the 20-day journal (NAS replica), per-pair `ordermin`/`costmin` from the snapshot register (stamped 2026-07-07 — [[T0113]]'s sweep refreshes it before the figure is quoted at the gate).
- The replay is policy-only (no fills modeled beyond full-fill-at-mid); slippage/fees stay the cost model's job — this measures the *placement* floor alone.

## Suggested next steps

- **(autonomous)** Implement the replay: journaled targets → accumulation deltas → place-when-≥`ordermin` → per-asset and book-level |live−sim| series over the 20 days.
- **(autonomous)** Report the drift floor (median / p95 weekly) at €1,000 and at the ramp sizes (25/50/100 % of $10k), so the band re-derivation covers the whole ramp, not just rung 3's entry.
- **(autonomous)** Hand the measured floor to [[T0116]] as the band parameter; sensitivity-check it against [[T0117]]'s gross answer (a 3× larger book shrinks the relative floor 3×).
