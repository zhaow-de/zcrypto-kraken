#!/usr/bin/env bash
# amend-reviewed-by.sh <commit-ish> "<reviewer model name>"
#
# Lands ONE `Reviewed-by: <model> <noreply@anthropic.com>` trailer on ONE commit of the
# current branch -- HEAD or any ancestor -- so a review's trailer is amended the turn the
# review returns instead of being batched later (.claude/rules/commit-messages.md). The
# trailer is appended as the last line of the trailer block with no blank line before it;
# a message with no trailer block gets the separating blank line first, so git parses it.
#
# Refuses, rewriting nothing: a dirty index or worktree (untracked files are fine); a
# detached HEAD or the main branch; a commit not on the current branch; a commit already
# carrying that exact trailer; two commits in the replayed range with byte-identical
# messages (a non-HEAD target is matched during the rebase by its full message); any
# commit in the replayed range whose hash is recorded in docs/reference/deploy-log.jsonl or
# fleet-pins.md (a rewrite would orphan a rollback operand -- exit 7); a merge commit in the
# replayed range (a rebase would linearize it -- exit 8). A pre-commit hook failing mid-rebase
# leaves the rebase in progress: fix, `git rebase --continue`, and re-verify the diff is empty.
# The blank-line rule keys on known trailer names, so a body ending in a `Note:`-shaped line
# still gets its separating blank line.
# Every commit after the target is rewritten -- hashes change, content does not, and the
# script asserts that with an empty `git diff <old-head> HEAD --stat` before it prints
# old -> new for the target.
set -euo pipefail
target_ish="${1:?usage: $0 <commit-ish> \"<model name>\"}"
model="${2:?usage: $0 <commit-ish> \"<model name>\"}"
trailer="Reviewed-by: ${model} <noreply@anthropic.com>"

branch=$(git branch --show-current)
[[ -z "$branch" ]] && { echo "amend-reviewed-by: refuse -- detached HEAD" >&2; exit 3; }
[[ "$branch" == "main" ]] && { echo "amend-reviewed-by: refuse -- never rewrite main" >&2; exit 3; }
[[ -n "$(git status --porcelain --untracked-files=no)" ]] && { echo "amend-reviewed-by: refuse -- dirty index/worktree; commit or stash first" >&2; exit 3; }
target=$(git rev-parse --verify -q "${target_ish}^{commit}") || { echo "amend-reviewed-by: refuse -- not a commit: $target_ish" >&2; exit 2; }
git merge-base --is-ancestor "$target" HEAD || { echo "amend-reviewed-by: refuse -- $target is not on $branch" >&2; exit 2; }
git log -1 --format=%B "$target" | grep -qF -- "$trailer" && { echo "amend-reviewed-by: refuse -- $target already carries '$trailer'" >&2; exit 4; }

msg=$(mktemp); new=$(mktemp); exec_script=$(mktemp)
trap 'rm -f "$msg" "$new" "$exec_script"' EXIT
git log -1 --format=%B "$target" > "$msg"

if git rev-parse --verify -q "${target}^" >/dev/null; then range="${target}^..HEAD"; base_arg="${target}^"; else range="HEAD"; base_arg="--root"; fi
for h in $(git rev-list --merges "$range"); do echo "amend-reviewed-by: refuse -- ${h:0:8} in the replayed range is a merge commit; a rebase would linearize it" >&2; exit 8; done
dup=0
for h in $(git rev-list "$range"); do [[ "$(git log -1 --format=%B "$h")" == "$(cat "$msg")" ]] && dup=$((dup+1)); done
(( dup == 1 )) || { echo "amend-reviewed-by: refuse -- $dup commits in the replayed range share the target's message" >&2; exit 5; }
top=$(git rev-parse --show-toplevel)
for rec in docs/reference/deploy-log.jsonl docs/reference/fleet-pins.md; do
  [[ -f "$top/$rec" ]] || continue
  for h in $(git rev-list "$range"); do
    grep -qE "${h}|${h:0:8}" "$top/$rec" && { echo "amend-reviewed-by: refuse -- ${h:0:8} is recorded in $rec; a rewrite would orphan it. Trailer before a hash is recorded, or cite by subject." >&2; exit 7; }
  done
done

awk 'BEGIN{RS="\0"} {sub(/\n+$/,""); printf "%s", $0}' "$msg" > "$new"
grep -qE '^(Co-Authored-By|Reviewed-by|Refine-Round-Closed|Signed-off-by): ' "$new" || printf '\n' >> "$new"
printf '\n%s\n' "$trailer" >> "$new"

old_head=$(git rev-parse HEAD)
if [[ "$target" == "$old_head" ]]; then
  git commit --amend -F "$new" --no-edit --quiet
else
  cat > "$exec_script" <<EOS
#!/usr/bin/env bash
set -e
[[ "\$(git log -1 --format=%B)" == "\$(cat '$msg')" ]] && git commit --amend -F '$new' --no-edit --quiet
exit 0
EOS
  chmod +x "$exec_script"
  git rebase --quiet $base_arg --exec "$exec_script"
fi

[[ -z "$(git diff "$old_head" HEAD --stat)" ]] || { echo "amend-reviewed-by: CONTENT CHANGED across the rewrite -- inspect before trusting this branch" >&2; exit 6; }
new_target=""
for h in $(git rev-list "$( [[ "$base_arg" == "--root" ]] && echo HEAD || echo "$base_arg..HEAD" )"); do
  [[ "$(git log -1 --format=%B "$h")" == "$(cat "$new")" ]] && new_target="$h" && break
done
[[ -n "$new_target" ]] || { echo "amend-reviewed-by: rewrite finished but the trailered commit was not found" >&2; exit 6; }
echo "amend-reviewed-by: $target -> $new_target  [$trailer]"
