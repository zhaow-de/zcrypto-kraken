# NAS archive-pull stack (spec 00048, Role A)

The always-on NAS pull/archive tier: a single container (`archive-pull`) that pulls the VPS
capture segments and the engine journal on a schedule and archives the result to
`/volume1/ZhaoCrypto` — decoupling data durability from the intermittently-online workstation
(see `docs/specs/00048-three-tier-topology-design.md`, Role A). It supersedes T0003's
workstation-pull approach. The capture-segments pull is hash-verified against each segment's
`.sha256` manifest sidecar; the engine-journal pull runs `--no-verify` (its `.parquet` snapshots
have no sidecars — their integrity is a JSON `snapshot_content_hash`, verified later by Role B on
replay).

Everything runs **inside the container** under Synology Container Manager: no systemd units, no
DSM Task Scheduler entries, no NAS-OS config. `infra/nas/pull-entrypoint.sh` is the in-container
scheduler — a loop that runs `zcrypto archive pull` for each source every
`ARCHIVE_PULL_INTERVAL` seconds and survives a single failed pull without exiting; Container
Manager's `restart: unless-stopped` policy is what survives a NAS reboot.

## Deploy

1. On the NAS, place `compose.yaml`, `pull-entrypoint.sh`, and `zcrypto.toml` (the app config the
   `gate-export` step reads for its journal/store paths) under `/volume1/docker/zcrypto-archive/`.
2. Drop the `sync_capture` private key at `/volume1/docker/zcrypto-archive/keys/sync_capture`,
   mode `0600` (the vaulted keypair from plan Task 6; the public half is installed on the VPS as
   a read-only `rrsync` forced-command channel for the capture segments).
3. Drop the `sync_journal` private key at `/volume1/docker/zcrypto-archive/keys/sync_journal`,
   mode `0600` — the engine journal's OWN least-privilege keypair (Role B), distinct from
   `sync_capture` so a leaked key exposes only one channel; the public half is installed on the
   VPS as a read-only `rrsync` forced-command channel for the engine journal.
4. Pre-seed the pinned VPS host key at `/volume1/docker/zcrypto-archive/keys/known_hosts`.
   DSM ships no `ssh-keyscan`, so run it from a machine that has one (e.g. the workstation):
   `ssh-keyscan -p 10022 <vps-host>` and copy its output to that path. Host-key checking is strict
   (`StrictHostKeyChecking=yes`), so an unseeded or stale file fails the pull closed.
5. Create the shared textfile-collector directory
   `/volume1/docker/zcrypto-archive/textfile`, writable by uid 1000 — `archive-pull` writes
   `gate.prom` there after each journal pull; Task 3 also mounts it (read-only) into Alloy for
   scraping.
6. Pin the image to the **`-compat`** variant digest: `ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest>`
   (the NAS Atom has no AVX, so it runs the `-compat` build, not the VPS's default AVX image — see
   `docs/open-topics/T0029-nas-cpu-no-avx-polars.md`). Read the digest with
   `docker buildx imagetools inspect ghcr.io/zhaow-de/zcrypto-capture:latest-compat`. The image
   already contains the `zcrypto` CLI, so there is no NAS-side build.
7. Set the deploy-time env vars (see below) in an adjacent `.env` file next to `compose.yaml`, or
   export them in the shell that runs `docker compose`.
8. Start the stack: `/usr/local/bin/docker compose -f compose.yaml up -d` (the full path — Docker
   is off the login `PATH` on the NAS). Confirm with
   `/usr/local/bin/docker compose -f compose.yaml ps` that `archive-pull` is `Up` and running as
   `1000:1000`.

## Env-var contract

