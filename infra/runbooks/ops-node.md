# Ops node — its timers and units

You are here because **an alert fired in Slack**, or because **a guard in the code pointed you here**. Find the section whose anchor matches the alert `uid` or the anchor in the comment that sent you. Each section is written to be actioned without opening any other document.

Everything below is produced on one host — `zcrypto-ops`, reached as `ssh hp`. Six systemd timers run there (`infra/ansible/roles/ops/`), each firing a `Type=oneshot` unit that runs an ephemeral, digest-pinned `docker run --rm --pull never` and then publishes a node-exporter textfile under `/var/lib/zcrypto-ops/textfile/`; the host's Alloy scrapes those files and ships their series to Grafana Cloud, and ships the units' journal lines to Loki. Every rule in this file reads one of those textfile series, or those log lines, or the host's own load average. The host has **no `uv`** — it runs containers, not the repo CLI.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-ops-archive-pull-stalled"></a>
<a name="zcrypto-ops-archive-pull-exit-nonzero"></a>

## zcrypto-ops-archive-pull — ALERT

### What you are seeing

Two Grafana alerts on the same unit, `zcrypto-archive-pull.service` — despite the name it pulls nothing; it is the **overlay-writer cycle** (reconcile + the daily trade backfill), and the unit and metric names are historical because the alert rules are provisioned against them.

- **`Ops · archive-pull stalled (dead-man)`** (uid `zcrypto-ops-archive-pull-stalled`) — **critical**. `time() - ops_archive_pull_last_success_timestamp > 10800` (3 h), `for: 5m`, `noDataState: Alerting`. No series at all is itself the alarm: the host, the timer, or Alloy is gone.
- **`Ops · archive-pull non-zero exit`** (uid `zcrypto-ops-archive-pull-exit-nonzero`) — **warning**. `ops_archive_pull_exit_code > 0`, `for: 5m`, `noDataState: OK`. The cycle ran and its reconcile step failed.

### What it means

`zcrypto-archive-pull.timer` fires at `*-*-* *:12,42:00` with `Persistent=true`, so 3 h is about six missed half-hourly ticks. Each tick reads the NAS's canonical trees through the read-only NFS automount at `/mnt/zhao-crypto` and writes the overlay locally under `/var/lib/zcrypto-ops/capture-reconciled`.

**The two rules partition the failure, and a gate-skip is in neither of them.** The cycle opens with a fail-closed gate: it reads `/mnt/zhao-crypto/.pull-status` — written by the NAS right after its own capture pulls — and skips reconcile *and* backfill unless `capture_ok=1`, `secondary_ok=1`, and `ts_epoch` is younger than 14400 s and no more than 600 s in the future. A skip is a state, not a fault: it exits 0, bumps `ops_archive_pull_last_success_timestamp`, and echoes `WARNING: writer cycle SKIPPED (fail-closed gate): <reason>` to the journal. So **stalled firing is never a skip** — it is the unit itself not completing.

`rc=1` is set in exactly one place in `infra/ansible/roles/ops/templates/archive-pull.sh.j2`: the reconcile `docker run` failing. A trade-backfill failure leaves rc at 0 and pages through its own exit-code rule instead.

**A persistent skip pages nowhere here.** A skipped cycle never rewrites `reconcile.prom`, so `zcrypto_reconcile_last_success_timestamp_seconds` ages until `Reconciler · exporter stale` (uid `zcrypto-reconcile-exporter-stale`, critical at 3 h, its section in `infra/runbooks/ops.md`) pages. The same rule is what escalates a reconcile step that keeps failing — the CLI publishes no textfile on a failed cycle, so exit-nonzero at warning is the early notice and exporter-stale at critical is the follow-up.

**The cycle does feed a healthchecks.io dead-man on rc 0** — `curl` to `ops_archive_pull_healthcheck_url` at the tail of the script, restored 2026-07-17 after the rewrite that dropped it starved the check into DOWN. Correcting a stale claim: `infra/ops/README.md`'s *Dead-man pings* paragraph under *Overlay writer + panel* still says the cycle "pings **nothing**"; that sentence describes a state the script has left. Whether the URL is non-empty on the live host is a vaulted host var — not readable from the repo, and never read by printing a container's environment.

### What to do

