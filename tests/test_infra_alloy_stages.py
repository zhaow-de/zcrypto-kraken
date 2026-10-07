"""The Alloy log stages, read from the configs' own expressions and driven over the line shapes the
journals carry. Where an `alloy` binary is on PATH, the engine and container stages also run through Alloy itself over
the same samples."""

from __future__ import annotations

import json
import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.alloy_text import live_alloy_text
from tests.skip_gates import no_binary

REPO = Path(__file__).resolve().parents[1]
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"
HC_ALLOY = REPO / "infra/ansible/roles/hc/files/config.alloy"
ALERTS = REPO / "infra/grafana/alerts.yaml"

ESC = "\x1b"
PREFIX = "zcrypto-engine  | "
# The engine unit's journal, one line per writer and shape: `docker compose up` attached prefixes the
# service name (coloured or not), nautilus colours its lines unless told otherwise, the Python records
# and their tracebacks share the stream, and a traceback line can carry a nautilus-shaped stamp mid-line.
SAMPLE: list[tuple[str, tuple[str, str] | None]] = [
    (
        f"{ESC}[36m{PREFIX}{ESC}[0m{ESC}[1;33m2026-09-26T10:06:08.341550420Z [WARN] SHADOW-001.nautilus_kraken::execution::spot: "
        f"Ambiguous cancel failure for O-20260926-100440-001-000-1, awaiting reconciliation: HTTP transport error{ESC}[0m",
        (
            "WARNING",
            "2026-09-26T10:06:08.341550420Z [WARN] SHADOW-001.nautilus_kraken::execution::spot: Ambiguous cancel failure for "
            "O-20260926-100440-001-000-1, awaiting reconciliation: HTTP transport error",
        ),
    ),
    (
        f"{PREFIX}2026-09-16T13:05:23.100000000Z [ERROR] SHADOW-001.nautilus_kraken::execution::spot: Failed to connect execution "
        "client: Failed to load Kraken spot instruments",
        (
            "ERROR",
            "2026-09-16T13:05:23.100000000Z [ERROR] SHADOW-001.nautilus_kraken::execution::spot: Failed to connect execution client: "
            "Failed to load Kraken spot instruments",
        ),
    ),
    (f"{PREFIX}2026-09-26T10:06:09.000000001Z [INFO] SHADOW-001.nautilus_kraken::execution::spot: Loaded 4 Spot instruments", None),
    (f"{PREFIX}2026-09-26T10:06:09.000000002Z [DEBUG] SHADOW-001.nautilus_kraken::http::spot::client: Generated nonce", None),
    (
        f"{ESC}[36m{PREFIX}{ESC}[0m2026-09-26T10:06:10.500000000Z [WARN] SHADOW-001.nautilus_network::websocket: Backing off for 2.5s "
        "before reconnect attempt 3",
        None,
    ),
    (
        f"{PREFIX}2026-09-26T10:06:11.000000000Z [WARN] SHADOW-001.nautilus_network::websocket: Reconnect attempt 3 failed: dns error: "
        "Temporary failure in name resolution",
        (
            "WARNING",
            "2026-09-26T10:06:11.000000000Z [WARN] SHADOW-001.nautilus_network::websocket: Reconnect attempt 3 failed: dns error: "
            "Temporary failure in name resolution",
        ),
    ),
    (
        f"{PREFIX}2026-09-26 10:06:12,341 WARNING zcrypto.engine.executor [executor.py:123] - the venue order behind OT53PH could "
        "not be read -- its row keeps the state it has",
        None,
    ),
    (
        f"{PREFIX}2026-09-26 10:06:12,342 ERROR zcrypto.engine.node [node.py:88] - shadow node: run_cycle(2026-09-26T08:00:00+00:00) raised",
        None,
    ),
    (f"{PREFIX}Traceback (most recent call last):", None),
    (f'{PREFIX}  File "/app/cli/engine/node.py", line 88, in _invoke_cycle', None),
    (f"{PREFIX}ValueError: 2026-09-26T10:06:12.000000000Z [ERROR] looks nautilus-shaped but is a traceback line", None),
    (
        "2026-09-26T10:06:13.000000000Z [ERROR] SHADOW-001.nautilus_kraken::execution::spot: no compose prefix at all",
        ("ERROR", "2026-09-26T10:06:13.000000000Z [ERROR] SHADOW-001.nautilus_kraken::execution::spot: no compose prefix at all"),
    ),
]
EXPECTED = [expected for _, expected in SAMPLE if expected is not None]


