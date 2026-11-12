from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.vintage.verify as verify_module
from cli.__main__ import app
from cli.vintage.record import tick_json_bytes
from cli.vintage.sources import ForkAcknowledgment, LinkAcknowledgment
from cli.vintage.verify import verify
from tests.vintage_fixtures import BASE_TICK_START
from tests.vintage_stub import build_record, run_tick

T0 = BASE_TICK_START
HOUR = timedelta(hours=1)
SUMMARY = re.compile(
    r" (INFO|ERROR) .* vintage verify complete ticks=(\d+) head=(\S+) head_tick_json_sha256=(\S+) bodies_hashed=(\d+) breaks=(\d+)$"
)
runner = CliRunner()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cli(root: Path, *args: str):
    return runner.invoke(app, ["vintage", "verify", "--root", str(root), *args])


def _lines(result, level: str) -> list[str]:
    return [line for line in result.output.splitlines() if f" {level} " in line and "vintage verify complete" not in line]


def _summary(result) -> tuple[str, ...]:
    found = [match.groups() for line in result.output.splitlines() if (match := SUMMARY.search(line))]
    assert len(found) == 1, result.output
    return found[0]


def _kinds(findings) -> list[str]:
    return [finding.kind for finding in findings]


def _opened(tick_dir: Path) -> None:
    os.chmod(tick_dir, 0o755)


def _replace(path: Path, data: bytes) -> None:
    _opened(path.parent)
    path.unlink()
    path.write_bytes(data)


def _removed(tick_dir: Path) -> None:
    _opened(tick_dir)
    shutil.rmtree(tick_dir)


def _set_aside(tick_dir: Path) -> Path:
    aside = tick_dir.with_name(tick_dir.name + ".aside")
    tick_dir.rename(aside)
    return aside


def _edited(tick_dir: Path, recorder: str) -> bytes:
    """The tick's `tick.json` with its `recorder` changed: valid, and consistent with the bodies its directory holds."""
    manifest = json.loads((tick_dir / "tick.json").read_bytes())
    return tick_json_bytes(manifest | {"recorder": recorder})


def _other_body(path: Path) -> None:
    _replace(path, gzip.compress(b"other bytes", compresslevel=9, mtime=0))


def _four(tmp_path: Path):
    return build_record(tmp_path, [(T0 + i * 3 * HOUR, {}) for i in range(4)])


def _bodies(published) -> int:
    manifest = json.loads((published.dir / "tick.json").read_bytes())
    return sum(1 for fetch in manifest["fetches"] if fetch["body"] is not None)


def _fork(tmp_path: Path):
    """Four ticks, the third set aside while the fourth ran, then put back: the third and the fourth both name the
    second, the fourth on the chain and the third off it."""
    first, second, third = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {}), (T0 + 6 * HOUR, {})])
    aside = _set_aside(third.dir)
    fourth = run_tick(tmp_path, T0 + 9 * HOUR)
    aside.rename(third.dir)
    return tmp_path / "record", (first, second, third, fourth)


def test_a_clean_record_and_an_empty_one_exit_0(tmp_path):
    _four(tmp_path)
    root = tmp_path / "record"
    clean = _cli(root)
    assert clean.exit_code == 0, clean.output
    assert _lines(clean, "ERROR") == []
    found = verify(root)
    assert (found.breaks, found.notes) == ([], [])

    empty = tmp_path / "empty"
    empty.mkdir()
    read = _cli(empty)
    assert read.exit_code == 0, read.output
    assert (verify(empty).breaks, verify(empty).notes) == ([], [])


def test_the_summary_line_counts_what_it_read(tmp_path):
    published = _four(tmp_path)
    root = tmp_path / "record"
    head = published[-1]
    result = _cli(root)
    assert _summary(result) == (
        "INFO",
        "4",
        head.stamp,
        _sha((head.dir / "tick.json").read_bytes()),
        str(sum(_bodies(tick) for tick in published)),
        "0",
    )
    found = verify(root)
    assert (found.ticks, found.head, found.head_tick_json_sha256) == (4, head.stamp, head.tick_json_sha256)

    empty = tmp_path / "empty"
    empty.mkdir()
    assert _summary(_cli(empty)) == ("INFO", "0", "none", "none", "0", "0")


def _missing_root(tmp_path):
    root = tmp_path / "absent"
    return root, "missing root", [root]


