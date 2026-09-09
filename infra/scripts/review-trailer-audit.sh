#!/usr/bin/env bash
# Compute review-before-push compliance for <base>..HEAD (default develop) against
# .claude/rules/commit-messages.md: exit 0 iff the BRANCH carries a review record -- any
# `Reviewed-by:` trailer in the range -- 1 if it carries none, 2 on a refusal. The record is per
# branch, not per commit, so a trailer on HEAD answers for the whole range.
#
# What this CANNOT check, and does not claim to: that the reviewer was a different AGENT. The trailer
# names a model, and author and reviewer are routinely the same model here, so trailer equality is
# not evidence either way. The different-agent clause is enforced by whoever dispatches the review.
set -uo pipefail


base="${1:-develop}"

git rev-parse --git-dir >/dev/null 2>&1 \
  || { echo "refusing: not inside a git repository" >&2; exit 2; }

# Run from the repo root so the script works from any cwd in the tree.
root="$(git rev-parse --show-toplevel)" \
  || { echo "refusing: could not resolve the repository root" >&2; exit 2; }
cd "$root" || { echo "refusing: could not enter $root" >&2; exit 2; }

git rev-parse --verify --quiet "${base}^{commit}" >/dev/null \
  || { echo "refusing: '$base' does not resolve to a commit" >&2; exit 2; }

range="${base}..HEAD"

records=()
unattributed=()
bare=()
total=0

# One record per commit, field-separated by 0x1f and record-separated by 0x1e, so a subject
# containing anything at all cannot split a record. `separator=` on the trailers placeholder is
# load-bearing: without it the placeholder emits one line per trailer and every field after it
# lands on the wrong record — the exact misread that makes a naive audit report zero compliance.
while IFS=$'\x1f' read -r -d $'\x1e' hash subject reviewers authors; do
  hash="${hash#$'\n'}"
  [ -n "$hash" ] || continue
  total=$((total + 1))
  entry="$(git log -1 --format='%h' "$hash")  ${subject}"

  if [ -z "$reviewers" ]; then
    bare+=("$entry")
    continue
  fi

  records+=("$entry")
  # `authors` is read only to report the pair; it cannot decide independence -- see the header.
  [ -n "$authors" ] || unattributed+=("$entry")
done < <(git log --no-merges --format="%H%x1f%s%x1f%(trailers:key=Reviewed-by,valueonly,separator=%x2C)%x1f%(trailers:key=Co-authored-by,valueonly,separator=%x2C)%x1e" "$range")

merges="$(git rev-list --count --merges "$range")"

echo "review-trailer audit — ${range}"
echo "  ${total} non-merge commits, ${#records[@]} carrying a review record, ${merges} merge commits excluded"
echo

list() {
  local label="$1"; shift
  [ "$#" -eq 0 ] && return 0
  echo "${label}: $#"
  printf '  %s\n' "$@"
  echo
}

list "Review records (a Reviewed-by trailer; independence is not machine-checkable)" \
  "${records[@]+"${records[@]}"}"
list "Carrying a review record but no Co-Authored-By to pair it with" \
  "${unattributed[@]+"${unattributed[@]}"}"
list "Commits carrying no Reviewed-by — expected, the record is per branch" \
  "${bare[@]+"${bare[@]}"}"

if [ "${#records[@]}" -gt 0 ]; then
  echo "PASS — ${range} carries a review record."
  exit 0
fi

echo "FAIL — no commit in ${range} carries a Reviewed-by trailer."
echo "       Review the branch with an agent that is not its author, then amend"
echo "       'Reviewed-by: <reviewer model> <noreply@anthropic.com>' onto HEAD."
exit 1
