import errno
import hashlib
import itertools
import json
import os
import re
import stat
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from cli.onchain.chain import (
    CHAIN_GENERATION,
    ChainError,
    Line,
    canonical,
    chain_name,
    head,
    line_days,
    line_relpath,
    read_line,
    staging_leftovers,
    verify,
    walk,
    write_base,
    write_day,
)
from cli.onchain.series import COLUMNS, SCHEMA

COMMIT = "1a19c5e969761a0ce446483767da8c765e4aa895"
FIRST = date(2025, 12, 20)
# The base day; its next two days cross a month and a year, so each part of a relpath is read.
D0 = date(2025, 12, 30)


def _day(offset: int) -> date:
    return D0 + timedelta(days=offset)


def _frame(days: list[date]) -> pl.DataFrame:
    index = [(day - FIRST).days for day in days]
    rows = {
        "ts": [datetime(day.year, day.month, day.day, tzinfo=UTC) for day in days],
        "last_height": [144 * i + 143 for i in index],
        "last_hash": [f"{144 * i + 143:064x}" for i in index],
    } | {column: [1000.0 * i + n for i in index] for n, column in enumerate(COLUMNS[3:])}
    return pl.DataFrame(rows, schema=SCHEMA)


def _vintage(day: date) -> dict:
    height = 144 * (day - FIRST).days + 143
    return {
        "written_at": f"{day + timedelta(days=1)}T02:17:00+00:00",
        "last_height": height,
        "last_hash": f"{height:064x}",
        "tip_height": height + 12,
        "depth": 12,
        "brk_commit": COMMIT,
        "bitview_image": "sha256:" + "b" * 64,
        "bitcoind_image": "sha256:" + "c" * 64,
        "chain": chain_name(COMMIT),
    }


def _chain(root: Path, through: int) -> list[Line]:
    """The base through D0, then one line for each day up to D0 + `through`."""
    lines = [write_base(root, _frame([FIRST + timedelta(days=n) for n in range((D0 - FIRST).days + 1)]), _vintage(D0))]
    for offset in range(1, through + 1):
        lines.append(write_day(root, _frame([_day(offset)]), _vintage(_day(offset))))
    return lines


def _tree(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in sorted(root.rglob("*"))}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _replace(path: Path, data: bytes) -> None:
    path.unlink()
    path.write_bytes(data)


def _flip_last_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-1] ^= 1
    _replace(path, bytes(data))


def _rewrite_written_at(path: Path) -> None:
    line = json.loads(path.read_bytes())
    line["vintage"]["written_at"] = "2026-02-01T00:17:00+00:00"
    _replace(path, canonical(line))