1. **`ssh hp`, then read the timer and the unit**: `systemctl list-timers zcrypto-archive-pull.timer` (`LAST`/`NEXT`) and `systemctl status zcrypto-archive-pull.service zcrypto-archive-pull.timer`. A `Persistent=true` catch-up run right after the 02:25 UTC reboot is expected, not a finding.
2. **Read the journal, and prove you read something**: `sudo journalctl -u zcrypto-archive-pull.service --since -4h --no-pager | wc -l` first, then the same without `wc`. Unprivileged `journalctl -u` prints `-- No entries --` above a you-cannot-see-system-messages hint — that empty result is a permissions artifact, not an idle unit. Look for `writer cycle SKIPPED (fail-closed gate):` and `reconcile failed, continuing`.
3. **If it is a skip, the fault is upstream.** `cat /mnt/zhao-crypto/.pull-status` and `date -u +%s`, and compare against the three conditions above. A not-clean or stale status means the NAS's own capture pulls are broken — go to the NAS's rules and its `infra/nas/pull-entrypoint.sh` logs. **Do not hand-edit `.pull-status`**: it is the gate's ground truth, and the gate exists to refuse a frozen view.
4. **If reconcile failed, look for a leftover container first.** `sudo docker ps -a --filter name=zcrypto-reconcile` — after a dockerd crash the leftover makes the next run fail on the name conflict; `sudo docker rm zcrypto-reconcile`. Then `sudo systemctl status docker`.
5. **Check the mount.** `ls /mnt/zhao-crypto/capture-segments | tail`. The automount times out at 15 s and the NFS is `ro,soft,timeo=100,retrans=3` (`timeo` is deciseconds, so 10 s × 3). An EIO is the designed outcome of a hung NAS and fails the cycle loudly — the CLI treats an unreadable segment as an integrity fact, never as absence, so it cannot ledger a false verdict.
6. **Check the image.** The run is `--pull never`, so a digest the host never pulled fails every tick: `sudo docker image inspect --format '{{.Id}}' ghcr.io/zhaow-de/zcrypto-capture@<the ops digest from docs/reference/fleet-pins.md>`. Scope every inspect to the field you need — never `{{json .Config}}`, never `{{json .Config.Env}}`, never `docker compose config`.
7. **Re-running is attended.** `sudo systemctl start zcrypto-archive-pull.service`. Reconcile is detect-only on this host (`ops_reconcile_mint: false`) and the ledger dedupes, so a re-run costs nothing but time; it also runs the daily backfill if today's stamp is absent.
8. **Verify by outcome, from the workstation**: `bash infra/scripts/ops-postverify.sh`. Its `archive-pull exit code` and `reconcile freshness (s)` checks are exactly these two rules' operands. `(no series)` is a FAIL there, never a zero.
9. **Never read "nothing was lost" out of these two rules.** They are unit liveness. Loss is booked by the reconciler, and hour H is bookable no earlier than H+2 h, at the next `:12`/`:42` tick after that.

### Retire when

