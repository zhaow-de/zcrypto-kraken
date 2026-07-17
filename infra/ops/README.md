# Ops-node stack (spec 00051, compute tier)

The home ops node (`zcrypto-ops`, `ssh hp`) is the fleet's compute tier: a home-LAN box converged by the third `site.yml` play (roles `base`/`chrony`/`docker`/`ops` — no `hardening`/`firewall`/`fail2ban`, it is not internet-facing). Charter (spec 00051 D10): **no trade key, never `engine_host`, no write path toward custody** — it reads everything it consumes from the NAS (read-only NFS mount since T0058; the rsync pull loop before that) and is pulled *from* for everything it produces.

Everything below is installed by the `ops` Ansible role (`infra/ansible/roles/ops/`) **only when the pinned image digest is supplied** (`-e ops_image_digest=sha256:<...>`, always the **default AVX** build of `ghcr.io/zhaow-de/zcrypto-capture`, never `-compat`, never `:latest`); a converge without the digest skips those installs rather than rendering artifacts that point at a broken image reference.

## Liquidations poller (OPS-2)

The `zcrypto liquidations-poll` daemon runs as the single service in `{{ ops_compose_dir }}/compose.yaml` (default `/etc/zcrypto-ops/compose.yaml`), rendered by the role from `infra/ansible/roles/ops/templates/compose.yaml.j2`. It polls Coinalyze's `/v1/liquidation-history` REST endpoint (interval `1min`, `convert_to_usd=true`) every `COINALYZE_POLL_SECONDS` (default 300 s) for the funding basket's 10 Binance USDT perps, ingesting only buckets **proven closed** (`t+60 <= now-120`) into hourly Parquet segments + `.sha256` manifests under `<COIN>/liquidations-1m/`. It replaced the Binance `forceOrder` WS recorder (`zcrypto liquidations`, shelved in place — Binance geo-fences its futures streams from every egress we own; see [T0023]). Liquidations are **not backfillable** beyond Coinalyze's ~25–33 h retention, so the tree replicates to the NAS (D10 no-sole-custody — the channel below) and the daemon is **never auto-(re)started by a converge**: the role only renders the file; starting is a deliberate attended step.

### Deploy

