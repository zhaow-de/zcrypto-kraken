#!/usr/bin/env bash
# The documented converge path (traceability: spec 00083 D1): preview first, typed-limit confirm,
# then the real pass through run.sh (which loads the vaulted deploy keys into a throwaway agent).
# Usage: converge.sh <playbook.yml> --limit <target> [more ansible args...]
# rc 2 usage | rc 3 confirm-abort / no tty | rc 4 preview failed | rc 5 argv ansible refuses
# | else the real pass's own exit.
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

# ANSIBLE parses this argv, never a pattern here: `--limit`/`-l`, `--tags`/`-t`, `--check`/`-C` and
# `-e` each have spellings, abbreviations and clusters a `case` arm cannot reproduce, and every one
# it gets wrong either books a row for a pass that converged nothing or names the wrong host in it.
# Both streams to files: ansible refuses to start on a non-blocking stdout.
PYBIN="${ZCRYPTO_PYTHON:-$SD/../../../.venv/bin/python}"
if [ ! -x "$PYBIN" ]; then
  echo "converge.sh: no project interpreter at $PYBIN — run uv sync, or set ZCRYPTO_PYTHON" >&2
  exit 5
fi
CLI_OUT="$(mktemp)"; CLI_ERR="$(mktemp)"
trap 'rm -f "$CLI_OUT" "$CLI_ERR"' EXIT
if ! "$PYBIN" "$SD/parse-argv.py" "$PLAYBOOK" "$@" > "$CLI_OUT" 2> "$CLI_ERR"; then
  echo "converge.sh: ansible refuses this argv — nothing ran:" >&2
  cat "$CLI_ERR" >&2
  exit 5
fi
LIMIT=""; CHECK_ONLY=0; TAGS=""; EV=""; ARGV=""
while IFS=$'\t' read -r key value; do
  case "$key" in
    ARGV) ARGV="$value" ;;
    LIMIT) LIMIT="$value" ;;
    CHECK) if [ "$value" = "1" ]; then CHECK_ONLY=1; fi ;;
    TAGS) TAGS="$value" ;;
    EXTRA) EV="$value" ;;
  esac
done < "$CLI_OUT"
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
# The real pass, RECORDED: fleet-pins.md is re-trued from the line this appends, never from memory.
# An `-e` operand can reach that line, so never pass a secret as one. The line is written after the
# pass returns: a wrapper killed mid-pass leaves an orphaned child converging with NO record, and
# the line is then appended by hand from the container's `.State.StartedAt`.
set +e
"$SD/run.sh" "$PLAYBOOK" "$@"
rc=$?
set -e
LOG="${ZCRYPTO_DEPLOY_LOG:-$SD/../../../docs/reference/deploy-log.jsonl}"
ADIR="${ZCRYPTO_ANSIBLE_DIR:-$SD/..}"
REV="$(git -C "$SD" rev-parse HEAD 2>/dev/null || echo unknown)"
# `dirty` answers "does REV fully describe what was deployed?" -- ansible renders from the working
# tree. The deploy log is excluded because THIS SCRIPT writes it and would otherwise dirty itself.
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
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" "$ADIR" "$ARGV" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, pathlib, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev, adir, argv = sys.argv[1:11]
# Both come from `parse-argv.py`, i.e. from ansible's own parser: this script no longer has an
# opinion about argv. A field it cannot read is a bug there, not a dialect to add here.
extra = json.loads(ev) if ev else {}
argv_words = json.loads(argv) if argv else []
# The pins this converge deployed that no `-e` carries. Read from the PLAINTEXT vars.yml with a
# regex, never `ansible-inventory --host`, which decrypts the vault and prints every secret
# (CLAUDE.md). The value must be bare -- unquoted, no trailing YAML comment -- or the regex silently
# drops it and the pin goes unrecorded.
import re as _re
committed = {}
_vars = pathlib.Path(adir) / "host_vars" / limit / "vars.yml"
if _vars.is_file():
    for m in _re.finditer(r"^(\w+_image):\s*(\S+@sha256:[0-9a-f]{64})\s*$", _vars.read_text(), _re.M):
        committed[m.group(1)] = m.group(2)
rec = {
    "ts": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "playbook": playbook, "limit": limit, "tags": tags, "extra_vars": extra,
    "argv": argv_words, "committed_pins": committed,
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