`zcrypto-ops-archive-pull-stalled` and `zcrypto-ops-archive-pull-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `ops_archive_pull_last_success_timestamp` and `ops_archive_pull_exit_code` are no longer written by `infra/ansible/roles/ops/templates/archive-pull.sh.j2`.

______________________________________________________________________

<a name="zcrypto-trade-backfill-stale"></a>
<a name="zcrypto-trade-backfill-exit-nonzero"></a>

## zcrypto-trade-backfill — ALERT

### What you are seeing

Two **critical** Grafana alerts on the daily trade-tape healing step, which runs as the second half of the same `zcrypto-archive-pull.service` cycle.

- **`Trade backfill · last success stale`** (uid `zcrypto-trade-backfill-stale`) — `time() - zcrypto_trade_backfill_last_success_timestamp > 172800` (~2 days), `for: 5m`, `noDataState: Alerting`. The step is daily, so ~2 days is the cadence plus one tolerated miss.
- **`Trade backfill · non-zero exit code`** (uid `zcrypto-trade-backfill-exit-nonzero`) — `zcrypto_trade_backfill_exit_code > 0`, `for: 5m`, `noDataState: OK`.

### What it means

Only the trade tape is affected. Book data — the unbackfillable part — is untouched by this step; it heals Kraken trade rows over the public REST endpoint, and Kraken serves roughly 18 months of them, so there is no urgency cliff.

**The step runs at most once per UTC day, and it does not retry.** It is gated on `/var/lib/zcrypto-ops/.trade-backfill-last-utc-day`, which holds the UTC day and is written **unconditionally, before the run**. A failure therefore costs one attempt per day, not one per cycle: `zcrypto_trade_backfill_exit_code` stays above zero for up to ~24 h, and the metric — not a retry — is what carries the failure.

**Read the exit code as three cases, not two.** The rule's summary names the CLI's own codes: `2` = the primary root does not exist (the NFS view of `capture-segments` is gone), `1` = the sweep completed and recorded errors, its count printed as `errors=<n>` on the summary line. **Any other value came from `docker run` itself and means the container never started** — most often a leftover `zcrypto-trade-backfill` after a dockerd crash, or a digest the host never pulled. The summary does not cover that case; the code does.

**The backfill sits inside the fail-closed gate.** A skipped cycle never reaches this branch and never writes the stamp, so the backfill simply retries on the first non-skipped cycle of that day. Two days of skips will therefore trip `-stale` — but `Reconciler · exporter stale` will have paged many hours earlier, which is the discriminator.

**A backfill failure leaves the unit's rc at 0**, so `Ops · archive-pull non-zero exit` stays quiet for it by design.

`zcrypto_trade_backfill_hours_repaired_after_loss_total` is monotone and carried forward across runs; a partially failed run that still repaired hours still counts them.

### What to do

1. **Read the day's attempt.** `ssh hp`, then `sudo journalctl -u zcrypto-archive-pull.service --since -48h --no-pager | grep -iE 'backfill|SKIPPED'` — the script echoes `trade backfill failed (exit=<n>), continuing` and replays the CLI's whole output into the journal, including the `errors=` summary line.
2. **Read the stamp and the textfile.** `cat /var/lib/zcrypto-ops/.trade-backfill-last-utc-day` — today's date means today's attempt has already happened. `cat /var/lib/zcrypto-ops/textfile/trade-backfill.prom` for the exit code, last run and last success as published.
3. **Exit 2 → the mount.** `ls /mnt/zhao-crypto/capture-segments`. Treat it exactly as the writer cycle's mount check above.
4. **Exit 1 → read the errors.** Fetch failures against Kraken's REST point at the venue (check its status page and the capture-side venue-status signals); unreadable segments point at the NAS or the mount.
5. **Any other code → clear the container.** `sudo docker ps -a --filter name=zcrypto-trade-backfill`, then `sudo docker rm zcrypto-trade-backfill`.
6. **To re-run today instead of waiting 24 h** — attended, and it re-runs reconcile in the same cycle:
   ```
   sudo rm /var/lib/zcrypto-ops/.trade-backfill-last-utc-day
   sudo systemctl start zcrypto-archive-pull.service
   ```
   Both steps are safe to repeat — reconcile is detect-only and its ledger dedupes, the backfill is watermarked. If the gate is skipping, this run will skip too and change nothing; fix the `.pull-status` cause first.
7. **Verify the metric moved, not the unit's exit status**: `zcrypto_trade_backfill_exit_code` back at 0 and `zcrypto_trade_backfill_last_success_timestamp` advanced, read through `uv run python infra/scripts/grafana-query.py` from the workstation. The unit exits 0 on a failed backfill, so `$?` proves nothing here.
8. **Expect the downstream page if this persists.** tape-bars defers any day whose trade tape is not heal-complete and exits 0 while doing so, so a stalled healer surfaces next as `Ops · tape-bars not advancing` — `infra/runbooks/ops.md#zcrypto-ops-tapebars-not-advancing`.

### Retire when

