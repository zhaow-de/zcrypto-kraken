#!/usr/bin/env bash
# The consumers of a changed file: the tests and scripts that name it, and the tests that walk the tree from the
# repository root -- the selector guard, the metric census, the operator-term and internal-token walkers, the
# count list, the guidance guard -- which name no file and so never match a grep for one. Every path printed is
# a test or a reader to run before the commit. The search is `git grep -l` over `tests`, `infra` and `.claude`
# with every vault-shaped and `*.sops.*` path excluded: a recursive `grep -r` over `infra/` opens the vault files.
# An empty direct-reader list is printed as such and is a finding for the report, answered by the file's own test
# or its directory's readers -- never by the full suite, which is CI's on every push.
# Usage: infra/scripts/consumers.sh <path>...   (a path as the tree names it: infra/scripts/foo.sh, cli/engine/x.py)
#   rc: 0 printed, 2 usage or not in a repository.
set -euo pipefail
[[ $# -gt 0 ]] || { echo "usage: infra/scripts/consumers.sh <path>..." >&2; exit 2; }
root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "consumers: not inside a git repository" >&2; exit 2; }
cd "$root"
for path in "$@"; do
  name="$(basename "$path")"
  stem="${name%.*}"
  echo "## $path"
  echo "# direct readers (git grep -l, vault paths excluded):"
  # A Python module is also imported by its stem, as a word; a script is named by its file name alone.
  if [[ "$name" == *.py ]]; then stem_arg=(-e "$stem"); else stem_arg=(-e "$name"); fi
  readers="$(git grep -l -w "${stem_arg[@]}" -e "$name" -- tests infra .claude ':!*vault*' ':!*.sops.*' | grep -v -F -x "$path" || true)"
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- a finding: run the file's own test or its directory's readers, never the full suite)"; fi
done
echo "# tree walkers (tests that glob from the repository root; they name no file):"
# A walker globs, anchors on the repository root (`parents[1]`) and names a root directory beside it; a test that
# globs its own fixtures does neither.
while IFS= read -r t; do
  grep -q -E 'parents\[1\]' "$t" || continue
  grep -q -E "(ROOT|REPO|repo_root|root)[ /]*/? *['\"]?(tests|infra|cli|\.claude|docs)" "$t" || continue
  echo "$t"
done < <(git grep -l -E 'rglob\(|\.glob\(|os\.walk\(' -- tests ':!*vault*' || true) | sort
