---
status: resolved
---

# gate-export cache: the replay fingerprint covers the code but not the execution environment

## Context — what

`zcrypto engine gate-export --cache` (spec `00060`) skips re-replaying already-verified journal cycles. Its safety rests on a **replay fingerprint** that invalidates the whole cache whenever anything which could change a replay's verdict changes. That fingerprint covers the ten modules on the replay call graph, the effective `CrossfreqSystemConfig`, and the replay path (`fast`/`verified`).

It does **not** cover the **execution environment** — notably the installed `numpy` and Python versions. A numeric-behaviour change after a `uv.lock` bump (e.g. in `sliding_window_view` or the vol-targeting arithmetic) would therefore be served from a stale cache: the journal is unchanged, the source bytes are unchanged, so every cached entry still "matches" while a fresh replay would now produce different numbers.

## Why this matters

This is the same class of failure the fingerprint exists to prevent — a **silent stale PASS** on gate evidence, the artifact that decides whether the strategy may trade real money. It is narrower than the code-coverage holes closed in `00060`'s fix wave, because it only bites when the numeric drift **exceeds `compare_targets`' 1e-6 tolerance** — a budget the design already accepts as cross-environment float drift. But "narrow" is not "absent", and the failure is silent by construction.

## Findings so far

- Surfaced by the spec-`00060` Task-1 review (2026-07-20), which traced `replay_cycle`'s call graph, closed two live code gaps (`cli/risk/governor.py`, `cli/engine/journal.py`) and then judged the residual: *"the fingerprint now covers every module that can change a fast-route replay verdict; the residual hole is the execution environment, not the code."*
- Two lesser residuals from the same review, both judged **not** silent-stale-PASS vectors and deliberately not fixed:
  - the parquet decode path (`_snapshot_reader`/`read_parquet`) is unhashed — but a decode change trips the snapshot content-hash check and fails **loudly** as `validation_failed`, rather than passing silently;
  - the `errors.py` modules defining the caught exception hierarchy are unhashed (very low risk).
- The cache is **opt-in** (`--cache`), and as of this writing no deployment passes it — so nothing is exposed until the attended enablement (tracked in [[T0069]]).

## Suggested next steps

- **(Autonomous, one line)** Fold the environment into `replay_fingerprint`: `importlib.metadata.version("numpy")` plus `sys.version_info[:2]` (and `polars` if the decode path is ever hashed). Consistent with spec `00060` D3's stated rationale that over-invalidation is safe and under-invalidation silently corrupts evidence — the cost of a version bump is exactly one full rebuild.
- **(Autonomous)** Add a test that a changed environment string moves the fingerprint, mirroring the existing byte-mutation tests for the ten covered modules.
- **(Judgement, cheap)** Decide whether to also hash the parquet decode path. The review's argument for leaving it is that a decode change fails loudly rather than silently — record the decision either way so it does not get silently revisited.

## Resolution — 2026-07-20

`replay_fingerprint` now digests the execution environment alongside the ten replay modules, the effective config and the replay path: the **full** installed `numpy` version string, and Python **major.minor** (`sys.version_info[:2]`). A `PackageNotFoundError` degrades to a sentinel rather than propagating — it is deliberately caught *inside* the function, because it is not an `OSError` and the caller's degrade-to-no-cache net only catches `OSError`.

**Granularity is asymmetric on purpose.** numpy is tracked at full version granularity (its changelogs do carry numeric-correctness fixes in patch releases); Python is tracked at major.minor, because patch releases are bugfix-only and float arithmetic is IEEE-754-via-C, orthogonal to the patch number — and this repo's own `.python-version` pins `"3.14"`, with no patch component to invalidate against. Verified empirically: a patch bump leaves the digest unchanged, a minor bump moves it.

**The polars question is settled, and more tightly than this topic originally argued.** The concern was that a decode-behaviour change could alter a replay silently. It cannot: `journal.snapshot_content_hash` hashes the **decoded values** (int64 epoch-seconds and IEEE-754 float64 via `struct.pack`), not the raw file bytes, and `replay_cycle` raises `HashMismatchError` on any mismatch with the journaled `entry.content_hash`. So a decode change that altered even one bit flips that hash and fails loudly as `validation_failed` before the value reaches the builder. polars is deliberately **not** fingerprinted, and the `errors.py` residual is likewise judged non-silent.
