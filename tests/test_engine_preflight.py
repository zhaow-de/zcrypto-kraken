from __future__ import annotations

import json
import shutil
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.config import ConfigError, load_config
from cli.engine.command import engine_app
from cli.engine.execgate import _verified_nautilus_versions
from cli.engine.journal import to_json
from cli.engine.store import BASKET, GRID_INTERVALS
from tests.test_engine_journal import _record

runner = CliRunner()

_HELD_VERSION = min(_verified_nautilus_versions())
_FIELDS = {"config", "verified", "stores_missing", "journal", "version", "nautilus", "ok"}


@pytest.fixture(autouse=True)
def _nautilus_held(monkeypatch):
    monkeypatch.setattr("cli.engine.preflight._installed_nautilus_version", lambda: _HELD_VERSION)


def _store_file(root: Path, symbol: str, interval: int) -> Path:
    base, quote = symbol.split("/")
    return root / base / quote / f"{interval}.parquet"


def _write_config(work: Path, store_dir: str, journal_dir: str) -> None:
    (work / "zcrypto.toml").write_text(
        f"[zcrypto.engine]\nstore_dir = {json.dumps(store_dir)}\njournal_dir = {json.dumps(journal_dir)}\n"
    )


def _write_record(state: Path, day: str) -> Path:
    path = state / "journal" / day / "cycle-20.json"
    path.parent.mkdir(parents=True)
    path.write_text(to_json(_record()))
    return path


@pytest.fixture
def host(tmp_path, monkeypatch) -> tuple[Path, Path]:
    state = tmp_path / "state"
    work = tmp_path / "work"
    state.mkdir()
    work.mkdir()
    _write_config(work, f"{state}/store", f"{state}/journal")
    for symbol in BASKET:
        for interval in GRID_INTERVALS:
            path = _store_file(state / "store", symbol, interval)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")
    _write_record(state, "2026-10-07")
    monkeypatch.chdir(work)
    return state, work


def _preflight(state: Path) -> tuple[int, dict]:
    result = runner.invoke(engine_app, ["preflight", "--state-dir", str(state)])
    lines = result.stdout.strip().splitlines()
    assert lines, f"exit {result.exit_code}, no stdout: {result.output}"
    return result.exit_code, json.loads(lines[-1])


def _all_stores() -> set[str]:
    return {f"{symbol}@{interval}" for symbol in BASKET for interval in GRID_INTERVALS}


def test_preflight_happy_path_exits_0_with_the_json_shape(host):
    state, _ = host
    code, line = _preflight(state)
    assert set(line) == _FIELDS
    assert line == {
        "config": "ok",
        "verified": True,
        "stores_missing": [],
        "journal": "ok",
        "version": version("zcrypto"),
        "nautilus": _HELD_VERSION,
        "ok": True,
    }
    assert code == 0


def test_preflight_refuses_a_working_directory_without_zcrypto_toml(host):
    state, work = host
    (work / "zcrypto.toml").unlink()
    code, line = _preflight(state)
    assert code == 1
    assert "no zcrypto.toml" in line["config"]
    assert line["stores_missing"] is None
    assert line["journal"] is None
    assert line["ok"] is False


def test_preflight_refuses_a_config_the_loader_rejects(host):
    state, work = host
    (work / "zcrypto.toml").write_text(f"[zcrypto.engine]\nstore_dir = 5\njournal_dir = {json.dumps(f'{state}/journal')}\n")
    with pytest.raises(ConfigError) as refused:
        load_config()
    code, line = _preflight(state)
    assert code == 1
    assert str(refused.value) in line["config"]
    assert line["stores_missing"] is None
    assert line["journal"] is None


@pytest.mark.parametrize("key", ["journal_dir", "store_dir"])
@pytest.mark.parametrize("shape", ["outside", "a parent segment", "a prefix sibling"])
def test_preflight_refuses_a_config_whose_dirs_lie_outside_the_state_dir(host, tmp_path, key, shape):
    state, work = host
    leaf = key.removesuffix("_dir")
    placed = {
        "outside": f"{tmp_path}/elsewhere/{leaf}",
        "a parent segment": f"{state}/../elsewhere/{leaf}",
        "a prefix sibling": f"{state}-old/{leaf}",
    }[shape]
    dirs = {"store_dir": f"{state}/store", "journal_dir": f"{state}/journal", key: placed}
    _write_config(work, dirs["store_dir"], dirs["journal_dir"])
    code, line = _preflight(state)
    assert code == 1
    assert line["config"] != "ok"
    assert key in line["config"]
    assert line["stores_missing"] is None
    assert line["journal"] is None


