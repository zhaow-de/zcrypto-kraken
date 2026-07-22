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

Static scrape targets — capture `127.0.0.1:9101`, engine `:9102`, poller `:9103` (the first two are 00043's pinned ports) — no discovery, no socket. **The security boundary is the host-side publish**: compose maps `127.0.0.1:<port>:<port>`, so the endpoint is reachable from the host's loopback only — nftables untouched, nothing public on the trade-key host. Inside the container the exporter binds `0.0.0.0`, and must: the app containers are bridge-networked, and Docker delivers published-port traffic to the container's eth0, never its loopback — an inside-`127.0.0.1` bind would refuse every scrape (`up=0` fleet-wide, cold-review C1). Alloy's existing `prometheus.remote_write` (basic auth: metrics instance ID + access-policy token, vaulted since iter-094) carries the samples — byte-for-byte the pattern the official doc prescribes (verified 2026-07-22 against `grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/`). App-side `remote_write` push was rejected: it needs protobuf+snappy and forfeits the free `up`/absence semantics the later alerting iteration will want.

## D4 — Container-level CPU/memory: process self-metrics; cadvisor rejected on posture

Every app container on this fleet runs exactly one Python process, so container CPU/mem ≈ process CPU/mem. Each daemon's endpoint includes its own `process_cpu_seconds_total`, `process_max_fds`, `process_open_fds`, `process_resident_memory_bytes`, `process_start_time_seconds`, `process_virtual_memory_bytes` (`prometheus_client`'s ProcessCollector) — ~6 series per daemon, zero new containers, zero sockets, zero privileged.

**cadvisor is rejected everywhere, on posture, regardless of its crash behavior.** Embedded or standalone, cadvisor needs the docker API to resolve container names (without it, containers are anonymous cgroup hex ids) — re-adding a socket consumer one iteration after 00068's headline removed them all. The `.tmp/cadvisor-at-synology.md` tips were evaluated as the owner asked: the three fixes (drop `/dev/disk` mounts, inotify bump, pin v0.49.1) are credible against the DSM SIGSEGV class, and standalone isolation would stop it taking Alloy down — but the prescription is `privileged: true` plus a **read-write** `/var/run` mount on the custody host, a strictly worse posture than the one 00068 retired. Verdict: technically credible, disqualified on posture. This closes [[T0020]]'s untriaged "retry NAS cadvisor" item as an explicit rejection.

Named coverage gaps, accepted: the NAS pull loop (shell — host-level `node_*` still watches the Atom), and page-cache/child-process accounting (irrelevant to single-process containers). Alloy's own resources: the same four `process_*` families flow from each Alloy's existing self-endpoint. (An earlier draft said "exactly two for Alloy"; that would need a per-job relabel component per host — RE2 has no negative lookahead, so a drop-rule carve-out cannot express it — machinery for two series. Instead the drop rule shrinks to `go_.*|alloy_.*` and the keep stage owns `process_*` admission uniformly; the +2-series/host delta is in D9.)

## D5 — Instruments

- **Shared helper** `cli/obs/metrics.py`, per 00043's pinned contract: opt-in via `ZCRYPTO_METRICS_PORT` (unset ⇒ no server — the workstation soak stays exporter-free), late registration of collectors over live objects (capture's objects are constructed inside `_run()`), and the isolation invariant: **telemetry may never kill a daemon or void a cycle**. Exporter startup failure logs ERROR and continues; **so does a malformed `ZCRYPTO_METRICS_PORT`** (log ERROR, run without the exporter — cold-review I6: the env is rendered unguarded, so a deploy typo must never stop capture; `--ship-logs`'s hard-error precedent does not transfer because 00068 structurally couples its flag to its env in one file, making that error unreachable at deploy). A raising metrics update can never affect a `CycleResult` or a journal artifact (regression-tested).
- **capture**: 00043's additive set, faithfully this time (cold-review I2 caught a silent drop): reconnects, resubscribes, segments written + **segment bytes**, held/quarantined rows, **`zcrypto_capture_gap_seconds_total{pair}`** (the restart-safe gap counter — the T0003 exit-bar quantity 00043 existed to make visible; tap `GapMonitor.gap_seconds`), **`zcrypto_capture_book_desynced{pair}`** (gauge, from `OrderBook.desynced`), plus **`zcrypto_capture_disk_watermark_breached` (gauge, 0/1)**: [[T0032]]'s silent killer (watermark breach stops all writes while every monitor stays green) finally gets a live signal; the alerting iteration turns both gauges into pages.
- **engine**: 00043's pinned set verbatim — per-asset target weight, order count + notional EUR, cycle success (0/1), `zcrypto_engine_cycle_completed_at_seconds` (completion time, seeded at `engine run` startup from the newest journal artifact so a routine restart never false-fires staleness), cycle duration. Gate *streak* deliberately not exported (the gate-ops report's derived quantity).
- **poller**: poll cycles by outcome, Coinalyze API errors, last-success timestamp.
- **all four**: the 00068 ship-handler internals — `zcrypto_logship_dropped_lines_total`, `zcrypto_logship_shipped_lines_total`, `zcrypto_logship_last_success_timestamp_seconds` — making the logs path's health metrics-visible (the division of labor 00068 D3 records), plus the ProcessCollector families (D4).

