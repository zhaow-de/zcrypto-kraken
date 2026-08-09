# Verifiable dataset provenance for the trial registry

Closes [[T0065]]'s execution-reproducibility round **whole, in one round**: the registry floor, byte-grade provenance, and the committed research command that is the registry's one real door — together, so nothing about this subject is left partial. Master-plan §8 requires a verdict to reference the data it was fitted on rather than "latest". Today that reference is an opaque caller-supplied `dataset_hash`; for **44 of 46** records it can no longer be resolved to anything.

## Context — the failure, and the two failed shapes before this one

The registry validates `dataset_hash` as "a non-empty str" and nothing more. Whatever a caller passed became permanent provenance; the computing drivers were gitignored scratchpad scripts, never committed (`git log --all --diff-filter=D` confirms none was committed and deleted), and `ba47e37e` (38 records) and `81dc9b44` (4) are unrecoverable against ~226,000 tested candidate recipes.

**Two prior designs failed under cold review — nine rounds total.** A generic manifest reader died in four rounds (10→6→6→5 blocking) on one recorded root cause: *the manifest ecosystem has no contract* — five writers, four `series` shapes, two digest spellings, a per-run nonce, a machine-local path, a holdout manifest with no hashes at all ([[T0132]]). An allowlist reshape ran five more rounds (13→8→6→4→5) and was stopped by judgement, not convergence; its bounded claims conceded the block attests *what a manifest declared*, its capture gate guarded `append()` — which has **no production caller** — and record 47's identity would have anchored on an externally-produced `manifest_sha256` that six candidate recipes fail to reproduce and that may move on a byte-identical re-pull.

**This design removes the act both failures attach to.** No manifest is parsed anywhere in the identity path. Identity is computed from the bytes a run actually reads, at the moment it reads them, by committed code — and the committed research command becomes the first production caller of `append()`, so the door being guarded is a door something uses.

## Decisions

### D1 — Identity is what the run read: the capturing loader

`cli/registry/observed.py` — `ObservedReader(data_root)` is the one sanctioned way research reads frozen datasets:

- `read_series(dataset, relpath, window=None) -> pl.DataFrame` — streams sha256 over the file's bytes as on disk, loads the frame through the existing parquet reader, applies the window **itself**, and accumulates per-dataset `files`/`rows`/`span` from what it *returns*. The loader owning the windowing means rows-used cannot drift from rows-recorded by construction, not by caller discipline.
- `block() -> dict` — the accumulated `datasets` block. Refuses an empty accumulation and refuses any dataset accumulated to zero rows: a block that says nothing is the failure being replaced, so it cannot be emitted.
- A file read twice yields one `files` entry, hashed once (memoised per path). A repeated read returning a different frame (window mismatch) is refused — one record, one read discipline.
- It imports nothing from manifests. Consequences, each the direct negation of a recorded killer: the four-shape `series` zoo, the stamp-format splits, and the axis-resolution machinery have nothing to attach to; a new dataset backing a trial needs **zero provenance code** — no allowlist entry, no adapter; the holdout's opaque external digest appears nowhere in record 47's identity, so a byte-identical re-pull cannot move it.

**Vouched-hash cross-check (bonus layer, not identity):** where a dataset's manifest vouches per-series hashes (`sync.py::_manifest_sha256s`'s existing shape-agnostic recursion), the loader compares its computed hashes by membership and **refuses on mismatch** — fitting on bytes the manifest disputes is exactly what should stop a run. An empty vouched set (the holdout) makes the check inert, and the runner prints that it is inert. This cannot weaken the identity, which is computed, never copied.

### D2 — The block records files, rows, span — observed, not declared

```json
"datasets": {
  "ohlc-holdout-2026-07-10": {
    "files": {"ADA/EUR/1440.parquet": "<64-hex sha256 of file bytes>", "…": "…"},
    "rows": 30032,
    "span": ["2013-09-10 00:00:00+00:00", "2026-07-09 00:00:00+00:00"]
  }
}
```

