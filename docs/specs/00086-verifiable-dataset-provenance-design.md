# Verifiable dataset provenance for the trial registry

Closes the going-forward half of [[T0065]]'s execution-reproducibility round. Master-plan §8 requires a backtest to reference the data it was fitted on rather than "latest". Today that reference is a single opaque `dataset_hash` the caller supplies; for **44 of 46** records it can no longer be resolved to anything. This spec replaces the opaque string with a structure the store derives from disk — **for the datasets that actually back trials** — and records what is known about the historical ones.

## Context — the failure, and the failed first attempt

The registry validates `dataset_hash` as "a non-empty str" and nothing more (`cli/registry/record.py`). Whatever a caller passed became permanent provenance. The computing drivers were never committed — `git log --all --diff-filter=D` confirms none was ever committed and deleted — so `ba47e37e` (38 records) and `81dc9b44` (4) are unrecoverable against ~226,000 tested candidate recipes.

**An earlier version of this spec tried to capture provenance generically, from any dataset's manifest. It failed four consecutive rework-and-cold-review rounds** — 10 → 6 → 6 → 5 blocking findings, both reviewers rejecting every round. The defects kept *moving* rather than recurring, and shared one root cause: **the manifest ecosystem has no contract.** Five committed writers produce four `series` shapes and two set-digest spellings; `ohlc-reach` carries a per-run nonce that moves on every rebuild with zero content change; `ohlc-15m`'s `source` is an absolute machine-local path; the holdout has no `basket_sha256` and no per-series `sha256` at all. Each round handled one more shape and met another.

**This version does not attempt generality — that is the entire reshape.** The four residual findings of round 4 are not patched here; they are removed from existence: three concerned datasets now out of scope, and the rest concerned a byte-re-derivation layer this version does not build (D5).

## Decisions

### D1 — Scope is an explicit allowlist of trial-backing datasets

Capture supports a **named list**, each with a declared adapter. Measured against the registry: all four historical hashes trace to `ohlc-full` and `ohlc-15m`. Nothing else has ever backed a trial.

| dataset | set digest | timestamp | `series` shape | per-series `sha256` |
|---|---|---|---|---|
| `ohlc-full`, `ohlc-15m` | `basket_sha256` | `fetched_at` | `[pair][interval]` nested | yes |
| `ohlc-holdout-*` | `manifest_sha256` | `pulled_at` | `[asset]` flat | **no** |

**The holdout entry is built ahead of its consumer, deliberately.** No trial has ever cited it and `grep -rn ohlc-holdout cli/` returns nothing today. It is in scope because the holdout is the set out-of-sample evaluation reads ([[T0133]]), because a provenance record matters most at exactly the evaluation that decides a deployable, and because its manifest is the **second shape** — a design with one adapter is a special case pretending to be a rule, and the shape is on disk now while the next freeze's is not.

**Two adapters, not a generic walker.** `derivatives-funding`, `derivatives-oi` and `ohlc-reach` are deliberately excluded: none backs a trial today, and each needs its own adapter when one first does.

