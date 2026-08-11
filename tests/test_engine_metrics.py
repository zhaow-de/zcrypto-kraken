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
from cli.engine.command import _CycleGauges, _ExecGauges, _seed_completed_at
from cli.engine.cycle import CycleResult, run_cycle
from cli.engine.execgate import LEVEL_CODE, GateLevel, GateVerdict
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
NOW = datetime(2026, 7, 10, 8, 3, tzinfo=UTC)

# `_reset_metrics_sink` (cycle._metrics_sink reset after every test) now lives in tests/conftest.py
# so every file in the suite is protected, not just this one.


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


# The forming-row position the fake builder plants per sleeve, per asset -- deliberately shaped so
# that BOTH halves of run_cycle's extraction are discriminated (every value is exactly representable
# in binary, so the expectations below are equalities, not approximations):
#   - the ROW INDEX: every completed period is 0.0 and only the forming row is non-zero, so an
#     off-by-one reads 0.0 for all three sleeves -- exactly the false "the book is flat" claim these
#     gauges exist to prevent, and one that would poison the alert's baseline.
#   - the abs(): two sleeves carry a NEGATIVE leg, so an extraction that summed raw positions would
#     read A1 as -0.5 and A2 as 0.125 rather than 0.5 and 0.375.
# B is flat, mirroring the measured dormant state; A1/A2 carry the book.
SLEEVE_FORMING = {
    "B": dict.fromkeys(ASSETS, 0.0),
    "A1": {**dict.fromkeys(ASSETS, 0.0), ASSETS[0]: -0.5},
    "A2": {**dict.fromkeys(ASSETS, 0.0), ASSETS[0]: 0.25, ASSETS[1]: -0.125},
}
SLEEVE_GROSS_EXPECTED = {"B": 0.0, "A1": 0.5, "A2": 0.375}


def _fake_builder(targets: dict[str, float]):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        # The real builder's three fixed-weight sleeves; run_cycle reads the forming row of each.
        sleeves = {name: {a: [0.0] * n_periods + [SLEEVE_FORMING[name][a]] for a in h4_prices} for name in ("B", "A1", "A2")}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods, sleeve_positions=sleeves)

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
    # No set_metrics_sink call in this test -- the workstation soak's exact path. Assert the sink
    # itself is None (not just that run_cycle succeeds): _update_metrics's guard swallows even a
    # RAISING default sink, so a bare success assertion here can't tell "no sink installed" from
    # "a sink is installed and just didn't blow up" (Minor 3, spec 00069 T4 review).
    assert cycle._metrics_sink is None
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


def test_run_cycle_extracts_each_sleeves_forming_row_gross(tmp_path, monkeypatch):
    # THE end-to-end pin on the extraction itself. Every other sleeve test in this file drives
    # `_CycleGauges.update` with a hand-built CycleResult, so none of them can see run_cycle reading
    # the WRONG ROW out of the builder: mutating `[result.n_periods]` to `[result.n_periods - 1]`
    # left all of them green. That mutation ships sleeve_gross={0,0,0} and active_sleeves=0 -- the
    # book reported permanently flat, and the composition-changed alert baselined on a lie, so the
    # eventual fix deploy fires a spurious page.
    config = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(_store_rows()), clock=_clock())

    assert result.status == "success"
    assert result.sleeve_gross == SLEEVE_GROSS_EXPECTED
    # The fixture genuinely discriminates, asserted rather than assumed: a wrong row index reads
    # 0.0 for every sleeve (so the two non-zero expectations bite), and a dropped abs() reads the
    # signed sums below (so the negative legs bite).
    assert SLEEVE_GROSS_EXPECTED["A1"] > 0.0 and SLEEVE_GROSS_EXPECTED["A2"] > 0.0
    signed = {name: sum(book.values()) for name, book in SLEEVE_FORMING.items()}
    assert signed != SLEEVE_GROSS_EXPECTED, "no sleeve carries a negative leg -- abs() would be unpinned"


def test_run_cycle_leaves_sleeve_gross_none_on_a_failed_cycle(tmp_path, monkeypatch):
    # The other half of the contract the gauges depend on: a cycle that never reached the build has
    # no composition, so the gauges must hold their previous values rather than read as "all flat".
    store_rows = _store_rows({("ETH", 240): _series_rows("ETH", 240, drop_last=1)})
    config = _env(tmp_path, monkeypatch, rows_by=store_rows)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert result.sleeve_gross is None


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
        sleeve_gross={"B": 0.0, "A1": 0.0, "A2": 0.32},
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
        sleeve_gross={"B": 0.0, "A1": 0.0, "A2": 0.32},
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
        sleeve_gross=None,
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


