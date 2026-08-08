# Verifiable dataset provenance for the trial registry

Closes the going-forward half of [[T0065]]'s execution-reproducibility round. Master-plan §8 requires a backtest to reference the data it was fitted on rather than "latest". Today that reference is a single opaque `dataset_hash` string the caller supplies, and for **44 of 46** records it can no longer be resolved to anything. This spec replaces the opaque string with a structure the store derives from disk, checks in two layers, and records what is known about the historical ones.

## Context — the failure this is designed against

The registry validates `dataset_hash` as "a non-empty str" and nothing more (`cli/registry/record.py`, `_REQUIRED_CALLER`). Whatever a caller passed became the permanent provenance of that verdict. The drivers that computed those strings were never committed, and `git log --all --diff-filter=D` confirms none was ever committed and later deleted.

Measured over the committed registry (46 records, four distinct `dataset_hash` values, schema versions 2 and 3 only):

| hash | records | schema | status |
|---|---|---|---|
| `ba47e37e` | 38 | 32×v2 + 6×v3 | unresolved — ~226,000 candidate recipes tested, none reproduces |
| `81dc9b44` | 4 | v3 | unresolved (the 4h primitive) |
| `45275ebe` | 2 | v3 | unresolved; record 44, the deployable. The runbook's stated recipe does not verify |
| `cccb8d17` | 2 | v3 | **reproduces** — `sha256(hex_4h + ":" + hex_15m)`, re-verified against the live file |

So 44 of 46 records carry a digest nobody can recompute. Three facts shape the design:

- **The data did not move.** `data/ohlc-full`'s 36 per-series `sha256` re-derive from disk today and its parquet mtimes predate every registry record. The loss is of the *derivation*, not the bytes.
- **Extent rescued what the digest could not.** Record 1 was re-identified from its own `run_ref` ("2013→2026, 4581 returns" — 4582 daily union stamps yield 4581 returns, and `UNION_BARS = {1440: 4582, 240: 27338}` is pinned in `tests/test_record44_legs.py`) against `data/ohlc-full`'s daily span 2013-09-10 → 2026-03-31, plus the structural impossibility of the only alternative daily dataset (the retired v0 seed: 721 bars from 2024-07-17, zero per-series hash overlap). Record 44 is carried the same way by the extent pins in `tests/test_crossfreq_system.py`.
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

### D1 — The record carries a `datasets` block: what was read, what the data *is*, and what it *was*

Schema 4 adds one structure, keyed by dataset name. Values below are the measured capture of `data/ohlc-full`:

```json
"datasets": {
  "ohlc-full": {
    "select": ["1440", "240"],
    "series_digest": "76edb3a0633a5ab5f9f2c6f9d7b3af4d2000c1aaab22c69da0e278cbe88eafb0",
    "extent": {"series": 36, "rows": 1052322,
               "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T23:00:00+00:00"]}
  }
}
```

Three fields, three different jobs; none replaces another.

**`select` — what the trial actually read.** Without it the design would be a *regression*: a daily-only trial, a 4h-only trial and record 44's daily+4h trial would all name `ohlc-full` and receive one identical digest, where history gave them three distinct ones. `select` is the caller's list of addressing tokens (interval and/or symbol), and the store **refuses a token that does not appear in the manifest's `series` subtree** — the token set is the dict keys of that subtree plus, for the list-shaped manifests, the `symbol`/`interval` values of their rows (the only shape knowledge in the module, and it is named). An empty list is legal and means "the whole set"; the key is always present, so choosing the whole set is an explicit act rather than an omission.

**`select` is stored normalised — `sorted(set(tokens))`.** `canonical_json` sorts dict keys but preserves list order, so an un-normalised `select` would make `dataset_hash` sensitive to the order and multiplicity of the caller's list: measured with the repo's own `compute_hash`, `["1440","240"]` and `["240","1440"]` produce different digests for one identical read. A digest that identifies the read must not have two spellings. Normalisation only reorders and de-duplicates — it never rewrites a token — so the unknown-token refusal still names the caller's own value.

**`series_digest` — the drift alarm.** `compute_hash({"series": manifest["series"]})`: the registry's own `compute_hash`/`canonical_json` over the manifest's `series` subtree and nothing else. It works for every shape because it makes no assumption about any; where the manifest carries per-series `sha256`/`dataset_hash` values it transitively commits to every one of them, so a `basket_sha256` is covered without being named; where none exists (the holdout) the digest still moves on any change to any series entry's rows or span. Formatting is irrelevant (the digest is over the parsed object), so a re-indent does not fire it.

