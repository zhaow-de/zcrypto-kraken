#!/usr/bin/env bash
# Installed by the `engine` Ansible role at /usr/local/sbin/zcrypto-engine-journal-prune — do not
# hand-edit on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_engine_journal_prune.py, which drives THIS script) instead. The NAS holds the durable
# archive and the gate scores THAT copy, so this VPS tail is a local one (spec 00070, T0021).
set -euo pipefail

usage="usage: zcrypto-engine-journal-prune <journal-dir> <retention-days> [--dry-run] [--textfile PATH]"
dir=${1:-}
days=${2:-}
shift 2 2>/dev/null || true

dry_run=0
textfile=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1; shift ;;
    --textfile) textfile=${2:-}; [ -n "$textfile" ] || { echo "--textfile needs a path — $usage" >&2; exit 2; }; shift 2 ;;
    *) echo "unknown argument: $1 — $usage" >&2; exit 2 ;;
  esac
done

[ -n "$dir" ] && [ -n "$days" ] || { echo "$usage" >&2; exit 2; }
case "$days" in
  '' | *[!0-9]*) echo "retention-days must be a positive integer, got: '$days' — $usage" >&2; exit 2 ;;
esac
[ "$days" -ge 1 ] || { echo "retention-days must be >= 1, got: '$days'" >&2; exit 2; }
case "$dir" in
  / | /var | /var/lib | /usr | /etc | /home) echo "refusing to sweep a system root: $dir" >&2; exit 2 ;;
esac
[ -d "$dir" ] || { echo "engine journal dir not found: $dir" >&2; exit 2; }

# An absolute UTC DATE compared against the directory's own name, never `-mtime +N`: mtimes are
# rewritten by any restore or rsync, while the name is the day's identity. The current UTC day can
# never be strictly older than the cutoff, so it is excluded by construction, not by a special case.
cutoff=$(date -u -d "$days days ago" '+%Y-%m-%d')

# ISO names sort lexically == chronologically, so the newest <days> entries are simply the tail.
# Only names matching an ISO day are considered; anything else in the journal root is left untouched
# unconditionally, because an unexpected name means something else is writing here.
mapfile -t all < <(find "$dir" -mindepth 1 -maxdepth 1 -type d \
  -regextype posix-extended -regex '.*/20[0-9]{2}-[0-9]{2}-[0-9]{2}$' -printf '%f\n' | sort)

# A day-dir goes only if BOTH hold: (1) its name is strictly older than the cutoff and (2) it is not
# among the newest <retention-days> present. (2) is the load-bearing one: `cli/engine/cycle.py`
# derives each cycle's orders as a DELTA against the most recent journaled cycle, so an emptied
# journal rebuilds the whole book. In healthy operation the two coincide, a day arriving daily.
total=${#all[@]}
protected=$(( total > 10#$days ? 10#$days : total ))
candidates=$(( total - protected ))

deleted=0
for (( i = 0; i < candidates; i++ )); do
  name=${all[$i]}
  # Condition (1): strictly older than the cutoff date. String comparison is correct for ISO dates.
  [[ "$name" < "$cutoff" ]] || continue
  if [ "$dry_run" -eq 0 ]; then
    rm -rf -- "${dir:?}/${name:?}"
  fi
  deleted=$(( deleted + 1 ))
done

kept=$(( total - deleted ))
echo "zcrypto-engine-journal-prune: deleted=$deleted kept=$kept retention_days=$days cutoff=\"$cutoff UTC\" dir=$dir$([ "$dry_run" -eq 1 ] && echo ' (dry-run)' || true)"

# A dry run counts what it WOULD delete, so `kept` above is counterfactual -- publishing it would
# render a pruned journal that was never pruned. The log line says "(dry-run)"; a metric cannot.
if [ -n "$textfile" ] && [ "$dry_run" -eq 0 ]; then
  # A prune that silently stops running is otherwise indistinguishable from one with nothing to
  # do; _last_run_timestamp_seconds is what tells them apart (spec 00070 D5).
  oldest_age=0
  if [ "$kept" -gt 0 ]; then
    oldest=${all[$(( total - kept ))]}
    oldest_age=$(( $(date -u '+%s') - $(date -u -d "$oldest" '+%s') ))
  fi
  tmp=$(mktemp "${textfile}.XXXXXX")
  chmod 0644 -- "$tmp"   # mktemp makes 0600 and `mv` preserves it; the collector reads as non-root
  {
    echo "# HELP zcrypto_engine_journal_prune_deleted_days day-directories deleted by the last run"
    echo "zcrypto_engine_journal_prune_deleted_days $deleted"
    echo "# HELP zcrypto_engine_journal_prune_kept_days day-directories remaining after the last run"
    echo "zcrypto_engine_journal_prune_kept_days $kept"
    echo "# HELP zcrypto_engine_journal_prune_oldest_day_age_seconds age of the oldest retained day"
    echo "zcrypto_engine_journal_prune_oldest_day_age_seconds $oldest_age"
    echo "# HELP zcrypto_engine_journal_prune_last_run_timestamp_seconds unix time of the last completed run"
    echo "zcrypto_engine_journal_prune_last_run_timestamp_seconds $(date -u '+%s')"
  } > "$tmp"
  mv -- "$tmp" "$textfile"   # atomic: the collector never reads a half-written file
fi
