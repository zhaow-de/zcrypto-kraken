---
status: open
ripe_when: "the owner ratifies or amends the change-class table in `## Proposed path` — drafted 2026-08-29, so this is gated on a decision, not an event. Deployment sets when the path is first USED, never when it can be written."
---

# How a newly validated sleeve enters the live book

## Context — what

The deployable is registry record **47** (record 44 until 2026-08-16, re-ratified onto the twelve-leg basket at measured-identical metrics — the model is unchanged, only the traded basket and the record id moved): three fixed ⅓-weight sleeves built by a committed builder against a pinned contract, gated through Stage 6a's shadow concordance. Research continues after go-live (new Phase-4 sprints under the same registry, per §12's Ongoing regime) — but no document says what happens when a new family reaches ADOPT: a new record supersedes 44, the builder contract changes, sleeve weights are re-derived (Phase-5 assembly), and presumably the changed book must re-earn some concordance evidence before live capital runs on it. Undefined, that path either blocks research from ever reaching production or, worse, gets improvised around live capital.

## Why this matters

The stated goal of the whole 6b structure is that the live stack runs while research explores better alpha continuously. Without a promotion path the two halves never reconnect: an adopted family sits in the registry while the live book stays frozen at record 47 — or the promotion happens ad hoc, skipping exactly the gates (assembly, shadow parity, ramp) that made the deployable trustworthy.

## Findings so far

- The pieces all exist separately: Phase-5 assembly produced the deployable's weights; the builder-contract mechanism versions records; Stage 6a defined shadow concordance as the parity gate; the ramp defined criteria-gated capital steps. The promotion path is their composition for a *changed* book, plus the answer to how much shadow evidence a change needs (a full 14-day re-gate? proportional to the change?).
- §12 already forbids the alternative ("new research = new Phase 4 sprints under the same registry") — so promotion governance is an amendment-shaped decision — the same shape as [[T0116]]'s, which was ruled and landed in §12 on 2026-08-02.

## Proposed path

**Status: a draft awaiting the owner's ruling. Nothing here is ratified, and none of it has been landed in §12.**

The gates that made the deployable trustworthy were four: Phase-5 assembly derived the weights, the builder contract pinned them, Stage 6a's concordance proved the live engine computes what the backtest computed, and 6b's rungs proved the book could actually be executed. A promotion re-earns *some* of those. Which ones is the whole question, and the answer is not a duration — it is **what the change touches**.

### Always, for any promotion

1. **A new registry record** via Phase-5 assembly, superseding the current deployable (33 → 44 → 47 is the existing precedent for the mechanics).
2. **A builder-contract version bump.** The contract is what makes a record reproducible; a changed book with an unchanged contract is a record that cannot be rebuilt.
3. **Shadow concordance re-earned on the NEW contract.** This is the non-negotiable one. 6a's parity check proves the *live* engine computes what the *backtest* computed; a new contract is new code on that path, so parity is unproven by construction until re-measured. No change class exempts it.

### Scoped by what the change touches

| class | the change | re-entry beyond parity |
| --- | --- | --- |
| **A** | weights only — same legs, same builder code path | none: parity + the tracking band |
| **B** | new or changed legs / instruments | + rung 1 (plumbing: the order path, fills, fees, rollover and tax rows are unproven for an instrument never traded) |
| **C** | changed execution semantics — sides, order types, cadence, skip-or-carry | + rungs 1 and 2 (the operational loop itself changed) |

**The class is declared and ratified BEFORE the evidence is gathered**, exactly as a trial is pre-registered. Declared afterwards it becomes a post-hoc argument for the least work, which is the failure this table exists to prevent.

### Capital

The ramp re-enters at the class's floor and **capital never steps up while a re-gate is open**. A promotion is not a reason to advance the ladder; it is a reason to re-prove the rung you are on.

### What the owner must rule

- **The durations.** How many weeks of parity for each class, and how many complete ISO weeks of tracking-band evidence before capital resumes stepping. The go/no-go's `≥3 consecutive complete ISO weeks` is the natural anchor for class A, but whether a promotion earns the same bar as first go-live is a judgement about how much a changed book is trusted, not something measurable from here.
- **Whether class A may run at full capital during its re-gate**, or must step down first.

## Suggested next steps

- **(owner)** Rule on `## Proposed path` — the change-class table, the durations, and whether class A steps down during its re-gate. On ratification it lands as a §12 amendment plus a decision-register entry.
- **(autonomous, after the ruling)** Land the amendment and the register entry; nothing else in this topic is blocked.
