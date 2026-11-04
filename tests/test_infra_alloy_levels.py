"""Each host's level stages after its parse, driven over the line shapes its sources print. The model reads the
configs' own selectors; where an `alloy` binary is on PATH the same blocks also run through Alloy itself."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.alloy_text import live_alloy_text
from tests.skip_gates import no_binary
from tests.test_infra_alloy_stages import (
    ALLOY_CONFIGS,
    _alloy_run_command,
    _assigned,
    _blocks,
    _parse_body,
    _stage_blocks,
    _unquoted,
)

REPO = Path(__file__).resolve().parents[1]
CONFIGS = {host: REPO / f"infra/ansible/roles/{host}/files/config.alloy" for host in ("mon", "hc", "ops", "capture", "cache")} | {
    "nas": REPO / "infra/nas/config.alloy"
}
DROP = "DROP"


class Fixture(NamedTuple):
    id: str
    host: str
    labels: dict[str, str]
    line: str
    expected: str | None


# The labels are the ones the level stages see, a level among them where the host's parse set one; numbers are filled
# in, and an address or a user name is a documentation one.
FIXTURES: list[Fixture] = [
    Fixture(
        "mon_selfcheck_ok",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> pinged",
        "INFO",
    ),
    Fixture(
        "mon_selfcheck_fail",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=FAIL (unreadable: URLError) fleet=FAIL (unreadable: URLError) loki=FAIL (unreadable: URLError) -> not pinging",
        "WARNING",
    ),
    Fixture(
        "mon_selfcheck_ping_failed",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> ping failed: URLError",
        "WARNING",
    ),
    Fixture(
        "mon_selfcheck_no_ping_url",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> healthy, and no ping URL is set",
        "WARNING",
    ),
    Fixture(
        "mon_grafana_panel_cancelled",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        r'logger=plugin.loki t=2026-11-03T16:37:12.345678901Z level=error msg="Partial data response error" dsName=Loki dsUid=grafanacloud-logs error="Get \"http://127.0.0.1:3100/loki/api/v1/query_range?direction=backward&end=1762187832000000000&query=sum%28rate%28%7Bhost%3D~%22zcrypto%22%7D%5B5m%5D%29%29&start=1762184232000000000&step=60000ms\": context canceled"',
        "INFO",
    ),
    Fixture(
        "mon_loki_mapping_cancelled",
        "mon",
        {"container": "loki", "level": "WARNING"},
        r'ts=2026-11-03T16:37:30.123456789Z caller=spanlogger.go:111 middleware=QueryShard.astMapperware org_id=fake user=fake level=warn msg="failed mapping AST" err="context canceled" query="sum(rate({host=~\"zcrypto|zcrypto-red|ops\"} [5m]))"',
        "INFO",
    ),
    Fixture(
        "mon_loki_scheduler_cancelled",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-03T16:33:01.123456789Z caller=scheduler_processor.go:111 component=querier msg="error processing requests from scheduler" err="rpc error: code = Canceled desc = context canceled" addr=127.0.0.1:9095',
        "INFO",
    ),
    Fixture(
        "mon_loki_scheduler_eof",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-03T16:33:02.123456789Z caller=scheduler_processor.go:175 component=querier org_id=fake msg="error notifying scheduler about finished query" err=EOF addr=127.0.0.1:9095',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_quotas_501",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=501 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81',
        "INFO",
    ),
    Fixture(
        "mon_grafana_quotas_500",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=500 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_contact_point_test",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver= integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"',
        "INFO",
    ),
    Fixture(
        "mon_grafana_notifier_failure",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver=logs integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_plugin_stop",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: terminated"',
        "INFO",
    ),
    Fixture(
        "mon_grafana_plugin_killed",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: killed"',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_stale_session",
        "mon",
        {"container": "grafana-server", "level": "WARNING"},
        'logger=authn.service t=2026-11-03T09:55:01.123456789Z level=warn msg="Failed to authenticate request" client=auth.client.session error="user token not found"',
        "WARNING",
    ),
    Fixture("mon_alloy_start", "mon", {"container": "alloy"}, "Alloy starting in Default Engine mode", "INFO"),
    Fixture("mon_caddy_env_home", "mon", {"container": "caddy"}, "HOME=/var/lib/caddy", "INFO"),
    Fixture(
        "mon_caddy_env_version",
        "mon",
        {"container": "caddy"},
        "caddy.Version=v2.11.7 h1:yj3Y5fYZGPkSvibBJ1sTWE4xC2fxztVyXEW8iIdUT0=",
        "INFO",
    ),
    Fixture(
        "mon_caddy_json_line",
        "mon",
        {"container": "caddy", "level": "INFO"},
        '{"level":"info","ts":1762187832.1234567,"logger":"http.log","msg":"server running","name":"srv0","protocols":["h1","h2","h3"]}',
        "INFO",
    ),
    Fixture(
        "mon_grafana_store_not_ready",
        "mon",
        {"container": "grafana-server"},
        "curl: (22) The requested URL returned error: 503",
        "WARNING",
    ),
    Fixture(
        "mon_grafana_store_unreachable",
        "mon",
        {"container": "grafana-server"},
        "curl: (7) Failed to connect to 127.0.0.1 port 9090 after 0 ms: Could not connect to server",
        "WARNING",
    ),
]

_STRING = r'"((?:[^"\\]|\\.)*)"'
_LABEL_OPS = {
    "=": lambda value, want: value == want,
    "!=": lambda value, want: value != want,
    "=~": lambda value, want: re.fullmatch(want, value) is not None,
    "!~": lambda value, want: re.fullmatch(want, value) is None,
}
_LINE_OPS = {
    "|=": lambda line, want: want in line,
    "!=": lambda line, want: want not in line,
    "|~": lambda line, want: re.search(want, line) is not None,
    "!~": lambda line, want: re.search(want, line) is None,
}


def _unquote(literal: str) -> str:
    """A LogQL string literal's value; LogQL refuses an escape other than these two, and so does the model."""
    assert re.fullmatch(r'(?:[^\\]|\\[\\"])*', literal), f"an escape LogQL refuses: {literal!r}"
    return re.sub(r"\\(.)", r"\1", literal)


