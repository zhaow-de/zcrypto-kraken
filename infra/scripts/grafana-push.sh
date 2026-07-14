#!/usr/bin/env bash
# Pushes the committed-as-code Grafana dashboard + alert rules (infra/grafana/) to the
# already-provisioned Grafana Cloud instance (spec 00049, Role B / Task 4). Idempotent: the
# dashboard call always overwrites by its fixed uid (zcrypto-main); each alert rule upserts by
# its own stable `uid` (GET to check whether it already exists, then POST to create or PUT to
# update) -- safe to re-run after any commit to infra/grafana/.
#
# Env. Only GRAFANA_SA_TOKEN has no default (it is the secret); the rest default to THIS project's
# real, verified values so nobody has to guess them again -- guessing them wrong is not a harmless
# error, it is T0034: "first datasource of each type" once silently repointed all 7 rules at the
# wrong data while still reporting health=ok. Override only to target a different stack.
#   GRAFANA_SA_TOKEN           (REQUIRED) service-account token: dashboards + alerting-provisioning write
#   GRAFANA_URL                default https://zcrypto2026.grafana.net
#   GRAFANA_PROM_DS_UID        default grafanacloud-prom   (NOT grafanacloud-usage / -alert-state-history)
#   GRAFANA_LOKI_DS_UID        default grafanacloud-logs
#   GRAFANA_ALERT_FOLDER_UID   default bfrxdfoybx98gb      (the `zcrypto` folder)
#
# The alert-rules call targets Grafana's **Alerting Provisioning HTTP API**
# (POST/PUT/GET /api/v1/provisioning/alert-rules[/:uid]), which is JSON-only and one rule per
# call -- the `apiVersion: 1` / `groups:` file-provisioning shape is a different mechanism and is
# not accepted here (and file provisioning isn't usable on Grafana Cloud SaaS at all). See
# https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/
#
# The defaults above were read back from the LIVE stack on 2026-07-14 (7 rules, folder bfrxdfoybx98gb,
# datasources grafanacloud-prom / grafanacloud-logs) and confirmed to match infra/grafana/alerts.yaml.
# After ANY push, read the rules back and check the datasourceUid of each -- the API accepts a wrong
# UID happily and reports health=ok (T0034).
set -euo pipefail

: "${GRAFANA_SA_TOKEN:?GRAFANA_SA_TOKEN is required}"
GRAFANA_URL="${GRAFANA_URL:-https://zcrypto2026.grafana.net}"
GRAFANA_PROM_DS_UID="${GRAFANA_PROM_DS_UID:-grafanacloud-prom}"
GRAFANA_LOKI_DS_UID="${GRAFANA_LOKI_DS_UID:-grafanacloud-logs}"
GRAFANA_ALERT_FOLDER_UID="${GRAFANA_ALERT_FOLDER_UID:-bfrxdfoybx98gb}"
echo "grafana-push: stack=$GRAFANA_URL prom=$GRAFANA_PROM_DS_UID loki=$GRAFANA_LOKI_DS_UID folder=$GRAFANA_ALERT_FOLDER_UID" >&2

command -v python3 >/dev/null 2>&1 || { echo "grafana-push: python3 is required" >&2; exit 1; }
python3 -c "import yaml" >/dev/null 2>&1 \
  || { echo "grafana-push: python3's PyYAML module is required (pip install pyyaml)" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "grafana-push: jq is required" >&2; exit 1; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
auth=(-H "Authorization: Bearer ${GRAFANA_SA_TOKEN}")

echo "grafana-push: pushing dashboard"
dashboard_payload=$(python3 -c '
import json, os, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({"dashboard": d, "folderUid": os.environ["GRAFANA_ALERT_FOLDER_UID"], "overwrite": True}))
' "${root}/infra/grafana/zcrypto-dashboard.json")
curl -fsS -X POST "${GRAFANA_URL}/api/dashboards/db" \
  "${auth[@]}" -H "Content-Type: application/json" -d "${dashboard_payload}" >/dev/null

echo "grafana-push: pushing alert rules"
# One-time YAML -> JSON conversion (the file is YAML only for its inline comments); everything
# after this is plain JSON handled by jq, substituting the ${GRAFANA_*_UID} placeholder tokens
# from this script's own environment (the provisioning API has no template substitution of its
# own).
rules_json=$(python3 -c '
import json, sys, yaml
print(json.dumps(yaml.safe_load(open(sys.argv[1]))["rules"]))
' "${root}/infra/grafana/alerts.yaml")

rule_uids=$(jq -r '.[].uid' <<<"${rules_json}")

while IFS= read -r uid; do
  [ -n "${uid}" ] || continue
  rule_payload=$(jq --arg uid "${uid}" \
    --arg prom "${GRAFANA_PROM_DS_UID}" \
    --arg loki "${GRAFANA_LOKI_DS_UID}" \
    --arg folder "${GRAFANA_ALERT_FOLDER_UID}" '
    .[] | select(.uid == $uid) |
    walk(
      if type == "string" then
        gsub("\\$\\{GRAFANA_PROM_DS_UID\\}"; $prom)
        | gsub("\\$\\{GRAFANA_LOKI_DS_UID\\}"; $loki)
        | gsub("\\$\\{GRAFANA_ALERT_FOLDER_UID\\}"; $folder)
      else . end
    )
  ' <<<"${rules_json}")

  status=$(curl -s -o /dev/null -w "%{http_code}" "${auth[@]}" \
    "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}")
  if [ "${status}" = "200" ]; then
    curl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}" \
      "${auth[@]}" -H "Content-Type: application/json" -d "${rule_payload}" >/dev/null
  else
    curl -fsS -X POST "${GRAFANA_URL}/api/v1/provisioning/alert-rules" \
      "${auth[@]}" -H "Content-Type: application/json" -d "${rule_payload}" >/dev/null
  fi
done <<<"${rule_uids}"

echo "grafana-push: done"
