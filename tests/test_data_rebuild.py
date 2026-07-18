"""Tests for `cli.data.rebuild` (spec 00056 D3): the sibling-minting rebuild orchestration. The
builders are monkeypatched into `rebuild.REBUILDABLE` so these tests stay hermetic."""

import json
from pathlib import Path

import polars as pl
import pytest

from cli.data import rebuild
from cli.data.errors import DataSyncError

_FIXTURES = Path(__file__).parent / "fixtures"
_ASSETPAIRS = json.loads((_FIXTURES / "kraken_assetpairs.json").read_text())
_ASSETS = json.loads((_FIXTURES / "kraken_assets.json").read_text())


def _fake_fetch_public(endpoint: str) -> dict:
    return _ASSETPAIRS if endpoint == "AssetPairs" else _ASSETS


def _write_daily(path: Path, *, vwap: float, volume: float, n: int = 30) -> None:
    frame = pl.DataFrame(
        {
            "ts": list(range(n)),
            "open": [vwap] * n,
            "high": [vwap] * n,
            "low": [vwap] * n,
            "close": [vwap] * n,
            "vwap": [vwap] * n,
            "volume": [volume] * n,
            "count": [1] * n,
        }
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def test_rebuild_mints_sibling_and_dispatches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: calls.append(out) or (out / "ok").write_text("x"))
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    minted = rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert minted == [tmp_path / "ohlc-full-20260718"] == calls
    assert (tmp_path / "ohlc-full-20260718/ok").exists()


def test_rebuild_refuses_existing_sibling(tmp_path, monkeypatch):
    (tmp_path / "ohlc-full-20260718").mkdir()
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    with pytest.raises(DataSyncError, match="already exists"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)


def test_rebuild_never_touches_live_dir(tmp_path, monkeypatch):
    live = tmp_path / "ohlc-full"
    live.mkdir()
    (live / "keep.parquet").write_bytes(b"K")
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "new").write_text("x"))
    rebuild.rebuild_sets(["ohlc-full"], rebuild.RebuildContext(tmp_path, tmp_path, "20260718"))
    assert sorted(p.name for p in live.iterdir()) == ["keep.parquet"]


def test_rebuild_unknown_set_raises(tmp_path):
    with pytest.raises(DataSyncError, match="unknown"):
        rebuild.rebuild_sets(["ohlc"], rebuild.RebuildContext(tmp_path, None, "20260718"))


def test_refresh_snapshots_writes_timestamped_kraken_refdata_json(tmp_path, monkeypatch):
    # Matches the live set's filename convention (kraken-refdata-<UTC stamp>.json) and the
    # canonical build_snapshot payload shape -- not an ad-hoc dict (spec D3).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "snapshots-20260718"
    out_root.mkdir()

    rebuild._refresh_snapshots(ctx, out_root)

    files = list(out_root.glob("kraken-refdata-*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text())
    assert set(payload) == {"fetched_at", "raw", "raw_sha256", "symbols", "universe"}
    assert payload["symbols"] == ["BTC/EUR", "ETH/BTC"]


def test_refresh_universe_writes_point_in_time_universe_json(tmp_path, monkeypatch):
    # Matches the live set's filename (point-in-time-universe.json, the sole file
    # cli/capture/command.py's _default_pairs reads) and the canonical build_universe_file
    # payload shape, incl. the "selected" key -- not an ad-hoc dict (spec D3).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0)
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0)
    (ohlc_root / "manifest.json").write_text(json.dumps({"basket_sha256": "deadbeef"}))

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    assert set(payload) == {"as_of", "entries", "escalate", "params", "provenance", "selected", "spread_cap"}
    assert payload["selected"] == ["BTC/EUR", "ETH/BTC"]
    assert payload["provenance"]["ohlc_dataset_hash"] == "deadbeef"
    assert len(payload["provenance"]["snapshot_sha256"]) == 64


def test_refresh_universe_requires_live_ohlc_full(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")

    with pytest.raises(DataSyncError, match="ohlc-full"):
        rebuild._refresh_universe(ctx, tmp_path / "universe-20260718")
