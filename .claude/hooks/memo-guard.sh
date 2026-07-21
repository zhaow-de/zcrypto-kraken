#!/usr/bin/env bash
# Read-guard for docs/memo.local.md (hand-edited outside sessions, not version-controlled).
# Protocol: a write is allowed only when the file has been Read since its content last changed;
# every write invalidates the stamp, so the next write (and honest verification) needs a re-read.
# Wired in .claude/settings.json: pre-write on Edit|Write (blocks), post-read on Read (stamps),
# post-write on Edit|Write (invalidates + instructs the read-back). Shell writes bypass Edit/Write,
# which is why the grooming/auto-exec skills require memo edits to go through those tools.
set -euo pipefail
mode="${1:?mode required: pre-write|post-read|post-write}"
path="$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_input",{}).get("file_path",""))')"
case "$path" in
  */docs/memo.local.md|docs/memo.local.md) ;;
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
    if [[ ! -f "$stamp" || "$(cat "$stamp")" != "$cur" ]]; then
      echo "memo-guard: BLOCKED. docs/memo.local.md must be Read immediately before this write — it is hand-edited outside sessions, and every write invalidates the previous read. Read the file, then retry the edit." >&2
      exit 2
    fi
    ;;
  post-write)
    rm -f "$stamp"
    printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"memo-guard: the write to docs/memo.local.md landed and invalidated the read-stamp. Re-read the file now to verify the result on disk; any further memo write is blocked until that read happens."}}\n'
    ;;
esac
exit 0
