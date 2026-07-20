# Spec 00060 — gate-export incremental scoring (T0069's structural fix)

## Goal

Bound `zcrypto engine gate-export`'s per-run cost by the journal's **new tail** instead of its whole history, so the hourly archive-pull step stops re-verifying work it already verified.

## Why (measured, iter-109)

`_evaluate_journal` calls `replay_cycle` **once per journaled cycle**, and each replay runs a full ~28k-bar, 10-asset, 12-year strategy rebuild. Profiling attributes **81%** of the run to `build_crossfreq_system_fast` (39 calls, 120.6 s cumulative). Cost is **O(n)** at ~1.60 s/cycle on the ops i7 and ~10.9 s/cycle on the NAS Atom — so every hour the NAS re-replays the entire append-only, hash-verified journal from scratch. Linear on an unbounded input is still a deadline: the "~20 min wall" trigger projects to ≈2026-07-29, 50% of the 3600 s pull interval to ≈2026-08-07, 100% to ≈2026-09-04.

`replay_cycle` depends **only on that cycle's own journaled snapshots** (verified by reading it: validate → hash-verify → build → read the forming row), with no cross-cycle state; `evaluate_gate` then does cheap streak arithmetic over the resulting `CycleOutcome`s. So a per-cycle cache is structurally sound.

## Decisions

- **D1 — opt-in via `--cache PATH`; default behavior unchanged.** No cache path ⇒ today's full replay, byte-for-byte. This keeps `report` (a human-facing *verification* tool, which should genuinely re-verify) and every existing invocation untouched, and makes enabling the cache an explicit, attended deployment step. The cache is **not** written into the journal tree — the journal is an append-only archive and must not be polluted.

- **D2 — the cache maps a cycle to its outcome, keyed by an evidence fingerprint.** Entry key = `cycle_ts`; stored alongside it: the cycle's **evidence fingerprint** and the `CycleOutcome` fields. The evidence fingerprint is derived from the record's own journaled `SnapshotEntry` values **in full** — `pair`, `grid`, `n_bars`, `first_ts`, `last_ts`, `content_hash`, `path`, for every entry, in a canonical order — plus `cycle_ts`, `completed_at`, and the record's `final_targets` — i.e. everything a replay's verdict depends on from the journal side. The full entry, not just `content_hash`, because `replay_cycle` also reconciles freshly read data against `n_bars`/`first_ts`/`last_ts` and raises `EngineJournalError` on disagreement — a `content_hash`-only fingerprint would let a cached PASS survive a metadata tamper the real replay would reject. A cache entry is used **only** when the recomputed fingerprint matches exactly; otherwise the cycle is replayed and the entry replaced.

- **D3 — the fingerprint also covers the REPLAY CODE, not just the journal.** *(Review catch from iter-109; module list widened in a follow-up fix wave.)* A journal-only hash detects journal-side change but **not** a change to the replaying code: revise `build_crossfreq_system_fast` or `CrossfreqSystemConfig` and a journal-keyed cache would keep serving stale pre-change outcomes forever, since the price data and therefore its hash are unchanged. The cache therefore carries a **replay fingerprint** — a digest over the source bytes of the modules that determine a replay's result, the effective `CrossfreqSystemConfig`, and the replay path (below) — stored once per cache file. **A mismatch invalidates the entire cache**, not one entry. This is deliberately **over-sensitive** (a comment-only edit costs one full rebuild): over-invalidation is safe, under-invalidation silently corrupts gate evidence.

  **AMENDED by specs `00064` D9 and `00065` (2026-07-20).** As originally written this decision named its coverage — *"the modules that determine a replay's result"* — and then delivered a hand-enumerated list that never matched it. The list was wrong **three times**: 4 modules originally, +6 at the iter-109 review, +2 at `00064` D9, and still missing the ancestor packages every replay executes. Measured at the end: the twelve-path list covered 12 of the 61 modules that actually run — about 20%. Each round added the file someone had just noticed and restated this sentence as true, which is exactly why nobody re-checked it.

  **The wording was the defect, not just the list.** A spec sentence asserting completeness is unfalsifiable prose; it invites every later reader to assume the check exists. Coverage is now *derived* — the transitive `cli.*` import closure of three roots (`00065` D1) — and, more importantly, *measured*: `test_closure_covers_every_module_the_replay_roots_actually_execute` imports the roots in a clean subprocess and asserts the closure is a superset of what actually executed. **That test is the invariant; this paragraph only describes it.** If the two ever disagree, believe the test.

  The covered modules, split by whether they are reachable on the `path="fast"` route `_evaluate_journal` actually uses:
  - **LIVE** (fast route): `cli/portfolio/crossfreq_system.py`, `cli/portfolio/crossfreq.py`, `cli/risk/limits.py`, `cli/risk/governor.py` (the §10 drawdown governor `crossfreq.py` calls and folds into `final_targets`), `cli/engine/concordance.py`, `cli/engine/journal.py` (`validate_record`/`snapshot_content_hash`, called directly by `replay_cycle`).
  - **LATENT** (only reachable on the `path="verified"` route, `build_crossfreq_system`): `cli/alpha/a1.py`, `cli/alpha/a2.py`, `cli/portfolio/builder.py`, `cli/benchmark/strategies.py`. Covered anyway per the over-invalidation-is-safe rationale above, even though no caller passes `path="verified"` today.

  The fingerprint also folds in the **replay path itself** (`"fast"` vs `"verified"` select different builders): a route switch must not serve the other route's cached verdicts. Implemented as a `replay_fingerprint(config, *, path="fast")` parameter threaded from the caller (`_evaluate_journal` always passes `"fast"`, matching `_replay_one`'s hardcoded route) rather than folded into the per-entry cache key — the whole cache is scoped to one replay route, consistent with how the module list and config are already scoped to the whole cache file, not per entry.

