"""`infra/scripts/grafana-compare.py` against two canned stacks behind `urlopen`: the comparison's verdicts, the
instants it sends, the three exclusions by name, and the walk over the real rule file."""

from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import urllib.error
import urllib.parse
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "grafana-compare.py"
_ALERTS = _REPO / "infra" / "grafana" / "alerts.yaml"
_spec = importlib.util.spec_from_file_location("grafana_compare", _SCRIPT)
gc = importlib.util.module_from_spec(_spec)
sys.modules["grafana_compare"] = gc
_spec.loader.exec_module(gc)

TOKEN = "glsa_TOTALLY_NOT_A_REAL_TOKEN_0123456789"
DAY = "2026-09-30"
# The epoch of 2026-09-30T00:00Z, a ten-digit literal: an instant sent in milliseconds, or in another day, is not among these.
INSTANTS = [1790726400 + 3600 * i for i in range(24)]
PROM = "${GRAFANA_PROM_DS_UID}"
LOKI = "${GRAFANA_LOKI_DS_UID}"
PROM_PATH = "api/v1/query"
LOKI_PATH = "loki/api/v1/query"
# The measured basis's listing of the rules that select a direct shipper's stream: the uids written here, and the
# listing's own selectors below, never the script's constant.
DIRECT_SHIPPED = (
    "zcrypto-engine-error-logs",
    "zcrypto-engine-log-dead",
    "zcrypto-ops-error-logs",
    "zcrypto-ops-poller-log-dead",
    "zcrypto-capture-error-logs",
    "zcrypto-capture-log-dead-primary",
    "zcrypto-capture-log-dead-secondary",
)
_DIRECT_SELECTORS = ('container="engine"', 'container="capture"', "liquidations")


class Request(NamedTuple):
    stack: str
    ds_uid: str
    path: str
    expr: str
    time: str | None
    timeout: object
    authorization: str | None


class _Response:
    def __init__(self, raw: bytes) -> None:
        self._raw = io.BytesIO(raw)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *a):
        return self._raw.read(*a)


