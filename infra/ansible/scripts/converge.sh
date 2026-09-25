#!/usr/bin/env bash
# The documented converge path (traceability: spec 00083 D1 for the preview and the typed confirm;
# its `[more ansible args...]` tail is superseded by the grammar below, on the owner's ruling that
# this fleet's converges are enumerable): preview first, typed-limit confirm, then the real pass
# through run.sh (which loads the vaulted deploy keys into a throwaway agent).
# Usage: converge.sh site.yml --limit <host> (or --limit=<host>) [--tags <list> | --skip-tags engine]
#        [--check]
#        [-e KEY=VALUE | -e '{"KEY": "<reason>"}'] ...   (the braced form is JSON, spanning lines or not)
# rc 2 usage, or an argument outside that grammar | rc 3 confirm-abort / no tty
# | rc 4 preview failed | else the real pass's own exit.
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"

# A WHITELIST, not a parser. This fleet's converges are enumerable, and every argument outside the
# grammar is refused before the preview, so no spelling can reach a host recorded as something it is
# not. The sets are what this fleet USES -- what the deploy log and the operator's history record,
# plus what a skill or runbook publishes as a procedure to run. A tag, host or variable that exists
# but has never been converged is not here: when a new case arises, this is where it is added, and
# until then passing it refuses loudly instead of converging while ansible ignores it.
# The four the deploy log records, plus `zaccess`: `infra/runbooks/zaccess.md` publishes its only
# converge, `--limit zaccess --tags access`; plus the three cache nodes, whose rollout (spec 00118
# D14) converges one node per run, so `cache_host` is not a host here.
HOSTS="zcrypto zcrypto-red zcrypto-ops nas zaccess zcrypto-valkey1 zcrypto-valkey2 zcrypto-valkey3"
# The five converged, plus `chrony`: `infra/runbooks/capture.md` prescribes re-converging that role
# as the repair for a stopped or hand-edited chrony on a capture host; plus spec 00118's: a cache
# node's first converge names the six base roles (`--tags base,hardening,firewall,fail2ban,chrony,docker`),
# the mesh converge `firewall,cache-link` on a node or the engine host, and `cache` Valkey, Sentinel
# and Alloy on a node.
TAGNAMES="base hardening firewall fail2ban chrony docker capture engine ops nas access cache cache-link"
# The keys converges have carried, minus `nas_capture_image_digest` -- no role reads it, so the one
# row that passed it re-pinned nothing -- plus the ones a live page publishes as an `-e`:
# `daemon_json_ack` and `ops_panel_timer_hold` (the rollout skill), `ops_reconcile_mint` (the ops
# host_vars), `docker_apt_distribution` and `access_ops_agentboard_live` (their role defaults); plus
# spec 00118's three: the cache role's two digests and its deliberate config re-render (D9).
EVKEYS="capture_image_digest capture_alloy_digest engine_image_digest converge_primary \
ops_image_digest ops_alloy_digest ops_panel_timer_hold ops_grafana_watchdog_probe_url \
ops_reconcile_mint liquidations_decision nas_apply_compose daemon_json_ack \
docker_apt_distribution access_ops_agentboard_live cache_image_digest cache_alloy_digest \
cache_config_reset"
# A reason is prose, and `k=v` truncates it at the first space, so these four travel as JSON alone.
OVERRIDES="canary_override pins_override engine_window_override arming_override"

# EXACT, word by word: a substring test answers true for `zcrypto zcrypto-red`, which is two hosts
# to ansible and both capture daemons restarted in one pass.
in_set() { for m in $2; do [ "$m" = "$1" ] && return 0; done; return 1; }

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
# `site.yml` alone: every row in the deploy log and every published procedure names it, and no
# guidance publishes a `bootstrap.yml` run through this script -- the one published bootstrap is a
# bare `ansible-playbook` carrying `-e ansible_user=root`, which this grammar refuses anyway.
case "$PLAYBOOK" in site.yml) : ;; *) refuse "this script converges site.yml: $PLAYBOOK" ;; esac

