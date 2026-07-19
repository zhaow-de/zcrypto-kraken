"""CLI test for `zcrypto engine soak-check` (spec 00058): a short, contiguous 3-cycle synthetic
journal + store with NO canonical dir wired -- exercises the command's plumbing, the NO-VERDICT
gate (short window + canonical absent), the banner, and the atomic --json write, without needing
the heavy real canonical build (that's the data-gated regression coverage in test_engine_soak.py)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json
from cli.ohlc.dataset import to_frame, write_parquet

runner = CliRunner()


def _patch_config(monkeypatch, tmp_path: Path) -> EngineConfig:
    cfg = AppConfig(
        data_dir=None,
        nfs_mount_dir=Path("/mnt/zhao-crypto"),
        fetch=FetchConfig(),
        engine=EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal"),
        data=DataConfig(),
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    return cfg.engine


def _row(ts, close):  # Kraken 8-field OHLC shape (see tests/test_engine_store.py)
    return [int(ts.timestamp()), str(close), str(close), str(close), str(close), str(close), "1.0", 1]


def _mk_journal_and_store(tmp_path: Path, closes_by_label: dict) -> tuple[Path, Path]:
    """3 contiguous cycles at 00:00, 04:00, 08:00 on 2026-07-16 (single asset BTC, final_targets
    BTC=1.0), journaled as real cycle-*.json files under `<journal_dir>/<day>/`, plus a matching
    BTC 240 store parquet built from closes_by_label. Mirrors tests/test_engine_soak.py's
    `_mk_records_and_store`, but writes to disk instead of returning in-memory CycleRecords, since
    the command reads the journal via `_journal_artifacts` + `from_json`."""
    asset = "BTC"
    labels = sorted(closes_by_label)
    rows = [_row(ts, closes_by_label[ts]) for ts in labels]
    store_dir = tmp_path / "store"
    (store_dir / asset / "EUR").mkdir(parents=True)
    write_parquet(to_frame(rows), store_dir / asset / "EUR" / "240.parquet")

    journal_dir = tmp_path / "journal"
    base = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    for k in range(3):
        cycle_ts = base + timedelta(hours=4 * k)
        last_ts = cycle_ts - timedelta(hours=4)
        upto = [t for t in labels if t <= last_ts]
        h4 = SnapshotEntry(
            pair=asset,
            grid="240",
            n_bars=len(upto),
            first_ts=upto[0],
            last_ts=last_ts,
            content_hash=snapshot_content_hash(upto, [closes_by_label[t] for t in upto]),
            path="p240",
        )
        record = CycleRecord(
            schema_version=1,
            cycle_ts=cycle_ts,
            snapshots=(h4,),
            final_targets={asset: 1.0},
            started_at=cycle_ts,
            completed_at=cycle_ts + timedelta(minutes=1),
            code_version="test",
            builder_path="fast",
        )
        day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"cycle-{cycle_ts:%H}.json").write_text(to_json(record) + "\n")

    return journal_dir, store_dir


def test_soak_check_no_canonical_short_window_is_no_verdict(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)
    empty_canonical = tmp_path / "no-canonical"
    json_out = tmp_path / "report.json"

    result = runner.invoke(
        app,
        [
            "engine",
            "soak-check",
            "--journal-dir",
            str(journal_dir),
            "--store-dir",
            str(store_dir),
            "--canonical-dir",
            str(empty_canonical),
            "--json",
            str(json_out),
        ],
    )

    out = result.output
    assert result.exit_code == 0, out
    assert "ZERO out-of-time holdout" in out  # banner on every run
    assert "NO VERDICT" in out.upper()  # L=2 < floor=30 AND canonical absent

    payload = json.loads(json_out.read_text())
    assert payload["void_reasons"]  # non-empty: at least the two reasons above
    assert any("canonical absent" in r for r in payload["void_reasons"])
    assert any("floor" in r for r in payload["void_reasons"])
    assert payload["provenance"]["L"] < 30
    assert payload["self_test"] is None  # canonical absent -> self-tests never ran
    assert payload["gating_verdicts"] is None  # void -> no per-metric conclusion in the payload either
