#!/usr/bin/env bash
# Drill A2's reboot-on-rest, run as infra/runbooks/drills-order-path.md#drill-a2 says: $1 the plan id or its prefix,
# $2 the deadline in seconds, $3 = live to reboot, anything else only prints the decision. JOURNAL overrides the
# journal root for a dry test.
set -u
prefix="$1"; deadline=$(( $(date +%s) + ${2:-900} )); mode="${3:-dry}"
journal="${JOURNAL:-/var/lib/zcrypto-engine/journal}"
while [ "$(date +%s)" -lt "$deadline" ]; do
  verdict=$(python3 - "$prefix" "$journal" <<'PY'
import json, pathlib, sys
prefix, root = sys.argv[1], pathlib.Path(sys.argv[2])
paths = list(root.glob("*/exec-*.json"))
if not paths:
    print("WAIT no execution record"); sys.exit()
d = json.loads(max(paths, key=lambda q: q.stat().st_mtime).read_text())
plans = [e for e in d.get("plans", []) if e["plan_id"].startswith(prefix)]
if not plans:
    print("WAIT no plan"); sys.exit()
plan = plans[-1]
intent = plan["intents"][0] if plan["intents"] else None
if intent is None:
    print("WAIT no intent"); sys.exit()
rows = [r for r in d["submitted"] if r["plan_id"] == plan["plan_id"] and r["intent_index"] == 0]
row = rows[-1] if rows else None
txid = next((ev.get("venue_order_id") for ev in (row or {}).get("events", []) if ev.get("venue_order_id")), None)
if intent["outcome"] == "pending" and row and row["state"] == "accepted" and row["filled_qty"] == 0 and txid:
    print(f"REST {plan['plan_id']} {row['client_order_id']} {txid}")
elif intent["outcome"] != "pending" or intent["filled_qty"] or (row and (row["filled_qty"] or row["state"] not in ("initialized", "submitted", "accepted"))):
    print(f"STOP {plan['plan_id']} intent={intent['outcome']} filled={intent['filled_qty']} row={row and row['state']}")
else:
    print(f"WAIT {plan['plan_id']} intent={intent['outcome']} row={row and row['state']}")
PY
)
  case "$verdict" in
    REST*) echo "$(date -u +%FT%T.%3NZ) $verdict"; if [ "$mode" = live ]; then systemctl reboot; fi; exit 0 ;;
    STOP*) echo "$(date -u +%FT%T.%3NZ) $verdict -- no reboot"; exit 3 ;;
  esac
  sleep 0.2
done
echo "$(date -u +%FT%TZ) TIMEOUT, last: $verdict -- no reboot"; exit 4
