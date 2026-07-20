# Gate-arithmetic pins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make [[T0076]]'s seven remaining gate guarantees fail when broken (spec `00063`).

**Architecture:** Tests only, in `tests/test_engine_concordance.py`. No production file changes.

**Tech Stack:** Python 3.14, pytest.

## Global Constraints

- **Test-only (D6).** `cli/engine/concordance.py` and every other production file must be byte-identical at the end. If a pin cannot be written without changing production code, stop and report it — that is a finding, not a licence to change the gate.
- **Every pin is mutation-verified (D7).** For each: apply the mutation, **`grep` the file to confirm the edit landed**, purge `__pycache__`, run with `PYTHONDONTWRITEBYTECODE=1`, observe the failure, restore, confirm `git diff -- cli/` is empty. Report the observed failure output per pin. A test you did not watch fail is not evidence.
  - Beware four ways this has lied here: stale bytecode running the previous mutant; a mutation landing on a docstring rather than code; the original text being a **substring** of the mutant so the replace silently no-ops; and concurrent agents reverting each other.
- **Pin the rule, not today's value.** Assert against `tol` / `_GATE_STREAK_DAYS` / the constant, not a literal — except where an external anchor is mathematically required to pin a value (PR #162's lesson: `N >= N` is a tautology, so a literal pin is the only thing that can catch the constant drifting).
- **Do not touch the metadata-equality guard (D8)** — it looks redundant and is a provably equivalent mutant. It is the backstop for the keystone on the h4 grid.

______________________________________________________________________

## Task 1: the `concordance.py:118` conjuncts — the keystone and its siblings

**Files:** `tests/test_engine_concordance.py`.

The line is `if len(ts) != entry.n_bars or ts[0] != entry.first_ts or ts[-1] != entry.last_ts:`. Today's peek fixture violates two terms at once, so deleting any single one leaves the suite green.

- [ ] **Step 1 — the keystone (spec D2, test-list 1).** `test_same_length_peek_is_still_rejected`: build a cycle whose snapshot has the **same** `n_bars` and **same** `first_ts` as its journaled entry, but whose final bar is the in-progress candle so only `last_ts` differs. Assert `replay_cycle` raises `EngineJournalError`. Name it for what it defends — if this check is absent the builder runs on **lookahead data and the targets still compare equal**, which is silent contamination of the verdict, not a loud failure.
- [ ] **Step 2 — `n_bars` alone** (test-list 2): length differs, both timestamps match.
- [ ] **Step 3 — `first_ts` alone** (test-list 3): leading bar differs, length and `last_ts` match.
- [ ] **Step 4 — mutation-verify all three**, deleting **one conjunct at a time** from line 118. Each deletion must fail exactly its own test and leave the other two passing. That cross-check is the point: it proves the three cases are independent rather than three spellings of the same one.
- [ ] **Step 5** — `uv run pre-commit run -a`; commit `test(cli): pin each replay_cycle metadata conjunct independently`.

______________________________________________________________________

## Task 2: bracketed constants — tolerance and the day-cutoff anchor

**Files:** `tests/test_engine_concordance.py`.

- [ ] **Step 1 — tolerance, both sides (spec D3, test-list 4).** `compare_targets(a, b, *, tol=1e-6)` is exercised at ~1e-7 and 1e-2 today, leaving five orders of magnitude free — a divergence 120× over budget passes at `tol=1e-3`. Add a diff just **inside** `tol` that must pass and one just **outside** that must fail, both expressed relative to the `tol` argument.
- [ ] **Step 2 — day-cutoff anchor (test-list 6).** The intra-day test uses `now=09:00`, which is below *every* candidate anchor and therefore discriminates none. Add a case where `now` sits so that different anchors give **different** verdicts, so the test distinguishes them.
- [ ] **Step 3 — mutation-verify:** widen `tol` to `1e-3` (the outside-case must fail); shift the day-cutoff anchor by an hour (the new anchor case must fail).
- [ ] **Step 4** — gate + commit `test(cli): bracket the compare tolerance and the day-cutoff anchor`.

______________________________________________________________________

## Task 3: reachability and ordering — multi-pair, asset-set, last_failure

**Files:** `tests/test_engine_concordance.py`.

- [ ] **Step 1 — multi-pair calendar guard (spec D4, test-list 5).** Every `replay_cycle` test today uses one pair, so the guard needs ≥2 to execute at all — deleting it changes nothing in CI while production is multi-pair. Add a two-pair cycle whose pairs disagree on the calendar; assert it raises.
- [ ] **Step 2 — asset-set equality (test-list 7).** `compare_targets` over dicts of equal cardinality but different keys must not compare equal. Note the mutant raises `KeyError` rather than passing silently, so this pins an unreached path, not a silent-corruption one — say so in the test's comment so its severity is not over-read later.
- [ ] **Step 3 — `last_failure` is the most recent (spec D5, test-list 8).** Every failure test injects exactly one failure, so ordering is untestable as written. Inject two; assert the later.
- [ ] **Step 4 — mutation-verify:** delete the calendar guard; weaken asset-set equality to length equality; make `last_failure` keep the first rather than the last.
- [ ] **Step 5** — gate + commit `test(cli): reach the multi-pair guard, pin asset-set equality and last_failure ordering`.

______________________________________________________________________

## Task 4 (orchestrator, not a subagent): verification + closeout

- [ ] Confirm **no production file changed**: `git diff --stat develop..HEAD` touches `tests/` and `docs/` only (test-list 9).
- [ ] Re-run the full targeted set; confirm the pre-existing concordance tests still pass unchanged.
- [ ] Independently re-run at least the keystone mutation rather than trusting the subagent reports.
- [ ] Final whole-branch review.
- [ ] Closeout: iterations-history entry; [[T0076]] → `resolved` **only if** every finding is pinned and no live deferred sub-item remains — otherwise `partial` with the remainder named (the `open-topics` rule, and the mistake this branch's predecessor made by pre-writing "resolved"). PR into `develop`.

## Self-Review

- Spec coverage: D1/D2→Task 1; D3→Task 2; D4/D5→Task 3; D6/D7→every task's mutation step + Task 4's diff check; D8→a standing constraint, no task.
- Test-list 1–3→Task 1, 4+6→Task 2, 5+7+8→Task 3, 9→Task 4.
- Grounded: `concordance.py:118` (the three-conjunct disjunction), `compare_targets` signature at `:157` with `tol=1e-6` documented at `:159`, `_GATE_STREAK_DAYS` at `:28`, `evaluate_gate` returning `GateStatus(streak, gate_met, last_failure)` at `:239` — all verified present.