| Variable | Meaning | Set where |
| -- | -- | -- |
| `CAPTURE_SOURCE` | rsync source spec for the capture segments, e.g. `deploy@<vps-host>:` (the `rrsync` forced command on the VPS pins the actual remote subtree, so the client-side path is effectively ignored). | deploy-time `.env` |
| `CAPTURE_DEST` | Local archive path the segments land in. | defaults to `/archive/capture-segments` in `compose.yaml` |
| `JOURNAL_SOURCE` | rsync source spec for the engine journal, e.g. `deploy@<vps-host>:` (same `rrsync` forced-command pattern, the existing journal channel). | deploy-time `.env` |
| `JOURNAL_DEST` | Local archive path the journal lands in. | defaults to `/archive/engine-journal` in `compose.yaml` |
| `CAPTURE_SSH_KEY` | Private key path inside the container for the capture channel's rsync-over-ssh transport. Passed as `ARCHIVE_SSH_KEY` to `zcrypto archive pull` for the capture-segments call only (`cli/archive/command.py` reads a single `ARCHIVE_SSH_KEY` from the environment; the entrypoint scopes it per subprocess call). | fixed to `/keys/sync_capture` in `compose.yaml` (matches the `./keys:/keys:ro` mount) |
| `JOURNAL_SSH_KEY` | Private key path inside the container for the engine-journal channel's OWN least-privilege rsync-over-ssh transport, distinct from `CAPTURE_SSH_KEY` (Deploy step 3). Passed as `ARCHIVE_SSH_KEY` for the journal-pull call only. | fixed to `/keys/sync_journal` in `compose.yaml` |
| `ARCHIVE_SSH_KNOWN_HOSTS` | `UserKnownHostsFile` path pinning the VPS host key. Host-key checking is strict (`StrictHostKeyChecking=yes`), so this file must be pre-seeded (Deploy step 4) — an unseeded or stale key fails the pull closed. | fixed to `/keys/known_hosts` in `compose.yaml` |
| `ARCHIVE_SSH_PORT` | VPS SSH port; defaults to 10022 (matching the capture/engine channels) if omitted or blank. | deploy-time `.env` (optional) |
| `ARCHIVE_PULL_INTERVAL` | Seconds between pull cycles; the entrypoint defaults to `3600` (hourly) if unset. | deploy-time `.env`, or leave unset for the hourly default |
| `GATE_TEXTFILE` | Prometheus node-exporter textfile-collector path the `zcrypto engine gate-export` step (run after each journal pull) atomically writes the gate metrics to. | fixed to `/textfile/gate.prom` in `compose.yaml` (matches the textfile-dir mount, Deploy step 5) |
| `GATE_HEALTHCHECK_URL` | Dead-man's-switch base URL for `gate-export`: GET on a clean gate, GET `<url>/fail` otherwise. Omit to skip the ping. | deploy-time `.env` (optional) |

## Reading pull-lag + verify failures

`docker logs` on the container surfaces `zcrypto archive pull`'s own log lines (see
`cli/archive/command.py`):

- `pull complete source=... checked=N ok=N failed=N lag_s=...` — one line per pull, for the
  capture-segments source. `lag_s` is the pull-lag dead-man signal: the age (seconds) of the
  newest verified segment. A growing `lag_s` across cycles means the scheduler loop is stuck or
  the transport is failing — check for the `pull-entrypoint: ... pull failed` line right above it.
- `archive pull complete (no verify) source=... dest=...` — the engine-journal pull (run with
  `--no-verify`, see above); no hash-verify pass runs, so this line replaces the
  `pull complete ... checked=...` line for that source.
- `archive pull: verify failed path=...` (ERROR) — a pulled capture segment's hash mismatched its
  manifest; it is logged, not archived as good. Re-pull on the next cycle picks it up again.
- `archive pull: rsync failed source=... dest=... returncode=...` (ERROR) — a transport failure;
  the pull is never verified as authoritative. The loop logs
  `pull-entrypoint: capture pull failed ...` / `... journal pull failed ...` to stderr and
  continues to the next interval rather than exiting the container.

```bash
/usr/local/bin/docker compose -f compose.yaml logs -f archive-pull
```

## Alloy telemetry stack (spec 00049 Role B, Task 3)

