#!/usr/bin/env bash
# The consumers of a changed file: the files under tests, infra and .claude that name it, then the tests that walk
# the tree, which name no file and so never match a grep for one. The search is `git grep` with vault-shaped and
# `*.sops.*` paths excluded, never `grep -r`, which opens the vault files.
# Usage: infra/scripts/consumers.sh <path>...   (a path as the tree names it: infra/scripts/foo.sh, cli/engine/x.py)
#   rc: 0 printed, 2 usage or not in a repository.
set -euo pipefail
[[ $# -gt 0 ]] || { echo "usage: infra/scripts/consumers.sh <path>..." >&2; exit 2; }
root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "consumers: not inside a git repository" >&2; exit 2; }
cd "$root"
VAULT_EXCLUDES=(':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519')
for path in "$@"; do
  name="$(basename "$path")"
  stem="${name%.*}"
  echo "## $path"
  echo "# direct readers (git grep -l, vault paths excluded):"
  # A Python module is also imported by its stem, as a word; a script is named by its file name alone.
  if [[ "$name" == *.py ]]; then stem_arg=(-e "$stem"); else stem_arg=(-e "$name"); fi
  readers="$(git grep -l -w "${stem_arg[@]}" -e "$name" -- tests infra .claude "${VAULT_EXCLUDES[@]}" | grep -v -F -x "$path" || true)"
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- a finding: run the file's own test or its directory's readers, never the full suite)"; fi
done
echo "# tree walkers (tests that walk the tree; they name no file):"
while IFS= read -r t; do
  if grep -q -E 'ls-files' "$t"; then echo "$t"; continue; fi
  if grep -q -E 'resolve\(\)\.parent\b' "$t" && grep -q -E 'glob\(["'"'"']test_' "$t"; then echo "$t"; continue; fi
  grep -q -E 'parents\[1\]|parent\.parent' "$t" || continue
  grep -q -E "(ROOT|REPO|repo_root|root)[ /]*/? *['\"]?(tests|infra|cli|\.claude|docs)" "$t" || continue
  echo "$t"
done < <(git grep -l -E 'rglob\(|\.glob\(|os\.walk\(|iterdir\(|ls-files' -- tests "${VAULT_EXCLUDES[@]}" || true) | sort
