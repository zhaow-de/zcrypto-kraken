import fcntl
import logging
import os
import random
import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from typer.testing import CliRunner

from cli.__main__ import app
from cli.capture.command import LOCKFILE_NAME
from cli.onchain import command
from cli.onchain.brk import BITVIEW_URL
from cli.onchain.chain import VINTAGE_KEYS, chain_name, line_days, read_line
from cli.onchain.command import run_onchain_write
from cli.onchain.series import BRK_SERIES, MVRV_Z_MIN_VALUES
from cli.onchain.write import DEPTH, WriteOutcome, closed_days, run_write
from tests.onchain_stub import (
    BITCOIND_IMAGE,
    BITVIEW_IMAGE,
    COMMIT,
    FakeBrk,
    build_chain,
    day_end,
    fake_client,
    last_height,
)

FIRST = date(2025, 12, 20)
PER_DAY = 144
NAME = chain_name(COMMIT)
_LOG_LINE = re.compile(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} (INFO|WARNING|ERROR) zcrypto\.onchain\.\w+ \[[^\]]*\] - (.*)")


def _day(n: int) -> date:
    return FIRST + timedelta(days=n)


def _fake(n_days: int) -> FakeBrk:
    """`n_days` days from FIRST, `PER_DAY` blocks each, every pinned series served for every day, each value above 0."""
    rng = random.Random(42)
    days = [_day(n) for n in range(n_days) for _ in range(PER_DAY)]
    series = {series_id: {_day(n): rng.uniform(1e9, 1e12) for n in range(n_days)} for series_id in BRK_SERIES.values()}
    return FakeBrk(days=days, series=series)


def _confirm(fake: FakeBrk, day: date) -> None:
    fake.indexed_height = fake.tip_height = last_height(fake, day) + DEPTH


def _run(chain_root: Path, fake: FakeBrk, now: datetime) -> WriteOutcome:
    return run_write(
        chain_root, fake_client(fake), brk_commit=COMMIT, bitview_image=BITVIEW_IMAGE, bitcoind_image=BITCOIND_IMAGE, now=now
    )


def _command(chain_root: Path, fake: FakeBrk, now: datetime) -> int:
    return run_onchain_write(
        chain_root, fake_client(fake), brk_commit=COMMIT, bitview_image=BITVIEW_IMAGE, bitcoind_image=BITCOIND_IMAGE, now=now
    )


def _cli(chain_root: Path, fake: FakeBrk, monkeypatch) -> tuple[int, list[tuple[str, str]]]:
    """`zcrypto onchain write` through the app, its client `fake`'s; each line it printed as (level, message)."""
    urls = []

    def client(url: str):
        urls.append(url)
        return fake_client(fake)

    monkeypatch.setattr(command, "BrkClient", client)
    result = CliRunner().invoke(
        app,
        [
            "onchain",
            "write",
            "--chain-root",
            str(chain_root),
            "--bitview",
            BITVIEW_URL,
            "--brk-commit",
            COMMIT,
            "--bitview-image",
            BITVIEW_IMAGE,
            "--bitcoind-image",
            BITCOIND_IMAGE,
        ],
    )
    assert urls == [BITVIEW_URL]
    printed = result.output.splitlines()
    lines = [_LOG_LINE.fullmatch(line) for line in printed]
    assert all(lines), printed
    return result.exit_code, [line.groups() for line in lines]


def _messages(caplog, level: int) -> list[str]:
    return [
        record.getMessage() for record in caplog.records if record.levelno == level and record.name.startswith("zcrypto.onchain")
    ]


def _tree(root: Path) -> dict[str, bytes | None]:
    return {path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None for path in sorted(root.rglob("*"))}


def _complete(head: date | None, wrote: int, base: int) -> str:
    return f"onchain write complete chain={NAME} head={head or 'none'} wrote={wrote} base={base}"


def test_a_day_is_closed_only_once_a_later_monotonic_day_has_a_block():
    day = date(2026, 3, 1)
    assert closed_days([day, day, day, day + timedelta(days=1)], 870_000, 870_100) == [(day, 870_002)]
    assert closed_days([day, day, day, day], 870_000, 870_100) == []


