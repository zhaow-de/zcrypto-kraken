"""spec 00069 T4: the engine's `/metrics` tap -- cycle.py's sink mechanism (isolation-tested) and
command.py's gauge holder + startup seeding + `run()` wiring."""

import json
import socket
import types
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
from prometheus_client import CollectorRegistry
from prometheus_client.parser import text_string_to_metric_families
from typer.testing import CliRunner

import cli.engine.command as command
import cli.engine.cycle as cycle
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.command import _CycleGauges, _seed_completed_at
from cli.engine.cycle import CycleResult, run_cycle
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json, snapshot_content_hash, to_json, validate_record
from cli.engine.store import GRID_INTERVALS, PAIR_KEYS
from cli.obs.metrics import METRICS_PORT_ENV_VAR
from cli.ohlc.dataset import to_frame, write_parquet

runner = CliRunner()

UTC = timezone.utc
ASSETS = tuple(sorted(PAIR_KEYS))
KEY_TO_ASSET = {v: k for k, v in PAIR_KEYS.items()}
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
H4_LAST = CYCLE_TS - timedelta(hours=4)
DAILY_LAST = datetime(2026, 7, 9, tzinfo=UTC)
N_H4, N_DAILY = 6, 4
TARGETS = {asset: round(0.1 * (i + 1), 3) for i, asset in enumerate(ASSETS)}


@pytest.fixture(autouse=True)
def _reset_metrics_sink():
    """`cycle._metrics_sink` is module-level global state -- leaking a test's sink into the next
    test (or into an unrelated test file sharing this process) would be a real isolation bug of
    its own. Reset it unconditionally after every test in this file."""
    yield
    cycle.set_metrics_sink(None)


def _base(asset: str) -> float:
    return 100.0 * (1 + ASSETS.index(asset))


def _row(ts: datetime, close: float) -> list:
    return [int(ts.timestamp()), str(close), str(close), str(close), str(close), str(close), "1.0", 1]


def _grid_spec(interval: int) -> tuple[datetime, timedelta, int]:
    return (DAILY_LAST, timedelta(days=1), N_DAILY) if interval == 1440 else (H4_LAST, timedelta(hours=4), N_H4)


def _series_rows(asset: str, interval: int, *, drop_last: int = 0) -> list[list]:
    last, step, n = _grid_spec(interval)
    rows = [_row(last - (n - 1 - i) * step, _base(asset) + i) for i in range(n)]
    return rows[: len(rows) - drop_last] if drop_last else rows


def _store_rows(overrides: dict | None = None) -> dict:
    rows = {(a, iv): _series_rows(a, iv) for a in ASSETS for iv in GRID_INTERVALS}
    rows.update(overrides or {})
    return rows


def _write_store(store_dir: Path, rows_by: dict) -> None:
    for (asset, interval), rows in rows_by.items():
        write_parquet(to_frame(rows), store_dir / asset / "EUR" / f"{interval}.parquet")


def _tail_fetch(rows_by: dict):
    def fn(pair_key: str, interval: int) -> list[list]:
        return rows_by[(KEY_TO_ASSET[pair_key], interval)][-2:]

    return fn


class _SteppingClock:
    def __init__(self, start: datetime, step: timedelta = timedelta(seconds=10)):
        self._now, self._step = start, step

    def __call__(self) -> datetime:
        now = self._now
        self._now += self._step
        return now


def _clock(step: timedelta = timedelta(seconds=10)) -> _SteppingClock:
    return _SteppingClock(CYCLE_TS + timedelta(seconds=90), step)


def _fake_builder(targets: dict[str, float]):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods)

    return builder


def _env(tmp_path, monkeypatch, *, rows_by: dict | None = None) -> EngineConfig:
    rows_by = rows_by if rows_by is not None else _store_rows()
    store_dir = tmp_path / "store"
    _write_store(store_dir, rows_by)
    config = EngineConfig(store_dir=store_dir, journal_dir=tmp_path / "journal", shadow_nav_eur=1000.0)
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    return config


# --- cycle.py: the sink mechanism, isolation-tested -----------------------------------------------


