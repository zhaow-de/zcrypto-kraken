#!/usr/bin/env bash
# Installed by the `capture` role at /usr/local/sbin/zcrypto-clock-offset, so a hand-edit there is
# lost on the next converge; tests/test_clock_offset.py drives this file. Host clock-skew exporter
# (spec 00103 D4, T0037): a clock LEADING the true hour closes an archive hour early, and no clock-
# referenced counter can see it, because the wrong clock subtracts its own lead back out. It runs on
# the HOST rather than in the Alloy container, whose adjtimex route needs CAP_SYS_TIME -- the
# capability to SET the clock, on a host whose correctness argument is that the clock is not
# trusted.
set -euo pipefail

usage="usage: zcrypto-clock-offset <chronyc-path> <output.prom>"
chronyc=${1:-}
out=${2:-}
[ -n "$chronyc" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

# Both series are emitted on EVERY run: an absent series is indistinguishable from a dead exporter.
# When chronyc fails or answers in a shape this parser does not recognise, these stay as they are: a
# fabricated 0 offset reads as a disciplined clock, and NaN comparisons are false, so the threshold
# cannot fire while the 0 flag still pages through the alert's synchronisation leg.
offset=NaN
synced=0

if tracking=$("$chronyc" tracking 2>/dev/null); then
  # The human-readable form, not `chronyc -c tracking`, whose CSV column carries the offset as a
  # bare signed number that reads a leading clock as a lagging one. "System time" is the clock's
  # CURRENT error, where "Last offset" is its error at the most recent measurement.
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
  # unrecognised fall through to the 0 above. Fail closed -- this signal exists to page.
  case $leap in
    Normal | "Insert leap second" | "Delete leap second") synced=1 ;;
  esac
else
  echo "zcrypto-clock-offset: '$chronyc tracking' failed; publishing an unknown offset" >&2
fi

# Atomic publish: the collector globs this directory continuously and must never read a half-written
# file. mktemp as a SIBLING so the mv is a same-filesystem rename, never a copy.
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
