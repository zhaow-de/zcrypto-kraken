---
status: partial
status stays `partial` because the routine recurs — ripe_when: monthly from 2026-09-04 (sweep #1's stamp + 1 month), and unconditionally before the go/no-go — whichever comes first. The trigger is readable from the register itself: `docs/reference/kraken-snapshot-register.md`'s `**Fetched at:**` line versus today
---

# The master plan's go-live re-confirmation sweep is mandated in prose and registered nowhere

## Context — what

`docs/research/00.master-plan.md` marks a set of externally-owned facts with ⏱ and states they "must be reconfirmed at Phase 0 and again at go-live": fees and fee tiers, borrow/rollover rates, tradeable pair lists, MiCA/regulatory status, tax rules, and market-data pricing. Phase 0 did that — `docs/reference/kraken-snapshot-register.md` carries **`Fetched at: 2026-07-07T03:29:00+00:00`**.

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


## Done so far

- **The routine is registered and its first sweep has run — sweep #1, 2026-08-04** (`docs/reference/kraken-snapshot-register.md`). The register's header now always carries the latest sweep, and a **re-confirmation log** table records each one with its own timestamp, response counts, raw hash and verdict — which is the mechanism this topic existed to create: "re-confirmed, identical" is now distinguishable from "never re-run" by reading one table.
- **Sweep #1's verdict: UNCHANGED.** All twelve §3 candidates still online and margin-enabled, identical leverage bands, `ordermin`, `costmin` and aliases — re-rendered through the same `cli/snapshot/` code and diffed cell-by-cell. Independently re-derived at review, including a fresh live fetch ~61 minutes later that also matched.
- **A changed raw hash is not a changed fact, and the register now says so.** Kraken's full response moved (1509 → 1429 pairs, 809 → 824 assets) while our basket held; review computed the actual set difference from both archived snapshots — **13 pairs added / 93 removed, 15 assets added / 0 removed** — and confirmed none of the twelve candidates or their assets appear in any changed set. The verdict is therefore read from the rendered table, never the hash; treating hash churn as fact churn would raise a false alarm every month.

## Suggested next steps

- *(autonomous, monthly — the recurring routine, next due ~2026-09-04)* Re-fetch and update the register, adding a row to its re-confirmation log. An unchanged sweep still moves the stamp.
- *(autonomous, newly surfaced at sweep #1's review)* **The register tracks less than `AssetPairs` carries, and some of what it omits moves.** `derive_universe` extracts status, margin flag, leverage bands, `ordermin` and `costmin` — but **not** the public per-pair **`fees`/`fees_maker` volume-tier schedule**, `margin_rate`, `margin_call`/`margin_stop`, or the position limits. Review measured `margin_rate` on **AVAX** and `short_position_limit` on **four pairs** changing inside a 61-minute window, invisible to both the rendered table and the hash-is-noise convention. This matters disproportionately because **fees are the largest term in the cost model** ([[T0090]]) and the topic's own rationale rests on catching exactly that class of drift — while the register currently defers "the fee tier" to the account-gated section, which is a different thing from the *public* schedule it could be tracking today. Decide whether to extend the extraction (and therefore the table and the diff) before relying on another "UNCHANGED" verdict to mean *nothing we depend on moved*.
- *(autonomous)* When a delta touches fees or borrow rates, say plainly which downstream numbers it invalidates ([[T0090]]'s cost basis, the deployable's quoted Sharpe) rather than leaving the reader to work it out.
- *(attended, at the go/no-go)* The final pre-live sweep is a precondition of the decision, not a follow-up to it — it runs as a step in [[T0049]]'s go-live runbook, where the monthly routine is recorded.