def test_preflight_refuses_a_relative_store_dir_outside_a_dot_state_dir(host):
    _, work = host
    _write_config(work, "../elsewhere/store", "../elsewhere/journal")
    code, line = _preflight(Path("."))
    assert code == 1
    assert "store_dir" in line["config"]
    assert line["stores_missing"] is None
    assert line["journal"] is None


def test_preflight_refuses_an_unverified_library_version(host, monkeypatch):
    state, _ = host
    monkeypatch.setattr("cli.engine.preflight._verified_nautilus_versions", lambda: frozenset({"0.0.0"}))
    code, line = _preflight(state)
    assert code == 1
    assert line["verified"] is False
    assert (line["config"], line["stores_missing"], line["journal"]) == ("ok", [], "ok")


def test_preflight_lists_every_missing_store(host):
    state, _ = host
    removed = [(BASKET[0], GRID_INTERVALS[0]), (BASKET[-1], GRID_INTERVALS[-1])]
    for symbol, interval in removed:
        _store_file(state / "store", symbol, interval).unlink()
    code, line = _preflight(state)
    assert code == 1
    assert sorted(line["stores_missing"]) == sorted(f"{symbol}@{interval}" for symbol, interval in removed)


def test_preflight_reads_the_stores_under_the_configured_store_dir(host):
    state, _ = host
    for symbol in BASKET:
        for interval in GRID_INTERVALS:
            moved = _store_file(state, symbol, interval)
            moved.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(_store_file(state / "store", symbol, interval), moved)
    code, line = _preflight(state)
    assert code == 1
    assert set(line["stores_missing"]) == _all_stores()
    assert len(line["stores_missing"]) == 24


def test_preflight_refuses_an_unloadable_newest_cycle_record(host):
    state, _ = host
    newest = state / "journal" / "2026-10-07" / "cycle-20.json"
    text = newest.read_text()
    newest.write_text(text[: len(text) // 2])
    code, line = _preflight(state)
    assert code == 1
    assert line["journal"] not in ("ok", "none", None)
    assert "invalid journal JSON" in line["journal"]

    _write_record(state, "2026-10-06")
    code, line = _preflight(state)
    assert code == 1
    assert "invalid journal JSON" in line["journal"]


def test_preflight_refuses_an_unreadable_newest_cycle_record(host):
    state, _ = host
    newest = state / "journal" / "2026-10-08" / "cycle-0.json"
    newest.mkdir(parents=True)
    with pytest.raises(IsADirectoryError) as refused:
        newest.read_text()
    code, line = _preflight(state)
    assert code == 1
    assert line["journal"] == f"{newest}: {refused.value}"
    assert line["ok"] is False


def test_preflight_refuses_a_newest_cycle_record_that_is_not_utf8(host):
    state, _ = host
    newest = state / "journal" / "2026-10-07" / "cycle-20.json"
    newest.write_bytes(b"\xff\xfe{}")
    with pytest.raises(UnicodeDecodeError) as refused:
        newest.read_text()
    code, line = _preflight(state)
    assert code == 1
    assert line["journal"] == f"{newest}: {refused.value}"


@pytest.mark.parametrize("emptied", ["journal", "journal/2026-10-07"], ids=["absent", "empty"])
def test_preflight_reports_journal_none_without_a_record(host, emptied):
    state, _ = host
    shutil.rmtree(state / emptied)
    code, line = _preflight(state)
    assert line["journal"] == "none"
    assert line["ok"] is True
    assert code == 0


def test_preflight_refuses_a_journal_dir_with_entries_and_no_cycle_record(host):
    state, _ = host
    (state / "journal" / "2026-10-07" / "cycle-20.json").unlink()
    code, line = _preflight(state)
    assert line["journal"] == f"{state / 'journal'}: no cycle record found"
    assert line["ok"] is False
    assert code == 1


def test_preflight_refuses_a_journal_dir_it_cannot_list(host):
    state, _ = host
    journal = state / "journal"
    shutil.rmtree(journal)
    journal.write_text("")
    with pytest.raises(NotADirectoryError) as refused:
        any(journal.iterdir())
    code, line = _preflight(state)
    assert line["journal"] == f"{journal}: {refused.value}"
    assert code == 1


def _tree(root: Path) -> dict[str, int]:
    return {str(p.relative_to(root)): p.stat().st_mtime_ns for p in [root, *root.rglob("*")]}


def test_preflight_writes_nothing(host):
    state, work = host
    before = (_tree(state), _tree(work))
    code, _ = _preflight(state)
    assert code == 0
    assert (_tree(state), _tree(work)) == before
