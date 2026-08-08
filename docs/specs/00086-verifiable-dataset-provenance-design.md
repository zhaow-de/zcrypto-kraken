# Verifiable dataset provenance for the trial registry

Closes the going-forward half of [[T0065]]'s execution-reproducibility round. Master-plan §8 requires a backtest to reference the data it was fitted on rather than "latest". Today that reference is a single opaque `dataset_hash` string the caller supplies, and for 42 of 46 records it can no longer be resolved to anything. This spec makes the reference **self-describing and machine-checkable by construction**, and records what is known about the historical ones.

## Context — the failure this is designed against

The registry validates `dataset_hash` as "a non-empty str" and nothing more (`cli/registry/record.py`, `_REQUIRED_CALLER`). Whatever a caller passed became the permanent provenance of that verdict. The drivers that computed those strings were never committed, and `git log --all --diff-filter=D` confirms none was ever committed and later deleted — so for `ba47e37e` (38 records, A1 + P1) and `81dc9b44` (4 records) the recipe is gone. Measured 2026-08-08: ~226,000 candidate recipes fail to reproduce either, on a method validated against two known targets.

Three facts shape the design:

- **The data did not move.** `data/ohlc-full`'s 36 per-series `sha256` re-derive from disk today and its parquet mtimes predate every registry record. The loss is of the *derivation*, not the bytes.
- **Extent rescued what the digest could not.** Record 1 was re-identified from its own `run_ref` ("2013→2026, 4581 returns") matching `ohlc-full`'s exact 4581 daily rows over exactly that span, plus the structural impossibility of the only alternative dataset (the retired v0 seed: 721 bars from 2024-07-17). Record 44 is carried the same way by the extent pins in `tests/test_crossfreq_system.py`.
- **One hash survived, and the reason is instructive.** `cccb8d17` reproduces exactly as `sha256(hex_4h + ":" + hex_15m)` — solely because `docs/specs/00045` wrote the recipe down. It survived by documentation discipline, which is not a mechanism.

## Decisions

### D1 — The record carries a `datasets` block; the digest is derived from it

Schema 4 adds one caller-visible structure:

```json
"datasets": {
  "<dataset-name>": {
    "basket_sha256": "<from that dataset's manifest>",
    "fetched_at": "<from that dataset's manifest>",
    "extent": {"<interval>": {"series": <int>, "rows": <int>, "span": ["<first>", "<last>"]}}
  }
}
```

**`extent` is derived from the manifest alone and must stay that way** — `series` is the count of series at that interval, `rows` their SUM, and `span` is `min(first_ts) → max(last_ts)`. For `data/ohlc-full` that is `1440: {series: 12, rows: 34460, span: 2013-09-10 → 2026-03-31}`. Deliberately NOT the union-calendar bar count (4582 at 1440): that number is not in any manifest and recovering it means reading every parquet, which would make registering a trial an O(dataset) operation and couple the registry to the data's schema rather than to its manifest. Sum-of-rows is the stronger identifier anyway — it moves when any single series changes length, where a union count does not.

The two halves do different jobs and neither replaces the other. `basket_sha256` is the **drift alarm** — byte-exact, already produced by committed code. `extent` is the **identifier** — coarse, human-readable, and the only half that survives the loss of a hashing convention, which is precisely the failure being designed against.

Rejected: extent alone. It cannot distinguish two datasets of identical shape and different content, so it is an identifier without an integrity check.

Rejected: digest alone, with the recipe merely committed. That is the status quo plus documentation discipline — the same thing that failed, and the same thing that saved `cccb8d17` by luck rather than by construction.

### D2 — `dataset_hash` is derived, never supplied

`dataset_hash = compute_hash(datasets)` — the registry's **own** `compute_hash`/`canonical_json`, already committed, already tested, already what produces `record_hash`.

This is the load-bearing choice for sustainability: the derivation cannot be lost without simultaneously breaking the registry's own record hashing, which every record depends on and every test exercises. The recipe stops being a fact about a driver and becomes a fact about the store.

`TrialRegistry.append()` **loses its `dataset_hash` parameter entirely** and gains `datasets: list[str]`. Not "validate what the caller passes" — *remove the ability to pass it*. A caller cannot record a provenance that disagrees with disk because there is no argument through which to express one.

### D3 — The registry captures the block itself, and refuses when it cannot

