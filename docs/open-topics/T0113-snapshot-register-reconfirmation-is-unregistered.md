---
status: open
ripe_when: monthly from 2026-08-07 (the register's fetch stamp + 1 month), and unconditionally before the go/no-go — whichever comes first. The trigger is readable from the register itself: `docs/research/01.1.kraken-snapshot-register.md`'s `**Fetched at:**` line versus today
---

# The master plan's go-live re-confirmation sweep is mandated in prose and registered nowhere

## Context — what

`docs/research/00.master-plan.md` marks a set of externally-owned facts with ⏱ and states they "must be reconfirmed at Phase 0 and again at go-live": fees and fee tiers, borrow/rollover rates, tradeable pair lists, MiCA/regulatory status, tax rules, and market-data pricing. Phase 0 did that — `docs/research/01.1.kraken-snapshot-register.md` carries **`Fetched at: 2026-07-07T03:29:00+00:00`**.

Nothing registers the second half. The obligation exists only as plan prose, and `.claude/rules/open-topics.md` is explicit that prose is not registration: a deferred action is only tracked if it lives in a topic. Surfaced by the 2026-07-30 Phase-6a completion audit.

## Why this matters

Every one of these facts is owned by a third party and can move without notice, and each one feeds a number the go/no-go decision rests on:

- **Fees and tier** are the single largest term in the cost model — the deployable record's Sharpe already moves ±30–40 % on execution style alone ([[T0090]]), and a tier change moves it again.
- **Borrow/rollover rates** price every margin-short leg.
- **Pair lists** decide whether the selected universe is still tradeable at all.
- **MiCA/regulatory status and tax rules** can change what is permissible or reportable, which is not a number that can be corrected after the fact.

A stale register does not announce itself. The failure mode is quiet: the go/no-go is taken against figures that were true in July, and nothing in the pipeline objects.

## Findings so far

- The register's own stamp is the measurable trigger — `Fetched at: 2026-07-07T03:29:00+00:00` — so staleness is readable without instrumenting anything.
- The plan states the obligation in three places (the ⏱ convention note, and again in the Phase-6 and go-live material); none of them is a tracked item.
- The only topic that ever named the register is resolved and archived (`archive/T0000`), which is why the second sweep has no home today.
- This is registration, not new research: the sweep itself is a re-fetch of known sources into an existing document shape.

## Suggested next steps

- *(autonomous, monthly)* Re-fetch the ⏱ facts and update `01.1.kraken-snapshot-register.md`, bumping its `Fetched at:` stamp. Record any DELTA against the previous fetch explicitly — an unchanged sweep must still move the stamp, or the next reader cannot tell "re-confirmed and identical" from "never re-run".
- *(autonomous)* When a delta touches fees or borrow rates, say plainly which downstream numbers it invalidates ([[T0090]]'s cost basis, the deployable's quoted Sharpe) rather than leaving the reader to work it out.
- *(attended, at the go/no-go)* The final pre-live sweep is a precondition of the decision, not a follow-up to it — it runs as a step in [[T0049]]'s go-live runbook, where the monthly routine is recorded.
