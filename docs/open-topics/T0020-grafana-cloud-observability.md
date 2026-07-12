---
status: partial
ripe_when: the credentials are vaulted (done 2026-07-11); the canonical dashboard + alert rules + push script + creds path landed via iter-094's NAS build (spec 00049) — still open is the VPS `obs` role + app `/metrics` exporters (spec 00043's original scope), and running `scripts/grafana-push.sh` (needs the human's `<stack>.grafana.net` URL) to provision the dashboard/alerts + create the `email` contact point; the capture exporter flip additionally waits for the ≥7-day clean-run clock (≈ 2026-07-15)
---

# Grafana Cloud observability — execute spec 00043

## Context — what

The design and plan are done (authored attended, 2026-07-11, during iter-084's boundary wait; three-agent adversarial pass applied): both VPS containers ship docker logs and three metric levels (OS / container / application incl. trades+portfolio) to the **already-provisioned Grafana Cloud instance** via one non-root Alloy behind a GET-only docker-socket proxy; one committed dashboard; API-provisioned email alerts. This topic parks the **execution**.

- Spec: `docs/specs/00043-observability-design.md`
- Plan: `docs/plans/00043-observability.md` (Tasks 1–3 subagent TDD, Task 4 attended deployment/shakedown)

## Why this matters

Tonight's iter-084 deployment ran on ad-hoc journalctl playbooks and dead-man pings alone — no ERROR alerting, no resource visibility on a 2 vCPU/4 GB host now running three workloads, no disk watch (the VPS journal grows ~1.4 GB/month). The disk-watermark alert this delivers is also the ripe trigger for the journal-retention topic, and the gap-ratio panel continuously watches the T0003 exit-bar quantity.

## Findings so far

- The adversarial pass caught and the spec now pins: per-rule no-data semantics (a blanket "no-data ⇒ alert" leaves the ERROR rule permanently firing when healthy), the §8 posture (non-root Alloy + GET-only proxy; the inspect-Env residual is a named waiver), capture-counter honesty (reconnect/resubscribe/segment counters must be added — additive state only), exporter failure isolation (telemetry may never kill a daemon or void a gate cycle), restart-safe staleness math (completed-at gauge + startup seeding), and the mechanical deploy embargo (`capture_metrics_enabled`/`engine_metrics_enabled` default `false`).
- Grafana Cloud IRM (OnCall) heartbeats offer dead-man semantics; the deliberate choice is to keep healthchecks.io as an independent failure domain. **Consolidation is an explicit open option, not a default** (see next steps).
- Series budget: keep-only relabeling seeded from the Docker integration's ~16-metric allowlist; target < 1 k active series on the free tier.

## Done so far

- **(human sub-item — DONE 2026-07-11, this branch)** The seven `grafana_*` credentials were fetched from the provisioned Grafana Cloud instance and vaulted into `infra/ansible/group_vars/capture_host/vault.yml` via an in-process scripted append (`grafana_prom_url/user/token`, `grafana_loki_url/user/token`, `grafana_sa_token`; a single access-policy token with `metrics:write`+`logs:write` covers both writes). The append verified the six pre-existing vault keys are byte-identical and never emitted a value to the transcript. This clears the topic's only human gate — the remaining Tasks 1–4 are build + attended deploy, no further account action needed.
- **(iter-094, spec/plan `00049`)** The NAS observability slice landed as part of Role B's build (see [[T0003]]): a Grafana Alloy stack on the NAS (`infra/nas/compose.yaml` + `infra/nas/config.alloy`) ships host metrics (load/netdev/disk-free), the Role B gate metric, and the `archive-pull` container's logs to the already-provisioned Grafana Cloud instance — deployed + verified live (`samples_failed 0`, `loki sent 7`, healthcheck up). Container/cadvisor metrics are **not** collected on the NAS (Synology cgroup incompatibility). The same increment also created this topic's shared, not-yet-existing infra ahead of schedule: the **single canonical dashboard** (`infra/grafana/zcrypto-dashboard.json`), the **alert rules** (`infra/grafana/alerts.yaml`: gate, NAS host, ERROR-logs), and the push tooling (`scripts/grafana-push.sh`) — designed so this topic's VPS work later adds its rows to the same file. These are committed but **not yet pushed** to the live Grafana Cloud instance (see next steps); the VPS-side Alloy/exporters and app `/metrics` endpoints remain unbuilt.

## Suggested next steps

- **(autonomous, subagent-driven — VPS `obs` role, spec 00043's original scope)** Build the VPS side: the `cli/obs/metrics.py` exporter helper + engine `/metrics` wiring, capture's additive counters + wiring, and the ansible `obs` role (Alloy + GET-only docker-socket-proxy, gating vars, `--tags obs`) — deploy + shakedown phase 1, then flip the engine exporter away from its 4h-boundary+30-min window. The dashboard, alert rules, and push script are already built (iter-094, spec 00049); this work only needs to fold the VPS rows into the same `infra/grafana/` files.
- **(human-action, executable)** Provision the dashboard + alert rules on the live Grafana Cloud instance: export `GRAFANA_URL` (the stack's `<stack>.grafana.net` base URL — the only piece not yet vaulted, since only the hosted Prometheus/Loki push URLs are), `GRAFANA_SA_TOKEN` (vaulted service-account token with dashboards + alerting-provisioning write scope), `GRAFANA_PROM_DS_UID` / `GRAFANA_LOKI_DS_UID` (the Prometheus/Loki datasource UIDs, read off the live instance's datasource list), and `GRAFANA_ALERT_FOLDER_UID` (the alert folder UID to provision into); in Grafana, create the `email` contact point (Alerting → Contact points → New contact point, name it exactly `email`, integration `Email`, enter the destination address(es)) since every rule in `alerts.yaml` routes there by name; then run `scripts/grafana-push.sh` with those five vars exported — idempotent, safe to re-run after any `infra/grafana/` commit (full steps: `infra/nas/README.md` § "Grafana dashboard + alerts").
- **(autonomous, gated on the clean-run clock)** Flip the capture exporter on only after the ≥7-day clean-run clock closes (≈ 2026-07-15) — the mechanical deploy embargo (`capture_metrics_enabled` default `false`) stays until then.
- **(human decision, later)** Healthchecks.io vs Grafana IRM heartbeat consolidation: keep both, or migrate the dead-man checks into Grafana IRM and retire the healthchecks.io account. Decide only after the Grafana pipeline has weeks of proven reliability — the independent failure domain is currently load-bearing.
