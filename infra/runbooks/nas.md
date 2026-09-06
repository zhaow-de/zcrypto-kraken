# NAS — the durable archive and its pull loop

Every signal here comes from one Synology DSM box (`ssh nas`) running two containers: `zcrypto-archive-pull`, whose in-container loop (`infra/nas/pull-entrypoint.sh`) pulls and hash-verifies the capture mirrors, the engine journal, and the ops-node trees into `/volume1/ZhaoCrypto` once per `ARCHIVE_PULL_INTERVAL` (3600 s) plus work, and `grafana-alloy`, which ships the host metrics and both containers' journald lines. `docker` on this host is `/usr/local/bin/docker`, needs `sudo`, and is **not** on a non-interactive ssh `PATH` — called bare, `docker ps` prints nothing and reads as "no containers" rather than "command not found". The mirror is the only backup of unbackfillable L2: no procedure here deletes archive data.

______________________________________________________________________

<a name="zcrypto-nas-disk-low"></a>

## zcrypto-nas-disk-low — ALERT

### What you are seeing

A warning Grafana alert (`NAS · /volume1 free space low`, panel `zcrypto-fleet`/301): `node_filesystem_avail_bytes{mountpoint="/volume1"} / node_filesystem_size_bytes{mountpoint="/volume1"}` has been below `0.1` for 5 minutes.

The rule carries no `host=` matcher; it relies on only the NAS presenting a `/volume1` mountpoint. Read the `host` label on the page: anything other than `nas` means a second box has mounted a `/volume1` and the rule needs scoping.

With **no value** on the page the series itself is gone — `noDataState` is `Alerting`, so read `Fleet · Alloy dark — NAS` first; that rule fires on the same fault and this one carries nothing.

### What it means

`/volume1` is the whole box: the archive (`/volume1/ZhaoCrypto` — `capture-segments/`, `capture-segments-red/`, `capture-reconciled/`, `engine-journal/`, `liquidations/`, `l2-panel/`, `hot/`), the docker stack and its textfiles (`/volume1/docker/zcrypto-archive`), Alloy's storage dir, and DSM's own docker image root `/volume1/@docker`.

Nothing has failed yet and the loop keeps pulling. When the volume actually fills, three things break at once: `zcrypto archive pull`'s rsyncs fail (loud — `NAS · archive-pull ERROR logs`), `zcrypto engine gate-export` cannot write `gate.prom` (`Gate · exporter stale`), and the gate's scoring-cache save degrades quietly rather than loudly.

The tree only grows by design: the pulls run `rsync -a` with **no** `--delete`, so the mirror never sheds what a source host has pruned. "Delete old data" is never the answer on this host.

### What to do

1. **Measure before touching anything.**
   ```
   ssh nas
   df -h /volume1
   sudo du -sh /volume1/ZhaoCrypto/* /volume1/docker/* 2>/dev/null | sort -h
   sudo du -sh /volume1/@docker
   ```
2. **Reclaim images, and only images.** Every converge pulls another ~3.25 GB capture image and nothing on this host ever removes one. From the workstation, dry-run first:
   ```
   uv run python infra/scripts/prune-host-images.py nas
   uv run python infra/scripts/prune-host-images.py nas --apply
   ```
   The keep-set is every `docs/reference/fleet-pins.md` row naming `nas` plus whatever digest the running container uses, so **the pins row must already be true of this host** — run it right after that row is updated, never before, which is what the script's own `--help` says and what it cannot check for you. A Phase-4 rollback re-trues no pins row (`.claude/rules/fleet-deploys.md`), so a stale row is a state the fleet actually reaches.
   **Never `docker system prune` or `docker image prune -a` by hand**: both take the recorded rollback operands with them.
