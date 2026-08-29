# Hosts — disk, load, reboots and the textfile transport

You are here because **an alert fired in Slack**. These are the two capture VPSes as *machines* — `zcrypto` (primary, also the trade engine) and `zcrypto-red` (secondary) — not the venue feed and not the archive. Every signal below is produced by Alloy's embedded node-exporter (`prometheus.exporter.unix` in `infra/ansible/roles/capture/files/config.alloy`): the `filesystem`, `loadavg`/`cpu` and `textfile` collectors, the last of them reading `.prom` files that small systemd oneshots write into `/var/lib/zcrypto-node-textfile`. Each section is written to be actioned without opening any other document.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

**Two standing constraints on everything below.** Reads on a host are fine at any hour; a **converge, an image re-pin or anything that stops the capture daemon is an attended action** — the operator's explicit word, never a 03:00 reflex, because L2 capture is unbackfillable. And **never print a container's whole environment or config on `zcrypto`** (`docker inspect … {{json .Config}}` / `.Config.Env`, `docker exec … env`, `docker compose config`): that host carries the live Kraken trade key and the Loki push password as container env. Scope every inspect to the field you need — `.State`, `.RestartCount`, `.Config.Image`, `.Mounts`.

______________________________________________________________________

<a name="zcrypto-capture-disk-low"></a>

## zcrypto-capture-disk-low — ALERT

### What you are seeing

A warning-severity Grafana alert (*Capture · spool disk low*), one instance per capture host: the **root** filesystem is below 10 % free and has been for 5 minutes. The value on the page is a **fraction, not a percent** — `0.08` means 8 % free. Dashboard: `zcrypto-fleet`, panel 301 *Filesystem free % by mountpoint*.

The rule reads `node_filesystem_avail_bytes / node_filesystem_size_bytes` at `mountpoint="/"`, because the unbackfillable L2 spool `/var/lib/zcrypto-capture` sits on the root filesystem.

### What it means

Nothing is lost yet. This is the **early** warning; the hard stop is much lower and much worse: below **1 GiB free** (`DEFAULT_MIN_FREE_BYTES` in `cli/capture/gap_monitor.py`) the daemon stops appending, every message is dropped, and `zcrypto-capture-watermark-breached` goes critical. L2 is unbackfillable and the venue serves no history, so seconds spent there are permanent.

The spool alone should not get you here: it is a bounded ring, pruned daily. Firing means either **the ring broke** or **something else is consuming the disk**. The three consumers that actually exist on these hosts:

- the capture spool — `zcrypto-capture-prune` at 03:17 UTC (`Persistent=true`), deleting committed finals `<HH>.parquet` and their `.sha256` sidecars older than `capture_retention_days` (14 in `infra/ansible/roles/capture/defaults/main.yml`), and **nothing else**;
- the engine journal, **primary only** — `zcrypto-engine-journal-prune` at 01:23 UTC, day-dirs older than `engine_journal_retention_days` (60) with a keep-newest-`retention_days` floor;
- **docker image layers — the known one, and the one nothing prunes.** No role and no timer removes images, every converge pulls another multi-GB app image, and the removal path is a workstation script run at pins-update time (`docs/reference/fleet.md` § Storage topology).

### What to do

