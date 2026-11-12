---
status: open
ripe_when: 'a milestone: rung 3''s first attended week closes; check: `git log --oneline origin/develop --merges --grep=records/rung3-week-1` prints a line'
---

# The venue record's EUR is not Kraken's free EUR

## Context — what

The engine refuses a margin intent whose margin floor exceeds `free_zeur`, and it reads `free_zeur` from the venue state's `balances` (`cli/engine/command.py:2192`, `cli/engine/executor.py:2772`, checked at `cli/engine/probeplan.py:223`). Under rung 3 that figure is not Kraken's free EUR: the venue record's `state.balances.EUR` stood still across rung 3's fills and stepped at drill G's restart, while every `accum` record's `eur_free` tracked Kraken's. The figures are `docs/reference/rung3/days.md`'s entry for 2026-11-12, which reaches `develop` with the week's records.

## Why this matters

The figure overstates free cash by about the value of the coins held, so a margin intent can pass the engine's floor check and then be refused by Kraken. Rung 3's loop is spot-only today; the check matters the first time a plan carries a margin intent.

## Findings so far

- Inferred, not proven: the adapter seeds the balance at start from Kraken's equivalent balance, and spot fills do not move it. A restart re-seeds it, which fits the step at drill G's restart.

## Suggested next steps

- Read where the venue state's `balances` is filled. Confirm or refute the seeding inference against the adapter's account state over one restart and one spot fill.
- Point the margin check at the figure the `accum` records read, or at Kraken's free balance read at the check. Add a test in which a spot fill moves the free EUR the check sees.
- Ride the image that carries T0226's, T0227's and T0229's fixes.
