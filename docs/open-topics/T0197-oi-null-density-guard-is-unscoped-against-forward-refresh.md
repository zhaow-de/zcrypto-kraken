---
status: open
---

# The OI level-column null-density guard is unscoped, unlike its sibling zero-population guard

## Context — what

`tests/test_derivatives_oi.py::test_both_oi_level_columns_carry_no_nulls` asserts
`sum_open_interest` and `sum_open_interest_value` carry zero nulls across the whole `oi_panel`
fixture -- every row read from the substrate, with no window. Its sibling,
`test_the_oi_zero_populations_hold_over_a_closed_window`, pins a different property of the same
two columns (the venue-hole zero counts) but does so only over `_CLOSED_WINDOW_END` (2026-01-01),
explicitly so a forward substrate refresh extending past that date cannot move the pinned count.
The null-density guard has no equivalent window.

## Why this matters

Spec `00110` (`docs/specs/00110-b2-derivatives-feature-harness-design.md:36`) states the two
columns are complete as a **measured** fact -- "zero nulls in all ten symbols" -- not as a
structural guarantee the venue or the capture path enforces. If a forward refresh (the substrate
is a live, growing 5-minute series, `docs/specs/00110...:10` puts it at 5,010,882 rows ending
2026-07-22 as of that measurement) ever lands a single null in either level column, anywhere, this
test fails on a data change with no code change behind it -- the same class of test-breaks-on-live-
data-drift the closed-window sibling was built to prevent for the zero-population guard.

## Findings so far

- `tests/test_derivatives_oi.py:472-480` (`test_both_oi_level_columns_carry_no_nulls`): sums
  `null_count()` over every frame in `oi_panel` for both columns, asserting both equal `0` --
  unwindowed.
- `tests/test_derivatives_oi.py:483-501` (`test_the_oi_zero_populations_hold_over_a_closed_window`):
  filters to `ts < _CLOSED_WINDOW_END` before counting, precisely to keep a forward refresh from
  moving the pinned figures.
- Registered from `docs/prose-gap-round2-batch1`, where a prose correction on the comment above
  `_CLOSED_WINDOW_END` (which had claimed the null-count assertion's lack of scoping as an
  enumerated blind spot, banned by `prose.md`'s no-coverage-claims rule) surfaced this as a
  question worth tracking rather than stating in-line.

## Suggested next steps

- **Decide whether the density claim is meant to hold for all time or only as measured.** If a
  venue-emitted null is expected to never occur going forward (an instrument-defect-if-violated
  invariant), the current unscoped assertion is correct by design and this topic closes as a
  non-issue. If it is only a measured historical fact like the zero-population counts, window the
  assertion to `_CLOSED_WINDOW_END` the same way, and re-verify the file's own docstring/spec
  citation still supports an unwindowed reading for whichever choice is made.
  Either way, this is a behavior-shaped test change -- its own branch and review, not a fold-in to
  a docs-kind batch.