def selector(text: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """A stream selector's label matchers and the line filters after it, each value unquoted."""
    m = re.fullmatch(r"\{([^}]*)\}((?:\s*(?:\|=|\|~|!=|!~)\s*" + _STRING + r")*)\s*", text)
    assert m, f"a selector the model does not read whole: {text!r}"
    matchers = re.findall(r"(\w+)\s*(=~|!~|!=|=)\s*" + _STRING, m.group(1))
    assert ", ".join(f'{k}{op}"{v}"' for k, op, v in matchers) == m.group(1).strip(), m.group(1)
    filters = re.findall(r"(\|=|\|~|!=|!~)\s*" + _STRING, m.group(2))
    return [(k, op, _unquote(v)) for k, op, v in matchers], [(op, _unquote(v)) for op, v in filters]


def _admits(text: str, labels: dict[str, str], line: str) -> bool:
    matchers, filters = selector(text)
    return all(_LABEL_OPS[op](labels.get(k, ""), v) for k, op, v in matchers) and all(_LINE_OPS[op](line, v) for op, v in filters)


def _top_blocks(host: str) -> list[str]:
    return _blocks(_parse_body(live_alloy_text(CONFIGS[host])), "stage.match")


def _keys_on_level(block: str) -> bool:
    return any(k == "level" for k, _, _ in selector(_assigned(block, "selector"))[0])


def _static_level(block: str) -> str | None:
    m = re.search(r'stage\.static_labels \{\s*values = \{ level = "([A-Z]+)" \}', block)
    return m and m.group(1)


def level_blocks(host: str) -> list[tuple[str, str]]:
    """The host's top-level blocks that key on `level`, in pipeline order: each selector with its level or DROP."""
    out = []
    for block in _top_blocks(host):
        if not _keys_on_level(block):
            continue
        if _assigned(block, "action") == "drop":
            out.append((_assigned(block, "selector"), DROP))
            continue
        assert len(_stage_blocks(block)) == 1 and _static_level(block), f"a level-keyed block the model does not read:\n{block}"
        out.append((_assigned(block, "selector"), _static_level(block)))
    return out


def model(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's level-keyed blocks leave on a line, None for none, DROP for a dropped line."""
    labels = dict(labels)
    for text, action in level_blocks(host):
        if _admits(text, labels, line):
            if action == DROP:
                return DROP
            labels["level"] = action
    return labels.get("level")


def _level_name(value: str | None) -> str | None:
    """The `level` label the fleet's template stage renders from a parsed value."""
    return value and {"warn": "WARNING", "fatal": "CRITICAL"}.get(value, value.upper())


def _logfmt_level(line: str) -> str | None:
    m = re.search(r"(?:^| )level=(\w+)(?: |$)", line)
    return _level_name(m and m.group(1))


def _parser(host: str, labels: dict[str, str], line: str) -> str | None:
    """The block of the host's that parsed the line: for a `cache-proxy` line the one named `cache_proxy`, whose own
    stages set that container label; else the first that keys on no level and admits it."""
    if labels.get("container") == "cache-proxy":
        return next(b for b in _top_blocks(host) if _assigned(b, "pipeline_name") == "cache_proxy")
    blocks = [b for b in _top_blocks(host) if not _keys_on_level(b)]
    return next((b for b in blocks if _admits(_assigned(b, "selector"), labels, line)), None)


def _parsed_level(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's parse leaves on a line, read through the expressions its config carries."""
    block = _parser(host, labels, line)
    if block is None:
        return None
    if "stage.logfmt" in block:
        return _logfmt_level(line)
    if "stage.json" in block:
        (key,) = re.findall(r'expressions = \{ level = "(\w+)" \}', block)
        try:
            record = json.loads(line)
        except ValueError:
            return None
        value = record.get(key) if isinstance(record, dict) else None
        return _level_name(value) if "stage.template" in block else value
    if _assigned(block, "pipeline_name") == "cache_proxy":
        (expression,) = [e for e in re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block) if "?P<level>" in e]
        m = re.search(_unquote(expression), line)
        return m and {"ALERT": "CRITICAL", "NOTICE": "INFO"}.get(m.group("level"), m.group("level"))
    (expression,) = re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block)
    m = re.search(_unquote(expression), line)
    if m is None:
        return None
    if "level" in m.groupdict():
        return m.group("level").upper()
    return {"#": "WARNING", ".": "DEBUG"}.get(m.group("mark"), "INFO")


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES])
def test_each_line_takes_the_level_its_source_reports(fixture):
    assert model(fixture.host, fixture.labels, fixture.line) == fixture.expected


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES])
def test_each_line_reaches_the_level_stages_as_its_hosts_parse_leaves_it(fixture):
    assert _parsed_level(fixture.host, fixture.labels, fixture.line) == fixture.labels.get("level")


