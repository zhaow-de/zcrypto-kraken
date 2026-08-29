---
status: resolved
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
- **The two operating imperatives this work needed are live on the deploy skills, not on `.claude/rules/fleet-deploys.md`** — the rule's condensation moved every per-tier converge mechanic out to the skills, leaving it one NAS line (the `-compat` invariant) and no NAS section. The NAS-specific one is a bullet in `.claude/skills/zcrypto-rollout-image/SKILL.md`'s `## NAS converges`: there is no `nas_alloy_digest` — the pin is `nas_alloy_image` — and the role deploys `infra/nas/config.alloy` unconditionally but restarts Alloy only under `-e nas_apply_compose=true`, without which a converge is render-only. The other is generic, and sits in the `## Shared converge mechanics` block duplicated verbatim into that skill and `zcrypto-bump-alloy`: a newly admitted metric family's first scrape is verified by VALUE, where `(no series)` reads FAIL.

## Resolution

**Resolved 2026-08-29 by spec `00102`, measured on both legs rather than modelled.** The pull's walk is unchanged — every file is still stat-ed, so lag and the dead-man still cover the whole archive — and only the sha256 narrowed, to what rsync transferred plus a rotating 1/24 slice keyed on the loop's own cycle counter.

Leg A ran the old `full` scope under the new image to take the baseline; leg B flipped one config value. Per channel, log line and published gauge agreeing to the millisecond:

| channel | files_hashed A→B | verify_s A→B | hashed/walked |
| --- | --- | --- | --- |
| capture | 28,171 → 1,175 | 169.978 → 13.583 | 4.15% |
| capture_red | 25,141 → 1,052 | 221.819 → 9.085 | 4.16% |
| panel | 14,028 → 590 | 13.402 → 3.989 | 4.18% |
| liquidations | 8,701 → 346 | 4.825 → 2.117 | 3.96% |
| reconciled | 456 → 20 | 0.499 → 0.147 | 4.39% |

**410.5 s → 28.9 s per cycle, a 93.0% cut**, `failed=0` on all five channels. `files_walked` GREW on four of five and shrank on none, which is the check that the walk stayed whole. Every channel lands on the 1/24 = 4.167% slice target, so the rotation is doing what D3 says rather than a channel getting lucky.

**The horizon, replacing every estimate this topic carried.** A full re-verification of the archive is 24 cycles. Measured cadence: `changes(zcrypto_archive_pull_verify_seconds{channel="capture"}[6h])` = 5, so the period is ~70–75 min and the wrap completes in roughly **28–30 h**. That is change-counting over a 6 h window, not a timed wrap — no wrap has been watched end to end, and coverage rests on the slice arithmetic plus `test_the_rotation_slice_catches_a_corrupt_final_nothing_transferred` and the two mutation probes.

**Deployed exceptionally, and the exception is recorded where it binds.** Both legs ran an interim image built from the feature branch rather than `develop` — the user's decision, for the two-leg measurement, explicitly not a pattern to repeat. `docs/reference/fleet-pins.md`'s archive-pull row carries that constraint and the condition that retires it.

**What the branch found that the spec did not predict**: every NAS converge that RECREATES the container replays the whole gate export cold (~59 min measured on both legs), because the cache lives in the container's ephemeral `/tmp`. The spec had reasoned that keeping `cli/archive/` outside the replay-fingerprint closure avoided it; that reasoning was sound and the conclusion did not follow. Corrected in the spec, the plan, `fleet-pins.md`, `vars.yml` and the rollout skill.

## Suggested next steps

**Both remaining legs are attended NAS converges, run BEFORE the spec-`00102` PR merges — on an interim image built from this branch exceptionally (`capture-image.yml`'s `workflow_dispatch` against the unmerged branch, not CI's normal merge-triggered build) — and land inside that same implementing PR alongside the code (plan Tasks 6-9).**

- **Leg A — converge at `full`, and take the baseline by value.** Pull the new `-compat` digest on the NAS and prove `runtime=compat` by running polars in it; re-pin `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml`; converge `infra/ansible/scripts/converge.sh site.yml --limit nas -e nas_apply_compose=true` with `nas_archive_pull_hash_scope` still `full`. Wait one full pull cycle, then read all three series for every channel — `uv run python infra/scripts/grafana-query.py 'zcrypto_archive_pull_files_walked{host="nas"}'` and the same for `_files_hashed` and `_verify_seconds`; `(no series)` is FAIL and means the keep-regex edit or the Alloy restart did not take. Record the per-channel values in leg A's pins-row commit message, and the literal token `archive_pull baseline`, which leg B's gate greps for — that message is the only baseline leg B has to compare against.
- **The image pin and the new entrypoint must land in the SAME applied converge, so leg A cannot be split.** `infra/nas/pull-entrypoint.sh` is bind-mounted and re-read on any container restart, and an image predating this work answers `--hash-scope` with exit 2 — which the loop books as `capture_ok=0` and the ops writer reads as a not-clean capture pull, fail-closed until the dead-man pages. `nas_capture_image` **is** re-pinned by the implementing PR — to the interim digest built from this branch — committed on the branch at leg A, and a render-only converge of the new entrypoint against the old image is never run.
- **Leg B — flip to `incremental`, and measure the drop.** Set `nas_archive_pull_hash_scope: incremental` and converge the same way with `nas_capture_image` unchanged (config-only — the apply flag is what recreates the container with the new value). Wait one full pull cycle, read the same three series, and record the drop against leg A's per-channel numbers in leg B's pins-row commit message. Prune the NAS's stale image only after that row is written.
- **Resolve this topic on leg B's measurement** — write the measured per-cycle cost and the horizon it implies into the `## Resolution`, and retire the estimates in `## Why this matters` and `## Findings so far` rather than carrying them forward. No `ripe_when` is owed: the topic closes on a fix, not on a trigger.
