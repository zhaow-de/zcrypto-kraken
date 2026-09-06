# Fleet topology

What runs where: host roles, data paths, mounts, replication, telemetry endpoints. Consult this before running commands on a fleet host or guessing a path; any change to what-runs-where updates this file **in the same change**. Dataset schemas/provenance are the data catalogs' job; running digests are [fleet-pins.md](fleet-pins.md).

## Hosts

| host | ssh | ansible groups | role | trust boundary |
| --- | --- | --- | --- | --- |
| `zcrypto` | `ssh zcrypto` | `capture_host`, `engine_host` | L2 capture **primary** + the trade engine | holds the **live Kraken trade key** (as container env — see CLAUDE.md `## Secrets`) |
| `zcrypto-red` | `ssh red` | `capture_host` | L2 capture **secondary** only | never joins `engine_host`; no trade key |
| `zcrypto-ops` | `ssh hp` | `ops_host`, `observed` | compute tier (spec `00051`): archive reconcile/backfill, liquidations poller, panel materialize | no trade key (D10); **no `uv`** — it runs containers, not the repo CLI. Memory headroom is `node_memory_MemAvailable_bytes{host="ops"}`, never MemFree — read it with `infra/scripts/grafana-query.py` |
| `nas` | `ssh nas` | `nas_host`, `observed` | archive/custody (spec `00048` Role A), gate export, NFS server | DSM owns the OS; ansible manages only the zcrypto payload. sftp is chrooted at `/volume1` and `nas-hot:` is a forced-command rrsync endpoint into `hot/`, so a transfer path and a shell path for one file differ — `infra/runbooks/nas.md`'s `nas-file-transfer` |
| `zaccess` | `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` | `access_host`, `observed` | internet bridgehead (spec `00075`): WireGuard tunnel head, Caddy mTLS edge, SSH + NAS socket-proxyd relays | Linode public-IP VPS; **no trade key, no capture data, no containers** — everything on it is re-issuable, so losing it is re-provisioning, not data loss. It holds the Grafana Cloud push creds and the PUBLIC half of the mTLS CA + pinned leaves; the CA private key never leaves the vault |
| workstation | — | `workstation` (local) | research node; the repo checkout | its `data/engine-store`/`engine-journal` are the **retired** pre-VPS engine state, not live data |

- **The live trade key reaches the engine as container environment** — `/opt/zcrypto-engine/engine.env`, `0600 root:root`, pulled in by the rendered compose as `env_file`. An ad-hoc read that needs it therefore runs inside the engine image, and inside the engine play's own window because it shares the key with the running engine: `infra/runbooks/engine-procedures.md`'s `engine-adhoc-key-read` carries the procedure.
- SSH as `zcrypto-deploy` (**passwordless sudo** — non-interactive `sudo` over ssh works). Root is key-only break-glass, installed by hand at bootstrap.
- **The bridgehead's sshd offers only two authentication tries**, `devsec.hardening`'s own default, and the five fleet deploy keys load into one agent — so its converges need an agent holding only that host's key: `infra/runbooks/zaccess.md`'s `zaccess-converge` carries the procedure.
- **The bridgehead's Alloy is a native deb followed from apt, not a pinned image** — no digest operand, no pins row, no bake: `infra/runbooks/zaccess.md`'s `zaccess-alloy-converge` carries what converging it takes.

- **The bridgehead's break-glass is Linode LISH** (serial console, provider panel) — root key-only SSH is the normal path; LISH is the recovery path when SSH is unreachable (`os_hardening` keeps `ttyS0` for it).
- **Route53: `zhaow.me` delegates `zaccess.zhaow.me` to its own hosted zone** (`Z0912077…`), where the apex `A`/`AAAA` (→ the Linode) and the `tmux.`/`nas.` `CNAME`s and the Let's Encrypt `CAA` live. The apex address records MUST live in that child zone, not the parent — a parent `A` co-located with the `NS` delegation is shadowed and never served. DNS is created by hand (spec `00075` D18).
- **The mTLS client pins are PEMs under `roles/access/files/pinned-leaves/`**, globbed into the Caddyfile at converge time; revoking one is `infra/runbooks/zaccess.md`'s `zaccess-revoke-client-cert`.
- **The agentboard unit's node and package are installed under nvm as `zhaow`, not by the role** — its `ExecStart` resolves them at start, so an upgrade is a restart rather than a converge: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade` carries it, and the safety clauses that restart has.

## Services and instruments