def test_a_level_is_set_after_every_parse():
    for host in CONFIGS:
        blocks = _top_blocks(host)
        parses = [i for i, b in enumerate(blocks) if not _keys_on_level(b)]
        levels = [
            i for i, b in enumerate(blocks) if _static_level(b) or ("level", "=", "") in selector(_assigned(b, "selector"))[0]
        ]
        assert not levels or max(parses) < min(levels), f"{host}: a parse runs after a level stage, blocks {parses} and {levels}"


_RELEVELLED = {("level", "=", "ERROR"), ("level", "=~", "ERROR|WARNING")}


def test_a_trailing_stage_sets_a_level_only_where_none_is_set():
    for host in CONFIGS:
        for block in _top_blocks(host):
            if not _static_level(block):
                continue
            matchers = selector(_assigned(block, "selector"))[0]
            on_level = {m for m in matchers if m[0] == "level"}
            if on_level == {("level", "=", "")}:
                continue
            containers = [v for k, _, v in matchers if k == "container"]
            assert host == "mon" and on_level and on_level <= _RELEVELLED and _static_level(block) == "INFO", (host, block)
            assert containers and all(set(c.split("|")) <= {"grafana-server", "loki"} for c in containers), block


def test_no_alloy_config_reads_the_journal_priority():
    readers = [c.relative_to(REPO).as_posix() for c in ALLOY_CONFIGS if "__journal_priority" in live_alloy_text(c)]
    assert not readers, f"the journal's priority is no line's level: {readers}"


