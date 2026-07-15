# Ops-node stack (spec 00051, compute tier)

The home ops node (`zcrypto-ops`, `ssh hp`) is the fleet's compute tier: a home-LAN box converged by the third `site.yml` play (roles `base`/`chrony`/`docker`/`ops` — no `hardening`/`firewall`/`fail2ban`, it is not internet-facing). Charter (spec 00051 D10): **no trade key, never `engine_host`, pull-only transport** — it pulls everything it consumes from the NAS and is pulled *from* for everything it produces.

Everything below is installed by the `ops` Ansible role (`infra/ansible/roles/ops/`) **only when the pinned image digest is supplied** (`-e ops_image_digest=sha256:<...>`, always the **default AVX** build of `ghcr.io/zhaow-de/zcrypto-capture`, never `-compat`, never `:latest`); a converge without the digest skips those installs rather than rendering artifacts that point at a broken image reference.

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
