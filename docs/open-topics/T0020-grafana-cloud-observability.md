---
status: open
ripe_when: the first attended ops window after iter-084's PR merges (Alloy/proxy deploy + engine exporter flip); the capture exporter flip additionally waits for the ≥7-day clean-run clock (≈ 2026-07-15), ideally sharing T0003's attended window
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

## Suggested next steps

- **(human)** From the Grafana Cloud instance UI (zcrypto2026.grafana.net → stack settings): copy the Prometheus remote_write URL + username + token, the Loki push URL + username + token, and create a service-account token with dashboard+alert-provisioning scope; hand them to the session for the scripted vault append (values never printed). Expected result: seven new `grafana_*` vars in `group_vars/capture_host/vault.yml`.
- **(autonomous, subagent-driven)** Plan Tasks 1–3: exporter helper + engine wiring; capture additive counters + wiring; the `obs` ansible role + gating vars + `scripts/grafana-push.sh` + dashboard JSON + alert rules.
- **(attended)** Plan Task 4: deploy Alloy+proxy (`--tags obs`), shakedown phase 1, dashboard/alert push + one test-fire per rule (email confirmed), engine exporter flip away from a 4h-boundary+30-min window, capture exporter flip **only after ≈ 2026-07-15**.
- **(human decision, later)** Healthchecks.io vs Grafana IRM heartbeat consolidation: keep both, or migrate the dead-man checks into Grafana IRM and retire the healthchecks.io account. Decide only after the Grafana pipeline has weeks of proven reliability — the independent failure domain is currently load-bearing.