1. **Look at the filesystem.** `ssh zcrypto` (primary) or `ssh red` (secondary), then `df -h /`.
2. **Find the consumer — with `sudo`.** `sudo du -xsh /var/lib/zcrypto-capture /var/log /tmp "$(sudo docker info --format '{{.DockerRootDir}}')" 2>/dev/null | sort -h`. The `sudo` is load-bearing: the spool is `0750 zcrypto-data:zcrypto-data`, so an unprivileged `du`/`find` reads it as **empty** and you conclude the spool is innocent when it is not. Ask docker for its own root dir rather than assuming `/var/lib/docker`.
3. **Prove the prune ring is alive** — its log line is the whole evidence: `systemctl list-timers 'zcrypto-*'` and `journalctl -u zcrypto-capture-prune -n 3 --no-pager`, which prints `zcrypto-capture-prune: deleted=N retention_days=14 cutoff="… UTC" dir=…`. `deleted=0` on a single day is normal; `deleted=0` day after day while the tree grows means the ring is broken. On the primary also `journalctl -u zcrypto-engine-journal-prune -n 3 --no-pager` (`deleted=N kept=M …`). Neither timer publishes anything for a Grafana query to answer this — the journal line is it.
4. **Images dominating: use the script, never a blanket prune.** From the workstation, `uv run python infra/scripts/prune-host-images.py <host>` (dry-run by default), read the removal list against `docs/reference/fleet-pins.md`, then re-run with `--apply`. Pass `--keep <digest12>` for any image pre-staged for a converge that has not happened — the script cannot see one. **Never `docker image prune -a`**: it takes the recorded rollback digests, which is how a bad re-pin becomes unrecoverable.
5. **Never hand-delete inside `/var/lib/zcrypto-capture`.** The prune script's name globs are the entire safety argument: `<HH>.part####.parquet` (the live hour), `<HH>.held####.parquet` (quarantined rows), `<HH>.parquet.merging` and `*.corrupt*` all end up looking deletable and none of them is. If the spool must shrink now, run the sanctioned deleter: `sudo systemctl start zcrypto-capture-prune.service`.
6. **Confirm by value, not by silence.** From the workstation: `uv run python infra/scripts/grafana-query.py 'node_filesystem_avail_bytes{host="<host>",mountpoint="/"} / node_filesystem_size_bytes{host="<host>",mountpoint="/"}'` and read a number above `0.1`. **`(no series)` is a FAIL, not a zero** — it means the filesystem collector or the host's telemetry is gone, and this rule is `noDataState: OK`, so it would sit green through exactly that.

### Retire when

`zcrypto-capture-disk-low` is absent from `infra/grafana/alerts.yaml`, or `capture_data_dir` (`infra/ansible/group_vars/capture_host/vars.yml`) is no longer on the root filesystem — the rule's `mountpoint="/"` selector then no longer names the spool and the section describes the wrong disk.

______________________________________________________________________

<a name="zcrypto-capture-load-high"></a>

## zcrypto-capture-load-high — ALERT

### What you are seeing

A warning-severity Grafana alert (*Capture · node load high*), one instance per capture host: the 1-minute load average **per core** has been above 1.5 for 10 minutes. Dashboard: `zcrypto-fleet`, panel 201 *Node load — each host against its own bar*.

The value is already normalized — the rule divides `node_load1` by that host's core count (`count by (host) (node_cpu_seconds_total{mode="idle"})`), so one threshold means the same thing on two differently-sized boxes.

### What it means

Sustained saturation, not a spike. The hourly NAS archive pull (an `rrsync` forced-command session against the spool) lasts seconds, and the rule's 10-minute hold outlasts it by construction, so this is a runaway or a thrashing host.

**Do not take core counts, baselines or container CPU limits from any prose — read them.** The rule's own comment records per-host vCPU counts "measured live", the two hosts' capture containers carry different `capture_cpu_limit`/`capture_memory_limit` values (a `host_vars/zcrypto-red` override of the role default), and all of those numbers rot without the file that states them changing. The series answer today's question:

- cores: `uv run python infra/scripts/grafana-query.py 'count by (host) (node_cpu_seconds_total{host="<host>", mode="idle"})'`
- applied container limits, on the host: `sudo docker inspect zcrypto-capture --format 'cpus={{.HostConfig.NanoCpus}} mem={{.HostConfig.Memory}}'` (scoped fields — never the whole `.Config`).

### What to do

1. **See who is spending the CPU.** `ssh <host>`, then `uptime; top -b -n1 -o %CPU | head -20; sudo docker stats --no-stream`.
2. **Is it the capture daemon?** If `zcrypto-capture` is pinned at its own CPU limit, read its log for a storm rather than restarting it — Grafana Explore, Loki `{host="<host>", container="capture", level=~"WARNING|ERROR"}` over the last hour. **A restart is not a load remedy**: it drops every pair and re-snapshots, which costs a gap on an unbackfillable stream.
3. **Is it patching?** `ps -eo pid,etime,cmd | grep -E '[a]pt|[d]pkg|[u]nattended'`. Wait it out; then expect `zcrypto-capture-reboot-pending` to follow.
4. **Is it the hourly pull?** `ps -eo etime,cmd | grep '[r]sync'`. Seconds is normal; a session that has been running for many minutes is a stuck pull, and the finding belongs to the NAS side.
5. **Is it I/O rather than CPU?** `vmstat 1 5` — a high `wa` column with modest CPU means the disk, and the next thing to read is `zcrypto-capture-disk-low` above.
6. **Confirm capture never actually degraded**, which is the only question that matters here: `uv run python infra/scripts/grafana-query.py 'zcrypto_capture_seconds_since_last_book_message{host="<host>"}'` — every pair small and moving. `(no series)` is a FAIL.

