---
status: resolved
---

# The branch pre-review fans out per task range

## Context — what

`pre-review.js` budgets one grader over a range. On `spec/00114-skip-gate-matcher` that range was 27 commits across nineteen test files and six task ranges; the one grader graded 103 claims and 11 prose sites, and the four pre-reviews that followed over the fix ranges asked for 6, 5, 4 and 1 further changes on sites the branch pre-review had walked. The seam-only integration design of refine round 13 names the remedy: a `ranges` argument — one entry per SDD task range plus a `tail` for the merges, the change-index row and the closeout — run as parallel graders each inside its own budget and its own worktree, with one union report and exactly one ledger row at the branch tip, so `review.js`'s tip rule still reads one pre-review of the tip. Beside it, SDD's task reviewer and scoped re-reviewer append `{"kind":"task","task":N,"range":…,"tip":…}` rows to the same `ledger.jsonl`, which the trio's gates ignore, so the controller can derive the ranges from the ledger after a compaction; and SDD's parked rulings and deferred Minors reach the pre-review as claims to re-run, which the Exit of `zcrypto-plan-review` now requires by hand.

## Why this matters

The prose axis is the one no SDD seat grades, and it is the axis that thins when a single grader is handed a whole branch: the accretion the owner diagnosed as the convergence blocker arrives at the branch read in one piece, from implementers whose context is gone. A fan-out reads it at the width it was written.

## Findings so far

- `pre-review.js` at refine round 13 takes `{repo, range, tip, reportDir, worktree?, model?}`; its `worktree` arm tells the grader it is the checkout's only user, which a fan-out makes false — each grader needs its own worktree path, as `review.js`'s `CHECKOUT(label)` already gives its lenses.
- The trio's three ledger gates test `e.kind === 'pre-review' | 'review'` and ignore other kinds, so a `task` row breaks nothing.

## Resolution

Delivered by PR #573: `pre-review.js` takes `ranges` — one `{label, range}` per slice, chained from the range's opening to its close, a worktree per label, a union of the graders' rows with `graded` summed and `ready` ANDed, one Record row at the tip — and `rulings`, the SDD ledger whose `Ruling:` lines the last slice's grader re-runs as claims; `tests/test_review_workflows.py` drives both. The task rows are appended by the controller at each task's completion — this repo's SDD is the `superpowers` plugin's skill, with no dispatch script of its own to carry a closing sentence — and `zcrypto-plan-review`'s Exit tells the controller to pass both arguments.

Measured once, on PR #572's branch (`develop..639f3b490` — a plan range and four task ranges; both reads on Opus, 2026-09-20, run side by side into two report directories). The single grader graded 74 sites (3 corrected, 3 trimmed, 2 cut) in 208k tokens, 42 tool calls and 11.6 minutes. The fan-out's five slices graded 228 (6 corrected, 12 trimmed, 6 cut) and found two message claims that do not reproduce, in 674k tokens, 181 tool calls and 12.0 minutes. Both found the skill paragraph's false clause, two duplicated topic lines and two comment trims. Only the single grader found the same false sentence in spec D4 and in the plan's copy of the paragraph — a falsehood whose refutation sat in a file another slice held. Only the fan-out found the plan's false Expected, two false test docstrings, a false test comment, an archived bullet's tense against its Resolution and ten more trims and cuts. Neither read alone was the right read: the branch shipped their union, and the Exit sentence prescribes both reads until a second measurement says otherwise.