def test_a_line_is_canonical_and_its_sha256_is_of_its_bytes(tmp_path):
    assert canonical({"b": 1, "a": "é", "c": {"z": None, "y": [1, 2]}}) == '{"a":"é","b":1,"c":{"y":[1,2],"z":null}}\n'.encode()
    assert line_relpath(date(2026, 1, 1)) == "index/2026/01/01.json"

    for line in _chain(tmp_path, 1):
        data = (tmp_path / line.relpath).read_bytes()
        assert data == (json.dumps(json.loads(data), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()
        assert data.count(b"\n") == 1
        assert line.relpath == line_relpath(line.day)
        assert line.sha256 == hashlib.sha256(data).hexdigest()


def test_the_base_then_days_walk_to_the_as_of(tmp_path):
    _chain(tmp_path, 2)

    lines = walk(tmp_path, _day(2))

    assert [line.day for line in lines] == [D0, _day(1), _day(2)]
    assert lines[0].prev is None
    for before, after in itertools.pairwise(lines):
        assert after.prev == _sha256(tmp_path / before.relpath)
    assert [line.files for line in lines] == [
        {"base/history.parquet": _sha256(tmp_path / "base/history.parquet")},
        {"days/2025/12/31.parquet": _sha256(tmp_path / "days/2025/12/31.parquet")},
        {"days/2026/01/01.parquet": _sha256(tmp_path / "days/2026/01/01.parquet")},
    ]
    assert [line.vintage for line in lines] == [_vintage(day) for day in (D0, _day(1), _day(2))]
    assert_frame_equal(pl.read_parquet(tmp_path / "base/history.parquet"), _frame([FIRST + timedelta(days=n) for n in range(11)]))
    assert_frame_equal(pl.read_parquet(tmp_path / "days/2026/01/01.parquet"), _frame([_day(2)]))
    assert [line.day for line in walk(tmp_path, _day(1))] == [D0, _day(1)]
    assert head(tmp_path) == lines[-1]
    assert head(tmp_path / "no-chain") is None


@pytest.mark.parametrize("offset", [1, 0], ids=["the-heads-day", "a-day-before-the-head"])
def test_a_day_is_written_once(tmp_path, offset):
    _chain(tmp_path, 1)
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match=f"{_day(offset)} is already written; its head is {_day(1)}"):
        write_day(tmp_path, _frame([_day(offset)]), _vintage(_day(offset)))

    assert _tree(tmp_path) == before


def test_a_file_no_line_names_is_refused_and_left_as_it_is(tmp_path):
    _chain(tmp_path, 0)
    planted = tmp_path / "days/2025/12/31.parquet"
    planted.parent.mkdir(parents=True)
    planted.write_bytes(b"the file a writer renamed in before it died")
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match=re.escape("no line names days/2025/12/31.parquet")):
        write_day(tmp_path, _frame([_day(1)]), _vintage(_day(1)))

    assert _tree(tmp_path) == before
    assert line_days(tmp_path) == [D0]


@pytest.mark.parametrize(
    ("through", "offset", "refusal"),
    [(0, 2, f"{_day(2)} is not the next day; its head is {D0}"), (None, 0, "holds no base line")],
    ids=["a-day-past-the-next", "no-base"],
)
def test_a_day_that_is_not_the_heads_next_is_refused(tmp_path, through, offset, refusal):
    if through is not None:
        _chain(tmp_path, through)
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match=refusal):
        write_day(tmp_path, _frame([_day(offset)]), _vintage(_day(offset)))

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("offsets", [(), (1, 2)], ids=["no-day", "two-days"])
def test_a_frame_of_other_than_one_day_is_refused(tmp_path, offsets):
    _chain(tmp_path, 0)
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match=f"holds {len(offsets)} rows"):
        write_day(tmp_path, _frame([_day(offset) for offset in offsets]), _vintage(_day(1)))

    assert _tree(tmp_path) == before


@pytest.mark.parametrize("base", [True, False], ids=["a-base-without-a-key", "a-day-with-a-key-more"])
def test_a_vintage_off_its_keys_is_refused_and_nothing_written(tmp_path, base):
    if not base:
        _chain(tmp_path, 0)
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match="a vintage's keys are"):
        if base:
            write_base(tmp_path, _frame([D0]), {key: value for key, value in _vintage(D0).items() if key != "chain"})
        else:
            write_day(tmp_path, _frame([_day(1)]), _vintage(_day(1)) | {"note": "x"})

    assert _tree(tmp_path) == before


def test_a_base_of_no_day_is_refused(tmp_path):
    with pytest.raises(ChainError, match="holds 0 rows"):
        write_base(tmp_path, _frame([]), _vintage(D0))

    assert _tree(tmp_path) == {}


def test_a_base_over_a_chain_is_refused(tmp_path):
    _chain(tmp_path, 1)
    before = _tree(tmp_path)

    with pytest.raises(ChainError, match=f"holds lines through {_day(1)}"):
        write_base(tmp_path, _frame([_day(1)]), _vintage(_day(1)))

    assert _tree(tmp_path) == before


