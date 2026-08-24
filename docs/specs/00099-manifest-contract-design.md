# Manifest contract — design

**Topic:** [[T0132]] — the manifest writers have no contract, so nothing can read them generically.

## Why this, and why the shape of the answer is "normalise first"

Two prior attempts at a generic manifest *consumer* failed nine cold-review rounds between them. The findings kept **moving** rather than recurring — round 1 was "the holdout set is unregisterable", round 4 was "`derivatives-funding`/`-oi` are unregisterable" and "`ohlc-reach` false-alarms" — because a generic reader over a zoo is a pile of special cases discovered one review at a time. This spec does not write a reader for the zoo. It removes the zoo.

Nothing is blocked today, which is exactly the risk the topic names: the cost is latent and payable by the next consumer. That consumer now exists and is concrete — [[T0133]] shipped path-bound verification for sets attested by the committed sidecar and **consciously kept hash *membership* for manifest-attested sets**, because deriving a path per hash needed the per-set knowledge this contract exists to remove. Until it lands, two series swapped inside `ohlc-full`/`ohlc-15m`/`derivatives-*`/`ohlc-reach` are invisible at both consumers.

## What was measured (2026-08-24), and what it corrected

The topic's own table is wrong in three places, and was wrong the day it was written. This spec is written against measurement, not against the table:

- **Three timestamp spellings, not two.** `fetched_at` (backfill → `ohlc-full`/`ohlc-15m`, funding, oi, and the retired `ingest.py`), `built_at` (`ohlc-reach`), `pulled_at` (the external holdout). `git log -S'"fetched_at"' -- cli/ohlc/reach.py` returns nothing: reach never had it.
- **`ingest.py`'s timestamp is `fetched_at`**, not absent as the table records.
- **`series_digest` does not exist.** Zero code, zero manifests — the token appears only in the topic's own prose. `basket_sha256` is sha256 over the concatenated sorted per-series `dataset_hash` values, so it is content-only and **stable across a no-change rebuild**. The genuine per-run values are `built_at` at top level and `rest_first`/`rest_last` inside each `ohlc-reach` series row. A rule quarantining `series_digest` would quarantine nothing.

Three further measurements that decide the design:

- **The holdout is a shape mismatch, not a missing field.** Its series key is `ADA` while the file is `ADA/EUR/1440.parquet` — the path is not derivable from the key. Its `manifest_sha256` is opaque: 367 reconstruction candidates, zero matches, so it maps to no slot of known grade.
- **Identity must be frame content, never file bytes.** `ohlc-full` rebuilds byte-identically (36/36), but `ohlc-15m` does not — polars moved row-group boundaries between 1.42.1 and 1.43.2 — while `dataset_hash` recomputes 36/36 and 12/12. The repo's existing grade is correct and this contract must not introduce a byte grade.
- **Live manifest consumers are exactly two**: `_manifest_sha256s` (collects the key `sha256`, feeding `_verify_new_files`, `_verify_outgoing`, `ObservedReader._vouched_for`) and `cli/data/rebuild.py:260` (`["basket_sha256"]`, raising on `KeyError`).

## The contract

A conformant manifest is exactly:

```json
{
  "schema_version": 1,
  "written_at": "2026-08-24T09:00:00+00:00",
  "set_sha256": "<64 hex>",
  "series": {
    "ADA/EUR/1440.parquet": {"sha256": "<64 hex>", "rows": 2842,
                             "first_ts": "2018-09-28 00:00:00+00:00",
                             "last_ts": "2026-07-09 00:00:00+00:00"}
  },
  "provenance": { }
}
```

**`series` is keyed by the parquet's path relative to the dataset root.** This is the load-bearing decision: the path IS the key, so no consumer ever derives one, and all four existing shapes flatten into this one. It is what makes path binding possible without per-set knowledge.

**`sha256` is `dataset_hash`** — sha256 of the frame's canonical CSV — the grade every writer already vouches and both consumers already compare. Not file bytes (measured unstable across polars versions).

**`set_sha256`** is sha256 over the concatenated per-series `sha256` values in sorted key order — the existing `basket_sha256` recipe, renamed to one name, and reproducible by construction.

**`written_at`** is when the manifest was written. That is well-defined for every writer, unlike the three spellings it replaces, whose *meanings* genuinely differ (retrieved / assembled / pulled-from-elsewhere). Collapsing three spellings is a rename; collapsing three meanings is a semantic decision, so it is taken explicitly here: the source-specific meaning moves into `provenance`.

**`provenance` is the quarantine.** Machine-local paths, wall-clock stamps, per-run windows (`rest_first`/`rest_last`), and anything else that moves without content moving live here. It is free-form, **excluded from `set_sha256` by construction**, and no consumer may depend on it. This is what stops a false drift alarm without naming individual keys.

## Scope: which manifests this binds

The contract binds manifests **this repo writes**, identified by `schema_version`. A manifest without that key is legacy and is not read by the contract reader at all.

**The external freeze is excluded, and the sidecar is its normalised form.** `docs/reference/vouched-dataset-hashes.jsonl` already carries `dataset` / `relpath` / `dataset_sha256` / `rows` / `first_ts` / `last_ts` per series in one uniform shape — that *is* the contract's content for a set we cannot rewrite. The freeze is not accommodated and the contract is not loosened to fit it, which is what killed round 1.

## Migration: manifest-only, no parquet is touched

A one-shot converter reads each dataset's existing parquets, recomputes `rows` / `first_ts` / `last_ts` / `dataset_hash`, and writes the conformant manifest. **No parquet byte changes**, so nothing invalidates the committed sidecar hashes or the registry records citing byte hashes of `ohlc-full`. This also sidesteps `ohlc-15m`'s row-group instability entirely, which a full rebuild would have walked into for no gain.

`rebuild.py:260` reads `basket_sha256` and raises on `KeyError`; it moves to `set_sha256` in the same change, since a converted manifest no longer carries the old key.

## What "resolved" requires

1. The contract exists as committed, runnable code — one writer and one reader in `cli/`, called by every producer, so the shape cannot drift per-writer again.
2. Every writer emits it.
3. A conformance test walks every manifest on disk and asserts it, with legacy sets either converted or explicitly named.
4. The migration has run and the manifests on disk conform.
5. **The waiting consumer is discharged**: `_attestation_failure` takes its path→hash map from the manifest as well as the sidecar, so manifest-attested sets become path-bound and a swap inside one is no longer invisible.
6. The topic's three factual errors are corrected in place.

## Out of scope, stated

The holdout freeze process itself. It is not in this repo, and the sidecar covers it.
