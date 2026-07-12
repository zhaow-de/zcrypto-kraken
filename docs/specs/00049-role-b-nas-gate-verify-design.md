# Role B — the always-on NAS gate-verify tier + NAS telemetry (design)

**Spec:** `00049` · **Iteration:** iter-094 (attended) · **Supersedes for gate-ops:** the workstation `zcrypto-engine-gateops` timer (spec 00042).

**Goal.** Increment 2 of the three-tier topology (spec `00048`): move Stage-6a gate scoring off the intermittently-online workstation onto the **always-on NAS**, and ship NAS host/container/gate telemetry to the **single** Grafana Cloud dashboard. Role B is pure compute + telemetry layered on Role A's already-live journal data path.

## The determinism finding (why this is safe — measured, not assumed)

T0029's pivotal residual — can the NAS's no-AVX `polars-runtime-compat` reproduce the VPS's AVX-computed (`polars-runtime-32`) gate verdict? — was **measured** this iteration against the 8 VPS-journaled cycles (2026-07-11 00/04/08/12/16/20 + 2026-07-12 00/04):

| Path | AVX control (workstation, `runtime-32`) | Gold standard (real Atom NAS, `runtime-compat` + baseline numpy) |
| -- | -- | -- |
| **fast** (the gate path — `report`) | 8/8 `ok`, all `0.00e+00` | 8/8 `ok`, all `0.00e+00` |
| **verified** (deep-check) | ~`1e-18` same-runtime float noise, all `ok` (≤ 1e-6) | 1st cycle `0.00e+00`; slow — did not finish 8 cycles in 40 min |

**Conclusion:** the fast path is **bit-identical cross-runtime** on the real Atom (the exact-rational big-integer builder routes no float reductions through polars/numpy on that path — a genuine cross-runtime *portability* property). The verified path is inherently ~`1e-18`-noisy *even same-runtime* (so it offers no bit-identity guarantee the fast path lacks) and is punishingly slow on the Atom. **Role B scores the gate on the FAST path, at the strict `0.00e+00` bar; the verified deep-check is dropped from the NAS loop.** This resolves T0029.

## Architecture — five pieces on the already-live Role A container + a new telemetry stack

1. **Journal pull** — enable the journal channel on Role A's pull loop (its own least-privilege key).
2. **Role B gate-verify + emit** — a new `zcrypto engine gate-export` command run after each journal pull.
3. **NAS Alloy telemetry stack** — Alloy + a GET-only docker-socket-proxy as Container-Manager compose services.
4. **Grafana** — one canonical dashboard + alert rules, pushed by a committed script.
5. **Retire the workstation gate-ops timer.**

All NAS deployment is **plain `docker compose` under Container Manager** — no systemd, no DSM Task Scheduler, no NAS-OS config (the spec-00048 NAS-runtime constraint). The NAS runs the **`-compat`** image (no AVX).

### 1. Journal pull (extend Role A — no new VPS channel)

The VPS-side rrsync journal channel already exists (engine ansible role, `tasks/main.yml:269-274`): `command="/usr/bin/rrsync -ro {{ engine_state_dir }}/journal",restrict` on `deploy`'s `authorized_keys`, keyed by `sync_authorized_key` (`zcrypto-sync-pullonly`; private half vaulted at `infra/ansible/files/sync_ed25519`). It is **distinct** from Role A's `sync_capture` key. Increment 2 needs **zero** new VPS `authorized_keys` work — only key distribution to the NAS and the two-key wiring the entrypoint already anticipates.

