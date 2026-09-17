#!/usr/bin/env bash
# PostToolUse[Bash] guard: after a command containing `git fetch`, `git pull`, `git merge`,
# `git rebase` or `git remote update`, REPORT a tracking branch left behind its upstream. The command
# already ran, so a PostToolUse hook cannot refuse anything; what it can do is say, before the next
# command cuts a branch from or commits on the stale one, that HEAD..@{u} is non-empty, by how much,
# and the one command that closes it -- except a diverged `develop` or `main`, where it says that a
# shared branch is a STOP for the owner, never a local rebase or merge. The judgment is the repo's
# state after the command, not the command's refspec: a fetch of another branch leaves a level
# branch level, and is silent for that reason.
# Silent, deliberately: no verb in the command (`git merge-base` is not `git merge`; `switch`,
# `checkout` and `worktree add` are not verbs -- nothing moves a remote-tracking ref); a detached HEAD
# or a branch with no upstream, or whose upstream ref is gone (a pruned remote branch) -- nothing to
# be behind; a branch level with or ahead of its upstream; a merge, cherry-pick or revert in progress
# (MERGE_HEAD, CHERRY_PICK_HEAD, REVERT_HEAD, or an unmerged index -- a conflicted `merge --squash`
# writes no head), where the fix is to finish it, not to pull; a directory the command names through
# a variable or a substitution, or through `--git-dir` or `--work-tree`, judged as nothing rather
# than as the process cwd (that would report a different repo's state as this command's); a
# directory that is not a repo. Not silent: a verb quoted inside a string (`git commit -m 'run git
# fetch origin next'`) -- the match is textual, the state it reports is true, and nothing is blocked.
set -euo pipefail
# WHICH repo: the `-C <dir>` options before the verb, joined as git chdirs through them, a relative
# first one against the last `cd <dir>` before the verb; the other global options stepped over in
# any order and count -- any `-<letter>` or `--<word>[=<value>]`, the value-taking ones `opt` names
# consuming the next token when not `=`-attached; else that last `cd`, one that starts a command
# after a newline, `&&`, `||` or `;`; else the process cwd. Scope is not tracked, so a `cd` the scan
# takes outlives its subshell: `( git log ; cd /x ) ; git fetch` reports /x, a repo the fetch never
# ran in. Left so on purpose -- tracking scope means asking bash's question of a regex, which is
# what this family's `judge_status` arm was dropped for, and this hook only ever reports.
# One line per distinct repository the command
# names, keyed on its toplevel, in order.
input="$(cat)"
dirs="$(printf '%s' "$input" | python3 -c '
import json, os, re, sys

try:
    cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
except Exception:
    sys.exit(0)

val = r"(?:\"[^\"]*\"|\x27[^\x27]*\x27|\S+)"
mark = r"--git-dir|--work-tree"
take = r"--namespace|--config-env|--exec-path|--super-prefix|--attr-source"
# `--git-dir`/`--work-tree` keep an arm of their own for the mark (group 2) that judges the command as
# nothing; the generic arms exclude every value-taking name, or an option whose value is the verb
# (`git --namespace fetch origin`, which git runs as the command `origin`) would backtrack into them.
opt = re.compile(
    r"(?:-c\s*%s|-C\s+(%s)|(%s)(?:=|\s+)%s|(?:%s)(?:=|\s+)%s|(?!%s|%s)--[\w-]+(?:=%s)?|-(?![cC])[A-Za-z])\s+"
    % (val, val, mark, val, take, val, mark, take, val)
)
verb = re.compile(r"\bgit\s+((?:%s)*)(?:fetch|pull|merge|rebase|remote\s+update)(?![\w-])" % opt.pattern)

def unquote(s):
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"\x27":
        return s[1:-1]
    return s

for m in verb.finditer(cmd):
    opts = list(opt.finditer(m.group(1)))
    if any(o.group(2) for o in opts):
        continue
    cds = re.findall(r"(?:^|\n|&&|\|\||;)\s*cd\s+(\"[^\"]*\"|\x27[^\x27]*\x27|[^\s;&|]+)", cmd[: m.start()])
    parts = [unquote(cds[-1])] if cds else []
    parts += [unquote(o.group(1)) for o in opts if o.group(1)]
    d = os.path.join(*parts) if parts else "."
    if any(ch in d for ch in "$`"):
        continue
    print(d)
' 2>/dev/null || true)"
[[ -z "$dirs" ]] && exit 0

declare -A judged=()
report=""
while IFS= read -r dir; do
  [[ -z "$dir" ]] && continue
  top="$(git -C "$dir" rev-parse --show-toplevel 2>/dev/null || true)"
  [[ -z "$top" || -n "${judged[$top]:-}" ]] && continue
  judged[$top]=1
  branch="$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null || true)"
  [[ -z "$branch" ]] && continue
  upstream="$(git -C "$dir" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null || true)"
  [[ -z "$upstream" ]] && continue
  for head in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD; do git -C "$dir" rev-parse -q --verify "$head" >/dev/null 2>&1 && continue 2; done
  [[ -n "$(git -C "$dir" ls-files --unmerged 2>/dev/null)" ]] && continue
  behind="$(git -C "$dir" rev-list --count 'HEAD..@{u}' 2>/dev/null || echo 0)"
  [[ "$behind" == 0 ]] && continue
  ahead="$(git -C "$dir" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)"
  at=""
  [[ "$dir" != "." ]] && printf -v at ' -C %q' "$dir"
  if [[ "$ahead" == 0 ]]; then
    report+="$branch is behind $upstream by $behind — git${at} pull --ff-only"$'\n'
  elif [[ "$branch" == develop || "$branch" == main ]]; then
    report+="$branch is behind $upstream by $behind and ahead by $ahead (diverged)${at:+ in $dir} — a shared branch: STOP for the owner, never a local rebase or merge"$'\n'
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
