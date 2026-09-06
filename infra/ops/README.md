# Ops-node stack (spec 00051, compute tier)

The home ops node (`zcrypto-ops`, `ssh hp`) is the fleet's compute tier: a home-LAN box converged by the third `site.yml` play (roles `base`/`chrony`/`docker`/`ops`/`access_ops` — no `hardening`/`firewall`/`fail2ban`, it is not internet-facing). Charter (spec 00051 D10): **no trade key, never `engine_host`, no write path toward custody** — it reads everything it consumes from the NAS over a read-only NFS mount (T0058) and is pulled *from* for everything it produces.

Installs that consume the image are gated on a pinned digest (`-e ops_image_digest=sha256:<...>`, always the **default AVX** build of `ghcr.io/zhaow-de/zcrypto-capture`, never `-compat`, never `:latest`): a converge without it skips them rather than rendering artifacts that point at a broken image reference. Everything else in the `ops` role (`infra/ansible/roles/ops/`) — the accounts, the data directories, the pull keys, the NFS mount, the grafana-watchdog units — lands on every converge.

## Users and groups (spec 00057)

The node runs on the fleet users/groups model (all Ansible-provisioned):

- **`zcrypto-deploy`** — the interactive admin: sudo, the `ansible_user`, the `ssh hp` login. Renamed from `deploy` (uid 1001 kept); its `authorized_keys` holds exactly the one operator login key (`exclusive: true`, spec 00057 D1). Never in the data path.
- **`zcrypto-data`** — the machine-to-machine data user (no sudo, no password). It runs every data container via `--user`, owns `{{ ops_data_dir }}` (default `/var/lib/zcrypto-ops`) and every tree under it, and **serves** the four NAS pull channels via `rrsync -ro` forced-command keys (role-provisioned; the committed pubs in `infra/ansible/files/sync_*_ed25519.pub`). Its shell is the rrsync-only wrapper `ops_rrsync_shell` (`/usr/local/sbin/rrsync-shell`, from `infra/ansible/files/rrsync-shell`), **not** `nologin`: sshd runs a `command="rrsync …"` forced command through the login shell, so `nologin` would swallow it — the wrapper permits only rrsync, and each key is jailed by `command=`/`restrict` to one read-only subtree.
- **`zcrypto-alloy`** — the telemetry stack's dedicated non-admin user (see the Alloy section).
- **`zhaow`** (uid 1000) — the research user; authors into `hot-out` via the shared setgid `zcrypto-hot` group (`zcrypto-data` owns + serves it, `zhaow` writes into it).

No trade key ever touches this host (D10).

## Liquidations poller (OPS-2)

The `zcrypto liquidations-poll` daemon runs as the single service in `{{ ops_compose_dir }}/compose.yaml` (default `/etc/zcrypto-ops/compose.yaml`), rendered by the role from `infra/ansible/roles/ops/templates/compose.yaml.j2`. It polls Coinalyze's `/v1/liquidation-history` REST endpoint (interval `1min`, `convert_to_usd=true`) every `COINALYZE_POLL_SECONDS` (default 300 s) for the funding basket's 10 Binance USDT perps, ingesting only buckets **proven closed** (`t+60 <= now-120`) into hourly Parquet segments + `.sha256` manifests under `<COIN>/liquidations-1m/`. It replaced the Binance `forceOrder` WS recorder (`zcrypto liquidations`, shelved in place — Binance geo-fences its futures streams from every egress we own; see [T0023]). Liquidations are **not backfillable** beyond Coinalyze's ~25–33 h retention, so the tree replicates to the NAS (D10 no-sole-custody — the channel below) and the daemon is **never auto-(re)started by a converge**: the role only renders the file; starting is a deliberate attended step.

### Deploy

