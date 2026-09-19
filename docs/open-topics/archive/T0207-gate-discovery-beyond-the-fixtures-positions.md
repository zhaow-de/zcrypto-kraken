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
- An independent derivation is what the property needs, and `test_the_fixture_carries_every_position_a_skip_can_sit`'s docstring named the two routes to one: a fixture whose expected gates are written down independently, or a second implementation. The second is cheap for the call-shaped positions: a FLAT walk over every module under `tests/`, collecting every `pytest.skip` call and every `raise unittest.SkipTest` by line and knowing nothing about enclosing constructs, then asserting each line appears among `_gates()`'s results. It is independent of exactly the arms `_gates` can be missing, and it does not cover the mark and decorator positions, which are found by a different route again.

## Resolution

Delivered by PR #569, in `tests/test_live_venue_opt_in.py`. `_flat_sites` is the second implementation: it finds the skips something DECIDES, asking only whether anything between a skip and its function could keep it from running, and answering from a list of the node types known NOT to decide — never from a list of the constructs that do, which is `_guards_of`'s list and the thing under test. `test_every_decided_skip_a_second_walk_finds_is_a_gate_the_walker_found` holds that every such skip over `tests/` is a gate `_gates` found, by file and line, and a further test holds that `_flat_sites` names no function `_gates` reaches or is reached from, a set read off the module's own call graph.

The assertion runs one way on purpose: a gate the second walk does not see is a binding it does not read, and `_FLAT_WALK_UNSEEN` holds those fixture cases as a list. So what remains unheld is narrower than it was and is written in the module docstring: a skip bound any other way, where it sits in a position `_guards_of` does not walk or is reached by a binding `_pytest_bindings` does not follow.

The walker gains no arm for the positions that remain unwalked: none is in the tree, and one that arrives fails the suite with its file and line and the remedy `_walker_missed` prints, which is the reader this topic said did not exist.
