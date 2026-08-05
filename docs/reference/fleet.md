# Fleet topology

What runs where: host roles, data paths, mounts, replication, telemetry endpoints. Consult this before running commands on a fleet host or guessing a path; any change to what-runs-where updates this file **in the same change**. Dataset schemas/provenance are the data catalogs' job; running digests are [fleet-pins.md](fleet-pins.md).

## Hosts

| host | ssh | ansible groups | role | trust boundary |
| --- | --- | --- | --- | --- |
| `zcrypto` | `ssh zcrypto` | `capture_host`, `engine_host` | L2 capture **primary** + the trade engine | holds the **live Kraken trade key** (as container env — see CLAUDE.md `## Secrets`) |
| `zcrypto-red` | `ssh red` | `capture_host` | L2 capture **secondary** only | never joins `engine_host`; no trade key |
| `zcrypto-ops` | `ssh hp` | `ops_host`, `observed` | compute tier (spec `00051`): archive reconcile/backfill, liquidations poller, panel materialize | no trade key (D10); **no `uv`** — it runs containers, not the repo CLI |
| `nas` | `ssh nas` | `nas_host`, `observed` | archive/custody (spec `00048` Role A), gate export, NFS server | DSM owns the OS; ansible manages only the zcrypto payload. **`docker` is at `/usr/local/bin/docker` and is NOT on a non-interactive ssh `PATH`** — call it by full path and with `sudo`, or `docker ps` returns empty and reads as "no containers" rather than "command not found" |
| `zaccess` | `ssh -p 10022 zcrypto-deploy@zaccess.zhaow.me` | `access_host`, `observed` | internet bridgehead (spec `00075`): WireGuard tunnel head, Caddy mTLS edge, SSH + NAS socket-proxyd relays | Linode public-IP VPS; **no trade key, no capture data, no containers** — everything on it is re-issuable (certs re-ACME, keys vaulted), so losing it is re-provisioning, not data loss. Holds the Grafana Cloud push creds (same class as the capture VPSes) and the mTLS **CA cert + pinned leaves** (public only — the CA private key never leaves the vault) |
| workstation | — | `workstation` (local) | research node; the repo checkout | its `data/engine-store`/`engine-journal` are the **retired** pre-VPS engine state, not live data |

- SSH as `zcrypto-deploy` (**passwordless sudo** — non-interactive `sudo` over ssh works). Root is key-only break-glass, installed by hand at bootstrap.
- **`zaccess` converges need a single-identity SSH agent.** `ssh_hardening` sets `MaxAuthTries 2` on the bridgehead, and `scripts/run.sh` loads all five fleet deploy keys with `deploy_zaccess` **last**, so a multi-key agent exhausts the limit before offering it → `Too many authentication failures`. Converge it not through `run.sh` but with only its own key: `eval "$(ssh-agent -s)"; uv run ansible-vault view --vault-password-file scripts/vault-pass.sh files/deploy_zaccess_ed25519 | ssh-add -; ANSIBLE_SSH_EXTRA_ARGS="-o IdentitiesOnly=yes -o IdentityFile=$PWD/files/deploy_zaccess_ed25519.pub" uv run ansible-playbook site.yml --limit zaccess --tags access` (run from `infra/ansible/`; `ansible.cfg` supplies the vault password independently). The other hosts' keys sit earlier in `run.sh`'s load order, so only `zaccess` trips this.
- **The bridgehead's Alloy takes NO digest operand and owes no bake** — unlike capture (`capture_alloy_digest`) and ops (`ops_alloy_digest`), which both refuse an ordinary converge after a config edit. It is a **native deb** held at `access_alloy_version` via `dpkg_selections`, and its `config.alloy` is an **ungated `copy`**: every converge ships it, so a hand edit cannot outlive the next run and there is no drift assert to satisfy. A keep-regex or config change therefore converges with a plain `site.yml --limit` on that host. Recorded because the absence of a gate reads as an oversight and invites someone to add a digest that does not exist.

