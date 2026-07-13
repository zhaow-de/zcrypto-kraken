# Grafana Cloud Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution is deferred** — parked as open topic T0020. This plan is written so a future attended session executes it mechanically without a clarification round.

**Goal:** Implement spec `docs/specs/00043-observability-design.md`: both VPS containers ship logs + three metric levels to the provisioned Grafana Cloud instance via one non-root Alloy behind a GET-only docker-socket proxy, with one committed dashboard, API-provisioned alerts to email, and the two production-redeploy embargoes enforced mechanically.

**Architecture:** Two code tasks (the shared exporter helper + engine wiring; the capture additive counters + wiring), one infra task (the `obs` role, the metrics-gating role vars, the push script, dashboard/alert artifacts), then the attended deployment/shakedown. iter-083/084's engine contracts and the capture daemon's behavior are consumed, never modified beyond the spec's pinned deltas.

**Tech Stack:** Python 3.14, `prometheus_client` (new dep via `uv add`), existing `cli` machinery, ansible (existing roles as patterns), Grafana Alloy + docker-socket-proxy (digest-pinned images), Grafana Cloud (Loki, Prometheus, alerting, HTTP API).

## Global Constraints

- **Secrets**: Grafana credentials (prom URL/user/token, loki URL/user/token, service-account token) live ONLY in `group_vars/capture_host/vault.yml`; `config.alloy` renders `0600` with `no_log: true` + `diff: false`; compose files stay secret-free. Nothing in this plan prints any token.
- **Capture L2 rule**: no behavioral capture changes — additive state-only counters + the two pinned log-hygiene lines are the entire capture delta; `capture_metrics_enabled` defaults `false` and flips ONLY after the ≥7-day clean-run clock (≈ 2026-07-15), in an attended window.
- **Engine gate protection**: `engine_metrics_enabled` defaults `false`; flips only away from a 4h-boundary+30-min window. A raising metrics update must never affect the CycleResult or journal artifact.
- **Exporter failure isolation**: startup failure of the exporter in either daemon logs ERROR and continues WITHOUT metrics.
- **Alloy security posture**: non-root Alloy; docker access exclusively via the GET-only proxy on `127.0.0.1:2375`; app ports loopback-only (`127.0.0.1:9101/9102`); the inspect-Env residual is a named, accepted §8 waiver (spec §posture).
- **Series minimization**: explicit `set_collectors` (unix: `cpu, loadavg, meminfo, filesystem, netdev` — no diskstats), cadvisor `docker_only` + network group disabled, keep-only `write_relabel_configs` seeded from the Docker integration's ~16-metric allowlist, Alloy self-metrics dropped.
- Aware-UTC everywhere; ruff 132/double quotes; gate `uv run pre-commit run -a`; actual-model trailers + `Claude-Session`; subagent review + `Reviewed-by` before push.

______________________________________________________________________

### Task 1 (subagent, TDD): the exporter helper + engine wiring

**Files:** Create `cli/obs/__init__.py`, `cli/obs/metrics.py`, `tests/test_obs_metrics.py`; modify `cli/engine/command.py` (start exporter in `run`), `cli/engine/cycle.py` (post-journal metrics update + ping-URL redaction), `cli/engine/node.py` (`LoggingConfig(log_colors=False)`), extend `tests/test_engine_cycle.py`, `tests/test_engine_command.py`. Add the dependency: `uv add prometheus_client`.

**Interfaces (produces):**

```python
# cli/obs/metrics.py — loggers get_logger("obs.metrics")
def start_exporter_from_env(*, env_var: str = "ZCRYPTO_METRICS_PORT") -> bool
#   Reads the env var; unset/empty -> False (no server). Otherwise starts the prometheus_client
#   HTTP server on 0.0.0.0:<port> (the compose publish pins it to 127.0.0.1 host-side) and
#   returns True. ANY exception (bad value, bind failure) -> logger.error + return False —
#   the daemon continues without metrics; never raises.
def register_collector(collector) -> None
#   Late registration onto the default REGISTRY (the capture objects exist only inside _run()).
#   Duplicate registration -> logger.error + swallowed (a restarted wiring must not kill the daemon).

# engine metric names (all gauges unless noted):
#   zcrypto_engine_target_weight{asset}         — per-asset target weight from the cycle record
#   zcrypto_engine_orders_count / zcrypto_engine_orders_notional_eur
#   zcrypto_engine_cycle_success                — 1 success / 0 failed(sidecar)
#   zcrypto_engine_cycle_completed_at_seconds   — COMPLETION time (not the boundary), epoch secs
#   zcrypto_engine_cycle_duration_seconds
def update_engine_cycle_metrics(result) -> None   # result: CycleResult; never raises (try/except-log)
def seed_engine_completed_at(journal_dir: Path) -> None
#   At `engine run` startup: glob the newest cycle-*.json / failed-cycle-*.json across day dirs
#   (same shape startup_action uses), parse its completed_at/attempted_at, set the gauge; empty
#   journal -> set process-start time. Read-only; never raises.
```

