---
status: open
ripe_when: the next Alloy version bump on the NAS (test whether upstream fixed the tailer refresh), or if the manual restart-after-recreate runbook line is ever missed again
---

# Alloy's docker tailer does not survive container recreation

## Context — what

When a NAS compose service is **recreated** (`docker compose up -d` after a compose/env change — new container ID), Alloy's `loki.source.docker` tailer keeps retrying the **dead** container ID every ~5 s (`error inspecting Docker container … No such container`) and never begins tailing the replacement. Log shipping for that service goes dark while everything else looks healthy. First observed 2026-07-15/16: two archive-pull recreations (16:46 Z re-pin, 21:36 Z panel-channel activation) left Loki blind for hours until the `NAS · archive-pull stalled` dead-man fired at ~22:1x Z — **the alert working exactly as designed** (it is the one rule that fires on monitoring-pipeline death, and this was the first real fire through the new Slack-only path).

## Why this matters

Every future NAS deploy that recreates a container silently kills its log shipping — the ERROR-log alert goes green-because-blind, dashboards stop, and only the dead-man (3 h window) eventually notices. The failure is quiet, recurring, and operator-induced, which is exactly the class that erodes trust in the instrument.

## Findings so far

- Root cause is in Alloy's tailer lifecycle, not discovery: `discovery.docker` refreshes targets, but the running `loki.source.docker` tailer set doesn't reap the dead ID or adopt the new one (observed on the pinned NAS Alloy version; zero mentions of the new container ID in Alloy's own logs post-recreate).
- **Remediation is a plain `docker restart` of the Alloy container**: fresh discovery adopts the live container, the fresh position re-ships its whole (small) log with ingest-time-stamped **original** timestamps, so the dead-man's window repopulates and the alert self-resolves within an evaluation cycle (proven live 2026-07-16 22:25 Z).
- Related-but-distinct earlier lesson (from the spec-00050 Task-10 deploy, previously recorded only in session notes — undocumented until now): `compose up -d` does not restart Alloy when only its *mounted config* changed, silently dropping every new metric series at remote_write. The runbook line added with this topic covers both cases: **restart Alloy after any NAS compose change**.

## Suggested next steps

- On the next Alloy image bump: recreate a scratch container and verify whether upstream fixed tailer refresh; if fixed, drop the runbook caveat.
- (autonomous, optional) If it recurs despite the runbook: consider a NAS-side `docker events`-driven nudge or moving the restart into the deploy steps as an explicit numbered item — for now the README line (added with this topic) is the control.