def test_sink_is_a_noop_by_default(tmp_path, monkeypatch):
    # No set_metrics_sink call in this test -- the workstation soak's exact path.
    config = _env(tmp_path, monkeypatch)
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(_store_rows()), clock=_clock())
    assert result.status == "success"


def test_sink_called_on_success_with_completed_at_and_duration(tmp_path, monkeypatch):
    config = _env(tmp_path, monkeypatch)
    calls = []
    cycle.set_metrics_sink(lambda result, completed_at, duration_seconds: calls.append((result, completed_at, duration_seconds)))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(_store_rows()), clock=_clock())

    assert len(calls) == 1
    sunk_result, completed_at, duration_seconds = calls[0]
    assert sunk_result is result
    assert result.status == "success"
    record = from_json(result.record_path.read_text())
    assert completed_at == record.completed_at
    assert duration_seconds == pytest.approx((record.completed_at - record.started_at).total_seconds())
    assert duration_seconds > 0


def test_sink_called_on_a_failed_cycle_with_the_sidecars_own_timing(tmp_path, monkeypatch):
    store_rows = _store_rows({("ETH", 240): _series_rows("ETH", 240, drop_last=1)})
    config = _env(tmp_path, monkeypatch, rows_by=store_rows)
    calls = []
    cycle.set_metrics_sink(lambda result, completed_at, duration_seconds: calls.append((result, completed_at, duration_seconds)))

    # The fetch keeps returning the lagging tail: the cycle_ts - 4h bar never commits -> refresh_deadline.
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert len(calls) == 1
    sunk_result, completed_at, duration_seconds = calls[0]
    assert sunk_result is result
    sidecar = json.loads(result.sidecar_path.read_text())
    assert completed_at.isoformat() == sidecar["completed_at"]
    assert duration_seconds > 0


def test_a_raising_sink_leaves_the_cycle_result_and_journal_artifact_intact(tmp_path, monkeypatch, caplog):
    # THE isolation regression (spec 00069 D5, verbatim requirement): a raising metrics update can
    # never affect the CycleResult already built or the journal artifact already written -- both
    # happen strictly before the sink is invoked.
    config = _env(tmp_path, monkeypatch)

    def _boom(result, completed_at, duration_seconds):
        raise RuntimeError("sink boom")

    cycle.set_metrics_sink(_boom)
    with caplog.at_level("ERROR"):
        result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(_store_rows()), clock=_clock())

    assert result.status == "success"  # run_cycle returned normally -- the raise never propagated
    record = from_json(result.record_path.read_text())
    validate_record(record)  # the journal artifact is intact and still passes its own schema check
    assert record.final_targets == TARGETS
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed


def test_a_raising_sink_leaves_a_failed_cycles_sidecar_intact(tmp_path, monkeypatch):
    store_rows = _store_rows({("ETH", 240): _series_rows("ETH", 240, drop_last=1)})
    config = _env(tmp_path, monkeypatch, rows_by=store_rows)
    cycle.set_metrics_sink(lambda *a: (_ for _ in ()).throw(RuntimeError("sink boom")))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "refresh_deadline"


# --- command.py: _CycleGauges ---------------------------------------------------------------------


def _families(registry: CollectorRegistry) -> dict:
    """Sample-name -> the family carrying it (see `tests/test_capture_metrics.py::_families`):
    `Counter` strips a trailing `_total` from `family.name` and re-adds it per sample, so a lookup
    by the exposed series name has to go through `samples`, not the family object's own name."""
    result: dict = {}
    for family in registry.collect():
        for sample in family.samples:
            result[sample.name] = family
    return result