- `files`: non-empty dict, POSIX relpath under `data/<dataset>/` → 64-char lowercase hex. `canonical_json`'s key sorting orders it; no list-order digest split is possible.
- `rows`: `type(x) is int`, ≥ 1 — the rows the loader returned (post-window). `span`: `[first, last]` serialized from the loaded frames' own timestamps; stored and checked as raw strings — the loader emits one format, the checker never parses.
- A windowed fit moves `rows`/`span` honestly — the sample-window inexpressibility that was the allowlist design's admitted gap closes at the data level. The scored/decisive sub-window of an evaluation protocol is a property of the evaluation, not the data; it goes in `notes`, formatted by the runner.
- Line size: a record-44-shaped slice is ~20 files ≈ 2 KB of hashes — cleartext in the record on purpose, so the referent is recoverable from the record alone, with no side table.
- Sibling re-freezes never compare equal by digest — under §8's immutability rule that is the correct reading (a rewritten frozen set IS a different set); cross-set comparison is by extent and span, and a digest difference reads "re-examine", never "invalidated".

### D3 — `dataset_hash` is derived; there is no argument through which to supply it

`dataset_hash = compute_hash(datasets)` — the registry's own `compute_hash`/`canonical_json`, the same machinery that produces every `record_hash`, so the derivation cannot be lost without breaking record hashing itself. Mechanically: `dataset_hash` moves into the store-owned key set; `datasets` is version-scoped like `variant`. The three enumerated breakage paths from the branch's earlier review rounds are handled exactly as verified there (0/46 breakage): the hardcoded type-check tuple loses `dataset_hash`; `datasets` joins **neither** base key set; `_EXPECTED_STORED_KEYS` gains an explicit `4:` entry. `append()` drops its `dataset_hash` parameter, gains `datasets: dict`, and **re-validates the finished record with `validate_stored_record` before writing** — the file is append-only and hash-chained, so one bad line is permanent; validation before the write turns irreversible corruption into a refused append. The schema bump and the `append()` rework land in ONE commit.

### D4 — Enforced at load, floored at trial 46

For `schema_version >= 4`, `validate_stored_record` checks — placed before `validate_caller_fields`, raising corruption errors, with no disk access and no dataset-name knowledge: `datasets` is a non-empty dict; each value exactly `{files, rows, span}` per D2's clauses including the emptiness clauses (an empty `files`, a zero `rows` — the degenerate blocks that say nothing must not load); `dataset_hash == compute_hash(datasets)`.

**Every record past trial 46 must declare `schema_version >= 4`** — a hard floor in `_assert_cross_record`, by **id** because ids cannot grow retroactively: the 46 committed records predate the block and are unrepairable, while 47 is the next thing anyone can write. Without the floor, `{"schema_version": 3, "dataset_hash": "ba47e37e"}` reproduces the original failure verbatim and loads clean forever ("non-decreasing" is vacuous — the real file already measures `[2]×32 [3]×14`). A stored schema-2/3 record's `dataset_hash` keeps its non-empty-str check, re-homed when the key becomes store-owned.

The registry file is committed and `tests/test_registry_store.py::test_live_registry_file_loads_clean` loads it ungated on every CI run — so floor, shape, and derivation bind mechanically **at the exact PR that adds record 47**, on bare checkouts, under the suite that already exists.

### D5 — The committed research command is the door, and registration goes through it

`cli/research/command.py`, registered as `zcrypto research` with one subcommand:

```
uv run zcrypto research eval --subject <name> --dataset <dir> [--window A B] [--register]
```

