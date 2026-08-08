# Verifiable dataset provenance for the trial registry

Closes the going-forward half of [[T0065]]'s execution-reproducibility round. Master-plan §8 requires a backtest to reference the data it was fitted on rather than "latest". Today that reference is a single opaque `dataset_hash` string the caller supplies, and for **44 of 46** records it can no longer be resolved to anything. This spec replaces the opaque string with a structure the store derives from disk, checks in two layers, and records what is known about the historical ones.

## Context — the failure this is designed against

The registry validates `dataset_hash` as "a non-empty str" and nothing more (`cli/registry/record.py`, `_REQUIRED_CALLER`). Whatever a caller passed became the permanent provenance of that verdict. The drivers that computed those strings were never committed, and `git log --all --diff-filter=D` confirms none was ever committed and later deleted.

Measured over the committed registry (46 records, four distinct `dataset_hash` values, schema versions 2 and 3 only):

| hash | records | trials | schema | status |
|---|---|---|---|---|
| `ba47e37e` | 38 | 1–35, 40–42 | 32×v2 + 6×v3 | unresolved — ~226,000 candidate recipes tested, none reproduces |
| `81dc9b44` | 4 | 36–39 | v3 | unresolved (the 4h primitive) |
| `45275ebe` | 2 | 43–44 | v3 | unresolved; record 44 is the deployable. The runbook's stated recipe does not verify |
| `cccb8d17` | 2 | 45–46 | v3 | **reproduces** — `sha256(hex_4h + ":" + hex_15m)`, re-verified against the live file |

So 44 of 46 records carry a digest nobody can recompute. Three facts shape the design:

- **The data did not move.** `data/ohlc-full`'s 36 per-series `sha256` re-derive from disk today and its parquet mtimes predate every registry record. The loss is of the *derivation*, not the bytes.
- **Extent rescued what the digest could not.** Record 1 was re-identified from its own `run_ref` (`docs/research/06.phase4-a1-results.md` headlines "full history 2013→2026, 4581 returns"; 4582 daily union stamps yield 4581 returns, and `UNION_BARS = {1440: 4582, 240: 27338}` is pinned in `tests/test_record44_legs.py`) against `data/ohlc-full`'s daily span 2013-09-10 → 2026-03-31, plus the structural impossibility of the only alternative daily dataset (the retired v0 seed: 721 bars from 2024-07-17, zero per-series hash overlap). Record 44 is carried the same way by the extent pins in `tests/test_crossfreq_system.py`.
- **One hash survived, and the reason is instructive.** `cccb8d17` reproduces solely because `docs/specs/00045-b1-seasonality-conditioning-design.md` wrote the recipe down, operands and all. It survived by documentation discipline, which is not a mechanism.

**The manifest zoo is a hard constraint, not a detail.** Six committed writers plus one uncommitted one produce three `series` shapes, two per-series digest key spellings, three timestamp keys, and three set-level digest spellings — measured, not assumed:

| writer | `series` shape | per-series digest key | set-level digest | timestamp key |
|---|---|---|---|---|
| `cli/ohlc/ingest.py` | **list** of rows carrying `symbol`/`interval` | `dataset_hash` | none | `fetched_at` |
| `cli/backfill/backfill.py` (and `substrate15m.py`, which delegates to it) | `series[pair][interval]` | `sha256` | `basket_sha256` | `fetched_at` |
| `cli/derivatives/funding.py`, `cli/derivatives/oi.py` | `series[symbol]` | `sha256` | `basket_sha256` | `fetched_at` |
| `cli/ohlc/reach.py` | **list** of rows carrying `symbol`/`interval` | `sha256` | `basket_sha256` + `detached_sha256` | `built_at` |
| *(no committed writer)* `data/ohlc-holdout-2026-07-10` | `series[symbol]` | **none** | `manifest_sha256` (top-level; reproduces from no recipe tried) | `pulled_at` |