# --- command.py: cycle_duration lazy registration + target_weight retirement (spec 00084 D4) -------


def test_cycle_duration_is_absent_before_the_first_cycle():
    # Same reasoning as cycle_success/active_sleeves (cold-review I4): a freshly-registered Gauge
    # defaults to 0.0, and "the last cycle took 0 seconds" before any cycle has run is a claim the
    # engine has not measured -- false. An absent series is honest; a published 0 is a claim.
    registry = CollectorRegistry()
    _CycleGauges(registry)
    assert registry.get_sample_value("zcrypto_engine_cycle_duration_seconds") is None


def test_cycle_duration_registers_on_first_cycle():
    # A failed CycleResult, deliberately: this is the one place in the file that pins duration
    # being published on a failed cycle too, not just a successful one -- not redundant with the
    # "is absent before the first cycle" test above even though both pass pre-fix.
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
        sleeve_gross=None,
    )

    gauges.update(result, CYCLE_TS, 12.5)

    assert registry.get_sample_value("zcrypto_engine_cycle_duration_seconds") == 12.5


def test_a_dropped_asset_stops_publishing_its_target_weight():
    # A weight that persists after the asset leaves the book over-reports for the life of the process.
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    first = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets={"BTC": 0.6, "ETH": 0.4},
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )
    second = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS + timedelta(hours=4),
        record_path=Path("cycle-12.json"),
        sidecar_path=None,
        targets={"BTC": 1.0},
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )

    gauges.update(first, CYCLE_TS, 1.0)
    gauges.update(second, CYCLE_TS + timedelta(hours=4), 1.0)

    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "BTC"}) == 1.0
    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "ETH"}) is None, (
        "a dropped asset must go ABSENT, not to zero -- zero and not-in-the-book are different states"
    )


def test_a_failed_cycle_leaves_the_last_target_weights_standing():
    # targets=None on a failed cycle: retiring the book there would blank both weight panels and
    # the gross line for a full 4h gap, reading as "the engine holds nothing" -- the same
    # absence-versus-value confusion this pair of fixes exists to remove.
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    success = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets={"BTC": 0.6, "ETH": 0.4},
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )
    failed = CycleResult(
        status="failed",
        cycle_ts=CYCLE_TS + timedelta(hours=4),
        record_path=None,
        sidecar_path=Path("failed-cycle-12.json"),
        targets=None,
        orders=None,
        reason="stale_pair",
        offending_pairs=("BTC",),
        sleeve_gross=None,
    )

    gauges.update(success, CYCLE_TS, 1.0)
    gauges.update(failed, CYCLE_TS + timedelta(hours=4), 1.0)

    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "BTC"}) == 0.6
    assert registry.get_sample_value("zcrypto_engine_target_weight", {"asset": "ETH"}) == 0.4


# --- command.py: sleeve occupancy (T0124's rung-3 precondition) ------------------------------------
# The deployable combines three sleeves at fixed 1/3 weights and two of them have been flat for
# months. Nothing observed that, and nothing would observe them RE-ARMING either -- which roughly
# triples portfolio gross. These two series make the composition, and any change to it, visible.

SLEEVE_GROSS = {"B": 0.0, "A1": 0.0, "A2": 0.32}


def _sleeve_result(sleeve_gross: dict[str, float] | None, *, status: str = "success") -> CycleResult:
    return CycleResult(
        status=status,
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json") if status == "success" else None,
        sidecar_path=None if status == "success" else Path("failed-cycle-08.json"),
        targets=dict(TARGETS) if status == "success" else None,
        orders=[] if status == "success" else None,
        reason=None if status == "success" else "stale_pair",
        offending_pairs=None if status == "success" else ("BTC",),
        sleeve_gross=sleeve_gross,
    )


def test_active_sleeves_publishes_no_series_before_the_first_cycle():
    # THE lazy-registration pin, the same reasoning as `zcrypto_engine_cycle_success` (cold-review
    # I4): a labelled Gauge is naturally honest -- it publishes nothing until `.labels()` is first
    # called -- but `zcrypto_engine_active_sleeves` is UNLABELLED, and a freshly-registered
    # unlabelled Gauge publishes 0.0 immediately. "Zero sleeves are carrying exposure" is a claim,
    # and before any cycle has run it is a false one -- it would read as the whole book having gone
    # flat for up to the 4h until the next cycle, and (worse) it becomes the baseline the
    # composition-changed alert measures the first real cycle against. An absent series is honest.
    registry = CollectorRegistry()
    _CycleGauges(registry)
    assert [f for f in registry.collect() if f.name == "zcrypto_engine_active_sleeves"] == []