- **Subjects are an enum of committed builders** — `cli/research/subjects.py`, initially `record44-crossfreq` (`build_crossfreq_system_fast`) and `record33-combined` (`build_combined_system`), each entry naming its builder, its required series, and its committed metrics function. Adding a subject is adding an enum entry and an import — the per-need growth discipline that made the allowlist reviewable, applied to the axis that actually needed it.
- The command resolves the repo `data/` root (module constant, `record44_legs.DATA_ROOT`-style — no caller-chosen root), instantiates `ObservedReader`, asks the subject for its required series, and **refuses a subject whose required series the dataset lacks, naming the missing files** (the crossfreq deployable on a daily-only holdout is a refusal, not a crash).
- It builds the subject, computes the subject's committed metrics, prints the report. Only with `--register` does it call `append()` — with the observed block, the metrics, the verdict, and a `run_ref` naming `cli/research/command.py` plus the protocol doc, satisfying the existing run_ref committed-path guard by construction.
- **The registration rule, total:** exploration (fits, sweeps, seeds) may stay scratchpad — exploration appends nothing. **Appending a record requires a committed subject**: a candidate reaches the registry only after its builder is committed code, which is the discipline record 44 already followed (`crossfreq_system.py` is the committed trial-44 driver) — this command makes it the paved, enforced-by-review path rather than an unwritten norm. A future look (e.g. [[T0064]]'s) adds its committed metrics function at its own round like any research adds committed code; the **door itself is complete now** and proven end-to-end by D7's controls against existing subjects.

### D6 — Historical hashes: the ruling, executed as a committed table

**The ruling this spec carries (owner decision, ratified with this spec's approval):** `ba47e37e` and `81dc9b44` are accepted as **unverifiable** — no further reconstruction effort — and every citation must say so.

`docs/reference/legacy-dataset-pins.jsonl`, one line per distinct pre-schema-4 hash: `referent`, `confidence` (`reproduced` | `inferred` | `unrecoverable`), `trial_ids`, evidence. The epistemics live **in the referent value**, not only in a sibling field, so a careless grep can never return a bare path that reads as verified fact:

- `cccb8d17` — `reproduced`: re-derives as `sha256(hex_4h + ":" + hex_15m)`, **executed by a test** rather than asserted; its referent names inline that its 4h operand is the unrecoverable `81dc9b44` — the row a careless reader trusts most needs the qualifier most.
- `ba47e37e` — `inferred`: identified by extent + the v0 exclusion, daily series only; referent reads `"data/ohlc-full daily (INFERRED from extent + exclusion — never recomputed)"`; `trial_ids` exposes the scope mismatch (36 A1 + trials 33/35 which also read 4h).
- `81dc9b44` — `unrecoverable`, `referent: null`.
- `45275ebe` — `inferred`: composes the two above, inherits unrecoverability; pinned by `tests/test_record44_legs.py`'s `UNION_BARS` extent assertion; the runbook's stated composition does not reproduce, and the entry says so.

### D7 — Verification is constructed, and it runs where it can actually run

- **Everywhere (CI, bare checkout):** the full pipeline over synthetic parquets in tmp — loader → block → `append()` → load → re-derive — plus the real-file load (D4) binding floor/shape/derivation on the committed registry. This is coverage the manifest-reading designs could not have: no real manifest is needed to exercise the whole identity path.
- **Workstation (data-bearing):** (a) the runner's **control against history** — the loading path over `data/ohlc-full`'s record-44 slice must reproduce the registered figures the suite already pins (`test_crossfreq_system.py`, `instrument_self_check`) and a frozen block extent; (b) the **disk conformance pass** — every schema-4 record's `files` re-hashed against disk, memoised per `(path, size, mtime)`, verdicts `rederived` / `absent-here` (dataset dir missing on this host) / **finding** (dir present, hash mismatch or named file missing). Data-gated tests skip, never pass vacuously.
- **Probes:** every guard proven by a constructed failure through `infra/scripts/mutate-probe.sh` — the floor, each shape clause, the derivation equality, the loader's hash (a flipped byte moves the block), the zero-row refusal, the missing-series refusal, `--register` gating — each with a control that fails first.

## What this does NOT do — bounded claims

1. **A writer reimplementing the hash chain by hand can still fabricate a block.** The floor guarantees any such record is schema-4, shape-valid, derivation-consistent — nothing more. The record lands in a reviewed PR diff against a committed file, the conformance pass re-hashes it on the workstation, and the paved road is *less* work than hand-assembly — but no mechanism can close a door that is "importing the code and lying to it". Recorded here as the reason, not parked as a topic.
2. **Byte identity is file-grain.** A re-encoded parquet with identical logical content moves every hash (correct under §8's immutability rule); sub-file addressing is rejected as a canonicalization swamp.
3. **Bypass reads are invisible.** The block covers what went through `ObservedReader`; a run that also opens files directly records nothing about them. "Provenance at the point of consumption" is honest only for loads through the loader — this spec never writes the phrase without the qualifier. The runner is the committed path; review is the fence.
4. **Whole-file hashes even for windowed use** — a trial reading 100 bars of a 3,003-row file vouches the whole file's bytes; `rows`/`span` carry the slice.
5. **Nothing retroactive.** The 44 unresolved hashes stay unresolved; D6 documents, never repairs; all 46 records load untouched.
6. **Freeze-side verification stays [[T0133]]'s scope** — record 47 pins what it read at eval time; nothing here re-verifies the freeze on later syncs. The record-scoped hashes reduce T0133's sting (a later edit to a file record 47 read is caught by the conformance pass) without absorbing its scope.
7. **Environment is not captured** — data identity only; numeric reproduction of results is concordance territory.
8. **The registry cannot verify protocol compliance** (window choice, budget state, §12 ratification) — ledger and runbook territory.

## Why this is sustainable

The identity path touches nothing that varies: file bytes, row counts, timestamps the loader itself returned. A new dataset, a re-freeze sibling, a holdout re-pull, a new trial family — zero provenance code change. The manifest zoo can stay uncontracted forever ([[T0132]]) without costing this design anything; the cross-check consumes vouched hashes when present and says so when absent. The one growth point is the subject enum, which grows exactly when research produces a committed builder — which is what research must produce anyway for its results to be real.

**What happens to the branch's Task 1** (`cli/registry/provenance.py`, two manifest adapters, unmerged): **discarded** — its jobs (slice-vs-manifest resolution, digest-key normalisation, manifest-leaf extent) have no consumer here; the one fragment with residual value (vouched-hash collection) already exists in `sync.py`. The write-off is 158 + 168 unmerged lines and the allowlist-specific share of five review rounds. What transfers intact: the D3 key-set minefield map (verified 0/46), the D2a load-check philosophy, the D4 floor rationale, D6 whole, the 14-site test-migration map, the probe designs, and Task 1's frozen full-set figures — reused verbatim as the loader's workstation expectations (36 / 1,052,322 rows; 12 / 3,122,044; 10 / 30,032, measured 2026-08-08).

## Out of scope — every line maps to an existing topic or an explicit drop

- **Manifest normalisation across writers** — [[T0132]]; its body is updated in this PR: provenance no longer waits on the contract.
- **Freeze-side byte verification for the holdout** — [[T0133]]; its body is updated in this PR: record-scoped hashes exist from record 47 on.
- **The holdout look's statistical protocol and its ratification** — [[T0064]] / §12; the command's subject enum receives that look's committed metrics function at its own round.
- **REACH (Q2 OHLCVT ingest, live-trades→bars)** — [[T0065]]'s separate round, gated on an external publication, untouched here.
- **Explicit drops, with reasons recorded above:** mechanically closing the hand-rolled-writer door (bounded claim 1); sub-file content addressing (bounded claim 2); environment capture (bounded claim 7).

**T0065 closure effect:** with this spec implemented, the execution-reproducibility round is **done in full** — recipe (D1–D4), command (D5), ruling (D6). T0065's remaining open work is the REACH round alone.