def test_cycle_gauges_update_sets_all_gauges_and_increments_counters():
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    started_at = CYCLE_TS
    completed_at = CYCLE_TS + timedelta(minutes=3)
    result = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets=dict(TARGETS),
        orders=[
            {"asset": "BTC", "side": "buy", "quantity": 0.001, "notional_eur": 200.0, "price": 200000.0},
            {"asset": "ETH", "side": "sell", "quantity": 0.01, "notional_eur": 50.0, "price": 5000.0},
        ],
        reason=None,
        offending_pairs=None,
    )

    gauges.update(result, completed_at, (completed_at - started_at).total_seconds())

    families = _families(registry)
    assert families["zcrypto_engine_cycle_success"].samples[0].value == 1.0
    assert families["zcrypto_engine_cycle_completed_at_seconds"].samples[0].value == pytest.approx(completed_at.timestamp())
    assert families["zcrypto_engine_cycle_duration_seconds"].samples[0].value == pytest.approx(
        (completed_at - started_at).total_seconds()
    )
    assert families["zcrypto_engine_orders_total"].samples[0].value == 2.0
    assert families["zcrypto_engine_order_notional_eur"].samples[0].value == 250.0
    weights = {sample.labels["asset"]: sample.value for sample in families["zcrypto_engine_target_weight"].samples}
    assert weights == TARGETS


def test_cycle_gauges_weight_series_count_matches_the_pinned_asset_universe():
    # PAIR_KEYS is the measured pinned universe (not an assumed count -- see the T4 report).
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    result = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets=dict(TARGETS),
        orders=[],
        reason=None,
        offending_pairs=None,
    )
    gauges.update(result, CYCLE_TS, 1.0)
    families = _families(registry)
    assert len(families["zcrypto_engine_target_weight"].samples) == len(PAIR_KEYS)


def test_cycle_gauges_update_on_failure_sets_success_zero_and_skips_targets_and_orders():
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    result = CycleResult(
        status="failed",
        cycle_ts=CYCLE_TS,
        record_path=None,
        sidecar_path=Path("failed-cycle-08.json"),
        targets=None,
        orders=None,
        reason="stale_pair",
        offending_pairs=("BTC",),
    )
    gauges.update(result, CYCLE_TS + timedelta(minutes=2), 120.0)

    families = _families(registry)
    assert families["zcrypto_engine_cycle_success"].samples[0].value == 0.0
    assert families["zcrypto_engine_orders_total"].samples[0].value == 0.0  # Counter defaults to 0, never incremented
    # The target_weight family is registered (its HELP/TYPE header always renders) but carries no
    # SAMPLES: `.labels(...)` was never called, since this cycle failed and has no targets. It
    # cannot appear in `_families()` (nothing to key by), so find it directly among the families.
    target_weight_family = next(family for family in registry.collect() if family.name == "zcrypto_engine_target_weight")
    assert target_weight_family.samples == []


# --- command.py: startup seeding -------------------------------------------------------------------


def _series(cycle_ts: datetime, interval: int, base: float) -> tuple[list[datetime], list[float]]:
    if interval == 240:
        last, step, n = cycle_ts - timedelta(hours=4), timedelta(hours=4), 6
    else:
        last, step, n = cycle_ts.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1), timedelta(days=1), 4
    ts = [last - (n - 1 - i) * step for i in range(n)]
    return ts, [base + i for i in range(n)]


def _write_success_record(journal_dir: Path, cycle_ts: datetime, *, completed_at: datetime) -> None:
    rel_dir = Path(f"{cycle_ts:%Y-%m-%d}") / "snapshots" / f"cycle-{cycle_ts:%H}"
    entries = []
    for interval in (1440, 240):
        ts, closes = _series(cycle_ts, interval, 100.0)
        rel_path = rel_dir / f"BTC-{interval}.parquet"
        frame = pl.DataFrame({"ts": ts, "close": closes}, schema={"ts": pl.Datetime("us", "UTC"), "close": pl.Float64})
        write_parquet(frame, journal_dir / rel_path)
        entries.append(
            SnapshotEntry(
                pair="BTC",
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
        final_targets={"BTC": 0.1},
        started_at=cycle_ts + timedelta(seconds=90),
        completed_at=completed_at,
        code_version="test",
        builder_path="fast",
    )
    validate_record(record)
    path = journal_dir / f"{cycle_ts:%Y-%m-%d}" / f"cycle-{cycle_ts:%H}.json"
    path.write_text(to_json(record) + "\n")


def _write_sidecar(journal_dir: Path, cycle_ts: datetime, *, completed_at: datetime) -> None:
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "cycle_ts": cycle_ts.isoformat(),
        "attempted_at": (cycle_ts + timedelta(seconds=90)).isoformat(),
        "completed_at": completed_at.isoformat(),
        "reason": "stale_pair",
        "offending_pairs": ["BTC"],
    }
    (day_dir / f"failed-cycle-{cycle_ts:%H}.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def test_seed_completed_at_falls_back_to_process_start_when_the_journal_is_empty(tmp_path, monkeypatch):
    fixed_now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(command, "_utc_now", lambda: fixed_now)
    assert _seed_completed_at(tmp_path / "journal") == fixed_now


def test_seed_completed_at_reads_the_newest_success_record(tmp_path):
    journal_dir = tmp_path / "journal"
    older, newer = datetime(2026, 7, 10, 8, 3, tzinfo=UTC), datetime(2026, 7, 10, 12, 3, tzinfo=UTC)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), completed_at=older)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 12, 0, tzinfo=UTC), completed_at=newer)
    assert _seed_completed_at(journal_dir) == newer