def _tampered_body(tmp_path):
    published = _four(tmp_path)
    path = published[1].dir / "cm-btc.jsonl.gz"
    _other_body(path)
    return tmp_path / "record", "tampered body", [path]


def _missing_body(tmp_path):
    published = _four(tmp_path)
    path = published[1].dir / "fng.json.gz"
    _opened(path.parent)
    path.unlink()
    return tmp_path / "record", "missing body", [path]


def _missing_tick(tmp_path):
    published = _four(tmp_path)
    _removed(published[1].dir)
    return tmp_path / "record", "missing tick", [published[1].dir]


def _broken_link(tmp_path):
    published = _four(tmp_path)
    _replace(published[1].dir / "tick.json", _edited(published[1].dir, "other"))
    return tmp_path / "record", "broken link", [published[2].dir / "tick.json"]


def _unreadable_manifest(tmp_path):
    published = _four(tmp_path)
    path = published[1].dir / "tick.json"
    _replace(path, b"{not json")
    return tmp_path / "record", "unreadable manifest", [path]


def _forked(tmp_path):
    root, (_, _, third, fourth) = _fork(tmp_path)
    return root, "fork", [third.dir, fourth.dir]


def _unlisted_file(tmp_path):
    published = _four(tmp_path)
    path = published[1].dir / ".cm-btc.jsonl.gz.Ab12Cd"
    _opened(path.parent)
    path.write_bytes(b"a partial transfer")
    return tmp_path / "record", "unlisted file", [path]


@pytest.mark.parametrize(
    "damage",
    [
        _missing_root,
        _tampered_body,
        _missing_body,
        _missing_tick,
        _broken_link,
        _unreadable_manifest,
        _forked,
        _unlisted_file,
    ],
    ids=[
        "missing-root",
        "tampered-body",
        "missing-body",
        "missing-tick",
        "broken-link",
        "unreadable-manifest",
        "fork",
        "unlisted-file",
    ],
)
def test_each_break_exits_1_naming_its_path(tmp_path, damage):
    root, kind, paths = damage(tmp_path)
    result = _cli(root)
    assert result.exit_code == 1, result.output
    named = [line for line in _lines(result, "ERROR") if f"vintage verify {kind} " in line]
    assert named, result.output
    for path in paths:
        assert any(str(path) in line for line in named), (path, named)
    assert _summary(result)[0] == "ERROR"
    assert kind in _kinds(verify(root).breaks)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
@pytest.mark.parametrize("mode", [0o111, 0o000], ids=["listing-refused", "no-access"])
def test_an_unreadable_tick_directory_is_a_break_naming_it(tmp_path, request, mode):
    tick_dir = _four(tmp_path)[1].dir
    request.addfinalizer(lambda: os.chmod(tick_dir, 0o555))
    os.chmod(tick_dir, mode)
    result = _cli(tmp_path / "record")
    assert result.exit_code == 1, result.output
    named = [line for line in _lines(result, "ERROR") if "vintage verify unreadable manifest " in line]
    assert any(str(tick_dir) in line for line in named), result.output
    assert _summary(result)[0] == "ERROR"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
@pytest.mark.parametrize("mode", [0o000, 0o444], ids=["no-access", "listing-only"])
def test_an_unreadable_date_directory_holding_the_newest_ticks_never_reads_clean(tmp_path, request, mode):
    published = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {}), (T0 + 24 * HOUR, {}), (T0 + 27 * HOUR, {})])
    day = published[-1].dir.parent
    assert published[-2].dir.parent == day != published[1].dir.parent
    request.addfinalizer(lambda: os.chmod(day, 0o755))
    os.chmod(day, mode)
    result = _cli(tmp_path / "record")
    assert result.exit_code == 1, result.output
    named = [line for line in _lines(result, "ERROR") if "vintage verify unreadable manifest " in line]
    assert any(str(day) in line for line in named), result.output
    assert _summary(result)[0] == "ERROR"


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file permissions")
def test_an_unreadable_body_is_named_unreadable(tmp_path, request):
    path = _four(tmp_path)[1].dir / "cm-btc.jsonl.gz"
    request.addfinalizer(lambda: os.chmod(path, 0o444))
    os.chmod(path, 0o000)
    found = verify(tmp_path / "record")
    assert [(finding.kind, finding.path, finding.detail) for finding in found.breaks] == [
        ("tampered body", str(path), "unreadable: PermissionError")
    ]


