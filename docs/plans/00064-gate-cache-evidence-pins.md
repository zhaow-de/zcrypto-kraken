# Gate-cache evidence pins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make [[T0075]]'s 19 gate-cache guarantees fail when broken (spec `00064`).

**Architecture:** Tests only, in `tests/test_engine_gate_cache.py` and `tests/test_engine_gate_export_cache.py`, plus one comment-only docstring correction in `cli/engine/gate_cache.py`. No behaviour change anywhere.

**Tech Stack:** Python 3.14, pytest.

## Global Constraints

- **No behaviour change (D7).** `cli/engine/gate_cache.py`'s only permitted edit is the `_REPLAY_CODE_PATHS` docstring label; `cli/engine/command.py` and every other production file must be byte-identical at the end. If a pin cannot be written without changing production code, **stop and report it** — that is a finding, not a licence to change the cache.
- **Every pin is mutation-verified under bytecode control (D8).** For each: apply the mutation, **`grep` the file to confirm the edit landed**, purge `__pycache__`, run with `PYTHONDONTWRITEBYTECODE=1`, observe the failure, restore, confirm `git diff -- cli/` is empty. Report the observed failure output per pin. **A test you did not watch fail is not evidence.**
  - Five ways this has lied in this repo: stale bytecode running the previous mutant; a mutation landing on a docstring rather than code; the original text being a **substring** of the mutant so the replace silently no-ops; concurrent agents reverting each other; and a triage ruling generalised from one non-distinguishing input.
- **An evidence-key field is pinned by a stale HIT, never by field presence (D2).** A test asserting a field "appears in the digest" passes against a fingerprint that ignores it. Construct the tamper; assert the cache **misses**.
- **Pin the general guarantee, not the instance that prompted it.** That is the defect T0075 describes. Assert the full `_REPLAY_CODE_PATHS` tuple, not four more membership lines.
- **Reuse `_counted_replay_cycle`** (`tests/test_engine_gate_export_cache.py:119`) wherever attribution matters — it asserts *which* `cycle_ts` was replayed, identity rather than count, and the audit found that pattern caught all 9 same-typed swaps.

______________________________________________________________________

## Task 1: the fingerprint's inputs — module list and replay path

**Files:** `tests/test_engine_gate_cache.py`; `cli/engine/gate_cache.py` (docstring only).

Findings 1–4 (four original modules droppable), 18 (`_EVALUATE_JOURNAL_REPLAY_PATH` coupling), and the D7 docstring correction.

- [ ] **Step 1 — full-tuple pin (spec D1, test-list 1).** Assert the **complete** `_REPLAY_CODE_PATHS` tuple — all ten paths, exact and ordered — so removing *any* entry fails, including one added later. Do **not** add four membership lines for the four originals; that repeats the fix-the-instance defect this whole topic is about.
- [ ] **Step 2 — fingerprint responds to each original module's bytes (test-list 2).** For each of `crossfreq_system.py`, `crossfreq.py`, `limits.py`, `concordance.py`: monkeypatch the list at synthetic files (the existing tests already do this — follow that pattern, never mutate real repo source), edit the file's bytes, assert `replay_fingerprint` changes.
- [ ] **Step 3 — replay-path coupling (finding 18, test-list 12).** Assert `replay_fingerprint(path="fast") != replay_fingerprint(path="verified")`.
- [ ] **Step 4 — docstring correction (spec D7).** In `_REPLAY_CODE_PATHS`, the four modules labelled "LATENT — only reachable on the verified route" are imported at module scope by `cli/portfolio/crossfreq_system.py:53-56` (`a1`, `a2`, `strategies`, `builder`), so they are **live on the fast route**. Correct the label to say so. Comment-only — verify `git diff` shows no executable line changed.
- [ ] **Step 5 — mutation-verify:** delete each of the four originals from the tuple in turn (Step 1 must fail each time); drop `path` from the digest (Step 3 must fail).
- [ ] **Step 6** — `uv run pre-commit run -a`; commit `test(cli): pin the full replay-code module list and the replay-path coupling`.

______________________________________________________________________

## Task 2: the evidence key — five fields, each pinned by a stale hit

**Files:** `tests/test_engine_gate_cache.py`.

Findings 5, 6, 7, 8, 10 — the audit proved a stale PASS end-to-end for all five, so each exploit already exists and needs only encoding.

- [ ] **Step 1 — `first_ts` and `last_ts` (test-list 3).** Tamper each in a journaled `SnapshotEntry`, assert `evidence_fingerprint` changes and the cache **misses**.
- [ ] **Step 2 — `pair` and `grid`, order-preserving (spec D3, test-list 4).** Entries are digested in canonical `(pair, grid)` order, so an order-*changing* tamper is masked by the sort — that masking is exactly what fooled Audit A into ruling these equivalent. Use `ETH`→`FTH` and `1440`→`1441`, which preserve sort position. **State that reason in the test's comment**, or the next reader simplifies it back into a vacuous pin.
- [ ] **Step 3 — `path` (test-list 5).** Repoint one entry at another pair's parquet; assert a miss.
- [ ] **Step 4 — mutation-verify:** drop each of the five fields from `evidence_fingerprint` in turn; each must fail exactly its own test and leave the other four passing. That cross-check is the point — it proves five independent pins rather than five spellings of one.
- [ ] **Step 5** — gate + commit `test(cli): pin each evidence-key field by a stale cache hit`.

______________________________________________________________________

## Task 3: fail-open and robustness — the corrupt-input paths

**Files:** `tests/test_engine_gate_cache.py`, `tests/test_engine_gate_export_cache.py`.

Findings 9, 11, 14, 15, 16, 17.

