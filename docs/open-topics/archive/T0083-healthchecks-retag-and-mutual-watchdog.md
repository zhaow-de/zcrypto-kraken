---
status: resolved
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

## Resolution (2026-07-21, attended window — all four steps done and drilled)

- **Retag** — all nine checks retagged by node + application via the management API (read-back verified): `capture`/`capture-redundant` + `capture-daemon`, `engine` + `engine-shadow`, `nas` + `gate-verify`, `ops` + {`panel`, `archive-pull`, `verify-replay`, `verified-replay`, `liquidations`}. Two latent defects fell out: `zcrypto-archive-pull` had been mis-tagged `panel`, and `zcrypto-engine-shadow` carried **no tags at all**.
- **hc.io half** — check `zcrypto-grafana-watchdog` (600 s timeout / 600 s grace, fleet notification channel) plus an ops systemd timer every 5 min running `/usr/local/sbin/zcrypto-grafana-watchdog`: it probes `zcrypto2026.grafana.net/api/health` and pings **only** on success, pings `/fail` on probe failure (immediate page), and a dead pinger still pages by staleness — all three failure paths covered. Runner + units render from the `ops` role; the ping URL is vaulted per host.
- **Grafana half** — the ops Alloy scrapes hc.io's project Prometheus endpoint (path with the embedded **read-only** key vaulted as `hc_prometheus_metrics_path`, reaching the container via `alloy-secrets.env`), and rule `zcrypto-hcio-watchdog` fires on `max(hc_checks_down_total) or on() vector(999) > 0` — the fallback makes scrape silence read as 999, so the watchdog cannot go green-when-blind. Keep-list and `tests/test_infra_alloy_series.py` admit `hc_check_up` + `hc_checks_down_total`. **The series names were read from the live endpoint, not guessed** — the natural guess (`hc_checks_down`) does not exist.
- **The drill — both directions fired, then self-resolved.** *Grafana direction*: a throwaway check with no notification channels was failed; `hc_checks_down_total` went to 1, the rule fired at 20:34:40 UTC with `value=1`, and deleting the check returned it to Normal. *hc.io direction*: the **real** pinger script was run with only its probe target swapped to an unreachable address; it took the `/fail` branch, the check went DOWN at 20:28:47 and Slack carried "received a failure signal", then the next timer slot re-pinged and Slack carried "is UP. The downtime lasted 2 minutes, 7 seconds."

Delivered on branch `feat/t0083-healthchecks-watchdog`; converge previewed with `--check --diff`, then applied to the ops node, Alloy recreated so the new env var landed, rules pushed with `grafana-push.sh` (datasource read-back clean, no orphans).

## Suggested next steps

_(none — resolved. The window also surfaced an unrelated live incident, registered as [[T0089]]: a `copytruncate` logrotate policy wedges docker's log readers, which is why the capture hosts' log plane is dark.)_
