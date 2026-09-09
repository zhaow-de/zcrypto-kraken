"""CLI tests for `zcrypto engine soak-check` (spec 00058): a short synthetic journal + store with NO
canonical dir wired, so the command's plumbing runs without the heavy real canonical build."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.engine.command as command
import cli.engine.soak as soak
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.cycle import _MODEL_SYMBOLS
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json
from cli.engine.soak import NullSystem, RealizedInternals, SelfTestReport
from cli.engine.store import GRID_INTERVALS
from cli.ohlc.dataset import to_frame, write_parquet
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

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


def _report_field(out: str, label: str) -> str:
    """The value the rendered report prints against `label`, asserting the label appears exactly once --
    a payload compared against a line that vanished would otherwise fail as a generator's StopIteration."""
    matched = [line for line in out.splitlines() if line.strip().startswith(label)]
    assert len(matched) == 1, f"{label!r} matched {len(matched)} lines in:\n{out}"
    return matched[0].split(":", 1)[1].strip()


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
    assert payload["null_reference"] is None  # canonical absent -> no null, so neither null count is writable
    # The realized count sits at the payload's top level rather than inside `provenance`, which a window
    # the store closed to nothing would omit while the text block still printed the line.
    assert _report_field(out, "realized no-book bars") == f"{payload['realized_no_book_bars']} of {payload['provenance']['L']}"


def _mk_fake_null(n: int = 40, *, reconcile_ok: bool = True) -> NullSystem:
    return NullSystem(
        weights=[{"BTC": 1.0}] * n,
        net_live=[0.001] * n,
        multipliers=[1.0] * n,
        day_index=list(range(n)),
        assets=("BTC",),
        reconcile_ok=reconcile_ok,
        n_periods=n,
        governed_net=[0.001] * n,
        cap_breach=[0.0] * n,
        cap_breach_bars=0,
    )


def _patch_canonical_pipeline(
    monkeypatch,
    *,
    available: bool = True,
    reason: str = "",
    identity_ok: bool | None = True,
    identity_unmeasurable: int = 0,
    cap_consistent: bool = True,
    null_bars: int = 40,
    reconcile_ok: bool = True,
    stub_self_tests: bool = True,
) -> None:
    """Stub the canonical-present branch of `soak_report` so a command test needs no real frozen canonical
    dataset or trial registry: `_canonical_present` always True, `build_null`/`self_tests` canned non-void
    results, `realized_internals` one over the actual scored records. `stub_self_tests=False` runs the REAL
    `self_tests` -- the only way to reach the `reconcile_ok` wiring the stub swallows -- the instrument canned."""
    monkeypatch.setattr(soak, "_canonical_present", lambda canonical_dir: True)
    monkeypatch.setattr(
        soak, "build_null", lambda canonical_dir, fee=0.006, path="fast": _mk_fake_null(null_bars, reconcile_ok=reconcile_ok)
    )
    if stub_self_tests:
        monkeypatch.setattr(
            soak,
            "self_tests",
            lambda *a, **kw: SelfTestReport(instrument_ok=True, identity_ok=True, reconcile_ok=True, messages=()),
        )
    else:
        monkeypatch.setattr(soak, "instrument_self_check", lambda *a, **kw: (True, "stubbed instrument check"))

    def _fake_realized_internals(scored_records, latest_record, reader):
        cycle_ts = [r.cycle_ts for r in scored_records]
        return RealizedInternals(
            available=available,
            reason=reason,
            mult_by_cycle=dict.fromkeys(cycle_ts, 1.0),
            breach_by_cycle=dict.fromkeys(cycle_ts, False),
            identity_ok=identity_ok,
            identity_unmeasurable=identity_unmeasurable,
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
        "identity_unmeasurable": 0,
        "identity_detail": "worst |diff|=0.0",
        "cap_consistent": True,
        "cap_detail": "completed-bar breach count=0",
        "n_scored_cycles": payload["provenance"]["L"],
    }
    assert isinstance(payload["disclosures"], list) and payload["disclosures"]  # day-granularity note at least
    # Both faces read the same two numbers off one helper, so equality here is by construction, not by
    # two computations happening to agree. `_mk_fake_null` builds no span, which is the stamps-absent arm.
    null_reference = payload["null_reference"]
    assert null_reference["first_bar"] is None and null_reference["last_bar"] is None
    assert _report_field(out, "retained bars") == str(null_reference["retained_bars"]) == "40"
    assert _report_field(out, "no-book bars") == f"{null_reference['no_book_bars']} of 40"


