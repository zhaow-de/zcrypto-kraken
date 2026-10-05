#!/usr/bin/env bash
# Pushes the committed dashboards, notification templates and alert rules under infra/grafana/ to
# the Grafana stack GRAFANA_URL names (spec 00049, Role B). Idempotent: each dashboard overwrites by
# its own uid, each alert rule upserts by its own stable uid.
#
# Run it from a checkout that carries origin/develop's tip with infra/grafana/ clean: it pushes the
# working tree whole, and its prune deletes the folder's rules that tree lacks. MERGED develop is the
# default, since summaries and panel descriptions cite repo paths; a feature-branch push is admitted
# only under .claude/skills/zcrypto-grafana-push/SKILL.md's conditions; an open PR with a live push holds
# every other push and every prune until it merges or closes, and a prune runs from develop alone.
#
# GRAFANA_SA_TOKEN is the one variable with no default. Obtain it with `grafana_auth.py`'s
# `vault_var("grafana_sa_token")`, loaded by path the way `grafana-query.py` loads it -- it
# encapsulates the two decrypt footguns its own docstring records, so do not hand-roll the
# extraction. Assign it by command substitution and nothing else: the value must never reach a
# file, a log or argv. For a PromQL or LogQL read-back use `infra/scripts/grafana-query.py`, which needs no
# token from you at all.
#
# PATH note, which the PyYAML refusal below points at: this script calls bare `python3`, and PyYAML
# lives in the project venv, so run it with that venv first on PATH --
# `PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh` from the repo root -- rather than
# installing PyYAML into the system python, where a second copy drifts unseen.
#
# Two stacks take this push until the Grafana Cloud leg retires. With no GRAFANA_URL it goes to Grafana
# Cloud and leaves out the rule groups the observability node alone evaluates, which have no data there;
# the node's push is `infra/runbooks/mon.md#mon-push`.
#
# Rules go one per call through Grafana's Alerting Provisioning HTTP API; the `apiVersion: 1` /
# `groups:` file-provisioning shape is not accepted here and is not available on Grafana Cloud SaaS.
#
# Verify a DASHBOARD by RENDERING it, never by reading its JSON back: a read-back proves what was
# stored, not what a panel DISPLAYS, and a unit that reaches a string column renders every cell `NaN`
# while the stored JSON looks perfect.
#
#   printf 'header = "Authorization: Bearer %s"\n' "$(uv run python -c '<the vault_var("grafana_sa_token") one-liner>')" \
#     | curl -fsS -K - -o panel.png \
#     "$GRAFANA_URL/render/d-solo/<dashboard-uid>/x?panelId=<id>&width=1100&height=420&from=now-6h&to=now"
#
# Append &var-<name>=<value> per template variable, and render the NARROWED case too: a query
# returning a single series yields one frame whose value field is named `Value` rather than `Value
# #<refId>`, so name-matched renames and overrides miss there and only there.
set -euo pipefail

: "${GRAFANA_SA_TOKEN:?GRAFANA_SA_TOKEN is required}"
# `export` is load-bearing: the python3 heredocs below read these from os.environ, so a plain shell
# assignment is invisible to them (they used to be exported by whoever supplied them).
export GRAFANA_URL="${GRAFANA_URL:-https://zcrypto2026.grafana.net}"
export GRAFANA_PROM_DS_UID="${GRAFANA_PROM_DS_UID:-grafanacloud-prom}"
export GRAFANA_LOKI_DS_UID="${GRAFANA_LOKI_DS_UID:-grafanacloud-logs}"
export GRAFANA_ALERT_FOLDER_UID="${GRAFANA_ALERT_FOLDER_UID:-bfrxdfoybx98gb}"
# The rule groups this push leaves out, space-separated: none of their rules is sent, and one found live is
# reported as an orphan, which a prune deletes. `-`, never `:-`: set and empty skips no group whatever the host.
push_host="${GRAFANA_URL#*://}"; push_host="${push_host%%/*}"; push_host="${push_host##*@}"; push_host="${push_host%%:*}"; push_host="${push_host%.}"; push_host="${push_host,,}"
case "${push_host}" in
  *.grafana.net) skip_default="zcrypto-mon zcrypto-hc" ;;
  *) skip_default="" ;;