3. **Never delete under `/volume1/ZhaoCrypto`.** `capture-segments*/` and `capture-reconciled/` are unbackfillable L2; `liquidations/` is sole-custody of a non-backfillable feed; `l2-panel/` and `hot/` are the ops node's copies of work you would have to recompute. The `engine-journal/` mirror is a replica of an authoritative copy on the engine host, but the gate exporter scores the whole mirror, so trimming it moves `zcrypto_gate_mismatch_total`'s baseline — not a page-time action.
4. **If images are already pruned and the fraction is still under 0.1, this is a capacity decision, not an ops fix.** Report the `du` breakdown and the growth rate; adding or resizing storage on DSM is attended and outside the repo.
5. **Confirm by value**, never by "it looked better": `uv run python infra/scripts/grafana-query.py 'node_filesystem_avail_bytes{mountpoint="/volume1"} / node_filesystem_size_bytes{mountpoint="/volume1"}'` reads above `0.1`. `(no series)` is a FAIL, not a zero — it means the read never happened.

### Retire when

`zcrypto-nas-disk-low` is absent from `infra/grafana/alerts.yaml`, or `node_filesystem_avail_bytes` / `node_filesystem_size_bytes` are no longer in the keep-regex in `infra/nas/config.alloy`.

______________________________________________________________________

<a name="zcrypto-nas-load-high"></a>

## zcrypto-nas-load-high — ALERT

### What you are seeing

A warning Grafana alert (`NAS · load high`, panel `zcrypto-fleet`/201): `node_load1{host="nas"}` has been above `4` for 5 minutes — the box is a 4-core Atom, so the threshold is one runnable process per core.

With no value on the page, read `Fleet · Alloy dark — NAS` first (`noDataState` is `Alerting` here too).

### What it means

**The load number is not the thing to act on. The `pull complete` cadence is.** A single-threaded loop on an Atom pins a core by design, and the only question that matters is whether the loop still finishes a full pass and keeps saying so.

The loop's steps, in the order `infra/nas/pull-entrypoint.sh` runs them, each best-effort and each logging its own failure without exiting the loop:

1. capture pull from the primary (hash-verified) — the heavy one;
2. capture pull from the secondary, when `CAPTURE_RED_SOURCE` is set (hash-verified);
3. the `.pull-status` write into `/archive` — the ops overlay writer's fail-closed gate;
4. the engine-journal pull (`--no-verify`) followed by `zcrypto engine gate-export` — the other heavy one;
5. the liquidations, panel and reconciled pulls from the ops node (all hash-verified);
6. the `hot` rsync from the ops node (raw `rsync`, not the wrapper — it emits no `pull complete` line);
7. `sleep ${ARCHIVE_PULL_INTERVAL:-3600}`.

The deployed hash scope is **`incremental`** (`nas_archive_pull_hash_scope` in `infra/ansible/host_vars/nas/vars.yml`): each pull hashes what rsync transferred plus a rotating 1/24 slice, so every segment is still re-hashed about daily. `full` re-hashes every segment every cycle and costs proportionally more.

The loop's real period is interval **plus** work, so periodic saturation inside a cycle is the design, not a fault.

One cause is always worth ruling out: a converge or restart that **recreated** the container discards the gate exporter's `/tmp/gate-cache.json` and buys one cold full-journal replay — roughly an hour of near-saturation with nothing wrong, and growing with the journal (`docs/reference/fleet-pins.md` carries the measured rate).

DSM's own jobs — a RAID scrub, media indexing, snapshot replication — share this CPU and nothing in the repo schedules or controls them.

### What to do

1. **Ask the only question that matters — is the loop still completing?**
   ```
   ssh nas
   sudo /usr/local/bin/docker logs --since 6h zcrypto-archive-pull | grep -E 'pull complete|gate-export'
   ```
   Use a **duration** (`--since 6h`), never a bare `HH:MM`: `docker logs --since` takes a duration or a full timestamp, and a bare clock time fails to parse into empty output that reads as a clean bill. Print the line count before trusting a negative result. Healthy: one `pull complete … failed=0` per verified channel per pass, passes spaced roughly `ARCHIVE_PULL_INTERVAL` + work apart. If those keep landing, high load is the loop working and there is nothing to fix.
