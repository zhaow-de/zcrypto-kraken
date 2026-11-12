from __future__ import annotations

import copy
import dataclasses
import fcntl
import gzip
import hashlib
import io
import json
import logging
import os
import re
import shutil
import stat
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import polars as pl
import pytest

import cli.vintage.command as command_module
import cli.vintage.derive as derive_module
import cli.vintage.storage as storage_module
import cli.vintage.table as table_module
from cli.capture.command import LOCKFILE_NAME
from cli.config import load_config
from cli.vintage.asof import as_of
from cli.vintage.chain import TickFile, chain, scan
from cli.vintage.derive import DERIVE_GENERATION, HEAD_PINS, DeriveState, derive_record, derive_tick, frames
from cli.vintage.record import Published
from cli.vintage.sources import SOURCE_BY_ID, SOURCES, LinkAcknowledgment
from cli.vintage.storage import refuse_table_root
from cli.vintage.table import TableError, derive_table, frame_hash, head, read_table
from tests.vintage_fixtures import BASE_TICK_START, body
from tests.vintage_stub import FakeClock, Reply, build_record, run_tick, standard_record

T0 = BASE_TICK_START
HOUR = timedelta(hours=1)
RUN_AT = T0 + timedelta(days=30, seconds=17)
NAS = Path("/mnt/zhao-crypto")
STATUS_FILE = SOURCE_BY_ID["cm-status"].file
ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


def _derive(record_root: Path, table_root: Path, **kwargs):
    return derive_table(record_root, table_root, nas_mount=NAS, opened_by="0.0.0", clock=FakeClock(RUN_AT), **kwargs)


def _dated(root: Path, stamp: str) -> Path:
    return root / stamp[:4] / stamp[4:6] / stamp[6:8] / stamp


def _gen(table_root: Path, generation: int = 1) -> Path:
    return table_root / f"gen-{generation}"


def _head_file(table_root: Path, stamp: str, generation: int = 1) -> Path:
    return _dated(_gen(table_root, generation) / "heads", stamp) / "head.json"


def _part_dir(table_root: Path, stamp: str, generation: int = 1) -> Path:
    return _dated(_gen(table_root, generation) / "parts", stamp)


def _heads(table_root: Path, generation: int = 1) -> dict[str, bytes]:
    return {
        path.parent.name: path.read_bytes() for path in sorted((_gen(table_root, generation) / "heads").glob("*/*/*/*/head.json"))
    }


def _parts(table_root: Path, generation: int = 1) -> list[str]:
    return sorted(path.name for path in (_gen(table_root, generation) / "parts").glob("*/*/*/*"))


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _order(record_root: Path) -> tuple[TickFile, ...]:
    return chain(scan(record_root).ticks).order


def _stamps(record_root: Path) -> list[str]:
    return [tick.stamp for tick in _order(record_root)]


def fixture_head_sha256(root: Path) -> str:
    """The sha256 of the last head of a table derived from `standard_record` under `root`."""
    standard_record(root / "vintages")
    outcome = _derive(root / "vintages" / "record", root / "versions")
    assert outcome.complete, outcome
    return _sha(_head_file(root / "versions", outcome.head["tick"]).read_bytes())


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> Path:
    """The standard record's data root, built once; a test copies it before it changes anything."""
    root = tmp_path_factory.mktemp("standard")
    standard_record(root)
    return root / "record"


# cm-btc along a restatement, a retraction, its restoration under a clock regression, and new days; mempool restated
# once; every other cm-* source and fng answering 404, so the record keeps its kinds and a later fact at a fifth of the
# standard record's rows.
_COMPACT_LEGS = (
    ("cm-btc", 0),
    ("second/cm-btc-restatement", 3),
    ("second/cm-btc-retraction", 7),
    ("cm-btc", 6),
    ("second/cm-btc-next", 10),
)


@pytest.fixture(scope="module")
def compact(tmp_path_factory) -> Path:
    gone = Reply(404, b"not found", reason="Not Found")
    unserved = {
        source.id: gone for source in SOURCES if source.id == "fng" or (source.kind == "cm-asset" and source.id != "cm-btc")
    }
    plan = []
    for name, hours in _COMPACT_LEGS:
        replies = {**unserved, "cm-btc": body(name)}
        if name == "second/cm-btc-restatement":
            replies["mempool-hashrate"] = body("second/mempool-hashrate-restated-big")
        plan.append((T0 + hours * HOUR, replies))
    root = tmp_path_factory.mktemp("compact")
    build_record(root, plan)
    return root / "record"


def _copy(record_root: Path, into: Path) -> Path:
    shutil.copytree(record_root, into)
    return into


def _nas_shaped(record_root: Path) -> Path:
    for directory, _, files in os.walk(record_root):
        os.chmod(directory, 0o775)
        for name in files:
            os.chmod(Path(directory) / name, 0o664)
    return record_root


def _grow(source: Path, record_root: Path, count: int, *, nas: bool = False) -> None:
    """The first `count` ticks of `source`, by stamp, present in `record_root`, as a record that grew tick by tick."""
    for tick in scan(source).ticks[:count]:
        target = record_root / tick.dir.relative_to(source)
        if not target.exists():
            shutil.copytree(tick.dir, target)
    if nas:
        _nas_shaped(record_root)


def _opened(directory: Path) -> int:
    mode = stat.S_IMODE(directory.stat().st_mode)
    os.chmod(directory, 0o755)
    return mode


def _rewrite(path: Path, data: bytes) -> None:
    mode = _opened(path.parent)
    try:
        path.unlink()
        path.write_bytes(data)
        os.chmod(path, 0o444)
    finally:
        os.chmod(path.parent, mode)


def _removed(directory: Path) -> None:
    for inner, _, _ in os.walk(directory):
        os.chmod(inner, 0o755)
    mode = _opened(directory.parent)
    try:
        shutil.rmtree(directory)
    finally:
        os.chmod(directory.parent, mode)


