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
# With no argument at all grep takes the first path as its pattern and answers whatever rc that accidental
# regex earns -- a hit or a clean, never the error this is.
[ $# -gt 0 ] || { echo "sweep: usage: sweep.sh [grep flags] <pattern>" >&2; exit 2; }
cd "$(git rev-parse --show-toplevel)"
main="$(dirname "$(cd "$(git rev-parse --git-common-dir)" && pwd -P)")"
# Under `--separate-git-dir`, or a worktree of a bare repo, that dirname is not a checkout: refuse rather
# than sweep the tracked tree alone.
[ "$(git -C "$main" rev-parse --show-toplevel 2>/dev/null)" = "$main" ] || {
  echo "sweep: no main checkout at $main, resolved from $(git rev-parse --git-common-dir)" >&2; exit 2; }
ledger=.local
[ "$main" = "$(pwd -P)" ] || ledger="$main/.local"
[ -d "$ledger" ] || echo "sweep: no $ledger -- the memo, the table and the inboxes are not in this sweep" >&2
mapfile -d '' -t listed < <(git ls-files -z --deduplicate --cached --others --exclude-standard -- ':(exclude).local'; [ -d "$ledger" ] && find "$ledger" -type f -print0)
# A tracked file deleted in the worktree is still in the index, and grep exits 2 over it whatever it printed,
# so the list is narrowed to what exists and rc keeps the meaning the usage line documents.
files=()
for f in ${listed[@]+"${listed[@]}"}; do
  if [ -f "$f" ]; then files+=("$f")
  # A nested checkout, a submodule and a link to a directory all pass the directory test, and a dangling
  # link passes none: one band, named not dropped, because silence here answers "absent" over content
  # nobody opened. A path merely gone from the worktree is the exception -- it is in the index alone, with
  # no worktree entry to name.
  elif [ -d "$f" ] || [ -L "$f" ]; then echo "sweep: $f is not a regular file, not swept" >&2
  fi
done
[ "${#files[@]}" -gt 0 ] || { echo "sweep: no files to search under $PWD" >&2; exit 2; }
set +e
grep -I -H "$@" -- "${files[@]}"
rc=$?
exit $rc
