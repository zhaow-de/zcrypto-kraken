---
status: resolved
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

## Resolution

**Resolved 2026-08-04 — the routine has a home, a trigger and a procedure, and every deferral it
carried has been re-homed rather than archived with it.** The topic's complaint was never that the
sweep was hard; it was that a mandated recurring routine lived only as plan prose, so nothing would
run it. That is now false in four separate places:

- **The procedure** is the `zcrypto-refdata-sweep` skill — fetch, diff the rendered tables, update
  the register's re-confirmation log, and state what any delta invalidates. It leads with the rule
  that makes a verdict meaningful (read the tables, never `raw_sha256`) because Kraken's response
  churns on nearly every sweep.
- **The trigger** is a scheduled Slack reminder in `#zcrypto` (2026-09-04, ID `Dr0BMU0AS44V`) — the
  same mechanism `T0103`/`T0105` use, chosen because a `ripe_when:` date is read by nobody at the
  moment it fires. Re-arming next month's is step 4 of the runbook procedure, since a scheduled
  message fires once.
- **The runbook section** `refdata-sweep-due` gives that signal its procedure, which is also what
  makes it legitimate under the runbook's own scope rule rather than a backlog entry smuggled in.
- **The artifact moved** to `docs/reference/kraken-snapshot-register.md` — it is a living
  cross-phase reference re-measured on a schedule, not a phase-0 research output.

**Sweep #1 ran and its verdict is UNCHANGED**: all twelve §3 candidates still online and
margin-enabled, identical leverage bands, `ordermin`, `costmin` and aliases — re-rendered through the
same code and diffed cell-by-cell, then independently re-derived at review including a fresh live
fetch an hour later. Kraken's own universe churned underneath (13 pairs added, 93 removed, 15 assets
added) without touching the basket.

**The extraction gap this topic's review surfaced is closed, not deferred.** `derive_universe` now
also captures the public fee ladders, `margin_call`/`margin_stop`, position limits, and — the one
that mattered — per-asset **`margin_rate`**, which *is* the borrow/rollover rate the master plan
names as externally owned and which the register had never captured despite it being public all
along.

**One correction belongs in the record, because it nearly became a false finding.** Reading the
public fee ladder, I concluded `CrossfreqSystemConfig.fee_per_side = 0.0040` was mislabelled
"tier-1 MAKER". It is not: the **public endpoint was still serving the pre-2026-07-09 schedule**, a
month after it was superseded, and under the schedule actually in force 0.40 % *is* tier-1 maker.
`docs/reference/kraken-fee-schedule.md` — captured from the logged-in account during `T0000` — owns
the fee level; the register's fee columns are a **drift detector on the endpoint** and are labelled
as such in both files and in the skill.

**Where the two deferrals went**, so neither is lost with this file:

- **The monthly cadence** → the skill + the runbook item + the Slack reminder above. Not a topic:
  there is no open question, the tool exists, the protocol is written and the schedule is armed.
- **The final pre-go/no-go sweep** → a sub-item of [[T0085]], where it belongs — that run is an
  *input to the decision*, so it lives beside the decision rather than in a monthly cadence.
- **The account fee tier's own re-read**, which had lost its trigger when `T0000` was archived → the
  attended half of the same monthly sweep, recorded in the register's log as confirmed, corrected,
  or *not re-read* — never inherited.