- **The bridgehead's break-glass is Linode LISH** (serial console, provider panel) — root key-only SSH is the normal path; LISH is the recovery path when SSH is unreachable (`os_hardening` keeps `ttyS0` for it).
- **Route53: `zhaow.me` delegates `zaccess.zhaow.me` to its own hosted zone** (`Z0912077…`), where the apex `A`/`AAAA` (→ the Linode) and the `tmux.`/`nas.` `CNAME`s and the Let's Encrypt `CAA` live. The apex address records MUST live in that child zone, not the parent — a parent `A` co-located with the `NS` delegation is shadowed and never served (fixed 2026-07-29). DNS is created by hand (spec `00075` D18).
- **Revoke a client cert** = delete its PEM from `roles/access/files/pinned-leaves/` and converge — the re-rendered Caddyfile drops the pin, so the leaf is refused at the next handshake. The host copy has no `--delete`, so **also `rm /etc/caddy/pinned-leaves/<name>.pem` on the bridgehead** for hygiene; it is inert either way (the Caddyfile no longer lists it), proven by the 2026-07-30 revocation drill.
- **A node upgrade for the agentboard (G2) unit needs no converge**: its `ExecStart` sources nvm and execs `agentboard` at start, so `nvm install <new> && nvm alias default <new> && npm i -g @gbasin/agentboard@<pin> && sudo systemctl restart zaccess-agentboard` picks up the new node. Never run a test/second agentboard on the ops **default** tmux socket (collides with the live one + the durable session — it has crashed the tmux server); isolate any test with `TMUX_TMPDIR`, and never blanket-`pkill agentboard` (kills the live systemd unit). **And check `echo $TMUX` first: a Claude Code session may itself be running inside the tmux agentboard fronts, so a server-killing action there is self-termination — the session dies mid-command with no report.**

## Services and instruments

| service | host(s) | data / output | endpoint |
| --- | --- | --- | --- |
| `zcrypto-capture` | zcrypto, zcrypto-red | `/var/lib/zcrypto-capture/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` | `/metrics` `127.0.0.1:9101` |
| `zcrypto-engine` | zcrypto | `/var/lib/zcrypto-engine/{store,journal}` (bind mounts; compose at `/opt/zcrypto-engine`); journal day-dirs hold `cycle-HH.json` (written **last**, after validation), `orders.jsonl`, `snapshots/` | `/metrics` `127.0.0.1:9102` |
| liquidations poller | zcrypto-ops | under `ops_data_dir` = `/var/lib/zcrypto-ops` (container-visible as `/data`) | `/metrics` `127.0.0.1:9103` |
| `grafana-alloy` | all four | scrape jobs: `capture_app`+`engine_app` (both capture hosts; `engine_app` reads 0 on red by design), `liquidations_app`+`healthchecks` (ops), host/textfile only (nas); + journal log sources | self-metrics `:12345` |
| ops timers | zcrypto-ops | `zcrypto-{archive-pull,panel-materialize,verify-replay,verified-replay}.service` (+ grafana-watchdog) — ephemeral `docker run` per tick; `.prom` outputs under `/var/lib/zcrypto-ops/textfile` | scraped by the ops Alloy textfile collector |
| capture/engine timers | zcrypto, zcrypto-red | `zcrypto-capture-prune` (03:17, segments), `zcrypto-reboot-check` (every 15 min, pending-reboot gauge), and — zcrypto only — `zcrypto-engine-journal-prune` (01:23, journal day-dirs, 60 d + a keep-newest-60 floor) | **`zcrypto-reboot-check` and `zcrypto-engine-journal-prune` publish `.prom` into `/var/lib/zcrypto-node-textfile`**, read by Alloy's textfile collector through the existing `/:/host/root:ro` mount (spec `00071`); long-lived services use `/metrics` instead. **`zcrypto-capture-prune` publishes no metric** — it predates the transport and is observable only through its journald line in Loki, so the staleness alerts do not cover it |
| `zcrypto-archive-pull` | nas | hourly pull+verify loop into `/volume1/ZhaoCrypto`; runs the gate export | container, journald logging |
| gate export | nas | `/volume1/docker/zcrypto-archive/textfile/gate.prom` — `zcrypto_gate_{status,streak_days,journal_pull_lag_seconds,mismatch_total,cache_*,export_*}` | refreshed each archive-pull loop (~hourly, `ARCHIVE_PULL_INTERVAL` 3600 s); the gate score itself advances per 4 h engine cycle |
| Caddy (mTLS edge) | zaccess | `/etc/caddy/Caddyfile`; ACME certs under `/var/lib/caddy`; CA + pins in `/etc/caddy/{zaccess_ca.crt,pinned-leaves/,nas-upstream-ca.pem}` | serves `:80` (ACME HTTP-01 + redirect) and `:443` (mTLS, require_and_verify); admin `:2019` localhost |
| `zaccess0` WireGuard | zaccess (10.99.0.1) ↔ zcrypto-ops (10.99.0.2) | `/etc/wireguard/zaccess0.conf`; `:51820/udp`; `AllowedIPs /32` each way (no LAN route) | `wg show zaccess0` |
| socket-proxyd relays | zaccess (`zaccess-ssh-proxy` :20022→10.99.0.2:22), zcrypto-ops (`zaccess-nas-proxy` 10.99.0.2:5001→192.168.100.5:5001) | raw TCP byte-copy, no TLS termination (SSH stays e2e-encrypted; the NAS TLS is e2e Caddy↔DSM) | systemd `.socket` units |
| agentboard (G2) | zcrypto-ops | web terminal onto tmux, bound `10.99.0.2:4040`; **spike-gated** on `access_ops_agentboard_live` (default false) | behind the tmux. mTLS vhost |
| access probe timers | zaccess + zcrypto-ops | `zaccess-probe(.timer)` → `zaccess.prom`: WireGuard handshake age + TLS `notAfter` (edge certs on zaccess, `target=nas-dsm` on ops) | scraped by each host's Alloy textfile collector |