def test_a_block_after_midnight_with_a_timestamp_in_the_day_belongs_to_it(tmp_path):
    fake = _fake(8)
    build_chain(tmp_path, fake, [_day(3)])
    day = _day(4)
    later = last_height(fake, day)
    fake.indexed_height = later - 1
    fake.tip_height = later - 1 + 12

    assert _run(tmp_path, fake, day_end(day) + timedelta(hours=1)) == WriteOutcome((), False, None)

    fake.indexed_height = later + 1
    fake.tip_height = later + 12
    assert _run(tmp_path, fake, day_end(day) + timedelta(hours=3)) == WriteOutcome((day,), False, None)
    root = tmp_path / NAME
    assert read_line(root, day).vintage["last_height"] == later
    assert pl.read_parquet(root / "days/2025/12/24.parquet")["last_height"].to_list() == [later]


@pytest.mark.parametrize(("above", "written"), [(11, False), (12, True)], ids=["11-deep", "12-deep"])
def test_a_day_is_written_only_at_12_confirmations(tmp_path, above, written):
    fake = _fake(8)
    build_chain(tmp_path, fake, [_day(3)])
    last = last_height(fake, _day(4))
    fake.indexed_height = last + 1
    fake.tip_height = last + above

    outcome = _run(tmp_path, fake, day_end(_day(4)) + timedelta(hours=2))

    assert outcome == WriteOutcome((_day(4),) if written else (), False, None)
    assert line_days(tmp_path / NAME) == ([_day(3), _day(4)] if written else [_day(3)])


def test_the_base_holds_every_closed_confirmed_day_and_each_later_day_is_written_once_in_order(tmp_path):
    fake = _fake(10)
    root = tmp_path / NAME
    # Day 5 is closed by day 6's first block, one block short of its depth.
    fake.indexed_height = fake.tip_height = last_height(fake, _day(5)) + 11

    assert _run(tmp_path, fake, day_end(_day(5)) + timedelta(hours=2)) == WriteOutcome((_day(4),), True, None)
    base = pl.read_parquet(root / "base/history.parquet")
    days = [_day(n) for n in range(5)]
    assert base["ts"].to_list() == [datetime(day.year, day.month, day.day, tzinfo=UTC) for day in days]
    assert base["last_height"].to_list() == [last_height(fake, day) for day in days]
    assert base["last_hash"].to_list() == [f"{last_height(fake, day):064x}" for day in days]
    for column, series_id in BRK_SERIES.items():
        assert base[column].to_list() == [fake.series[series_id][day] for day in days], column
    assert line_days(root) == [_day(4)]

    _confirm(fake, _day(6))
    assert _run(tmp_path, fake, day_end(_day(6)) + timedelta(hours=2)) == WriteOutcome((_day(5), _day(6)), False, None)
    assert line_days(root) == [_day(4), _day(5), _day(6)]
    for day, relpath in [(_day(5), "days/2025/12/25.parquet"), (_day(6), "days/2025/12/26.parquet")]:
        row = pl.read_parquet(root / relpath)
        assert row["ts"].to_list() == [datetime(day.year, day.month, day.day, tzinfo=UTC)]
        assert row["last_height"].to_list() == [last_height(fake, day)]
        assert read_line(root, day).files.keys() == {relpath}

    tree = _tree(root)
    assert _run(tmp_path, fake, day_end(_day(6)) + timedelta(hours=3)) == WriteOutcome((), False, None)
    assert _tree(root) == tree