@pytest.mark.parametrize(
    ("damage", "refusal"),
    [
        (lambda root: _flip_last_byte(root / "days/2025/12/31.parquet"), "days/2025/12/31.parquet does not hash to its listing"),
        (lambda root: (root / "days/2025/12/31.parquet").unlink(), "days/2025/12/31.parquet is listed and absent"),
        (lambda root: _rewrite_written_at(root / "index/2025/12/31.json"), "its prev is not the sha256 of index/2025/12/31.json"),
        (lambda root: (root / "index/2025/12/31.json").unlink(), f"no line for {_day(1)}"),
        (lambda root: (root / "index/2025/12/30.json").unlink(), "index/2025/12/31.json: the oldest line .* is not a base line"),
    ],
    ids=["a-changed-file", "a-missing-file", "a-broken-link", "a-missing-day", "a-missing-base"],
)
def test_verify_refuses_a_changed_file_a_broken_link_and_a_missing_day(tmp_path, damage, refusal):
    _chain(tmp_path, 2)
    assert verify(tmp_path, _day(2)) == head(tmp_path)
    damage(tmp_path)

    with pytest.raises(ChainError, match=refusal):
        verify(tmp_path, _day(2))


@pytest.mark.parametrize(
    ("damage", "refusal"),
    [
        (lambda root: _flip_last_byte(root / "days/2025/12/31.parquet"), None),
        (lambda root: _flip_last_byte(root / "days/2026/01/01.parquet"), "days/2026/01/01.parquet does not hash to its listing"),
        (lambda root: _rewrite_written_at(root / "index/2025/12/31.json"), None),
        (lambda root: _rewrite_written_at(root / "index/2026/01/01.json"), "its prev is not the sha256 of index/2026/01/01.json"),
    ],
    ids=["the-third-newest-file", "the-second-newest-file", "the-third-newest-line", "the-second-newest-line"],
)
def test_verify_of_the_newest_lines_reads_their_files_and_their_links_alone(tmp_path, damage, refusal):
    _chain(tmp_path, 3)
    damage(tmp_path)

    with pytest.raises(ChainError):
        verify(tmp_path, _day(3))
    if refusal is None:
        assert verify(tmp_path, _day(3), newest=2) == head(tmp_path)
    else:
        with pytest.raises(ChainError, match=refusal):
            verify(tmp_path, _day(3), newest=2)


@pytest.mark.parametrize("newest", [0, -1])
def test_verify_refuses_a_newest_below_1(tmp_path, newest):
    _chain(tmp_path, 1)

    with pytest.raises(ChainError, match=f"newest is {newest}; a verify reads at least the newest line"):
        verify(tmp_path, _day(1), newest=newest)


def _sha256_of_the_first_file(line: dict) -> str:
    return next(iter(line["files"].values()))


@pytest.mark.parametrize(
    ("offset", "plant", "refusal"),
    [
        (1, lambda line: canonical(line | {"note": "x"}), "its keys are"),
        (1, lambda line: canonical({key: value for key, value in line.items() if key != "vintage"}), "its keys are"),
        (
            1,
            lambda line: (json.dumps(dict(reversed(line.items())), separators=(",", ":"), ensure_ascii=False) + "\n").encode(),
            "canonical form",
        ),
        (1, lambda line: b"{\n", "canonical form"),
        (
            1,
            lambda line: canonical(line | {"files": {"days/2025/12/30.parquet": _sha256_of_the_first_file(line)}}),
            "its own day's file",
        ),
        (1, lambda line: canonical(line | {"day": "2025-12-29"}), "its day is '2025-12-29', not the 2025-12-31 its name gives"),
        (1, lambda line: canonical(line | {"prev": line["prev"][:63]}), "its prev is neither null nor a sha256"),
        (
            1,
            lambda line: canonical(line | {"files": {"days/2025/12/31.parquet": _sha256_of_the_first_file(line).upper()}}),
            "not mapped to a sha256",
        ),
        (
            0,
            lambda line: canonical(line | {"files": {"days/2025/12/30.parquet": _sha256_of_the_first_file(line)}}),
            "a base line lists",
        ),
        (1, lambda line: canonical(line | {"vintage": []}), "its vintage is not a map"),
    ],
    ids=[
        "a-key-added",
        "a-key-missing",
        "non-canonical-bytes",
        "not-json",
        "a-file-not-of-its-day",
        "a-day-not-its-names",
        "a-prev-not-a-sha256",
        "a-file-not-mapped-to-a-sha256",
        "a-base-file-elsewhere",
        "a-vintage-not-a-map",
    ],
)
def test_read_line_refuses_a_line_off_its_shape(tmp_path, offset, plant, refusal):
    _chain(tmp_path, 1)
    path = tmp_path / line_relpath(_day(offset))
    _replace(path, plant(json.loads(path.read_bytes())))

    with pytest.raises(ChainError, match=refusal):
        read_line(tmp_path, _day(offset))


