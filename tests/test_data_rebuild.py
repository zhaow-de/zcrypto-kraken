"""Tests for `cli.data.rebuild` (spec 00056 D3): the sibling-minting rebuild orchestration. The
builders are monkeypatched into `rebuild.REBUILDABLE` so these tests stay hermetic."""

import json
from pathlib import Path

import polars as pl
import pytest

from cli.costs.spread import effective_spread_bps
from cli.data import rebuild
from cli.data.errors import DataSyncError
from cli.universe.rules import DEFAULT_MAX_SPREAD_BPS, SPREAD_REFERENCE_NOTIONAL_EUR

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


def test_rebuild_cleans_up_empty_sibling_on_builder_failure(tmp_path, monkeypatch):
    # A builder that raises must not orphan an empty sibling — else the per-day stamp blocks retry.
    def _boom(ctx, out):
        raise RuntimeError("network down")

    monkeypatch.setitem(rebuild.REBUILDABLE, "snapshots", _boom)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    with pytest.raises(RuntimeError, match="network down"):
        rebuild.rebuild_sets(["snapshots"], ctx)
    assert not (tmp_path / "snapshots-20260718").exists()  # retryable same day


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


def test_refresh_universe_actually_applies_the_spread_cap(tmp_path, monkeypatch):
    # The production path is the whole point of the criterion: wiring it in `_refresh_universe` is
    # what makes the cap real, so reverting that call to `finalize_universe(pairs, volumes)` must
    # turn this test red. Asserting only the `spread_cap` record would NOT -- that record is built
    # separately from the map that does the screening, so the two can drift silently (T0024 review).
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR", "ETH/BTC"))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)

    ohlc_root = tmp_path / "ohlc-full"
    _write_daily(ohlc_root / "BTC" / "EUR" / "1440.parquet", vwap=50_000.0, volume=1_000.0)
    _write_daily(ohlc_root / "ETH" / "BTC" / "1440.parquet", vwap=0.05, volume=1_000.0)

    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")
    out_root = tmp_path / "universe-20260718"
    out_root.mkdir()

    rebuild._refresh_universe(ctx, out_root)

    payload = json.loads((out_root / "point-in-time-universe.json").read_text())
    entries = {e["symbol"]: e["spread_bps"] for e in payload["entries"]}
    # The EUR leg carries the calibrated number at the reference notional -- not None, not 0.0.
    expected = round(effective_spread_bps("BTC", SPREAD_REFERENCE_NOTIONAL_EUR), 3)
    assert entries["BTC/EUR"] == expected
    # The BTC-quoted leg has no capture, so it is recorded unevaluated rather than auto-failed (D3).
    assert entries["ETH/BTC"] is None
    assert payload["spread_cap"]["max_spread_bps"] == DEFAULT_MAX_SPREAD_BPS
    assert payload["spread_cap"]["reference_notional_eur"] == SPREAD_REFERENCE_NOTIONAL_EUR
    assert payload["spread_cap"]["unevaluated_count"] == 1


def test_refresh_universe_requires_live_ohlc_full(tmp_path, monkeypatch):
    monkeypatch.setattr(rebuild, "CANDIDATE_SYMBOLS", ("BTC/EUR",))
    monkeypatch.setattr(rebuild, "fetch_public", _fake_fetch_public)
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=None, stamp="20260718")

    with pytest.raises(DataSyncError, match="ohlc-full"):
        rebuild._refresh_universe(ctx, tmp_path / "universe-20260718")
