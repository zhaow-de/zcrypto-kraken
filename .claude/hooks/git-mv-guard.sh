#!/usr/bin/env bash
# PostToolUse[Bash] guard: after any command containing `git mv`, warn on RM-state entries --
# rename staged while the worktree still differs, i.e. the staged rename carries PRE-edit content.
# The pre-commit framework stashes unstaged changes before hooks run, so repo-side hooks
# structurally cannot see this; the moment the trap forms is the only place to catch it.
set -euo pipefail
input="$(cat)"
cmd="$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || true)"
case "$cmd" in *"git mv"*) ;; *) exit 0 ;; esac
rm_lines="$(git status --porcelain 2>/dev/null | grep -E '^RM ' || true)"
[[ -z "$rm_lines" ]] && exit 0
echo "git-mv-guard: WARNING — rename staged but the worktree still differs (the staged rename carries the PRE-edit content):"
echo "$rm_lines"
echo "Fix: git add <newpath> for each line above, then verify against the COMMITTED tree (git show :<path>), never the working tree."
