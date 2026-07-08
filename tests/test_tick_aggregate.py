from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from cli.tick.aggregate import ticks_to_bars

HOUR = 60


def _tick_frame(rows: list[tuple[int, float, float, str]]) -> pl.DataFrame:
    """Build a tick frame (as `read_trades_csv` would return) from `(epoch_secs, price, volume, side)`
    rows."""
    return pl.DataFrame(
        {
            "ts": [datetime.fromtimestamp(ts, tz=UTC) for ts, _, _, _ in rows],
            "price": [p for _, p, _, _ in rows],
            "volume": [v for _, _, v, _ in rows],
            "side": [s for _, _, _, s in rows],
        },
        schema={"ts": pl.Datetime("us", "UTC"), "price": pl.Float64, "volume": pl.Float64, "side": pl.Utf8},
    )


def test_ticks_to_bars_single_bucket_ohlc_volume_count_and_true_vwap():
    ticks = _tick_frame(
        [
            (0, 100.0, 1.0, "b"),
            (600, 102.0, 2.0, "s"),
            (1200, 99.0, 0.5, "b"),
            (3599, 100.5, 1.5, "s"),
        ]
    )

    out = ticks_to_bars(ticks, interval_minutes=HOUR)

    assert out.height == 1
    row = out.row(0, named=True)
    assert row["ts"] == datetime.fromtimestamp(0, tz=UTC)
    assert row["open"] == pytest.approx(100.0)  # first by time
    assert row["high"] == pytest.approx(102.0)
    assert row["low"] == pytest.approx(99.0)
    assert row["close"] == pytest.approx(100.5)  # last by time
    assert row["volume"] == pytest.approx(5.0)
    assert row["count"] == 4
    expected_vwap = (100.0 * 1.0 + 102.0 * 2.0 + 99.0 * 0.5 + 100.5 * 1.5) / 5.0
    assert row["vwap"] == pytest.approx(expected_vwap)


def test_ticks_to_bars_tick_at_bucket_boundary_lands_in_the_new_bucket():
    ticks = _tick_frame(
        [
            (3599, 100.0, 1.0, "b"),  # last second of bucket 0
            (3600, 200.0, 1.0, "s"),  # exactly the next bucket's start — left-closed, belongs to it
        ]
    )

    out = ticks_to_bars(ticks, interval_minutes=HOUR)

    assert out["ts"].to_list() == [datetime.fromtimestamp(0, tz=UTC), datetime.fromtimestamp(3600, tz=UTC)]
    assert out["open"].to_list() == [100.0, 200.0]
    assert out["count"].to_list() == [1, 1]


def test_ticks_to_bars_unsorted_input_is_sorted_before_bucketing():
    ticks = _tick_frame(
        [
            (1200, 99.0, 0.5, "b"),
            (0, 100.0, 1.0, "b"),
            (600, 102.0, 2.0, "s"),
        ]
    )

    out = ticks_to_bars(ticks, interval_minutes=HOUR)

    assert out.height == 1
    assert out.row(0, named=True)["open"] == pytest.approx(100.0)
    assert out.row(0, named=True)["close"] == pytest.approx(99.0)


def test_ticks_to_bars_empty_input_returns_empty_frame_no_error():
    empty = pl.DataFrame(schema={"ts": pl.Datetime("us", "UTC"), "price": pl.Float64, "volume": pl.Float64, "side": pl.Utf8})

    out = ticks_to_bars(empty, interval_minutes=HOUR)

    assert out.height == 0
    assert out.columns == ["ts", "open", "high", "low", "close", "volume", "count", "vwap"]


def test_ticks_to_bars_column_schema():
    ticks = _tick_frame([(0, 100.0, 1.0, "b")])

    out = ticks_to_bars(ticks, interval_minutes=HOUR)

    assert out.columns == ["ts", "open", "high", "low", "close", "volume", "count", "vwap"]
    assert out.schema["count"] == pl.Int64
