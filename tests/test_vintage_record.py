from __future__ import annotations

import ast
import base64
import errno
import fcntl
import gzip
import hashlib
import importlib
import io
import itertools
import json
import logging
import os
import re
import shutil
import stat
from collections import defaultdict
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from typer.testing import CliRunner

import cli.vintage.command as command_module
import cli.vintage.gauges as gauges_module
import cli.vintage.record as record_module
import cli.vintage.storage as storage_module
from cli.__main__ import app
from cli.capture.command import LOCKFILE_NAME
from cli.vintage.chain import Scan, chain, scan
from cli.vintage.credential import ApiKey
from cli.vintage.gauges import last_ok_value
from cli.vintage.record import RecordRefused, record_tick
from cli.vintage.sources import SOURCE_BY_ID, SOURCES
from cli.vintage.storage import create_exclusive, publish_tick
from tests.vintage_fixtures import BASE_TICK_START, SENTINEL_KEY, body, dumps_compact, loads_tokens
from tests.vintage_stub import FakeClock, FakeHTTPS, Reply, build_record, default_bodies, run_tick

T0 = BASE_TICK_START
HOUR = timedelta(hours=1)
CM_HOST = "community-api.coinmetrics.io"
RETRY_300 = [Reply(503, b"", headers=[("Retry-After", "300")], reason="Service Unavailable")] * 3
ISO = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z")


@contextmanager
def _logged():
    logger = logging.getLogger("zcrypto.vintage.record")
    records: list[logging.LogRecord] = []
    handler = logging.Handler()
    handler.emit = records.append
    level = logger.level
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def _at(records, level: int) -> list[str]:
    return [record.getMessage() for record in records if record.levelno == level]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _manifest(published) -> dict:
    return json.loads((published.dir / "tick.json").read_bytes())


def _fetches(published) -> dict[str, dict]:
    return {fetch["source"]: fetch for fetch in _manifest(published)["fetches"]}


def _url(source_id: str) -> str:
    return SOURCE_BY_ID[source_id].url


def _handler(at=T0, overrides=None):
    clock = FakeClock(at)
    script = {_url(source_id): [Reply(200, data)] for source_id, data in default_bodies().items()}
    script.update(overrides or {})
    return FakeHTTPS(script, clock), clock


def _record(data_dir: Path, https, clock, clock_prom=None):
    return record_tick(
        data_dir,
        key=ApiKey(SENTINEL_KEY),
        key_reason=None,
        clock_prom=clock_prom,
        https_handler=https,
        clock=clock,
        version="0.0.0",
    )


class _Os:
    """`os` with the named calls replaced, for a module that imports `os` whole."""

    def __init__(self, **replaced) -> None:
        self.__dict__.update(replaced)

    def __getattr__(self, name: str):
        return getattr(os, name)


def _eio(*args) -> None:
    raise OSError(errno.EIO, "input/output error")


def _tree(root: Path) -> dict[str, tuple[int, bytes | None]]:
    return {
        str(path.relative_to(root)): (_mode(path), None if path.is_dir() else path.read_bytes()) for path in sorted(root.rglob("*"))
    }


def _opened(tick_dir: Path) -> None:
    os.chmod(tick_dir, 0o755)


def _replace(path: Path, data: bytes) -> None:
    path.unlink()
    path.write_bytes(data)


def test_a_tick_publishes_every_body_as_served(tmp_path):
    published = run_tick(tmp_path, T0)
    tick_dir = tmp_path / "record" / "2026" / "11" / "11" / "20261111T003700Z"
    assert (published.stamp, published.dir) == ("20261111T003700Z", tick_dir)
    assert sorted(path.name for path in tick_dir.iterdir()) == sorted(["tick.json", *(source.file for source in SOURCES)])
    assert len(SOURCES) == 18
    bodies, fetches = default_bodies(), _fetches(published)
    for source in SOURCES:
        raw, stored = bodies[source.id], (tick_dir / source.file).read_bytes()
        assert gzip.decompress(stored) == raw
        assert stored == gzip.compress(raw, compresslevel=9, mtime=0)
        assert fetches[source.id]["body"] == {"file": source.file, "bytes": len(raw), "sha256": _sha(raw)}
    assert {path.name: _mode(path) for path in tick_dir.iterdir()} == {path.name: 0o444 for path in tick_dir.iterdir()}
    assert _mode(tick_dir) == 0o555
    assert [_mode(tick_dir.parents[n]) for n in range(3)] == [0o755] * 3


def test_the_date_directories_are_0755_under_a_narrow_umask(tmp_path):
    previous = os.umask(0o027)
    try:
        published = run_tick(tmp_path, T0)
    finally:
        os.umask(previous)
    assert [_mode(published.dir.parents[n]) for n in range(4)] == [0o755] * 4
    assert _mode(published.dir) == 0o555


def test_tick_json_is_compact_sorted_with_a_trailing_newline(tmp_path):
    first = run_tick(tmp_path, T0)
    retried = [Reply(503, b"busy", reason="Service Unavailable"), Reply(200, body("fng"))]
    published = run_tick(tmp_path, T0 + 12 * HOUR, {"fng": retried})
    raw = (published.dir / "tick.json").read_bytes()
    assert raw == json.dumps(json.loads(raw), sort_keys=True, separators=(",", ":")).encode() + b"\n"
    assert raw.endswith(b"}\n") and raw.count(b"\n") == 1
    manifest = json.loads(raw)
    types = {
        "schema": int,
        "tick": str,
        "started_at": str,
        "ended_at": str,
        "recorder": str,
        "prev": dict,
        "genesis_reason": type(None),
        "clock": dict,
        "fetches": list,
    }
    assert {key: type(value) for key, value in manifest.items()} == types
    assert (manifest["schema"], manifest["tick"], manifest["recorder"]) == (1, published.stamp, "0.0.0")
    assert ISO.fullmatch(manifest["started_at"]) and ISO.fullmatch(manifest["ended_at"])
    assert manifest["prev"] == {"tick": first.stamp, "tick_json_sha256": first.tick_json_sha256, "error": None}
    assert manifest["clock"].keys() == {"offset_seconds", "synchronised", "prom_age_seconds", "error"}
    assert isinstance(manifest["clock"]["error"], str)
    fetch_keys = {
        "source": str,
        "url": str,
        "request_headers": list,
        "attempts": list,
        "final_url": str,
        "http_version": str,
        "status": int,
        "reason": str,
        "headers": list,
        "body": dict,
        "check": dict,
    }
    assert [fetch["source"] for fetch in manifest["fetches"]] == [source.id for source in SOURCES]
    for fetch in manifest["fetches"]:
        assert {key: type(value) for key, value in fetch.items()} == fetch_keys
        assert all(len(pair) == 2 and all(isinstance(part, str) for part in pair) for pair in fetch["request_headers"])
        assert all(len(pair) == 2 and all(isinstance(part, str) for part in pair) for pair in fetch["headers"])
        assert fetch["body"].keys() == {"file", "bytes", "sha256"}
        assert fetch["check"].keys() == {
            "outcome",
            "reason",
            "newest_day",
            "rows",
            "metrics_absent",
            "metrics_failed",
            "acknowledged",
        }
        for attempt in fetch["attempts"]:
            assert attempt.keys() == {"started_at", "ended_at", "duration_seconds", "status", "error", "head", "withheld"}
            assert ISO.fullmatch(attempt["started_at"]) and ISO.fullmatch(attempt["ended_at"])
            assert isinstance(attempt["duration_seconds"], (int, float)) and isinstance(attempt["status"], int)
    fng = next(fetch for fetch in manifest["fetches"] if fetch["source"] == "fng")
    assert [attempt["head"] for attempt in fng["attempts"]] == [base64.b64encode(b"busy").decode(), None]


def test_the_same_body_twice_gives_the_same_file_bytes(tmp_path, monkeypatch):
    seconds = itertools.count(1_800_000_000)
    monkeypatch.setattr(gzip, "time", SimpleNamespace(time=lambda: float(next(seconds))))
    first, second = build_record(tmp_path, [(T0, {}), (T0 + 12 * HOUR, {})])
    for source in SOURCES:
        assert (first.dir / source.file).read_bytes() == (second.dir / source.file).read_bytes()


def test_a_non_identity_2xx_is_stored_as_served_and_graded_2(tmp_path):
    served = gzip.compress(body("cm-btc"), mtime=0)
    published = run_tick(tmp_path, T0, {"cm-btc": Reply(200, served, headers=[("Content-Encoding", "gzip")])})
    assert gzip.decompress((published.dir / "cm-btc.jsonl.gz").read_bytes()) == served
    fetch = _fetches(published)["cm-btc"]
    assert fetch["body"]["sha256"] == _sha(served)
    assert fetch["check"]["outcome"] == 2
    assert ["*", "encoding"] in fetch["check"]["metrics_failed"]


def _remove_tick(tick_dir: Path) -> None:
    os.chmod(tick_dir.parent, 0o755)
    os.chmod(tick_dir, 0o755)
    shutil.rmtree(tick_dir)


def test_a_broken_link_with_several_heads_takes_the_newest_and_names_the_others(tmp_path):
    a, b, c = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {}), (T0 + 2 * HOUR, {})])
    _remove_tick(b.dir)
    found = chain(scan(tmp_path / "record").ticks)
    assert found.head.stamp == c.stamp
    assert [tick.stamp for tick in found.other_heads] == [a.stamp]
    with _logged() as records:
        following = run_tick(tmp_path, T0 + 3 * HOUR)
    assert _manifest(following)["prev"]["tick"] == c.stamp
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and a.stamp in errors[0]


def test_an_exclusive_create_never_truncates(tmp_path):
    path = tmp_path / "taken"
    path.write_bytes(b"the bytes already there")
    with pytest.raises(FileExistsError):
        create_exclusive(path, b"new")
    assert path.read_bytes() == b"the bytes already there"


def test_a_last_ok_body_that_does_not_re_hash_is_passed_over(tmp_path):
    collapsed = body("second/cm-btc-collapse")
    second = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {})])[-1]
    _opened(second.dir)
    _replace(second.dir / "cm-btc.jsonl.gz", gzip.compress(collapsed, compresslevel=9, mtime=0))
    check = _fetches(run_tick(tmp_path, T0 + 2 * HOUR, {"cm-btc": collapsed}))["cm-btc"]["check"]
    assert check["outcome"] == 2 and ["*", "collapse"] in check["metrics_failed"]


def test_a_non_2xx_body_is_stored_as_its_file(tmp_path):
    served = body("second/cm-btc-403")
    published = run_tick(tmp_path, T0, {"cm-btc": Reply(403, served, reason="Forbidden")})
    fetch = _fetches(published)["cm-btc"]
    assert (fetch["status"], fetch["check"]["outcome"], fetch["check"]["reason"]) == (403, 1, "HTTP 403 (no retry)")
    assert gzip.decompress((published.dir / "cm-btc.jsonl.gz").read_bytes()) == served
    assert fetch["body"] == {"file": "cm-btc.jsonl.gz", "bytes": len(served), "sha256": _sha(served)}