def test_cycle_gauges_publish_per_sleeve_gross_and_the_active_count():
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)

    gauges.update(_sleeve_result(dict(SLEEVE_GROSS)), CYCLE_TS, 1.0)

    families = _families(registry)
    gross = {sample.labels["sleeve"]: sample.value for sample in families["zcrypto_engine_sleeve_gross"].samples}
    assert gross == SLEEVE_GROSS
    assert len(families["zcrypto_engine_sleeve_gross"].samples) == 3  # one series per sleeve, always
    # The one-sleeve book as measured across every journaled cycle: only A2 carries exposure.
    assert families["zcrypto_engine_active_sleeves"].samples[0].value == 1.0


def test_a_re_armed_sleeve_moves_the_active_count():
    # The reversal the alert exists to announce -- B coming back from flat is a 1 -> 2 step, which
    # is what `changes(zcrypto_engine_active_sleeves[26h])` reads.
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)

    gauges.update(_sleeve_result(dict(SLEEVE_GROSS)), CYCLE_TS, 1.0)
    gauges.update(_sleeve_result({"B": 0.28, "A1": 0.0, "A2": 0.32}), CYCLE_TS + timedelta(hours=4), 1.0)

    families = _families(registry)
    assert families["zcrypto_engine_active_sleeves"].samples[0].value == 2.0
    gross = {sample.labels["sleeve"]: sample.value for sample in families["zcrypto_engine_sleeve_gross"].samples}
    assert gross == {"B": 0.28, "A1": 0.0, "A2": 0.32}


def test_a_cycle_without_sleeve_gross_leaves_both_series_untouched():
    # A failed cycle carries sleeve_gross=None. Publishing 0/absent-of-3 there would read exactly
    # like every sleeve going flat and would step the active count -- firing the
    # composition-changed alert on a refresh timeout, twice (once down, once back).
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)
    gauges.update(_sleeve_result(dict(SLEEVE_GROSS)), CYCLE_TS, 1.0)

    gauges.update(_sleeve_result(None, status="failed"), CYCLE_TS + timedelta(hours=4), 1.0)

    families = _families(registry)
    assert families["zcrypto_engine_active_sleeves"].samples[0].value == 1.0
    gross = {sample.labels["sleeve"]: sample.value for sample in families["zcrypto_engine_sleeve_gross"].samples}
    assert gross == SLEEVE_GROSS


def test_a_failed_first_cycle_still_leaves_active_sleeves_absent():
    # The lazy registration must survive a failure-first startup too: a node whose very first cycle
    # times out has no composition to report, and 0 would be a claim it never measured.
    registry = CollectorRegistry()
    gauges = _CycleGauges(registry)

    gauges.update(_sleeve_result(None, status="failed"), CYCLE_TS, 1.0)

    assert [f for f in registry.collect() if f.name == "zcrypto_engine_active_sleeves"] == []


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


# --- _seed_cycle_state: the outcome half (cold-review I4) -------------------------------------------


def test_seed_cycle_state_scores_a_newest_success_record_true(tmp_path):
    journal_dir = tmp_path / "journal"
    older = datetime(2026, 7, 10, 8, 3, tzinfo=UTC)
    newer = datetime(2026, 7, 10, 12, 3, tzinfo=UTC)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), completed_at=older)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 12, 0, tzinfo=UTC), completed_at=newer)
    completed_at, success = command._seed_cycle_state(journal_dir)
    assert completed_at == newer
    assert success is True


def test_seed_cycle_state_scores_a_newest_sidecar_false(tmp_path):
    journal_dir = tmp_path / "journal"
    older = datetime(2026, 7, 10, 8, 3, tzinfo=UTC)
    newer_sidecar = datetime(2026, 7, 10, 12, 2, tzinfo=UTC)
    _write_success_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), completed_at=older)
    _write_sidecar(journal_dir, datetime(2026, 7, 10, 12, 0, tzinfo=UTC), completed_at=newer_sidecar)
    completed_at, success = command._seed_cycle_state(journal_dir)
    assert completed_at == newer_sidecar
    assert success is False