`zcrypto-trade-backfill-stale` and `zcrypto-trade-backfill-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `zcrypto_trade_backfill_last_success_timestamp` and `zcrypto_trade_backfill_exit_code` are no longer written by `infra/ansible/roles/ops/templates/archive-pull.sh.j2`.

______________________________________________________________________

<a name="zcrypto-ops-verified-replay-stale"></a>
<a name="zcrypto-ops-verified-replay-exit-nonzero"></a>

## zcrypto-ops-verified-replay — ALERT

### What you are seeing

Two Grafana alerts on `zcrypto-verified-replay.service`, the daily verified-path replay of the engine journal.

- **`Ops · verified-replay stale`** (uid `zcrypto-ops-verified-replay-stale`) — **warning**. `time() - ops_verified_replay_last_success_timestamp > 172800` (48 h = two missed daily cycles), `for: 5m`, `noDataState: Alerting`.
- **`Ops · verified-replay non-zero exit`** (uid `zcrypto-ops-verified-replay-exit-nonzero`) — **critical**. `ops_verified_replay_exit_code > 0`, `for: 5m`, `noDataState: OK`. Critical because a verified-path mismatch means the canonical replay disagrees with what the engine journaled.

### What it means

`zcrypto-verified-replay.timer` fires daily at `05:23` UTC with `Persistent=true`. The unit runs `zcrypto engine replay --path verified --date <day> --journal-dir /nas/engine-journal` in the pinned image, reading the journal through the same read-only NFS mount.

**It is a catch-up loop over a watermark, not a single-day run.** `/var/lib/zcrypto-ops/.verified-replay-watermark` holds the last successfully replayed UTC day; the loop walks watermark+1 through yesterday, capped at 30 days per run.

**`last_success` bumps only when the run is clean AND fully caught up** (`ops_verified_replay_days_behind` at 0). Read `days_behind` on the same panel — it is the discriminator:

- **`days_behind > 0`, exit code 0** — the loop stopped short without advancing, for one of four reasons, each logged verbatim: the day's directory under `/mnt/zhao-crypto/engine-journal/<day>/` holds no `cycle-*.json` or `failed-cycle-*.json` (`journal has not caught up`); the **successor** day holds none either, so the day may be only partly pulled (`journal freshness unproven` — this successor-day probe is the only journal-freshness check there is, because `.pull-status` carries `capture_ok`/`secondary_ok` and nothing about the journal); or the 30-day budget ran out (`capped at 30 day(s)`).
- **Exit code non-zero** — either a day genuinely mismatched, or the run was **refused** before it started.

**A refused run touches neither the watermark nor the textfile**, exits 1, and names the file in its own error line: the watermark is not a `YYYY-MM-DD` day, is a shape-valid but nonexistent calendar date, is beyond yesterday (clock skew or a manual edit), or the seed could not be persisted. An **empty** watermark file is the one to know: it once parsed as *tomorrow*, skipped the loop forever, and read fully healthy while doing so — hence the refusal.

**A mismatch is retried nightly and blocks everything after it.** The loop breaks on the first failing day without advancing, so no later day is verified past the gap — which is why `-stale` follows about 48 h behind a persistent `-exit-nonzero`.

The healthchecks.io dead-man for this timer is fed only on a clean, fully-caught-up run, so hc.io silence during a stall is consistent with these pages, not a second incident.

### What to do

1. **`ssh hp`, then read the unit and its last three days**: `systemctl status zcrypto-verified-replay.service`, then `sudo journalctl -u zcrypto-verified-replay.service --since -3d --no-pager` — confirm the output is non-empty before reading anything into it. Grep for the four stop messages above and for `ERROR: watermark`.
2. **Read the watermark and the journal tree.** `cat /var/lib/zcrypto-ops/.verified-replay-watermark`; `ls /mnt/zhao-crypto/engine-journal/ | tail -3`. The day after the watermark **and** its successor must each hold `cycle-*.json` or `failed-cycle-*.json`.
3. **Journal not arriving is a NAS-side finding**, not this unit's. Nothing here can fix a stalled journal pull, and the fail-closed stop is correct behaviour.
4. **Repair a refused run with a tmp+mv write, matching the script** — an in-place truncate is what minted the zero-byte watermark in the first place:
   ```
   printf '%s\n' YYYY-MM-DD | sudo tee /var/lib/zcrypto-ops/.verified-replay-watermark.tmp > /dev/null
   sudo mv /var/lib/zcrypto-ops/.verified-replay-watermark.tmp /var/lib/zcrypto-ops/.verified-replay-watermark
   ```
   Set it to the last day genuinely verified, or delete the file to re-seed from yesterday-1. **Never leave it empty.**
5. **Never advance the watermark past a mismatching day to silence the page** — that marks the day verified forever, and the day is exactly the finding.
6. **Reproduce a mismatch off-host** from the workstation, which mounts the same export: `uv run zcrypto engine replay --path verified --date <day> --journal-dir /mnt/zhao-crypto/engine-journal`. The output names each boundary — `MISMATCH: worst <asset> |diff| <n>`, `MISMATCH (corrupt evidence): …`, or `VALIDATION-FAILED: …` — and closes with `replayed N success record(s) via the verified path: …`. The CLI exits 1 if any mismatch or validation failure appears; a day with no journal artifacts at all exits 0 after printing `no journaled cycles found`, which is why the loop's artifact probes exist.
7. **Clear a leftover container.** `sudo docker ps -a --filter name=zcrypto-verified-replay`, then `sudo docker rm zcrypto-verified-replay` — the name conflict alone yields a non-zero exit.
8. **Re-run attended**: `sudo systemctl start zcrypto-verified-replay.service`. One run replays at most 30 days; a deeper backlog resumes the next night, and `-stale` correctly keeps firing until it catches up.
9. **Record a mismatch somewhere durable before the next clean night.** `ops_verified_replay_exit_code` returns to 0 on the next successful day and the evidence goes with it.

### Retire when

`zcrypto-ops-verified-replay-stale` and `zcrypto-ops-verified-replay-exit-nonzero` are both absent from `infra/grafana/alerts.yaml`, or `ops_verified_replay_last_success_timestamp` and `ops_verified_replay_exit_code` are no longer written by `infra/ansible/roles/ops/templates/verified-replay.sh.j2`.

______________________________________________________________________

<a name="zcrypto-ops-panel-exit-nonzero"></a>

## zcrypto-ops-panel-exit-nonzero — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · panel non-zero exit`): `ops_panel_exit_code > 0`, `for: 5m`, `noDataState: OK`. The last hourly L2 panel materialize errored.