def test_one_failing_source_never_stops_the_others(tmp_path):
    failing = [Reply(503, b"busy %d" % n, reason="Service Unavailable") for n in (1, 2, 3)]
    published = run_tick(tmp_path, T0, {"fng": failing})
    fetches = _fetches(published)
    assert list(fetches) == [source.id for source in SOURCES]
    assert (fetches["fng"]["check"]["outcome"], fetches["fng"]["check"]["reason"]) == (1, "HTTP 503 after 3 attempts")
    assert gzip.decompress((published.dir / "fng.json.gz").read_bytes()) == b"busy 3"
    others = [source for source in SOURCES if source.id != "fng"]
    assert len(others) == 17
    for source in others:
        assert gzip.decompress((published.dir / source.file).read_bytes()) == default_bodies()[source.id]
        assert fetches[source.id]["check"]["outcome"] == 0, source.id


def test_a_retried_attempts_head_is_its_first_4_kib_in_standard_base64(tmp_path):
    first = bytes(range(256)) * 40
    published = run_tick(tmp_path, T0, {"fng": [Reply(503, first, reason="Service Unavailable"), Reply(200, body("fng"))]})
    attempts = _fetches(published)["fng"]["attempts"]
    assert attempts[0]["head"] == base64.b64encode(first[:4096]).decode()
    assert "+" in attempts[0]["head"] and "/" in attempts[0]["head"]
    assert attempts[1]["head"] is None


def test_a_read_back_mismatch_refuses_and_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(record_module, "_read_back", lambda path: b"other bytes")
    with pytest.raises(RecordRefused):
        run_tick(tmp_path, T0)
    assert scan(tmp_path / "record") == Scan([], ())
    assert (tmp_path / "staging" / "20261111T003700Z").is_dir()


def test_a_crash_before_the_rename_leaves_record_untouched(tmp_path, monkeypatch):
    run_tick(tmp_path, T0)
    before = _tree(tmp_path / "record")

    def crash(staged, target):
        raise OSError("a crash before the rename")

    monkeypatch.setattr(record_module, "publish_tick", crash)
    with pytest.raises(OSError, match="a crash before the rename"):
        run_tick(tmp_path, T0 + 12 * HOUR)
    assert _tree(tmp_path / "record") == before


def _fsync_fails(monkeypatch) -> None:
    monkeypatch.setattr(storage_module, "fsync_dir", _eio)


def _seal_fails(monkeypatch) -> None:
    monkeypatch.setattr(storage_module, "os", _Os(chmod=lambda path, mode: _eio() if mode == 0o555 else os.chmod(path, mode)))


@pytest.mark.parametrize(("fail", "step"), [(_fsync_fails, "fsync"), (_seal_fails, "chmod")], ids=["fsync", "chmod"])
def test_a_failure_after_the_rename_returns_the_published_tick_with_an_error(tmp_path, monkeypatch, fail, step):
    fail(monkeypatch)
    with _logged() as records:
        published = run_tick(tmp_path, T0)
    assert published.dir.is_dir() and not (tmp_path / "staging" / published.stamp).exists()
    witness = _sha((published.dir / "tick.json").read_bytes())
    assert _at(records, logging.INFO).count(f"vintage tick published tick={published.stamp} tick_json_sha256={witness}") == 1
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and published.stamp in errors[0] and step in errors[0]
    assert step in published.after_rename


def test_an_existing_target_refuses_before_any_request(tmp_path):
    https, clock = _handler()
    (tmp_path / "record" / "2026" / "11" / "11" / "20261111T003700Z").mkdir(parents=True)
    with pytest.raises(RecordRefused):
        _record(tmp_path, https, clock)
    assert https.seen == []


def test_publish_tick_refuses_an_existing_target(tmp_path):
    staged = tmp_path / "staging" / "20261111T003700Z"
    staged.mkdir(parents=True)
    (staged / "tick.json").write_bytes(b"{}\n")
    target = tmp_path / "record" / "2026" / "11" / "11" / "20261111T003700Z"
    target.mkdir(parents=True)
    with pytest.raises(FileExistsError):
        publish_tick(staged, target)
    assert list(target.iterdir()) == []
    assert (staged / "tick.json").read_bytes() == b"{}\n"


def test_the_chain_names_the_head_and_its_sha256(tmp_path):
    first, second = build_record(tmp_path, [(T0, {}), (T0 + 12 * HOUR, {})])
    opening = _manifest(first)
    assert (opening["prev"], opening["genesis_reason"]) == (None, "empty record")
    following = _manifest(second)
    first_sha = _sha((first.dir / "tick.json").read_bytes())
    assert following["prev"] == {"tick": first.stamp, "tick_json_sha256": first_sha, "error": None}
    assert following["genesis_reason"] is None


def test_a_stamp_regression_is_published_with_an_error(tmp_path):
    head = run_tick(tmp_path, T0 + 12 * HOUR)
    with _logged() as records:
        earlier = run_tick(tmp_path, T0 + 11 * HOUR)
    assert earlier.dir.is_dir() and earlier.regression
    assert _manifest(earlier)["prev"]["tick"] == head.stamp
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and head.stamp in errors[0] and earlier.stamp in errors[0]


def _unparseable(tick_dir: Path) -> None:
    _replace(tick_dir / "tick.json", b"{not json")


def _tick_json_removed(tick_dir: Path) -> None:
    (tick_dir / "tick.json").unlink()


def _body_removed(tick_dir: Path) -> None:
    (tick_dir / "fng.json.gz").unlink()


def _unlisted_added(tick_dir: Path) -> None:
    (tick_dir / "notes.txt").write_bytes(b"an operator's note\n")


def _body_changed(tick_dir: Path) -> None:
    _replace(tick_dir / "cm-btc.jsonl.gz", gzip.compress(b"other bytes", compresslevel=9, mtime=0))


@pytest.mark.parametrize(
    ("damage", "named"),
    [
        (_unparseable, "unparseable"),
        (_tick_json_removed, "unreadable"),
        (_body_removed, "missing fng.json.gz"),
        (_unlisted_added, "unlisted notes.txt"),
        (_body_changed, "cm-btc.jsonl.gz does not re-hash"),
    ],
    ids=["unparseable", "tick-json-removed", "body-removed", "unlisted-added", "body-changed"],
)
def test_a_damaged_head_is_named_at_chaining(tmp_path, damage, named):
    head = build_record(tmp_path, [(T0, {}), (T0 + 12 * HOUR, {})])[-1]
    _opened(head.dir)
    damage(head.dir)
    found = head.dir / "tick.json"
    found_sha = _sha(found.read_bytes()) if found.exists() else None
    with _logged() as records:
        following = run_tick(tmp_path, T0 + 13 * HOUR)
    prev = _manifest(following)["prev"]
    assert prev["tick"] == head.stamp
    assert named in prev["error"]
    assert prev["tick_json_sha256"] == found_sha
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and head.stamp in errors[0] and named in errors[0]


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
@pytest.mark.parametrize("mode", [0o000, 0o444], ids=["no-access", "listing-only"])
def test_an_unreadable_date_directory_is_named_and_the_record_read_as_damaged(tmp_path, request, mode):
    older, newest = build_record(tmp_path / "a", [(T0, {}), (T0 + 24 * HOUR, {})])
    (only,) = build_record(tmp_path / "b", [(T0 + 24 * HOUR, {})])
    days = [newest.dir.parent, only.dir.parent]
    for day in days:
        request.addfinalizer(lambda day=day: os.chmod(day, 0o755))
        os.chmod(day, mode)

    with _logged() as records:
        following = run_tick(tmp_path / "a", T0 + 48 * HOUR)
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and "vintage record path unreadable" in errors[0] and str(days[0]) in errors[0]
    manifest = _manifest(following)
    assert manifest["prev"]["tick"] == older.stamp
    assert "record paths unreadable: 2026/11/12" in manifest["prev"]["error"]

    with _logged() as records:
        genesis = run_tick(tmp_path / "b", T0 + 48 * HOUR)
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and "vintage record path unreadable" in errors[0] and str(days[1]) in errors[0]
    manifest = _manifest(genesis)
    assert manifest["prev"] is None
    assert manifest["genesis_reason"].startswith("record paths unreadable: 2026/11/12")


def test_the_clock_block(tmp_path):
    prom = tmp_path / "clock-offset.prom"
    prom.write_text(
        "# HELP zcrypto_clock_offset_seconds offset\n# TYPE zcrypto_clock_offset_seconds gauge\n"
        "zcrypto_clock_offset_seconds 0.001150123\n# TYPE zcrypto_clock_synchronised gauge\nzcrypto_clock_synchronised 1\n"
    )
    os.utime(prom, (T0.timestamp() - 37, T0.timestamp() - 37))
    published = _record(tmp_path / "read", *_handler(), clock_prom=prom)
    assert _manifest(published)["clock"] == {
        "offset_seconds": 0.001150123,
        "synchronised": 1,
        "prom_age_seconds": 37.0,
        "error": None,
    }

    garbled = tmp_path / "garbled.prom"
    garbled.write_text("zcrypto_clock_offset_seconds about-a-millisecond\nzcrypto_clock_synchronised 1\n")
    for name, path in (("absent", tmp_path / "absent.prom"), ("garbled", garbled)):
        published = _record(tmp_path / name, *_handler(), clock_prom=path)
        assert published.dir.is_dir()
        block = _manifest(published)["clock"]
        assert [block["offset_seconds"], block["synchronised"], block["prom_age_seconds"]] == [None, None, None], name
        assert isinstance(block["error"], str) and block["error"], name

    unread = tmp_path / "nan.prom"
    unread.write_text("zcrypto_clock_offset_seconds NaN\nzcrypto_clock_synchronised 0\n")
    published = _record(tmp_path / "nan", *_handler(), clock_prom=unread)
    block = _manifest(published)["clock"]
    assert (block["offset_seconds"], block["synchronised"], block["error"]) == (None, 0, "offset not finite")
    assert b"NaN" not in (published.dir / "tick.json").read_bytes()


def test_the_witness_line_is_the_published_tick_jsons_sha256(tmp_path):
    with _logged() as records:
        published = run_tick(tmp_path, T0)
    witness = _sha((published.dir / "tick.json").read_bytes())
    line = f"vintage tick published tick={published.stamp} tick_json_sha256={witness}"
    assert _at(records, logging.INFO).count(line) == 1
    assert published.tick_json_sha256 == witness
    assert published.after_rename is None


