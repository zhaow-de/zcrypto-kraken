---
status: partial
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

## Done so far

- Phase 1, the node taking a shadow push: spec `docs/specs/00121-self-hosted-observability-design.md` and plan `docs/plans/00121-mon-node.md`, built and merged as PR #652 (`cb85a29bc`, 2026-10-03); the attended rollout R0 to R10 run 2026-10-03, the node `zcrypto-mon` (Linode `g6-standard-2`, Debian 13, `de-fra-2`, Backups on) running Grafana 13.2.3, Prometheus 2.53.3, Loki 3.7.8, Caddy 2.11.7 and Alloy 1.20.1 at `https://zcrypto-mon.zhaow.me`, every rule pushed to its own stack paging the shadow channel, and R9's acceptance read by value: 115 rules healthy at 60 s, the node's nine rules by value, both store stops, the head series 9,740 after the push (8,033 before it). Two findings of the acceptance fixed on their own branches before this record: PR #653 (`cookie_samesite = lax`, kept on the owner's word as Grafana's default) and PR #654 (the edge answers the cookieless `HEAD` Slack for macOS pre-resolves a link with, so a Slack link opens its target).

## Suggested next steps

- Phase 2, dual-shipping, the primary last and after the box: its plan skeleton is `docs/plans/00121-dual-shipping.md` on branch `docs/t0217-phase-2-plan`, filled from the rollout's readings and reviewed by `zcrypto-plan-review` before its first task. It carries three small items the rollout left: the self-check naming the absent series where it says "no scheduler tick"; the push script's orphan wording for a skipped group's rule; the push skill's `mon-push` pointer promising a per-rule read its step 3 does not carry.
- Phase 3, the cutover of paging, and phase 4, the retirement of the Grafana Cloud leg and the keep-alive: each takes its own plan once the phase before it has been read.
