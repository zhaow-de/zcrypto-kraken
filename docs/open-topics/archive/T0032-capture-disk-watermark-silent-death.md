---
status: resolved
---

# Capture stops silently when the disk watermark breaches — and the dead-man still reports healthy

## Context — what

When `DiskWatermark` breaches (free space below `min_free_bytes`, default **1 GiB**), the capture daemon
**stops writing every row** but keeps looking perfectly healthy:

- `_handle_book_message` / `_handle_trade_message` (`cli/capture/command.py`) return early on
  `watermark.breached` — no book rows, no trade rows are appended.
- The breach does **not** disconnect the WS, so `client.connected` stays `True`.
- The breach does **not** open a gap, so `monitor.is_healthy(pairs)` stays `True`.
- Therefore `_healthcheck_loop`'s condition still holds and **the healthchecks.io dead-man keeps
  pinging green**:

```python
if client.connected and monitor.is_healthy(pairs):
    ping_healthcheck(url)
```

The only signal is a single `logger.error("disk watermark breached …")` on the **transition** — and at
the time of writing the VPS's logs shipped **nowhere** *\[since 2026-07-19 (iter-105) the capture hosts
ship container logs via Alloy, so that ERROR line now reaches Loki — though no alert rule selects
capture-host logs yet; see [[T0020]]'s capture-host alert-rules item\]*.

Net effect: **the disk fills → capture silently produces nothing → every monitor stays green → the
unbackfillable L2 stream is lost until a human happens to look.**

## Why this matters

L2 is the one artifact in this project that **cannot be backfilled**. This is a total-capture-loss
failure mode with **no alerting whatsoever**, and it is **dated**, not hypothetical:

- Measured on the live primary (2026-07-13, read-only): root fs **79 G total / 10 G used / 65 G avail**;
  capture data **2.4 G spanning 2026-07-08 → 2026-07-13** ⇒ **≈0.48 GB/day**.
- 64 GB of headroom before the 1 GiB watermark ⇒ **≈133 days ⇒ the breach lands ≈2026-11-23.**
- **No eviction/retention exists.** Confirmed on the host: no zcrypto prune timer or cron
  (`systemctl list-timers` shows only `systemd-tmpfiles-clean`). Spec `00048` explicitly made
  delete-after-verified a **non-goal** — but it did so reasoning from a **wrong** disk figure (below).
- Any unexpected disk consumer (log growth, the engine journal, a stray file) brings the date forward.

## Findings so far

- **`T0003`'s "~10 GB/day" figure is wrong by ~20×.** Measured: **0.48 GB/day** (both on the VPS and
  independently on the pulled NAS archive: 2.57 GB over ~5.2 days). This single bad number is load-bearing
  in the current design: it produced the "~7-day VPS ring buffer" and the "bring the workstation online
  every few days or the VPS evicts un-pulled segments and that L2 is **permanently lost**" constraint in
  T0003. **At the true rate the safe-offline window is ~4 months, not ~7 days**, and 00048's "the 7-day
  buffer's 12× margin makes eviction unnecessary" reasoning rests on the same bad figure.
- The same 20× error makes **[[T0028]]** far less urgent than believed: its stall cliff (~250–600 GB)
  is ~1–2 years out at the real rate, not ~2 months.
- The daemon is otherwise very lean (measured live): capture uses **102 MiB RAM** and ~24% of one core
  (max 53%) at ~58% of the peak hour's message rate.

## Done so far

- **The silent half is fixed.** `_healthcheck_loop` now withholds the dead-man ping while the watermark is
  breached, so a breach **pages** instead of reporting green:
  ```python
  if client.connected and monitor.is_healthy(pairs) and not watermark.breached:
      ping_healthcheck(url)
  ```
  Two TDD tests cover it (`tests/test_capture_command.py`): the dead-man pings with disk headroom, and
  **stops** on a breach. This converts a silent, total, unbackfillable-data loss into a loud, actionable
  alert — the highest value-per-line change available. *(Deliberately NOT implemented via
  `GapMonitor.start_gap`, which looked more elegant but interacts badly: `start_gap` is idempotent, so a
  concurrent `checksum_resync` gap would swallow the watermark gap, and its `end_gap` would then resume
  pinging **while still breached** — reintroducing the very bug.)*
- **The 20×-wrong disk figure is corrected** in [[T0003]] (measured **0.48 GB/day**, not ~10 GB/day),
  along with the "~7-day ring buffer / bring the workstation online every few days" framing it produced.
