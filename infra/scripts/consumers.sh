#!/usr/bin/env bash
# The consumers of a changed file: the files under tests, infra and .claude that name it, then the tests that glob,
# walk or list files and name its top-level directory -- or, for a changed test, walk their own. The search is
# `git grep` with vault-shaped and `*.sops.*` paths excluded, never `grep -r`, which opens the vault files.
# --direct lists only the tests/test_*.py files that name the path in a full form, never by its bare stem, and no walkers.
# Usage: infra/scripts/consumers.sh [--direct] <path>...   (a path as the tree names it: infra/scripts/foo.sh, cli/engine/x.py)
#   rc: 0 printed, 2 usage or not in a repository.
set -euo pipefail
direct=0
if [[ "${1:-}" == --direct ]]; then direct=1; shift; fi
[[ $# -gt 0 ]] || { echo "usage: infra/scripts/consumers.sh [--direct] <path>..." >&2; exit 2; }
root="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "consumers: not inside a git repository" >&2; exit 2; }
cd "$root"
VAULT_EXCLUDES=(':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519')

# A form's edges. A path's right edge refuses a further extension, so `foo.sh` is not read in `foo.sh.j2`, and a
# package's refuses a submodule; a module's admits an attribute, `cli.x.y._NAME` being a read of `cli/x/y.py`.
L='(^|[^[:alnum:]_.-])'
R='([^[:alnum:]_]|$)'
RP='([^[:alnum:]_.]|\.([^[:alnum:]_]|$)|$)'
SEP="(/|[\"'][[:space:]]*[/,][[:space:]]*[\"'])"
ere() { printf '%s' "$1" | sed -E 's/[][\\.*^$+?(){}|]/\\&/g'; }
direct_readers() {
  local path="$1" split mod="" pkg nm readers
  local -a forms paren=()
  split="$(ere "$path")"
  forms=(-e "$L${split//\//"$SEP"}$RP")
  # A name several tracked files carry, `command.py` or `__init__.py`, names none of them.
  if [[ "$path" == */* && -z "$(git ls-files -- ":(glob)**/${path##*/}" | grep -v -F -x "$path" || true)" ]]; then
    forms+=(-e "$L$(ere "${path##*/}")$RP")
  fi
  if [[ "$path" == *.py ]]; then mod="${path%.py}"; mod="${mod%/__init__}"; mod="${mod//\//.}"; fi
  if [[ "$mod" == *.* ]]; then
    pkg="$(ere "${mod%.*}")"; nm="$(ere "${mod##*.}")"
    if [[ "$path" == */__init__.py ]]; then forms+=(-e "$L$(ere "$mod")$RP"); else forms+=(-e "$L$(ere "$mod")$R"); fi
    forms+=(-e "${L}from[[:space:]]+${pkg}[[:space:]]+import[[:space:]]+(.*[^[:alnum:]_])?$nm$R")
    paren=(-e "^[[:space:]]*from[[:space:]]+${pkg}[[:space:]]+import[[:space:]]*\(" -e "^[[:space:]]+$nm([[:space:]]+as[[:space:]]+[[:alnum:]_]+)?[[:space:]]*,?[[:space:]]*(#.*)?$")
  elif [[ -n "$mod" ]]; then
    # A top-level module's dotted name is its bare stem, so only an import statement names it.
    forms+=(-e "${L}(import|from)[[:space:]]+$(ere "$mod")([^[:alnum:]_.]|$)")
  fi
  readers="$(git grep -l -E "${forms[@]}" -- ':(glob)tests/test_*.py' "${VAULT_EXCLUDES[@]}" || true)"
  # A parenthesised import splits the name onto its own line: the file must hold both the opening and the name.
  if [[ ${#paren[@]} -gt 0 ]]; then
    readers="$(printf '%s\n%s' "$readers" "$(git grep -l -E --all-match "${paren[@]}" -- ':(glob)tests/test_*.py' "${VAULT_EXCLUDES[@]}" || true)")"
  fi
  readers="$(printf '%s\n' "$readers" | sed '/^$/d' | grep -v -F -x "$path" | LC_ALL=C sort -u || true)"
  case "$path" in tests/test_*.py) readers="$(printf '%s\n%s' "$path" "$readers" | sed '/^$/d')" ;; esac
  echo "## $path"
  echo "# direct test readers (--direct: the path whole or split, a unique file name, the dotted module, the from-import; no tree walkers):"
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- no test file names it in a full form: a prose file runs nothing and its claim is the pre-review's or prove-inert.py's; a code file runs its own test; never the full suite)"; fi
}

for path in "$@"; do
  if [[ $direct -eq 1 ]]; then direct_readers "$path"; continue; fi
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