- **D4 — a cache hit must be indistinguishable from a fresh replay.** The cached `CycleOutcome` must equal what a replay would produce, field for field. This is the load-bearing correctness property and is pinned by a test that replays a journal twice — once cold, once warm — and asserts the resulting `CycleOutcome` lists and the final `evaluate_gate` status are **equal**, not merely similar.

- **D5 — fail open, never fail trusting.** Any cache problem — unreadable/corrupt/unparseable file, schema mismatch, missing fields — degrades to a **full replay** and rewrites the cache; it never aborts the run and never serves a partially-trusted entry. A cache is an optimization; gate evidence is not.

- **D6 — the cache is written atomically and only on success.** Write to `<path>.tmp` then `os.replace`, after the run's outcomes are complete, mirroring the existing textfile discipline. A crashed run leaves the previous cache intact rather than a truncated one.

- **D7 — sidecars and absent boundaries are not cached.** `failed-cycle-*.json` sidecars are already cheap (a small JSON read, no rebuild) and absent boundaries are scored by `evaluate_gate` from what is present. Only the expensive path — a success record's `replay_cycle` — is cached. This keeps the cache's semantics narrow and its invalidation surface small.

- **D8 — observability.** `gate-export` emits the cache outcome as Prometheus metrics alongside the existing gate metrics: cycles replayed this run, cycles served from cache, and whether the cache was invalidated wholesale. Without this, a silently-degrading cache (e.g. a fingerprint that changes every run) would look like a working one while delivering no speedup.

## Non-goals

- Not the **relocation** to the ops node (spec `00054` D6, still parked in [[T0069]] as an attended deploy). This change is complementary: relocation buys a constant ~6.8×, incremental scoring bounds the cost regardless of growth.
- No change to `evaluate_gate`'s streak arithmetic, the gate definition, `report`'s behavior, or the journal format.
- Not a cache for `report` — it should keep re-verifying.

## Test list (TDD)

1. **D4 keystone — warm equals cold.** Run `_evaluate_journal` over a synthetic journal with no cache, then with a cache (cold, then warm); assert the `CycleOutcome` lists are **equal** and `evaluate_gate` yields an equal status. A cache hit that differs in any field fails.
2. **Only new cycles are replayed.** With a warm cache, appending one cycle replays exactly one (assert via a counted/monkeypatched `replay_cycle`), not the whole journal.
3. **Tampered evidence misses the cache.** Mutating a record's `content_hash`/`final_targets`/`completed_at` after caching forces a replay for that cycle and does not serve the stale entry.
4. **D3 — a replay-code change invalidates the whole cache.** With a warm cache, a changed replay fingerprint causes every cycle to be replayed and the cache rewritten (pinned by injecting a different fingerprint, so it fails if the fingerprint is journal-only).
5. **D5 — corrupt/unreadable cache degrades, never aborts.** Truncated JSON, wrong schema, and an unreadable path each fall back to a full replay with the correct outcomes.
6. **D1 — no `--cache` means byte-identical current behavior** (no file created, same outcomes).
7. **D6 — atomicity:** the cache file is replaced, not appended/truncated in place; a failure before completion leaves the prior cache readable.
8. **Mismatch/validation-failure outcomes cache correctly** — a cycle whose replay yields `mismatch` or `validation_failed` round-trips through the cache with the same classification (a cached failure must not silently become a pass).
9. **D8 — the new metrics appear** in the textfile with plausible values (replayed + cached counts sum to the success-record count).
10. **Real-journal speedup (data-gated):** on the ops mirror, a cold run then a warm run produce identical gate status, and the warm run replays 0 cycles. Verified manually on the ops journal mirror (iter-110; figures recorded in [[T0069]]: no-cache 63.11 s, cold 62.77 s, warm 0.30 s, identical gate metrics across all three) and deliberately **not committed** as a test -- no journal mirror is committed to the repo, so a data-gated test for this would always skip in CI.
