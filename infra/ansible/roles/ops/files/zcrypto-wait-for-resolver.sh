#!/bin/sh
# Installed by the `ops` role at /usr/local/sbin/zcrypto-wait-for-resolver; docker.service runs it as
# ExecStartPre (docker-wait-for-resolver.conf beside this file). It exits 0 at its bound as well:
# docker up without a resolver beats docker not up.
set -eu

usage="usage: zcrypto-wait-for-resolver <resolv.conf> <seconds>"
conf=${1:-}
bound=${2:-}
[ -n "$conf" ] && [ -n "$bound" ] || { echo "$usage" >&2; exit 2; }

waited=0
until grep -q '^nameserver[[:space:]]' "$conf" 2>/dev/null; do
  if [ "$waited" -ge "$bound" ]; then
    echo "zcrypto-wait-for-resolver: no nameserver in $conf after $bound s; docker starts without a resolver" >&2
    exit 0
  fi
  sleep 1
  waited=$((waited + 1))
done
