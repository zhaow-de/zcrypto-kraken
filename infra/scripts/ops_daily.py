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
from datetime import datetime, timedelta, timezone
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


LOKI_DS_UID_DEFAULT = "grafanacloud-logs"
HEALTHCHECKS_API = "https://healthchecks.io/api/v3/checks/"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_LOG = REPO_ROOT / "docs/reference/deploy-log.jsonl"


@dataclass
class LogCount:
    host: str
    container: str
    level: str
    count: int


@dataclass
class LogsRead:
    counts: list[LogCount] = field(default_factory=list)
    unreadable: str | None = None


@dataclass
class DeadmenRead:
    via_prometheus: float | None = None
    via_healthchecks: list[dict] = field(default_factory=list)
    unreadable: str | None = None


@dataclass
class Check:
    name: str
    expr: str
    ok: bool
    value: str


def _proxy_query(ds_uid: str, expr: str, token: str, opener) -> list[dict]:
    url = f"{GRAFANA_URL}/api/datasources/proxy/uid/{ds_uid}/api/v1/query?" + urllib.parse.urlencode({"query": expr})
    return _get(url, token, opener)["data"]["result"]


def loki_ds_uid(env: dict | None = None) -> str:
    """By UID, never by type: a Cloud stack ships several Loki datasources, and picking 'the first
    of each type' once silently repointed every rule."""
    import os

    return (env if env is not None else os.environ).get("GRAFANA_LOKI_DS_UID", LOKI_DS_UID_DEFAULT)


def read_logs(token: str, *, window: timedelta, opener=urllib.request.urlopen, env=None) -> LogsRead:
    hours = max(1, int(window.total_seconds() // 3600))
    expr = f'sum by (host, container, level) (count_over_time({{host=~".+", level=~"WARNING|ERROR|CRITICAL"}}[{hours}h]))'
    try:
        result = _proxy_query(loki_ds_uid(env), expr, token, opener)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        return LogsRead(unreadable=f"the log plane could not be read: {exc}")
    counts = [
        LogCount(
            host=(s.get("metric") or {}).get("host", "?"),
            container=(s.get("metric") or {}).get("container", "?"),
            level=(s.get("metric") or {}).get("level", "?"),
            count=int(float(s["value"][1])),
        )
        for s in result
    ]
    return LogsRead(counts=sorted(counts, key=lambda c: -c.count))


def _readonly_key() -> str | None:
    try:
        return grafana_auth.vault_var("healthchecks_readonly_api_key")
    except Exception:
        return None


def read_deadmen(token: str, *, opener=urllib.request.urlopen) -> DeadmenRead:
    read = DeadmenRead()
    try:
        series = _proxy_query(PROM_DS_UID, "max(hc_checks_down_total) or on() vector(999)", token, opener)
        read.via_prometheus = float(series[0]["value"][1]) if series else None
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, IndexError) as exc:
        read.unreadable = f"the dead-man count could not be read through Grafana: {exc}"

    def note(text):
        read.unreadable = f"{read.unreadable}; {text}" if read.unreadable else text

    key = _readonly_key()
    if not key:
        note("healthchecks_readonly_api_key is absent from the vault, so the direct dead-man read did not run")
        return read
    try:
        request = urllib.request.Request(HEALTHCHECKS_API, headers={"X-Api-Key": key})
        with opener(request, timeout=_TIMEOUT) as response:
            read.via_healthchecks = json.load(response).get("checks", [])
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
        note(f"healthchecks.io could not be read directly: {exc}")
    return read


# Presence and freshness, which the alert rules deliberately cannot give -- their absence states are
# `OK` by design, so a vanished series pages nothing. `(no series)` here is a FAIL, never a zero.
VERDICT_CHECKS: tuple[tuple[str, str], ...] = (
    ("capture primary up", 'up{job="capture_app",host="zcrypto"}'),
    ("capture secondary up", 'up{job="capture_app",host="zcrypto-red"}'),
    ("engine cycle age", "time() - zcrypto_engine_cycle_completed_at_seconds"),
    ("gate status present", "zcrypto_gate_status"),
    ("gate streak present", "zcrypto_gate_streak_days"),
    ("exec gate level present", "zcrypto_exec_gate_level"),
    ("reconcile source lag", "max(zcrypto_reconcile_source_lag_seconds)"),
    ("logship drops", "max(zcrypto_logship_dropped_lines_total)"),
)


def read_verdict(token: str, *, opener=urllib.request.urlopen) -> list[Check]:
    checks = []
    for name, expr in VERDICT_CHECKS:
        try:
            series = _proxy_query(PROM_DS_UID, expr, token, opener)
        except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError) as exc:
            checks.append(Check(name, expr, ok=False, value=f"unreadable: {exc}"))
            continue
        checks.append(
            Check(name, expr, ok=True, value=str(series[0]["value"][1]))
            if series
            else Check(name, expr, ok=False, value="(no series)")
        )
    return checks


