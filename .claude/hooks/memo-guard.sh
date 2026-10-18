#!/usr/bin/env bash
# retire when: .local/memo.md is no longer the session's hand-edited queue, and no stamp is pasted by hand.
# Read-guard for .local/memo.md (hand-edited outside sessions, not version-controlled), and the placeholder-stamp
# refusal.
# Protocol: an Edit is allowed only when the file has been Read since its content last changed;
# every write invalidates the stamp, so the next write (and honest verification) needs a re-read.
# A Write of the existing file is refused outright -- it drops whatever the rewrite forgot, and
# there is no history to recover from; only the Write that creates an absent memo is admitted.
# Wired in .claude/settings.json: pre-write on Edit|Write (blocks), post-read on Read (stamps),
# post-write on Edit|Write (invalidates + instructs the read-back). Shell writes bypass Edit/Write,
# which is why the grooming/auto-exec skills require memo edits to go through those tools.
set -euo pipefail
mode="${1:?mode required: pre-write|post-read|post-write}"
# The fields are read one per line, so a newline in `tool_name` or `file_path` desynchronises them; not fixed, as
# the harness sets `tool_name` and a path with a newline is not the memo -- NUL-separating them moves the byte.
{ read -r tool; read -r path; read -r placeholder; } < <(python3 -c 'import json,re,sys; d=json.load(sys.stdin); t=d.get("tool_input",{}); print(d.get("tool_name","")); print(t.get("file_path","")); m=next((x.group(0) for x in re.finditer(r"(?i)[0-9x?]{2}:[0-9x?]{2}(?![0-9a-f])", str(t.get("new_string") or t.get("content") or "")) if re.search(r"(?i)[x?]", x.group(0))), ""); print(m)')
# Every file, not the memo alone, before the memo's own checks -- a test module's or a hook's own cases spell the
# placeholders; a hex literal is no stamp.
if [[ "$mode" == pre-write && -n "${placeholder:-}" && "$path" != */tests/*.py && "$path" != */.claude/hooks/* ]]; then
  echo "memo-guard: BLOCKED. '$placeholder' is a placeholder stamp — paste the printed value of \`date -u\` or of the record (an mtime, a reflog, a PR's createdAt)." >&2
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
