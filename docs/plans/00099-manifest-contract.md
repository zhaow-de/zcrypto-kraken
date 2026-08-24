# Manifest contract — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use `superpowers:subagent-driven-development` or `superpowers:executing-plans`. Steps use `- [ ]` for tracking.

**Goal:** Every manifest this repo writes conforms to one contract, written and read through one module, so a consumer never needs per-set knowledge — and the path-binding consumer T0133 parked is discharged.

**Architecture:** A new `cli/data/manifest.py` owns the shape: one `build_manifest()` that every writer calls, one `read_manifest()` that every consumer calls, and the digest recipe in one place. The five writers stop hand-assembling dicts. A one-shot converter rewrites existing manifests from the parquets already on disk — no parquet is touched.

**Tech Stack:** Python 3.14, polars, pytest. `dataset_hash` from `cli/ohlc/dataset.py` is the hash grade throughout.

## Global Constraints

- `series` is keyed by the parquet path **relative to the dataset root**; the path is the key, never derived.
- `sha256` everywhere means `dataset_hash` (sha256 of canonical CSV). **Never file bytes** — measured unstable across polars versions (`ohlc-15m` row-group boundaries moved 1.42.1 → 1.43.2 while `dataset_hash` reproduced 12/12).
- `set_sha256` = sha256 over concatenated per-series `sha256` in sorted key order, over EVERY series.
- `subset_sha256: {name: hex}` is optional, same recipe over a named subset. `ohlc-reach` declares `continuous` (its detached series are excluded by design), and that value must reproduce `d77fff97c819f5afbabbddf44ad0b8d94185a62a84002aaf36d153357100c98e` — a citation committed in `docs/universe/point-in-time-universe.md` and in `data/universe-20260813/point-in-time-universe.json`.
- `written_at` is when the manifest was written. Source-specific meaning goes in `provenance`.
- `provenance` is free-form, **excluded from `set_sha256`**, and no consumer may depend on it.
- A manifest without `schema_version` is legacy: the reader refuses it rather than guessing.
- **No parquet bytes change anywhere in this plan.**
- The external holdout freeze is out of scope; `docs/reference/vouched-dataset-hashes.jsonl` is its normalised form.
- **Legacy manifests are tolerated at named boundaries.** The hub keeps legacy copies (rsync `--ignore-existing` cannot overwrite), so path binding engages only where a conformant manifest exists and degrades to membership otherwise. Never assert universal conformance.

---

### Task 1: The contract module

**Files:** Create `cli/data/manifest.py`; Test `tests/test_data_manifest.py`

**Produces:** `SCHEMA_VERSION: int`, `build_manifest(series, *, written_at, provenance=None, subsets=None) -> dict`, `read_manifest(path) -> Manifest`, `series_entry(frame, relpath) -> dict`, `set_digest(series, keys=None) -> str`, `ManifestError`.

- [ ] **Step 1: Write failing tests** — round-trip; `set_digest` reproducible and independent of `provenance`; a leaf missing any of `sha256`/`rows`/`first_ts`/`last_ts` refuses; a non-relative or absolute `series` key refuses; a legacy manifest (no `schema_version`) refuses **typed**; an unknown `schema_version` refuses.
- [ ] **Step 2: Run — expect ImportError.**
- [ ] **Step 3: Implement.** Keep it small: build, read, validate, digest.
- [ ] **Step 4: Tests pass.**
- [ ] **Step 5a: Pin `subset_sha256`** — `set_digest(series, keys=<continuous subset>)` over reach's real continuous series must equal `d77fff97c819f5af…`; a test asserts it against the committed citation, so a recipe change that silently re-anchors the universe chain fails here.
- [ ] **Step 5: Prove the digest excludes `provenance`** — construct two manifests differing only in `provenance` and assert equal `set_sha256`; mutate a series hash and assert it moves.
- [ ] **Step 6: Commit.**

### Task 2: Every writer emits it

**Files:** Modify `cli/backfill/backfill.py`, `cli/derivatives/funding.py`, `cli/derivatives/oi.py`, `cli/ohlc/reach.py`, `cli/ohlc/ingest.py`; Tests: the existing per-writer test files.

**Consumes:** Task 1's `build_manifest` / `series_entry`.

