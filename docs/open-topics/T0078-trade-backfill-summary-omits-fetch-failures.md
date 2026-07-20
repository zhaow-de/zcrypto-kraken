---
status: open
ripe_when: ripe NOW — a ~5-line fix plus a README correction, fully specified below; it is registered rather than fixed inline only to keep the archive-audit PR focused, so take it as the next small change rather than carrying it
---

# The trade-backfill run summary omits fetch failures, and the README promises it cannot

## Context — what

`cli/trades/backfill.py` accumulates `pair_fetch_error_missing` as a **per-pair local** (assigned ~line 155, accumulated ~line 162). It never reaches `BackfillResult` (~lines 43-54) and never reaches the run-level completion summary (~lines 240-253). It surfaces in exactly one place: the D9 invariant-violation message (~lines 230-232) — i.e. **only once the invariant has already failed.**

A repo-wide grep finds the identifier in three places: those two code sites and the archived [[T0053]] file. Nothing else covers it.

## Why this matters

**`README.md:209` documents the summary as listing "every outcome bucket a fetched or existing row can land in", and asserts that "a run can never read as clean by omitting one." That guarantee is false today** — a fetch-failed gap's missing ids land in no printed bucket. This is the same defect class as the rest of this audit's findings: an artifact asserting something that is not so.

It matters operationally, not just documentarily. The backfill step runs daily on the ops node (`infra/ansible/roles/ops/templates/archive-pull.sh.j2:145-176`), and [[T0053]]'s own fix **deleted the retry**, so `zcrypto_trade_backfill_exit_code` is the sole signal a failed pass emits. That makes this summary the operator's first diagnostic when the critical alert fires — and it is the one number missing from it.

Severity is genuinely low, for two reasons worth recording so nobody over-reacts: the per-gap warning at ~lines 159-161 prints pair/`after_id`/`before_id`, so the count is manually derivable from the journal (un-totalled, not absent), and the D9 invariant subtracts the bucket, so there are no false "clean" invariant passes. The damage is to triage speed, not to data integrity — the raw mirrors are untouched.

## Findings so far

Found by the 2026-07-20 archived-topic audit. The history shows this was **known and dropped, not out of scope**:

- The sibling defect ("report what the detector FOUND, not only what was healed") was fixed first, in `7e145cf`.
- [[T0053]] was opened *after* it, in `d3d0112`, explicitly citing "same defect class as the found-vs-healed split".
- [[T0053]]'s headline fix landed in `69dfbd6`, touching no reporting code.
- `3c6ec30` archived the topic with this accounting finding still sitting in its `## Findings so far` — never promoted to next steps, never handed to a successor.

[[T0053]] itself stays archived: its headline concern is genuinely fixed, and this is a distinct residual rather than a reopening.

## Suggested next steps

- **(Autonomous, ~5 lines)** Add a run-level `trades_fetch_failed` accumulator beside the existing counters (~line 112), add the field to `BackfillResult` (~lines 43-54), and thread it into the summary format string and args (~lines 240-253).
- **(Autonomous)** Correct `README.md:209` — the "every outcome bucket / can never read as clean by omitting one" sentence becomes true only once the fix lands. Land both together so the document and the behaviour never disagree.
- **(Autonomous)** Extend `tests/test_trades_backfill.py:249-256` and `tests/test_trades_command.py:77` to cover a fetch-failed gap, so the summary arithmetic is pinned by a test rather than by prose. Mutation-check it: remove the new field from the summary and confirm a test fails.
- **Do NOT fold this into [[T0043]].** That topic's headline is loss-event attribution in `settle.py`; burying a summary-arithmetic fix there would repeat exactly the mis-filing this audit exists to catch.
- Trivial-change path per `.claude/rules/spec-plan-locations.md`: branch off `develop`, TDD, subagent review, PR into `develop` — no committed spec/plan, no iterations-history entry.
