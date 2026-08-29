"""The daily operations pass's instrument: reads the fleet, never writes to it.

Its exit code is the pass's headline -- 0 all-clear, 1 attention, 2 a source it could not read --
because a source that cannot be reached is a finding ABOUT that source, never a silent gap.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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
        if isinstance(line, dict):
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


class Tier(Enum):
    """Which authority an action needs. `PREPARED` means prepare it and stop."""

    AUTONOMOUS = "autonomous"
    PREPARED = "prepared"


# Seeded from the commands the runbooks actually contain, not from imagination: extract every
# backtick span and fenced-block line across infra/runbooks/*.md and count the heads before editing
# this. A diagnostic the pass refuses is the halt-at-step-1 failure moved rather than fixed.
_READ_ONLY_COMMANDS = frozenset(
    {
        ("docker", "logs"),
        ("docker", "inspect"),
        ("docker", "ps"),
        ("docker", "images"),
        ("docker", "stats"),
        ("journalctl", None),
        ("systemctl", "status"),
        ("systemctl", "list-timers"),
        ("systemctl", "show"),
        ("systemctl", "is-active"),
        ("cat", None),
        ("grep", None),
        ("ls", None),
        ("df", None),
        ("du", None),
        ("find", None),
        ("stat", None),
        ("head", None),
        ("tail", None),
        ("wc", None),
        ("sort", None),
        ("uniq", None),
        ("date", None),
        ("echo", None),
        ("curl", None),
        ("grafana-query.py", None),
        ("continuity.py", None),
    }
)
# `zcrypto engine <sub>` is three tokens, so it needs its own read-only set rather than a
# (binary, subcommand) pair: `exec-status` reads, `cycle --replace` deletes a boundary's record.
_READ_ONLY_ZCRYPTO_ENGINE = frozenset({"exec-status", "report", "tracking-report", "decompose", "accum-replay", "soak-check"})
# `docker inspect` REQUIRES --format: unscoped it prints the container's environment, which on the
# engine host is the live Kraken trade key.
_REQUIRE_FORMAT = frozenset({("docker", "inspect")})
# Refused inside an otherwise-read-only command, matched as exact tokens so `-fsS` is not `-f`.
# find's primaries are single-dash, so the double-dash spellings alone would miss them.
_MUTATING_FLAGS = frozenset(
    {
        "--rotate",
        "--flush",
        "--force",
        "-f",
        "--apply",
        "--delete",
        "-delete",
        "-exec",
        "--prune",
        "--rm",
        "--replace",
    }
)
# Prefixes, because the flag carries a value: `--vacuum-size=200M` deletes the journal and would
# never match an exact-token list. This is the round-4 Critical; keep it a prefix.
_MUTATING_FLAG_PREFIXES = ("--vacuum",)
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
_TELEMETRY_OBJECTS = ("grafana-alloy", "alloy", ".timer", ".prom")
_TELEMETRY_HOSTS = frozenset({"ops", "nas", "zaccess"})
_WRAPPERS = ("sudo", "uv", "run", "python", "python3", "bash", "sh", "-c", "time", "env")

_CMD_SPAN = re.compile(r"`([^`\n]+)`")


def _commands(text: str) -> list[str]:
    """Every backtick span, or — when there is none — the whole text as one command.

    Never refused for want of markup: the skill passes the one command it is about to run, usually
    bare, and refusing that would prepare everything at runtime under a green suite.
    """
    spans = [s.strip() for s in _CMD_SPAN.findall(text) if s.strip()]
    return spans or ([text.strip()] if text.strip() else [])


def _strip_wrappers(tokens: list[str]) -> list[str]:
    """`docker exec <container>` is a wrapper, never a read: its payload is the real command.

    `docker exec zcrypto-engine zcrypto engine exec-status` reads; `docker exec zcrypto-archive-pull
    rm -f /tmp/gate-cache.json` deletes. Only the payload separates them.
    """
    while tokens:
        head = tokens[0].split("/")[-1]
        if head in _WRAPPERS or head.startswith("--"):
            tokens = tokens[1:]
        elif head == "ssh" and len(tokens) > 1:
            tokens = tokens[2:]
        elif head == "docker" and len(tokens) > 2 and tokens[1] == "exec":
            tokens = tokens[2:]
            while tokens and (tokens[0].startswith("-") or tokens[0].startswith("zcrypto-")):
                tokens = tokens[1:]
        else:
            return tokens
    return tokens


# CLAUDE.md names the fields an inspect may scope to. `--format` alone is not enough: the banned
# `{{json .Config}}` and `{{.Config.Env}}` both carry it, and both print the live trade key.
_SAFE_INSPECT_FIELDS = (".Mounts", ".State", ".Config.Image", ".Config.Entrypoint", ".RestartCount", ".Name", ".Created", ".Id")


def _inspect_format_is_scoped(segment: str) -> bool:
    match = re.search(r"--format[= ]\s*(\S.*)", segment)
    if not match:
        return False
    selectors = re.findall(r"\.\w[\w.]*", match.group(1))
    return bool(selectors) and all(sel.startswith(_SAFE_INSPECT_FIELDS) for sel in selectors)


# A bare `curl` is a read; with a method, a body, an upload or an output file it writes. And a plain
# GET to a healthchecks ping URL MARKS A DEAD-MAN ALIVE -- a read that silences the alarm.
_CURL_MUTATING = (
    "-X",
    "--request",
    "-d",
    "--data",
    "--data-binary",
    "--data-raw",
    "--data-urlencode",
    "--json",
    "-F",
    "--form",
    "-T",
    "--upload-file",
    "-O",
)


def _has_mutating_flag(tokens: list[str]) -> bool:
    return any(t in _MUTATING_FLAGS or t.startswith(_MUTATING_FLAG_PREFIXES) for t in tokens)


# Shell composition is refused outright rather than parsed: a substitution, a redirect or a
# process substitution can carry ANY command inside a segment an allowlisted head vouches for --
# `echo 1 > /var/lib/zcrypto-engine/exec/armed` arms the live executor, and `cat x; rm -rf y`
# deletes. Understanding shell is not the job; refusing to guess is.
_SEPARATORS = frozenset({";", "&", "&&", "|", "||", "\n"})
_REDIRECTS = frozenset({">", ">>", "<", "<<", ">|"})
_NOISE = ("2>&1", "2>/dev/null", "> /dev/null", ">/dev/null")

# Flags are ALLOWLISTED per command, never denylisted. `curl` accepts `-XDELETE` attached and `-sO`
# combined; `find` has `-execdir`, `-fprint` and `-ok` beside the `-exec` and `-delete` anyone thinks
# to ban. Enumerating what may pass is the only side of that list with a finite length.
_CURL_READ_FLAGS = frozenset(
    {
        "-s",
        "-S",
        "-f",
        "-L",
        "-I",
        "-k",
        "-m",
        "-w",
        "-H",
        "-A",
        "-o",
        "-v",
        "--silent",
        "--show-error",
        "--fail",
        "--location",
        "--head",
        "--insecure",
        "--max-time",
        "--write-out",
        "--header",
        "--user-agent",
        "--output",
        "--connect-timeout",
        "--retry",
    }
)
_FIND_READ_PRIMARIES = frozenset(
    {
        "-name",
        "-iname",
        "-type",
        "-mtime",
        "-mmin",
        "-newer",
        "-size",
        "-path",
        "-ipath",
        "-maxdepth",
        "-mindepth",
        "-print",
        "-print0",
        "-printf",
        "-ls",
        "-empty",
        "-user",
        "-group",
        "-not",
        "-o",
        "-a",
        "-prune",
        "-regex",
        "-inum",
        "-links",
        "-perm",
    }
)


def _strip_noise(text: str) -> str:
    for noise in _NOISE:
        text = text.replace(noise, " ")
    return text


def _lex(text: str) -> list[str]:
    r"""Tokenise with `shlex`, which knows quoting and backslash escapes; refuse what it cannot parse.

    Hand-rolled splitting lost to shell repeatedly. `echo \' ; rm -rf /x` opens a quote span in a
    naive scanner, so the real `;` reads as quoted and the whole string passes as one `echo` -- while
    bash runs the `rm`. `punctuation_chars` makes `;`, `&`, `|`, `<` and `>` their own tokens, so
    composition is seen rather than inferred, and an unbalanced quote raises rather than parsing to
    something convenient.
    """
    lexer = shlex.shlex(text, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def _segments(command: str) -> list[list[str]]:
    """One token list per shell segment; an unparseable command yields one refusing segment."""
    try:
        tokens = _lex(_strip_noise(command))
    except ValueError:
        return [["\x00unparseable"]]
    out, current = [], []
    for token in tokens:
        if token in _SEPARATORS:
            out.append(current)
            current = []
        else:
            current.append(token)
    out.append(current)
    return [seg for seg in out if seg]


def _flags_are_read_only(head: str, tokens: list[str]) -> bool:
    joined = " ".join(tokens).lower()
    if head == "curl":
        # A plain GET to a ping URL marks a dead-man alive: a read that silences an alarm. DNS is
        # case-insensitive, so the check is too.
        if "hc-ping" in joined or "healthchecks.io/ping" in joined:
            return False
        for token in tokens[1:]:
            if not token.startswith("-"):
                continue
            base = token.split("=", 1)[0]
            if base in _CURL_READ_FLAGS:
                continue
            if re.fullmatch(r"-[A-Za-z]+", token) and all(f"-{ch}" in _CURL_READ_FLAGS for ch in token[1:]):
                continue
            return False
        return True
    if head == "find":
        # `-3` is the VALUE of `-mmin`, not a primary: a signed integer can never be a primary, and
        # refusing it would reject the runbooks' own `find … -mmin -3` freshness checks.
        return all(t in _FIND_READ_PRIMARIES for t in tokens[1:] if t.startswith("-") and not re.fullmatch(r"[-+]?\d+", t))
    return True


def _segment_is_read_only(tokens: list[str]) -> bool:
    # shlex splits `$(` into `$` and `(`, so both halves are named; `(`, `)` and `$` never appear in
    # a read this pass should run, and a substitution can carry any command at all.
    if any(t in _REDIRECTS or t in ("$", "(", ")", "$(") or "`" in t or t == "\x00unparseable" for t in tokens):
        return False
    tokens = _strip_wrappers(list(tokens))
    if not tokens:
        return False
    head = tokens[0].split("/")[-1]
    sub = tokens[1] if len(tokens) > 1 and not tokens[1].startswith("-") else None
    if head == "zcrypto":
        if sub != "engine" or len(tokens) < 3 or tokens[2] not in _READ_ONLY_ZCRYPTO_ENGINE:
            return False
        return not _has_mutating_flag(tokens)
    pair = (head, sub) if (head, sub) in _READ_ONLY_COMMANDS else (head, None)
    if pair not in _READ_ONLY_COMMANDS:
        return False
    if pair in _REQUIRE_FORMAT and not _inspect_format_is_scoped(" ".join(tokens)):
        return False
    if not _flags_are_read_only(head, tokens):
        return False
    return not _has_mutating_flag(tokens)


def classify_action(text: str, *, host: str | None = None) -> Tier:
    """Which tier a runbook step falls in: what it DOES first, what it touches second.

    Rules 2 and 4 are both default-deny -- an unrecognised binary, an unparseable command, or a flag
    outside its command's read allowlist all refuse. That is the property that catches the verb
    nobody imagined, and a change making either permissive is wrong however reasonable it looks.
    """
    lowered = text.lower()
    commands = _commands(text)
    read_only = bool(commands) and all(all(_segment_is_read_only(seg) for seg in _segments(c)) for c in commands)
    protected = any(obj in lowered for obj in _PROTECTED_OBJECTS)
    if not read_only and protected:
        return Tier.PREPARED
    if read_only:
        return Tier.AUTONOMOUS
    if any(obj in lowered for obj in _TELEMETRY_OBJECTS) and host in _TELEMETRY_HOSTS:
        return Tier.AUTONOMOUS
    return Tier.PREPARED
