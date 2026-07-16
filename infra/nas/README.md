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
5. Create the shared textfile-collector directory `/volume1/docker/zcrypto-archive/textfile`,
   owned `1000:1000` and `chmod 0775`:

   ```bash
   mkdir -p /volume1/docker/zcrypto-archive/textfile
   chown 1000:1000 /volume1/docker/zcrypto-archive/textfile
   chmod 0775 /volume1/docker/zcrypto-archive/textfile
   ```

   The explicit `chmod` matters: a Synology DSM ACL granting the host uid write access is **not**
   honored inside the container, which only sees the underlying POSIX mode — so real
   owner-writable bits (`0775`) are required, not just an ACL grant. `archive-pull` writes
   `gate.prom` there after each journal pull; Alloy also mounts it (read-only) for scraping (Task
   3 below).
6. Pin the image to the **`-compat`** variant digest: `ghcr.io/zhaow-de/zcrypto-capture@sha256:<digest>`
   (the NAS Atom has no AVX, so it runs the `-compat` build, not the VPS's default AVX image — see
   `docs/open-topics/T0029-nas-cpu-no-avx-polars.md`). Read the digest with
   `docker buildx imagetools inspect ghcr.io/zhaow-de/zcrypto-capture:latest-compat`. The image
   already contains the `zcrypto` CLI, so there is no NAS-side build.
7. Create a new healthchecks.io check (e.g. named `zcrypto-gate-verify`) and copy its ping URL into
   `GATE_HEALTHCHECK_URL` (Deploy step 8) — a **new, dedicated** check, distinct from the engine's
   own `HEALTHCHECK_URL`. This is the **sole Alloy-independent paging path** for the gate (spec
   00049): if Alloy or the whole Grafana pipeline is down, this dead-man still pages, so it is
   required, not optional.
8. Set the deploy-time env vars (see below) in an adjacent `.env` file next to `compose.yaml`, or
   export them in the shell that runs `docker compose`.
