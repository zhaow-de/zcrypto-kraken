#!/usr/bin/env bash
# The consumers of a changed file: the files under tests, infra and .claude that name it, then the tests that glob,
# walk or list files and name its top-level directory -- or, for a changed test, walk their own. The search is
# `git grep` with vault-shaped and `*.sops.*` paths excluded, never `grep -r`, which opens the vault files.
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
  case "$path" in tests/test_*.py) readers="$(printf '%s\n%s' "$path" "$readers")" ;; esac
  readers="$(printf '%s\n' "$readers" | sed '/^$/d')"
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- no direct reader: a prose file runs nothing and its claim is the pre-review's or prove-inert.py's; a code file runs its own test; never the full suite)"; fi
  # A glob over a tmp_path fixture names no directory of the tree.
  if [[ "$path" != */* ]]; then echo "# tree walkers: none -- a top-level file"; continue; fi
  top="${path%%/*}"
  echo "# tree walkers over $top/ (the tests that glob, walk or list files and name that directory, or walk their own under tests/; a whole-tree walk naming none is not listed):"
  walkers="$(git grep -l -E 'rglob\(|\.glob\(|os\.walk\(|iterdir\(|listdir\(|scandir\(|ls-files' -- tests "${VAULT_EXCLUDES[@]}" | sort || true)"
  for w in $walkers; do
    if git grep -q -E "(^|[\"'/ (])${top//./\\.}([\"'/ )]|$)" -- "$w"; then printf '%s\n' "$w"
    elif [[ "$top" == tests ]] && git grep -q -E '__file__\)(\.resolve\(\))?\.parent(\.(glob|rglob|iterdir)\(|$)' -- "$w"; then printf '%s\n' "$w"; fi
  done
done
