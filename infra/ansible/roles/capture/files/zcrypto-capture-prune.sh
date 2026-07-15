#!/usr/bin/env bash
# Installed by the `capture` Ansible role at /usr/local/sbin/zcrypto-capture-prune — do not
# hand-edit on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_capture_prune.py, which drives THIS script) instead.
#
# Segment retention (spec 00050 D8, T0032): the NAS mirror is the durable archive; a capture host's
# local disk is only a spool (50 GB on the secondary, ~0.48 GB/day for 10 pairs). Once a committed
# hour is older than <retention-days> it has long since been pulled and hash-verified, so it is
# deleted here to keep the disk bounded.
#
# It deletes ONLY committed finals (`<HH>.parquet`) and their `<HH>.parquet.sha256` sidecars. The
# name globs are the entire safety argument, because L2 book capture is unbackfillable — a wrong
# delete here is permanent data loss, not an outage:
#   * `<HH>.part####.parquet`  — the live hour's parts, not yet merged into a final.
#   * `<HH>.held####.parquet`  — rows the corroboration oracle never confirmed (quarantine).
#   * `<HH>.parquet.merging`   — a complete merge interrupted before its atomic rename.
#   * `*.corrupt` / `*.corrupt.N` — forensic evidence of a read failure; never deleted, by design.
# Note that parts and held-spills END in `.parquet`: a `-name '*.parquet'` sweep would eat the live
# hour. The two-digit prefix match is what keeps them apart.
#
# Empty <YYYY>/<MM>/<DD> directories are deliberately left behind: removing directories could race
# the writer creating the current hour's, and they cost nothing.
set -euo pipefail

usage="usage: zcrypto-capture-prune <capture-data-dir> <retention-days>"
dir=${1:-}
days=${2:-}

[ -n "$dir" ] && [ -n "$days" ] || { echo "$usage" >&2; exit 2; }
case "$days" in
  '' | *[!0-9]*) echo "retention-days must be a positive integer, got: '$days' — $usage" >&2; exit 2 ;;
esac
[ "$days" -ge 1 ] || { echo "retention-days must be >= 1, got: '$days'" >&2; exit 2; }
case "$dir" in
  / | /var | /var/lib | /usr | /etc | /home) echo "refusing to sweep a system root: $dir" >&2; exit 2 ;;
esac
[ -d "$dir" ] || { echo "capture data dir not found: $dir" >&2; exit 2; }

# An absolute cutoff instant, not `-mtime +N`: `-mtime` truncates to whole days, so its boundary is
# a day fuzzier than the retention the operator asked for.
cutoff=$(date -u -d "$days days ago" '+%Y-%m-%d %H:%M:%S')

deleted=$(
  find "$dir" -type f \
    \( -name '[0-9][0-9].parquet' -o -name '[0-9][0-9].parquet.sha256' \) \
    ! -newermt "$cutoff" -print -delete | wc -l
)

echo "zcrypto-capture-prune: deleted=$deleted retention_days=$days cutoff=\"$cutoff UTC\" dir=$dir"
