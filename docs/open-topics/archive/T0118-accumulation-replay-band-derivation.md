---
status: resolved
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

## Resolution

**Resolved 2026-08-02 by spec `00081`** (`docs/specs/00081-6b-feeder-measurements-design.md`), commits `6ef95da9` (per-cycle stage extraction), `ed657f11` (`accumulation_payload` — the accumulate-until-placeable simulation), `5dbb0974` (`zcrypto engine accum-replay`). Measured over **136 journaled cycles, 2026-07-11 → 2026-08-02**, on the NAS journal replica. All three sub-items close.

**Venue minimums stamp — read this before quoting any number below.** The `ordermin`/`costmin` figures driving every row come from `data/snapshots/kraken-refdata-20260707T032900Z.json`, **`fetched_at 2026-07-07T03:29:00+00:00`**. Kraken owns these values and moves them without notice, so a band quoted at the go/no-go from this table without re-checking the stamp is exactly the silent-staleness failure [[T0113]] exists to prevent. The command prints the stamp beside the table for the same reason.

**The drift floor as a function of NAV** (per cycle, bps of NAV; `placed` counts the cycles in which at least one order cleared both floors, out of 136):

| NAV | cycles that placed | median | p95 |
| --- | --- | --- | --- |
| €500 | 14/136 | **147.0** | 209.2 |
| €1,000 | 29/136 | **51.2** | 115.7 |
| €2,500 | 40/136 | **11.6** | 30.9 |
| €5,000 | 50/136 | **6.2** | 14.2 |
| €10,000 | 64/136 | **4.3** | 8.9 |

**Weekly means** (bps of NAV, in the same NAV order 500 / 1,000 / 2,500 / 5,000 / 10,000):

| ISO week | cycles | 500 | 1,000 | 2,500 | 5,000 | 10,000 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-W28 | 12 (partial) | 180.1 | 94.5 | 8.7 | 6.9 | 4.3 |
| 2026-W29 | 42 | 138.6 | 50.3 | 12.1 | 5.8 | 3.6 |
| 2026-W30 | 42 | 165.6 | 68.0 | 19.2 | 9.7 | 5.8 |
| 2026-W31 | 40 (partial) | 125.7 | 32.4 | 7.2 | 4.8 | 4.2 |

**No weekly p95 is reported, deliberately.** The window is exactly four ISO weeks, two of them partial; a p95 over four points is the maximum wearing a percentile's name, and this number is destined for a live-trading gate band. The per-cycle median and p95 over all 136 points are what carry statistical weight, and both are in the table above.

**The pre-registered band is confirmed structurally unmeetable at rung 3's size, now with numbers instead of an argument.** Against `weekly |live − sim| ≤ 10 bps of NAV`, at €1,000 the floor Kraken's minimums impose is **5.1× the band at the median and 11.6× at p95**. The gate would measure the venue, not our execution, exactly as this topic claimed. The band only becomes meetable at **€5,000 (median 6.2 bps)** and **€10,000 (p95 8.9 bps)** — the far end of §12's ramp, not the tiny-live size the stage specifies. That is the whole finding: 10 bps is not a wrong number, it is a number that presupposes a book roughly an order of magnitude larger than rung 3's.

**Sensitivity against [[T0117]]: no correction is owed.** This topic's third sub-item asked for a check against the gross answer on the reasoning that a 3× larger book would shrink the relative floor ~3×. T0117 measured that there is **no** hidden larger book — the ~5 % gross is fully accounted (32.2 % A2 sleeve gross ÷ 3 fixed weights × 0.5 governor = 5.371 %), with no residual — and this replay consumed the very same journaled `final_targets` T0117 decomposed. The floor above is therefore already the floor of the real book at each NAV, not a figure awaiting a scale correction.

**Scope, unchanged from the spec.** Policy-only: full fill at the journaled close, no slippage, fees or partial fills — those stay the cost model's job, and modelling them here would make the floor read as a cost estimate, which it is not. Held state is carried in **base units**, not EUR, because `ordermin` is natively a quantity and a EUR-denominated held state would compare a price-stale "held" against a freshly priced "target". NAV is held constant across the window on purpose, so the number is pure venue-minimum and carries no P&L.

**Handed to [[T0116]]** in this same change, together with the re-derivation trigger: the floor is derived from **shadow** targets, so if rung 1/2 execution changes the target series materially the band wants re-deriving before rung 3's gate reads it.
