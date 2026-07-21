---
status: partial
ripe_when: the attended alerts.yaml push window (vaulted `GRAFANA_SA_TOKEN`) — the rules are authored, reviewed, and branch-ready on `feat/t0079-alloy-dark-rules`; T0083 rides the same window
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

## Done so far

Authored 2026-07-21 by /zcrypto-auto-exec on branch `feat/t0079-alloy-dark-rules` — **branch-ready, deliberately NOT PR'd**: the component includes its push tail, so the single PR opens after the attended push (the loop's landing rule). What landed on the branch:

- Four per-host rules `zcrypto-alloy-dark-{nas,ops,capture-primary,capture-secondary}` in group `zcrypto-fleet` (`infra/grafana/alerts.yaml`). Shape: `count(up{host=...}) or on() vector(0)` below 1, instant, `for: 10m`, `noDataState/execErrState: Alerting` — the repo's fires-on-silence dead-man idiom rather than a bare `absent()`, which would need `noDataState: OK` and could park green. `count()` not `sum()`: presence of the series is the "shipping" signal; `up`'s value 0 is still shipped telemetry.
- The per-host selector question resolved from repo state alone: ops = `host="ops"`, capture = `host="zcrypto"` / `host="zcrypto-red"` (each sets `external_labels`), the NAS = **`{host=""}`** — the empty-value "label absent" matcher, because the NAS deliberately ships no host label (adding one changes series identity under the reconciler's `increase()` → false permanent-loss page risk); same idiom `NAS · load high` already uses.
- Severity: uniform `critical`/`metrics` for all four — the responder's action is identical on every host; what differs is only what accumulates unseen, which each summary states. (Reversible call made by the loop; overrule at the push if wanted.)
- The T0048-incident check: these rules would **not** have fired 2026-07-15/16 (Alloy alive, only discovery wedged — `up` kept shipping); the SD-wedged rule owns that case. Stated in the block comment.
- The keep-list pin: `up` added to the capture required-list in `tests/test_infra_alloy_series.py` (NAS/ops already pinned it); mutation-verified — deleting `up` from the capture keep-regex fails the test.

## Suggested next steps

- **(Attended — the remainder)** In the alerts.yaml push window: review the four rules (severity overrule is cheap here), run `grafana-push.sh`, verify in Grafana Cloud that all four evaluate OK against live data (especially the NAS `{host=""}` selector resolving to exactly the NAS series), then flip this topic `resolved` + archive on the same branch and open the single PR. [[T0083]] rides the same window.
