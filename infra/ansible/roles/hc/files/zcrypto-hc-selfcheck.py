#!/usr/bin/env python3
"""The dead-man node's self-check, installed by the `hc` role at /usr/local/sbin/zcrypto-hc-selfcheck.

It pings the node's own check through zcrypto_selfcheck while the clone's web answers its status read. The clone
answers a ping only once it has stored it, so the ping is the write probe.
tests/test_hc_selfcheck.py drives this file.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

try:
    import zcrypto_selfcheck
except ModuleNotFoundError:
    sys.path.append("/usr/local/lib/zcrypto")
    import zcrypto_selfcheck

TIMEOUT_SECONDS = 10


def web_up(status_url: str, host: str, *, opener) -> tuple[bool, str]:
    # The clone refuses a request naming any host but its own with a 400.
    request = urllib.request.Request(status_url, headers={"Host": host})
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            body = response.read().decode().strip()
    except urllib.error.HTTPError as refused:
        return False, f"answered {refused.code}"
    return (True, "answered OK") if body == "OK" else (False, f"answered {body[:60]!r}")


def main(env=os.environ, *, opener=urllib.request.urlopen) -> int:
    # No notifier probe, by the owner's ruling (spec 00122 D8): a dispatch the clone fails is its own ERROR record,
    # which the node's Alloy ships.
    checks = (("web", lambda: web_up(env["HC_SELFCHECK_STATUS"], env["HC_SELFCHECK_HOST"], opener=opener)),)
    return zcrypto_selfcheck.run(checks, env, ping_var="HC_SELFCHECK_HEALTHCHECK_URL", opener=opener)


if __name__ == "__main__":
    sys.exit(main())
