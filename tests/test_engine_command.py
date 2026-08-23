"""CLI tests for the `zcrypto engine` sub-app (spec 00041 SS The CLI): CliRunner over every
subcommand with tmp dirs and monkeypatched seeder/cycle/builder stubs -- no network, no dataset,
no live node. `run`'s fail-fast checks and watchdog are exercised against a stub node + a
synchronous timer; nautilus lazy-import stays a subprocess check at the bottom; the attended soak
is the live smoke."""

import io
import json
import re
import subprocess
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.config import AppConfig, ConfigError, DataConfig, EngineConfig, FetchConfig
from cli.engine import concordance
from cli.engine.cycle import CycleResult
from cli.engine.errors import EngineError
from cli.engine.execgate import GateLevel, GateVerdict
from cli.engine.execledger import append_plan_entry, write_exec_record
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json, validate_record
from cli.engine.store import BASKET, GRID_INTERVALS, SeedEntry, SeedReport, _store_path
from cli.engine.venue import VenueStatus
from cli.ohlc.dataset import write_parquet

runner = CliRunner()

UTC = timezone.utc
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
PAIRS = ("BTC", "ETH")
TARGETS = {"BTC": 0.2, "ETH": 0.05}
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _output(result) -> str:
    # result.output carries stdout + stderr on this click version; strip rich's ANSI styling.
    return _ANSI_RE.sub("", result.output)


def _patch_config(monkeypatch, tmp_path: Path) -> EngineConfig:
    """Point load_config (as cli.engine.command sees it) at tmp-dir engine paths."""
    cfg = AppConfig(
        data_dir=None,
        nfs_mount_dir=Path("/mnt/zhao-crypto"),
        fetch=FetchConfig(),
        engine=EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal"),
        data=DataConfig(),
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    return cfg.engine


def _success_result(cycle_ts: datetime, journal_dir: Path) -> CycleResult:
    return CycleResult(
        status="success",
        cycle_ts=cycle_ts,
        record_path=journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"cycle-{cycle_ts:%H}.json",
        sidecar_path=None,
        targets={"BTC": 0.2, "ETH": 0.0},
        orders=[{"asset": "BTC", "side": "buy", "quantity": 0.001, "notional_eur": 200.0, "price": 200000.0}],
        reason=None,
        offending_pairs=None,
        sleeve_gross={"B": 0.0, "A1": 0.0, "A2": 0.32},
    )


# --- journal fixtures (real, replayable records -- the shapes run_cycle writes) --------------------


def _series(cycle_ts: datetime, interval: int, base: float) -> tuple[list[datetime], list[float]]:
    if interval == 240:
        last, step, n = cycle_ts - timedelta(hours=4), timedelta(hours=4), 6
    else:
        last, step, n = cycle_ts.replace(hour=0) - timedelta(days=1), timedelta(days=1), 4
    ts = [last - (n - 1 - i) * step for i in range(n)]
    return ts, [base + i for i in range(n)]


def _snapshot_frame(ts: list[datetime], closes: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"ts": ts, "close": closes}, schema={"ts": pl.Datetime("us", "UTC"), "close": pl.Float64})


def _write_success_record(journal_dir: Path, cycle_ts: datetime, targets: dict[str, float] = TARGETS) -> Path:
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
    entries = []
    for interval in (1440, 240):
        for i, pair in enumerate(PAIRS):
            ts, closes = _series(cycle_ts, interval, 100.0 * (i + 1))
            rel_path = rel_dir / f"{pair}-{interval}.parquet"
            write_parquet(_snapshot_frame(ts, closes), journal_dir / rel_path)
            entries.append(
                SnapshotEntry(
                    pair=pair,
                    grid=str(interval),
                    n_bars=len(ts),
                    first_ts=ts[0],
                    last_ts=ts[-1],
                    content_hash=snapshot_content_hash(ts, closes),
                    path=rel_path.as_posix(),
                )
            )
    record = CycleRecord(
        schema_version=1,
        cycle_ts=cycle_ts,
        snapshots=tuple(entries),
        final_targets=dict(targets),
        started_at=cycle_ts + timedelta(seconds=95),
        completed_at=cycle_ts + timedelta(minutes=3),
        code_version="test",
        builder_path="fast",
    )
    validate_record(record)
    path = journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"cycle-{cycle_ts:%H}.json"
    path.write_text(to_json(record) + "\n")
    return path


def _write_sidecar(journal_dir: Path, cycle_ts: datetime, *, reason: str = "stale_pair", offending=("DOGE",)) -> Path:
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"failed-cycle-{cycle_ts:%H}.json"
    payload = {
        "cycle_ts": cycle_ts.isoformat(),
        "attempted_at": (cycle_ts + timedelta(seconds=95)).isoformat(),
        "completed_at": (cycle_ts + timedelta(minutes=2)).isoformat(),
        "reason": reason,
        "offending_pairs": list(offending),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return path


def _refusing_verdict() -> GateVerdict:
    return GateVerdict(
        level=GateLevel.NONE,
        reasons=("arm_file_absent", "restart_hold"),
        inputs={"armed_in_config": False, "venue_status": "online"},
    )


def _fake_builder(targets: dict[str, float]):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods)

    return builder