9. Start the stack: `/usr/local/bin/docker compose -f compose.yaml up -d` (the full path — Docker
   is off the login `PATH` on the NAS). Confirm with
   `/usr/local/bin/docker compose -f compose.yaml ps` that `archive-pull` is `Up` and running as
   `1000:1000`.
   **After ANY `up -d` that recreates a container, also run `docker restart zcrypto-archive-alloy-1`** — Alloy's docker tailer keeps following the dead container ID and the recreated service's logs silently stop shipping until Alloy is restarted (T0048; the `NAS · archive-pull stalled` dead-man is what eventually catches it).

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
| `CAPTURE_RED_SOURCE` | rsync source spec for the **redundant secondary's** capture segments, e.g. `deploy@zcrypto-red.zhaow.me:` (its own `rrsync -ro` forced command pins the remote subtree, same pattern as the primary). **Leave unset and both the secondary pull and the reconcile step are skipped entirely**, so this stack still runs on a NAS that has not been given the red channel. | deploy-time `.env` |
| `CAPTURE_RED_DEST` | Where the secondary's raw mirror lands. Kept separate from the primary's on purpose: the reconciler needs the two mirrors as **independent witnesses**, and the raw primary is the T0003 exit bar's only input. | fixed to `/archive/capture-segments-red` in `compose.yaml` |
| `CAPTURE_RED_SSH_KEY` | Private key for the secondary's pull channel — a **separate** least-privilege keypair (`sync_capture_red`), never the primary's. | fixed to `/keys/sync_capture_red` in `compose.yaml` |
| `LIQUIDATIONS_SOURCE` | rsync source spec for the **ops node's** liquidations tree (spec 00051 OPS-2), e.g. `deploy@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). Liquidations are not backfillable, so this pull is the no-sole-custody replica. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the ops channel. Hash-verified like the capture pulls (the recorder writes `.sha256` manifests). | deploy-time `.env` |
| `LIQUIDATIONS_DEST` | Where the liquidations mirror lands. | fixed to `/archive/liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_KEY` | Private key for the liquidations pull — a **separate** least-privilege keypair (`sync_liquidations`), never the capture or journal keys. | fixed to `/keys/sync_liquidations` in `compose.yaml` |
| `LIQUIDATIONS_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `PANEL_SOURCE` | rsync source spec for the **ops node's** L2 primitive panel tree (spec 00052 D7), e.g. `deploy@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). Convenience-durability only — the panel is recomputable from raw, so this copy is not custody-critical. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the panel channel. Hash-verified like the capture/liquidations pulls (the materializer writes `.sha256` manifests). | deploy-time `.env` |
| `PANEL_DEST` | Where the panel mirror lands. | fixed to `/archive/l2-panel` in `compose.yaml` |
| `PANEL_SSH_KEY` | Private key for the panel pull — a **separate** least-privilege keypair (`sync_panel`), never the capture/journal/liquidations keys. | fixed to `/keys/sync_panel` in `compose.yaml` |
| `PANEL_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `RECONCILED_SOURCE` | rsync source spec for the **ops node's** healed overlay tree (spec 00054 D4), e.g. `deploy@<ops-host>:` (its own `rrsync -ro` forced command pins the remote subtree — see `infra/ops/README.md` for the channel setup). The overlay writer (reconciler + trade-backfill) moved to the ops node, so this pull is how the NAS re-acquires custody of it. **Leave unset and the pull is skipped entirely**, so this stack still runs on a NAS that has not been given the channel — which is also the rollback path. Hash-verified like the capture/liquidations/panel pulls (every minted hour carries a `.sha256` sidecar). | deploy-time `.env` |
| `RECONCILED_SSH_KEY` | Private key for the reconciled-overlay pull — a **separate** least-privilege keypair (`sync_reconciled`), never the capture/journal/liquidations/panel keys. | fixed to `/keys/sync_reconciled` in `compose.yaml` |
| `RECONCILED_SSH_PORT` | The ops node's SSH port, scoped to this pull only (passed as `ARCHIVE_SSH_PORT` per call, like the per-call keys). The ops node is a home-LAN box on port **22**, unlike the VPS channels' 10022. | defaults to `22` in `compose.yaml` |
| `RECONCILED_DEST` | The healed overlay `zcrypto archive reconcile` writes to. Only **healed** hours land here, plus the append-only ledger; readers resolve reconciled-first, primary-final otherwise (`cli/archive/reader.py`). | fixed to `/archive/capture-reconciled` in `compose.yaml` |
| `RECONCILE_TEXTFILE` | Prometheus textfile the reconcile step writes its metrics to (`zcrypto_reconcile_*`). Alloy's keep-regex must list that prefix or **every series is silently dropped and no rule can ever fire** — see `infra/nas/config.alloy`. | fixed to `/textfile/reconcile.prom` in `compose.yaml` |
| `RECONCILE_MIN_GAP_SECONDS` | Primary book silence longer than this counts as a gap. Defaults to `30` — 2× the measured 14.78 s single-host maximum natural quiescence. **Unvalidated cross-host (T0039)**, which is why reconcile runs **detect-only** until the soak pins it from real data. | deploy-time `.env` (optional) |
| `RECONCILE_WINDOW_HOURS` | Trailing settled hours the reconciler examines each cycle; defaults to `48`. | deploy-time `.env` (optional) |
| `TRADE_BACKFILL_TEXTFILE` | Prometheus textfile the daily trade-backfill step (spec `00053`) writes its metrics to (`zcrypto_trade_backfill_*`), atomically (tmp + `mv`). Alloy's keep-regex lists that prefix, same as `RECONCILE_TEXTFILE` above. | defaults to `/textfile/trade-backfill.prom` in `pull-entrypoint.sh` (no compose.yaml entry yet) |
| `ARCHIVE_SSH_PORT` | VPS SSH port; defaults to 10022 (matching the capture/engine channels) if omitted or blank. | deploy-time `.env` (optional) |
| `ARCHIVE_PULL_INTERVAL` | Seconds between pull cycles; the entrypoint defaults to `3600` (hourly) if unset. | deploy-time `.env`, or leave unset for the hourly default |
| `GATE_TEXTFILE` | Prometheus node-exporter textfile-collector path the `zcrypto engine gate-export` step (run after each journal pull) atomically writes the gate metrics to. | fixed to `/textfile/gate.prom` in `compose.yaml` (matches the textfile-dir mount, Deploy step 5) |
| `GATE_HEALTHCHECK_URL` | Dead-man's-switch base URL for `gate-export`: GET on a clean gate, GET `<url>/fail` otherwise. **Required** — the sole Alloy-independent paging path (Deploy step 7); a new, dedicated healthchecks.io check, distinct from the engine's own `HEALTHCHECK_URL`. | deploy-time `.env` |

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

## Correcting the reconcile ledger (T0044)

The reconcile counters (`zcrypto_reconcile_residual_gap_seconds_total`, `_healable_gap_seconds_total`, the hour/deficit counters) are **summed from the whole append-only** `reconcile-ledger.jsonl` on every cycle, so they are monotone as long as the ledger only ever grows. The one operation that breaks that is a **correction** — removing a record a classifier bug wrote (as on 2026-07-14, a false `total_loss`). A correction *decreases* a counter, Prometheus reads the decrease as a **reset**, and a bare `increase()` would report the whole post-reset value as fresh change. The two `increase()`-based alert rules (`Reconciler · residual gap increased`, `Reconciler · primary gap rate high`) are guarded with `and resets(...) == 0` precisely so a correction cannot false-page — so **expect both to go quiet for one window after a correction; that is the guard working, not a fault.**

The procedure (a deliberate, one-off exception to the ledger's append-only discipline):

```bash
L=/volume1/ZhaoCrypto/capture-reconciled/reconcile-ledger.jsonl
sudo cp "$L" "$L.bak-$(date -u +%Y%m%d-%H%M%S)"        # 1. back up VERBATIM (the audit trail of the bug)
# 2. filter by an EXACT-MATCH predicate, asserting the count you expect to drop:
sudo python3 - "$L" <<'PY'
import json, sys
L = sys.argv[1]
keep, dropped = [], []
for line in open(L):
    if not line.strip():
        continue
    r = json.loads(line)                               # raises on a malformed line -> never write a broken ledger
    is_bad = r.get("state") == "total_loss" and r.get("pair") == "LINK/EUR" and r.get("hour", "").startswith("2026-07-14T02")
    (dropped if is_bad else keep).append(r)