- [ ] **Step 1:** For each writer, replace the hand-built dict with `build_manifest(...)`, keying `series` by relative path. Into `provenance`: `ohlc-reach`'s `built_at`, `min_seam_overlap`, and per-row `rest_first`/`rest_last`/`overlap_bars`/`gap_bars`/`appended`; backfill's machine-local `source`; **and funding's and oi's `source` too** — every writer that carries one.
- [ ] **Step 1b:** `ohlc-reach` declares `subsets={"continuous": [...]}` so its committed digest survives the change.
- [ ] **Step 2:** Update each writer's existing tests to assert the new shape. Where a test asserted the old nesting, re-point it — do not delete.
- [ ] **Step 3:** Assert in one test that all five writers produce a manifest `read_manifest` accepts.
- [ ] **Step 4:** Commit.

### Task 3: The converter

**Files:** Create the command in `cli/data/command.py`; Test `tests/test_data_manifest_migrate.py`

**The converter carries every unrecognised legacy field into `provenance` verbatim.** Reach's seam evidence was computed against an expired REST window and every set's original `fetched_at` is a freeze moment; neither is recoverable from parquets, so recomputing only the recoverable fields would erase them.

- [ ] **Step 1: Failing test** — a legacy-shaped dataset on disk converts to a conformant manifest, with `rows`/`first_ts`/`last_ts`/`sha256` recomputed **from the parquets**, and every parquet's bytes unchanged (assert file sha256 before and after).
- [ ] **Step 2:** Implement `zcrypto data migrate-manifests [--apply]`, defaulting to a dry run that prints what would change.
- [ ] **Step 3:** Refuse a dataset whose parquets do not all read, rather than writing a partial manifest.
- [ ] **Step 4:** Tests pass; update `README.md` Usage (`readme-usage.md`).
- [ ] **Step 5: Commit.**

### Task 4: Consumers move to the contract

**Files:** Modify `cli/data/rebuild.py` (→ the reach `continuous` **subset** digest, not the set-wide one), `cli/data/sync.py`, **`cli/registry/observed.py`**; Tests: `tests/test_data_rebuild.py`, `tests/test_data_sync.py`, `tests/test_data_vouched_sidecar.py`, **`tests/test_registry_observed.py`**, **`tests/test_legacy_dataset_pins.py`**, **`tests/test_universe_provenance.py`**

`ObservedReader.read_series` does NOT route through `_attestation_failure` — it carries its own sidecar-else-membership logic, so the read half needs its own change or T0133's registered residual is silently dropped. Both halves, or an explicit written drop; no new topic is permitted for the remainder.

`tests/test_legacy_dataset_pins.py` reads `data/ohlc-15m/manifest.json["basket_sha256"]` and `tests/test_universe_provenance.py` reads reach's — both data-gated, both skip in CI, so they run nowhere else and must be re-pointed here.

- [ ] **Step 1: Failing test** — a manifest-attested set with two series **swapped** is refused at fetch and at read. This is the waiting consumer; it must fail before the fix.
- [ ] **Step 2:** `_attestation_failure` takes its path→hash map from the manifest as well as the sidecar, so a manifest-attested set is path-bound.
- [ ] **Step 3:** `rebuild.py` reads `set_sha256` through `read_manifest`.
- [ ] **Step 4:** Tests pass. **Prove by mutation** that reverting step 2 makes the swap invisible again.
- [ ] **Step 5: Commit.**

### Task 5: Conformance test over what is on disk

**Files:** Create `tests/test_manifest_conformance.py`

- [ ] **Step 1:** Walk every `data/*/manifest.json`; assert `read_manifest` accepts each, **except** explicitly named legacy sets (the holdout, plus any set whose only copy came from the hub), which must instead be covered by the sidecar or named.
- [ ] **Step 2:** CI-safe gate: **absent data root → skip** (CI has no `data/`); root present but glob empty → **fail**. A test that reddens every PR gets deleted, which is worse than no test.
- [ ] **Step 3:** Commit.

### Task 6: Run the migration, then closeout

- [ ] **Step 1:** `zcrypto data migrate-manifests` dry run; read the diff.
- [ ] **Step 2:** `--apply`; re-run the conformance test and the full reachable suite.
- [ ] **Step 3:** Verify no parquet changed — compare file hashes across the whole data root before/after.
- [ ] **Step 3b: The hub conversion is ATTENDED and takes the owner's explicit word at the moment it runs.** The additive channel cannot overwrite a manifest, so this deliberately replaces the hub's copies; until it happens, fetch-side path binding is inert in production and that stays stated rather than implied.
- [ ] **Step 4:** Correct T0132's three factual errors **in place** (mechanics per the `topic-ops` skill) (three timestamp spellings; `ingest.py` emits `fetched_at`; `series_digest` does not exist), then resolve and archive it; move its index bullet; update `docs/reference/data-catalog-full.md`.
- [ ] **Step 5:** Append the iterations-history entry (phase routing per `iteration-closeout`).
- [ ] **Step 6: Commit.**
