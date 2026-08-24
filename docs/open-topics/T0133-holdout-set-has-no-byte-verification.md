---
status: partial
ripe_when: "the fail-closed step is unblocked NOW — no set under the hot dir vouches nothing any more, so it would refuse nothing (re-check by running `_vouched_for_set` over every set there); the path-binding step waits on [[T0132]]'s manifest contract"
---

# The holdout set is the one canonical dataset with no byte verification

## Context — what

`cli/data/sync.py::_verify_new_files` re-hashes each newly transferred parquet and refuses content the manifest does not attest. It works off `_manifest_sha256s`, which collects **per-artifact `sha256` keys only** — its docstring says the manifest-level `manifest_sha256` is deliberately not collected, because it is not a per-parquet hash.

`data/ohlc-holdout-2026-07-10/manifest.json` carries no per-series `sha256` at all (measured 2026-08-08: each asset entry has exactly `rows`, `first_ts`, `last_ts`, `overlap_bars_verified`, `appended`). So `vouched` is empty, the code logs a warning and `continue`s, and **not one holdout byte is checked**.

## Why this matters

The sync-side verification that covers `ohlc-full` and `ohlc-15m` is inert here — on the one dataset an out-of-sample validation depends on.

**Partial mitigation shipped 2026-08-09 (spec `00086`), and its limit is the point.** Every schema-4 record stores the per-file **byte** `sha256` of what the run read, and a conformance pass re-hashes those citations on the canonical data host — so an edit to a parquet that a registered evaluation READ is caught. That is record-scoped and after-the-fact: it says nothing about whether the freeze was faithful when it was cut, it covers no file that no record cites, and it arrives only once a holdout trial is actually registered. Freeze-side hashes and a fail-closed sync — the coverage that would make an edit detectable regardless of who read what — remain this topic's whole subject.

Three further bounds on `_verify_new_files`, worth stating so its coverage is not overclaimed elsewhere: it sees only files rsync itemizes as **new**, only `.parquet`, only when `verify=True`, and it matches by hash **membership** in the manifest's hash set rather than by path binding — so two swapped series pass.

## Findings so far

- Measured 2026-08-08: `ohlc-full` and `ohlc-15m` expose per-series `sha256` (36 and 12 leaves); `derivatives-funding` exposes them per symbol; `ohlc-holdout-2026-07-10` exposes none.
- The holdout manifest is produced by an **external freeze process this repo does not write** ([[T0132]]), so the fix is not a one-line writer change here.
- The set is frozen and small — 10 series, 30,032 rows, `2013-09-10 00:00:00+00:00` → `2026-07-09 00:00:00+00:00` — so a repo-side hash sidecar is cheap if the freeze cannot be changed.

- **Why the re-freeze is the cheap moment.** That is when the freeze process can emit per-series `sha256` for free, rather than paying a separate pass later. It is also ripe if [[T0064]]'s out-of-sample work moves from accepted-once to repeated evaluation, since a re-run against silently altered holdout bytes is exactly the failure this guards against.

## Done so far

**The gap the title names is closed, and the fix is bigger than this topic expected — because `_verify_new_files` was never the important consumer.** `_manifest_sha256s` has a second caller: `ObservedReader.read_series` cross-checks `dataset_hash(full)` against the vouched set on EVERY read, but guards with `if vouched and ...`, so an empty set made it a no-op. `vouched_status()` reported the holdout verbatim as `inert (0 vouched hashes)`; it now reports `checked (10 vouched hashes)`. That is a data-at-rest guard on the local copy, which is what this topic actually needed — and it fires on reads, not only on transfers.

**That distinction matters, because the sync-side fix alone would have bought almost nothing.** Measured: `fetch_hot` runs rsync `--ignore-existing`, so on a node that already holds the holdout, a tampered local parquet is never itemized as new and never reaches `_verify_new_files` at all — measured across same-length, different-length, truncated-to-zero and dangling-symlink tamper, every one silent. The sync check can only ever cover a first ingest.

**The hashes are committed here, not emitted by the freeze.** This topic preferred option (a), the freeze process emitting `sha256`. That was never actionable from this repo: `git log --all` finds no `holdout_pull.py` — the producer has never lived here. `docs/reference/vouched-dataset-hashes.jsonl` carries one line per series in its own uniform shape, so reading it needs none of the per-set manifest knowledge the varied manifest shapes would demand — it does not walk into [[T0132]]'s zoo.

**The title is a misnomer, and it is left standing only because the file name is its slug.** Nothing in this repo does byte verification of any dataset. All five manifest writers vouch `dataset_hash` — sha256 of the frame's canonical CSV — and `observed.py` records that a byte-grade test "refuses every healthy read of ohlc-full/ohlc-15m". The sidecar matches that grade deliberately; a byte digest would be a second, incompatible one.

**What the attestation can and cannot claim.** Minting asserted each frame's rows and span against the freeze manifest first and refused to pin anything uncorroborated; all ten matched, 30,032 rows. The freeze-day ledger entry still matches the manifest's own `manifest_sha256`. None of that excludes a value-only edit made before minting that preserved row count and span — that is the residue, and it is the same edit the new hashes now catch going forward.

**`push_hot` ran no verifier at all, and now verifies before transmitting.** The channel never overwrites, so a node that accepts tampered bytes is never corrected by a later push — detection afterwards detects a permanent fact. A dry-run pass lists what would leave and refuses unattested parquet content.

**The old trigger could never have discharged this topic**, which is why it was taken now rather than waited on. A re-freeze of `data/ohlc-holdout-2026-07-10` cannot happen — the look budget is 1, remaining 0, and a fresh cut is a NEW directory. Both of the first two clauses were the same event, and it delivers hashes for a different set while this one keeps its gap forever.

## Suggested next steps

- **(autonomous, unblocked now)** Make the empty-`vouched` branch of `_verify_new_files` fail closed for datasets that are *supposed* to expose hashes, instead of warning and continuing — today an allowlisted set that silently stops emitting `sha256` degrades to no verification with only a log line.
- **(autonomous, independent)** Bind the check to paths: `_verify_new_files` currently asserts hash **membership**, so two swapped series inside one set pass. Per-set knowledge of the parquet layout is what the docstring says it avoids, so this is a deliberate trade to re-examine, not an oversight to patch blindly.
