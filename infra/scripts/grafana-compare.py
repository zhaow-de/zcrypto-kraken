#!/usr/bin/env python3
"""Run every rule's query on both Grafana stacks at the same 24 instants and compare the answers by value.
    uv run python infra/scripts/grafana-compare.py [--day YYYY-MM-DD]
Each query node of infra/grafana/alerts.yaml is sent as an instant query, `time=<epoch seconds>`, to each stack's
datasource proxy at the top of each UTC hour of the day named, the preceding UTC day by default; the rule's own
range selector supplies the window. The node's own rule group and `host` exist on the node alone, so both are
outside the comparison by name. The last line is one summary whatever the outcome:
  `compare: <nodes> nodes × 24 instants, <n> differences`, exit 0 at none and 1 otherwise, one line per difference above it;
  `compare: failed: <what failed>`, exit 2, naming the stack where a stack failed -- never a match, never a skip.
The requests go one at a time, so a run adds one query at a time to either stack's query path. The tokens are only
ever request headers: never printed, never written, never in argv.
"""

from __future__ import annotations

import http.client
import importlib.util
import json
import math
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import yaml

_HERE = Path(__file__).resolve().parent


def _load_sibling(name: str, file: str):
    spec = importlib.util.spec_from_file_location(name, _HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


grafana_auth = _load_sibling("grafana_auth", "grafana_auth.py")
_query_tool = _load_sibling("grafana_query", "grafana-query.py")

ALERTS = _HERE.parents[1] / "infra" / "grafana" / "alerts.yaml"
EXCLUDED_GROUPS = ("zcrypto-mon",)
EXCLUDED_HOSTS = ("zcrypto-mon",)
# The rules that select a direct shipper's log stream, which reaches the node only at the cutover; the test holds
# this tuple to the measured basis's listing over the rule file, so an eighth such rule fails the test, not a run.
DIRECT_SHIPPED_RULES = (
    "zcrypto-engine-error-logs",
    "zcrypto-engine-log-dead",
    "zcrypto-capture-error-logs",
    "zcrypto-capture-log-dead-primary",
    "zcrypto-capture-log-dead-secondary",
    "zcrypto-ops-poller-log-dead",
    "zcrypto-ops-error-logs",
)
INSTANTS_PER_DAY = 24
RELATIVE_TOLERANCE = 1e-6
TIMEOUT = 30
# The rule file carries the placeholder, never a uid: each routes to the uid both stacks serve and that path's query API.
_PATHS = {
    "${GRAFANA_PROM_DS_UID}": (_query_tool.PROM_DS_UID, "api/v1/query"),
    "${GRAFANA_LOKI_DS_UID}": (_query_tool.LOKI_DS_UID, "loki/api/v1/query"),
}


class Failed(Exception):
    """Ends the run as `compare: failed: <text>`; the text names the stack when a stack failed."""


class Node(NamedTuple):
    uid: str
    ref_id: str
    expr: str
    ds_uid: str
    path: str


def walk(rules: list[dict]) -> list[Node]:
    nodes = []
    for rule in rules:
        if rule.get("ruleGroup") in EXCLUDED_GROUPS or rule["uid"] in DIRECT_SHIPPED_RULES:
            continue
        for data in rule["data"]:
            placeholder = data.get("datasourceUid")
            if placeholder == "__expr__":
                continue
            if placeholder not in _PATHS:
                raise Failed(
                    f"rule {rule['uid']} node {data.get('refId')} carries datasourceUid {placeholder!r}, neither placeholder"
                )
            ds_uid, path = _PATHS[placeholder]
            nodes.append(Node(rule["uid"], data["refId"], data["model"]["expr"], ds_uid, path))
    if not nodes:
        raise Failed("the walk would send no query node")
    return nodes


def instants(day: date) -> list[int]:
    """The epoch second of each UTC hour top of `day`: a ten-digit integer, which Prometheus and Loki both read as seconds."""
    first = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    return [first + 3600 * hour for hour in range(INSTANTS_PER_DAY)]


def _rows(stack: str, node: Node, instant: int, result) -> dict[tuple[tuple[str, str], ...], float]:
    """Each series by its whole label set, the node's rows dropped; a shape that is not an instant vector fails the stack."""
    try:
        rows = {}
        for series in result:
            labels = tuple(sorted((str(k), str(v)) for k, v in series["metric"].items()))
            if series["metric"].get("host") in EXCLUDED_HOSTS:
                continue
            rows[labels] = float(series["value"][1])
        return rows
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        raise Failed(f"{stack} {node.uid} {node.ref_id} at {instant}: a result that is not an instant vector: {exc!r}") from exc


def query(stack: str, url: str, token: str, node: Node, instant: int) -> dict[tuple[tuple[str, str], ...], float]:
    endpoint = f"{url}/api/datasources/proxy/uid/{node.ds_uid}/{node.path}?" + urllib.parse.urlencode(
        {"query": node.expr, "time": instant}
    )
    request = urllib.request.Request(endpoint, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310 -- the stack table's https urls
            result = json.load(response)["data"]["result"]
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as exc:
        raise Failed(f"{stack} {node.uid} {node.ref_id} at {instant}: {exc}") from exc
    return _rows(stack, node, instant, result)


def _same(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=RELATIVE_TOLERANCE, abs_tol=0.0) or (math.isnan(a) and math.isnan(b))


def _labels(labels: tuple[tuple[str, str], ...]) -> str:
    return "{" + ", ".join(f'{k}="{v}"' for k, v in labels) + "}"


def differences(node: Node, instant: int, first: str, a: dict, second: str, b: dict) -> list[str]:
    when = datetime.fromtimestamp(instant, timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    head = f"{node.uid} {node.ref_id} {when}"
    if bool(a) != bool(b):
        empty, full, n = (first, second, len(b)) if not a else (second, first, len(a))
        return [f"{head} empty on {empty}, {n} row{'s' if n != 1 else ''} on {full}"]
    out = [f"{head} only on {first} {_labels(labels)}" for labels in a if labels not in b]
    out += [f"{head} only on {second} {_labels(labels)}" for labels in b if labels not in a]
    out += [
        f"{head} value {first}={a[labels]} {second}={b[labels]} {_labels(labels)}"
        for labels in a
        if labels in b and not _same(a[labels], b[labels])
    ]
    return out


def _day(argv: list[str]) -> date:
    today = datetime.now(timezone.utc).date()
    if "--day" not in argv:
        return today - timedelta(days=1)
    try:
        day = date.fromisoformat(argv[argv.index("--day") + 1])
    except (IndexError, ValueError) as exc:
        raise Failed(f"--day takes YYYY-MM-DD: {exc}") from exc
    if day >= today:
        raise Failed(f"--day {day} has not ended in UTC")
    return day


def _token(name: str, stack) -> str:
    try:
        return grafana_auth.vault_var(stack.token_var, stack.vault_file)
    except Exception as exc:  # noqa: BLE001 -- the vault fails across hierarchies; the run ends on its summary line either way
        raise Failed(f"{name} token could not be read: {type(exc).__name__}: {exc}") from exc


def compare(day: date) -> tuple[int, int]:
    """(nodes, differences), each difference printed as it is found; `Failed` ends the run before the first query
    it cannot ground, and at the first answer a stack could not give."""
    if len(grafana_auth.STACKS) != 2:
        n = len(grafana_auth.STACKS)
        raise Failed(f"the stack table holds {n} stack{'s' if n != 1 else ''}, not two")
    first, second = sorted(grafana_auth.STACKS)
    stacks = {name: (grafana_auth.STACKS[name].url, _token(name, grafana_auth.STACKS[name])) for name in (first, second)}
    nodes = walk(yaml.safe_load(ALERTS.read_text(encoding="utf-8"))["rules"])
    found = 0
    for instant in instants(day):
        for node in nodes:
            answers = {name: query(name, url, token, node, instant) for name, (url, token) in stacks.items()}
            for line in differences(node, instant, first, answers[first], second, answers[second]):
                print(line)
                found += 1
    return len(nodes), found


def _failed(text: str) -> int:
    print(f"compare: failed: {' '.join(text.split())}")
    return 2


def main(argv: list[str]) -> int:
    try:
        nodes, found = compare(_day(argv))
    except Failed as exc:
        return _failed(str(exc))
    except Exception as exc:  # noqa: BLE001 -- the last line is the summary whatever failed; the traceback keeps the cause on stderr
        traceback.print_exc()
        return _failed(f"{type(exc).__name__}: {exc}")
    print(f"compare: {nodes} nodes × {INSTANTS_PER_DAY} instants, {found} differences")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