def test_a_changed_hash_at_a_recorded_height_stops_the_run_and_writes_nothing(tmp_path):
    fake = _fake(8)
    lines = build_chain(tmp_path, fake, [_day(3), _day(4)])
    root = tmp_path / NAME
    recorded = lines[0].vintage["last_height"]
    fake.hashes[recorded] = "e" * 64
    _confirm(fake, _day(6))
    tree = _tree(root)

    outcome = _run(tmp_path, fake, day_end(_day(6)) + timedelta(hours=2))

    assert (outcome.wrote, outcome.base) == ((), False)
    assert outcome.stopped is not None
    for named in (str(_day(3)), f"height {recorded}", f"{recorded:064x}", "e" * 64):
        assert named in outcome.stopped, named
    assert _tree(root) == tree


def test_an_unready_index_before_the_base_is_info_and_exit_0(tmp_path, monkeypatch):
    fake = _fake(8)
    # Days 0 to 4 are closed and 12 deep below the indexed height, so only the tip holds the base back.
    fake.indexed_height = last_height(fake, _day(4)) + DEPTH
    fake.tip_height = fake.indexed_height + 1

    code, lines = _cli(tmp_path, fake, monkeypatch)

    assert code == 0
    assert [level for level, _ in lines] == ["INFO", "INFO"]
    assert f"height {fake.indexed_height}" in lines[0][1] and f"tip at {fake.tip_height}" in lines[0][1]
    assert lines[1][1] == _complete(None, 0, 0)
    assert line_days(tmp_path / NAME) == []


def test_an_unreachable_index_before_the_base_is_info_and_exit_0(tmp_path, monkeypatch):
    fake = _fake(8)
    _confirm(fake, _day(4))
    fake.unreachable = True

    code, lines = _cli(tmp_path, fake, monkeypatch)

    assert code == 0
    assert [level for level, _ in lines] == ["INFO", "INFO"]
    assert "unreachable" in lines[0][1] and "/api/series/list" in lines[0][1]
    assert lines[1][1] == _complete(None, 0, 0)
    assert line_days(tmp_path / NAME) == []


@pytest.mark.parametrize(
    ("index", "after", "code"),
    [
        ("nothing-due", timedelta(seconds=-1), 0),
        ("nothing-due", timedelta(seconds=1), 1),
        ("two-days-due", timedelta(seconds=1), 0),
        ("unreachable", timedelta(seconds=1), 1),
    ],
    ids=["nothing-due-1s-before", "nothing-due-1s-after", "two-days-due-1s-after", "unreachable-1s-after"],
)
def test_a_stale_index_after_the_base_is_an_error(tmp_path, caplog, index, after, code):
    fake = _fake(10)
    head = _day(4)
    build_chain(tmp_path, fake, [head])
    if index == "two-days-due":
        _confirm(fake, _day(6))
    else:
        # Every block of the day after the head is indexed, none of the day after it, so nothing is due.
        fake.indexed_height = last_height(fake, _day(5))
        fake.tip_height = fake.indexed_height + 12
        fake.unreachable = index == "unreachable"
    # The end of the day after the head, 48 hours on.
    bar = datetime.combine(head + timedelta(days=4), time(), UTC)
    caplog.set_level(logging.INFO)
    caplog.clear()

    assert _command(tmp_path, fake, bar + after) == code

    errors = _messages(caplog, logging.ERROR)
    if index == "two-days-due":
        assert errors == []
        assert _messages(caplog, logging.INFO) == [_complete(_day(6), 2, 0)]
        assert line_days(tmp_path / NAME) == [head, _day(5), _day(6)]
    elif code == 0:
        assert errors == []
        assert _messages(caplog, logging.INFO) == [_complete(head, 0, 0)]
    else:
        height = "unread" if index == "unreachable" else fake.indexed_height
        assert len(errors) == 1
        assert errors[0].startswith(f"onchain write stopped chain={NAME} head={head} reason=")
        assert str(_day(5)) in errors[0] and f"height {height}" in errors[0]
        assert ("/api/block-height/" in errors[0]) == (index == "unreachable")
        assert _messages(caplog, logging.WARNING) == []


