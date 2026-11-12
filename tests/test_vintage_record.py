from __future__ import annotations

import base64
import errno
import gzip
import hashlib
import itertools
import json
import logging
import os
import re
import shutil
import stat
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

import cli.vintage.record as record_module
import cli.vintage.storage as storage_module
from cli.vintage.chain import chain, scan
from cli.vintage.credential import ApiKey
from cli.vintage.record import RecordRefused, record_tick
from cli.vintage.sources import SOURCE_BY_ID, SOURCES
from cli.vintage.storage import create_exclusive, publish_tick
from tests.vintage_fixtures import BASE_TICK_START, SENTINEL_KEY, body
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
    found = chain(scan(tmp_path / "record"))
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
    assert scan(tmp_path / "record") == []
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
    before = chain(scan(root))
    day = head.dir.parent
    (day / "20261111T080000Z").write_bytes(b"a stray file\n")
    partial = day / ".20261111T093700Z.rsync-tmp"
    partial.mkdir()
    (partial / "tick.json").write_bytes((head.dir / "tick.json").read_bytes())
    (root / ".rsync-tmp").mkdir()
    (root / "2026" / "11" / "12").mkdir()
    assert chain(scan(root)) == before
    following = run_tick(tmp_path, T0 + 8 * HOUR)
    assert _manifest(following)["prev"] == {"tick": head.stamp, "tick_json_sha256": head.tick_json_sha256, "error": None}


def test_an_unreadable_middle_tick_json_keeps_the_chain_whole(tmp_path):
    a, b, c = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {}), (T0 + 2 * HOUR, {})])
    _opened(b.dir)
    _unparseable(b.dir)
    found = chain(scan(tmp_path / "record"))
    assert [tick.stamp for tick in found.order] == [a.stamp, b.stamp, c.stamp]
    assert found.head.stamp == c.stamp
    assert found.other_heads == ()
    assert [tick.stamp for tick in found.unreadable] == [b.stamp]


def test_a_cycle_of_prev_links_chains_to_the_newest_tick_with_an_error(tmp_path):
    a, b = build_record(tmp_path, [(T0, {}), (T0 + HOUR, {})])
    _opened(a.dir)
    closed = _manifest(a) | {"prev": {"tick": b.stamp, "tick_json_sha256": b.tick_json_sha256, "error": None}}
    _replace(a.dir / "tick.json", json.dumps(closed, sort_keys=True, separators=(",", ":")).encode() + b"\n")
    found = chain(scan(tmp_path / "record"))
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
