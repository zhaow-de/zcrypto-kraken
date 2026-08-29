#!/usr/bin/env bash
# Installed by the `capture` Ansible role at /usr/local/sbin/zcrypto-clock-offset -- do not hand-edit
# on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_clock_offset.py, which drives THIS script) instead.
#
# Host clock-skew exporter (spec 00103 D4, T0037). A clock LEADING the true hour lets one bogus
# exchange timestamp close an archive hour early, and every clock-referenced counter measures that
# earliness with the same wrong clock, so the lead cancels itself out -- this reading is the ONLY
# detector for that residual, and the loss it precedes is unbackfillable.
#
# It runs on the HOST rather than inside the Alloy container deliberately: the in-container route
# reads the clock through adjtimex, gated behind CAP_SYS_TIME -- the capability that lets a process
# SET the clock. Widening what can move the clock in order to watch the clock is the wrong trade on
# hosts whose correctness argument is that the clock is not trusted (spec 00103 D4 records it).
#
# Both series are emitted on EVERY run, healthy included: an absent series is indistinguishable from
# a dead exporter, which is the ambiguity this exporter exists to remove.
#
# When chronyc is missing, fails, or answers in a shape this parser does not recognise, the offset
# publishes as NaN and the flag as 0. A fabricated 0 offset would read as a perfectly disciplined
# clock, and staying silent would lose the distinction altogether; NaN keeps "unknown" apart from
# "zero" -- PromQL comparisons against NaN are false, so the offset threshold cannot fire on it --
# while the 0 flag still pages through the alert's synchronisation leg. The exit status stays 0: the
# published values ARE the report, and a permanently failed oneshot beside them is a second channel
# nothing watches.
set -euo pipefail

usage="usage: zcrypto-clock-offset <chronyc-path> <output.prom>"
chronyc=${1:-}
out=${2:-}
[ -n "$chronyc" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

offset=NaN
synced=0

if tracking=$("$chronyc" tracking 2>/dev/null); then
  # The human-readable form, not `chronyc -c tracking`: the CSV column carries the offset as a bare
  # signed number, and reading its direction backwards would report a leading clock as a lagging one
  # -- exactly the distinction this exporter exists to make. This form spells it out in words.
  #
  # "System time     : 0.000000123 seconds fast of NTP time" -- the clock's CURRENT error, where
  # "Last offset" is only its error at the most recent measurement.
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