### What it means

`zcrypto-panel-materialize.timer` fires at `*-*-* *:22:00` with `Persistent=true` — ten minutes after the `:12` writer tick, so the reconciled overlay hours the materialize prefers are fresh from that cycle. The unit runs `zcrypto panel materialize /nas/capture-segments /data/capture-reconciled --panel-root /data/l2-panel`, writing the panel tree locally under `/var/lib/zcrypto-ops/l2-panel`.

**Freshness, not truth.** The panel is derived, watermarked per pair and recomputable from the archive; a failed hour costs staleness and the next healthy run picks it up. Nothing here is unbackfillable.

The CLI exits 1 **iff at least one hour errored**, and logs each failure at ERROR as `panel hour failed pair=… hour=… : …` — so `Ops · ERROR logs` usually pages the same event with the message attached, which is where the actual cause is. A generation/manifest refusal is different: it aborts before any hour runs and prints its own instruction. Do not "fix" that by deleting `panel-meta.json` alone — the refusal exists precisely because that would stamp this code's generation onto hours another one wrote.

**There is no panel staleness rule, and that is deliberate.** `panel-materialize.sh.j2` publishes `ops_panel_last_success_timestamp`, but **no rule in `infra/grafana/alerts.yaml` reads it** — `ops_panel_exit_code` is the only `ops_panel_*` series any rule selects. A timer that stops firing altogether therefore trips **no Grafana rule at all**; the exit code freezes at its last value and the textfile is re-served forever. The only thing that can catch it is the healthchecks.io dead-man for the panel check, pinged only on a clean run and only when `ops_panel_healthcheck_url` is set — surfacing through `Fleet · healthchecks.io watchdog` (uid `zcrypto-hcio-watchdog`) and hc.io's own Slack integration. Whether that URL is set on the live host is a vaulted host var, not readable from the repo. This gap is recorded and measured, not overlooked, and drill O **has now answered it**: on 2026-08-31 the panel timer was stopped and the dead-man alone caught it, paging 3 h after the last clean ping and 2 h 49 m after the stop (`docs/reference/drill-log.md`, entry `O`). **No staleness rule is owed**, and this paragraph stands as the reason one is absent rather than as an open question. The notice is long by construction — `timeout` 7200 s + `grace` 3600 s — so a panel that dies just after a clean ping is unnoticed for the better part of three hours; that is the cost this deliberate gap carries, now measured rather than assumed. **Do not close or reopen it from this runbook** — a rule found owed is a change to `alerts.yaml`.

### What to do