def _edited_tick_json(tick_dir: Path, recorder: str) -> bytes:
    original = (tick_dir / "tick.json").read_bytes()
    manifest = json.loads(original)
    _rewrite(tick_dir / "tick.json", _canonical(manifest | {"recorder": recorder}))
    return original


def _snapshot(root: Path) -> dict[str, tuple[int, bytes | None]]:
    found = {}
    for path in sorted(root.rglob("*")):
        mode = stat.S_IMODE(path.lstat().st_mode)
        found[str(path.relative_to(root))] = (mode, path.read_bytes() if path.is_file() else None)
    return found


def _no_config(monkeypatch, tmp_path: Path) -> Path:
    nas = tmp_path / "nas"
    monkeypatch.setattr(
        command_module, "load_config", lambda: dataclasses.replace(load_config(tmp_path / "absent.toml"), nfs_mount_dir=nas)
    )
    return nas


def _run(record_root: Path, table_root: Path, *, textfile: Path | None = None, through: str | None = None, **kwargs) -> int:
    kwargs = {"version": "0.0.0", "revision": "", **kwargs}
    return command_module.run_derive(record_root, table_root, textfile=textfile, through=through, clock=FakeClock(RUN_AT), **kwargs)


def _messages(caplog, level: int) -> list[str]:
    return [record.getMessage() for record in caplog.records if record.levelno == level]


def _small(data_root: Path, count: int, *, start: int = 0) -> list[Published]:
    return build_record(data_root, [(T0 + 3 * (start + i) * HOUR, {}) for i in range(count)])


def test_three_tables_agree_head_by_head(standard, tmp_path):
    stamps = _stamps(standard)
    tick_by_tick = tmp_path / "tick-by-tick"
    for count in range(1, len(stamps) + 1):
        _grow(standard, tmp_path / "ops" / "record", count)
        assert _derive(tmp_path / "ops" / "record", tick_by_tick).complete
        assert list(_heads(tick_by_tick)) == stamps[:count]
    caught_up = tmp_path / "caught-up"
    for count in (2, 5, len(stamps)):
        _grow(standard, tmp_path / "nas" / "record", count, nas=True)
        assert _derive(tmp_path / "nas" / "record", caught_up).complete
    nas_copy = _nas_shaped(_copy(standard, tmp_path / "nas-copy" / "record"))
    rebuilt_from_ops, rebuilt_from_nas = tmp_path / "rebuilt-ops", tmp_path / "rebuilt-nas"
    assert _derive(standard, rebuilt_from_ops).complete
    assert _derive(nas_copy, rebuilt_from_nas).complete
    expected = _heads(tick_by_tick)
    assert list(expected) == stamps
    for table in (caught_up, rebuilt_from_ops, rebuilt_from_nas):
        assert _heads(table) == expected


def _read_equal(left, right) -> bool:
    return (
        left.head == right.head
        and left.versions.equals(right.versions)
        and left.coverage.equals(right.coverage)
        and left.later_facts.equals(right.later_facts)
    )


def test_ticks_after_a_head_change_nothing_read_through_it(standard, tmp_path):
    stamps = _stamps(standard)
    record_root, table = tmp_path / "vintages" / "record", tmp_path / "versions"
    _grow(standard, record_root, 3)
    assert _derive(record_root, table).complete
    before = read_table(table, 1, stamps[2])
    _grow(standard, record_root, len(stamps))
    outcome = _derive(record_root, table)
    assert outcome.complete and outcome.parts_added == 3
    assert outcome.read is True
    after = read_table(table, 1, stamps[2])
    assert _read_equal(before, after)
    assert read_table(table, 1, stamps[-1]).versions.height > after.versions.height


def test_read_table_takes_a_path_a_stamp_or_a_sha256(compact, tmp_path):
    table = tmp_path / "versions"
    assert _derive(compact, table).complete
    versions, coverage, _ = derive_record(compact)
    stamps = _stamps(compact)
    gaps = {(datetime.strptime(b, "%Y%m%dT%H%M%SZ") - datetime.strptime(a, "%Y%m%dT%H%M%SZ")) for a, b in zip(stamps, stamps[1:])}
    assert len(gaps) > 1
    for position, stamp in enumerate(stamps):
        path = _head_file(table, stamp)
        ways = (stamp, str(path.relative_to(_gen(table))), path, _sha(path.read_bytes()))
        reads = [read_table(table, 1, way) for way in ways]
        for other in reads[1:]:
            assert _read_equal(reads[0], other)
        assert reads[0].head == json.loads(path.read_bytes())
        through = pl.col("position") <= position
        assert (
            reads[0]
            .versions.sort(["position", "ts", "source", "series"])
            .equals(versions.filter(through).sort(["position", "ts", "source", "series"]))
        )
        assert (
            reads[0]
            .coverage.sort(["position", "source", "series"])
            .equals(coverage.filter(through).sort(["position", "source", "series"]))
        )


def _a_head_byte(table: Path, stamps: list[str]) -> None:
    path = _head_file(table, stamps[2])
    entry = json.loads(path.read_bytes())
    entry["rows"]["coverage"] += 1
    _rewrite(path, _canonical(entry))


def _a_part_json(table: Path, stamps: list[str]) -> None:
    path = _part_dir(table, stamps[2]) / "part.json"
    _rewrite(path, path.read_bytes().replace(b'"generation":1', b'"generation":1 '))


def _a_frame(table: Path, stamps: list[str]) -> None:
    _change_versions(_part_dir(table, stamps[3]) / "versions.parquet")


def _change_versions(path: Path) -> None:
    frame = pl.read_parquet(path)
    changed = frame.with_columns(pl.when(pl.int_range(pl.len()) == 0).then(pl.lit("9")).otherwise(pl.col("token")).alias("token"))
    assert not changed.equals(frame)
    buffer = io.BytesIO()
    changed.write_parquet(buffer)
    _rewrite(path, buffer.getvalue())


