---
status: open
ripe_when: "`data/ohlc-holdout-*` is re-frozen, a second holdout is cut, or [[T0064]]'s out-of-sample work moves to repeated evaluation"
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

## Suggested next steps

- **(design, when triggered)** Decide where the holdout's per-series hashes come from: (a) the freeze process emits `sha256` per asset, matching the backfill writers' spelling, or (b) this repo mints a committed sidecar (`docs/reference/` or a manifest-adjacent file) at first ingest and `_verify_new_files` reads it. (a) is correct; (b) is available now and does not need the external producer.
- **(autonomous, after that)** Make the empty-`vouched` branch of `_verify_new_files` fail closed for datasets that are *supposed* to expose hashes, instead of warning and continuing — today an allowlisted set that silently stops emitting `sha256` degrades to no verification with only a log line.
- **(autonomous, independent)** Bind the check to paths: `_verify_new_files` currently asserts hash **membership**, so two swapped series inside one set pass. Per-set knowledge of the parquet layout is what the docstring says it avoids, so this is a deliberate trade to re-examine, not an oversight to patch blindly.
