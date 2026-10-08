#!/usr/bin/env bash
# The consumers of a changed file: the files under tests, infra and .claude that name it, then every test that globs,
# walks or lists files -- the tree walkers name no file and so never match a grep for one, and the list is a superset,
# since no text rule tells a tree walk from a fixture walk and a missed walker is a red CI run. The search is `git grep` with vault-shaped and
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
  case "$path" in tests/test_*.py) readers="$(printf '%s\n%s' "$path" "$readers")" ;; esac   # a changed test runs itself
  readers="$(printf '%s\n' "$readers" | sed '/^$/d')"
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- a finding: run the file's own test or its directory's readers, never the full suite)"; fi
done
echo "# tree walkers (every test that globs, walks or lists files -- a superset: one over its own fixtures is harmless to run):"
git grep -l -E 'rglob\(|\.glob\(|os\.walk\(|iterdir\(|listdir\(|scandir\(|ls-files' -- tests "${VAULT_EXCLUDES[@]}" | sort || true
