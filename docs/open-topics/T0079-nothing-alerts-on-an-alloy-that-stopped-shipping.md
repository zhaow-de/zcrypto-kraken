---
status: open
ripe_when: ripe NOW — it is a single alert rule, and the gap is live on all four hosts today. Take it with the next alerts.yaml change rather than on its own, since pushing alert rules is an attended step (vaulted `GRAFANA_SA_TOKEN`)
---

# Nothing alerts on an Alloy that has stopped shipping entirely

## Context — what

The fleet runs four Alloy instances (NAS, ops, both capture hosts). Every one ships `up` — it is the first entry in all three `config.alloy` keep-lists — but **no alert rule consumes it**, and no rule fires on the *absence* of a host's telemetry. If an Alloy stops shipping, the series it carries simply go absent, and the only things that notice are the handful of exporter-stale rules scoped to specific metrics (`zcrypto-gate-exporter-stale`, `zcrypto-reconcile-exporter-stale`), each of which owns one producer rather than the shipping path itself.

Surfaced 2026-07-20 while adding `zcrypto-alloy-docker-sd-wedged` for [[T0048]] defect 1. That rule deliberately uses `noDataState: OK`, because absence there means "not shipping" rather than "wedged" — and writing that comment made it plain that **nothing else owns "not shipping" either**.

## Why this matters

It is the failure mode with the widest blast radius and the least coverage. A dead Alloy takes out, per host: host metrics, container logs, and every textfile-collector series — which on the NAS includes the gate metrics that decide whether the strategy may trade real money, and on the capture hosts includes the signals for data that is **unbackfillable**.

The exporter-stale rules do cover the two most important producers, so this is not a total blind spot — but they cover them *incidentally*, by noticing their own metric went stale. That means:

- coverage is per-metric, so anything without a dedicated stale rule is uncovered;
- the diagnosis points at the wrong layer — "the gate exporter is stale" reads as a gate problem when the actual fault is the telemetry agent on that host;
- and it is silent for whichever hosts have no such rule at all.

This also interacts with [[T0048]]: three separate defects there are remediated by restarting Alloy, and the codified NAS restart plus the manual runbook step on the render-only hosts are the controls. A restart that *fails* — or an Alloy that dies later — currently produces no direct signal.

## Findings so far

- `up` is admitted by all three keep-lists (`infra/nas/config.alloy`, `roles/ops/files/config.alloy`, `roles/capture/files/config.alloy`) — verified 2026-07-20 — so the data needed already reaches Grafana Cloud. **This is a missing rule, not a missing metric.**
- `grep -nE "expr: up|absent\(" infra/grafana/alerts.yaml` returns nothing: no rule uses `up`, and no rule uses `absent()`.
- The two exporter-stale rules use `time() - <last_success_timestamp> > threshold` with `noDataState: Alerting`, so they *do* fire when their own series vanishes — which is why a dead Alloy is partially covered today, and why this is a gap rather than a hole.
- `zcrypto-alloy-docker-sd-wedged` (added 2026-07-20) explicitly does **not** own this case, and says so inline, to avoid double-paging and to keep its own semantics clean.

## Suggested next steps

- **(Autonomous, one rule — but the design choice is the whole task)** Add a rule that fires when a host stops shipping. The two shapes, and the tradeoff:
  - `up == 0` — fires when the scrape target is reachable but failing. Does **not** fire when the series disappears entirely, which is the common case for a dead agent, so on its own it is close to useless here.
  - `absent(up{...})` per host, or a `time() - timestamp(...)`-style staleness check — fires on disappearance, which is what is wanted. Needs a per-host instantiation (or a rule per host label) because `absent()` over a multi-host selector goes quiet as long as *any* host reports.
  The second is right; the work is choosing the per-host selector and confirming the label set Grafana Cloud actually receives, since the hosts' `instance`/`job` labels are set by the remote_write pipeline rather than by us.
- **(Decide with it)** Severity and routing. The exporter-stale precedents are `critical`/`metrics`. A dead capture-host Alloy is arguably more serious than a dead ops one — the capture hosts hold unbackfillable data and the primary holds the live trade key — so a single severity for all four may be wrong.
- **(Check while implementing)** Whether this rule would have fired during the 2026-07-15/16 [[T0048]] incident. It would **not** have — Alloy was alive and shipping, only its docker discovery was wedged — which is a useful reminder that this rule and `zcrypto-alloy-docker-sd-wedged` cover genuinely different failures and neither subsumes the other.
- **(Cheap, do it in the same change)** Pin the new rule in `tests/test_infra_alert_rules.py` the way the others are, and confirm `up` stays in all three keep-lists via `tests/test_infra_alloy_series.py` — a keep-list edit dropping `up` would silently disarm this rule, the same failure shape [[T0048]]'s mitigation had to guard against.
