#!/usr/bin/env bash
# Installed by the `capture` role at /usr/local/sbin/zcrypto-reboot-check, so a hand-edit there is
# lost on the next converge; tests/test_reboot_check.py drives this file. The reboot is a human act
# (spec 00071, T0027), so this publishes the pending-reboot flag as a metric.
set -euo pipefail

usage="usage: zcrypto-reboot-check <flag-path> <output.prom>"
flag=${1:-}
out=${2:-}
[ -n "$flag" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

# /run, not /var/run: the latter is a compatibility symlink. It resolves today, but the flag's real
# home is /run and an indirection inside a ProtectSystem=strict namespace is the kind of thing that
# breaks quietly. The caller passes the path; the unit passes /run/reboot-required.
pending=0
[ -e "$flag" ] && pending=1

# The collector globs this directory continuously, so mktemp as a SIBLING makes the mv a same-
# filesystem rename. 0 is emitted EXPLICITLY: an absent series is indistinguishable from a dead
# exporter, and staleness is node_textfile_mtime_seconds (spec 00071 D3).
tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP node_reboot_required 1 when the host has a pending reboot (/run/reboot-required), else 0."
  echo "# TYPE node_reboot_required gauge"
  echo "node_reboot_required $pending"
} > "$tmp"
chmod 0644 -- "$tmp"   # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out"
trap - EXIT
