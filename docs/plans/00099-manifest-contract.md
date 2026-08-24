# Manifest contract — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Steps use `- [ ]` for tracking.

**Goal:** Every manifest this repo writes conforms to one contract, written and read through one module, so a consumer never needs per-set knowledge — and the path-binding consumer T0133 parked is discharged.

**Architecture:** A new `cli/data/manifest.py` owns the shape: one `build_manifest()` that every writer calls, one `read_manifest()` that every consumer calls, and the digest recipe in one place. The five writers stop hand-assembling dicts. A one-shot converter rewrites existing manifests from the parquets already on disk — no parquet is touched.

**Tech Stack:** Python 3.14, polars, pytest. `dataset_hash` from `cli/ohlc/dataset.py` is the hash grade throughout.

## Global Constraints

- `series` is keyed by the parquet path **relative to the dataset root**; the path is the key, never derived.
- `sha256` everywhere means `dataset_hash` (sha256 of canonical CSV). **Never file bytes** — measured unstable across polars versions (`ohlc-15m` row-group boundaries moved 1.42.1 → 1.43.2 while `dataset_hash` reproduced 12/12).
- `set_sha256` = sha256 over concatenated per-series `sha256` in sorted key order.
- `written_at` is when the manifest was written. Source-specific meaning goes in `provenance`.
- `provenance` is free-form, **excluded from `set_sha256`**, and no consumer may depend on it.
- A manifest without `schema_version` is legacy: the reader refuses it rather than guessing.
- **No parquet bytes change anywhere in this plan.**
- The external holdout freeze is out of scope; `docs/reference/vouched-dataset-hashes.jsonl` is its normalised form.

---

### Task 1: The contract module

**Files:** Create `cli/data/manifest.py`; Test `tests/test_data_manifest.py`

**Produces:** `SCHEMA_VERSION: int`, `build_manifest(series: dict[str, SeriesEntry], *, written_at: datetime, provenance: dict | None = None) -> dict`, `read_manifest(path: Path) -> Manifest`, `series_entry(frame, relpath) -> dict`, `set_digest(series: dict) -> str`, `ManifestError`.

- [ ] **Step 1: Write failing tests** — round-trip; `set_digest` reproducible and independent of `provenance`; a leaf missing any of `sha256`/`rows`/`first_ts`/`last_ts` refuses; a non-relative or absolute `series` key refuses; a legacy manifest (no `schema_version`) refuses **typed**; an unknown `schema_version` refuses.
- [ ] **Step 2: Run — expect ImportError.**
- [ ] **Step 3: Implement.** Keep it small: build, read, validate, digest.
- [ ] **Step 4: Tests pass.**
- [ ] **Step 5: Prove the digest excludes `provenance`** — construct two manifests differing only in `provenance` and assert equal `set_sha256`; mutate a series hash and assert it moves.
- [ ] **Step 6: Commit.**

### Task 2: Every writer emits it

**Files:** Modify `cli/backfill/backfill.py`, `cli/derivatives/funding.py`, `cli/derivatives/oi.py`, `cli/ohlc/reach.py`, `cli/ohlc/ingest.py`; Tests: the existing per-writer test files.

**Consumes:** Task 1's `build_manifest` / `series_entry`.

- [ ] **Step 1:** For each writer, replace the hand-built dict with `build_manifest(...)`, keying `series` by relative path. `ohlc-reach`'s `rest_first`/`rest_last` and `built_at`, and backfill's machine-local `source`, move into `provenance`.
- [ ] **Step 2:** Update each writer's existing tests to assert the new shape. Where a test asserted the old nesting, re-point it — do not delete.
- [ ] **Step 3:** Assert in one test that all five writers produce a manifest `read_manifest` accepts.
- [ ] **Step 4:** Commit.

### Task 3: The converter

**Files:** Create the command in `cli/data/command.py`; Test `tests/test_data_manifest_migrate.py`

- [ ] **Step 1: Failing test** — a legacy-shaped dataset on disk converts to a conformant manifest, with `rows`/`first_ts`/`last_ts`/`sha256` recomputed **from the parquets**, and every parquet's bytes unchanged (assert file sha256 before and after).
- [ ] **Step 2:** Implement `zcrypto data migrate-manifests [--apply]`, defaulting to a dry run that prints what would change.
- [ ] **Step 3:** Refuse a dataset whose parquets do not all read, rather than writing a partial manifest.
- [ ] **Step 4:** Tests pass; update `README.md` Usage (`readme-usage.md`).
- [ ] **Step 5: Commit.**

### Task 4: Consumers move to the contract

**Files:** Modify `cli/data/rebuild.py` (`basket_sha256` → `set_sha256`), `cli/data/sync.py`; Tests: `tests/test_data_rebuild.py`, `tests/test_data_sync.py`, `tests/test_data_vouched_sidecar.py`

- [ ] **Step 1: Failing test** — a manifest-attested set with two series **swapped** is refused at fetch and at read. This is the waiting consumer; it must fail before the fix.
- [ ] **Step 2:** `_attestation_failure` takes its path→hash map from the manifest as well as the sidecar, so a manifest-attested set is path-bound.
- [ ] **Step 3:** `rebuild.py` reads `set_sha256` through `read_manifest`.
- [ ] **Step 4:** Tests pass. **Prove by mutation** that reverting step 2 makes the swap invisible again.
- [ ] **Step 5: Commit.**

### Task 5: Conformance test over what is on disk

**Files:** Create `tests/test_manifest_conformance.py`

- [ ] **Step 1:** Walk every `data/*/manifest.json`; assert `read_manifest` accepts each, **except** an explicitly named legacy set (the holdout), which must instead be covered by the sidecar.
- [ ] **Step 2:** Assert the guard is non-empty (a glob that matches nothing must fail, not pass).
- [ ] **Step 3:** Commit.

### Task 6: Run the migration, then closeout

- [ ] **Step 1:** `zcrypto data migrate-manifests` dry run; read the diff.
- [ ] **Step 2:** `--apply`; re-run the conformance test and the full reachable suite.
- [ ] **Step 3:** Verify no parquet changed — compare file hashes across the whole data root before/after.
- [ ] **Step 4:** Correct T0132's three factual errors **in place** (three timestamp spellings; `ingest.py` emits `fetched_at`; `series_digest` does not exist), then resolve and archive it; move its index bullet; update `docs/reference/data-catalog-full.md`.
- [ ] **Step 5:** Append the iterations-history entry (phase routing per `iteration-closeout`).
- [ ] **Step 6: Commit.**