def test_a_chain_with_no_head_candidate_is_a_broken_link(tmp_path):
    first, second = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {})])
    manifest = json.loads((first.dir / "tick.json").read_bytes())
    closed = manifest | {"prev": {"tick": second.stamp, "tick_json_sha256": second.tick_json_sha256, "error": None}}
    _replace(first.dir / "tick.json", tick_json_bytes(closed))
    found = verify(tmp_path / "record")
    cycle = [finding for finding in found.breaks if "no tick is a head candidate" in finding.detail]
    assert _kinds(cycle) == ["broken link"]


def test_a_stamp_regression_is_named_and_exits_0(tmp_path):
    published = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {}), (T0 + 12 * HOUR, {}), (T0 + 11 * HOUR, {})])
    newest, regression = published[2], published[3]
    root = tmp_path / "record"
    result = _cli(root)
    assert result.exit_code == 0, result.output
    named = [line for line in _lines(result, "INFO") if "vintage verify clock regression " in line]
    assert len(named) == 1 and regression.stamp in named[0] and newest.stamp in named[0], result.output
    found = verify(root)
    assert (_kinds(found.breaks), _kinds(found.notes)) == ([], ["clock regression"])


def test_a_link_carrying_the_chaining_error_is_named_and_exits_0(tmp_path):
    first, second = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {})])
    body = second.dir / "cm-btc.jsonl.gz"
    kept = body.read_bytes()
    _other_body(body)
    third = run_tick(tmp_path, T0 + 6 * HOUR)
    assert json.loads((third.dir / "tick.json").read_bytes())["prev"]["error"] is not None
    _replace(body, kept)
    run_tick(tmp_path, T0 + 9 * HOUR)
    root = tmp_path / "record"
    result = _cli(root)
    assert result.exit_code == 0, result.output
    named = [line for line in _lines(result, "INFO") if "vintage verify link carries the chaining error " in line]
    assert len(named) == 1 and str(third.dir) in named[0], result.output
    found = verify(root)
    assert (_kinds(found.breaks), _kinds(found.notes)) == ([], ["link carries the chaining error"])


def test_an_acknowledged_link_exits_0_and_its_mismatch_exits_1(tmp_path, monkeypatch):
    first, second, predecessor = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {}), (T0 + 6 * HOUR, {})])
    tick_json = predecessor.dir / "tick.json"
    witnessed = tick_json.read_bytes()
    recorded = _edited(predecessor.dir, "edited before its successor ran")
    _replace(tick_json, recorded)
    successor = run_tick(tmp_path, T0 + 9 * HOUR)
    _replace(tick_json, witnessed)
    root = tmp_path / "record"
    entry = LinkAcknowledgment(successor.stamp, _sha(recorded), _sha(witnessed))

    assert _cli(root).exit_code == 1
    assert _kinds(verify(root).breaks) == ["broken link"]
    monkeypatch.setattr(verify_module, "LINK_ACKNOWLEDGMENTS", (entry,))
    result = _cli(root)
    assert result.exit_code == 0, result.output
    named = [line for line in _lines(result, "INFO") if "vintage verify acknowledged link " in line]
    assert len(named) == 1 and str(successor.dir) in named[0], result.output
    found = verify(root, acknowledgments=(entry,))
    assert (_kinds(found.breaks), _kinds(found.notes)) == ([], ["acknowledged link"])
    assert successor.stamp in found.notes[0].path

    _replace(tick_json, _edited(predecessor.dir, "other bytes again"))
    assert _cli(root).exit_code == 1
    assert _kinds(verify(root, acknowledgments=(entry,)).breaks) == ["acknowledged link mismatch"]

    _replace(tick_json, witnessed)
    _removed(successor.dir)
    assert _cli(root).exit_code == 0
    before = verify(root, acknowledgments=(entry,))
    assert (before.breaks, before.notes, before.head) == ([], [], predecessor.stamp)