## D6 — Infra wiring, and the named deviations from 00043

- Compose per daemon: publish `127.0.0.1:<port>:<port>`, set `ZCRYPTO_METRICS_PORT`. **No embargo flags** (`capture_metrics_enabled` / `engine_metrics_enabled` are NOT built) — a deliberate deviation from 00043, whose embargo protected a then-live ≥7-day clean-run clock that matured 2026-07-15 and no longer exists. The safety property the flags bought is now structural: env+port without the new image are inert (unknown env var, unpublished port), and the new image without env is exporter-off. Nothing here can break a container start.
- Alloy per host: one static scrape job per local daemon; keep-lists name every new family explicitly; `tests/test_infra_alloy_series.py` gains admit **and** exclude assertions for the new families (both directions, per T0051). **The NAS's own `config.alloy` is in scope too** (cold-review I5): it carries the same `process_*` drop rule, and without its drop/keep edit one of the four Alloys would never ship the process pair D4 budgets.
- The other deviation from 00043: its GET-only docker-socket proxy and cadvisor scrape job are not built (D4); its `prometheus.exporter.unix`/host-metrics scope shipped long ago (iter-094/105). 00043 is thereby fully discharged — executed in part, superseded in part, every superseded piece named here.

## D7 — NAS host label: fold in now (owner's call)

`external_labels host="nas"` on the NAS's `prometheus.remote_write`, and the `{host=""}` selectors re-keyed to `{host="nas"}` in the same change — **exactly two exist** (measured, cold-review I1): `node_load1{host=""}` in `NAS · load high` and `count(up{host=""})` in the Fleet·Alloy-dark NAS rule. `NAS · /volume1 free space low` carries no host matcher and needs nothing. The Alloy-dark rule's *"do NOT fix this to host=nas"* comment — written for the unlabeled era — is rewritten in place in the same change (it becomes the instruction it used to forbid). This is a **mechanical re-key, not alert design**, which is how it stays inside this iteration's "no alerting work" boundary. Recorded honestly: the designer recommended deferring to the dashboards iteration (which rewrites those selectors anyway); the owner chose symmetry now, taking the known series-identity seam at an attended window where a false page is cheap to dismiss (T0020's own standing advice). Gate rules carry no host matcher and survive untouched; the reconcile `increase()`/`resets()` rule moved to ops at 00054 and is unaffected.

## D8 — Rollout: one deployment, both changesets, plus the T0069 rider