def _alloy_string(literal: str) -> str:
    """An Alloy string literal's value: `\\\\` is a backslash and `\\"` a quote, nothing else escapes here."""
    return re.sub(r"\\(.)", r"\1", literal)


def _blocks(text: str, opener: str) -> list[str]:
    """Every top-level `<opener> {` block of a component body, braces balanced."""
    out, depth, cur = [], 0, []
    for line in text.splitlines(keepends=True):
        if depth == 0 and line.strip().startswith(opener):
            cur = []
        cur.append(line)
        depth += line.count("{") - line.count("}")
        if depth == 0 and line.strip() == "}" and cur[0].strip().startswith(opener):
            out.append("".join(cur))
            cur = []
    return out


def _parse_body(text: str) -> str:
    start = re.search(r'^loki\.process "parse" \{\n', text, re.M)
    assert start, 'no loki.process "parse" component'
    body = text[start.end() :]
    return body[: body.index("\n}\n")]


def _assigned(block: str, key: str) -> str | None:
    """The value the `<key> = "..."` line of `block` assigns; a commented-out copy opens with `//` and is not it."""
    for line in block.splitlines():
        if m := re.fullmatch(rf'{re.escape(key)}\s*=\s*"((?:[^"\\]|\\.)*)"', line.strip()):
            return _alloy_string(m.group(1))
    return None


def _engine_blocks() -> tuple[str, str]:
    """The nautilus stage and its sibling drop, in the order the pipeline runs them."""
    blocks = _blocks(_parse_body(live_alloy_text(CAPTURE_ALLOY)), "stage.match")
    stages = [b for b in blocks if _assigned(b, "pipeline_name") == "engine_nautilus"]
    drops = [b for b in blocks if _assigned(b, "action") == "drop" and "engine-nautilus" in (_assigned(b, "selector") or "")]
    assert len(stages) == 1 and len(drops) == 1, f"expected the nautilus stage and its drop, found {len(stages)} and {len(drops)}"
    return stages[0], drops[0]


def _expressions(block: str) -> list[str]:
    return [_alloy_string(m) for m in re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block)]


def model(line: str) -> tuple[str, str] | None:
    """The stage as Python `re` reads its expressions: strips, the shape's level, the two drops."""
    stage, drop = _engine_blocks()
    *strips, shape, backoff = _expressions(stage)
    assert len(strips) == 2, strips
    for strip in strips:
        line = re.sub(strip, "", line)
    m = re.search(shape, line)
    level = None
    if m:
        level = "WARNING" if m.group("level") == "WARN" else m.group("level")
    if re.search(backoff, line):
        return None
    selector = _assigned(drop, "selector")
    kept = selector and re.search(r'level!~"([^"]+)"', selector)
    assert kept, f"the sibling drop no longer keys on the level label: {selector}"
    if level is None or not re.fullmatch(kept.group(1), level):
        return None
    return level, line


def test_the_sample_carries_every_shape_the_stage_answers_for():
    raw = [line for line, _ in SAMPLE]
    assert any(ESC in line and "[WARN]" in line for line in raw)
    assert any("[INFO]" in line for line in raw) and any("[DEBUG]" in line for line in raw)
    assert any("Backing off" in line for line in raw)
    assert any(" WARNING zcrypto." in line for line in raw) and any(" ERROR zcrypto." in line for line in raw)
    assert any(line.startswith(PREFIX + "Traceback") for line in raw)
    assert any("ValueError: 2026" in line and "[ERROR]" in line for line in raw)
    assert len(EXPECTED) == 4


def test_the_engine_stage_keeps_nautilus_warnings_and_errors_alone():
    assert [model(line) for line, _ in SAMPLE] == [expected for _, expected in SAMPLE]


