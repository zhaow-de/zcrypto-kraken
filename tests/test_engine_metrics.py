"""spec 00069 T4: the engine's `/metrics` tap -- cycle.py's sink mechanism (isolation-tested) and
command.py's gauge holder + startup seeding + `run()` wiring."""

import json
import logging
import re
import socket
import types
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest
import yaml
from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.parser import text_string_to_metric_families
from typer.testing import CliRunner

import cli.engine.command as command
import cli.engine.cycle as cycle
import cli.engine.executor as executor_module
from cli.__main__ import app
from cli.config import AppConfig, DataConfig, EngineConfig, FetchConfig
from cli.engine.command import _CycleGauges, _ExecGauges, _seed_completed_at, _seed_exec_positions, _VenueGauges
from cli.engine.cycle import CycleResult, run_cycle
from cli.engine.errors import EngineJournalError
from cli.engine.execgate import LEVEL_CODE, ExecutionGate, GateLevel, GateVerdict
from cli.engine.instruments import INSTRUMENT_IDS
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json, snapshot_content_hash, to_json, validate_record
from cli.engine.store import BASKET, GRID_INTERVALS, PAIR_KEYS
from cli.engine.venue import VenueStatus
from cli.obs.metrics import METRICS_PORT_ENV_VAR
from cli.ohlc.dataset import to_frame, write_parquet

runner = CliRunner()

UTC = timezone.utc
ASSETS = tuple(sorted(PAIR_KEYS))  # the twelve full symbols
EUR_SYMBOLS = tuple(s for s in BASKET if s.endswith("/EUR"))
BTC_SYMBOLS = tuple(s for s in BASKET if s.endswith("/BTC"))
MODEL_BASES = tuple(s.split("/")[0] for s in EUR_SYMBOLS)
KEY_TO_ASSET = {v: k for k, v in PAIR_KEYS.items()}
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
H4_LAST = CYCLE_TS - timedelta(hours=4)
DAILY_LAST = datetime(2026, 7, 9, tzinfo=UTC)
N_H4, N_DAILY = 6, 4
# Base-keyed going in (the key space select_model_inputs hands the model), symbol-keyed coming out
# with the two /BTC legs at the structural zero (spec 00094 D1) -- the shape run_cycle journals.
MODEL_TARGETS = {base: round(0.1 * (i + 1), 3) for i, base in enumerate(MODEL_BASES)}
TARGETS = {f"{base}/EUR": value for base, value in MODEL_TARGETS.items()} | dict.fromkeys(BTC_SYMBOLS, 0.0)
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
    for (symbol, interval), rows in rows_by.items():
        base, quote = symbol.split("/")
        write_parquet(to_frame(rows), store_dir / base / quote / f"{interval}.parquet")


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
# Base-keyed: sleeve books come back from the builder in the model's own key space.
SLEEVE_FORMING = {
    "B": dict.fromkeys(MODEL_BASES, 0.0),
    "A1": {**dict.fromkeys(MODEL_BASES, 0.0), MODEL_BASES[0]: -0.5},
    "A2": {**dict.fromkeys(MODEL_BASES, 0.0), MODEL_BASES[0]: 0.25, MODEL_BASES[1]: -0.125},
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
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))
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
    store_rows = _store_rows({("ETH/EUR", 240): _series_rows("ETH/EUR", 240, drop_last=1)})
    config = _env(tmp_path, monkeypatch, rows_by=store_rows)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert result.sleeve_gross is None


def test_sink_called_on_a_failed_cycle_with_the_sidecars_own_timing(tmp_path, monkeypatch):
    store_rows = _store_rows({("ETH/EUR", 240): _series_rows("ETH/EUR", 240, drop_last=1)})
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
    store_rows = _store_rows({("ETH/EUR", 240): _series_rows("ETH/EUR", 240, drop_last=1)})
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


@pytest.mark.parametrize(
    ("limit_bound", "expected"),
    [(True, 1.0), (False, 0.0), (None, 0.0)],
    ids=["bound", "clear", "no-answer"],
)
def test_the_limit_bound_counter_moves_only_when_a_limit_actually_bound(limit_bound, expected):
    """T0121's counter. `None` (a failed cycle: no build ran) must be indistinguishable from a clear
    book HERE -- an increment on it would report a limit binding on a boundary that never built one."""
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
        limit_bound=limit_bound,
    )

    gauges.update(result, CYCLE_TS, 1.0)

    assert registry.get_sample_value("zcrypto_engine_limit_bound_total") == expected


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
# moves portfolio gross by an amount only measurement can give. These two series make the composition, and any
# change to it, visible; they do not by themselves say what the gross did.

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