def _a_parts_sha256(table: Path, stamps: list[str]) -> None:
    path = _head_file(table, stamps[-1])
    entry = json.loads(path.read_bytes())
    entry["parts_sha256"] = _sha(entry["parts_sha256"].encode())
    _rewrite(path, _canonical(entry))


def _newest_head(table: Path, stamps: list[str], edit) -> None:
    path = _head_file(table, stamps[-1])
    entry = json.loads(path.read_bytes())
    _rewrite(path, edit(entry))


def _a_head_missing_field(table: Path, stamps: list[str]) -> None:
    _newest_head(table, stamps, lambda entry: _canonical({key: value for key, value in entry.items() if key != "rows"}))


def _a_head_not_canonical(table: Path, stamps: list[str]) -> None:
    _newest_head(table, stamps, lambda entry: json.dumps(entry, sort_keys=True, indent=1).encode() + b"\n")


def _a_head_rows(table: Path, stamps: list[str]) -> None:
    def edit(entry: dict) -> bytes:
        entry["rows"]["versions"]["inherited"] += 1
        return _canonical(entry)

    _newest_head(table, stamps, edit)


DAMAGE = [_a_head_byte, _a_part_json, _a_frame, _a_parts_sha256, _a_head_missing_field, _a_head_not_canonical, _a_head_rows]


@pytest.mark.parametrize("damage", DAMAGE, ids=lambda f: f.__name__[3:])
def test_read_table_refuses_what_does_not_hash(standard, tmp_path, damage):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    stamps = _stamps(standard)
    read_table(table, 1, stamps[-1])
    damage(table, stamps)
    with pytest.raises(TableError):
        read_table(table, 1, _head_file(table, stamps[-1]))