# Two callers type this: a session, or the operator pasting the line that session wrote. So the
# arms below catch a WRONG name -- a host, tag or variable that is stale, mistyped or read from
# nothing -- and not a malformed one; a spelling neither caller would type takes no arm of its own.
LIMIT=""; TAGS=""; SKIP=""; CHECK_ONLY=0; EV=""; want=""
for a in "$@"; do
  if [ -n "$want" ]; then
    case "$want" in
      limit) LIMIT="$a" ;;
      tags) TAGS="${TAGS:+$TAGS,}$a" ;;   # `--tags` is append to ansible, so the cell joins too
      skip) SKIP="${SKIP:+$SKIP,}$a" ;;  # append too: `--skip-tags` is the same action to ansible
      ev) EV="$EV$a"$'\x1e' ;;   # RS, never a newline: a JSON reason may carry one
    esac
    want=""
    continue
  fi
  case "$a" in
    --limit) want=limit ;;
    --limit=*) LIMIT="${a#--limit=}" ;;
    --tags) want=tags ;;
    --skip-tags) want=skip ;;
    --check) CHECK_ONLY=1 ;;
    -e) want=ev ;;
    *) refuse "outside the grammar: $a" ;;
  esac
done
case "$want" in
  "") : ;;
  limit | tags) refuse "--$want with no value" ;;
  skip) refuse "--skip-tags with no value" ;;
  ev) refuse "-e with no operand" ;;
  *) refuse "$want with no value" ;;   # a branch added above and not here would pass silently
esac

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
      # The check prints its own one-line reason; a traceback at the terminal reads as a crash.
      why="$(python3 - "$op" "$OVERRIDES" 2>&1 <<'PYCHK'
import json, sys

operand, names = sys.argv[1], sys.argv[2].split()
try:
    parsed = json.loads(operand)
except ValueError as exc:
    raise SystemExit(f"not JSON ({exc.msg})")
if not isinstance(parsed, dict) or len(parsed) != 1:
    raise SystemExit("a braced operand carries exactly one override")
(key, value), = parsed.items()
if key not in names:
    raise SystemExit(f"{key} is not an override name; they are: {' '.join(names)}")
# What the reason SAYS is the roles' gate, not this script's: each of the four asserts
# `| string | length > 8` and refuses a boolean word, and that refusal is the one an operator must
# meet. Here it only has to parse and name an override, or the row cannot record it.
PYCHK
)" || refuse "$why: $op"
      ;;
    *=*)
      key="${op%%=*}"
      in_set "$key" "$OVERRIDES" && refuse "an override is a reason: -e '{\"$key\": \"<why>\"}'"
      # Ansible accepts an unknown `-e` silently and converges nothing, so the key is named here
      # rather than passed through. A key this fleet has not used yet is added to EVKEYS above.
      in_set "$key" "$EVKEYS" || refuse "$key is not in this script's key set — add it there if you need it"
      [ -n "${op#*=}" ] || refuse "empty value: $op"
      case "$op" in *[[:space:]]*) refuse "an operand carries whitespace; pass a reason as JSON: $op" ;; esac
      ;;
    *) refuse "an -e operand is KEY=VALUE or a braced JSON override: $op" ;;
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
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" "$ADIR" "$SKIP" -- "$PLAYBOOK" "$@" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, pathlib, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev, adir, skip = sys.argv[1:11]
argv_words = sys.argv[sys.argv.index("--", 1) + 1 :]
# Every operand was checked against the grammar BEFORE the pass, so there is nothing to fail on and
# nothing to guess: the two accepted forms are a braced JSON override and a single `KEY=VALUE`.
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
    # `skip_tags` is its own cell, not an empty `tags`: `un-tagged-primary-runs` reads both, and
    # `--skip-tags engine` is the Alloy bump's published primary form, not the violation.
    "skip_tags": skip, "argv": argv_words, "committed_pins": committed,
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