def _write_venue_record(
    journal_dir: Path,
    cycle_ts: datetime,
    *,
    status: str = "ok",
    loaded: int = 10,
    failures: int = 0,
    snapshot_at: datetime | None = None,
) -> None:
    """A raw **schema-1** venue-<HH>.json, written directly (rather than through
    `VenueState`/`write_venue_record`) so this file never has to import `cli.engine.venuestate` ->
    nautilus_trader. The pinned `schema_version: 1` is deliberate v1-reader coverage, not drift
    against the current `VENUE_SCHEMA_VERSION`: every record written before the widening is v1 and
    the startup seed must keep reading them, so a v1 record is exactly what these gauges must
    survive at the deploy boundary. Base-keyed throughout (`ASSET{i}`, no "/"), each instrument
    entry carrying the full v1 key set (base/instrument_id/ordermin/costmin/lot_step/tick_size/
    costmin_source, no `costmin_quote`) -- `_seed_venue_state` now `validate_venue_record`-checks
    every record it reads (T0140 D9), so this fixture's output must itself validate."""
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": 1, "cycle_ts": cycle_ts.isoformat(), "code_version": "test", "status": status}
    if status == "ok":
        doc["state"] = {
            "snapshot_at": (snapshot_at or cycle_ts).isoformat(),
            "instruments": {
                f"ASSET{i}": {
                    "base": f"ASSET{i}",
                    "instrument_id": f"ASSET{i}/EUR.KRAKEN",
                    "ordermin": 0.0001,
                    "costmin": 0.5,
                    "lot_step": 0.00000001,
                    "tick_size": 0.1,
                    "costmin_source": "snapshot-constant",
                }
                for i in range(loaded)
            },
            "positions": {f"ASSET{i}": 0.0 for i in range(loaded)},
            "balances": {"EUR": 1000.0},
        }
        doc["concordance"] = {"ok": failures == 0, "failures": [f"F{i}" for i in range(failures)]}
    else:
        doc["error"] = "no venue snapshot available for this cycle"
    (day_dir / f"venue-{cycle_ts:%H}.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _write_venue_record_v2(
    journal_dir: Path,
    cycle_ts: datetime,
    *,
    status: str = "ok",
    positions: dict[str, float] | None = None,
) -> None:
    """A raw **schema-2** venue-<HH>.json, written directly for the same avoid-nautilus reason
    `_write_venue_record` documents above -- symbol-keyed instruments/positions (the shape
    `validate_venue_record` requires for schema_version 2). Used by the `_seed_exec_positions`
    tests: only a schema_version 2 "ok" record can seed the symbol-labelled positions gauge, so
    these tests need genuine v2 fixtures rather than `_write_venue_record`'s v1 ones."""
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": 2, "cycle_ts": cycle_ts.isoformat(), "code_version": "test", "status": status}
    if status == "ok":
        pos = positions if positions is not None else {"BTC/EUR": 0.0}
        doc["state"] = {
            "snapshot_at": cycle_ts.isoformat(),
            "instruments": {
                symbol: {
                    "symbol": symbol,
                    "instrument_id": f"{symbol}.KRAKEN",
                    "ordermin": 0.0001,
                    "costmin": 0.5,
                    "costmin_quote": symbol.split("/")[1],
                    "lot_step": 0.00000001,
                    "tick_size": 0.1,
                    "costmin_source": "snapshot-constant",
                }
                for symbol in pos
            },
            "positions": pos,
            "balances": {"EUR": 1000.0},
        }
        doc["concordance"] = {"ok": True, "failures": []}
    else:
        doc["error"] = "no venue snapshot available for this cycle"
    (day_dir / f"venue-{cycle_ts:%H}.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


def _write_shape_invalid_venue_record(journal_dir: Path, cycle_ts: datetime) -> None:
    """A v1-SHAPED body (base-keyed instruments/positions, the v1 instrument-entry key set) stamped
    `schema_version: 2` -- refused by `validate_venue_record`'s key-DIRECTION check (schema 2
    demands full-symbol keys), never by an accidental missing/extra key. Proves the D9
    validate-before-status wiring inside `_seed_venue_state`/`_seed_exec_positions` is load-bearing
    and not refactor-erasable: every other fixture in this file now writes schema-valid records (the
    latent-bug fix to `_write_venue_record`), so without this one, deleting either
    `validate_venue_record(doc)` call leaves the whole suite green."""
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": 2,
        "cycle_ts": cycle_ts.isoformat(),
        "code_version": "test",
        "status": "ok",
        "state": {
            "snapshot_at": cycle_ts.isoformat(),
            "instruments": {
                "BTC": {
                    "base": "BTC",
                    "instrument_id": "BTC/EUR.KRAKEN",
                    "ordermin": 0.0001,
                    "costmin": 0.5,
                    "lot_step": 0.00000001,
                    "tick_size": 0.1,
                    "costmin_source": "snapshot-constant",
                }
            },
            "positions": {"BTC": 0.0},
            "balances": {"EUR": 1000.0},
        },
        "concordance": {"ok": True, "failures": []},
    }
    (day_dir / f"venue-{cycle_ts:%H}.json").write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")


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


# --- command.py: _seed_venue_state (spec 00089 D6, cold-review MAJOR 1) ------------------------------


def test_seed_venue_state_returns_none_when_the_journal_is_empty(tmp_path):
    assert command._seed_venue_state(tmp_path / "journal") is None


def test_seed_venue_state_reads_the_newest_ok_record(tmp_path):
    journal_dir = tmp_path / "journal"
    older = datetime(2026, 7, 10, 4, 1, tzinfo=UTC)
    newer = datetime(2026, 7, 10, 8, 1, tzinfo=UTC)
    _write_venue_record(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC), loaded=8, failures=2, snapshot_at=older)
    _write_venue_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), loaded=10, failures=0, snapshot_at=newer)

    seed = command._seed_venue_state(journal_dir)

    assert seed == {"loaded": 10, "expected": len(INSTRUMENT_IDS), "failures": 0, "snapshot_at": newer.isoformat()}


