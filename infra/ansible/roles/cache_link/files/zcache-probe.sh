#!/usr/bin/env bash
# Installed by the `cache_link` role at /usr/local/sbin/zcache-probe, so a hand-edit there is lost on
# the next converge; tests/test_zcache_probe.py drives this file.
set -euo pipefail

usage="usage: zcache-probe <wireguard-conf> <output.prom>"
conf=${1:-}
out=${2:-}
[ -n "$conf" ] && [ -n "$out" ] || { echo "$usage" >&2; exit 2; }
iface=$(basename "$conf" .conf)

# The peers are read from the rendered config, never from the running interface: an interface that is
# down lists no peers, and a peer absent from the output would read as healthy by omission.
mapfile -t peers < <(sed -n 's|^AllowedIPs[[:space:]]*=[[:space:]]*\([0-9.]*\)/32[[:space:]]*$|\1|p' "$conf")
[ "${#peers[@]}" -gt 0 ] || { echo "zcache-probe: $conf names no /32 AllowedIPs peer" >&2; exit 1; }

# `wg show <if> dump`: an interface line, then one tab-separated line per peer whose fourth field is its
# allowed-ips and fifth its latest handshake in epoch seconds, 0 when it has none.
declare -A handshake=()
if dump=$(wg show "$iface" dump 2>/dev/null); then
  while IFS=$'\t' read -r _key _psk _endpoint allowed latest _rest; do
    handshake[${allowed%/32}]=$latest
  done < <(printf '%s\n' "$dump" | tail -n +2)
fi
now=$(date +%s)

# Atomic publish: the collector globs this directory continuously, and a sibling mktemp makes the mv a
# same-filesystem rename.
tmp=$(mktemp "${out}.XXXXXX")
trap 'rm -f -- "$tmp"' EXIT
{
  echo "# HELP zcache_wireguard_handshake_age_seconds Seconds since the mesh peer's last WireGuard handshake, +Inf when it has none."
  echo "# TYPE zcache_wireguard_handshake_age_seconds gauge"
  for peer in "${peers[@]}"; do
    latest=${handshake[$peer]:-0}
    if [ "$latest" -gt 0 ]; then age=$((now - latest)); else age=+Inf; fi
    printf 'zcache_wireguard_handshake_age_seconds{peer="%s"} %s\n' "$peer" "$age"
  done
} > "$tmp"
chmod 0644 -- "$tmp"   # mktemp makes 0600; the collector reads as a non-root user
mv -- "$tmp" "$out"
trap - EXIT