Digesting the **whole** manifest was rejected on measurement, not taste. `data/ohlc-full` records `source: "../zcrypto-kraken-data/kraken-ohlcvt-updates"` while `data/ohlc-15m` records `source: "/home/zhaow/Projects/zcrypto-kraken-data/kraken-ohlcvt-updates"` — the same source directory in two spellings, so a rebuild from identical bytes at a different working directory moves a whole-manifest digest. `cli/ohlc/reach.py` also writes the config knob `min_seam_overlap` at top level. Excluding a hand-listed set of "volatile" top-level keys would make the design's correctness depend on that list staying exhaustive across writers nobody has written yet; scoping the digest to `series` drops the list and the burden with it.

**`extent` — the identifier.** Derived from the same `series` subtree by a shape-agnostic walk: a *series leaf* is any dict carrying all three of `rows`, `first_ts`, `last_ts`; `series` is the leaf count, `rows` their sum, `span` is `min(first_ts) → max(last_ts)` with each stamp parsed by `datetime.fromisoformat` before comparison (the holdout spells its stamps with a space separator, the rest with `T`, and a string comparison across those two spellings would be wrong). Measured against the four datasets on disk:

| dataset | `series` | `rows` | `span` |
|---|---|---|---|
| `ohlc-full` | 36 | 1052322 | 2013-09-10T00:00:00+00:00 → 2026-03-31T23:00:00+00:00 |
| `ohlc-15m` | 12 | 3122044 | 2013-09-10T23:45:00+00:00 → 2026-03-31T23:45:00+00:00 |
| `derivatives-funding` | 10 | 68281 | 2020-01-01T00:00:00+00:00 → 2026-06-30T16:00:00.005000+00:00 |
| `ohlc-holdout-2026-07-10` | 10 | 30032 | 2013-09-10T00:00:00+00:00 → 2026-07-09T00:00:00+00:00 |

`extent` is the only half that survives losing the manifest itself, which is precisely the failure class being designed against: coarse, human-readable, and — as record 1's rescue shows — enough to identify a dataset against the realistic alternatives.

Never read parquet. The registry must not become an O(dataset) operation, and coupling it to every dataset's on-disk layout is the coupling `sync.py` already refused.

**Rejected — `basket_sha256` as the drift alarm** (the obvious choice): absent from the holdout and from `cli/ohlc/ingest.py`'s manifests, and spelled three ways across the writers that do emit one. It would disqualify [[T0064]]'s dataset.

**Rejected — extent alone.** It cannot distinguish two datasets of identical shape and different content: an identifier without an integrity check.

**Rejected — digest alone, recipe merely committed.** That is the status quo plus documentation discipline — the thing that failed, and the thing that saved `cccb8d17` by luck.

**Rejected — per-`select` extent** (restricting the leaf walk to the selected slice). Slice semantics differ per manifest shape (AND across dimensions, OR within), so it would put real shape knowledge in the module in exchange for a number the manifest already carries and `series_digest` already commits to. `extent` describes the dataset; `select` names the slice; the pair identifies the read.

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

Given `datasets={"ohlc-full": ["1440", "240"]}`, `append` reads `<repo>/data/ohlc-full/manifest.json` and builds the block. Four refusals, each naming the offending value:

1. the manifest is absent or unparseable;
2. it carries no non-empty `series`, or no series leaf carrying all of `rows`/`first_ts`/`last_ts` (a `series` that exposes neither identifies nothing);
3. a series timestamp that `datetime.fromisoformat` cannot parse;
4. a `select` token appears nowhere in that `series` subtree.

**The data root is a module constant, not a parameter.** `capture_datasets(selection, data_root)` takes one so it is testable against a temporary tree, but `append()` calls it with `DATA_ROOT = <repo>/data` and exposes no argument for it. This mirrors `_validate_run_ref`, which anchors to `_REPO_ROOT` for exactly the same reason: a root the caller chooses is a root the caller can point at a hand-made manifest, and `append(datasets={"x": []}, data_root=Path("/tmp/whatever"))` would be a fabrication path with extra steps. It also makes D5 possible at all — two layers can only compare if they agree on the root, and a constant is how they agree by construction rather than by convention.

