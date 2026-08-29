---
status: partial
ripe_when: "a post-deploy family reaches an ADOPT verdict in `docs/reference/trial-registry.jsonl` — the first candidate that needs the ruled path. The shadow-alongside capability (running the candidate's contract beside the live record; no `builder_contract`/`contract_version` symbol in `cli/` today) is built then, against a real promotion."
---

# How a newly validated sleeve enters the live book

## Context — what

The deployable is registry record **47** (record 44 until 2026-08-16, re-ratified onto the twelve-leg basket at measured-identical metrics — the model is unchanged, only the traded basket and the record id moved): three fixed ⅓-weight sleeves built by a committed builder against a pinned contract, gated through Stage 6a's shadow concordance. Research continues after go-live (new Phase-4 sprints under the same registry, per §12's Ongoing regime) — but no document says what happens when a new family reaches ADOPT: a new record supersedes 44, the builder contract changes, sleeve weights are re-derived (Phase-5 assembly), and presumably the changed book must re-earn some concordance evidence before live capital runs on it. Undefined, that path either blocks research from ever reaching production or, worse, gets improvised around live capital.

## Why this matters

The stated goal of the whole 6b structure is that the live stack runs while research explores better alpha continuously. Without a promotion path the two halves never reconnect: an adopted family sits in the registry while the live book stays frozen at record 47 — or the promotion happens ad hoc, skipping exactly the gates (assembly, shadow parity, ramp) that made the deployable trustworthy.

## Findings so far

- The pieces all exist separately: Phase-5 assembly produced the deployable's weights; the builder-contract mechanism versions records; Stage 6a defined shadow concordance as the parity gate; the ramp defined criteria-gated capital steps. The promotion path is their composition for a *changed* book, plus the answer to how much shadow evidence a change needs (a full 14-day re-gate? proportional to the change?).
- §12 already forbids the alternative ("new research = new Phase 4 sprints under the same registry") — so promotion governance is an amendment-shaped decision — the same shape as [[T0116]]'s, which was ruled and landed in §12 on 2026-08-02.

## Done so far

**The path is ruled and landed (owner, 2026-08-29; iter-155).** Scoped by what a change TOUCHES rather than by a duration, because the four gates that made the deployable trustworthy each proved something different. Always: a new record via Phase-5 assembly, a builder-contract version bump, and shadow concordance re-earned on the new contract — no class exempt, since a new contract is new code on the path Stage 6a exists to prove.

**Parity is re-earned on cycles the new contract produces live** — the candidate runs disarmed beside the trading record, journaling its own cycles, and concordance is the ratified Stage-6a gate over that journal (the `1e-6` compare, ≥14 consecutive clean on-time days, unshortened, every class). Replay against the incumbent's journal cannot be the parity gate: `replay_stages` raises the moment rebuilt targets differ from the journaled ones, and that difference *is* the promotion. The 14 days cost no calendar — they nest inside the band window. **The band keeps its bar** — ≥3 consecutive complete ISO weeks, every class — because it is statistical and conditional on realized composition, which is precisely what a promotion changes.

**The band splits at cut-over, because only half of it is measurable before.** A shadow book has no fills and the go/no-go band is defined on realized return *with its fills*, so no shadow window can ever produce one — gating cut-over on a passing band would wait forever. The floor half (p95 per-cycle drift floor at the funded NAV, by `accum-replay`) is measurable from the shadow cycles and is quoted in the cut-over decision; the realized half re-accumulates after cut-over on the new record's own fills, ≥3 complete ISO weeks, with the tracking-error trip and the DD ladder armed. Cut-over re-enters at the class's rung — A at 50 % of funded NAV, B and C at rung 1's scale — and capital never steps up until the realized band clears. **A promotion must also beat the incumbent head-to-head**, not merely the registered bar.

Landed in `docs/research/00.master-plan.md` §12 under *Ongoing*, with the alternatives and their rejections in `docs/research/14.phase6-decisions.md` (iter-155).

## Proposed path

**Ratified 2026-08-29 and landed in §12. Kept here as the reasoning behind the amendment; §12 is the operative text.**

The gates that made the deployable trustworthy were four: Phase-5 assembly derived the weights, the builder contract pinned them, Stage 6a's concordance proved the live engine computes what the backtest computed, and 6b's rungs proved the book could actually be executed. A promotion re-earns *some* of those. Which ones is the whole question, and the answer is not a duration — it is **what the change touches**.

### Always, for any promotion

1. **A new registry record** via Phase-5 assembly, superseding the current deployable (33 → 43 → 44 → 47 is the existing precedent for the mechanics — and 43 is why the contract bump is a rule: its construction was recoverable only by a salvage from a workstation-local transcript, absorbed into maintained code as `cli/portfolio/record43_book.py` by [[T0148]], not by anything the record itself carried).
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

**The live book keeps trading its current record at its current rung; the candidate shadows beside it**, and capital moves only when the candidate's band clears. Stepping the live book down was considered and rejected: the go/no-go edge is the p95 of the per-cycle drift floor *at the funded NAV*, so a band measured at reduced capital validates a floor the book will not run at. Capital never steps *up* while a re-gate is open — a promotion re-proves the rung you are on, it does not advance the ladder.

### The two open questions, as ruled

- **Duration.** Parity is ≥14 consecutive clean on-time days of Stage-6a concordance over the candidate's OWN journal — the ratified gate, unshortened. It costs no calendar, because those days nest inside the band window. The tracking band keeps its full bar for every class: ≥3 consecutive complete ISO weeks, unweakened.
- **Capital during a class-A re-gate.** Shadow until cut-over, then re-enter at 50 % of funded NAV while the realized band accumulates, per *Capital* above.

## Suggested next steps

- **Build the shadow-alongside capability against the first real promotion.** The ruled path needs the candidate runnable beside the live record and scorable under its own contract; the engine selects neither today (the builder is imported directly). The shape — likely a second disarmed instance at the candidate's image digest, plus per-record builder dispatch in the scorer — is deliberately left to the promotion that first needs it, rather than pre-designed against no candidate. This is the only thing left.
