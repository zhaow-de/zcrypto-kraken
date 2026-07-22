# App-level `/metrics` — implementation plan (spec 00069, iter-117)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** the four Python daemons serve `/metrics` (incl. process self-metrics and the 00068 logship internals), each host's Alloy scrapes them, the NAS gains `host="nas"`, and the WHOLE fleet — 00068 + 00069 in one image — is rolled out attended before the PR merges.

**Architecture:** one new module `cli/obs/metrics.py` (exporter helper on `prometheus_client`, opt-in, isolation-invariant), one small tap per daemon, per-role compose/Alloy wiring, and the attended rollout as explicit checklist steps executed with the owner from the pushed branch.

**Tech Stack:** `prometheus_client` (the ONE new dependency — pure-Python, zero transitive deps; `uv add prometheus-client`). Everything else stdlib + existing infra tooling.

## Global Constraints (from spec 00069 — exact values)

- Ports: capture `9101`, engine `9102`, poller `9103`; compose publishes `127.0.0.1:<port>:<port>` ONLY. Env name exactly `ZCRYPTO_METRICS_PORT`; unset ⇒ no server, no thread.
- **Isolation invariant (00043, re-pinned):** telemetry may never kill a daemon or void a cycle. Exporter startup failure ⇒ one ERROR log, daemon continues. A raising metrics update can never affect a `CycleResult`, a journal artifact, or a capture write path. Each has a regression test.
- **No embargo flags** — deliberate deviation from 00043, spec D6. Nothing in this plan may make a container start depend on new env/files.
- Default-registry noise (`python_gc_*`, `python_info`) unregistered at source AND excluded by keep-list; ProcessCollector families (`process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_open_fds`, `process_start_time_seconds`) admitted uniformly (spec D4's "exactly two for Alloy" is widened to the same four families — a per-job relabel component per host to shave two series is machinery for nothing; note the +2-series/host delta against D9's budget).
- Every new series family named explicitly in each host's keep-regex, with admit AND exclude assertions in `tests/test_infra_alloy_series.py` (T0051, both directions).
- The PR gate (spec D8): PR opens after the final whole-branch review; **merges only after every rollout step including the post-gate engine flip and the final prune**.

______________________________________________________________________

### Task 1: `cli/obs/metrics.py` — the exporter helper

**Files:** Create `cli/obs/__init__.py`, `cli/obs/metrics.py`; Test `tests/test_obs_metrics.py`. Dep: `uv add prometheus-client`.

**Interfaces:**