The holdout is [[T0064]]'s out-of-sample dataset — the deployable's missing validation evidence. **Any design that requires `basket_sha256`, or that assumes an interval level in `series`, or that assumes a per-series digest, refuses the holdout and is therefore disqualified.** `cli/data/sync.py::_manifest_sha256s` already documents this zoo and already solves a neighbouring problem shape-agnostically; this spec follows that precedent.

## Decisions

### D1 — The record carries a `datasets` block: the slice that was declared, what that slice *is*, and what the dataset *is*

Schema 4 adds one structure, keyed by dataset name. Values below are the measured capture of `data/ohlc-full` for a daily+4h read:

```json
"datasets": {
  "ohlc-full": {
    "select": ["1440", "240"],
    "series_digest": "76edb3a0633a5ab5f9f2c6f9d7b3af4d2000c1aaab22c69da0e278cbe88eafb0",
    "extent": {"series": 24, "rows": 240377,
               "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T20:00:00+00:00"]}
  }
}
```

Three fields, three different jobs; none replaces another. Nothing in the block is a per-run value — no `fetched_at`, no `pulled_at`, no `built_at` — so a re-fetch that changes only the stamp cannot move `dataset_hash`.

**`select` — the slice the caller declares.** Not "what the trial read": the registry cannot observe the run, only the record. What it *can* do is resolve the declaration against the manifest and record what it resolves to, so an under-declared slice is visible as a number rather than silently collapsing.

`select` is a list of addressing tokens; the store resolves it to a set of series leaves and refuses anything it cannot. Resolution is **AND across dimensions, OR within one**, and a *dimension* falls out of the walk rather than out of per-set knowledge: for a nested manifest a dimension is the nesting depth (`level0` = pair, `level1` = interval); for the two list-shaped manifests it is the row's own address field (`symbol`, `interval`). Measured against `data/ohlc-full`:

| `select` | resolves to | rows |
|---|---|---|
| `[]` (the whole set, explicitly) | 36 series | 1,052,322 |
| `["1440"]` | 12 series | 34,460 |
| `["240"]` | 12 series | 205,917 |
| `["1440", "240"]` | 24 series | 240,377 |
| the 10 EUR pairs + `["1440", "240"]` | 20 series | 202,405 |
| `["BTC/EUR", "1440"]` | 1 series | 4,581 |

Without this the design would be a *regression*: a daily-only trial, a 4h-only trial and record 44's daily+4h trial would all name `ohlc-full` and receive one identical digest, where history gave them three distinct ones. With it they receive three distinct extents and therefore three distinct digests — and the 10-EUR-pair row above is exactly what `tests/test_crossfreq_system.py`'s frozen per-asset `EXTENT` table sums to (29,032 daily + 173,373 4h), so the resolution reproduces an independently-pinned number rather than asserting one of its own.

**`extent` — the identifier, scoped to the resolved slice.** `series` is the matched leaf count, `rows` their sum, `span` is `min(first_ts) → max(last_ts)` with each stamp parsed by `datetime.fromisoformat` before comparison (the holdout spells its stamps with a space separator, the rest with `T`, and a string comparison across those two spellings would be wrong). A *series leaf* is any dict carrying all three of `rows`, `first_ts`, `last_ts` — the only structural assumption in the module. `extent` is the half that survives losing the manifest itself, which is precisely the failure class being designed against: coarse, human-readable, and — as record 1's rescue shows — enough to identify a dataset against the realistic alternatives.

Whole-set extents, measured, for the four datasets on disk:

| dataset | `series` | `rows` | `span` |
|---|---|---|---|
| `ohlc-full` | 36 | 1052322 | 2013-09-10T00:00:00+00:00 → 2026-03-31T23:00:00+00:00 |
| `ohlc-15m` | 12 | 3122044 | 2013-09-10T23:45:00+00:00 → 2026-03-31T23:45:00+00:00 |
| `derivatives-funding` | 10 | 68281 | 2020-01-01T00:00:00+00:00 → 2026-06-30T16:00:00.005000+00:00 |
| `ohlc-holdout-2026-07-10` | 10 | 30032 | 2013-09-10T00:00:00+00:00 → 2026-07-09T00:00:00+00:00 |