| service | host(s) | data / output | endpoint |
| --- | --- | --- | --- |
| `zcrypto-capture` | zcrypto, zcrypto-red | `/var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` | `/metrics` `127.0.0.1:9101` |
| `zcrypto-engine` | zcrypto | `/var/lib/zcrypto-engine/{store,journal}` (bind mounts; compose at `/opt/zcrypto-engine`); journal day-dirs hold `cycle-HH.json` (written **last**, after validation), `orders.jsonl`, `snapshots/`. **The red button is `/usr/local/sbin/zcrypto-flatten`** (`750 root:root`), rendered by an engine converge from `roles/engine/templates/zcrypto-flatten.sh.j2`; its procedure is `infra/runbooks/engine-procedures.md` → *engine-flatten* | `/metrics` `127.0.0.1:9102` |
| liquidations poller | zcrypto-ops | under `ops_data_dir` = `/var/lib/zcrypto-ops` (container-visible as `/data`) | `/metrics` `127.0.0.1:9103` |
| `grafana-alloy` | all four | scrape jobs: `capture_app`+`engine_app` (both capture hosts; `engine_app` reads 0 on red by design), `liquidations_app`+`healthchecks` (ops), host/textfile only (nas); + journal log sources | self-metrics `:12345` |
| ops timers | zcrypto-ops | `zcrypto-{archive-pull,panel-materialize,tape-bars,verify-replay,verified-replay}.service` (+ grafana-watchdog) — ephemeral `docker run` per tick; `.prom` outputs under `/var/lib/zcrypto-ops/textfile` | scraped by the ops Alloy textfile collector |
| capture/engine timers | zcrypto, zcrypto-red | `zcrypto-capture-prune` (03:17, segments), `zcrypto-reboot-check` (every 15 min, pending-reboot gauge), and — zcrypto only — `zcrypto-engine-journal-prune` (01:23, journal day-dirs, 60 d + a keep-newest-60 floor) | **`zcrypto-reboot-check` and `zcrypto-engine-journal-prune` publish `.prom` into `/var/lib/zcrypto-node-textfile`**, read by Alloy's textfile collector over the `/:/host/root:ro` mount (spec `00071`); long-lived services use `/metrics` |
| `zcrypto-archive-pull` | nas | hourly pull+verify loop into `/volume1/ZhaoCrypto`; runs the gate export | container, journald logging |
| gate export | nas | `/volume1/docker/zcrypto-archive/textfile/gate.prom` — `zcrypto_gate_{status,streak_days,journal_pull_lag_seconds,mismatch_total,cache_*,export_*}` | refreshed each archive-pull loop (~hourly, `ARCHIVE_PULL_INTERVAL` 3600 s); the gate score itself advances per 4 h engine cycle |
| Caddy (mTLS edge) | zaccess | `/etc/caddy/Caddyfile`; ACME certs under `/var/lib/caddy`; CA + pins in `/etc/caddy/{zaccess_ca.crt,pinned-leaves/,nas-upstream-ca.pem}` | serves `:80` (ACME HTTP-01 + redirect) and `:443` (mTLS, require_and_verify); admin `:2019` localhost |
| `zaccess0` WireGuard | zaccess (10.99.0.1) ↔ zcrypto-ops (10.99.0.2) | `/etc/wireguard/zaccess0.conf`; `:51820/udp`; `AllowedIPs /32` each way (no LAN route) | `wg show zaccess0` |
| socket-proxyd relays | zaccess (`zaccess-ssh-proxy` :20022→10.99.0.2:22), zcrypto-ops (`zaccess-nas-proxy` 10.99.0.2:5001→z-home-storage.zhaow.pro:5001) | raw TCP byte-copy, no TLS termination (SSH stays e2e-encrypted; the NAS TLS is e2e Caddy↔DSM) | systemd `.socket` units |
| agentboard (G2) | zcrypto-ops | web terminal onto tmux, bound `10.99.0.2:4040`; **LIVE** — `access_ops_agentboard_live` is `true` in `host_vars/zcrypto-ops`, `false` being only the role default | behind the tmux. mTLS vhost |
| access probe timers | zaccess + zcrypto-ops | `zaccess-probe(.timer)` → `zaccess.prom`: WireGuard handshake age + TLS `notAfter` (edge certs on zaccess, `target=nas-dsm` on ops) | scraped by each host's Alloy textfile collector |

