#!/usr/bin/env bash
# Read-guard for .local/memo.md (hand-edited outside sessions, not version-controlled).
# Protocol: an Edit is allowed only when the file has been Read since its content last changed;
# every write invalidates the stamp, so the next write (and honest verification) needs a re-read.
# A Write of the existing file is refused outright -- it drops whatever the rewrite forgot, and
# there is no history to recover from; only the Write that creates an absent memo is admitted.
# Wired in .claude/settings.json: pre-write on Edit|Write (blocks), post-read on Read (stamps),
# post-write on Edit|Write (invalidates + instructs the read-back). Shell writes bypass Edit/Write,
# which is why the grooming/auto-exec skills require memo edits to go through those tools.
set -euo pipefail
# The two fields are read one per line, so a separator in `tool_name` desynchronises the pair and
# `path` holds a fragment that matches no memo pattern, exiting 0. Not reachable and not fixed: the
# harness sets `tool_name`, and a `file_path` carrying a newline names a file that is not the memo,
# so no input both desynchronises this and writes the memo. NUL-separating the pair moves the byte
# rather than closing the class -- a NUL in `tool_name` desynchronises that too.
mode="${1:?mode required: pre-write|post-read|post-write}"
{ read -r tool; read -r path; read -r placeholder; } < <(python3 -c 'import json,re,sys; d=json.load(sys.stdin); t=d.get("tool_input",{}); print(d.get("tool_name","")); print(t.get("file_path","")); m=re.search(r"[0-9]{2}:[0-9]x(?:[0-9]|Z|\b)", str(t.get("new_string") or t.get("content") or "")); print(m.group(0) if m else "")')
# A placeholder stamp -- an hour with an x digit, `08:5xZ`, `13:1xZ` -- is refused in any Edit or Write: eleven such
# slips in two days, each disclaimed in the same breath, and the clock or a record was always one call away.
if [[ "$mode" == pre-write && -n "${placeholder:-}" ]]; then
  echo "memo-guard: BLOCKED. '$placeholder' is a placeholder stamp — paste the printed value of \`date -u\` or of the record (an mtime, a reflog, a PR's createdAt), never an x digit." >&2
  exit 2
fi
case "$path" in
  */.local/memo.md|.local/memo.md) ;;
  *) exit 0 ;;
esac
stamp="${TMPDIR:-/tmp}/zcrypto-memo-read-stamp-$(id -un)"
current_hash() { sha256sum "$path" 2>/dev/null | cut -d' ' -f1 || true; }
case "$mode" in
  post-read)
    current_hash > "$stamp" || true
    ;;
  pre-write)
    cur="$(current_hash)"
    # Absent file: nothing to stale-clobber -- allow the creating write (else Write deadlocks:
    # the block message demands a Read of a file that does not exist).
    [[ -z "$cur" ]] && exit 0
    if [[ "$tool" == Write ]]; then
      echo "memo-guard: BLOCKED. A wholesale Write of .local/memo.md drops whatever the rewrite forgot and there is no history — use Edit." >&2
      exit 2
    fi
    if [[ ! -f "$stamp" || "$(cat "$stamp")" != "$cur" ]]; then
      echo "memo-guard: BLOCKED. .local/memo.md must be Read immediately before this write — it is hand-edited outside sessions, and every write invalidates the previous read. Read the file, then retry the edit." >&2
      exit 2
    fi
    ;;
  post-write)
    rm -f "$stamp"
    printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"memo-guard: the write to .local/memo.md landed and invalidated the read-stamp. Re-read the file now to verify the result on disk; any further memo write is blocked until that read happens."}}\n'
    ;;
esac
exit 0