**`series_digest` — the drift alarm, scoped to the whole dataset.** `compute_hash({"series": manifest["series"]})`: the registry's own `compute_hash`/`canonical_json` over the manifest's `series` subtree and nothing else. It works for every shape because it makes no assumption about any; where the manifest carries per-series `sha256`/`dataset_hash` values it transitively commits to every one of them, so a `basket_sha256` is covered without being named; where none exists (the holdout) the digest still moves on any change to any series entry's rows or span. Formatting is irrelevant (the digest is over the parsed object), so a re-indent does not fire it.

It is deliberately **dataset**-scoped where `extent` is slice-scoped, and the asymmetry buys something specific: one dataset has one `series_digest`, so that value can be pinned once in the committed catalog and a record's digest stays checkable from committed state after the data leaves the machine (D5). A slice-scoped digest would have as many values as there are ways to read the set, and could be pinned nowhere.

Digesting the **whole** manifest was rejected on measurement, not taste. `data/ohlc-full` records `source: "../zcrypto-kraken-data/kraken-ohlcvt-updates"` while `data/ohlc-15m` records `source: "/home/zhaow/Projects/zcrypto-kraken-data/kraken-ohlcvt-updates"` — the same source directory in two spellings, so a rebuild from identical bytes at a different working directory moves a whole-manifest digest. `cli/ohlc/reach.py` also writes the config knob `min_seam_overlap` at top level. Excluding a hand-listed set of "volatile" top-level keys would make the design's correctness depend on that list staying exhaustive across writers nobody has written yet; scoping the digest to `series` drops the list and the burden with it.

**`select` is stored normalised — `sorted(set(tokens))`.** `canonical_json` sorts dict keys but preserves list order, so an un-normalised `select` would make `dataset_hash` sensitive to the order and multiplicity of the caller's list: measured with the repo's own `compute_hash`, `["1440","240"]` and `["240","1440"]` produce different digests for one identical read. A digest that identifies the read must not have two spellings. Normalisation only reorders and de-duplicates — it never rewrites a token — so the unknown-token refusal still names the caller's own value.

Never read parquet **at capture**. The registry must not become an O(dataset) operation on every append, and coupling the store to every dataset's on-disk layout is the coupling `sync.py` already refused. The bytes are reached in D5's layer instead, which is explicitly allowed to be expensive.

**Rejected — `basket_sha256` as the drift alarm** (the obvious choice): absent from the holdout and from `cli/ohlc/ingest.py`'s manifests, and spelled three ways across the writers that do emit one. It would disqualify [[T0064]]'s dataset.

**Rejected — extent alone.** It cannot distinguish two datasets of identical shape and different content: an identifier without an integrity check.

**Rejected — digest alone, recipe merely committed.** That is the status quo plus documentation discipline — the thing that failed, and the thing that saved `cccb8d17` by luck.

**Rejected — refusing a `select` that leaves a dimension unnamed** (forcing every record to enumerate pairs *and* intervals). It would make `select: []` — the honest "the whole set" — the only concise spelling, and it buys nothing the resolved `extent` does not already show: a declaration that names only intervals resolves to 24 series where the trial read 20, and the record says 24. The residual is named below rather than papered over.

**Named residual, already registered:** the record attests what the caller *declared*, resolved against real data. Nothing verifies that the run read only that slice — closing it needs the committed research-run command, which is [[T0065]]'s other sub-item and already registered there; no new topic is owed.

### D2 — `dataset_hash` is derived, and there is no argument through which to supply it

`dataset_hash = compute_hash(datasets)` — the registry's **own** `compute_hash`/`canonical_json`, already committed, already tested, already what produces `record_hash`. The derivation cannot be lost without simultaneously breaking the registry's own record hashing, which every record depends on and every test exercises. The recipe stops being a fact about a driver and becomes a fact about the store.