def test_the_engine_stage_labels_the_survivors_as_their_own_container():
    stage, drop = _engine_blocks()
    assert _assigned(stage, "selector") == '{container="zcrypto-engine"}', (
        "the stage no longer selects the unit's relabelled stream"
    )
    assert re.search(r'stage\.static_labels \{\s*values = \{ container = "engine-nautilus" \}', stage), stage
    assert _assigned(drop, "selector") == '{container="engine-nautilus", level!~"WARNING|ERROR"}', drop


def test_the_journal_keep_rule_admits_the_engine_unit():
    rule = next(
        b
        for b in re.findall(r"^\s*rule \{(.*?)\n  \}", live_alloy_text(CAPTURE_ALLOY), re.M | re.S)
        if "__journal__systemd_unit" in b and '"keep"' in b
    )
    live = re.search(r'^\s*regex\s*=\s*"(.*?)"\s*$', rule, re.M)
    assert live, f"no live regex line in the journal keep rule: {rule!r}"
    regex = _alloy_string(live.group(1))
    assert re.fullmatch(regex, "zcrypto-engine.service;"), "the engine unit's journal is not admitted, so the stage reads nothing"
    assert not re.fullmatch(regex, "zcrypto-capture.service;"), "the capture unit would double-ingest the daemon's own records"


@pytest.mark.parametrize("uid", ["zcrypto-engine-error-logs", "zcrypto-engine-log-dead"])
def test_the_engine_log_rules_select_the_python_stream_by_exact_name(uid):
    """The nautilus lines page nothing: the paging rule keys on container="engine" by equality, so
    no regex there can widen onto `engine-nautilus`."""
    rule = next(r for r in yaml.safe_load(ALERTS.read_text())["rules"] if r["uid"] == uid)
    exprs = [q["model"]["expr"] for q in rule["data"] if q.get("datasourceUid") == "${GRAFANA_LOKI_DS_UID}"]
    assert exprs, f"{uid} reads no Loki query"
    for expr in exprs:
        assert 'container="engine"' in expr and "engine-nautilus" not in expr and 'container=~"' not in expr, expr


# --- the same stage, through Alloy itself ---------------------------------------------------------
def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


_LOGFMT_ESCAPES = {"n": "\n", "t": "\t", "r": "\r"}


def _unquoted(value: str) -> str:
    return re.sub(r"\\(.)", lambda m: _LOGFMT_ESCAPES.get(m.group(1), m.group(1)), value)


def _run_alloy(
    alloy: str, tmp_path: Path, lines: list[str], blocks: list[str], labels: dict[str, str], carried: str
) -> list[tuple[str | None, str]]:
    """Feed `lines` through `loki.source.file` under `labels` -> `blocks` as committed -> `loki.echo`, and read each
    survivor's `level` label and entry off Alloy's stdout after a fixed window; every survivor carries `carried`."""
    sample = tmp_path / "sample.log"
    sample.write_text("".join(line + "\n" for line in lines))
    targets = "".join(f', {name} = "{value}"' for name, value in labels.items())
    (tmp_path / "harness.alloy").write_text(
        'loki.source.file "sample" {\n'
        f'  targets    = [{{__path__ = "{sample}"{targets}}}]\n'
        "  forward_to = [loki.process.parse.receiver]\n"
        "}\n\n"
        'loki.process "parse" {\n'
        "  forward_to = [loki.echo.out.receiver]\n\n" + "\n".join(blocks) + "}\n\n"
        'loki.echo "out" {}\n'
    )
    cmd = [
        alloy,
        "run",
        "--storage.path",
        str(tmp_path / "storage"),
        "--server.http.listen-addr",
        f"127.0.0.1:{_free_port()}",
        str(tmp_path / "harness.alloy"),
    ]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=6, cwd=tmp_path)
        streams = [done.stdout, done.stderr]
    except subprocess.TimeoutExpired as exc:  # Alloy runs until killed; the window is the read
        streams = [exc.stdout, exc.stderr]
    # Alloy's component logs, loki.echo's lines among them, go to stderr; read both streams.
    out = "".join(s.decode() if isinstance(s, bytes) else (s or "") for s in streams)
    survivors = []
    for line in out.splitlines():
        if "component_id=loki.echo.out" not in line:
            continue
        entry = _unquoted(re.search(r' entry="((?:[^"\\]|\\.)*)"', line).group(1))
        echoed = re.search(r' labels="((?:[^"\\]|\\.)*)"', line).group(1)
        assert carried in echoed, echoed
        level = re.search(r'level=\\"([A-Z]+)\\"', echoed)
        survivors.append((level.group(1) if level else None, entry))
    return survivors