def test_crash_leftovers_are_named_and_a_0755_tick_is_set_0555(tmp_path):
    first = run_tick(tmp_path, T0)
    _opened(first.dir)
    (tmp_path / "staging" / "20261101T073700Z").mkdir(parents=True)
    with _logged() as records:
        run_tick(tmp_path, T0 + 12 * HOUR)
    warnings = _at(records, logging.WARNING)
    assert len(warnings) == 1 and "20261101T073700Z" in warnings[0]
    assert _mode(first.dir) == 0o555


def test_a_tick_that_cannot_be_sealed_is_named_and_the_tick_still_runs(tmp_path, monkeypatch):
    first = run_tick(tmp_path, T0)
    _opened(first.dir)
    monkeypatch.setattr(record_module, "os", _Os(chmod=_eio))
    with _logged() as records:
        following = run_tick(tmp_path, T0 + 12 * HOUR)
    assert following.dir.is_dir()
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and str(first.dir) in errors[0]
    assert _mode(first.dir) == 0o755


def test_the_scan_skips_what_is_not_a_tick(tmp_path):
    first, head = build_record(tmp_path, [(T0, {}), (T0 + 7 * HOUR, {})])
    root = tmp_path / "record"
    before = chain(scan(root).ticks)
    day = head.dir.parent
    (day / "20261111T080000Z").write_bytes(b"a stray file\n")
    partial = day / ".20261111T093700Z.rsync-tmp"
    partial.mkdir()
    (partial / "tick.json").write_bytes((head.dir / "tick.json").read_bytes())
    (root / ".rsync-tmp").mkdir()
    (root / "2026" / "11" / "12").mkdir()
    assert chain(scan(root).ticks) == before
    following = run_tick(tmp_path, T0 + 8 * HOUR)
    assert _manifest(following)["prev"] == {"tick": head.stamp, "tick_json_sha256": head.tick_json_sha256, "error": None}


def test_an_unreadable_middle_tick_json_keeps_the_chain_whole(tmp_path):
    a, b, c = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {}), (T0 + 2 * HOUR, {})])
    _opened(b.dir)
    _unparseable(b.dir)
    found = chain(scan(tmp_path / "record").ticks)
    assert [tick.stamp for tick in found.order] == [a.stamp, b.stamp, c.stamp]
    assert found.head.stamp == c.stamp
    assert found.other_heads == ()
    assert [tick.stamp for tick in found.unreadable] == [b.stamp]


def test_a_cycle_of_prev_links_chains_to_the_newest_tick_with_an_error(tmp_path):
    a, b = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {})])
    _opened(a.dir)
    closed = _manifest(a) | {"prev": {"tick": b.stamp, "tick_json_sha256": b.tick_json_sha256, "error": None}}
    _replace(a.dir / "tick.json", json.dumps(closed, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    found = chain(scan(tmp_path / "record").ticks)
    assert (found.head.stamp, [tick.stamp for tick in found.order], found.other_heads) == (b.stamp, [a.stamp, b.stamp], ())
    with _logged() as records:
        following = run_tick(tmp_path, T0 + 2 * HOUR)
    manifest = _manifest(following)
    assert manifest["prev"] == {"tick": b.stamp, "tick_json_sha256": b.tick_json_sha256, "error": None}
    assert manifest["genesis_reason"] is None
    errors = _at(records, logging.ERROR)
    assert len(errors) == 1 and "no tick is a head candidate" in errors[0] and b.stamp in errors[0]


def _later(source_id: str) -> list[str]:
    ids = [source.id for source in SOURCES]
    return ids[ids.index(source_id) + 1 :]


def test_the_tick_deadline_reads_the_monotonic_clock(tmp_path):
    assert [source.id for source in SOURCES][4:6] == ["fng", "cm-status"]
    https, clock = _handler(overrides={_url("fng"): RETRY_300, _url("cm-status"): RETRY_300})
    assert clock.now().year == 2026 and clock.monotonic() == 0.0
    fetches = _fetches(_record(tmp_path, https, clock))
    assert fetches["fng"]["check"]["reason"] == "HTTP 503 after 3 attempts"
    assert fetches["cm-status"]["check"]["reason"] == "tick deadline"
    assert len(fetches["cm-status"]["attempts"]) == 2
    later = _later("cm-status")
    assert later[0] == "mempool-hashrate"
    for source_id in later:
        assert (fetches[source_id]["check"]["reason"], fetches[source_id]["attempts"]) == ("tick deadline", []), source_id
    assert not {seen.url for seen in https.seen} & {_url(source_id) for source_id in later}


def test_one_host_answering_503_all_tick_leaves_every_other_host_recorded(tmp_path):
    cm = [source for source in SOURCES if source.host == CM_HOST]
    https, clock = _handler(overrides={source.url: RETRY_300 for source in cm})
    published = _record(tmp_path, https, clock)
    fetches = _fetches(published)
    for source_id in ("bg-sopr", "bg-asopr", "bg-sth-sopr", "bg-lth-sopr", "fng", "cm-status", "mempool-hashrate"):
        assert fetches[source_id]["check"]["outcome"] == 0, source_id
        stored = (published.dir / SOURCE_BY_ID[source_id].file).read_bytes()
        assert gzip.decompress(stored) == default_bodies()[source_id]
    assert fetches["cm-btc"]["check"]["reason"] == "HTTP 503 after 3 attempts"
    assets = [source for source in cm if source.kind == "cm-asset" and source.id != "cm-btc"]
    assert len(assets) == 9
    seen = {seen.url for seen in https.seen}
    for source in assets:
        assert fetches[source.id]["check"]["reason"] == "breaker", source.id
        assert source.url not in seen
    catalog = fetches["cm-catalog"]
    assert _url("cm-catalog") in seen
    assert (catalog["check"]["reason"], len(catalog["attempts"])) == ("tick deadline", 2)
    assert 0 < clock.slept[-1] < 300


def test_the_catalog_endpoint_answering_503_all_tick_leaves_every_asset_recorded(tmp_path):
    https, clock = _handler(overrides={_url("cm-catalog"): RETRY_300, _url("fng"): RETRY_300})
    published = _record(tmp_path, https, clock)
    fetches = _fetches(published)
    assert fetches["fng"]["check"]["reason"] == "HTTP 503 after 3 attempts"
    seen = {seen.url for seen in https.seen}
    recorded = [source for source in SOURCES if source.kind in ("cm-asset", "bg", "cm-status", "mempool-hashrate")]
    assert len(recorded) == 16
    for source in recorded:
        assert source.url in seen, source.id
        assert fetches[source.id]["check"]["outcome"] == 0, source.id
        assert gzip.decompress((published.dir / source.file).read_bytes()) == default_bodies()[source.id]
    catalog = fetches["cm-catalog"]
    assert _url("cm-catalog") in seen
    assert (catalog["check"]["reason"], len(catalog["attempts"])) == ("tick deadline", 2)
    assert 0 < clock.slept[-1] < 300


SAMPLE = re.compile(r'^(zcrypto_vintage_[a-z_]+)\{source="([^"]+)"\} (\S+)$')
FAMILIES = (
    "zcrypto_vintage_last_ok_timestamp_seconds",
    "zcrypto_vintage_outcome",
    "zcrypto_vintage_body_bytes",
    "zcrypto_vintage_days_missing",
    "zcrypto_vintage_changed_values",
)
LAST_OK, OUTCOME, BODY_BYTES, DAYS_MISSING, CHANGED = FAMILIES
WITNESS = re.compile(r"vintage tick published tick=(\S+) tick_json_sha256=([0-9a-f]{64})$")
SUMMARY = re.compile(
    r"vintage record complete tick=(\S+) tick_json_sha256=([0-9a-f]{64}) ok=\d+ not_fetched=\d+ failed_checks=\d+ bytes=\d+$"
)
BUSY = [Reply(503, b"busy" * n, reason="Service Unavailable") for n in (1, 2, 3)]
runner = CliRunner()


def _vintages(tmp_path: Path) -> Path:
    return tmp_path / "vintages"


def _textfile(tmp_path: Path) -> Path:
    (tmp_path / "textfile").mkdir(exist_ok=True)
    return tmp_path / "textfile" / "vintage.prom"


def _recorded(tmp_path: Path, at=T0, replies=None, *, key: str | None = SENTINEL_KEY, sources: tuple[str, ...] = ()):
    """One `run_record` at `at`, every source answering its default body but where `replies` names its own."""
    script = {}
    for source_id, items in (replies or {}).items():
        items = items if isinstance(items, list) else [items]
        script[_url(source_id)] = [Reply(200, item) if isinstance(item, bytes) else item for item in items]
    https, clock = _handler(at, script)
    textfile = _textfile(tmp_path)
    code = command_module.run_record(
        _vintages(tmp_path),
        textfile,
        tmp_path / "clock-offset.prom",
        key_stream=None if key is None else io.BytesIO(key.encode() + b"\n"),
        https_handler=https,
        clock=clock,
        version="0.0.0",
        revision="",
        sources=sources,
    )
    return SimpleNamespace(code=code, https=https, textfile=textfile)


def _tick_dir(tmp_path: Path, at) -> Path:
    stamp = at.strftime("%Y%m%dT%H%M%SZ")
    return _vintages(tmp_path) / "record" / stamp[:4] / stamp[4:6] / stamp[6:8] / stamp


def _prom(textfile: Path) -> dict[str, dict[str, float]]:
    found: dict[str, dict[str, float]] = {}
    for line in textfile.read_text().splitlines():
        if match := SAMPLE.match(line):
            found.setdefault(match[1], {})[match[2]] = float(match[3])
    return found


def _ended(tick_dir: Path, source_id: str) -> datetime:
    fetch = next(fetch for fetch in json.loads((tick_dir / "tick.json").read_bytes())["fetches"] if fetch["source"] == source_id)
    return datetime.fromisoformat(fetch["attempts"][-1]["ended_at"])


def _damage(tick_dir: Path, name: str) -> Path:
    _opened(tick_dir)
    _replace(tick_dir / name, gzip.compress(b"other bytes", compresslevel=9, mtime=0))
    os.chmod(tick_dir, 0o555)
    return tick_dir / name


def _cli_args(tmp_path: Path) -> list[str]:
    return [
        "vintage",
        "record",
        "--data-dir",
        str(_vintages(tmp_path)),
        "--textfile",
        str(_textfile(tmp_path)),
        "--clock-prom",
        str(tmp_path / "clock-offset.prom"),
    ]


def test_the_flag_reads_the_key_from_stdin(tmp_path, monkeypatch):
    handed = []

    def capture(*args, key_stream, **kwargs):
        handed.append(None if key_stream is None else key_stream.read())
        return 0

    monkeypatch.setattr(command_module, "run_record", capture)
    flagged = runner.invoke(app, [*_cli_args(tmp_path), "--bgeometrics-key-stdin"], input=SENTINEL_KEY + "\n")
    plain = runner.invoke(app, _cli_args(tmp_path), input=SENTINEL_KEY + "\n")
    assert (flagged.exit_code, plain.exit_code) == (0, 0)
    assert handed == [(SENTINEL_KEY + "\n").encode(), None]


def test_the_source_option_repeats(tmp_path, monkeypatch):
    handed = []

    def capture(*args, sources, **kwargs):
        handed.append(sources)
        return 2

    monkeypatch.setattr(command_module, "run_record", capture)
    named = runner.invoke(app, [*_cli_args(tmp_path), "--source", "cm-eth", "--source", "fng"])
    unnamed = runner.invoke(app, _cli_args(tmp_path))
    assert (named.exit_code, unnamed.exit_code) == (2, 2)
    assert handed == [("cm-eth", "fng"), ()]


def test_a_named_source_is_recorded_while_another_assets_query_answers_503(tmp_path):
    result = _recorded(tmp_path, replies={"cm-btc": RETRY_300}, sources=("cm-eth",))
    assert result.code == 1
    tick_dir = _tick_dir(tmp_path, T0)
    fetches = {fetch["source"]: fetch for fetch in json.loads((tick_dir / "tick.json").read_bytes())["fetches"]}
    assert list(fetches) == [source.id for source in SOURCES] and len(fetches) == 18
    assert fetches["cm-eth"]["check"]["outcome"] == 0
    assert gzip.decompress((tick_dir / "cm-eth.jsonl.gz").read_bytes()) == default_bodies()["cm-eth"]
    for source_id, fetch in fetches.items():
        if source_id != "cm-eth":
            assert (fetch["check"]["outcome"], fetch["check"]["reason"], fetch["attempts"]) == (1, "not selected", []), source_id
    assert [seen.url for seen in result.https.seen] == [_url("cm-eth")]


def test_an_unknown_source_refuses_before_any_fetch(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path, sources=("cm-eth", "cm-nope"))
    assert result.code == 2
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1 and "cm-nope" in errors[0]
    assert result.https.seen == []
    assert scan(_vintages(tmp_path) / "record") == Scan([], ())
    assert not result.textfile.exists()


def _all_ok(tmp_path, monkeypatch):
    return None


def _textfile_read_only(tmp_path, monkeypatch):
    if os.geteuid() == 0:
        pytest.skip("root writes into a read-only directory")
    os.chmod(_textfile(tmp_path).parent, 0o555)


def _body_damaged_earlier(tmp_path, monkeypatch):
    return _damage(run_tick(_vintages(tmp_path), T0).dir, "fng.json.gz")


def _raises(*args, **kwargs):
    raise RuntimeError("a message the ERROR never carries")


def _fetch_all_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(record_module, "fetch_all", _raises)


def _render_prom_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(command_module, "render_prom", _raises)


def _fsync_fails_after_the_rename(tmp_path, monkeypatch):
    _fsync_fails(monkeypatch)
    return "after its rename"


@pytest.mark.parametrize(
    ("setup", "replies", "code", "published"),
    [
        (_all_ok, {}, 0, True),
        (_all_ok, {"fng": BUSY}, 1, True),
        (_textfile_read_only, {}, 1, True),
        (_body_damaged_earlier, {}, 1, True),
        (_fetch_all_raises, {}, 2, False),
        (_render_prom_raises, {}, 1, True),
        (_fsync_fails_after_the_rename, {}, 1, True),
    ],
    ids=[
        "all-ok",
        "one-503",
        "textfile-read-only",
        "body-damaged-earlier",
        "fetch-all-raises",
        "render-prom-raises",
        "after-rename",
    ],
)
def test_the_exit_codes(tmp_path, monkeypatch, caplog, setup, replies, code, published):
    named = setup(tmp_path, monkeypatch)
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path, T0 + HOUR, replies)
    assert result.code == code
    assert _tick_dir(tmp_path, T0 + HOUR).is_dir() is published
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    if named is not None:
        assert any(str(named) in error for error in errors), errors
    if code == 0:
        assert errors == []
    assert not any("a message the ERROR never carries" in error for error in errors)


@pytest.mark.parametrize(
    ("index", "code"), [(2, 1), (12, 1), (1, 0), (11, 0)], ids=["slice", "fourth-newest", "neither-1", "neither-11"]
)
def test_the_re_verify_reads_the_newest_four_and_the_slice_the_tick_count_names(tmp_path, caplog, index, code):
    ticks = build_record(_vintages(tmp_path), [(T0 + n * HOUR, {}) for n in range(15)])
    damaged = _damage(ticks[index].dir, "fng.json.gz")
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path, T0 + 15 * HOUR)
    assert len(scan(_vintages(tmp_path) / "record").ticks) == 16
    assert result.code == code
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    if code == 1:
        assert any(str(damaged) in error for error in errors), errors
    else:
        assert errors == []


