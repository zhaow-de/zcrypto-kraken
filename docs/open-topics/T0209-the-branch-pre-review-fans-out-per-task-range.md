---
status: open
ripe_when: 'the next spec and plan pair with four or more tasks reaches its hand-off to subagent-driven development at the Exit of `zcrypto-plan-review` — an activity the session at that Exit reads; the trigger is the branch it is about to execute, not a repo path'
---

# The branch pre-review fans out per task range

## Context — what

`pre-review.js` budgets one grader over a range. On `spec/00114-skip-gate-matcher` that range was 27 commits across thirteen test files and six task ranges; the one grader graded 103 claims and 11 prose sites, and the four pre-reviews that followed over the fix ranges asked for 6, 5, 4 and 1 further changes on sites the branch pre-review had walked. The seam-only integration design of refine round 13 names the remedy: a `ranges` argument — one entry per SDD task range plus a `tail` for the merges, the change-index row and the closeout — run as parallel graders each inside its own budget and its own worktree, with one union report and exactly one ledger row at the branch tip, so `review.js`'s tip rule still reads one pre-review of the tip. Beside it, SDD's task reviewer and scoped re-reviewer append `{"kind":"task","task":N,"range":…,"tip":…}` rows to the same `ledger.jsonl`, which the trio's gates ignore, so the controller can derive the ranges from the ledger after a compaction; and SDD's parked rulings and deferred Minors reach the pre-review as claims to re-run, which the Exit of `zcrypto-plan-review` now requires by hand.

## Why this matters

The prose axis is the one no SDD seat grades, and it is the axis that thins when a single grader is handed a whole branch: the accretion the owner diagnosed as the convergence blocker arrives at the branch read in one piece, from implementers whose context is gone. A fan-out reads it at the width it was written.

## Findings so far

- `pre-review.js` at refine round 13 takes `{repo, range, tip, reportDir, worktree?, model?}`; its `worktree` arm tells the grader it is the checkout's only user, which a fan-out makes false — each grader needs its own worktree path, as `review.js`'s `CHECKOUT(label)` already gives its lenses.
- The trio's three ledger gates test `e.kind === 'pre-review' | 'review'` and ignore other kinds, so a `task` row breaks nothing.
- The fanned union does not dedupe: a site three tasks touched would carry three rows; `review.js` clusters on `path:line` and `pre-review.js` does not.
- Cost, modelled and not metered: about seven grader seats per branch instead of one, no added wall-clock, nothing added per task.

## Suggested next steps

- Give `pre-review.js` a `ranges` argument of `{label, range}` entries, a per-label worktree in its `worktree` arm, a union of the graders' `prose`/`claims`/`probes`/`classWalk` with `graded` summed and `ready` ANDed, and one Record row at `tip`; drive it in `tests/test_review_workflows.py` with a two-entry `ranges` asserting exactly one append whose tip is the branch tip.
- Add one closing sentence to the SDD task-reviewer and re-reviewer dispatches in the execution script so each appends its task row to `.tmp/reads/<slug>/ledger.jsonl`, and a `rulings` argument to `pre-review.js` naming the SDD `progress.md`, whose `Ruling:` lines the grader re-runs as claims.
- On the branch that ripens this, run the fan-out and a single grader over the same range once and compare what each graded; the topic closes on that measurement, whichever way it falls.
