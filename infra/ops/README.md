# Ops-node stack (spec 00051, compute tier)

The home ops node (`zcrypto-ops`, `ssh hp`) is the fleet's compute tier: a home-LAN box converged by the third `site.yml` play (roles `base`/`chrony`/`docker`/`ops` — no `hardening`/`firewall`/`fail2ban`, it is not internet-facing). Charter (spec 00051 D10): **no trade key, never `engine_host`, pull-only transport** — it pulls everything it consumes from the NAS and is pulled *from* for everything it produces.

Everything below is installed by the `ops` Ansible role (`infra/ansible/roles/ops/`) **only when the pinned image digest is supplied** (`-e ops_image_digest=sha256:<...>`, always the **default AVX** build of `ghcr.io/zhaow-de/zcrypto-capture`, never `-compat`, never `:latest`); a converge without the digest skips those installs rather than rendering artifacts that point at a broken image reference.

## Liquidations recorder (OPS-2)

The `zcrypto liquidations` daemon (Binance USD-M `forceOrder` events → hourly Parquet segments + `.sha256` manifests) runs as the single service in `{{ ops_compose_dir }}/compose.yaml` (default `/etc/zcrypto-ops/compose.yaml`), rendered by the role from `infra/ansible/roles/ops/templates/compose.yaml.j2`. Liquidations are **not backfillable**, so the tree replicates to the NAS (D10 no-sole-custody — the channel below) and the daemon is **never auto-(re)started by a converge**: the role only renders the file; starting is a deliberate attended step.

### Deploy

1. Converge with the digest: `./scripts/run.sh site.yml --limit zcrypto-ops -e ops_image_digest=sha256:<...>` (from `infra/ansible/`; read the **default AVX** digest from the capture-image workflow's job summary, and confirm `zcrypto liquidations --help` exists in that image before pinning).
2. Create a healthchecks.io check (e.g. named `zcrypto-liquidations`) and put its ping URL in the role var `ops_liquidations_healthcheck_url` (host var or `-e`) before the converge — it renders into the compose file as `LIQUIDATIONS_HEALTHCHECK_URL`. Empty skips the recorder's liveness pings (the ping gate is `client.connected` + disk-watermark healthy, `cli/liquidations/command.py`); the dead-man alerts by **missed** pings, so an attached email channel on the check is what pages.
3. Start it (attended, plan Task 5): `ssh hp`, then `docker compose -f /etc/zcrypto-ops/compose.yaml up -d`.
4. Verify by outcome after the next hour boundary: finals appear **for a liquid symbol** (`BTCUSDT`/`ETHUSDT`) at `/var/lib/zcrypto-ops/liquidations/<SYM>/liquidations/<YYYY>/<MM>/<DD>/<HH>.parquet` with a valid `.sha256` sidecar. Sparse symbols linger as `.part` files until their next event ([T0046] — event-driven rotation); that is known, not a failure. `dropping late event` lines right after a (re)start are healthy (reconnect redelivery), not a failure signal.

### Env contract (rendered into `compose.yaml`)

| Variable | Meaning | Set where |
| -- | -- | -- |
| `ZCRYPTO_LIQUIDATIONS_DATA_DIR` | Segment output base inside the container: `/data/liquidations` (= `{{ ops_data_dir }}/liquidations` on the host, default `/var/lib/zcrypto-ops/liquidations`). | fixed in `compose.yaml.j2` (matches the `{{ ops_data_dir }}:/data` mount) |
| `LIQUIDATIONS_HEALTHCHECK_URL` | healthchecks.io dead-man ping URL; the daemon pings it every 60 s while connected and disk-healthy. Empty → pings skipped. | role var `ops_liquidations_healthcheck_url` (Deploy step 2) |

The service runs digest-pinned (`{{ ops_image }}@{{ ops_image_digest }}`), as the `deploy` uid:gid, `restart: unless-stopped`, `json-file` logging capped 10m×3.

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

Two daily systemd timers run the `zcrypto` CLI in the digest-pinned image (`docker run --rm --entrypoint zcrypto <image>@<digest> ...`, as the `deploy` uid/gid, with `ops_data_dir` mounted read-only at `/data`):

| Unit | Schedule (UTC) | What it runs |
| -- | -- | -- |
| `zcrypto-verify-replay.timer` | daily 03:41 | `zcrypto archive verify-replay /data/capture-segments /data/capture-reconciled` — continuity-replays the pulled canonical archive (reconciled-first) through `OrderBook`; exits non-zero if any hour is not snapshot-anchored / ts-ordered / checksum-attested / structurally replayable. |
| `zcrypto-verified-replay.timer` | daily 05:23 | `zcrypto engine replay --path verified --journal-dir /data/engine-journal` — the oracle-builder replay of the pulled journal; exits non-zero on any mismatch or validation failure. |

Both slots are off the hour boundary and clear of the ops reboot window (02:25 UTC) and the capture hosts' maintenance windows (21:25/22:25 UTC). `Persistent=true`: a host that was down at the slot runs on the next boot instead of skipping the day.

### Textfile metrics

Each run atomically rewrites its node-exporter textfile in `ops_textfile_dir` (default `/var/lib/zcrypto-ops/textfile`): `ops-verify-replay.prom` / `ops-verified-replay.prom`, carrying (per family, prefixes `ops_verify_replay_` / `ops_verified_replay_`):

| Metric | Meaning |
| -- | -- |
| `<prefix>exit_code` | Exit code of the last run (`0` = clean; non-zero is the CLI's own failure verdict). |
| `<prefix>last_run_timestamp` | Unix time of the last run, clean or not. |
| `<prefix>last_success_timestamp` | Unix time of the last **clean** run (`0` = never). A failed run carries the previous value forward, so "time since last clean replay" stays directly alertable. |

The metric families are new: per the T0034 discipline, arm Grafana alert rules only once the series are visible in the scrape (OPS-4/5 wires the ops node's scraper; do not push rules blind).

### Dead-man pings

On a clean run (exit 0) each script GETs its healthchecks.io ping URL — role vars `ops_verify_replay_healthcheck_url` / `ops_verified_replay_healthcheck_url`, both defaulting to empty, which **skips** the ping entirely (the CLI's optional `ping_healthcheck` semantics, shell edition: `[ -n "$URL" ] && curl -fsS -m 10 "$URL"`). A failed run pings nothing and alerts by silence.