def test_line_days_refuses_a_name_not_of_a_day(tmp_path):
    _chain(tmp_path, 0)
    (tmp_path / "index/2025/12/1.json").write_bytes(b"")

    with pytest.raises(ChainError, match=re.escape("index/2025/12/1.json is not named for a day")):
        line_days(tmp_path)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_an_unlistable_index_month_raises_never_reads_an_older_line_as_the_newest(tmp_path):
    _chain(tmp_path, 2)
    month = tmp_path / "index/2026/01"
    os.chmod(month, 0o000)
    try:
        with pytest.raises(PermissionError) as raised:
            line_days(tmp_path)
    finally:
        os.chmod(month, 0o755)

    assert raised.value.filename == str(month)


def test_every_placed_file_is_read_only(tmp_path):
    _chain(tmp_path, 1)
    placed = sorted(path for path in tmp_path.rglob("*") if path.is_file())

    assert [path.relative_to(tmp_path).as_posix() for path in placed] == [
        "base/history.parquet",
        "days/2025/12/31.parquet",
        "index/2025/12/30.json",
        "index/2025/12/31.json",
    ]
    assert {stat.S_IMODE(path.stat().st_mode) for path in placed} == {0o444}


def test_a_failed_write_leaves_no_temporary(tmp_path, monkeypatch):
    _chain(tmp_path, 0)

    def failing_fsync(fd: int) -> None:
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "fsync", failing_fsync)
    with pytest.raises(OSError, match="Input/output error"):
        write_day(tmp_path, _frame([_day(1)]), _vintage(_day(1)))
    monkeypatch.undo()

    assert staging_leftovers(tmp_path) == []
    assert not (tmp_path / "days/2025/12/31.parquet").exists()
    assert line_days(tmp_path) == [D0]


def test_a_staging_leftover_is_listed_and_never_a_line(tmp_path):
    _chain(tmp_path, 1)
    assert staging_leftovers(tmp_path) == []
    assert staging_leftovers(tmp_path / "no-chain") == []
    leftover = tmp_path / "staging" / f"01.json.{os.getpid()}.0badf00d"
    leftover.write_bytes(canonical({"day": _day(2).isoformat(), "prev": head(tmp_path).sha256, "files": {}, "vintage": {}}))

    written = write_day(tmp_path, _frame([_day(2)]), _vintage(_day(2)))

    assert staging_leftovers(tmp_path) == [leftover]
    assert line_days(tmp_path) == [D0, _day(1), _day(2)]
    assert verify(tmp_path, _day(2)) == written
    assert written.prev == _sha256(tmp_path / "index/2025/12/31.json")


def test_chain_name():
    assert CHAIN_GENERATION == 1
    assert chain_name("1a19c5e969761a0ce446483767da8c765e4aa895") == "btc-brk1a19c5e96976-g1"
    assert chain_name("1a19c5e969761a0ce446483767da8c765e4aa895", 2) == "btc-brk1a19c5e96976-g2"