def _refusal(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://stub.invalid/x", code, "refused", {}, io.BytesIO(b""))


class _Stacks:
    """Both stacks behind `urlopen`, as `tests/test_grafana_query.py`'s `_Recorded` stubs one: each request is
    recorded, and answered by `answer(stack, path, expr, time)` -- a list of rows, raw bytes, or an exception to raise."""

    def __init__(self, monkeypatch, answer=None) -> None:
        self.requests: list[Request] = []
        self.answer = answer or (lambda stack, path, expr, time: [])
        self._by_url = {s.url: name for name, s in gc.grafana_auth.STACKS.items()}
        monkeypatch.setattr(gc.grafana_auth, "vault_var", lambda name, vault_file: TOKEN)
        monkeypatch.setattr(gc.urllib.request, "urlopen", self._urlopen)

    def _urlopen(self, request, timeout=None):
        url = urllib.parse.urlsplit(request.full_url)
        stack = self._by_url[f"{url.scheme}://{url.netloc}"]
        m = re.fullmatch(r"/api/datasources/proxy/uid/([^/]+)/(api/v1/query|loki/api/v1/query)", url.path)
        assert m, request.full_url
        q = urllib.parse.parse_qs(url.query)
        sent = Request(
            stack, m.group(1), m.group(2), q["query"][0], q.get("time", [None])[0], timeout, request.get_header("Authorization")
        )
        self.requests.append(sent)
        body = self.answer(stack, sent.path, sent.expr, sent.time)
        if isinstance(body, Exception):
            raise body
        if isinstance(body, bytes):
            return _Response(body)
        return _Response(json.dumps({"status": "success", "data": {"resultType": "vector", "result": body}}).encode())


def _row(value, **labels) -> dict:
    return {"metric": labels, "value": [1790726400, str(value)]}


def _rule(uid: str, expr: str, *, group: str = "zcrypto-x", loki: bool = False, ref: str = "A") -> dict:
    return {
        "uid": uid,
        "title": uid,
        "ruleGroup": group,
        "data": [
            {"refId": ref, "datasourceUid": LOKI if loki else PROM, "model": {"expr": expr, "instant": True, "refId": ref}},
            {"refId": "C", "datasourceUid": "__expr__", "model": {"type": "threshold", "expression": ref, "refId": "C"}},
        ],
    }


def _alerts(monkeypatch, tmp_path, *rules) -> Path:
    path = tmp_path / "alerts.yaml"
    path.write_text(yaml.safe_dump({"rules": list(rules)}), encoding="utf-8")
    monkeypatch.setattr(gc, "ALERTS", path)
    return path


def _by_stack(answers: dict):
    """`answer` from a per-stack mapping, optionally per path: `{"cloud": rows, "mon": rows}`."""
    return lambda stack, path, expr, time: answers[stack]


def _run(capsys, argv=("--day", DAY)) -> tuple[int, list[str]]:
    rc = gc.main(list(argv))
    return rc, capsys.readouterr().out.splitlines()


def test_the_same_answer_on_both_stacks_is_no_difference_and_the_summary_is_the_last_line(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch, _by_stack({"cloud": [_row(1, host="ops")], "mon": [_row(1, host="ops")]}))
    rc, out = _run(capsys)
    assert rc == 0
    assert out == ["compare: 1 nodes × 24 instants, 0 differences"]
    assert len(stacks.requests) == 48
    assert TOKEN not in "\n".join(out) and all(r.authorization == f"Bearer {TOKEN}" for r in stacks.requests)


@pytest.mark.parametrize(("off", "differences"), [(1e-5, 24), (1e-7, 0)], ids=["off by 1e-5 differs", "off by 1e-7 matches"])
def test_the_tolerance_is_a_relative_1e_6_held_from_both_sides(monkeypatch, tmp_path, capsys, off, differences):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    _Stacks(monkeypatch, _by_stack({"cloud": [_row(1.0, host="ops")], "mon": [_row(1.0 + off, host="ops")]}))
    rc, out = _run(capsys)
    assert rc == (1 if differences else 0)
    assert out[-1] == f"compare: 1 nodes × 24 instants, {differences} differences"
    assert len(out) == differences + 1
    assert all(line.startswith("r-up A 2026-09-30T") for line in out[:-1]), out


def test_a_label_set_on_one_stack_is_a_difference_even_when_its_nearest_row_differs_in_one_label_other_than_host(
    monkeypatch, tmp_path, capsys
):
    """A comparison keyed on `host`, or on any subset of the labels, reads these two rows as one series."""
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    _Stacks(monkeypatch, _by_stack({"cloud": [_row(1, host="ops", job="a")], "mon": [_row(1, host="ops", job="b")]}))
    rc, out = _run(capsys)
    assert rc == 1
    assert out[-1] == "compare: 1 nodes × 24 instants, 48 differences"
    assert sum("cloud" in line and 'job="a"' in line for line in out[:-1]) == 24, out[:3]
    assert sum("mon" in line and 'job="b"' in line for line in out[:-1]) == 24, out[:3]


@pytest.mark.parametrize(
    ("cloud", "mon", "differences"),
    [([], [], 0), ([], [_row(0, host="ops")], 24), ([_row(0, host="ops")], [], 24)],
    ids=["empty against empty", "empty against a row", "a row against empty"],
)
def test_an_empty_result_matches_an_empty_result_alone(monkeypatch, tmp_path, capsys, cloud, mon, differences):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    _Stacks(monkeypatch, _by_stack({"cloud": cloud, "mon": mon}))
    rc, out = _run(capsys)
    assert rc == (1 if differences else 0)
    assert out[-1] == f"compare: 1 nodes × 24 instants, {differences} differences"


@pytest.mark.parametrize("stack", ["cloud", "mon"])
@pytest.mark.parametrize(
    "fault",
    [_refusal(503), _refusal(401), OSError("connection reset"), b"<html>bad gateway</html>", b'{"status": "success", "data": {}}'],
    ids=["a 5xx", "a 4xx", "unreachable", "a malformed body", "a body without a result"],
)
def test_a_stack_that_cannot_answer_ends_the_run_naming_it_never_as_a_match(monkeypatch, tmp_path, capsys, stack, fault):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    other = "mon" if stack == "cloud" else "cloud"
    stacks = _Stacks(monkeypatch, lambda s, path, expr, time: fault if s == stack else [])
    rc, out = _run(capsys)
    assert rc == 2
    assert out[-1].startswith(f"compare: failed: {stack} ") and "r-up" in out[-1], out[-1]
    assert other not in out[-1].split(":")[2], out[-1]
    assert len(stacks.requests) <= 2, "the run ends at the stack's first failed answer"


def test_the_three_exclusions_are_by_name_so_a_prefix_or_a_prefixed_name_still_counts(monkeypatch, tmp_path, capsys):
    """Rows for `zcrypto`, which the excluded name extends, `zcrypto-red` and `zcrypto-mon2`, which extends it, differ
    and count; a `zcrypto-mon` row differs and does not. A rule of the node's group and a direct-shipped rule are not
    sent at all."""
    _alerts(
        monkeypatch,
        tmp_path,
        _rule("r-up", "up"),
        _rule("zcrypto-mon-disk-low", "node_filesystem_avail_bytes", group="zcrypto-mon"),
        _rule("zcrypto-engine-error-logs", 'count_over_time({container="engine"} [5m])', loki=True),
    )

    def answer(stack, path, expr, time):
        rows = [_row(1, host=h) for h in ("zcrypto", "zcrypto-red", "zcrypto-mon2", "zcrypto-mon")]
        return rows if stack == "cloud" else [_row(2, host=r["metric"]["host"]) for r in rows]

    stacks = _Stacks(monkeypatch, answer)
    rc, out = _run(capsys)
    assert rc == 1
    assert out[-1] == "compare: 1 nodes × 24 instants, 72 differences"
    hosts = Counter(re.search(r'host="([^"]+)"', line).group(1) for line in out[:-1])
    assert hosts == {"zcrypto": 24, "zcrypto-red": 24, "zcrypto-mon2": 24}, hosts
    assert {r.expr for r in stacks.requests} == {"up"}


def test_every_request_to_either_stack_carries_one_of_the_days_24_hour_tops_in_epoch_seconds(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"), _rule("r-logs", 'count_over_time({host="ops"} [5m])', loki=True))
    stacks = _Stacks(monkeypatch)
    rc, out = _run(capsys)
    assert rc == 0 and out[-1] == "compare: 2 nodes × 24 instants, 0 differences"
    expected = Counter(
        (stack, expr, str(t))
        for stack in ("cloud", "mon")
        for expr in ("up", 'count_over_time({host="ops"} [5m])')
        for t in INSTANTS
    )
    assert Counter((r.stack, r.expr, r.time) for r in stacks.requests) == expected
    assert all(re.fullmatch(r"\d{10}", r.time) for r in stacks.requests)


@pytest.mark.parametrize("ahead", [0, 1], ids=["today", "tomorrow"])
def test_a_day_that_has_not_ended_is_refused_before_any_query(monkeypatch, tmp_path, capsys, ahead):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)
    day = (datetime.now(timezone.utc).date() + timedelta(days=ahead)).isoformat()
    rc, out = _run(capsys, ("--day", day))
    assert rc == 2
    assert out == [f"compare: failed: --day {day} has not ended in UTC"], out
    assert stacks.requests == []


def test_the_preceding_utc_day_is_the_default(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)
    rc, out = _run(capsys, ())
    assert rc == 0
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    first = int(datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=timezone.utc).timestamp())
    assert {r.time for r in stacks.requests} == {str(first + 3600 * i) for i in range(24)}