**The mechanism is the file's existing machinery, not a new rule.** `dataset_hash` and `datasets` both move into `_STORE_OWNED`, whose sole existing job is `validate_caller_fields`'s "caller must not supply store-owned field(s)" check. A caller passing either is rejected by code that already exists, and `validate_stored_record`'s caller-half re-validation already excludes `_STORE_OWNED` keys, so the loader does not fight the writer.

Two mechanical constraints follow, and both are the difference between this working and bricking the live registry:

- `_BASE_STORED_KEYS` is *derived* from `_STORE_OWNED` and is the set required of **every** record at every schema version. `datasets` therefore may not enter that derivation, or all 46 committed records become unloadable for a missing key. The tuple splits: `_STORE_OWNED_ALWAYS` (which now gains `dataset_hash`, present in every record since schema 2) feeds `_BASE_STORED_KEYS`; `_STORE_OWNED = _STORE_OWNED_ALWAYS + ("datasets",)` feeds only the caller-surplus check and the caller-half exclusion.
- `datasets` is version-scoped in `_EXPECTED_STORED_KEYS` exactly as `variant` already is — `{2: base, 3: base | {"variant"}, 4: base | {"variant", "datasets"}}`. A `4:` entry must exist or a schema-4 load raises a bare `KeyError`; and the surplus check then rejects a pre-4 record that carries `datasets`, with no extra rule.

`TrialRegistry.append()` loses its `dataset_hash` parameter and gains `datasets: dict[str, list[str]]` (name → `select`). It gains **no** data-root parameter — see D4. `TrialRegistry.__init__` is untouched and keeps its single-argument signature.

**What actually reads this file at runtime, measured:** `cli/portfolio/record44_legs.py` constructs `TrialRegistry(path)` (two call sites) and therefore goes through the loader. `cli/engine/command.py` does **not** — it passes `--registry` down to `cli/engine/soak.py::_load_registry_record`, which `json.loads` each line directly and pulls record 44's `metrics`. The engine's soak path is therefore unaffected by the loader change, and equally *not* covered by D3's invariant; it never reads `dataset_hash` or `datasets` at all. That pre-existing gap (the live engine's self-test reads the registry without any chain or hash validation) is real but out of this spec's scope, and is registered rather than left as prose.

### D3 — Layer 1: the invariant is enforced at LOAD, not only at append

`validate_stored_record` re-checks, for every schema-4 record it reads: the block is a non-empty dict whose entries carry a 64-char `series_digest`, an `extent` dict and a `select` list; and `compute_hash(rec["datasets"]) == rec["dataset_hash"]`. This is also where `dataset_hash`'s type check now lives, since it is store-owned and `validate_caller_fields` no longer sees it.

Append-time validation alone would be theatre here. **`append()` has no production caller** — all 46 records were written by scripts that were never committed, which is the whole reason this spec exists. A hand-written record is the *normal* case, not the exotic one, so the check that matters is the one every reader runs.

**And this layer is honest about its limit: it proves internal consistency, nothing about disk.** A hand-writer who invents a `datasets` block and calls `compute_hash` on it satisfies every check here, forever. Layer 1 kills the *accidental* forgery — a copied block, a stale digest, an edited extent — and it is the layer that runs everywhere, including on a machine with no `data/`. It does not kill the *deliberate* one. That is D5's job, and shipping D3 alone would rebuild the same failure in richer clothes.

Pre-schema-4 records are untouched by all of it: `_LOADABLE_SCHEMA_VERSIONS` gains `4` and keeps `2` and `3`, and an absent `datasets` block below schema 4 is normal.

### D4 — The store captures the block from disk, from a root the caller cannot choose

Given `datasets={"ohlc-full": ["1440", "240"]}`, `append` reads `<repo>/data/ohlc-full/manifest.json` and builds the block. Six refusals, each naming the offending value:

1. the manifest is absent or unparseable;
2. it carries no non-empty `series`, or no series leaf carrying all of `rows`/`first_ts`/`last_ts` (a `series` that exposes neither identifies nothing);
3. a series timestamp that `datetime.fromisoformat` cannot parse;
4. a `select` token that appears in no leaf address (the message lists the addressable tokens);
5. a `select` that resolves to zero leaves — tokens from different dimensions that never co-occur;
6. anything above, for any named dataset: the block is all-or-nothing.

**The data root is a module constant, not a parameter.** `capture_datasets(selection, data_root)` takes one so it is testable against a temporary tree, but `append()` calls it with `DATA_ROOT = <repo>/data` and exposes no argument for it. This mirrors `_validate_run_ref`, which anchors to `_REPO_ROOT` for exactly the same reason. It is also how the two layers agree on what to compare: they can only compare if they read the same root, and a constant is how they agree without a convention.

**What the constant root does and does not buy, stated exactly.** It removes the *parameter* — `append(datasets={"x": []}, data_root=Path("/tmp/anything"))` cannot be written. It does **not** remove the fabrication *path*: `data/` is gitignored and writer-controlled, so `mkdir data/x && write manifest.json` still produces a capturable dataset. Nothing at append time can close that, because append reads exactly one file. The layer that reaches past the manifest to the bytes is D5, and the honest guarantee of the pair is stated there.

**A refusal, never a warning.** A record whose provenance could not be captured must not exist; the alternative is a record that looks pinned and is not, which is exactly today's state.

**Named cost, accepted:** a trial can only be registered on a machine where its datasets sit under the repo's own `data/`, so registering from a bare checkout is impossible and a non-default `data_dir` in `zcrypto.toml` is not a registration root. That is the price of removing the root parameter, and the failure being fixed is precisely a record written without the data being read at all.

**Rejected — caller supplies, registry validates.** On a machine without the datasets it degrades to trusting the caller, so the failure mode returns exactly where verification is hardest.

### D5 — Layer 2: re-derive from disk, re-hash the bytes the manifest vouches for, and fall back to the committed pin

`tests/test_trial_registry_provenance.py` gains a second guard beside the `run_ref` one it already carries. For every schema-4 record in the committed registry, **per named dataset**, exactly one of three verdicts:

1. **The manifest is present here** → re-run `capture_datasets({name: entry["select"]}, DATA_ROOT)` and compare to the stored entry. A disagreement is a **mismatch** and the failure message carries the reason verbatim — a value that moved, or a refusal (unknown token, unreadable manifest) with its own text. Additionally, where the manifest vouches per-series `sha256` values, every vouched hash must be reproduced by some parquet under the dataset root: `dataset_hash(read_parquet(p))` over `rglob("*.parquet")`, the same `cli/ohlc/dataset` pair `cli/data/sync.py::_verify_new_files` already uses for the neighbouring problem. Measured cost on this machine: 0.7 s for `ohlc-full` (36 files), 0.9 s for `ohlc-15m`, 0.1 s for `derivatives-funding`.
2. **The manifest is absent here** → **not** a mismatch. The dataset was never fetched on this node, or was retired; both are normal and neither is evidence about the record. The record is still checked against committed state: its `series_digest` must equal the pin `docs/reference/data-catalog-full.md` carries **in that dataset's own section**, so the name↔digest binding is checked and not merely the digest's presence somewhere in the file. That check needs no `data/` at all, so it holds on a bare checkout and after the bytes are gone.
3. **The record names a dataset whose section carries no matching pin** → a finding, naming the digest and the file to add it to. That is the forcing function for a new canonical set: the pin lands with the first record that reads it, in the same change.

**Why the gating is not a detail.** Keying the whole layer to one dataset's presence, and scoring every `RegistryError` as a mismatch, would make "this node has not fetched that set" indistinguishable from "this block is forged" — and would permanently red the suite for anyone registering a trial against a set they have and someone else does not. Measured on this machine: `data/` holds `derivatives-funding`, `ohlc-15m`, `ohlc-full`, `ohlc-holdout-2026-07-10`, `snapshots`, `universe` — and **not** `derivatives-oi` (a documented hot set, ~189 MB, staged for the B2 family) or `ohlc-reach`. Retirement is not hypothetical either: the v0 `ohlc` set was retired 2026-07-18 and is absent from disk and the NAS.

