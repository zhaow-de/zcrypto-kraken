# App-level `/metrics` — the fleet's application-metrics layer (iter-117)

**Status:** designed and approved in the attended 2026-07-22 brainstorming session; every decision below was made explicitly by the owner. Executes [[T0020]]'s remaining core — spec `00043`'s app-metrics layer — under 00068's post-socket architecture, with the deviations from 00043 named in D6.

## Goal

The four Python daemons (capture ×2, engine, liquidations poller) expose a `/metrics` endpoint that each host's Alloy scrapes and `remote_write`s to Grafana Cloud. Container-level CPU/memory arrives as **process self-metrics** through the same endpoints — no cadvisor, no docker socket, anywhere. This iteration ends at "the metrics land in Grafana Cloud, verified per host"; dashboards and alert *design* are a later, dedicated iteration. The deployment is included and carries 00068's code in the same rollout — one image, one canary bake.

## D1 — Endpoint scope: daemons serve `/metrics`; job outcomes keep the textfile

All five of today's `.prom` producers are shell scripts, four of them oneshots (the ops wrappers `archive-pull` — which also writes the reconcile + trade-backfill families — `verify-replay`, `verified-replay`, `panel-materialize`; and the NAS pull loop, whose gate metric is written by a short-lived `zcrypto engine gate-export` invocation each cycle). A `/metrics` endpoint is a live HTTP server: a process that has exited cannot be scraped, and half these metrics measure the shell wrapper itself. The textfile collector is the Prometheus-blessed pattern for cron-shaped work, not legacy debt.

So the structure mirrors 00068 exactly: **daemons ship live (endpoint), oneshots conclude (textfile)** — the endpoint is all new capability, and nothing file-based is actually retired. "Truly everything through endpoints" was considered and rejected: it requires rearchitecting shell wrappers into services or adding a second push path, real engineering for zero new information. (The official transport doc independently backs this: Grafana Cloud "doesn't support the Prometheus push gateway protocol" — job metrics belong on the scrape side.)

## D2 — Exposition: `prometheus_client`, adopting 00043's ratified choice

Pure-Python, zero transitive dependencies, and its `ProcessCollector` is exactly D4's mechanism. Hand-rolling (the `ship.py` precedent) would reimplement the exposition format and thread-safe instruments for no leanness gain a one-file pure wheel doesn't give. Default-registry noise (`python_gc_*`, `python_info`) is unregistered at source **and** excluded by keep-list — both directions tested (the T0051 lesson: an admitted-but-unpublished series is a trap; so is a published-but-unadmitted one).

## D3 — Transport: Alloy scrapes loopback ports; nothing pushes

Static scrape targets — capture `127.0.0.1:9101`, engine `:9102`, poller `:9103` (the first two are 00043's pinned ports) — no discovery, no socket. Ports published `127.0.0.1`-only: loopback never leaves the host, nftables untouched, nothing public on the trade-key host. Alloy's existing `prometheus.remote_write` (basic auth: metrics instance ID + access-policy token, vaulted since iter-094) carries the samples — byte-for-byte the pattern the official doc prescribes (verified 2026-07-22 against `grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/`). App-side `remote_write` push was rejected: it needs protobuf+snappy and forfeits the free `up`/absence semantics the later alerting iteration will want.

## D4 — Container-level CPU/memory: process self-metrics; cadvisor rejected on posture

Every app container on this fleet runs exactly one Python process, so container CPU/mem ≈ process CPU/mem. Each daemon's endpoint includes its own `process_cpu_seconds_total`, `process_resident_memory_bytes`, `process_open_fds`, `process_start_time_seconds` (`prometheus_client`'s ProcessCollector) — ~4 series per daemon, zero new containers, zero sockets, zero privileged.