assert len(dropped) == 1, f"expected exactly 1 record, found {len(dropped)}"   # 3. STOP if it does not match
open("/tmp/ledger.new", "w").write("".join(json.dumps(r) + "\n" for r in keep))
print(f"dropped {len(dropped)}, kept {len(keep)}")
PY
sudo cp /tmp/ledger.new "$L" && sudo chown zcrypto:zcrypto "$L" && sudo chmod 0664 "$L" && sudo rm -f /tmp/ledger.new
```

Rules: keep **one record per line** (`_load_ledger` raises `CaptureError` on a malformed line, which fails the next cycle loudly); never truncate to shrink the file (that resets every counter — see [[T0044]] for the compaction design that preserves the totals); and confirm the two alert rules return to Normal within a window after the reset ages out.

## Alloy telemetry stack (spec 00049 Role B, Task 3)

One more service on the same `compose.yaml`, unrelated to `archive-pull`'s own deploy sequence above:
**Grafana Alloy**, shipping NAS host metrics (load, memory, free disk space, network IO), the Role B
gate metrics (Task 2's `gate.prom` textfile), and every container's logs to the already-provisioned
Grafana Cloud instance.

Alloy reads the Docker socket **directly**. A GET-only `docker-socket-proxy` (tecnativa) used to sit in front of it with `POST=0` as the boundary; it was removed on 2026-07-14 because it corrupted the logs it existed to carry — its HAProxy `timeout client/server 10m` severed Docker's long-lived `/containers/<id>/logs?follow=1` stream whenever a container went quiet, and Alloy's reconnect (inclusive `since=<second>`) re-ingested the last line each time, duplicating it every 10 minutes forever. **Accepted residual:** anything holding the Docker API is root-equivalent — `:ro` on the socket mount is not a boundary, since the API can create a privileged container — so a compromised Alloy could reach the rrsync keys that pull from the capture VPS. Alloy is still kept non-root (uid 1031 + `group_add: "0"`), which preserves T0030's protection of the `0600` keys against the `/host/root:ro` mount. Tracked in `docs/open-topics/T0042-*` — revisit before go-live.

**Container-level metrics (CPU/mem/fs per container) are NOT collected on this NAS.** `cadvisor`
SIGSEGVs on Synology DSM — a nil-pointer panic because DSM's kernel has no CPU cgroup hierarchy for
it to walk — and the panic takes down all of Alloy with it, so `prometheus.exporter.cadvisor` is
not run here at all. Only host metrics + the gate metrics + the container logs flow off this NAS.

See `docs/specs/00043-observability-design.md` for the design this is adapted from (the VPS
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
3. Create the dedicated Alloy user **`zcrypto-dummy` (uid 1031, gid 1000 — the `zcrypto` group)** on
   the NAS if it doesn't exist (DSM → Control Panel → User & Group, or `synouser --add`), then create
   Alloy's `--storage.path` dir owned by it and `chmod 0775`:

   ```bash
   mkdir -p /volume1/docker/zcrypto-archive/alloy-data
   chown 1031:1000 /volume1/docker/zcrypto-archive/alloy-data
   chmod 0775 /volume1/docker/zcrypto-archive/alloy-data
   ```

   This dir holds the remote_write WAL and Loki log read-positions, which persist across a container
   replacement so a redeploy doesn't re-ship each source's retained backlog into the ingest quota.
   The compose file pins `user: "1031:1000"` (`zcrypto-dummy`) — **not** the image's built-in uid-473
   `alloy` user, nor uid 1000. Rationale: (1) the upstream `grafana/alloy` image runs as `root` by
   default (its Dockerfile keeps `USER root`), and the `/:/host/root:ro` mount would then expose
   every 0600 host secret, so a non-root override is load-bearing; (2) uid 473 is not a
   Synology-recognized user, so the DSM ACL denies it write (`mkdir /var/lib/alloy/...: permission
   denied`) — a real DSM user is required, and the `chmod 0775` above sets the actual POSIX mode the
   container honors (the DSM ACL granting host-uid write is **not** seen inside the container); and
   (3) uid 1031 is a **dedicated, non-secret-owning** user — it is **not** the owner of the `0600`
   rrsync pull keys (uid 1000 is), so a compromised Alloy cannot read them through `/host/root`. Note
   `zcrypto-dummy`'s gid 1000 IS the key-owning group, so this protection rests on the keys being
   `0600` — owner-only, group has no read — not on group isolation; keep the keys `0600`. (This closes
   [[T0030]]; verified live as 1031:1000: the key read is denied while metrics + logs still ship.)
4. Pin the Alloy image to a digest, same pattern as the capture image (Deploy step 6 above):
   `docker buildx imagetools inspect grafana/alloy:latest`, then replace the `:latest` tag on the
   `alloy` service in `compose.yaml` with `@sha256:<digest>`.
5. Start (or restart to pick up the new service):
   `/usr/local/bin/docker compose -f compose.yaml up -d`. Confirm with
   `/usr/local/bin/docker compose -f compose.yaml ps` that `alloy` is `Up`.

### Resource budget

Diverges from the VPS design (`docs/specs/00043-observability-design.md`) here: the Synology DSM
kernel has no CPU CFS cgroup, so this stack sets **no `cpus:`/`cpu_shares:` limits** at all — a
`NanoCPUs` limit fails hard (`NanoCPUs can not be set ... cgroup is not mounted`) and blocks the
whole `compose up`. Only `memory` limits work (a separate, mounted cgroup): Alloy `memory: 512m`,
`GOMEMLIMIT=460MiB` (Go's GC overshoots a small cap under default behavior otherwise).
cadvisor is not run on the NAS at all (see above), which also
removes the one component that would have needed its own CPU budget. 32 GB NAS RAM makes the
memory ceiling arithmetic comfortable — these are caps, not reservations.

### Verification note

The NAS deploy shakedown ran this stack live on the actual Synology DSM host and surfaced several
DSM-specific incompatibilities, all now fixed in `compose.yaml`/`config.alloy` and reflected above:
cadvisor SIGSEGVs on DSM's cgroup-less kernel (removed entirely — see the container-metrics note
above), the alloy-data volume's DSM ACL rejects the image's built-in uid 473 (Alloy runs as the
dedicated non-secret-owning uid 1031 `zcrypto-dummy` — see Deploy step 3 above), and a
`cpus:`/`cpu_shares:` limit fails hard on DSM's CPU-cgroup-less kernel (removed — see Resource budget
above). This file now reflects a live-verified deploy, not just the originally-authored design.

## Grafana dashboard + alerts (spec 00049 Role B, Task 4)

The committed-as-code dashboard (`infra/grafana/zcrypto-dashboard.json`) and alert rules
(`infra/grafana/alerts.yaml`) are provisioned onto the already-live Grafana Cloud instance by
`infra/scripts/grafana-push.sh` — run from any machine with network access to that instance (not
NAS-side; this is a one-off/on-change push, not a running service). Idempotent: re-run after any
commit to `infra/grafana/`.

### Deploy

1. Set these env vars (vault-sourced — the Grafana Cloud service-account token, same out-of-band
   distribution as the other vaulted secrets above):
   - `GRAFANA_URL` — the Grafana Cloud stack base URL, e.g. `https://<stack>.grafana.net`.
   - `GRAFANA_SA_TOKEN` — a Grafana service-account token with dashboards + alerting-provisioning
     write scope.
   - `GRAFANA_PROM_DS_UID` — the Prometheus datasource UID on the instance (alert-rule queries).
   - `GRAFANA_LOKI_DS_UID` — the Loki datasource UID on the instance (the ERROR-logs rule).
   - `GRAFANA_ALERT_FOLDER_UID` — the folder UID the alert rules provision into.
   - `GRAFANA_SLACK_WEBHOOK_URL` (optional, T0047) — the Slack incoming-webhook URL, sourced from
     the vaulted `slack_webhook_url` in `infra/ansible/group_vars/capture_host/vault.yml` — never
     committed plaintext. Unset/empty skips the Slack section cleanly.
   - `GRAFANA_SLACK_RECEIVER` (optional, T0047) — the exact contact-point/receiver name to attach
     the Slack integration to (e.g. `email`, the receiver every rule in `alerts.yaml` already routes
     to). No default: leaving it unset (while the webhook URL is set) lists the live contact points
     instead of guessing.
2. Create the `email` contact point in Grafana (Alerting → Contact points → New contact point,
   name it exactly `email`, integration `Email`, enter the destination address(es)) — every alert
   rule in `alerts.yaml` routes to `notification_settings.receiver: email` by name, so the rules
   fail to notify anywhere until this contact point exists.
3. Run `infra/scripts/grafana-push.sh` with the env vars from step 1 exported. It pushes the dashboard
   (overwriting by its fixed uid `zcrypto-main`) then upserts each alert rule (by its own stable
   `uid`); if `GRAFANA_SLACK_WEBHOOK_URL` and `GRAFANA_SLACK_RECEIVER` are both set, it also upserts
   a Slack integration (stable uid `zcrypto-slack-webhook`) onto the named receiver — phase one runs
   Slack **alongside** email, with no notification-policy changes (T0047).
4. On first load of the dashboard, confirm (or set as the template-variable defaults) that its
   `${DS_PROMETHEUS}`/`${DS_LOKI}` datasource variables resolve to the correct Prometheus/Loki
   datasources — Grafana auto-binds these on import, but an instance with more than one datasource
   of either type needs the operator to confirm/select the right one.
