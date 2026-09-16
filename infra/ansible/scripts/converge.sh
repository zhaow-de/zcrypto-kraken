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
# The real pass, RECORDED: fleet-pins.md is re-trued from the line this appends, never from memory.
# An `-e` operand can reach that line, so never pass a secret as one. The line is written after the
# pass returns: a wrapper killed mid-pass leaves an orphaned child converging with NO record, and
# the line is then appended by hand from the container's `.State.StartedAt`.
set +e
"$SD/run.sh" "$PLAYBOOK" "$@"
rc=$?
set -e
LOG="${ZCRYPTO_DEPLOY_LOG:-$SD/../../../docs/reference/deploy-log.jsonl}"
TAGS=""; EV=""; UNREAD=""; prev=""
for a in "$@"; do
  # Exact arms, never a prefix: `--extra-var*` matches the attached `--extra-vars=K=V` too, and then
  # books the NEXT argv word as a variable. The abbreviations `allow_abbrev` honours (`--e` …
  # `--extra-var`, `--ta`, `-ve`) are not collected -- they leave a short row, which the drill pages
  # read as "nothing was overridden", so the last arms name them for the warning below. RS, never a
  # newline: an operand carries its own.
  case "$prev" in -e | --extra-vars) EV="$EV$a"$'\x1e' ;; esac
  case "$prev" in --tags | -t) TAGS="$a" ;; esac
  case "$a" in
    --tags | -t) : ;;                         # value is the next word; `prev` above takes it
    --tags=*) TAGS="${a#--tags=}" ;;
    -t?*) v="${a#-t}"; TAGS="${v#=}" ;;       # attached short form; argparse drops `-t=`'s `=`
    -e | --extra-vars) : ;;
    -e?*) v="${a#-e}"; EV="$EV${v#=}"$'\x1e' ;;
    --extra-vars=*) EV="$EV${a#--extra-vars=}"$'\x1e' ;;
    --e* | --ta*) UNREAD="$UNREAD $a" ;;      # an abbreviation ansible honours and this loop does not
    -[a-zA-Z]*[et]*) UNREAD="$UNREAD $a" ;;   # a clustered short carrying one, e.g. `-ve`
  esac
  prev="$a"
done
if [ -n "$UNREAD" ]; then
  echo "converge.sh: NOT RECORDED:$UNREAD — ansible honours the spelling and this collector does not;" \
    "the row will read as though nothing was overridden" >&2
fi
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
python3 - "$LOG" "$PLAYBOOK" "$LIMIT" "$TAGS" "$REV" "$DIRTY" "$rc" "$EV" "$ADIR" <<'PYREC' || echo "converge.sh: RECORD FAILED — append the line above to docs/reference/deploy-log.jsonl by hand" >&2
import json, pathlib, shlex, sys, datetime as dt
log, playbook, limit, tags, rev, dirty, rc, ev, adir = sys.argv[1:10]
# A braced operand never reaches the `=` split, which would mint a key out of its own text. Ansible
# YAML-loads `{`/`[`; this runs under the system `python3`, which has no PyYAML, so a YAML-only
# spelling records a short row.
extra, unread = {}, []
for operand in ev.split("\x1e"):  # never splitlines(): an operand may carry newlines of its own
    if not operand.strip():
        continue
    booked = {}
    # The RAW first character, as `load_extra_vars` tests it: ` {…}` is not braced to ansible.
    if operand[:1] in "{[":
        try:
            parsed = json.loads(operand)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            booked = {str(k): v for k, v in parsed.items()}
    else:
        # One `-e` may carry several vars (`-e "a=1 b=2"`), and ansible's `split_args` breaks them on
        # the SPACE and the NEWLINE only -- a tab stays inside the value (measured). A token with no
        # `=` is the remainder ansible books as `_raw_params`; it names no variable the operator set.
        lex = shlex.shlex(operand, posix=True)
        lex.whitespace, lex.whitespace_split, lex.commenters = " \n", True, ""
        try:
            tokens = list(lex)
        except ValueError:  # an unbalanced quote: ansible refused this operand, so record nothing
            tokens = []
        for token in tokens:
            if "=" in token:
                k, v = token.split("=", 1)
                booked[k.strip()] = v.strip()
    if booked:
        extra.update(booked)
    else:
        unread.append(operand)
if unread:
    print("converge.sh: NOT RECORDED: " + " | ".join(unread) + " — no variable this recorder reads;"
          " the row will read as though nothing was overridden", file=sys.stderr)
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
