---
status: open
ripe_when: 'the next branch that adds a skip in a position `_FIXTURE` does not already carry, or the next change to `_gates` in `tests/test_live_venue_opt_in.py` — either is a session already reading the walker'
---

# Gate discovery beyond the fixture's positions

## Context — what

`tests/test_live_venue_opt_in.py` judges the gates `_gates()` finds — a `pytest.skip` call under any enclosing condition, a `skipif` mark, `raise unittest.SkipTest`, `@unittest.skipIf`/`skipUnless`, and `self.skipTest(...)` — and every assertion in the file is over that set.

Whether that walk finds every skip in `tests/` is asserted by nothing, and cannot be asserted from inside the guard: any set it computes to check the walker is computed by the walker (spec 00114 D6).
What stands in for the assertion is `test_the_fixture_carries_every_position_a_skip_can_sit`, over `_FIXTURE` — a hand-written file carrying one skip per position someone thought of.
A position nobody thought of is a gate the matcher never judges, and no test in the file names it.

Spec 00114 states this limit rather than closing it, in D6 and in its `## Out of scope`; it was T0190's residual before that, and T0190 is archived, so this file is where it is now parked.

## Why this matters

A gate the walker misses is indistinguishable from a tree that has no such gate — the suite is green either way, which is the same failure mode the matcher exists to close, one level up: a skip reading as coverage.

The cost of a miss is the whole guard, not one gate: a venue read written in a skip position `_gates` does not walk passes every assertion in the file, including the one-name assertion the suite behind `infra/scripts/count-list.sh skip-gate-contract` carries.

The two `unittest` positions show how a position is actually found today. They were a hole T0190's guard recorded in its own docstring, and they closed on this branch (`641eda4e6`) because someone read the docstring and wrote the arms — by a person reading for it, never by a test going red.

## Findings so far

- `_gates()` reads five constructs at this registration; the tree has no `unittest` skip gate, so the two arms added on this branch cost no migration and are held by the fixture alone.
- The positions `_FIXTURE` carries are enclosing shapes rather than call shapes: a skip in an `if` body and one in its `else`, one nested a level below the condition rather than directly under it, one in an `except` handler with no condition anywhere, one under a `match` case, and one inside a skip helper the test calls.
- Three of those were proven on T0190's branch by planted worktrees rather than by `infra/scripts/mutate-probe.sh`, because a `sed` expression cannot restructure a statement into a branch; that cost is unchanged and any new position pays it.
- An independent derivation is what the property needs, and `test_the_fixture_carries_every_position_a_skip_can_sit`'s docstring names the two routes to one: a fixture whose expected gates are written down independently, or a second implementation. The second is cheap for the call-shaped positions: a FLAT walk over every module under `tests/`, collecting every `pytest.skip` call and every `raise unittest.SkipTest` by line and knowing nothing about enclosing constructs, then asserting each line appears among `_gates()`'s results. It is independent of exactly the arms `_gates` can be missing, and it does not cover the mark and decorator positions, which are found by a different route again.

## Suggested next steps

- Write that flat walk as a second test in `tests/test_live_venue_opt_in.py`, deriving its set without calling `_gates` or `_guards_of`, and assert set equality by `(file, line)` — a difference in either direction is the finding: a line the flat walk sees and `_gates` does not is a missed position, and the reverse is a gate attributed to a line nothing skips at.
- For the mark and decorator positions, derive the second set off the decorator and mark nodes directly rather than through `_is_pytest_call`, so the two routes share no resolution code.
- Prove each new check by planting one skip per position in a scratch worktree and confirming the check names it; a `sed` mutation is enough only for the positions that do not restructure a statement, and `infra/scripts/mutate-probe.sh` refuses the rest for that reason.
- If the equality cannot be made to hold — the likely outcome for the decorator half, whose four spellings resolve through imports — record what the second route does and does not see in the guard's module docstring, and leave the gap stated rather than implied.