def test_seed_venue_state_an_error_record_never_overrides_the_last_ok_one(tmp_path):
    # An "error" record (00089 D7: no VenueState that cycle) must not overwrite the last REAL
    # snapshot, even though it is chronologically newer -- the same "absence never overwrites a
    # real value" invariant _VenueGauges.update itself enforces for venue=None.
    journal_dir = tmp_path / "journal"
    ok_at = datetime(2026, 7, 10, 4, 1, tzinfo=UTC)
    _write_venue_record(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC), loaded=10, failures=0, snapshot_at=ok_at)
    _write_venue_record(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), status="error")

    seed = command._seed_venue_state(journal_dir)

    assert seed == {"loaded": 10, "expected": len(INSTRUMENT_IDS), "failures": 0, "snapshot_at": ok_at.isoformat()}


def test_seed_venue_state_refuses_a_shape_invalid_record(tmp_path):
    # D9: validate_venue_record is called on every record before status is even consulted -- a
    # v1-shaped body stamped schema_version 2 must never be silently skipped as "not ok", it must
    # raise, because the shape violation itself (not the status) is the thing being refused.
    journal_dir = tmp_path / "journal"
    _write_shape_invalid_venue_record(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC))

    with pytest.raises(EngineJournalError):
        command._seed_venue_state(journal_dir)


# --- command.py: _seed_exec_positions (T0140) -------------------------------------------------------


def test_seed_exec_positions_returns_none_when_the_journal_is_empty(tmp_path):
    assert _seed_exec_positions(tmp_path / "journal") is None


def test_seed_exec_positions_reads_the_newest_ok_records_positions(tmp_path):
    journal_dir = tmp_path / "journal"
    _write_venue_record_v2(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC), positions={"BTC/EUR": 1.0})
    _write_venue_record_v2(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), positions={"BTC/EUR": 2.5, "ETH/EUR": -1.0})

    seed = _seed_exec_positions(journal_dir)

    assert seed == {"BTC/EUR": 2.5, "ETH/EUR": -1.0}


def test_seed_exec_positions_skips_an_error_record_even_when_newer(tmp_path):
    journal_dir = tmp_path / "journal"
    _write_venue_record_v2(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC), positions={"BTC/EUR": 1.0})
    _write_venue_record_v2(journal_dir, datetime(2026, 7, 10, 8, 0, tzinfo=UTC), status="error")

    seed = _seed_exec_positions(journal_dir)

    assert seed == {"BTC/EUR": 1.0}


def test_seed_exec_positions_skips_a_schema_version_1_record(tmp_path):
    # A base-keyed v1 "ok" record cannot honestly seed the symbol-labelled positions gauge -- it
    # must be skipped even though "ok" is otherwise the qualifying status.
    journal_dir = tmp_path / "journal"
    _write_venue_record(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC), loaded=1)

    assert _seed_exec_positions(journal_dir) is None


def test_seed_exec_positions_refuses_a_shape_invalid_record(tmp_path):
    # Same D9 guard, this function's own call site -- must be independently erasable-proof.
    journal_dir = tmp_path / "journal"
    _write_shape_invalid_venue_record(journal_dir, datetime(2026, 7, 10, 4, 0, tzinfo=UTC))

    with pytest.raises(EngineJournalError):
        _seed_exec_positions(journal_dir)


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


# --- command.py: _VenueGauges (spec 00089 D6) --------------------------------------------------------


def _venue_result(venue: dict | None) -> CycleResult:
    return CycleResult(
        status="success",
        cycle_ts=CYCLE_TS,
        record_path=Path("cycle-08.json"),
        sidecar_path=None,
        targets={},
        orders=[],
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
        venue=venue,
    )


def test_venue_gauges_exist_after_seeding():
    reg = CollectorRegistry()
    _VenueGauges(reg)
    assert reg.get_sample_value("zcrypto_venue_snapshot_timestamp_seconds") == 0.0
    assert reg.get_sample_value("zcrypto_venue_instruments_loaded") == 0.0
    # DERIVED from len(INSTRUMENT_IDS), never a literal -- a future basket re-ratification moves one
    # committed place; this pins the CURRENT basket size at 12.
    assert reg.get_sample_value("zcrypto_venue_instruments_expected") == len(INSTRUMENT_IDS) == 12
    assert reg.get_sample_value("zcrypto_venue_concordance_failures") == 0.0


def test_venue_gauges_update_moves_all_four_from_a_cycle_results_venue_summary():
    reg = CollectorRegistry()
    gauges = _VenueGauges(reg)
    snapshot_at = CYCLE_TS + timedelta(minutes=1)
    # 11, not 12: the eager constructor seed (`command.py:623`) also sets this gauge to
    # len(INSTRUMENT_IDS) == 12, so a value equal to the seed can't tell "update() moved it" from
    # "the seed was never touched" -- 11 is a value the seed cannot produce.
    result = _venue_result({"loaded": 9, "expected": 11, "failures": 1, "snapshot_at": snapshot_at.isoformat()})

    gauges.update(result.venue)

    assert reg.get_sample_value("zcrypto_venue_snapshot_timestamp_seconds") == pytest.approx(snapshot_at.timestamp())
    assert reg.get_sample_value("zcrypto_venue_instruments_loaded") == 9.0
    assert reg.get_sample_value("zcrypto_venue_instruments_expected") == 11.0
    assert reg.get_sample_value("zcrypto_venue_concordance_failures") == 1.0


