from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

from cli.backfill.aggregate import aggregate_minutes
from cli.backfill.substrate15m import build_15m_substrate, qa_15m, reconcile_15m_vs_ticks, seam_15m_to_1h
from cli.ohlc.dataset import to_frame, write_parquet

FETCHED_AT = "2026-07-11T00:00:00+00:00"
BASE_TS = 1767225600  # 2026-01-01T00:00:00Z — midnight UTC, so hour- and 900s-grid-aligned


def _dt(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


def _write_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _minute_csv(rows: list[tuple]) -> str:
    return "".join(f"{t},{o},{h},{l},{c},{v},{n}\n" for t, o, h, l, c, v, n in rows)


def _make_source_dir(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()
    # 120 one-minute bars = exactly 8 fifteen-minute buckets.
    rows = [(BASE_TS + i * 60, "100.0", "101.0", "99.0", "100.5", "1.0", 1) for i in range(120)]
    _write_zip(source_dir / "Kraken_OHLCVT.zip", {"master_q4/XBTEUR_1.csv": _minute_csv(rows)})
    return source_dir


def test_build_15m_substrate_writes_15m_parquet_and_manifest(tmp_path):
    source_dir = _make_source_dir(tmp_path)
    out_root = tmp_path / "ohlc-15m"

    manifest = build_15m_substrate(source_dir, ["BTC/EUR"], out_root, fetched_at=FETCHED_AT)

    assert (out_root / "BTC" / "EUR" / "15.parquet").exists()
    assert (out_root / "manifest.json").exists()
    # Contract shape (spec 00099): `build_15m_substrate` delegates to `backfill_basket`, so it
    # inherits the shape -- series keyed by the path relative to the dataset root, the wall clock
    # quarantined in provenance, one digest name.
    assert manifest["written_at"] == FETCHED_AT
    assert manifest["provenance"]["fetched_at"] == FETCHED_AT
    entry = manifest["series"]["BTC/EUR/15.parquet"]
    assert entry["rows"] == 8
    assert entry["first_ts"] == _dt(BASE_TS).isoformat()
    assert len(entry["sha256"]) == 64
    assert len(manifest["set_sha256"]) == 64


def _write_15m_parquet(out_root: Path, symbol: str, rows_15m: list[list]) -> None:
    base, quote = symbol.split("/")
    write_parquet(to_frame(rows_15m), out_root / base / quote / "15.parquet")


def test_qa_15m_reports_rows_gaps_and_density(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    # Buckets 0, 1, 3 — bucket 2 missing: one gap of one candle, density 3/4.
    rows = [[BASE_TS + k * 900, 100.0, 101.0, 99.0, 100.5, 100.5, 1.0, 1] for k in (0, 1, 3)]
    _write_15m_parquet(out_root, "BTC/EUR", rows)

    report = qa_15m(out_root, ["BTC/EUR"])

    entry = report["BTC/EUR"]
    assert entry["rows"] == 3
    assert entry["first_ts"] == _dt(BASE_TS)
    assert entry["last_ts"] == _dt(BASE_TS + 3 * 900)
    assert entry["gap_count"] == 1
    assert entry["largest_gap_missing"] == 1
    assert entry["density_by_year"] == {2026: 75.0}


def test_qa_15m_density_splits_calendar_years(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    # One bar each side of the 2025→2026 boundary: both years fully dense over their in-span slice.
    rows = [[BASE_TS - 900, 100.0, 101.0, 99.0, 100.5, 100.5, 1.0, 1], [BASE_TS, 100.0, 101.0, 99.0, 100.5, 100.5, 1.0, 1]]
    _write_15m_parquet(out_root, "BTC/EUR", rows)

    report = qa_15m(out_root, ["BTC/EUR"])

    assert report["BTC/EUR"]["density_by_year"] == {2025: 100.0, 2026: 100.0}


def _ticks_csv(rows: list[tuple]) -> str:
    # Quarterly trades layout: Price,Volume,Timestamp,Type.
    return "".join(f"{price},{volume},{ts},{side}\n" for price, volume, ts, side in rows)


def _make_tick_zip(root: Path) -> Path:
    tick_zip = root / "Kraken_Trading_History_Q1.zip"
    ticks = [
        # Bucket BASE_TS: open=100, high=102, low=99, close=99, volume=4.
        ("100.0", "1.0", BASE_TS + 10, "b"),
        ("102.0", "2.0", BASE_TS + 400, "s"),
        ("99.0", "1.0", BASE_TS + 800, "b"),
        # Bucket BASE_TS+900: open=99.5, high=101, low=99.5, close=101, volume=2.
        ("99.5", "1.5", BASE_TS + 910, "s"),
        ("101.0", "0.5", BASE_TS + 1700, "b"),
        # Bucket BASE_TS+1800 — outside the reconcile window; would mismatch wildly if included.
        ("5000.0", "1.0", BASE_TS + 1805, "b"),
    ]
    _write_zip(tick_zip, {"XBTEUR.csv": _ticks_csv(ticks)})
    return tick_zip


def _canonical_15m_rows() -> list[list]:
    return [
        [BASE_TS, 100.0, 102.0, 99.0, 99.0, 100.0, 4.0, 3],
        [BASE_TS + 900, 99.5, 101.0, 99.5, 101.0, 100.0, 2.0, 2],
    ]


def test_reconcile_15m_vs_ticks_full_match_and_coverage(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    _write_15m_parquet(out_root, "BTC/EUR", _canonical_15m_rows())
    tick_zip = _make_tick_zip(tmp_path)

    report = reconcile_15m_vs_ticks(out_root, tick_zip, {"BTC/EUR": "XBTEUR.csv"}, (_dt(BASE_TS), _dt(BASE_TS + 1800)))

    entry = report["BTC/EUR"]
    assert entry["tol"] == 1e-2  # the T0004 acceptance band: "within 1 %"
    assert entry["n_intervals"] == 2
    assert entry["pct_within_tol"] == 100.0
    assert entry["canonical_bars_in_window"] == 2
    assert entry["coverage_pct"] == 100.0
    assert entry["worst_mismatches"] == []


def test_reconcile_15m_vs_ticks_planted_mismatch_caught(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    rows = _canonical_15m_rows()
    rows[1][2] = 999.0  # planted high, far beyond the 1 % band
    _write_15m_parquet(out_root, "BTC/EUR", rows)
    tick_zip = _make_tick_zip(tmp_path)

    report = reconcile_15m_vs_ticks(out_root, tick_zip, {"BTC/EUR": "XBTEUR.csv"}, (_dt(BASE_TS), _dt(BASE_TS + 1800)))

    entry = report["BTC/EUR"]
    assert entry["n_intervals"] == 2
    assert entry["pct_within_tol"] == 50.0
    assert entry["worst_mismatches"][0]["field"] == "high"


def _seam_fixture(out_root: Path, canonical_root: Path, *, n_minutes: int = 180) -> list[list]:
    """Write a 15m parquet + canonical 60 parquet derived from the same synthetic minute rows.

    Volumes are multiples of 0.25 (exactly representable), so float sums agree bit-for-bit
    regardless of summation grouping and the seam's exact-volume check is deterministic.
    """
    rows_1m = []
    for i in range(n_minutes):
        price = 100.0 + (i % 7) * 0.5
        rows_1m.append([BASE_TS + i * 60, price, price + 0.25, price - 0.25, price + 0.125, 0.25 * (i % 4 + 1), 1])
    base, quote = "BTC", "EUR"
    write_parquet(to_frame(aggregate_minutes(rows_1m, 900)), out_root / base / quote / "15.parquet")
    write_parquet(to_frame(aggregate_minutes(rows_1m, 3600)), canonical_root / base / quote / "60.parquet")
    return rows_1m


def test_seam_15m_to_1h_reproduces_canonical_hourly_in_window(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    canonical_root = tmp_path / "ohlc-full"
    _seam_fixture(out_root, canonical_root)  # 3 hours of data; the window keeps 2

    report = seam_15m_to_1h(out_root, canonical_root, ["BTC/EUR"], (_dt(BASE_TS), _dt(BASE_TS + 7200)))

    entry = report["BTC/EUR"]
    assert entry["n_hours_15m"] == 2
    assert entry["n_hours_canonical"] == 2
    assert entry["n_joined"] == 2
    assert entry["n_matched"] == 2
    assert entry["n_price_mismatch"] == 0
    assert entry["n_volume_mismatch"] == 0
    assert entry["n_volume_bitexact"] == 2
    assert entry["n_count_mismatch"] == 0
    assert entry["max_volume_rel_diff"] == 0.0
    assert entry["all_match"] is True


def test_seam_15m_to_1h_flags_price_and_volume_mismatches(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    canonical_root = tmp_path / "ohlc-full"
    rows_1m = _seam_fixture(out_root, canonical_root)
    corrupted = aggregate_minutes(rows_1m, 3600)
    corrupted[0][6] += 0.5  # volume off on hour 0 — rel diff ~1e-2, far beyond the 2-ULP band
    corrupted[1][2] = 999.0  # high off on hour 1
    write_parquet(to_frame(corrupted), canonical_root / "BTC" / "EUR" / "60.parquet")

    report = seam_15m_to_1h(out_root, canonical_root, ["BTC/EUR"], (_dt(BASE_TS), _dt(BASE_TS + 7200)))

    entry = report["BTC/EUR"]
    assert entry["n_joined"] == 2
    assert entry["n_matched"] == 0
    assert entry["n_price_mismatch"] == 1
    assert entry["n_volume_mismatch"] == 1
    assert entry["n_volume_bitexact"] == 1  # only the uncorrupted hour is still bit-identical
    assert entry["n_count_mismatch"] == 0
    assert entry["max_volume_rel_diff"] > 5e-16
    assert entry["all_match"] is False


def test_seam_15m_to_1h_flags_count_mismatch(tmp_path):
    out_root = tmp_path / "ohlc-15m"
    canonical_root = tmp_path / "ohlc-full"
    rows_1m = _seam_fixture(out_root, canonical_root)
    corrupted = aggregate_minutes(rows_1m, 3600)
    corrupted[1][7] += 1  # trade count off by one on hour 1 — a minute-set identity break
    write_parquet(to_frame(corrupted), canonical_root / "BTC" / "EUR" / "60.parquet")

    report = seam_15m_to_1h(out_root, canonical_root, ["BTC/EUR"], (_dt(BASE_TS), _dt(BASE_TS + 7200)))

    entry = report["BTC/EUR"]
    assert entry["n_joined"] == 2
    assert entry["n_matched"] == 1
    assert entry["n_price_mismatch"] == 0
    assert entry["n_volume_mismatch"] == 0
    assert entry["n_count_mismatch"] == 1
    assert entry["all_match"] is False