def test_a_held_lock_exits_2_with_the_recorders_own_message(tmp_path, caplog):
    _vintages(tmp_path).mkdir()
    fd = os.open(_vintages(tmp_path) / LOCKFILE_NAME, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        caplog.set_level(logging.DEBUG)
        result = _recorded(tmp_path)
    finally:
        os.close(fd)
    assert result.code == 2
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1 and "zcrypto-vintage-record.service" in errors[0]
    assert "zcrypto-capture" not in errors[0] and "systemctl stop" not in errors[0]
    assert result.https.seen == [] and not result.textfile.exists()


def test_a_failed_source_logs_a_warning_and_a_refusal_an_error(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    failed = _recorded(tmp_path, replies={"fng": BUSY})
    assert failed.code == 1
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and "fng" in warnings[0] and "outcome=1" in warnings[0] and "HTTP 503 after 3 attempts" in warnings[0]
    assert [record for record in caplog.records if record.levelno >= logging.ERROR] == []

    caplog.clear()
    refused = _recorded(tmp_path)
    assert refused.code == 2
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert len(errors) == 1 and "its target exists" in errors[0]


def test_the_witness_precedes_the_gauges_and_the_summary_repeats_it(tmp_path, monkeypatch, caplog):
    caplog.set_level(logging.DEBUG)
    published = command_module.publish_prom
    at_publish = []

    def spy(path, text):
        at_publish.append((path.exists(), list(caplog.messages)))
        published(path, text)

    monkeypatch.setattr(command_module, "publish_prom", spy)
    result = _recorded(tmp_path)
    assert result.code == 0
    ((existed, before),) = at_publish
    assert not existed
    witnesses = [match for message in before if (match := WITNESS.search(message))]
    assert len(witnesses) == 1
    summaries = [match for message in caplog.messages if (match := SUMMARY.search(message))]
    assert len(summaries) == 1
    assert summaries[0].groups() == witnesses[0].groups()
    assert witnesses[0][2] == _sha((_tick_dir(tmp_path, T0) / "tick.json").read_bytes())


def test_the_prom_is_0644_and_holds_the_five_families(tmp_path):
    result = _recorded(tmp_path, replies={"cm-btc": BUSY}, key=None)
    assert _mode(result.textfile) == 0o644
    text = result.textfile.read_text()
    for family in FAMILIES:
        assert re.search(rf"^# HELP {family} \S", text, re.M), family
        assert f"\n# TYPE {family} gauge\n" in text, family
    prom = _prom(result.textfile)
    bg = [source.id for source in SOURCES if source.kind == "bg"]
    assert len(bg) == 4
    assert {source_id: prom[OUTCOME][source_id] for source_id in ["cm-btc", *bg, "fng"]} == {
        "cm-btc": 1,
        **dict.fromkeys(bg, 1),
        "fng": 0,
    }
    stored = gzip.decompress((_tick_dir(tmp_path, T0) / "cm-btc.jsonl.gz").read_bytes())
    assert stored == BUSY[-1].body
    assert prom[BODY_BYTES]["fng"] == len(default_bodies()["fng"])
    assert prom[BODY_BYTES]["cm-btc"] == len(stored)
    assert [prom[BODY_BYTES][source_id] for source_id in bg] == [0] * 4
    assert re.search(r'^zcrypto_vintage_last_ok_timestamp_seconds\{source="bg-sopr"\} \S+$', text, re.M)
    assert prom[LAST_OK]["bg-sopr"] == 0


def test_last_ok_reads_along_the_chain(tmp_path):
    future = run_tick(_vintages(tmp_path), T0 + 24 * HOUR)
    result = _recorded(tmp_path, T0)
    head = _tick_dir(tmp_path, T0)
    assert json.loads((head / "tick.json").read_bytes())["prev"]["tick"] == future.stamp
    fng = _prom(result.textfile)[LAST_OK]["fng"]
    assert fng == last_ok_value(_ended(head, "fng"))
    assert fng < last_ok_value(_ended(future.dir, "fng"))


def test_last_ok_is_capped_at_1957_utc():
    day = T0.date()
    late = datetime.combine(day, time(23, 30), UTC)
    early = datetime.combine(day, time(19, 38), UTC)
    assert last_ok_value(late) == datetime.combine(day, time(19, 57), UTC).timestamp()
    assert last_ok_value(early) == early.timestamp()


def test_the_last_ok_cap_is_the_evening_slot_plus_the_tick_deadline():
    timer = (Path(__file__).resolve().parents[1] / "infra/ansible/roles/ops/templates/vintage-record.timer.j2").read_text()
    slots = re.findall(r"^OnCalendar=\*-\*-\* (\d{2}):(\d{2}):(\d{2})$", timer, re.M)
    evening = datetime.combine(T0.date(), time(*map(int, slots[1])), UTC)
    deadline = timedelta(seconds=record_module.TICK_DEADLINE_SECONDS)
    assert (evening + deadline).time() == gauges_module.LAST_OK_CAP


def _mempool_503() -> list[Reply]:
    return BUSY


def _mempool_graded_2() -> bytes:
    doc = loads_tokens(default_bodies()["mempool-hashrate"])
    doc["hashrates"] = []
    return dumps_compact(doc)


@pytest.mark.parametrize(("middle", "outcome"), [(_mempool_503, 1), (_mempool_graded_2, 2)], ids=["503", "graded-2"])
def test_days_missing_is_read_off_the_record(tmp_path, middle, outcome):
    run_tick(_vintages(tmp_path), T0)
    between = run_tick(_vintages(tmp_path), T0 + 24 * HOUR, {"mempool-hashrate": middle()})
    assert _fetches(between)["mempool-hashrate"]["check"]["outcome"] == outcome
    result = _recorded(tmp_path, T0 + 48 * HOUR)
    prom = _prom(result.textfile)
    assert prom[OUTCOME]["mempool-hashrate"] == 0
    assert prom[DAYS_MISSING]["mempool-hashrate"] == 1


def test_changed_values_is_the_two_body_reading(tmp_path):
    run_tick(_vintages(tmp_path), T0)
    restated = _recorded(tmp_path, T0 + HOUR, {"cm-btc": body("second/cm-btc-restatement")})
    assert _prom(restated.textfile)[CHANGED]["cm-btc"] == 1
    failed = _recorded(tmp_path, T0 + 2 * HOUR, {"cm-btc": BUSY})
    changed = _prom(failed.textfile)[CHANGED]
    assert "cm-btc" not in changed and changed["fng"] == 0


def test_a_body_that_does_not_parse_leaves_no_changed_values_line(tmp_path, monkeypatch, caplog):
    run_tick(_vintages(tmp_path), T0)
    previous = default_bodies()["cm-btc"]
    parse = gauges_module.parse_series

    def refusing(source, data):
        if source.id == "cm-btc" and data == previous:
            raise ValueError("cm-btc refused")
        return parse(source, data)

    monkeypatch.setattr(gauges_module, "parse_series", refusing)
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path, T0 + HOUR, {"cm-btc": body("second/cm-btc-restatement")})
    assert result.code == 0
    changed = _prom(result.textfile)[CHANGED]
    compared = [source.id for source in SOURCES if source.kind in ("fng", "cm-asset", "mempool-hashrate", "bg")]
    assert len(compared) == 16
    assert sorted(changed) == sorted(source_id for source_id in compared if source_id != "cm-btc")
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and "cm-btc" in warnings[0]


def test_a_refusal_writes_no_prom(tmp_path, caplog):
    _tick_dir(tmp_path, T0).mkdir(parents=True)
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path)
    assert result.code == 2
    errors = [record.getMessage() for record in caplog.records if record.levelno == logging.ERROR]
    assert errors == [f"vintage tick refused: its target exists tick={T0.strftime('%Y%m%dT%H%M%SZ')}; nothing published"]
    assert result.https.seen == []
    assert list(result.textfile.parent.iterdir()) == []


