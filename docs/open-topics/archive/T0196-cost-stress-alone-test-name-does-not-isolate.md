---
status: resolved
---

# Two `..._can_fail_alone` test names claim isolation their shared fixture value does not pin

## Context — what

`tests/test_alpha_killbar.py` has two tests named for isolating one kill-bar leg --
`test_a1_kill_bar_cost_stress_can_fail_alone` and `test_a1_kill_bar_worst_slice_can_fail_alone` --
and both build their fixture with `var_trials=1.0` (not the file's usual `1e-3`). Driven directly,
both compound: the cost-stress test gets `dsr=3.83e-89, dsr_pass=False` alongside its named
`cost_stress_pass=False`, and the worst-slice test gets the same `dsr=3.83e-89, dsr_pass=False`
alongside its named `worst_slice_pass=False`. Neither test's assertions pin `dsr_pass` at all, so
neither name is true of what its own fixture proves -- both are two-leg failures wearing a
one-leg name, from the same root cause.

## Why this matters

A reader auditing kill-bar coverage by test name credits each of these with proving its named leg
can fail on its own -- the exact thing an all-must-hold gate needs each leg individually verified
for, so a leg that can never independently fail is dead code wearing a passing test. The corrected
comment beside the cost-stress assertion (`docs/prose-gap-round2-batch1`, commit `b884a9d7`)
mitigates this only for a reader already inside that one function; the worst-slice test carries no
such comment yet, and the names are what `pytest -k`, a failure line, and a coverage audit all show
first.

## Findings so far

- Driven on `docs/prose-gap-round2-batch1`, both at each test's own `var_trials=1.0` and at the
  file's usual `var_trials=1e-3` on the same book (`beta=1.2, seed=42`):
  - `test_a1_kill_bar_cost_stress_can_fail_alone`'s fixture: `dsr=3.83e-89, dsr_pass=False,
    cost_stress_pass=False` at `var_trials=1.0`; at `1e-3` the same book gives `dsr=1.0,
    dsr_pass=True, cost_stress_pass=False` -- so `var_trials=1.0` is what compounds it, not
    anything inherent to cost stress.
  - `test_a1_kill_bar_worst_slice_can_fail_alone`'s fixture: `dsr=3.83e-89, dsr_pass=False,
    cost_stress_pass=True, spa_pass=True, worst_slice_pass=False` -- the same compounding, same
    root cause, on a different fixture.
- `test_a1_kill_bar_dsr_fails_between_old_and_new_bar` was checked the same way and does NOT
  compound: `dsr=0.9254678660756066, dsr_pass=False`, with `spa_pass`, `cost_stress_pass` and
  `worst_slice_pass` all `True` -- this one's isolation is real, at `var_trials=0.01`.
  `test_a1_kill_bar_spa_decisive_window_diverges_from_full` (the SPA-alone test) was not
  re-driven here.
- Neither `..._can_fail_alone` test's assertions mention `dsr` or `dsr_pass` at all, so nothing in
  either test would catch a further change that made a third leg fail too.
- Registered from the branch that found and corrected the cost-stress comment; corrected sentence
  cannot fix a test's name, since renaming moves the AST and cannot ride a prose-only batch.

## Resolution

Fixed by rebuilding both fixtures at `VAR_TRIALS_PER_PERIOD` (`1e-3`, the file's usual value)
instead of `1.0`, on `fix/t0196-kill-bar-isolation-fixtures`:

- `test_a1_kill_bar_cost_stress_can_fail_alone`: driven at `1e-3` on the same book --
  `dsr_pass=True, spa_pass=True, worst_slice_pass=True` alongside `cost_stress_pass=False`, a
  genuine single-leg isolation. Assertions added pinning all three; the now-obsolete comment
  explaining why `dsr_pass` also failed at `var_trials=1.0` was deleted, since it no longer does.
- `test_a1_kill_bar_worst_slice_can_fail_alone`: driven the same way -- `dsr_pass=True,
  spa_pass=True, cost_stress_pass=True` alongside `worst_slice_pass=False`. Assertions added
  pinning all three.
- Both proved by construction: reverting `var_trials` back to `1.0` fails the new `dsr_pass is
  True` assertion in each test (a heavy flat cost drag or a very negative regime slice both also
  fail the DSR leg at that scale, per the deleted comment's own claim), so the added assertions
  discriminate the defect they were written to catch, not merely restate the fixture.
- `test_a1_kill_bar_spa_decisive_window_diverges_from_full` was driven per the suggestion below:
  `dsr_pass=True, cost_stress_pass=True, worst_slice_pass=True` alongside `spa_pass=False` -- this
  one already isolates genuinely (it already used `VAR_TRIALS_PER_PERIOD`, not `1.0`) and needed no
  change.
