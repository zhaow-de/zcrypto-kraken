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

_(Audit A's original four, kept for the record and **superseded by the 19 below** — the re-audit found each of these still real, and twelve more. Two of Audit A's not-gap rulings were wrong.)_

> 1. **(HIGH) The four original hashed modules are pinned by nothing.** `crossfreq_system.py`, `crossfreq.py`, `limits.py` and `concordance.py` can each be silently deleted from `_REPLAY_CODE_PATHS` with 22/22 still passing. The six modules *added at review* are pinned by an explicit membership assertion; the four that were there first are not. `concordance.py` holds `replay_cycle`, `compare_targets` and `evaluate_gate` — the entire verdict pipeline.
> 2. **(HIGH) `first_ts` and `last_ts` are droppable from the evidence key**, and dropping either was confirmed empirically to yield a stale cache hit on a realistic tamper. They sit in the *same `or` clause of the same guard* (`concordance.py:118`) as `n_bars` — i.e. the identical tamper class to the review hole already fixed once, left unpinned for its siblings.
> 3. **(MEDIUM) `SnapshotEntry.path` is droppable and exploitable** — repoint one entry at another pair's parquet and the stale entry is served.
> 4. **(MEDIUM) A structurally-valid cache file with one malformed entry inside `entries[]` can serve its good entries** instead of invalidating wholesale. Every existing fail-open test corrupts the file *before* the entry loop, so this is the single path where "discard the file" and "skip the bad row" diverge — and it is untested.

**RE-AUDITED 2026-07-20 under bytecode control — the scope is 19 gaps, not 8, and the reason is not what this topic predicted.**

The caveat above expected stale bytecode to have inflated Audit A's "detected" count. **It had not: zero false detections.** Every Audit A mutation re-executed under `PYTHONDONTWRITEBYTECODE=1` came back detected, so its 44 clean verdicts stand. The premise was right that the count was understated; the mechanism was wrong.

The real cause is **triage error**. Audit A dismissed `pair` and `grid` as equivalent mutants — "self-healing, the sort key masks the tamper" — which holds only for an *order-changing* tamper. An order-**preserving** rename (`ETH`→`FTH`, `1440`→`1441`) defeats the masking and yields a stale PASS end-to-end. Both are HIGH, and both were recorded here as not-gaps.

*Why this module and not the concordance one:* Audit A's mutations were dominated by **line deletions**, which change source size and so invalidate the `.pyc` on the size validator regardless of mtime. Same-size in-place edits — the profile that bit the concordance audit — were rare here.

**The methodological lesson, which generalises past this module: an equivalent-mutant ruling is a UNIVERSAL claim. One non-distinguishing input is not evidence for it.** Audit A tested one input per ruling and generalised; this run constructed a distinguishing input and two rulings collapsed.

Re-audit: 80 mutations, 53 detected, 27 survivors, **19 genuine gaps** after triage — each proven by a written exploitability probe rather than a test outcome. Eight survivors are genuinely equivalent or safe-direction, including an independent reproduction of one Audit A ruling that does hold.

**No live defect.** Every finding is coverage; the code behaves correctly today.

### The 19 gaps

1. **(HIGH)** `crossfreq_system.py` droppable from `_REPLAY_CODE_PATHS` — the fingerprint is unchanged after a real edit to it.
2. **(HIGH)** `crossfreq.py` droppable — same.
3. **(HIGH)** `limits.py` droppable — same.
4. **(HIGH)** `concordance.py` droppable — the whole verdict pipeline; the cache survives edits to it.
5. **(HIGH)** `first_ts` droppable from the evidence key — stale PASS proven end-to-end.
6. **(HIGH)** `last_ts` droppable — stale PASS proven end-to-end.
7. **(HIGH)** `pair` droppable — **stale PASS proven**; Audit A mis-triaged this as equivalent.
8. **(HIGH)** `grid` droppable — **stale PASS proven**; same mis-triage.
9. **(HIGH)** An unparseable `cycle-*.json` scored as a clean pass — **flips a 14-day journal from `gate_met=False` to `gate_met=True`** with `last_failure=None`. A corrupt journal file becoming a *pass* on the artifact that authorises real-money trading.
10. **(MEDIUM)** `SnapshotEntry.path` droppable — stale PASS on a repointed parquet.
11. **(MEDIUM)** One malformed row in an otherwise valid cache file serves the good rows instead of invalidating wholesale.
12. **(MED-HIGH)** `mismatches` can stop counting compare failures — `zcrypto_gate_mismatch_total` reads 0 during a real mismatch.
13. **(MEDIUM)** `replayed_ok` can count a failed cycle as OK.
14. **(MEDIUM)** A **lower** `schema_version` cache is accepted, and the existing v1 test passes for the wrong reason — a `KeyError` fallback, not the schema gate.
15. **(MEDIUM)** `load_cache` can be made to raise: D5's "never raises" is unpinned except for `OSError`.
16. **(LOW-MED)** `save_cache` can be made to raise — the `TypeError` arm is reachable via `sorted()` on mixed keys.
17. **(LOW-MED)** A vanished record's cache entry is retained forever, permanently poisoning `oldest_verification_age`.
18. **(LOW-MED)** The fingerprint's coupling to `_EVALUATE_JOURNAL_REPLAY_PATH` is unpinned.
19. **(LOW-MED)** `EngineJournalError` is misattributable as `mismatch` — `_replay_one`'s classifier is not covered by the attribution pattern Audit A called airtight.

