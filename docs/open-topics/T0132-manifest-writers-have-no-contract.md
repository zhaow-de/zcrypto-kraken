---
status: open
ripe_when: a generic manifest reader is proposed again, or a manifest writer is being changed for another reason
---

# The manifest writers have no contract, so nothing can read them generically

## Context — what

Five committed writers emit `manifest.json` for canonical datasets, plus one externally-produced freeze. They agree on nothing structural:

| writer | dataset(s) | `series` shape | set digest | timestamp |
|---|---|---|---|---|
| `cli/backfill/backfill.py` | `ohlc-full`, `ohlc-15m` | `[pair][interval]` nested | `basket_sha256` | `fetched_at` |
| `cli/derivatives/funding.py` | `derivatives-funding` | `[symbol]` flat | `basket_sha256` | `fetched_at` |
| `cli/derivatives/oi.py` | `derivatives-oi` | `[symbol]` flat | `basket_sha256` | `fetched_at` |
| `cli/ohlc/reach.py` | `ohlc-reach` | **`list[dict]` rows** | `basket_sha256` + `detached_sha256` | **`built_at`** |
| `cli/ohlc/ingest.py` (v0, retired) | `ohlc` | `list[dict]` rows, hashing under **`dataset_hash`** | **none** | `fetched_at` |
| external freeze | `ohlc-holdout-*` | `[asset]` flat | **`manifest_sha256`** | **`pulled_at`** |

Four `series` shapes, two set-digest spellings, **three** timestamp keys, and one dataset with no set digest under either name. (The table said two until 2026-08-24; `reach.py` has emitted `built_at` since 4735b600 and `fetched_at` appears nowhere in its history, so the row was wrong the day this topic was written. `ingest.py`'s timestamp was recorded as absent and is `fetched_at`; it also spells its content hash `dataset_hash`, which is why `_manifest_sha256s` — matching the exact key `sha256` — never saw a v0 set at all.)

Two further hazards measured 2026-08-08:

- **`ohlc-reach` carries per-run values, but not the one this topic named.** `series_digest` does not exist — the token appears in no writer and no manifest on either root, only in this topic's own prose, so a contract quarantining it would have quarantined nothing. `basket_sha256` is sha256 over the concatenated per-series `dataset_hash` values and is therefore content-only and stable across a no-change rebuild. The genuine per-run values are `built_at` at top level and `rest_first`/`rest_last` inside each series row.
- **Shape does not determine PATH, measured 2026-08-24 across the live hub.** `derivatives-funding` and `derivatives-oi` share the identical `series[SYMBOL].sha256` shape yet lay their files out as `SYMBOL/funding.parquet` and `SYMBOL/oi.parquet`. So a contract that normalises only the `series` SHAPE still leaves a consumer unable to map a hash to a file — the path convention has to be part of it, or be declared in the manifest.
- **`ohlc-15m`'s `source` is an absolute machine-local path.** A manifest rebuilt on another host changes it, so any consumer including `source` in a digest gets a false difference between nodes holding identical bytes.

## Why this matters

This is not a tidiness complaint — it has already cost a full design cycle. Spec `00086`'s first version tried to capture dataset provenance generically from any manifest. It failed **four consecutive rework-and-cold-review rounds** (10 → 6 → 6 → 5 blocking findings, both reviewers rejecting every round). The findings kept *moving* rather than recurring: round 1 was "the holdout set is unregisterable", round 4 was "`derivatives-funding`/`-oi` are unregisterable" and "`ohlc-reach` false-alarms". Every round handled one more shape and met another.

The root cause is that there is no contract to read against, so a generic reader is really a pile of special cases discovered one review at a time. A second design then narrowed to a two-adapter allowlist and still did not converge — five more rounds, stopped by judgement rather than agreement.

**What finally shipped (2026-08-09) did not solve this; it stopped depending on it.** `00086`'s provenance derives dataset identity from the bytes a run reads, so no manifest is parsed in the identity path and the four `series` shapes, two digest spellings, per-run nonce and machine-local path cost it nothing. Its one manifest touch is a vouched-hash cross-check that walks any JSON without extracting structure, so it is not a generic reader either.

So nothing is blocked on this today, and that is precisely the risk: the zoo is unchanged and the next consumer that genuinely needs to read a manifest generically pays the whole cost again. **That is what this topic exists to prevent.**

## Findings so far

- The table above, read from the writers themselves rather than from the files, so it reflects what will be emitted next time rather than what happened to be on disk.
- The holdout manifest is **not ours to normalise** — it is produced by an external freeze process. Any contract has to either accommodate it or explicitly exclude it.
- Nothing currently reads manifests generically. `cli/data/rebuild.py` reads specific ones; `cli/data/sync.py::_verify_new_files` verifies per-series hashes at ingest; and `cli/registry/observed.py` collects vouched hashes for a cross-check that walks any JSON shape without extracting structure — deliberately not a generic reader, and it treats a vouch-nothing manifest as inert rather than failing. So there is no live breakage — this is a latent cost, payable on the next generic consumer.

- **Two attempts at a generic manifest consumer have now failed nine cold-review rounds** — the first squarely against this heterogeneity, the second narrowed to an allowlist and still stopped by judgement rather than convergence. When the trigger fires the answer should be **normalise first**, not read generically. Spec `00086` is NOT such a consumer and no longer waits on this: its provenance identity is computed from file bytes, and its only manifest touch is a vouched-hash cross-check that walks any JSON shape without extracting structure.

## Suggested next steps

- **(waiting consumer — the first one that is real)** [[T0133]] wanted `_verify_new_files` and `ObservedReader.read_series` bound to PATHS rather than hash membership, because two series swapped inside one set leave the hash SET unchanged and pass every membership test. It shipped path binding for sets attested by the committed sidecar (`docs/reference/vouched-dataset-hashes.jsonl`, which carries a `relpath` per line), and **consciously kept membership for sets attested by their own manifest**, because deriving a path per hash is exactly the per-set knowledge this topic exists to remove — a fifth hard-coded reader would have been the wrong payment. So when the contract lands, path-binding those sets is owed, and the residual until then is that a swap inside `ohlc-full`/`ohlc-15m`/`derivatives-*`/`ohlc-reach` is invisible at both consumers.
- **(design, when triggered)** Decide the contract: required keys (`series`, a set digest under ONE name, a timestamp under ONE name), a single `series` shape, and an explicit rule for per-run values — a nonce like `ohlc-reach`'s `series_digest` and a machine-local `source` must be OUTSIDE anything a consumer would hash, or absent.
- **(autonomous, after that)** A single shared writer/reader in `cli/` that every producer calls, so the shape cannot drift per-writer again; plus a test walking every `data/*/manifest.json` on disk and asserting conformance.
- **(decide explicitly)** Whether existing manifests are migrated, versioned in place, or left as legacy shapes behind adapters. They are gitignored data, so a migration is a rebuild, not a rewrite of history.
- **(carry)** `00086`'s two manifest adapters were the concrete statement of what a generic consumer needs — they were **deleted** when the design moved to observed bytes, so a migration has no in-repo consumer to build against. Recover the requirement from `git show 82379bf4:cli/registry/provenance.py` rather than from anything at HEAD.