**A refusal, never a warning.** A record whose provenance could not be captured must not exist; the alternative is a record that looks pinned and is not, which is exactly today's state.

**Named cost, accepted:** a trial can only be registered on a machine where its datasets sit under the repo's own `data/`, so registering from a bare checkout is impossible and a non-default `data_dir` in `zcrypto.toml` is not a registration root. That is the price of removing the fabrication path, and the failure being fixed is precisely a record written without the data being checked.

**Rejected — caller supplies, registry validates.** On a machine without the datasets it degrades to trusting the caller, so the failure mode returns exactly where verification is hardest.

**Residual gap, named not deferred:** nothing verifies that the run *actually* read only the selected slice — the registry cannot observe the run, only the record. Closing that needs the committed research-run command, which is [[T0065]]'s other sub-item and already registered there; no new topic is owed.

### D5 — Layer 2: the block is re-derived from disk over the real registry

`tests/test_trial_registry_provenance.py` gains a second guard beside the `run_ref` one it already carries: for every schema-4 record in the committed registry, re-run `capture_datasets({name: entry["select"]}, DATA_ROOT)` and assert the result **equals** the stored block. A fabricated block fails; a stale one fails; an invented dataset name fails at the manifest refusal.

This is the same two-layer split the file's own docstring already describes for `run_ref` — an append-time check that must be cheap and total, and a repo-level check that has the real world available and can afford to be expensive. The precedent is not decoration: it exists because the append-time layer structurally cannot see what the repo-level one can.

**The guard is live on day one, with zero schema-4 records.** A test that only asserts over an empty set is a decoration, so the layer ships with a constructive companion, exactly as `test_a_new_record_without_committed_provenance_would_fail_this_test` does for `run_ref`: build one honest record from `capture_datasets` over the real `data/ohlc-full`, assert it re-derives; forge its `series_digest`, assert it is flagged; invent a dataset name that is not on disk, assert it is flagged.

**Two named limits, neither hidden.** The layer needs `data/`, which is gitignored — it skips where the compiled datasets are absent, on the repo's existing data-dependent-test convention, so it protects the research machine where records are actually written rather than a bare CI checkout. And it will legitimately go red if a canonical dataset is ever refreshed after a record was written against it: `extent` and `series_digest` both move on a refresh, the registry is append-only, and the record can never be edited. The remedy at that point is a frozen, both-direction-asserted exemption pin naming the affected trial ids and the refresh that caused it — the machinery `LEGACY_UNCOMMITTED` already is in that file. It is deliberately **not** pre-built: there is nothing to exempt yet, and an empty exemption set is a hole waiting for a lazy commit.

### D6 — Historical hashes get a committed legacy table, not prose

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 `dataset_hash`:

```json
{"dataset_hash": "...", "referent": "data/ohlc-full", "basis": "extent",
 "confidence": "inferred", "reproduced": false, "evidence": {...}, "recipe": null, "notes": "..."}
```

`confidence` is `inferred` or `reproduced`; `reproduced: true` requires a `recipe` a test executes against the stated target. `cccb8d17` is the one `reproduced` entry (`sha256(hex_4h + ":" + hex_15m)`, both operands carried literally); `ba47e37e`, `81dc9b44` and `45275ebe` are `inferred`, carrying their extent evidence and, for `45275ebe`, the negative result that the runbook's stated recipe does not verify.

Prose was rejected because [[T0065]] is archived on resolution and archived topics are never re-read — the knowledge would leave with it and the next reader would repeat the investigation. A file the tests police cannot rot the same way.

**The distinction is load-bearing and must survive into the file's own wording**: `inferred` means an arithmetic match plus an exclusion, not a recomputation. A future reader must not mistake it for verification.

The completeness test reads the real registry and asserts every distinct pre-schema-4 `dataset_hash` appears in the table. It is a guard against the table silently losing an entry — **not** "completeness by construction": the historical set is frozen at four the moment `SCHEMA_VERSION` is 4, so the test asserts over constants and its value is regression protection, nothing grander.

### D7 — Six guards proven by a constructed failure, plus one proven by construction