def test_soak_check_void_wiring_for_internals(tmp_path, monkeypatch):
    """The D2/D3-vs-D7 void distinction, wired at `soak_report`: `available=True` with
    `identity_ok=False` or `cap_consistent=False` VOIDS (the instrument is lying about alignment);
    `identity_ok=None` (unmeasured) does not, `available=False` DEGRADES but never voids alone --
    and `identity_unmeasurable` picks which void-reason string names the failure (spec 00113 D6)."""
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

    # A journaled value that is not a number and a rebuild that disagrees by magnitude are different
    # operator actions, so they take different reasons. The branch sees only the count, which is how
    # it names the unmeasurable case when both hold (spec 00113 D6).
    _patch_canonical_pipeline(monkeypatch, identity_ok=False, identity_unmeasurable=1)
    unmeasurable_out = tmp_path / "identity-unmeasurable.json"
    result = runner.invoke(app, [*common_args, "--json", str(unmeasurable_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(unmeasurable_out.read_text())
    assert any("identity unmeasurable" in r for r in payload["void_reasons"])
    assert not any("identity mismatch" in r for r in payload["void_reasons"])
    assert payload["internals"]["identity_unmeasurable"] == 1
    # The text report renders `void_reasons` and never `identity_detail`, so the reason it picks
    # carries the detail (spec 00113 D6) -- read off the payload, and non-empty, or `in` is vacuous.
    detail = payload["internals"]["identity_detail"]
    assert detail and any(detail in r for r in payload["void_reasons"])

    # `identity_ok=None` is the identity UNMEASURED -- no journaled target was compared against the
    # rebuild. Only a ran-and-failed proof voids, so this one must not, while `cap_consistent=False`
    # below still does from the same available rebuild.
    _patch_canonical_pipeline(monkeypatch, identity_ok=None)
    unmeasured_out = tmp_path / "identity-unmeasured.json"
    result = runner.invoke(app, [*common_args, "--json", str(unmeasured_out)])
    assert result.exit_code == 0, result.output
    payload = json.loads(unmeasured_out.read_text())
    assert payload["internals"]["identity_ok"] is None
    assert not any("identity mismatch" in r for r in payload["void_reasons"])

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
    # An unavailable-internals "n/a" nulls its numeric fields (live=0.0 would otherwise be
    # indistinguishable from a genuinely-zero value to a JSON consumer) -- gross stays real, it
    # never degrades.
    for field in ("live", "median", "lo", "hi", "percentile", "effective_n", "width"):
        assert payload["gating_verdicts"]["governor_engagement"][field] is None
        assert payload["gating_verdicts"]["cap_breach"][field] is None
    assert payload["gating_verdicts"]["gross"]["live"] is not None


def _soak_args(journal_dir, store_dir, canonical_dir, json_out) -> list[str]:
    return [
        "engine",
        "soak-check",
        "--journal-dir",
        str(journal_dir),
        "--store-dir",
        str(store_dir),
        "--canonical-dir",
        str(canonical_dir),
        "--registry",
        str(canonical_dir.parent / "fake-registry.jsonl"),
        "--floor",
        "1",
        "--json",
        str(json_out),
    ]


_CLOSES = {
    datetime(2026, 7, 15, 20, 0, tzinfo=UTC): 100.0,
    datetime(2026, 7, 16, 0, 0, tzinfo=UTC): 110.0,
    datetime(2026, 7, 16, 4, 0, tzinfo=UTC): 121.0,
    datetime(2026, 7, 16, 8, 0, tzinfo=UTC): 133.1,
}


def test_soak_check_exits_non_zero_when_the_null_reconciliation_fails(tmp_path, monkeypatch):
    """A `reconcile_ok=False` null is a BROKEN CODE CONTRACT, not a data finding: the run prints its
    window, its self-tests and its record-47 comparison, then exits 1. No other test takes that branch."""
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch, reconcile_ok=False, stub_self_tests=False)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, tmp_path / "fake-canonical", json_out))

    out = result.output
    assert result.exit_code == 1, out
    assert "REALIZED-SERIES WINDOW" in out
    assert "self-tests VOID" in out
    reasons = json.loads(json_out.read_text())["void_reasons"]
    assert any("reconcile_ok=False" in r for r in reasons), reasons
    # The one string that DESCRIBES the flag names both identities it now ANDs; naming the live-cost
    # reconstruction alone would send a reader debugging the wrong one of the two.
    assert any("cap-breach count" in r and "live-cost reconstruction" in r for r in reasons), reasons


