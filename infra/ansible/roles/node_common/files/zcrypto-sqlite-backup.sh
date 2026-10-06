#!/usr/bin/env bash
# Installed by the `node_common` role at /usr/local/sbin/zcrypto-sqlite-backup; edit
# infra/ansible/roles/node_common/files/zcrypto-sqlite-backup.sh and re-converge.
set -euo pipefail

# archive-pull.sh.j2's log(): the line shape an Alloy parse stage levels.
log() {
  _ts=$(date -u +'%Y-%m-%d %H:%M:%S,%N')
  printf '%s %s zcrypto.sqlite-backup [zcrypto-sqlite-backup.sh] - %s\n' "${_ts%??????}" "$1" "$2" >&2
}

# The gauge is left as it was: its age is the failure's signal.
fail() {
  log ERROR "$1"
  exit 1
}

usage="usage: zcrypto-sqlite-backup <name> <database> <staging-dir> <dest-dir> <keep-days> <output.prom>"
[ $# -eq 6 ] && [[ $1 =~ ^[A-Za-z0-9_-]+$ && -n $2 && -n $3 && -n $4 && $5 =~ ^[0-9]+$ && -n $6 ]] || {
  log ERROR "$usage"
  exit 2
}
name=$1
db=$2
staging=$3
dest=$4
keep_days=$5
out=$6

# One run of a backup at a time: the file a run finds already staged is then never one another run is still writing.
lock="$(dirname -- "$out")/zcrypto-sqlite-backup-$name.lock"
exec {lock_fd}>>"$lock" || fail "cannot open $lock"
flock -n "$lock_fd" || fail "another run of the $name backup holds $lock"

# A command prefix the database and the staging directory are read through, empty where the host holds them itself.
read -r -a runner <<<"${SQLITE_BACKUP_RUNNER:-}"
copy=${SQLITE_BACKUP_COPY:-cp }

now=$(date -u +%s)
staged="$staging/$name-$(date -u -d "@$now" +%Y-%m-%dT%H%M%SZ).sqlite"
cutoff=$(date -u -d "@$((now - 10#$keep_days * 86400))" +%Y-%m-%d)

# systemd signals the unit's whole control group, so a child dies with the script at the signal's default: a Python
# handler runs only between bytecodes and would wait out SQLite's VACUUM before removing what this trap removes at
# once. A runner's VACUUM runs on in its container, out of the host's reach; its file is never copied, and the prune
# removes it past the keep-days.
stopped() {
  rm -f -- "$dest/${staged##*/}" || true
  if [ ${#runner[@]} -eq 0 ]; then
    rm -f -- "$staged" "$staged-journal" || true
  fi
  log ERROR "stopped by $1 before the backup completed; this run's files are removed"
  exit "$2"
}
trap 'stopped SIGTERM 143' TERM
trap 'stopped SIGINT 130' INT

# One process makes the staging directory and runs the VACUUM, so the runner's uid owns both.
vacuum=$(
  cat <<'PY'
import contextlib, os, sqlite3, sys, urllib.parse

db, staged = sys.argv[1:]
os.makedirs(os.path.dirname(staged), exist_ok=True)
if os.path.lexists(staged):
    sys.exit(f"{staged} already exists")
try:
    source = sqlite3.connect("file:" + urllib.parse.quote(db) + "?mode=ro", uri=True)
    source.execute("VACUUM INTO ?", (staged,))
    source.close()
except BaseException:
    for leftover in (staged, staged + "-journal"):
        with contextlib.suppress(FileNotFoundError):
            os.remove(leftover)
    raise
PY
)
# By the date in the name, which a copy keeps and its mtime need not.
prune=$(
  cat <<'PY'
import os, re, sys

directory, name, cutoff = sys.argv[1:]
for entry in os.listdir(directory):
    dated = re.fullmatch(re.escape(name) + r"-(\d{4}-\d{2}-\d{2})T\d{6}Z\.sqlite", entry)
    if dated and dated.group(1) < cutoff:
        os.remove(os.path.join(directory, entry))
PY
)

"${runner[@]}" python3 -c "$vacuum" "$db" "$staged" || fail "VACUUM INTO $staged from $db failed"

# 0700, since the copies carry the database.
[ -d "$dest" ] || install -d -m 0700 -- "$dest" || fail "cannot create $dest"
# The prefix's last word takes the staged path whole, `web:` becoming `web:<staged>`; a prefix ending in a space, as
# the host's `cp ` does, takes it as a word of its own.
read -r -a copy_command <<<"$copy"
if [[ $copy == *[[:space:]] ]]; then
  copy_command+=("$staged")
else
  copy_command[-1]+=$staged
fi
# A copy that fails part-way leaves its file under a backup's name, which the destination's readers would keep.
"${copy_command[@]}" "$dest/" || {
  rm -f -- "$dest/${staged##*/}" || true
  fail "copying $staged into $dest failed"
}

"${runner[@]}" python3 -c "$prune" "$staging" "$name" "$cutoff" || fail "pruning $staging failed"
python3 -c "$prune" "$dest" "$name" "$cutoff" || fail "pruning $dest failed"

# The run's files are complete: a stop from here leaves them, and the gauge as it was.
trap - TERM INT

# Atomic publish, as the reboot check's: the collector globs the directory, and mktemp as a sibling makes the mv a
# same-filesystem rename.
tmp=$(mktemp "${out}.XXXXXX") || fail "cannot write beside $out"
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP zcrypto_sqlite_backup_last_success_timestamp_seconds Unix time of the last backup written, copied out and pruned."
  echo "# TYPE zcrypto_sqlite_backup_last_success_timestamp_seconds gauge"
  echo "zcrypto_sqlite_backup_last_success_timestamp_seconds{db=\"$name\"} $now"
} >"$tmp" || fail "cannot write $tmp"
chmod 0644 -- "$tmp" || fail "cannot publish $out" # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out" || fail "cannot publish $out"
trap - EXIT
log INFO "backed up $db to $staged and copied it into $dest"
