#!/usr/bin/env bash
# Installed by the `ops` role at /usr/local/sbin/zcrypto-clock-offset, a copy of the capture role's
# script; tests/test_clock_offset.py drives the capture role's and holds this one's program equal to
# it. It runs on the host, not in the Alloy container, whose adjtimex route would need CAP_SYS_TIME.
set -euo pipefail

# archive-pull.sh.j2's log(): the shape the ops Alloy parse stage levels. WARNING, never ERROR: the
# 0 flag published below already pages through the clock rule's synchronisation leg.
log() {
  _ts=$(date -u +'%Y-%m-%d %H:%M:%S,%N')
  printf '%s %s zcrypto.clock-offset [zcrypto-clock-offset.sh] - %s\n' "${_ts%??????}" "$1" "$2" >&2
}

usage="usage: zcrypto-clock-offset <chronyc-path> <output.prom>"
chronyc=${1:-}
out=${2:-}
[ -n "$chronyc" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

# Both series are emitted on every run: an absent series is indistinguishable from a dead exporter.
# When chronyc fails or answers in a shape this parser does not recognise, these stay as they are: a
# fabricated 0 offset reads as a disciplined clock, and NaN comparisons are false, so the threshold
# cannot fire while the 0 flag still pages through the alert's synchronisation leg.
offset=NaN
synced=0

if tracking=$("$chronyc" tracking 2>/dev/null); then
  # The human-readable form, not `chronyc -c tracking`: the CSV column carries the offset as a bare
  # signed number, and reading its direction backwards reports a leading clock as a lagging one.
  magnitude=$(awk '$1 == "System" && $2 == "time" {print $4}' <<<"$tracking")
  direction=$(awk '$1 == "System" && $2 == "time" {print $6}' <<<"$tracking")
  leap=$(sed -n 's/^Leap status *: *//p' <<<"$tracking")

  if [[ $magnitude =~ ^[0-9]+(\.[0-9]+)?$ ]]; then
    case $direction in
      fast) offset=$magnitude ;;
      slow) offset=-$magnitude ;;
    esac
  fi

  # Only these three leap states mean the clock is disciplined; "Not synchronised" and anything
  # unrecognised fall through to the 0 above.
  case $leap in
    Normal | "Insert leap second" | "Delete leap second") synced=1 ;;
  esac
else
  log WARNING "'$chronyc tracking' failed; publishing an unknown offset"
fi

# Atomic publish: the collector globs this directory continuously and must never read a half-written
# file. mktemp as a sibling so the mv is a same-filesystem rename, never a copy. The exit status
# stays 0 even when chronyc failed -- the published values are the report.
tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP zcrypto_clock_offset_seconds The host clock's error against NTP time in seconds, positive when the clock is ahead; NaN when it could not be read."
  echo "# TYPE zcrypto_clock_offset_seconds gauge"
  echo "zcrypto_clock_offset_seconds $offset"
  echo "# HELP zcrypto_clock_synchronised 1 when the time daemon reports the clock synchronised to a reference, else 0."
  echo "# TYPE zcrypto_clock_synchronised gauge"
  echo "zcrypto_clock_synchronised $synced"
} > "$tmp"
chmod 0644 -- "$tmp"   # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out"
trap - EXIT