1. Converge with the digest: `./scripts/run.sh site.yml --limit zcrypto-ops -e ops_image_digest=sha256:<...>` (from `infra/ansible/`; read the **default AVX** digest from the capture-image workflow's job summary, and confirm `zcrypto liquidations-poll --help` exists in that image before pinning).
2. Secrets, both vaulted in `host_vars/zcrypto-ops/vault.yml` and wired via `vars.yml`: `coinalyze_api_key` (free key from coinalyze.net → account → API key) and `liquidations_healthcheck_url` (a healthchecks.io check, e.g. `zcrypto-liquidations`; the dead-man alerts by **missed** pings, so an attached notification channel is what pages). The rendered compose is mode `0600` because it carries the API key.
3. Start it (attended, plan Task 5): `ssh hp`, then `docker compose -f /etc/zcrypto-ops/compose.yaml up -d`.
4. Verify by outcome within a minute: the first cycle back-fills the ~30 h catch-up window, so hour finals appear immediately at `/var/lib/zcrypto-ops/liquidations/<COIN>/liquidations-1m/<YYYY>/<MM>/<DD>/<HH>.parquet` with valid `.sha256` sidecars, for all 10 coins. The dead-man pings after each fully-successful cycle. Sparse hours (no liquidation for a coin) simply have no bucket; the open hour lingers as `.part` files until a later bucket closes it ([T0046]).

### Env contract (rendered into `compose.yaml`)

| Variable | Meaning | Set where |
| -- | -- | -- |
| `COINALYZE_API_KEY` | The Coinalyze API credential (required; header-only, never in URLs or logs). | vaulted `coinalyze_api_key` → rendered into the `0600` compose |
| `ZCRYPTO_LIQUIDATIONS_DATA_DIR` | Segment output base inside the container: `/data/liquidations` (= `{{ ops_data_dir }}/liquidations` on the host). | fixed in `compose.yaml.j2` (matches the `{{ ops_data_dir }}:/data` mount) |
| `LIQUIDATIONS_HEALTHCHECK_URL` | healthchecks.io dead-man ping URL; pinged after each fully-successful poll cycle (~300 s cadence) while disk-healthy. Empty → pings skipped. | role var `ops_liquidations_healthcheck_url` ← vaulted `liquidations_healthcheck_url` |
| `COINALYZE_POLL_SECONDS` | Poll cadence (default 300; one 10-symbol call per cycle ≈ 2 of Coinalyze's 40/min per-symbol budget). | compose default; override for testing only |

The service runs digest-pinned (`{{ ops_image }}@{{ ops_image_digest }}`), as the `deploy` uid:gid, `restart: unless-stopped`, `json-file` logging capped 10m×3. The shelved WS recorder shares the same data dir and `single_instance_lock`, so the two can never run concurrently.

### The `sync_liquidations` replication channel (the NAS pulls this node)

Pull-only transport, mirroring the capture channels (`infra/nas/README.md`): the NAS pulls the liquidations tree hash-verified (the recorder writes `.sha256` manifests — never `--no-verify`), over a **dedicated** read-only rrsync forced-command keypair. One difference from the VPS channels: the ops node is a home-LAN box on SSH **port 22** (not 10022), so the NAS side scopes `LIQUIDATIONS_SSH_PORT` per call.

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_liquidations_ed25519 -C zcrypto-sync-liquidations-pullonly -N ""`.
2. **Ops node** — install the public half as a forced-command entry in `deploy`'s `~/.ssh/authorized_keys` (rrsync lives at `/usr/bin/rrsync` on Debian 13; the role installs `rsync`):

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/liquidations",restrict ssh-ed25519 AAAA... zcrypto-sync-liquidations-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_liquidations`, mode `0600` (matches the fixed `LIQUIDATIONS_SSH_KEY=/keys/sync_liquidations` in `infra/nas/compose.yaml`).
4. **NAS** — pin the ops host key: from a machine with `ssh-keyscan`, run `ssh-keyscan -p 22 <ops-host>` and **append** its output to `/volume1/docker/zcrypto-archive/keys/known_hosts` (the shared pinned file; host-key checking is strict). Verify the key against the ops node's own `/etc/ssh/ssh_host_ed25519_key.pub` — never trust-on-first-use.
5. **NAS** — set `LIQUIDATIONS_SOURCE=deploy@<ops-host>:` in the `.env` next to `compose.yaml` (the rrsync forced command pins the actual remote subtree) and `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely. The pull is deliberately **not** an input to the NAS reconcile gate — the reconciler reasons only about the two capture mirrors.

## Replay timers (OPS-3)

Two daily systemd timers run the `zcrypto` CLI in the digest-pinned image (`docker run --rm --entrypoint zcrypto <image>@<digest> ...`, as the `deploy` uid/gid, with the NAS NFS export mounted read-only at `/nas` and — where the local overlay is an input — `ops_data_dir` read-only at `/data`; T0058):

| Unit | Schedule (UTC) | What it runs |
| -- | -- | -- |
| `zcrypto-verify-replay.timer` | daily 03:41 | `zcrypto archive verify-replay /nas/capture-segments /data/capture-reconciled` — continuity-replays the canonical archive (reconciled-first) through `OrderBook`; exits non-zero if any hour is not (chain-)anchored / ts-ordered / checksum-attested / structurally replayable. |
| `zcrypto-verified-replay.timer` | daily 05:23 | `zcrypto engine replay --path verified --journal-dir /nas/engine-journal` — the oracle-builder replay of the journal (watermark catch-up loop over every still-unverified day, T0059); exits non-zero on any mismatch or validation failure, and refuses loudly on an invalid/future watermark. A day whose journal day-dir holds no cycle artifacts — or whose **successor** day has none yet (a mid-day pull stall leaves only the early cycles; the successor day starting to arrive is the proof the pull finished this one) — stops the loop without advancing the watermark (rc 0 alone is not proof of verification — the day retries once the journal has caught up). |

Both slots are off the hour boundary and clear of the ops reboot window (02:25 UTC) and the capture hosts' maintenance windows (21:25/22:25 UTC). `Persistent=true`: a host that was down at the slot runs on the next boot instead of skipping the day.

### Textfile metrics

Each run atomically rewrites its node-exporter textfile in `ops_textfile_dir` (default `/var/lib/zcrypto-ops/textfile`): `ops-verify-replay.prom` / `ops-verified-replay.prom`, carrying (per family, prefixes `ops_verify_replay_` / `ops_verified_replay_`):

| Metric | Meaning |
| -- | -- |
| `<prefix>exit_code` | Exit code of the last run (`0` = clean; non-zero is the CLI's own failure verdict). |
| `<prefix>last_run_timestamp` | Unix time of the last run, clean or not. |
| `<prefix>last_success_timestamp` | Unix time of the last **clean** run (`0` = never). A failed run carries the previous value forward, so "time since last clean replay" stays directly alertable. |
| `ops_verified_replay_days_behind` | Days between the replay watermark and yesterday (`0` = fully caught up). Verified-replay family only — the watermark catch-up loop (T0059) is what makes "behind" a meaningful state. |

The metric families are new: per the T0034 discipline, arm Grafana alert rules only once the series are visible in the scrape (OPS-4/5 wires the ops node's scraper; do not push rules blind).

### Dead-man pings

On a clean run (exit 0) each script GETs its healthchecks.io ping URL — role vars `ops_verify_replay_healthcheck_url` / `ops_verified_replay_healthcheck_url`, both defaulting to empty, which **skips** the ping entirely (the CLI's optional `ping_healthcheck` semantics, shell edition: `[ -n "$URL" ] && curl -fsS -m 10 "$URL"`). A failed run pings nothing and alerts by silence.

## Overlay writer + panel (OPS-4/OPS-5, specs 00052/00054; re-plumbed by T0058)

Two wiring notes: (1) a digest-only converge arms `panel-materialize` before any archive is readable — its hourly runs then fail loudly (missing `PRIMARY_ROOT`) until the archive is present; that pre-wire-up noise is expected, not a bug (review M2). (2) The `sync_panel` channel setup below assumes the ops host key is already pinned in the NAS `known_hosts` by the `sync_liquidations` setup — if the panel channel is provisioned standalone, do that pinning step first (review M7).

**The NAS→ops rsync mirror is retired (T0058).** The NAS exports `/volume1/ZhaoCrypto` read-only over NFS; the role writes the fstab entry (`ops_nas_mount`, default `/mnt/zhao-crypto`; `ro,nfsvers=3,nolock,soft,timeo=100,retrans=3,noatime,nosuid,nodev,noauto,x-systemd.automount,x-systemd.mount-timeout=15` — `timeo` is **deciseconds**, so 10 s) and the systemd automount owns mounting. The export's server side is a hand-made DSM rule — a `ZhaoCrypto` NFS permission for the ops node's IP with privilege **Read-Only**, recorded in `infra/external-systems.md` (NAS → Initial setup): the export-side Read-Only is the server half of the D10 no-write-toward-custody boundary, so the boundary never rests on the client `ro` flag alone. The canonical trees (`capture-segments`, `capture-segments-red`, `engine-journal`) are read through the mount; the write-back direction is unchanged (overlay + panel return via the NAS-initiated rrsync pulls below). `zcrypto-archive-pull` keeps its unit + metric names for the provisioned alerts' sake, but it is now the **overlay-writer cycle**: it pulls nothing.

**Attended retirement step (after the NFS path is verified live):** remove the old pull channel's credentials — the `sync_nas_archive` private key + `nas_known_hosts` pin under `~deploy/.ssh` on this host, the matching forced-command entry in the NAS-side `authorized_keys`, and the now-unpinged `archive-pull` healthchecks.io check (it alerts on missed pings, so leaving it armed pages). Deliberately not automated: deleting live-looking keys is an irreversible, verify-first action.

| Unit | Schedule (UTC) | What it runs |
| -- | -- | -- |
| `zcrypto-archive-pull.timer` | half-hourly, :12 and :42 (T0058 — NFS reads cost no transfer) | The overlay-writer cycle: first the **fail-closed gate** — read `{{ ops_nas_mount }}/.pull-status` (written by the NAS right after its own VPS capture pulls, `infra/nas/pull-entrypoint.sh`) and skip the whole cycle (reconcile **and** backfill, exit 0, loud WARNING) unless `capture_ok=1`, `secondary_ok=1`, and `ts_epoch` is younger than 4 h and not more than 10 min in the future (a future stamp is clock skew, never freshness). Then `zcrypto archive reconcile /nas/capture-segments /nas/capture-segments-red /data/capture-reconciled` (detect-only until T0039) and the daily `zcrypto archive backfill-trades /nas/capture-segments /data/capture-reconciled`, both in the digest-pinned image with the NFS mount at `/nas:ro`. A persistent skip surfaces via the reconcile-staleness alert (the skipped cycle never rewrites `reconcile.prom`). |
| `zcrypto-panel-materialize.timer` | hourly, :22 | `zcrypto panel materialize /nas/capture-segments /data/capture-reconciled --panel-root /data/l2-panel` in the digest-pinned image, with the NFS mount at `/nas:ro` (T0058) — watermarked, so only canonical hours strictly newer than the panel's per-pair watermark are processed (installed inside the same `ops_image_digest is defined` guard as the replay timers). |

All slots are off the hour boundary and clear of the ops reboot window (02:25 UTC) and the capture
hosts' maintenance windows (21:25/22:25 UTC). The `:12`/`:22` slots are also clear of the daily
replay timers (03:41/05:23); the writer's T0058-added `:42` slot **knowingly overlaps** the daily
03:41 `zcrypto-verify-replay` run once a day (03:42) — accepted: both are read-only NFS readers,
contention only slows them, and a soft-mount EIO fails loudly (rc != 0), never silently.
`Persistent=true` on both: a host down at its slot catches up on the next boot instead of skipping
the hour — the panel timer's watermark makes a caught-up run idempotent regardless.

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
cycle pings **nothing** — the archive-pull dead-man died with the pull (T0058; see the attended
retirement step above for the healthchecks.io check), and the cycle's own failure paths are the
`ops_archive_pull_exit_code` alert plus the reconcile/trade-backfill staleness alerts.

### The `sync_panel` replication channel (the NAS pulls this node)

Pull-only transport, mirroring `sync_liquidations` above — convenience-durability only (spec 00052
D7): the panel is recomputable from raw (`f(raw)`, spec 00052), so this copy is **not**
custody-critical.

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_panel_ed25519 -C zcrypto-sync-panel-pullonly -N ""`.
2. **Ops node** — install the public half as a forced-command entry in `deploy`'s `~/.ssh/authorized_keys`, pinning the panel root:

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/l2-panel",restrict ssh-ed25519 AAAA... zcrypto-sync-panel-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_panel`, mode
   `0600` (matches the fixed `PANEL_SSH_KEY=/keys/sync_panel` in `infra/nas/compose.yaml`).
4. **NAS** — the ops host key is already pinned in the shared `known_hosts` file from the
   `sync_liquidations` setup above (step 4 there); no re-pin needed for a second channel to the
   same host.
5. **NAS** — set `PANEL_SOURCE=deploy@<ops-host>:` in the `.env` next to `compose.yaml` and
   `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely.

### The `sync_reconciled` replication channel (the NAS pulls this node)

Pull-only transport, mirroring `sync_panel`/`sync_liquidations` above -- spec 00054 D4: the overlay
writer (reconciler + trade-backfill) moved to this node, so the NAS acquires the healed overlay
instead of writing it. Custody stays on the NAS (D3); only the computation moved. Hash-verified,
like the panel/liquidations channels (every minted hour carries a `.sha256` sidecar).

1. **Keygen** (workstation; vault the private half like the other sync keys): `ssh-keygen -t ed25519 -f sync_reconciled_ed25519 -C zcrypto-sync-reconciled-pullonly -N ""`.
2. **Ops node** — install the public half as a forced-command entry in `deploy`'s `~/.ssh/authorized_keys`, pinning the overlay root:

   ```
   command="/usr/bin/rrsync -ro /var/lib/zcrypto-ops/capture-reconciled",restrict ssh-ed25519 AAAA... zcrypto-sync-reconciled-pullonly
   ```

3. **NAS** — drop the private key at `/volume1/docker/zcrypto-archive/keys/sync_reconciled`, mode
   `0600` (matches the fixed `RECONCILED_SSH_KEY=/keys/sync_reconciled` in `infra/nas/compose.yaml`).
4. **NAS** — the ops host key is already pinned in the shared `known_hosts` file from the
   `sync_liquidations` setup above (step 4 there); no re-pin needed for a third channel to the
   same host.
5. **NAS** — set `RECONCILED_SOURCE=deploy@<ops-host>:` in the `.env` next to `compose.yaml` and
   `docker compose up -d` to pick it up. Leave it unset and the pull cycle is skipped entirely.

## Alloy telemetry stack (Task 1, spec 00054 D1/D7)

Grafana Alloy runs as its own compose project at `{{ ops_alloy_dir }}` (default
`/etc/zcrypto-ops/alloy`), rendered by the `ops` role only when the pinned Alloy digest is supplied
(`-e ops_alloy_digest=sha256:<...>`; no default, matching `ops_image_digest`'s pattern). It ships
host metrics (load, memory, free disk space, network IO), the four OPS-3/OPS-4 timers' textfile
series, and every container's logs to Grafana Cloud — mirroring `infra/nas/config.alloy`'s pipeline
(see `infra/ansible/roles/ops/files/config.alloy` for the three deliberate divergences: no
cadvisor, dedicated non-`deploy` uid + rootfs mount, compose-service-first log labelling).

Ops log streams are labelled two ways (T0060): the long-lived compose-managed containers
(`liquidations`, `alloy`) ship via the docker path, labelled from the **compose service label**;
the ephemeral systemd-unit `docker run --rm` jobs are **dropped** from the docker path (their
`--rm` lifetime makes polling discovery structurally lossy) and ship via the **unit journal**,
labelled by unit name. The full `container` label set is therefore `liquidations`, `alloy`,
`zcrypto-archive-pull`, `zcrypto-verify-replay`, `zcrypto-verified-replay`,
`zcrypto-panel-materialize` — there is **no** `zcrypto-reconcile` or `zcrypto-trade-backfill`
stream: those runs are attached children of the archive-pull unit, so their stdout lands under
`container="zcrypto-archive-pull"`. (The docker-name fallback rule in `config.alloy` is
future-proofing for a later non-compose container; today it matches nothing.) This deliberately
differs from the NAS's docker-name-derived scheme (whose selectors, copied verbatim, were dead on
ops — T0060); unifying the fleet's labelling is T0020's fleet-wide dashboards pass.

**Runs as the dedicated `zcrypto-alloy` system user, never `deploy`.** The role creates it
(`nologin`, no home) and derives its uid/gid via `getent`, the same pattern used for `ops_uid`. This
is load-bearing, not cosmetic: `/home/deploy/.ssh` (0700 `deploy:deploy`) still holds the
`sync_nas_archive` private key (0600) of the T0058-retired pull channel (on the host until the
attended retirement step above runs), and Alloy mounts
`/:/host/root:ro` for its free-disk-space collector. Running Alloy as `deploy` would let it read
that key directly through the mount, no escalation needed — defeating the protection this stack
claims to replicate from the NAS (T0030). `zcrypto-alloy` owns nothing under `/home/deploy/.ssh`, so
the direct read is closed. Docker-socket access is granted via `group_add` set to the host's real
numeric docker gid, derived at converge time with `getent` (`infra/ansible/roles/ops/tasks/main.yml`)
— **not** a named `"docker"` entry: Docker resolves a named `group_add` entry against the
**container's own** `/etc/group`, not the host's, and the upstream `grafana/alloy` image ships only
`alloy:x:473:`, so a literal `"docker"` would never resolve and the container would fail to start.
This is exactly why `infra/nas/compose.yaml`'s `alloy` service passes the numeric `group_add: ["0"]`
rather than a name. Either way this is **defence in depth only**: holding the Docker API is
root-equivalent by definition (it can launch a privileged container regardless of a `:ro` socket
mount), so that escalation path remains — the same accepted residual the NAS's comments record for
T0042.

### Deploy

1. Converge with the digest: `./scripts/run.sh site.yml --limit zcrypto-ops -e ops_alloy_digest=sha256:<...>` (from `infra/ansible/`). There is no hand-placed secrets file (and none on the NAS either since T0056 — the `nas` role renders its copy from the same vault group): the `ops` role renders `{{ ops_alloy_dir }}/alloy-secrets.env` (default `/etc/zcrypto-ops/alloy/alloy-secrets.env`) straight from the vault, mode `0600`, owned by `zcrypto-alloy` (the container runs as that user and must be able to read a 0600 file it does not own by default), with `no_log: true` + `diff: false` so the converge never prints the values. The six vars (`GRAFANA_PROM_URL/USERNAME/PASSWORD`, `GRAFANA_LOKI_URL/USERNAME/PASSWORD`) live in `group_vars/observed/vault.yml` — rotate them there. `config.alloy` reads the rendered file via the River `sys.env(...)` stdlib function; `compose.yaml` itself stays secret-free (only `env_file: ./alloy-secrets.env` references the file by name).
2. Start it (attended, plan Task 3): `ssh hp`, then `docker compose -f /etc/zcrypto-ops/alloy/compose.yaml up -d`.
3. Verify by outcome: the four textfile series (`ops_archive_pull_*`, `ops_panel_*`,
   `ops_verify_replay_*`, `ops_verified_replay_*`) and host metrics appear in Grafana Cloud within a
   scrape interval; `tests/test_infra_alloy_series.py` pins the keep-regex against every series this
   stack (present + Task 6's future writer move) actually publishes.
