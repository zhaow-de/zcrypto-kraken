---
status: open
---

# The deployable is operating as a one-sleeve book, and no document says so

## Context — what

Registry record 44 — the system Stage 6b would take live — is **three sleeves combined at fixed ⅓ weights**: B (record 33's daily `w·l3`, intraday-held), A1 (A1-lf weekly v0.12 offset-mean), and A2 (the equal-weight native-4h ensemble). Measured across all **136** journaled shadow cycles (2026-07-11 → 2026-08-02, spec `00081`'s attribution run): **B and A1 hold exactly zero in every cycle.** Only A2 carries exposure.

This is not a defect. Both sleeves were live for much of the backtest — B non-zero on **51.4 %** of its 28,079 rows, A1 on **57.0 %** — and each went flat and stayed flat: B last held a position around **2025-10-30**, A1 around **2025-11-09**. B sits behind a 200-day SMA gate that `13.phase5-holdout-ledger.md` already records as *"off since before April"*; these are long-only sleeves correctly sitting out a sustained downtrend.

What no document records is the **compound consequence**: because the combination is fixed ⅓ weights, a single live sleeve contributes one third of its own gross, and the governor then halves that. The book that would go live is structurally a **one-sleeve book at ⅙ of that sleeve's gross**, not the diversified three-sleeve system whose Sharpe, drawdown and stress figures were registered.

## Why this matters

Three consequences, none of which the go/no-go currently sees:

- **The validated object and the operating object differ in structure, not just in parameters.** Record 44's registered figures (net-of-cost Sharpe 1.5609, maxDD 13.57 %, the ×1.5/×2 stress results, the SPA grid) were earned by a three-sleeve combination. A one-sleeve realization has different risk characteristics, and record 44's diversification thesis — the reason ⅓/⅓/⅓ was adopted over a single sleeve — is dormant in exactly the regime the sleeve would go live in.
- **It is the mechanism behind the placeability problem**, which was previously attributed only to sizing. The chain measured per cycle: A2 alone at **32.2 %** median gross → ÷3 by the fixed weights → **10.7 %** combined → position caps bind on **0 of 136** cycles → ×0.5 governor → **5.37 %** final. That ~5 % is why 0 of 801 intended orders cleared Kraken's minimums at tiny-live size ([[T0116]]).
- **Nothing observes it.** No metric, alert, or report states how many sleeves are contributing. The condition arrived ~9 months ago and was found only because a measurement iteration happened to decompose the book; it could equally reverse — B and A1 re-arming would roughly triple gross without anything announcing that either.

## Findings so far

- Measured 2026-08-02 by `zcrypto engine decompose` over the full journal (spec `00081`): sleeve→combined ratio **1.000** on every cycle — trivially, because two of three sleeves are zero, so there is nothing to cancel. The iteration's own spec had predicted sleeve *disagreement* as the likely mechanism; that hypothesis is refuted, and the real answer is dormancy.
- Per-sleeve backtest occupancy and last-non-zero rows above are from `build_crossfreq_system_fast` on the newest journaled cycle's snapshots (28,079 rows).
- Both known pieces were already recorded separately — the 200-day gate being off (holdout ledger) and the governor entering live at ×0.5 ([[T0018]]). Neither document draws the consequence for the live book's composition, and A1's dormancy is recorded nowhere.
- The governor's ×0.5 is itself carried from the 2025 drawdown, so two independent regime facts are compounding.

## Suggested next steps

- **(decision)** The owner's call, and the reason this is registered rather than folded into a measurement topic: **is a one-sleeve book what rung 3 should go live on?** Options include proceeding knowingly (recording the divergence in the go/no-go), waiting for sleeve re-arming, or re-deriving the deployable's expected figures for the realized composition. This is a go/no-go input, not a research question.
- **(autonomous)** Add sleeve occupancy to the engine's observability — a per-sleeve gross gauge or an active-sleeve count — so the condition is visible and its reversal is announced. Fold into [[T0018]]'s metrics work rather than opening a separate build; the families it would join do not exist yet.
- **(autonomous)** Quantify what the registered figures become under a one-sleeve realization, so the decision above is taken against numbers rather than against the structural argument alone. This is a re-read of an existing verdict, not a new trial.