# --- seed ------------------------------------------------------------------------------------------


def test_seed_prints_per_pair_overlap_summary(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    report = SeedReport(
        entries=(
            SeedEntry(pair="BTC", interval=1440, overlap_bars=98, appended=12, replaced_tail_rows=0),
            SeedEntry(pair="BTC", interval=240, overlap_bars=621, appended=77, replaced_tail_rows=3),
        )
    )
    calls = []
    monkeypatch.setattr(command, "seed_store", lambda store_dir, canonical_dir: calls.append((store_dir, canonical_dir)) or report)

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 0, _output(result)
    assert calls == [(engine_cfg.store_dir, Path("data/ohlc-full"))]
    out = _output(result)
    assert "BTC" in out
    assert "1440" in out and "240" in out
    assert "98" in out and "621" in out  # per-pair x grid overlap_bars -- the seam-QA evidence
    assert "12" in out and "77" in out  # appended
    assert "3" in out  # replaced tail rows
    assert "89" in out  # the appended total (12 + 77)


def test_seed_engine_error_is_a_clean_exit_1(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)

    def boom(store_dir, canonical_dir):
        raise EngineError("window shortfall for BTC@240 -- use the quarterly OHLCVT dump")

    monkeypatch.setattr(command, "seed_store", boom)

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 1
    assert "OHLCVT" in _output(result)
    assert isinstance(result.exception, SystemExit)  # clean typer.Exit, not an EngineError traceback


def test_config_error_is_a_clean_exit_1(monkeypatch):
    def bad_config():
        raise ConfigError("zcrypto.toml is not valid TOML: boom")

    monkeypatch.setattr(command, "load_config", bad_config)

    result = runner.invoke(app, ["engine", "seed"])

    assert result.exit_code == 1
    assert "not valid TOML" in _output(result)
    assert isinstance(result.exception, SystemExit)


# --- cycle -----------------------------------------------------------------------------------------


def test_cycle_defaults_to_the_most_recent_boundary(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 10, 9, 23, 45, tzinfo=UTC))
    calls = []

    def fake_run_cycle(cycle_ts, *, config):
        calls.append((cycle_ts, config))
        return _success_result(cycle_ts, config.journal_dir)

    monkeypatch.setattr(command, "run_cycle", fake_run_cycle)

    result = runner.invoke(app, ["engine", "cycle"])

    assert result.exit_code == 0, _output(result)
    assert calls == [(datetime(2026, 7, 10, 8, 0, tzinfo=UTC), engine_cfg)]
    out = _output(result)
    assert "success" in out
    assert "cycle-08.json" in out