def test_an_unreadable_tick_json_logs_an_error_and_counts_no_ok_fetch(tmp_path, caplog):
    a, b, _ = build_record(_vintages(tmp_path), [(T0, {}), (T0 + HOUR, {}), (T0 + 2 * HOUR, {"fng": BUSY})])
    _opened(b.dir)
    _unparseable(b.dir)
    os.chmod(b.dir, 0o555)
    caplog.set_level(logging.DEBUG)
    result = _recorded(tmp_path, T0 + 3 * HOUR, {"fng": BUSY})
    unreadable = str(b.dir / "tick.json")
    naming = [
        record.getMessage() for record in caplog.records if record.levelno == logging.ERROR and unreadable in record.getMessage()
    ]
    assert naming and all("unreadable manifest" in message for message in naming), naming
    assert result.code == 1
    prom = _prom(result.textfile)
    assert prom[LAST_OK]["fng"] == last_ok_value(_ended(a.dir, "fng"))
    assert prom[LAST_OK]["cm-btc"] == last_ok_value(_ended(_tick_dir(tmp_path, T0 + 3 * HOUR), "cm-btc"))


def test_an_outcome_the_manifest_does_not_hold_is_written_as_not_fetched(tmp_path, caplog):
    published = run_tick(_vintages(tmp_path), T0)
    record_root = _vintages(tmp_path) / "record"
    fetches = [fetch for fetch in published.manifest["fetches"] if fetch["source"] != "fng"]
    for fetch in fetches:
        if fetch["source"] == "cm-btc":
            fetch["check"] = {**fetch["check"], "outcome": "0"}
    published.manifest = {**published.manifest, "fetches": fetches}
    caplog.set_level(logging.DEBUG)
    text = gauges_module.render_prom(record_root, chain(scan(record_root).ticks), published, today=T0.date())
    assert "None" not in text
    outcomes = {match[2]: match[3] for line in text.splitlines() if (match := SAMPLE.match(line)) and match[1] == OUTCOME}
    assert (outcomes["fng"], outcomes["cm-btc"], outcomes["cm-eth"]) == ("1", "1", "0")
    warnings = [record.getMessage() for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert [sum(source_id in warning for warning in warnings) for source_id in ("fng", "cm-btc")] == [1, 1]


VINTAGE_DIR = Path(__file__).resolve().parents[1] / "cli" / "vintage"
FS_MODULES = ("os", "os.path", "shutil", "pathlib", "io", "codecs", "gzip", "tempfile")
# A name added here reads or creates without replacing; nothing that writes over, moves, truncates or removes a path.
FS_ALLOWED = frozenset(
    {
        "codecs.open",
        "gzip.GzipFile",
        "gzip.compress",
        "gzip.decompress",
        "gzip.open",
        "io.BytesIO",
        "io.open",
        "os.chmod",
        "os.close",
        "os.environ.get",
        "os.fstat",
        "os.fsync",
        "os.listdir",
        "os.mkdir",
        "os.open",
        "os.read",
        "os.rename",
        "os.replace",
        "os.scandir",
        "os.stat",
        "os.write",
        "pathlib.Path",
        "tempfile.mkstemp",
    }
)
# Every module cli/vintage/ may import: the walk sees only what these modules name, so a module added here widens what
# the guard must hold, a reviewed edit. `logging` is the log levels' (`log.log`); no handler of it writes a file.
VINTAGE_IMPORTS = frozenset(
    {
        "__future__",
        "base64",
        "cli.capture.command",
        "cli.capture.errors",
        "cli.config",
        "cli.logging",
        "cli.vintage",
        "cli.vintage.chain",
        "cli.vintage.credential",
        "cli.vintage.derive",
        "cli.vintage.fetch",
        "cli.vintage.gauges",
        "cli.vintage.record",
        "cli.vintage.sources",
        "cli.vintage.storage",
        "cli.vintage.table",
        "collections",
        "collections.abc",
        "compression.zstd",
        "contextlib",
        "dataclasses",
        "datetime",
        "email.utils",
        "errno",
        "gzip",
        "hashlib",
        "http.client",
        "importlib.metadata",
        "io",
        "json",
        "logging",
        "math",
        "os",
        "pathlib",
        "polars",
        "re",
        "secrets",
        "signal",
        "stat",
        "sys",
        "tempfile",
        "time",
        "traceback",
        "typer",
        "typing",
        "urllib.error",
        "urllib.parse",
        "urllib.request",
        "zlib",
    }
)
# What cli/vintage/ takes from each module it imports, read from its syntax tree and exact both ways: a name the tree
# stops taking fails as one it starts to take does, so the pin never admits more than the tree uses.
VINTAGE_NAMES = {
    "__future__": frozenset({"annotations"}),
    "base64": frozenset({"b64encode"}),
    "cli.capture.command": frozenset({"LOCKFILE_NAME", "single_instance_lock"}),
    "cli.capture.errors": frozenset({"CaptureError"}),
    "cli.config": frozenset({"load_config"}),
    "cli.logging": frozenset({"get_logger"}),
    "cli.vintage": frozenset({"chain", "derive", "verify"}),
    "cli.vintage.chain": frozenset({"Chain", "STAMP_RE", "TICK_JSON", "TickFile", "chain", "check_head", "listed", "scan"}),
    "cli.vintage.credential": frozenset({"ApiKey", "decode_for_scan", "holds_key", "key_forms", "read_key"}),
    "cli.vintage.derive": frozenset(
        {
            "DERIVE_GENERATION",
            "DeriveError",
            "DeriveState",
            "GENERATION_ENTRIES",
            "KINDS",
            "LATER_FACTS_SCHEMA",
            "changed_values",
            "derive_tick",
            "frames",
            "parse_series",
        }
    ),
    "cli.vintage.fetch": frozenset({"Attempt", "Clock", "Exchange", "SystemClock", "build_openers", "fetch_all", "header"}),
    "cli.vintage.gauges": frozenset({"render_prom"}),
    "cli.vintage.record": frozenset({"Published", "RECORD_SUBDIR", "RecordRefused", "record_tick"}),
    "cli.vintage.sources": frozenset(
        {
            "BodySummary",
            "FORK_ACKNOWLEDGMENTS",
            "ForkAcknowledgment",
            "LINK_ACKNOWLEDGMENTS",
            "LinkAcknowledgment",
            "SOURCES",
            "SOURCE_BY_ID",
            "Source",
            "as_object",
            "check_block",
            "check_body",
            "date_day",
            "epoch_day",
            "iso_day",
            "rows",
            "summarise",
        }
    ),
    "cli.vintage.storage": frozenset(
        {
            "AFTER_RENAME",
            "create_exclusive",
            "fsync_dir",
            "gzip_bytes",
            "publish_prom",
            "publish_table_dir",
            "publish_tick",
            "refuse_table_root",
        }
    ),
    "cli.vintage.table": frozenset({"DeriveOutcome", "derive_table"}),
    "collections": frozenset({"Counter"}),
    "collections.abc": frozenset({"Iterator", "Sequence"}),
    "compression.zstd": frozenset({"ZstdDecompressor", "ZstdError"}),
    "contextlib": frozenset({"AbstractContextManager", "ExitStack", "contextmanager", "suppress"}),
    "dataclasses": frozenset({"asdict", "dataclass", "field"}),
    "datetime": frozenset({"UTC", "date", "datetime", "time", "timedelta"}),
    "email.utils": frozenset({"parsedate_to_datetime"}),
    "errno": frozenset({"EEXIST"}),
    "gzip": frozenset({"compress", "decompress"}),
    "hashlib": frozenset({"sha256"}),
    "http.client": frozenset({"HTTPException"}),
    "importlib.metadata": frozenset({"version"}),
    "io": frozenset({"BytesIO"}),
    "json": frozenset({"JSONDecodeError", "dumps", "loads"}),
    "logging": frozenset({"ERROR", "INFO"}),
    "math": frozenset({"inf", "isfinite"}),
    "os": frozenset(
        {
            "O_CREAT",
            "O_EXCL",
            "O_RDONLY",
            "O_WRONLY",
            "chmod",
            "close",
            "environ",
            "fsync",
            "mkdir",
            "open",
            "rename",
            "replace",
            "stat",
            "write",
        }
    ),
    "pathlib": frozenset({"Path"}),
    "polars": frozenset(
        {"Boolean", "DataFrame", "DataType", "Date", "Datetime", "Int64", "String", "col", "concat", "exceptions", "read_parquet"}
    ),
    "re": frozenset({"Pattern", "compile"}),
    "secrets": frozenset({"token_hex"}),
    "signal": frozenset({"ITIMER_REAL", "SIGALRM", "setitimer", "signal"}),
    "stat": frozenset({"S_IMODE", "S_ISDIR"}),
    "sys": frozenset({"stdin"}),
    "tempfile": frozenset({"mkstemp"}),
    "time": frozenset({"monotonic", "sleep"}),
    "traceback": frozenset({"extract_tb"}),
    "typer": frozenset({"BadParameter", "Exit", "Option", "Typer"}),
    "typing": frozenset({"BinaryIO", "Optional", "Protocol"}),
    "urllib.error": frozenset({"HTTPError"}),
    "urllib.parse": frozenset({"quote", "urlsplit"}),
    "urllib.request": frozenset({"BaseHandler", "HTTPRedirectHandler", "OpenerDirector", "Request", "build_opener"}),
    "zlib": frozenset({"MAX_WBITS", "decompressobj", "error"}),
}
_FILE_HANDLERS = frozenset(
    {"FileHandler", "BaseRotatingHandler", "RotatingFileHandler", "TimedRotatingFileHandler", "WatchedFileHandler"}
)
_RULES = ("rename", "os_open", "mkstemp", "write_parquet", "opening", "fs", "imports", "logging_file", "names")
# Each helper is its module's path under the walked root and its function's name: a function of that name elsewhere,
# a nested package's `storage.py` among them, is no helper.
_RENAME_HELPERS = frozenset({("storage.py", "publish_tick"), ("storage.py", "publish_prom"), ("storage.py", "publish_table_dir")})
_MKSTEMP_HELPER = ("storage.py", "publish_prom")
_PART_WRITER = ("table.py", "write_part")
_DIAL = ("fetch.py", "_dial")
_RENAMES = frozenset({"os.replace", "os.rename", "os.renames"})
_WRITE_FLAGS = frozenset({"O_WRONLY", "O_RDWR", "O_TRUNC", "O_APPEND"})
_OPENERS = frozenset({"io.open", "codecs.open", "gzip.open", "gzip.GzipFile"})
_FORBIDDEN_METHODS = frozenset(
    {
        "unlink",
        "rmdir",
        "truncate",
        "write_bytes",
        "write_text",
        "touch",
        "symlink_to",
        "hardlink_to",
        "copy_into",
        "move",
        "move_into",
        "save_to_file",
        "show_graph",
    }
)
# Refused with any argument, and when named rather than called: `dict.copy()` and `DataFrame.serialize()` return
# their bytes, `Path.copy(target)` and `DataFrame.serialize(file)` write a path.
_ARGUMENT_WRITERS = frozenset({"copy", "serialize"})


def _bindings(tree: ast.Module) -> dict[str, set[str]]:
    """Each name an import anywhere in the module binds, to the qualified names it may hold."""
    bound: dict[str, set[str]] = defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")[0]
                bound[alias.asname or head].add(alias.name if alias.asname else head)
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            for alias in node.names:
                bound[alias.asname or alias.name].add(f"{node.module}.{alias.name}")
    return bound


def _qualified(expr: ast.expr, bound: dict[str, set[str]]) -> set[str]:
    if isinstance(expr, ast.Name):
        return set(bound.get(expr.id, ()))
    if isinstance(expr, ast.Attribute):
        return {f"{base}.{expr.attr}" for base in _qualified(expr.value, bound)}
    return set()


def _in_fs(name: str) -> bool:
    return any(name == module or name.startswith(f"{module}.") for module in FS_MODULES)


def _fs_allowed(name: str) -> bool:
    return name in FS_ALLOWED or name == "os.path" or name.startswith("os.path.")


def _is_rename(call: ast.Call, names: set[str]) -> bool:
    if names & _RENAMES:
        return True
    if not (isinstance(call.func, ast.Attribute) and call.func.attr in ("replace", "rename")):
        return False
    keywords = [keyword.arg for keyword in call.keywords]
    return (len(call.args) == 1 and not keywords) or (not call.args and keywords == ["target"])


def _flags(expr: ast.expr, bound: dict[str, set[str]]) -> set[str] | None:
    """The `O_*` names of `os` joined by `|`; None for any other spelling."""
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.BitOr):
        left, right = _flags(expr.left, bound), _flags(expr.right, bound)
        return None if left is None or right is None else left | right
    names = _qualified(expr, bound)
    if len(names) == 1 and (name := next(iter(names))).startswith("os.O_"):
        return {name.removeprefix("os.")}
    return None