def read_deploys(window: timedelta, *, now: datetime, path: Path | None = None) -> list[dict]:
    log = path or DEPLOY_LOG
    if not log.exists():
        return []
    start = now - window
    out = []
    for line in log.read_text().splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            stamp = datetime.strptime(record["ts"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError, KeyError:
            continue
        if stamp >= start:
            out.append(record)
    return out


@dataclass
class Report:
    now: datetime
    window: timedelta
    alerts: AlertsRead
    logs: LogsRead
    deadmen: DeadmenRead
    verdict: list[Check]
    deploys: list[dict]

    @property
    def unreadable(self) -> list[str]:
        return [n for n in (self.alerts.unreadable, self.logs.unreadable, self.deadmen.unreadable) if n]

    @property
    def exit_code(self) -> int:
        """2 outranks 1: a partial read reported as mere attention hides that something was not seen."""
        if self.unreadable:
            return 2
        if self.alerts.firing_now or [c for c in self.verdict if not c.ok] or (self.deadmen.via_prometheus or 0) > 0:
            return 1
        return 0

    @property
    def verdict_word(self) -> str:
        return "all-clear" if self.exit_code == 0 else "attention"

    def markdown(self) -> str:
        hours = int(self.window.total_seconds() // 3600)
        out = [f"# Daily pass — {self.now:%Y-%m-%d %H:%MZ} (window {hours} h)", ""]
        out.append(f"**Verdict: {self.verdict_word}** (exit {self.exit_code})")
        if self.unreadable:
            out += ["", "## Sources that could not be read"] + [f"- {n}" for n in self.unreadable]
        out += ["", "## Alerts firing"]
        out += [f"- `{a.uid}` on {a.host or '?'} — {a.runbook or 'NO RUNBOOK'}" for a in self.alerts.firing_now] or ["- none"]
        out += ["", "## Fleet checks"] + [f"- {'PASS' if c.ok else 'FAIL'} {c.name}: {c.value}" for c in self.verdict]
        out += ["", "## Logs"] + ([f"- {c.host}/{c.container} {c.level}: {c.count}" for c in self.logs.counts[:10]] or ["- none"])
        out += [
            "",
            "## Dead-men",
            f"- via Grafana: {self.deadmen.via_prometheus}",
            f"- direct: {len(self.deadmen.via_healthchecks)} checks read",
        ]
        out += ["", "## Deploys in window"] + (
            [f"- {d.get('ts')} {d.get('playbook')} --limit {d.get('limit')}" for d in self.deploys] or ["- none"]
        )
        return "\n".join(out)

    def journal_paragraph(self) -> str:
        fired = ", ".join(f"`{a.uid}`" for a in self.alerts.firing_now) or "none"
        failed = ", ".join(c.name for c in self.verdict if not c.ok) or "all pass"
        errors = sum(c.count for c in self.logs.counts if c.level in ("ERROR", "CRITICAL"))
        deploys = ", ".join(str(d.get("limit")) for d in self.deploys) or "none"
        hours = int(self.window.total_seconds() // 3600)
        return (
            f"window {hours} h to {self.now:%Y-%m-%d %H:%MZ} · alerts {fired} · checks {failed} · "
            f"logs {errors} ERROR/CRITICAL lines · dead-men {self.deadmen.via_prometheus} down via Grafana, "
            f"{len(self.deadmen.via_healthchecks)} read directly · deploys {deploys} · "
            f"actions none · follow-ups none"
        )


def build_report(*, alerts, logs, deadmen, verdict, deploys, now, window=timedelta(hours=24)) -> Report:
    return Report(now=now, window=window, alerts=alerts, logs=logs, deadmen=deadmen, verdict=verdict, deploys=deploys)


def _parse_since(text: str) -> timedelta:
    return {"h": timedelta(hours=int(text[:-1])), "d": timedelta(days=int(text[:-1]))}[text[-1]]


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "report":
        print("usage: ops-daily.py report [--since 24h] [--journal-entry]")
        return 2
    window = _parse_since(argv[argv.index("--since") + 1]) if "--since" in argv else timedelta(hours=24)
    now = datetime.now(timezone.utc)
    token = grafana_auth.vault_var("grafana_sa_token")
    report = build_report(
        alerts=read_alerts(token, now=now, window=window),
        logs=read_logs(token, window=window),
        deadmen=read_deadmen(token),
        verdict=read_verdict(token),
        deploys=read_deploys(window, now=now),
        now=now,
        window=window,
    )
    print(report.journal_paragraph() if "--journal-entry" in argv else report.markdown())
    return report.exit_code