- Produces: `start_metrics_server(port: int, registry: CollectorRegistry) -> bool` (True = serving; False = failed, ERROR logged, caller continues), `build_registry() -> CollectorRegistry` (fresh registry with ProcessCollector registered and NOTHING else — no python_gc/python_info), `metrics_port_from_env() -> int | None` (reads `ZCRYPTO_METRICS_PORT`; None when unset/empty; raises `ValueError` on non-integer — a deploy typo fails loudly at startup, matching `--ship-logs`'s hard-error posture).
- Consumes: `prometheus_client.start_http_server(port, addr="127.0.0.1", registry=...)` — bind loopback INSIDE the container too (defense in depth under the port publish).

**Steps:**

- [ ] **Step 1: failing tests** — `build_registry()` output contains the four `process_*` families and NO `python_gc_*`/`python_info`; `metrics_port_from_env()` unset→None, `"9101"`→9101, `""`→None, `"x"`→ValueError naming the var; `start_metrics_server` on port 0 serves the exposition format (GET and parse); **startup-failure isolation**: bind the port first with a plain socket, call `start_metrics_server` on the SAME port → returns False, exactly one ERROR record, no raise, no thread leak (assert on returned server absence, not global thread counts).
- [ ] **Step 2: verify FAIL. Step 3: implement** (~60 lines: registry builder, env reader, a try/except-log wrapper around `start_http_server`). **Step 4: verify PASS. Step 5: commit** `feat(obs): metrics exporter helper -- opt-in, isolated, loopback-only (00069 T1)`

### Task 2: logship internals become collectable

**Files:** Modify `cli/logging/ship.py` (add `shipped_lines_total` and `last_ship_success_at: float | None`, both mutated only in the worker's `"ok"` branch under `_ring_lock`); Create the custom collector in `cli/obs/metrics.py` (`LogshipCollector(handler)` — a snapshot-reading collector: `zcrypto_logship_dropped_lines_total`, `zcrypto_logship_shipped_lines_total`, `zcrypto_logship_last_success_timestamp_seconds`); Test: extend `tests/test_logging_ship_handler.py` + `tests/test_obs_metrics.py`.

- [ ] **Step 1: failing tests** — after a successful ship, `shipped_lines_total` == lines sent and `last_ship_success_at` is recent; the collector renders all three families from a live handler and tolerates a handler mid-mutation (snapshot under the same lock); with no ship handler configured the collector families are absent (not 0 — absence is honest, zero is a claim).
- [ ] **Step 2-5:** FAIL → implement → PASS → commit `feat(obs): logship counters exposed via the registry (00069 T2)`

### Task 3: capture tap

**Files:** Modify `cli/capture/command.py` (late registration inside `_run()` after the objects exist), `cli/capture/ws_client.py` (reconnect/resubscribe counters — additive attributes, incremented where `_RECONNECT_ERROR_EVERY` bookkeeping already lives); Test `tests/test_capture_metrics.py`.

**Instruments (additive only, 00043's honesty pin):** `zcrypto_capture_reconnects_total`, `zcrypto_capture_resubscribes_total`, `zcrypto_capture_segments_written_total`, `zcrypto_capture_rows_held_total`, `zcrypto_capture_rows_quarantined_total`, and **`zcrypto_capture_disk_watermark_breached` (gauge 0/1, read live from `watermark.breached` — the T0032 signal; `cli/capture/command.py:139/162/219` are the existing read sites)**.

- [ ] **Step 1: failing tests** — collectors read snapshot copies (mutate the fixture object mid-scrape; scrape stays consistent); watermark gauge flips 0→1 when the fixture watermark breaches; `ZCRYPTO_METRICS_PORT` unset ⇒ `_run()` starts no server (pin: capture on the workstation soak has no exporter); a raising collector never propagates into a message-handler path (regression: wrap-and-log verified).
- [ ] **Step 2-5:** commit `feat(capture): /metrics tap -- additive counters + the watermark gauge (00069 T3)`

### Task 4: engine tap

**Files:** Modify `cli/engine/command.py` (`run()` at :413 — server start + gauge updates AFTER the record/sidecar write, wrapped try/except-log exactly like `_ping_healthcheck`); Test `tests/test_engine_metrics.py`.

**Instruments (00043's pinned set, names verbatim):** per-asset target weight gauge (`zcrypto_engine_target_weight{asset=...}`), `zcrypto_engine_orders_total` + `zcrypto_engine_order_notional_eur`, `zcrypto_engine_cycle_success` (0/1), `zcrypto_engine_cycle_completed_at_seconds`, `zcrypto_engine_cycle_duration_seconds`. **Startup seeding:** at `engine run` start, seed `completed_at` from the newest journal artifact (same day-dir glob as `startup_action`), falling back to process start. Gate streak deliberately NOT exported.

- [ ] **Step 1: failing tests** — update called on success AND sidecar paths; **a RAISING update leaves the `CycleResult` and journal artifact intact** (the 00043 regression test, verbatim requirement); seeding reads the newest artifact, falls back to process start when the journal dir is empty; 12-asset weight gauge yields 12 series.
- [ ] **Step 2-5:** commit `feat(engine): /metrics tap -- cycle gauges with restart-safe seeding (00069 T4)`

### Task 5: poller tap

**Files:** Modify `cli/liquidations/command.py` (+ `recorder.py`/`coinalyze.py` counters as fits); Test `tests/test_liquidations_metrics.py`.

**Instruments:** `zcrypto_liquidations_polls_total{outcome="ok|error"}`, `zcrypto_liquidations_api_errors_total`, `zcrypto_liquidations_last_success_timestamp_seconds`.

- [ ] **Steps 1-5** (same TDD shape; isolation regression: a raising update never aborts a poll cycle). Commit `feat(liquidations): /metrics tap (00069 T5)`

### Task 6: compose + Alloy wiring, all hosts

**Files:** Modify `infra/ansible/roles/capture/templates/compose.yaml.j2`, `roles/engine/templates/compose.yaml.j2`, `roles/ops/templates/compose.yaml.j2` (port publish + `ZCRYPTO_METRICS_PORT` — UNGUARDED, spec D6: inert without the image, and the image without env is exporter-off); `roles/capture/files/config.alloy`, `roles/ops/files/config.alloy` (one static scrape job per local daemon: `prometheus.scrape "capture_app"` → `127.0.0.1:9101` etc., 60 s interval, forwarding to the existing remote_write; keep-regex gains every new family; the `go_.*|process_.*|alloy_.*` drop rule becomes `go_.*|alloy_.*` so the keep stage owns process_* admission); `infra/docker/compose.yaml` (reference counterpart); `tests/test_infra_alloy_series.py` (admit + exclude, per host).

- [ ] **Step 1:** failing infra tests naming the new families per host (capture hosts: capture families + engine's on the primary… **engine scrape job lands on the PRIMARY's capture-role config only** — one config file serves both hosts, so the engine job scrapes `127.0.0.1:9102` on both; on the secondary nothing listens ⇒ `up=0` for a job whose alerting lands later; state this in a comment rather than special-casing). Both Jinja branches render valid YAML.
- [ ] **Step 2-4:** implement, tests green, `pre-commit` clean. **Step 5: commit** `feat(infra): alloy scrapes the app /metrics endpoints (00069 T6)`

### Task 7: NAS label + T0069 cache rider (repo side)

**Files:** Modify `infra/nas/config.alloy` (`external_labels { host = "nas" }` on `prometheus.remote_write`), `infra/grafana/alerts.yaml` (re-key the three `{host=""}` selectors → `{host="nas"}`: the Fleet·Alloy-dark NAS rule, `NAS · load high`, `NAS · /volume1 free space low` — mechanical, no threshold/for/noDataState changes), `infra/nas/pull-entrypoint.sh` (add `--cache "$CACHE_DIR"` to the gate-export call + create the dir; `CACHE_DIR` under the container's existing writable volume), `infra/nas/compose.yaml` (cache path env/mount if needed); `tests/test_infra_alert_rules.py` if it pins selectors.

- [ ] **Step 1:** grep `alerts.yaml` for every `host=""` occurrence — the list above must be verified against the file, not assumed (if a fourth selector exists, it re-keys too and the spec's count is corrected).
- [ ] **Step 2-4:** implement; `alerts.yaml` parses, no duplicate uids; infra tests green. **Step 5: commit** `feat(infra): nas host label + gate-export --cache enabled (00069 T7, T0069 rider)`

### Task 8: final whole-branch review, PR OPENED (not merged)

- [ ] Full suite + gate; whole-branch review package (merge-base → HEAD) to an Opus reviewer; fix round if needed.
- [ ] Open the PR into `develop` with the spec's PR-gate stated in the body: **merges only after the full rollout**. Push the branch; the deploy image builds from this branch head.

### Task 9: THE ROLLOUT — attended, with the owner, from the pushed branch

Execute spec 00068 D7's step list (already operator-executable) with 00069's additions. Every step: positive-trace verification (a log line arriving in Loki AND `up{job=…}==1` with one app series visible), `docker inspect` shows no socket mount, series count recorded.

- [ ] **Step 0:** build + push the image from the branch head; record default-AVX + `-compat` digests; `zcrypto --help` in the image shows `--ship-logs`; `/metrics` serves locally with `ZCRYPTO_METRICS_PORT=9101 zcrypto capture --help`-level smoke.
- [ ] **Step 1 (ops):** converge with new digests; `compose up -d` both projects; verify poller direct-ship line + `up{job="liquidations_app"}`==1 + logship/process series visible.
- [ ] **Step 2 (NAS):** `-e nas_apply_compose=true` + new `-compat` digest; journald read-probe (`--user 1031:19` ls) BEFORE recreation; recreate both containers; verify journal-path lines in Loki, `host="nas"` on new samples, the three re-keyed rules evaluating, **gate-export first warm cycle: `gate.prom` field-for-field equal to the prior full-replay output + cycle time seconds-not-minutes (T0069's D4 property)**.
- [ ] **Step 3:** upsert-only `grafana-push.sh` (no prune) for the re-keyed NAS rules.
- [ ] **Step 4 (secondary capture):** new image + flags; **24 h canary bake per `capture-deploys.md`** (digest running, `RestartCount` 0, capture green, dead-man pinging; schedule the T+24 h Slack reminder). Verify capture direct-ship + `up{job="capture_app"}`==1 + watermark gauge present at 0.
- [ ] **Step 5 (primary):** after the bake — `-e converge_primary=true` with both digests; same verification; T0089's capture wedges now cleared fleet-wide (all six containers' post-recreation lines confirmed).
- [ ] **Step 6 (post-gate, ~07-25+):** engine converge — `--ship-logs` + `ZCRYPTO_METRICS_PORT=9102`; verify engine series + direct-ship line.
- [ ] **Step 7:** `GRAFANA_PRUNE=1` push (retires `zcrypto-alloy-docker-sd-wedged`); record final per-host series counts vs D9's ≤120 budget.

### Task 10: closeout — AFTER the rollout, from measured facts

- [ ] Topic updates (all in this branch, per the owner's ruling): **T0020** (core executed + deployed; cadvisor item closed as posture rejection; series counts), **T0032** (watermark gauge live + scrape-verified), **T0069** (cache flipped with the measured warm-cycle time; relocation stays parked), **T0089** (→ `resolved` if all six containers confirmed shipping — its own closure criterion), **T0042** (socket residual closed with `docker inspect` evidence; engine-egress note updated). Index bullets synced (`topic-ops` conventions).
- [ ] `docs/iterations-history-phase6.md` entry (iter-117) + `docs/research/14.phase6-decisions.md` entries (transport/scope/cadvisor decisions with options, per `decisions-log.md`).
- [ ] README `## Usage` already updated in Task 3-5 commits if any CLI surface changed (`ZCRYPTO_METRICS_PORT` is env, not a flag — document beside `--ship-logs`'s env block).
- [ ] Full suite + gate; commit `docs(closeout): iter-117 (00069 T10)`; **then merge the PR** per `merge-pr` and the spec's gate.

## Explicitly NOT in this plan

Dashboard/alert design (only Task 7's mechanical re-key); the oneshot push path; cadvisor; T0069's relocation-to-ops; Grafana retention tuning.
