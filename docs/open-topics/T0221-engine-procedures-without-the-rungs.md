---
status: open
ripe_when: 'a milestone: rung 3 retired — `engine-rung-3`''s *Retire when*, the boundary no longer drafting the book; check: `grep -c _draft_cycle_plan cli/engine/executor.py` prints 0'
---

# engine-procedures.md without the one-time rungs

## Context — what

`infra/runbooks/engine-procedures.md` carries two sections that are one-time activities, not procedures: `engine-rung-2-box` (the October 2026 box) and `engine-rung-3` (the accumulation that follows it), each with its entry, its daily and weekly steps, its stops and its retirement. Once rung 3 is retired the two sections are history, and the runbook is revised to hold only what an operator does when something fires: when and how to do what, and by whom.

## Why this matters

The owner's word of 2026-10-12: "as a post-rung-3 activity, revise engine-procedures because in a runbook it shouldn't have the history/records for the one-time activities like rung-2 and rung-3 at all. it should be a document for 'when/how to do what by whom'." A runbook a paged operator opens is read under time; two long sections about activities that have ended cost that reader every page they scroll past, and a stale step in them reads as a live instruction.

## Findings so far

The box's records moved into the tree under `docs/reference/rung2-box/` (PR #693) and rung 3's are to follow under `docs/reference/rung3/` (this topic's registering PR), each directory's README declaring the record; what the two runbook sections hold beyond their procedures — the entry values, the decisions, the deviations — is already recorded there and in `docs/research/14.phase6-decisions.md`.

## Suggested next steps

- Read `engine-rung-2-box` and `engine-rung-3` whole and sort each step into one of three: a standing procedure an operator still needs (moves into a procedure section of its own, named by what fires it), a one-time instruction (dropped, its outcome already in the records), or a record (dropped, already in `docs/reference/rung2-box/`, `docs/reference/rung3/` or the decisions log).
- Keep every anchor another page links to — `git grep -n 'engine-rung-2-box\|engine-rung-3\|rung-3-pause\|rung-3-re-birth' -- docs infra/runbooks .claude tests` lists them — by re-pointing each link to the section its step moved into, and run `tests/test_guidance_refs_resolve.py` and `tests/test_runbook_internal_tokens.py` after.
- Land the revision in one PR under the ordinary read, with the two sections' removal and the moved procedures in separate commits so the review can read what was kept apart from what went.
