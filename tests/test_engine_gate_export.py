"""CLI tests for `zcrypto engine gate-export`: the Prometheus textfile it writes and the dead-man's-switch ping."""

import json
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine import concordance
from cli.engine.journal import CycleRecord, SnapshotEntry, snapshot_content_hash, to_json, validate_record
from cli.ohlc.dataset import write_parquet

runner = CliRunner()

UTC = timezone.utc
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
PAIRS = ("BTC", "ETH")
TARGETS = {"BTC": 0.2, "ETH": 0.05}

# A day starting at hour 0: evaluate_gate EXCLUDES a mid-day-start first day rather than failing it
# (`excluded_day` in cli/engine/concordance.py).
GATE_CYCLE_HOURS = (0, 4, 8, 12, 16, 20)
DAY0 = datetime(2026, 7, 1, 0, 0, tzinfo=UTC)


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


def _write_success_record(
    journal_dir: Path,
    cycle_ts: datetime,
    targets: dict[str, float] = TARGETS,
    *,
    completed_at: datetime | None = None,
) -> Path:
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
        completed_at=completed_at if completed_at is not None else cycle_ts + timedelta(minutes=3),
        code_version="test",
        builder_path="fast",
    )
    validate_record(record)
    path = journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"cycle-{cycle_ts:%H}.json"
    path.write_text(to_json(record) + "\n")
    return path


def _write_clean_day(journal_dir: Path, day: datetime, *, skip_hour: int | None = None, late_hour: int | None = None) -> None:
    """Write a full 6-cycle day (00/04/08/12/16/20 UTC); `late_hour` pushes one boundary's
    completed_at past the 30-minute freshness window `evaluate_gate` checks."""
    for h in GATE_CYCLE_HOURS:
        if h == skip_hour:
            continue
        cycle_ts = day.replace(hour=h)
        completed_at = cycle_ts + timedelta(minutes=31) if h == late_hour else None
        _write_success_record(journal_dir, cycle_ts, completed_at=completed_at)


def _fake_builder(targets: dict[str, float]):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods)

    return builder


@pytest.fixture
def clean_journal(tmp_path, monkeypatch) -> Path:
    """A single clean success record at CYCLE_TS; `_utc_now` sits 10 min after it, so the default
    `--lag-fail-seconds` threshold is never tripped."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_success_record(journal, CYCLE_TS)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(minutes=10))
    return journal


@pytest.fixture
def mismatch_journal(tmp_path, monkeypatch) -> Path:
    """A full DAY0 (6 cycles) whose 00:00 record's schema_version is tampered with post-write, so
    `_evaluate_journal` counts a validation failure. A whole day, not a lone mid-day cycle:
    `evaluate_gate` scores only days whose freshness window has elapsed, so nothing shorter moves
    streak or last_failure."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_clean_day(journal, DAY0)
    record_path = journal / f"{DAY0:%Y-%m-%d}" / f"cycle-{DAY0:%H}.json"
    payload = json.loads(record_path.read_text())
    payload["schema_version"] = 99  # unsupported at ANY schema -- never 2, which 00094 made loadable
    record_path.write_text(json.dumps(payload))
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: DAY0.replace(hour=21))
    return journal


@pytest.fixture
def sidecar_journal(tmp_path, monkeypatch) -> Path:
    """DAY0's 12:00 boundary has ONLY a failed-cycle sidecar (the stale_pair/refresh_deadline path
    run_cycle writes, no success record for that cycle); the other 5 boundaries are clean successes,
    so the day is complete and scored. `_evaluate_journal` tallies the sidecar in sidecar_count."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_clean_day(journal, DAY0, skip_hour=12)
    sidecar_ts = DAY0.replace(hour=12)
    day_dir = journal / f"{DAY0:%Y-%m-%d}"
    payload = {
        "cycle_ts": sidecar_ts.isoformat(),
        "completed_at": (sidecar_ts + timedelta(minutes=1)).isoformat(),
        "reason": "stale_pair",
        "offending_pairs": ["BTC"],
    }
    (day_dir / f"failed-cycle-{sidecar_ts:%H}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: DAY0.replace(hour=21))
    return journal


@pytest.fixture
def missing_cycle_journal(tmp_path, monkeypatch) -> Path:
    """DAY0's only complete day is missing its 12:00 boundary entirely. `_evaluate_journal` never
    fabricates absent entries, so mismatch_total stays 0 and only evaluate_gate's streak sees the
    break."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_clean_day(journal, DAY0, skip_hour=12)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: DAY0.replace(hour=21))
    return journal


