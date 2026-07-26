#!/usr/bin/env bash
# Installed by the `capture` Ansible role at /usr/local/sbin/zcrypto-reboot-check -- do not hand-edit
# on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_reboot_check.py, which drives THIS script) instead.
#
# Attended-reboot detector (spec 00071, T0027). The capture VPSes run unattended-upgrades with
# Automatic-Reboot "false": patches install, the reboot is a human act. That closes one risk (an
# unwatched reboot of unbackfillable L2 capture and the live trade engine) and opens another -- a
# kernel flag nobody notices -- so this publishes the flag as a metric and an alert makes it loud.
#
# It emits 0 EXPLICITLY when no reboot is pending, never "no output". An absent series is
# indistinguishable from a dead exporter, so the healthy state has to be a value rather than a
# silence -- otherwise the alert cannot tell "fine" from "this host stopped reporting".
#
# Staleness is NOT this script's job: the textfile collector stamps node_textfile_mtime_seconds for
# every .prom it reads, which is what detects the timer having stopped (spec 00071 D3). A stale file
# is not a node_textfile_scrape_error -- that fires only on malformed input.
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

# Atomic publish: the collector globs this directory continuously and must never read a half-written
# file. mktemp as a SIBLING so the mv is a same-filesystem rename, never a copy.
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