1. **Read the failing hours.** `ssh hp`, then `sudo journalctl -u zcrypto-panel-materialize.service --since -2h --no-pager` — each failure names pair, hour and message, and the run closes with a `panel materialize complete … errors=<n>` line.
2. **Check both roots.** `ls /mnt/zhao-crypto/capture-segments` (the read-only NFS view; an EIO on the soft mount is a loud per-hour error by design) and `ls /var/lib/zcrypto-ops/l2-panel` (the writable output tree).
3. **Clear a leftover container.** `sudo docker ps -a --filter name=zcrypto-panel-materialize`, then `sudo docker rm zcrypto-panel-materialize`.
4. **Re-run**: wait for the next `:22`, or `sudo systemctl start zcrypto-panel-materialize.service`. The per-pair watermark makes the re-run idempotent — it processes only hours newer than what is already written.
5. **A full regeneration is not this, and is not yours to start.** Panel regeneration is the point of no return (no old tree survives, rollback is another full rebuild) and runs only on the user's explicit word. Related trap while one is in progress: **an ordinary converge silently re-arms this timer**, firing a materialize against a half-rebuilt tree — `-e ops_panel_timer_hold=true` is the opt-in that keeps it stopped for that window.

### Retire when

`zcrypto-ops-panel-exit-nonzero` is absent from `infra/grafana/alerts.yaml`, or `ops_panel_exit_code` is no longer written by `infra/ansible/roles/ops/templates/panel-materialize.sh.j2`. The no-staleness-rule paragraph above retires when any rule in `infra/grafana/alerts.yaml` selects `ops_panel_last_success_timestamp`.

______________________________________________________________________

<a name="zcrypto-ops-load-high"></a>

## zcrypto-ops-load-high — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · node load high`): `node_load1{host="ops"} > 20`, `for: 5m`, `noDataState: OK`, charted on the `Fleet health` board. The `host="ops"` label comes from `external_labels` on this host's Alloy, which is what makes the selector partition the metric away from the NAS's own `node_load1`.

### What it means

Sustained saturation, not a transient burst. Nothing is lost by load alone — the cost is that timers overrun their ticks, and one of them has a cliff: a writer cycle past 1800 s means the next `:12`/`:42` trigger fires against a still-activating unit and is **dropped**, halving the booking cadence (`infra/runbooks/ops.md#zcrypto-reconcile-cycle-duration` owns that, and its own rule warns at 1500 s).

**Two corrections to the rule's own comment, which the responder would otherwise reason from.**

*The timer count is stale.* The comment says "Alloy, the four timers, and soon the overlay writer". Counted from `infra/ansible/roles/ops/` today there are **six** timers, and the overlay writer is one of them rather than pending:

| Timer | Schedule (UTC) | `Persistent=` |
| -- | -- | -- |
| `zcrypto-archive-pull.timer` | `*:12,42:00` | yes |
| `zcrypto-panel-materialize.timer` | `*:22:00` | yes |
| `zcrypto-tape-bars.timer` | `*:52:00` | yes |
| `zcrypto-verify-replay.timer` | `03:41:00` | yes |
| `zcrypto-verified-replay.timer` | `05:23:00` | yes |
| `zcrypto-grafana-watchdog.timer` | `*:0/5:41` | no |

*The thread count is unverified.* The comment sources "24 threads" to `infra/ansible/roles/ops/defaults/main.yml`, and that file records no CPU count; nothing in the repo does. The threshold is 20 either way — but if you are about to reason about the ratio, run `nproc` on the host and use that.

**Known, accepted overlaps and bursts, none of them findings on their own**: the writer's `:42` slot collides with the 03:41 verify-replay run once a day (both are read-only NFS readers); the host auto-reboots at 02:25 UTC and five of the six timers are `Persistent=true`, so a post-boot catch-up burst is expected; and this host also carries the liquidations poller, Alloy, and the agentboard web terminal with its tmux sessions, so not every load spike is pipeline work.

### What to do