### Retire when

`zcrypto-capture-load-high` is absent from `infra/grafana/alerts.yaml`.

______________________________________________________________________

<a name="zcrypto-capture-reboot-pending"></a>

## zcrypto-capture-reboot-pending — ALERT

### What you are seeing

A warning-severity Grafana alert (*Capture · reboot pending (attended)*), one instance per capture host: `/run/reboot-required` has existed for 15 minutes. Dashboard: `zcrypto-fleet`, panel 503 *Reboot pending & probe presence*.

The gauge is published every 15 minutes by `zcrypto-reboot-check.timer` as an **explicit 0 or 1**, never as an absent series. It will keep firing until a human reboots the host. That persistence is the design, not a nuisance.

**The alert summary's pointer is wrong and is being corrected to name this section.** It says "Guidance in `.claude/rules/fleet-deploys.md`"; that rule carries only the Kraken-maintenance-window bullet and no reboot procedure. The discipline lives in **`docs/reference/fleet.md` § Reboots**, restated below so you need neither file at 03:00.

### What it means

A kernel or other critical patch installed. Nothing is broken and nothing is degrading. The capture VPSes run unattended-upgrades with `Automatic-Reboot "false"` (`base_unattended_upgrades_automatic_reboot: "false"` in `infra/ansible/group_vars/capture_host/vars.yml`), so patches install themselves and the reboot is a human act — precisely so that unbackfillable L2 capture, and on the primary the live trade engine, are never restarted unwatched. This rule is what makes that flip safe: it is the only thing that notices the flag.

**This is not an emergency and it is not a 03:00 job.** The cost of waiting is an unpatched kernel; the cost of a careless reboot is a capture gap in the wrong place and, on the primary, a killed engine cycle. It selects only the two capture hosts — the ops node still auto-reboots on its own schedule.

### What to do

**Rebooting is an attended action.** Schedule it; do not fire it off from the page.

1. **Check the venue's published maintenance calendar first** — `https://status.kraken.com/api/v2/scheduled-maintenances.json`, the entries carrying `WebSocket` or `REST` in `components`. Never reboot inside one: the reboot gap landing inside a venue outage conflates two loss sources exactly where the ledger is least readable. Windows appear only 2–6 days ahead, so check at planning time **and again immediately before**.
2. **Secondary first, primary second** — `ssh red`, then `ssh zcrypto`. Same canary logic as an image rollout: if the kernel bricks the secondary, the primary is never touched.
3. **Pick the slot**: at least 1 h from any 4-hourly engine boundary (00/04/08/12/16/20 UTC), off the hour boundary itself, the primary in the measured book-traffic trough and right after a completed engine cycle, and the two hosts at least 1 h apart. Measure the trough from the archive; do not guess it.
4. **On the primary, additionally read the engine's state before you go**: `uv run python infra/scripts/grafana-query.py 'zcrypto_exec_armed' 'zcrypto_exec_kill_tripped'`. A reboot landing mid-order-submission is an untested path — that is the open sub-item of `T0027` — so with live order submission armed, wait for the gap after a completed cycle rather than reasoning about it.
5. **Expect a ~83 s capture gap.** Both containers come back on their own: `zcrypto-capture.service` runs compose attached with `Restart=always`, and the containers themselves are `restart: unless-stopped`.
6. **Verify by outcome before touching the next host** — this is what makes secondary-first mean anything:
   - every book stream's next `<HH>.parquet` begins at `:00:00.0x`, read from a **pulled** copy (the hosts have no parquet reader);
   - the NAS archive-pull's next hourly loop reports `failed=0` — that is the manifest verification;
   - `infra/scripts/continuity.py` on a pulled copy shows no new truncated hours;
   - on the primary additionally, the next `cycle-<HH>.json` lands with `completed_at` inside `[boundary, boundary+30 min]`;
   - the restart marker is the container's own timestamp — `sudo docker inspect zcrypto-capture --format 'started={{.State.StartedAt}} restarts={{.RestartCount}}'`, scoped fields only — never the time your `reboot` command returned.
7. **The alert clears itself.** The timer's `OnBootSec=2min` republishes a `0` within about two minutes of boot. If it does not clear, the probe has stopped publishing rather than the flag persisting — go to the textfile-transport section below.

