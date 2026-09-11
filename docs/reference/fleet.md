# Fleet topology

What runs where: hosts, services, data paths, mounts, replication, telemetry labels. Read it before running a command on a fleet host or naming a path there; a change to what-runs-where updates this file in the same change. Running digests are [fleet-pins.md](fleet-pins.md); dataset schemas are the data catalogs'. This file holds state, not history — a measurement, an incident or a drill goes to git, a runbook or the drill log — and `tests/test_fleet_contracts.py` refuses a date, a table cell, a bullet or a paragraph past its cap, a heading outside the six sections and anything nested below them.

## Hosts

| host | ssh | ansible groups | role | trust boundary |
| --- | --- | --- | --- | --- |
| `zcrypto` | `ssh zcrypto` | `capture_host`, `engine_host` | L2 capture **primary**; the trade engine | holds the live Kraken trade key as container env (CLAUDE.md `## Secrets`) |
| `zcrypto-red` | `ssh red` | `capture_host` | L2 capture **secondary** | no trade key; not in `engine_host` |
| `zcrypto-ops` | `ssh hp` | `ops_host`, `observed` | compute tier (spec `00051`): archive reconcile and backfill, liquidations poller, panel materialize | no trade key; no `uv` — it runs containers, not the repo CLI |
| `nas` | `ssh nas` | `nas_host`, `observed` | archive and custody (spec `00048` Role A), gate export, NFS server | DSM owns the OS; ansible manages the zcrypto payload alone. sftp chroots at `/volume1`; `nas-hot:` is an rrsync endpoint into `hot/` (`infra/runbooks/nas.md`'s `nas-file-transfer`) |
| `zaccess` | `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` | `access_host`, `observed` | internet bridgehead (spec `00075`): WireGuard tunnel head, Caddy mTLS edge, SSH and NAS socket-proxyd relays | Linode VPS; no trade key, no capture data, no containers — all of it re-issuable. Holds the Grafana Cloud push creds and the public half of the mTLS CA; the CA key stays in the vault |
| workstation | — | `workstation` (local) | research node; the repo checkout | `data/engine-store` and `data/engine-journal` are the retired pre-VPS engine state, not live data |

- SSH as `zcrypto-deploy`, passwordless sudo, so non-interactive `sudo` over ssh works; root is break-glass by key alone, installed by hand at bootstrap. The bridgehead's break-glass is Linode LISH, the provider's serial console (`os_hardening` keeps `ttyS0` for it).
- The trade key reaches the engine as container env, `/opt/zcrypto-engine/engine.env` (`0600 root:root`, the rendered compose's `env_file`); an ad-hoc read that needs it is `infra/runbooks/engine-procedures.md`'s `engine-adhoc-key-read`.
- The bridgehead's sshd allows two authentication tries, so `infra/ansible/scripts/run.sh` offers its deploy key first when `--limit zaccess` names it, and it converges through `converge.sh` like the other hosts. Its Alloy is a native deb followed from apt — no digest, no pins row, no bake: `infra/runbooks/zaccess.md`'s `zaccess-alloy-converge`. The mTLS client pins are PEMs under `roles/access/files/pinned-leaves/`, globbed into the Caddyfile at converge; revoking one is `zaccess-revoke-client-cert` on the same page.
- Route53: `zaccess.zhaow.me` is its own hosted zone, delegated from `zhaow.me`; the apex `A`/`AAAA`, the `tmux.` and `nas.` `CNAME`s and the `CAA` live in that child zone, created by hand (spec `00075` D18) — an apex record in the parent beside the `NS` delegation is shadowed.
- The agentboard unit's node and package are installed under nvm as `zhaow`, not by the role, so an upgrade is a restart: `infra/runbooks/ops-node.md`'s `agentboard-node-upgrade`.

## Services and instruments

| service | host(s) | data / output | endpoint |
| --- | --- | --- | --- |
| `zcrypto-capture` | zcrypto, zcrypto-red | `/var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` | `/metrics` `127.0.0.1:9101` |
| `zcrypto-engine` | zcrypto | `/var/lib/zcrypto-engine/{store,journal}` (bind mounts; compose at `/opt/zcrypto-engine`); a journal day-dir: `cycle-HH.json` (written last, after validation), `orders.jsonl`, `snapshots/` | `/metrics` `127.0.0.1:9102` |
| the red button | zcrypto | `/usr/local/sbin/zcrypto-flatten` (`750 root:root`), rendered by the engine converge from `roles/engine/templates/zcrypto-flatten.sh.j2`; `infra/runbooks/engine-procedures.md`'s `engine-flatten` | — |
| liquidations poller | zcrypto-ops | under `ops_data_dir` = `/var/lib/zcrypto-ops` (`/data` inside the container) | `/metrics` `127.0.0.1:9103` |
| `grafana-alloy` | zcrypto, zcrypto-red, zcrypto-ops, nas | scrape jobs: `capture_app`, `engine_app` on the capture hosts (`engine_app` reads 0 on red); `liquidations_app`, `healthchecks` on ops; host and textfile on the nas; journal logs | self-metrics `:12345` |
| ops timers | zcrypto-ops | `zcrypto-{archive-pull,panel-materialize,tape-bars,verify-replay,verified-replay}.service` (a `docker run` per tick); `grafana-{watchdog,keepalive}` (scripts) | `.prom` into `/var/lib/zcrypto-ops/textfile` (all but the watchdog), read by the ops Alloy textfile collector |
| capture and engine timers | zcrypto, zcrypto-red | `zcrypto-capture-prune` (03:17), `zcrypto-reboot-check` (15-min), `zcrypto-clock-offset` (5-min); on zcrypto also `zcrypto-engine-journal-prune` (01:23, day-dirs, 60 d, keep-newest 60) | `.prom` into `/var/lib/zcrypto-node-textfile`, read by Alloy's textfile collector over the `/:/host/root:ro` mount (spec `00071`) |
| `zcrypto-archive-pull` | nas | hourly pull and verify into `/volume1/ZhaoCrypto`; runs the gate export | a container, journald logging |
| gate export | nas | `/volume1/docker/zcrypto-archive/textfile/gate.prom`: `zcrypto_gate_{status,streak_days,journal_pull_lag_seconds,mismatch_total,cache_*,export_*}` | refreshed each archive-pull loop (`ARCHIVE_PULL_INTERVAL` 3600 s); the gate score advances per 4 h engine cycle |
| Caddy (mTLS edge) | zaccess | `/etc/caddy/Caddyfile`; ACME certs under `/var/lib/caddy`; CA and pins in `/etc/caddy/{zaccess_ca.crt,pinned-leaves/,nas-upstream-ca.pem}` | `:80` (ACME HTTP-01, redirect), `:443` (mTLS, require_and_verify); admin `:2019` on localhost |
| `zaccess0` WireGuard | zaccess (10.99.0.1) ↔ zcrypto-ops (10.99.0.2) | `/etc/wireguard/zaccess0.conf`; `:51820/udp`; `AllowedIPs /32` each way, no LAN route | `wg show zaccess0` |
| socket-proxyd relays | zaccess (`zaccess-ssh-proxy` :20022→10.99.0.2:22), zcrypto-ops (`zaccess-nas-proxy` 10.99.0.2:5001→z-home-storage.zhaow.pro:5001) | raw TCP byte-copy, no TLS termination | systemd `.socket` units |
| agentboard (G2) | zcrypto-ops | web terminal onto tmux, bound `10.99.0.2:4040`; live — `access_ops_agentboard_live: true` in `host_vars/zcrypto-ops` | behind the `tmux.` mTLS vhost |
| access probe timers | zaccess, zcrypto-ops | `zaccess-probe(.timer)` → `zaccess.prom`: WireGuard handshake age and TLS `notAfter` (edge certs on zaccess, `target=nas-dsm` on ops) | each host's Alloy textfile collector |

- Engine cycles are 4-hourly at 00/04/08/12/16/20 UTC (+ ~90 s settle); the converge windows and the re-run cutoff are `.claude/rules/fleet-deploys.md` and `.claude/skills/zcrypto-rollout-image/SKILL.md` → *Engine converges*.
- Both app services read Loki push creds from `/opt/zcrypto-capture/logship-secrets.env` (one per host; the engine reuses the capture role's render), an `env_file` marked `required: false`: absent, the engine crash-loops for want of the Loki vars (`--ship-logs` is compose-baked) and capture starts on stdout alone.

## Storage topology

- The NAS exports `/volume1/ZhaoCrypto`, mounted at `/mnt/zhao-crypto` on the workstation and the ops node (ops: read-only by role default). Never write through the mount — a soft-mounted write can corrupt silently on timeout (spec `00056` D2); a push goes through the `nas-hot:` rrsync channel, and a dataset is read in place, not ssh-pulled (no count command: a write through the mount leaves no record in the tree).
- Under `/mnt/zhao-crypto`: `hot/` (the canonical datasets: `ohlc-full`, `ohlc-15m`, `ohlc-reach`, `ohlc-holdout-*`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`), `engine-journal/`, `capture-segments/`, `capture-segments-red/`, `capture-reconciled/`, `kraken-ohlcvt-updates/`, `kraken-trades/`, `l2-panel/`, `liquidations/`. The journal and the reconciled tree are pulled replicas of the hosts' own paths: `capture-reconciled/reconcile-ledger.jsonl` lags the ops copy, `/var/lib/zcrypto-ops/capture-reconciled/reconcile-ledger.jsonl`, by up to one archive-pull cycle with no marker of the lag, so a question about a recent hour reads the ops path.
- Not replicated: the engine price store, `/var/lib/zcrypto-engine/store` on zcrypto.
- Docker images are removed only by `infra/scripts/prune-host-images.py <host>`, at pins-update time: no role or timer prunes them, and each converge pulls another capture image. On a capture host that is a data-loss guard — capture stops appending below 1 GiB free (`DEFAULT_MIN_FREE_BYTES`, `cli/capture/gap_monitor.py`). Ordering and the keep-set: `.claude/skills/zcrypto-rollout-image/SKILL.md` → *Shared converge mechanics* (set: the non-comment, non-Markdown lines under `infra/`, `cli/` and `.claude/` invoking `docker rmi`, `docker image rm|prune` or `docker system prune`, the script and counter excluded; count: `infra/scripts/count-list.sh image-removals-outside-the-pruner`).

## Reboots

- The capture VPSes never reboot themselves: patches auto-install, and *Capture · reboot pending (attended)* — a Grafana rule paging Slack — fires until you reboot (set: the two capture hosts' `base_unattended_upgrades_automatic_reboot`, in `host_vars` or `group_vars/capture_host`; count: `infra/scripts/count-list.sh capture-hosts-with-automatic-reboot`). The ops node auto-reboots at 02:25; the capture hosts' 21:25 and 22:25 `host_vars` slots stay, read by the base role's window-collision assert.
- Reboot the secondary first, then the primary — the canary order of an image rollout: a kernel that bricks the secondary leaves the primary untouched.
- Schedule: ≥ 1 h from each 4 h bar boundary and off the hour boundary; ≥ 1 h between hosts; the primary in the book-traffic trough, right after a completed engine cycle, measured from the archive rather than guessed; and never inside a published Kraken maintenance window, read again immediately before — `.claude/rules/fleet-deploys.md` carries the feed (no count command: a reboot leaves no row in the tree; the deploy log records converges).
- Expect a ~83 s capture gap; both containers self-restart.
- Verify by outcome before touching the next host — the checks a converge owes: on the pulled copy, every book stream's next `<HH>.parquet` begins where the other host's does (identical first rows), not at a fixed `:00:00.0x`; the NAS archive-pull's next cycle logs `pull complete … failed=0` for every verified channel; `infra/scripts/continuity.py` on a pulled copy shows no new truncated hours; on the primary, the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and the restart marker is the container's `.State.StartedAt`, never the reboot command's return time (no count command: a reboot leaves no row in the tree).

## Drills

Inducing a fault without touching production — the recipes, the standing rules on a throwaway subject and what a drill's latency proves — is `infra/runbooks/drills-telemetry.md`; the order path's drills are `infra/runbooks/drills-order-path.md`; a drill run is an entry in `docs/reference/drill-log.md`.

## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red}`.
- The bridgehead ships Prometheus under `host="zaccess"`; its `zaccess_wireguard_handshake_age_seconds` and `zaccess_tls_not_after_seconds` also arrive under `host="ops"` from the ops-side probe, so the tunnel is watched from both ends; the certificates are three, one per target — the bridgehead reads its own edge certificate for each of the `tmux` and `nas` vhosts, the ops probe reads the NAS's DSM certificate as `nas-dsm`, and no other probe reads them.
- Prometheus carries the same four `host` values plus `host="primary"`/`"secondary"` on one series, `zcrypto_reconcile_trade_deficit_rows_total` (`cli/archive/command.py` — the reconcile series keyed by `host=` where its siblings use `source=`; the textfile label wins over the ops Alloy's `external_labels`): `host=` is not uniform when keying a rule or a query.
