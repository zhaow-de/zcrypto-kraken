---
status: open
---

# Three of §10's four whole-book limits have no caller

## Context — what

`apply_gross_leverage_cap`, `apply_net_exposure_band`, and `apply_margin_floor` are implemented and tested — and called by nothing outside their own test file. Only `apply_position_caps` is wired into the live target pipeline. Verified 2026-07-30 in the capability audit: the §10 risk layer that the master plan treats as standing between the book and a margin blow-up exists as dead code for three of its four limits.

## Why this matters

Stage 6b's rungs put real capital under the book for the first time; the ramp (25 → 50 → 100 % of $10k) multiplies whatever the limits do not cap. A margin floor that is implemented-and-tested-but-unwired reads as "we have a margin floor" in every design document while enforcing nothing — the worst shape of gap, invisible until the day it is needed. Wiring must land before rung 3 puts full weights on.

## Findings so far

- The wiring point is a design decision, not a mechanical edit: the limits compose (position caps → whole-book caps → governor?) and the order of application changes the result — e.g. a gross-leverage cap applied before vs after the governor multiplier caps different books. The composition order needs the owner's ruling, then a pinned test.
- Shadow-mode neutrality is checkable: on the 20-day journal the long-only ~5 % gross book should pass all three limits untouched, so wiring them must be verdict-neutral on the replay ([[T0117]]'s decomposition rebuild is the natural harness to prove it on).

## Suggested next steps

- **(decision)** Owner ruling: which of the three wire in for 6b, and the composition order relative to position caps and the governor.
- **(autonomous, after the ruling)** Wire them at the ruled point; prove verdict-neutrality on the journal replay (all 120 cycles' final targets bit-identical — the limits must not bind on the shadow book, only guard the live one).
- **(autonomous)** Add the limit-breach events to the order/PnL metrics families so a binding limit is a visible event, not a silent clamp.