def test_seed_completed_at_considers_sidecars_too(tmp_path):
    journal_dir = tmp_path / "journal"
    older = datetime(2026, 7, 10, 8, 3, tzinfo=UTC)
    newer_sidecar = datetime(2026, 7, 10, 12, 2, tzinfo=UTC)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), completed_at=older)
    _write_sidecar(journal_dir, datetime(2026, 7, 10, 12, 0, tzinfo=UTC), completed_at=newer_sidecar)
    assert _seed_completed_at(journal_dir) == newer_sidecar


# --- run(): opt-in wiring ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fake_node(is_running: bool = True):
    return types.SimpleNamespace(
        _config=types.SimpleNamespace(timeout_connection=1.5, timeout_reconciliation=2.0),
        trader=types.SimpleNamespace(is_running=is_running),
        run=lambda: None,
        dispose=lambda: None,
    )


def _patch_engine_config(monkeypatch, tmp_path: Path) -> EngineConfig:
    cfg = AppConfig(
        data_dir=None,
        nfs_mount_dir=Path("/mnt/zhao-crypto"),
        fetch=FetchConfig(),
        engine=EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal"),
        data=DataConfig(),
    )
    monkeypatch.setattr(command, "load_config", lambda: cfg)
    return cfg.engine


def _run_env(monkeypatch, tmp_path):
    engine_cfg = _patch_engine_config(monkeypatch, tmp_path)
    (engine_cfg.store_dir / "BTC" / "EUR").mkdir(parents=True)
    (engine_cfg.store_dir / "BTC" / "EUR" / "240.parquet").write_bytes(b"")  # never read; the node is stubbed
    monkeypatch.delenv("ZCRYPTO_REQUIRE_CONFIG", raising=False)
    monkeypatch.setattr("cli.engine.node.build_shadow_node", lambda config: _fake_node())
    return engine_cfg


def test_run_metrics_port_unset_starts_no_server(tmp_path, monkeypatch):
    monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
    _run_env(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(command, "start_metrics_server", lambda port, registry: calls.append(port) or True)

    result = runner.invoke(app, ["engine", "run"])

    assert result.exit_code == 0, result.output
    assert calls == []


def test_run_metrics_port_set_serves_process_and_engine_series_seeded_at_startup(tmp_path, monkeypatch):
    journal_dir = tmp_path / "journal"
    completed_at = datetime(2026, 7, 9, 12, 3, tzinfo=UTC)
    _write_success_record(journal_dir, datetime(2026, 7, 9, 12, 0, tzinfo=UTC), completed_at=completed_at)

    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _run_env(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "run"])
    assert result.exit_code == 0, result.output

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    assert "process_resident_memory_bytes" in body
    seeded = {family.name: family for family in text_string_to_metric_families(body)}["zcrypto_engine_cycle_completed_at_seconds"]
    assert seeded.samples[0].value == pytest.approx(completed_at.timestamp())  # seeded, not absent
    for name in (
        "zcrypto_engine_target_weight",
        "zcrypto_engine_orders_total",
        "zcrypto_engine_order_notional_eur",
        "zcrypto_engine_cycle_success",
        "zcrypto_engine_cycle_duration_seconds",
    ):
        assert name in body, f"{name} missing from /metrics: {body}"
