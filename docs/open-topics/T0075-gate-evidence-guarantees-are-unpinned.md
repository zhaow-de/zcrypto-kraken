---
status: open
ripe_when: ripe NOW — the gaps are in merged, gate-critical code and every sub-item is autonomous; take it as a dedicated iteration before the Stage-6a soak gate is read, since every finding here concerns the evidence that gate is read FROM
---

# The gate-evidence cache's safety guarantees are generalised in code but pinned only at the instance that prompted them

## Context — what

A mutation audit (2026-07-20, 60 mutations against `cli/engine/gate_cache.py` + `_evaluate_journal`) found that several of the cache's load-bearing safety properties would survive being broken: the mutation was applied, the covering tests ran, and nothing failed. The implemented logic is **correct today** — these are coverage findings, not live defects — but a guarantee nothing pins is a guarantee that decays silently at the next refactor.

The audit was motivated by a defect in the **testing practice** rather than in any one test. The iteration that had just merged (iter-111, spec `00061`) found several of its own pins vacuous: swapping two labels, or attributing a result to a source that never ran, left the whole suite green because the assertions were order-agnostic membership checks. The retroactive-audit rule then requires re-auditing everything built under the same practice, and the gate-evidence cache is the most consequential such code.

## Why this matters

`gate_cache.py` caches **gate evidence** — the artifact deciding whether the strategy may trade real money. Its design is deliberately over-sensitive: over-invalidation costs one rebuild, under-invalidation silently corrupts the evidence. That asymmetry only holds while the invalidation triggers are actually enforced by tests.

The audit also named a pattern behind several of the findings (1 and 2 below; others are different shapes — never pinned at all, or pinned to the wrong target), worth stating on its own because it is the same failure as the iteration that triggered the audit, one level up: **each past review fix was generalised in the code, but its test pinned only the specific instance that prompted it.** The fix is real; the guarantee is unpinned.

## Findings so far

Full audit, committed as durable evidence: `docs/research/14.phase6-gate-guarantee-mutation-audits.md` (Audit A; 2026-07-20, Opus 4.8; 60 mutations, 44 detected, 16 undetected raw → **8 genuine gaps** after triaging equivalent and safe-direction mutants, each triaged individually via a written exploitability script rather than assumed).

1. **(HIGH) The four original hashed modules are pinned by nothing.** `crossfreq_system.py`, `crossfreq.py`, `limits.py` and `concordance.py` can each be silently deleted from `_REPLAY_CODE_PATHS` with 22/22 still passing. The six modules *added at review* are pinned by an explicit membership assertion; the four that were there first are not. `concordance.py` holds `replay_cycle`, `compare_targets` and `evaluate_gate` — the entire verdict pipeline.
2. **(HIGH) `first_ts` and `last_ts` are droppable from the evidence key**, and dropping either was confirmed empirically to yield a stale cache hit on a realistic tamper. They sit in the *same `or` clause of the same guard* (`concordance.py:118`) as `n_bars` — i.e. the identical tamper class to the review hole already fixed once, left unpinned for its siblings.
3. **(MEDIUM) `SnapshotEntry.path` is droppable and exploitable** — repoint one entry at another pair's parquet and the stale entry is served.
4. **(MEDIUM) A structurally-valid cache file with one malformed entry inside `entries[]` can serve its good entries** instead of invalidating wholesale. Every existing fail-open test corrupts the file *before* the entry loop, so this is the single path where "discard the file" and "skip the bad row" diverge — and it is untested.

**Design-level question, flagged rather than decided** (it would change ratified spec `00060` D3, which fixes the list at ten modules): `cli/engine/command.py` (`_replay_one`'s exception→verdict mapping — the sole classifier — and `_snapshot_reader`) and `cli/ohlc/dataset.py` (`read_parquet`, which feeds both the content hash and the builder) determine a replay's verdict yet are **not** hashed. Same class as the two under-invalidation holes already found at review.

**Docstring inaccuracy (small, but the same false-artifact class the audit was chasing):** `_REPLAY_CODE_PATHS` labels `a1.py` / `a2.py` / `builder.py` / `strategies.py` as "LATENT — verified route only", but `crossfreq_system.py:53-56` imports all four at module scope, so they are live on the fast route. Harmless today; the risk is that the false label invites a future cleanup to drop them from the list.

**Worth preserving — what the audit found already airtight.** Category 5 (attribution/order) caught all 9 same-typed swaps, several with 9 failing tests. The pattern that makes it work is `_counted_replay_cycle` asserting *which* `cycle_ts` was replayed — identity, not count — and it is the direct antidote to what failed in iter-111. Reuse it when pinning the gaps above.

## Suggested next steps

- **(Autonomous)** Pin the four original modules the same way the six added ones are pinned — an explicit membership assertion over the full `_REPLAY_CODE_PATHS` list, so the assertion fails if *any* entry is removed rather than enumerating the ones someone once forgot.
- **(Autonomous)** Extend the evidence-key tests to cover `first_ts`, `last_ts` and `path`, using the realistic tamper the audit constructed (a stale hit against a mutated entry) rather than a field-presence check.
- **(Autonomous)** Add the fail-open case that no existing test covers: a structurally-valid cache file with one malformed row inside `entries[]` must invalidate wholesale, not serve its good rows.
- **(Autonomous)** Correct the LATENT/LIVE docstring labels in `_REPLAY_CODE_PATHS` to match the module-scope imports at `crossfreq_system.py:53-56`.
- **(Autonomous research, then a human ruling)** Make the case for or against hashing `cli/engine/command.py` and `cli/ohlc/dataset.py`. The research is autonomous — trace whether a change in either can alter a replay verdict without altering any currently-hashed byte — but adopting it edits ratified spec `00060` D3, so present the finding and the recommendation rather than changing the spec unilaterally.
- **(Method, applies beyond this topic)** When pinning any of the above, pin the *general* guarantee, not the instance that prompted it — that is the defect this whole topic describes.