Two more services on the same `compose.yaml`, unrelated to `archive-pull`'s own deploy sequence
above: **Grafana Alloy** + a GET-only **`docker-socket-proxy`**, shipping NAS host metrics (load,
memory, free disk space, network IO), container metrics (`archive-pull`, `alloy`, the proxy
itself), the Role B gate metrics (Task 2's `gate.prom` textfile), and the `archive-pull`
container's logs to the already-provisioned Grafana Cloud instance. See
`docs/specs/00043-observability-design.md` for the design this is adapted from (the VPS
counterpart) and `infra/nas/config.alloy` for the Alloy pipeline itself — everything here runs
under Container Manager as plain compose services, no ansible/systemd.

### Deploy

1. Place `config.alloy` (this directory) alongside the already-deployed `compose.yaml` under
   `/volume1/docker/zcrypto-archive/`.
2. Create the secrets file `/volume1/docker/zcrypto-archive/alloy-secrets.env`, mode `0600`,
   **never committed** — distributed out-of-band the same way the `sync_capture`/`sync_journal`
   keys are (Deploy steps 2–3 above). Contents (one `KEY=value` per line, no quoting):

   ```
   GRAFANA_PROM_URL=https://<prometheus-remote-write-endpoint>/api/prom/push
   GRAFANA_PROM_USERNAME=<prometheus-instance-id>
   GRAFANA_PROM_PASSWORD=<prometheus-access-token>
   GRAFANA_LOKI_URL=https://<loki-push-endpoint>/loki/api/v1/push
   GRAFANA_LOKI_USERNAME=<loki-instance-id>
   GRAFANA_LOKI_PASSWORD=<loki-access-token>
   ```

   `config.alloy` reads these via the River `sys.env(...)` stdlib function; `compose.yaml` itself
   stays secret-free and diffable (only `env_file: ./alloy-secrets.env` references the file by
   name).
3. Create `/volume1/docker/zcrypto-archive/alloy-data/` owned by **uid/gid 473** (`sudo chown -R
   473:473 …/alloy-data`) — this is Alloy's `--storage.path`: the remote_write WAL and Loki log
   read-positions persist here so a container replacement doesn't re-ship each source's retained
   backlog into the ingest quota. The compose file pins `user: "473:473"` because the upstream
   `grafana/alloy` image does **not** activate its non-root user by default (its Dockerfile keeps
   `USER root`); running as root with the `/:/host/root:ro` mount would expose every 0600 host
   secret, so the override is load-bearing. Confirm the image's `alloy` uid is still 473 at deploy
   (`docker run --rm --entrypoint id grafana/alloy:latest alloy`); if it differs, update both the
   compose `user:` and this directory's ownership to match.
4. Pin both new images to a digest, same pattern as the capture image (Deploy step 6 above):
   `docker buildx imagetools inspect grafana/alloy:latest` and
   `docker buildx imagetools inspect ghcr.io/tecnativa/docker-socket-proxy:latest`, then replace
   the `:latest` tags on the `alloy` and `docker-socket-proxy` services in `compose.yaml` with
   `@sha256:<digest>`.
5. Start (or restart to pick up the two new services):
   `/usr/local/bin/docker compose -f compose.yaml up -d`. Confirm with
   `/usr/local/bin/docker compose -f compose.yaml ps` that `docker-socket-proxy` and `alloy` are
   both `Up`.

### Resource budget

Same tuning as the VPS design (`docs/specs/00043-observability-design.md`), reused as-is since the
NAS Atom is comparably weak and cadvisor's per-second housekeeping is the CPU hog on either host:
Alloy `cpus: "0.5"`, `memory: 512m`, `cpu_shares: 256`, `GOMEMLIMIT=460MiB` (Go's GC overshoots a
small cap under default behavior otherwise); `docker-socket-proxy` `cpus: "0.1"`, `memory: 64m`.
`docker_only` + the disabled cadvisor network metrics group keep container-metric collection cheap.
32 GB NAS RAM makes the ceiling arithmetic comfortable — these are caps, not reservations.

### Verification note

No Docker on the machine this was authored on, so `alloy validate` / `alloy fmt` against
`config.alloy` and a pulling `docker compose config` could not be run here. `config.alloy` was
written carefully against the River config language and 00043's design; live `alloy validate` (a
throwaway `grafana/alloy` container, offline/stub creds) is deferred to the NAS deploy shakedown —
run it before trusting this file in production.