esac
export GRAFANA_SKIP_RULE_GROUPS="${GRAFANA_SKIP_RULE_GROUPS-${skip_default}}"
echo "grafana-push: stack=$GRAFANA_URL prom=$GRAFANA_PROM_DS_UID loki=$GRAFANA_LOKI_DS_UID folder=$GRAFANA_ALERT_FOLDER_UID skip-groups=${GRAFANA_SKIP_RULE_GROUPS:-<none>}" >&2
# Grafana Cloud never takes one of the node's groups: a rule of one that fires on no data would page the
# main channel. The default above skips them only while the variable is unset, so a push addressed to Grafana
# Cloud whose list does not name each of them is refused here, before any call.
case "${push_host}" in
  *.grafana.net)
    for group in ${skip_default}; do
      case " ${GRAFANA_SKIP_RULE_GROUPS} " in
        *" ${group} "*) ;;
        *)
          echo "grafana-push: refusing to push to Grafana Cloud without skipping the ${group} rule group -- GRAFANA_SKIP_RULE_GROUPS is set and does not name it: unset it for a Grafana Cloud push, or name the node in GRAFANA_URL" >&2
          exit 1
          ;;
      esac
    done
    ;;
esac

command -v python3 >/dev/null 2>&1 || { echo "grafana-push: python3 is required" >&2; exit 1; }
python3 -c "import yaml" >/dev/null 2>&1 \
  || { echo "grafana-push: python3's PyYAML module is required -- rerun with the project venv first on PATH (see the PATH note in this script's header); do not pip-install into the system python" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "grafana-push: jq is required" >&2; exit 1; }

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The bearer reaches curl as a config line on a pipe: a `-H` value is in argv.
gcurl() { curl -K <(printf 'header = "Authorization: Bearer %s"\n' "${GRAFANA_SA_TOKEN}") "$@"; }

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
  gcurl -fsS -X POST "${GRAFANA_URL}/api/dashboards/db" \
    -H "Content-Type: application/json" -d "${dashboard_payload}" >/dev/null
done