1. **Ask what is running.** `ssh hp`, then `uptime`, `top -bn1 | head -25`, `sudo docker stats --no-stream`.
2. **Ask which oneshots are mid-run.** `systemctl list-units 'zcrypto-*.service' --state=active` and `systemctl list-timers 'zcrypto-*'`.
3. **Correlate on the `Data integrity` board** before touching anything: `zcrypto_reconcile_cycle_duration_seconds` against its 1500 s bar, `zcrypto_reconcile_ledger_scan_seconds` (the append-only ledger becomes the cycle's cost driver as it grows — `infra/runbooks/ops.md#reconcile-ledger-scan-cost`), and `ops_verified_replay_days_behind` (a catch-up run replays up to 30 days in one pass).
4. **The heaviest single thing this host does is a verify-replay rebuild** after its state directory was lost — it replays the whole archive and takes nights, and the sweep's census says so (`replayed` high, `reused` near zero).
5. **Do not kill a running unit to shed load.** A killed reconcile publishes nothing, so it goes *stale* rather than red and you lose the signal you would have read; a killed verify-replay loses up to 250 replayed hours, its checkpoint interval (`_FLUSH_EVERY` in `cli/archive/replay.py`).
6. **Do not retune the bar in place.** A breach that repeats is capacity or scheduling work, not a threshold problem.

### Retire when

`zcrypto-ops-load-high` is absent from `infra/grafana/alerts.yaml`. The metric itself is node-exporter's and will not stop existing.

______________________________________________________________________

<a name="zcrypto-ops-error-logs"></a>

## zcrypto-ops-error-logs — ALERT

### What you are seeing

A **warning** Grafana alert (`Ops · ERROR logs`) on the `logs` receiver, `for: 0s`, `noDataState: OK`. **The log message itself is on the page** — that is the whole point of the rule, so read it before opening anything.

One alert instance per distinct line, message truncated at 200 characters, and **at most five instances**: the query is `topk(5, …)` over `count_over_time({host="ops", container=~"alloy|liquidations|zcrypto-.*", level=~"ERROR|CRITICAL"} … [15m])`. A storm carries more lines than the page shows.

### What it means

The `container` label names the source, and that is your routing:

- **`zcrypto-archive-pull`** — the reconcile or trade-backfill CLI errored inside the writer cycle. Pair it with `zcrypto-ops-archive-pull-exit-nonzero` and `zcrypto-trade-backfill-exit-nonzero` above.
- **`zcrypto-panel-materialize`** — a per-hour panel failure (`panel hour failed pair=… hour=…`); the panel section above.
- **`zcrypto-verify-replay`** / **`zcrypto-verified-replay`** — that sweep's CLI; `infra/runbooks/ops.md#zcrypto-ops-verify-replay-new-breakage` and the verified-replay section above.
- **`zcrypto-tape-bars`** — the tape-bars sweep; its sections are in `infra/runbooks/ops.md`.
- **`alloy`** — Alloy's own logfmt `level=error`, typically a remote-write or Loki-push failure. The telemetry plane is complaining about itself.
- **`liquidations`** — the poller. **This rule is its only error channel**: it is a long-lived daemon that flips no exit-code metric, and it direct-ships its own lines to Loki without passing through Alloy at all.

**Silence here is not a clean bill, and the reason is mechanical.** The `level` label is set by Alloy's parse stage, which matches only the CLI's Python-logging line shape (`YYYY-MM-DD HH:MM:SS,mmm LEVEL …`). The runner scripts' own `echo` lines never match it and ship unleveled — including the load-bearing `WARNING: writer cycle SKIPPED (fail-closed gate): …`. A gate-skip streak produces no ERROR page by construction.

Correcting the rule's own comment: it says the selector covers "the four zcrypto-\* units". The journal keep-regex in `infra/ansible/roles/ops/files/config.alloy` admits **five** — `archive-pull`, `verify-replay`, `verified-replay`, `panel-materialize`, `tape-bars`. The rule's selector is `zcrypto-.*`, so all five are in fact watched; only the count in the comment is stale.

### What to do

1. **Act on the message on the page first.** It names the failing pair, hour, day or endpoint in most cases.
2. **Get the full set out of Loki** — `topk(5, …)` truncates a storm, so five instances is a floor, not a count. Query `{host="ops", container="<the one named>", level=~"ERROR|CRITICAL"}` over the last hour, and size the storm with `sum(count_over_time({host="ops", level=~"ERROR|CRITICAL"}[15m]))` before calling it "five errors".
3. **On the host, read the source stream.** For a unit container: `sudo journalctl -u zcrypto-<unit>.service --since -30m --no-pager | wc -l` and then the lines themselves — an empty unprivileged result is a permissions artifact, not an idle unit. For the poller: `sudo docker logs --since 30m zcrypto-ops-liquidations`. For Alloy: `sudo docker logs --since 30m grafana-alloy`. **`--since` takes a duration or a full timestamp** — a bare `HH:MM:SS` fails to parse, and a grep over the resulting empty output reads as a clean bill.
4. **Then follow the section that owns whatever was named.** This rule reports that something errored and quotes it; it never diagnoses.
5. **Do not silence it to quiet a known storm** without a time box — for the liquidations poller it is the only error signal there is.

### Retire when

`zcrypto-ops-error-logs` is absent from `infra/grafana/alerts.yaml`.
