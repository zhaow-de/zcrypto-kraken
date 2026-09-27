"""The Alloy log stages, read from the configs' own expressions and driven over the line shapes the
journals carry: the primary's engine-unit stage keeps nautilus's [WARN]/[ERROR] lines alone, under a
label no paging rule selects, and the timestamp stages keep a journal's time on a miss. Where an
`alloy` binary is on PATH, the engine stage also runs through Alloy itself over the same sample."""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.skip_gates import no_binary

REPO = Path(__file__).resolve().parents[1]
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"
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
    blocks = [b for b in _blocks(_parse_body(CAPTURE_ALLOY.read_text()), "stage.match") if "engine" in b]
    assert len(blocks) == 2, f"expected the nautilus stage and its drop, found {len(blocks)}"
    stage, drop = blocks
    assert _assigned(stage, "pipeline_name") == "engine_nautilus" and _assigned(drop, "action") == "drop"
    return stage, drop


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
        for b in re.findall(r"rule \{(.*?)\n  \}", CAPTURE_ALLOY.read_text(), re.S)
        if "__journal__systemd_unit" in b and '"keep"' in b
    )
    regex = _alloy_string(re.search(r'regex\s*=\s*"(.*?)"\n', rule).group(1))
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


def _run_alloy(alloy: str, tmp_path: Path) -> list[tuple[str, str]]:
    """Feed the sample through `loki.source.file` -> the two engine blocks as committed -> `loki.echo`,
    and read the survivors and their labels off Alloy's stdout after a fixed window."""
    stage, drop = _engine_blocks()
    sample = tmp_path / "sample.log"
    sample.write_text("".join(line + "\n" for line, _ in SAMPLE))
    (tmp_path / "harness.alloy").write_text(
        'loki.source.file "sample" {\n'
        f'  targets    = [{{__path__ = "{sample}", container = "zcrypto-engine", host = "zcrypto"}}]\n'
        "  forward_to = [loki.process.parse.receiver]\n"
        "}\n\n"
        'loki.process "parse" {\n'
        "  forward_to = [loki.echo.out.receiver]\n\n"
        f"{stage}\n{drop}"
        "}\n\n"
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
        entry = re.search(r' entry="((?:[^"\\]|\\.)*)"', line).group(1).replace('\\"', '"')
        labels = re.search(r' labels="((?:[^"\\]|\\.)*)"', line).group(1)
        assert 'container=\\"engine-nautilus\\"' in labels, labels
        survivors.append((re.search(r'level=\\"([A-Z]+)\\"', labels).group(1), entry))
    return survivors


def test_alloy_itself_agrees_with_the_model(tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    assert _run_alloy(shutil.which("alloy"), tmp_path) == EXPECTED


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