- Engine cycles are 4-hourly at **00/04/08/12/16/20 UTC** (+ ~90 s settle). Converge discipline (windows, re-run cutoff): `capture-deploys.md` → *Engine converges*.
- Both app services read Loki push creds from `/opt/zcrypto-capture/logship-secrets.env` (one file per host; the engine reuses the capture role's render); compose marks the env_file `required: false`, so absence never fails the render — the **engine** (compose-baked `--ship-logs`) crash-loops for want of the Loki vars, while **capture** silently starts on stdout only (its ship flag lives inside the file).
- Capture, engine, ops, and the NAS archive-pull all run the shared image repo `ghcr.io/zhaow-de/zcrypto-capture` with **independent** digests — match the pin to the service, never to the repo.

## Storage topology

- The NAS exports `/volume1/ZhaoCrypto`, mounted at `/mnt/zhao-crypto` on the workstation and the ops node (ops: ro by role default; the workstation mount's flags are not load-bearing). **Never write through the mount** — a soft-mounted write can silently corrupt on timeout (spec `00056` D2); pushes go only via the `nas-hot:` rrsync channel. Read datasets in place — never ssh-pull what the mount already serves.
- Under `/mnt/zhao-crypto`: `hot/` (the canonical datasets: `ohlc-full`, `ohlc-15m`, `ohlc-reach`, `ohlc-holdout-*`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`), `engine-journal/` (pulled replica — the engine host is authoritative; check freshness before trusting the tail), `capture-segments/`, `capture-segments-red/`, `capture-reconciled/`, `kraken-ohlcvt-updates/`, `kraken-trades/`, `l2-panel/`, `liquidations/`.
- **Not replicated anywhere: the engine price store** (`/var/lib/zcrypto-engine/store`, zcrypto only). Anything needing it reads the engine host.

## Reboots

- **The capture VPSes never reboot themselves** — patches still auto-install; *Capture · reboot pending (attended)* — a Grafana rule paging Slack, not the dead-man domain — fires until you reboot. The ops node still auto-reboots at 02:25. The on-host 21:25 / 22:25 times no longer fire but are kept on purpose — they are the measured slots that already satisfy the Schedule bullet, and the base role's window-collision assert still reads their host_vars, so never delete them as dead config.
- **Reboot SECONDARY first, then primary** — the same canary order as an image rollout: if the kernel bricks the secondary, the primary is never touched.
- Schedule: ≥ 1 h from any 4h bar boundary, off the hour boundary, primary in the measured book-traffic trough, ≥ 1 h host separation, and on the primary right after a completed engine cycle. Measure from the archive, don't guess.
- Expect a ~83 s capture gap; both containers self-restart.

## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red}`.
- The bridgehead ships Prometheus under `host="zaccess"` (native apt Alloy, not a container — its version is pinned in `fleet-pins.md`, there is no image digest). Its `zaccess_wireguard_handshake_age_seconds` and `zaccess_tls_not_after_seconds` also arrive under `host="ops"` from the ops-side probe — the tunnel and NAS cert are watched from both ends.
- Prometheus carries the same four `host` values **plus** `host="primary"`/`"secondary"` on one series each (`zcrypto_reconcile_trade_deficit_rows_total`, `cli/archive/command.py` — the one reconcile series using `host=` where its siblings use `source=`; the pre-existing textfile label wins over the ops Alloy's `external_labels host="ops"`) — do not assume `host=` is uniform when keying rules or queries.
