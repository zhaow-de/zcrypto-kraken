---
status: open
ripe_when: 'a milestone: rung 3''s go/no-go decided, `engine-rung-3` step 9; check: `grep -c -E "rung 3.s go/no-go.*\(Decision: [0-9]+\)" docs/research/14.phase6-decisions.md` prints at least 1 — the decision entry in the log''s own shape, where the bare phrase already has hits'
---

# engine-procedures.md without the one-time rungs

## Context — what

`infra/runbooks/engine-procedures.md` carries two sections that are one-time activities, not procedures: `engine-rung-2-box` (the October 2026 box) and `engine-rung-3` (the accumulation that follows it). Once rung 3's go/no-go is decided both are history, and the runbook keeps only the procedures an operator still runs.

## Why this matters

The owner's word of 2026-10-12: "as a post-rung-3 activity, revise engine-procedures because in a runbook it shouldn't have the history/records for the one-time activitities like rung-2 and rung-3 at all. it should be a document for "when/how to do what by whom"". A step of an ended activity left in a runbook reads as a live instruction.

## Findings so far

The box's records are in `docs/reference/rung2-box/` (PR #693) and rung 3's go to `docs/reference/rung3/`; the entry values, decisions and deviations are in `docs/research/14.phase6-decisions.md`. Each directory's README defers what an entry carries to its runbook section, so that definition moves into the README before the section goes.

## Suggested next steps

- Read `engine-rung-2-box` and `engine-rung-3` whole and sort each step into one of three: a standing procedure an operator still needs (moves into a procedure section of its own, named by when it is run), a one-time instruction, or a record — the last two dropped, their content already where Findings names.
- Re-point each link into the sections to where its step moved — `git grep -n -E 'engine-rung-[23]|rung-[23]-[a-z]' -- docs/reference docs/open-topics infra/runbooks .claude tests cli` lists them; `tests/test_infra_alert_rules.py::test_every_runbook_cross_reference_resolves` and `tests/test_engine_draftplan.py` read the anchors.
- Land the removal and the moved procedures as separate commits, so the review reads what was kept apart from what went.
