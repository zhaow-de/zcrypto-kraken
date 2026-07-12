#!/usr/bin/env bash
# Pushes the committed-as-code Grafana dashboard + alert rules (infra/grafana/) to the
# already-provisioned Grafana Cloud instance (spec 00049, Role B / Task 4). Idempotent: the
# dashboard call always overwrites by its fixed uid (zcrypto-main); safe to re-run after any
# commit to infra/grafana/.
#
# Env (vault-sourced -- see infra/nas/README.md's Grafana Cloud creds section):
#   GRAFANA_URL       Grafana Cloud stack base URL, e.g. https://<stack>.grafana.net
#   GRAFANA_SA_TOKEN  Service-account token, dashboards + alerting-provisioning write scope
#
# NOTE: the alert-rules call targets Grafana's alerting provisioning API; this repo has no live
# Grafana Cloud access to verify the exact call from here -- confirm/adjust against the instance
# during the attended deploy shakedown (docs/specs/00049), same caveat as infra/nas/config.alloy's
# "Verification note" in infra/nas/README.md.
set -euo pipefail

: "${GRAFANA_URL:?GRAFANA_URL is required}"
: "${GRAFANA_SA_TOKEN:?GRAFANA_SA_TOKEN is required}"

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
curl -fsS -X POST "${GRAFANA_URL}/api/v1/provisioning/alert-rules" \
  "${auth[@]}" -H "Content-Type: application/yaml" \
  --data-binary "@${root}/infra/grafana/alerts.yaml" >/dev/null

echo "grafana-push: done"
