---
status: open
---

# The week-boundary tracking fixture cannot tell its refusal arms apart

## Context — what

`tests/test_engine_executor.py::test_the_first_fill_landing_on_the_week_boundary_is_not_scored_either` asserts that a week whose first fill lands exactly on the Monday boundary goes unscored. `_score_closed_week` can refuse that week on either of two arms — the birth-record arm (`birth != first_fill`) or the week-start arm (`first_fill >= week_start`) — and the test's assertions read the same on both, so it does not say which one it is exercising.

## Why this matters

The week-start arm is what stops the week containing the first fill being scored with its pre-fill cycles averaged into the mean, which latches the kill file on a healthy engine — a live-trade-path stop that no code path clears. This is the only test named for that shape, and it does not pin it: a change to `_BIRTH_MINT_WINDOW`, to the fixture's boundaries, or to `_tracking_executor`'s clock offset moves which arm fires, and the test stays green either way.

## Findings so far

Driven both ways on `docs/docstrings-tests-engine-executor-rerun` at `e1f52258`, reading the refusal off the executor's own logger rather than inferring it:

- As written, the clock sits `_BIRTH_MINT_WINDOW` (seven days) plus two minutes past the fill: the mint refuses, no `FIRST_FILL_FILE` is written, and the birth-record arm refuses the week.
- Four minutes earlier, the mint succeeds, the birth file appears, and the week-start arm refuses it instead.
- Both readings give `tripped=False` and `states=[_TRACKING_UNSCORED]`, so every assertion in the test passes on either arm.

The docstring is truthful as it stands: `e1f52258` rewrote it to claim only the outcome its assertions pin. This is a test that could pin more, not a false claim left standing.

## Suggested next steps

- Add one assertion naming the arm — on the mint-refusal warning, or on `(exec_dir(tmp_path) / FIRST_FILL_FILE).exists()`, which is the shape the sibling `test_a_pruned_journal_head_refuses_instead_of_scoring_a_short_held` already uses. It cannot ride a docstring pass: it moves the AST, which falsifies that branch's prose-only proof, so it takes its own branch and its own review.
- With the arm pinned, the docstring may name it again.