**The honest guarantee, and it is not "the record matches the data" without qualification.** Layer 1 proves the record is internally consistent. Layer 2 proves the block agrees with the manifest **present on this machine**, and — for the sets whose manifest vouches per-series hashes — that those vouched hashes are the hashes of parquet files that actually exist there. A fabricated `data/x/manifest.json` therefore survives only if its author also produced parquet reproducing every hash they invented, which is no longer "with extra steps". The one set where the link cannot be closed at all is `ohlc-holdout-2026-07-10`: its manifest carries no per-series digest, so for it the guarantee stops at rows and spans. Said plainly rather than left to be discovered.

**The guard is live on day one, with zero schema-4 records.** A test that only asserts over an empty set is a decoration, so the layer ships with a constructive companion, exactly as `test_a_new_record_without_committed_provenance_would_fail_this_test` does for `run_ref`: build one honest record from `capture_datasets` over the real `data/ohlc-full`, assert it re-derives; forge its `series_digest`, assert it is flagged; inflate its `extent`, assert it is flagged; name a dataset that is neither on disk nor in the catalog, assert it is flagged; and pass a forged vouched-hash set to the parquet check, assert every forged hash comes back unattested.

**Two named limits, neither hidden.** Where `data/` is absent entirely, only the committed-pin half runs, on the repo's existing data-dependent-test convention — the layer protects the research machine where records are actually written, not a bare CI checkout. And it will legitimately go red if a canonical dataset is refreshed after a record was written against it: `extent` and `series_digest` both move on a refresh, the registry is append-only, and the record can never be edited. The remedy at that point is a frozen, both-direction-asserted exemption pin naming the affected trial ids and the refresh that caused it — the machinery `LEGACY_UNCOMMITTED` already is in that file. It is deliberately **not** pre-built: there is nothing to exempt yet, and an empty exemption set is a hole waiting for a lazy commit.

### D6 — Historical hashes get a committed legacy table whose evidence executes

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 `dataset_hash`. The shape (the four real entries are tabulated below):

```json
{"dataset_hash": "...", "records": [1, 2], "referent": ["data/ohlc-full"], "confidence": "inferred",
 "evidence": [{"kind": "extent", "dataset": "ohlc-full", "select": ["BTC/EUR", "1440"],
               "extent": {"series": 1, "rows": 4581, "span": ["...", "..."]}}],
 "notes": "..."}
```

Six keys, no derived duplicates — there is no `basis` beside `evidence[].kind` and no `reproduced` beside `confidence`, because two spellings of one fact drift and only one of them gets corrected.

`records` is the sorted list of trial ids the hash stamps, and the test asserts it against the registry: the pre-4 set is frozen, so a pin that names the wrong records fails immediately. `referent` is always a **list** of dataset roots, because one of the four hashes has two: `cccb8d17`'s recipe takes operands from `data/ohlc-full` and `data/ohlc-15m`, and a single-path referent would be a false one.

**Every pin's `evidence` is a list of executable items, and the test executes each by `kind`** — this is what makes the file a pin rather than a paragraph in JSON clothing:

- `extent` — `capture_datasets({dataset: select}, DATA_ROOT)` must reproduce the stated extent (skipped, per item, where that dataset's manifest is absent here).
- `citation` — the named committed file must exist and contain the stated literal.
- `recipe` — the recipe is executed and must reproduce the pin's own `dataset_hash`.

`confidence` is `inferred` or `reproduced`, and it is not a label anyone types freely: the test asserts `confidence == "reproduced"` **iff** the pin carries a `recipe` item. The distinction is load-bearing and must survive into the file's own wording: **`inferred` means an arithmetic match plus an exclusion, not a recomputation.** A future reader must not mistake it for verification — an executable `extent` item proves the *evidence quoted in the pin is still true of the referent*, never that the hash was recomputed.

The four entries, with the evidence measured this session:

| hash | records | referent | confidence | evidence (kind) |
|---|---|---|---|---|
| `ba47e37e` | 1–35, 40–42 | `data/ohlc-full` | inferred | extent: the 10 EUR pairs at `1440` — 10 series, 29,032 rows, 2013-09-10 → 2026-03-31 |
| `81dc9b44` | 36–39 | `data/ohlc-full` | inferred | citation: `docs/specs/00045-…-design.md` names it verbatim as "the literal trials-37–39 dataset hash" |
| `45275ebe` | 43–44 | `data/ohlc-full` | inferred | extent: the 10 EUR pairs at `1440`+`240` — 20 series, 202,405 rows, the exact sum of `tests/test_crossfreq_system.py`'s frozen `EXTENT` table |
| `cccb8d17` | 45–46 | `data/ohlc-full`, `data/ohlc-15m` | reproduced | recipe: `sha256(a + ":" + b)`, `a` = `81dc9b44…` (ohlc-full's 4h primitive), `b` = `0fed24a6…` (`data/ohlc-15m`'s `basket_sha256`) |

`81dc9b44` gets a citation rather than an extent because the committed evidence identifies it by *name* ("the trials-37–39 dataset hash") and nothing ties it to a row count; inventing an extent for it would be manufacturing the very kind of unchecked inference this table exists to prevent. Its `referent` is `data/ohlc-full` by exclusion — the only 4h set that existed at iter-074 — and the notes say so in those words.

Prose was rejected because [[T0065]] is archived on resolution and archived topics are never re-read — the knowledge would leave with it and the next reader would repeat the investigation. A file whose evidence the tests execute cannot rot the same way.

The completeness test reads the real registry and asserts every distinct pre-schema-4 `dataset_hash` appears in the table. It is a guard against the table silently losing an entry — **not** "completeness by construction": the historical set is frozen at four the moment `SCHEMA_VERSION` is 4, so the test asserts over constants and its value is regression protection, nothing grander.

### D7 — Eight guards, each proven by a constructed failure

1. **Load-time round-trip** — a schema-4 record whose `dataset_hash` is not `compute_hash(datasets)` fails to load.
2. **No caller path to the digest** — `validate_caller_fields` rejects a caller supplying `dataset_hash` or `datasets`; `append` has neither parameter, nor a data-root one.
3. **Capture refuses an absent manifest**, naming the path.
4. **Capture refuses an unknown `select` token**, naming the token and the addressable set.
5. **`select` resolves per dimension** — the recorded extent is the slice, not the whole set.
6. **Legacy completeness** — every distinct pre-4 `dataset_hash` is pinned.
7. **Legacy evidence executes** — a corrupted `extent` evidence item fails against the referent's manifest.
8. **Reproduced means reproduced** — the `cccb8d17` recipe is executed and its target reproduced.

Each is proven through `infra/scripts/mutate-probe.sh` — the guard is mutated, the probe must go red — rather than asserted. D5's layer is proven differently and deliberately: its constructive companion *is* the constructed failure, built from real data at test time, which is stronger than mutating the assertion that would catch it. (Its parquet half could not be mutation-probed anyway: the only file to mutate would be under `data/`, which is gitignored, so the probe's `git checkout --` restore has nothing to restore from.)

## Why this is sustainable, and where it still decays

**Sustainable because the mechanism is not documentation.** The derivation is the store's own hashing; there is no argument through which to bypass the capture or redirect its root; the invariant is re-checked by every reader on every load; the block is re-derived from disk — and the vouched bytes re-hashed — wherever the data exists; and where it does not, the digest still meets a committed pin. None of these depends on anyone remembering a convention.

**Named decay paths:**