- **Attended, out-of-band:** decrypt `sync_ed25519` and place it on the NAS at `/volume1/docker/zcrypto-archive/keys/sync_journal`, mode `0600` (mirrors the `sync_capture` deploy step; the `./keys` mount already exposes it as `/keys/sync_journal`).
- **`pull-entrypoint.sh`:** select the ssh key **per call** — `cli/archive/command.py:_run_rsync` reads a single `ARCHIVE_SSH_KEY` from the environment, so the entrypoint sets it per subprocess: `ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY"` for the segment pull, `ARCHIVE_SSH_KEY="$JOURNAL_SSH_KEY"` for the journal pull. **No `command.py` change** — the least-privilege two-key split the entrypoint comment already calls for.
- **`compose.yaml`:** add `CAPTURE_SSH_KEY=/keys/sync_capture`, `JOURNAL_SSH_KEY=/keys/sync_journal`, `JOURNAL_SOURCE=deploy@<vps-host>:` (bare — the rrsync forced command pins the remote subtree, same pattern as `CAPTURE_SOURCE`), and `JOURNAL_DEST` (default `/archive/engine-journal`). The journal pull runs `--no-verify` (already coded — the journal `.parquet` snapshots carry no `.sha256` sidecars; Role B verifies them by replay).

### 2. Role B gate-verify + emit — `zcrypto engine gate-export`

A new subcommand (TDD, `cli/engine/command.py` + a small emit module), the machine-readable sibling of `report`:

```
zcrypto engine gate-export --journal-dir <dir> --textfile <path.prom> [--healthcheck-url <url>] [--lag-fail-seconds <N>]
```

Behavior, on each invocation (called by the entrypoint after the journal pull, only when `JOURNAL_SOURCE` is set):

- Run `evaluate_gate(entries, now)` (from `cli.engine.concordance`, **fast path**) over the pulled journal → `status.streak` (int), `status.gate_met` (bool), `status.last_failure` (`None` | `{cycle_ts, reason}`).
- Compute `journal_pull_lag_seconds` = `now − newest journaled cycle timestamp` (the gate's own journal-freshness dead-man, independent of the pull's `lag_s`).
- **Atomically** write the textfile-collector `.prom` (write-temp-then-rename) with four series:
  ```
  zcrypto_gate_status <1 if MET else 0>
  zcrypto_gate_streak_days <streak>
  zcrypto_gate_journal_pull_lag_seconds <lag>
  zcrypto_gate_mismatch_total <count of failed/mismatched cycles in the journal>
  ```
  plus `zcrypto_gate_export_timestamp_seconds` (last successful run, for a Grafana staleness alert).
- **Healthcheck ping** (reusing the engine's `_ping_healthcheck` pattern, `cli/engine/cycle.py`; `--healthcheck-url` sourced from a `GATE_HEALTHCHECK_URL` compose env → a **new, dedicated** healthchecks.io check, distinct from the engine's own): ping `<url>` on a clean run (no mismatch **and** `lag ≤ lag-fail-seconds`), ping `<url>/fail` on any replay mismatch/validation failure or a stale journal. `--lag-fail-seconds` defaults to **`18000` (5 h)** — one 4 h cycle plus the hourly-pull margin. This is the **independent** paging path (see §Alerting).
- **Exit codes:** `0` when the emit succeeded (regardless of the gate *verdict* — a mismatch is a finding, emitted, not a loop error); non-zero only on an **operational** failure (journal unreadable, textfile unwritable) so the entrypoint logs it and continues. The loop must keep scoring across a gate mismatch.

`report` (human-readable) is unchanged and retained for attended reads. `gate-export` and `report` share `evaluate_gate`, so they can never disagree.

The entrypoint gains a post-journal-pull step: `zcrypto engine gate-export …` (guarded by `JOURNAL_SOURCE`, like the journal pull). The container mounts a `zcrypto.toml` at `/app/zcrypto.toml` (config load; replay never touches `store_dir`) and the **shared textfile dir** — a host path (`/volume1/docker/zcrypto-archive/textfile`) bind-mounted into **both** `archive-pull` (as `/textfile`, where `gate-export` writes the `.prom`) and Alloy (where the unix `textfile` collector reads it).

### 3. NAS Alloy telemetry stack (Container-Manager compose services)

Two new compose services alongside `archive-pull`, config adapted from spec `00043`'s `config.alloy` but deployed via `docker compose` (not the VPS's ansible/systemd `obs` role):

