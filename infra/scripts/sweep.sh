#!/usr/bin/env bash
# Sweep the tracked tree AND `.local/` -- the memo, the coordination table, the lesson inboxes -- which a
# bare sweep cannot see: the shell's `grep` honours `.gitignore` and `.local/.gitignore` is `*`, so it
# reports clean over files it never opened. Inside a script `grep` is GNU grep, which honours nothing and
# would walk `.venv`. Both are answered by handing grep the file list rather than a flag.
# `.local/` is per-checkout: run this in the main checkout when the memo or the inboxes are the subject.
# Usage: infra/scripts/sweep.sh [grep flags] <pattern>   rc: 0 a hit, 1 none, 2 an error.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
mapfile -d '' -t files < <(git ls-files -z; [ -d .local ] && find .local -type f -print0)
[ "${#files[@]}" -gt 0 ] || { echo "sweep: no files to search under $PWD" >&2; exit 2; }
set +e
grep -I -H "$@" -- "${files[@]}"
rc=$?
exit $rc