# One provisioned template object per infra/grafana/notification-templates/*.tmpl, named after the
# basename -- the name is what a contact point's `{{ template "..." . }}` resolves against, so
# renaming a file is visible in the provisioning API. Deliberately OUTSIDE the webhook-gated branch
# below, so a steady-state run with no webhook still ships template edits.
#
# ORDERING IS LOAD-BEARING: this runs BEFORE the contact points, because a contact point whose `{{
# template }}` target does not exist renders an EMPTY body, Grafana accepts that without complaint,
# and Slack then rejects the message. The read-back is the point for the same reason: the API stores
# whatever it is given and never parses the Go template, so a truncated or mis-escaped push is
# invisible until an alert renders blank on someone's phone. Both `$( )` substitutions strip
# trailing newlines, so a file's final newline is not a difference.
for tmpl in "${root}"/infra/grafana/notification-templates/*.tmpl; do
  [ -e "${tmpl}" ] || continue
  tname="$(basename "${tmpl}" .tmpl)"
  tmpl_payload=$(jq -n --arg name "${tname}" --rawfile template "${tmpl}" '{name: $name, template: $template}')
  gcurl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/templates/${tname}" \
    -H "Content-Type: application/json" -H "X-Disable-Provenance: true" -d "${tmpl_payload}" >/dev/null
  live_tmpl=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/templates/${tname}" | jq -r '.template')
  if [ "${live_tmpl}" != "$(cat "${tmpl}")" ]; then
    echo "grafana-push: notification template ${tname} did NOT read back byte-identical" >&2
    exit 1
  fi
  echo "grafana-push: notification template ${tname} pushed and verified byte-identical" >&2
done

# Slack contact points, the `metrics` and `logs` receivers (T0047). Both deliver to the same
# webhook: `metrics` has resolve messages ON and is what every metrics rule pins, `logs` has them
# OFF because Loki alerts resolve by aging and a resolve ping is noise. Both are minted here as-code
# by stable uid, so no receiver name is guessed. This runs BEFORE the rules push, because Grafana
# validates a rule's notification_settings.receiver against existing receivers.
if [ -z "${GRAFANA_SLACK_WEBHOOK_URL:-}" ]; then
  # Steady-state escape hatch: the receivers persist once minted, so a webhook-less run is fine
  # THEN. On a from-scratch stack they do not exist yet, and the rules push below would reference
  # nonexistent receivers -- verify both are live before proceeding, abort otherwise.
  preexisting_cps=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/contact-points")
  for name in metrics logs; do
    if ! jq -e --arg name "${name}" 'any(.[]; .name == $name)' <<<"${preexisting_cps}" >/dev/null; then
      echo "grafana-push: GRAFANA_SLACK_WEBHOOK_URL not set and receiver '${name}' does not exist on the stack -- set the webhook so the metrics/logs receivers can be minted before the rules push" >&2
      exit 1
    fi
    # The template-reference half of the read-back verify below, repeated HERE deliberately: that
    # one lives inside the webhook branch, so a contact point reverted in the UI would survive every
    # webhook-less steady-state run undetected. This predicate needs no webhook because it compares
    # template names rather than the url; RESTORING the reference does need one, since the upsert
    # rewrites the whole integration -- hence an instruction rather than a repair.
    if ! jq -e --arg name "${name}" \
        'any(.[]; .name == $name
             and ((.settings.title // "") | test("zcrypto\\.slack\\.title"))
             and ((.settings.text // "") | test("zcrypto\\.slack\\.body")))' <<<"${preexisting_cps}" >/dev/null; then
      echo "grafana-push: receiver '${name}' is live but no longer references the notification template -- it is rendering Grafana's stock message; re-run with GRAFANA_SLACK_WEBHOOK_URL set to restore the reference" >&2
      exit 1
    fi
  done
  echo "grafana-push: GRAFANA_SLACK_WEBHOOK_URL not set -- receivers metrics+logs already live, skipping Slack upserts" >&2
else
  existing_cps=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/contact-points")
  upsert_slack_integration() { # uid receiver_name disable_resolve title_tmpl body_tmpl
    local uid="$1" name="$2" disable="$3" title="$4" text="$5"
    local payload
    payload=$(jq -n --arg uid "${uid}" --arg name "${name}" --arg url "${GRAFANA_SLACK_WEBHOOK_URL}" \
      --argjson disable "${disable}" --arg title "${title}" --arg text "${text}" \
      '{uid: $uid, name: $name, type: "slack", settings: {url: $url, title: $title, text: $text}, disableResolveMessage: $disable}')
    if jq -e --arg uid "${uid}" 'any(.[]; .uid == $uid)' <<<"${existing_cps}" >/dev/null; then
      gcurl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/contact-points/${uid}" \
        -H "Content-Type: application/json" -d "${payload}" >/dev/null
    else
      gcurl -fsS -X POST "${GRAFANA_URL}/api/v1/provisioning/contact-points" \
        -H "Content-Type: application/json" -d "${payload}" >/dev/null
    fi
    echo "grafana-push: upserted Slack integration uid=${uid} receiver=${name} disableResolve=${disable}" >&2
  }
  # SINGLE-quoted references, so `{{`, `}}` and the bare `.` reach jq untouched by bash. Without a
  # title/text of their own both receivers fall back to Grafana's stock default.title/default.message.
  upsert_slack_integration "zcrypto-slack-metrics" "metrics" false \
    '{{ template "zcrypto.slack.title.metrics" . }}' '{{ template "zcrypto.slack.body.metrics" . }}'
  upsert_slack_integration "zcrypto-slack-logs" "logs" true \
    '{{ template "zcrypto.slack.title.logs" . }}' '{{ template "zcrypto.slack.body.logs" . }}'

  # Default route -> `metrics` (GET the tree, mutate only the receiver, PUT it back verbatim). The
  # tree may carry UI provenance, hence X-Disable-Provenance.
  policy=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/policies")
  if [ "$(jq -r '.receiver' <<<"${policy}")" != "metrics" ]; then
    jq '.receiver = "metrics"' <<<"${policy}" \
      | gcurl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/policies" \
          -H "Content-Type: application/json" -H "X-Disable-Provenance: true" -d @- >/dev/null
    echo "grafana-push: notification-policy default route -> metrics" >&2
  fi

  # One-time legacy cleanup: the pre-2026-07-16 integration (uid zcrypto-slack-webhook, receiver
  # "email"). Deleted only AFTER the rules push below has repointed every rule, so it can never
  # strand a referenced receiver -- see the post-rules block.

  # Read-back verify (T0034): both integrations present with the right name and type, and each still
  # POINTING AT THE TEMPLATE. Grafana redacts settings.url on read-back so the url cannot be
  # checked, but title and text are not secure fields and do read back, which is what catches a
  # contact point reverted to the stock template -- otherwise that resurfaces weeks later as "the
  # messages look like they used to" with nobody sure when. If a future Grafana redacts title/text
  # too, drop to a presence-only assertion rather than deleting the guard.
  live_cps=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/contact-points")
  for pair in "zcrypto-slack-metrics metrics" "zcrypto-slack-logs logs"; do
    uid="${pair%% *}"; name="${pair##* }"
    if ! jq -e --arg uid "${uid}" --arg name "${name}" \
        'any(.[]; .uid == $uid and .type == "slack" and .name == $name
             and ((.settings.title // "") | test("zcrypto\\.slack\\.title"))
             and ((.settings.text // "") | test("zcrypto\\.slack\\.body")))' <<<"${live_cps}" >/dev/null; then
      echo "grafana-push: Slack integration verification FAILED for uid=${uid} name=${name} -- absent, or no longer referencing the notification template" >&2
      exit 1
    fi
  done
  echo "grafana-push: Slack receivers metrics+logs verified, both referencing the notification template" >&2
fi

echo "grafana-push: pushing alert rules"
# One-time YAML -> JSON conversion (the file is YAML only for its inline comments); everything
# after this is plain JSON handled by jq, substituting the ${GRAFANA_*_UID} placeholder tokens
# from this script's own environment (the provisioning API has no template substitution of its
# own).
rules_split=$(python3 -c '
import json, os, sys, yaml
skipped = os.environ["GRAFANA_SKIP_RULE_GROUPS"]
rules = yaml.safe_load(open(sys.argv[1]))["rules"]
kept = [r for r in rules if r.get("ruleGroup") not in skipped.split()]
if len(kept) != len(rules):
    print(f"grafana-push: skipping {len(rules) - len(kept)} rule(s) of group(s): {skipped}", file=sys.stderr)
print(json.dumps({"kept": kept, "skipped": {r["uid"]: r["ruleGroup"] for r in rules if r.get("ruleGroup") in skipped.split()}}))
' "${root}/infra/grafana/alerts.yaml")
rules_json=$(jq -c '.kept' <<<"${rules_split}")
skipped_json=$(jq -c '.skipped' <<<"${rules_split}")

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

  status=$(gcurl -s -o /dev/null -w "%{http_code}" \
    "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}")
  if [ "${status}" = "200" ]; then
    gcurl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}" \
      -H "Content-Type: application/json" -d "${rule_payload}" >/dev/null
  else
    gcurl -fsS -X POST "${GRAFANA_URL}/api/v1/provisioning/alert-rules" \
      -H "Content-Type: application/json" -d "${rule_payload}" >/dev/null
  fi
done <<<"${rule_uids}"

# Read the rules back and assert each datasource (T0034): the provisioning API accepts a wrong
# datasourceUid happily and reports health=ok, so a typo or a drifted default silently repoints a
# rule at the usage or alert-state-history source and it never fires on the data it should.
echo "grafana-push: verifying datasources on the pushed rules" >&2
ds_bad=0
while IFS= read -r uid; do
  [ -n "${uid}" ] || continue
  live=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}")
  # every query node's datasourceUid, excluding the expression node (__expr__)
  bad=$(jq -r --arg prom "${GRAFANA_PROM_DS_UID}" --arg loki "${GRAFANA_LOKI_DS_UID}" '
    [.data[].datasourceUid] | map(select(. != "__expr__" and . != $prom and . != $loki)) | .[]
  ' <<<"${live}")
  if [ -n "${bad}" ]; then
    echo "grafana-push: !! ${uid} points at an UNEXPECTED datasource: ${bad}" >&2
    ds_bad=1
  fi
done <<<"${rule_uids}"
# T0034: "first datasource of each type" silently repointed every rule at the wrong data once.
[ "${ds_bad}" = "0" ] || { echo "grafana-push: datasource check FAILED — a rule is pointing at the wrong data" >&2; exit 1; }

# Prune orphaned rules (T0034). The push upserts and never deletes, so a rule removed from
# alerts.yaml keeps evaluating forever and a rule that changed uid leaves the old one live beside
# the new. Deleting a rule is NOT reversible from the repo, so this is DRY-RUN by default and
# reports only; GRAFANA_PRUNE=1 deletes, scoped to our folder so a rule elsewhere is never touched.
echo "grafana-push: checking for orphaned rules in folder ${GRAFANA_ALERT_FOLDER_UID}" >&2
all_live=$(gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/alert-rules")
orphans=$(jq -r --arg folder "${GRAFANA_ALERT_FOLDER_UID}" --argjson keep "$(jq '[.[].uid]' <<<"${rules_json}")" '
  .[] | select((.folderUID // .folderUid) == $folder) | select(.uid as $u | ($keep | index($u)) == null) | .uid
' <<<"${all_live}")
if [ -z "${orphans}" ]; then
  echo "grafana-push: no orphaned rules" >&2
else
  while IFS= read -r uid; do
    [ -n "${uid}" ] || continue
    if [ "${GRAFANA_PRUNE:-0}" = "1" ]; then
      gcurl -fsS -X DELETE "${GRAFANA_URL}/api/v1/provisioning/alert-rules/${uid}" >/dev/null
      echo "grafana-push: DELETED orphaned rule ${uid}" >&2
    else
      skipped_group=$(jq -r --arg uid "${uid}" '.[$uid] // empty' <<<"${skipped_json}")
      if [ -n "${skipped_group}" ]; then
        echo "grafana-push: ORPHAN (live, of skipped group ${skipped_group}): ${uid}  — re-run with GRAFANA_PRUNE=1 under .claude/skills/zcrypto-grafana-push/SKILL.md's Step 4 to delete" >&2
      else
        echo "grafana-push: ORPHAN (live but not in alerts.yaml): ${uid}  — re-run with GRAFANA_PRUNE=1 under .claude/skills/zcrypto-grafana-push/SKILL.md's Step 4 to delete" >&2
      fi
    fi
  done <<<"${orphans}"
fi

# --- Legacy cleanup: the pre-2026-07-16 "email"-named Slack integration ---------------------------
# Safe only here: the rules push above repointed every rule to metrics/logs, and the policy default
# is metrics, so nothing references the old receiver any more.
if [ -n "${GRAFANA_SLACK_WEBHOOK_URL:-}" ]; then
  if gcurl -fsS "${GRAFANA_URL}/api/v1/provisioning/contact-points" \
      | jq -e 'any(.[]; .uid == "zcrypto-slack-webhook")' >/dev/null; then
    gcurl -fsS -X DELETE "${GRAFANA_URL}/api/v1/provisioning/contact-points/zcrypto-slack-webhook" >/dev/null
    echo "grafana-push: legacy integration zcrypto-slack-webhook (receiver email) deleted" >&2
  fi
fi

echo "grafana-push: done"