def test_venue_gauges_update_with_a_venueless_cycle_result_moves_nothing():
    # 00089 D7: absence must look STALE, not fresh -- the timestamp keeps its last real value rather
    # than being reset or left untouched-but-fresh-looking.
    reg = CollectorRegistry()
    gauges = _VenueGauges(reg)
    snapshot_at = CYCLE_TS + timedelta(minutes=1)
    # 11, not 12 -- same reason as the update-moves-all-four test above.
    gauges.update(_venue_result({"loaded": 9, "expected": 11, "failures": 1, "snapshot_at": snapshot_at.isoformat()}).venue)

    gauges.update(_venue_result(None).venue)

    assert reg.get_sample_value("zcrypto_venue_snapshot_timestamp_seconds") == pytest.approx(snapshot_at.timestamp())
    assert reg.get_sample_value("zcrypto_venue_instruments_loaded") == 9.0
    assert reg.get_sample_value("zcrypto_venue_instruments_expected") == 11.0
    assert reg.get_sample_value("zcrypto_venue_concordance_failures") == 1.0


# --- run(): opt-in wiring ---------------------------------------------------------------------------


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _fake_node(run=lambda: None):
    """The assembled node as `run()` reaches for it: run and dispose, nothing else."""
    return types.SimpleNamespace(run=run, dispose=lambda: None)


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
    passed (e.g. `state_dir` -- the exact silent-failure shape: `journal_dir` instead of
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
    for symbol in BASKET:  # run()'s guard wants every basket leg on both grids; never read (the node is stubbed)
        for interval in GRID_INTERVALS:
            base, quote = symbol.split("/")
            (engine_cfg.store_dir / base / quote).mkdir(parents=True, exist_ok=True)
            (engine_cfg.store_dir / base / quote / f"{interval}.parquet").write_bytes(b"")
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


@contextmanager
def _zcrypto_caplog_attached(caplog):
    """`cli.logging.config.configure()` sets `propagate = False` on the "zcrypto" logger on the
    CLI's first-ever invocation in the process; caplog only auto-attaches its capture handler to a
    logger that is ALREADY non-propagating when the fixture sets up, so a session whose first CLI
    call is one of these tests would otherwise capture nothing. Attach the handler to "zcrypto"
    directly so the assertion holds regardless of test order/selection (same fix as
    `test_cli_verify_replay_failed_hour_logs_at_warning_not_error` in test_archive_replay.py)."""
    zcrypto_logger = logging.getLogger("zcrypto")
    zcrypto_logger.addHandler(caplog.handler)
    try:
        yield
    finally:
        zcrypto_logger.removeHandler(caplog.handler)


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
        with _zcrypto_caplog_attached(caplog), caplog.at_level("ERROR"):
            result = runner.invoke(app, ["engine", "run"])
    finally:
        bad_path.chmod(0o644)  # restore so tmp_path cleanup never depends on the test's outcome

    assert result.exit_code == 0, result.output
    assert node_started == [True]  # build_shadow_node/node.run() was still reached
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    assert "process_resident_memory_bytes" in body  # process metrics still serve


def test_run_seeds_the_venue_timestamp_from_the_newest_on_disk_record(tmp_path, monkeypatch):
    # Cold-review MAJOR 1: without this seed, a routine restart (which always lands inside the
    # inter-cycle gap, fleet-deploys.md) would leave zcrypto_venue_snapshot_timestamp_seconds at
    # its eager 0.0 default -- read as `time() - 0` ~= 1.77e9 -- and zcrypto-venue-snapshot-stale
    # would false-page "the writer has stopped" against an engine that merely restarted.
    journal_dir = tmp_path / "journal"
    snapshot_at = datetime(2026, 7, 9, 12, 1, tzinfo=UTC)
    _write_venue_record(journal_dir, datetime(2026, 7, 9, 12, 0, tzinfo=UTC), loaded=9, failures=1, snapshot_at=snapshot_at)

    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _run_env(monkeypatch, tmp_path)

    result = runner.invoke(app, ["engine", "run"])
    assert result.exit_code == 0, result.output

    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    families = {family.name: family for family in text_string_to_metric_families(body)}
    assert families["zcrypto_venue_snapshot_timestamp_seconds"].samples[0].value == pytest.approx(
        snapshot_at.timestamp()
    )  # seeded, not the eager 0.0 (1970) default
    assert families["zcrypto_venue_instruments_loaded"].samples[0].value == 9.0
    assert families["zcrypto_venue_concordance_failures"].samples[0].value == 1.0


def test_run_survives_an_unreadable_venue_record_at_metrics_seed_time(tmp_path, monkeypatch, caplog):
    # Mirrors test_run_survives_an_unreadable_journal_record_at_metrics_seed_time above, for the
    # venue seed's own read: an unreadable venue-<HH>.json (bad mode/ownership on the bind mount)
    # must degrade -- logged, gauges left at their eager defaults -- never abort run().
    journal_dir = tmp_path / "journal"
    _write_venue_record(journal_dir, datetime(2026, 7, 9, 12, 0, tzinfo=UTC))
    bad_path = journal_dir / "2026-07-09" / "venue-12.json"
    bad_path.chmod(0o000)

    port = _free_port()
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(port))
    _run_env(monkeypatch, tmp_path)
    node_started = []
    monkeypatch.setattr("cli.engine.node.build_shadow_node", lambda config: (node_started.append(True), _fake_node())[1])

    try:
        with _zcrypto_caplog_attached(caplog), caplog.at_level("ERROR"):
            result = runner.invoke(app, ["engine", "run"])
    finally:
        bad_path.chmod(0o644)  # restore so tmp_path cleanup never depends on the test's outcome

    assert result.exit_code == 0, result.output
    assert node_started == [True]  # build_shadow_node/node.run() was still reached
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2.0) as resp:
        body = resp.read().decode()
    families = {family.name: family for family in text_string_to_metric_families(body)}
    assert families["zcrypto_venue_snapshot_timestamp_seconds"].samples[0].value == 0.0  # left at its eager default


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
        venue={"loaded": 9, "expected": 10, "failures": 1, "snapshot_at": completed_at.isoformat()},
    )

    def _run_and_complete_a_cycle():
        cycle._metrics_sink(result, completed_at, 30.0)  # the same call cycle.py makes post-artifact

    monkeypatch.setattr(
        "cli.engine.node.build_shadow_node",
        lambda config: _fake_node(run=_run_and_complete_a_cycle),
    )

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    (gate_instance,) = _StubGate.instances
    assert gate_instance.state_dir == engine_cfg.journal_dir.parent  # the exact silent-fail shape
    # run() passes venue_reader explicitly rather than relying on ExecutionGate's default, so
    # `monkeypatch.setattr(command, "read_system_status", ...)` is a working seam for tests.
    assert gate_instance.venue_reader is command.read_system_status
    assert list((engine_cfg.journal_dir / f"{CYCLE_TS:%Y-%m-%d}").glob("exec-*.json")), "the sink never wrote an exec record"
    # the startup evaluation alone -- before the cycle above ever ran -- must already have
    # published a truthful restart hold, or a kill switch tripped across a restart would resolve
    # the alert for up to 4h until the next cycle completes.
    assert registry.get_sample_value("zcrypto_exec_restart_hold") == 1
    assert registry.get_sample_value("zcrypto_exec_gate_level") == LEVEL_CODE[GateLevel.REDUCE_ONLY]
    # The venue half of the same sink closure (cold-review MAJOR 2): _VenueGauges.update is tested
    # directly elsewhere with hand-built dicts, but only this test drives run()'s actual composition
    # -- `if venue_gauges is not None: venue_gauges.update(result.venue)` -- so a broken wire (a
    # dropped call, the wrong attribute) fails SILENTLY in production exactly like the exec half would.
    assert registry.get_sample_value("zcrypto_venue_concordance_failures") == 1


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

    with _zcrypto_caplog_attached(caplog), caplog.at_level("ERROR"):
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
        lambda config: _fake_node(run=_run_and_complete_a_cycle),
    )

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert registry_calls == [], "no registry may be built when the metrics port is unset"
    assert list((engine_cfg.journal_dir / f"{CYCLE_TS:%Y-%m-%d}").glob("exec-*.json")), (
        "the ledger must not be a side effect of telemetry being switched on"
    )