def test_every_request_carries_its_30_s_timeout(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)
    _run(capsys)
    assert stacks.requests and all(r.timeout == 30 for r in stacks.requests)


def _rules() -> list[dict]:
    return yaml.safe_load(_ALERTS.read_text(encoding="utf-8"))["rules"]


def _listing() -> list[str]:
    """The measured basis's listing, as the spec prints it: a Loki node selecting a direct shipper's stream."""
    return [
        r["uid"]
        for r in _rules()
        for d in r["data"]
        if "LOKI" in str(d.get("datasourceUid")) and any(s in d["model"]["expr"] for s in _DIRECT_SELECTORS)
    ]


def test_the_direct_shipped_rules_are_the_measured_basis_listing_and_the_other_two_exclusions_are_one_name_each():
    assert sorted(_listing()) == sorted(DIRECT_SHIPPED)
    assert sorted(gc.DIRECT_SHIPPED_RULES) == sorted(DIRECT_SHIPPED)
    assert gc.EXCLUDED_GROUPS == ("zcrypto-mon",)
    assert gc.EXCLUDED_HOSTS == ("zcrypto-mon",)


def test_the_walk_sends_every_query_node_but_the_three_exclusions(monkeypatch, capsys):
    """The (expression, path) pairs each stack is sent at each instant, with their repeats, against the pairs the rule
    file itself holds less the group `zcrypto-mon` and the listed rules -- both written here, never the script's."""
    expected: Counter[tuple[str, str]] = Counter()
    for rule in _rules():
        if rule["ruleGroup"] == "zcrypto-mon" or rule["uid"] in DIRECT_SHIPPED:
            continue
        for node in rule["data"]:
            if node["datasourceUid"] == PROM:
                expected[(node["model"]["expr"], PROM_PATH)] += 1
            elif node["datasourceUid"] == LOKI:
                expected[(node["model"]["expr"], LOKI_PATH)] += 1
    assert {path for _, path in expected} == {PROM_PATH, LOKI_PATH}
    stacks = _Stacks(monkeypatch)
    rc, out = _run(capsys)
    assert rc == 0
    assert out == [f"compare: {sum(expected.values())} nodes × 24 instants, 0 differences"]
    for stack in ("cloud", "mon"):
        for instant in INSTANTS:
            sent = Counter((r.expr, r.path) for r in stacks.requests if r.stack == stack and r.time == str(instant))
            assert sent == expected, (stack, instant)
    assert {(r.path, r.ds_uid) for r in stacks.requests} == {(PROM_PATH, "grafanacloud-prom"), (LOKI_PATH, "grafanacloud-logs")}


