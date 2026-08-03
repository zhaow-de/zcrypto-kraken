#!/usr/bin/env bash
# Verify-by-outcome after an ops converge, as one command (traceability: spec 00083 D3). Six
# checks through grafana-query.py; each prints PASS/FAIL; exit 0 iff all pass. "(no series)" is a
# FAIL, never a zero — an empty query is not an absent event.
set -uo pipefail   # deliberately NOT -e: a failed query is a FAIL result, not a crash
QUERY="${ZCRYPTO_GRAFANA_QUERY:-uv run python infra/scripts/grafana-query.py}"
fails=0

# check <name> <promql> <mode: zero|under> [limit]
check() {
  local name="$1" q="$2" mode="$3" limit="${4:-0}" out vals bad
  if ! out=$(timeout 60 $QUERY "$q" 2>&1); then
    echo "FAIL $name — query error: $(printf '%s' "$out" | tail -1)"
    fails=$((fails + 1)); return
  fi
  vals=$(printf '%s\n' "$out" | sed -n 's/^  .*= //p')
  if [ -z "$vals" ]; then
    echo "FAIL $name — no series (an empty query is not a zero)"
    fails=$((fails + 1)); return
  fi
  bad=$(printf '%s\n' "$vals" | awk -v mode="$mode" -v l="$limit" \
    'mode=="zero" && $1+0 != 0 {n++} mode=="under" && $1+0 >= l {n++} END{print n+0}')
  if [ "$bad" -eq 0 ]; then
    echo "PASS $name ($(printf '%s' "$vals" | paste -sd, -))"
  else
    echo "FAIL $name — $bad series out of bounds ($(printf '%s' "$vals" | paste -sd, -))"
    fails=$((fails + 1))
  fi
}

check "archive-pull exit code" 'ops_archive_pull_exit_code' zero
check "panel exit code" 'ops_panel_exit_code' zero
check "reconcile freshness (s)" 'time() - node_textfile_mtime_seconds{file=~".*reconcile.prom"}' under 4200
check "residual-gap counter unbumped (2h)" 'increase(zcrypto_reconcile_residual_gap_seconds_total[2h])' zero
check "healable-gap counter unbumped (2h)" 'increase(zcrypto_reconcile_healable_gap_seconds_total[2h])' zero
check "healthchecks down" 'hc_checks_down_total' zero

if [ "$fails" -eq 0 ]; then echo "ops-postverify: ALL PASS"; else echo "ops-postverify: $fails FAIL"; fi
[ "$fails" -eq 0 ]
