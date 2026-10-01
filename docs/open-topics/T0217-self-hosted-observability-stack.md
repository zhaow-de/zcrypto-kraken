---
status: open
ripe_when: "2026-10-05"
---

# Self-hosting the metrics, logs and alerting stack in place of Grafana Cloud's free tier

## Context — what

The fleet ships metrics and logs with Grafana Alloy to Grafana Cloud's free tier, where the dashboards and the alert rules of `infra/grafana/` evaluate and page Slack. This topic is the move of that stack onto one self-hosted node the project runs itself: one additional 4 GB Linode, no HA, Docker-free, native apt packages.

## Why this matters

- The free tier has no ticket support, only a community forum, and no SLA remedy.
- Its faults reach the pager and nothing in the repo can fix them: the rule evaluator timing out against its own Prometheus (2026-09-28 to 09-30, `docs/reference/ops-journal/2026-09.md`), `/api/health` answering 404 in bursts, and hibernation (`docs/open-topics/archive/T0181-a-503-cannot-separate-hibernation-from-outage.md`).
- The rules that watch a held position, the engine dark with exposure and the stale cycle among them, evaluate there.

## Findings so far

The assessment of 2026-10-01 is `docs/research/92.self-hosted-observability-assessment.md`; its conclusions follow, and its figures are the spec's to re-derive.

- **The stores are the choice, not Grafana.** Grafana holds no metrics or logs. Keeping Grafana as the evaluator keeps the rule file, the dashboards and the push script in their present shape.
- **Recommended: Grafana OSS on SQLite, one Prometheus as the remote_write receiver, single-binary Loki.** No alert expression is rewritten, and the evaluator's call to its store becomes a local one.
- **OSS, not the unlicensed Enterprise build**: every Enterprise feature is licence-gated, so unlicensed it adds nothing here.
- **SQLite, not PostgreSQL**: the database holds Grafana's own state alone. A second Grafana instance, or `database is locked` errors, would force PostgreSQL.
- **Prometheus, not Mimir**: Mimir buys scale, replication and object-store retention, none of which one small node needs. A second node, or retention moved to object storage, would flip it.
- **VictoriaMetrics and VictoriaLogs are rejected**: VictoriaLogs has no apt package and its query language would force a rewrite of every log rule; VictoriaMetrics computes `increase`, `delta` and `changes` differently at a series' first sample and after a gap, which changes what some rules page on.
- **It does not help rung 2's box.** Its pre-entry gates come first, through Sun 2026-10-04; Grafana Cloud stays the alert evaluator through the box, and nothing from this work converges `zcrypto` inside it.
- **What gets worse**: one more host to patch and repair, with no HA; while it is down, nothing evaluates the rules; its history is lost with the host unless backups are bought; a monthly cost where there was none.
- **Size**: a new host and role, dual-shipping in every Alloy config, a cutover and a retirement — large, with many attended converges.
- **Not verified by the assessment**: the Prometheus engine version Grafana Cloud runs, which decides whether range selectors read identically on both stacks; the memory Prometheus and Loki need at this scale; the unlicensed Enterprise build's licence text.

## Suggested next steps

- The owner's open decisions, each recorded in the spec:
  - Go: self-host as above, pay for Grafana Cloud Pro, or stay on the free tier.
  - Whether any host ships to both stacks while rung 2's box runs, and which.
  - What covers the exposure rule while the node is down, once Grafana Cloud is retired: a thin Grafana Cloud leg kept for it, or the engine's healthchecks.io check and a hand-read procedure.
  - The node's public surface: the UI and API behind the bridgehead's client certificates with ingest alone public, or a public login.
  - Reboots and patching: an unattended reboot slot with a monthly hand patch pass, or attended reboots.
  - Backup: rebuild from git with history lost, the provider's backups, or a pull to the NAS.
- Write the spec and its plan.
- Build in this order: the node and its role taking a shadow push; dual-shipping, the primary last and after the box; the cutover of paging; the retirement of the Grafana Cloud leg and the keep-alive.
