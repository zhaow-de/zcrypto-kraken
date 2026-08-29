"""The daily operations pass's instrument: reads the fleet, never writes to it.

Its exit code is the pass's headline -- 0 all-clear, 1 attention, 2 a source it could not read --
because a source that cannot be reached is a finding ABOUT that source, never a silent gap.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


def _load_sibling(name: str):
    """Import a sibling script by path.

    `sys.modules` registration is load-bearing, not tidiness: a `@dataclass` in a module loaded by
    path raises `AttributeError: 'NoneType' object has no attribute '__dict__'` without it, because
    dataclasses resolves `cls.__module__` through `sys.modules`.
    """
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


grafana_auth = _load_sibling("grafana_auth")
GRAFANA_URL = grafana_auth.GRAFANA_URL

PROM_DS_UID = "grafanacloud-prom"
_RUNBOOK_LINK = re.compile(r"infra/runbooks/([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)")
_TIMEOUT = 30

# The history API pages. A chunk returning AT the limit may have dropped transitions, and a report
# that shows the survivors reads as a quiet day -- so chunks stay narrow and the count is checked.
HISTORY_CHUNK = timedelta(hours=6)
HISTORY_PAGE_LIMIT = 5000

# These rules aggregate the host away in their own expr (`count(up{host="ops"}) or on() vector(0)`),
# so the firing instance carries only `severity`. Without this map the pass cannot tell an Alloy
# restart that is routine on ops from the same restart on the capture pair, which is attended.
_UID_HOST = {
    "zcrypto-alloy-dark-ops": "ops",
    "zcrypto-alloy-dark-nas": "nas",
    "zcrypto-alloy-dark-zaccess": "zaccess",
    "zcrypto-alloy-dark-capture-primary": "zcrypto",
    "zcrypto-alloy-dark-capture-secondary": "zcrypto-red",
}


@dataclass(frozen=True)
class Alert:
    uid: str
    title: str
    state: str
    active_at: str | None
    runbook: str | None
    host: str | None


@dataclass
class AlertsRead:
    firing_now: list[Alert] = field(default_factory=list)
    fired_in_window: list[Alert] = field(default_factory=list)
    unreadable: str | None = None


def _get(url: str, token: str, opener) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with opener(request, timeout=_TIMEOUT) as response:
        return json.load(response)


def _host_of(uid: str, instance: dict) -> str | None:
    labels = instance.get("labels") or {}
    return labels.get("host") or _UID_HOST.get(uid)


def read_alerts(token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen) -> AlertsRead:
    read = AlertsRead()
    try:
        payload = _get(f"{GRAFANA_URL}/api/prometheus/grafana/api/v1/rules", token, opener)
        for group in payload["data"]["groups"]:
            for rule in group.get("rules", []):
                uid = rule.get("uid")
                if not uid:
                    return AlertsRead(unreadable=f"a rule arrived with no uid ({rule.get('name', '?')!r}) -- the API shape changed")
                instances = rule.get("alerts") or [{}]
                summary = (rule.get("annotations") or {}).get("summary") or ""
                link = _RUNBOOK_LINK.search(summary)
                if rule.get("state") == "firing":
                    read.firing_now.append(
                        Alert(
                            uid=uid,
                            title=rule.get("name", ""),
                            state="firing",
                            active_at=instances[0].get("activeAt"),
                            runbook=link.group(0) if link else None,
                            host=_host_of(uid, instances[0]),
                        )
                    )
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        return AlertsRead(unreadable=f"the rules API could not be read: {exc}")

    fired = {a.uid: a for a in read.firing_now}
    chunk_start = now - window
    try:
        while chunk_start < now:
            chunk_end = min(chunk_start + HISTORY_CHUNK, now)
            url = f"{GRAFANA_URL}/api/v1/rules/history?" + urllib.parse.urlencode(
                {"from": int(chunk_start.timestamp()), "to": int(chunk_end.timestamp()), "limit": HISTORY_PAGE_LIMIT}
            )
            rows = (_get(url, token, opener).get("data") or {}).get("values") or []
            if rows and len(rows[0]) >= HISTORY_PAGE_LIMIT:
                read.unreadable = (
                    f"the alert-state history hit the page limit ({HISTORY_PAGE_LIMIT}) in "
                    f"{chunk_start:%Y-%m-%dT%H:%MZ}..{chunk_end:%Y-%m-%dT%H:%MZ}: transitions may be missing"
                )
                break
            chunk_start = chunk_end
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        read.unreadable = f"the alert-state history could not be read: {exc}"
    read.fired_in_window = list(fired.values())
    return read
