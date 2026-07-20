# Replay-fingerprint import closure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make `replay_fingerprint`'s coverage structural — the transitive `cli.*` import closure of three roots, not a hand-maintained list (spec `00065`, [[T0080]]).

**Architecture:** `cli/engine/gate_cache.py` gains a closure walker; `_REPLAY_CODE_PATHS` (12 hand-listed paths) becomes `_REPLAY_ROOTS` (3). Tests move from pinning the list to pinning the guarantee.

**Tech Stack:** Python 3.14, `ast`, pytest.

## Global Constraints

- **No change to what a replay computes.** `replay_cycle`, `compare_targets`, `evaluate_gate`, the journal format, and every threshold are untouched. Only what gets digested changes.
- **Deterministic (spec D4).** Sorted repo-relative path order. An unstable digest rebuilds the cache every run — which looks exactly like a working cache while doing no work, so it must be pinned, not assumed.
- **Digest unconditionally; traverse best-effort (spec D6).** A module that fails to parse still contributes its bytes. Never let an AST failure silently drop a file from coverage — that is the under-invalidation this whole topic is about.
- **Never raises to the caller (spec D8 / `00060` D5).** A missing or unreadable module degrades the run to the no-cache path, logged. Gate evidence outranks the cache.
- **Every pin mutation-verified under bytecode control.** `PYTHONDONTWRITEBYTECODE=1`, purge `__pycache__`, `grep` the mutation on disk, observe the failure, restore, confirm `git diff -- cli/` clean. A test you did not watch fail is not evidence.
- **The measured baseline is 61 modules / ~59 ms** from roots `concordance.py` + `command.py` + `dataset.py`. A large deviation means the walk is wrong — investigate before proceeding. *(Was 54 as first written; that figure predates D10's ancestor fix. Corrected at final review — an unchecked instruction to verify a stale number would have a later worker measure 61 and conclude the walk is broken.)*

______________________________________________________________________

## Task 1: the closure walker

**Files:** `cli/engine/gate_cache.py`; `tests/test_engine_gate_cache.py`.

- [ ] **Step 1 — write the failing tests first** for a `_replay_code_paths()` helper: it returns sorted paths; it contains all twelve previously-listed modules; it contains `cli/portfolio/__init__.py`, `cli/risk/__init__.py`, `cli/alpha/__init__.py`, `cli/engine/errors.py`; it excludes non-`cli` modules (test-list 3, 9).
- [ ] **Step 2 — implement the walker.** Roots as `_REPLAY_ROOTS` (3 paths). AST-parse each file, collect `Import`/`ImportFrom` names whose first segment is `cli`, resolve each to candidate files, recurse. **D5:** `from cli.pkg import X` resolves to BOTH `cli/pkg/__init__.py` and `cli/pkg/X.py` when the latter exists — that is the case the old list missed. Return sorted.
- [ ] **Step 3 — D6 correctness.** The parse is inside `try`, but the file's bytes are digested regardless. Write the test that proves it: a syntactically broken module inside the closure still changes the fingerprint when edited (test-list 7).
- [ ] **Step 4 — wire into `replay_fingerprint`**, replacing the `_REPLAY_CODE_PATHS` loop. Keep every other digested input exactly as-is: config, `path`, numpy version, `sys.version_info[:2]`. Update the docstring — it currently characterises a fixed module list.
- [ ] **Step 5 — pin the roots** as an exact three-entry tuple (test-list 1). Same whole-tuple discipline as `00064` D1: the roots are now the only hand-maintained input, so they are the only thing that can silently drift.
- [ ] **Step 6 — mutation-verify:** drop a root (the contains-test must fail); drop the `__init__.py` resolution from D5 (the re-export-layer contains-test must fail); return unsorted (determinism must fail).
- [ ] **Step 7** — `uv run pre-commit run -a`; commit `feat(cli): derive replay-fingerprint coverage from the import closure`.

______________________________________________________________________

## Task 2: the guarantee pins

**Files:** `tests/test_engine_gate_cache.py`.

The old exact-tuple pin cannot survive — there is no tuple. These replace it, and **the exploit test is the real guarantee**; the closure is only today's implementation of it.

- [ ] **Step 1 — the exploit (spec D7-ii, test-list 2).** Rebinding `build_crossfreq_system_fast` to `build_crossfreq_system` in `cli/portfolio/__init__.py` must change `replay_fingerprint`. Work on a **copy** of the tree under `tmp_path` with `_REPLAY_ROOTS`/repo-root monkeypatched — never mutate real repo source in a test. Name it for what it defends. Comment that this exact edit was byte-identical before spec `00065`, with 31 tests green.
- [ ] **Step 2 — determinism (test-list 4, 5).** Repeated calls agree; a fresh subprocess agrees; the result is independent of `cwd`. Then verify the sorted order is load-bearing by mutating the walker to return unsorted.
- [ ] **Step 3 — D5 resolution (test-list 6).** A synthetic package where `from cli.pkg import X` must pull in both `__init__.py` and `X.py`.
- [ ] **Step 4 — never-raises (test-list 8, spec D8).** A missing root and an unreadable module each degrade rather than propagate. Assert the caller's no-cache degrade path, matching how `00060` D5 is already pinned.
- [ ] **Step 5 — remove the superseded exact-tuple test**, and say in the commit body why it is *replaced* rather than deleted: it pinned an enumeration that no longer exists, and its guarantee is now carried by Steps 1–3. A reviewer must be able to see the coverage did not silently shrink.
- [ ] **Step 6 — mutation-verify each** of the above; report the observed failure per pin.
- [ ] **Step 7** — gate + commit `test(cli): pin the fingerprint's coverage by exploit, not by enumeration`.

______________________________________________________________________

## Task 3 (orchestrator): verification + closeout

- [ ] Re-run **at least the exploit mutation** independently rather than trusting the subagent report.
- [x] Confirm the closure is **61** modules / ~59 ms; a large deviation means the walk is wrong. Verified: 61 covered, 60 executed, 0 executed-but-uncovered.
- [ ] Full suite; confirm `00064`'s 19 pins are unaffected (test-list 10).
- [ ] Amend ratified spec `00060` D3 — its wording is the origin of three rounds of this defect. It must now say the coverage is derived, not enumerated.
- [ ] Final whole-branch review on the most capable model.
- [ ] Closeout: iterations-history entry; [[T0080]] → `resolved` (option 2 chosen and implemented); [[T0075]] → `resolved` (D9 was its last live sub-item; T0080 was split out, so nothing live remains inside it). PR into `develop`, noting the **single** cold rebuild the fleet pays.

## Self-Review

- Spec coverage: D1→T1S5; D2→T1S2; D3→T1S1; D4→T2S2; D5→T1S2+T2S3; D6→T1S3; D7→T2S1-3; D8→T2S4; D9→T3 (PR note). Test-list 1→T1S5, 2→T2S1, 3+9→T1S1, 4+5→T2S2, 6→T2S3, 7→T1S3, 8→T2S4, 10→T3.
- Grounded: `_REPLAY_CODE_PATHS` at `gate_cache.py:54` (twelve paths after `00064` D9), `replay_fingerprint`'s digest loop at :86, `concordance.py:24` importing the fast builder from `cli.portfolio` (the exploit's mechanism), and the measured baseline (54 modules / 58.6 ms as first written; **61 / ~59 ms** after D10 corrected the ancestor gap) — all verified present.
