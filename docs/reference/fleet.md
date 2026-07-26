# Fleet topology

What runs where: host roles, data paths, mounts, replication, telemetry endpoints. Consult this before running commands on a fleet host or guessing a path; any change to what-runs-where updates this file **in the same change**. Dataset schemas/provenance are the data catalogs' job; running digests are [fleet-pins.md](fleet-pins.md).

## Hosts

| host | ssh | ansible groups | role | trust boundary |
| --- | --- | --- | --- | --- |
| `zcrypto` | `ssh zcrypto` | `capture_host`, `engine_host` | L2 capture **primary** + the trade engine | holds the **live Kraken trade key** (as container env — see CLAUDE.md `## Secrets`) |
| `zcrypto-red` | `ssh red` | `capture_host` | L2 capture **secondary** only | never joins `engine_host`; no trade key |
| `zcrypto-ops` | `ssh hp` | `ops_host`, `observed` | compute tier (spec `00051`): archive reconcile/backfill, liquidations poller, panel materialize | no trade key (D10); **no `uv`** — it runs containers, not the repo CLI |
| `nas` | `ssh nas` | `nas_host`, `observed` | archive/custody (spec `00048` Role A), gate export, NFS server | DSM owns the OS; ansible manages only the zcrypto payload. **`docker` is at `/usr/local/bin/docker` and is NOT on a non-interactive ssh `PATH`** — call it by full path and with `sudo`, or `docker ps` returns empty and reads as "no containers" rather than "command not found" |
| workstation | — | `workstation` (local) | research node; the repo checkout | its `data/engine-store`/`engine-journal` are the **retired** pre-VPS engine state, not live data |

- SSH as `zcrypto-deploy` (**passwordless sudo** — non-interactive `sudo` over ssh works). Root is key-only break-glass, installed by hand at bootstrap.

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

- Engine cycles are 4-hourly at **00/04/08/12/16/20 UTC** (+ ~90 s settle). Converge discipline (windows, re-run cutoff): `capture-deploys.md` → *Engine converges*.
- Both app services read Loki push creds from `/opt/zcrypto-capture/logship-secrets.env` (one file per host; the engine reuses the capture role's render); compose marks the env_file `required: false`, so absence never fails the render — the **engine** (compose-baked `--ship-logs`) crash-loops for want of the Loki vars, while **capture** silently starts on stdout only (its ship flag lives inside the file).
- Capture and engine share the image repo `ghcr.io/zhaow-de/zcrypto-capture` but pin **independent** digests — never read one service's pin as the other's.

## Storage topology

- The NAS exports `/volume1/ZhaoCrypto`, mounted at `/mnt/zhao-crypto` on the workstation and the ops node (ops: ro by role default; the workstation mount's flags are not load-bearing). **Never write through the mount** — a soft-mounted write can silently corrupt on timeout (spec `00056` D2); pushes go only via the `nas-hot:` rrsync channel. Read datasets in place — never ssh-pull what the mount already serves.
- Under `/mnt/zhao-crypto`: `hot/` (the canonical datasets: `ohlc-full`, `ohlc-15m`, `ohlc-reach`, `ohlc-holdout-*`, `derivatives-funding`, `derivatives-oi`, `snapshots`, `universe`), `engine-journal/` (pulled replica — the engine host is authoritative; check freshness before trusting the tail), `capture-segments/`, `capture-segments-red/`, `capture-reconciled/`, `kraken-ohlcvt-updates/`, `kraken-trades/`, `l2-panel/`, `liquidations/`.
- **Not replicated anywhere: the engine price store** (`/var/lib/zcrypto-engine/store`, zcrypto only). Anything needing it reads the engine host.

## Telemetry labels

- Loki labels: `container`, `host`, `job`, `level`, `service_name`; `host ∈ {nas, ops, zcrypto, zcrypto-red}`.
- Prometheus carries the same four `host` values **plus** `host="primary"`/`"secondary"` on one series each (`zcrypto_reconcile_trade_deficit_rows_total`, `cli/archive/command.py` — the one reconcile series using `host=` where its siblings use `source=`; the pre-existing textfile label wins over the ops Alloy's `external_labels host="ops"`) — do not assume `host=` is uniform when keying rules or queries.
