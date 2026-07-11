from __future__ import annotations

import pytest

from cli.backfill.aggregate import aggregate_minutes
from cli.ohlc.dataset import to_frame

HOUR = 3600
QUARTER_HOUR = 900


def _row(ts, o, h, l, c, v, n):
    return [ts, o, h, l, c, v, n]


def test_aggregate_minutes_single_bucket_ohlc_and_vwap():
    rows = [
        _row(0, "100.0", "101.0", "99.0", "100.5", "1.0", 5),
        _row(60, "100.5", "102.0", "100.0", "101.0", "2.0", 3),
        _row(120, "101.0", "101.5", "100.5", "100.8", "1.0", 2),
        _row(180, "100.8", "100.9", "100.0", "100.2", "0.0", 0),
    ]

    out = aggregate_minutes(rows, HOUR)

    assert len(out) == 1
    bucket_ts, o, h, l, c, vwap, volume, count = out[0]
    assert bucket_ts == 0
    assert o == pytest.approx(100.0)
    assert h == pytest.approx(102.0)
    assert l == pytest.approx(99.0)
    assert c == pytest.approx(100.2)
    assert volume == pytest.approx(4.0)
    assert count == 10
    expected_vwap = (100.5 * 1.0 + 101.0 * 2.0 + 100.8 * 1.0 + 100.2 * 0.0) / 4.0
    assert vwap == pytest.approx(expected_vwap)


def test_aggregate_minutes_splits_across_buckets_with_floor():
    rows = [
        _row(3599, "1", "1", "1", "1", "1.0", 1),  # last minute of bucket 0
        _row(3600, "2", "2", "2", "2", "1.0", 1),  # first minute of bucket 3600
    ]

    out = aggregate_minutes(rows, HOUR)

    assert [r[0] for r in out] == [0, 3600]


def test_aggregate_minutes_900s_buckets_ohlc_and_vwap():
    rows = [
        _row(0, "100.0", "101.0", "99.0", "100.5", "1.0", 5),
        _row(60, "100.5", "102.0", "100.0", "101.0", "2.0", 3),
        _row(840, "101.0", "101.5", "100.5", "100.8", "1.0", 2),  # last minute of bucket 0
        _row(900, "100.8", "100.9", "100.0", "100.2", "1.0", 1),  # first minute of bucket 900
    ]

    out = aggregate_minutes(rows, QUARTER_HOUR)

    assert [r[0] for r in out] == [0, 900]
    bucket_ts, o, h, l, c, vwap, volume, count = out[0]
    assert bucket_ts == 0
    assert o == pytest.approx(100.0)
    assert h == pytest.approx(102.0)
    assert l == pytest.approx(99.0)
    assert c == pytest.approx(100.8)
    assert volume == pytest.approx(4.0)
    assert count == 10
    expected_vwap = (100.5 * 1.0 + 101.0 * 2.0 + 100.8 * 1.0) / 4.0
    assert vwap == pytest.approx(expected_vwap)


def test_aggregate_minutes_zero_volume_bucket_vwap_is_close():
    rows = [_row(0, "100.0", "100.0", "100.0", "100.0", "0.0", 0)]

    out = aggregate_minutes(rows, HOUR)

    assert out[0][4] == pytest.approx(100.0)  # close
    assert out[0][5] == pytest.approx(100.0)  # vwap == close when volume == 0


def test_aggregate_minutes_empty_input_returns_empty():
    assert aggregate_minutes([], HOUR) == []


def test_aggregate_minutes_feeds_to_frame_cleanly():
    rows = [
        _row(0, "100.0", "101.0", "99.0", "100.5", "1.0", 5),
        _row(3600, "100.5", "102.0", "100.0", "101.0", "2.0", 3),
    ]

    frame = to_frame(aggregate_minutes(rows, HOUR))

    assert frame.height == 2
    assert frame.columns == ["ts", "open", "high", "low", "close", "vwap", "volume", "count"]
