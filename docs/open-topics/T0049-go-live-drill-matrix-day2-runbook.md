---
status: open
ripe_when: anytime before the final go-live — picked up manually by the human, never auto-triggered (drills deliberately break production paths, so execution still needs attended maintenance windows per capture-deploys.md); flipped from "the final go-live preparation" at the 2026-07-21 grooming
---

# Go-live drill matrix and day-2 operations runbook

## Context — what

The Phase-1 exit-bar **alerting drill is passed** (owner sign-off 2026-07-16, discharged by the live `zcrypto-nas-archive-pull-stalled` firing — Loki → Grafana → Slack, fired/investigated/resolved the same evening, [[T0048]]). That proved one path, once, on the incident that happened to occur. Before live trading, run a **deliberate drill across the fleet's failure scenarios** and distill the responses into a **day-2 operations runbook** (owner directive 2026-07-16).

## Why this matters

Live money raises the cost of a missed, misrouted, or misread alert from "lost telemetry" to "unattended open positions". Today each alert path has been proven only by whichever incidents happened to fire it, and incident response lives in session memory plus scattered fragments — the [[T0048]] Alloy wedge was diagnosed from scratch live, and its runbook line exists only because the incident occurred. A scenario matrix proves the untested paths; the runbook turns response into a durable procedure a future operator (or session) can execute without rediscovery.

## Findings so far

The drill's starting inventory:

- **Paths proven by real events:** Loki log alert → Slack (the 2026-07-15/16 archive-pull-stalled incident); healthchecks.io dead-man → email (the iter-039 desync) and now native Slack (owner-configured 2026-07-15); Grafana metric rules → Slack (12 rules pinned as-code to the `metrics`/`logs` receivers, 2026-07-16).
- **Dead-men in service:** capture (primary + secondary), engine cycle (`/fail` semantics), NAS archive-pull, gate-export, and the ops-node timers (verify-replay, verified-replay, archive-pull, panel, liquidations poller).
- **Runbook fragments scattered:** ledger correction (`infra/nas/README.md`, [[T0044]]), capture-deploy canary + maintenance windows (`.claude/rules/capture-deploys.md`), Alloy tailer restart ([[T0048]]), reboot slots (spec `00050`).
- **Drill-worthy failure modes already parked:** disk-watermark ping-withhold deploy verification ([[T0032]]), WS-reconnect ride-out ([[T0035]]), phantom-splice guard ([[T0039]]), Alloy tailer death on recreate ([[T0048]]), lost-trades invisibility ([[T0043]]).

## Suggested next steps

- Enumerate the scenario matrix (draft — extend at execution): capture daemon stopped (each host) → dead-man fires, Slack lands; disk-watermark breach → withheld ping pages; engine cycle failure → `/fail` ping routes; NAS pull stall → Loki alert (re-verify post-[[T0048]]-fix); Alloy itself down → what pages, and how fast; secondary host loss → primary unaffected, loss still visible; Grafana Cloud unreachable → the healthchecks.io independent failure domain still pages; ops-node timer failure → its dead-man; reboot-window overlap sanity (primary 21:25 / secondary 22:25 UTC); a compose-level "container never created" failure (docker-path logs never exist and the owning unit's journal is filtered on the capture hosts — the one log class no Alloy pipeline sees; registered 2026-07-19 from the iter-105 config.alloy review) → confirm the healthchecks dead-man is the catcher and time it.
- Run each scenario in an attended maintenance window, per `capture-deploys.md` discipline (never induce a failure on live capture outside a window); record per scenario: time-to-alert, channel(s) that fired, and the operator action taken.
- Write `docs/reference/day2-operations-runbook.md`: one section per alert/dead-man — what it means, first checks, remediation, escalation — folding in the existing fragments (ledger correction, Alloy restart, canary rule) so the runbook is the single entry point.
- **(direction, 2026-07-21 grooming)** Evolve this from a one-shot drill matrix into a human-triggered **healthcheck skill**: root-cause fixes keep producing tests as today, and *additionally* each incident adds a check script/instruction here, so the skill verifies all systems/components/datasets are present and consistent (fold in [[T0039]]'s findings). The skill also fetches and analyzes historical logs + alerts — aiming, eventually, at autonomous operation.
- Human item: during the drill window, on the phone's Slack app confirm a mobile push actually arrives for one `metrics`-receiver alert and one `logs`-receiver alert (not just the desktop client); record delivery latency for both in the drill log.
