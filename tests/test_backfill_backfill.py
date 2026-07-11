from __future__ import annotations

import json
import zipfile
from pathlib import Path

from cli.backfill.backfill import backfill_basket, backfill_pair

FETCHED_AT = "2026-07-07T00:00:00+00:00"


def _write_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)


def _minute_csv(rows: list[tuple]) -> str:
    return "".join(f"{t},{o},{h},{l},{c},{v},{n}\n" for t, o, h, l, c, v, n in rows)


def _make_source_dir(root: Path) -> Path:
    source_dir = root / "source"
    source_dir.mkdir()
    # 120 one-minute bars = exactly 2 hourly buckets.
    hour_rows = [(i * 60, "100.0", "101.0", "99.0", "100.5", "1.0", 1) for i in range(120)]
    _write_zip(
        source_dir / "Kraken_OHLCVT.zip",
        {
            "master_q4/XBTEUR_1.csv": _minute_csv(hour_rows),
            "master_q4/ETHEUR_1.csv": _minute_csv(hour_rows),
        },
    )
    return source_dir


def test_backfill_pair_returns_frame_per_interval(tmp_path):
    source_dir = _make_source_dir(tmp_path)

    frames = backfill_pair(source_dir, "BTC/EUR", ["60"])

    assert set(frames) == {"60"}
    assert frames["60"].height == 2


def test_backfill_pair_15m_interval_returns_900s_spaced_frame(tmp_path):
    source_dir = _make_source_dir(tmp_path)

    frames = backfill_pair(source_dir, "BTC/EUR", ["15"])

    assert set(frames) == {"15"}
    frame = frames["15"]
    assert frame.height == 8  # 120 one-minute bars = exactly 8 fifteen-minute buckets
    deltas = (frame["ts"] - frame["ts"].shift(1)).dt.total_seconds().drop_nulls()
    assert deltas.to_list() == [900] * 7


def test_backfill_basket_writes_tree_and_returns_manifest(tmp_path):
    source_dir = _make_source_dir(tmp_path)
    out_root = tmp_path / "out"

    manifest = backfill_basket(source_dir, ["BTC/EUR", "ETH/EUR"], ["60"], out_root, FETCHED_AT)

    assert manifest["fetched_at"] == FETCHED_AT
    assert (out_root / "BTC" / "EUR" / "60.parquet").exists()
    assert (out_root / "ETH" / "EUR" / "60.parquet").exists()
    assert manifest["series"]["BTC/EUR"]["60"]["rows"] == 2
    assert len(manifest["series"]["BTC/EUR"]["60"]["sha256"]) == 64
    assert len(manifest["basket_sha256"]) == 64

    manifest_path = out_root / "manifest.json"
    assert manifest_path.exists()
    assert json.loads(manifest_path.read_text()) == manifest


def test_backfill_basket_deterministic_given_fixed_fetched_at(tmp_path_factory):
    source_dir = _make_source_dir(tmp_path_factory.mktemp("source"))

    manifest_a = backfill_basket(source_dir, ["BTC/EUR"], ["60"], tmp_path_factory.mktemp("a"), FETCHED_AT)
    manifest_b = backfill_basket(source_dir, ["BTC/EUR"], ["60"], tmp_path_factory.mktemp("b"), FETCHED_AT)

    assert manifest_a == manifest_b