Given `datasets=["ohlc-full", "ohlc-15m"]`, the store reads each `data/<name>/manifest.json`, extracts `basket_sha256`/`fetched_at`, derives `extent` from the manifest's own `series` entries, and stamps the result.

**A missing or unreadable manifest is a refusal, not a warning.** A record whose provenance could not be captured must not exist; the alternative is a record that looks pinned and is not, which is exactly today's state.

**Named cost, accepted:** a trial can only be registered on a machine where its datasets are present. This couples the registry to dataset layout and forbids registering from a bare checkout. That is the price of making fabrication structurally impossible, and it is the right trade — the failure being fixed is precisely a record written without the data being checked.

Rejected: caller supplies, registry validates. On a machine without the datasets it degrades silently to trusting the caller — the failure mode returns exactly where verification is hardest.

### D4 — Historical hashes get a committed legacy table, not prose

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 `dataset_hash`:

```json
{"dataset_hash": "...", "referent": "data/ohlc-full", "basis": "extent",
 "confidence": "inferred", "reproduced": false,
 "evidence": {...}, "recipe": null, "notes": "..."}
```

`confidence` is `inferred` or `reproduced`; `reproduced: true` requires a `recipe` field that a test executes. `cccb8d17` is `reproduced: true` and carries its recipe; `ba47e37e` is `inferred` with the extent evidence.

Prose was rejected because [[T0065]] is archived on resolution and archived topics are never reviewed again — the knowledge would leave with it, and the next reader would repeat the investigation. A file the tests police cannot rot the same way.

**The distinction is load-bearing and must survive into the file's own wording**: `inferred` means an arithmetic match plus an exclusion, not a recomputation. A future reader must not mistake it for verification.

### D5 — Four properties, each enforced by a test that can fail

1. **Round-trip** — for any schema-4 record, `compute_hash(record.datasets) == record.dataset_hash`.
2. **No fabrication path** — `append()` rejects a `dataset_hash` keyword; proving the structural fix by construction rather than by claim.
3. **Legacy completeness** — every distinct `dataset_hash` among pre-schema-4 records appears in the legacy table. Makes the table complete *by construction*: a historical hash cannot be forgotten, and a future backfill cannot silently omit one.
4. **Reproduced means reproduced** — every legacy entry with `reproduced: true` has its `recipe` executed and its target reproduced. `cccb8d17` becomes a live executable assertion rather than a claim in a document.

Each is proven by construction through `infra/scripts/mutate-probe.sh` rather than asserted.

## Why this is sustainable, and where it still decays

**Sustainable because the mechanism is not documentation.** The derivation is the store's own hashing; the capture path has no bypass; the legacy table's completeness is a test, not a habit. None of these depends on anyone remembering a convention.

**Named decay paths, so they are not discovered later:**

- **Dataset rename or relocation** breaks the `name → referent` link. `extent` and `basket_sha256` still identify the data; the *name* becomes a historical label. Accepted — a rename is a human event that can be recorded.
- **Manifest shape change** changes the `datasets` block shape, so digests before and after are not comparable. Old records stay readable (the loader already carries `_LOADABLE_SCHEMA_VERSIONS`); comparability across the boundary is lost. This is the same class of event as a schema bump and is handled the same way.
- **`extent` is coarser than content.** Two datasets with identical shape and different values share an extent. That is why `basket_sha256` is carried beside it, and why neither alone was accepted.
- **This fixes nothing retroactively.** The 42 historical records remain unverifiable; D4 documents them, it does not repair them. The registry is append-only and hash-chained, so no design could.

## Verification

- The four D5 properties, each with a constructed failure that trips it.
- A schema-4 record round-trips through write → read → re-derive with byte-stable output.
- Pre-schema-4 records still load (`_LOADABLE_SCHEMA_VERSIONS` gains 4, keeps 2 and 3), and their absent `datasets` block is not an error.
- The legacy table's `cccb8d17` entry reproduces its target when its recipe is executed.
- `append()` refuses when a named dataset's manifest is absent, and the refusal names the missing path.

## Out of scope

- **Rewriting historical records** — impossible by construction (hash-chained, append-only), and D4 is the alternative.
- **The committed research-run/backtest command** — [[T0065]]'s other sub-item, design-bearing, its own spec.
- **Re-deriving `ba47e37e` or `81dc9b44`** — ~226,000 candidates and a clean git history say the driver is gone. Consciously dropped, recorded in the legacy table as `inferred`.
- **Any change to `spec_hash`**, which has its own immutability rule and is not implicated here.
