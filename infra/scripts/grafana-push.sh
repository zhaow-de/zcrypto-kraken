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
#   GRAFANA_SLACK_WEBHOOK_URL  (REQUIRED for the Slack section) Slack incoming-webhook URL, vaulted
#                              as slack_webhook_url in infra/ansible/group_vars/capture_host/vault.yml.
#                              Unset/empty SKIPS the section cleanly -- the script stays runnable
#                              without it (T0047).
#   (receivers `metrics`/`logs` are as-code constants minted by this script -- no receiver env)
#   GRAFANA_SLACK_RECEIVER     REMOVED 2026-07-16 (receiver names are as-code constants now).
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
# `export` is load-bearing: the python3 heredocs below read these from os.environ, so a plain shell
# assignment is invisible to them (they used to be exported by whoever supplied them).
export GRAFANA_URL="${GRAFANA_URL:-https://zcrypto2026.grafana.net}"
export GRAFANA_PROM_DS_UID="${GRAFANA_PROM_DS_UID:-grafanacloud-prom}"
export GRAFANA_LOKI_DS_UID="${GRAFANA_LOKI_DS_UID:-grafanacloud-logs}"
export GRAFANA_ALERT_FOLDER_UID="${GRAFANA_ALERT_FOLDER_UID:-bfrxdfoybx98gb}"
echo "grafana-push: stack=$GRAFANA_URL prom=$GRAFANA_PROM_DS_UID loki=$GRAFANA_LOKI_DS_UID folder=$GRAFANA_ALERT_FOLDER_UID" >&2