2. **Read the cost by value**, from the workstation:
   ```
   uv run python infra/scripts/grafana-query.py 'zcrypto_archive_pull_verify_seconds' 'zcrypto_gate_export_duration_seconds' 'zcrypto_gate_journal_pull_lag_seconds'
   ```
   `zcrypto_archive_pull_verify_seconds` is labelled per `channel`, so it names which pull grew. A pull-lag figure climbing past one engine cycle is the loop falling behind; a flat one is not.
3. **Identify who is busy** on the host: `uptime`, then `top -b -n1 | head -25`. A `python`/`zcrypto` process inside the pull container is the loop; DSM daemons and md/RAID threads are DSM's. Read CPU from the host, not from `docker stats` — DSM's kernel mounts no CPU cgroup at all (`infra/nas/README.md`, *Resource budget*), which is also why this stack sets memory limits and no CPU limits.
4. **Do not restart the container to shed load.** A recreate costs the cold gate replay above — it raises load for the next hour rather than lowering it.
5. **If the loop genuinely cannot keep up**, the knob is `nas_archive_pull_hash_scope` and it is a config converge (`./scripts/converge.sh site.yml --limit nas --tags nas -e nas_apply_compose=true` — the documented path, and the only one that previews, takes a typed confirm and appends the `deploy-log.jsonl` line) — an **attended** action, on the user's word, through the rollout skill's mechanics; the flag is what actually restarts anything, and without it the role is render-only and still reports success.
6. **If DSM is the cause**, let its job finish; nothing in the repo starts or stops it.
7. **Confirm by outcome, not by the gauge**: the next pass logs `pull complete … failed=0` for every verified channel and `zcrypto_gate_journal_pull_lag_seconds` stays under one engine cycle.

### Retire when

`zcrypto-nas-load-high` is absent from `infra/grafana/alerts.yaml`, or `node_load1` leaves the keep-regex in `infra/nas/config.alloy`. The `gt 4` bar belongs to a 4-core host: it retires with that hardware.

______________________________________________________________________

<a name="zcrypto-nas-archive-pull-errors"></a>

## zcrypto-nas-archive-pull-errors — ALERT

### What you are seeing

A warning Grafana alert on the **logs** receiver (`NAS · archive-pull ERROR logs`, panel `zcrypto-logs`/102): at least one line labelled `level="ERROR"` or `"CRITICAL"` from `{container="archive-pull"}` in the last 15 minutes.

The rule selects on the `level` **label** Alloy attaches at ingest, not on the text "ERROR" — Alloy strips the level out of the message, so a text grep would match nothing. The `container` label value is `archive-pull`: `infra/nas/config.alloy` relabels the journald container name `zcrypto-archive-pull` to it deliberately, so the selector is correct as written.

It is a log alert: no resolve message, and it ages out 15 minutes after the last matching line.

### What it means

One step of the loop failed and the loop continued; the message names the step.

| line | producer | what it means |
| -- | -- | -- |
| `archive pull: rsync failed source=… dest=… returncode=N` | `pull` in `cli/archive/command.py` | transport to that source — 255 = ssh itself; 23 = partial transfer (an unreadable file at the source); 12 = protocol/disk |
| `archive pull: verify failed path=…` | same | a pulled segment's bytes did not match its `.sha256` sidecar; the wrapper's own ERROR follows |
| `archive pull: publishing the verify cost failed path=…` | same | the channel's `.prom` under `/textfile` could not be written, so its `zcrypto_archive_pull_*` freeze at their last values; the verdict is unaffected |
| `archive pull: ARCHIVE_SSH_KEY is not set; cannot establish the ssh transport` | same | the channel's key variable arrived empty — a fault in the rendered `.env`, not a host-key problem |
| `capture pull failed` / `secondary capture pull failed` / `journal pull failed` / `liquidations pull failed` / `panel pull failed` / `reconciled pull failed` / `hot pull failed` / `gate-export failed` / `pull-status write failed`, each `(source=… dest=…), continuing` | `infra/nas/pull-entrypoint.sh` | the wrapper's record of the failed step — and the **only** one when the process was killed (OOM, signal) before it could log for itself |
| `could not write gate textfile …` | `gate_export` in `cli/engine/command.py` | the textfile dir is unwritable or the volume is full; `Gate · exporter stale` follows if it persists |