**cadvisor is rejected everywhere, on posture, regardless of its crash behavior.** Embedded or standalone, cadvisor needs the docker API to resolve container names (without it, containers are anonymous cgroup hex ids) — re-adding a socket consumer one iteration after 00068's headline removed them all. The `.tmp/cadvisor-at-synology.md` tips were evaluated as the owner asked: the three fixes (drop `/dev/disk` mounts, inotify bump, pin v0.49.1) are credible against the DSM SIGSEGV class, and standalone isolation would stop it taking Alloy down — but the prescription is `privileged: true` plus a **read-write** `/var/run` mount on the custody host, a strictly worse posture than the one 00068 retired. Verdict: technically credible, disqualified on posture. This closes [[T0020]]'s untriaged "retry NAS cadvisor" item as an explicit rejection.

Named coverage gaps, accepted: the NAS pull loop (shell — host-level `node_*` still watches the Atom), and page-cache/child-process accounting (irrelevant to single-process containers). Alloy's own resources: keep exactly `process_cpu_seconds_total` + `process_resident_memory_bytes` from each Alloy's existing self-endpoint (currently dropped by the `go_.*|process_.*|alloy_.*` relabel — the drop rule gains a carve-out for those two).

## D5 — Instruments

- **Shared helper** `cli/obs/metrics.py`, per 00043's pinned contract: opt-in via `ZCRYPTO_METRICS_PORT` (unset ⇒ no server — the workstation soak stays exporter-free), late registration of collectors over live objects (capture's objects are constructed inside `_run()`), and the isolation invariant: **telemetry may never kill a daemon or void a cycle**. Exporter startup failure logs ERROR and continues; a raising metrics update can never affect a `CycleResult` or a journal artifact (regression-tested).
- **capture**: 00043's additive counters — reconnects, resubscribes, segments written, held/quarantined rows — plus **`zcrypto_capture_disk_watermark_breached` (gauge, 0/1)**: [[T0032]]'s silent killer (watermark breach stops all writes while every monitor stays green) finally gets a live signal; the alerting iteration turns it into a page.
- **engine**: 00043's pinned set verbatim — per-asset target weight, order count + notional EUR, cycle success (0/1), `zcrypto_engine_cycle_completed_at_seconds` (completion time, seeded at `engine run` startup from the newest journal artifact so a routine restart never false-fires staleness), cycle duration. Gate *streak* deliberately not exported (the gate-ops report's derived quantity).
- **poller**: poll cycles by outcome, Coinalyze API errors, last-success timestamp.
- **all four**: the 00068 ship-handler internals — `zcrypto_logship_dropped_total`, shipped-lines counter, last-ship-success timestamp — making the logs path's health metrics-visible (the division of labor 00068 D3 records), plus the ProcessCollector families (D4).

## D6 — Infra wiring, and the named deviations from 00043

- Compose per daemon: publish `127.0.0.1:<port>:<port>`, set `ZCRYPTO_METRICS_PORT`. **No embargo flags** (`capture_metrics_enabled` / `engine_metrics_enabled` are NOT built) — a deliberate deviation from 00043, whose embargo protected a then-live ≥7-day clean-run clock that matured 2026-07-15 and no longer exists. The safety property the flags bought is now structural: env+port without the new image are inert (unknown env var, unpublished port), and the new image without env is exporter-off. Nothing here can break a container start.
- Alloy per host: one static scrape job per local daemon; keep-lists name every new family explicitly; `tests/test_infra_alloy_series.py` gains admit **and** exclude assertions for the new families (both directions, per T0051).
- The other deviation from 00043: its GET-only docker-socket proxy and cadvisor scrape job are not built (D4); its `prometheus.exporter.unix`/host-metrics scope shipped long ago (iter-094/105). 00043 is thereby fully discharged — executed in part, superseded in part, every superseded piece named here.

## D7 — NAS host label: fold in now (owner's call)

