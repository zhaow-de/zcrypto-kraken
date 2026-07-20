# Spec 00064 — pinning the gate-evidence cache's invalidation guarantees (T0075)

## Goal

Make [[T0075]]'s **19** gate-cache guarantees fail when broken. No behaviour change: an 80-mutation re-audit found **no live defect** — the cache invalidates correctly today. What is missing is any test that notices when it stops.

## Why

`gate_cache.py` caches **gate evidence** — the artifact deciding whether the strategy may trade real money. Its design is deliberately over-sensitive because the error costs are asymmetric: over-invalidation costs one rebuild, under-invalidation silently serves a stale PASS. That asymmetry holds only while the invalidation triggers are enforced by tests, and 19 of them are not.

Three things from the re-audit shape this spec more than the individual findings:

- **Every gap is under-invalidation.** Not one mutation that made the cache *more* eager to rebuild survived undetected. The existing tests were written by someone checking the cache does not thrash; nobody checked it does not go stale. Same asymmetry the concordance audit found (`00063`), independently.
- **The scope grew 8 → 19 through triage error, not measurement error.** Audit A ruled `pair`/`grid` equivalent because the entry sort key masks the tamper — true only for an *order-changing* tamper. An order-preserving rename defeats it. **An equivalent-mutant ruling is a universal claim**, and this spec treats one as a finding to disprove, not a conclusion to reuse.
- **The audit also named what already works.** The attribution category caught all 9 same-typed swaps because `_counted_replay_cycle` asserts *which* `cycle_ts` was replayed — identity, not count. That is the direct antidote to what failed in iter-111, and it is the pattern to reuse rather than reinvent.

## Decisions

- **D1 — the module list is pinned as a whole, not per module.** Findings 1–4 are four modules droppable from `_REPLAY_CODE_PATHS`; the six added at review are pinned by an explicit membership assertion and the four originals are not. Do **not** add four more membership lines — assert the **full tuple**, so removing *any* entry fails, including one added next year. The current fix-the-instance habit is precisely the defect T0075 describes.

- **D2 — an evidence-key field is pinned by a stale *hit*, never by field presence.** Findings 5–8 and 10 (`first_ts`, `last_ts`, `pair`, `grid`, `path`). A test asserting "the field appears in the digest" passes against a fingerprint that ignores it. Each pin constructs the realistic tamper and asserts the cache **misses** — the audit proved a stale PASS end-to-end for all five, so the exploit already exists and needs only encoding.

- **D3 — `pair` and `grid` need an order-PRESERVING tamper specifically.** These two are the mis-triaged pair, and the reason matters for the test: entries are digested in canonical `(pair, grid)` order, so an order-*changing* tamper is masked by the sort and would make the pin vacuous in exactly the way Audit A was fooled by. Use a rename that preserves sort position (`ETH`→`FTH`, `1440`→`1441`). **Write the reason in the test**, or the next reader "simplifies" it back to a masked tamper.

- **D4 — finding 9 gets the loudest test on the branch.** An unparseable `cycle-*.json` scored as a clean pass flips a 14-day journal from `gate_met=False` to `gate_met=True` with `last_failure=None`. It is the only finding whose failure mode is *the gate opening on corrupt input* — a strictly worse shape than a stale hit, which at least served a verdict that was once true. Name the test for what it defends and assert the journal-level outcome (`gate_met`), not just the per-cycle classification.

- **D5 — fail-open guarantees are pinned by the exception, not the outcome.** Findings 15/16: D5 of spec `00060` says `load_cache` never raises, and only `OSError` is pinned. Pin the general claim — malformed JSON, wrong top-level type, and the `TypeError` arm reachable via `sorted()` on mixed keys — asserting a clean miss rather than a raise.

- **D6 — the schema gate is currently passing for the wrong reason.** Finding 14: the v1 test passes via a `KeyError` fallback, not the version check, so the check itself is unpinned and a *lower* `schema_version` is accepted. Fix the existing test to fail for the right reason **and** add the lower-version case. A test passing for the wrong reason is worse than a missing one — it reports coverage that does not exist.

