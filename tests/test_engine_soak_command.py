"""CLI test for `zcrypto engine soak-check` (spec 00058): a short, contiguous 3-cycle synthetic
journal + store with NO canonical dir wired -- exercises the command's plumbing, the NO-VERDICT
gate (short window + canonical absent), the banner, and the atomic --json write, without needing
the heavy real canonical build (that's the data-gated regression coverage in test_engine_soak.py)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.engine.command as command
import cli.engine.soak as soak
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json
from cli.engine.soak import NullSystem, RealizedInternals, SelfTestReport
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
    # canonical absent -> soak_report never builds an internals rebuild either; both new keys are
    # present in the payload shape but carry no analysis, symmetric with the other analysis fields.
    assert "internals" in payload and payload["internals"] is None
    assert "disclosures" in payload and payload["disclosures"] is None


def _mk_fake_null(n: int = 40) -> NullSystem:
    return NullSystem(
        weights=[{"BTC": 1.0}] * n,
        net_live=[0.001] * n,
        multipliers=[1.0] * n,
        day_index=list(range(n)),
        assets=("BTC",),
        reconcile_ok=True,
        n_periods=n,
        governed_net=[0.001] * n,
        cap_breach=[0.0] * n,
        cap_breach_bars=0,
    )


def _patch_canonical_pipeline(
    monkeypatch, *, available: bool = True, reason: str = "", identity_ok: bool = True, cap_consistent: bool = True
) -> None:
    """Stub the canonical-present branch of `soak_report` so a command test can exercise the new
    internals wiring without a real frozen canonical dataset or trial registry: `_canonical_present`
    always True, `build_null`/`self_tests` return canned non-void results, and `realized_internals`
    (which `soak_report` now calls) returns a `RealizedInternals` built from the actual scored
    records it's given, with the caller-controlled `available`/`identity_ok`/`cap_consistent`."""
    monkeypatch.setattr(soak, "_canonical_present", lambda canonical_dir: True)
    monkeypatch.setattr(soak, "build_null", lambda canonical_dir, fee=0.006: _mk_fake_null())
    monkeypatch.setattr(
        soak,
        "self_tests",
        lambda *a, **kw: SelfTestReport(instrument_ok=True, identity_ok=True, reconcile_ok=True, messages=()),
    )

    def _fake_realized_internals(scored_records, latest_record, reader):
        cycle_ts = [r.cycle_ts for r in scored_records]
        return RealizedInternals(
            available=available,
            reason=reason,
            mult_by_cycle=dict.fromkeys(cycle_ts, 1.0),
            breach_by_cycle=dict.fromkeys(cycle_ts, False),
            identity_ok=identity_ok,
            identity_detail="worst |diff|=0.0",
            cap_consistent=cap_consistent,
            cap_detail="completed-bar breach count=0",
        )

    monkeypatch.setattr(soak, "realized_internals", _fake_realized_internals)


def test_soak_check_json_includes_internals_and_disclosures(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)
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
            str(tmp_path / "fake-canonical"),
            "--registry",
            str(tmp_path / "fake-registry.jsonl"),
            "--floor",
            "1",
            "--json",
            str(json_out),
        ],
    )

    out = result.output
    assert result.exit_code == 0, out
    assert not json.loads(json_out.read_text())["void_reasons"]  # non-void: full analysis ran

    payload = json.loads(json_out.read_text())
    assert set(payload["gating_verdicts"]) == {
        "gross",
        "net",
        "active_frac",
        "turnover",
        "hhi",
        "governor_engagement",
        "cap_breach",
    }
    assert payload["internals"] == {
        "available": True,
        "reason": "",
        "identity_ok": True,
        "identity_detail": "worst |diff|=0.0",
        "cap_consistent": True,
        "cap_detail": "completed-bar breach count=0",
        "n_scored_cycles": payload["provenance"]["L"],
    }
    assert isinstance(payload["disclosures"], list) and payload["disclosures"]  # day-granularity note at least


def test_soak_check_void_wiring_for_internals(tmp_path, monkeypatch):
    """The D2/D3-vs-D7 void distinction, wired at the `soak_report` level: `available=True` with
    `identity_ok=False` or `cap_consistent=False` VOIDS the run (the instrument is lying about
    alignment); `available=False` DEGRADES (governor_engagement/cap_breach read "n/a") but never
    voids on its own."""
    _patch_config(monkeypatch, tmp_path)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)
    common_args = [
        "engine",
        "soak-check",
        "--journal-dir",
        str(journal_dir),
        "--store-dir",
        str(store_dir),
        "--canonical-dir",
        str(tmp_path / "fake-canonical"),
        "--registry",
        str(tmp_path / "fake-registry.jsonl"),
        "--floor",
        "1",
    ]

    _patch_canonical_pipeline(monkeypatch, identity_ok=False)
    identity_out = tmp_path / "identity.json"
    result = runner.invoke(app, [*common_args, "--json", str(identity_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(identity_out.read_text())
    assert any("identity mismatch" in r for r in payload["void_reasons"])

    _patch_canonical_pipeline(monkeypatch, cap_consistent=False)
    cap_out = tmp_path / "cap.json"
    result = runner.invoke(app, [*common_args, "--json", str(cap_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(cap_out.read_text())
    assert any("cap-breach inconsistent" in r for r in payload["void_reasons"])

    _patch_canonical_pipeline(monkeypatch, available=False, reason="mocked internals rebuild degrade")
    degraded_out = tmp_path / "degraded.json"
    result = runner.invoke(app, [*common_args, "--json", str(degraded_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(degraded_out.read_text())
    assert not any("identity mismatch" in r or "cap-breach inconsistent" in r for r in payload["void_reasons"])
    assert payload["internals"]["available"] is False
    assert payload["internals"]["reason"] == "mocked internals rebuild degrade"
    assert payload["gating_verdicts"]["governor_engagement"]["verdict"] == "n/a"
    assert payload["gating_verdicts"]["cap_breach"]["verdict"] == "n/a"
    # Fix 4: an unavailable-internals "n/a" nulls its numeric fields (live=0.0 would otherwise be
    # indistinguishable from a genuinely-zero value to a JSON consumer) -- gross stays real, it
    # never degrades.
    for field in ("live", "median", "lo", "hi", "percentile", "effective_n", "width"):
        assert payload["gating_verdicts"]["governor_engagement"][field] is None
        assert payload["gating_verdicts"]["cap_breach"][field] is None
    assert payload["gating_verdicts"]["gross"]["live"] is not None


def test_soak_report_propagates_soak_error_from_realized_internals(tmp_path, monkeypatch):
    # Fix 3: a SoakError from realized_internals (e.g. a scored cycle's T-4h missing from the
    # rebuilt grid) signals a genuine inconsistency and must PROPAGATE out of soak_report rather
    # than being caught into the D7 degrade path -- correct by construction today (the call sits
    # outside any try in soak_report), but pin it so a future refactor that wraps it in a broad
    # except is caught.
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch)

    def _raise(scored_records, latest_record, reader):
        raise soak.SoakError("cycle boom: T - 4h not found in the rebuilt h4 grid")

    monkeypatch.setattr(soak, "realized_internals", _raise)

    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)

    with pytest.raises(soak.SoakError):
        soak.soak_report(
            journal_dir=journal_dir,
            store_dir=store_dir,
            canonical_dir=tmp_path / "fake-canonical",
            registry_path=tmp_path / "fake-registry.jsonl",
            floor=1,
        )
