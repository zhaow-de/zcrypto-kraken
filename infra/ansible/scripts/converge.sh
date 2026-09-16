#!/usr/bin/env bash
# The documented converge path (traceability: spec 00083 D1): preview first, typed-limit confirm,
# then the real pass through run.sh (which loads the vaulted deploy keys into a throwaway agent).
# Usage: converge.sh <playbook.yml> --limit <host> [--tags <list> | --skip-tags engine] [--check]
#        [-e KEY=VALUE | -e '{"KEY": "<reason>"}'] ...
# rc 2 usage, or an argument outside that grammar | rc 3 confirm-abort / no tty
# | rc 4 preview failed | else the real pass's own exit.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"

# A WHITELIST, not a parser. This fleet's converges are enumerable -- one image into four cases
# across the hosts below -- and every argument outside the grammar is refused before the preview,
# so no spelling can reach a host recorded as something it is not. The sets are what the tree
# publishes and what `deploy-log.jsonl` records; a new variable or host is added HERE, and until it
# is, passing it refuses loudly instead of converging while ansible ignores it.
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess"
TAGNAMES="capture engine ops nas access"
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
liquidations_decision nas_apply_compose daemon_json_ack rebootstrap"
# A reason is prose, and `k=v` truncates it at the first space, so these four travel as JSON alone.
OVERRIDES="canary_override pins_override engine_window_override arming_override"

in_set() { case " $2 " in *" $1 "*) return 0 ;; esac; return 1; }

refuse() {
  echo "converge.sh: $1" >&2
  echo "usage: converge.sh <playbook.yml> --limit <host> [--tags <list> | --skip-tags engine]" >&2
  echo "                  [--check] [-e KEY=VALUE | -e '{\"KEY\": \"<reason>\"}'] ..." >&2
  echo "hosts: $HOSTS" >&2
  echo "tags:  $TAGNAMES" >&2
  exit 2
}

[ "$#" -ge 1 ] || refuse "no playbook — a bare site.yml still runs every play"
PLAYBOOK="$1"; shift
case "$PLAYBOOK" in site.yml | bootstrap.yml) : ;; *) refuse "unknown playbook: $PLAYBOOK" ;; esac

LIMIT=""; TAGS=""; SKIP=""; CHECK_ONLY=0; EV=""; want=""
for a in "$@"; do
  if [ -n "$want" ]; then
    case "$want" in
      limit) LIMIT="$a" ;;
      tags) TAGS="$a" ;;
      skip) SKIP="$a" ;;
      ev) EV="$EV$a"$'\x1e' ;;   # RS, never a newline: a JSON reason may carry one
    esac
    want=""
    continue
  fi
  case "$a" in
    --limit) [ -z "$LIMIT" ] || refuse "--limit twice"; want=limit ;;
    --limit=*) [ -z "$LIMIT" ] || refuse "--limit twice"; LIMIT="${a#--limit=}" ;;
    --tags) [ -z "$TAGS" ] || refuse "--tags twice"; want=tags ;;
    --skip-tags) [ -z "$SKIP" ] || refuse "--skip-tags twice"; want=skip ;;
    --check) CHECK_ONLY=1 ;;
    -e) want=ev ;;
    *) refuse "outside the grammar: $a" ;;
  esac
done
[ -z "$want" ] || refuse "--$want with no value"

[ -n "$LIMIT" ] || refuse "--limit is required"
in_set "$LIMIT" "$HOSTS" || refuse "unknown host: $LIMIT"
[ -z "$TAGS" ] || [ -z "$SKIP" ] || refuse "--tags and --skip-tags together"
[ -z "$SKIP" ] || [ "$SKIP" = "engine" ] || refuse "--skip-tags takes only engine, not $SKIP"
if [ -n "$TAGS" ]; then
  OLDIFS="$IFS"; IFS=,
  for t in $TAGS; do
    IFS="$OLDIFS"
    in_set "$t" "$TAGNAMES" || refuse "unknown tag: $t"
    IFS=,
  done
  IFS="$OLDIFS"
fi
# Each operand, before the preview: the only two forms the fleet uses, checked where the operator is
# still standing at the terminal rather than in a row read weeks later.
OLDIFS="$IFS"; IFS=$'\x1e'
for op in $EV; do
  IFS="$OLDIFS"
  case "$op" in
    '{'*)
      python3 - "$op" "$OVERRIDES" <<'PYCHK' || refuse "not a one-line override operand: $op"
import json, sys
operand, names = sys.argv[1], sys.argv[2].split()
parsed = json.loads(operand)
assert isinstance(parsed, dict) and len(parsed) == 1, "exactly one key"
(key, value), = parsed.items()
assert key in names, f"{key} is not an override name"
assert isinstance(value, str) and len(value) > 8, "the reason is prose, longer than 8 characters"
assert value.strip().lower() not in ("true", "false", "yes", "no", "1", "0"), "a reason, not a boolean"
PYCHK
      ;;
    *=*)
      key="${op%%=*}"
      in_set "$key" "$EVKEYS" || refuse "no role reads $key — ansible would accept it and converge nothing"
      [ -n "${op#*=}" ] || refuse "empty value: $op"
      case "$op" in *[[:space:]]*) refuse "an operand carries whitespace; pass a reason as JSON: $op" ;; esac
      ;;
    *) refuse "an -e operand is KEY=VALUE or one-line JSON: $op" ;;
  esac
  IFS=$'\x1e'
done
IFS="$OLDIFS"

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
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" "$ADIR" -- "$PLAYBOOK" "$@" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, pathlib, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev, adir = sys.argv[1:10]
argv_words = sys.argv[sys.argv.index("--", 1) + 1 :]
# Every operand was checked against the grammar BEFORE the pass, so there is nothing to fail on and
# nothing to guess: the two accepted forms are one-line JSON and a single `KEY=VALUE`.
extra = {}
for operand in ev.split("\x1e"):
    if not operand:
        continue
    if operand[:1] == "{":
        extra.update(json.loads(operand))
    else:
        key, value = operand.split("=", 1)
        extra[key] = value
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