Extends 00068 D7 **with two named amendments** (cold-review M3 — "in place, same steps" overstated): (1) the image builds from the **pushed branch head**, not the merged commit — the owner's PR-gate ruling makes the merge follow the rollout; (2) the prune moves **after** the engine flip, so "all steps done including the prune" is the single terminal point the merge gate tests (00068 ordered prune before engine; nothing depends on that order — the SD rule's series die with the four Alloy converges, which all precede either). Otherwise D7's step list is the execution sequence, one image carrying 00068+00069, each step's verification gaining "`up{job="<daemon>"}` is 1 and one application series is visible in Grafana Cloud" — with the `job` label **set explicitly** (`job_name` on each scrape component; Alloy's default is the component path, and a check against an unset name queries a value that does not exist).

- **The T0069 rider on the NAS step is deploy-only — the repo side is ALREADY LANDED** (cold-review C2 corrected this spec's first draft, which claimed "the code ships inert" from a truncated grep): `pull-entrypoint.sh` has passed `--cache /tmp/gate-cache.json` since commit `b60dea5` (2026-07-20), and the committed pin already postdates PR #157. The cache path is deliberately container-internal — **never a shared volume**: 00062 D9 records that `/archive` is reachable by both hosts, whose different polars runtimes would mutually poison a shared cache. What rides here: pin the NAS to this rollout's new `-compat` digest, recreate, and verify — knowing the recreation empties `/tmp`, so the **first** cycle is a cold rebuild (~10 min on the Atom) and the verifiable warm cycle is the **second** (spec 00060's D4 property: `gate.prom` field-for-field equal, cycle time seconds-not-minutes). At Step 2 also **measure whether the cache was already live pre-rollout** (was the container recreated since `b60dea5`'s pin?) and record the fact in T0069's closeout, whose own text is stale on this point. **The relocation-to-ops does NOT ride** — different work shape (moves a Role-B deliverable across hosts with healthcheck + textfile rewiring); it stays parked in T0069, whose own analysis calls incremental scoring the structural fix.
- The engine's flag flip (both `--ship-logs` and `ZCRYPTO_METRICS_PORT`) remains the post-Stage-6a-gate step; the `grafana-push.sh` prune remains last, after every converge.
- The NAS label re-key (D7) rides the NAS window; its verification is the two re-keyed rules evaluating against live series.
- **The PR gate (owner's ruling, 2026-07-22): the PR opens after the implementation review but MERGES only after the full rollout** — every D7 step including the post-gate engine flip and the final prune. The component includes its deploy tail; a green CI is not the finish line. Consequences, stated: the branch lives ~a week (spanning the 24 h canary bake and Stage-6a gate day ~07-25); the deploy image is built from the pushed branch head, which the merge then lands unchanged (digest pins reference the image, not the branch); and the closeout — history entry and topic updates — is written AFTER the rollout, from measured facts.

## D9 — Series budget

The earlier estimate counted "the Alloy process pair ×4 hosts" (8 series) where the ratified decision (D4/D5) admits the full six ProcessCollector names ×4 hosts (24), and it omitted the five new per-job `up` series (`capture_app`, `engine_app` ×2 hosts, `liquidations_app`) — both corrected in the reviewer's measured recount:

| Host | New series |
| --- | --- |
| primary (zcrypto) | 68 |
| secondary (zcrypto-red) | 44 |
| ops | 20 |
| nas | 6 |
| **Total** | **~138** |

~138 measured against the **≤150 budget** — ~8% headroom, not the ~20% the old "~120 nominal" implied. The 405-series base is the 2026-07-16 measurement and predates the capture-host Alloys — **re-measured at rollout Step 0**, not assumed. Comfortably inside spec 00043's <1k target; measured at each rollout window, recorded in the closeout.

## D10 — Testing (TDD)

- `cli/obs/metrics.py`: opt-in semantics (unset ⇒ no server, no thread); late registration; exporter startup failure ⇒ ERROR logged, daemon continues; a raising update leaves the `CycleResult`/journal artifact intact (regression); endpoint serves the exposition format `prometheus_client` emits; default-registry noise absent from output.
- Per-daemon taps: snapshot-safety (fixture objects mutated mid-scrape stay safe — 00043's pin); engine startup seeding reads the newest journal artifact, falls back to process start.
- Infra: every new family admitted AND every retired/never-published family excluded in each host's keep-regex (`tests/test_infra_alloy_series.py`); both Jinja guard branches of every touched compose template render valid YAML.

## Out of scope

- Dashboard and alert **design** — the dedicated later iteration (T0020's dashboards package). Only D7's mechanical re-key rides.
- The oneshot push path (rejected, D1), cadvisor anywhere (rejected, D4), NAS pull-loop resource metrics (accepted gap, D4).
- T0069's relocation-to-ops (stays parked; D8).
- Grafana Cloud retention/usage tuning.

## Cross-topic records — updated at THIS iteration's closeout (owner's ruling: the closeout follows the rollout, so every update records measured facts)

- [[T0020]] — the remaining core is executed AND deployed; the untriaged "retry NAS cadvisor" item closes as an explicit posture rejection; per-host series counts recorded; the dashboards package stays queued for the owner.
- [[T0032]] — the watermark gauge is live and scrape-verified; the alert itself still lands in the alerting iteration; the prune-verification sub-item is unrelated calendar work and unaffected. **This rollout is also the topic's `ripe_when` trigger (2)**: the capture-image rollout that finally deploys the `3e03aac` measurable-probe fix — recorded at closeout.
- [[T0069]] — the cache-enablement sub-item flips with the measured warm-cycle time and the field-for-field gate.prom equality; its stale "code ships inert" text is rewritten in place (`b60dea5` enabled it in the deployment config); relocation stays parked.
- [[T0089]] — inherited from 00068 and discharged by this same rollout: all six wedged containers recreated, each confirmed by a post-recreation line in Loki — the topic's own closure criterion, so it should reach `resolved` here.
- [[T0042]] — the socket residual closes, verified by `docker inspect` (no socket mount) at every window; the engine-egress note updates.
- Spec `00043` — fully discharged (D6); its remaining unbuilt pieces are either built here or explicitly superseded.