- Engine cycles are 4-hourly at **00/04/08/12/16/20 UTC** (+ ~90 s settle). Converge discipline (windows, re-run cutoff): `.claude/skills/zcrypto-rollout-image/SKILL.md` → *Engine converges*.
- Both app services read Loki push creds from `/opt/zcrypto-capture/logship-secrets.env` (one file per host; the engine reuses the capture role's render); compose marks the env_file `required: false`, so absence never fails the render — the **engine** (compose-baked `--ship-logs`) crash-loops for want of the Loki vars, while **capture** silently starts on stdout only (its ship flag lives inside the file).
- Capture, engine, ops, and the NAS archive-pull all run the shared image repo `ghcr.io/zhaow-de/zcrypto-capture` with **independent** digests — match the pin to the service, never to the repo.

## Storage topology

- The NAS exports `/volume1/ZhaoCrypto`, mounted at `/mnt/zhao-crypto` on the workstation and the ops node (ops: ro by role default; the workstation mount's flags are not load-bearing). **Never write through the mount** — a soft-mounted write can silently corrupt on timeout (spec `00056` D2); pushes go only via the `nas-hot:` rrsync channel. Read datasets in place — never ssh-pull what the mount already serves.
- Under `/mnt/zhao-crypto`: `hot/` (the canonical datasets: `ohlc-full`, `ohlc-15m`, `ohlc-reach`, `ohlc-holdout-*`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`), `engine-journal/` (pulled replica — the engine host is authoritative; check freshness before trusting the tail), `capture-segments/`, `capture-segments-red/`, `capture-reconciled/` (**a PULLED REPLICA whose `reconcile-ledger.jsonl` lags the live one by up to one NAS `archive-pull` cycle and carries no marker of that lag** — the reconciler appends only to `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl` under `ops_data_dir`, which the NAS pulls over the read-only `sync_reconciled` rrsync channel, so **read the ops path when the question is about a recently booked hour**), `kraken-ohlcvt-updates/`, `kraken-trades/`, `l2-panel/`, `liquidations/`.
- **Not replicated anywhere: the engine price store** (`/var/lib/zcrypto-engine/store`, zcrypto only). Anything needing it reads the engine host.
- **Docker images are removed only by `infra/scripts/prune-host-images.py <host>`, run at pins-update time** (dry-run by default; `--apply` removes) — no role or timer prunes them, and every converge pulls another capture image. On the capture hosts this is a data-loss guard, not tidiness: capture **stops appending below 1 GiB free** (`DEFAULT_MIN_FREE_BYTES`, `cli/capture/gap_monitor.py`) and L2 is unbackfillable. Ordering and the keep-set rule: `.claude/skills/zcrypto-rollout-image/SKILL.md` → *Shared converge mechanics*.

## Reboots

- **The capture VPSes never reboot themselves** — patches still auto-install; *Capture · reboot pending (attended)* — a Grafana rule paging Slack, not the dead-man domain — fires until you reboot. The ops node still auto-reboots at 02:25. The on-host 21:25 / 22:25 times no longer fire but are kept on purpose — they are the measured slots that already satisfy the Schedule bullet, and the base role's window-collision assert still reads their host_vars, so never delete them as dead config.
- **Reboot SECONDARY first, then primary** — the same canary order as an image rollout: if the kernel bricks the secondary, the primary is never touched.
- Schedule: ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation, and on the primary right after a completed engine cycle. Measure from the archive, don't guess. **And never inside a published Kraken maintenance window** — the ~83 s reboot gap landing inside one conflates two failure sources exactly where the ledger is least readable; same feed and same publication lag as the converge rule in `.claude/rules/fleet-deploys.md`, which carries both — an empty feed at planning time is never evidence the window is clear, so read the feed again immediately before.
- Expect a ~83 s capture gap; both containers self-restart.
- **Verify by outcome before touching the next host** — the same checks a converge owes, which is why the reboot does not carry its own: every book stream's next `<HH>.parquet` begins at `:00:00.0x`, the NAS archive-pull loop's next pull reports `failed=0`, and `infra/scripts/continuity.py` on a PULLED copy shows no new truncated hours. On the primary, additionally: the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and the restart marker is the container's `.State.StartedAt`, never the reboot command's return time.

## Drills — how to induce a fault without touching production

Recipes for inducing a fault without touching production. The telemetry-tier drill program — every drill's preconditions, induction and bounds — is `infra/runbooks/drills-telemetry.md`.

**Inducing a fault on a throwaway subject, and what a drill's latency does and does not prove**, are `infra/runbooks/drills-telemetry.md`'s standing rules and bound derivations.

**The node-exporter textfile directory is the alert path's own injection point** — that recipe is a standing rule on the same page.

## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red}`.
- The bridgehead ships Prometheus under `host="zaccess"` (native apt Alloy, not a container — so no image digest and no pins row; see `infra/runbooks/zaccess.md`'s `zaccess-alloy-converge`). Its `zaccess_wireguard_handshake_age_seconds` and `zaccess_tls_not_after_seconds` also arrive under `host="ops"` from the ops-side probe — the tunnel and NAS cert are watched from both ends.
- Prometheus carries the same four `host` values **plus** `host="primary"`/`"secondary"` on one series each (`zcrypto_reconcile_trade_deficit_rows_total`, `cli/archive/command.py` — the one reconcile series using `host=` where its siblings use `source=`; the pre-existing textfile label wins over the ops Alloy's `external_labels host="ops"`) — do not assume `host=` is uniform when keying rules or queries.
