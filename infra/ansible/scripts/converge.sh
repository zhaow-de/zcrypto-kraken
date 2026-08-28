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
# The line is written by THIS process after the pass returns: a wrapper killed mid-pass (terminal
# death, a timeout) leaves an orphaned ansible child that converges with NO record -- the host's
# container .State.StartedAt is the evidence then; append the line by hand from it.
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
ADIR="${ZCRYPTO_ANSIBLE_DIR:-$SD/..}"
REV="$(git -C "$SD" rev-parse HEAD 2>/dev/null || echo unknown)"
# `dirty` answers "does REV fully describe what was deployed?" -- ansible renders from the working
# tree, so a modified role means it does not. The deploy log is excluded because THIS SCRIPT writes
# it: measured on the first live rollout, a converge recorded dirty=false, appended its line, and
# the next converge two minutes later read dirty=true at the same revision, dirtied by nothing but
# the recorder. A flag that cannot separate that from a modified role reports neither.
TOP="$(git -C "$SD" rev-parse --show-toplevel 2>/dev/null || true)"
DIRTY=false
if [ -n "$TOP" ]; then
  # Both sides resolved before comparing: $LOG carries `../../..` from $SD, so an unresolved
  # prefix test yields a pathspec git cannot match and the exclusion silently does nothing.
  LOGABS="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$LOG" 2>/dev/null || echo "$LOG")"
  TOPABS="$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$TOP" 2>/dev/null || echo "$TOP")"
  LOGREL=""
  case "$LOGABS" in "$TOPABS"/*) LOGREL="${LOGABS#"$TOPABS"/}" ;; esac
  if [ -n "$LOGREL" ]; then
    STATUS="$(git -C "$TOP" status --porcelain -- ':(top)' ":(top,exclude)$LOGREL" 2>/dev/null || true)"
  else
    STATUS="$(git -C "$TOP" status --porcelain 2>/dev/null || true)"
  fi
  [ -n "$STATUS" ] && DIRTY=true
fi
# Best-effort and LOUD, never fatal: the pass has already run, so its rc is the truth this script
# returns; a record that cannot be written is printed for the operator to append by hand instead of
# being turned into a converge failure that did not happen.
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" "$ADIR" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, pathlib, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev, adir = sys.argv[1:10]
extra = {}
for line in ev.splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        extra[k.strip()] = v.strip()
# The pins this converge deployed that NO -e carries: the NAS's image lives in a committed
# host_vars file, so its line named an apply flag and no digest at all -- on the one tier whose
# rollback operand is in git. Read from the PLAINTEXT vars.yml with a regex, never through
# `ansible-inventory --host`, which decrypts the vault and prints every secret (CLAUDE.md).
# Only `@sha256:`-pinned image refs: a path or a port is not a rollback operand.
# The value must be bare -- unquoted, no trailing YAML comment -- or this regex silently drops it
# and the pin goes unrecorded.
import re as _re
committed = {}
_vars = pathlib.Path(adir) / "host_vars" / limit / "vars.yml"
if _vars.is_file():
    for m in _re.finditer(r"^(\w+_image):\s*(\S+@sha256:[0-9a-f]{64})\s*$", _vars.read_text(), _re.M):
        committed[m.group(1)] = m.group(2)
rec = {
    "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "playbook": playbook, "limit": limit, "tags": tags, "extra_vars": extra,
    "committed_pins": committed,
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
