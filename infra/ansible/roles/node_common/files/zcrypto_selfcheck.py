"""The self-check loop a node's script runs over its own probes, installed by the `node_common` role at
/usr/local/lib/zcrypto/zcrypto_selfcheck.py, where the unit's PYTHONPATH finds it.

A rule cannot page the death of the node it runs on, so a node's self-check pings its dead-man check only while
every probe passes. A failing probe sends nothing and the run exits 0: the missing ping is the page.
tests/test_*_selfcheck.py drive this file through each node's script.
"""

from __future__ import annotations

import urllib.request

PING_TIMEOUT_SECONDS = 10


def get(url: str, opener, timeout: float) -> str:
    with opener(urllib.request.Request(url), timeout=timeout) as response:
        return response.read().decode()


def sample(text: str, name: str) -> float | None:
    for line in text.splitlines():
        if line.startswith(name + " "):
            return float(line.split()[1])
    return None


def run(checks, env, *, ping_var: str, opener) -> int:
    healthy, parts = True, []
    for name, check in checks:
        try:
            ok, detail = check()
        except Exception as exc:  # noqa: BLE001 -- an endpoint that cannot be read is the finding, whatever it raised
            ok, detail = False, f"unreadable: {type(exc).__name__}"
        healthy = healthy and ok
        parts.append(f"{name}={'ok' if ok else 'FAIL'} ({detail})")
    url = env.get(ping_var, "")
    if not healthy:
        verdict = "not pinging"
    elif not url:
        verdict = "healthy, and no ping URL is set"
    else:
        try:
            get(url, opener, PING_TIMEOUT_SECONDS)
            verdict = "pinged"
        except Exception as exc:  # noqa: BLE001 -- a ping that fails is reported; the next run sends another
            verdict = f"ping failed: {type(exc).__name__}"
    print(f"selfcheck: {' '.join(parts)} -> {verdict}")
    return 0