- **`docker-socket-proxy`** (GET-only guard): exposes only read endpoints on `127.0.0.1:2375`; Alloy talks Docker exclusively through it, so a misbehaving Alloy can read container metadata but never stop/kill/exec the `archive-pull` container.
- **`grafana/alloy`** (non-root, `network_mode: host`, read-only host mounts `/proc→/host/proc`, `/sys→/host/sys`, `/→/host/root` with `procfs_path`/`sysfs_path`/`rootfs_path` set, `/var/lib/docker:ro` for cadvisor, and one RW `./alloy-data:/var/lib/alloy` persistence mount so the remote_write WAL + log positions survive container replacement). New file `infra/nas/config.alloy`:
  - **Host metrics** — `prometheus.exporter.unix`, explicit `set_collectors = [cpu, loadavg, meminfo, filesystem, netdev, textfile]` (`textfile_directory` = the shared `/textfile` dir). Delivers **system load, network IO, free disk space** (incl. the 27 TB `/volume1` the archive grows into) — the requested host telemetry — plus the Role B gate `.prom` via the textfile collector (the clean fit for a *batch* emitter — no long-running `/metrics` server).
  - **Container metrics** — `prometheus.exporter.cadvisor` (`docker_host` = the proxy, `docker_only: true`, network group disabled) → CPU/mem/fs for archive-pull + Alloy + proxy.
  - **Logs** — `loki.source.docker` (archive-pull container logs) → `loki.write`. Useful for debugging the NAS stack; trimmable via `loki.process` drop rules if ingest matters.
  - `prometheus.scrape` → `prometheus.remote_write` and `loki.write` → the **already-provisioned** Grafana Cloud instance. Series minimization per 00043 (keep-only `write_relabel_configs`, drop Alloy self-metrics), target well under 1 k active series.
- **Secrets** — the Grafana Cloud Prometheus remote_write + Loki creds (URL/user/token) enter a NAS-side `config.alloy` mounted `0600`, distributed **out-of-band** (attended; the same creds vaulted earlier this session). `compose.yaml` stays secret-free.
- **Resource budget** — the Atom is weak (cadvisor housekeeping is the CPU hog): `docker_only`, trimmed metric groups, `GOMEMLIMIT`, and `cpus`/`memory` caps per 00043's tuning. 32 GB RAM is ample.

### 4. Grafana — one dashboard for everything + alerts (created here)

`infra/grafana/` and `scripts/grafana-push.sh` do not exist yet (spec 00043 / T0020 is parked), so this increment **creates the single canonical dashboard** and the push tooling, designed so T0020 later adds the VPS rows to the **same file**:

- `infra/grafana/zcrypto-dashboard.json` — the one dashboard, with a **NAS host row** (load / mem / disk-free / netdev), a **NAS containers row** (archive-pull / Alloy CPU-mem-fs), and a **gate row** (gate status, streak days, journal pull-lag, mismatch count, a Loki logs panel for archive-pull). Rows are namespaced so the VPS rows slot in later without collision.
- `infra/grafana/alerts.yaml` — alert rules: **gate** (status → not-MET, `mismatch_total` increases, streak resets, journal pull-lag > threshold, `gate_export_timestamp` stale) → email; **host** (disk-free low, load high); **ERROR logs** (archive-pull). Per-rule `no-data` semantics per 00043.
- `scripts/grafana-push.sh` (~20 lines) — POSTs the dashboard JSON (`/api/dashboards/db`) and the alert rules (provisioning API) using a **service-account token from the vault**; the committed JSON/YAML is authoritative (edits round-trip through re-export + commit + re-push). One attended script run.

### 5. Retire the workstation gate-ops timer

The NAS becomes the authoritative always-on scorer, mirroring how Role A superseded the workstation capture-pull. The gate-ops units are **manually-installed systemd `--user`** templates (not ansible-deployed):