# --- command.py: _ExecutionMetrics (the execution families) -------------------------------------


def test_the_order_outcome_labels_cover_every_outcome_the_executor_can_emit():
    """DERIVED from the executor's own call sites, never hand-listed: an outcome the executor emits
    and this label set omits still publishes -- as an unadmitted, unpanelled series nobody watches.
    `ambiguous` is the one that matters. Folding it into `refused` would put back exactly the lie a
    prior ruling removed from the forensic ledger: "refused" asserts no order exists, and after a
    submission whose venue outcome is unknown that claim is unavailable."""
    emitted = set(re.findall(r'_inc_order\("([a-z_]+)"\)', Path(executor_module.__file__).read_text()))
    assert len(emitted) >= 7, f"the call-site scan found only {sorted(emitted)} -- this guard would pass vacuously"
    assert "ambiguous" in emitted, "the executor no longer emits `ambiguous` -- read WHY before touching the label set"
    assert emitted == set(command._EXEC_ORDER_OUTCOMES)


def test_the_liquidity_labels_are_the_venue_enums_own_names():
    """DERIVED from the real `LiquiditySide` and routed through the executor's own emit-site helper,
    because a string-based fake agrees with any rendering that helper produces. The label set must
    be exactly what the venue can report, lower-cased -- a member this tuple omits would spring into
    existence as an unadmitted series on the first live fill that carried it, while the
    pre-registered children read zero for the whole probe window."""
    from nautilus_trader.model import LiquiditySide

    members = tuple(LiquiditySide.variants())  # the class itself is not iterable
    assert len(members) >= 3, f"the enum yielded {[m.name for m in members]} -- this guard would pass vacuously"
    assert {executor_module._liquidity(member).lower() for member in members} == set(command._EXEC_LIQUIDITY_SIDES)

    # And the consequence, measured: a real member mints no child the registry had not already
    # seeded. A numeric label would add `0`/`1`/`2` here and leave the admitted series at zero.
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)
    seeded = {s.labels["liquidity"] for s in _families(registry)["zcrypto_exec_fills_total"].samples}
    for member in members:
        metrics.inc_fill(executor_module._liquidity(member).lower(), None)
    assert {s.labels["liquidity"] for s in _families(registry)["zcrypto_exec_fills_total"].samples} == seeded


