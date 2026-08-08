# Verifiable dataset provenance for the trial registry

Closes the going-forward half of [[T0065]]'s execution-reproducibility round. Master-plan §8 requires a backtest to reference the data it was fitted on rather than "latest". Today that reference is a single opaque `dataset_hash` the caller supplies; for **44 of 46** records it can no longer be resolved to anything. This spec replaces the opaque string with a structure the store derives from disk — **for the datasets that actually back trials** — and records what is known about the historical ones.

## Context — the failure, and the failed first attempt

The registry validates `dataset_hash` as "a non-empty str" and nothing more (`cli/registry/record.py`). Whatever a caller passed became permanent provenance. The computing drivers were never committed — `git log --all --diff-filter=D` confirms none was ever committed and deleted — so `ba47e37e` (38 records) and `81dc9b44` (4) are unrecoverable against ~226,000 tested candidate recipes.

**An earlier version of this spec tried to capture provenance generically, from any dataset's manifest. It failed four consecutive rework-and-cold-review rounds** — 10 → 6 → 6 → 5 blocking findings, both reviewers rejecting every round. The defects kept *moving* rather than recurring, and shared one root cause: **the manifest ecosystem has no contract.** Five committed writers produce four `series` shapes and two set-digest spellings; `ohlc-reach` carries a per-run nonce that moves on every rebuild with zero content change; `ohlc-15m`'s `source` is an absolute machine-local path; the holdout has no `basket_sha256` and no per-series `sha256` at all. Each round handled one more shape and met another.

**This version does not attempt generality — that is the entire reshape.** The four residual findings of round 4 are not patched here; they are removed from existence: three concerned datasets now out of scope, and the rest concerned a byte-re-derivation layer this version does not build (D5).

## Decisions

### D1 — Scope is an explicit allowlist of trial-backing datasets

Capture supports a **named list**, each with a declared adapter. Measured against the registry: all four historical hashes trace to `ohlc-full` and `ohlc-15m`, and [[T0064]]'s pending out-of-sample work needs `ohlc-holdout-*`. Nothing else has ever backed a trial.

| dataset | set digest | timestamp | `series` shape | per-series `sha256` |
|---|---|---|---|---|
| `ohlc-full`, `ohlc-15m` | `basket_sha256` | `fetched_at` | `[pair][interval]` nested | yes |
| `ohlc-holdout-*` | `manifest_sha256` | `pulled_at` | `[asset]` flat | **no** |

**Two adapters, not a generic walker.** `derivatives-funding`, `derivatives-oi` and `ohlc-reach` are deliberately excluded: none backs a trial today, and each needs its own adapter when one first does.

**An unlisted dataset is refused, and the refusal names the remedy** — add an adapter. That is the design, not a limitation: when B2 first registers against funding/OI, someone must consciously decide how that dataset's identity is expressed, at the moment they have the context. A generic reader guessing is what produced four failed rounds.

Rejected: normalise all five writers to one manifest contract first. That is a data-pipeline change across code producing canonical data, serving a 46-record registry whose historical entries cannot be repaired — disproportionate, and it cannot touch the holdout's manifest, which this repo does not write. Registered as [[T0132]]; the zoo is a real liability, just not this spec's job.

### D2 — The block records the declared slice, the set's identity, and that slice's extent

```json
"datasets": {
  "ohlc-full": {
    "select": ["1440", "240"],
    "set_digest": "70c2728e0badf7015f6a13f6261bb4d41e58a8047afe91aacc0d0f895d0cc9cd",
    "extent": {"series": 24, "rows": 240377,
               "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T20:00:00+00:00"]}
  }
}
```

**Nothing in the block is a per-run value** — no `fetched_at`, no `pulled_at`, and no `source` (absolute and machine-local for `ohlc-15m`). A re-fetch that changes only a stamp cannot move `dataset_hash`.

**`set_digest` is the adapter's normalisation** of `basket_sha256` or `manifest_sha256` under one name, so the block does not leak which writer produced the manifest. It is deliberately **not** a digest over the selected series' hashes: the holdout carries no per-series `sha256`, so such a field could not exist for the one dataset out-of-sample validation most needs.

**`select` is the slice the caller declares.** Not "what the trial read" — the registry sees a record, never a run. What it *can* do is resolve the declaration against the manifest and record what that resolves to, so an under-declared slice is visible as a number rather than silently collapsing. Resolution is per-adapter over the two shapes above; it is not a generic dimension walker.

**Two emptinesses that must not be confused.** An empty `select` **list** is legal and meaningful — the explicit "whole set". An empty `datasets` **mapping** is refused: a record naming no dataset carries no provenance at all, which is the failure being replaced.

**`select` is normalised before hashing** — sorted, deduplicated — so the digest identifies the slice, not the caller's argument order.

This is what makes genuinely different trials differ: a daily-only run and a daily+4h run on the same dataset produce different blocks and therefore different digests. The first attempt omitted `select` and collapsed three historically distinct trials onto one identical digest — a regression on the very property being replaced.

### D3 — `dataset_hash` is derived, and there is no argument through which to supply it