def test_seed_cycle_state_returns_none_success_when_the_journal_is_empty(tmp_path, monkeypatch):
    fixed_now = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    monkeypatch.setattr(command, "_utc_now", lambda: fixed_now)
    completed_at, success = command._seed_cycle_state(tmp_path / "journal")
    assert completed_at == fixed_now
    assert success is None


# --- command.py: _ExecGauges -------------------------------------------------------------------------


def test_exec_gauges_publish_the_verdict():
    reg = CollectorRegistry()
    g = _ExecGauges(reg)
    g.update(
        GateVerdict(
            level=GateLevel.REDUCE_ONLY,
            reasons=("restart_hold",),
            inputs={
                "armed_in_config": True,
                "arm_file": True,
                "kill_file": False,
                "restart_hold": True,
                "venue_status": "online",
                "venue_snapshot_age_seconds": 4.0,
            },
        ),
        evaluated_at=NOW,
    )
    assert reg.get_sample_value("zcrypto_exec_gate_level") == 1
    assert reg.get_sample_value("zcrypto_exec_armed") == 1
    assert reg.get_sample_value("zcrypto_exec_kill_tripped") == 0
    assert reg.get_sample_value("zcrypto_exec_restart_hold") == 1
    assert reg.get_sample_value("zcrypto_exec_venue_ok") == 1
    assert reg.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == NOW.timestamp()


def test_armed_requires_BOTH_keys():
    for cfg_armed, file_armed in ((True, False), (False, True), (False, False)):
        reg = CollectorRegistry()
        _ExecGauges(reg).update(
            GateVerdict(
                level=GateLevel.NONE,
                reasons=("x",),
                inputs={
                    "armed_in_config": cfg_armed,
                    "arm_file": file_armed,
                    "kill_file": False,
                    "restart_hold": False,
                    "venue_status": "online",
                    "venue_snapshot_age_seconds": 0.0,
                },
            ),
            evaluated_at=NOW,
        )
        assert reg.get_sample_value("zcrypto_exec_armed") == 0


def test_the_heartbeat_series_is_absent_until_an_evaluation_exists():
    # `_CycleGauges` precedent: an absent series is honest, a published 0 is a claim. Before any
    # venue read, "the snapshot is 0 seconds old" would assert a reading that never happened.
    reg = CollectorRegistry()
    _ExecGauges(reg)  # constructed, never updated
    assert reg.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") is None
    # gate_level seeds at 0 = "nothing may be submitted", which is true of a process that has not
    # evaluated anything yet. The other presence gauges also seed at 0, which is NOT necessarily
    # true -- hence the startup evaluation in run().
    assert reg.get_sample_value("zcrypto_exec_gate_level") == 0


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


class _StubGate:
    """Replaces `ExecutionGate` for every `run()` test in this file: the gate's own logic (venue
    reads, control-file presence, restart hold) is proven exhaustively in
    tests/test_engine_execgate.py, so these tests only need a canned, network-free verdict to
    exercise the WIRING `run()` builds around it -- the sink it installs, the gauges it updates,
    the ledger it writes. `instances` records every construction so a test can pin the args `run()`
    passed (e.g. `state_dir` -- Task 4's exact silent-failure shape: `journal_dir` instead of
    `journal_dir.parent` would leave the hold permanently invisible with every other test green)."""

    instances: list["_StubGate"] = []

    def __init__(self, *, armed_in_config, state_dir, venue_reader=None):
        self.armed_in_config = armed_in_config
        self.state_dir = state_dir
        self.venue_reader = venue_reader
        _StubGate.instances.append(self)

    def evaluate(self, now):
        return GateVerdict(
            level=GateLevel.REDUCE_ONLY,
            reasons=("restart_hold",),
            inputs={
                "armed_in_config": self.armed_in_config,
                "arm_file": False,
                "kill_file": False,
                "restart_hold": True,
                "venue_status": "online",
                "venue_snapshot_age_seconds": 0.0,
            },
        )


def _run_env(monkeypatch, tmp_path):
    engine_cfg = _patch_engine_config(monkeypatch, tmp_path)
    (engine_cfg.store_dir / "BTC" / "EUR").mkdir(parents=True)
    (engine_cfg.store_dir / "BTC" / "EUR" / "240.parquet").write_bytes(b"")  # never read; the node is stubbed
    monkeypatch.delenv("ZCRYPTO_REQUIRE_CONFIG", raising=False)
    monkeypatch.setattr("cli.engine.node.build_shadow_node", lambda config: _fake_node())
    _StubGate.instances.clear()
    monkeypatch.setattr(command, "ExecutionGate", _StubGate)  # no live venue read in these tests
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
    ):
        assert name in body, f"{name} missing from /metrics: {body}"
    # cycle_duration is NOT in the list above: it is lazy (spec 00084 D4) and this test never runs
    # a real cycle (node.run() is a no-op stub), so it must stay absent -- the false-0 this task fixes.
    assert "zcrypto_engine_cycle_duration_seconds" not in body