def test_a_head_its_successor_does_not_name_is_refused_as_a_broken_link(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    stamps = _stamps(standard)
    path = _head_file(table, stamps[2])
    entry = json.loads(path.read_bytes())
    entry["prev"] = _sha(entry["prev"].encode())
    _rewrite(path, _canonical(entry))
    with pytest.raises(TableError) as refused:
        read_table(table, 1, stamps[-1])
    assert refused.value.tick == stamps[2]
    assert "does not hash to the prev its successor records" in str(refused.value)


def _forge(table: Path, stamps: list[str], index: int, *, part=None, versions=None, head=None) -> None:
    """The index-th part or head damaged, then every hash the damage moved re-sealed: its part_json_sha256, the
    parts_sha256 chain and each later head's prev, so only the check under test can refuse it."""
    parts_sha256 = "0" * 64 if index == 0 else json.loads(_head_file(table, stamps[index - 1]).read_bytes())["parts_sha256"]
    prev_raw = None
    for position in range(index, len(stamps)):
        part_dir, head_path = _part_dir(table, stamps[position]), _head_file(table, stamps[position])
        entry = json.loads(head_path.read_bytes())
        if position == index:
            recorded = json.loads((part_dir / "part.json").read_bytes())
            if versions is not None:
                frame = versions(pl.read_parquet(part_dir / "versions.parquet"), entry)
                buffer = io.BytesIO()
                frame.write_parquet(buffer)
                _rewrite(part_dir / "versions.parquet", buffer.getvalue())
                recorded["frames"]["versions"] = {"hash": frame_hash(frame, 1), "rows": frame.height}
            if part is not None:
                part(recorded)
            _rewrite(part_dir / "part.json", _canonical(recorded))
        entry["part_json_sha256"] = _sha((part_dir / "part.json").read_bytes())
        parts_sha256 = entry["parts_sha256"] = _sha((parts_sha256 + entry["part_json_sha256"]).encode("ascii"))
        if prev_raw is not None:
            entry["prev"] = _sha(prev_raw)
        if position == index and head is not None:
            head(entry)
        prev_raw = _canonical(entry)
        _rewrite(head_path, prev_raw)


def _a_genesis_prev(table: Path, stamps: list[str]) -> tuple[int, str]:
    _forge(table, stamps, 0, head=lambda entry: entry.update(prev=_sha(b"elsewhere")))
    return 0, "the genesis head names a prev"


def _other_entries(table: Path, stamps: list[str]) -> tuple[int, str]:
    _forge(table, stamps, len(stamps) - 1, head=lambda entry: entry.update(entries_sha256=_sha(b"other entries")))
    return len(stamps) - 1, "the head names another generation or other entries than its generation.json"


def _a_part_naming_another_tick(table: Path, stamps: list[str]) -> tuple[int, str]:
    _forge(table, stamps, len(stamps) - 1, part=lambda part: part.update(tick_json_sha256="0" * 64))
    return len(stamps) - 1, "part.json names another tick than its head"


def _a_position_off_its_place(table: Path, stamps: list[str]) -> tuple[int, str]:
    def moved(record: dict) -> None:
        record["position"] += 1

    _forge(table, stamps, len(stamps) - 1, part=moved, head=moved)
    return len(stamps) - 1, f"the head's position {len(stamps)} is not its place {len(stamps) - 1} on the head log"


def _a_kind_no_derive_writes(table: Path, stamps: list[str]) -> tuple[int, str]:
    def renamed(frame: pl.DataFrame, entry: dict) -> pl.DataFrame:
        entry["rows"]["versions"][frame["kind"][0]] -= 1
        return frame.with_columns(
            pl.when(pl.int_range(pl.len()) == 0).then(pl.lit("bogus")).otherwise(pl.col("kind")).alias("kind")
        )

    _forge(table, stamps, len(stamps) - 1, versions=renamed)
    return len(stamps) - 1, "the versions through the head hold kinds no derive writes: ['bogus']"


@pytest.mark.parametrize(
    "damage",
    [_a_genesis_prev, _other_entries, _a_part_naming_another_tick, _a_position_off_its_place, _a_kind_no_derive_writes],
    ids=lambda f: f.__name__.removeprefix("_a_").removeprefix("_"),
)
def test_each_check_of_the_walk_refuses_its_own_damage(compact, tmp_path, damage):
    table = tmp_path / "versions"
    assert _derive(compact, table).complete
    stamps = _stamps(compact)
    position, reason = damage(table, stamps)
    with pytest.raises(TableError) as refused:
        read_table(table, 1, _head_file(table, stamps[-1]))
    assert (refused.value.tick, str(refused.value)) == (stamps[position], reason)


@pytest.mark.parametrize("damage", [_a_head_missing_field, _a_head_not_canonical, _a_head_rows], ids=lambda f: f.__name__[3:])
def test_a_derive_extends_only_a_head_that_is_its_own_bytes(standard, tmp_path, damage):
    stamps = _stamps(standard)
    record_root, table = tmp_path / "vintages" / "record", tmp_path / "versions"
    _grow(standard, record_root, len(stamps) - 1)
    assert _derive(record_root, table).complete
    damage(table, stamps[:-1])
    _grow(standard, record_root, len(stamps))
    outcome = _derive(record_root, table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, stamps[-2], 0)
    assert list(_heads(table)) == stamps[:-1]


def test_head_names_the_highest_position_after_a_clock_regression(tmp_path):
    published = build_record(tmp_path / "vintages", [(T0, {}), (T0 + 12 * HOUR, {}), (T0 + 11 * HOUR, {})])
    table = tmp_path / "versions"
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert outcome.complete
    assert published[2].stamp < published[1].stamp
    assert (head(table, 1)["tick"], head(table, 1)["position"]) == (published[2].stamp, 2)
    assert outcome.head == head(table, 1)
    assert head(tmp_path / "empty", 1) is None


def test_the_frame_hash(standard, tmp_path, monkeypatch):
    frame = pl.DataFrame(
        {
            "at": [datetime(2026, 11, 12, 7, 37, 0, 120034, tzinfo=UTC), None],
            "day": [date(2026, 11, 11), None],
            "n": [-3, None],
            "ok": [True, False],
            "text": ['a "quoted" é', None],
        },
        schema={"at": pl.Datetime("us", "UTC"), "day": pl.Date(), "n": pl.Int64(), "ok": pl.Boolean(), "text": pl.String()},
    )
    lines = [
        '["at", "day", "n", "ok", "text"]',
        '["2026-11-12T07:37:00.120034Z","2026-11-11",-3,true,"a \\"quoted\\" \\u00e9"]',
        "[null,null,null,false,null]",
    ]
    assert frame_hash(frame, 1) == _sha("".join(line + "\n" for line in lines).encode())
    buffer = io.BytesIO()
    frame.write_parquet(buffer)
    assert frame_hash(pl.read_parquet(io.BytesIO(buffer.getvalue())), 1) == frame_hash(frame, 1)

    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    stamp = _stamps(standard)[-1]
    expected = read_table(table, 1, stamp)
    assert expected.head["hash_version"] == 1
    monkeypatch.setattr(table_module, "FRAME_HASH_VERSION", 2)
    assert _read_equal(read_table(table, 1, stamp), expected)


def test_the_frame_hash_reads_an_instant_and_refuses_a_naive_datetime():
    utc = pl.DataFrame({"at": [datetime(2026, 11, 12, 7, 37, 0, 120034, tzinfo=UTC)]}, schema={"at": pl.Datetime("us", "UTC")})
    tokyo = utc.with_columns(pl.col("at").dt.convert_time_zone("Asia/Tokyo"))
    assert tokyo["at"][0].utcoffset() == timedelta(hours=9)
    assert frame_hash(tokyo, 1) == frame_hash(utc, 1)
    naive = utc.with_columns(pl.col("at").dt.replace_time_zone(None))
    assert naive["at"][0].tzinfo is None
    with pytest.raises(ValueError):
        frame_hash(naive, 1)


def test_a_later_facts_taught_at_is_written_in_utc_and_never_naive():
    tick = TickFile("20261112T073700Z", Path("unused"), None, "0" * 64, None, None)
    versions, coverage, _ = frames([], [], [])
    taught = datetime(2026, 11, 12, 16, 40, 0, 5, tzinfo=ZoneInfo("Asia/Tokyo"))
    fact = {"fact": "link-error", "tick": "20261111T193700Z", "taught_at": taught}
    part = table_module._part(tick, 1, 1, versions, coverage, [fact])
    assert part["later_facts"] == [{"fact": "link-error", "taught_at": "2026-11-12T07:40:00.000005Z", "tick": "20261111T193700Z"}]
    with pytest.raises(ValueError):
        table_module._part(tick, 1, 1, versions, coverage, [fact | {"taught_at": taught.replace(tzinfo=None)}])


def _later_fact_record(data_root: Path) -> list[Published]:
    """Five ticks: the third a stamp regression, the fourth carrying `prev.error`, the fifth's link acknowledged."""
    published = build_record(data_root, [(T0, {}), (T0 + 12 * HOUR, {}), (T0 + 11 * HOUR, {})])
    junk = published[2].dir / "junk"
    _opened(published[2].dir)
    junk.write_bytes(b"junk")
    published.append(run_tick(data_root, T0 + 14 * HOUR))
    _opened(published[2].dir)
    junk.unlink()
    os.chmod(published[2].dir, 0o555)
    published.append(run_tick(data_root, T0 + 17 * HOUR))
    assert published[3].manifest["prev"]["error"] is not None
    return published


def test_a_later_fact_lands_in_the_later_part(tmp_path, monkeypatch):
    published = _later_fact_record(tmp_path / "vintages")
    stamps = [tick.stamp for tick in published]
    third_sha = published[3].tick_json_sha256
    entries = (LinkAcknowledgment(stamps[4], third_sha, third_sha),)
    monkeypatch.setitem(derive_module.GENERATION_ENTRIES, 1, entries)
    table = tmp_path / "versions"
    assert _derive(tmp_path / "vintages" / "record", table).complete
    _, _, facts = derive_record(tmp_path / "vintages" / "record", entries=entries)
    taught = {"regression-predecessor": (2, 1), "link-error": (3, 2), "link-acknowledged": (4, 3)}
    assert {row["fact"]: (row["taught_position"], stamps.index(row["tick"])) for row in facts.iter_rows(named=True)} == taught
    for position, stamp in enumerate(stamps):
        part = json.loads((_part_dir(table, stamp) / "part.json").read_bytes())
        expected = [
            {"fact": row["fact"], "taught_at": row["taught_at"].strftime(ISO), "tick": row["tick"]}
            for row in facts.iter_rows(named=True)
            if row["taught_by"] == stamp
        ]
        assert part["later_facts"] == expected
        assert len(expected) == (position >= 2)
        flags = pl.read_parquet(_part_dir(table, stamp) / "coverage.parquet")["flags"].str.split(",").list
        assert flags.contains("stamp-regression").any() == (position == 2)
    assert read_table(table, 1, stamps[-1]).later_facts.equals(facts)


def test_a_link_that_does_not_hash_stops_the_run_keeping_earlier_parts(tmp_path):
    published = _small(tmp_path / "vintages", 2)
    table = tmp_path / "versions"
    assert _derive(tmp_path / "vintages" / "record", table).complete
    published += _small(tmp_path / "vintages", 2, start=2)
    _edited_tick_json(published[2].dir, "edited")
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, published[3].stamp, 1)
    assert "link" in outcome.reason
    assert outcome.head["tick"] == published[2].stamp
    assert _parts(table) == list(_heads(table)) == [tick.stamp for tick in published[:3]]


