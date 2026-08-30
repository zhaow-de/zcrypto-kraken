"""The daily operations pass's instrument: reads the fleet, never writes to it.

Its exit code is the pass's headline -- 0 all-clear, 1 attention, 2 a source it could not read --
because a source that cannot be reached is a finding ABOUT that source, never a silent gap.
"""

from __future__ import annotations

import calendar
import http.client
import importlib.util
import json
import re
import sys
import traceback
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from enum import Enum
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
# What "the source could not be read" actually looks like against a live endpoint. `URLError` alone
# is not enough: urllib wraps OSError only around the REQUEST, so a timeout, a reset or a truncated
# body during `getresponse()` or the read escapes uncaught -- and the pass dies at 03:00 with a
# traceback and exit 1, which is the ATTENTION code, exactly inverting the module's contract that an
# unreachable source is a finding about that source. `URLError` and `HTTPError` are `OSError`
# subclasses, so naming `OSError` covers them too; `HTTPException` carries `IncompleteRead` and
# `RemoteDisconnected`. No fixture produces any of these -- only a real network does.
_UNREACHABLE = (OSError, http.client.HTTPException, KeyError, ValueError, IndexError)

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


def _history_transitions(payload: dict):
    """(timestamp_ms, line) per state transition.

    Measured against the live API 2026-08-29: the frame carries three columns named by
    `schema.fields` -- `time`, `line`, `labels` -- and the RULE IDENTITY is in `line`
    (`ruleUID`, `ruleTitle`), never in `labels`, which holds only the ingest's own metadata.
    """
    columns = (payload.get("data") or {}).get("values") or []
    names = [f.get("name") for f in ((payload.get("schema") or {}).get("fields") or [])]
    if len(columns) < 2:
        return
    t_idx = names.index("time") if "time" in names else 0
    l_idx = names.index("line") if "line" in names else 1
    for stamp, line in zip(columns[t_idx], columns[l_idx]):
        # `stamp` is type-checked for the same reason `line` is, and it is the more dangerous of the
        # two: if the frame ever drops its `time` field, `t_idx` falls back to 0 and lands on the
        # SAME column as `line`, so the isinstance below passes and `stamp / 1000` divides a dict.
        # `TypeError` is deliberately outside `_UNREACHABLE`, so that raise would take the whole
        # pass down -- no report, exit 1 -- for a frame it could not read.
        if isinstance(line, dict) and isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
            yield stamp, line


def _host_of(uid: str, instance: dict) -> str | None:
    labels = instance.get("labels") or {}
    return labels.get("host") or _UID_HOST.get(uid)


def read_alerts(token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen) -> AlertsRead:
    read = AlertsRead()
    rule_links: dict[str, str | None] = {}
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
                rule_links[uid] = link.group(0) if link else None
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
    except _UNREACHABLE as exc:
        return AlertsRead(unreadable=f"the rules API could not be read: {exc}")

    fired = {a.uid: a for a in read.firing_now}
    chunk_start = now - window
    try:
        while chunk_start < now:
            chunk_end = min(chunk_start + HISTORY_CHUNK, now)
            url = f"{GRAFANA_URL}/api/v1/rules/history?" + urllib.parse.urlencode(
                {"from": int(chunk_start.timestamp()), "to": int(chunk_end.timestamp()), "limit": HISTORY_PAGE_LIMIT}
            )
            payload = _get(url, token, opener)
            rows = (payload.get("data") or {}).get("values") or []
            for stamp, line in _history_transitions(payload):
                if (line.get("current") or "") != "Alerting":
                    continue
                uid = line.get("ruleUID")
                if not uid or uid in fired:
                    continue
                fired[uid] = Alert(
                    uid=uid,
                    title=line.get("ruleTitle", ""),
                    state="fired-in-window",
                    active_at=datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat(),
                    runbook=rule_links.get(uid),
                    host=_UID_HOST.get(uid),
                )
            if rows and len(rows[0]) >= HISTORY_PAGE_LIMIT:
                read.unreadable = (
                    f"the alert-state history hit the page limit ({HISTORY_PAGE_LIMIT}) in "
                    f"{chunk_start:%Y-%m-%dT%H:%MZ}..{chunk_end:%Y-%m-%dT%H:%MZ}: transitions may be missing"
                )
                break
            chunk_start = chunk_end
    except _UNREACHABLE as exc:
        read.unreadable = f"the alert-state history could not be read: {exc}"
    read.fired_in_window = list(fired.values())
    return read


LOKI_DS_UID_DEFAULT = "grafanacloud-logs"
HEALTHCHECKS_API = "https://healthchecks.io/api/v3/checks/"
REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_LOG = REPO_ROOT / "docs/reference/deploy-log.jsonl"
REGISTER = REPO_ROOT / "docs/reference/kraken-snapshot-register.md"
# A row of the register's `## Re-confirmation log` table: first cell `#<n> (...)`, second cell the
# ISO stamp. The heading gate in `last_sweep_date` is defensive, not a report on what the register
# currently holds: a dated row under any other heading must never become the answer, whether or not
# one exists there yet.
_LOG_ROW = re.compile(r"^\| #\d+[^|]*\|\s*(\d{4}-\d{2}-\d{2})T")


def last_sweep_date(register: Path) -> date | None:
    """The `Fetched at` date of the LAST row under `## Re-confirmation log`, or None when no row parses."""
    found = None
    in_log = False
    for line in register.read_text().splitlines():
        if line.startswith("## "):
            in_log = line.startswith("## Re-confirmation log")
            continue
        row = _LOG_ROW.match(line) if in_log else None
        if row:
            found = date.fromisoformat(row.group(1))
    return found


