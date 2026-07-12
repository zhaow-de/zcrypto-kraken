---
status: open
ripe_when: the NAS capture archive grows large enough that one hourly `verify_tree` sweep approaches the pull interval (est. ~1–2 months in, ~250–600 GB of segments), or an attended optimization window before then
---

# Role A NAS pull re-hashes the whole archive every cycle

## Context — what

The three-tier Role A pull (`zcrypto archive pull`, spec/plan `00048`) verifies pulled capture segments by `verify_tree(dest)`, which does `rglob("*.parquet")` over the **entire** destination archive and recomputes each segment's sha256 against its `.sha256` sidecar **every** pull cycle — not just the segments rsync actually transferred that cycle. The archive on the NAS is never pruned (only the VPS prunes its ~7-day window), so it grows unbounded.

## Why this matters

The capture verify sweep is therefore **O(total archive size) per hourly cycle**. Back-of-envelope on RAID-5 spinning disk (~150 MB/s): ~70 GB (1 week) → ~8 min; ~300 GB (~1 month) → ~33 min; ~600 GB (~2 months) → ~66 min > the 3600 s interval, at which point a single sweep no longer fits in the pull period and the in-container loop stalls (each cycle runs long, pull-lag climbs, the health signal degrades). Found by the iter-093 final whole-branch review of Role A (finding #2). Not deploy-blocking (the archive starts near-empty and grows), but it will bite within ~2 months if unaddressed. Part of the [[T0003]] → three-tier pipeline.

## Findings so far

- The verify is a genuine integrity gate for **freshly-pulled** capture segments (rsync exit 0 = complete transfer; sha256-vs-sidecar catches truncation/corruption). The waste is re-verifying already-verified historical segments every hour.
- The journal channel is unaffected — it now pulls `--no-verify` (archive-only; Role B verifies via replay).

## Suggested next steps

- **(autonomous, on a branch) Verify only what rsync transferred this cycle.** Have `_run_rsync` capture rsync's itemized transfer list (`--out-format='%i %n'` / `-i`), parse the transferred `*.parquet` paths, and verify only those (a `verify_paths(paths, *, now)` alongside `verify_tree`). This makes the per-cycle cost O(new segments), independent of archive size.
- **Optionally** keep a low-frequency (e.g. weekly) full-tree re-verify to catch silent bit-rot, decoupled from the hourly incremental pull.
- Add a test that a pull with an unchanged archive + one new transferred segment verifies only the new one.