- **D7 — test-only, with ONE exception.** No change to `gate_cache.py` behaviour. The exception is the `_REPLAY_CODE_PATHS` **docstring**: it labels `a1.py`/`a2.py`/`builder.py`/`strategies.py` "LATENT — verified route only", but `crossfreq_system.py:53-56` imports all four at module scope, so they are live on the fast route. Comment-only, no behaviour change. It is in scope because the false label invites a future cleanup to drop them from the list — the same false-artifact class this audit was chasing.

  **D7 CORRECTED at review — this decision as first written was itself wrong, in the same class it set out to fix.** Two errors: (i) it claimed all four are live on the fast route, but only `a1.py` is — `build_crossfreq_system_fast` calls `_asset_returns` (`a1.py:176`) at `crossfreq_system.py:617`, and the fast helpers call it at `:475/:505/:537`; `a2_book_returns`/`sma_gate`/`vol_target`/`dynamic_inverse_vol_basket`/`build_combined_system` are reached only from `build_crossfreq_system` at `:215-276`, the *verified* route, because the fast helpers at `:469+` re-implement that arithmetic locally and bit-identically. (ii) More importantly, **"imported at module scope" was never a sound justification at all** — import-time execution binds `def` statements; it does not make a function body determine a replay's result. The three genuinely-uncalled modules are covered by D3's over-invalidation-is-safe rationale, not by the import. So the original "LATENT" label was *correct* for those three and wrong only for `a1.py`; this spec replaced one false label with another and would have licensed exactly the future misjudgement D7 exists to prevent. `a1.py` is promoted on merit; the other three keep the D3 justification, stated as D3.

- **D8 — every pin is mutation-verified under bytecode control.** `PYTHONDONTWRITEBYTECODE=1`, purge `__pycache__`, `grep` the file to confirm the edit landed, assert baseline-green, observe the failure, restore, confirm `git diff -- cli/` clean. Five ways this has lied here: stale bytecode; a mutation landing on a docstring; the original text being a **substring** of the mutant so the replace silently no-ops; concurrent agents in a shared tree reverting each other; and — new from this audit — **a triage ruling generalised from a single non-distinguishing input**.

- **D9 — the `command.py` / `dataset.py` hashing question is researched, not decided.** `_replay_one`'s exception→verdict classifier and `cli/ohlc/dataset.py:read_parquet` determine a replay's verdict yet are not hashed. Adopting them edits ratified spec `00060` D3, so this branch produces the **evidence and a recommendation**; the ruling is the owner's. Findings 12/13/19 (counters and misattribution) are pinned regardless — they are independent of the ruling.

## Non-goals

- **Changing any invalidation trigger, the schema version, the module list's membership, or the rotation.** Pinning a guarantee is not endorsing it. Adding `command.py`/`dataset.py` is D9's ruling, not this branch's work.
- [[T0076]]'s concordance guarantees — merged (`00063`).
- The eight survivors triaged equivalent or safe-direction. They are recorded in the audit with their reasoning; re-litigating one requires constructing a distinguishing input, per D8.

## Test list (TDD)

1. **Full-tuple module pin (D1)** — the complete `_REPLAY_CODE_PATHS` list; removing any entry fails.
2. **Fingerprint responds to each module's bytes (1–4)** — an edit to each of the four originals changes `replay_fingerprint`.
3. **`first_ts` / `last_ts` stale-hit pins (5, 6)** — the audit's tamper; assert a cache **miss**.
4. **`pair` / `grid` order-preserving tampers (7, 8, D3)** — `ETH`→`FTH`, `1440`→`1441`; the reason stated in-test.
5. **`path` repointed at another pair's parquet (10)** — assert a miss.
6. **Unparseable `cycle-*.json` (9, D4)** — asserted at journal level: `gate_met` stays `False`, `last_failure` is set.
7. **One malformed row inside a valid `entries[]` (11)** — invalidates wholesale; the only path where "discard the file" and "skip the bad row" diverge.
8. **Schema gate for the right reason + lower version rejected (14, D6)**.
9. **`load_cache` / `save_cache` never raise (15, 16, D5)** — malformed JSON, wrong top-level type, mixed-key `sorted()`.
10. **Counter pins (12, 13)** — `mismatches` counts a real compare failure; `replayed_ok` does not count a failed cycle.
11. **Vanished record's entry is evicted (17)** — otherwise it poisons `oldest_verification_age` permanently.
12. **`_EVALUATE_JOURNAL_REPLAY_PATH` coupling (18)**.
13. **`EngineJournalError` attribution (19)** — reusing `_counted_replay_cycle`'s identity assertion.
14. **Regression** — the existing gate-cache suites pass unchanged; `git diff` touches `tests/`, `docs/`, and only the `gate_cache.py` docstring (D7).
