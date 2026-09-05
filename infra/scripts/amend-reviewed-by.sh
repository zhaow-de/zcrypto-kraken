#!/usr/bin/env bash
# amend-reviewed-by.sh <commit-ish> "<reviewer model name>"
# Lands ONE `Reviewed-by:` trailer on ONE commit, HEAD or any ancestor, so a review's trailer lands
# the turn it returns (.claude/rules/commit-messages.md). Each refusal below rewrites nothing and
# prints its own reason and exit code.
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
for base in origin/develop develop; do
  [[ "$branch" == "${base#origin/}" ]] && continue
  git rev-parse -q --verify "$base" >/dev/null 2>&1 || continue
  git merge-base --is-ancestor "$target" "$base" && { echo "amend-reviewed-by: refuse -- $target is already on $base; rewriting it here would fork the branch off its base" >&2; exit 9; }
done
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
# Keys on the LAST line matching a known trailer name, so a `Note:`-shaped final line still gets
# its blank separator and a trailer name quoted mid-body does not suppress it. Claude-Session is
# listed so the harness default still parses, never because it is allowed.
last=$(tail -n 1 "$new")
[[ "$last" =~ ^([Cc]o-[Aa]uthored-[Bb]y|Reviewed-by|Refine-Round-Closed|Signed-off-by|BREAKING-CHANGE|Claude-Session):\  ]] || printf '\n' >> "$new"
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
  # A pre-commit hook failing here leaves the rebase in progress: fix it, `git rebase --continue`,
  # and re-verify that the diff below is empty.
  git rebase --quiet $base_arg --exec "$exec_script"
fi

[[ -z "$(git diff "$old_head" HEAD --stat)" ]] || { echo "amend-reviewed-by: CONTENT CHANGED across the rewrite -- inspect before trusting this branch" >&2; exit 6; }
new_target=""
for h in $(git rev-list "$( [[ "$base_arg" == "--root" ]] && echo HEAD || echo "$base_arg..HEAD" )"); do
  [[ "$(git log -1 --format=%B "$h")" == "$(cat "$new")" ]] && new_target="$h" && break
done
[[ -n "$new_target" ]] || { echo "amend-reviewed-by: rewrite finished but the trailered commit was not found" >&2; exit 6; }
echo "amend-reviewed-by: $target -> $new_target  [$trailer]"