### Retire when

`zcrypto-capture-reboot-pending` is absent from `infra/grafana/alerts.yaml`, or `infra/ansible/group_vars/capture_host/vars.yml` no longer sets `base_unattended_upgrades_automatic_reboot: "false"` — the hosts then reboot themselves and there is no human act to page for.

______________________________________________________________________

<a name="zcrypto-capture-textfile-missing"></a>
<a name="zcrypto-capture-textfile-unreadable"></a>
<a name="zcrypto-reboot-probe-stale"></a>
<a name="zcrypto-oneoff-textfile-stale"></a>

## capture-textfile-transport — ALERT

### What you are seeing

Four warning-severity rules over **one transport**. Which one fired names the failure mode; all four point at the same directory.

| uid | condition | what fired means |
| -- | -- | -- |
| `zcrypto-capture-textfile-missing` | `count(node_reboot_required{host=~"zcrypto\|zcrypto-red"}) < 2`, held 20 m | the metric is **absent**, not stale, on at least one host. The alert value is how many capture machines still publish the probe — `1` or `0` |
| `zcrypto-capture-textfile-unreadable` | `max by (host) (node_textfile_scrape_error) > 0`, held 15 m | the collector could not **open or parse** a `.prom` on the named host |
| `zcrypto-reboot-probe-stale` | `time() - max by (host) (node_textfile_mtime_seconds{file=~".*/reboot.prom"}) > 3600`, held 10 m | the pending-reboot probe has not rewritten its file in over an hour — about four missed 15-minute runs |
| `zcrypto-oneoff-textfile-stale` | the same shape for `.*/engine-journal-prune.prom`, `> 93600` (26 h), held 30 m | the daily engine-journal prune has not rewritten its file in over a day |

Dashboards: `zcrypto-fleet` panels 501 *Textfile age — did the timer run (capture)*, 502 *Textfile collector parse errors*, 503 *Reboot pending & probe presence*.

`zcrypto-oneoff-textfile-stale` can only ever be about the **primary**, whatever its selector says: `engine-journal-prune.prom` is written by the engine role's timer (01:23 UTC daily), and the engine runs only on `zcrypto`.

### What it means

One path, three ways to break, hence three alert shapes:

- a systemd **oneshot** writes a `.prom` atomically (`mktemp` beside the target, then `mv`) into `/var/lib/zcrypto-node-textfile` — `0755 root:root`;
- **Alloy's node-exporter textfile collector** reads that directory through the read-only `/:/host/root:ro` mount, running as the non-root `zcrypto-alloy` user;
- a **keep-regex** in `infra/ansible/roles/capture/files/config.alloy` decides which series reach Grafana Cloud at all.

A **stale** file is not a scrape error — the collector re-serves the last values forever, so the gauge keeps looking healthy; that is why the mtime rules exist. An **unreadable** file raises the scrape error. An **absent** series cannot go stale at all, and a staleness rule cannot fire on a series that never exists; only a `count()` shape turns absence into a value, which is why `zcrypto-capture-textfile-missing` exists in that shape.

What is actually at stake: the **attended-reboot safety net** — `node_reboot_required`, the section above — is frozen or gone, so a pending kernel reboot would go unseen; and the journal prune's liveness read is frozen, so a prune that silently stopped looks identical to one with nothing to do.

**Two blind spots this family does not close, so do not read its silence as coverage:**

- A **deleted** `.prom` makes its mtime series vanish rather than go stale. `max by (host)` simply drops that dimension and `noDataState: OK` swallows the empty result, so neither staleness rule fires. For `reboot.prom` the deletion is still caught, because `node_reboot_required` disappears with it and the `count()` rule sees that. For `engine-journal-prune.prom` **nothing catches it** — its four `zcrypto_engine_journal_prune_*` gauges have no rule of their own. The same gap is recorded on the sibling clock exporter (`infra/runbooks/capture.md#zcrypto-capture-clock-exporter-stale`).
- `zcrypto-capture-textfile-missing` has no `or vector(0)` fallback, so it catches **one** host going silent. If both stop publishing `node_reboot_required`, the query returns nothing and `noDataState: OK` keeps it green. If both hosts' telemetry is dark, the alloy-dark canaries page instead; if the whole textfile collector failed, `zcrypto-node-collector-failed` does.