def test_soak_check_voids_when_the_null_cannot_discriminate(tmp_path, monkeypatch):
    """A null too short to discriminate is a void reason, not a full page of "n/a" over an empty
    `void_reasons`. At this fixture's L=2 over one realized day every gating arm is under the cutoff
    at 2 retained bars -- the governor arm is the binding one, its numerator the null's distinct-day count."""
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch, null_bars=2)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, tmp_path / "fake-canonical", json_out))

    out = result.output
    assert result.exit_code == 0, out  # a reference too short to judge against is a data state
    assert "NO VERDICT" in out
    payload = json.loads(json_out.read_text())
    assert any("null retains 2 bars" in r and "L=2" in r for r in payload["void_reasons"]), payload["void_reasons"]


def test_soak_check_short_null_reason_does_not_fire_on_an_empty_realized_window(tmp_path, monkeypatch):
    """The `L > 0` arm, on a store that closed the realized window to nothing: every `effective_n` is 0.0
    there for the REALIZED side's reason, so without the arm a healthy 40-bar null is blamed for it."""
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, {d - timedelta(hours=8): 100.0, d - timedelta(hours=4): 105.0})
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, tmp_path / "fake-canonical", json_out))

    assert result.exit_code == 0, result.output
    reasons = json.loads(json_out.read_text())["void_reasons"]
    assert any("L=0 < floor" in r for r in reasons), reasons  # the fixture really did close the window
    assert not any("null retains" in r for r in reasons), reasons


def test_soak_report_degrades_when_the_canonical_is_missing_a_leg(tmp_path, monkeypatch):
    """State (a): a canonical carrying only the leg `_canonical_present` probes. Nothing is stubbed, so
    the real `_load_canonical` probe runs -- without it the run dies on a `FileNotFoundError` out of
    `read_store_series`, which is neither a SoakError nor an EngineError and reaches no handler at all."""
    _patch_config(monkeypatch, tmp_path)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    canonical = tmp_path / "canonical"
    (canonical / "BTC" / "EUR").mkdir(parents=True)
    (canonical / "BTC" / "EUR" / "240.parquet").touch()
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, canonical, json_out))

    out = result.output
    assert result.exit_code == 0, out
    assert "REALIZED-SERIES WINDOW" in out
    reasons = json.loads(json_out.read_text())["void_reasons"]
    # The missing legs by NAME -- the absent-canonical reason names none, which is what tells the two
    # states apart -- and by COORDINATE, the whole product minus the file present: naming one entry
    # leaves either loop narrowed to a single element green, and a probe blind to `.exists()` names
    # the present file too.
    reason = next(r for r in reasons if r.startswith("null unavailable: "))
    expected = {
        f"{symbol}@{interval}" for symbol in _MODEL_SYMBOLS for interval in GRID_INTERVALS if (symbol, interval) != ("BTC/EUR", 240)
    }
    assert all(leg in reason for leg in expected), sorted(leg for leg in expected if leg not in reason)
    assert "BTC/EUR@240" not in reason, reason


def test_soak_report_degrades_when_the_null_refuses(tmp_path, monkeypatch):
    """The wiring, against a stub: whatever `build_null` refuses on, the run keeps its window block and
    its self-tests block and exits 0 -- the degrade path leaves `self_test` None, so exit 1 never fires."""
    _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(soak, "_canonical_present", lambda canonical_dir: True)

    def _refuse(canonical_dir, fee=0.006, path="fast"):
        raise soak.SoakError("basket never complete: no index prices all of ['XRP']")

    monkeypatch.setattr(soak, "build_null", _refuse)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, tmp_path / "fake-canonical", json_out))

    out = result.output
    assert result.exit_code == 0, out
    assert "REALIZED-SERIES WINDOW" in out and "SELF-TESTS" in out
    reasons = json.loads(json_out.read_text())["void_reasons"]
    assert any(r.startswith("null unavailable: ") for r in reasons), reasons