command -v python3 >/dev/null 2>&1 || { echo "grafana-push: python3 is required" >&2; exit 1; }
python3 -c "import yaml" >/dev/null 2>&1 \
  || { echo "grafana-push: python3's PyYAML module is required (pip install pyyaml)" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "grafana-push: jq is required" >&2; exit 1; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
auth=(-H "Authorization: Bearer ${GRAFANA_SA_TOKEN}")

# Every dashboard under infra/grafana/*-dashboard.json is pushed, keyed by its own `uid` — add a
# file, it ships. (Metrics and logs are separate dashboards: mixing them puts log-only filters on a
# metrics board, where they do nothing.)
for dash in "${root}"/infra/grafana/*-dashboard.json; do
  echo "grafana-push: pushing dashboard $(basename "${dash}")"
  dashboard_payload=$(python3 -c '
import json, os, sys
d = json.load(open(sys.argv[1]))
print(json.dumps({"dashboard": d, "folderUid": os.environ["GRAFANA_ALERT_FOLDER_UID"], "overwrite": True}))
' "${dash}")
  curl -fsS -X POST "${GRAFANA_URL}/api/dashboards/db" \
    "${auth[@]}" -H "Content-Type: application/json" -d "${dashboard_payload}" >/dev/null
done

# --- Slack contact points: `metrics` + `logs` receivers (T0047; generalized 2026-07-16) -----------
# Two receivers, both delivering to the SAME Slack webhook: `metrics` (resolve messages ON) is the
# default + what every metrics rule pins via notification_settings; `logs` (resolve messages OFF --
# Loki alerts resolve by aging, a resolve ping is noise) is pinned by the Loki-sourced rules. Both
# are minted here as-code by stable uid, so there is no receiver-name guessing (the T0034 guard
# moved from "must pre-exist" to "we are the source of truth"). This section runs BEFORE the rules
# push: Grafana validates a rule's notification_settings.receiver against existing receivers.
if [ -z "${GRAFANA_SLACK_WEBHOOK_URL:-}" ]; then
  echo "grafana-push: GRAFANA_SLACK_WEBHOOK_URL not set -- skipping Slack contact-point section" >&2
else
  existing_cps=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/contact-points")
  upsert_slack_integration() { # uid receiver_name disable_resolve
    local uid="$1" name="$2" disable="$3"
    local payload
    payload=$(jq -n --arg uid "${uid}" --arg name "${name}" --arg url "${GRAFANA_SLACK_WEBHOOK_URL}" --argjson disable "${disable}" \
      '{uid: $uid, name: $name, type: "slack", settings: {url: $url}, disableResolveMessage: $disable}')
    if jq -e --arg uid "${uid}" 'any(.[]; .uid == $uid)' <<<"${existing_cps}" >/dev/null; then
      curl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/contact-points/${uid}" \
        "${auth[@]}" -H "Content-Type: application/json" -d "${payload}" >/dev/null
    else
      curl -fsS -X POST "${GRAFANA_URL}/api/v1/provisioning/contact-points" \
        "${auth[@]}" -H "Content-Type: application/json" -d "${payload}" >/dev/null
    fi
    echo "grafana-push: upserted Slack integration uid=${uid} receiver=${name} disableResolve=${disable}" >&2
  }
  upsert_slack_integration "zcrypto-slack-metrics" "metrics" false
  upsert_slack_integration "zcrypto-slack-logs" "logs" true

  # Default route -> `metrics` (GET the tree, mutate only the receiver, PUT it back verbatim). The
  # tree may carry UI provenance, hence X-Disable-Provenance.
  policy=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/policies")
  if [ "$(jq -r '.receiver' <<<"${policy}")" != "metrics" ]; then
    jq '.receiver = "metrics"' <<<"${policy}" \
      | curl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/policies" \
          "${auth[@]}" -H "Content-Type: application/json" -H "X-Disable-Provenance: true" -d @- >/dev/null
    echo "grafana-push: notification-policy default route -> metrics" >&2
  fi

  # One-time legacy cleanup: the pre-2026-07-16 integration (uid zcrypto-slack-webhook, receiver
  # "email"). Deleted only AFTER the rules push below has repointed every rule, so it can never
  # strand a referenced receiver -- see the post-rules block.

  # Read-back verify (T0034): both integrations present with the right name/type. Grafana redacts
  # settings.url on read-back, so uid/name/type only.
  live_cps=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/contact-points")
  for pair in "zcrypto-slack-metrics metrics" "zcrypto-slack-logs logs"; do
    uid="${pair%% *}"; name="${pair##* }"
    if ! jq -e --arg uid "${uid}" --arg name "${name}" \
        'any(.[]; .uid == $uid and .type == "slack" and .name == $name)' <<<"${live_cps}" >/dev/null; then
      echo "grafana-push: Slack integration verification FAILED for uid=${uid} name=${name}" >&2
      exit 1
    fi
  done
  echo "grafana-push: Slack receivers metrics+logs verified" >&2
fi

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

# --- Read the rules back and assert each datasource (T0034) ---------------------------------------
# The provisioning API accepts a wrong datasourceUid happily and reports health=ok, so a typo or a
# drifted default silently repoints a rule at grafanacloud-usage / -alert-state-history and it never
# fires on the data it should. Read every rule we just pushed back and fail if any query node points
# at a datasource that is neither the prom nor the loki UID we intended.
echo "grafana-push: verifying datasources on the pushed rules" >&2
ds_bad=0
while IFS= read -r uid; do
  [ -n "${uid}" ] || continue
  live=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}")
  # every query node's datasourceUid, excluding the expression node (__expr__)
  bad=$(jq -r --arg prom "${GRAFANA_PROM_DS_UID}" --arg loki "${GRAFANA_LOKI_DS_UID}" '
    [.data[].datasourceUid] | map(select(. != "__expr__" and . != $prom and . != $loki)) | .[]
  ' <<<"${live}")
  if [ -n "${bad}" ]; then
    echo "grafana-push: !! ${uid} points at an UNEXPECTED datasource: ${bad}" >&2
    ds_bad=1
  fi
done <<<"${rule_uids}"
[ "${ds_bad}" = "0" ] || { echo "grafana-push: datasource check FAILED — a rule is pointing at the wrong data (T0034)" >&2; exit 1; }

# --- Prune orphaned rules (T0034) ----------------------------------------------------------------
# The push upserts but never deletes: a rule removed from alerts.yaml keeps evaluating and emailing
# forever, and a rule that changed uid leaves the old one live beside the new. List every rule live in
# OUR folder whose uid is absent from alerts.yaml. Deleting an alert rule is NOT reversible from the
# repo, so this is DRY-RUN by default: it only reports the orphans. Re-run with GRAFANA_PRUNE=1 to
# actually delete them (scoped to GRAFANA_ALERT_FOLDER_UID so a rule in another folder is never touched).
echo "grafana-push: checking for orphaned rules in folder ${GRAFANA_ALERT_FOLDER_UID}" >&2
all_live=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/alert-rules")
orphans=$(jq -r --arg folder "${GRAFANA_ALERT_FOLDER_UID}" --argjson keep "$(jq '[.[].uid]' <<<"${rules_json}")" '
  .[] | select((.folderUID // .folderUid) == $folder) | select(.uid as $u | ($keep | index($u)) == null) | .uid
' <<<"${all_live}")
if [ -z "${orphans}" ]; then
  echo "grafana-push: no orphaned rules" >&2
else
  while IFS= read -r uid; do
    [ -n "${uid}" ] || continue
    if [ "${GRAFANA_PRUNE:-0}" = "1" ]; then
      curl -fsS -X DELETE "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}" >/dev/null
      echo "grafana-push: DELETED orphaned rule ${uid}" >&2
    else
      echo "grafana-push: ORPHAN (live but not in alerts.yaml): ${uid}  — re-run with GRAFANA_PRUNE=1 to delete" >&2
    fi
  done <<<"${orphans}"
fi

# --- Legacy cleanup: the pre-2026-07-16 "email"-named Slack integration ---------------------------
# Safe only here: the rules push above repointed every rule to metrics/logs, and the policy default
# is metrics, so nothing references the old receiver any more.
if [ -n "${GRAFANA_SLACK_WEBHOOK_URL:-}" ]; then
  if curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/contact-points" \
      | jq -e 'any(.[]; .uid == "zcrypto-slack-webhook")' >/dev/null; then
    curl -fsS -X DELETE "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/contact-points/zcrypto-slack-webhook" >/dev/null
    echo "grafana-push: legacy integration zcrypto-slack-webhook (receiver email) deleted" >&2
  fi
fi

echo "grafana-push: done"
