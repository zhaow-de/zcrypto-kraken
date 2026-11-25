#!/usr/bin/env bash
# The prescribed route for a session's command on a fleet host; a raw ssh is not refused here. The block comes on
# stdin, is judged by host_run_sh.py beside this script before anything runs, is recorded in the main checkout's
# .local/host-commands.jsonl, and runs as the alias's own ssh user: `bash -l -c` on the host, its stdin /dev/null.
# Usage: host-run.sh [--judge] [--timeout <seconds, 1-570, default 120>] <alias>  < block
# rc 64 usage: no alias, a bad timeout, an empty block, a terminal on stdin, a block that is not text
# | rc 65 refused, the rule named on stderr | rc 66 nothing could record the run, so nothing ran
# | rc 124 the run outlived --timeout and the local ssh was killed, said on stderr | else the block's own rc (255: ssh's own failure)
set -uo pipefail

SD="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO="$(cd "$SD/../.." && pwd -P)"
JUDGE="$SD/host_run_sh.py"
MAX_TIMEOUT=570

usage() {
  [ "$#" -eq 0 ] || echo "host-run: $1" >&2
  echo "usage: host-run.sh [--judge] [--timeout <seconds, 1-$MAX_TIMEOUT>] <alias>  < block" >&2
  exit 64
}
die() { echo "host-run: $2" >&2; exit "$1"; }

judge_only=0; secs=120; alias=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --judge) judge_only=1; shift ;;
    --timeout) [ "$#" -ge 2 ] || usage "--timeout takes a number of seconds"; secs="$2"; shift 2 ;;
    --timeout=*) secs="${1#--timeout=}"; shift ;;
    -*) usage "unknown option $1" ;;
    *) [ -z "$alias" ] || usage "one alias, the block on stdin: $1"; alias="$1"; shift ;;
  esac
done
[ -n "$alias" ] || usage "no alias"
{ [[ "$secs" =~ ^[1-9][0-9]*$ ]] && [ "$secs" -le "$MAX_TIMEOUT" ]; } || usage "--timeout is 1 to $MAX_TIMEOUT seconds: $secs"
[ ! -t 0 ] || usage "the block comes on stdin, never from a terminal"

work="$(mktemp -d)" || die 66 "no temporary directory for the block"
trap 'rm -rf "$work"' EXIT
block="$work/block"
cat > "$block" || die 64 "stdin could not be read"
[ -s "$block" ] || usage "the block is empty"

# The judge's own failure is a refusal: the door fails closed.
judge() {
  python3 -I "$JUDGE" judge --repo "$REPO" --alias "$alias" "$@" < "$block"
  local rc=$?
  case "$rc" in
    0 | 64 | 65) return "$rc" ;;
    *) echo "host-run: REFUSED (judge-error) — the judge exited $rc, so nothing ran; yours to report: the door fails closed" >&2; return 65 ;;
  esac
}

if [ "$judge_only" = 1 ]; then
  judge
  exit $?
fi

common="$(git -C "$SD" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" \
  || die 66 "no git checkout around $SD to hold the record; nothing ran"
main="$(dirname "$common")"
[ "$(git -C "$main" rev-parse --show-toplevel 2>/dev/null)" = "$main" ] \
  || die 66 "no main checkout at $main, resolved from git rev-parse --git-common-dir; nothing ran"
log="$main/.local/host-commands.jsonl"

# One JSON line, appended under the log's lock; a missing .local fails the redirection, so nothing is created.
record() {
  { flock -w 10 9 && printf '%s\n' "$1" >&9; } 9>>"$log"
}

stamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha="$(sha256sum < "$block")"
sha="${sha%% *}"
verdict="$(judge --record --ts "$(stamp)" --timeout "$secs")"
case "$?" in
  0) ;;
  65)
    [ -n "$verdict" ] || verdict="{\"kind\":\"refused\",\"ts\":\"$(stamp)\",\"sha256\":\"$sha\",\"rule\":\"judge-error\"}"
    record "$verdict" || die 66 "the refusal could not be appended to $log"
    exit 65 ;;
  *) exit 64 ;;
esac
record "$verdict" || die 66 "the begin line could not be appended to $log (is $main/.local there?); nothing ran"

b64="$(base64 -w0 < "$block")"
remote="s=\$(printf %s $b64 | base64 -d) && exec bash -l -c \"\$s\" host-run </dev/null"
start="${EPOCHREALTIME/./}"
timeout --kill-after=5 "$secs" ssh -o BatchMode=yes -o ConnectTimeout=10 -n -T -a -x -- "$alias" "$remote"
rc=$?
spent=$(( ${EPOCHREALTIME/./} - start ))
if { [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; } && [ "$spent" -ge $(( secs * 1000000 )) ]; then
  rc=124
  echo "host-run: the run outlived --timeout $secs s; the local ssh was killed" >&2
fi
duration="$(printf '%d.%06d' $(( spent / 1000000 )) $(( spent % 1000000 )))"
record "{\"kind\":\"end\",\"ts\":\"$(stamp)\",\"alias\":\"$alias\",\"sha256\":\"$sha\",\"rc\":$rc,\"duration_s\":$duration}" \
  || echo "host-run: the end line could not be appended to $log" >&2
exit "$rc"