def test_cycle_at_runs_the_given_on_grid_boundary(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    calls = []

    def fake_run_cycle(cycle_ts, *, config):
        calls.append(cycle_ts)
        return _success_result(cycle_ts, config.journal_dir)

    monkeypatch.setattr(command, "run_cycle", fake_run_cycle)

    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-09T16:00:00+00:00"])

    assert result.exit_code == 0, _output(result)
    assert calls == [datetime(2026, 7, 9, 16, 0, tzinfo=UTC)]


def test_cycle_at_normalizes_an_aware_non_utc_boundary(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    calls = []

    def fake_run_cycle(cycle_ts, *, config):
        calls.append(cycle_ts)
        return _success_result(cycle_ts, config.journal_dir)

    monkeypatch.setattr(command, "run_cycle", fake_run_cycle)

    # 10:00+02:00 == 08:00 UTC -- exactly on the grid once normalized.
    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-10T10:00:00+02:00"])

    assert result.exit_code == 0, _output(result)
    assert calls == [datetime(2026, 7, 10, 8, 0, tzinfo=UTC)]


@pytest.mark.parametrize(
    ("raw", "needle"),
    [
        ("2026-07-10T09:00:00+00:00", "grid"),  # off the 00/04/08/12/16/20 hour grid
        ("2026-07-10T08:15:00+00:00", "grid"),  # non-zero minutes
        ("2026-07-10T08:00:00", "naive"),  # naive -- the repo convention is aware-UTC
        ("not-a-timestamp", "ISO-8601"),
    ],
)
def test_cycle_at_rejections_never_reach_run_cycle(tmp_path, monkeypatch, raw, needle):
    _patch_config(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(command, "run_cycle", lambda *a, **k: calls.append(1))

    result = runner.invoke(app, ["engine", "cycle", "--at", raw])

    assert result.exit_code == 1
    assert needle in _output(result)
    assert calls == []


@pytest.mark.parametrize("existing", ["cycle-08.json", "failed-cycle-08.json"])
def test_cycle_refuses_an_existing_boundary_artifact_without_replace(tmp_path, monkeypatch, existing):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    day_dir = engine_cfg.journal_dir / "2026-07-10"
    day_dir.mkdir(parents=True)
    (day_dir / existing).write_text("{}")
    calls = []
    monkeypatch.setattr(command, "run_cycle", lambda *a, **k: calls.append(1))

    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-10T08:00:00+00:00"])

    assert result.exit_code == 1
    assert "--replace" in _output(result)
    assert calls == []
    assert (day_dir / existing).exists()  # refused, never clobbered


def test_cycle_replace_deletes_both_artifacts_and_snapshots_before_running(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    day_dir = engine_cfg.journal_dir / "2026-07-10"
    snapshots_dir = day_dir / "snapshots" / "cycle-08"
    snapshots_dir.mkdir(parents=True)
    (snapshots_dir / "BTC-240.parquet").write_text("stale")
    (day_dir / "cycle-08.json").write_text("{}")
    (day_dir / "failed-cycle-08.json").write_text("{}")
    seen = {}

    def fake_run_cycle(cycle_ts, *, config):
        seen["record_gone"] = not (day_dir / "cycle-08.json").exists()
        seen["sidecar_gone"] = not (day_dir / "failed-cycle-08.json").exists()
        seen["snapshots_gone"] = not snapshots_dir.exists()
        return _success_result(cycle_ts, config.journal_dir)

    monkeypatch.setattr(command, "run_cycle", fake_run_cycle)

    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-10T08:00:00+00:00", "--replace"])

    assert result.exit_code == 0, _output(result)
    assert seen == {"record_gone": True, "sidecar_gone": True, "snapshots_gone": True}


def test_cycle_failed_result_prints_the_sidecar_summary_and_exits_nonzero(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    sidecar_path = engine_cfg.journal_dir / "2026-07-10" / "failed-cycle-08.json"

    def fake_run_cycle(cycle_ts, *, config):
        return CycleResult(
            status="failed",
            cycle_ts=cycle_ts,
            record_path=None,
            sidecar_path=sidecar_path,
            targets=None,
            orders=None,
            reason="stale_pair",
            offending_pairs=("DOGE",),
            sleeve_gross=None,
        )

    monkeypatch.setattr(command, "run_cycle", fake_run_cycle)

    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-10T08:00:00+00:00"])

    assert result.exit_code == 1
    out = _output(result)
    assert "failed" in out
    assert "stale_pair" in out
    assert "DOGE" in out
    assert "failed-cycle-08.json" in out


# --- replay ----------------------------------------------------------------------------------------


def test_replay_classifies_ok_hash_mismatch_and_sidecar_without_crashing(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    clean_ts = datetime(2026, 7, 10, 0, 0, tzinfo=UTC)
    corrupt_ts = datetime(2026, 7, 10, 4, 0, tzinfo=UTC)
    sidecar_ts = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
    _write_success_record(journal, clean_ts)
    _write_success_record(journal, corrupt_ts)
    # Corrupt one journaled snapshot: same calendar/metadata, shifted closes -> a pure hash mismatch.
    ts, closes = _series(corrupt_ts, 240, 100.0)
    write_parquet(
        _snapshot_frame(ts, [c + 1.0 for c in closes]),
        journal / "2026-07-10" / "snapshots" / "cycle-04" / "BTC-240.parquet",
    )
    _write_sidecar(journal, sidecar_ts, reason="refresh_deadline", offending=("ETH",))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    result = runner.invoke(app, ["engine", "replay"])

    out = _output(result)
    assert result.exit_code == 1, out  # a mismatch is present
    assert result.exception is None or isinstance(result.exception, SystemExit)  # classified, not crashed
    lines = out.splitlines()
    assert any(clean_ts.isoformat() in line and "ok" in line for line in lines)
    assert any(corrupt_ts.isoformat() in line and "MISMATCH" in line for line in lines)
    assert any(sidecar_ts.isoformat() in line and "failed cycle" in line and "refresh_deadline" in line for line in lines)
    assert "1 ok" in out
    assert "1 mismatch(es)" in out
    assert "0 validation failure(s)" in out
    assert "1 failed cycle(s)" in out


def test_replay_classifies_a_validation_failure(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    record_path = _write_success_record(journal, CYCLE_TS)
    payload = json.loads(record_path.read_text())
    # from_json still parses; replay_cycle's validate_record rejects. 99 is unsupported at ANY
    # schema -- never 2, which 00094 made loadable, so the tamper would be a no-op once the
    # writer emits v2 and this test would stop exercising the rejection path at all.
    payload["schema_version"] = 99
    record_path.write_text(json.dumps(payload))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    result = runner.invoke(app, ["engine", "replay"])

    out = _output(result)
    assert result.exit_code == 1, out
    assert "VALIDATION-FAILED" in out
    assert "1 validation failure(s)" in out


def test_replay_all_clean_exits_zero(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    _write_success_record(engine_cfg.journal_dir, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    result = runner.invoke(app, ["engine", "replay"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "1 ok" in out
    assert "0 mismatch(es)" in out


def test_replay_date_filter_restricts_the_sweep(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    day1_ts = datetime(2026, 7, 9, 12, 0, tzinfo=UTC)
    day2_ts = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
    _write_success_record(engine_cfg.journal_dir, day1_ts)
    _write_success_record(engine_cfg.journal_dir, day2_ts)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    result = runner.invoke(app, ["engine", "replay", "--date", "2026-07-09"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert day1_ts.isoformat() in out
    assert day2_ts.isoformat() not in out
    assert "replayed 1 success record(s)" in out


def test_replay_verified_path_uses_the_verified_builder(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    _write_success_record(engine_cfg.journal_dir, CYCLE_TS)
    fast_calls, verified_calls = [], []

    def _spy(calls, targets):
        inner = _fake_builder(targets)

        def builder(*args, **kwargs):
            calls.append(1)
            return inner(*args, **kwargs)

        return builder

    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _spy(fast_calls, TARGETS))
    monkeypatch.setattr(concordance, "build_crossfreq_system", _spy(verified_calls, TARGETS))

    result = runner.invoke(app, ["engine", "replay", "--path", "verified"])

    assert result.exit_code == 0, _output(result)
    assert verified_calls == [1]
    assert fast_calls == []


def test_replay_rejects_an_unknown_path(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "replay", "--path", "sloppy"])

    assert result.exit_code == 1
    assert "fast" in _output(result) and "verified" in _output(result)


def test_replay_rejects_a_malformed_date(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "replay", "--date", "last-tuesday"])

    assert result.exit_code == 1
    assert "YYYY-MM-DD" in _output(result)


def test_replay_empty_journal_reports_nothing_found(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "replay"])

    assert result.exit_code == 0
    assert "no journaled cycles" in _output(result)


# --- report ----------------------------------------------------------------------------------------


def test_report_end_to_end_over_a_mixed_journal(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    day1 = datetime(2026, 7, 7, tzinfo=UTC)
    for hour in (0, 4, 8, 12, 16, 20):
        _write_success_record(journal, day1 + timedelta(hours=hour))
    day2 = datetime(2026, 7, 8, tzinfo=UTC)
    for hour in (0, 12, 16, 20):
        _write_success_record(journal, day2 + timedelta(hours=hour))
    _write_sidecar(journal, day2 + timedelta(hours=4), reason="stale_pair", offending=("DOGE",))
    # day2 08:00 is absent entirely -- NOT fabricated; evaluate_gate scores it missing.
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 8, 21, 0, tzinfo=UTC))  # aware-UTC now

    result = runner.invoke(app, ["engine", "report"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "11 journaled outcome(s)" in out  # 10 success records + 1 sidecar; the absence adds nothing
    assert "10 replayed ok" in out
    assert "streak: 0" in out  # day1 clean (streak 1), day2's sidecar resets it
    assert "not met" in out
    # The most recent reset: day2's 04:00 sidecar (validation_failed) fires before the 08:00 absence.
    assert "2026-07-08T04:00:00+00:00" in out
    assert "validation failed" in out


def test_report_clean_days_build_the_streak(tmp_path, monkeypatch):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    day1 = datetime(2026, 7, 7, tzinfo=UTC)
    for hour in (0, 4, 8, 12, 16, 20):
        _write_success_record(engine_cfg.journal_dir, day1 + timedelta(hours=hour))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 7, 21, 0, tzinfo=UTC))

    result = runner.invoke(app, ["engine", "report"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "streak: 1" in out
    assert "not met" in out  # 1 < 14
    assert "last failure: none" in out


def test_report_empty_journal_is_a_zero_streak_not_an_error(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 8, 21, 0, tzinfo=UTC))

    result = runner.invoke(app, ["engine", "report"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "0 journaled outcome(s)" in out
    assert "streak: 0" in out


def test_execution_records_do_not_change_the_gate_report(tmp_path, monkeypatch):
    """Task 5's load-bearing invariant, pinned at the real call sites rather than against
    `evaluate_gate` directly (which never globs, so a test against it proves nothing): drive
    `report` -> `_evaluate_journal` -> the `_journal_artifacts` call-site globs -> `evaluate_gate`
    over a journal of clean days, once with no execution records and once with a refusing verdict
    written beside every cycle record, and require byte-identical output. If a future call site
    widens its glob to something that also sweeps up `exec-*.json`, this is the test that catches
    the streak silently resetting on a deliberate refusal to trade."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    day1 = datetime(2026, 7, 7, tzinfo=UTC)
    day2 = datetime(2026, 7, 8, tzinfo=UTC)
    for day in (day1, day2):
        for hour in (0, 4, 8, 12, 16, 20):
            _write_success_record(journal, day + timedelta(hours=hour))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 8, 21, 0, tzinfo=UTC))

    before = runner.invoke(app, ["engine", "report"])
    assert before.exit_code == 0, _output(before)

    for day_dir in sorted(journal.glob("20*-*-*")):
        day = datetime.strptime(day_dir.name, "%Y-%m-%d").replace(tzinfo=UTC)
        for hour in (0, 4, 8, 12, 16, 20):
            cycle_ts = day + timedelta(hours=hour)
            write_exec_record(journal, cycle_ts, _refusing_verdict(), evaluated_at=cycle_ts)
    assert list(journal.glob("*/exec-*.json")), "fixture wrote no exec records -- the test is vacuous"

    after = runner.invoke(app, ["engine", "report"])
    assert after.exit_code == 0, _output(after)
    assert _output(after) == _output(before), "a refusal to trade changed the concordance report -- the streak is no longer immune"


# --- the sub-app itself ----------------------------------------------------------------------------


def test_engine_help_lists_all_six_subcommands():
    result = runner.invoke(app, ["engine", "--help"])

    assert result.exit_code == 0
    out = _output(result)
    for name in ("seed", "run", "cycle", "replay", "report", "gate-export"):
        assert name in out, f"{name!r} missing from `zcrypto engine --help`"


def test_help_does_not_import_nautilus():
    # Subprocess check (robust to other tests having already imported nautilus in this process):
    # both the root help and the engine group help must never pay the ~1 s nautilus import.
    code = (
        "import sys\n"
        "from typer.testing import CliRunner\n"
        "from cli.__main__ import app\n"
        "runner = CliRunner()\n"
        "assert runner.invoke(app, ['--help']).exit_code == 0\n"
        "assert runner.invoke(app, ['engine', '--help']).exit_code == 0\n"
        "assert 'nautilus_trader' not in sys.modules, 'nautilus imported at --help time'\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr


def test_report_classifies_a_corrupt_snapshot_without_crashing(tmp_path, monkeypatch):
    # A truncated snapshot parquet (the partial-rsync case) is bad evidence -> validation-failed
    # CycleOutcome, streak reset, no traceback (the Task-4 review's hardening item).
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    day = datetime(2026, 7, 7, tzinfo=UTC)
    for hour in (0, 4, 8, 12, 16, 20):
        _write_success_record(journal, day + timedelta(hours=hour))
    # truncate one journaled snapshot mid-file
    victim = next((journal / "2026-07-07" / "snapshots" / "cycle-08").glob("*.parquet"))
    victim.write_bytes(victim.read_bytes()[: victim.stat().st_size // 2])
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 7, 21, 0, tzinfo=UTC))

    result = runner.invoke(app, ["engine", "report"])

    out = _output(result)
    assert result.exit_code == 0, out  # report itself succeeds; the gate verdict carries the failure
    assert "validation failed" in out
    assert "2026-07-07T08:00:00+00:00" in out
    assert "streak: 0" in out
    assert "Traceback" not in out


def test_cycle_rejects_a_future_boundary(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 10, 9, 0, tzinfo=UTC))
    called = []
    monkeypatch.setattr(command, "run_cycle", lambda *a, **k: called.append(1))

    result = runner.invoke(app, ["engine", "cycle", "--at", "2026-07-10T12:00:00+00:00"])

    assert result.exit_code == 1
    assert "has not elapsed" in _output(result)
    assert called == []


# --- run: fail-fast + the supervision watchdog (spec 00042) ----------------------------------------


class FakeTimer:
    """A synchronous stand-in for threading.Timer: start() fires the callback immediately, so the
    watchdog check runs deterministically inside `engine run` without waiting out the real delay."""

    instances: list["FakeTimer"] = []

    def __init__(self, interval, function):
        self.interval = interval
        self.function = function
        self.daemon = False
        self.started = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True
        self.function()

    def cancel(self):
        self.cancelled = True


def _fake_node(is_running: bool):
    return types.SimpleNamespace(
        _config=types.SimpleNamespace(timeout_connection=1.5, timeout_reconciliation=2.0),
        trader=types.SimpleNamespace(is_running=is_running),
        run=lambda: None,
        dispose=lambda: None,
    )


def _write_basket_store(store_dir: Path, symbols=BASKET) -> None:
    """Placeholder store files for `symbols` on both grids -- never read (the node is stubbed), they
    exist only to satisfy `run()`'s store-presence guard."""
    for symbol in symbols:
        for interval in GRID_INTERVALS:
            path = _store_path(store_dir, symbol, interval)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"")


def _run_env(monkeypatch, tmp_path, *, is_running: bool, symbols=BASKET) -> list[int]:
    """A passable `engine run` environment: valid store, stub node builder, synchronous timer, and
    a recording os._exit. Returns the list force-exit codes are recorded into."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    _write_basket_store(engine_cfg.store_dir, symbols)
    monkeypatch.delenv("ZCRYPTO_REQUIRE_CONFIG", raising=False)
    monkeypatch.setattr("cli.engine.node.build_shadow_node", lambda config: _fake_node(is_running))
    monkeypatch.setattr(command.threading, "Timer", FakeTimer)
    FakeTimer.instances.clear()
    exits: list[int] = []
    monkeypatch.setattr(command.os, "_exit", lambda code: exits.append(code))
    return exits


def test_run_require_config_aborts_without_zcrypto_toml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # no zcrypto.toml in the CWD
    monkeypatch.setenv("ZCRYPTO_REQUIRE_CONFIG", "1")

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 1
    assert "zcrypto.toml" in _output(result)
    assert isinstance(result.exception, SystemExit)


@pytest.mark.parametrize("store_state", ["missing", "empty"])
def test_run_aborts_on_a_missing_or_empty_store(tmp_path, monkeypatch, store_state):
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    if store_state == "empty":
        (engine_cfg.store_dir / "BTC" / "EUR").mkdir(parents=True)  # dirs but no series file in them
    monkeypatch.delenv("ZCRYPTO_REQUIRE_CONFIG", raising=False)

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 1
    assert str(engine_cfg.store_dir) in _output(result)


def test_run_aborts_when_the_store_holds_every_eur_leg_but_neither_btc_leg(tmp_path, monkeypatch):
    """The converge's real failure shape: the ten `/EUR` series are already on the host from the
    pre-widening build and the two `/BTC` parquets were never staged. A `*/EUR/*.parquet` glob
    passes on exactly this store, so the node starts and looks healthy; the first boundary's
    `refresh_store` then dies on a missing `ETH/BTC/240.parquet`, and the failed-cycle sidecar makes
    that boundary unretryable at any time (capture-deploys.md), costing the ratified gate streak."""
    _run_env(monkeypatch, tmp_path, is_running=True, symbols=[s for s in BASKET if s.endswith("/EUR")])

    result = runner.invoke(app, ["engine", "run"])

    out = _output(result)
    assert result.exit_code == 1, out
    assert "ETH/BTC@240" in out and "ETH/BTC@1440" in out
    assert "SOL/BTC@240" in out and "SOL/BTC@1440" in out
    assert "ADA/EUR" not in out  # only the absent legs are named -- the present ones are not noise
    assert str(tmp_path / "store") in out


def test_run_starts_on_a_complete_twelve_leg_store(tmp_path, monkeypatch):
    """The guard's healthy path: every basket leg present on both grids and `run()` proceeds -- a
    guard that also trips here would abort every correct deploy."""
    exits = _run_env(monkeypatch, tmp_path, is_running=True)

    result = runner.invoke(app, ["engine", "run"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "basket series" not in out
    assert exits == []


def test_run_logs_the_effective_config_line(tmp_path, monkeypatch):
    exits = _run_env(monkeypatch, tmp_path, is_running=True)

    result = runner.invoke(app, ["engine", "run"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert f"engine run: exec_enabled=False, store_dir={tmp_path / 'store'}, journal_dir={tmp_path / 'journal'}" in out
    assert exits == []


def test_run_re_arms_faulthandler_immediately_after_the_node_is_built(tmp_path, monkeypatch):
    """Building the node registers nautilus's asyncio SIGABRT handler, which installs CPython's own
    no-op C handler over faulthandler's -- after which a native abort prints nothing at all. Both
    calls and their order are pinned: the re-arm must follow the build (before it, there is nothing
    to undo), and `disable()` must precede `enable()` (`enable()` returns early when faulthandler
    already considers itself enabled, so on its own it cannot reinstall the clobbered handler).
    `tests/test_engine_node.py` measures the underlying library behaviour this rests on."""
    _run_env(monkeypatch, tmp_path, is_running=True)
    calls: list[str] = []
    monkeypatch.setattr(
        "cli.engine.node.build_shadow_node",
        lambda config: (calls.append("build"), _fake_node(True))[1],
    )
    monkeypatch.setattr(
        command,
        "faulthandler",
        types.SimpleNamespace(disable=lambda: calls.append("disable"), enable=lambda: calls.append("enable")),
    )

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 0, _output(result)
    assert calls == ["build", "disable", "enable"]


def test_run_starts_even_when_the_faulthandler_re_arm_cannot_take(tmp_path, monkeypatch):
    """`faulthandler.enable()` raises when `sys.stderr` has no file descriptor. The re-arm is a
    diagnostic aid and must never be able to stop the engine from starting -- so the raise is
    swallowed rather than propagated out of `engine run`."""

    def _no_fileno():
        raise io.UnsupportedOperation("fileno")

    _run_env(monkeypatch, tmp_path, is_running=True)
    monkeypatch.setattr(command, "faulthandler", types.SimpleNamespace(disable=lambda: None, enable=_no_fileno))

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 0, _output(result)


def test_run_watchdog_force_exits_when_the_trader_never_runs(tmp_path, monkeypatch):
    exits = _run_env(monkeypatch, tmp_path, is_running=False)

    result = runner.invoke(app, ["engine", "run"])

    out = _output(result)
    assert result.exit_code == 0, out  # os._exit is stubbed to record; run() then completes normally
    assert exits == [1]
    assert "trader not running" in out
    (timer,) = FakeTimer.instances
    assert timer.interval == pytest.approx(1.5 + 2.0 + 30.0)  # the node config's timeouts + the 30 s slack
    assert timer.daemon is True
    assert timer.started is True
    assert timer.cancelled is True  # cancelled in the finally once node.run() returned


def test_run_watchdog_does_nothing_when_the_trader_is_running(tmp_path, monkeypatch):
    exits = _run_env(monkeypatch, tmp_path, is_running=True)

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 0, _output(result)
    assert exits == []


def test_engine_startup_latches_the_restart_hold(tmp_path, monkeypatch):
    # The hold must land beside the journal (journal_dir.parent), not inside it -- a hold at
    # journal_dir/exec/restart-hold is where the gate never looks (see execgate.exec_dir), so
    # the latch would be silently invisible and every other test would still pass.
    _run_env(monkeypatch, tmp_path, is_running=True)

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 0, _output(result)
    assert (tmp_path / "exec" / "restart-hold").exists(), (
        "the hold must land beside the journal, not inside it -- a hold the gate cannot see is no hold"
    )


# --- exec-status -------------------------------------------------------------------------------------


def test_exec_status_prints_the_level_and_every_reason(tmp_path, monkeypatch):
    from cli.engine.execgate import exec_dir

    exec_dir(tmp_path).mkdir(parents=True)
    (exec_dir(tmp_path) / "restart-hold").touch()
    # --state-dir makes the config's journal_dir irrelevant here; the venue read is stubbed so no
    # test touches the network. Patch the symbol as imported INTO command.py, not at its source.
    # The status "stubbed-by-test" is a sentinel no real reader can produce (Kraken's own strings,
    # or "unreachable"/"unreadable") -- unlike "unreachable" it cannot pass by accident if the
    # `venue_reader=read_system_status` seam were ever dropped from exec_status, in which case this
    # test would silently start making a real network call instead of catching the regression.
    monkeypatch.setattr(
        "cli.engine.command.read_system_status",
        lambda *, now, opener=None: VenueStatus(status="stubbed-by-test", ok=False, observed_at=now),
    )
    result = runner.invoke(app, ["engine", "exec-status", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "level=none" in result.stdout
    assert "arm_file_absent" in result.stdout
    assert "restart_hold" in result.stdout
    assert "venue_status=stubbed-by-test" in result.stdout


# --- probe-plan --check ------------------------------------------------------------------------------

PLAN_AT = datetime(2026, 7, 10, 8, 30, tzinfo=UTC)


def _instrument(symbol: str, *, ordermin=0.0001, costmin=0.45, costmin_quote="EUR", lot_step=1e-08, tick_size=0.1) -> dict:
    return {
        "symbol": symbol,
        "instrument_id": f"{symbol}.KRAKEN",
        "ordermin": ordermin,
        "costmin": costmin,
        "costmin_quote": costmin_quote,
        "lot_step": lot_step,
        "tick_size": tick_size,
        "costmin_source": "snapshot-constant",
    }


def _write_venue_record(journal_dir: Path, cycle_ts: datetime, *, instruments: dict, balances: dict) -> Path:
    """A schema-2 `ok` venue record built as literal JSON -- the shape `write_venue_record` emits,
    without importing nautilus into this module (`validate_venue_record` checks it either way)."""
    doc = {
        "schema_version": 2,
        "cycle_ts": cycle_ts.isoformat(),
        "code_version": "test",
        "status": "ok",
        "state": {
            "snapshot_at": cycle_ts.isoformat(),
            "instruments": instruments,
            "positions": {},
            "balances": balances,
        },
        "concordance": {"ok": True, "failures": []},
    }
    path = journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"venue-{cycle_ts:%H}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))
    return path


def _write_plan(tmp_path: Path, intents: list[dict], *, created_at: datetime = PLAN_AT, plan_id: str = "probe-1") -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"plan_id": plan_id, "created_at": created_at.isoformat(), "intents": intents}))
    return path


def _intent(symbol="BTC/EUR", **overrides) -> dict:
    return {"symbol": symbol, "side": "buy", "action": "open", "mode": "execute", "notional_eur": 20.0} | overrides


def _probe_plan_env(tmp_path, monkeypatch, *, instruments=None, balances=None) -> EngineConfig:
    """The configured journal + a stubbed venue read + a frozen clock inside the plan's TTL."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    if instruments is not None:
        _write_venue_record(engine_cfg.journal_dir, CYCLE_TS, instruments=instruments, balances=balances or {"ZEUR": 500.0})
    monkeypatch.setattr(command, "_utc_now", lambda: PLAN_AT + timedelta(minutes=5))
    # The same sentinel-status stub exec-status uses: no test may reach the network, and a dropped
    # `venue_reader=read_system_status` seam would surface rather than pass silently.
    monkeypatch.setattr(
        "cli.engine.command.read_system_status",
        lambda *, now, opener=None: VenueStatus(status="stubbed-by-test", ok=False, observed_at=now),
    )
    return engine_cfg


def test_probe_plan_without_check_submits_nothing_and_exits_1(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent()])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan)])

    assert result.exit_code == 1
    assert "--check" in _output(result)


def test_probe_plan_check_accepts_a_valid_plan(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent()])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "plan ok: 1 intent(s), total notional 20.00 EUR" in out
    assert "BTC/EUR" in out
    # The gate is REPORTED, never held: a validator that exited 0 only when the gate was open would
    # read as permission, and the engine re-takes the gate inside every submission anyway.
    assert "level=none" in out
    assert "venue_status=stubbed-by-test" in out


def test_probe_plan_check_refuses_an_expired_plan(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent()], created_at=PLAN_AT - timedelta(hours=3))

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "expired" in _output(result)


def test_probe_plan_check_refuses_without_a_venue_snapshot(tmp_path, monkeypatch):
    engine_cfg = _probe_plan_env(tmp_path, monkeypatch)  # no venue record written
    plan = _write_plan(tmp_path, [_intent()])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 1
    assert str(engine_cfg.journal_dir) in out


def test_probe_plan_check_refuses_a_plan_over_the_cap(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent(notional_eur=90.0), _intent(notional_eur=90.0)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "exceeds the cap" in _output(result)


def test_probe_plan_check_refuses_a_plan_id_already_ledgered(tmp_path, monkeypatch):
    engine_cfg = _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    append_plan_entry(
        engine_cfg.journal_dir,
        CYCLE_TS,
        {
            "plan_id": "probe-1",
            "received_at": CYCLE_TS.isoformat(),
            "disposition": "accepted",
            "reasons": [],
            "plan": {},
            "intents": [],
        },
        verdict=_refusing_verdict(),
        evaluated_at=CYCLE_TS,
    )
    plan = _write_plan(tmp_path, [_intent()])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "already ledgered" in _output(result)


def test_probe_plan_check_refuses_a_cross_denomination_notional(tmp_path, monkeypatch):
    # The T0138 guard's rule at the validator: a /BTC leg's BTC-denominated costmin must never be
    # compared against a EUR notional -- 2e-05 BTC would pass every EUR figure silently.
    _probe_plan_env(tmp_path, monkeypatch, instruments={"ETH/BTC": _instrument("ETH/BTC", costmin=2e-05, costmin_quote="BTC")})
    plan = _write_plan(tmp_path, [_intent("ETH/BTC")])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 1
    assert "'BTC'" in out


def test_probe_plan_check_refuses_a_notional_below_costmin(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent(notional_eur=0.2)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "costmin" in _output(result)


def test_probe_plan_check_refuses_a_qty_below_ordermin(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR", ordermin=0.5, lot_step=0.1)})
    plan = _write_plan(tmp_path, [_intent(action="close", side="sell", notional_eur=None, qty=0.2)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "is below ordermin" in _output(result)


def test_probe_plan_check_refuses_a_qty_off_the_lot_step(tmp_path, monkeypatch):
    # Deliberately ABOVE ordermin, so only the alignment check can produce the refusal -- with a qty
    # that fails both, the exit code and the printed "lot step <n>" floor line are identical whether
    # the alignment check runs or not, and the test proves nothing (measured: that shape survived a
    # mutation disabling the check entirely).
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR", ordermin=0.5, lot_step=0.1)})
    plan = _write_plan(tmp_path, [_intent(action="close", side="sell", notional_eur=None, qty=0.65)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 1
    assert "is not a multiple of the 0.1 lot step" in out
    assert "below ordermin" not in out


def test_probe_plan_check_accepts_a_lot_aligned_qty_disposal(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR", ordermin=0.5, lot_step=0.1)})
    plan = _write_plan(tmp_path, [_intent(action="close", side="sell", notional_eur=None, qty=0.6)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 0, out
    # A qty intent carries no EUR notional at validation time -- the plan wall counts it as 0.00 and
    # the executor cumulates its real notional at sizing time instead.
    assert "plan ok: 1 intent(s), total notional 0.00 EUR" in out


def test_probe_plan_check_refuses_a_malformed_plan(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    path = tmp_path / "plan.json"
    path.write_text('{"plan_id": "probe-1", "created_at": "2026-07-10T08:30:00+00:00", "intents": []}')

    result = runner.invoke(app, ["engine", "probe-plan", str(path), "--check"])

    assert result.exit_code == 1
    assert "intents" in _output(result)


def test_probe_plan_check_refuses_an_unreadable_plan_file(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})

    result = runner.invoke(app, ["engine", "probe-plan", str(tmp_path / "nope.json"), "--check"])

    assert result.exit_code == 1
    assert "nope.json" in _output(result)


def test_probe_plan_check_refuses_a_margin_intent_over_the_free_balance(tmp_path, monkeypatch):
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")}, balances={"ZEUR": 5.0})
    plan = _write_plan(tmp_path, [_intent(notional_eur=40.0, leverage=2)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 1
    assert "margin floor" in _output(result)


def test_probe_plan_check_mutates_nothing(tmp_path, monkeypatch):
    engine_cfg = _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent()])
    before = {p: p.read_bytes() for p in sorted(engine_cfg.journal_dir.rglob("*")) if p.is_file()}

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    assert result.exit_code == 0, _output(result)
    assert {p: p.read_bytes() for p in sorted(engine_cfg.journal_dir.rglob("*")) if p.is_file()} == before
    # And nothing was dropped where the engine would pick it up.
    assert not (tmp_path / "exec").exists()


# --- --journal-dir overrides on replay/report ------------------------------------------------------


def test_replay_journal_dir_overrides_the_configured_journal(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)  # the configured journal stays empty
    pulled = tmp_path / "pulled-vps-journal"
    _write_success_record(pulled, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))

    result = runner.invoke(app, ["engine", "replay", "--journal-dir", str(pulled)])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "replayed 1 success record(s)" in out
    assert "1 ok" in out


def test_report_journal_dir_overrides_the_configured_journal(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)  # the configured journal stays empty
    pulled = tmp_path / "pulled-vps-journal"
    day = datetime(2026, 7, 7, tzinfo=UTC)
    for hour in (0, 4, 8, 12, 16, 20):
        _write_success_record(pulled, day + timedelta(hours=hour))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: datetime(2026, 7, 7, 21, 0, tzinfo=UTC))

    result = runner.invoke(app, ["engine", "report", "--journal-dir", str(pulled)])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "6 journaled outcome(s)" in out
    assert "streak: 1" in out
