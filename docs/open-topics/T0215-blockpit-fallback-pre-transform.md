---
status: open
ripe_when: "a milestone: rung 2 is entered, its time box fixed (master plan §12); check: `docs/research/14.phase6-decisions.md` carries the entry"
---

# The Blockpit T3 fallback: a deterministic pre-transform of Kraken's exports into the manual-import CSV

## Context — what

Rung 1's T2 probe failed two of Step 7's five criteria (`[iter-172]` in `docs/research/14.phase6-decisions.md`; the measured import table in `docs/reference/blockpit-t1-memo.md`): Blockpit's Kraken connector drops the `Collateral Conversion` pairs Kraken books to charge a margin open's fee in EURC, so EURC runs negative and EUR reads high; and a margin close with PnL arrives as one row whose fee Blockpit capitalises into the received EUR, where it never reaches a summed figure. Master plan §11's T3 is the fallback for exactly this: a deterministic, unit-tested pre-transform that maps Kraken's ledger and trades exports into Blockpit's manual-import CSV with explicit margin rows, run monthly as part of the bookkeeping.

## Why this matters

At rung 3 every PnL-carrying close loses its fee from the deductible sums and every EURC-charged open leaves its fee as phantom EUR (`[iter-172]` sizes both). The ramp past 25 % of the sleeve requires the T2 pass or this fallback deployed (master plan §12).

## Findings so far

- The mapping Blockpit applies to every Kraken row type this window produced is the table in `docs/reference/blockpit-t1-memo.md`; the transform reproduces it row for row and changes two shapes: a conversion pair becomes a Trade EUR → EURC at the pair's amounts, and a `margin` row with a non-zero amount becomes a Margin Profit (or Loss) at the amount plus a separate Margin Fee row at its fee.
- The input is a spec decision: Kraken's ledger CSV (full precision, `refid`) or the read-only key of [[T0000]]; the PDFs are neither.
- In the ledger CSV a position's opening `margin` row, its `collateralconversion` pair and its `rollover` rows carry `refid` = the opening trade id, while a close's `margin` row and a settle's `settled` pair carry an id of their own, so the ledger alone does not link a close to its open; the types are `deposit`, `margin`, `rollover`, `settled`, `collateralconversion`, and `trade` with subtype `tradespot` for a spot leg.
- Blockpit computes FIFO per integration, so a manual-import depot that replaces the connector's must carry the whole history from the 2026-07-10 deposit, not the rows from the switch on; whether the connector's depot is removed or the manual one supplements it is the spec's first decision.

## Suggested next steps

- **(autonomous, at the trigger)** Spec and plan under a new serial: the CSV template Blockpit's help centre publishes for manual import, read at build time; the row mapping above; the input and the depot decision (replace or supplement); the transform as a `zcrypto` subcommand, unit-tested on a fixture, its output content-hashed beside its input.
- **(human)** Import the transform's CSV into a fresh Blockpit depot and re-read the five criteria against Kraken's ledger; record pass or fail in the decisions log beside `[iter-172]`.
- **(decision)** Whether the connector's depot is deactivated once the manual depot reconciles.
