#!/usr/bin/env bash
# The documented converge path (traceability: spec 00083 D1): preview first, typed-limit confirm,
# then the real pass through run.sh (which loads the vaulted deploy keys into a throwaway agent).
# Usage: converge.sh <playbook.yml> --limit <target> [more ansible args...]
# rc 2 usage | rc 3 confirm-abort / no tty | rc 4 preview failed | else the real pass's own exit.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"

usage() {
  echo "converge.sh requires a playbook and --limit — a bare site.yml still runs every play." >&2
  echo "usage: converge.sh <playbook.yml> --limit <host> [more ansible args...]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
PLAYBOOK="$1"; shift
case "$PLAYBOOK" in --*) usage ;; esac

LIMIT=""; CHECK_ONLY=0; prev=""
for a in "$@"; do
  [ "$prev" = "--limit" ] && LIMIT="$a"
  case "$a" in
    --limit=*) LIMIT="${a#--limit=}" ;;
    --check) CHECK_ONLY=1 ;;
  esac
  prev="$a"
done
[ -n "$LIMIT" ] || usage

echo "== preview: --check --diff =="
"$SD/run.sh" "$PLAYBOOK" --check --diff "$@" || {
  echo "converge.sh: preview failed — fix the check pass before converging" >&2
  exit 4
}

if [ "$CHECK_ONLY" -eq 1 ]; then
  echo "== --check requested: preview only, nothing to converge =="
  exit 0
fi

# /dev/tty, never stdin: a pipe or heredoc must not be able to drive the confirm. No controlling
# terminal -> refuse; unattended contexts do not converge through this path.
if ! { : < /dev/tty; } 2>/dev/null; then
  echo "converge.sh: no controlling terminal — the confirm gate needs an attended session" >&2
  exit 3
fi
printf 'Type the --limit value (%s) to converge, anything else aborts: ' "$LIMIT" > /dev/tty
IFS= read -r reply < /dev/tty || reply=""
if [ "$reply" != "$LIMIT" ]; then
  echo "converge.sh: aborted — confirmation did not match the --limit value; nothing executed" >&2
  exit 3
fi
# The real pass, RECORDED. Every converge appends one JSON line -- the target, the tags, every -e
# operand (digests, flags, override reasons; never a secret, none travels on the command line), the
# tree it ran from, and how it ended. The digest and the timestamp a rollback needs are then written
# by the pass that set them, never re-typed from memory into fleet-pins.md afterwards. Preview-only
# runs and aborted confirms never reach this point, so they leave no line.
set +e
"$SD/run.sh" "$PLAYBOOK" "$@"
rc=$?
set -e
LOG="${ZCRYPTO_DEPLOY_LOG:-$SD/../../../docs/reference/deploy-log.jsonl}"
TAGS=""; EV=""; prev=""
for a in "$@"; do
  [ "$prev" = "--tags" ] && TAGS="$a"
  [ "$prev" = "-e" ] && EV="$EV$a"$'\n'
  case "$a" in
    --tags=*) TAGS="${a#--tags=}" ;;
    --extra-vars=*) EV="$EV${a#--extra-vars=}"$'\n' ;;
  esac
  prev="$a"
done
REV="$(git -C "$SD" rev-parse HEAD 2>/dev/null || echo unknown)"
DIRTY=false; [ -n "$(git -C "$SD" status --porcelain 2>/dev/null)" ] && DIRTY=true
# Best-effort and LOUD, never fatal: the pass has already run, so its rc is the truth this script
# returns; a record that cannot be written is printed for the operator to append by hand instead of
# being turned into a converge failure that did not happen.
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev = sys.argv[1:9]
extra = {}
for line in ev.splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        extra[k.strip()] = v.strip()
rec = {
    "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "playbook": playbook, "limit": limit, "tags": tags, "extra_vars": extra,
    "revision": rev, "dirty": dirty == "true", "rc": int(rc),
}
line = json.dumps(rec, sort_keys=True)
try:
    with open(log, "a") as f:
        f.write(line + "\n")
except OSError as exc:
    print(f"converge.sh: could not append to {log}: {exc}\n{line}", file=sys.stderr)
    raise SystemExit(1)
PYREC
exit "$rc"
