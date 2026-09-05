#!/usr/bin/env bash
# Installed by the `capture` Ansible role at /usr/local/sbin/zcrypto-capture-prune — do not
# hand-edit on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_capture_prune.py, which drives THIS script) instead.
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

# Segment retention (spec 00050 D8, T0032): the NAS mirror is the durable archive and a capture
# host's disk only a spool, so a committed hour older than <retention-days> has long since been
# pulled and hash-verified. An absolute cutoff instant, not `-mtime +N`: `-mtime` truncates to whole
# days, so its boundary is a day fuzzier than the retention the operator asked for.
cutoff=$(date -u -d "$days days ago" '+%Y-%m-%d %H:%M:%S')

# ONLY committed finals and their sidecars, and the name globs are the entire safety argument,
# because L2 book capture is unbackfillable. Parts, held-spills (rows the oracle never confirmed) and
# `<HH>.parquet.merging` all END in `.parquet`, so a `-name '*.parquet'` sweep would eat the live
# hour — the two-digit prefix is what keeps them apart; `*.corrupt*` is evidence and never deleted.
deleted=$(
  find "$dir" -type f \
    \( -name '[0-9][0-9].parquet' -o -name '[0-9][0-9].parquet.sha256' \) \
    ! -newermt "$cutoff" -print -delete | wc -l
)

# Empty <YYYY>/<MM>/<DD> directories are left behind deliberately: removing a directory could race
# the writer creating the current hour's, and they cost nothing.
echo "zcrypto-capture-prune: deleted=$deleted retention_days=$days cutoff=\"$cutoff UTC\" dir=$dir"