def test_an_unreachable_index_after_the_base_warns_inside_the_bar(tmp_path, caplog):
    fake = _fake(8)
    build_chain(tmp_path, fake, [_day(4)])
    root = tmp_path / NAME
    tree = _tree(root)
    fake.unreachable = True
    caplog.set_level(logging.INFO)
    caplog.clear()

    assert _command(tmp_path, fake, day_end(_day(4)) + timedelta(hours=30)) == 0

    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == 1 and "/api/block-height/" in warnings[0]
    assert _messages(caplog, logging.ERROR) == []
    assert _messages(caplog, logging.INFO) == [_complete(_day(4), 0, 0)]
    assert _tree(root) == tree


def test_a_changed_file_among_the_newest_30_stops_the_run_and_writes_nothing(tmp_path, caplog):
    fake = _fake(10)
    lines = build_chain(tmp_path, fake, [_day(4), _day(5), _day(6)])
    root = tmp_path / NAME
    (relpath,) = lines[-1].files
    changed = pl.read_parquet(root / relpath).with_columns(pl.col("price") + 1.0)
    (root / relpath).unlink()
    changed.write_parquet(root / relpath)
    _confirm(fake, _day(7))
    tree = _tree(root)
    caplog.set_level(logging.INFO)
    caplog.clear()

    assert _command(tmp_path, fake, day_end(_day(7)) + timedelta(hours=2)) == 1

    errors = _messages(caplog, logging.ERROR)
    assert len(errors) == 1
    assert errors[0].startswith(f"onchain write stopped chain={NAME} head={_day(6)} reason=") and relpath in errors[0]
    assert _tree(root) == tree


def test_a_staging_leftover_is_named_in_a_warning_and_the_run_goes_on(tmp_path, caplog):
    fake = _fake(8)
    build_chain(tmp_path, fake, [_day(4)])
    leftover = tmp_path / NAME / "staging" / "25.parquet.4242.0badf00d"
    leftover.write_bytes(b"a temporary a writer that died left")
    _confirm(fake, _day(5))
    caplog.set_level(logging.INFO)
    caplog.clear()

    assert _run(tmp_path, fake, day_end(_day(5)) + timedelta(hours=2)) == WriteOutcome((_day(5),), False, None)

    warnings = _messages(caplog, logging.WARNING)
    assert len(warnings) == 1 and str(leftover) in warnings[0]
    assert leftover.read_bytes() == b"a temporary a writer that died left"


@pytest.mark.parametrize("based", [False, True], ids=["before-the-base", "after-the-base"])
def test_a_series_the_instance_lacks_refuses_the_run_naming_it(tmp_path, based):
    fake = _fake(8)
    if based:
        build_chain(tmp_path, fake, [_day(3)])
    _confirm(fake, _day(5))
    lacked = BRK_SERIES["asopr"]
    fake.ids = sorted(set(fake.series) - {lacked})
    days = line_days(tmp_path / NAME)

    outcome = _run(tmp_path, fake, day_end(_day(5)) + timedelta(hours=2))

    assert (outcome.wrote, outcome.base) == ((), False)
    assert outcome.stopped is not None and lacked in outcome.stopped
    assert line_days(tmp_path / NAME) == days


def test_mvrv_z_of_a_day_line_equals_the_rebuilds(tmp_path):
    fake = _fake(MVRV_Z_MIN_VALUES + 4)
    base = _day(MVRV_Z_MIN_VALUES)
    days = [base, base + timedelta(days=1), base + timedelta(days=2)]
    (tmp_path / "three").mkdir()
    (tmp_path / "one").mkdir()
    lines = build_chain(tmp_path / "three", fake, days)

    assert _run(tmp_path / "one", fake, day_end(days[-1]) + timedelta(hours=2)) == WriteOutcome((days[-1],), True, None)

    three = pl.concat([pl.read_parquet(tmp_path / "three" / NAME / relpath) for line in lines for relpath in line.files])
    one = pl.read_parquet(tmp_path / "one" / NAME / "base/history.parquet")
    assert three["mvrv_z"].tail(2).null_count() == 0
    assert_frame_equal(three, one, check_exact=True)