`zcrypto-capture-prune` publishes no `.prom` at all and is outside all four rules — its only liveness trace is its journald line in Loki (`{host="<host>", container="zcrypto-capture-prune"}`).

### What to do

1. **Name the host and the file.** `unreadable` and both staleness rules carry `host`; `missing` gives you a count, so compare both hosts. `oneoff-textfile-stale` is the primary.
2. **Ask whether the timer ran.** `ssh <host>`, then `systemctl list-timers 'zcrypto-*'` and `systemctl status zcrypto-reboot-check.timer zcrypto-reboot-check.service --no-pager`. For the daily one, on the primary: `systemctl status zcrypto-engine-journal-prune.timer --no-pager` and `journalctl -u zcrypto-engine-journal-prune -n 3 --no-pager` — its last line reads `zcrypto-engine-journal-prune: deleted=N kept=M retention_days=… cutoff="…"`.
3. **Look at the files.** `ls -la /var/lib/zcrypto-node-textfile/` — every `.prom` must be world-readable (`0644`). `mktemp` creates `0600` and `mv` preserves it, so a publisher missing an explicit `chmod` publishes root-only and the non-root collector gets EACCES: the metric vanishes while everything else looks fine.
   **Do not fix that with `chmod` on the host.** The next run of the timer recreates the file at whatever mode its script sets, so a host `chmod` buys you one interval and hides the defect. The fix is the **script in the repo** — `infra/ansible/roles/capture/files/zcrypto-reboot-check.sh` and `infra/ansible/roles/engine/files/zcrypto-engine-journal-prune.sh`, both of which `chmod 0644` their temp file today — followed by an attended converge.
4. **Read the content**: `cat /var/lib/zcrypto-node-textfile/*.prom`. Malformed text is the parse leg of the unreadable rule; `node_reboot_required 0` or `1` plus its `# HELP`/`# TYPE` lines is what healthy looks like.
5. **Force a fresh publish of the reboot probe**: `sudo systemctl start zcrypto-reboot-check.service`. It is a `stat` plus a three-line atomic write under `ProtectSystem=strict` with only the textfile directory writable — safe at any hour. Then re-read the result from the workstation: `uv run python infra/scripts/grafana-query.py 'node_reboot_required{host="<host>"}' 'node_textfile_mtime_seconds{host="<host>", file=~".*/reboot.prom"}'`. **`(no series)` is a FAIL, never a zero.**
   **Do not casually start `zcrypto-engine-journal-prune.service` just to refresh its file** — that is a real delete of aged journal day-dirs on the engine host. It is idempotent and floored at the newest `engine_journal_retention_days`, but read its journal line first and know what you are running.
6. **File fresh and `0644`, series still absent → suspect the keep-regex.** Compare the deployed config with the repo: `sha256sum /etc/zcrypto-capture/alloy/conf/config.alloy` on the host against `sha256sum infra/ansible/roles/capture/files/config.alloy` in the checkout. The names that must be in the keep list are `node_reboot_required`, `node_textfile_scrape_error`, `node_textfile_mtime_seconds` and the four `zcrypto_engine_journal_prune_*`. A repo edit reaches the host only through an **attended converge** of that host, and the capture role's Alloy block is gated on `capture_alloy_digest`, which has no default — a converge that omits it skips the config copy silently. (Any converge of the host also asserts this checksum, so a drift you find here is a drift a converge would have refused.)
7. **Read the collector's own complaint**: `sudo docker logs grafana-alloy --since 1h 2>&1 | grep -i textfile`. If the collector itself is failing rather than one file, `zcrypto-node-collector-failed` will be firing too and every one-off timer's metrics are gone at once.
8. **Scope every inspect.** If you need the container's shape, ask for the field — `sudo docker inspect grafana-alloy --format '{{json .Mounts}}'`, `--format '{{.State.Status}} {{.RestartCount}}'`. Never the whole `.Config` and never `docker exec … env`: the primary holds the live trade key and the Loki push password in container env.

### Retire when

All four uids — `zcrypto-capture-textfile-missing`, `zcrypto-capture-textfile-unreadable`, `zcrypto-reboot-probe-stale`, `zcrypto-oneoff-textfile-stale` — are absent from `infra/grafana/alerts.yaml`, or the `textfile { directory = … }` block leaves `infra/ansible/roles/capture/files/config.alloy` (the one-off timers then publish through something else and every command above names the wrong path).