1. **Load-time round-trip** — a schema-4 record whose `dataset_hash` is not `compute_hash(datasets)` fails to load.
2. **No caller path to the digest** — `validate_caller_fields` rejects a caller supplying `dataset_hash` or `datasets`; `append` has neither parameter, nor a data-root one.
3. **Capture refuses an absent manifest**, naming the path.
4. **Capture refuses an unknown `select` token**, naming the token and the addressable set.
5. **Legacy completeness** — every distinct pre-4 `dataset_hash` is pinned.
6. **Reproduced means reproduced** — the `cccb8d17` recipe is executed and its target reproduced.

Each of the six is proven through `infra/scripts/mutate-probe.sh` — the guard is mutated, the probe must go red — rather than asserted. D5's re-derivation layer is proven differently and deliberately: its constructive companion *is* the constructed failure, built from real data at test time, which is stronger than mutating the assertion that would catch it.

## Why this is sustainable, and where it still decays

**Sustainable because the mechanism is not documentation.** The derivation is the store's own hashing; there is no argument through which to bypass the capture or redirect its root; the invariant is re-checked by every reader on every load; and the block is re-derived from disk over the real file wherever the data exists. None of these depends on anyone remembering a convention.

**Named decay paths:**

- **A refresh of a canonical dataset after a record was written against it** reds D5 for that record, permanently, because the registry is append-only. The remedy is a frozen exemption pin naming the ids and the refresh — loud and reviewable, never silent.
- **Dataset rename or relocation** breaks the `name → referent` link. `extent` and `series_digest` still identify the data; the name becomes a historical label, and D5 flags the record until the rename is pinned. Accepted — a rename is a human event that can be recorded.
- **A new manifest shape** that carries no `series`, or whose series leaves lack `rows`/`first_ts`/`last_ts`, is refused at capture rather than mis-captured. Loud, and the fix is one writer-side field.
- **`series_digest` is only as strong as the manifest's own leaves.** For `data/ohlc-holdout-2026-07-10`, which carries no per-series digest at all, it commits to row counts and spans but not to bytes — a content edit preserving both is invisible to it. And the holdout's leaves carry the per-run process fields `appended` and `overlap_bars_verified`, so a re-pull that changed only those *would* move the digest without a content change. Both directions of that looseness are the holdout's manifest, not this design, and both are visible in the table above.
- **`extent` is coarser than content.** Two datasets with identical shape and different values share an extent. That is why `series_digest` sits beside it, and why neither alone was accepted.
- **D3 alone proves nothing about disk.** Where `data/` is absent, layer 2 does not run, and a deliberately fabricated block loads clean. Stated here rather than left to be discovered.
- **This fixes nothing retroactively.** The 44 historical records remain unverifiable; D6 documents them, it does not repair them. The registry is append-only and hash-chained, so no design could.

## Verification

- The six D7 guards, each with a constructed failure that trips it under `mutate-probe.sh`.
- D5's re-derivation layer, with its constructive companion proving it bites before any schema-4 record exists.
- A schema-4 record round-trips write → read → re-derive with byte-stable output.
- Pre-schema-4 records still load: the committed 46-record registry loads unchanged, and an absent `datasets` block below schema 4 is not an error.
- `capture_datasets` produces the measured `extent` above for each of the four datasets present on disk — including the holdout, which has no `basket_sha256` and no per-series digest (data-dependent, skipped where `data/` is absent).
- Two spellings of one `select` list produce one digest.
- The legacy table's `cccb8d17` entry reproduces its target when its recipe is executed.

## Out of scope

- **Rewriting historical records** — impossible by construction (hash-chained, append-only); D6 is the alternative. No task in the implementation touches `docs/reference/trial-registry.jsonl`.
- **The committed research-run/backtest command** — [[T0065]]'s other sub-item, design-bearing, its own spec. The `select`-is-caller-asserted gap in D4 belongs to it.
- **`cli/engine/soak.py`'s unvalidated read of the registry** — a pre-existing gap this spec neither creates nor closes (D2). Registered as its own topic at closeout.
- **Re-deriving `ba47e37e` or `81dc9b44`** — ~226,000 candidates and a clean git history say the driver is gone. Consciously dropped, recorded in the legacy table as `inferred`.
- **Any change to `spec_hash`**, which has its own immutability rule and is not implicated here.
- **A CLI surface.** No subcommand or option changes, so `README.md`'s Usage section is unaffected.
