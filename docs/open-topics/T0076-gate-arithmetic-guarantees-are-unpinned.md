---
status: partial
ripe_when: ripe NOW — merged, gate-critical code, every sub-item autonomous. Do it BEFORE the Stage-6a gate is read for a go/no-go, since the two HIGH findings are precisely the arithmetic that decides when the gate opens
---

# The concordance gate's arithmetic is correct but its guarantees are unpinned — a one-character edit opens the gate a day early, silently

## Context — what

A mutation audit (2026-07-20, 62 mutations against `cli/engine/concordance.py` — `evaluate_gate`, `replay_cycle`, `compare_targets`) found 9 triaged gaps that would survive being broken: the mutation is applied, the covering tests run, and nothing fails. **No live defect** — the code computes the right thing everywhere probed — but these are the guarantees that decide when real money is allowed to trade.

Companion to [[T0075]], which ran the same audit against the gate-evidence *cache*. Both were prompted by a defect in the **testing practice** rather than in any one test: the iteration that had just merged (iter-111, spec `00061`) found several of its own pins vacuous — swapping two labels, or attributing a result to a source that never ran, left the suite green because assertions were order-agnostic membership checks. The retroactive-audit rule then requires re-auditing everything built under the same practice.

## Why this matters

`_GATE_STREAK_DAYS` is the number of consecutive clean days the shadow engine must post before the strategy may go live. **Nothing asserts that one day fewer fails.** Verified independently, not merely taken from the audit: setting `_GATE_STREAK_DAYS = 13` (with `__pycache__` purged and the mutation confirmed on disk before the run) leaves **20/20** `tests/test_engine_concordance.py` green. The constant appears in `cli/` only — it is referenced by **no test at all**.

Two other findings are worse in subtler ways. A test that *looks* like it covers the dead-engine reset does not — `test_gate_export_stale_journal_pings_fail` exercises a separate command-level `--lag-fail-seconds` check and stays green while the reset is broken; a test that appears to cover a risk is more dangerous than a visibly missing one, because it stops anyone from looking. And the daily **no-peek** guarantee reopens on a same-length peek, where the failure mode is not a mis-set threshold but the builder silently running on lookahead data while the targets still compare equal.

## Findings so far

Full audit, committed as durable evidence: `docs/research/14.phase6-gate-guarantee-mutation-audits.md` (Audit B; 2026-07-20, Opus 4.8). **62 mutations, 16 undetected, 9 genuine gaps after triage**, each gap demonstrated pristine-vs-mutant rather than inferred from a passing test.