1. Converge with the digest: `./scripts/run.sh site.yml --limit zcrypto-ops -e ops_image_digest=sha256:<...>` (from `infra/ansible/`; read the **default AVX** digest from the capture-image workflow's job summary, and confirm `zcrypto liquidations-poll --help` exists in that image before pinning).
2. Secrets, both vaulted in `host_vars/zcrypto-ops/vault.yml` and wired via `vars.yml`: `coinalyze_api_key` (free key from coinalyze.net → account → API key) and `liquidations_healthcheck_url` (a healthchecks.io check, e.g. `zcrypto-liquidations`; the dead-man alerts by **missed** pings, so an attached notification channel is what pages). The rendered compose is mode `0600` because it carries the API key.
3. Start it (attended): `ssh hp`, then `docker compose -f /etc/zcrypto-ops/compose.yaml up -d`.
4. Verify by outcome within a minute: the first cycle back-fills the ~30 h catch-up window, so hour finals appear immediately at `/var/lib/zcrypto-ops/liquidations/<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet` with valid `.sha256` sidecars, for all 10 coins. The dead-man pings after each fully-successful cycle. Sparse hours (no liquidation for a coin) simply have no bucket; the open hour lingers as `.part` files until a later bucket closes it ([T0046]).

### Env contract (rendered into `compose.yaml`)

| Variable | Meaning | Set where |
| -- | -- | -- |
| `COINALYZE_API_KEY` | The Coinalyze API credential (required; header-only, never in URLs or logs). | vaulted `coinalyze_api_key` → rendered into the `0600` compose |
| `ZCRYPTO_LIQUIDATIONS_DATA_DIR` | Segment output base in the container: `/data/liquidations`. | fixed in `compose.yaml.j2`, matching its `{{ ops_data_dir }}:/data` mount |
| `LIQUIDATIONS_HEALTHCHECK_URL` | Dead-man ping URL; pinged on a clean cycle, disk watermark healthy. Empty skips it. | `ops_liquidations_healthcheck_url` ← vaulted `liquidations_healthcheck_url` |
| `COINALYZE_POLL_SECONDS` | Poll cadence: one batched 10-symbol call per cycle. | unset in the rendered compose — the 300 s default is `DEFAULT_POLL_SECONDS` in `cli/liquidations/coinalyze.py` |
| `ZCRYPTO_METRICS_PORT` | The poller's `/metrics` port, `9103`, published on host loopback only. | fixed in `compose.yaml.j2`, scraped by `files/config.alloy`'s `liquidations_app` job |
| `ZCRYPTO_LOG_HOST` | Direct-ship label: the literal `ops`. | fixed in `compose.yaml.j2`, guarded by `logship_loki_token is defined` |
| `ZCRYPTO_LOG_SERVICE` | Direct-ship label: the literal `liquidations`. | fixed in `compose.yaml.j2`, same guard |

The service runs digest-pinned (`{{ ops_image }}@{{ ops_image_digest }}`) as the `zcrypto-data` uid:gid, `restart: unless-stopped`. **Two log paths, not one** (spec 00068 D3/D5): `json-file` logging capped 10m×3 keeps the container's stdout on the host, and when `logship_loki_token` is vaulted the exec-form entrypoint bakes in `--ship-logs` so the poller **direct-ships** its own lines to Grafana Cloud Loki, reading its creds from the role-rendered `{{ ops_compose_dir }}/logship-secrets.env` (owner `zcrypto-deploy`, mode `0600`; `env_file` long-form `required: false`, so a missing file never blocks `docker compose up`). The shelved WS recorder shares the same data dir and `single_instance_lock`, so the two can never run concurrently.

### The `sync_liquidations` replication channel (the NAS pulls this node)

Pull-only transport, mirroring the capture channels (`infra/nas/README.md`): the NAS pulls the liquidations tree hash-verified (the recorder writes `.sha256` manifests — never `--no-verify`), over a **dedicated** read-only rrsync forced-command keypair. One difference from the VPS channels: the ops node is a home-LAN box on SSH **port 22** (not 10022), so the NAS side scopes `LIQUIDATIONS_SSH_PORT` per call.

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_liquidations_ed25519 -C zcrypto-sync-liquidations-pullonly -N ""`.
2. **Ops node** — the ops role installs the public half (committed in `infra/ansible/files/`) as a forced-command entry in `zcrypto-data`'s `~/.ssh/authorized_keys` (rrsync lives at `/usr/bin/rrsync` on Debian 13; the role installs `rsync`):

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/liquidations",restrict ssh-ed25519 AAAA... zcrypto-sync-liquidations-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_liquidations`, mode `0600` (matches the fixed `LIQUIDATIONS_SSH_KEY=/keys/sync_liquidations` in `infra/nas/compose.yaml`).
4. **NAS** — pin the ops host key: from a machine with `ssh-keyscan`, run `ssh-keyscan -p 22 <ops-host>` and **append** its output to `/volume1/docker/zcrypto-archive/keys/known_hosts` (the shared pinned file; host-key checking is strict). Verify the key against the ops node's own `/etc/ssh/ssh_host_ed25519_key.pub` — never trust-on-first-use.
5. **NAS** — set `LIQUIDATIONS_SOURCE=zcrypto-data@<ops-host>:` in the `.env` next to `compose.yaml` (the rrsync forced command pins the actual remote subtree) and `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely. The pull is deliberately **not** an input to the NAS reconcile gate — the reconciler reasons only about the two capture mirrors.

## Replay timers (OPS-3)

Two daily systemd timers run the `zcrypto` CLI in the digest-pinned image (`docker run --rm --entrypoint zcrypto <image>@<digest> ...`, as the `zcrypto-data` uid/gid, with the NAS NFS export mounted read-only at `/nas` and — where the local overlay is an input — `ops_data_dir` read-only at `/data`; T0058). The sweep's checkpoint (`ops_verify_replay_state_subdir`) is the one writable mount either gets, at `/state`:

| Unit | Schedule (UTC) | What it runs |
| -- | -- | -- |
| `zcrypto-verify-replay.timer` | daily 03:41 | `zcrypto archive verify-replay /nas/capture-segments /data/capture-reconciled --state-dir /state` — replays the canonical archive through `OrderBook`. |
| `zcrypto-verified-replay.timer` | daily 05:23 | `zcrypto engine replay --path verified --date <day> --journal-dir /nas/engine-journal` — the oracle-builder replay, looped from a watermark. |

Both slots are off the hour boundary and clear of the ops reboot window (02:25 UTC) and the capture hosts' maintenance windows (21:25/22:25 UTC). `Persistent=true`: a host that was down at the slot runs on the next boot instead of skipping the day.

### Textfile metrics

Each run atomically rewrites its node-exporter textfile in `ops_textfile_dir` (default `/var/lib/zcrypto-ops/textfile`): `ops-verify-replay.prom` / `ops-verified-replay.prom`, carrying (per family, prefixes `ops_verify_replay_` / `ops_verified_replay_`):

| Metric | Meaning |
| -- | -- |
| `<prefix>exit_code` | Exit code of the last run (`0` = clean; non-zero is the CLI's own failure verdict). |
| `<prefix>last_run_timestamp` | Unix time of the last run, clean or not. |
| `<prefix>last_success_timestamp` | Unix time of the last **clean** run (`0` = never). A failed run carries the previous value forward, so "time since last clean replay" stays directly alertable. |
| `ops_verified_replay_days_behind` | Days between the replay watermark and yesterday (`0` = fully caught up). Verified-replay family only. |
| `ops_verify_replay_failed_hours` | Count of hours that failed the last sweep that produced a summary. Verify-replay family only (spec 00077 D2); carried forward when a run breaks before reporting. |
| `ops_verify_replay_hours_total` | Count of canonical hours in the last sweep that produced a summary. Verify-replay family only (spec 00077 D2); carried forward when a run breaks before reporting. |
| `ops_verify_replay_run_ok` | `1` iff the run produced a parseable summary — the sweep *completed*, whatever it found; `0` is a run that never got there. Verify-replay family only (spec 00077 D2). |
| `ops_verify_replay_replayed_hours` | Hours actually re-replayed by the last completed sweep. Verify-replay family only (spec 00078 D11); carried forward when a run breaks before reporting. |
| `ops_verify_replay_reused_hours` | Hours the last completed sweep served from the checkpoint instead of re-replaying. Verify-replay family only (spec 00078 D11); carried forward on a broken run. |
| `ops_verify_replay_pending_hours` | Hours awaiting re-verification after the last sweep spent its drain budget. Verify-replay family only (spec 00078 D11/D12); carried forward on a broken run. |
| `ops_verify_replay_duration_seconds` | Wall-clock seconds the last completed sweep took. Verify-replay family only (spec 00078 D11); carried forward when a run breaks before reporting. |
| `ops_verify_replay_audit_mismatches` | Checkpoint hours that disagreed with a fresh replay in the last sweep that reported a census (`0` = none). Verify-replay family only (spec 00078 D6). **The one series NOT gated on `run_ok`** — a disagreement withholds the summary, so gating it would carry a stale `0` over the only condition it traces; carried forward only when no census was emitted. |


### Dead-man pings

`verified-replay` GETs its healthchecks.io ping URL when the run is clean (exit 0) **and** fully caught up (`days_behind <= 0`) — a clean-but-behind run pings nothing; a stalled catch-up must trip the dead man, not feed it. `verify-replay` differs (spec 00077 D5): it pings whenever the sweep *ran* and produced a summary (`run_ok == 1`), not on exit code — once any bad hour exists, `rc` stays 1 forever, so gating on `rc` would withhold the ping (and page through healthchecks.io) forever; a sweep that completed and reported bad hours still ran. Both read role vars `ops_verify_replay_healthcheck_url` / `ops_verified_replay_healthcheck_url`, defaulting to empty, which **skips** the ping entirely (the CLI's optional `ping_healthcheck` semantics, shell edition). A run that fails its own gate (`verified-replay`: non-zero exit or still behind; `verify-replay`: `run_ok == 0`) pings nothing and alerts by silence.

## Overlay writer + panel (OPS-4/OPS-5, specs 00052/00054; re-plumbed by T0058)


The canonical trees (`capture-segments`, `capture-segments-red`, `engine-journal`) are read over the NAS's read-only NFS export of `/volume1/ZhaoCrypto`: the role writes the fstab entry (`ops_nas_mount`, default `/mnt/zhao-crypto`; `ro,nfsvers=3,nolock,soft,timeo=100,retrans=3,noatime,nosuid,nodev,noauto,x-systemd.automount,x-systemd.mount-timeout=15` — `timeo` is **deciseconds**, so 10 s) and the systemd automount owns mounting. The export's server side is a hand-made DSM rule — a `ZhaoCrypto` NFS permission for the ops node's IP with privilege **Read-Only**, recorded in `infra/external-systems.md` (NAS → Initial setup): that server-side Read-Only is the server half of the D10 no-write-toward-custody boundary, so the boundary never rests on the client `ro` flag alone. `zcrypto-archive-pull` keeps its unit and metric names for the provisioned alerts' sake, but it is the **overlay-writer cycle**: it pulls nothing.


| Unit | Schedule (UTC) | What it runs |
| -- | -- | -- |
| `zcrypto-archive-pull.timer` | half-hourly, :12 and :42 | The overlay-writer cycle, digest-pinned image, NFS mount at `/nas:ro`: `zcrypto archive reconcile /nas/capture-segments /nas/capture-segments-red /data/capture-reconciled` (`--mint` or `--detect-only`, from `ops_reconcile_mint`) and the daily `zcrypto archive backfill-trades /nas/capture-segments /data/capture-reconciled`. A fail-closed gate on the NAS-written `{{ ops_nas_mount }}/.pull-status` skips both — WARNING, exit 0 — unless that file attests a fresh, clean capture pull. |
| `zcrypto-panel-materialize.timer` | hourly, :22 | `zcrypto panel materialize /nas/capture-segments /data/capture-reconciled --panel-root /data/l2-panel`, same mount — watermarked per pair. |

The writer's `:42` slot **knowingly overlaps** the 03:41 `zcrypto-verify-replay` run once a day — accepted: both are read-only NFS readers, contention only slows them, and a soft-mount EIO fails loudly (rc != 0), never silently. `Persistent=true` on both: a host down at its slot catches up on the next boot, and the panel timer's watermark makes a caught-up run idempotent.

### Textfile metrics

Same shape as the replay timers' (`ops-archive-pull.prom` / `ops-panel-materialize.prom`, prefixes
`ops_archive_pull_` / `ops_panel_`): `<prefix>exit_code`, `<prefix>last_run_timestamp`,
`<prefix>last_success_timestamp` (a failed run carries the previous success forward, same
rationale as the replay timers above). No extra `hours_written`-style gauge is parsed out of
`panel materialize`'s summary log line — the replay scripts don't parse container stdout for
extra metrics either, and this stays consistent with that rather than inventing a new pattern for
one unit.

### Dead-man pings

Same optional-ping semantics as the replay timers for the panel: role var
`ops_panel_healthcheck_url`, defaulting to empty (skips the ping entirely). The overlay-writer
cycle pings `ops_archive_pull_healthcheck_url` on rc 0, gate-skips included, so that dead-man
measures the cycle's own liveness rather than the upstream's; its other failure paths are the
`ops_archive_pull_exit_code` alert plus the reconcile/trade-backfill staleness alerts.

### The `sync_panel` replication channel (the NAS pulls this node)

Pull-only transport, mirroring `sync_liquidations` above — convenience-durability only (spec 00052
D7): the panel is recomputable from raw (`f(raw)`, spec 00052), so this copy is **not**
custody-critical.

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_panel_ed25519 -C zcrypto-sync-panel-pullonly -N ""`.
2. **Ops node** — the ops role installs the public half (committed in `infra/ansible/files/`) as a forced-command entry in `zcrypto-data`'s `~/.ssh/authorized_keys`, pinning the panel root:

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/l2-panel",restrict ssh-ed25519 AAAA... zcrypto-sync-panel-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_panel`, mode
   `0600` (matches the fixed `PANEL_SSH_KEY=/keys/sync_panel` in `infra/nas/compose.yaml`).
4. **NAS** — the ops host key is already pinned in the shared `known_hosts` file from the
   `sync_liquidations` setup above (step 4 there); no re-pin needed for a second channel to the
   same host.
5. **NAS** — set `PANEL_SOURCE=zcrypto-data@<ops-host>:` in the `.env` next to `compose.yaml` and
   `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely.

### The `sync_reconciled` replication channel (the NAS pulls this node)

Pull-only transport, mirroring `sync_panel`/`sync_liquidations` above -- spec 00054 D4: the overlay
writer (reconciler + trade-backfill) moved to this node, so the NAS acquires the healed overlay
instead of writing it. Custody stays on the NAS (D3); only the computation moved. Hash-verified,
like the panel/liquidations channels (every minted hour carries a `.sha256` sidecar).

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_reconciled_ed25519 -C zcrypto-sync-reconciled-pullonly -N ""`.
2. **Ops node** — the ops role installs the public half (committed in `infra/ansible/files/`) as a forced-command entry in `zcrypto-data`'s `~/.ssh/authorized_keys`, pinning the overlay root:

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/capture-reconciled",restrict ssh-ed25519 AAAA... zcrypto-sync-reconciled-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_reconciled`, mode
   `0600` (matches the fixed `RECONCILED_SSH_KEY=/keys/sync_reconciled` in `infra/nas/compose.yaml`).
4. **NAS** — the ops host key is already pinned in the shared `known_hosts` file from the
   `sync_liquidations` setup above (step 4 there); no re-pin needed for a third channel to the
   same host.
5. **NAS** — set `RECONCILED_SOURCE=zcrypto-data@<ops-host>:` in the `.env` next to `compose.yaml` and
   `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely.

### The `sync_hot` replication channel (the NAS pulls this node)

Pull-only transport, mirroring `sync_reconciled`/`sync_panel` above -- spec 00056 D2/D4: the hot-out
outbox this node stages (the hot-cluster working set it authors) is pulled into the NAS `hot/` hub.
A **new dedicated 4th D9 channel**: the three existing `rrsync -ro` roots are each exact-subtree
pinned, so none is a parent of `hot-out` -- it MUST get its own least-privilege key, not a widened
root. Two differences from the reconciled/panel channels: the NAS pulls it with a **raw
`rsync --archive --ignore-existing`** (not `zcrypto archive pull`), because hot sets are
append-only-at-file (D1c) and carry `manifest.json`, not the `.sha256` sidecars `verify_tree`
expects -- so the pull is unverified-at-transport and append-only-by-construction (a content-changed
file is simply untransmittable).

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_hot_ed25519 -C zcrypto-sync-hot-pullonly -N ""`.
2. **Ops node** — the ops role installs the public half (committed in `infra/ansible/files/`) as a forced-command entry in `zcrypto-data`'s `~/.ssh/authorized_keys`, pinning the outbox root:

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/hot-out",restrict ssh-ed25519 AAAA... zcrypto-sync-hot-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_hot`, mode
   `0600` (matches the fixed `HOT_SSH_KEY=/keys/sync_hot` in `infra/nas/compose.yaml`).
4. **NAS** — the ops host key is already pinned in the shared `known_hosts` file from the
   `sync_liquidations` setup above (step 4 there); no re-pin needed for a fourth channel to the
   same host.
5. **NAS** — set `HOT_SOURCE=zcrypto-data@<ops-host>:` in the `.env` next to `compose.yaml` and
   `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely.

## Alloy telemetry stack (Task 1, spec 00054 D1/D7)

Grafana Alloy runs as its own compose project at `{{ ops_alloy_dir }}` (default `/etc/zcrypto-ops/alloy`), rendered by the `ops` role only when the pinned Alloy digest is supplied (`-e ops_alloy_digest=sha256:<...>`; no default, matching `ops_image_digest`'s pattern). It ships host metrics (load, memory, free disk space, network IO), the ops timers' textfile series, and its own logs plus those units' logs to Grafana Cloud, mirroring `infra/nas/config.alloy`'s pipeline — see `infra/ansible/roles/ops/files/config.alloy` for the two deliberate divergences: no cadvisor, dedicated non-admin uid + rootfs mount.

Ops log streams reach Grafana Cloud two ways (00068 D3/D6): the liquidations poller **direct-ships** its own logs straight to Grafana Cloud Loki (`--ship-logs`, `cli/logging/ship.py`) — Alloy is not in that path at all, and the `container` label (`liquidations`) is set by the app itself (`ZCRYPTO_LOG_SERVICE`), never by an Alloy relabel rule. Everything else — Alloy's own logs (journald logging driver on the alloy compose service) and the ephemeral systemd-unit `docker run --rm` jobs — ships via the **host journal** to Alloy's `loki.source.journal` pipeline, labelled by unit name there. The full `container` label set across the two paths is therefore `liquidations` (direct-ship), `alloy`, `zcrypto-archive-pull`, `zcrypto-verify-replay`, `zcrypto-verified-replay`, `zcrypto-panel-materialize`, `zcrypto-tape-bars` (journal) — there is **no** `zcrypto-reconcile` or `zcrypto-trade-backfill` stream: those runs are attached children of the archive-pull unit, so their stdout lands under `container="zcrypto-archive-pull"`.

**Runs as the dedicated `zcrypto-alloy` system user, never `zcrypto-deploy` or `zcrypto-data`.** The role creates it (`nologin`, no home) and derives its uid/gid via `getent`, the same pattern used for the `zcrypto-data` container uid. This is least-privilege defense-in-depth: Alloy mounts `/:/host/root:ro` for its free-disk-space collector, so running it as a user whose `~/.ssh` held a private key would let it read that key straight through the mount, no escalation needed — the exact protection this stack replicates from the NAS (T0030). `zcrypto-alloy` owns nothing under either home, so the direct-read path stays closed by construction. The docker-socket mount and its `group_add` are gone entirely (00068 D6/T6) — Alloy's only remaining `group_add` grants read of the host's persistent journal, set to the host's real numeric **systemd-journal** gid, derived at converge time with `getent` (`infra/ansible/roles/ops/tasks/main.yml`) — **not** a named `"systemd-journal"` entry: Docker resolves a named `group_add` entry against the **container's own** `/etc/group`, not the host's, and the upstream `grafana/alloy` image ships only `alloy:x:473:` with no such entry, so a literal name would never resolve and the container would fail to start. This grants read of the whole system journal, read-only — broader than the units the pipeline keeps, but strictly telemetry-class data — and confers **no** Docker API access, so [[T0042]]'s docker-socket residual on this host **closes**: nothing here holds the API any more.

### Deploy

1. Converge with the digest: `./scripts/run.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<...>` (from `infra/ansible/`). No secrets file on this host is hand-placed: the `ops` role renders both, mode `0600` — this Alloy one, and `{{ ops_compose_dir }}/logship-secrets.env` for the liquidations poller's own direct-ship Loki creds (spec 00068 D3/T6). For Alloy: the role renders `{{ ops_alloy_dir }}/alloy-secrets.env` (default `/etc/zcrypto-ops/alloy/alloy-secrets.env`) straight from the vault, owned by `zcrypto-alloy` (the container runs as that user and must be able to read a 0600 file it does not own by default), with `no_log: true` + `diff: false` so the converge never prints the values. Its vars — the six `GRAFANA_PROM_*`/`GRAFANA_LOKI_*` credentials and `hc_prometheus_metrics_path` — live in `group_vars/observed/vault.yml`; rotate them there. `config.alloy` reads the rendered file via the River `sys.env(...)` stdlib function; `compose.yaml` itself stays secret-free (only `env_file: ./alloy-secrets.env` references the file by name).
2. Start it (attended): `ssh hp`, then `docker compose -f /etc/zcrypto-ops/alloy/compose.yaml up -d`.
3. Verify by outcome: the timers' textfile series (`ops_archive_pull_*`, `ops_panel_*`, `ops_verify_replay_*`, `ops_verified_replay_*`, `zcrypto_tapebars_*`) and host metrics appear in Grafana Cloud within a scrape interval; `tests/test_infra_alloy_series.py` pins the keep-regex against the series this stack publishes.
