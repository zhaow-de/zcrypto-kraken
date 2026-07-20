---
status: open
ripe_when: ripe NOW — merged, gate-critical code, every sub-item autonomous. Do it BEFORE the Stage-6a gate is read for a go/no-go, since the two HIGH findings are precisely the arithmetic that decides when the gate opens
---

# The concordance gate's arithmetic is correct but its guarantees are unpinned — a one-character edit opens the gate a day early, silently

## Context — what

A mutation audit (2026-07-20, 46 mutations against `cli/engine/concordance.py` — `evaluate_gate`, `replay_cycle`, `compare_targets`) found 10 claims that would survive being broken: the mutation is applied, the covering tests run, and nothing fails. **No live defect** — the code computes the right thing everywhere probed — but these are the guarantees that decide when real money is allowed to trade.

Companion to [[T0075]], which ran the same audit against the gate-evidence *cache*. Both were prompted by a defect in the **testing practice** rather than in any one test: the iteration that had just merged (iter-111, spec `00061`) found several of its own pins vacuous — swapping two labels, or attributing a result to a source that never ran, left the suite green because assertions were order-agnostic membership checks. The retroactive-audit rule then requires re-auditing everything built under the same practice.

## Why this matters

`_GATE_STREAK_DAYS` is the number of consecutive clean days the shadow engine must post before the strategy may go live. **Nothing asserts that one day fewer fails.** Verified independently, not merely taken from the audit: setting `_GATE_STREAK_DAYS = 13` (with `__pycache__` purged and the mutation confirmed on disk before the run) leaves **20/20** `tests/test_engine_concordance.py` green. The constant appears in `cli/` only — it is referenced by **no test at all**.

The second HIGH is worse in a subtler way: a test that *looks* like it covers the case does not. `test_gate_export_stale_journal_pings_fail` reads as though it pins the dead-engine reset, but it exercises a separate command-level `--lag-fail-seconds` check and stays green while the reset itself is broken. A test that appears to cover a risk is more dangerous than a visibly missing one, because it stops anyone from looking.

## Findings so far

Full audit, committed as durable evidence: `docs/research/14.phase6-gate-guarantee-mutation-audits.md` (Audit B; 2026-07-20, Opus 4.8). A shared-working-tree run of the same audit was discarded as unreliable (two concurrent mutation agents each reverting the other's in-flight edits via broad `git checkout`); an isolated-worktree re-run corroborates. The reported pass also carries an on-disk assertion that each mutation survived its own test run.

**Methodological note worth keeping** — the audit's first pass was wrong and it caught itself: stale `__pycache__` (CPython validates `.pyc` on source mtime+size, and a detected mutation completes in ~2 s, so consecutive iterations collide inside the same mtime second) made pytest silently re-run the *previous* mutation's bytecode. It biases **both** directions — two mutants were falsely "undetected", two falsely "detected". Any future mutation work in this repo must purge `__pycache__` between iterations and assert on disk that the mutation is still present after the test run.

1. **(HIGH) `_GATE_STREAK_DAYS 14 → 13` is undetected.** Nothing asserts that 13 clean days does *not* meet the gate; the 14-day test passes at threshold 13. Independently reproduced (20/20 green).
2. **(HIGH) `upper_bound_day = max(...) → min(...)` is undetected.** A dead engine's frozen journal would keep its old streak and report `gate_met=True` instead of resetting. The apparently-covering test checks something else entirely.
3. **(MEDIUM) The `_assemble` cross-pair calendar check never executes in tests** — every `replay_cycle` test is single-pair; production is multi-pair.
4. **(MEDIUM) The day-cutoff `+ _FRESHNESS_WINDOW` can be dropped** — no test sets `now` inside the 20:00–20:30 window the docstring's opening sentence is about.
5. **(MEDIUM) `last_failure` keeps the *first* failure rather than the most recent, undetectably** — every test has exactly one failure, so "most recent" is untestable as written. This is iter-111's exact shape.
6. **(MEDIUM ×3) The reconcile line's `n_bars` / `first_ts` / `last_ts` sub-checks are each individually deletable.** One peek scenario trips two sub-checks at once, so the line is pinned *as a whole* but *which* check fired is not.
7. **(LOW–MEDIUM) The freshness *lower* bound is unpinned** — a record claiming completion before its own boundary scores clean.
8. **(LOW, not a gap) The metadata-equality guard is an equivalent mutant** — `validate_record` already enforces it and the reconcile forces data==metadata. Genuine defence-in-depth; only the docstring oversells it as *the* mechanism.

**What is already airtight, and should be preserved and copied.** The catastrophic direction is well defended: FAILURE→PASS was caught in all six forms tested (hash mismatch, validation failure, inverted compare, missing cycle, inverted tolerance, disabled hash verification). Attribution scored 9/10 — `test_replay_cycle_locates_newest_row_by_cycle_ts` deliberately makes `series[2]` differ from `series[-1]` so the mutation cannot hide. That, and [[T0075]]'s `_counted_replay_cycle` asserting *which* `cycle_ts` was replayed (identity, not count), are the two patterns that work; reuse them.

## Suggested next steps

- **(Autonomous)** Pin the gate threshold from both sides: `_GATE_STREAK_DAYS - 1` clean days must **not** meet the gate, and exactly `_GATE_STREAK_DAYS` must. Assert against the constant, not a literal `14`, so the test states the *rule* rather than re-encoding today's value.
- **(Autonomous)** Pin the dead-engine reset directly — a frozen journal whose newest cycle is older than the boundary must reset the streak and report `gate_met=False`. Then re-check `test_gate_export_stale_journal_pings_fail`'s name and docstring, which currently imply a guarantee it does not provide.
- **(Autonomous)** Add a multi-pair `replay_cycle` case so the `_assemble` cross-pair calendar branch executes at all; add a `now` inside the 20:00–20:30 freshness window; add a second failure so "most recent" in `last_failure` becomes testable; add a record completing before its own boundary.
- **(Autonomous)** Pin the three reconcile sub-checks individually, with a scenario that trips exactly one at a time.
- **(Autonomous)** Correct the docstring that oversells the metadata-equality guard as the mechanism rather than defence-in-depth.
- **(Method)** Purge `__pycache__` and assert the mutation is still on disk after the run, for any future mutation audit in this repo — see the methodological note above.
