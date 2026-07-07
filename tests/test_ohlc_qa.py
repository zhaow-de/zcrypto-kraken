from __future__ import annotations

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from cli.ohlc.dataset import to_frame
from cli.ohlc.qa import detect_gaps, qa_series, render_markdown, wick_outliers

BASE_TS = 1721174400  # 2024-07-17T00:00:00Z
DAY = 86400


def _row(ts: int, *, high: str = "101.0", low: str = "99.0", volume: str = "10.0") -> list:
    return [ts, "100.0", high, low, "100.0", "100.0", volume, 5]


def _daily_rows(n: int) -> list[list]:
    return [_row(BASE_TS + i * DAY) for i in range(n)]


def test_detect_gaps_finds_one_mid_series_gap():
    rows = _daily_rows(5)
    del rows[2]  # delete the mid-series candle, leaving a 2-day gap
    frame = to_frame(rows)

    gaps = detect_gaps(frame, DAY)

    assert len(gaps) == 1
    assert gaps[0]["missing"] == 1
    assert gaps[0]["after_ts"] == frame["ts"][1]
    assert gaps[0]["before_ts"] == frame["ts"][2]


def test_detect_gaps_contiguous_frame_has_no_gaps():
    frame = to_frame(_daily_rows(5))

    assert detect_gaps(frame, DAY) == []


def test_wick_outliers_flags_extreme_candle_only():
    rows = _daily_rows(3)
    rows[1] = _row(BASE_TS + DAY, high="140.0", low="90.0")  # rel_range == 0.50
    frame = to_frame(rows)

    outliers = wick_outliers(frame)

    assert len(outliers) == 1
    assert outliers[0]["ts"] == frame["ts"][1]
    assert outliers[0]["high"] == 140.0
    assert outliers[0]["low"] == 90.0
    assert outliers[0]["close"] == 100.0
    assert outliers[0]["rel_range"] == pytest.approx(0.50)


def test_wick_outliers_respects_threshold():
    frame = to_frame(_daily_rows(2))  # rel_range == 0.02 for every candle

    assert wick_outliers(frame) == []
    assert len(wick_outliers(frame, rel_range=0.01)) == 2


def test_qa_series_reports_gap_coverage_and_flags():
    rows = _daily_rows(10)
    del rows[5]  # one missing candle
    frame = to_frame(rows)

    result = qa_series(frame, DAY)

    assert result["rows"] == 9
    assert result["first_ts"] == frame["ts"][0]
    assert result["last_ts"] == frame["ts"][-1]
    assert result["gap_count"] == 1
    assert result["missing_candles"] == 1
    assert result["coverage_pct"] == pytest.approx(9 / 10 * 100)
    assert result["wick_outlier_count"] == 0
    assert result["monotonic_ts"] is True
    assert result["nonneg_volume"] is True


def test_qa_series_flags_non_monotonic_ts():
    start = datetime.fromtimestamp(BASE_TS, tz=timezone.utc)
    frame = pl.DataFrame(
        {
            "ts": [start + timedelta(days=1), start],  # out of order
            "open": [100.0, 100.0],
            "high": [101.0, 101.0],
            "low": [99.0, 99.0],
            "close": [100.0, 100.0],
            "vwap": [100.0, 100.0],
            "volume": [10.0, 10.0],
            "count": [5, 5],
        }
    ).with_columns(pl.col("ts").cast(pl.Datetime("us", "UTC")))

    result = qa_series(frame, DAY)

    assert result["monotonic_ts"] is False


def test_qa_series_flags_negative_volume():
    rows = _daily_rows(3)
    rows[1] = _row(BASE_TS + DAY, volume="-5.0")
    frame = to_frame(rows)

    result = qa_series(frame, DAY)

    assert result["nonneg_volume"] is False


def test_render_markdown_contains_series_rows_and_summary():
    report = {
        "series": {
            "BTC/EUR/1440": {
                "rows": 10,
                "first_ts": "2024-07-17T00:00:00+00:00",
                "last_ts": "2024-07-26T00:00:00+00:00",
                "gap_count": 1,
                "missing_candles": 1,
                "coverage_pct": 90.0,
                "wick_outlier_count": 0,
                "monotonic_ts": True,
                "nonneg_volume": True,
            }
        },
        "summary": {"series_count": 1, "total_gaps": 1, "min_coverage_pct": 90.0},
    }

    md = render_markdown(report)

    assert "BTC/EUR/1440" in md
    assert "90.00" in md
    assert "Series count: 1" in md
    assert "Total gaps: 1" in md
    assert "Min coverage" in md