**The dataset key recorded in the block is the directory name as captured, and each allowlist key also prefix-matches `<key>-…`.** All three sets are frozen — a revision mints a sibling `data/<name>-<stamp>` rather than overwriting (`cli/data/rebuild.py::rebuild_sets`; `docs/reference/data-catalog-full.md`'s hot cluster) — so `ohlc-full-<stamp>` is the canonical's own successor, same writer and same shape. Refusing it would refuse the revision workflow itself.

**An unlisted dataset is refused, and the refusal names the remedy** — add an adapter. That is the design, not a limitation: when B2 first registers against funding/OI, someone must consciously decide how that dataset's identity is expressed, at the moment they have the context. A generic reader guessing is what produced four failed rounds.

Rejected: normalise all five writers to one manifest contract first. That is a data-pipeline change across code producing canonical data, serving a 46-record registry whose historical entries cannot be repaired — disproportionate, and it cannot touch the holdout's manifest, which this repo does not write. Registered as [[T0132]]; the zoo is a real liability, just not this spec's job.

### D2 — The block records the resolved slice, the set's identity, and that slice's extent

```json
"datasets": {
  "ohlc-full": {
    "select": {"intervals": ["1440", "240"],
               "pairs": ["ADA/EUR", "AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR",
                         "ETH/EUR", "LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR"]},
    "set_digest": "70c2728e0badf7015f6a13f6261bb4d41e58a8047afe91aacc0d0f895d0cc9cd",
    "extent": {"series": 20, "rows": 202405,
               "span": ["2013-09-10T00:00:00+00:00", "2026-03-31T20:00:00+00:00"]}
  }
}
```

That is record 44's actual slice, measured from the manifest on disk 2026-08-08.

**Nothing in the block is a per-run value** — no `fetched_at`, no `pulled_at`, and no `source` (absolute and machine-local for `ohlc-15m`). A re-fetch that changes only a stamp cannot move `dataset_hash`.

**`set_digest` is the adapter's normalisation** of `basket_sha256` or `manifest_sha256` under one name, so the block does not leak which writer produced the manifest. It is deliberately **not** a digest over the selected series' hashes: the holdout carries no per-series `sha256`, so such a field could not exist for the one dataset out-of-sample validation most needs.

**`select` is per-axis, and it must be — the pair axis is the one the registry's history actually varies on.** `data/ohlc-full` holds 12 pairs × 3 intervals; `CrossfreqSystemConfig.assets` is 10 and `cli/portfolio/record44_legs.py` reads `<asset>/EUR/<interval>.parquet`, so record 44 is 20 series / 202,405 rows, not the 24 / 240,377 an intervals-only declaration resolves to (+18.8 %). And trials 1–8 (`base=btc_only`) versus 9–16 (`base=equal_risk_basket`) differ on **pairs alone** — an intervals-only `select` gives them one identical digest, reproducing exactly the collapse this decision exists to kill. So each adapter declares its axes:

| adapter | axes | absent or empty axis |
|---|---|---|
| backfill (`ohlc-full`, `ohlc-15m`) | `pairs`, `intervals` | all of that axis |
| holdout (`ohlc-holdout-*`) | `assets` | all of that axis |

An unknown axis key is refused, as is a token that matches nothing — this stays two hand-written adapters, not a dimension walker. `select: {}` is the caller's shorthand for "whole set"; an empty `datasets` **mapping** is refused, because a record naming no dataset carries no provenance at all, which is the failure being replaced.

**`select` is RESOLVED before hashing, not recorded as written** — each axis is expanded to the sorted, deduplicated list of tokens actually selected, an absent or empty axis becoming that axis's full membership. Two consequences, and both are the point: the digest is a function of the **slice**, so `select: {}` and the same slice spelled out hash identically instead of differently; and the stored block states which pairs/intervals were read **without the manifest**, which is gitignored and unreachable from a checkout. `extent` resolves over the cross-product of the selected axes.

### D2a — The block's shape is checked at load, not only at capture

`capture_datasets` is the only *writer* of a block, and D4 explains why the write path is not where enforcement can live: every one of the 46 records was written by direct JSONL, and nothing stops the 47th. Without a load-time shape check, `"datasets": "ba47e37e"` — an opaque caller string, the original failure verbatim — hashes and loads cleanly.

So `validate_stored_record` also checks the block **structurally**, for `schema_version >= 4`: `datasets` is a non-empty `dict`; each value is a dict with exactly `{select, set_digest, extent}`; `select` is a **non-empty** `dict[str, list[str]]` whose lists are **non-empty**, sorted and deduplicated; `set_digest` is 64-char lowercase hex; `extent` is `{series: int, rows: int, span: [str, str]}` with `series >= 1` and `rows >= 1`. Integers are checked `type(x) is int`, the is-strict form `_assert_finite` already uses in the same module: `isinstance(True, int)` is `True`, so a lax check admits `{"series": true, "rows": true}`. No disk access, no adapter knowledge — axis *names* are the adapter's business at capture, the shape is the file's business at load.

**The emptiness clauses are the ones carrying D2's property.** A block whose `select` is `{}`, or whose axes resolve to nothing, or whose `extent` is zero, satisfies every other clause — so it hashes and loads clean while saying nothing about which pairs and intervals were read, which is the entire reason the block exists given that the manifest is gitignored and unreachable from a checkout. Refusing it is free: capture can never emit it, since backfill always resolves both axes and holdout its one, each to at least one token. Note the asymmetry with D2's shorthand — `select: {}` stays legal to *pass*, because capture resolves it to full membership before anything is stored.

### D3 — `dataset_hash` is derived, and there is no argument through which to supply it

`dataset_hash = compute_hash(datasets)` — the registry's **own** `compute_hash`/`canonical_json`, already committed, already what produces every `record_hash`. The derivation cannot be lost without simultaneously breaking record hashing, which all 46 records and the whole suite depend on.

Mechanically, `dataset_hash` moves from `_REQUIRED_CALLER` into the store-owned set, exactly as the loader already treats `trial_id`/`timestamp`/`record_hash`. "The caller cannot supply it" then falls out of existing machinery instead of a new rule fighting `validate_stored_record`.

**`_BASE_STORED_KEYS` is the union of both sets, so the move itself leaves it unchanged — and that is the only reason the move is safe.** Three separate mistakes around it each stop all 46 records loading, which is exactly how the first attempt broke:

1. `validate_caller_fields` type-checks a **hardcoded** tuple containing `dataset_hash`, and `validate_stored_record` re-runs it on every load over a `caller` dict with the store-owned keys stripped — so leaving `dataset_hash` in that tuple raises a bare `KeyError` on record 1.
2. Putting `datasets` in `_REQUIRED_CALLER` makes that function's own missing-check demand it from every stored record, including all 46 schema-2/3 lines that predate it. `datasets` therefore belongs in **neither** key set: it is version-scoped only.
3. `_EXPECTED_STORED_KEYS` needs an explicit `4:` entry, mirroring how `variant` is already handled, or a schema-4 load raises a bare `KeyError`.

Requiring `datasets` for `schema_version >= 4` is then an explicit check in `validate_stored_record`, not a consequence of set membership.

### D4 — Enforced at load, because `append()` is not the door

There is **no production caller of `append()`** anywhere in `cli/` — all 46 records were written by uncommitted scripts. Bolting the API alone bolts an unused door.

So `validate_stored_record` checks, for `schema_version >= 4`, that `datasets` is present, that it satisfies D2a's shape, and that `dataset_hash == compute_hash(datasets)` — three distinct corruption errors. One hash and one cheap walk per record on load: the property becomes a fact about the file rather than about a function signature.

**Every record past trial 46 must declare `schema_version >= 4`** — a hard floor in `_assert_cross_record`, constant `_LEGACY_UNPROVENANCED_MAX_TRIAL_ID = 46`. The load check above binds only `>= 4`, so on its own nothing makes a *new* record declare 4: the next direct writer templates off an existing line, all 46 say 2 or 3, and `{"schema_version": 3, "dataset_hash": "ba47e37e"}` reproduces the original failure verbatim and loads clean forever. A weaker "`schema_version` never decreases" does **not** close that — an unbroken run of 3s satisfies it, and the 46 committed records measure `[2]×32` then `[3]×14`, already non-decreasing. The floor binds from the very next record instead of from a first schema-4 append nothing compels.

46 is the highest `trial_id` committed today, and the exemption is by **id** rather than by version because that is what cannot grow: those records predate the block and are unrepairable (append-only), while 47 is the next thing anyone can write. Same freeze idiom as `tests/test_trial_registry_provenance.py`'s `LEGACY_UNCOMMITTED`, in the loader rather than a test because the writers it binds do not call `append()`. `append()` itself cannot trip it — it writes `SCHEMA_VERSION`.

**`append()` re-validates the finished record with `validate_stored_record` before writing.** Schema 4 is the first path where a *successful* capture can produce a record the loader rejects: `set_digest` and `extent.rows` come straight from a manifest, and the holdout's is produced by an external freeze this repo does not write ([[T0132]]) — an uppercase `manifest_sha256`, or a `rows` emitted as `2842.0`, passes capture and fails load. The file is append-only and hash-chained and `_read_healing` self-heals only a torn *trailing* line, so one such write makes the registry permanently unloadable with no legal repair. Validating before the write turns an irreversible corruption into a refused append.

**Named limitation, not a claim:** `cli/engine/soak.py` parses the registry with raw `json.loads` and never calls `validate_stored_record`, so the engine's soak path does not inherit this check.

### D5 — Byte verification is NOT rebuilt here; what exists is partial, and the gap is registered

The block attests what the **manifest says**, not what the bytes are. Rather than add a re-derivation layer — where the first attempt's complexity and most of its residual defects lived — this spec states exactly what the two committed mechanisms cover, measured 2026-08-08:

- `cli/data/sync.py::_verify_new_files` re-hashes newly transferred `.parquet` files against the per-series `sha256` values a manifest exposes. Bounds: only rsync-itemized **new** files, only parquet, only when `verify=True`, and by hash **membership** rather than path binding (two swapped series pass). It is **inert for `ohlc-holdout-*`** — `_manifest_sha256s` deliberately collects only per-artifact `sha256` keys, the holdout manifest has none, so `vouched` is empty and the code warns and continues. **The holdout has no byte coverage at all**; registered as [[T0133]].
- `cli/engine/soak.py::instrument_self_check` rebuilds the strategy and reproduces **two integers** of record 44 — `governor_engaged_bars` and `cap_breach_bars` — over `PAIR_KEYS × (1440, 240)` on `ohlc-full`, and returns `(None, "canonical absent")` on a host without the canonical. It is not stronger than a digest: a digest detects any byte change, two bar counters detect only changes that move those counters. Nothing there touches `ohlc-15m` or the holdout.

Not rebuilding still follows for `ohlc-full` and `ohlc-15m`, whose manifests carry per-series hashes and whose deployable is separately extent-pinned by tests. It does **not** follow for the holdout — that is [[T0133]]'s job, not this spec's, because the fix is in the freeze producer or a sidecar, not in the registry.

**The honest claim is therefore bounded**: a schema-4 record proves *which declared slice of which dataset capture* a trial names, and that its digest derives from that block. It does not prove the bytes were unchanged, and it does not prove the run read only what it declared. The latter is unclosable from inside the registry and belongs to [[T0065]]'s committed research-run command, already registered.

### D6 — Historical hashes get a committed legacy table

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 hash, carrying `referent`, `confidence` (`reproduced` | `inferred` | `unrecoverable`), and evidence.

The three confidence levels are the whole point — [[T0065]] warns explicitly that this must not be "written up as though the hash had been reproduced", and its measured table is the source:

- `cccb8d17` — `reproduced`. It re-derives as `sha256(hex_4h + ":" + hex_15m)`, and its entry is **executed** by a test rather than asserted. Its 15m operand is `data/ohlc-15m`'s on-disk `basket_sha256`; its 4h operand is `81dc9b44`, which the row below classes unrecoverable — T0065's words, "fully reproducible but only half traceable to bytes". `reproduced` names the *recipe*, not the data, and the referent must say so.
- `ba47e37e` — `inferred`. Identified by extent plus the v0 exclusion, over the **daily** series only; that is the whole scope of T0065's argument.
- `81dc9b44` — `unrecoverable`, `referent: null`. T0065 classes it an unresolved 4h primitive: it resisted ~226,000 candidates and nothing in the repo establishes a referent for it. Writing one down would be the exact failure T0065 names.
- `45275ebe` — `inferred`. It composes the two above, so it inherits `81dc9b44`'s unrecoverability and cannot be recomputed; what pins its data is `tests/test_record44_legs.py`'s `UNION_BARS = {1440: 4582, 240: 27338}` extent assertion. The runbook's stated composition does **not** reproduce, and the entry says so.

**The qualification lives in the value, not only in a sibling field** — an `inferred` row's `referent` reads `"data/ohlc-full daily (INFERRED from extent + exclusion — never recomputed)"`, so a careless grep cannot return a bare path that reads as verified fact. An `unrecoverable` row carries no referent at all, for the same reason. **`reproduced` gets the treatment too, and needs it most**: it is the row a careless reader trusts unconditionally, and it is half unrecoverable, so its referent names its unrecoverable operand inline. All four rows carry their own epistemics in the value; none is qualified only by `confidence`.

Prose was rejected: [[T0065]] is archived on resolution, and archived topics are never re-read.

## Why this is sustainable, and where it still decays

**Sustainable because the mechanism is not documentation, and because the surface is small.** The derivation is the store's own hashing; enforcement is at load; the allowlist is two adapters over shapes this repo either controls or has frozen. The first attempt's decay came from generality — this version has very little to decay.

- **A new dataset backs a trial** → refused until an adapter exists. Deliberate; the refusal *is* the design.
- **A supported writer changes its manifest shape** → its adapter fails loudly at capture, and a test over every allowlisted manifest on disk goes red **on a data-bearing host**. The data root is gitignored, so on a bare checkout that test must **skip**, not pass: a loop over an empty glob asserting nothing is a green that means nothing.
- **Dataset rename** → the block's dataset key stops matching the allowlist, so capture refuses; `set_digest` and `extent` in already-written records still identify the data. A re-freeze **sibling** is not a rename — the allowlist keys prefix-match (D1).
- **`extent` is coarser than content** → deliberate; D5 states exactly how far the existing coverage reaches, and [[T0133]] carries the hole it leaves.
- **This repairs nothing retroactively** — 44 records stay unverifiable; D6 documents them.

## Verification

- All 46 existing records still load, asserted against the **real** `docs/reference/trial-registry.jsonl`, not a fixture, and through the real loader rather than a set-arithmetic model of it.
- A schema-4 record round-trips write → read → re-derive.
- Two trials declaring different slices of one dataset get different `dataset_hash` — on **each** axis, pairs and intervals; two declaring the same slice get the same one whatever the order, and whether spelled out or abbreviated to `select: {}` (D2's resolution).
- A schema-4 line whose `datasets` is missing, empty, or not the D2a shape is refused **at load**, not only at capture — including the degenerate blocks: an empty `select`, an empty axis list, a zero `extent`, a boolean where an int belongs.
- A schema-3 record 47 appended to the real 46 is refused; the same record at schema 4 loads, so the floor is what rejects it.
- A manifest value the loader would reject — an uppercase set digest; equally a float `rows` — is refused **at append**, with nothing written.
- Every allowlisted dataset present on disk captures without error, and all three are frozen, so all three get a measured whole-set extent pin (measured 2026-08-08): `ohlc-full` 36 series / 1,052,322 rows / `2013-09-10T00:00:00+00:00` → `2026-03-31T23:00:00+00:00`; `ohlc-15m` 12 / 3,122,044 / `2013-09-10T23:45:00+00:00` → `2026-03-31T23:45:00+00:00`; `ohlc-holdout-2026-07-10` 10 / 30,032 / `2013-09-10 00:00:00+00:00` → `2026-07-09 00:00:00+00:00`. Without a pin the on-disk test asserts only that some number is positive, which any non-empty manifest satisfies. The test enumerates from disk rather than a hardcoded tuple, and skips rather than passes when the glob is empty.
- An unlisted dataset is refused, and the message names the adapter remedy.
- `cccb8d17`'s legacy entry reproduces when executed.
- Each guard proven by a constructed failure through `infra/scripts/mutate-probe.sh`, never asserted — including that the on-disk test itself can go red.

## Out of scope

- **Rewriting historical records** — impossible (append-only, hash-chained); D6 is the alternative.
- **Manifest normalisation across all writers** — [[T0132]].
- **Byte-level re-verification** — D5 states what the two committed mechanisms actually cover; the holdout's gap is [[T0133]].
- **Proving a run read only what it declared** — [[T0065]]'s research-run command.
- **Adapters for `derivatives-funding`, `derivatives-oi`, `ohlc-reach`** — deferred until one backs a trial (D1).
