#!/usr/bin/env bash
# Pushes the committed-as-code Grafana dashboard + alert rules (infra/grafana/) to the
# already-provisioned Grafana Cloud instance (spec 00049, Role B / Task 4). Idempotent: the
# dashboard call always overwrites by its fixed uid (zcrypto-main); each alert rule upserts by
# its own stable `uid` (GET to check whether it already exists, then POST to create or PUT to
# update) -- safe to re-run after any commit to infra/grafana/.
#
# Env (vault-sourced -- see infra/nas/README.md's Grafana Cloud creds section):
#   GRAFANA_URL                Grafana Cloud stack base URL, e.g. https://<stack>.grafana.net
#   GRAFANA_SA_TOKEN           Service-account token, dashboards + alerting-provisioning write scope
#   GRAFANA_PROM_DS_UID        Prometheus datasource UID on the instance (alert rule queries)
#   GRAFANA_LOKI_DS_UID        Loki datasource UID on the instance (the ERROR-logs rule)
#   GRAFANA_ALERT_FOLDER_UID   Folder UID the alert rules provision into
#
# The alert-rules call targets Grafana's **Alerting Provisioning HTTP API**
# (POST/PUT/GET /api/v1/provisioning/alert-rules[/:uid]), which is JSON-only and one rule per
# call -- the `apiVersion: 1` / `groups:` file-provisioning shape is a different mechanism and is
# not accepted here (and file provisioning isn't usable on Grafana Cloud SaaS at all). See
# https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/http-api-provisioning/
#
# NOTE: this repo has no live Grafana Cloud access to verify the exact call from here -- confirm
# the datasource + folder UIDs and test-fire each rule during the attended deploy shakedown
# (docs/specs/00049), same caveat as infra/nas/config.alloy's "Verification note" in
# infra/nas/README.md.
set -euo pipefail

: "${GRAFANA_URL:?GRAFANA_URL is required}"
: "${GRAFANA_SA_TOKEN:?GRAFANA_SA_TOKEN is required}"
: "${GRAFANA_PROM_DS_UID:?GRAFANA_PROM_DS_UID is required}"
: "${GRAFANA_LOKI_DS_UID:?GRAFANA_LOKI_DS_UID is required}"
: "${GRAFANA_ALERT_FOLDER_UID:?GRAFANA_ALERT_FOLDER_UID is required}"

command -v python3 >/dev/null 2>&1 || { echo "grafana-push: python3 is required" >&2; exit 1; }
python3 -c "import yaml" >/dev/null 2>&1 \
  || { echo "grafana-push: python3's PyYAML module is required (pip install pyyaml)" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "grafana-push: jq is required" >&2; exit 1; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
auth=(-H "Authorization: Bearer ${GRAFANA_SA_TOKEN}")

echo "grafana-push: pushing dashboard"
dashboard_payload=$(python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({"dashboard": d, "overwrite": True}))
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