def test_a_body_that_does_not_rehash_stops_the_run_at_its_tick(tmp_path, monkeypatch, caplog):
    _no_config(monkeypatch, tmp_path)
    published = _small(tmp_path / "vintages", 3)
    table = tmp_path / "versions"
    assert _run(tmp_path / "vintages" / "record", table) == 0
    published += _small(tmp_path / "vintages", 1, start=3)
    body = published[3].dir / STATUS_FILE
    assert gzip.decompress(body.read_bytes()) != b"other"
    _rewrite(body, gzip.compress(b"other", mtime=0))
    caplog.set_level(logging.DEBUG)
    assert _run(tmp_path / "vintages" / "record", table) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert stopped.startswith(f"vintage derive stopped generation=1 head={published[2].stamp} at={published[3].stamp} reason=")
    assert "the tick's files do not re-hash" in stopped
    assert _parts(table) == list(_heads(table)) == [tick.stamp for tick in published[:3]]


def _set_aside(tick_dir: Path, aside: Path) -> None:
    shutil.copytree(tick_dir, aside)
    _removed(tick_dir)


def _forked(data_root: Path, table: Path) -> tuple[list[Published], Path]:
    """Three ticks taken by the table; the third deleted from the record and kept aside; a fourth chaining around it."""
    published = _small(data_root, 3)
    assert _derive(data_root / "record", table).complete
    aside = data_root / "aside"
    _set_aside(published[2].dir, aside)
    published += _small(data_root, 1, start=3)
    assert published[3].manifest["prev"]["tick"] == published[1].stamp
    return published, aside


def test_a_fork_stops_before_deriving(tmp_path, monkeypatch):
    table = tmp_path / "versions"
    published, aside = _forked(tmp_path / "vintages", table)
    taken = _snapshot(table / "gen-1")
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, published[2].stamp, 0)
    assert "fork" in outcome.reason
    shutil.copytree(aside, published[2].dir)
    assert _sha((published[2].dir / "tick.json").read_bytes()) == published[2].tick_json_sha256
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, published[2].stamp, 0)
    assert "fork" in outcome.reason
    assert _snapshot(table / "gen-1") == taken

    monkeypatch.setitem(derive_module.GENERATION_ENTRIES, 2, ())
    outcome = _derive(tmp_path / "vintages" / "record", table, generation=2)
    assert outcome.complete
    assert _parts(table, 2) == list(_heads(table, 2)) == [published[i].stamp for i in (0, 1, 3)]
    assert _snapshot(table / "gen-1") == taken


def test_a_moved_tick_stops_before_deriving(tmp_path):
    published = _small(tmp_path / "vintages", 3)
    table = tmp_path / "versions"
    assert _derive(tmp_path / "vintages" / "record", table).complete
    original = _edited_tick_json(published[1].dir, "edited")
    published += _small(tmp_path / "vintages", 1, start=3)
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, published[1].stamp, 0)
    assert "moved tick" in outcome.reason
    assert len(_parts(table)) == 3
    _rewrite(published[1].dir / "tick.json", original)
    outcome = _derive(tmp_path / "vintages" / "record", table)
    assert (outcome.complete, outcome.parts_added) == (True, 1)
    assert list(_heads(table)) == [tick.stamp for tick in published]


def test_through_rebuilds_the_old_branch_and_refuses_a_non_empty_root(tmp_path, monkeypatch, caplog):
    _no_config(monkeypatch, tmp_path)
    table = tmp_path / "versions"
    data_root = tmp_path / "vintages"
    published = _small(data_root, 3)
    assert _derive(data_root / "record", table).complete
    old_heads = _heads(table)
    nas_record = _copy(data_root / "record", tmp_path / "nas-copy" / "record")
    published += _forked_after(data_root, published)
    shutil.copytree(published[3].dir, nas_record / published[3].dir.relative_to(data_root / "record"))
    _nas_shaped(nas_record)
    assert [tick.stamp for tick in _order(nas_record)] == [published[i].stamp for i in (0, 1, 3)]

    rebuilt = tmp_path / "rebuilt"
    outcome = _derive(nas_record, rebuilt, through=published[2].stamp)
    assert outcome.complete and _heads(rebuilt) == old_heads
    through_cli = tmp_path / "rebuilt-cli"
    assert _run(nas_record, through_cli, through=published[2].stamp) == 0
    assert _heads(through_cli) == old_heads
    assert sorted(entry.name for entry in through_cli.iterdir()) == [LOCKFILE_NAME, "gen-1", "staging"]

    held = tmp_path / "held"
    held.mkdir()
    (held / "notes").write_bytes(b"")
    outcome = _derive(nas_record, held, through=published[2].stamp)
    assert (outcome.complete, outcome.at, outcome.head) == (False, None, None)
    assert sorted(entry.name for entry in held.iterdir()) == ["notes"]
    caplog.set_level(logging.DEBUG)
    assert _run(nas_record, held, through=published[2].stamp) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert re.fullmatch(r"vintage derive stopped generation=1 head=none at=none reason=--through takes .* it holds notes", stopped)
    assert not _gen(held).exists()