def test_every_outcome_and_liquidity_series_exists_before_anything_happens():
    """A Counter's zero is a measured fact ("nothing has been refused yet"), unlike a Gauge's, so
    every label child is registered up front: `rate()` over a series that springs into existence at
    its first event has no baseline, and an absent `rejected` reads identically to a scrape gap."""
    registry = CollectorRegistry()
    command._ExecutionMetrics(registry)

    families = _families(registry)
    outcomes = {s.labels["outcome"]: s.value for s in families["zcrypto_exec_orders_total"].samples}
    assert outcomes == dict.fromkeys(command._EXEC_ORDER_OUTCOMES, 0.0)
    liquidity = {s.labels["liquidity"]: s.value for s in families["zcrypto_exec_fills_total"].samples}
    assert liquidity == dict.fromkeys(command._EXEC_LIQUIDITY_SIDES, 0.0)
    assert registry.get_sample_value("zcrypto_exec_fees_eur_total") == 0.0
    # Labelled and unseeded: no symbol has been named yet, so the family carries no samples at all.
    position_family = next(f for f in registry.collect() if f.name == "zcrypto_exec_position")
    assert position_family.samples == []


def test_the_execution_families_carry_the_names_and_labels_the_keep_regex_admits():
    """Parsed out of the exposition text, not off the objects: the keep-regex and every panel match
    the EXPOSED series name, which for a Counter is not the family name."""
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)

    metrics.inc_order("submitted")
    metrics.inc_fill("maker", 0.42)
    metrics.set_position("BTC/EUR", -1.5)
    metrics.set_realized(-12.25)

    exposed = {
        (sample.name, tuple(sorted(sample.labels.items()))): sample.value
        for family in text_string_to_metric_families(generate_latest(registry).decode())
        for sample in family.samples
    }
    assert exposed[("zcrypto_exec_orders_total", (("outcome", "submitted"),))] == 1.0
    assert exposed[("zcrypto_exec_fills_total", (("liquidity", "maker"),))] == 1.0
    assert exposed[("zcrypto_exec_fees_eur_total", ())] == pytest.approx(0.42)
    assert exposed[("zcrypto_exec_position", (("symbol", "BTC/EUR"),))] == -1.5
    # A Gauge, never a Counter: realized PnL falls.
    assert exposed[("zcrypto_exec_realized_pnl_eur", ())] == -12.25
    metrics.set_realized(-30.0)
    assert registry.get_sample_value("zcrypto_exec_realized_pnl_eur") == -30.0


def test_a_fee_the_caller_could_not_denominate_in_eur_counts_the_fill_but_not_the_money():
    """`zcrypto_exec_fees_eur_total` is EUR by name. A `/BTC` leg's BTC-denominated commission added
    to it would be a number with no unit -- so the fill still counts (it happened) and the fee does
    not. The executor is what decides EUR-or-None; this pins that a None can never reach the total."""
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)

    metrics.inc_fill("taker", None)

    assert registry.get_sample_value("zcrypto_exec_fills_total", {"liquidity": "taker"}) == 1.0
    assert registry.get_sample_value("zcrypto_exec_fees_eur_total") == 0.0


def test_external_events_counter_preregisters_both_dispositions():
    """`unmatched` is the disposition that carries the signal, and it is the one whose ZERO has to be
    a measured fact from the first scrape: an event the engine counted and ignored is the only trace
    a fill on an order this engine's ledger does not vouch for ever leaves. A series that springs
    into existence at the first such event reads identically to a scrape gap right up to the moment
    it matters, and gives `rate()` no baseline to measure the step against. Both children therefore
    exist at 0 before anything happens, and an event moves EXACTLY one of them -- a helper that
    incremented both, or the wrong one, would report a matched adoption as an unvouched stranger."""
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)

    assert command._EXEC_EXTERNAL_DISPOSITIONS == ("matched", "unmatched")
    before = {s.labels["disposition"]: s.value for s in _families(registry)["zcrypto_exec_external_events_total"].samples}
    assert before == dict.fromkeys(command._EXEC_EXTERNAL_DISPOSITIONS, 0.0)

    metrics.inc_external("unmatched")

    after = {s.labels["disposition"]: s.value for s in _families(registry)["zcrypto_exec_external_events_total"].samples}
    assert after == {"matched": 0.0, "unmatched": 1.0}


def test_the_external_disposition_labels_cover_every_disposition_the_executor_can_emit():
    """DERIVED from the executor's own call sites, the sibling outcome pin's reasoning exactly: a
    disposition the executor emits and this label set omits still publishes -- as an unadmitted,
    unpanelled series nobody watches -- and `unmatched` is the one whose entire purpose is to be
    watched. The tuple could only be hand-listed correctly once; this is what keeps it correct."""
    emitted = set(re.findall(r'_inc_external\("([a-z_]+)"\)', Path(executor_module.__file__).read_text()))
    assert len(emitted) >= 2, f"the call-site scan found only {sorted(emitted)} -- this guard would pass vacuously"
    assert emitted == set(command._EXEC_EXTERNAL_DISPOSITIONS)


