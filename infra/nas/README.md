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

1. On the NAS, place `compose.yaml` and `pull-entrypoint.sh` under
   `/volume1/docker/zcrypto-archive/`.
2. Drop the `sync_capture` private key at `/volume1/docker/zcrypto-archive/keys/sync_capture`,
   mode `0600` (the vaulted keypair from plan Task 6; the public half is installed on the VPS as
   a read-only `rrsync` forced-command channel for the capture segments).
3. Pin the image: edit `compose.yaml`'s `image:` line from `ghcr.io/zhaow-de/zcrypto-capture:latest`
   to the digest-pinned form `ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest>` (same image the
   VPS capture/engine containers run — it already contains the `zcrypto` CLI, no NAS-side build).
4. Set the deploy-time env vars (see below) in an adjacent `.env` file next to `compose.yaml`, or
   export them in the shell that runs `docker compose`.
5. Start the stack: `/usr/local/bin/docker compose -f compose.yaml up -d` (the full path — Docker
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
| `ARCHIVE_SSH_KEY` | Private key path inside the container for the rsync-over-ssh transport. | fixed to `/keys/sync_capture` in `compose.yaml` (matches the `./keys:/keys:ro` mount) |
| `ARCHIVE_SSH_KNOWN_HOSTS` | `UserKnownHostsFile` path — pre-seed it (`ssh-keyscan -p 10022 <vps> > keys/known_hosts`) to pin the VPS host key across container restarts. | fixed to `/keys/known_hosts` in `compose.yaml` |
| `ARCHIVE_SSH_PORT` | VPS SSH port; defaults to 10022 (matching the capture/engine channels) if omitted or blank. | deploy-time `.env` (optional) |
| `ARCHIVE_PULL_INTERVAL` | Seconds between pull cycles; the entrypoint defaults to `3600` (hourly) if unset. | deploy-time `.env`, or leave unset for the hourly default |

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