@pytest.fixture
def late_cycle_journal(tmp_path, monkeypatch) -> Path:
    """DAY0's only complete day has all 6 boundaries present, but the 08:00 cycle's completed_at
    falls outside the 30-minute freshness window: replay and compare both pass, so mismatch_total
    stays 0 and only evaluate_gate's streak reset catches it."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    _write_clean_day(journal, DAY0, late_hour=8)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: DAY0.replace(hour=21))
    return journal


@pytest.fixture
def recovered_gate_journal(tmp_path, monkeypatch) -> Path:
    """DAY0 breaks (its 00:00 record's schema_version is tampered with post-write), then DAY0+1 and
    DAY0+2 are fully clean: the streak recovers to 2 while mismatch_total, a cumulative counter over
    the whole journal, stays >= 1."""
    engine_cfg = _patch_config(monkeypatch, tmp_path)
    journal = engine_cfg.journal_dir
    day1, day2 = DAY0 + timedelta(days=1), DAY0 + timedelta(days=2)
    _write_clean_day(journal, DAY0)
    corrupt_path = journal / f"{DAY0:%Y-%m-%d}" / f"cycle-{DAY0:%H}.json"
    payload = json.loads(corrupt_path.read_text())
    payload["schema_version"] = 99  # unsupported at ANY schema -- never 2, which 00094 made loadable
    corrupt_path.write_text(json.dumps(payload))
    _write_clean_day(journal, day1)
    _write_clean_day(journal, day2)
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    monkeypatch.setattr(command, "_utc_now", lambda: day2.replace(hour=21))
    return journal


def _prom(text: str) -> dict[str, float]:
    return {ln.split()[0]: float(ln.split()[1]) for ln in text.splitlines() if ln and not ln.startswith("#")}


# --- gate-export -------------------------------------------------------------------------------------


def test_gate_export_clean_writes_all_series(tmp_path, monkeypatch, clean_journal):
    out = tmp_path / "gate.prom"
    pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))

    result = runner.invoke(
        app,
        ["engine", "gate-export", "--journal-dir", str(clean_journal), "--textfile", str(out), "--healthcheck-url", "http://hc"],
    )

    assert result.exit_code == 0, result.output
    m = _prom(out.read_text())
    assert m["zcrypto_gate_mismatch_total"] == 0
    assert "zcrypto_gate_streak_days" in m and "zcrypto_gate_status" in m
    assert "zcrypto_gate_journal_pull_lag_seconds" in m
    assert "zcrypto_gate_export_timestamp_seconds" in m
    assert pings == [("http://hc", True)]


def test_gate_export_mismatch_pings_fail_and_counts(tmp_path, monkeypatch, mismatch_journal):
    out = tmp_path / "gate.prom"
    pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))

    result = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(mismatch_journal),
            "--textfile",
            str(out),
            "--healthcheck-url",
            "http://hc",
        ],
    )

    assert result.exit_code == 0, result.output  # emit succeeded; mismatch is a finding
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] >= 1
    assert pings == [("http://hc", False)]


def test_gate_export_sidecar_failure_counts_and_pings_fail(tmp_path, monkeypatch, sidecar_journal):
    out = tmp_path / "gate.prom"
    pings: list[tuple[str, bool]] = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = runner.invoke(
        app,
        ["engine", "gate-export", "--journal-dir", str(sidecar_journal), "--textfile", str(out), "--healthcheck-url", "http://hc"],
    )
    assert res.exit_code == 0
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] >= 1
    assert pings == [("http://hc", False)]


def test_gate_export_missing_cycle_in_last_complete_day_pings_fail(tmp_path, monkeypatch, missing_cycle_journal):
    # A missing cycle breaks evaluate_gate's streak but contributes nothing to mismatch_total.
    out = tmp_path / "gate.prom"
    pings: list[tuple[str, bool]] = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(missing_cycle_journal),
            "--textfile",
            str(out),
            "--healthcheck-url",
            "http://hc",
        ],
    )
    assert res.exit_code == 0
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] == 0
    assert pings == [("http://hc", False)]


def test_gate_export_late_cycle_in_last_complete_day_pings_fail(tmp_path, monkeypatch, late_cycle_journal):
    # A late cycle resets the streak but is invisible to mismatch_total: replay and compare both
    # pass, and only evaluate_gate's freshness-window check catches it.
    out = tmp_path / "gate.prom"
    pings: list[tuple[str, bool]] = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(late_cycle_journal),
            "--textfile",
            str(out),
            "--healthcheck-url",
            "http://hc",
        ],
    )
    assert res.exit_code == 0
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] == 0
    assert pings == [("http://hc", False)]


def test_gate_export_recovered_gate_pings_clean_despite_historical_mismatch(tmp_path, monkeypatch, recovered_gate_journal):
    # A historical break, still counted in the cumulative mismatch_total, must not keep pinging
    # /fail once the gate has recovered a clean streak.
    out = tmp_path / "gate.prom"
    pings: list[tuple[str, bool]] = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))
    res = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(recovered_gate_journal),
            "--textfile",
            str(out),
            "--healthcheck-url",
            "http://hc",
        ],
    )
    assert res.exit_code == 0
    m = _prom(out.read_text())
    assert m["zcrypto_gate_mismatch_total"] >= 1  # the historical break is still counted (cumulative)
    assert m["zcrypto_gate_streak_days"] == 2  # but the gate has since recovered
    assert pings == [("http://hc", True)]


def test_gate_export_lag_beyond_lag_fail_seconds_pings_fail(tmp_path, monkeypatch, clean_journal):
    """The COMMAND-level `--lag-fail-seconds` check: the newest journaled cycle is older than the
    threshold, so the dead-man is pinged /fail."""
    out = tmp_path / "gate.prom"
    pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))

    result = runner.invoke(
        app,
        [
            "engine",
            "gate-export",
            "--journal-dir",
            str(clean_journal),
            "--textfile",
            str(out),
            "--healthcheck-url",
            "http://hc",
            "--lag-fail-seconds",
            "1",
        ],
    )

    assert result.exit_code == 0, result.output
    assert pings == [("http://hc", False)]


def test_gate_export_no_healthcheck_url_never_pings(tmp_path, monkeypatch, clean_journal):
    out = tmp_path / "gate.prom"
    pings = []
    monkeypatch.setattr(command, "_gate_ping", lambda url, success: pings.append((url, success)))

    result = runner.invoke(app, ["engine", "gate-export", "--journal-dir", str(clean_journal), "--textfile", str(out)])

    assert result.exit_code == 0, result.output
    assert pings == []


def test_gate_export_atomic_no_partial_on_write_error(tmp_path, monkeypatch, clean_journal):
    bad = tmp_path / "nope" / "gate.prom"

    result = runner.invoke(app, ["engine", "gate-export", "--journal-dir", str(clean_journal), "--textfile", str(bad)])

    assert result.exit_code != 0
    assert not bad.exists()
    assert not (tmp_path / "nope").exists()


def test_gate_export_journal_dir_defaults_to_configured_journal(tmp_path, monkeypatch, clean_journal):
    out = tmp_path / "gate.prom"
    # clean_journal already points load_config's engine.journal_dir at the fixture's journal.
    result = runner.invoke(app, ["engine", "gate-export", "--textfile", str(out)])

    assert result.exit_code == 0, result.output
    assert _prom(out.read_text())["zcrypto_gate_mismatch_total"] == 0


def test_gate_export_empty_journal_omits_lag_line(tmp_path, monkeypatch):
    _patch_config(monkeypatch, tmp_path)
    out = tmp_path / "gate.prom"

    result = runner.invoke(app, ["engine", "gate-export", "--textfile", str(out)])

    assert result.exit_code == 0, result.output
    m = _prom(out.read_text())
    assert "zcrypto_gate_journal_pull_lag_seconds" not in m
    assert m["zcrypto_gate_mismatch_total"] == 0


# --- report unchanged after the _evaluate_journal extraction ----------------------------------------


def test_report_output_unchanged_after_refactor(tmp_path, monkeypatch, clean_journal):
    result = runner.invoke(app, ["engine", "report", "--journal-dir", str(clean_journal)])

    out = result.output
    assert result.exit_code == 0, out
    assert "streak:" in out and "gate (>= 14 clean days):" in out
    assert "1 journaled outcome(s): 1 replayed ok, 0 mismatch(es), 0 validation failure(s), 0 failed cycle(s)" in out


# --- _gate_ping (mirrors cli/engine/cycle.py's _ping_healthcheck coverage) --------------------------


def test_gate_ping_success_hits_the_plain_url(monkeypatch):
    pings = []
    monkeypatch.setattr(command, "_urlopen", lambda url, timeout: pings.append((url, timeout)))

    command._gate_ping("http://hc", True)

    assert pings == [("http://hc", 10)]


def test_gate_ping_failure_hits_the_fail_suffixed_url(monkeypatch):
    pings = []
    monkeypatch.setattr(command, "_urlopen", lambda url, timeout: pings.append((url, timeout)))

    command._gate_ping("http://hc", False)

    assert pings == [("http://hc/fail", 10)]


def test_gate_ping_swallows_opener_errors(monkeypatch):
    def boom(url, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(command, "_urlopen", boom)

    command._gate_ping("http://hc", True)  # must not raise