`dataset_hash = compute_hash(datasets)` — the registry's **own** `compute_hash`/`canonical_json`, already committed, already what produces every `record_hash`. The derivation cannot be lost without simultaneously breaking record hashing, which all 46 records and the whole suite depend on.

Mechanically, `dataset_hash` moves from `_REQUIRED_CALLER` into the store-owned set, exactly as the loader already treats `trial_id`/`timestamp`/`record_hash`. "The caller cannot supply it" then falls out of existing machinery instead of a new rule fighting `validate_stored_record`.

**`_BASE_STORED_KEYS` is derived from `_REQUIRED_CALLER`, and that is the load-bearing detail.** Getting this move wrong stops all 46 records loading — three separate ways — which is exactly how the first attempt broke. The version-scoped `_EXPECTED_STORED_KEYS` entry for schema 4 is required, mirroring how `variant` is already handled.

### D4 — Enforced at load, because `append()` is not the door

There is **no production caller of `append()`** anywhere in `cli/` — all 46 records were written by uncommitted scripts. Bolting the API alone bolts an unused door.

So `validate_stored_record` checks, for `schema_version >= 4`, that `dataset_hash == compute_hash(datasets)`. One hash per record on load: the property becomes a fact about the file rather than about a function signature.

**Named limitation, not a claim:** `cli/engine/soak.py` parses the registry with raw `json.loads` and never calls `validate_stored_record`, so the engine's soak path does not inherit this check.

### D5 — Byte verification is NOT rebuilt; two committed mechanisms already do it

The block attests what the **manifest says**, not what the bytes are. Rather than add a re-derivation layer — where the first attempt's complexity and most of its residual defects lived — this spec names what already closes that gap and does not duplicate it:

- `cli/data/sync.py::_verify_new_files` recomputes each series hash at ingest and refuses content the manifest does not attest.
- `cli/engine/soak.py::instrument_self_check` rebuilds the strategy from `data/ohlc-full` and asserts it reproduces record 44's figures exactly — strictly stronger than a digest comparison, and already running.

**The honest claim is therefore bounded**: a schema-4 record proves *which declared slice of which dataset capture* a trial names, and that its digest derives from that block. It does not prove the bytes were unchanged, and it does not prove the run read only what it declared. The latter is unclosable from inside the registry and belongs to [[T0065]]'s committed research-run command, already registered.

### D6 — Historical hashes get a committed legacy table

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 hash, carrying `referent`, `basis`, `confidence` (`reproduced` | `inferred`), and evidence.

`cccb8d17` is `reproduced` — it re-derives as `sha256(hex_4h + ":" + hex_15m)`, and its entry is **executed** by a test rather than asserted. The other three are `inferred`: `ba47e37e` from the extent match plus the v0 exclusion; `81dc9b44` and `45275ebe` inheriting.

**The qualification lives in the value, not only in a sibling field** — an `inferred` row's `referent` reads `"data/ohlc-full (INFERRED from extent + exclusion — never recomputed)"`, so a careless grep cannot return a bare path that reads as verified fact.

Prose was rejected: [[T0065]] is archived on resolution, and archived topics are never re-read.

## Why this is sustainable, and where it still decays

**Sustainable because the mechanism is not documentation, and because the surface is small.** The derivation is the store's own hashing; enforcement is at load; the allowlist is two adapters over shapes this repo either controls or has frozen. The first attempt's decay came from generality — this version has very little to decay.

- **A new dataset backs a trial** → refused until an adapter exists. Deliberate; the refusal *is* the design.
- **A supported writer changes its manifest shape** → its adapter fails loudly at capture, and a test over every allowlisted manifest on disk goes red. Not silent.
- **Dataset rename** → the `select` key stops matching; `set_digest` and `extent` still identify the data.
- **`extent` is coarser than content** → deliberate; D5 names what already closes it.
- **This repairs nothing retroactively** — 44 records stay unverifiable; D6 documents them.

## Verification

- All 46 existing records still load, asserted against the **real** `docs/reference/trial-registry.jsonl`, not a fixture.
- A schema-4 record round-trips write → read → re-derive.
- Two trials declaring different slices of one dataset get different `dataset_hash`; two declaring the same slice in different order get the same one.
- Every allowlisted dataset present on disk captures without error, its extent matching a measured pin; the test enumerates from disk rather than a hardcoded tuple.
- An unlisted dataset is refused, and the message names the adapter remedy.
- `cccb8d17`'s legacy entry reproduces when executed.
- Each guard proven by a constructed failure through `infra/scripts/mutate-probe.sh`, never asserted.

## Out of scope

- **Rewriting historical records** — impossible (append-only, hash-chained); D6 is the alternative.
- **Manifest normalisation across all writers** — [[T0132]].
- **Byte-level re-verification** — D5; two committed mechanisms already cover it.
- **Proving a run read only what it declared** — [[T0065]]'s research-run command.
- **Adapters for `derivatives-funding`, `derivatives-oi`, `ohlc-reach`** — deferred until one backs a trial (D1).
