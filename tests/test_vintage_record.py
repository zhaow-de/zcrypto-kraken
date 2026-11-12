from __future__ import annotations

import base64
import errno
import fcntl
import gzip
import hashlib
import io
import itertools
import json
import logging
import os
import re
import shutil
import stat
from contextlib import contextmanager
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

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