`external_labels host="nas"` on the NAS's `prometheus.remote_write`, and the `{host=""}` selectors re-keyed to `{host="nas"}` in the same change — the Fleet·Alloy-dark NAS rule, `NAS · load high`, `NAS · /volume1 free space low`. This is a **mechanical re-key, not alert design**, which is how it stays inside this iteration's "no alerting work" boundary. Recorded honestly: the designer recommended deferring to the dashboards iteration (which rewrites those selectors anyway); the owner chose symmetry now, taking the known series-identity seam at an attended window where a false page is cheap to dismiss (T0020's own standing advice). Gate rules carry no host matcher and survive untouched; the reconcile `increase()`/`resets()` rule moved to ops at 00054 and is unaffected.

## D8 — Rollout: one deployment, both changesets, plus the T0069 rider

Extends 00068 D7 **in place** (that spec's step list stays the single execution sequence): same ordered steps, one image build carrying 00068+00069, each step's verification gaining "`up{job="<daemon>"}` is 1 and one application series is visible in Grafana Cloud."

- **The T0069 `--cache` rider on the NAS step.** The NAS `archive-pull` recreation (already in the rollout for the journald driver) is exactly the maintenance window T0069's cache enablement was parked for: add `--cache <path>` + a writable cache dir to `pull-entrypoint.sh`'s gate-export call, and re-pin the `-compat` image (the current pin predates PR #157, merged 2026-07-20 — no capture-image rollout has happened since). Verification is spec 00060's own D4 property: the first warm cycle's `gate.prom` equal field-for-field to a fresh replay, cycle time collapsing from ~8 min to seconds. **The relocation-to-ops does NOT ride** — different work shape (moves a Role-B deliverable across hosts with healthcheck + textfile rewiring); it stays parked in T0069, whose own analysis calls incremental scoring the structural fix.
- The engine's flag flip (both `--ship-logs` and `ZCRYPTO_METRICS_PORT`) remains the post-Stage-6a-gate step; the `grafana-push.sh` prune remains last, after every converge.
- The NAS label re-key (D7) rides the NAS window; its verification is the three re-keyed rules evaluating against live series.

## D9 — Series budget

Estimate: engine ~15 (per-asset gauges dominate at 12 names) + capture ~10 ×2 hosts + poller ~7 + logship ~3 ×4 daemons + ProcessCollector ~4 ×4 daemons + the Alloy process pair ×4 hosts = **~78 nominal; budgeted ≤120** with headroom for label variants, on a measured 405-series base. Comfortably inside spec 00043's <1k target; measured at each rollout window, recorded in the closeout.

## D10 — Testing (TDD)

- `cli/obs/metrics.py`: opt-in semantics (unset ⇒ no server, no thread); late registration; exporter startup failure ⇒ ERROR logged, daemon continues; a raising update leaves the `CycleResult`/journal artifact intact (regression); endpoint serves the exposition format `prometheus_client` emits; default-registry noise absent from output.
- Per-daemon taps: snapshot-safety (fixture objects mutated mid-scrape stay safe — 00043's pin); engine startup seeding reads the newest journal artifact, falls back to process start.
- Infra: every new family admitted AND every retired/never-published family excluded in each host's keep-regex (`tests/test_infra_alloy_series.py`); both Jinja guard branches of every touched compose template render valid YAML.

## Out of scope

- Dashboard and alert **design** — the dedicated later iteration (T0020's dashboards package). Only D7's mechanical re-key rides.
- The oneshot push path (rejected, D1), cadvisor anywhere (rejected, D4), NAS pull-loop resource metrics (accepted gap, D4).
- T0069's relocation-to-ops (stays parked; D8).
- Grafana Cloud retention/usage tuning.

## Cross-topic records (closeout obligations)

- [[T0020]] — this executes its remaining core; the untriaged "retry NAS cadvisor" item closes as an explicit posture rejection; the dashboards package stays queued for the owner.
- [[T0032]] — the watermark gauge is the live signal its alerting sub-item needs; the alert itself lands in the alerting iteration.
- [[T0069]] — the cache-enablement sub-item flips at the NAS window; relocation stays parked.
- [[T0089]] / [[T0042]] — unchanged obligations, discharged by the same rollout (00068 D7).
- Spec `00043` — fully discharged (D6); its remaining unbuilt pieces are either built here or explicitly superseded.