- **Delete** `infra/systemd/zcrypto-engine-gateops.service` and `…​.timer` (superseded).
- **Attended step (documented, not automated):** on the workstation, `systemctl --user disable --now zcrypto-engine-gateops.timer`, remove the installed user units, and remove the decrypted `~/.ssh/zcrypto-sync_ed25519`.
- Update the docs that reference the workstation gate-ops flow (00042 note, T0003/T0018) at closeout.

## Data flow

VPS engine journals a cycle → rrsync `-ro` journal channel → NAS `archive-pull` (journal key) → `JOURNAL_DEST` → `gate-export` (fast-path `evaluate_gate`) → `.prom` textfile **+** healthcheck ping → Alloy (unix `textfile` collector + host/container metrics + logs) → remote_write / loki → Grafana Cloud → single dashboard + alert rules → email.

## Error handling & failure domains

- **Journal pull fails** → logged, loop continues (Role A pattern); `gate-export` runs on the last-good journal, `journal_pull_lag_seconds` grows → Grafana pull-lag alert **and** the healthcheck `/fail` fires.
- **`gate-export` operational error** (unreadable journal / unwritable textfile) → non-zero, logged, loop continues.
- **Gate mismatch** (a replay disagreement) → emitted via `mismatch_total` + healthcheck `/fail`; loop continues (a finding, never a crash).
- **Alloy / proxy down** → Grafana `no-data`/staleness alerts fire — *but* those alerts travel the Alloy→Grafana pipeline that is itself down. The **healthchecks.io dead-man is the independent failure domain** (Role B pings it directly, outside Alloy): if Role B dies or the gate breaks, it still pages. This is why the dead-man is kept alongside Alloy (00043's own rationale). Consolidating into Grafana IRM heartbeats is explicitly out of scope.

## Testing & acceptance

- **`gate-export` (TDD):** streak / gate_met / last_failure derived correctly from fixture journals (clean streak, a planted mismatch, a stale journal); `.prom` format + atomic write (temp-then-rename); `journal_pull_lag_seconds` math; healthcheck ping on clean vs `/fail` on mismatch/stale (stub the opener, as `cycle.py` tests do); exit `0` on emit-success-with-mismatch, non-zero on operational failure.
- **Determinism regression guard:** cite the measured fast-path bit-identity (this iteration); optionally a checked-in fixture cycle whose fast-path replay must yield `0.00e+00` (a cheap same-runtime guard that would catch a future builder change breaking replay determinism).
- **`config.alloy`:** render-smoke (jinja/env stub vars) + `alloy validate` against the rendered config (offline, no live creds), per 00043.
- **Live shakedown (attended):** the journal pulls to the NAS with the journal key; `gate-export` writes the `.prom`; Alloy ships host + container + gate metrics and logs to Grafana Cloud; the dashboard rows populate; each alert rule test-fires once; a simulated mismatch flips the healthcheck check to *down*; the workstation timer is confirmed disabled.

## Out of scope

- The **verified** deep-check on the NAS (dropped — the fast path is bit-identical and the verified path is too slow on the Atom + inherently ~`1e-18`-noisy same-runtime).
- **Role C** (redundant NAS L2 capture) — Increment 3.
- The full **VPS** `obs` role (spec 00043 / T0020) — this increment establishes the shared dashboard + push script + creds path; the VPS Alloy/exporters + the app-`/metrics` endpoints (`cli/obs/metrics.py`) stay T0020's scope.
- Consolidating healthchecks.io into Grafana IRM (kept deliberately as an independent failure domain).

## Global constraints

- NAS deployment is `docker compose` under Container Manager only — no systemd, no NAS-OS config.
- The NAS runs the **`-compat`** (no-AVX) image variant.
- Gate scoring is on the **fast path**, strict **`0.00e+00`** bar.
- Least-privilege keys: the capture and journal channels use **distinct** rrsync keys.
- Attended out-of-band secrets onto the NAS: the journal key (`sync_journal`), the Grafana Cloud remote_write + Loki creds + a dashboard-push service-account token, and a new healthchecks.io check URL.
- One canonical Grafana dashboard (`infra/grafana/zcrypto-dashboard.json`) — no separate NAS dashboard.
