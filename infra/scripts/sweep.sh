#!/usr/bin/env bash
# Sweep the tracked tree, the untracked files git does not ignore, AND `.local/` -- the memo, the coordination
# table, the lesson inboxes -- which a bare sweep cannot see: the shell's `grep` honours `.gitignore` and
# `.local/.gitignore` is `*`, so it reports clean over files it never opened. Inside a script `grep` is GNU
# grep, which honours nothing and would walk `.venv`. Both are answered by handing grep the file list rather
# than a flag.
# The `.local/` swept is the MAIN checkout's, whichever checkout you call this from: a linked worktree
# carries a `.local/` of its own holding nothing but the tracked `.gitignore`, and sweeping that one returns
# the silent clean this script exists to end.
# Usage: infra/scripts/sweep.sh [grep flags] <pattern>   rc: 0 a hit, 1 none, 2 an error.
set -euo pipefail
# Given no pattern -- none at all, or flags alone -- grep takes the first path as its regex and answers
# whatever that earns, a hit or a clean, never the error this is. Deciding this needs grep's option table:
# `--include '*.py'` has a bare operand that is not a pattern, so the flags below that take one AS A
# SEPARATE WORD consume it. `--color`'s argument is optional and grep reads it only attached, so it is not
# one of them. The table is the short list anyone sweeping would reach for, in the spelling it is written
# here: a flag outside it, a long spelling of one inside it (`--after-context 3`), or one clustered into
# `-lm 5`, still reads its operand as a pattern and passes. An attached `-eNEEDLE` is refused although grep
# accepts it -- a loud refusal naming the spelling that works, which is the recoverable error of the two.
# A pattern flag records the pattern from its OPERAND: `sweep.sh -e` supplies none, and grep would then bind the script's own `--` as the regex.
pattern=0
skip=0     # the next word is a flag's operand, to be stepped over
carries=0  # ...and that operand is the pattern, so a dangling `-e` never records one
for a in "$@"; do
  if [ "$skip" -eq 1 ]; then
    skip=0
    if [ "$carries" -eq 1 ]; then pattern=1; carries=0; fi
    continue
  fi
  case "$a" in
    -e|-f|--regexp|--file) skip=1; carries=1 ;;
    --regexp=*|--file=*) pattern=1 ;;
    -m|-A|-B|-C|-d|-D|--include|--exclude|--exclude-dir|--exclude-from|--label|--binary-files|--devices|--directories|--group-separator) skip=1 ;;
    -*) ;;
    *) pattern=1 ;;
  esac
done
[ "$pattern" -eq 1 ] || { echo "sweep: no pattern in '$*' -- a pattern is a bare word that is not a flag's operand, or follows -e/-f/--regexp/--file as its own word; usage: sweep.sh [grep flags] <pattern>" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"
main="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")"
# Under `--separate-git-dir`, or a worktree of a bare repo, that dirname is not a checkout: refuse rather
# than sweep the tracked tree alone.
[ "$(git -C "$main" rev-parse --show-toplevel 2>/dev/null)" = "$main" ] || {
  echo "sweep: no main checkout at $main, resolved from $(git rev-parse --git-common-dir)" >&2; exit 2; }
ledger=.local
[ "$main" = "$(pwd -P)" ] || ledger="$main/.local"
[ -d "$ledger" ] || echo "sweep: no $ledger -- the memo, the table and the inboxes are not in this sweep" >&2
mapfile -d '' -t listed < <(git ls-files -z --deduplicate --cached --others --exclude-standard -- ':(exclude).local'; [ -d "$ledger" ] && find "$ledger" ! -type d -print0)
# A tracked file deleted in the worktree is still in the index, and grep exits 2 over it whatever it printed,
# so the list is narrowed to what exists and rc keeps the meaning the usage line documents.
files=()
for f in ${listed[@]+"${listed[@]}"}; do
  if [ -f "$f" ]; then files+=("$f")
  # Everything the list can hold that grep will not open -- a nested checkout, a submodule, a link to a
  # directory, a fifo, a dangling link -- is named rather than dropped, because silence here answers
  # "absent" over content nobody opened. A path merely gone from the worktree is the exception: neither
  # test holds, it is in the index alone, with no worktree entry to name.
  elif [ -e "$f" ] || [ -L "$f" ]; then echo "sweep: $f is not a regular file, not swept" >&2
  fi
done
[ "${#files[@]}" -gt 0 ] || { echo "sweep: no files to search under $PWD" >&2; exit 2; }
set +e
grep -I -H "$@" -- "${files[@]}"
rc=$?
exit $rc