def _a_month_after(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


HEALABLE_COUNTER = "zcrypto_reconcile_healable_gap_seconds_total"
REFDATA_RUNBOOK = "infra/runbooks/reference-data.md#refdata-sweep-due"
HEALABLE_RUNBOOK = "infra/runbooks/ops.md#healable-threshold-rederivation-due"


@dataclass(frozen=True)
class Reminder:
    name: str
    status: str
    owed: bool
    runbook: str


@dataclass
class RemindersRead:
    reminders: list[Reminder] = field(default_factory=list)
    unreadable: str | None = None


def read_reminders(
    token: str, *, now: datetime, window: timedelta, opener=urllib.request.urlopen, register: Path = REGISTER
) -> RemindersRead:
    """Due-ness computed from state the pass can read, so a Slack reminder that never arrives costs
    nothing (spec 00107 D1). Each reminder comes from the source that actually knows: the sweep from
    the register's last re-confirmation row plus the monthly cadence; the healable re-derivation from
    whether its counter moved in the window -- the qualifying-day COUNT comes from the ledger, which
    the runbook cited here names as the arbiter and which Grafana Cloud cannot see, so this pure-HTTP
    instrument does not reach it.

    An owed reminder reports and never blocks; a source that could not be read is `unreadable`, like
    every other read here.
    """
    read = RemindersRead()

    def note(text):
        read.unreadable = f"{read.unreadable}; {text}" if read.unreadable else text

    try:
        last = last_sweep_date(register)
    except _UNREACHABLE as exc:
        note(f"the snapshot register could not be read: {exc}")
    else:
        if last is None:
            note(f"no dated row under `## Re-confirmation log` in {register.name}")
        else:
            days = (_a_month_after(last) - now.date()).days
            status = f"due in {days} days" if days >= 0 else f"OVERDUE by {-days} days"
            read.reminders.append(
                Reminder("refdata sweep", f"{status} (last sweep {last.isoformat()})", owed=days <= 0, runbook=REFDATA_RUNBOOK)
            )

    hours = max(1, int(window.total_seconds() // 3600))
    try:
        series = _proxy_query(PROM_DS_UID, f"sum(increase({HEALABLE_COUNTER}[{hours}h]))", token, opener)
        resets = _proxy_query(PROM_DS_UID, f"sum(resets({HEALABLE_COUNTER}[{hours}h]))", token, opener)
        if not series or not resets:
            note("the healable counter returned no series, so the re-derivation reminder could not be evaluated")
            return read
        moved = float(series[0]["value"][1])
        reset = float(resets[0]["value"][1]) > 0
    except _UNREACHABLE as exc:
        note(f"the healable counter could not be read: {exc}")
        return read
    if reset:
        # A counter summed from an append-only ledger CAN DECREASE when a record is corrected or the
        # ledger is rebuilt -- a correction that raises the total resets nothing -- and `increase()`
        # then reports the whole post-reset value as movement (`T0044`, resolved, records the
        # correction it was opened on). The `zcrypto-reconcile-healable-gap-rate` rule guards the
        # same window with `resets()`; this mirrors it, and the number is deliberately not quoted --
        # the ledger's own count is the arbiter.
        owed = True
        status = f"counter reset in {hours} h (a ledger correction or rebuild), so its movement says nothing -- recount the qualifying days from the ledger"
    else:
        owed = moved > 0
        # `increase()` extrapolates to the range boundaries, so this figure is NOT the ledger's
        # delta -- and the ledger is the arbiter the runbook names, precisely because Cloud cannot
        # answer the question. Quote it as the approximation it is (spec 00107 D3).
        status = (
            f"counter moved ~+{moved:.1f} s in {hours} h (scraped, extrapolated -- not the ledger's), recount the qualifying days"
            if owed
            else f"counter unchanged in {hours} h"
        )
    read.reminders.append(Reminder("healable re-derivation", status, owed=owed, runbook=HEALABLE_RUNBOOK))
    return read


RUNBOOKS = REPO_ROOT / "infra/runbooks"
# A link the prefix introduces, not any path the description happens to mention: an unprefixed
# mention that resolves would otherwise pass a description whose actual link is dead. The prefix is
# the LOOSE half deliberately -- it marks a citation and is not a formatting rule, so any case and
# any run of whitespace (a newline included) after the colon still names a link an operator can
# follow, while `_RUNBOOK_LINK` keeps the path exact. Tightening it back reports descriptions whose
# links work, and this check cannot repair what it reports. The link is wrapped in a group so a
# finding can quote it verbatim; `_RUNBOOK_LINK`'s own file and anchor groups sit one number further
# along, and it is composed rather than respelled so the two cannot drift apart.
_RUNBOOK_CITED = re.compile(r"(?i:Runbook:)\s*(" + _RUNBOOK_LINK.pattern + ")")
# The vocabulary `.claude/rules/operator-facing-text.md` bans from any surface read without the repo
# open, spelled wider than that rule spells it wherever hand-written prose varies: either separator
# after the phase word, an optional backtick around a serial. The bare decision number the rule also
# bans is deliberately absent -- this check detects and cannot repair, so a false positive is a
# finding line in every daily report until a human edits a description that was never wrong, and a
# two-character token is the alternation that would mint them.
_INTERNAL_TOKEN = re.compile(r"\bPhase[ -]\d|\bT\d{4}\b|\biter-\d+|\bspec\s+`?\d{5}|\bWP\d")


def check_descriptions(checks: list[dict], runbooks: Path = RUNBOOKS) -> list[str]:
    """One line per defect in a dead-man check's description, named per check (spec 00107 D5).

    The descriptions are hand-written in healthchecks.io, outside the reach of every repo test, and
    are read from a phone with nothing open. Two assertions each: at least one
    `Runbook: infra/runbooks/<file>#<anchor>` citation -- the prefix is part of the shape the finding
    quotes back -- EVERY one of them resolving against a real `<a name=…>` tag in the file it names,
    and no internal token.
    Detects, never repairs -- the descriptions live in the SaaS, so a finding is a line for a human.
    """
    out = []
    for check in checks:
        name = check.get("name") or check.get("slug") or "?"
        desc = check.get("desc") or ""
        links = list(_RUNBOOK_CITED.finditer(desc))
        if not links:
            out.append(f"`{name}`: no `Runbook: infra/runbooks/<file>#<anchor>` in its description")
        for link in links:
            path = runbooks / link.group(2)
            if not path.exists() or f'<a name="{link.group(3)}"></a>' not in path.read_text():
                out.append(f"`{name}`: its runbook link {link.group(1)} resolves to no anchor")
        for token in _INTERNAL_TOKEN.findall(desc):
            out.append(f"`{name}`: its description carries the internal token {token!r}")
    return out


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
    # Three states, not two: `None` is "the check did not run" (healthchecks unreadable, or the
    # runbooks were), `[]` is "ran, found nothing". Defaulting to `[]` would print the all-clear
    # description line under a report that never looked.
    description_findings: list[str] | None = None
    unreadable: str | None = None


@dataclass
class Check:
    name: str
    expr: str
    ok: bool
    value: str


# Loki and Prometheus answer under DIFFERENT paths behind the same datasource proxy, and the
# difference is not cosmetic: Loki 404s on Prometheus's `/api/v1/query`. The path is a parameter so
# each caller states which API it is talking to rather than inheriting a default that is right for
# only one of them.
_PROM_QUERY_PATH = "/api/v1/query"
_LOKI_QUERY_PATH = "/loki/api/v1/query"


def _proxy_query(ds_uid: str, expr: str, token: str, opener, api_path: str = _PROM_QUERY_PATH) -> list[dict]:
    url = f"{GRAFANA_URL}/api/datasources/proxy/uid/{ds_uid}{api_path}?" + urllib.parse.urlencode({"query": expr})
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
        result = _proxy_query(loki_ds_uid(env), expr, token, opener, api_path=_LOKI_QUERY_PATH)
        counts = _log_counts(result)
    except _UNREACHABLE as exc:
        return LogsRead(unreadable=f"the log plane could not be read: {exc}")
    return LogsRead(counts=sorted(counts, key=lambda c: -c.count))


def _log_counts(result) -> list[LogCount]:
    return [
        LogCount(
            host=(s.get("metric") or {}).get("host", "?"),
            container=(s.get("metric") or {}).get("container", "?"),
            level=(s.get("metric") or {}).get("level", "?"),
            count=int(float(s["value"][1])),
        )
        for s in result
    ]


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
    except _UNREACHABLE as exc:
        read.unreadable = f"the dead-man count could not be read through Grafana: {exc}"

    def note(text):
        read.unreadable = f"{read.unreadable}; {text}" if read.unreadable else text

    key = _readonly_key()
    if not key:
        note("healthchecks_readonly_api_key could not be read from the vault, so the direct dead-man read did not run")
        return read
    try:
        request = urllib.request.Request(HEALTHCHECKS_API, headers={"X-Api-Key": key})
        with opener(request, timeout=_TIMEOUT) as response:
            read.via_healthchecks = json.load(response).get("checks", [])
    except _UNREACHABLE as exc:
        note(f"healthchecks.io could not be read directly: {exc}")
        return read
    # The check reads runbook FILES, so it gets its own `try` and its own note: inside the
    # healthchecks `try`, an `OSError` from a runbook would be reported as healthchecks.io unreadable.
    try:
        read.description_findings = check_descriptions(read.via_healthchecks)
    # `AttributeError` beside `_UNREACHABLE`: this is the module's first content-dependent parse of
    # the healthchecks payload, and a `checks` element that is not an object would otherwise
    # traceback out at exit 1 -- ATTENTION, the inverted contract this module's docstring names.
    except (*_UNREACHABLE, AttributeError) as exc:
        note(f"the dead-man descriptions could not be checked (the runbooks are read here): {exc}")
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
        # The PARSE is inside the guard too: a 200 whose shape changed raises `KeyError` out here,
        # and an uncaught raise leaves the pass at exit 1 -- attention -- for a source it could not
        # read. A body it cannot understand is the same finding as a body it cannot fetch.
        try:
            series = _proxy_query(PROM_DS_UID, expr, token, opener)
            check = (
                Check(name, expr, ok=True, value=str(series[0]["value"][1]))
                if series
                else Check(name, expr, ok=False, value="(no series)")
            )
        except _UNREACHABLE as exc:
            check = Check(name, expr, ok=False, value=f"unreadable: {exc}")
        checks.append(check)
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
    reminders: RemindersRead

    @property
    def unreadable(self) -> list[str]:
        """Every source that could not be read -- the verdict checks and the reminders included.

        The verdict read reports through its checks rather than an `unreadable` field, so a timeout
        on it alone used to leave the pass at exit 1, ATTENTION: a Grafana it could not reach,
        reported as something wrong with the FLEET. The `unreadable:` prefix is written by
        `read_verdict` for exactly this case and is the only value that carries it.
        """
        named = [n for n in (self.alerts.unreadable, self.logs.unreadable, self.deadmen.unreadable, self.reminders.unreadable) if n]
        return named + [
            f"{c.name} could not be read: {c.value.removeprefix('unreadable: ')}"
            for c in self.verdict
            if c.value.startswith("unreadable:")
        ]

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
        # The `is not None` is the whole point of the three states: without it the all-clear line
        # prints beside `## Sources that could not be read` on a run where the check never ran.
        if self.deadmen.description_findings:
            out += [f"- description: {f}" for f in self.deadmen.description_findings]
        elif self.deadmen.description_findings is not None and self.deadmen.via_healthchecks:
            out.append(
                f"- descriptions: all {len(self.deadmen.via_healthchecks)} carry a resolving runbook link and no internal token"
            )
        out += ["", "## Reminders"] + (
            [f"- {'OWED' if r.owed else 'ok'} {r.name}: {r.status} — {r.runbook}" for r in self.reminders.reminders]
            or ["- none read"]
        )
        out += ["", "## Deploys in window"] + (
            [f"- {d.get('ts')} {d.get('playbook')} --limit {d.get('limit')}" for d in self.deploys] or ["- none"]
        )
        return "\n".join(out)

    def journal_paragraph(self) -> str:
        fired = ", ".join(f"`{a.uid}`" for a in self.alerts.firing_now) or "none"
        failed = ", ".join(c.name for c in self.verdict if not c.ok) or "all pass"
        errors = sum(c.count for c in self.logs.counts if c.level in ("ERROR", "CRITICAL"))
        # WARNING is carried too, and only when there is some. A healthy fleet produces no
        # ERROR/CRITICAL for weeks, so a paragraph counting only those records "0" every day and the
        # journal says nothing -- which is what happened on the first real pass, whose ONLY finding
        # was 1802 WARNING lines the paragraph dropped. Omitted when zero so a silent day stays short.
        warnings = sum(c.count for c in self.logs.counts if c.level == "WARNING")
        # A description finding moves no exit code (spec 00107 D5 -- the check detects and cannot
        # repair), so this clause is the only trace it leaves in the artefact that gets pasted.
        findings = len(self.deadmen.description_findings or [])
        # The OWED marker travels with the clause. The paragraph is the artefact that gets pasted
        # into the journal, and `refdata sweep: due in 0 days` -- the owed-today spelling -- skims
        # as "not yet" without it, where the markdown's own line is unambiguous.
        reminders = ", ".join(f"{'OWED ' if r.owed else ''}{r.name}: {r.status}" for r in self.reminders.reminders) or "none read"
        deploys = ", ".join(str(d.get("limit")) for d in self.deploys) or "none"
        hours = int(self.window.total_seconds() // 3600)
        return (
            f"window {hours} h to {self.now:%Y-%m-%d %H:%MZ} · alerts {fired} · checks {failed} · "
            f"logs {errors} ERROR/CRITICAL lines{f', {warnings} WARNING' if warnings else ''} · "
            f"dead-men {self.deadmen.via_prometheus} down via Grafana, "
            f"{len(self.deadmen.via_healthchecks)} read directly{f', {findings} description finding{"s" if findings != 1 else ""}' if findings else ''} · deploys {deploys} · "
            f"reminders {reminders} · "
            f"actions none · follow-ups none"
        )


def build_report(*, alerts, logs, deadmen, verdict, deploys, reminders, now, window=timedelta(hours=24)) -> Report:
    return Report(
        now=now, window=window, alerts=alerts, logs=logs, deadmen=deadmen, verdict=verdict, deploys=deploys, reminders=reminders
    )


def _parse_since(text: str) -> timedelta:
    return {"h": timedelta(hours=int(text[:-1])), "d": timedelta(days=int(text[:-1]))}[text[-1]]


def main(argv: list[str]) -> int:
    if argv and argv[0] == "classify":
        rest = argv[1:]
        host = None
        if "--host" in rest:
            i = rest.index("--host")
            host = rest[i + 1]
            rest = rest[:i] + rest[i + 2 :]
        if not rest:
            print('usage: ops-daily.py classify --host <host> "<command>"')
            return 2
        tier = classify_action(" ".join(rest), host=host)
        print(tier.value)
        return 0 if tier is Tier.AUTONOMOUS else 3
    if not argv or argv[0] != "report":
        print('usage: ops-daily.py report [--since 24h] [--journal-entry]\n       ops-daily.py classify --host <host> "<command>"')
        return 2
    try:
        window = _parse_since(argv[argv.index("--since") + 1]) if "--since" in argv else timedelta(hours=24)
    except (KeyError, ValueError, IndexError) as exc:
        print(f"--since takes a count and h or d, like 24h or 3d: {exc}")
        return 2
    now = datetime.now(timezone.utc)
    # The vault is a SOURCE like any other. A locked GPG agent raises `CalledProcessError`, which is
    # a `SubprocessError` and NOT an `OSError`, so `_UNREACHABLE` does not cover it -- and uncaught
    # it exits 1, the attention code, for a credential the pass could not read.
    try:
        token = grafana_auth.vault_var("grafana_sa_token")
    except Exception as exc:
        # The catch is deliberately broad -- `vault_var` fails across six unrelated hierarchies and a
        # narrow tuple would be guaranteed incomplete -- so keep the traceback for the case where
        # this is a real bug rather than a locked agent. stderr, so stdout stays valid markdown.
        traceback.print_exc(file=sys.stderr)
        print(
            f"# Daily pass\n\n**Verdict: attention** (exit 2)\n\n## Sources that could not be read\n- the vault could not be read, so no source was queried: {type(exc).__name__}: {exc}"
        )
        return 2
    report = build_report(
        alerts=read_alerts(token, now=now, window=window),
        logs=read_logs(token, window=window),
        deadmen=read_deadmen(token),
        verdict=read_verdict(token),
        deploys=read_deploys(window, now=now),
        reminders=read_reminders(token, now=now, window=window),
        now=now,
        window=window,
    )
    print(report.journal_paragraph() if "--journal-entry" in argv else report.markdown())
    return report.exit_code


class Tier(Enum):
    """Which authority an action needs. `PREPARED` means prepare it and stop."""

    AUTONOMOUS = "autonomous"
    PREPARED = "prepared"


# Default-deny. A command is AUTONOMOUS only when it matches one of the shapes enumerated below,
# and PREPARED otherwise. Three parser generations tried the opposite -- admit a head, then prove
# its arguments harmless -- and each shipped a fresh escape: shell composition, then attached and
# combined flags, then the operator spellings `|&` and `&>` beside `sort -o FILE` and
# `uniq IN OUT`. Those last two are the proof the approach was wrong: they write through an operand
# that is a filename BY POSITION, so no flag allowlist can ever catch them. Enumerating the
# permitted commands is the only side of the list with a finite length. A shape the runbooks need
# and this table lacks costs one PREPARED step; a shape it admits by accident costs the capture pair.

# Value classes. None may contain a shell metacharacter, so no hole can carry a command out of the
# shape that vouched for it -- the property `_METACHARS` enforces once for the whole string.
# No `*`: a container name is never a glob, and a glob names what a filter cannot check --
# the shape of the defect that reached the secret files through `cat <dir>/*`.
_NAME = r"[A-Za-z0-9][A-Za-z0-9._@:-]{0,63}"
_UNIT = r"[A-Za-z0-9][A-Za-z0-9._@*-]{0,63}"
# `systemctl list-timers 'zcrypto-*'` needs the glob; `systemctl restart 'zcrypto-*'` would be a
# mass restart from one token, so the MUTATING shapes take the exact spelling only.
_UNIT_EXACT = r"[A-Za-z0-9][A-Za-z0-9._@-]{0,63}"
_PATH = r"/[A-Za-z0-9._/*+-]{0,160}"
_FILEREF = r"[A-Za-z0-9._/*+-]{1,160}"
_SINCE = r"-?\d{1,4}[smhd]?|-?\d{4}-\d{2}-\d{2}(?:[ T]\d{2}:\d{2}(?::\d{2})?)?"
_INT = r"\d{1,6}"
_SINT = r"[-+]?\d{1,6}"
_URL = r"https?://[A-Za-z0-9._~:/?#@!%+,=-]{1,200}"
# A flag VALUE that is a literal string: the scanner has already refused every metacharacter that
# was active where it stood, so what survives cannot leave the shape that vouched for it. Operand
# classes stay narrow regardless -- an operand is where a filename lands.
_QUOTED = r"[^\n]{0,240}"
_PATTERN = r"[^\n]{0,240}"
_MATCHEXPR = r"[A-Z_]{1,32}=[A-Za-z0-9._@/-]{1,64}"
_DATEFMT = r"\+[%A-Za-z:._-]{1,24}"

# Every character that lets one command become two, or a word become a command. Checked against the
# whole string before any shape is tried, so a shape's holes are the only variable parts left.
# `\` joins them: it is how round two's escapes laundered a separator past a tokeniser.
_METACHARS = "`$;&<>()\\\n"
_NOISE = ("2>&1", "2>/dev/null", "> /dev/null", ">/dev/null", "1>/dev/null")


@dataclass(frozen=True)
class _Shape:
    """One permitted command: its literal head, the flags it may carry, and how many operands.

    Operand ARITY is the load-bearing field. `uniq IN OUT` and `sort -o FILE` write through an
    operand rather than a verb, so a shape that fixes how many operands a head may take -- and what
    class each must be -- refuses them without needing to know they write.
    """

    head: tuple[str, ...]
    flags: dict[str, str | None] = field(default_factory=dict)
    short: str | None = None
    arity: tuple[int, int] = (0, 0)
    classes: tuple[str, ...] = ()
    post: str | None = None


def _match_shape(shape: _Shape, tokens: list[str]) -> list[str] | None:
    """The operands this shape matched, or None. The operands are returned because a read's SAFETY
    can depend on which file it names -- `cat` under `/var/log` and `cat` under a secrets dir are
    the same shape."""
    if tuple(tokens[: len(shape.head)]) != shape.head:
        return None
    rest, operands, i = tokens[len(shape.head) :], [], 0
    while i < len(rest):
        token = rest[i]
        if token.startswith("-") and token != "-":
            key, sep, attached = token.partition("=")
            if key in shape.flags:
                spec = shape.flags[key]
                if spec is None:
                    if sep:
                        return None
                    i += 1
                    continue
                value = attached if sep else (rest[i + 1] if i + 1 < len(rest) else None)
                if value is None or not re.fullmatch(spec, value):
                    return None
                i += 1 if sep else 2
                continue
            if shape.short and re.fullmatch(shape.short, token):
                i += 1
                continue
            return None
        operands.append(token)
        i += 1
    if not shape.arity[0] <= len(operands) <= shape.arity[1]:
        return None
    if not all(re.fullmatch(shape.classes[min(n, len(shape.classes) - 1)], operand) for n, operand in enumerate(operands)):
        return None
    return operands


# Reads. Host-independent: none of them writes anywhere, so none needs a host to be safe.
_READ_SHAPES = (
    _Shape(
        ("docker", "logs"),
        {"--since": _SINCE, "--until": _SINCE, "--tail": _INT, "-n": _INT, "--timestamps": None, "-t": None},
        arity=(1, 1),
        classes=(_NAME,),
    ),
    _Shape(("docker", "inspect"), {"--format": _QUOTED, "-f": _QUOTED}, arity=(1, 1), classes=(_NAME,), post="inspect"),
    _Shape(("docker", "image", "inspect"), {"--format": _QUOTED}, arity=(1, 1), classes=(_NAME,), post="inspect"),
    _Shape(("docker", "ps"), {"--filter": _QUOTED, "--format": _QUOTED, "-a": None, "--all": None, "--no-trunc": None}),
    _Shape(("docker", "images"), {"--digests": None, "--format": _QUOTED}, arity=(0, 1), classes=(_NAME,)),
    _Shape(("docker", "stats"), {"--no-stream": None, "--format": _QUOTED}, arity=(0, 2), classes=(_NAME,)),
    _Shape(("systemctl", "status"), {"-n": _INT, "--lines": _INT, "--no-pager": None}, arity=(1, 3), classes=(_UNIT,)),
    _Shape(("systemctl", "is-active"), {"--quiet": None}, arity=(1, 3), classes=(_UNIT,)),
    _Shape(("systemctl", "is-enabled"), arity=(1, 3), classes=(_UNIT,)),
    _Shape(("systemctl", "show"), {"-p": _NAME, "--property": _NAME, "--value": None}, arity=(1, 2), classes=(_UNIT,)),
    _Shape(("systemctl", "list-timers"), {"--all": None, "--no-pager": None}, arity=(0, 2), classes=(_UNIT,)),
    _Shape(("systemctl", "list-units"), {"--all": None, "--state": _NAME, "--no-pager": None}, arity=(0, 2), classes=(_UNIT,)),
    _Shape(("systemctl", "cat"), arity=(1, 2), classes=(_UNIT,)),
    # journalctl's WRITES are all flags -- `--vacuum-size=`, `--rotate`, `--flush`, `--sync`,
    # `--update-catalog`, `--relinquish-var`. None is listed, so each refuses by absence rather than
    # by a denylist someone has to keep complete.
    _Shape(
        ("journalctl",),
        {
            "-u": _UNIT,
            "--unit": _UNIT,
            "--since": _SINCE,
            "--until": _SINCE,
            "-n": _INT,
            "--lines": _INT,
            "--no-pager": None,
            "-o": _NAME,
            "--output": _NAME,
            "-p": _NAME,
            "--priority": _NAME,
            "-b": None,
            "--boot": None,
            "-k": None,
            "-r": None,
            "--reverse": None,
            "--utc": None,
        },
        arity=(0, 2),
        classes=(_MATCHEXPR,),
    ),
    _Shape(("ls",), {"--time-style": _NAME, "--color": _NAME}, short=r"-[laLdhtrSR1]{1,7}", arity=(0, 4), classes=(_PATH,)),
    _Shape(("cat",), short=r"-[nA]{1,2}", arity=(1, 4), classes=(_PATH,)),
    _Shape(("stat",), {"-c": _QUOTED, "--format": _QUOTED}, arity=(1, 3), classes=(_PATH,)),
    _Shape(("df",), short=r"-[hikPT]{1,5}", arity=(0, 3), classes=(_PATH,)),
    _Shape(("du",), {"--max-depth": _INT}, short=r"-[xshcabkm]{1,6}", arity=(1, 5), classes=(_PATH,)),
    # `-exec`, `-execdir`, `-delete`, `-fprint`, `-fls` and `-ok` are absent, so find can only report.
    _Shape(
        ("find",),
        {
            "-name": _QUOTED,
            "-iname": _QUOTED,
            "-path": _QUOTED,
            "-type": _NAME,
            "-mmin": _SINT,
            "-mtime": _SINT,
            "-maxdepth": _INT,
            "-mindepth": _INT,
            "-size": _NAME,
            "-newer": _PATH,
            "-ls": None,
            "-print": None,
        },
        arity=(1, 2),
        classes=(_PATH,),
    ),
    _Shape(("sha256sum",), short=r"-[bc]{1,2}", arity=(1, 3), classes=(_FILEREF,)),
    _Shape(("md5sum",), arity=(1, 3), classes=(_FILEREF,)),
    _Shape(
        ("grep",),
        # `-e` is deliberately NOT value-taking, and must never become so: it would consume the
        # pattern, leaving the first FILE at operand 0 -- which `_reads_only_safe_paths` skips as
        # the pattern. That pair read `/etc/shadow` under an AUTONOMOUS verdict. Left as a valueless
        # short flag the pattern stays positional and every file is checked; no runbook uses `-e`.
        {"-A": _INT, "-B": _INT, "-C": _INT, "--include": _QUOTED},
        short=r"-[iEvnocleqrRFwxsah]{1,8}|-[ABC]\d{1,3}",
        arity=(1, 6),
        classes=(_PATTERN, _FILEREF),
    ),
    # A GET to a healthchecks PING url marks a dead-man alive: `post` refuses those by URL.
    _Shape(
        ("curl",),
        {
            "-m": _INT,
            "--max-time": _INT,
            "--connect-timeout": _INT,
            "-H": _QUOTED,
            "--header": _QUOTED,
            # `-o` WRITES the file it names, so only the discard target is permitted: a verified
            # escape wrote an arbitrary path with attacker-fetched content under an AUTONOMOUS
            # verdict, and the read path returns before the protected-object veto ever runs.
            # `-O`, `--output`, `--output-dir`, `-T`, `--upload-file` and `-d` stay absent.
            "-o": r"/dev/null",
            "-w": _QUOTED,
            "--user-agent": _QUOTED,
        },
        short=r"-[sSfLIkv]{1,6}",
        arity=(1, 1),
        classes=(_URL,),
        post="curl",
    ),
    _Shape(("wg", "show"), arity=(1, 2), classes=(_NAME,)),
    _Shape(("chronyc",), arity=(1, 2), classes=(_NAME,)),
    _Shape(("getent",), arity=(2, 2), classes=(_NAME,)),
    _Shape(("uptime",), short=r"-[ps]{1,2}"),
    _Shape(("nproc",)),
    _Shape(("free",), short=r"-[hmgb]{1,2}"),
    _Shape(("mount",)),
    _Shape(("vmstat",), arity=(0, 2), classes=(_INT,)),
    _Shape(("top",), {"-n": _INT}, short=r"-[bn1H]{1,4}"),
    _Shape(("date",), {"-u": None, "--utc": None}, arity=(0, 1), classes=(_DATEFMT,)),
    _Shape(("hostname",)),
    # The repo's own read-only instruments. Their operands are PromQL and paths, so the class is a
    # literal: the scanner has already refused every metacharacter that was active where it stood.
    _Shape(("grafana-query.py",), {"--since": _SINCE, "--step": _NAME}, arity=(1, 6), classes=(_QUOTED,)),
    _Shape(("continuity.py",), {"--root": _PATH, "--since": _SINCE, "--until": _SINCE}, arity=(0, 3), classes=(_PATH,)),
    _Shape(("ops-postverify.sh",), {"--since": _SINCE}, arity=(0, 3), classes=(_QUOTED,)),
    _Shape(("id",), arity=(0, 1), classes=(_NAME,)),
)

# `zcrypto engine <sub>`: `exec-status` reads, `cycle --replace` deletes a boundary's record, and
# `gate-export` writes a textfile. The read subcommands are named one by one for the same reason.
_ZCRYPTO_READ_SUBS = ("exec-status", "report", "tracking-report", "decompose", "accum-replay", "soak-check")
_ZCRYPTO_SHAPES = tuple(
    _Shape(
        ("zcrypto", "engine", sub),
        {
            "--journal-dir": _PATH,
            "--since": _SINCE,
            "--until": _SINCE,
            "--nav": _INT,
            "--minimums": _FILEREF,
            "--path": _NAME,
            "--date": _SINCE,
            "--pair": _NAME,
            "--json": None,
        },
    )
    for sub in _ZCRYPTO_READ_SUBS
)

# Pipeline filters. Every one takes ZERO file operands -- the rule that refuses `sort -o out`,
# `uniq in out` and `tee`, none of which announces its write in a verb. `grep` takes exactly its
# pattern. `awk`, `sed`, `xargs`, `tee` and `dd` are absent: each can run or write from an operand.
_FILTER_SHAPES = (
    _Shape(("head",), {"-n": _INT, "-c": _INT}, short=r"-\d{1,6}"),
    _Shape(("tail",), {"-n": _INT, "-c": _INT}, short=r"-\d{1,6}"),
    _Shape(("wc",), short=r"-[lwcm]{1,4}"),
    _Shape(("sort",), {"-k": _NAME, "-t": _QUOTED}, short=r"-[hrnufbV]{1,6}"),
    _Shape(("uniq",), short=r"-[cdu]{1,3}"),
    _Shape(("cut",), {"-d": _QUOTED, "-f": _NAME, "-c": _NAME}),
    _Shape(
        ("grep",),
        {"-A": _INT, "-B": _INT, "-C": _INT},
        short=r"-[iEvnocleqFwxa]{1,8}|-[ABC]\d{1,3}",
        arity=(1, 1),
        classes=(_PATTERN,),
    ),
    _Shape(("column",), {"-t": None, "-s": _QUOTED}),
    _Shape(("tr",), {"-d": _QUOTED, "-s": _QUOTED}, arity=(0, 2), classes=(_QUOTED,)),
)

# Mutations the user authorised for the telemetry hosts, where the loop can revert every one of them
# itself. Gated on the host, and vetoed by `_PROTECTED_OBJECTS` -- a converge is never here.
_TELEMETRY_SHAPES = (
    _Shape(("systemctl", "restart"), {"--no-block": None}, arity=(1, 2), classes=(_UNIT_EXACT,)),
    _Shape(("systemctl", "start"), {"--no-block": None}, arity=(1, 2), classes=(_UNIT_EXACT,)),
    _Shape(("systemctl", "stop"), arity=(1, 2), classes=(_UNIT_EXACT,)),
    _Shape(("docker", "restart"), arity=(1, 2), classes=(_NAME,)),
    _Shape(("docker", "start"), arity=(1, 2), classes=(_NAME,)),
    _Shape(("docker", "stop"), arity=(1, 2), classes=(_NAME,)),
)

_PROTECTED_OBJECTS = (
    "zcrypto-capture",
    "zcrypto-engine",
    "zcrypto-red",
    "exec/armed",
    "exec/kill",
    "restart-hold",
    "converge.sh",
    "site.yml",
    "grafana-push.sh",
    "@sha256:",
)
_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess"})
# The `docker inspect` guard exists because a READ can surface the trade key; `cat` and `grep` on
# the same host reach the same secrets through the filesystem, so they get the same treatment.
# Scoped to the heads that print file CONTENT: `ls`, `stat`, `find` and `sha256sum` still answer
# the runbooks' own permission check on `logship-secrets.env`, which prints no bytes of it.
#
# This is an allowlist of WHERE they may read, not a denylist of secret-looking names. The name
# version was written first and broke immediately: `cat /opt/zcrypto-capture/*` carries no
# secret-shaped token and printed the Loki push password, and `grep -r X /etc/zcrypto-ops/` did the
# same by recursion. A glob or a directory names nothing the filter can match -- which is the exact
# defect the two inherited post-checks had, reintroduced by hand one commit after being described.
_CONTENT_HEADS = frozenset({"cat", "grep"})
# Directories, matched by prefix -- every one ends in `/` so a sibling cannot ride in on its
# letters (`/var/logsecret/` is not `/var/log/`).
_READ_SAFE_DIRS = (
    "/var/log/",
    "/var/lib/zcrypto-node-textfile/",
    "/var/lib/zcrypto-ops/",
    "/var/lib/zcrypto-engine/exec/",
    "/var/lib/zcrypto-engine/journal/",
    "/mnt/zhao-crypto/",
    "/etc/systemd/journald.conf.d/",
)
# Single files, matched EXACTLY. As prefixes these admitted anything extending the name --
# `journald.conf.evil`, `compose.yamlxsecrets.env`, `/etc/machine-id-backup/secrets` all read
# clean, verified. Nothing on the fleet matches today, which is what made it latent rather than
# open; `/etc/zcrypto-ops/alloy/` is listed as this one file because alloy-secrets.env sits beside
# it, and a `compose.yaml.bak` would otherwise have been a door onto the same directory.
_READ_SAFE_FILES = (
    "/etc/systemd/journald.conf",
    "/etc/zcrypto-ops/alloy/compose.yaml",
    "/etc/machine-id",
)


def _reads_only_safe_paths(head: str, operands: list[str]) -> bool:
    """Every path a content head names must sit under a read-safe root, absolute and traversal-free.

    `grep`'s first operand is its pattern -- which holds only because no shape lets a flag consume
    that pattern. Give `-e` a value spec and this skip silently drops a FILE instead. A `*` cannot cross `/`, so a glob under a
    safe root stays under it; `..` can leave, so it is refused outright.
    """
    paths = operands[1:] if head == "grep" else operands
    return all(".." not in path and (path.startswith(_READ_SAFE_DIRS) or path in _READ_SAFE_FILES) for path in paths)


# Stripped before matching: they change who runs a command, never what it does. `ssh <host>` also
# RETARGETS it, so the host it names replaces the caller's for the telemetry gate.
_PREFIXES = (("sudo",), ("sudo", "-n"), ("uv", "run"), ("time",))
_DOCKER_EXEC_VALUE_FLAGS = frozenset({"-u", "--user", "-w", "--workdir", "-e", "--env"})

_CMD_SPAN = re.compile(r"`([^`\n]+)`")
_SAFE_INSPECT_FIELDS = (
    ".Mounts",
    ".State",
    ".Config.Image",
    ".Config.Entrypoint",
    ".RestartCount",
    ".Name",
    ".Created",
    ".Id",
    ".HostConfig.NanoCpus",
    ".HostConfig.Memory",
)


def _commands(text: str) -> list[str]:
    """Every backtick span, or -- when there is none -- the whole text as one command.

    Never refused for want of markup: the skill passes the one command it is about to run, usually
    bare, and refusing that would prepare everything at runtime under a green suite.
    """
    spans = [s.strip() for s in _CMD_SPAN.findall(text) if s.strip()]
    return spans or ([text.strip()] if text.strip() else [])


def _strip_noise(text: str) -> str:
    """Drop the stderr redirections, but only as WHOLE tokens.

    A raw replace made the classifier disagree with bash: `docker logs2>/dev/nullzcrypto-engine`
    became `docker logs zcrypto-engine` here while bash reads a command `logs2` redirecting into a
    file. Padding makes the match whitespace-delimited, so anything glued to a word keeps its `>`
    and meets the metacharacter gate.
    """
    padded = f" {text} "
    for noise in _NOISE:
        padded = padded.replace(f" {noise} ", " ")
    return padded.strip()


def _scan(text: str) -> list[list[str]] | None:
    r"""Tokenise into pipeline stages, refusing every metacharacter that is ACTIVE where it stands.

    Exact shell quoting rather than an approximation: outside quotes anything that can start a
    command, redirect one or join two is refused; inside single quotes nothing is special, so a real
    grep pattern may hold `(`, `|` and `\\`; inside double quotes only expansion and escape are.
    Getting this exactly right is what lets the shapes trust their operands -- and it is why
    `docker inspect --format '{{.State.Status}} {{.RestartCount}}'` is one token, not two.
    """
    stages: list[list[str]] = []
    tokens: list[str] = []
    current: list[str] = []
    quote = ""
    quoted = False

    def close() -> None:
        nonlocal current, quoted
        if current or quoted:
            tokens.append("".join(current))
        current, quoted = [], False

    for char in text:
        if quote:
            if char == quote:
                quote = ""
            elif quote == '"' and char in "$`\\":
                return None
            else:
                current.append(char)
        elif char in "'\"":
            quote, quoted = char, True
        elif char in _METACHARS:
            return None
        elif char == "|":
            close()
            stages.append(tokens)
            tokens = []
        elif char.isspace():
            close()
        else:
            current.append(char)
    if quote:
        return None
    close()
    stages.append(tokens)
    return stages


_TEMPLATE_ACTION = re.compile(r"\{\{(.*?)\}\}", re.S)
_SELECTOR = re.compile(r"\.\w[\w.]*")


def _inspect_format(tokens: list[str]) -> str | None:
    for n, token in enumerate(tokens):
        if token.startswith("--format="):
            return token.split("=", 1)[1]
        if token in ("--format", "-f") and n + 1 < len(tokens):
            return tokens[n + 1]
    return None


def _inspect_format_is_scoped(tokens: list[str]) -> bool:
    """CLAUDE.md's secrets rule, made structural: an inspect prints only the fields named there.

    Unscoped, `docker inspect` prints the container's environment, which on the engine host is the
    live Kraken trade key. Allowlisting the SELECTORS it mentions is not enough, and that premise
    cost a verified leak: a Go template reaches the whole object through a bare root reference, so
    `--format '{{.Name}}{{json .}}'` mentions one safe selector and marshals `ContainerJSON` --
    `.Config.Env` and the key with it. `{{index . "Config" "Env"}}` does the same with no selector
    at all. So each ACTION is default-denied instead: a safe dotted selector, optionally wrapped in
    `json`, and nothing else -- no bare `.`, no `index`, `printf`, `range`, `with` or `call`. Text
    outside the actions is inert label material and needs no check.
    """
    fmt = _inspect_format(tokens)
    if fmt is None:
        return False
    actions = _TEMPLATE_ACTION.findall(fmt)
    if not actions:
        return False
    for action in actions:
        body = action.strip()
        if body.startswith("json "):
            body = body[len("json ") :].strip()
        if not _SELECTOR.fullmatch(body) or not body.startswith(_SAFE_INSPECT_FIELDS):
            return False
    return True


def _curl_is_read(tokens: list[str]) -> bool:
    """A plain GET to a healthchecks ping URL marks a dead-man alive -- a read that silences an alarm."""
    joined = " ".join(tokens).lower()
    return "hc-ping" not in joined and "healthchecks.io/ping" not in joined


_POSTCHECKS = {"inspect": _inspect_format_is_scoped, "curl": _curl_is_read}


def _matches(shapes, tokens: list[str]) -> list[str] | None:
    for shape in shapes:
        operands = _match_shape(shape, tokens)
        if operands is None:
            continue
        check = _POSTCHECKS.get(shape.post) if shape.post else None
        if check and not check(tokens):
            continue
        return operands
    return None


def _strip_prefixes(tokens: list[str]) -> tuple[list[str], str | None]:
    """Peel what changes WHO runs a command, never what it does; report the host an ssh retargets to.

    `docker exec <container>` is peeled for the same reason: its payload is the real command, and
    only the payload separates `docker exec zcrypto-engine zcrypto engine exec-status` from
    `docker exec zcrypto-archive-pull rm -f /tmp/gate-cache.json`. What comes out is matched against
    the shapes like any other command, so a peeled payload is never trusted -- only re-examined.
    """
    target = None
    changed = True
    while changed and tokens:
        changed = False
        # The NAS spells it `/usr/local/bin/docker`: docker is off the non-interactive ssh PATH there.
        tokens = [tokens[0].rsplit("/", 1)[-1], *tokens[1:]]
        for prefix in _PREFIXES:
            if tuple(tokens[: len(prefix)]) == prefix:
                tokens, changed = tokens[len(prefix) :], True
                break
        if changed:
            continue
        if len(tokens) > 2 and tokens[0] == "ssh" and re.fullmatch(_NAME, tokens[1]):
            target, tokens, changed = tokens[1], tokens[2:], True
        elif len(tokens) > 1 and tokens[0] in ("python", "python3") and tokens[1].endswith(".py"):
            tokens, changed = tokens[1:], True
        elif len(tokens) > 1 and tokens[0] in ("bash", "sh") and tokens[1].endswith(".sh"):
            tokens, changed = tokens[1:], True
        elif len(tokens) > 2 and tokens[0] == "docker" and tokens[1] == "exec":
            rest = tokens[2:]
            while rest and rest[0].startswith("-"):
                rest = rest[2:] if rest[0] in _DOCKER_EXEC_VALUE_FLAGS else rest[1:]
            if len(rest) > 1 and re.fullmatch(_NAME, rest[0]):
                tokens, changed = rest[1:], True
    return tokens, target


def classify_action(text: str, *, host: str | None = None) -> Tier:
    """Which tier a runbook step falls in. Default-deny: unrecognised is PREPARED, always.

    A command is AUTONOMOUS only when EVERY backtick span in the text matches an enumerated shape.
    There is no rule that reads a command's words and decides it looks harmless -- that rule is what
    three review rounds broke. Making any branch here permissive is wrong however reasonable it looks.
    """
    commands = _commands(text)
    if not commands:
        return Tier.PREPARED
    if all(_classify_one(command, host) is Tier.AUTONOMOUS for command in commands):
        return Tier.AUTONOMOUS
    return Tier.PREPARED


def _classify_one(command: str, host: str | None) -> Tier:
    stages = _scan(_strip_noise(command))
    if not stages or not all(stages):
        return Tier.PREPARED
    first, *filters = stages
    if not all(_matches(_FILTER_SHAPES, stage) is not None for stage in filters):
        return Tier.PREPARED
    tokens, target = _strip_prefixes(first)
    if not tokens:
        return Tier.PREPARED
    operands = _matches(_READ_SHAPES + _ZCRYPTO_SHAPES, tokens)
    if operands is not None:
        if tokens[0] in _CONTENT_HEADS and not _reads_only_safe_paths(tokens[0], operands):
            return Tier.PREPARED
        return Tier.AUTONOMOUS
    lowered = command.lower()
    if (
        (target or host) in _TELEMETRY_HOSTS
        and not any(obj in lowered for obj in _PROTECTED_OBJECTS)
        and _matches(_TELEMETRY_SHAPES, tokens)
    ):
        return Tier.AUTONOMOUS
    return Tier.PREPARED
