---
status: partial
ripe_when: live now — both failure modes were hit for real on 2026-07-13, and the script is the only path we have for provisioning alerts
---

# `grafana-push.sh` can silently mis-point every alert, and never deletes a removed rule

## Context — what

`infra/scripts/grafana-push.sh` provisions the dashboard + alert rules onto Grafana Cloud. Two failure
modes were hit **for real** on 2026-07-13, within minutes of each other, while fixing an unrelated alert:

1. **Datasource UIDs are unvalidated env vars.** The script takes `GRAFANA_PROM_DS_UID` /
   `GRAFANA_LOKI_DS_UID` and substitutes them into every rule with **no check that they are the right
   datasources — or datasources at all**. A Grafana Cloud stack ships **two Prometheus** datasources
   (`grafanacloud-prom`, `grafanacloud-usage`) and **three Loki** ones (`grafanacloud-logs`,
   `grafanacloud-alert-state-history`, `grafanacloud-usage-insights`). Picking "the first of each type"
   — the obvious thing to do — silently repointed **all 7 alert rules and the dashboard** at
   `grafanacloud-usage` and `alert-state-history`. Every rule still reported `health=ok`; they were
   simply watching **the wrong data**. Nothing anywhere would have caught it.
2. **The push never prunes.** It upserts rules by `uid`. A rule **deleted from `alerts.yaml` stays live
   on the instance forever**, still evaluating and still emailing. Renaming a rule's `uid` (as the
   `Gate · not MET` → `Gate · streak reset` replacement did) leaves the old rule running unless it is
   deleted by hand — which is easy to forget and invisible in the repo.

## Why this matters

Both failure modes are **silent**: the rules keep reporting `health=ok`, so the monitoring *looks* fine
while it is either watching the wrong datasource or running rules that no longer exist in source control.
That is worse than a broken alert — it is an alert you *believe*. The whole point of the Grafana layer is
to be the thing that tells us when the irreplaceable capture pipeline breaks.

The git-vs-live divergence is the same class of bug as the deployed-compose drift that produced
[[T0031]]: the repo is not the source of truth unless the push makes it so.

## Findings so far

- Correct UIDs for this stack: **`grafanacloud-prom`** (isDefault) and **`grafanacloud-logs`**; the alert
  folder `zcrypto` is `bfrxdfoybx98gb`.
- The orphan was removed by hand:
  `DELETE /api/v1/provisioning/alert-rules/zcrypto-gate-not-met` → `204`.
- The live instance now holds exactly the 7 rules in `alerts.yaml`, all `health=ok`.


## Done so far

- **The mis-point half is closed (2026-07-14).** `infra/scripts/grafana-push.sh` no longer takes the
  stack URL and datasource/folder UIDs as unvalidated required env vars: they now **default to this
  project's real, verified values** (`https://zcrypto2026.grafana.net`, `grafanacloud-prom`,
  `grafanacloud-logs`, folder `bfrxdfoybx98gb`), read back from the live stack and confirmed to match
  `infra/grafana/alerts.yaml` (7 rules, titles in sync, both formerly-broken rules correct). The
  script also echoes the resolved values before pushing, so a wrong target is visible rather than
  silent. This removes the failure that actually happened: "first datasource of each type" grabbed
  `grafanacloud-usage` + `grafanacloud-alert-state-history` and repointed all 7 rules at the wrong
  data while still reporting `health=ok`.

- **The dashboard had the same defect, one layer over (2026-07-14).** `zcrypto-dashboard.json` used
  `datasource`-type template variables (`DS_PROMETHEUS` / `DS_LOKI`) with `current: null` — so no
  datasource was pinned and every panel queried whatever Grafana's "first datasource of this type"
  happened to be, i.e. `grafanacloud-usage` (billing metrics) and `grafanacloud-alert-state-history`.
  The dashboard was therefore rendering the wrong data unless a human re-picked the right source from
  the dropdown on every visit. Both variables are deleted and all 19 panels now hard-pin
  `grafanacloud-prom` / `grafanacloud-logs`; the dropdowns are gone. Verified by reading the live
  dashboard back after the push.

## Suggested next steps

- **The prune half is still open.** The push never deletes: a rule removed from `alerts.yaml` keeps
  evaluating and emailing forever, and a *renamed* rule (new `uid`) leaves the old one live beside it.
  Add a prune step that lists the live rules in the folder and deletes any whose `uid` is absent from
  `alerts.yaml` — with a dry-run first, since deleting an alert rule is not reversible from the repo.
- **Always read the rules back after a push** and assert each `datasourceUid` — the API accepts a wrong
  UID happily and reports `health=ok`.
