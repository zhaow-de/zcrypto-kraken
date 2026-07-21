---
status: open
ripe_when: NOW — the capture hosts' log plane is dark today and re-darkens after every nightly rotation; the repo fix is a two-line role change, but deploying it to the capture primary is an attended converge (`converge_primary=true`), so it wants the next capture maintenance window
---

# `logrotate copytruncate` on docker's json logs wedges the log readers

## Context — what

`infra/ansible/roles/base/tasks/main.yml:115` installs `/etc/logrotate.d/zcrypto-capture-docker`, a **daily, `copytruncate`** policy over `/var/lib/docker/containers/*/*-json.log` (rotate 90, compress, `olddir /var/log/zcrypto-capture`). `copytruncate` copies the file and then truncates the original **in place, while dockerd holds it open** — the one thing docker's own rename-based rotation never does. The observed effect: after the truncation the container ships no logs anywhere, and `docker logs <container>` hangs outright.

**Leading hypothesis for the mechanism** (the fix is the same either way, so this was not chased further): the json-file reader keeps its byte offset across the truncation and blocks until the file regrows past it. That cleanly explains the *follow* stream Alloy uses. It does **not** by itself explain a fresh, non-following `docker logs --tail 2` hanging — a new reader should not inherit the old offset — so there is a second dockerd-side effect in play (a read lock, or the decoder retrying on the truncated file). Treat the offset-strand as the leading account, not a settled one.

Found 2026-07-21 during the [[T0083]] attended window, from the `Capture · log pipeline dead` alerts (both hosts) that had been re-notifying every ~4h since ~06:07 UTC.

## Why this matters

It silently blinds the log plane of every **long-lived** container on any host carrying the `base` role — which is the capture hosts and ops (`site.yml`), the engine being co-located on the primary. That is both capture daemons, the engine, **and on ops the Alloy container plus the liquidations poller** (both `restart: unless-stopped` under the same glob); only the `--rm` ops jobs escape, because each new container gets a fresh log file and a fresh reader. The affected hosts' ERROR-log rules are blind for the duration, which is exactly the "green because we stopped looking" class. It is **not** data loss in the archive: capture itself is unaffected (both dead-men pinging, segments written), and metrics/SD are unaffected because they come from different components.

Severity scales with log volume, and the tail case is worse than "a day": the wedge lasts until the live file regrows past the pre-rotation size, so a 4 KB day self-heals in minutes, a 1.3 MB day stays dark for many hours — and once daily volume approaches the pre-rotation size, the file finishes catching up only around the *next* nightly rotation, i.e. the blindness becomes effectively permanent. It recurs after **every** rotation.

The policy is also **redundant**: the capture container already sets docker's own rotation (`max-size=50m`, `max-file=5`), which rotates correctly by renaming — the mechanism `copytruncate` exists to avoid, and which docker's reader follows without wedging.

## Findings so far — measured 2026-07-21 on the primary

- Loki's **last** capture line on both hosts: `2026-07-21 00:06:34 UTC` — identical to the second, i.e. a common cause, not two host-local faults.
- `logrotate.service` last ran `2026-07-21 00:49:52 UTC` — **43 minutes after** that last shipped line, which looks contradictory until the daemon's bursty logging is accounted for: 00:06:34 was simply the last line written before a quiet stretch, and the live file's own first post-truncation entry is `00:59:44`. Nothing shipped after the rotation.
- The rotated copy for the live capture container (`836397b183a5`) is **1,345,071 bytes** in `/var/log/zcrypto-capture/`; the live json.log has regrown only to **924,593 bytes**. So the file is roughly 420 KB short of the copy's size — and the reader's stranded offset is *at least* that copy size (under `copytruncate` anything written between copy and truncate is lost outright and pushes the offset higher), so that figure is a lower-bound estimate, not a measured offset.
- `docker logs zcrypto-capture --tail 2` **hangs (exit 124) on both hosts** — a fresh client wedges too, so the block is dockerd-side per container, not an Alloy bug.
- Alloy is healthy and shipping: the four `Fleet · Alloy dark` rules ([[T0079]]) all read Normal, `Alloy · docker service-discovery wedged` is inactive, and SD refresh is a flat 60/h on every host — so this is **not** the [[T0048]] defect-1 class. The two rule families together discriminate it: metrics up + logs dark ⇒ reader wedge, not agent death.
- Ops escapes it in practice because its workload containers are short-lived — each new container gets a fresh log file and a fresh reader.

## Suggested next steps

- **(Repo fix, autonomous)** Remove the logrotate policy from the `base` role — as `state: absent`, not merely deleted from the repo, or the existing `/etc/logrotate.d/zcrypto-capture-docker` persists on every host forever. Docker's own rotation already covers this correctly and reader-safely (rename-based): `max-size=50m`/`max-file=5` per capture container, 50m/3 daemon-wide. **Note the consequence to decide with it**: once the policy is gone, `/var/log/zcrypto-capture/`'s archived copies stop being pruned (and stop being produced) — decide whether to trim what is there. If a longer retention is genuinely wanted, change docker's `log-opts`, and be aware that **neither** alternative is free on the primary: container `log-opts` take effect only on container *recreate*, and daemon-wide `/etc/docker/daemon.json` is templated with `notify: restart docker` whose handler restarts dockerd **unconditionally, with no capture guard** — that would recreate every container including live L2 capture, i.e. an unbackfillable gap. Prefer leaving rotation as-is. Never `copytruncate` a live docker log.
- **(Attended deploy)** The capture primary needs `-e converge_primary=true`. Removing a logrotate file does not itself restart anything, but that flag's blast radius does — scope the run with `--tags base` so the capture role never executes (the `always`-tagged assert still demands the flag), which is a materially smaller blast radius than a full primary converge.
- **(Recovery, decide with the deploy)** The wedge clears by itself once the live file passes the stranded offset; nothing needs restarting, and restarting the capture container to hurry it is **not** worth an unbackfillable gap. Be clear about what recovery means: the lines written into the dark window are **skipped, not replayed** — the reader resumes at the offset, so that window survives only in the on-host json.log and never reaches Loki. Confirm by outcome that shipping resumed (`docker logs` returns promptly; the `Capture · log pipeline dead` rules go Normal), and do not read that as the window having been recovered.
- **(Check with it)** Whether the other long-lived containers are wedged the same way — the engine on the primary, and on ops the Alloy container and the liquidations poller (both `restart: unless-stopped`, both under the same glob). The ops Alloy was recreated 2026-07-21 20:21 UTC, so its reader is currently fresh.
