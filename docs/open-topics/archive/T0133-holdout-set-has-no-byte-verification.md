---
status: resolved
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

**The sync check fails closed.** It used to warn and `continue` when a set vouched nothing, which is how the holdout went unverified: a log line on an otherwise healthy fetch is not read. A set that ships parquet and is attested by neither its manifest nor the sidecar is now refused, with `--no-verify` as the explicit escape. Measured before landing it, across the live hub: all six parquet-bearing sets vouch a hash per parquet (`derivatives-funding` 10/10, `derivatives-oi` 10/10, `ohlc-15m` 12/12, `ohlc-full` 36/36, `ohlc-reach` 30/30, holdout 10/10), so it refuses nothing that works today — the value is that a writer which silently stops emitting hashes now stops the fetch instead of degrading it.

**The check is path-BOUND wherever a committed attestation names the path**, which the sidecar does by carrying `relpath` per line. That is strictly stronger than membership and catches the one case membership provably cannot: swap two series inside a set and the multiset of hashes is unchanged, so every membership test passes on both halves. A test constructs exactly that swap, asserts the hash set is identical, and then sees the read refused.

**Sets attested only by their own manifest deliberately stay on membership**, and that is a recorded trade rather than an oversight. Deriving a path per hash needs per-set knowledge of each set's layout, and the manifests speak four incompatible dialects — measured on the live hub, `ohlc-reach`'s `series` is a *list*, and `derivatives-funding`/`derivatives-oi` share one shape while laying files out under different names, so shape alone does not even determine the path. Building a fifth hard-coded reader here is precisely what [[T0132]] exists to stop. The residual — a swap inside a manifest-attested set is invisible at both consumers — is registered there as a named waiting consumer, so the contract landing has something concrete to discharge.

## Resolution

All three sub-items are disposed of: the holdout's hashes exist and are committed, the empty-vouched branch fails closed, and path binding is delivered where it can be had without a manifest contract and consciously declined where it cannot. The only thing this topic leaves behind is registered on [[T0132]], which owns the manifest contract that would let the last case be done properly.

## Superseded next steps

Both are discharged above; kept only so the record shows what was asked and how it was answered.

- **Fail closed on an empty `vouched`** — DONE. It refuses now, with `--no-verify` as the explicit escape, and it was measured to refuse nothing that works.
- **Bind the check to paths instead of hash membership** — DONE where a committed attestation names the path (the sidecar carries `relpath`), and CONSCIOUSLY DECLINED for sets attested only by their own manifest, because that needs the per-set layout knowledge [[T0132]] exists to remove. The residual is registered there.