def _os_open_breaks(call: ast.Call, bound: dict[str, set[str]]) -> bool:
    given = [keyword.value for keyword in call.keywords if keyword.arg == "flags"] or call.args[1:2]
    flags = _flags(given[0], bound) if given else None
    return flags is None or not ({"O_CREAT", "O_EXCL"} <= flags or not flags & _WRITE_FLAGS)


def _is_string(expr: ast.expr) -> bool:
    return isinstance(expr, ast.Constant) and isinstance(expr.value, str)


def _mode_breaks(call: ast.Call, slot: int) -> bool:
    """Whether the mode, from `mode=` or the positional slot, writes or cannot be read; no mode is the read default."""
    if any(isinstance(arg, ast.Starred) for arg in call.args) or any(keyword.arg is None for keyword in call.keywords):
        return True
    given = [keyword.value for keyword in call.keywords if keyword.arg == "mode"] or call.args[slot : slot + 1]
    if not given:
        return False
    return not _is_string(given[0]) or bool(set(given[0].value) & set("wax+"))


def _is_dial(call: ast.Call, module: str, function: str | None) -> bool:
    """The opener's call in fetch.py's `_dial`: one positional name, the request, and `timeout=` alone, which no
    `Path.open` takes; any other `.open` there is read for its mode."""
    return (
        (module, function) == _DIAL
        and len(call.args) == 1
        and isinstance(call.args[0], ast.Name)
        and [keyword.arg for keyword in call.keywords] == ["timeout"]
    )


def _opening_breaks(call: ast.Call, names: set[str], module: str, function: str | None) -> bool:
    if any(name.startswith("typer.") for name in names):
        given = [keyword.value for keyword in call.keywords if keyword.arg == "mode"]
        return bool(given) and (not _is_string(given[0]) or bool(set(given[0].value) & set("wax+")))
    if not names and isinstance(call.func, ast.Name) and call.func.id == "open":
        return _mode_breaks(call, 1)
    if names & _OPENERS:
        onto_fileobj = any(
            keyword.arg == "fileobj" and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None)
            for keyword in call.keywords
        )
        return not ("gzip.GzipFile" in names and onto_fileobj) and _mode_breaks(call, 1)
    if isinstance(call.func, ast.Attribute) and call.func.attr == "open" and "os.open" not in names:
        return not _is_dial(call, module, function) and _mode_breaks(call, 0)
    return False


def _fs_breaks(call: ast.Call, names: set[str]) -> bool:
    if any(_in_fs(name) and not _fs_allowed(name) for name in names):
        return True
    if not isinstance(call.func, ast.Attribute):
        return False
    return _forbidden_name(call.func.attr) or (call.func.attr in _ARGUMENT_WRITERS and bool(call.args or call.keywords))


def _forbidden_name(attr: str) -> bool:
    return attr in _FORBIDDEN_METHODS or (attr.startswith(("write_", "sink_")) and attr != "write_parquet")


def _past_breaches(expr: ast.expr, module: str, function: str | None):
    """The by-name rules over the attributes a chain passes before its last, whose call or use the tree does not show:
    `p.unlink.__call__()` is an unlink."""
    passed = []
    while isinstance(expr, ast.Attribute):
        expr = expr.value
        if isinstance(expr, ast.Attribute):
            passed.append(expr.attr)
    if {"replace", "rename"} & set(passed) and (module, function) not in _RENAME_HELPERS:
        yield "rename"
    if "write_parquet" in passed and (module, function) != _PART_WRITER:
        yield "write_parquet"
    if "open" in passed:
        yield "opening"
    if any(_forbidden_name(attr) or attr in _ARGUMENT_WRITERS for attr in passed):
        yield "fs"


def _call_breaches(call: ast.Call, bound: dict[str, set[str]], module: str, function: str | None):
    yield from _past_breaches(call.func, module, function)
    names = _qualified(call.func, bound)
    if _is_rename(call, names) and (module, function) not in _RENAME_HELPERS:
        yield "rename"
    if "os.open" in names and _os_open_breaks(call, bound):
        yield "os_open"
    if "tempfile.mkstemp" in names and (module, function) != _MKSTEMP_HELPER:
        yield "mkstemp"
    parquet = (isinstance(call.func, ast.Attribute) and call.func.attr == "write_parquet") or any(
        name.endswith(".write_parquet") for name in names
    )
    if parquet and (module, function) != _PART_WRITER:
        yield "write_parquet"
    if _opening_breaks(call, names, module, function):
        yield "opening"
    if _fs_breaks(call, names):
        yield "fs"


_MISSING = object()


def _inert(name: str) -> bool:
    """Whether the FS-module name is a constant, a mapping or an exception class, which writes nothing when named."""
    value: object = importlib.import_module(name.split(".")[0])
    for part in name.split(".")[1:]:
        value = getattr(value, part, _MISSING)
    if value is _MISSING or isinstance(value, ModuleType):
        return False
    return not callable(value) or (isinstance(value, type) and issubclass(value, BaseException))


def _reference_breaches(expr: ast.Name | ast.Attribute, bound: dict[str, set[str]], module: str, function: str | None):
    """A guarded callable named but not called: the call its receiver makes is not in the tree, so it breaks the rule
    that holds those calls unless it sits where that rule admits every call."""
    yield from _past_breaches(expr, module, function)
    names = _qualified(expr, bound)
    attr = expr.attr if isinstance(expr, ast.Attribute) else None
    place = (module, function)
    if (names & _RENAMES or attr in ("replace", "rename")) and place not in _RENAME_HELPERS:
        yield "rename"
    if "os.open" in names:
        yield "os_open"
    if "tempfile.mkstemp" in names and place != _MKSTEMP_HELPER:
        yield "mkstemp"
    if (attr == "write_parquet" or any(name.endswith(".write_parquet") for name in names)) and place != _PART_WRITER:
        yield "write_parquet"
    builtin_open = not names and isinstance(expr, ast.Name) and expr.id == "open"
    if builtin_open or names & _OPENERS or (attr == "open" and "os.open" not in names):
        yield "opening"
    by_name = attr is not None and (_forbidden_name(attr) or attr in _ARGUMENT_WRITERS)
    if by_name or any(_in_fs(name) and not _fs_allowed(name) and not _inert(name) for name in names):
        yield "fs"


def _chain_root_breaches(expr: ast.expr, bound: dict[str, set[str]], module: str, function: str | None, scope: str | None):
    """The breaches beneath a dotted name, which is resolved whole: those of whatever its chain of attributes starts
    from when that is not a bare name."""
    while isinstance(expr, ast.Attribute):
        expr = expr.value
    if not isinstance(expr, ast.Name):
        yield from _breaches(expr, bound, module, function, scope)


def _names_a_file_handler(expr: ast.expr, bound: dict[str, set[str]]) -> bool:
    last = expr.attr if isinstance(expr, ast.Attribute) else expr.id if isinstance(expr, ast.Name) else None
    return last in _FILE_HANDLERS or any(name.rsplit(".", 1)[-1] in _FILE_HANDLERS for name in _qualified(expr, bound))


