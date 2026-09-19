---
status: resolved
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

## Resolution

Delivered by PR #569, in `tests/test_live_venue_opt_in.py`. `_flat_sites` is the second implementation: it reads each node alone — a call or a raise that is a skip under its own name, a `skipif` / `skipIf` / `skipUnless` call — resolves no import and knows nothing of what encloses a node, so it has no position to miss. `test_a_second_walk_of_the_tree_finds_exactly_the_gates_the_walker_finds` holds the two walks equal over `tests/` by file and line, and a third test holds that `_flat_sites` names none of the functions `_gates` is built from.

Both halves hold as equality, the mark half included, which this topic expected to fail: measured before the assertion was written, the flat walk found 25 skip calls and 40 marks over `tests/`, and the walker's gates were exactly those. Over the guard's own fixture the walks differ in two cases, both a skip bound to another name, and `_FLAT_WALK_UNSEEN` holds that difference as a list. So what remains unheld is narrower than it was and is written in the module docstring: a skip under another name AND in a position `_guards_of` does not walk.

Planting named five such positions — a boolean short-circuit, a conditional expression, a `for`'s `else`, a comprehension, a nested function. The walker gains no arm for them: none is in the tree, and one that arrives fails the suite with its file and line and the instruction to add the arm and a fixture case, which is the reader this topic said did not exist. The same proving found the fixture carried no raised skip and no `mark.skip`, so the walker's arms for those were held by no case; four cases close that.
