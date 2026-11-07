#!/usr/bin/env bash
# The consumers of a changed file: the files under tests, infra and .claude that name it, then the tests that glob,
# walk or list files and name its top-level directory -- or, for a changed test, walk their own. The search is
# `git grep` with vault-shaped and `*.sops.*` paths excluded, never `grep -r`, which opens the vault files.
# --direct lists only the tests/test_*.py files that name the path in a full form, never by its bare stem, and no walkers.
# stdout is the paths alone, one per line; every header and note is stderr.
# --tests keeps only the tests/test_*.py lines, so the output is a pytest argument list.
# A bare `$(...)` inside a pytest line drops the rc and hands pytest no argument, which is the whole suite: hold the
# list first, `T="$(infra/scripts/consumers.sh --tests --direct <path>)" || exit`, then run pytest over `$T`.
# direct readers' -- so the output is a pytest argument list with no runbook or skill in it; with none kept it prints
# `consumers: --tests found no test file for <paths>` on stderr and exits 2 with nothing on stdout. The caller reads
# that rc: a bare `$(...)` inside a pytest line drops it and hands pytest no argument, which is the whole suite, so the
# list is held first -- `T="$(infra/scripts/consumers.sh --tests --direct <path>)"` under `set -e`, or `|| exit` after
# it -- and pytest runs under `[ -n "$T" ]`.
# Usage: infra/scripts/consumers.sh [--tests] [--direct] <path>...   (a path as the tree names it: infra/scripts/foo.sh, cli/engine/x.py)
#   rc: 0 printed, 2 usage, not in a repository, or --tests with no test file kept.
set -euo pipefail
direct=0
tests=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --direct) direct=1; shift ;;
    --tests) tests=1; shift ;;
    *) break ;;
  esac
done
[[ $# -gt 0 ]] || { echo "usage: infra/scripts/consumers.sh [--tests] [--direct] <path>..." >&2; exit 2; }
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
  echo "## $path" >&2
  echo "# direct test readers (--direct: the path whole or split, a unique file name, the dotted module, the from-import; no tree walkers):" >&2
  if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- no test file names it in a full form: a prose file runs nothing and its claim is the pre-review's or prove-inert.py's; a code file runs its own test; never the full suite)" >&2; fi
}

consumers() {
  local path name stem readers top walkers w
  local -a stem_arg
  for path in "$@"; do
    if [[ $direct -eq 1 ]]; then direct_readers "$path"; continue; fi
    name="$(basename "$path")"
    stem="${name%.*}"
    echo "## $path" >&2
    echo "# direct readers (git grep -l, vault paths excluded):" >&2
    # A Python module is also imported by its stem, as a word; a script is named by its file name alone.
    if [[ "$name" == *.py ]]; then stem_arg=(-e "$stem"); else stem_arg=(-e "$name"); fi
    readers="$(git grep -l -w "${stem_arg[@]}" -e "$name" -- tests infra .claude "${VAULT_EXCLUDES[@]}" | grep -v -F -x "$path" || true)"
    case "$path" in tests/test_*.py) readers="$(printf '%s\n%s' "$path" "$readers")" ;; esac
    readers="$(printf '%s\n' "$readers" | sed '/^$/d')"
    if [[ -n "$readers" ]]; then printf '%s\n' "$readers"; else echo "# (none -- no direct reader: a prose file runs nothing and its claim is the pre-review's or prove-inert.py's; a code file runs its own test; never the full suite)" >&2; fi
    # A glob over a tmp_path fixture names no directory of the tree.
    if [[ "$path" != */* ]]; then echo "# tree walkers: none -- a top-level file" >&2; continue; fi
    top="${path%%/*}"
    echo "# tree walkers over $top/ (the tests that glob, walk or list files and name that directory, or walk their own under tests/; a whole-tree walk naming none is not listed):" >&2
    walkers="$(git grep -l -E 'rglob\(|\.glob\(|os\.walk\(|iterdir\(|listdir\(|scandir\(|ls-files' -- tests "${VAULT_EXCLUDES[@]}" | sort || true)"
    for w in $walkers; do
      if git grep -q -E "(^|[\"'/ (])${top//./\\.}([\"'/ )]|$)" -- "$w"; then printf '%s\n' "$w"
      elif [[ "$top" == tests ]] && git grep -q -E '__file__\)(\.resolve\(\))?\.parent(\.(glob|rglob|iterdir)\(|$)' -- "$w"; then printf '%s\n' "$w"; fi
    done
  done
}

if [[ $tests -eq 0 ]]; then consumers "$@"; exit 0; fi
kept="$(consumers "$@" | grep -E '^tests/test_[^/]+\.py$' || true)"
if [[ -z "$kept" ]]; then echo "consumers: --tests found no test file for $*" >&2; exit 2; fi
printf '%s\n' "$kept"