def _imported(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    return ["." * node.level + (node.module or "")]


def _taken(tree: ast.Module, bound: dict[str, set[str]]) -> list[tuple[str, str, ast.AST]]:
    """Each (module, name) the module takes and the node taking it: an `ImportFrom`'s names, and on every outermost
    dotted chain the first name past the longest imported module it starts with."""
    modules = VINTAGE_IMPORTS | {
        name for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom)) for name in _imported(node)
    }
    inner = {id(node.value) for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    taken = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            taken += [(_imported(node)[0], alias.name, node) for alias in node.names]
        elif isinstance(node, (ast.Name, ast.Attribute)) and id(node) not in inner:
            for qualified in sorted(_qualified(node, bound)):
                starts = [module for module in modules if qualified.startswith(f"{module}.")]
                if starts:
                    module = max(starts, key=len)
                    taken.append((module, qualified.removeprefix(f"{module}.").split(".")[0], node))
    return sorted(taken, key=lambda item: item[2].lineno)


def _breaches(node: ast.AST, bound: dict[str, set[str]], module: str, function: str | None, scope: str | None = None):
    """Each (rule, node) breach under `node`, a call's place being the innermost function whose body holds it, named
    by its dotted path from the module (`outer.inner`, `Class.method`), so only a module-level def is a helper; a class
    body is no function's."""
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        qualified = node.name if scope is None else f"{scope}.{node.name}"
        if isinstance(node, ast.ClassDef):
            outside = (*node.decorator_list, *node.type_params, *node.bases, *node.keywords)
        else:
            outside = (*node.decorator_list, *node.type_params, node.args, *([node.returns] if node.returns else []))
        for part in outside:
            yield from _breaches(part, bound, module, function, scope)
        body_function = None if isinstance(node, ast.ClassDef) else qualified
        for statement in node.body:
            yield from _breaches(statement, bound, module, body_function, qualified)
        return
    if isinstance(node, ast.ImportFrom) and node.level == 0 and _in_fs(node.module):
        if any(not _fs_allowed(f"{node.module}.{alias.name}") for alias in node.names):
            yield "fs", node
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        if any(name not in VINTAGE_IMPORTS for name in _imported(node)):
            yield "imports", node
        if any(alias.name.rsplit(".", 1)[-1] in _FILE_HANDLERS for alias in node.names):
            yield "logging_file", node
    if isinstance(node, ast.Call):
        for rule in _call_breaches(node, bound, module, function):
            yield rule, node
        names = _qualified(node.func, bound)
        to_a_file = "logging.basicConfig" in names and any(keyword.arg == "filename" for keyword in node.keywords)
        if to_a_file or _names_a_file_handler(node.func, bound):
            yield "logging_file", node
        yield from _chain_root_breaches(node.func, bound, module, function, scope)
        for child in (*node.args, *node.keywords):
            yield from _breaches(child, bound, module, function, scope)
        return
    if isinstance(node, (ast.Name, ast.Attribute)) and isinstance(node.ctx, ast.Load):
        for rule in _reference_breaches(node, bound, module, function):
            yield rule, node
        if _names_a_file_handler(node, bound):
            yield "logging_file", node
        yield from _chain_root_breaches(node, bound, module, function, scope)
        return
    for child in ast.iter_child_nodes(node):
        yield from _breaches(child, bound, module, function, scope)


def _write_guard(paths, root: Path) -> dict[str, list[str]]:
    """Each rule's breaches over the modules at `paths` under `root`, as `path:line`; a module that does not parse
    raises."""
    found: dict[str, list[str]] = {rule: [] for rule in _RULES}
    for path in paths:
        tree = ast.parse(path.read_text(), filename=str(path))
        seen: set[tuple[str, int]] = set()
        for rule, node in _breaches(tree, _bindings(tree), path.relative_to(root).as_posix(), None):
            if (rule, id(node)) not in seen:
                seen.add((rule, id(node)))
                found[rule].append(f"{path}:{node.lineno}")
        for module, name, node in _taken(tree, _bindings(tree)):
            if name not in VINTAGE_NAMES.get(module, ()) and ("names", id(node)) not in seen:
                seen.add(("names", id(node)))
                found["names"].append(f"{path}:{node.lineno}")
    return found


def _planted(tmp_path: Path, name: str, lines: list[tuple[str, bool]]) -> tuple[list[str], dict[str, list[str]]]:
    """The module of the lines written under `tmp_path`, and the `path:line` of each line marked as a breach."""
    path = tmp_path / name
    path.write_text("".join(f"{line}\n" for line, _ in lines))
    return [f"{path}:{number}" for number, (_, breach) in enumerate(lines, 1) if breach], _write_guard([path], tmp_path)


def _modules(root: Path) -> list[Path]:
    return sorted(root.rglob("*.py"))


def _real() -> dict[str, list[str]]:
    return _write_guard(_modules(VINTAGE_DIR), VINTAGE_DIR)


def test_a_rename_lives_only_in_the_three_helpers(tmp_path):
    assert _real()["rename"] == []
    expected, found = _planted(
        tmp_path,
        "storage.py",
        [
            ("import os", False),
            ("from os import replace as swap", False),
            ("def publish_tick(a, b): os.rename(a, b)", False),
            ("def publish_prom(a, b): os.replace(a, b)", False),
            ("def publish_table_dir(a, b): os.rename(a, b)", False),
            ("def publish_tick_later(a, b): os.rename(a, b)", True),
            ("def f(a, b): swap(a, b)", True),
            ("def f(a): os.renames(a, a)", True),
            ("def f(p, q): p.replace(q)", True),
            ("def f(p, q): p.rename(q)", True),
            ("def f(p, q): p.replace(target=q)", True),
            ("def f(p, q): p.rename(target=q)", True),
            ("def publish_tick(a, b):", False),
            ("    def inner(): os.rename(a, b)", True),
            ("class Publisher:", False),
            ("    def publish_tick(self, a, b): os.rename(a, b)", True),
            ("def publish_prom(a, b):", False),
            ("    class Inner: os.replace(a, b)", True),
            ("class Holder:", False),
            ("    def method(self, a, b):", False),
            ("        def publish_tick(): os.rename(a, b)", True),
            ("def outer(a, b):", False),
            ("    def publish_tick(): os.rename(a, b)", True),
            ("def f(s): s.replace('a', 'b')", False),
            ("def f(b): b.replace(b'/', b'\\\\/')", False),
            ("def f(t): t.replace(microsecond=0)", False),
            ("def publish_tick(s, a): s.callback(os.rename, a, a)", False),
            ("def f(s, a): s.callback(os.rename, a, a)", True),
            ("def f(): return swap", True),
            ("def f(s, p, q): s.callback(p.replace, q)", True),
            ("def f(p, q): p.rename.__call__(q)", True),
        ],
    )
    assert found["rename"] == expected
    elsewhere, found = _planted(tmp_path, "verify.py", [("import os", False), ("def publish_tick(a, b): os.rename(a, b)", True)])
    assert found["rename"] == elsewhere
    nested = tmp_path / "tree" / "pkg"
    nested.mkdir(parents=True)
    for directory in (tmp_path / "tree", nested):
        (directory / "storage.py").write_text("import os\ndef publish_tick(a, b): os.rename(a, b)\n")
    assert _write_guard(_modules(tmp_path / "tree"), tmp_path / "tree")["rename"] == [f"{nested / 'storage.py'}:2"]


def test_every_os_open_is_an_exclusive_create_or_a_read(tmp_path):
    assert _real()["os_open"] == []
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import os", False),
            ("import os as o", False),
            ("from os import open as raw", False),
            ("def f(p): os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)", False),
            ("def f(p): os.open(p, os.O_RDONLY)", False),
            ("def f(p): os.open(p, flags=os.O_RDONLY | os.O_DIRECTORY)", False),
            ("def f(p): o.open(p, o.O_RDWR | o.O_CREAT | o.O_EXCL)", False),
            ("def f(p): os.open(p, os.O_WRONLY | os.O_CREAT)", True),
            ("def f(p): os.open(p, os.O_RDWR)", True),
            ("def f(p): os.open(p, os.O_RDONLY | os.O_TRUNC)", True),
            ("def f(p): os.open(p, os.O_WRONLY | os.O_APPEND | os.O_EXCL)", True),
            ("def f(p, flags): os.open(p, flags)", True),
            ("def f(p): os.open(p, 0)", True),
            ("def f(p): os.open(p, os.O_RDONLY + os.O_EXCL)", True),
            ("def f(p): os.open(p)", True),
            ("def f(p): o.open(p, o.O_WRONLY)", True),
            ("def f(p): raw(p, os.O_RDWR)", True),
            ("def f(s, p): s.callback(os.open, p, os.O_RDWR)", True),
            ("def f(): return raw", True),
            ("def f(): return os.O_RDONLY", False),
        ],
    )
    assert found["os_open"] == expected


def test_mkstemp_lives_only_in_the_prom_helper(tmp_path):
    assert _real()["mkstemp"] == []
    expected, found = _planted(
        tmp_path,
        "storage.py",
        [
            ("import tempfile", False),
            ("from tempfile import mkstemp", False),
            ("def publish_prom(p): tempfile.mkstemp(dir=p)", False),
            ("def publish_tick(p): tempfile.mkstemp(dir=p)", True),
            ("def f(): mkstemp()", True),
            ("def publish_prom(s): s.callback(mkstemp)", False),
            ("def f(s): s.callback(tempfile.mkstemp)", True),
        ],
    )
    assert found["mkstemp"] == expected
    elsewhere, found = _planted(
        tmp_path, "verify.py", [("import tempfile", False), ("def publish_prom(p): tempfile.mkstemp(dir=p)", True)]
    )
    assert found["mkstemp"] == elsewhere


def test_write_parquet_lives_only_in_the_part_writer(tmp_path):
    assert _real()["write_parquet"] == []
    expected, found = _planted(
        tmp_path,
        "table.py",
        [
            ("from polars import DataFrame", False),
            ("def write_part(df, b): df.write_parquet(b)", False),
            ("def f(df, p): df.write_parquet(p)", True),
            ("def f(df, p): DataFrame.write_parquet(df, p)", True),
            ("def write_part(s, df, b): s.callback(df.write_parquet, b)", False),
            ("def f(s, df, p): s.callback(df.write_parquet, p)", True),
            ("def f(df, p): df.write_parquet.__call__(p)", True),
        ],
    )
    assert found["write_parquet"] == expected
    elsewhere, found = _planted(tmp_path, "derive.py", [("def write_part(df, b): df.write_parquet(b)", True)])
    assert found["write_parquet"] == elsewhere


