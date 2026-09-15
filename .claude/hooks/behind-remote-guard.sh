#!/usr/bin/env bash
# PostToolUse[Bash] guard: after a command containing `git fetch`, `git pull`, `git merge` or
# `git rebase`, REPORT a tracking branch left behind its upstream. The command already ran, so a
# PostToolUse hook cannot refuse anything; what it can do is say, before the next command cuts a
# branch from or commits on the stale one, that HEAD..@{u} is non-empty, by how much, and the one
# command that closes it. The judgment is the repo's state after the command, not the command's
# refspec: a fetch of another branch leaves a level branch level, and is silent for that reason.
# Silent, deliberately: no verb in the command (`git merge-base` is not `git merge`); a detached HEAD
# or a branch with no upstream, or whose upstream ref is gone (a pruned remote branch) -- nothing to
# be behind; a branch level with or ahead of its upstream; a merge in progress (MERGE_HEAD), where
# the fix is to finish it, not to pull; a directory the command names through a variable or a
# substitution, judged as nothing rather than as the process cwd (that would report a different repo's
# state as this command's); a directory that is not a repo.
set -euo pipefail
# WHICH repo: `git -C <dir>`, else the last `cd <dir>` before the verb, else the process cwd -- one
# line per distinct directory the command names, in order.
input="$(cat)"
dirs="$(printf '%s' "$input" | python3 -c '
import json, re, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

verb = re.compile(r"\bgit\s+(?:-C\s+(\"[^\"]*\"|\x27[^\x27]*\x27|\S+)\s+)?(?:fetch|pull|merge|rebase)(?![\w-])")

def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27":
        return s[1:-1]
    return s

seen = []
for m in verb.finditer(cmd):
    if m.group(1):
        d = unquote(m.group(1))
    else:
        cds = re.findall(r"(?:^|&&|;)\s*cd\s+(\"[^\"]*\"|\x27[^\x27]*\x27|[^\s;&|]+)", cmd[: m.start()])
        d = unquote(cds[-1]) if cds else "."
    if any(ch in d for ch in "$`") or d in seen:
        continue
    seen.append(d)
    print(d)
' 2>/dev/null || true)"
[[ -z "$dirs" ]] && exit 0

report=""
while IFS= read -r dir; do
  [[ -z "$dir" ]] && continue
  branch="$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
  [[ -z "$branch" ]] && continue
  upstream="$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  [[ -z "$upstream" ]] && continue
  git -C "$dir" rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1 && continue
  behind="$(git -C "$dir" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
  [[ "$behind" == 0 ]] && continue
  ahead="$(git -C "$dir" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
  at=""
  [[ "$dir" != "." ]] && printf -v at ' -C %q' "$dir"
  if [[ "$ahead" == 0 ]]; then
    report+="$branch is behind $upstream by $behind — git${at} pull --ff-only"$'\n'
  else
    report+="$branch is behind $upstream by $behind and ahead by $ahead (diverged) — git${at} pull --rebase"$'\n'
  fi
done <<<"$dirs"
[[ -z "$report" ]] && exit 0
# systemMessage reaches the user, additionalContext the model; exit 0, since there is nothing left
# to block. Plain stdout would be transcript-only and the agent that just ran the fetch never reads it.
printf '%s' "$report" | python3 -c '
import json, sys

lines = [line for line in sys.stdin.read().splitlines() if line]
msg = "behind-remote-guard: " + "; ".join(lines)
print(json.dumps({
    "systemMessage": msg,
    "hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": msg + " -- the command that just ran left the branch behind its upstream; run the fix before cutting from or committing on it.",
    },
}))
'
exit 0
