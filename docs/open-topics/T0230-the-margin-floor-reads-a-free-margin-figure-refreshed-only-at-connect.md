---
status: open
ripe_when: 'a milestone: rung 3''s first attended week closes; check: `git log --oneline origin/develop --merges --grep=records/rung3-week-1` prints a line'
---

# The margin floor reads a free-margin figure refreshed only at connect

## Context — what

The engine refuses a plan whose margin floor exceeds `free_zeur` (`cli/engine/probeplan.py:223`), read from the venue state's `balances` (`cli/engine/command.py:2192`, `cli/engine/executor.py:2772`). That `EUR` row is Kraken's TradeBalance account summary in EUR from the MARGIN account (`cli/engine/node.py:561-562`, filled at `cli/engine/venuestate.py:126`): free margin, with the coins counted as collateral. Under rung 3 it stood still across the fills and stepped only at drill G's restart, so it is refreshed only when the engine connects. The figures are in `docs/reference/rung3/days.md`'s entry for 2026-11-12, which reaches `develop` with the week's records.

## Why this matters

1. **The figure goes stale between connects.** The floor is checked against free margin as it stood at the last connect, so a plan can pass on margin Kraken no longer has, or be refused on margin it does have.
2. **The spec's wording is not the decided basis.** The owner's decision of 2026-09-23 (`docs/research/14.phase6-decisions.md:841`) names free margin the right measure for `free_zeur`, as the code has it, while spec 00090 still writes the floor as `sum(notional_i / leverage_i) × 2.5 ≤ free ZEUR balance` (`docs/specs/00090-rung-1-order-path-design.md:68`); no test pins the basis.

Rung 3's loop is spot-only, so neither gap has bitten yet. Both matter the first time a plan carries a margin intent.

## Findings so far

_(none)_

## Suggested next steps

- Bring spec 00090's floor wording to free margin, as the decision of 2026-09-23 has it, and pin the basis with a test.
- Read free margin at the check rather than at connect. Add a test in which a fill between connects moves the figure the check sees.
- Ship the fix on the image that carries T0226's, T0227's and T0229's fixes.
