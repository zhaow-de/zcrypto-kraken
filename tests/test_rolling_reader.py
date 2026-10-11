import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import pytest
from polars.testing import assert_frame_equal
from typer.testing import CliRunner

from cli.__main__ import app
from cli.data.rolling import ROLLING_SET, RollingError, head, line_days, read_rolling, verify
from cli.ohlc.dataset import FRAME_SCHEMA
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from tests.rolling_fixtures import BARS_PER_DAY, BASE_DAY, HOLE, TAPE_ORDER, line_bytes, write_chain

runner = CliRunner()
DAY1, DAY2, DAY3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)


def _at(day: date, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def _edit_line(root: Path, relpath: str, edit) -> None:
    line = json.loads((root / relpath).read_bytes())
    edit(line)
    (root / relpath).write_bytes(line_bytes(line))


def _change_a_prev_digit(line: dict) -> None:
    line["prev"] = ("1" if line["prev"][0] == "0" else "0") + line["prev"][1:]


def _verify(root: Path, as_of: str):
    return runner.invoke(app, ["data", "rolling", "verify", "--root", str(root), "--as-of", as_of])


def test_the_read_returns_the_base_and_the_days_up_to_the_as_of_day(tmp_path):
    write_chain(tmp_path)

    read = read_rolling(tmp_path, "BTC/EUR", 15, DAY2)

    assert read.frame.height == 3 * BARS_PER_DAY
    assert read.frame["ts"].is_sorted()
    assert (read.frame["ts"][0], read.frame["ts"][-1]) == (_at(BASE_DAY), _at(DAY2, 23, 45))
    assert read.frame.filter(pl.col("ts") == _at(DAY1))["close"].to_list() == [111.0]
    assert read.holes == ()
    assert read.line.relpath == "index/2026/10/02.json"


@pytest.mark.parametrize(("interval", "bars"), [(15, 4 * 96), (60, 4 * 24), (240, 4 * 6), (1440, 4)])
def test_the_read_returns_frame_schema_columns_from_tape_order_day_files(tmp_path, interval, bars):
    write_chain(tmp_path)
    assert pl.read_parquet(tmp_path / "days/BTC/EUR/2026/10/01.parquet").columns == list(TAPE_ORDER)

    frame = read_rolling(tmp_path, "BTC/EUR", interval, DAY3).frame

    assert frame.columns == FRAME_SCHEMA.names()
    assert frame.schema == FRAME_SCHEMA
    assert frame.height == bars


def test_a_coarse_grid_is_derived_across_the_seam_as_bars_computed_by_hand(tmp_path):
    fields = {DAY1: {"volume": 2.5}, DAY2: {"vwap": 123.25}}
    write_chain(tmp_path, days=2, bar=lambda pair, day: fields.get(day, {}))

    frame = read_rolling(tmp_path, "BTC/EUR", 1440, DAY2).frame

    expected = pl.DataFrame(
        {
            "ts": [_at(BASE_DAY), _at(DAY1), _at(DAY2)],
            "open": [100.0, 110.0, 120.0],
            "high": [197.0, 207.0, 217.0],
            "low": [99.0, 109.0, 119.0],
            "close": [196.0, 206.0, 216.0],
            "vwap": [148.0, 158.0, 123.25],
            "volume": [48.0, 240.0, 48.0],
            "count": [288, 288, 288],
        },
        schema=FRAME_SCHEMA,
    )
    assert_frame_equal(frame, expected)


def test_an_edited_line_breaks_the_chain(tmp_path):
    write_chain(tmp_path)
    _edit_line(tmp_path, "index/2026/10/01.json", _change_a_prev_digit)

    with pytest.raises(RollingError, match=r"index/2026/10/01\.json"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3)


def test_a_skipped_day_breaks_the_chain(tmp_path):
    write_chain(tmp_path, skip=DAY2)
    assert not (tmp_path / "index/2026/10/02.json").exists()

    with pytest.raises(RollingError, match=r"index/2026/10/03\.json: no line for 2026-10-02"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3)


def test_two_day_files_swapped_between_pairs_are_refused(tmp_path):
    write_chain(tmp_path)
    ours, theirs = tmp_path / "days/BTC/EUR/2026/10/01.parquet", tmp_path / "days/ETH/BTC/2026/10/01.parquet"
    our_bytes, their_bytes = ours.read_bytes(), theirs.read_bytes()
    assert our_bytes != their_bytes
    ours.write_bytes(their_bytes)
    theirs.write_bytes(our_bytes)

    with pytest.raises(RollingError, match=r"days/BTC/EUR/2026/10/01\.parquet"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3)


def test_a_listed_file_absent_is_refused(tmp_path):
    write_chain(tmp_path)
    (tmp_path / "days/BTC/EUR/2026/10/02.parquet").unlink()

    with pytest.raises(RollingError, match=r"days/BTC/EUR/2026/10/02\.parquet"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3)


def test_an_as_of_past_the_head_is_refused(tmp_path):
    write_chain(tmp_path)

    with pytest.raises(RollingError, match="2026-10-04"):
        read_rolling(tmp_path, "BTC/EUR", 15, date(2026, 10, 4))


def test_a_line_naming_a_pair_outside_the_base_is_refused(tmp_path):
    write_chain(tmp_path)
    _edit_line(tmp_path, "index/2026/10/03.json", lambda line: line["holes"].update({"SOL/EUR": HOLE}))

    with pytest.raises(RollingError, match=r"index/2026/10/03\.json"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3)


def test_a_pair_outside_the_set_is_refused(tmp_path):
    write_chain(tmp_path)

    with pytest.raises(RollingError) as refused:
        read_rolling(tmp_path, "SOL/EUR", 15, DAY3)

    assert all(pair in str(refused.value) for pair in ("SOL/EUR", "BTC/EUR", "ETH/BTC"))


def test_a_hole_inside_the_window_is_refused_without_accept_holes(tmp_path):
    write_chain(tmp_path, holes={DAY2: {"BTC/EUR"}})

    with pytest.raises(RollingError, match="BTC/EUR.*2026-10-02"):
        read_rolling(tmp_path, "BTC/EUR", 15, DAY3, window=(_at(DAY2, 12), _at(DAY3, 23, 45)))


def test_a_hole_on_the_windows_last_day_is_refused_with_the_window_ending_at_that_days_midnight(tmp_path):
    write_chain(tmp_path, holes={DAY3: {"BTC/EUR"}})

    with pytest.raises(RollingError, match="BTC/EUR has a hole on 2026-10-03"):
        read_rolling(tmp_path, "BTC/EUR", 1440, DAY3, window=(_at(DAY1), _at(DAY3)))


def test_an_accepted_hole_is_reported_and_its_day_left_out(tmp_path):
    write_chain(tmp_path, holes={DAY2: {"BTC/EUR"}})

    read = read_rolling(tmp_path, "BTC/EUR", 15, DAY3, accept_holes=True)

    assert read.holes == (DAY2,)
    assert read.frame["ts"].dt.date().unique().sort().to_list() == [BASE_DAY, DAY1, DAY3]
    assert read.frame.height == 3 * BARS_PER_DAY


def test_a_hole_outside_the_window_is_not_a_refusal(tmp_path):
    write_chain(tmp_path, holes={DAY2: {"BTC/EUR"}})

    read = read_rolling(tmp_path, "BTC/EUR", 15, DAY3, window=(_at(DAY3), _at(DAY3, 23, 45)))

    assert read.holes == ()
    assert (read.frame.height, read.frame["ts"][0]) == (BARS_PER_DAY, _at(DAY3))


def _observed_block(data_root: Path) -> dict:
    reader = ObservedReader(data_root)
    for pair in ("BTC/EUR", "ETH/BTC"):
        for interval in (15, 1440):
            reader.read_rolling(ROLLING_SET, pair, interval, "2026-10-03")
    return reader.block()


def test_a_rolling_read_records_the_as_of_line_alone(tmp_path):
    write_chain(tmp_path / ROLLING_SET)
    line = (tmp_path / ROLLING_SET / "index/2026/10/03.json").read_bytes()

    block = _observed_block(tmp_path)

    assert block[ROLLING_SET]["files"] == {"index/2026/10/03.json": hashlib.sha256(line).hexdigest()}


def test_a_rolling_pin_reproduces_one_block_read_twice(tmp_path):
    write_chain(tmp_path / ROLLING_SET)

    first, second = _observed_block(tmp_path), _observed_block(tmp_path)

    assert first == second
    assert compute_hash(first) == compute_hash(second)


def test_the_head_is_the_newest_line_whose_files_are_present(tmp_path):
    write_chain(tmp_path)
    (tmp_path / "days/ETH/BTC/2026/10/03.parquet").unlink()

    assert head(tmp_path).day == DAY2


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_an_unlistable_index_month_raises_never_reads_an_older_line_as_the_newest(tmp_path):
    write_chain(tmp_path)
    month = tmp_path / "index/2026/10"
    os.chmod(month, 0o000)
    try:
        with pytest.raises(PermissionError) as raised:
            line_days(tmp_path)
    finally:
        os.chmod(month, 0o755)

    assert raised.value.filename == str(month)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
@pytest.mark.parametrize("reader", ["head", "verify", "read_rolling"])
def test_a_day_directory_the_reader_cannot_search_raises_never_reads_its_files_as_absent(tmp_path, reader):
    write_chain(tmp_path)
    month = tmp_path / "days/BTC/EUR/2026/10"
    read = {
        "head": lambda: head(tmp_path),
        "verify": lambda: verify(tmp_path, DAY3),
        "read_rolling": lambda: read_rolling(tmp_path, "BTC/EUR", 15, DAY3),
    }[reader]
    os.chmod(month, 0o000)
    try:
        with pytest.raises(PermissionError) as raised:
            read()
    finally:
        os.chmod(month, 0o755)

    assert Path(raised.value.filename).parent == month


def test_verify_prints_the_as_of_lines_sha256_and_exits_0(tmp_path):
    write_chain(tmp_path)
    digest = hashlib.sha256((tmp_path / "index/2026/10/03.json").read_bytes()).hexdigest()

    result = _verify(tmp_path, "2026-10-03")

    assert result.exit_code == 0, result.output
    assert f"2026-10-03 {digest} files=8" in result.output.splitlines()


def test_verify_names_the_first_broken_link_and_exits_1(tmp_path):
    write_chain(tmp_path)
    _edit_line(tmp_path, "index/2026/10/01.json", _change_a_prev_digit)

    result = _verify(tmp_path, "2026-10-03")

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "index/2026/10/02.json: its prev is not the sha256 of index/2026/10/01.json" in result.output


def test_verify_refuses_a_flipped_byte_in_an_earlier_days_file(tmp_path):
    write_chain(tmp_path)
    path = tmp_path / "days/BTC/EUR/2026/10/01.parquet"
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))

    result = _verify(tmp_path, "2026-10-03")

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "days/BTC/EUR/2026/10/01.parquet" in result.output


def test_verify_refuses_an_os_error_in_one_line(tmp_path, monkeypatch):
    from cli.data import rolling

    unreadable = tmp_path / "index/2026/10/01.json"

    def _verify_unreadable(root, as_of):
        raise OSError(13, "Permission denied", str(unreadable))

    monkeypatch.setattr(rolling, "verify", _verify_unreadable)

    result = _verify(tmp_path, "2026-10-03")

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(unreadable) in result.output


def test_the_cli_loads_where_no_data_root_is_configured(tmp_path):
    assert not (tmp_path / "zcrypto.toml").exists()

    result = subprocess.run(
        [sys.executable, "-m", "cli", "data", "rolling", "verify", "--help"], cwd=tmp_path, capture_output=True, text=True
    )

    assert result.returncode == 0, result.stderr
