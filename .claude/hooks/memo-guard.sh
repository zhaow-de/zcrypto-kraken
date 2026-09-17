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
{ read -r tool; read -r path; } < <(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("tool_name","")); print(d.get("tool_input",{}).get("file_path",""))')
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