Full re-audit, committed as durable evidence: `docs/research/14.phase6-gate-guarantee-mutation-audits.md` (Audit C).

**Design-level question, flagged rather than decided** (it would change ratified spec `00060` D3, which fixes the list at ten modules): `cli/engine/command.py` (`_replay_one`'s exception→verdict mapping — the sole classifier — and `_snapshot_reader`) and `cli/ohlc/dataset.py` (`read_parquet`, which feeds both the content hash and the builder) determine a replay's verdict yet are **not** hashed. Same class as the two under-invalidation holes already found at review.

**Docstring inaccuracy (small, but the same false-artifact class the audit was chasing):** `_REPLAY_CODE_PATHS` labels `a1.py` / `a2.py` / `builder.py` / `strategies.py` as "LATENT — verified route only", but `crossfreq_system.py:53-56` imports all four at module scope, so they are live on the fast route. Harmless today; the risk is that the false label invites a future cleanup to drop them from the list.

**Worth preserving — what the audit found already airtight.** Category 5 (attribution/order) caught all 9 same-typed swaps, several with 9 failing tests. The pattern that makes it work is `_counted_replay_cycle` asserting *which* `cycle_ts` was replayed — identity, not count — and it is the direct antidote to what failed in iter-111. Reuse it when pinning the gaps above.

## Suggested next steps

- **(Autonomous)** Pin the four original modules the same way the six added ones are pinned — an explicit membership assertion over the full `_REPLAY_CODE_PATHS` list, so the assertion fails if *any* entry is removed rather than enumerating the ones someone once forgot.
- **(Autonomous)** Extend the evidence-key tests to cover `first_ts`, `last_ts` and `path`, using the realistic tamper the audit constructed (a stale hit against a mutated entry) rather than a field-presence check.
- **(Autonomous)** Add the fail-open case that no existing test covers: a structurally-valid cache file with one malformed row inside `entries[]` must invalidate wholesale, not serve its good rows.
- **(Autonomous)** Correct the LATENT/LIVE docstring labels in `_REPLAY_CODE_PATHS` to match the module-scope imports at `crossfreq_system.py:53-56`.
- **(Autonomous research, then a human ruling)** Make the case for or against hashing `cli/engine/command.py` and `cli/ohlc/dataset.py`. The research is autonomous — trace whether a change in either can alter a replay verdict without altering any currently-hashed byte — but adopting it edits ratified spec `00060` D3, so present the finding and the recommendation rather than changing the spec unilaterally.
- ~~**(Autonomous, do this FIRST)** Re-run the audit itself with bytecode control (`PYTHONDONTWRITEBYTECODE=1`, purge `__pycache__`, assert baseline-green) in an isolated worktree, since the 44 "detected" verdicts may include false ones — see the caveat above. The 8 gaps already found stand regardless.~~ **DONE** 2026-07-20 — Audit C above. Zero false detections; the scope grew to 19 via triage error instead.
- **(Method, applies beyond this topic)** When pinning any of the above, pin the *general* guarantee, not the instance that prompted it — that is the defect this whole topic describes. And bracket constants from both sides rather than sampling far from either edge; the companion audit found every mutation loosening a threshold survived while every one tightening it was caught.
