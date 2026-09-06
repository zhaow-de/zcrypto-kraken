#!/usr/bin/env bash
# Compute review-before-push compliance for <base>..HEAD (default develop) against
# .claude/rules/commit-messages.md: exit 0 iff no CODE commit lacks `Reviewed-by:`, 1 if any does, 2
# on a refusal. Doc-kind commits are REPORTED, never failed, since their exemption turns on an
# approval no query recovers; an unreadable or unlisted type is UNCLASSIFIED and fails closed.
set -uo pipefail

CODE_KINDS='feat|fix|test|refactor|perf|chore|build|ci'
DOC_KINDS='docs|claude'

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

code_missing=()
doc_missing=()
other_missing=()
total=0
reviewed=0

# One record per commit, field-separated by 0x1f and record-separated by 0x1e, so a subject
# containing anything at all cannot split a record. `separator=` on the trailers placeholder is
# load-bearing: without it the placeholder emits one line per trailer and every field after it
# lands on the wrong record — the exact misread that makes a naive audit report zero compliance.
while IFS=$'\x1f' read -r -d $'\x1e' hash subject reviewers; do
  hash="${hash#$'\n'}"
  [ -n "$hash" ] || continue
  total=$((total + 1))

  if [ -n "$reviewers" ]; then
    reviewed=$((reviewed + 1))
    continue
  fi

  kind="$(printf '%s' "$subject" | sed -n -E 's/^([a-z]+)(\([^)]*\))?!?:.*/\1/p')"
  entry="$(git log -1 --format='%h' "$hash")  ${subject}"

  if printf '%s' "$kind" | grep -qxE "$CODE_KINDS"; then
    code_missing+=("$entry")
  elif printf '%s' "$kind" | grep -qxE "$DOC_KINDS"; then
    doc_missing+=("$entry")
  else
    other_missing+=("$entry")
  fi
done < <(git log --no-merges --format="%H%x1f%s%x1f%(trailers:key=Reviewed-by,valueonly,separator=%x2C)%x1e" "$range")

merges="$(git rev-list --count --merges "$range")"

echo "review-trailer audit — ${range}"
echo "  ${total} non-merge commits, ${reviewed} carry Reviewed-by, ${merges} merge commits excluded"
echo

report() {
  local label="$1" verdict="$2"; shift 2
  local n=$#
  if [ "$n" -eq 0 ]; then
    echo "${label} without Reviewed-by: none"
  else
    echo "${label} without Reviewed-by: ${n} — ${verdict}"
    printf '  %s\n' "$@"
  fi
  echo
}

report "CODE commits (${CODE_KINDS//|/, })" "FAIL" "${code_missing[@]+"${code_missing[@]}"}"
report "DOC commits (${DOC_KINDS//|/, })" "reported for a human decision, not failed" \
  "${doc_missing[@]+"${doc_missing[@]}"}"
report "UNCLASSIFIED commits (type unreadable or in neither list)" "FAIL" \
  "${other_missing[@]+"${other_missing[@]}"}"

failing=$(( ${#code_missing[@]} + ${#other_missing[@]} ))
if [ "$failing" -eq 0 ]; then
  echo "PASS — every code-kind commit in ${range} carries a Reviewed-by trailer."
  [ "${#doc_missing[@]}" -eq 0 ] \
    || echo "       ${#doc_missing[@]} doc-kind commit(s) above still need a human's read."
  exit 0
fi

echo "FAIL — ${failing} commit(s) in ${range} must be reviewed and have the trailer amended on."
echo "       Review each with a subagent that is not its author, then amend"
echo "       'Reviewed-by: <reviewer model> <noreply@anthropic.com>' as the LAST trailer."
exit 1