- [ ] **Step 1 — the corrupt-journal keystone (spec D4, test-list 6).** An unparseable `cycle-*.json` scored as a clean pass flips a 14-day journal from `gate_met=False` to `gate_met=True` with `last_failure=None`. Assert at **journal level**: `gate_met` stays `False` and `last_failure` is set — not merely that the cycle classified as a failure. Name the test for what it defends: this is the one finding where the failure mode is *the gate opening on corrupt input*.
- [ ] **Step 2 — one malformed row inside a valid `entries[]` (test-list 7).** Every existing fail-open test corrupts the file *before* the entry loop; this is the single path where "discard the file" and "skip the bad row" diverge. Assert wholesale invalidation.
- [ ] **Step 3 — schema gate, for the right reason (spec D6, test-list 8).** The existing v1 test passes via a `KeyError` fallback rather than the version check — fix it to fail for the right reason, then add a **lower** `schema_version` case (currently accepted). A test passing for the wrong reason reports coverage that does not exist.
- [ ] **Step 4 — never-raise (spec D5, test-list 9).** `load_cache` and `save_cache` must not raise: malformed JSON, wrong top-level type (e.g. a list), and the `TypeError` arm reachable via `sorted()` on mixed key types. Assert a clean miss, not an exception.
- [ ] **Step 5 — vanished record evicted (finding 17, test-list 11).** A cache entry whose record no longer exists must not be retained — retention poisons `oldest_verification_age` permanently.
- [ ] **Step 6 — mutation-verify:** make the parse failure score as a pass (Step 1 must fail); make the entry loop skip bad rows (Step 2); flip the schema check to `<` and to `!=`-via-`KeyError` (Step 3); make each of `load_cache`/`save_cache` raise (Step 4); retain vanished entries (Step 5).
- [ ] **Step 7** — gate + commit `test(cli): pin the cache's fail-open and corrupt-input guarantees`.

______________________________________________________________________

## Task 4: counters and attribution

**Files:** `tests/test_engine_gate_export_cache.py`.

Findings 12, 13, 19.

- [ ] **Step 1 — `mismatches` counts a real compare failure (finding 12, test-list 10).** The mutant makes `zcrypto_gate_mismatch_total` read 0 during a genuine mismatch — a metric asserting "all clear" while the gate is mismatching, which is why this is MED-HIGH rather than MEDIUM.
- [ ] **Step 2 — `replayed_ok` does not count a failed cycle (finding 13).**
- [ ] **Step 3 — `EngineJournalError` attribution (finding 19, test-list 13).** `_replay_one`'s exception→verdict classifier is not covered by the attribution pattern the audit called airtight. Pin it with `_counted_replay_cycle`'s identity assertion — assert *which* `cycle_ts` produced the error, not how many did.
- [ ] **Step 4 — mutation-verify:** make `mismatches` stop counting compare failures; make `replayed_ok` count a failed cycle; misclassify `EngineJournalError` as `mismatch`.
- [ ] **Step 5** — gate + commit `test(cli): pin the gate-export counters and error attribution`.

______________________________________________________________________

## Task 5 (orchestrator, not a subagent): the D9 research question

Not a code task — produce evidence and a recommendation, no spec edit.

- [ ] Trace whether a change in `cli/engine/command.py` (`_replay_one`'s exception→verdict mapping — the sole classifier — and `_snapshot_reader`) or `cli/ohlc/dataset.py` (`read_parquet`, feeding both the content hash and the builder) can alter a replay verdict **without altering any currently-hashed byte**. A concrete such change is the evidence; its absence is also a result.
- [ ] Adopting either edits ratified spec `00060` D3 (which fixes the list at ten modules), so **present the finding and a recommendation — do not change the spec**. Record it in the PR description and as a [[T0075]] sub-item.

## Task 6 (orchestrator): verification + closeout

- [ ] Confirm the only production change is the docstring: `git diff develop..HEAD -- cli/` shows the `_REPLAY_CODE_PATHS` comment and nothing else (test-list 14).
- [ ] Re-run the full targeted suites; confirm the pre-existing gate-cache tests pass unchanged.
- [ ] **Independently re-run at least the D4 keystone and one D2 stale-hit mutation** rather than trusting the subagent reports — the audit that produced this plan exists because reported results were wrong.
- [ ] Final whole-branch review on the most capable model.
- [ ] Closeout: iterations-history entry; [[T0075]] → `resolved` **only if** all 19 are pinned and no live deferred sub-item remains — the D9 ruling is a live sub-item, so if it is still open the topic is `partial` with D9 named as the remainder (split it into its own topic if it needs its own `ripe_when:`). PR into `develop`.

## Self-Review

- Spec coverage: D1/D7→Task 1; D2/D3→Task 2; D4/D5/D6→Task 3; D8→every task's mutation step + Task 6; D9→Task 5. Findings 1–4,18→T1; 5–8,10→T2; 9,11,14,15,16,17→T3; 12,13,19→T4. All 19 mapped.
- Test-list 1–2+12→T1, 3–5→T2, 6–9+11→T3, 10+13→T4, 14→T6.
- Grounded: `_REPLAY_CODE_PATHS` at `gate_cache.py:54` (ten paths, LIVE/LATENT labels at :55/:62), `load_cache` at :186, the schema check at :196, `save_cache` at :211, `_replay_one` at `command.py:171`, `replayed_ok`/`mismatches` at `command.py:266-267`, `_counted_replay_cycle` at `test_engine_gate_export_cache.py:119`, and the module-scope imports at `crossfreq_system.py:53-56` — all verified present. (Post-hoc: the module-scope import was verified present but is NOT a sound basis for the LIVE label — see spec D7's correction; `_REPLAY_CODE_PATHS` now holds twelve paths, not ten, after D9.)
