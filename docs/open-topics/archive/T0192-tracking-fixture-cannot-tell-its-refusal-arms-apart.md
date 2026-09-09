---
status: resolved
---

# The week-boundary tracking fixture cannot tell its refusal arms apart

## Context — what

`tests/test_engine_executor.py::test_the_first_fill_landing_on_the_week_boundary_is_not_scored_either` asserts that a week whose first fill lands exactly on the Monday boundary goes unscored. `_score_closed_week` can refuse that week on either of two arms — the birth-record arm (`birth != first_fill`) or the week-start arm (`first_fill >= week_start`) — and the test's assertions read the same on both, so it does not say which one it is exercising.

## Why this matters

The week-start arm is what stops the week containing the first fill being scored with its pre-fill cycles averaged into the mean, which latches the kill file on a healthy engine — a live-trade-path stop that no code path clears. This is the only test named for that shape, and it does not pin it: a change to `_BIRTH_MINT_WINDOW`, to the fixture's boundaries, or to `_tracking_executor`'s clock offset moves which arm fires, and the test stays green either way.

## Findings so far

Driven both ways on `docs/docstrings-tests-engine-executor-rerun`, at its commit `docs(tests): the line-number citations go, and three claims the bodies refute`, reading the refusal off the executor's own logger rather than inferring it:

- As written, the clock sits `_BIRTH_MINT_WINDOW` (seven days) plus two minutes past the fill: the mint refuses, no `FIRST_FILL_FILE` is written, and the birth-record arm refuses the week.
- Four minutes earlier, the mint succeeds, the birth file appears, and the week-start arm refuses it instead.
- Both readings give `tripped=False` and `states=[_TRACKING_UNSCORED]`, so every assertion in the test passes on either arm.

At that commit the docstring claimed only the outcome its assertions pinned, so what was open here was a test that could pin more, never a false claim left standing.

## Resolution

Both steps landed on `test/t0192-pin-the-week-boundary-refusal-arm`.

The cause was the fixture, not the assertions: `_BOUNDARY_RAMP_FILLS`' first fill is `_TRACK_MONDAY` while the shared `_MINT_AT` is twelve hours before it, so the mint ran against a journal holding no fill, no birth record was written, and the birth arm refused the week before the week-start arm could be reached. `_RAMP_MINT_AT` — the first boundary after this ramp's own first fill, which is what `_mint_birth` documents the mint to mean — lets the birth arm pass, and the week-start arm is what refuses.

The pin reads that arm's own refusal message, because every arm publishes `_TRACKING_UNSCORED` and the state alone cannot tell them apart. Two mutations of `_score_closed_week` are killed that were invisible before: narrowing `>=` to `>`, and widening the boundary-count arm so it refuses first. They are killed by different things: the first dies on the fixture change plus the pre-existing `assert not tripped`, before the added assertion is reached at all; the second dies on the added assertion, which is also what stops the docstring naming an arm nothing reads.

The docstring names the arm again.
