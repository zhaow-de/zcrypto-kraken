---
status: open
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

## Suggested next steps

- **(autonomous)** **Resolve the datasource UIDs in the script instead of trusting env vars.** Query
  `/api/datasources` and select by *name/role*, not by "first of type" — e.g. the Prometheus one that is
  `isDefault`, and the Loki one whose name ends `-logs`. Fail loudly if the choice is ambiguous. Keep the
  env vars only as an explicit override.
- **(autonomous)** **Make the push authoritative: prune orphans.** After upserting, list the provisioned
  rules and **delete any whose `uid` is not in `alerts.yaml`** (guarded to the `zcrypto*` uid prefix /
  the `zcrypto` folder so it can never touch anything else). Then the repo genuinely *is* the source of
  truth, and deleting a rule from the file deletes it from the instance.
- **(autonomous)** **Assert after pushing**: read the rules back and check each one's `datasourceUid` is
  the expected one and `health=ok` — the push should verify itself rather than print "done".
