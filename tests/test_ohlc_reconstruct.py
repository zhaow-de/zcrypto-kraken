from __future__ import annotations

import polars as pl

from cli.ohlc.dataset import to_frame
from cli.ohlc.qa import detect_gaps
from cli.ohlc.reconstruct import fill_gaps

BASE_TS = 1721174400  # 2024-07-17T00:00:00Z
DAY = 86400


def _row(ts: int, *, close: str = "100.0") -> list:
    return [ts, "100.0", "101.0", "99.0", close, "100.0", "10.0", 5]


def _daily_rows(n: int) -> list[list]:
    # distinct close per day (100.0, 101.0, ...) so a forward-filled synthetic bar is distinguishable from a real one.
    return [_row(BASE_TS + i * DAY, close=f"{100 + i}.0") for i in range(n)]


def test_fill_gaps_inserts_one_synthetic_bar_at_the_missing_grid_point():
    full = to_frame(_daily_rows(5))
    gap_ts = full["ts"][2]
    prior_close = full["close"][1]

    rows = _daily_rows(5)
    del rows[2]
    frame = to_frame(rows)

    result = fill_gaps(frame, DAY)

    assert result.height == 5
    assert result.filter(pl.col("ts") != gap_ts).equals(frame)

    synthetic = result.filter(pl.col("ts") == gap_ts).row(0, named=True)
    assert synthetic["open"] == synthetic["high"] == synthetic["low"] == synthetic["close"] == synthetic["vwap"] == prior_close
    assert synthetic["volume"] == 0.0
    assert synthetic["count"] == 0


def test_fill_gaps_two_consecutive_missing_bars_share_the_same_prior_close():
    full = to_frame(_daily_rows(6))
    gap_ts_1 = full["ts"][2]
    gap_ts_2 = full["ts"][3]
    prior_close = full["close"][1]

    rows = _daily_rows(6)
    del rows[3]  # delete higher index first so the lower index stays stable
    del rows[2]
    frame = to_frame(rows)

    result = fill_gaps(frame, DAY)

    assert result.height == 6
    synthetic = result.filter(pl.col("ts").is_in([gap_ts_1, gap_ts_2]))
    assert synthetic.height == 2
    for row in synthetic.iter_rows(named=True):
        assert row["open"] == row["high"] == row["low"] == row["close"] == row["vwap"] == prior_close
        assert row["volume"] == 0.0
        assert row["count"] == 0


def test_fill_gaps_contiguous_frame_is_returned_unchanged():
    frame = to_frame(_daily_rows(5))

    result = fill_gaps(frame, DAY)

    assert result.height == frame.height
    assert result.equals(frame)


def test_fill_gaps_returns_frame_unchanged_when_fewer_than_two_rows():
    empty = to_frame([])
    single = to_frame(_daily_rows(1))

    assert fill_gaps(empty, DAY).equals(empty)
    assert fill_gaps(single, DAY).equals(single)


def test_fill_gaps_round_trip_has_no_gaps_left():
    rows = _daily_rows(10)
    del rows[7]  # delete in descending order so earlier indices stay stable
    del rows[5]
    del rows[2]
    frame = to_frame(rows)

    result = fill_gaps(frame, DAY)

    assert result.height == 10
    assert detect_gaps(result, DAY) == []


def test_fill_gaps_output_schema_matches_input_schema():
    rows = _daily_rows(5)
    del rows[2]
    frame = to_frame(rows)

    result = fill_gaps(frame, DAY)

    assert result.schema == frame.schema
    assert result.columns == frame.columns
