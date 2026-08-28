---
status: open
---

# Role A NAS pull re-hashes the whole archive every cycle

## Context — what

The Role A NAS pull (`zcrypto archive pull`, spec/plan `00048`) verifies pulled segments by `verify_tree(dest)`, which `rglob`s the **entire** destination archive and recomputes each segment's sha256 against its `.sha256` sidecar **every** cycle — not just the segments rsync transferred. The NAS archive is never pruned (only the VPS prunes its ~7-day window), so it grows unbounded.

Five channels run verified pulls in that loop, not one: `CAPTURE_SOURCE`, `CAPTURE_RED_SOURCE`, `LIQUIDATIONS_SOURCE`, `PANEL_SOURCE` and `RECONCILED_SOURCE`. `JOURNAL_SOURCE` is `--no-verify` (Role B verifies via replay) and `HOT_SOURCE` is a raw rsync with no verification at all.

## Why this matters

The per-cycle hash cost is O(total archive), and the waste is re-verifying already-verified historical segments every hour. Measured 2026-08-28 over one cycle: **75,806 parquet files re-hashed** — 27,931 + 24,901 + 8,624 + 13,908 + 442 across the five verified channels.

**The consequence is drift, not a stall.** The in-container loop is `work; sleep "${ARCHIVE_PULL_INTERVAL:-3600}"` — not a fixed schedule — so cycles cannot overlap and nothing piles up. The period stretches to `work + 3600`, and the cost surfaces as growing pull lag. There is no cliff at 3600 s. This matters twice over: the degradation is smooth, so nobody would notice it happening, and no threshold at the pull interval has any special meaning.

The mode is nonetheless real on this host — `infra/nas/pull-entrypoint.sh` records that the Atom tax on every step sharing this clock had stretched the "hourly" loop to ~103 minutes before spec `00054` moved reconcile to the ops node.

Found by the iter-093 final whole-branch review of Role A (finding #2). Part of the [[T0003]] → three-tier pipeline.

## Findings so far

- The verify is a genuine integrity gate for **freshly-pulled** segments (rsync exit 0 = complete transfer; sha256-vs-sidecar catches truncation/corruption). Only the re-verification of unchanged history is waste.
- **Nothing measures the cost**, which is why this topic could not become ripe on its own terms. The NAS pull's entire observability is `NAS · archive-pull stalled (dead-man)` (fires on silence), `NAS · archive-pull ERROR logs`, and the `lag_s` field — which is data *freshness*, not sweep cost. The original `ripe_when` ("one hourly `verify_tree` sweep approaches the pull interval") named a quantity no data source delivers, so it was never satisfiable; it has been dropped rather than restated, and spec `00102` publishes the metric that replaces it.
- **Every earlier size estimate on this topic rested on a wrong fill rate and a wrong channel count.** The original figures assumed T0003's ~10 GB/day; a 2026-07-17 correction ([[T0032]] + spec `00050`) re-derived them at ~0.96 GB/day for the two capture mirrors, giving a ~250 GB onset ~8–9 months out and a ~600 GB cliff ~1.7 years out. Both passes counted the capture mirrors only, and five channels are verified — so even the corrected horizon is optimistic by an unmeasured factor. **Treat no horizon on this topic as load-bearing until the metric reports one.**
- `verify_tree`'s traversal also derives `newest_ts` (which feeds `pull_lag_seconds`, the entrypoint's dead-man signal) and the `verified` list (which drives `prune_stale_parts`). Narrowing the **walk** rather than the **hash** would blank the freshness figure on a cycle where nothing arrived — the condition it exists to detect. Whatever narrows the cost must leave the traversal whole.
- Spec `00078`'s checkpoint store solves "skip an unchanged hour" in this same package, using the sidecar digest as a cheap staleness probe. It was considered and declined here: that probe is itself O(total files) per cycle, so it shrinks the constant while keeping the growth term. rsync's own itemization costs no probe at all.

## Suggested next steps

- **(autonomous, on a branch) Implement spec `00102`** — the design that closes this topic. Component A publishes `zcrypto_archive_pull_{verify_seconds,files_hashed,files_walked}` per channel and admits the family to `infra/nas/config.alloy`'s keep regex; component B narrows the hash to rsync's itemized transfers plus a stateless 1/24 rotating slice, leaving the traversal whole. A converges and runs first, because its baseline is the only evidence B worked.
- **Record the measured horizon once the metric has reported**, and retire the estimates above rather than carrying them forward.