- **A refresh of a canonical dataset after a record was written against it** reds D5 for that record, permanently, because the registry is append-only. The remedy is a frozen exemption pin naming the ids and the refresh — loud and reviewable, never silent. The catalog's pin for that set moves in the same change, and the superseded value stays recorded beside it or the absent-dataset check loses its footing.
- **A new canonical set** must gain its catalog `series_digest` pin before a record names it; otherwise D5's third verdict fires on any node that lacks the data. One line, and the failure names it.
- **Dataset rename or relocation** breaks the `name → referent` link. `extent` and `series_digest` still identify the data; the name becomes a historical label, and D5 flags the record until the rename is pinned. Accepted — a rename is a human event that can be recorded.
- **A new manifest shape** that carries no `series`, or whose series leaves lack `rows`/`first_ts`/`last_ts`, is refused at capture rather than mis-captured. Loud, and the fix is one writer-side field.
- **`series_digest` is only as strong as the manifest's own leaves.** For `data/ohlc-holdout-2026-07-10`, which carries no per-series digest at all, it commits to row counts and spans but not to bytes — a content edit preserving both is invisible to it, and the parquet re-hash cannot cover it either. And the holdout's leaves carry the per-run process fields `appended` and `overlap_bars_verified`, so a re-pull that changed only those *would* move the digest without a content change. Both directions of that looseness are the holdout's manifest, not this design.
- **`extent` is coarser than content.** Two slices with identical shape and different values share an extent. That is why `series_digest` sits beside it, and why neither alone was accepted.
- **An under-declared `select` over-states the read.** The record says what the declaration resolved to; the trial may have read less. Visible as a number, not closed here — the research-run command closes it.
- **Where `data/` is absent, only the committed-pin half runs**, and a deliberately fabricated block whose digest happens to be pinned loads clean. Stated here rather than left to be discovered.
- **This fixes nothing retroactively.** The 44 historical records remain unverifiable; D6 documents them, it does not repair them. The registry is append-only and hash-chained, so no design could.

## Verification

- The eight D7 guards, each with a constructed failure that trips it under `mutate-probe.sh`.
- D5's re-derivation layer, with its constructive companion proving all four of its findings bite before any schema-4 record exists.
- A schema-4 record round-trips write → read → re-derive with byte-stable output.
- Pre-schema-4 records still load: the committed 46-record registry loads unchanged, record by record, and an absent `datasets` block below schema 4 is not an error.
- `capture_datasets` produces the measured whole-set extent above for each of the four datasets present on disk — including the holdout, which has no `basket_sha256` and no per-series digest (data-dependent, skipped per dataset where absent).
- `capture_datasets` produces each measured slice extent in D1's resolution table, including the 20-series/202,405-row slice that `tests/test_crossfreq_system.py`'s frozen table independently sums to.
- Two spellings of one `select` list produce one digest.
- Every vouched per-series `sha256` in `ohlc-full`'s manifest is reproduced by a parquet on disk; a forged vouched hash is reported unattested.
- The catalog pins the `series_digest` of every canonical dataset present here.
- Every legacy pin's evidence executes: two extents against the referent's manifest, one citation against the committed spec, one recipe against its own target.

## Out of scope

- **Rewriting historical records** — impossible by construction (hash-chained, append-only); D6 is the alternative. No task in the implementation touches `docs/reference/trial-registry.jsonl`.
- **The committed research-run/backtest command** — [[T0065]]'s other sub-item, design-bearing, its own spec. D1's `select`-is-declared residual belongs to it.
- **`cli/engine/soak.py`'s unvalidated read of the registry** — a pre-existing gap this spec neither creates nor closes (D2). Registered as its own topic at closeout.
- **Re-deriving `ba47e37e` or `81dc9b44`** — ~226,000 candidates and a clean git history say the driver is gone. Consciously dropped, recorded in the legacy table as `inferred`.
- **Verifying whole datasets for their own sake.** The parquet re-hash in D5 runs for the sets a registry record names, not as a general integrity sweep; transfer integrity remains `cli/data/sync.py`'s job.
- **Any change to `spec_hash`**, which has its own immutability rule and is not implicated here.
- **A CLI surface.** No subcommand or option changes, so `README.md`'s Usage section is unaffected.