def test_run_with_an_empty_journal_leaves_cycle_success_unpublished(tmp_path, monkeypatch):
    # THE I4 regression (cold-review, 00069 final review): a brand-new deployment (empty journal,
    # never populated by `_run_env`) must not publish zcrypto_engine_cycle_success at all before
    # the first real cycle completes -- a freshly-registered Gauge defaults to 0.0, which would
    # read as "the last cycle failed" for up to 4h. Absence is honest; a published 0 is a claim.
    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _run_env(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "run"])
    assert result.exit_code == 0, result.output

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    assert "process_resident_memory_bytes" in body  # process metrics still serve
    assert "zcrypto_engine_cycle_success" not in body


def test_run_survives_an_unreadable_journal_record_at_metrics_seed_time(tmp_path, monkeypatch, caplog):
    # THE Critical (spec 00069 T3/T4 review): _seed_completed_at reads arbitrary on-disk journal
    # artifacts (from_json / _sidecar_fields); an unreadable cycle-*.json (bad mode/ownership on
    # the bind mount) raises PermissionError, which the pre-fix code caught only EngineJournalError
    # around -- crash-looping the engine daemon at startup, on the trade-key host, before
    # build_shadow_node is ever reached. Metrics setup must degrade (logged), never abort `run()`.
    journal_dir = tmp_path / "journal"
    _write_success_record(
        journal_dir, datetime(2026, 7, 9, 12, 0, tzinfo=UTC), completed_at=datetime(2026, 7, 9, 12, 3, tzinfo=UTC)
    )
    bad_path = journal_dir / "2026-07-09" / "cycle-12.json"
    bad_path.chmod(0o000)

    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _run_env(monkeypatch, tmp_path)
    node_started = []
    monkeypatch.setattr("cli.engine.node.build_shadow_node", lambda config: (node_started.append(True), _fake_node())[1])

    try:
        with caplog.at_level("ERROR"):
            result = runner.invoke(app, ["engine", "run"])
    finally:
        bad_path.chmod(0o644)  # restore so tmp_path cleanup never depends on the test's outcome

    assert result.exit_code == 0, result.output
    assert node_started == [True]  # build_shadow_node/node.run() was still reached
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    assert "process_resident_memory_bytes" in body  # process metrics still serve


# --- run(): the sink's exec-envelope half (spec 00088 T6) --------------------------------------------
# `_ExecGauges.update` is tested above with hand-built verdicts, but the closure `run()` installs is
# the ledger's only production writer and `cycle.py::_update_metrics` swallows its exceptions by
# design -- so a broken composition (wrong journal_dir, a swapped state_dir, the update guarded by
# the wrong None-check) fails SILENTLY in production. These tests drive that closure directly.


def test_a_completed_cycle_writes_an_exec_record_and_moves_the_gauges(tmp_path, monkeypatch):
    registry = CollectorRegistry()
    monkeypatch.setattr(command, "build_registry", lambda: registry)
    monkeypatch.setattr(command, "start_metrics_server", lambda port, reg: True)
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    engine_cfg = _run_env(monkeypatch, tmp_path)

    completed_at = CYCLE_TS + timedelta(minutes=3)
    result = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets=dict(TARGETS),
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )

    def _run_and_complete_a_cycle():
        cycle._metrics_sink(result, completed_at, 30.0)  # the same call cycle.py makes post-artifact

    monkeypatch.setattr(
        "cli.engine.node.build_shadow_node",
        lambda config: types.SimpleNamespace(
            _config=types.SimpleNamespace(timeout_connection=1.5, timeout_reconciliation=2.0),
            trader=types.SimpleNamespace(is_running=True),
            run=_run_and_complete_a_cycle,
            dispose=lambda: None,
        ),
    )

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    (gate_instance,) = _StubGate.instances
    assert gate_instance.state_dir == engine_cfg.journal_dir.parent  # Task 4's exact silent-fail shape
    # run() passes venue_reader explicitly rather than relying on ExecutionGate's default, so
    # `monkeypatch.setattr(command, "read_system_status", ...)` is a working seam for tests.
    assert gate_instance.venue_reader is command.read_system_status
    assert list((engine_cfg.journal_dir / f"{CYCLE_TS:%Y-%m-%d}").glob("exec-*.json")), "the sink never wrote an exec record"
    # the startup evaluation alone -- before the cycle above ever ran -- must already have
    # published a truthful restart hold, or a kill switch tripped across a restart would resolve
    # the alert for up to 4h until the next cycle completes.
    assert registry.get_sample_value("zcrypto_exec_restart_hold") == 1
    assert registry.get_sample_value("zcrypto_exec_gate_level") == LEVEL_CODE[GateLevel.REDUCE_ONLY]