- **The breach window is now booked into the exit-bar gap accounting.** `GapMonitor` gained a dedicated
  global watermark window (`start_watermark_gap` / `end_watermark_gap`) that rolls into every pair's
  `gap_seconds` / `gap_ratio`, driven from `_disk_watermark_loop`. It is tracked **independently** of the
  per-pair `_open` gaps and of the ping-withholding — deliberately **not** via `GapMonitor.start_gap`
  (idempotent per pair: a concurrent `checksum_resync` gap would swallow it and resume the ping while
  still breached). So a breach inside a ≥7-day clean run now both **pages** *and* shows in the
  automated `<0.1 %` gap-time bar. Six executed tests (`tests/test_capture_gap_monitor.py`,
  `tests/test_capture_command.py`).
- **The watermark loop itself can no longer die silently.** Adversarial verification executed a
  backward wall-clock step (chrony makestep) across an open breach window: `end_watermark_gap`
  raised `CaptureError` inside `_disk_watermark_loop` — a task nothing awaits until shutdown — so
  polling stopped for the life of the process (`breached` froze, later real breaches never withheld
  the ping: the same silent death, reintroduced), and the corpse's exception re-raised in `_run`'s
  shutdown ahead of the writer-close loop. Fixed three ways, each with an executed regression test:
  `end_watermark_gap` clamps a negative window to zero instead of raising; the loop survives any
  exception from its body (a flaky mount's `OSError` out of `disk_usage` included) and keeps
  polling; and `_run`'s shutdown awaits log-and-continue on a task's non-`CancelledError` corpse so
  every writer still flushes on the way out.

~~Not yet deployed: the fix ships with the next capture-image rollout~~ *\[superseded 2026-07-19: the
breach-withhold fix has been **deployed since 2026-07-14** (verified inside the running image
`sha256:63708539…`); the (c) measurable-probe sub-fix `3e03aac` was the one remaining undeployed piece
— **now also deployed, confirmed 2026-07-26**: both `zcrypto` and `zcrypto-red` run image
`sha256:e5a44e1c…` (`RestartCount 0`), and `docker exec ... grep measurable cli/capture/gap_monitor.py`
finds the `measurable` property and the ping-gate's `and watermark.measurable` clause live in the
running code on both hosts — the spec `00069` capture-image rollout this topic's `ripe_when` named.
The ~135-day runway framing is dissolved by the live prune timers (a ~14-day ring once the first
deletion pass verifies).\]*

- **(b) 00048's eviction rationale corrected** — the body §Non-goals now carries an inline `[Superseded — …]` marker flagging that the "~12× margin makes delete-after-verified unnecessary" claim rests on the 20×-wrong fill figure, and that eviction is in fact *not* implemented (disk fills ≈2026-11-23).
- **(c) probe-outage blind spot closed** — `DiskWatermark` now tracks `measurable`; a probe that raises sets it False, and the dead-man ping is gated on `not breached AND measurable`, so "cannot measure" no longer pings green on a frozen `breached` (the healthcheck grace absorbs a transient blip; a sustained failure pages).

- **Partial verification 2026-07-22 (read-only, both hosts).** Recorded on the pushed branch `chore/t0032-prune-first-pass-partial-verification`, which **EXISTS** and has no PR; the 07-23 verification folds into it. Tonight's run executed on both hosts and correctly deleted nothing:

  ```
  zcrypto      ExecMainStartTimestamp=Wed 2026-07-22 03:17:02 UTC
  2026-07-22T03:17:02+00:00 zcrypto-capture-prune: deleted=0 retention_days=14 cutoff="2026-07-08 03:17:02 UTC"
  zcrypto-red  ExecMainStartTimestamp=Wed 2026-07-22 03:17:04 UTC
  2026-07-22T03:17:04+00:00 zcrypto-capture-prune: deleted=0 retention_days=14 cutoff="2026-07-08 03:17:04 UTC"
  ```

  `deleted=0` is the correct output here, and **non-trivially so on the primary**: its oldest final preceded the cutoff by only 10 h 30 m, so a retention one day too aggressive would have deleted ~14 hourly slots × 20 streams. `set -euo pipefail` plus `ExecMainStatus=0` also excludes a silently-failing `find`.

  **What this does NOT establish.** `deleted=0` is byte-identical to the output of a prune whose delete path cannot work at all: `-delete` under the unit's `ProtectSystem=strict` + `ReadWritePaths` has **never been exercised on either host**, and a sandbox misconfiguration surfaces only on the first run that actually tries to unlink. That — not the glob logic, which `tests/test_capture_prune.py` already covers offline — is what 07-23 uniquely tests.

- **The trigger date was estimated, not derived, and was a full week early for the secondary.** The cutoff is `now - 14d` evaluated at 03:17, so a final is eligible only once its mtime precedes that instant (`! -newermt`, i.e. mtime ≤ cutoff). Measured oldest finals:

  | host | oldest final (mtime) | first eligible run | why |
  |---|---|---|---|
  | `zcrypto` | 2026-07-08 13:47:32 | **2026-07-23** 03:17 UTC | tonight's cutoff (07-08 03:17) fell before it; 07-23's cutoff is 07-09 03:17 |
  | `zcrypto-red` | 2026-07-14 19:16:00 | **2026-07-29** 03:17 UTC | its oldest final is 6 days later than the primary's |

  The old estimate "~2026-07-22/23" happens to contain the primary's derived date; it was the **secondary** it got wrong, by a week. `Persistent=true` on the timer means a host down at 03:17 prunes at next boot, so these are first-*eligible* dates, i.e. floors.

  Both mtimes are corroborated independently by the finals counts: primary 6,516 finals over 325.55 h = **20.02** streams, secondary 3,520 over 176.07 h = **19.99** — two measurements agreeing on 20 concurrent final-producing streams.

- **Class counts at 03:20 UTC**: primary 6,516 finals / 117 `.part` / **0** `.held` / **0** `.corrupt`; secondary 3,520 / 117 / **0** / **0**. Note the consequence for the acceptance criterion: with zero `.held` and zero `.corrupt` on either host, the 07-23 pass **cannot** demonstrate that those classes are spared — only that finals + `.sha256` are deleted and the 117 `.part` files survive. Sparing of `.held`/`.corrupt` is covered by `tests/test_capture_prune.py`, not by this pass.

- **Disk is NOT yet flat, and cannot be before the first deletion** — the ring has not started. Primary `df Use%` 28 % (21 G used, 54 G avail of 79 G), secondary 20 % (9.1 G of 49 G). Against this topic's 2026-07-13 reading of 10 G used, that is +11 G in 9 days ≈ 1.2 GB/day, which looks like ~2.5× the 0.48 GB/day capture model — but the growth is **attributed, and capture is on-model**: `du` gives `/var/lib/zcrypto-capture` = **6.3 G** over 13.6 days = **0.46 GB/day**. The remainder is not capture (`/var/lib/docker` 5.1 G, `/var/log` 196 M). Flattening of the *capture* directory is what 07-23 should show.

- Method note: `journalctl --since "today 03:00"` returned empty on both hosts under a non-interactive `sudo` shell while the unfiltered `-n 3` query showed the lines above. The likely cause is quote handling through that shell, leaving `03:00` parsed as a separate argument rather than part of `--since` — **not diagnosed further**. The point that matters: an empty *filtered* query is absence-of-evidence, while `ExecMainStartTimestamp` and the dated journal lines are affirmative traces. Do not read an empty journal window as an absent run.

- **(2026-07-23 03:17 UTC — the PRIMARY's first REAL deletion pass, VERIFIED; the derived date held exactly.)** `zcrypto-capture-prune.service` ran on schedule, `Result=success` / `ExecMainStatus=0`, **`deleted=560`** at `cutoff="2026-07-09 03:17:02"`. The count is finals **plus** their `.sha256` sidecars — the script's single `find … \( -name '[0-9][0-9].parquet' -o -name '[0-9][0-9].parquet.sha256' \) ! -newermt "$cutoff" -print -delete | wc -l` counts both prints — so ≈ 280 finals + 280 sidecars.
  - **What this uniquely establishes** (the whole reason 07-23 mattered): the sandboxed `-delete` under the unit's `ProtectSystem=strict` + `ReadWritePaths` **works on its first real unlink** — the path that was byte-identical to a totally-broken delete until an actual deletion occurred. It is now exercised and green.
  - **Post-state, measured while fresh** (`ADA/EUR/book` sampled): the 07-08 day is emptied — `finals=0, .part=0, sha=0` (the day *directory* remains, since the prune is `-type f` only; harmless), while 07-09 is intact — `finals=21, sha=21, .part=0`, all kept (mtime past the 03:17 cutoff). Fleet-wide on the primary: `.part` **spared** (222 present at the snapshot; the count drifts with normal part-file churn between hourly merges), `.held`/`.corrupt` still **0** (so this pass does not exercise their sparing — `tests/test_capture_prune.py` covers that, as noted above).
  - **The ring buffer engaged.** Capture-dir `du` = **6.4 G** vs **6.3 G** at the 2026-07-22 reading — flat across 24 h against the pre-ring **1.2 GB/day** gross growth. On this single cycle the `≈2026-11-23` disk-fill deadline is **provisionally dissolved** into a steady ~14-day ring; the secondary's 07-29 pass confirms it (n=1 until then, which is why the topic stays `partial`).
  - **Clean attribution:** the prune is a **host** systemd unit (image-independent), and it ran at 03:17 — *before* spec 00069's Step-6 capture converge at 03:33 — so this result is untouched by the rollout. Capture stayed green through the deletion (`RestartCount=0`).
  - **The SECONDARY is still scan-only** (tonight: `deleted=0`, `cutoff 2026-07-09`, its oldest final 2026-07-14 19:16) — its first real deletion pass is **~2026-07-29**, the remaining open sub-item.

- **(2026-07-23 — sub-item (c)/(2) DISCHARGED: the measurable-probe fix is now deployed fleet-wide.)** Spec 00069's rollout put image `e5a44e1c` (revision `bada2e36`) on **both** capture hosts (secondary 07-22 Step 5, primary 07-23 Step 6). Verified two ways that it carries `3e03aac`: `git merge-base --is-ancestor 3e03aac bada2e36` is true, and the running image's `cli.capture.gap_monitor` source contains the `disk watermark UNMEASURABLE` line. So the "next capture-image rollout carries the not-yet-deployed probe fix" clause is satisfied; only the secondary deletion pass keeps this topic `partial`.


- **(2026-07-26, spec/plan `00069` T3 — the `/metrics` gauge)** `zcrypto_capture_disk_watermark_breached` (gauge, 0/1, tapped from `watermark.breached`) ships on both capture hosts' `/metrics` endpoints and is admitted by both hosts' Alloy keep-lists. Scrape-verified directly: `curl 127.0.0.1:9101/metrics` on both `zcrypto` and `zcrypto-red` returns `zcrypto_capture_disk_watermark_breached 0.0` (checked 2026-07-26). The alert itself is out of scope here — it lands in the dedicated alerting/dashboards iteration ([[T0020]]).

## Suggested next steps

- ~~(process, at the re-pin) schedule the T+24 h canary reminder~~ **(done as standing process, 2026-07-15):** codified in `.claude/rules/fleet-deploys.md` — the reminder is scheduled via the Slack MCP at every secondary re-pin, no longer this topic's item.
- **Retention: designed, config-implemented, deployed AND proven on the primary (2026-07-23).** Spec `00050` D8's `zcrypto-capture-prune` timer is **live on both hosts** (14-day retention, finals + `.sha256` only, never `.part`/`.held`/`.corrupt`). The primary's first real deletion pass is **verified** (deleted=560, sandboxed `-delete` proven, ring buffer confirmed — see Done so far), so the `≈2026-11-23` disk-fill deadline is dissolved there. **The delete-path property is thereby proven for BOTH hosts**: the prune `.service` is byte-identical across them (`sha256 ee51b6c5…`), same sandbox (`ProtectSystem=strict` + `ReadWritePaths=/var/lib/zcrypto-capture`), same `ext4` fs — nothing host-specific is left to differ. **That last sub-item — the secondary's first deletion pass — is DISCHARGED; its outcome is recorded under Resolution below.** **Recorded stance (explicit, 2026-07-19): the NAS custody mirror is deliberately never pruned** — it is the keep-forever archive (spec `00048` Role A); only the capture-host working copies ring-buffer.
- **(refuted 2026-07-30, see Resolution)** The compound `ENOSPC`-during-an-unmeasurable-probe residual rested on a false premise and is not carried forward.

## Resolution

**Resolved 2026-07-30**, on two grounds: the last open sub-item was confirmed clean, and the one residual this topic carried was **refuted** rather than deferred.

### The secondary's first deletion pass — confirmed

- **2026-07-29 03:17:04 UTC — `deleted=120`, `retention_days=14`, `cutoff="2026-07-15 03:17:04 UTC"`** (journal). The `ripe_when` predicted "~2026-07-29 03:17 UTC" from the oldest final (2026-07-14 19:16), and the pass fired on that date. `deleted=120` is ~60 finals + 60 sidecars, fewer than a full ~8 h of eligible hours across ~20 streams would give — consistent with this host's streams ramping in over its genesis day rather than all starting at 19:16; the date, not the count, is what the trigger predicted.
- **Steady state the next day** — 2026-07-30 03:17:04, `deleted=952`, cutoff `2026-07-16`: the ring buffer is engaged, not a one-off. `Result=success`, `ExecMainStatus=0` — read from `systemctl show` on 07-30, so these properties describe the **07-30** invocation; the 07-29 pass's success is evidenced by its own journal lines (`Deactivated successfully` / `Finished`), not by these.
- **The prune frontier is in the right day**: the oldest day still holding a final is 2026-07-16, against a 07-16 cutoff, and that day holds **421 finals** — consistent with ~20 h of retained hours across this host's ~21 final-producing streams, i.e. the sub-day boundary is where the cutoff puts it. Days 2026-07-14 and 07-15 are emptied of files entirely (finals=0, non-finals=0); only the directory skeleton remains, since the prune matches `-type f`.
- **`.part` sparing was NOT exercised by this pass and is not claimed from it.** The 229 `.part` files present are all from the live day 2026-07-30 — 14 days newer than the cutoff, so the prune's age filter never selected them, and their survival demonstrates nothing about sparing. The deleted window (07-14 → 07-16) contained no non-finals to spare. Sparing of `.part`/`.held`/`.corrupt` is covered by `tests/test_capture_prune.py`, exactly as recorded for the primary's pass above.
- **The host is healthy**: capture container `running`, `RestartCount=0`, 23 parquet files modified in the 5 minutes before the check.

### The residual is refuted, not deferred

The topic carried one: *"`_write_part`'s `ENOSPC` is caught, logged, and the buffer dropped — a real, un-booked loss, because `breached` is frozen at its last (green) value so no watermark gap is booked… the exit-bar gap accounting under-counts that window."* Checked against the code, its stated harm does not hold — and the half it did concede is real:

- **The operator is not blind** — which the residual itself granted. `DiskWatermark.check` sets `measurable` False and re-raises; the healthcheck loop's gate (`cli/capture/command.py`, `… and not watermark.breached and watermark.measurable`) is what **withholds the dead-man ping**, and `check`'s docstring names this as the fix for "the exact T0032 silent death". A sustained probe failure pages; it does not ping green.
- **The exit bar does book the loss.** T0003's bar is measured by `infra/scripts/continuity.py` **from the archive**, not by the daemon's in-process `GapMonitor` — the script's own header records that GapMonitor "cannot measure this" and undercounted the 07-13 crash ~50×. A dropped buffer leaves rows missing from the segment, which the archive-derived instrument books as intra-hour silence or a truncated hour.

What actually remains is narrower than the residual claimed: the daemon's **in-process** watermark-gap component under-counts during an unmeasurable window. That counter is explicitly not the exit-bar instrument, the incident pages regardless, and the archive-derived bar sees the loss — so this is a metric-fidelity nit, not the silent-loss hazard this topic exists about. Recorded as a conscious drop, with the refutation above as its reason.

### Disk headroom, stated at the right scope

The `≈2026-11-23` disk-fill deadline is dissolved on **both** hosts *for capture growth*, which is what this topic existed to achieve: the capture tree stands at **6.2 GiB** under the 14-day ring, with 17 day-dirs (07-14 → 07-30) — the ring has only just filled on this host, whose oldest final was 2026-07-14 19:16. (The 6.3 G figure recorded a week earlier in *Done so far* is the PRIMARY's tree, not this one's; the two hosts are not comparable on that number.)

Whole-volume usage is a separate scope and must not be quoted as if it were the same number: `df` reports **22 G used of 49 G (47 %), 25 G free**. The ~16 GiB that is not the capture tree is **`/var/lib/containerd` at 14 G — `docker system df` shows 6 images, 2 active, 9.98 GB (71 %) reclaimable**: accumulated capture-image layers from successive re-pins. That is step growth per rollout, not per day, so it does not threaten the watermark on any near horizon — but it is unmanaged, and it is recorded here rather than left implied. **A blanket `docker image prune -a` must never be the remedy**: `fleet-deploys.md`'s rollback path depends on the previous-good digest still being resident locally.

*A measurement note worth keeping:* the first pass of this check read the tree without `sudo` and with `2>/dev/null`, and returned "no day directories, 4.0K" — indistinguishable from a wiped capture root. The root is `0750 zcrypto-data`, so `find` was silently denied and the suppressed stderr turned a permission error into an apparent absence. Re-run with privileges, the same tree held 6.2 GiB across 17 day-dirs. An empty filtered query is not an absent event — and suppressing stderr is how you manufacture one.