def _daily_dead_leg_panels(dead: str = "XRP", *, n_daily: int = 60, n_h4: int = 360):
    """What a leg loads as when the forming-bar drop takes its only daily row: unpriced on the DAILY
    grid alone, finite from index 0 on h4 like every other leg. A panel dead on BOTH grids would refuse
    through the h4 call whether the daily one ran or not, so only this shape proves the daily call."""
    assets = CrossfreqSystemConfig().assets
    base = datetime(2026, 1, 1, tzinfo=UTC)
    daily_ts = [base + timedelta(days=i) for i in range(n_daily)]
    h4_ts = [base + timedelta(hours=4 * i) for i in range(n_h4)]
    daily = {a: [100.0 + i for i in range(n_daily)] for a in assets}
    daily[dead] = [None] * n_daily
    h4 = {a: [100.0 + i for i in range(n_h4)] for a in assets}
    return daily, daily_ts, h4, h4_ts


def test_soak_report_degrades_when_a_leg_carries_no_price(tmp_path, monkeypatch):
    """State (b) end to end, on the daily-only shape. Neither builder is stubbed: the daily refusal runs
    BEFORE them, and ordered after -- or with the daily call gone -- the real builder is entered on an
    all-None column and raises a bare `ValueError` that escapes the CLI's `except EngineError` entirely."""
    _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(soak, "_load_canonical", lambda canonical_dir: _daily_dead_leg_panels())
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    canonical = tmp_path / "canonical"
    (canonical / "BTC" / "EUR").mkdir(parents=True)
    (canonical / "BTC" / "EUR" / "240.parquet").touch()
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, canonical, json_out))

    out = result.output
    assert result.exit_code == 0, out
    assert "REALIZED-SERIES WINDOW" in out
    reasons = json.loads(json_out.read_text())["void_reasons"]
    # The refusal NARROWS to the legs absent at every index. Naming the whole basket would contain
    # 'XRP' too, so the priced leg's absence from the text is what tells the two apart.
    assert any("null unavailable" in r and "'XRP'" in r and "'BTC'" not in r for r in reasons), reasons


def test_soak_report_propagates_soak_error_from_realized_internals(tmp_path, monkeypatch):
    # A SoakError from realized_internals (e.g. a scored cycle's T-4h missing from the rebuilt grid)
    # signals a genuine inconsistency and must PROPAGATE out of soak_report rather than being caught
    # into the D7 degrade path.
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


def test_unrecognized_verdict_label_aborts_cleanly_through_the_cli(tmp_path, monkeypatch):
    # reconcile_verdicts raises SoakError on a label outside metric_verdict's closed vocabulary -- a
    # code defect, never a data finding. soak_report guards only realized_series, so the raise
    # reaches the CLI's `except EngineError` and aborts with a one-line message.
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch)

    real_metric_verdict = soak.metric_verdict
    calls = {"n": 0}

    def _poisoned(*args, **kwargs):
        # Corrupt exactly one side of one metric's pair so primary != secondary and one label is
        # off-vocabulary -- the precise condition reconcile_verdicts must refuse to place.
        calls["n"] += 1
        verdict = real_metric_verdict(*args, **kwargs)
        if calls["n"] == 1:
            return replace(verdict, verdict="probably-fine")
        return verdict

    monkeypatch.setattr(soak, "metric_verdict", _poisoned)

    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)

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
            "--null",
            "both",
        ],
    )

    out = result.output
    assert result.exit_code != 0, out
    assert "probably-fine" in out, out
    assert "internal contract violation" in out, out
    # A code defect must never be dressed up as a data finding, nor leak a traceback.
    assert "instrument-fragile" not in out, out
    assert "Traceback" not in out, out


# --- spec 00061: --null / --path CLI wiring -------------------------------------------------------------


def test_soak_check_null_and_path_options_thread_through(tmp_path, monkeypatch):
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
            "--null",
            "windows",
            "--path",
            "verified",
            "--json",
            str(json_out),
        ],
    )

    out = result.output
    assert result.exit_code == 0, out
    assert "null mode: windows" in out.lower()
    assert "builder path: verified" in out.lower()

    payload = json.loads(json_out.read_text())
    assert payload["null_mode"] == "windows"
    assert payload["path"] == "verified"
    assert all(v["dual"] is None for v in payload["gating_verdicts"].values())


def test_soak_check_null_defaults_to_both(tmp_path, monkeypatch):
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

    assert result.exit_code == 0, result.output
    payload = json.loads(json_out.read_text())
    assert payload["null_mode"] == "both"
    assert payload["path"] == "fast"


def test_soak_check_rejects_invalid_null_mode(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)

    result = runner.invoke(
        app,
        [
            "engine",
            "soak-check",
            "--journal-dir",
            str(journal_dir),
            "--store-dir",
            str(store_dir),
            "--null",
            "bogus",
        ],
    )
    assert result.exit_code == 1