def test_alloy_itself_agrees_with_the_model(tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    lines = [line for line, _ in SAMPLE]
    labels = {"container": "zcrypto-engine", "host": "zcrypto"}
    assert (
        _run_alloy(shutil.which("alloy"), tmp_path, lines, list(_engine_blocks()), labels, 'container=\\"engine-nautilus\\"')
        == EXPECTED
    )


# --- the dead-man node's container stage: the ping path's key written over, each JSON record's level lifted --------
PING_KEY = "abcdefghijklmnopqrstuv"
CHECK_UUID = "0b1c2d3e-4f50-4617-8293-a4b5c6d7e8f9"
STAMP = "2026-10-05T18:01:02.345678+00:00"
# The clone's JSON formatter writes `time`, `level`, `logger` and `message`, and `exception` beside a traceback.
HC_DISPATCH_FAILURE = json.dumps(
    {
        "time": STAMP,
        "level": "ERROR",
        "logger": "hc.api.models",
        "message": "Notification failed: check 'zcrypto-capture', slack channel 1a2b3c4d: Received status code 404",
    }
)
HC_SAMPLE = [
    json.dumps(
        {
            "time": STAMP,
            "level": "ERROR",
            "logger": "django.request",
            "message": f"Internal Server Error: /ping/{PING_KEY}/zcrypto-capture",
            "exception": 'Traceback (most recent call last):\n  File "/opt/healthchecks/hc/api/views.py", line 201, in _ping\n'
            "django.db.utils.OperationalError: database is locked",
        }
    ),
    # A line the JSON formatter did not write, in the text formatter's shape.
    f"2026-10-05 18:01:02,345 ERROR django.request Internal Server Error: /ping/{PING_KEY}/zcrypto-capture",
    json.dumps(
        {"time": STAMP, "level": "ERROR", "logger": "django.request", "message": f"Internal Server Error: /ping/{CHECK_UUID}/fail"}
    ),
    json.dumps(
        {"time": STAMP, "level": "INFO", "logger": "hc", "message": "'zcrypto-capture' goes down\n  1a2b3c4d (slack) OK in 0.3s"}
    ),
    HC_DISPATCH_FAILURE,
]
HC_EXPECTED = [
    ("ERROR", HC_SAMPLE[0].replace(PING_KEY, "REDACTED")),
    (None, HC_SAMPLE[1].replace(PING_KEY, "REDACTED")),
    ("ERROR", HC_SAMPLE[2].replace(CHECK_UUID, "REDACTED")),
    ("INFO", HC_SAMPLE[3]),
    ("ERROR", HC_DISPATCH_FAILURE),
]


def _hc_match() -> str:
    blocks = _blocks(_parse_body(live_alloy_text(HC_ALLOY)), "stage.match")
    matches = [b for b in blocks if _assigned(b, "selector") == '{container="hc"}']
    assert len(matches) == 1, f'expected one {{container="hc"}} match, found {len(matches)}'
    return matches[0]


def _stage_blocks(match: str) -> list[str]:
    """The stages inside a `stage.match`, in the order the pipeline runs them."""
    return _blocks("".join(match.splitlines(keepends=True)[1:-1]), "stage.")


def _map(stage: str, key: str) -> dict[str, str]:
    m = re.search(rf"^\s*{key}\s*=\s*\{{(.*?)\}}\s*$", stage, re.M)
    assert m, f"no {key} map in {stage!r}"
    return dict(re.findall(r'(\w+)\s*=\s*"([^"]*)"', m.group(1)))


def _replaced(line: str, expression: str, replace: str) -> str:
    """Every capture group of every match written over with `replace`, as the engine's replace stage does."""
    out, last = [], 0
    for m in re.finditer(expression, line):
        for group in range(1, m.re.groups + 1):
            start, end = m.span(group)
            if start >= 0:
                out += [line[last:start], replace]
                last = end
    return "".join(out) + line[last:]


def hc_model(line: str) -> tuple[str | None, str]:
    """The container's match as Python reads its stages: the replace, the JSON extract, and a label lifted only where
    a `stage.labels` names it."""
    extracted, labels = {}, {}
    for stage in _stage_blocks(_hc_match()):
        kind = stage.split("{", 1)[0].strip()
        if kind == "stage.replace":
            line = _replaced(line, _assigned(stage, "expression"), _assigned(stage, "replace") or "")
        elif kind == "stage.json":
            try:
                record = json.loads(line)
            except ValueError:
                continue
            extracted |= {
                name: str(record[path or name]) for name, path in _map(stage, "expressions").items() if (path or name) in record
            }
        elif kind == "stage.labels":
            labels |= {
                name: extracted[source or name] for name, source in _map(stage, "values").items() if (source or name) in extracted
            }
        else:
            raise AssertionError(f"the model does not read {kind}")
    return labels.get("level"), line


def test_the_sample_carries_the_clones_record_shapes():
    assert [json.loads(line)["level"] for line in HC_SAMPLE if line.startswith("{")] == ["ERROR", "ERROR", "INFO", "ERROR"]
    assert sum(f"/ping/{PING_KEY}/zcrypto-capture" in line for line in HC_SAMPLE) == 2
    assert sum(f"/ping/{CHECK_UUID}/fail" in line for line in HC_SAMPLE) == 1
    assert list(json.loads(HC_DISPATCH_FAILURE)) == ["time", "level", "logger", "message"]


def test_the_container_stage_writes_over_the_ping_key_and_lifts_each_json_records_level():
    assert [hc_model(line) for line in HC_SAMPLE] == HC_EXPECTED
    for _, line in map(hc_model, HC_SAMPLE):
        assert PING_KEY not in line and CHECK_UUID not in line, line


def test_the_container_stage_keeps_the_slug_and_passes_the_summary_and_the_dispatch_failure_unchanged():
    out = [line for _, line in map(hc_model, HC_SAMPLE)]
    assert [line.count("/ping/REDACTED/zcrypto-capture") for line in out[:2]] == [1, 1]
    assert out[3:] == HC_SAMPLE[3:]


def test_alloy_itself_agrees_with_the_container_model(tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    labels = {"container": "hc", "host": "zcrypto-hc"}
    survivors = _run_alloy(shutil.which("alloy"), tmp_path, HC_SAMPLE, [_hc_match()], labels, 'container=\\"hc\\"')
    assert survivors == [hc_model(line) for line in HC_SAMPLE]


# --- every timestamp stage keeps the journal's time on a miss --------------------------------------
ALLOY_CONFIGS = sorted((REPO / "infra").rglob("*.alloy"))


def _nested_blocks(text: str, opener: str) -> list[str]:
    """Every `<opener> {` block at any depth, braces balanced."""
    out, cur, depth = [], None, 0
    for line in text.splitlines(keepends=True):
        if cur is None and line.strip().startswith(opener):
            cur, depth = [], 0
        if cur is not None:
            cur.append(line)
            depth += line.count("{") - line.count("}")
            if depth == 0:
                out.append("".join(cur))
                cur = None
    return out


@pytest.mark.parametrize("config", ALLOY_CONFIGS, ids=lambda p: p.relative_to(REPO).as_posix())
def test_every_timestamp_stage_keeps_the_journal_time_on_a_miss(config):
    for block in _nested_blocks(config.read_text(), "stage.timestamp"):
        assert re.search(r'^\s*action_on_failure\s*=\s*"skip"\s*$', block, re.M), f"{config.relative_to(REPO)}:\n{block}"


def test_the_timestamp_guard_reads_the_stages_the_tree_carries():
    found = {c.relative_to(REPO).as_posix(): len(_nested_blocks(c.read_text(), "stage.timestamp")) for c in ALLOY_CONFIGS}
    assert sum(found.values()) >= 2, f"the guard above ran over no timestamp stage: {found}"
