---
status: open
ripe_when: an attended observability window — both halves are small attended changes (the healthchecks.io console for the retag + a cron on one host; a Grafana alert rule pushed via grafana-push.sh with the vaulted SA token). Pairs naturally with T0079's alert push — same window can take both.
---

# healthchecks.io: retag every check, and add the Grafana↔healthchecks mutual watchdog

## Context — what

Decided at the 2026-07-21 grooming: **no migration** of the dead-man checks into Grafana Cloud — the two systems are deliberately independent failure domains (CLAUDE.md codifies the separation), and merging them would mean one outage takes out alerting *and* dead-mans together. Two improvements instead:

- **Retag**: the `zcrypto` tag on every check is uninformative (the whole project is zcrypto). Retag by **node** (capture / capture-redundant / engine / ops / nas) and **application/container**, so a firing check names its origin.
- **Mutual watchdog**: a new healthchecks.io check whose pinger verifies `zcrypto2026.grafana.net` availability and pings only on success (Grafana down ⇒ check overdue ⇒ hc.io notifies), and a Grafana alert rule over the healthchecks.io status API (checks down/paused ⇒ Grafana notifies). Either side breaking pages via the survivor.

## Why this matters

A monitoring stack that cannot detect its own outage fails exactly when it matters most. The independence of the two domains only pays off if each side's outage is *noticed* by the other; today neither watches the other. The rejected migration is recorded here so it is not re-litigated: it was considered 2026-07-21 and declined for the failure-domain reason above.

## Findings so far

- healthchecks.io checks are ping-based, so "watching Grafana" means a small success-gated pinger cron on ops or the NAS (both already run cron/timer jobs).
- healthchecks.io exposes a read-only status API per project; the Grafana half is an Alloy scrape plus one rule (`noDataState: Alerting` — absence of the scraped status is itself the failure). The vaulted-credential pattern for the admin API token already exists.
- [[T0020]]'s old "(human decision, later)" consolidation bullet is settled by this topic.

## Suggested next steps

- **(Attended, small)** Retag all checks by node + application in the healthchecks.io console.
- **(Attended, small)** Create the Grafana-watching check + success-gated pinger cron; wire its notification channel.
- **(Attended, small)** Add the hc.io-status scrape + one Grafana rule; push via `grafana-push.sh`, read-back verify.
- **(With both halves)** One drill: block each side artificially and confirm the other side pages — an unfired watchdog is indistinguishable from a misconfigured one.
