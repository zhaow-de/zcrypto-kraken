---
status: partial
ripe_when: "a date: 2026-11-02, the first window's due day (spec 00126 D9); check: `date -u +%F` reads 2026-11-02 or later"
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

## Done so far

- The transform: `zcrypto tax blockpit` (`cli/tax/`), spec `docs/specs/00126-blockpit-fallback-transform-design.md`, plan `docs/plans/00126-blockpit-fallback-transform.md`, pull request #684.
- The monthly procedure and its daily-pass reminder: `infra/runbooks/bookkeeping.md`.
- The tracking report reads the export's `earn` reward rows (spec 00126 D10).

## Suggested next steps

- **(human, from 2026-11-02)** The first window into a fresh depot, per spec 00126 D9: run steps 1 to 5 of `infra/runbooks/bookkeeping.md#kraken-monthly-bookkeeping` for the first window; then in Blockpit, Integrations → + Integration → Manual Integration, named `Kraken manual import`; then the page's steps 6 and 7 into it. At that upload, read whether the Blockpit Template tab took the `.csv` and whether Blockpit took the one-leg trade's `0` amount; a refusal of either stops the window for a change of its own, on which the owner rules again. Then re-read the five criteria on that integration: the Margin Profit and Loss rows and the spot disposals under §23 as `[iter-172]` read them; every margin and rollover fee in a summed figure, Blockpit's Margin Fee transactions summed per asset equal to the provenance's `Margin Fee` sums and the Steuerbericht's Margin-Gebühr total equal to those transactions' euro values as Blockpit values them, a EURC fee at its EURC price; FIFO lots intact; EURC never negative and no `Auto-Korrektur` lot; the disposal's gain off the settle's basis — read per integration with both present, then with the connector's integration hidden for the Steuerbericht's read, noting whether a hidden integration leaves the report. Record pass or fail beside `[iter-172]` in `docs/research/14.phase6-decisions.md` through the `iteration-closeout` skill; on a fail, unhide the connector's integration and keep it, delete nothing, and this item becomes the failing criterion's change.
- **(decision, once every criterion passes)** Whether the connector's integration is hidden for good or deleted — deletion cannot be undone and splits merged transfers back into unlabeled deposits and withdrawals.
