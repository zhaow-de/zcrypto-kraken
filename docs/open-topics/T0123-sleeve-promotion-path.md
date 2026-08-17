---
status: open
ripe_when: a post-deploy alpha family reaches an ADOPT verdict in the trial registry — the first candidate that would actually need to enter the live book (until then there is nothing to promote and the design would be against zero examples)
---

# How a newly validated sleeve enters the live book

## Context — what

The deployable is registry record **47** (record 44 until 2026-08-16, re-ratified onto the twelve-leg basket at measured-identical metrics — the model is unchanged, only the traded basket and the record id moved): three fixed ⅓-weight sleeves built by a committed builder against a pinned contract, gated through Stage 6a's shadow concordance. Research continues after go-live (new Phase-4 sprints under the same registry, per §12's Ongoing regime) — but no document says what happens when a new family reaches ADOPT: a new record supersedes 44, the builder contract changes, sleeve weights are re-derived (Phase-5 assembly), and presumably the changed book must re-earn some concordance evidence before live capital runs on it. Undefined, that path either blocks research from ever reaching production or, worse, gets improvised around live capital.

## Why this matters

The stated goal of the whole 6b structure is that the live stack runs while research explores better alpha continuously. Without a promotion path the two halves never reconnect: an adopted family sits in the registry while the live book stays frozen at record 44 — or the promotion happens ad hoc, skipping exactly the gates (assembly, shadow parity, ramp) that made record 44 trustworthy.

## Findings so far

- The pieces all exist separately: Phase-5 assembly produced record 44's weights; the builder-contract mechanism versions records; Stage 6a defined shadow concordance as the parity gate; the ramp defined criteria-gated capital steps. The promotion path is their composition for a *changed* book, plus the answer to how much shadow evidence a change needs (a full 14-day re-gate? proportional to the change?).
- §12 already forbids the alternative ("new research = new Phase 4 sprints under the same registry") — so promotion governance is an amendment-shaped decision, likely a sibling of [[T0116]]'s when it fires.

## Suggested next steps

- **(autonomous drafting + decision)** When the trigger fires: define the path — new record via Phase-5 assembly, builder-contract version bump, shadow re-gate scope (**the re-gate duration/criteria are the owner's ruling**), ramp re-entry point — and land it as a §12 amendment + decision-register entry the owner ratifies.
- Until then: nothing, deliberately. Registered so the question is visible at the moment it becomes real, not designed against zero examples.
