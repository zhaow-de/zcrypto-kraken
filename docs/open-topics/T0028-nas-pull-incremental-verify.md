---
status: partial
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

## Done so far

**Spec `00102` is implemented; nothing has been deployed, and nothing on this topic has been measured on the NAS.** Every `feat`/`fix` commit of the spec-`00102` branch lands the code and its operating surfaces (closeout: `docs/iterations-history-phase1.md`, iter-152):

- **The cost is measurable.** `zcrypto archive pull` gains `--textfile` and `--channel` and publishes `zcrypto_archive_pull_verify_seconds`, `zcrypto_archive_pull_files_hashed` and `zcrypto_archive_pull_files_walked` labelled by channel — one file per channel, because the five verified NAS pulls share one textfile directory. `infra/nas/config.alloy`'s keep regex admits the family **and** `node_textfile_mtime_seconds` (the reader that distinguishes a stale channel's file from a fresh one); `tests/test_infra_alloy_series.py`'s `NAS_REQUIRED` pins both, and two panels on `infra/grafana/data-integrity-dashboard.json` chart verify-seconds per channel and hashed-against-walked. The `pull complete` line gains `verify_s=`/`hashed=` as the record of last resort and keeps `failed=%d` verbatim, which the dead-man rule matches.
- **The hash is narrowable, and the walk is never narrowed.** `_run_rsync` now returns an `RsyncOutcome` naming the `*.parquet` files rsync itemized as received; `verify_tree` takes `hash_only=` and `rotation_slice=` and hashes a final iff rsync transferred it this cycle or its `slice_of` name-hash equals the cycle's rotation index. Every final is still walked, so `checked` and `newest_ts` — and the pull-lag figure the entrypoint reads as its dead-man signal — keep their meaning on a cycle that transferred nothing (spec `00102` D1, the invariant this topic's fourth finding asked for). A narrowed scope with no slice is refused rather than silently defaulted.
- **The slice is keyed on the loop's own cycle counter, never the clock** — `infra/nas/pull-entrypoint.sh` passes `--slice $((cycle % 24))`. The loop's real period is `interval + work` and drifts, so a clock-keyed slice starves a fixed subset of slices forever whenever the drifted period divides 24 h; the counter is in-memory, so the every-24-cycles guarantee holds across an uninterrupted run.
- **The scope is a deployed setting, not a build.** `--hash-scope full|incremental` defaults to `full`, so every non-NAS caller behaves exactly as before; the NAS value is `nas_archive_pull_hash_scope` in `infra/ansible/host_vars/nas/vars.yml`, rendered into `ARCHIVE_PULL_HASH_SCOPE`, and the nas role asserts the value the CLI would otherwise reject with exit 2. Flipping the scope — and rolling it back — is a config-only converge on the running digest.
- **`.claude/rules/fleet-deploys.md`'s NAS section gained the two operating imperatives this work needed**: there is no `nas_alloy_digest` and every apply task in the nas role is gated on `-e nas_apply_compose=true` (without it a converge is render-only), and a newly admitted metric family's first scrape is verified by VALUE.

## Suggested next steps

**Both remaining legs are attended NAS converges, run after the spec-`00102` PR merges, as one rollout PR of two commits (`fleet-deploys.md`).**

- **Leg A — converge at `full`, and take the baseline by value.** Pull the new `-compat` digest on the NAS and prove `runtime=compat` by running polars in it; re-pin `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml`; converge `infra/ansible/scripts/converge.sh site.yml --limit nas -e nas_apply_compose=true` with `nas_archive_pull_hash_scope` still `full`. Wait one full pull cycle, then read all three series for every channel — `uv run python infra/scripts/grafana-query.py 'zcrypto_archive_pull_files_walked{host="nas"}'` and the same for `_files_hashed` and `_verify_seconds`; `(no series)` is FAIL and means the keep-regex edit or the Alloy restart did not take. Record the per-channel values in leg A's pins-row commit message — that message is the only baseline leg B has to compare against.
- **The image pin and the new entrypoint must land in the SAME applied converge, so leg A cannot be split.** `infra/nas/pull-entrypoint.sh` is bind-mounted and re-read on any container restart, and an image predating this work answers `--hash-scope` with exit 2 — which the loop books as `capture_ok=0` and the ops writer reads as a not-clean capture pull, fail-closed until the dead-man pages. `nas_capture_image` is therefore deliberately **unchanged** by the implementing PR (that image does not exist until CI builds it from the merge), and a render-only converge of the new entrypoint against the old image is never run.
- **Leg B — flip to `incremental`, and measure the drop.** Set `nas_archive_pull_hash_scope: incremental` and converge the same way with `nas_capture_image` unchanged (config-only — the apply flag is what recreates the container with the new value). Wait one full pull cycle, read the same three series, and record the drop against leg A's per-channel numbers in leg B's pins-row commit message. Prune the NAS's stale image only after that row is written.
- **Resolve this topic on leg B's measurement** — write the measured per-cycle cost and the horizon it implies into the `## Resolution`, and retire the estimates in `## Why this matters` and `## Findings so far` rather than carrying them forward. No `ripe_when` is owed: the topic closes on a fix, not on a trigger.