Engine wiring, exactly: `engine run` (command.py) calls `start_exporter_from_env()`; when it returned True, call `seed_engine_completed_at(config.journal_dir)`. In `run_cycle` (cycle.py), AFTER the record/sidecar write and AFTER `_ping_healthcheck` (same isolation contract), call `update_engine_cycle_metrics(result)`. The one-shot subcommands (`cycle`, `replay`, `report`, `seed`) never start the exporter. Hygiene in the same commit: `cycle.py`'s ping-failure warning logs the URL redacted to scheme+host (never the capability path); `node.py`'s `_node_config` gains `log_colors=False` in `LoggingConfig`.

Tests (stub sockets where needed; no network): env unset → no server + False; happy start → scrape over HTTP shows a registered gauge; bind-failure (occupied port fixture) → False + ERROR log + no raise; duplicate register_collector swallowed; update sets all six metric families from a success CycleResult and `cycle_success=0` from a sidecar result; **a raising update leaves the journal artifact intact** (monkeypatched gauge that raises; assert record file exists + CycleResult unchanged — the regression the spec pins); seeding picks the newest artifact across day dirs and falls back on empty journal; redacted warning contains host but not the path; `log_colors=False` present in the node config. Run the three test files + full suite + pre-commit. Commit `feat(obs): prometheus exporter helper + engine cycle metrics (spec 00043 task 1)`.

### Task 2 (subagent, TDD): capture counters + wiring

**Files:** Modify `cli/capture/ws_client.py` (reconnect/resubscribe counters), `cli/capture/segment_writer.py` (segments/bytes counters), `cli/capture/gap_monitor.py` (ping-URL redaction), `cli/capture/command.py` (exporter start + collector registration inside `_run()`; demote the two transient subscribe/unsubscribe rejection logs ERROR→WARNING); extend `tests/test_capture_*` files (find them via `grep -rl CaptureClient tests/`).

**Interfaces (consumes):** Task 1's `start_exporter_from_env` / `register_collector`. **Produces (additive state only — no behavioral change):**

```python
CaptureClient.reconnect_count: int    # += 1 at the existing reconnect site in stream()
CaptureClient.resubscribe_count: int  # += 1 in resubscribe_book()
SegmentWriter.segments_written: int   # += 1 at the existing hour-finalize site
SegmentWriter.bytes_written: int      # += final segment file size at the same site

# capture metric names:
#   zcrypto_capture_gap_seconds_total{pair,reason}  — monotonic counter fed from GapMonitor's
#     closed-gap durations (increase() is restart-safe; checksum-resync gaps ONLY, per spec)
#   zcrypto_capture_book_desynced{pair}             — 1/0 from OrderBook.desynced
#   zcrypto_capture_ws_reconnects_total / zcrypto_capture_resubscribes_total
#   zcrypto_capture_segments_written_total / zcrypto_capture_segment_bytes_total
```

Wiring, exactly: inside `_run()` (command.py), immediately after books/monitor/client/writers are constructed, call `start_exporter_from_env()`; when True, register ONE custom collector whose `collect()` reads **snapshot copies** (`dict(...)` / local ints) of the live objects — a scrape must never raise into the asyncio loop (test with an object mutated mid-iteration). Gap counter semantics: accumulate `end_gap`'s returned duration into the counter keyed `{pair, reason}` at the existing close site. Hygiene: `gap_monitor.py`'s ping-failure warning redacts the URL (scheme+host only); the subscribe/unsubscribe rejection logs in `command.py` demote to WARNING with a comment naming the pager rationale.

Tests: counters increment at each site (drive the existing unit fixtures); collector snapshot-safety (mutate the books dict during `collect()` — no raise); gap counter accumulates per pair+reason and is monotonic; exporter-start failure leaves `_run()` functioning (monkeypatch `start_exporter_from_env` to return False → capture proceeds); demoted log levels asserted; redaction asserted. Full suite + pre-commit. Commit `feat(capture): additive telemetry counters + exporter wiring (spec 00043 task 2)`.

### Task 3 (subagent): infra — the obs role, gating vars, push script, dashboard/alert artifacts

**Files:** Create `infra/ansible/roles/obs/{defaults/main.yml,tasks/main.yml,templates/compose.yaml.j2,templates/config.alloy.j2,files/zcrypto-obs.service,handlers/main.yml}`, `infra/grafana/zcrypto-dashboard.json`, `infra/grafana/alert-rules.yaml`, `infra/scripts/grafana-push.sh`; modify `infra/ansible/site.yml` (obs role after engine, `tags: [obs]`), `infra/ansible/roles/capture/templates/compose.yaml.j2` + `defaults/main.yml` (`capture_metrics_enabled: false` gating `ZCRYPTO_METRICS_PORT=9101` env + `127.0.0.1:9101:9101` publish), `infra/ansible/roles/engine/templates/compose.yaml.j2` + `defaults/main.yml` (`engine_metrics_enabled: false` gating the same at 9102), `infra/ansible/roles/base/tasks/main.yml` (**drop the "logrotate policy for the docker container console log" task** — the policy is superseded; see spec §Logs), `README.md` (observability section).