`reconciled channel unwired …` is a WARNING, so an unwired overlay channel pages nothing while custody stops re-acquiring it. The `hot` channel's ERROR line is its only record — raw `rsync` emits no `pull complete`, so the dead-man never watches it.

A single `verify failed` is not itself a finding: a pull whose copies of the final and its `.sha256` straddled a source-side rebuild of that hour mismatches once, and the next pass re-transfers and re-verifies it. A repeat on the same path, or any failure on a **capture** channel, means the unbackfillable mirror is not advancing.

### What to do

1. **Read the lines with context.**
   ```
   ssh nas
   sudo /usr/local/bin/docker logs --since 2h zcrypto-archive-pull | grep -B3 -A3 -E 'ERROR|CRITICAL'
   ```
   A duration, never a bare clock time. An empty result after a firing alert is a parse or scoping error on your part, not an all-clear.
2. **`rsync failed`** → name the channel from `source=`. The capture and journal channels reach the VPS on port 10022; the liquidations, panel, reconciled and hot channels reach the ops node on port 22. Each has its own least-privilege key under `/volume1/docker/zcrypto-archive/keys/`, and host-key checking is strict (`StrictHostKeyChecking=yes`, pinned `keys/known_hosts`), so a rebuilt or reinstalled source host fails the pull closed until that file is re-seeded — DSM ships no `ssh-keyscan`, so run `ssh-keyscan -p <port> <host>` from a machine that has one and copy the output in (`infra/nas/README.md`, bootstrap step 4). A permission failure on the far side instead means that host's `rrsync` forced-command entry lost the NAS's public key — a converge of that host's role, not a NAS fix.
3. **`verify failed` on the same path a second time** (under `incremental` the repeat comes about a day later, when its 1/24 slice rotates round — not on the next pass) → decide which copy is wrong before deleting anything. The mirror copy can be re-fetched **only while the source still holds that hour**: capture hosts prune their local segments at 14 days (`capture_retention_days`, `zcrypto-capture-prune` at 03:17). Confirm the source first —
   ```
   ssh zcrypto sudo ls -l /var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/
   ```
   (`ssh red` for the secondary's tree) — and only then delete the failing file under `/volume1/ZhaoCrypto/capture-segments…` so the next pass re-fetches it. This deletion is necessary because `rsync -a` skips on matching size and mtime: a file corrupted in place is never re-transferred on its own. If the source no longer holds the hour, **do not delete the mirror copy** — it is the only copy left, corrupt or not; treat it as a reconcile question (`infra/runbooks/ops.md`).
4. **A Python traceback at ERROR** is a defect, not a transient. Capture it, check `docs/reference/fleet-pins.md` for a NAS re-pin in the window, and hand it back — rolling a pin is an attended action through the rollout skill.
5. **Verify the next pass is clean**, one pull period later: `sudo /usr/local/bin/docker logs --since 2h zcrypto-archive-pull | grep 'pull complete'` shows `failed=0` for every verified channel. Count the lines you got before calling it clean.

### Retire when

`zcrypto-nas-archive-pull-errors` is absent from `infra/grafana/alerts.yaml`, or `infra/nas/config.alloy` no longer attaches a `level` label to the `archive-pull` stream (the rule matches on that label alone).

______________________________________________________________________

<a name="zcrypto-nas-archive-pull-stalled"></a>

## zcrypto-nas-archive-pull-stalled — ALERT

### What you are seeing

A critical Grafana alert on the **metrics** receiver (`NAS · archive-pull stalled (dead-man)`, panel `zcrypto-logs`/103): Loki holds no line matching `pull complete` **and** `failed=0` from `{container="archive-pull"}` in the last 3 hours.

The value is `0`, and the `host` label on the page is **empty** — the firing arm is the rule's `or on() vector(0)` fallback, which carries no labels. The host is the NAS; the summary names it in words for this reason.

This is not `Ops · archive-pull stalled (dead-man)`. That one watches the **ops node's** overlay-writer cycle through a Prometheus gauge and has nothing to do with this loop; the two titles are one word apart on a phone.

### What it means

The loop has stopped saying it succeeded. Silence, not failure — the sibling ERROR rule stays green when the container is gone, which is exactly when nothing is protecting the archive.

`failed=0` is load-bearing in the selector. The journal pull logs `archive pull complete (no verify) …` with no `failed=` field, and a capture pull whose verification failed logs `pull complete … failed=N` **before** raising — so a bare `pull complete` match would sit quiet through both.

Known and accepted: **any** verified channel keeps this dead-man green. The liquidations, panel and reconciled pulls all emit the identical clean line, so both capture channels can be broken while this rule reads healthy — capture-specific failure is deliberately delegated to the warning-severity ERROR rule.

Downstream, if the stall persists: the `.pull-status` file this loop writes ages out at 4 h, after which the ops node's overlay writer fail-closed skips its whole cycle — reconcile and trade-backfill both stop, surfacing as `Reconciler · exporter stale`. Data loss is a slower clock: capture hosts hold their own segments for 14 days, so a stall becomes permanent loss only if it outlives that.

### What to do

1. **Separate host-down from telemetry-dark from loop-dead — from the workstation, before you ssh anywhere.**
   ```
   uv run python infra/scripts/grafana-query.py 'count(up{host="nas"})' 'node_load1{host="nas"}' 'time() - zcrypto_gate_export_timestamp_seconds'
   ```
   - `(no series)` / no `up` → the NAS or its Alloy is dark. `Fleet · Alloy dark — NAS` should be firing too; the loop may be perfectly fine and simply unobserved. Go to step 2, then step 5.
   - `up` present, gate-export age climbing past ~2 h → the host and Alloy are alive and the **loop** is what stopped. Go to step 3.
   - `up` present and gate-export age fresh → the loop is running and only its **log lines** are missing. Go to step 5.
     `(no series)` is a FAIL of the read, never a zero: it does not distinguish "dark" from "the query never ran" until you have seen at least one of these three return a value.
2. **Reach the host.** `ssh nas`. If that fails, try `ssh hp` — the ops node is on the same home LAN, so its reachability separates "the NAS is down" from "the LAN or the relay is down" (access paths: `docs/reference/fleet.md`).
3. **Read the loop's state**, scoped — never an unscoped `docker inspect` on any host in this fleet:
   ```
   sudo /usr/local/bin/docker ps -a --format '{{.Names}} {{.Status}}'
   sudo /usr/local/bin/docker inspect --format '{{.State.Status}} restarts={{.RestartCount}}' zcrypto-archive-pull
   sudo /usr/local/bin/docker logs --since 6h zcrypto-archive-pull | tail -40
   ```
   The last log line says where it stopped: an rsync with no `pull complete` after it is a hung transport (the loop has no per-step timeout); `received TERM/INT, exiting loop` means something stopped it; a completed pass followed by nothing means it is in its `sleep` and the fault is upstream in the log path.
4. **Restart the loop** when the container is gone or wedged:
   ```
   cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose up -d archive-pull
   cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose restart archive-pull
   ```
   The entrypoint traps TERM/INT, so the stop is graceful. **Know the cost**: a recreate discards `/tmp/gate-cache.json` and buys one cold gate replay, the better part of an hour and growing. A restart is a deliberate act, not a reflex; a converge or an image re-pin is attended and goes through the rollout skill on the user's word.
5. **Log path only** (loop healthy, lines missing): `sudo /usr/local/bin/docker logs --since 1h grafana-alloy | tail`, then `cd /volume1/docker/zcrypto-archive && sudo /usr/local/bin/docker compose restart alloy`. Confirm by reading `{host="nas", container="archive-pull"}` back in Loki — a non-empty result, not an absent error.
6. **Confirm by value, then by outcome.** The rule clears when one `pull complete … failed=0` lands: watch for it directly (`sudo /usr/local/bin/docker logs -f zcrypto-archive-pull`), and confirm the capture channels specifically — the dead-man would go green on any single verified channel.
7. **If the stall ran long, ask whether anything was lost.** Under 14 days, the capture hosts still hold their segments and the next passes catch the mirror up; beyond that, segments were pruned at the source and the loss is permanent. Read it from the reconcile ledger (`infra/runbooks/ops.md#zcrypto-reconcile-residual-gap`) and from `uv run python infra/scripts/continuity.py` over the **pulled** mirror. An hour is only bookable at H+2 h and at the next `:12`/`:42` tick, so a read taken too early answers *pending*, never *clean*. A ledger record a classifier wrote wrongly is corrected on the **writer host** — the ops node, never the NAS copy, which the next pull overwrites — by the procedure in `infra/nas/README.md`, *Correcting the reconcile ledger*.

### Retire when

`zcrypto-nas-archive-pull-stalled` is absent from `infra/grafana/alerts.yaml`, or the `pull` command in `cli/archive/command.py` no longer logs the `pull complete … failed=%d` line the selector matches.

______________________________________________________________________

<a name="nas-file-transfer"></a>

## NAS file transfer — PROCEDURE

### What you are seeing

Nothing fired. You are putting a file onto the NAS (`ssh nas`) — or a copy that reported success left nothing at the path you expected.

### What it means

**`scp`/`sftp` through the `nas` alias is chrooted at `/volume1`.** DSM chroots sftp to the shared folders (`infra/nas/README.md`), so a transfer path and a shell path for the same file differ by that prefix, and the wrong one fails as `No such file or directory` — which reads as a missing directory rather than as the chroot it is.

**`nas-hot:` is not a shell.** It is an ssh alias onto a forced-command `rrsync`, pinned at `/volume1/ZhaoCrypto/hot` with `-munge -no-del -no-overwrite` (`infra/ansible/roles/nas/tasks/main.yml`) — the only write channel into custody. `-no-overwrite` forces `--ignore-existing`, so re-sending a file that is already there is **skipped in silence**: an overwrite through this channel is a no-op, never an error.

### What to do

1. **Transfer without the prefix**: `scp <file> nas:/ZhaoCrypto/...`, never `nas:/volume1/ZhaoCrypto/...`. Commands you then run inside an `ssh nas` session keep it — the same file is `/volume1/ZhaoCrypto/...` there.
2. **Into `hot/`, use the sanctioned program**: `uv run zcrypto data push` from the workstation, which sends that node's authored sets to the configured `push_dest`. Never write through the NFS mount, where a soft-mounted write can corrupt on a timeout.
3. **A published file is replaced by minting a sibling, never by pushing over it** — a second push of the same name is one of the silent skips above.
4. **Confirm by listing the destination, not by the copy's exit status**: `ssh nas ls -l /volume1/ZhaoCrypto/<path>` — over the shell, so with the prefix.

### Retire when

`infra/ansible/roles/nas/tasks/main.yml` no longer installs the hot-push key with `-no-overwrite` pinned at `/volume1/ZhaoCrypto/hot`, or `nas` is no longer the DSM box whose sftp chroot `infra/nas/README.md` records — either one removes the asymmetry every step above exists for.
