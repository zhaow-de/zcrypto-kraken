#!/usr/bin/env bash
# Installed by the `capture` Ansible role at /usr/local/sbin/zcrypto-reboot-check -- do not hand-edit
# on the host, it is overwritten on the next converge. Edit this file (and re-run
# tests/test_reboot_check.py, which drives THIS script) instead. Attended-reboot detector (spec
# 00071, T0027): patches install unattended, the reboot is a human act, so the flag is published.
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
# file; mktemp as a SIBLING makes the mv a same-filesystem rename. 0 is emitted EXPLICITLY, because
# an absent series is indistinguishable from a dead exporter -- staleness is the collector's own
# node_textfile_mtime_seconds (spec 00071 D3), never this script's job.
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