def test_inc_external_routes_to_the_installed_metrics_and_is_a_noop_without_one():
    """The executor-side half of the plumbing, `_inc_order`'s contract exactly: unset (a one-shot
    subcommand, or any test that installs no hooks) it must be a silent no-op rather than an
    AttributeError on the live trade path, and installed it must reach the SAME counter the
    exporter serves."""
    assert executor_module._metrics is None  # no hooks installed -- the default the guard protects
    executor_module._inc_external("matched")  # must not raise

    registry = CollectorRegistry()
    executor_module.set_executor_hooks(metrics=command._ExecutionMetrics(registry))
    executor_module._inc_external("matched")

    assert registry.get_sample_value("zcrypto_exec_external_events_total", {"disposition": "matched"}) == 1.0
    assert registry.get_sample_value("zcrypto_exec_external_events_total", {"disposition": "unmatched"}) == 0.0


# --- the D5 ordering: a failing ledger writer starves the heartbeat -----------------------------

ALERTS_YAML = Path(__file__).resolve().parents[1] / "infra/grafana/alerts.yaml"


def _staleness_threshold_seconds() -> float:
    """The DEPLOYED evaluator threshold for `zcrypto-engine-exec-not-evaluated`, read out of the
    rule rather than remembered: a test carrying a copy of the number proves nothing about the rule
    that actually fires, and would keep passing after the rule was retuned."""
    rule = next(r for r in yaml.safe_load(ALERTS_YAML.read_text())["rules"] if r["uid"] == "zcrypto-engine-exec-not-evaluated")
    (expr_node,) = [d for d in rule["data"] if "expr" in d["model"]]
    assert "zcrypto_exec_last_evaluation_timestamp_seconds" in expr_node["model"]["expr"]
    (condition,) = [d for d in rule["data"] if d["refId"] == rule["condition"]][0]["model"]["conditions"]
    assert condition["evaluator"]["type"] == "gt"
    (threshold,) = condition["evaluator"]["params"]
    return float(threshold)


def _raise(*args, **kwargs):
    raise OSError("read-only file system")


def _sink_result(cycle_ts: datetime) -> CycleResult:
    return CycleResult(
        status="success",
        cycle_ts=cycle_ts,
        record_path=Path("cycle.json"),
        sidecar_path=None,
        targets=None,
        orders=None,
        reason=None,
        offending_pairs=None,
        sleeve_gross=None,
    )


def test_a_raising_ledger_writer_freezes_the_heartbeat_and_the_staleness_condition_goes_true(tmp_path, monkeypatch):
    """The monitoring-gap discharge, read by VALUE: the sink writes the ledger BEFORE any gauge, so
    a persistently failing `write_exec_record` starves
    `zcrypto_exec_last_evaluation_timestamp_seconds` and the deployed staleness rule's condition
    goes true. That ordering is the whole reason the gap is monitored rather than merely documented
    -- reverse it and the ledger could fail silently for days behind a heartbeat that keeps ticking."""
    registry = CollectorRegistry()
    gate = ExecutionGate(
        armed_in_config=False,
        state_dir=tmp_path,
        venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now),
    )
    exec_gauges = _ExecGauges(registry)
    t0 = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    sink = command._make_exec_sink(gate, tmp_path / "journal", None, exec_gauges, None)

    sink(_sink_result(t0), t0, 1.0)  # one healthy cycle: the heartbeat is t0
    assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == t0.timestamp()

    monkeypatch.setattr(command, "write_exec_record", _raise)
    t1 = t0 + timedelta(hours=8)
    try:
        sink(_sink_result(t1), t1, 1.0)
    except OSError:
        pass  # in production cycle.py's _update_metrics swallows exactly this raise -- same effect

    frozen = registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds")
    assert frozen == t0.timestamp(), "the heartbeat moved past a cycle whose ledger record was never written"
    assert t1.timestamp() - frozen > _staleness_threshold_seconds()


def test_the_sink_moves_the_heartbeat_when_the_ledger_write_succeeds():
    """The control for the freeze above: without it, a sink that never touched the gauge at all
    would pass that test for the wrong reason."""
    registry = CollectorRegistry()
    exec_gauges = _ExecGauges(registry)
    t0 = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    t1 = t0 + timedelta(hours=8)
    gate = ExecutionGate(
        armed_in_config=False,
        state_dir=Path("/nonexistent"),
        venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now),
    )
    with pytest.MonkeyPatch.context() as mp:
        writes = []
        mp.setattr(command, "write_exec_record", lambda *a, **k: writes.append(a))
        sink = command._make_exec_sink(gate, Path("/nonexistent"), None, exec_gauges, None)
        sink(_sink_result(t0), t0, 1.0)
        sink(_sink_result(t1), t1, 1.0)

    assert len(writes) == 2
    assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == t1.timestamp()


# --- run(): the execution metrics, their seed, and the executor hooks ---------------------------


