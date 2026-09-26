# Blockpit T1 memo — the Kraken depot's import scope and labelling, read 2026-09-25

**What this is.** The T1 check of master plan §11, written from the depot the owner connected and the extracts they took on 2026-09-25 after Rung 1's T2 probe: Blockpit's transaction export, its ledger-mode export, its 2026 Steuerbericht (report id `46d39725-6eaf-41d0-8d6d-91413180b4fe`) and Kraken's own ledger and trades statements for 2026-07-06 to 2026-09-25. The T2 verdict is the `[iter-172]` entry of `docs/research/14.phase6-decisions.md`; this memo records what the pipeline does, so the after-tax model and the monthly bookkeeping read one description of it.

## The connection

- The depot is Blockpit's own Kraken connector, granted through Kraken's OAuth login on 2026-07-09 — not the read-only API key of [[T0000]]; the grant offered no scope to check or uncheck. Kraken's connected-apps entry for Blockpit, read by the owner on 2026-09-25, lists view and export scopes only — the account balance, closed and open orders and trades, the ledger's view and export, the account information and a one-time API key for the session — and no order placement.
- Blockpit's integration page for Kraken still names no spot-margin scope. What it imports is the table below, measured.

## The import scope, measured

| Kraken ledger row | Blockpit transaction | How the Steuerbericht treats it |
| --- | --- | --- |
| `Deposit` | Non-Taxable In | Steuerfrei (Ein): a EUR lot at cost |
| `Trade Sell` EUR + `Trade Buy` asset (a spot buy) | Trade, keyed by the trade id | an acquisition; the buy fee is capitalised into the lot |
| `Trade Sell` asset + `Trade Buy` EUR (a spot disposal) | Trade | a §23 disposal: proceeds − fee − the FIFO lot's cost; the holding period in days |
| `Margin Trade`, amount 0, fee f (a position's open, or a close at zero PnL) | Margin Fee f | "Optional abzugsfähige Transaktionen", attached to no lot |
| `Margin Trade`, amount p, fee f (a close with PnL) | Margin Profit p with fee f | p under §23 as `Margin-Gewinn`, gross; f capitalised into the received EUR, where it never yields a gain |
| `Rollover`, fee f | Margin Fee | optional abzugsfähig, as above |
| `Margin Settle` EUR out + `Margin Settle` asset in | Trade EUR → asset, no fee | an acquisition at the settle's EUR debit; the holding period starts at the settle |
| `Collateral Conversion` EUR out + EURC in | not imported | EURC runs negative; the report books zero-gain lots labelled `Auto-Korrektur (Rundungsdifferenz)` |

Not observed in this window: a `Margin Loss`, a taker close, a position held across a year-end, a EURC balance carried across months.

## Labelling of the historical rows

- The six BTC/EUR spot round trips of July to September and the SOL/EUR pair of the 24th are Blockpit Trade pairs; every disposal names its lot (`von ID` / `zu ID`), and FIFO runs per integration (`Berechnungsart FIFO, Per Integration`).
- The UI's Tax Type filter offers only §23 EStG and §22 Nr. 3 EStG; §20 is read from the Steuerbericht's three §20 lines.
- A transaction's Tax tab shows Price, Value, Fee, Cost Basis, Proceeds, Gain/Loss and a Taxable flag; the ledger-mode export's `taxFigures` carries the same figures, so an export answers what the UI shows without a screenshot per row.

## What the after-tax model takes from this

- The treatment of record is §23 at the marginal rate for BOTH the margin PnL and the spot disposals — master plan §11's S-A; the go/no-go still holds under the worse of S-A and S-B, because the Steuerberater files, not Blockpit.
- A margin position settled in kind restarts the holding period at the settle; a margin position closed by an opposing order creates no lot at all.
- The trade fees of spot legs are inside the §23 figure. The margin open and rollover fees are outside it, an optional deduction the Steuerberater claims from the report's tax-free section. The close fee of a PnL-carrying margin close is in no summed figure until [[T0215]]'s transform splits it out — the model counts it as deductible only under T0215.
- Every margin open charged in EURC leaves its fee as phantom EUR in Blockpit until T0215's conversion rows land.

## The gaps, and where they are worked

- [[T0215]], the T3 fallback: the deterministic pre-transform of Kraken's exports — the conversion pairs, the fee split, and the whole ledger into Blockpit's manual-import CSV so the connector's depot can be replaced.
- Kraken's ledger CSV export carries full precision and the `refid`; the PDF statements round to four decimals and carry neither, so they are evidence, not input.
