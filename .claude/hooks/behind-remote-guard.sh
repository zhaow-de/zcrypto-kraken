#!/usr/bin/env bash
# PostToolUse[Bash] guard: after a command containing `git fetch`, `git pull`, `git merge`,
# `git rebase` or `git remote update`, REPORT a tracking branch left behind its upstream. The command
# already ran, so a PostToolUse hook cannot refuse anything; what it can do is say, before the next
# command cuts a branch from or commits on the stale one, that HEAD..@{u} is non-empty, by how much,
# and the one command that closes it. The judgment is the repo's state after the command, not the
# command's refspec: a fetch of another branch leaves a level branch level, and is silent for that
# reason.
# Silent, deliberately: no verb in the command (`git merge-base` is not `git merge`; `switch`,
# `checkout` and `worktree add` are not verbs -- nothing moves a remote-tracking ref); a detached HEAD
# or a branch with no upstream, or whose upstream ref is gone (a pruned remote branch) -- nothing to
# be behind; a branch level with or ahead of its upstream; a merge, cherry-pick or revert in progress
# (MERGE_HEAD, CHERRY_PICK_HEAD, REVERT_HEAD), where the fix is to finish it, not to pull; a
# directory the command names through a variable or a substitution, or through `--git-dir` or
# `--work-tree`, judged as nothing rather than as the process cwd (that would report a different
# repo's state as this command's); a directory that is not a repo.
set -euo pipefail
# WHICH repo: the `-C <dir>` options before the verb, joined as git chdirs through them, the other
# global options `opt` names stepped over in any order and count; else the last `cd <dir>` that
# starts a command in the `&&`/`;` list before the verb -- a `cd` nested in `( ... )` or `bash -c`
# is not seen and the process cwd is judged instead; else the process cwd. One line per distinct
# directory the command names, in order.
input="$(cat)"
dirs="$(printf '%s' "$input" | python3 -c '
import json, os, re, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

val = r"(?:\"[^\"]*\"|\x27[^\x27]*\x27|\S+)"
# `--git-dir`/`--work-tree` are consumed, not merely unmatched: left in the text, `\bgit\s+` re-matches
# the tail of a `<path>/.git <verb>` and the process cwd is judged in place of the named repo.
opt = re.compile(r"(?:--no-pager|--no-optional-locks|--literal-pathspecs|-c\s*%s|-C\s+(%s)|(--git-dir|--work-tree)(?:=|\s+)%s)\s+" % (val, val, val))
verb = re.compile(r"\bgit\s+((?:%s)*)(?:fetch|pull|merge|rebase|remote\s+update)(?![\w-])" % opt.pattern)

def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27":
        return s[1:-1]
    return s

seen = []
for m in verb.finditer(cmd):
    opts = list(opt.finditer(m.group(1)))
    if any(o.group(2) for o in opts):
        continue
    named = [unquote(o.group(1)) for o in opts if o.group(1)]
    if named:
        d = os.path.join(*named)
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
  for head in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD; do git -C "$dir" rev-parse -q --verify "$head" >/dev/null 2>&1 && continue 2; done
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
        "additionalContext": msg + " -- run the fix before cutting from or committing on it.",
    },
}))
'
exit 0