def test_an_acknowledged_fork_exits_0_and_its_mismatch_exits_1(tmp_path, monkeypatch):
    root, (_, _, off_chain, _) = _fork(tmp_path)
    entry = ForkAcknowledgment(off_chain.stamp, off_chain.tick_json_sha256)

    monkeypatch.setattr(verify_module, "FORK_ACKNOWLEDGMENTS", (entry,))
    result = _cli(root)
    assert result.exit_code == 0, result.output
    named = [line for line in _lines(result, "INFO") if "vintage verify acknowledged fork " in line]
    assert len(named) == 1 and str(off_chain.dir) in named[0], result.output
    found = verify(root, forks=(entry,))
    assert (_kinds(found.breaks), _kinds(found.notes)) == ([], ["acknowledged fork"])

    other = ForkAcknowledgment(off_chain.stamp, _sha(b"another tick.json"))
    monkeypatch.setattr(verify_module, "FORK_ACKNOWLEDGMENTS", (other,))
    assert _cli(root).exit_code == 1
    assert _kinds(verify(root, forks=(other,)).breaks) == ["fork"]

    body = off_chain.dir / "cm-btc.jsonl.gz"
    kept = body.read_bytes()
    _other_body(body)
    tampered = verify(root, forks=(entry,))
    assert (_kinds(tampered.breaks), tampered.breaks[0].path) == (["tampered body"], str(body))
    _replace(body, kept)

    _removed(off_chain.dir)
    monkeypatch.setattr(verify_module, "FORK_ACKNOWLEDGMENTS", (entry,))
    ops = _cli(root)
    assert ops.exit_code == 0, ops.output
    assert _lines(ops, "ERROR") == [] and [line for line in _lines(ops, "INFO") if "vintage verify " in line] == []
    shape = verify(root, forks=(entry,))
    assert (shape.breaks, shape.notes) == ([], [])

    custody = _cli(root, "--custody")
    assert custody.exit_code == 1, custody.output
    named = [line for line in _lines(custody, "ERROR") if "vintage verify missing tick " in line]
    assert len(named) == 1 and str(off_chain.dir) in named[0], custody.output
    missing = verify(root, forks=(entry,), custody=True)
    assert (_kinds(missing.breaks), missing.breaks[0].path) == (["missing tick"], str(off_chain.dir))

    lost = ForkAcknowledgment(off_chain.stamp, off_chain.tick_json_sha256, lost=True)
    monkeypatch.setattr(verify_module, "FORK_ACKNOWLEDGMENTS", (lost,))
    marked = _cli(root, "--custody")
    assert marked.exit_code == 0, marked.output
    named = [line for line in _lines(marked, "INFO") if "vintage verify lost tick " in line]
    assert len(named) == 1 and str(off_chain.dir) in named[0], marked.output
    read = verify(root, forks=(lost,), custody=True)
    assert (_kinds(read.breaks), _kinds(read.notes), read.notes[0].path) == ([], ["lost tick"], str(off_chain.dir))


def test_newest_takes_the_chain_not_the_stamps(tmp_path):
    published = build_record(tmp_path, [(T0, {}), (T0 + 3 * HOUR, {}), (T0 + 12 * HOUR, {}), (T0 + 11 * HOUR, {})])
    newest_stamp, head = published[2], published[3]
    root = tmp_path / "record"
    # No stamp index is 4 modulo 5 among four ticks, so the newest tick along the chain is the only one re-hashed.
    only_newest = ("--newest", "1", "--slice", "4", "--slices", "5")

    body = head.dir / "cm-btc.jsonl.gz"
    kept = body.read_bytes()
    _other_body(body)
    result = _cli(root, *only_newest)
    assert result.exit_code == 1, result.output
    assert any("vintage verify tampered body " in line and str(body) in line for line in _lines(result, "ERROR"))
    assert _summary(result)[4] == str(_bodies(head))
    _replace(body, kept)

    _other_body(newest_stamp.dir / "cm-btc.jsonl.gz")
    assert _cli(root, *only_newest).exit_code == 0


def test_slice_takes_exactly_its_ticks(tmp_path):
    hours = (0, 3, 6, 12, 9)
    published = build_record(tmp_path, [(T0 + hour * HOUR, {}) for hour in hours])
    body = published[3].dir / "cm-btc.jsonl.gz"
    _other_body(body)
    root = tmp_path / "record"

    sliced = _cli(root, "--newest", "0", "--slice", "1", "--slices", "3")
    assert sliced.exit_code == 1, sliced.output
    assert any("vintage verify tampered body " in line and str(body) in line for line in _lines(sliced, "ERROR"))
    passed = _cli(root, "--newest", "0", "--slice", "0", "--slices", "3")
    assert passed.exit_code == 0, passed.output