**An earlier 46-mutation pass was discarded as untrustworthy** — it shared a working tree with the companion cache audit (so two agents reverted each other's in-flight edits) and lacked bytecode control. It scored the compare-tolerance mutation as DETECTED when it is undetected, and it missed the same-length-peek hole and the asset-set-equality gap entirely. Its **attribution of finding 1 to `upper_bound_day max→min` was correct** — see the correction note below, which is the third pass at getting that one sentence right. The numbering below is the isolated run's.

**The bytecode caution, stated precisely because it is invisible and biases BOTH ways.** CPython validates a cached `.pyc` against `(source mtime-in-seconds, source size)`. Many of these mutations are **byte-identical in size** — `max`→`min`, `14`→`13`, `1e-6`→`1e-3` — so rewriting the file inside the same wall-clock second leaves both validators unchanged and pytest silently re-runs the *previous* mutant's bytecode. Proven directly: a probe of supposedly-pristine source reported `_GATE_STREAK_DAYS=13`. Any future mutation work here must set `PYTHONDONTWRITEBYTECODE=1`, purge `__pycache__`, and assert baseline-green before trusting a verdict.

1. **(HIGH) A dead journal keeps reporting the gate met** — `upper_bound_day = max(last_observed_day, now.date())` mutated to `min(...)`. 14 clean days followed by 5 days of silence: pristine → `streak=0, gate_met=False`; mutant → `streak=14, gate_met=True, last_failure=None`. Silent, permanent, and it points at "trade".
2. **(HIGH) 13 clean days opens the gate.** The 14-day test pins that 14 *is* enough; nothing pins that 13 *is not*. Independently reproduced twice (20/20 green at threshold 13), and the constant is referenced by no test at all. The asymmetry is the tell: **the mutations that open the gate EARLIER survive, while those that open it later are either caught or err in the stricter, harmless direction.** The tests were written by someone checking the gate was not too strict; nobody checked it was not too loose.
3. **(HIGH) The compare tolerance is unpinned across five orders of magnitude.** The passing test uses ~1e-7 diffs and the failing test 1e-2; the entire band between is free. A divergence 120× over budget passes at `tol=1e-3`.
4. **(HIGH) The daily no-peek guarantee reopens on a SAME-LENGTH peek.** The peek test's fixture trips `n_bars` **and** `last_ts` simultaneously, so it pins only their disjunction. Swap the trailing settled bar for the in-progress candle at equal length and the builder runs on **lookahead data** while the targets still compare equal. This is the one finding whose failure mode is silent contamination of the verdict rather than a mis-set threshold.
5. **(MED-HIGH) The multi-pair calendar guard is unreachable in tests** — every `replay_cycle` test uses one pair and the guard needs ≥2, so deleting it changes nothing in CI while production is multi-pair.
6. **(MEDIUM) The `n_bars` / `first_ts` conjuncts are individually unpinned** — same disjunction problem as finding 4.
7. **(MEDIUM) The day-cutoff anchor and window are unpinned.** The intra-day test picks `now=09:00`, below *every* candidate anchor, so it discriminates none; the gate can flip met up to 3.5 h early.
8. **(MEDIUM) `compare_targets`' asset-set equality weakened to length equality is undetected** — the check that two target dicts cover the *same assets*, not merely the same number of them. The mutant raises `KeyError` rather than silently passing, so it fails loudly rather than corrupting a verdict, but the path is unreached by tests. It carries its own exploit probe in the audit artifacts yet was omitted from that audit's own write-up, which is why the source doc's internal count (13) and its triaged headline (8) disagree; recorded here so the discrepancy is not re-derived.
9. **(LOW) `last_failure` "most recent" is unpinned** — every failure test injects exactly one failure. Diagnostic only.

**Triaged as not-gaps** (recorded so nobody re-derives them): the day-cutoff `>` → `>=` mutation is a boundary instant only — it differs solely when `now` equals the cutoff to the microsecond, and the mutant is *stricter*. The metadata-equality guard is a provably equivalent mutant, since `validate_record` plus the reconcile already imply it — **keep it**, it is the backstop for finding 4 on the h4 grid.

**A correction to this topic's own first correction, recorded rather than quietly fixed.** An earlier revision claimed `upper_bound_day max→min` was safe and that the discarded first pass had mis-attributed finding 1 to it. That was wrong: the two audits number their mutations independently — `max→min` is M08 in the first pass and M12 in the isolated one, while the isolated run's M08 is the unrelated cutoff `>`/`>=` change — and the label was mapped across the two schemes without checking. **The first pass had this attribution right.** The lesson is the one this whole topic is about: a correction is a verdict and needs the same symmetric scepticism as the claim it overturns, and cross-audit identifiers are not portable.

**What is already airtight, and should be copied rather than re-invented.** The catastrophic direction is genuinely well defended: all nine classification mutants, both classification swaps, and the `cycle_ts`-identity attribution mutant died immediately, because those tests assert *which* `cycle_ts` was processed rather than how many. The gaps are uniformly the opposite shape — **conjunctions pinned only through a fixture that trips several terms at once, and constants sampled far from both edges instead of bracketed.** That sentence is the whole finding list in one line.

## Done so far

**Findings 1 and 2 are closed** (PR #162, `test(cli): pin the gate streak threshold and the dead-engine reset`; test-only, no `cli/` change):

- `test_gate_streak_threshold_pinned_both_directions` — pins the threshold from both sides, and fails under `_GATE_STREAK_DAYS 14 → 13` (`assert 13 == 14`).
- `test_gate_dead_engine_after_5_days_silence_resets_streak_not_stale_streak` — fails under `upper_bound_day max( → min(` with exactly the dead-engine symptom, `GateStatus(streak=14, gate_met=True, last_failure=None)`.

Both mutations were re-run independently by implementer and reviewer, each with `PYTHONDONTWRITEBYTECODE=1`, a `__pycache__` purge, and an on-disk confirmation that the mutation was present.

**A design point settled there, applicable to any future constant pin.** "Assert against the constant, never a literal" — normally sound — is *mathematically incompatible* with catching a mutation of that same constant: with `N = _GATE_STREAK_DAYS`, `N >= N` being True and `N-1 >= N` being False holds for every value of N, so it pins the `>=` relationship and never the ratified value. An external anchor is required. The resolution is both layers — rule-based boundary tests that survive a deliberate threshold change, plus one explicit `assert _GATE_STREAK_DAYS == 14`. The cost, a required diff line if the threshold is ever changed on purpose, is the *point*: silent drift is the failure mode, and a loud reviewable diff is the fix.

## Suggested next steps

- **(Autonomous)** Re-check `test_gate_export_stale_journal_pings_fail`'s name and docstring: the reset itself is now pinned, but that test still *reads* as though it covers it while exercising a separate `--lag-fail-seconds` check.
- **(Autonomous)** Bracket the compare tolerance from both sides: a diff just inside it must pass and one just outside must fail, asserted against the constant rather than a literal, so the band between the current 1e-7 and 1e-2 samples stops being free.
- **(Autonomous, highest value of the set)** Pin the no-peek guarantee against a **same-length** peek — swap the trailing settled bar for the in-progress candle at equal length, so `n_bars` and `last_ts` are pinned as separate conjuncts rather than as a disjunction. This is the only finding here whose failure mode is silent lookahead contamination rather than a mis-set threshold.
- **(Autonomous)** Add a multi-pair `replay_cycle` case so the cross-pair calendar guard executes at all; move the intra-day test's `now` above a candidate anchor so it discriminates between them; add a second failure so "most recent" in `last_failure` becomes testable.
- **(Autonomous)** Pin the `n_bars` / `first_ts` conjuncts individually, with a scenario that trips exactly one at a time.
- **(Do NOT 'clean up')** The metadata-equality guard looks redundant and is a provably equivalent mutant — keep it; it is the backstop for finding 4 on the h4 grid.
- **(Method)** For any future mutation audit here: `PYTHONDONTWRITEBYTECODE=1`, purge `__pycache__`, assert baseline-green, give each concurrent agent its own git worktree, and demonstrate every claimed gap pristine-vs-mutant. Two passes of this audit were discarded for skipping one of those.
