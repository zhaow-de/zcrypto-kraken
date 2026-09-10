"""The deploy-log audit's two arms: the rows that landed inside a published API-impacting window, and the engine rows that landed outside the 4-hourly gap."""

from __future__ import annotations

import importlib.util
import json
import pathlib
import sys
import urllib.error

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "deploy-log-audit.py"
FEED = _ROOT / "tests" / "fixtures" / "kraken_scheduled_maintenances.json"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


audit = _load(_SCRIPT, "deploy_log_audit")


def _row(ts: str, *, limit: str = "zcrypto", tags: str = "", rc: int = 0) -> dict:
    return {"ts": ts, "limit": limit, "tags": tags, "rc": rc, "playbook": "site.yml"}


def _log(tmp_path: pathlib.Path, rows: list[dict]) -> str:
    path = tmp_path / "deploy-log.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return str(path)


def test_api_impacting_reads_a_component_name_and_the_entrys_own_name():
    """An empty `components` is not an absent impact -- the second window carries it in its own name."""
    windows = audit.api_impacting(json.loads(FEED.read_text())["scheduled_maintenances"])
    assert [w["name"] for w in windows] == ["Beeks Maintenance", "REST API rate-limit change"]


def test_maintenance_counts_the_row_inside_an_api_impacting_window(tmp_path, capsys):
    """The second row sits inside the fixture's website window, which impacts no API and must not count."""
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit="nas"), _row("2026-08-20T01:00:00Z")])
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(FEED)]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["rows inside an API-impacting window 1 of 2", "  2026-08-28T23:40:17Z nas Beeks Maintenance"]


def test_maintenance_counts_none_when_every_row_sits_outside(tmp_path, capsys):
    log = _log(tmp_path, [_row("2026-08-29T03:00:00Z"), _row("2026-09-01T02:00:00Z")])
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(FEED)]) == 0
    assert capsys.readouterr().out.splitlines() == ["rows inside an API-impacting window 0 of 2"]


def test_engine_window_counts_the_rows_outside_the_gap(tmp_path, capsys):
    """First row is 600 s past a boundary, second is 300 s short of the next; the third clears both."""
    rows = [
        _row("2026-09-01T00:10:00Z", tags="engine"),
        _row("2026-09-01T03:55:00Z", tags="engine,ops", rc=1),
        _row("2026-09-01T01:00:00Z", tags="engine"),
    ]
    assert audit.main(["engine-window", "--log", _log(tmp_path, rows)]) == 0
    assert capsys.readouterr().out.strip() == "engine rows 3 outside window 2 failed 1"


def test_engine_window_counts_none_when_every_engine_row_sits_in_the_gap(tmp_path, capsys):
    """The capture row is outside the gap and belongs to no engine cycle, so the tag filter must drop it."""
    rows = [_row("2026-09-01T01:00:00Z", tags="engine"), _row("2026-09-01T00:10:00Z", tags="capture")]
    assert audit.main(["engine-window", "--log", _log(tmp_path, rows)]) == 0
    assert capsys.readouterr().out.strip() == "engine rows 1 outside window 0 failed 0"


def test_an_unreachable_feed_exits_2_rather_than_counting_zero(tmp_path, capsys, monkeypatch):
    def _unreachable(*_args, **_kwargs):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(audit, "fetch_maintenances", _unreachable)
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z")])
    assert audit.main(["maintenance", "--log", log]) == audit.EXIT_FEED_UNREACHABLE
    captured = capsys.readouterr()
    assert "feed unreachable" in captured.err
    assert captured.out == ""


def test_a_snapshot_reads_back_the_count_the_network_produced(tmp_path, capsys, monkeypatch):
    payload = json.loads(FEED.read_text())["scheduled_maintenances"]
    monkeypatch.setattr(audit, "fetch_maintenances", lambda *_a, **_k: payload)
    log = _log(tmp_path, [_row("2026-08-28T23:40:17Z", limit="nas")])
    snapshot = tmp_path / "feed.json"
    assert audit.main(["maintenance", "--log", log, "--snapshot", str(snapshot)]) == 0
    from_network = capsys.readouterr().out

    def _reached_the_network(*_args, **_kwargs):
        raise AssertionError("the --from-snapshot arm fetched the feed")

    monkeypatch.setattr(audit, "fetch_maintenances", _reached_the_network)
    assert audit.main(["maintenance", "--log", log, "--from-snapshot", str(snapshot)]) == 0
    assert capsys.readouterr().out == from_network


@pytest.mark.parametrize(
    "argv",
    [
        ["engine-window", "--from-snapshot", str(FEED)],
        ["maintenance", "--snapshot", "written.json", "--from-snapshot", str(FEED)],
    ],
)
def test_the_feed_flags_are_refused_where_they_would_do_nothing(tmp_path, argv):
    with pytest.raises(SystemExit) as raised:
        audit.main([*argv, "--log", _log(tmp_path, [_row("2026-09-01T01:00:00Z", tags="engine")])])
    assert raised.value.code == 2