def test_every_other_opening_call_reads(tmp_path):
    assert _real()["opening"] == []
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import codecs, gzip, io", False),
            ("from gzip import open as gz", False),
            ("def f(p): open(p)", False),
            ("def f(p): open(p, 'rb')", False),
            ("def f(p): io.open(p, mode='r')", False),
            ("def f(p): p.open('rb')", False),
            ("def f(b): gzip.GzipFile(fileobj=b, mode='wb')", False),
            ("def _dial(p): return p.open('rb')", False),
            ("def _dial(o, r): return o.open(r, timeout=30)", True),
            ("def f(p): open(p, 'w')", True),
            ("def f(p): open(p, mode='a')", True),
            ("def f(p, m): open(p, m)", True),
            ("def f(p): open(p, b'r')", True),
            ("def f(p): io.open(p, 'r+')", True),
            ("def f(p): codecs.open(p, 'x')", True),
            ("def f(p): gzip.open(p, 'wb')", True),
            ("def f(p): gz(p, 'ab')", True),
            ("def f(p): gzip.GzipFile(p, 'wb')", True),
            ("def f(p): gzip.GzipFile(p, 'wb', fileobj=None)", True),
            ("def f(p): p.open('w')", True),
            ("def f(p): p.open(mode='a')", True),
            ("def f(o, r): o.open(r, timeout=30)", True),
            ("def _dial(p): return p.open('w')", True),
            ("def _dial(p): return p.open(mode='wb')", True),
            ("def f(ps): return map(open, ps)", True),
            ("def f(): return gzip.open", True),
            ("def f(p): return p.open", True),
            ("def f(p): p.open.__call__('w')", True),
            ("import typer", False),
            ("def f(): return typer.Option(None, mode='rb')", False),
            ("def f(): return typer.Option(None, mode='w')", True),
            ("def f(m): return typer.Argument(None, mode=m)", True),
        ],
    )
    assert found["opening"] == expected
    dial, found = _planted(
        tmp_path,
        "fetch.py",
        [
            ("def _dial(o, r): return o.open(r, timeout=30)", False),
            ("def _dial(p): return p.open('rb')", False),
            ("def _dial(p, m): return p.open(m)", True),
            ("def _dial(p, m): return p.open(mode=m)", True),
            ("def _dial(p): return p.open('w')", True),
            ("def _dial(o, r, m): return o.open(r, m, timeout=30)", True),
            ("def _dial(o, r): return o.open(r, timeout=30, mode='w')", True),
            ("def f(o, r): return o.open(r, timeout=30)", True),
            ("class Dialer:", False),
            ("    def _dial(self, o, r): return o.open(r, timeout=30)", True),
        ],
    )
    assert found["opening"] == dial
    nested = tmp_path / "tree" / "pkg"
    nested.mkdir(parents=True)
    for directory in (tmp_path / "tree", nested):
        (directory / "fetch.py").write_text("def _dial(o, r): return o.open(r, timeout=30)\n")
    assert _write_guard(_modules(tmp_path / "tree"), tmp_path / "tree")["opening"] == [f"{nested / 'fetch.py'}:1"]


def test_no_copy_move_truncate_or_delete(tmp_path):
    assert _real()["fs"] == []
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import contextlib, gzip, io, os, pathlib, shutil, tempfile", False),
            ("import os as o", False),
            ("from os import fsync", False),
            ("from os.path import join", False),
            ("from pathlib import Path", False),
            ("from os import remove", True),
            ("from shutil import copyfile as c", True),
            ("def f(fd): fsync(fd)", False),
            ("def f(p): os.path.exists(p)", False),
            ("def f(): os.environ.get('X')", False),
            ("def f(p): Path(p)", False),
            ("def f(d): d.copy()", False),
            ("def f(df, b): df.write_parquet(b)", False),
            ("def f(a, b): shutil.copyfile(a, b)", True),
            ("def f(a, b): shutil.move(a, b)", True),
            ("def f(a): shutil.rmtree(a)", True),
            ("def f(a, b): c(a, b)", True),
            ("def f(p): os.remove(p)", True),
            ("def f(p): o.unlink(p)", True),
            ("def f(fd): os.ftruncate(fd, 0)", True),
            ("def f(p): io.FileIO(p, 'w')", True),
            ("def f(): tempfile.mkdtemp()", True),
            ("def f(a): os.renames(a, a)", True),
            ("def f(p): Path(p).unlink()", True),
            ("def f(p): pathlib.Path(p).rmdir()", True),
            ("def f(p): p.truncate()", True),
            ("def f(p): p.write_bytes(b'')", True),
            ("def f(p): p.write_text('')", True),
            ("def f(p): p.touch()", True),
            ("def f(p, q): p.symlink_to(q)", True),
            ("def f(p, q): p.hardlink_to(q)", True),
            ("def f(p, q): p.copy(q)", True),
            ("def f(p, q): p.copy_into(q)", True),
            ("def f(p, q): p.move(q)", True),
            ("def f(p, q): p.move_into(q)", True),
            ("def f(df, p): df.write_csv(p)", True),
            ("def f(df, p): df.sink_parquet(p)", True),
            ("def f(p): contextlib.ExitStack().callback(os.unlink, p)", True),
            ("def f(ps): return map(os.remove, ps)", True),
            ("m = shutil.move", True),
            ("def f(s, p): s.callback(p.unlink)", True),
            ("def f(s, d): s.callback(d.copy)", True),
            ("def f(df): return df.write_csv", True),
            ("def f(p): p.unlink.__call__()", True),
            ("def f(s, p): s.callback(p.unlink.__call__)", True),
            ("def f(p): p.write_text.__call__('x')", True),
            ("def f(p, q): p.unlink.unlink(q)", True),
            ("def f(df, p): df.serialize(p)", True),
            ("def f(df): return df.serialize()", False),
            ("def f(s, df): s.callback(df.serialize)", True),
            ("def f(config, p): config.save_to_file(p)", True),
            ("def f(lf, p): lf.show_graph(output_path=p)", True),
            ("def f(): return shutil", True),
            ("def f(): return os.environ", False),
            ("def f(): return fsync", False),
            ("def f(): return Path", False),
            ("def f(b):", False),
            ("    try: return b()", False),
            ("    except (EOFError, gzip.BadGzipFile): return None", False),
        ],
    )
    assert found["fs"] == expected
    nested = tmp_path / "tree" / "sub"
    nested.mkdir(parents=True)
    (nested / "verify.py").write_text("import os\ndef f(p): os.remove(p)\n")
    assert _write_guard(_modules(tmp_path / "tree"), tmp_path / "tree")["fs"] == [f"{nested / 'verify.py'}:2"]


def test_cli_vintage_imports_only_the_pinned_modules(tmp_path):
    assert _real()["imports"] == []
    imported = {
        name
        for path in _modules(VINTAGE_DIR)
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path)))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for name in _imported(node)
    }
    assert imported == VINTAGE_IMPORTS
    assert not VINTAGE_IMPORTS & {"subprocess", "zipfile", "bz2", "lzma", "tarfile", "sqlite3", "shelve", "dbm"}
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import os", False),
            ("import polars as pl", False),
            ("import cli.vintage.storage", False),
            ("from pathlib import Path", False),
            ("from cli.vintage.chain import scan", False),
            ("import subprocess", True),
            ("from zipfile import ZipFile", True),
            ("import os.path", True),
            ("import gzip, tarfile", True),
            ("from . import storage", True),
            ("def f():", False),
            ("    import bz2", True),
        ],
    )
    assert found["imports"] == expected


def test_no_logging_handler_writes_a_file(tmp_path):
    assert _real()["logging_file"] == []
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import logging", False),
            ("import logging.handlers", False),
            ("from logging.handlers import RotatingFileHandler as Rotating", True),
            ("def f(): return logging.getLogger('vintage')", False),
            ("def f(log): log.log(logging.ERROR, 'x')", False),
            ("def f(): logging.basicConfig(level=logging.INFO)", False),
            ("def f(p): logging.FileHandler(p)", True),
            ("def f(p): logging.handlers.TimedRotatingFileHandler(p)", True),
            ("def f(p): Rotating(p)", True),
            ("def f(p): logging.basicConfig(filename=p)", True),
            ("def f(s, p): s.callback(logging.handlers.WatchedFileHandler, p)", True),
            ("class Handler(logging.FileHandler): pass", True),
        ],
    )
    assert found["logging_file"] == expected


def test_cli_vintage_takes_only_the_pinned_names(tmp_path):
    assert _real()["names"] == []
    taken = defaultdict(set)
    for path in _modules(VINTAGE_DIR):
        tree = ast.parse(path.read_text(), filename=str(path))
        for module, name, _ in _taken(tree, _bindings(tree)):
            taken[module].add(name)
    assert {module: frozenset(names) for module, names in taken.items()} == VINTAGE_NAMES
    writers = {
        ("cli.capture.command", "SegmentWriter"),
        ("cli.capture.command", "os"),
        ("cli.logging", "configure"),
        ("compression.zstd", "ZstdFile"),
        ("compression.zstd", "open"),
        ("polars", "Config"),
        ("typer", "FileBinaryWrite"),
        ("typer", "FileTextWrite"),
        ("urllib.request", "urlretrieve"),
    }
    assert {(module, name) for module, name in writers if name in VINTAGE_NAMES.get(module, ())} == set()
    expected, found = _planted(
        tmp_path,
        "verify.py",
        [
            ("import compression.zstd, os, polars as pl, typer, urllib.request", False),
            ("from urllib.request import Request, urlretrieve", True),
            ("from compression.zstd import ZstdFile", True),
            ("from cli.logging import configure, get_logger", True),
            ("from cli.capture.command import SegmentWriter", True),
            ("from cli.capture.command import os as o", True),
            ("def f(u, p): urllib.request.urlretrieve(u, p)", True),
            ("def f(p): compression.zstd.open(p, 'wb')", True),
            ("def f(p): pl.Config.save_to_file(p)", True),
            ("def f(p: typer.FileTextWrite): return p", True),
            ("def f(p: typer.FileBinaryWrite): return p", True),
            ("def f(p): os.open(p, os.O_RDONLY)", False),
            ("def f(u): return urllib.request.Request(u)", False),
            ("def f(): return pl.DataFrame()", False),
            ("def f(): return typer.Option(None)", False),
        ],
    )
    assert found["names"] == expected


def test_the_guard_admits_the_allowed_forms(tmp_path):
    assert _real() == {rule: [] for rule in _RULES}
    _, found = _planted(
        tmp_path,
        "fetch.py",
        [
            ("import gzip, os", False),
            ("from os import fsync", False),
            ("def exclusive(p): return os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)", False),
            ("def read_only(p): return os.open(p, os.O_RDONLY)", False),
            ("def read(p): return open(p, 'rb')", False),
            ("def read_path(p): return p.open('rb')", False),
            ("def compress_onto(f): return gzip.GzipFile(fileobj=f, mode='wb')", False),
            ("def _dial(o, r): return o.open(r, timeout=30)", False),
            ("def escaped(): return b'/'.replace(b'/', b'\\\\/')", False),
            ("def floored(now): return now.replace(microsecond=0)", False),
            ("def copied(d): return d.copy()", False),
            ("def synced(fd): fsync(fd)", False),
        ],
    )
    assert {rule: lines for rule, lines in found.items() if rule != "names"} == {rule: [] for rule in _RULES if rule != "names"}