# --- the same blocks, through Alloy itself ---------------------------------------------------------------------------
def _echoed(out: str) -> list[tuple[str, str | None, str]]:
    """Each `loki.echo` line Alloy wrote: its file, its level label, its entry."""
    rows = []
    for line in out.splitlines():
        if "component_id=loki.echo.out" not in line:
            continue
        labels = re.search(r' labels="((?:[^"\\]|\\.)*)"', line).group(1)
        level = re.search(r'level=\\"([A-Z]+)\\"', labels)
        entry = _unquoted(re.search(r' entry="((?:[^"\\]|\\.)*)"', line).group(1))
        rows.append((re.search(r'filename=\\"([^"\\]+)\\"', labels).group(1), level and level.group(1), entry))
    return rows


def _run_alloy_groups(
    alloy: str, tmp_path: Path, groups: list[tuple[dict[str, str], list[str]]], blocks: list[str]
) -> list[list[tuple[str | None, str]]]:
    """Each group's lines in a file of its own under its labels, through `blocks` as committed, into `loki.echo`; each
    group's survivors, read off Alloy's output after a fixed window, in the order its file holds them."""
    files = [tmp_path / f"group-{i}.log" for i in range(len(groups))]
    targets = []
    for path, (labels, lines) in zip(files, groups, strict=True):
        path.write_text("".join(line + "\n" for line in lines))
        targets.append("{" + ", ".join([f'__path__ = "{path}"', *(f'{k} = "{v}"' for k, v in labels.items())]) + "}")
    (tmp_path / "harness.alloy").write_text(
        'loki.source.file "sample" {\n'
        f"  targets    = [{', '.join(targets)}]\n"
        "  forward_to = [loki.process.parse.receiver]\n"
        "}\n\n"
        'loki.process "parse" {\n'
        "  forward_to = [loki.echo.out.receiver]\n\n" + "\n".join(blocks) + "}\n\n"
        'loki.echo "out" {}\n'
    )
    cmd = _alloy_run_command(alloy, tmp_path, tmp_path / "harness.alloy")
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=6, cwd=tmp_path)
        streams = [done.stdout, done.stderr]
    except subprocess.TimeoutExpired as exc:  # Alloy runs until killed; the window is the read
        streams = [exc.stdout, exc.stderr]
    rows = _echoed("".join(s.decode() if isinstance(s, bytes) else (s or "") for s in streams))
    return [[(level, entry) for name, level, entry in rows if name == str(path)] for path in files]


@pytest.mark.parametrize("host", sorted({f.host for f in FIXTURES}))
def test_alloy_itself_agrees_with_the_level_model(host, tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    fixtures = [f for f in FIXTURES if f.host == host]
    keys = list(dict.fromkeys(json.dumps(f.labels, sort_keys=True) for f in fixtures))
    groups = [
        (json.loads(k) | {"host": host}, [f.line for f in fixtures if json.dumps(f.labels, sort_keys=True) == k]) for k in keys
    ]
    blocks = [b for b in _top_blocks(host) if _keys_on_level(b)]
    expected = [
        [(f.expected, f.line) for f in fixtures if json.dumps(f.labels, sort_keys=True) == k and f.expected != DROP] for k in keys
    ]
    assert _run_alloy_groups(shutil.which("alloy"), tmp_path, groups, blocks) == expected
