---
status: open
ripe_when: "rung 2's first ISO week of fills is in Kraken's ledger — the transform's second fixture, carrying the shapes rung 1 never produced (a margin close at a loss, a taker close); check: Kraken → History → Export → Ledgers over that week lists a `margin` row with a negative amount"
---

# The Blockpit T3 fallback: a deterministic pre-transform of Kraken's exports into the manual-import CSV

## Context — what

Rung 1's T2 probe failed two of Step 7's five criteria (`[iter-172]` in `docs/research/14.phase6-decisions.md`; the measured import table in `docs/reference/blockpit-t1-memo.md`): Blockpit's Kraken connector drops the `Collateral Conversion` pairs Kraken books to charge a margin open's fee in EURC, so EURC runs negative and EUR reads high; and a margin close with PnL arrives as one row whose fee Blockpit capitalises into the received EUR, where it never reaches a summed figure. Master plan §11's T3 is the fallback for exactly this: a deterministic, unit-tested pre-transform that maps Kraken's ledger and trades exports into Blockpit's manual-import CSV with explicit margin rows, run monthly as part of the bookkeeping.

## Why this matters

At rung 1's size the money is nil — the fictional EURC lots sit within 0.0001 of the truth and the lost fee is 0.0795 EUR. At rung 3 every PnL-carrying close loses its 40 bps of notional from the deductible sums and every EURC-charged open leaves 42 bps as phantom EUR, and a depot that no longer reconciles to the venue is what §11's probe existed to catch. The ramp past 25 % of the sleeve requires the T2 pass or this fallback deployed (master plan §12).

## Findings so far

- The mapping Blockpit applies to every Kraken row type this window produced is the table in `docs/reference/blockpit-t1-memo.md`; the transform reproduces it row for row and changes two shapes: a conversion pair becomes a Trade EUR → EURC at the pair's amounts, and a `margin` row with a non-zero amount becomes a Margin Profit (or Loss) at the amount plus a separate Margin Fee row at its fee.
- The bucket needs no judgment call: Blockpit's own framework puts a close under §23 and treats a settlement as an acquisition, so §11's escalation clause does not fire.
- The transform's input is the venue's CSV export (History → Export, Ledgers and Trades), keyed by `refid`; the PDF statements round to four decimals and carry no `refid`.
- Blockpit computes FIFO per integration, so a manual-import depot that replaces the connector's must carry the whole history from the 2026-07-10 deposit, not the rows from the switch on; whether the connector's depot is removed or the manual one supplements it is the spec's first decision.

## Suggested next steps

- **(human)** Export Kraken's Ledgers and Trades as CSV for 2026-07-06 to 2026-09-25 and place them with the monthly bookkeeping archive; they are the transform's first fixture and the tracking reader's input for §6 item 3 of the probe-window procedure.
- **(autonomous, at the trigger)** Spec and plan under a new serial: the CSV template Blockpit's help centre publishes for manual import, read at build time; the row mapping above; the depot decision (replace or supplement); the transform as a `zcrypto` subcommand over the two CSV exports, unit-tested on the fixture, its output content-hashed beside the exports.
- **(human)** Import the transform's CSV into a fresh Blockpit depot and re-read the five criteria against Kraken's ledger; record pass or fail in the decisions log beside `[iter-172]`.
- **(decision)** Whether the connector's depot is deactivated once the manual depot reconciles.