def test_a_held_lock_exits_1_with_the_writers_own_message(tmp_path, caplog):
    fake = _fake(8)
    build_chain(tmp_path, fake, [_day(3)])
    _confirm(fake, _day(4))
    fake.seen.clear()
    root = tmp_path / NAME
    fd = os.open(root / LOCKFILE_NAME, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        caplog.set_level(logging.INFO)
        code = _command(tmp_path, fake, day_end(_day(4)))
    finally:
        os.close(fd)

    assert code == 1
    assert _messages(caplog, logging.ERROR) == [
        f"another onchain writer holds {root}; refusing. Read the zcrypto-onchain-write.service journal",
        f"onchain write stopped chain={NAME} head={_day(3)} reason=lock held",
    ]
    assert fake.seen == []
    assert line_days(root) == [_day(3)]


@pytest.mark.parametrize("based", [False, True], ids=["before-the-base", "after-the-base"])
def test_a_day_the_index_serves_no_value_for_stops_the_run_naming_the_series_and_the_day(tmp_path, based):
    fake = _fake(8)
    if based:
        build_chain(tmp_path, fake, [_day(3)])
    _confirm(fake, _day(5))
    # The answer ends at day 4, so day 5 is absent from it, not served null.
    series_id = BRK_SERIES["sth_mvrv"]
    for n in (5, 6, 7):
        del fake.series[series_id][_day(n)]
    days = line_days(tmp_path / NAME)

    outcome = _run(tmp_path, fake, day_end(_day(5)) + timedelta(hours=2))

    assert outcome == WriteOutcome((), False, f"the index serves no value of {series_id} for {_day(5)}; nothing written")
    assert line_days(tmp_path / NAME) == days


@pytest.mark.parametrize(
    "commit", [COMMIT[:12], COMMIT.upper(), COMMIT + "0"], ids=["12-character-prefix", "uppercase", "41-characters"]
)
def test_a_brk_commit_not_of_40_lowercase_hex_characters_is_refused_before_a_chain_is_opened(tmp_path, caplog, commit):
    fake = _fake(8)
    _confirm(fake, _day(4))
    caplog.set_level(logging.INFO)

    code = run_onchain_write(
        tmp_path,
        fake_client(fake),
        brk_commit=commit,
        bitview_image=BITVIEW_IMAGE,
        bitcoind_image=BITCOIND_IMAGE,
        now=day_end(_day(4)),
    )

    assert code == 1
    reason = f"the BRK commit {commit!r} is not 40 lowercase hex characters; no chain is opened"
    assert _messages(caplog, logging.ERROR) == [f"onchain write stopped chain={chain_name(commit)} head=none reason={reason}"]
    assert list(tmp_path.iterdir()) == [] and fake.seen == []


def test_an_absent_chain_root_is_refused_and_never_made(tmp_path, caplog):
    fake = _fake(8)
    _confirm(fake, _day(4))
    absent = tmp_path / "absent"
    caplog.set_level(logging.INFO)

    assert _command(absent, fake, day_end(_day(4))) == 1

    reason = f"{absent} is not a directory; the writer never makes the chain root"
    assert _messages(caplog, logging.ERROR) == [f"onchain write stopped chain={NAME} head=none reason={reason}"]
    assert not absent.exists() and fake.seen == []


def test_the_vintage_carries_its_keys(tmp_path):
    fake = _fake(8)
    lines = build_chain(tmp_path, fake, [_day(3), _day(4), _day(5)])

    assert [line.day for line in lines] == [_day(3), _day(4), _day(5)]
    for line in lines:
        height = last_height(fake, line.day)
        assert line.vintage.keys() == VINTAGE_KEYS
        assert line.vintage == {
            "written_at": (day_end(line.day) + timedelta(hours=2, minutes=17)).isoformat(),
            "last_height": height,
            "last_hash": f"{height:064x}",
            "tip_height": height + 12,
            "depth": 12,
            "brk_commit": COMMIT,
            "bitview_image": BITVIEW_IMAGE,
            "bitcoind_image": BITCOIND_IMAGE,
            "chain": (tmp_path / NAME).name,
        }
