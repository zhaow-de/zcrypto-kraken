# Spec 00063 — pinning the concordance gate's arithmetic guarantees (T0076)

## Goal

Make the seven remaining [[T0076]] guarantees fail when broken. No production behaviour changes: the gate computes the right thing today, and a 62-mutation audit found no live defect. What is missing is any test that notices when it stops.

## Why

`evaluate_gate` / `replay_cycle` / `compare_targets` decide whether the strategy may trade real money. An audit mutated 62 of their claims and found 9 that survive — each one a guarantee the code currently honours and nothing enforces. Two are already pinned (the streak threshold and the dead-engine reset, PR #162); these are the rest.

The audit named the shape they share, and it is more useful than the individual findings: **conjunctions pinned only through a fixture that trips several terms at once, and constants sampled far from both edges instead of bracketed.** Every item below is one of those two.

One further asymmetry is worth carrying into the design: **every mutation that opened the gate EARLIER survived; every one that opened it later was caught or errs harmlessly stricter.** The existing tests were written by someone checking the gate was not too strict. Nobody checked it was not too loose.

## Decisions

- **D1 — a conjunct is pinned only by a scenario that trips exactly it.** `concordance.py:118` is `len(ts) != n_bars or ts[0] != first_ts or ts[-1] != last_ts`. Today's peek fixture violates two terms simultaneously, so deleting any single one leaves the suite green. Each of the three gets a case that satisfies the other two. This is D1 for findings 4 and 6 alike — they are the same line.

- **D2 — the same-length peek is the keystone, and it is not just another conjunct.** Swap the trailing settled bar for the in-progress candle at **equal length**: `n_bars` matches, `first_ts` matches, only `last_ts` differs. If that check is absent the builder runs on **lookahead data and the targets still compare equal** — the only finding here whose failure mode is silent contamination of the verdict rather than a mis-set threshold or a loud error. It gets an explicit test whose name says what it defends, not a parametrized row.

- **D3 — constants are bracketed, never sampled.** `compare_targets(tol=1e-6)` is currently exercised at ~1e-7 (passes) and 1e-2 (fails), leaving five orders of magnitude unconstrained — a divergence 120× over budget passes at `tol=1e-3`. Pin a diff just inside the tolerance passing and one just outside failing, **asserted against `tol` rather than a literal**, so the test states the rule while remaining sensitive to the value. Same treatment for the day-cutoff anchor (finding 7), whose intra-day test picks `now=09:00` — below *every* candidate anchor, so it discriminates none.

- **D4 — reachability is part of a guarantee.** The multi-pair calendar guard cannot execute under any current test because every `replay_cycle` case uses one pair. A guard that never runs in CI is indistinguishable from one that was deleted. It gets a two-pair case; production is multi-pair.

- **D5 — "most recent" needs two.** `last_failure` is only meaningful when more than one failure exists; every failure test injects exactly one, so the ordering is untestable as written. Two failures, assert the later one. Diagnostic-only, so LOW — but it is a one-line fixture change.

- **D6 — this is test-only.** No change to `evaluate_gate`, `replay_cycle`, `compare_targets`, the journal format, or any threshold. If a pin cannot be written without changing production code, that is a finding to report, not a licence to change the gate.

- **D7 — every pin is mutation-verified, and the mutation is confirmed on disk.** A test that passes proves nothing here; the audit exists because tests passed while their claims were false. For each pin: apply the mutation it targets, `grep` the file to confirm the edit is present, run with `PYTHONDONTWRITEBYTECODE=1` after purging `__pycache__`, observe the failure, restore. Three ways a mutation test has lied in this repo this month — stale bytecode running the previous mutant, concurrent agents reverting each other in a shared tree, and a mutation landing on a docstring — and a fourth found at review: the original text being a substring of the mutant, so the edit silently no-ops.

- **D8 — do not "clean up" the metadata-equality guard.** It looks redundant (`validate_record` enforces the same equality, and the reconcile forces data==metadata) and the audit confirms it is a provably equivalent mutant no test can kill. **Keep it**: it is the backstop for D2 on the h4 grid. Recorded here because the next reader will otherwise delete it as dead code.

## Non-goals

- The two already-pinned findings (streak threshold, dead-engine reset) — PR #162.
- [[T0075]]'s gate-cache guarantees. Separate module, separate PR, and its audit needs re-running under bytecode control before its scope is even known.
- Changing the tolerance, the anchor, the streak length, or any other ratified value. Pinning a constant is not the same as endorsing it; if `1e-6` is wrong, that is a separate decision with its own evidence.

## Test list (TDD)

1. **The keystone (D2)** — same-length peek: `n_bars` and `first_ts` match, `last_ts` is the in-progress candle. Must raise; must fail if the `ts[-1] != entry.last_ts` term is deleted.
2. **`n_bars` alone** — length differs, both timestamps match.
3. **`first_ts` alone** — leading bar differs, length and `last_ts` match.
4. **Tolerance, both sides** — a diff just inside `tol` passes, just outside fails, both expressed relative to `tol`.
5. **Multi-pair calendar guard** — a two-pair cycle whose pairs disagree on the calendar; must raise, and must fail if the guard is deleted.
6. **Day-cutoff anchor** — `now` positioned so the candidate anchors give *different* verdicts, so the test discriminates between them rather than agreeing with all.
7. **Asset-set equality** — `compare_targets` over dicts with the same cardinality but different keys must not compare equal. (The mutant raises `KeyError` rather than passing silently, so this pins an unreached path, not a silent-corruption one.)
8. **`last_failure` is the most recent** — two failures, assert the later.
9. **Regression** — the existing 22 concordance tests still pass unchanged, and no production file is modified (`git diff --stat` touches tests only).