def test_the_difference_line_names_the_rule_the_node_the_instant_and_what_differs(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up", ref="B"))
    _Stacks(monkeypatch, _by_stack({"cloud": [_row(1, host="ops")], "mon": [_row(3, host="ops")]}))
    rc, out = _run(capsys)
    assert rc == 1
    assert out[0] == 'r-up B 2026-09-30T00:00Z value cloud=1.0 mon=3.0 {host="ops"}', out[0]
    assert out[23].startswith("r-up B 2026-09-30T23:00Z ")


def test_a_date_the_flag_cannot_parse_is_a_failure_before_any_query(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)
    rc, out = _run(capsys, ("--day", "yesterday"))
    assert rc == 2 and out[-1].startswith("compare: failed: --day ") and stacks.requests == []


def test_a_stack_table_without_both_stacks_is_a_failure_before_any_query(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)
    monkeypatch.setattr(gc.grafana_auth, "STACKS", {"cloud": gc.grafana_auth.STACKS["cloud"]})
    rc, out = _run(capsys)
    assert rc == 2 and out == ["compare: failed: the stack table holds 1 stack, not two"] and stacks.requests == []


def test_a_token_the_vault_cannot_give_is_a_failure_naming_the_stack_not_a_traceback(monkeypatch, tmp_path, capsys):
    _alerts(monkeypatch, tmp_path, _rule("r-up", "up"))
    stacks = _Stacks(monkeypatch)

    def refuse(name, vault_file):
        if name == gc.grafana_auth.STACKS["mon"].token_var:
            raise FileNotFoundError(vault_file)
        return TOKEN

    monkeypatch.setattr(gc.grafana_auth, "vault_var", refuse)
    rc, out = _run(capsys)
    assert rc == 2 and out[-1].startswith("compare: failed: mon token") and stacks.requests == []


def test_the_instants_are_the_24_hour_tops_of_the_day():
    assert gc.instants(date(2026, 9, 30)) == INSTANTS