def test_the_startup_evaluation_alone_seeds_the_latch_gauges(tmp_path, monkeypatch):
    # Isolates the startup-evaluation property from the sink: no cycle ever completes here (the
    # node's run() is the file's ordinary no-op stub), so if run() dropped the startup evaluation
    # every latch gauge would sit at its seeded 0 for up to 4h -- a kill switch engaged across a
    # restart would read zcrypto_exec_kill_tripped=0, resolving the alert, until the next cycle.
    registry = CollectorRegistry()
    monkeypatch.setattr(command, "build_registry", lambda: registry)
    monkeypatch.setattr(command, "start_metrics_server", lambda port, reg: True)
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    _run_env(monkeypatch, tmp_path)  # _fake_node(): run() is a no-op, no cycle ever completes

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert registry.get_sample_value("zcrypto_exec_restart_hold") == 1
    assert registry.get_sample_value("zcrypto_exec_gate_level") == LEVEL_CODE[GateLevel.REDUCE_ONLY]
    assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") is not None


class _RaisingGate:
    """Guard-proving probe for the startup-evaluation try/except in run(): a guard is unproven
    until the defect it names is constructed and seen to trip it. `evaluate()` always raises, so
    this is the exact failure the wrap exists to isolate -- a broken gate at startup must log, not
    stop the engine from starting."""

    def __init__(self, *, armed_in_config, state_dir, venue_reader=None):
        pass

    def evaluate(self, now):
        raise RuntimeError("gate boom")


def test_a_raising_startup_evaluation_never_prevents_the_engine_from_starting(tmp_path, monkeypatch, caplog):
    registry = CollectorRegistry()
    monkeypatch.setattr(command, "build_registry", lambda: registry)
    monkeypatch.setattr(command, "start_metrics_server", lambda port, reg: True)
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    _run_env(monkeypatch, tmp_path)
    monkeypatch.setattr(command, "ExecutionGate", _RaisingGate)  # overrides _run_env's _StubGate

    with caplog.at_level("ERROR"):
        cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed
    assert registry.get_sample_value("zcrypto_exec_gate_level") == 0  # seeded default, never reached


def test_the_exec_ledger_writes_even_when_the_metrics_port_is_unset(tmp_path, monkeypatch):
    # THE property this task exists to fix: a manual `zcrypto engine run` on the host never sets
    # ZCRYPTO_METRICS_PORT, and the pre-fix code installed the sink INSIDE `if port is not None:` --
    # so a misconfigured/manual engine would journal cycles with no execution record and no error.
    # No registry is built here at all (build_registry/start_metrics_server are left unpatched and
    # must never be called), so this also pins that the gauge half stays correctly inert.
    monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
    registry_calls = []
    monkeypatch.setattr(command, "build_registry", lambda: registry_calls.append(1) or CollectorRegistry())
    engine_cfg = _run_env(monkeypatch, tmp_path)

    completed_at = CYCLE_TS + timedelta(minutes=3)
    result = CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets=dict(TARGETS),
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )

    def _run_and_complete_a_cycle():
        cycle._metrics_sink(result, completed_at, 30.0)

    monkeypatch.setattr(
        "cli.engine.node.build_shadow_node",
        lambda config: types.SimpleNamespace(
            _config=types.SimpleNamespace(timeout_connection=1.5, timeout_reconciliation=2.0),
            trader=types.SimpleNamespace(is_running=True),
            run=_run_and_complete_a_cycle,
            dispose=lambda: None,
        ),
    )

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert registry_calls == [], "no registry may be built when the metrics port is unset"
    assert list((engine_cfg.journal_dir / f"{CYCLE_TS:%Y-%m-%d}").glob("exec-*.json")), (
        "the ledger must not be a side effect of telemetry being switched on"
    )
