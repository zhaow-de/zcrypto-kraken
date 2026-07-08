# Trial-Registry Hash Chain — Design (Phase 2)

**Iteration:** iter-019 · **Phase:** 2 (Validation Harness & Cost Model First) · **Status:** design approved (unattended loop)
**Master-plan refs:** §9.7 ("registry hash-chain intact"; "CI test that corrupts a registry copy and requires a loud failure"), §12 Phase 2, §7. **Extends** the Phase-0 registry `cli/registry/` (iter-001, spec `00000`).

## Problem & context

The Phase-0 `TrialRegistry` (iter-001) is append-only JSONL with a per-record **self-hash** (`record_hash = sha256(canonical_json(body))`), plus contiguity (`trial_id = 1,2,3,…`), monotone `n_trials_in_family`, NaN-token rejection, and torn-tail self-heal. Its own docstring names the remaining gap: the self-hash *"catches accidental/careless in-place edits … it is NOT tamper-evidence against a re-hashing writer — that is the **Phase-2 hash chain**."* This iteration closes that gap.

**The gap, concretely:** an editor who changes a metric in record 2 **and recomputes record 2's `record_hash`** produces a file where every self-hash still verifies — the tamper is invisible today. A **hash chain** fixes this: each record commits to its predecessor's hash, so re-hashing one record breaks the *next* record's link.

## Goals

- **`prev_hash` chain** across `cli/registry/`: each record stores the prior record's `record_hash` (genesis for the first); a new cross-record check verifies the links, making single/partial tampers tamper-**evident**. Plus the §9.7 corruption-detection tests. Existing integrity (self-hash, contiguity, monotone counts, self-heal) is preserved.

## Non-goals

- No Merkle root / external anchor (over-engineered for a local flock-guarded append-only JSONL — deferred). The chain does not defend against a writer who re-hashes the *entire suffix*; that needs an out-of-band anchor (§8 immutable storage handles the medium).
- No schema migration tooling — the registry has **no persisted data yet** (trials begin in Phase 2), so the `SCHEMA_VERSION` bump needs no migration.
- No change to the caller-facing `append(...)` signature, the metric-finiteness (`_assert_finite`), NaN rejection, or self-heal behavior. No CLI/README change. No new deps.

## Design (edits to existing `cli/registry/`)

**`cli/registry/record.py`:**
- `SCHEMA_VERSION = 2` (was `1`) — `prev_hash` is a new store-owned field.
- Add `GENESIS_HASH = "0" * 64`.
- Add `"prev_hash"` to `_STORE_OWNED` (store-managed; callers must not supply it — the existing `validate_caller_fields` rejection then covers it).
- `TrialRecord`: add field `prev_hash: str` (kw-only dataclass; place it before `record_hash`).
- `validate_stored_record`: after the existing `record_hash` self-check (which already covers `prev_hash` since it's in the hashed body), also assert `type(rec.get("prev_hash")) is str and len == 64` — a structural check; its *value* is verified by the cross-record chain check.

**`cli/registry/store.py`:**
- `_to_record`: add `prev_hash=rec["prev_hash"]`.
- `append`: compute `prev_hash = disk[-1]["record_hash"] if disk else GENESIS_HASH`, and include it in the record body **before** hashing: `rec = {**caller, "trial_id": next_id, "schema_version": SCHEMA_VERSION, "timestamp": _now_utc_iso(), "prev_hash": prev_hash}`, then `rec["record_hash"] = compute_hash(rec)`. (Import `GENESIS_HASH`.)
- `_assert_cross_record`: add the **chain check** — for each `idx`, `expected_prev = GENESIS_HASH if idx == 0 else recs[idx - 1]["record_hash"]`; if `rec["prev_hash"] != expected_prev`, raise `RegistryCorruptionError(f"{path}: trial {rec['trial_id']} prev_hash breaks the chain")`. (Keep the existing contiguity + monotone-family checks.)

**`cli/registry/__init__.py`:** export `GENESIS_HASH`.

**Why this is minimal + correct:** `prev_hash` lives inside the hashed body, so the existing self-hash check already protects it and no new hashing path is introduced; the only genuinely new logic is the one-line chain link check in `_assert_cross_record`. A re-hashing tamper of record *i* leaves record *i+1*'s stored `prev_hash` pointing at record *i*'s **old** hash → chain break at *i+1*. Deleting/reordering a middle record breaks both contiguity and the chain.

## Testing

Update `tests/test_registry_record.py` + `tests/test_registry_store.py` for the new field (any directly-constructed `TrialRecord` gains `prev_hash`; any hand-built stored dict gains a correct `prev_hash`), keeping all existing integrity assertions green. Then add, in `tests/test_registry_store.py`:

- **Chain is written** — after appending 3 trials, `records[0].prev_hash == GENESIS_HASH` and `records[k].prev_hash == records[k-1].record_hash` for k=1,2.
- **Re-hashing tamper is caught (the new capability)** — append 3 trials; on disk, edit record 2's line: change a metric value **and** recompute its `record_hash` correctly (so the self-hash check passes); re-open the registry → `RegistryCorruptionError` (the chain check fails at record 3, whose `prev_hash` no longer matches record 2's new hash). Assert that the *same* tamper WITHOUT recomputing `record_hash` is also caught (by the existing self-hash check) — both paths raise.
- **Genesis mismatch** — corrupt record 1's `prev_hash` to a non-genesis value (re-hashing it) → `RegistryCorruptionError`.
- **Deletion breaks the chain** — remove the middle line of a 3-record file → `RegistryCorruptionError` (contiguity and/or chain).
- **`SCHEMA_VERSION` bump** — a stored record with `schema_version = 1` (old) is rejected as corruption (unknown schema).
- **Round-trip** — append → new `TrialRegistry(path)` reads back the same records with intact `prev_hash` links (no false corruption on a clean file); append across two registry instances chains correctly (second instance's first append `prev_hash` == the first instance's last `record_hash`).

## Deferred / parked

Merkle/external anchor; schema-migration tooling; a standalone `verify_registry(path)` CLI (the constructor already validates on read — a CI test just re-opens a corrupted copy); the rest of §9/§12 Phase-2 (multi-seed, SPA, the acceptance suite that reuses this corruption test).

## Closeout (planned)

On merge: append the `iter-019` `docs/iterations-history.md` entry. No dataset artifacts. The `.tmp/decisions.md` `[iter-019]` entry stays in the running log (drained at Phase-2 close-out). Note: `docs/specs/00000-trial-registry-design.md` describes the Phase-0 v1 schema; this iteration supersedes `SCHEMA_VERSION` to 2 — reference `00012` for the chain.
