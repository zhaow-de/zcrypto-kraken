#!/usr/bin/env python3
"""The observability node's self-check, installed by the `mon` role at /usr/local/sbin/zcrypto-mon-selfcheck.

A rule cannot page the death of the node it runs on, so this pings the node's dead-man check only while the node
does its job: Grafana's rule scheduler is ticking, a fleet host's sample is fresh in Prometheus, and Loki answers
ready. A failing check sends nothing and exits 0: the missing ping is the page.
tests/test_mon_selfcheck.py drives this file.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import zcrypto_selfcheck

TICK = "grafana_alerting_ticker_last_consumed_tick_timestamp_seconds"
SCHEDULED = "grafana_alerting_schedule_alert_rules"
# The scheduler ticks every ten seconds, so a minute without one is six missed.
TICK_MAX_AGE_SECONDS = 60
# An instant query reaches back five minutes, so this counts the fleet hosts with a sample at most that old.
FLEET_QUERY = 'count(count by (host) (up{host!="zcrypto-mon"}))'
TIMEOUT_SECONDS = 10


def rules_fresh(base: str, *, opener, now: float) -> tuple[bool, str]:
    text = zcrypto_selfcheck.get(f"{base}/metrics", opener, TIMEOUT_SECONDS)
    tick, scheduled = zcrypto_selfcheck.sample(text, TICK), zcrypto_selfcheck.sample(text, SCHEDULED)
    if tick is None or scheduled is None:
        return False, f"Grafana's /metrics carries no {TICK if tick is None else SCHEDULED}"
    age = now - tick
    if scheduled < 1:
        return False, "no rule is scheduled"
    if age > TICK_MAX_AGE_SECONDS:
        return False, f"the scheduler's last tick is {age:.0f} s old"
    return True, f"{scheduled:.0f} rules scheduled, last tick {age:.0f} s ago"


def fleet_fresh(base: str, *, opener) -> tuple[bool, str]:
    reply = json.loads(
        zcrypto_selfcheck.get(f"{base}/api/v1/query?" + urllib.parse.urlencode({"query": FLEET_QUERY}), opener, TIMEOUT_SECONDS)
    )
    result = reply["data"]["result"]
    hosts = int(float(result[0]["value"][1])) if result else 0
    if hosts < 1:
        return False, "no fleet host has a sample in the last five minutes"
    return True, f"{hosts} fleet hosts shipping"


def loki_ready(base: str, *, opener) -> tuple[bool, str]:
    try:
        body = zcrypto_selfcheck.get(f"{base}/ready", opener, TIMEOUT_SECONDS).strip()
    except urllib.error.HTTPError as refused:
        # Loki answers a not-ready ingester with a 503 whose body is the reason.
        return False, f"answered {refused.code}: {refused.read().decode().strip()[:60]!r}"
    return (True, "ready") if body == "ready" else (False, f"answered {body[:60]!r}")


def main(env=os.environ, *, opener=urllib.request.urlopen, now=time.time) -> int:
    checks = (
        ("rules", lambda: rules_fresh(env["MON_SELFCHECK_GRAFANA"], opener=opener, now=now())),
        ("fleet", lambda: fleet_fresh(env["MON_SELFCHECK_PROMETHEUS"], opener=opener)),
        ("loki", lambda: loki_ready(env["MON_SELFCHECK_LOKI"], opener=opener)),
    )
    return zcrypto_selfcheck.run(checks, env, ping_var="MON_SELFCHECK_HEALTHCHECK_URL", opener=opener, now=now)


if __name__ == "__main__":
    sys.exit(main())