def test_run_builds_the_execution_metrics_seeds_positions_and_installs_the_executor_hooks(tmp_path, monkeypatch):
    """The composition nothing else drives. A dropped `set_executor_hooks` call is silent in
    production -- the executor's own hooks are None-safe by design, so every order would be placed
    exactly as before while `zcrypto_exec_orders_total` sat at zero and read as "nothing traded"."""
    registry = CollectorRegistry()
    monkeypatch.setattr(command, "build_registry", lambda: registry)
    monkeypatch.setattr(command, "start_metrics_server", lambda port, reg: True)
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    engine_cfg = _run_env(monkeypatch, tmp_path)
    _write_venue_record_v2(engine_cfg.journal_dir, CYCLE_TS, positions={"BTC/EUR": 2.5, "ETH/EUR": -1.0})
    installed = {}
    monkeypatch.setattr(executor_module, "set_executor_hooks", lambda **kwargs: installed.update(kwargs))

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert registry.get_sample_value("zcrypto_exec_position", {"symbol": "BTC/EUR"}) == 2.5
    assert registry.get_sample_value("zcrypto_exec_position", {"symbol": "ETH/EUR"}) == -1.0
    assert isinstance(installed["metrics"], command._ExecutionMetrics)
    # The verdict hook is _ExecGauges.update -- the executor evaluates the gate before every
    # submission, and those evaluations are the only thing that keeps the heartbeat fresh between
    # cycles.
    assert installed["publish_verdict"] is not None
    # The metrics object the hooks got is the one on the served registry, not a second copy.
    installed["metrics"].inc_order("submitted")
    assert registry.get_sample_value("zcrypto_exec_orders_total", {"outcome": "submitted"}) == 1.0


def test_run_installs_the_hooks_with_no_metrics_when_the_exporter_is_off(tmp_path, monkeypatch):
    """The ledger runs with the exporter off, so the executor must too -- with both hooks None
    rather than an unbuilt registry's gauges."""
    monkeypatch.delenv(METRICS_PORT_ENV_VAR, raising=False)
    _run_env(monkeypatch, tmp_path)
    installed = {}
    monkeypatch.setattr(executor_module, "set_executor_hooks", lambda **kwargs: installed.update(kwargs))

    cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert installed == {"publish_verdict": None, "metrics": None}


def test_a_raising_execution_metrics_seed_never_prevents_the_engine_from_starting(tmp_path, monkeypatch, caplog):
    """The isolation guard, constructed: `_seed_exec_positions` reads arbitrary on-disk journal
    artifacts and raises by contract on a malformed one. Telemetry may never kill the engine daemon."""
    registry = CollectorRegistry()
    monkeypatch.setattr(command, "build_registry", lambda: registry)
    monkeypatch.setattr(command, "start_metrics_server", lambda port, reg: True)
    monkeypatch.setenv(METRICS_PORT_ENV_VAR, str(_free_port()))
    _run_env(monkeypatch, tmp_path)
    monkeypatch.setattr(command, "_seed_exec_positions", _raise)

    with _zcrypto_caplog_attached(caplog), caplog.at_level("ERROR"):
        cli_result = runner.invoke(app, ["engine", "run"])

    assert cli_result.exit_code == 0, cli_result.output
    assert any(r.levelno >= 40 for r in caplog.records)  # logged, not silently swallowed
    # The families still exist -- the seed failed, not the registration.
    assert registry.get_sample_value("zcrypto_exec_orders_total", {"outcome": "refused"}) == 0.0


def test_the_tracking_state_series_is_absent_until_a_week_has_been_scored():
    """`last_evaluation`'s reasoning, one gauge over: before the first boundary alert there is no
    verdict to state, and an eagerly-registered 0 is not "nothing yet" on a board -- it is a code
    outside the alphabet, rendering as a legitimate reading of a trip nobody has run."""
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)

    assert "zcrypto_exec_tracking_state" not in _families(registry)

    metrics.set_tracking_state(3)
    assert registry.get_sample_value("zcrypto_exec_tracking_state") == 3.0
    metrics.set_tracking_state(4)
    assert registry.get_sample_value("zcrypto_exec_tracking_state") == 4.0


def test_the_tracking_state_alphabet_never_publishes_zero_and_the_help_names_every_code():
    """DERIVED from the executor's own constants, the order-outcome pin's reasoning: a code the
    executor publishes and the help text does not describe is a number on a board with no meaning,
    and a 0 among them is the one value that reads as a measurement when it is an absence."""
    source = Path(executor_module.__file__).read_text()
    emitted = {int(v) for v in re.findall(r"^_TRACKING_[A-Z_]+ = (\d+)$", source, re.MULTILINE)}
    assert len(emitted) >= 4, f"the constant scan found only {sorted(emitted)} -- this guard would pass vacuously"
    assert 0 not in emitted

    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)
    metrics.set_tracking_state(sorted(emitted)[0])
    documentation = _families(registry)["zcrypto_exec_tracking_state"].documentation
    assert {int(code) for code in re.findall(r"(\d+) = ", documentation)} == emitted


# --- this file's own stub node is a restatement of LiveNode / LiveNodeHandle ---------------------
#
# tests/test_engine_stub_fidelity.py classifies every test double in the engine suite and names the
# guard below; the reasoning that makes it worth having lives there. The names `run()` READS off a
# node are checked against the real class in tests/test_engine_command.py -- one walk over the one
# production module covers both files' stubs, so only the offered direction is owed here.


def test_the_stub_node_offers_nothing_the_real_type_lacks():
    """A stub MISSING something `run()` reads fails loudly the first time a test runs it. A stub
    OFFERING something the real type lacks fails NOTHING -- every test believes the fabricated
    attribute, and production is the only place the read comes back wrong. This stub's sibling in
    tests/test_engine_command.py has already paid for that asymmetry once."""
    from nautilus_trader.live import LiveNode

    stub = _fake_node()
    offered = {name for name in dir(stub) if not name.startswith("__")}
    assert offered, "the stub node offers nothing at all -- the check is vacuous"
    extra = sorted(name for name in offered if not hasattr(LiveNode, name))
    assert extra == [], f"the stub node offers {extra}, which the real LiveNode does not carry"
