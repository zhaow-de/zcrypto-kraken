#!/usr/bin/env bash
# PostToolUse[Bash] guard: after any command containing `git mv`, warn on RM-state entries --
# rename staged while the worktree still differs, i.e. the staged rename carries PRE-edit content.
# The pre-commit framework stashes unstaged changes before hooks run, so repo-side hooks
# structurally cannot see this; the moment the trap forms is the only place to catch it.
set -euo pipefail
# Resolve WHICH repo to judge: `git -C <dir> mv`, else the last `cd <dir>` before the mv, else the
# process cwd. An unresolvable dir (variable or substitution) must NOT fall back to the cwd -- that
# would report an unrelated repo's porcelain as if it were this command's.
input="$(cat)"
analysis="$(printf '%s' "$input" | python3 -c '
import json, re, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    print("none")
    sys.exit(0)

m = re.search(r"\bgit\s+(?:-C\s+(\"[^\"]*\"|\x27[^\x27]*\x27|\S+)\s+)?mv\b", cmd)
if not m:
    print("none")
    sys.exit(0)

def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27":
        return s[1:-1]
    return s

d = None
if m.group(1):
    d = unquote(m.group(1))
else:
    cds = re.findall(r"(?:^|&&|;)\s*cd\s+(\"[^\"]*\"|\x27[^\x27]*\x27|\S+)", cmd[: m.start()])
    if cds:
        d = unquote(cds[-1])
if d is None:
    print("warn\t.")
elif any(ch in d for ch in "$`"):
    print("note")
else:
    print("warn\t" + d)
' 2>/dev/null || echo none)"

mode="${analysis%%$'\t'*}"
dir="${analysis#*$'\t'}"
case "$mode" in
  none) exit 0 ;;
  note)
    echo "git-mv-guard: NOTE — a git mv ran with a directory this guard could not resolve (variable or substitution in the path); check 'git status' there yourself for RM entries (rename staged over unstaged edits)." >&2
    exit 2 ;;
esac
rm_lines="$(git -C "$dir" status --porcelain 2>/dev/null | grep -E '^RM ' || true)"
[[ -z "$rm_lines" ]] && exit 0
# stderr + exit 2, not stdout + exit 0: a PostToolUse hook's plain stdout is transcript-only, so the
# agent that just ran `git mv` never reads it. Exit 2 is the one channel Claude Code feeds back to the
# model. On PostToolUse it cannot block the already-run command -- warn-only is exactly the intent.
{
  echo "git-mv-guard: WARNING — rename staged but the worktree still differs (the staged rename carries the PRE-edit content):"
  echo "$rm_lines"
  echo "Fix: git add <newpath> for each line above, then verify against the COMMITTED tree (git show :<path>), never the working tree."
} >&2
exit 2
