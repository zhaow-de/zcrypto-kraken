#!/usr/bin/env bash
# Compute review-before-push compliance for <base>..HEAD (default develop) against
# .claude/rules/commit-messages.md: exit 0 if the record commit carries a `Reviewed-by:` trailer or
# the range is empty, 1 otherwise, 2 on a refusal. The record commit is HEAD, or HEAD's first
# parent when HEAD is a merge -- a merge carries no trailers by convention (`merge-pr`), and
# `amend-reviewed-by.sh` refuses to rewrite one, so a reviewed branch that merged its base back in
# would otherwise fail with no route out.
#
# HEAD specifically, not anywhere in the range: a trailer on an early commit with unreviewed work
# after it would otherwise pass, and the tip is what gets pushed. When a fix-up lands after the read,
# the record moves to the new tip with it -- the trailer says this BRANCH was read by that model, and
# the branch has changed.
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
total=0

# One record per commit, field-separated by 0x1f and record-separated by 0x1e, so a subject
# containing anything at all cannot split a record. `separator=` on the trailers placeholder is
# load-bearing: without it the placeholder emits one line per trailer and every field after it
# lands on the wrong record — the exact misread that makes a naive audit report zero compliance.
while IFS=$'\x1f' read -r -d $'\x1e' hash subject reviewers; do
  hash="${hash#$'\n'}"
  [ -n "$hash" ] || continue
  total=$((total + 1))
  entry="$(git log -1 --format='%h' "$hash")  ${subject}"

  [ -n "$reviewers" ] || continue

  records+=("$entry")
done < <(git log --no-merges --format="%H%x1f%s%x1f%(trailers:key=Reviewed-by,valueonly,separator=%x2C)%x1e" "$range")

merges="$(git rev-list --count --merges "$range")"

# A merge tip carries no trailers by convention, so the record sits on its first parent.
if [ "$(git rev-list --parents -n 1 HEAD | wc -w)" -gt 2 ]; then
  record_at="HEAD^"; record_note=" (HEAD is a merge; read from its first parent)"
else
  record_at="HEAD"; record_note=""
fi
head_trailer="$(git log -1 --format='%(trailers:key=Reviewed-by,valueonly,separator=%x2C)' "$record_at")"
head_line="$(git log -1 --format='%h  %s' "$record_at")"

echo "review-trailer audit — ${range}"
echo "  ${total} non-merge commits, ${#records[@]} carrying a trailer, ${merges} merge commits excluded"
echo

list() {
  local label="$1"; shift
  [ "$#" -eq 0 ] && return 0
  echo "${label}: $#"
  printf '  %s\n' "$@"
  echo
}

list "Commits carrying a Reviewed-by trailer (independence is not machine-checkable)" \
  "${records[@]+"${records[@]}"}"

if [ "$total" -eq 0 ]; then
  echo "PASS — ${range} has no commits to review."
  exit 0
fi

if [ -n "$head_trailer" ]; then
  echo "PASS — the branch's review record is present${record_note}."
  echo "  ${head_line}"
  echo "  ${head_trailer}"
  exit 0
fi

echo "FAIL — no Reviewed-by trailer on the record commit${record_note}, so ${range} has no review record."
echo "  ${head_line}"
[ "${#records[@]}" -eq 0 ] \
  || echo "       Earlier commits carry one, but work has landed since: the record belongs on the tip."
echo "       Review the branch with an agent that is not its author, then"
echo "       infra/scripts/amend-reviewed-by.sh ${record_at} \"<reviewer model>\""
exit 1
