# 00080 — T0098's three reach-review residuals: sibling cleanup, `PAIR_KEYS` home, seam dedup

**Goal:** close [[T0098]] in full, one iteration, no new topics (owner directive): (1) a rebuild builder that fails mid-run no longer strands an unretriable sibling, (2) `PAIR_KEYS` moves to its natural home in `cli/ohlc/`, killing the inverted import and the half-initialised-package trap, and (3) the byte-identical seam logic exists once — with sub-item 1 **re-specified against measurement**, because the topic's proposed detection signature is false for 2 of the 7 rebuild targets.

## Why now, and why the freeze no longer applies

T0098 parked sub-items 2+3 as "safe and small **after** the Stage-6a gate call". That call happened: **Stage 6a CLOSED 2026-07-30, verdict PASS** (`docs/research/14.phase6a-closeout.md`). The other half of the freeze doesn't bite either: the engine runs pinned at `e5a44e1cb138`, its container unrestarted since 2026-07-26T13:35:16Z, so nothing merged to `develop` reaches production before an attended post-return converge (D6). Owner approved all three on 2026-08-02.

## Current state, measured (all from this iteration's probes, 2026-08-02)

**Sub-item 1's premise is false for 2 of the 7 targets.** `REBUILDABLE` carries **seven** keys (measured by import, not by grep: `ohlc-full`, `ohlc-15m`, `ohlc-reach`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`). The topic asserts "a missing `manifest.json` is a reliable partial-run signature — every completed reach round writes one as its last act." True for **five** of them — the three `ohlc-*` targets plus `derivatives-funding` and `derivatives-oi`, each builder's last act writing `out_root/manifest.json`. **False for `snapshots`** (writes only `kraken-refdata-<UTC stamp>.json`) **and `universe`** (writes only `point-in-time-universe.json`; it *reads* the OHLC set's manifest, which is what makes a naive grep call it a writer). Any manifest-based cleanup or retry-replace would classify those two targets' *completed* siblings as partial garbage.

**The cleanup gap itself:** `rebuild_sets` (`cli/data/rebuild.py`) guards the failure path with `if not any(out_root.iterdir()): out_root.rmdir()` — a builder that wrote anything before raising strands the sibling, and the date-stamped name then trips the `sibling already exists` refusal on every same-day retry. The trigger has never fired: exactly one sibling exists on this machine (`data/ohlc-holdout-2026-07-10`), manifest present. The strand is untested — the existing test covers only the empty-sibling case.

**The duplication, diffed rather than remembered:**

- `_drop_in_progress` — the two bodies are **byte-identical** (`frame.filter((pl.col("ts") + pl.duration(minutes=interval)) <= now)`); only docstring wording differs.
- `MIN_SEAM_OVERLAP = 6` (`cli/ohlc/reach.py`) and `_SEED_MIN_OVERLAP = 6` (`cli/engine/store.py`) — deliberately equal; the coupling is admitted in a comment instead of shared.
- The guard blocks (`_merge_or_detach` vs `_reconcile`) **mirror but measurably diverge**: different exception types (`OHLCError` vs `EngineError`); test-pinned message prefixes on both sides (`seam too thin` / `seam mismatch` in `tests/test_ohlc_reach.py`, `shortfall` / `mismatch` asserted via `EngineError` in `tests/test_engine_store.py`); reach's mismatch message carries **both close values**, store's carries neither; reach has a detached branch store lacks; store has the `allow_replace` poisoned-tail path reach lacks.

**Import graph:** `cli/ohlc/__init__.py` does not import `reach`; `cli/engine/store.py` already imports `cli.ohlc.fetch`; four downstream sites import `PAIR_KEYS` from `cli.engine.store` (`cli/engine/cycle.py`, `cli/engine/soak.py`, the `cli/engine/__init__.py` re-export, tests).

## Decisions

**D1 — On builder failure, delete the entire just-minted sibling (`shutil.rmtree`), uniformly for all seven targets.** Inside that `except` block, every byte under `out_root` was written by the builder invocation that just raised: the exists-guard raised *before* `mkdir` if the dir pre-existed, so nothing foreign can be there — the "never delete builder output" caveat was protecting a dir the function didn't mint, which is unreachable past that guard. The handler catches `BaseException` and re-raises: an operator's Ctrl-C during the ~90 s paced round is the likeliest mid-build abort, and it must clean up exactly like a builder error (cold review's finding; a test pins it so nobody narrows the handler back). Deletion loses nothing: every builder fetches or derives from repeatable input (the most expensive, a reach round, re-fetches ~90 s of paced REST). This supersedes the empty-only `rmdir`, needs zero per-target machinery, and does not rest on the refuted manifest premise. Rejected: a per-builder completion-witness protocol — machinery whose only consumer is a case D1 already handles.

**D2 — The hard-kill residual is accepted, and the guard message names the remedy.** SIGKILL/power-loss skips the `except`, so a sibling can still strand. Rather than a witness protocol, the `sibling already exists` refusal gains one sentence telling the operator how to recognise a crashed run's leavings and clear them. This is runtime output of `cli/` — **in scope** for `operator-facing-text.md`, plain language, no internal tokens. A conscious drop, recorded here and in the code comment; no new topic.

**D3 — `PAIR_KEYS` relocates to `cli/ohlc/fetch.py`; the store imports and re-exports it.** It is Kraken-REST reference data (display asset → REST pair key) consumed to call `fetch_ohlc`, and both current users already import `fetch.py` — so no new module and no new import edge. All four `from cli.engine.store import PAIR_KEYS` sites keep working unchanged (the store still binds the name and uses it itself; `cli/engine/__init__.py`'s re-export is untouched). `cli/ohlc/reach.py`'s inversion comment plus the upward import (12 lines) are deleted; the transcription comment (snapshot-register provenance) moves with the dict; the "`cli/ohlc/__init__.py` must never import reach" trap **dissolves** because reach then imports only `ohlc` siblings.

**D4 — Extract exactly what is identical into a new `cli/ohlc/seam.py`; cross-link what is parallel-but-divergent.** Three names move:

- `MIN_SEAM_OVERLAP = 6` — the single constant (with reach's why-6 comment). `_SEED_MIN_OVERLAP` is deleted; its one use reads the shared name. Reach re-imports it, so `tests/test_ohlc_reach.py`'s existing import keeps working.
- `drop_in_progress` — the two identical bodies collapse to one public function.
- `seam_overlap(left, right) -> tuple[int, pl.DataFrame]` — the join-on-`ts` + close-comparison both guard blocks open with (inner join with `_rest` suffix, overlap count, `close != close_rest` filter). This is the **seam definition** — the piece a future safety fix (say, comparing more columns) must hit in both callers, which is exactly the drift risk T0098 registered.

The guards, messages, and merge policy stay local, each gaining a one-line cross-pointer naming its sibling. Full unification is **not** a pure refactor — the measured divergences above mean it would either change operator-visible, test-pinned messages or drop the close-values diagnostic. Rejected: parameterising `_reconcile` with an exception class + noun-phrase parameters to absorb `_merge_or_detach` — it cannot reproduce both message sets byte-identically and over-parameterises a two-caller function.

**D5 — Behaviour-neutrality is D3/D4's bar, proven rather than asserted.** The full suite passes identically before and after with zero edits to existing test assertions; every error message stays byte-identical (partly test-pinned); `zcrypto engine soak-check` produces byte-identical stdout + exit code before and after on the same local inputs. The baseline is already captured (pre-branch, at `develop`'s tip): the deterministic `NO VERDICT -- no journaled cycles found` path, exit 0 — this probes the CLI→soak→store **wiring**, not the arithmetic; the arithmetic is pinned by `tests/test_engine_soak.py`'s fixtures. New behaviour exists only in D1's cleanup path, which is TDD'd.

**D6 — No deploy in this iteration; the exposure window is the next attended engine converge.** Merging to `develop` cannot reach the pinned engine. The refactor touches `cli/engine/store.py` and `cli/engine/soak.py`'s import path — the instrument that reads the ~40-day soak at the go/no-go — so the converge session must know it ships this change: recorded in the memo tail at completion, together with the T0098 queue item's completion move — an orchestrator edit in the main loop, never staged (the memo is gitignored).

## Non-goals

- No completion-witness protocol for the hard-kill strand (D2's message is the whole mitigation).
- No unification of the guard/merge blocks beyond `seam_overlap` (D4's measured reasons).
- No change to seam semantics, overlap thresholds, message texts, or any CLI surface (hence no README change).
- No new topics (owner directive); the residual is D2's conscious drop.

## Verification

Each guard proven by constructing its defect — the last three iterations' reviews found a combined ~19 guards that could not fail.

- **The strand reproduces first**: a builder that writes files then raises must leave the sibling behind under *current* code (the new test FAILS before the fix), then the fix flips it — sibling gone, the builder's exception propagates unchanged, a same-day retry succeeds.
- The existing empty-sibling test keeps passing unmodified (`rmtree` covers the empty case).
- The exists-guard still refuses a genuinely completed sibling; its test pins the extended message.
- **Single-definition greps**: exactly one `def drop_in_progress`, one `PAIR_KEYS: dict` binding, one `MIN_SEAM_OVERLAP =` binding repo-wide.
- **Mutation-proof on the extraction**: corrupt `seam_overlap`'s comparison (e.g. compare `open` instead of `close`) → the pinned mismatch tests fail in **both** `tests/test_ohlc_reach.py` and `tests/test_engine_store.py`, proving both callers actually route through the shared definition; restore, re-run green.
- Suite + soak-check identity per D5; `tests/test_internal_terms_not_operator_visible.py` green over D2's new message literal.

## Risks

- This refactor touches the soak instrument's import path weeks before that instrument's verdict matters (D6). Mitigated by D5's identity proofs and untouched fixtures; the residual (a defect the suite and the wiring probe both miss) is the same residual every green-suite refactor carries.
- `rmtree` in the failure path deletes what a debugging session might have wanted to inspect. Accepted: the builder's exception is the debugging surface, and the topic itself frames the strand as a papercut demanding manual `rm -rf` — deletion *is* the desired outcome.
- A future additional rebuild target inherits D1's cleanup for free, but also its assumption that builder output is repeatable; a builder consuming unrepeatable input (none exists today) would need its own protection. Named in the code comment.
