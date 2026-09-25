#!/usr/bin/env bash
# Installed by the `cache` role at /usr/local/sbin/zcrypto-reboot-check, a copy of the capture role's;
# tests/test_reboot_check.py drives the capture role's and holds this one's program equal to it.
set -euo pipefail

usage="usage: zcrypto-reboot-check <flag-path> <output.prom>"
flag=${1:-}
out=${2:-}
[ -n "$flag" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }

# /run, not /var/run: the latter is a compatibility symlink; the unit passes /run/reboot-required.
pending=0
[ -e "$flag" ] && pending=1

# Atomic publish: the collector globs this directory continuously and must never read a half-written
# file, and mktemp as a sibling makes the mv a same-filesystem rename. 0 is emitted explicitly: an
# absent series is indistinguishable from a dead exporter.
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
