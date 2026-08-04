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
exec "$SD/run.sh" "$PLAYBOOK" "$@"
