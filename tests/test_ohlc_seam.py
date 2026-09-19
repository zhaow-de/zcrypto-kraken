from datetime import UTC, datetime, timedelta

import polars as pl

from cli.ohlc.seam import drop_in_progress, seam_overlap

NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)


def test_drop_in_progress_drops_forming_candle_keeps_boundary():
    frame = pl.DataFrame(
        {
            "ts": [NOW - timedelta(minutes=120), NOW - timedelta(minutes=60), NOW - timedelta(minutes=30)],
            "close": [1.0, 2.0, 3.0],
        }
    )
    out = drop_in_progress(frame, 60, NOW)
    # -30min ends after NOW -> dropped; -60min ends exactly at NOW -> complete, kept.
    assert out["ts"].to_list() == [NOW - timedelta(minutes=120), NOW - timedelta(minutes=60)]


def test_seam_overlap_counts_shared_stamps_and_flags_close_disagreement():
    left = pl.DataFrame({"ts": [NOW, NOW + timedelta(hours=1)], "close": [1.0, 2.0]})
    right = pl.DataFrame({"ts": [NOW + timedelta(hours=1), NOW + timedelta(hours=2)], "close": [2.5, 3.0]})
    overlap_bars, mismatches = seam_overlap(left, right)
    assert overlap_bars == 1
    assert mismatches.height == 1
    assert mismatches["close"][0] == 2.0
    assert mismatches["close_rest"][0] == 2.5


def test_seam_overlap_clean_seam_has_no_mismatches():
    left = pl.DataFrame({"ts": [NOW], "close": [1.0]})
    right = pl.DataFrame({"ts": [NOW], "close": [1.0]})
    overlap_bars, mismatches = seam_overlap(left, right)
    assert overlap_bars == 1
    assert mismatches.is_empty()