The obs role mirrors the engine role's structure: (1) docker-present assert (its only gate); (1b) **remove the legacy logrotate policy** — `ansible.builtin.file: path=/etc/logrotate.d/zcrypto-capture-docker state=absent` (leave the `/var/log/zcrypto-capture` archive untouched); (2) `/opt/zcrypto-obs` + `/opt/zcrypto-obs/data` dirs (data owned by Alloy's uid); (3) `config.alloy` render `0600` `no_log: true` `diff: false` — components per spec §Architecture: `discovery.docker`/`loki.source.docker` via `tcp://127.0.0.1:2375`, `loki.process` (ANSI strip → dual level extraction → container label → hc-ping mask), `loki.write`; `prometheus.exporter.unix` (`set_collectors: cpu, loadavg, meminfo, filesystem, netdev`; `procfs_path/sysfs_path/rootfs_path` → `/host/*`), `prometheus.exporter.cadvisor` (`docker_host` = proxy, `docker_only: true`, network group disabled), two app scrape jobs (`127.0.0.1:9101/9102`), all scrapes → `prometheus.remote_write` with keep-only `write_relabel_configs` (Docker-integration allowlist + the `zcrypto_*` families + the unix collectors' series; drop `go_*`/`process_*`); (4) compose render — `docker-socket-proxy` (`CONTAINERS=1`, everything else 0, `127.0.0.1:2375:2375`, cpus 0.1/mem 64m) + `alloy` (non-root `user:`, `network_mode: host`, mounts per spec incl. `/opt/zcrypto-obs/data:/var/lib/alloy`, `--storage.path=/var/lib/alloy`, `GOMEMLIMIT=460MiB`, cpus 0.5/mem 512m/cpu_shares 256), both images digest-pinned via `obs_alloy_digest`/`obs_proxy_digest` asserts; (5) the systemd unit (capture's pull/up/down pattern) + enable/start with the engine role's first-run check-mode guards (register the unit install; guard enable+start and the restart handler). `infra/scripts/grafana-push.sh`: `set -euo pipefail`; reads the service-account token via `uv run ansible-vault view` piped in-process (never echoed); POSTs `infra/grafana/zcrypto-dashboard.json` to `/api/dashboards/db` and each rule in `alert-rules.yaml` to the alerting provisioning API; idempotent (overwrite=true / PUT-on-exists). Dashboard JSON: the five rows per spec §Dashboard (author against the metric names Tasks 1–2 produce). `alert-rules.yaml`: the seven rules with the spec's exact expressions and per-rule no-data column.

Verification (no live host): `uv run ansible-playbook --syntax-check infra/ansible/site.yml` from `infra/ansible/`; render-smoke of both templates with stub vars + `alloy validate` on the rendered config (install `alloy` locally or via the pinned container image with `docker run --rm -v <rendered>:/c alloy validate /c` — either is fine, note which in the task report); `uv run pre-commit run -a`; `python3 -c "import json; json.load(open('infra/grafana/zcrypto-dashboard.json'))"`. Commit `feat(infra): obs role (alloy + socket proxy), metrics gating vars, grafana push script + artifacts (spec 00043 task 3)`.

### Task 4 (orchestrator + human, attended): deployment + shakedown

- [ ] **Vault** (human fetches from the instance UI; scripted append, in-process, never printed): `grafana_prom_url`, `grafana_prom_user`, `grafana_prom_token`, `grafana_loki_url`, `grafana_loki_user`, `grafana_loki_token`, `grafana_sa_token`.
- [ ] **Deploy Alloy + proxy**: `./scripts/run.sh site.yml --check --diff --tags obs -e obs_alloy_digest=… -e obs_proxy_digest=…` → review → same without `--check` → unit active; capture/engine untouched (their metrics flags still false).
- [ ] **Shakedown phase 1**: logs from BOTH containers in Loki with correct `level` labels on both line formats (zcrypto + nautilus); host + container metrics queryable; series count read from the instance (expect < 1 k); Alloy RSS/CPU vs budget; hc-ping mask verified on a ping-failure line if one exists.
- [ ] **Dashboard + alerts**: `infra/scripts/grafana-push.sh` → the five rows populate (app rows stay empty until the exporters flip); each alert rule test-fired once (no-impact: rule test / `logger.error` probe); email arrives.
- [ ] **Engine exporter flip** (away from a boundary+30 window): image rebuild (workflow_dispatch), `-e engine_metrics_enabled=true` converge, engine row populates, `zcrypto_engine_cycle_completed_at_seconds` seeded pre-first-cycle.
- [ ] **Capture exporter flip** (ONLY after the ≥7-day clock, ≈ 2026-07-15, ideally in T0003's attended window): same flow with `capture_metrics_enabled=true`; capture row populates; gap-ratio rule live; the transient sub/unsub demotions verified in Loki.
- [ ] **Closeout**: T0020 sub-items checked off per lifecycle (status flips in the same change as the work); alert-rule/dashboard exports re-committed if tuned; iterations-history entry for the execution iteration; PR into develop; merge on the human's go.
