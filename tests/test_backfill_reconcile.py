from __future__ import annotations

import pytest

from cli.backfill.reconcile import reconcile_dataset, reconcile_series, render_markdown
from cli.ohlc.dataset import to_frame, write_parquet

BASE_TS = 1721174400  # 2024-07-17T00:00:00Z
HOUR = 3600


def _row(ts, o="100.0", h="101.0", l="99.0", c="100.0", vwap="100.0", v="10.0", n=5):
    return [ts, o, h, l, c, vwap, v, n]


def _rows(n, **kwargs):
    return [_row(BASE_TS + i * HOUR, **kwargs) for i in range(n)]


def test_reconcile_series_identical_frames_full_match():
    frame = to_frame(_rows(5))

    report = reconcile_series(frame, frame)

    assert report["overlap_rows"] == 5
    assert report["ohlc_exact_match_rows"] == 5
    assert report["ohlc_match_rate"] == 1.0


def test_reconcile_series_counts_planted_ohlc_diff():
    backfill = to_frame(_rows(5))
    rest_rows = _rows(5)
    rest_rows[2] = _row(BASE_TS + 2 * HOUR, h="999.0")  # planted diff
    rest = to_frame(rest_rows)

    report = reconcile_series(backfill, rest)

    assert report["overlap_rows"] == 5
    assert report["ohlc_exact_match_rows"] == 4
    assert report["ohlc_match_rate"] == pytest.approx(4 / 5)


def test_reconcile_series_reports_vwap_diff_without_raising():
    backfill = to_frame(_rows(5, vwap="100.0"))
    rest = to_frame(_rows(5, vwap="105.0"))  # different vwap reconstruction

    report = reconcile_series(backfill, rest)

    assert report["vwap_mean_abs_rel_diff"] == pytest.approx(5 / 105)
    assert report["ohlc_match_rate"] == 1.0  # OHLC unaffected — no raise on the vwap diff


def test_reconcile_series_disjoint_ts_zero_overlap():
    backfill = to_frame(_rows(3))
    rest = to_frame([_row(BASE_TS + 100 * HOUR + i * HOUR) for i in range(3)])

    report = reconcile_series(backfill, rest)

    assert report["overlap_rows"] == 0


def test_reconcile_dataset_discovers_symbols_and_aggregates_summary(tmp_path):
    frame = to_frame(_rows(5))
    backfill_root = tmp_path / "backfill"
    rest_root = tmp_path / "rest"
    write_parquet(frame, backfill_root / "BTC" / "EUR" / "60.parquet")
    write_parquet(frame, rest_root / "BTC" / "EUR" / "60.parquet")

    report = reconcile_dataset(backfill_root, rest_root, {"60": HOUR})

    assert set(report["series"]) == {"BTC/EUR/60"}
    assert report["series"]["BTC/EUR/60"]["ohlc_match_rate"] == 1.0
    assert report["summary"]["series_count"] == 1


def test_reconcile_dataset_skips_series_absent_from_rest_root(tmp_path):
    frame = to_frame(_rows(5))
    backfill_root = tmp_path / "backfill"
    rest_root = tmp_path / "rest"
    write_parquet(frame, backfill_root / "BTC" / "EUR" / "60.parquet")  # no rest counterpart

    report = reconcile_dataset(backfill_root, rest_root, {"60": HOUR})

    assert report["series"] == {}
    assert report["summary"]["series_count"] == 0


def test_render_markdown_contains_series_table():
    report = {
        "series": {
            "BTC/EUR/60": {
                "overlap_rows": 5,
                "ohlc_exact_match_rows": 5,
                "ohlc_match_rate": 1.0,
                "volume_rel_diff_max": 0.0,
                "vwap_mean_abs_rel_diff": 0.0,
            }
        },
        "summary": {"series_count": 1, "total_overlap_rows": 5, "min_ohlc_match_rate": 1.0},
    }

    md = render_markdown(report)

    assert "BTC/EUR/60" in md
    assert "Series count: 1" in md