def test_soak_check_rejects_invalid_path(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    d = datetime(2026, 7, 16, tzinfo=UTC)
    closes = {
        d - timedelta(hours=4): 100.0,
        d: 110.0,
        d + timedelta(hours=4): 121.0,
        d + timedelta(hours=8): 133.1,
    }
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, closes)

    result = runner.invoke(
        app,
        [
            "engine",
            "soak-check",
            "--journal-dir",
            str(journal_dir),
            "--store-dir",
            str(store_dir),
            "--path",
            "bogus",
        ],
    )
    assert result.exit_code == 1


# --- the mixed-schema window through the CLI (spec 00094 D3) ---------------------------------------


def _mk_straddling_journal_and_store(tmp_path: Path) -> tuple[Path, Path]:
    """5 contiguous cycles from 2026-07-16 00:00 whose journaled records flip from schema 1
    (base-keyed "BTC") to schema 2 (symbol-keyed, with the widened "ETH/BTC" leg at its structural
    zero) at 08:00, plus a store carrying BOTH legs at their real `<base>/<quote>` paths. Mirrors
    tests/test_engine_soak.py's `_mk_straddling_records_and_store`, but written to disk -- the
    command reads the journal via `_journal_artifacts` + `from_json`."""
    base = datetime(2026, 7, 16, 0, 0, tzinfo=UTC)
    labels = [base + timedelta(hours=4 * k) for k in range(-1, 4)]
    prices = {"BTC/EUR": [100.0 * 1.1**i for i in range(len(labels))], "ETH/BTC": [1.0 * 1.4**i for i in range(len(labels))]}

    store_dir = tmp_path / "store"
    for symbol, closes in prices.items():
        b, q = symbol.split("/")
        (store_dir / b / q).mkdir(parents=True, exist_ok=True)
        write_parquet(to_frame([_row(t, c) for t, c in zip(labels, closes)]), store_dir / b / q / "240.parquet")

    journal_dir = tmp_path / "journal"
    for k in range(5):
        cycle_ts = base + timedelta(hours=4 * k)
        last_ts = cycle_ts - timedelta(hours=4)
        upto = [i for i, t in enumerate(labels) if t <= last_ts]
        sub_ts = [labels[i] for i in upto]
        schema = 1 if k < 2 else 2
        snaps = tuple(
            SnapshotEntry(
                pair=pair,
                grid="240",
                n_bars=len(sub_ts),
                first_ts=sub_ts[0],
                last_ts=last_ts,
                content_hash=snapshot_content_hash(sub_ts, [prices["BTC/EUR"][i] for i in upto]),
                path=f"p240-{pair.replace('/', '-')}",
            )
            for pair in (("BTC",) if schema == 1 else ("BTC/EUR", "ETH/BTC"))
        )
        record = CycleRecord(
            schema_version=schema,
            cycle_ts=cycle_ts,
            snapshots=snaps,
            final_targets={"BTC": 0.4} if schema == 1 else {"BTC/EUR": 0.4, "ETH/BTC": 0.0},
            started_at=cycle_ts,
            completed_at=cycle_ts + timedelta(minutes=1),
            code_version="test",
            builder_path="fast",
        )
        day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        (day_dir / f"cycle-{cycle_ts:%H}.json").write_text(to_json(record) + "\n")

    return journal_dir, store_dir


def test_soak_check_spans_the_schema_boundary(tmp_path, monkeypatch):
    """A soak report over a window that straddles the deploy runs to a rendered report instead of
    aborting.

    SCOPE: the canonical is absent here, so this exercises the journal read and `realized_series` --
    the two things that previously raised, `SoakError` on the changing asset set and the store
    path's `ValueError` on a base key."""
    _patch_config(monkeypatch, tmp_path)
    journal_dir, store_dir = _mk_straddling_journal_and_store(tmp_path)
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
            str(tmp_path / "no-canonical"),
            "--json",
            str(json_out),
        ],
    )

    out = result.output
    assert result.exit_code == 0, out
    assert "ZERO out-of-time holdout" in out

    payload = json.loads(json_out.read_text())
    # 4 of the 5 clean cycles scored (the last has no successor) -- the window was not truncated at
    # the schema flip, and no reason mentions the realized series failing to build.
    assert payload["provenance"]["L"] == 4
    assert not any("realized series" in r for r in payload["void_reasons"]), payload["void_reasons"]
    assert any("canonical absent" in r for r in payload["void_reasons"])