def _forked_after(data_root: Path, published: list[Published]) -> list[Published]:
    _removed(published[2].dir)
    return _small(data_root, 1, start=3)


def test_a_dead_runs_staging_never_blocks_and_is_named(standard, tmp_path, caplog):
    second = int(RUN_AT.timestamp())
    first = _stamps(standard)[0]
    table = tmp_path / "versions"
    leftovers = [f"gen-1.{second}.deadbeef", f"{first}.{second}.deadbeef.part", f"{first}.{second}.deadbeef.head"]
    for name in leftovers:
        (table / "staging" / name).mkdir(parents=True)
    (table / "staging" / leftovers[0] / "generation.json").write_bytes(b'{"entr')
    caplog.set_level(logging.DEBUG)
    assert _derive(standard, table).complete
    (warning,) = _messages(caplog, logging.WARNING)
    assert all(name in warning for name in leftovers)
    assert sorted(entry.name for entry in (table / "staging").iterdir()) == sorted(leftovers)

    clean = tmp_path / "clean"
    assert _derive(standard, clean).complete
    assert list((clean / "staging").iterdir()) == []


def test_the_state_read_through_a_head_equals_the_state_in_memory(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    order = _order(standard)
    state = DeriveState.empty()
    through: list[DeriveState] = []
    for position, tick in enumerate(order):
        regression = position > 0 and tick.stamp <= order[position - 1].stamp
        derive_tick(state, tick, position, tick_dir=tick.dir, regression=regression)
        through.append(copy.deepcopy(state))
    for position, tick in enumerate(order):
        read = read_table(table, 1, tick.stamp)
        assert DeriveState.from_frames(read.versions, read.coverage) == through[position], position
    restored = read_table(table, 1, order[3].stamp).versions.filter(
        (pl.col("position") == 3) & (pl.col("kind") == "restoration") & (pl.col("source") == "cm-btc")
    )
    assert restored.height >= 1
    for row in restored.iter_rows(named=True):
        assert through[2].days[row["series"]][row["ts"].date()].retracted


def test_a_published_directory_left_0755_is_set_0555(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    stamp = _stamps(standard)[2]
    left = [_gen(table), _part_dir(table, stamp), _head_file(table, stamp).parent]
    for directory in left:
        os.chmod(directory, 0o755)
    assert _derive(standard, table).complete
    assert [stat.S_IMODE(directory.stat().st_mode) for directory in left] == [0o555] * 3


@pytest.mark.parametrize("part", ["byte-equal", "differing", "damaged-frame"])
def test_a_part_without_its_head_is_adopted_or_refused(standard, tmp_path, monkeypatch, part):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    stamp = _stamps(standard)[-1]
    published_head = _head_file(table, stamp).read_bytes()
    _removed(_head_file(table, stamp).parent)
    if part == "differing":
        path = _part_dir(table, stamp) / "part.json"
        _rewrite(path, path.read_bytes().replace(b'"generation":1', b'"generation":1 '))
    if part == "damaged-frame":
        _change_versions(_part_dir(table, stamp) / "versions.parquet")
    staged = []
    write_part = table_module.write_part
    monkeypatch.setattr(
        table_module, "write_part", lambda staging, name, *rest: staged.append(name) or write_part(staging, name, *rest)
    )
    outcome = _derive(standard, table)
    assert staged == []
    if part == "byte-equal":
        assert (outcome.complete, outcome.parts_added) == (True, 1)
        assert _head_file(table, stamp).read_bytes() == published_head
    else:
        assert (outcome.complete, outcome.at, outcome.parts_added) == (False, stamp, 0)
        reason = {"differing": "differs from the part derived", "damaged-frame": "versions frame does not hash"}[part]
        assert reason in outcome.reason
        assert not _head_file(table, stamp).exists()
    assert list((table / "staging").iterdir()) == []


def test_a_step_after_a_heads_rename_fails_and_the_stop_names_that_head(standard, tmp_path, monkeypatch):
    table = tmp_path / "versions"
    stamps = _stamps(standard)
    fsync_dir = storage_module.fsync_dir

    def failing(path: Path) -> None:
        if "heads" in path.parts:
            raise OSError("fsync failed")
        fsync_dir(path)

    monkeypatch.setattr(storage_module, "fsync_dir", failing)
    outcome = _derive(standard, table)
    published = _head_file(table, stamps[0])
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, stamps[0], 1)
    assert outcome.head == json.loads(published.read_bytes())
    assert outcome.head_sha256 == _sha(published.read_bytes())
    assert "the parent's fsync" in outcome.reason
    monkeypatch.setattr(storage_module, "fsync_dir", fsync_dir)
    outcome = _derive(standard, table)
    assert (outcome.complete, outcome.parts_added) == (True, len(stamps) - 1)
    assert stat.S_IMODE(published.parent.stat().st_mode) == 0o555


def test_a_torn_generation_and_a_differing_generation_json(standard, tmp_path, monkeypatch, caplog):
    table = tmp_path / "versions"
    create_exclusive = table_module.create_exclusive

    def torn(path: Path, data: bytes) -> None:
        if path.name == "generation.json":
            create_exclusive(path, data[:5])
            raise OSError("torn")
        create_exclusive(path, data)

    monkeypatch.setattr(table_module, "create_exclusive", torn)
    outcome = _derive(standard, table)
    assert (outcome.complete, outcome.at, outcome.head) == (False, None, None)
    assert not _gen(table).exists()
    (leftover,) = (table / "staging").iterdir()
    assert leftover.name.startswith("gen-1.")
    monkeypatch.setattr(table_module, "create_exclusive", create_exclusive)
    caplog.set_level(logging.DEBUG)
    assert _derive(standard, table).complete
    (warning,) = _messages(caplog, logging.WARNING)
    assert leftover.name in warning
    assert list(_heads(table)) == _stamps(standard)

    _no_config(monkeypatch, tmp_path)
    monkeypatch.setitem(derive_module.GENERATION_ENTRIES, 1, (LinkAcknowledgment(_stamps(standard)[1], "0" * 64, "1" * 64),))
    caplog.clear()
    assert _run(standard, table) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert re.fullmatch(r"vintage derive stopped generation=1 head=\S+ at=none reason=.*generation\.json.*", stopped)


def test_a_new_generation_builds_from_genesis_and_a_return_resumes(standard, tmp_path, monkeypatch):
    stamps = _stamps(standard)
    record_root, table = tmp_path / "vintages" / "record", tmp_path / "versions"
    _grow(standard, record_root, 4)
    assert _derive(record_root, table).complete
    first = _snapshot(_gen(table))
    _grow(standard, record_root, len(stamps))
    monkeypatch.setitem(derive_module.GENERATION_ENTRIES, 2, ())
    outcome = _derive(record_root, table, generation=2)
    assert (outcome.complete, outcome.parts_added) == (True, len(stamps))
    assert list(_heads(table, 2)) == stamps
    genesis = json.loads(_head_file(table, stamps[0], 2).read_bytes())
    assert (genesis["generation"], genesis["position"], genesis["prev"], genesis["prev_tick"]) == (2, 0, None, None)
    assert _snapshot(_gen(table)) == first
    assert read_table(table, 1, stamps[3]).head["tick"] == stamps[3]
    outcome = _derive(record_root, table, generation=1)
    assert (outcome.complete, outcome.parts_added) == (True, 2)
    assert list(_heads(table)) == stamps
    assert read_table(table, 1, stamps[-1]).versions.equals(read_table(table, 2, stamps[-1]).versions)


def test_a_held_lock_stops_with_the_derives_own_message(standard, tmp_path, monkeypatch, caplog):
    _no_config(monkeypatch, tmp_path)
    table = tmp_path / "versions"
    table.mkdir()
    fd = os.open(table / LOCKFILE_NAME, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        caplog.set_level(logging.DEBUG)
        code = _run(standard, table)
    finally:
        os.close(fd)
    assert code == 1
    refusal, stopped = _messages(caplog, logging.ERROR)
    assert "zcrypto-vintage-derive.service" in refusal and "zcrypto-capture" not in refusal
    assert stopped == "vintage derive stopped generation=1 head=none at=none reason=lock held"
    assert sorted(entry.name for entry in table.iterdir()) == [LOCKFILE_NAME]


def test_a_missing_record_root_refuses_before_reading(standard, tmp_path):
    absent = tmp_path / "vintages" / "record"
    outcome = _derive(absent, tmp_path / "empty")
    assert (outcome.complete, outcome.at, outcome.head) == (False, None, None)
    assert "record root" in outcome.reason
    assert not (tmp_path / "empty").exists()
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    outcome = _derive(absent, table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, None, 0)
    assert "record root" in outcome.reason and "fork" not in outcome.reason


def test_an_empty_record_root_under_a_table_with_heads_refuses_before_any_tick(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    taken = _snapshot(_gen(table))
    unmounted = tmp_path / "unmounted" / "record"
    unmounted.mkdir(parents=True)
    outcome = _derive(unmounted, table)
    assert (outcome.complete, outcome.at, outcome.parts_added) == (False, None, 0)
    assert "holds no tick" in outcome.reason and "fork" not in outcome.reason
    assert _snapshot(_gen(table)) == taken


def test_the_table_root_refusal(tmp_path, monkeypatch, caplog):
    record_root = tmp_path / "vintages" / "record"
    for refused in (record_root / "versions", tmp_path / "vintages" / "versions", NAS / "versions"):
        assert refuse_table_root(refused, record_root, NAS) is not None
    assert refuse_table_root(Path("/versions"), Path("/vintages/record"), NAS) is None
    host = Path("/var/lib/zcrypto-ops/vintages")
    assert refuse_table_root(host / "versions", host / "record", NAS) is not None
    assert refuse_table_root(tmp_path / "versions", record_root, NAS) is None

    nas = _no_config(monkeypatch, tmp_path)
    _small(tmp_path / "vintages", 1)
    under_nas = nas / "versions"
    caplog.set_level(logging.DEBUG)
    assert _run(record_root, under_nas) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert stopped.startswith("vintage derive stopped generation=1 head=none at=none reason=table root refused: ")
    assert f"lies in the NAS mount {nas}" in stopped
    assert not under_nas.exists()


def test_the_frames_columns_dtypes_and_order(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    read = read_table(table, 1, _stamps(standard)[-1])
    t, s, i = pl.Datetime("us", "UTC"), pl.String(), pl.Int64()
    assert list(read.versions.schema.items()) == [
        ("ts", t), ("provider", s), ("source", s), ("series", s), ("kind", s), ("token", s), ("tick", s), ("position", i),
        ("ended_at", t), ("knowable_at", t), ("appeared_after", t), ("outcome", i), ("flags", s),
    ]  # fmt: skip
    assert list(read.coverage.schema.items()) == [
        ("ts", t), ("provider", s), ("tick", s), ("position", i), ("tick_json_sha256", s), ("source", s), ("series", s),
        ("outcome", i), ("reason", s), ("ended_at", t), ("knowable_at", t), ("first_day", pl.Date()), ("last_day", pl.Date()),
        ("days", i), ("evidence", pl.Boolean()), ("flags", s),
    ]  # fmt: skip
    for position in range(len(_stamps(standard))):
        versions = read.versions.filter(pl.col("position") == position)
        coverage = read.coverage.filter(pl.col("position") == position)
        assert versions.equals(versions.sort(["ts", "source", "series"], maintain_order=True))
        assert coverage.equals(coverage.sort(["source", "series"], maintain_order=True))
    retracted = read.versions["kind"] == "retraction"
    assert retracted.any()
    assert (read.versions["token"].is_null() == retracted).all()


def test_provider_leaves_out_bgeometrics_alone(standard, tmp_path):
    table = tmp_path / "versions"
    assert _derive(standard, table).complete
    read = read_table(table, 1, _stamps(standard)[-1])
    for frame in (read.versions, read.coverage):
        bg = pl.col("source").str.starts_with("bg-")
        assert frame.filter(bg).height > 0
        assert frame.filter(pl.col("provider") != "bgeometrics").equals(frame.filter(~bg))


def test_as_of_through_a_head_equals_the_derivation_in_memory(compact, tmp_path):
    table = tmp_path / "versions"
    assert _derive(compact, table).complete
    read = read_table(table, 1, _stamps(compact)[-1])
    derived = derive_record(compact)
    assert {"restatement", "retraction", "restoration", "first_publication"} <= set(read.versions["kind"])
    assert read.later_facts["fact"].to_list() == ["regression-predecessor"]
    second = timedelta(seconds=1)
    for tick in _order(compact):
        ended = datetime.fromisoformat(tick.manifest["ended_at"])
        for t in (ended - second, ended, ended + second):
            assert as_of(read.versions, read.coverage, read.later_facts, t).equals(as_of(*derived, t)), (tick.stamp, t)


def test_the_fixture_head_is_pinned(tmp_path):
    assert fixture_head_sha256(tmp_path) == HEAD_PINS[DERIVE_GENERATION]


def _prom_value(textfile: Path) -> str:
    (line,) = [line for line in textfile.read_text().splitlines() if not line.startswith("#")]
    name, value = line.split()
    assert name == "zcrypto_vintage_derive_head_timestamp_seconds"
    return value


def _through_into_a_held_root(record_root: Path, table: Path, monkeypatch) -> dict:
    return {"through": _stamps(record_root)[0]}


def _no_pinned_entries(record_root: Path, table: Path, monkeypatch) -> dict:
    monkeypatch.delitem(derive_module.GENERATION_ENTRIES, DERIVE_GENERATION)
    return {}


def _an_unreadable_newest_head(record_root: Path, table: Path, monkeypatch) -> dict:
    _a_head_not_canonical(table, _stamps(record_root))
    return {}


UNREAD_REASONS = {
    "_through_into_a_held_root": "reason=--through takes a table root holding only",
    "_no_pinned_entries": "reason=no link entries are pinned for generation 1",
    "_an_unreadable_newest_head": "is not its own canonical line",
}


@pytest.mark.parametrize(
    "unread", [_through_into_a_held_root, _no_pinned_entries, _an_unreadable_newest_head], ids=lambda f: f.__name__[1:]
)
def test_the_gauge_is_left_alone_by_a_run_that_did_not_read_its_table(standard, tmp_path, monkeypatch, caplog, unread):
    _no_config(monkeypatch, tmp_path)
    textfile, table = tmp_path / "vintage-derive.prom", tmp_path / "versions"
    assert _run(standard, table, textfile=textfile) == 0
    written = textfile.read_bytes()
    assert _prom_value(textfile) != "0"
    kwargs = unread(standard, table, monkeypatch)
    caplog.set_level(logging.DEBUG)
    assert _run(standard, table, textfile=textfile, **kwargs) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert UNREAD_REASONS[unread.__name__] in stopped
    assert textfile.read_bytes() == written


def test_the_summary_lines_and_the_prom(standard, tmp_path, monkeypatch, caplog):
    _no_config(monkeypatch, tmp_path)
    textfile = tmp_path / "vintage-derive.prom"
    caplog.set_level(logging.DEBUG)
    (tmp_path / "vintages" / "record").mkdir(parents=True)
    assert _run(tmp_path / "vintages" / "record", tmp_path / "empty", textfile=textfile) == 0
    assert _messages(caplog, logging.INFO)[-1] == "vintage derive complete generation=1 head=none head_sha256=none parts_added=0"
    assert _prom_value(textfile) == "0"

    record_root = _copy(standard, tmp_path / "copy" / "record")
    table = tmp_path / "versions"
    caplog.clear()
    assert _run(record_root, table, textfile=textfile) == 0
    stamp = _stamps(record_root)[-1]
    head_sha = _sha(_head_file(table, stamp).read_bytes())
    assert (
        _messages(caplog, logging.INFO)[-1]
        == f"vintage derive complete generation=1 head={stamp} head_sha256={head_sha} parts_added=6"
    )
    assert _messages(caplog, logging.ERROR) == []
    expected = int(datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp())
    assert _prom_value(textfile) == str(expected)
    assert expected != int(RUN_AT.timestamp())
    assert (textfile.stat().st_mode & 0o777) == 0o644

    later = run_tick(record_root.parent, T0 + 30 * HOUR)
    _rewrite(later.dir / STATUS_FILE, gzip.compress(b"other", mtime=0))
    caplog.clear()
    assert _run(record_root, table, textfile=textfile) == 1
    (stopped,) = _messages(caplog, logging.ERROR)
    assert stopped.startswith(f"vintage derive stopped generation=1 head={stamp} at={later.stamp} reason=")
    assert "the tick's files do not re-hash" in stopped
    assert _prom_value(textfile) == str(expected)

    monkeypatch.setenv("ZCRYPTO_BUILD_REVISION", "0123456789abcdef0123")
    fresh = tmp_path / "fresh"
    assert (
        command_module.run_derive(record_root, fresh, textfile=None, through=_stamps(record_root)[0], clock=FakeClock(RUN_AT)) == 0
    )
    opened_by = json.loads((_gen(fresh) / "generation.json").read_bytes())["opened_by"]
    assert opened_by.endswith("+0123456789ab")
