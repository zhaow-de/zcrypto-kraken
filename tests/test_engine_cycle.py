import json
import shutil
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cli.config import EngineConfig
from cli.engine import concordance, cycle
from cli.engine.concordance import compare_targets, replay_cycle
from cli.engine.cycle import run_cycle
from cli.engine.errors import EngineError
from cli.engine.journal import CycleRecord, from_json, to_json, validate_record
from cli.engine.store import GRID_INTERVALS, PAIR_KEYS
from cli.ohlc.dataset import read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError

UTC = timezone.utc
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
H4_LAST = CYCLE_TS - timedelta(hours=4)  # the boundary invariant: last 4h stamp == cycle_ts - 4h
DAILY_LAST = datetime(2026, 7, 9, tzinfo=UTC)  # last daily stamp == midnight(cycle_ts) - 1d
N_H4 = 6
N_DAILY = 4
ASSETS = tuple(sorted(PAIR_KEYS))
KEY_TO_ASSET = {v: k for k, v in PAIR_KEYS.items()}
TARGETS = {
    "ADA": 0.05,
    "AVAX": 0.0,
    "BTC": 0.2,
    "DOGE": 0.01,
    "DOT": 0.0,
    "ETH": 0.15,
    "LINK": 0.02,
    "LTC": 0.0,
    "SOL": 0.08,
    "XRP": 0.04,
}


def _base(asset: str) -> float:
    return 100.0 * (1 + ASSETS.index(asset))


def _row(ts: datetime, close: float) -> list:
    # Kraken's real shape: [time, open, high, low, close, vwap, volume, count].
    return [int(ts.timestamp()), str(close), str(close), str(close), str(close), str(close), "1.0", 1]


def _grid_spec(interval: int) -> tuple[datetime, timedelta, int]:
    return (DAILY_LAST, timedelta(days=1), N_DAILY) if interval == 1440 else (H4_LAST, timedelta(hours=4), N_H4)


def _series_rows(asset: str, interval: int, *, drop_last: int = 0, skip: tuple[datetime, ...] = ()) -> list[list]:
    last, step, n = _grid_spec(interval)
    rows = [_row(last - (n - 1 - i) * step, _base(asset) + i) for i in range(n) if last - (n - 1 - i) * step not in skip]
    return rows[: len(rows) - drop_last] if drop_last else rows


def _store_rows(overrides: dict | None = None) -> dict:
    rows = {(a, iv): _series_rows(a, iv) for a in ASSETS for iv in GRID_INTERVALS}
    rows.update(overrides or {})
    return rows


def _write_store(store_dir: Path, rows_by: dict) -> None:
    for (asset, interval), rows in rows_by.items():
        write_parquet(to_frame(rows), store_dir / asset / "EUR" / f"{interval}.parquet")


def _tail_fetch(rows_by: dict):
    """A fetch stub returning each pair x grid's own store tail — overlap-exact, nothing new."""

    def fn(pair_key: str, interval: int) -> list[list]:
        return rows_by[(KEY_TO_ASSET[pair_key], interval)][-2:]

    return fn


class SteppingClock:
    def __init__(self, start: datetime, step: timedelta = timedelta(seconds=10)):
        self._now, self._step = start, step

    def __call__(self) -> datetime:
        now = self._now
        self._now += self._step
        return now


def _clock(step: timedelta = timedelta(seconds=10)) -> SteppingClock:
    return SteppingClock(CYCLE_TS + timedelta(seconds=90), step)


def _fake_builder(targets: dict[str, float], calls: list | None = None):
    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        if calls is not None:
            calls.append((daily_prices, daily_ts, h4_prices, h4_ts))
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods)

    return builder


def _env(tmp_path, monkeypatch, *, rows_by: dict | None = None, nav: float = 1000.0):
    rows_by = rows_by if rows_by is not None else _store_rows()
    store_dir = tmp_path / "store"
    _write_store(store_dir, rows_by)
    config = EngineConfig(store_dir=store_dir, journal_dir=tmp_path / "journal", shadow_nav_eur=nav)
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    calls: list = []
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(TARGETS, calls))
    return config, rows_by, calls


def _journal_reader(root: Path):
    def reader(entry):
        frame = read_parquet(root / entry.path)
        return frame["ts"].to_list(), frame["close"].to_list()

    return reader


# --- happy path ----------------------------------------------------------------------------------


def test_happy_path_writes_validated_success_record(tmp_path, monkeypatch):
    config, rows_by, calls = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert result.cycle_ts == CYCLE_TS
    assert result.reason is None and result.offending_pairs is None and result.sidecar_path is None
    assert result.targets == TARGETS
    assert result.record_path == config.journal_dir / "2026-07-10" / "cycle-08.json"
    assert len(calls) == 1

    record = from_json(result.record_path.read_text())
    validate_record(record)  # the written record passes schema + the boundary invariant
    assert record.schema_version == 1
    assert record.cycle_ts == CYCLE_TS
    assert record.final_targets == TARGETS
    assert record.builder_path == "fast"
    assert record.code_version
    assert record.started_at.tzinfo is not None and record.completed_at.tzinfo is not None
    assert record.started_at <= record.completed_at

    assert len(record.snapshots) == len(PAIR_KEYS) * len(GRID_INTERVALS)
    for entry in record.snapshots:
        assert not Path(entry.path).is_absolute()  # relative to journal_dir
        assert entry.path.startswith("2026-07-10/snapshots/cycle-08/")
        assert (config.journal_dir / entry.path).exists()


def test_happy_path_round_trips_through_replay_cycle(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    replayed = replay_cycle(record, _journal_reader(config.journal_dir), path="fast")

    assert compare_targets(record.final_targets, replayed).passed


# --- failure sidecars ----------------------------------------------------------------------------


def test_persistently_lagging_tail_exhausts_reserve_as_refresh_deadline(tmp_path, monkeypatch):
    # A lagging daily tail the venue never heals gets the FULL retry budget (settle-verify covers
    # both grids), then honestly fails as refresh_deadline naming the pair -- not an instant
    # stale_pair with unused reserve.
    rows_by = _store_rows({("DOGE", 1440): _series_rows("DOGE", 1440, drop_last=1)})  # daily tail one bar behind
    stale_fetch = {(a, iv): rows[-2:] for (a, iv), rows in rows_by.items()}  # fetch keeps returning the stale tail
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=lambda k, iv: stale_fetch[(KEY_TO_ASSET[k], iv)], clock=_clock())

    assert result.status == "failed"
    assert result.reason == "refresh_deadline"
    assert result.offending_pairs == ("DOGE",)
    assert result.record_path is None and result.targets is None and result.orders is None
    assert calls == []  # the build is skipped
    assert result.sidecar_path == config.journal_dir / "2026-07-10" / "failed-cycle-08.json"
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "refresh_deadline"
    assert sidecar["offending_pairs"] == ["DOGE"]
    for key in ("cycle_ts", "attempted_at", "completed_at"):
        assert datetime.fromisoformat(sidecar[key]).tzinfo is not None  # ISO-8601 aware-UTC
    assert not (config.journal_dir / "2026-07-10" / "snapshots").exists()
    assert not (config.journal_dir / "2026-07-10" / "cycle-08.json").exists()


def test_stale_pair_sidecar_as_defense_in_depth(tmp_path, monkeypatch):
    # With settle-verify covering both grids, _stale_pairs is the belt-and-braces invariant: it can
    # fire only if settle reports clean while the raw read disagrees (a store race). Simulate that
    # by patching the settle check; the invariant must still catch it and write the stale_pair
    # sidecar rather than feeding a stale book to the builder.
    import cli.engine.cycle as cycle_mod

    rows_by = _store_rows({("DOGE", 1440): _series_rows("DOGE", 1440, drop_last=1)})
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)
    monkeypatch.setattr(cycle_mod, "_settle_pending", lambda store_dir, cycle_ts: {})

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "failed"
    assert result.reason == "stale_pair"
    assert result.offending_pairs == ("DOGE",)
    assert calls == []
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "stale_pair"


def test_refresh_deadline_writes_sidecar(tmp_path, monkeypatch):
    store_rows = _store_rows({("ETH", 240): _series_rows("ETH", 240, drop_last=1)})
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=store_rows)

    # The fetch keeps returning the lagging tail: the cycle_ts - 4h bar never commits.
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert result.reason == "refresh_deadline"
    assert result.offending_pairs == ("ETH",)
    assert calls == []
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "refresh_deadline"
    assert sidecar["offending_pairs"] == ["ETH"]
    assert not (config.journal_dir / "2026-07-10" / "snapshots").exists()
    assert not (config.journal_dir / "2026-07-10" / "cycle-08.json").exists()


# --- settle-verify -------------------------------------------------------------------------------


class SettleFetch:
    """First 4h fetch for the lagging pair returns rows WITHOUT the boundary bar (a successful fetch
    of a not-yet-committed candle); the retry returns it."""

    def __init__(self, rows_by: dict, lag_asset: str):
        self.rows_by, self.lag_asset, self.lag_h4_calls = rows_by, lag_asset, 0

    def __call__(self, pair_key: str, interval: int) -> list[list]:
        asset = KEY_TO_ASSET[pair_key]
        rows = self.rows_by[(asset, interval)]
        if asset == self.lag_asset and interval == 240:
            self.lag_h4_calls += 1
            if self.lag_h4_calls == 1:
                return rows[-3:-1]
        return rows[-2:]


def test_settle_verify_refetches_a_not_yet_committed_candle(tmp_path, monkeypatch):
    full = _store_rows()
    store_rows = _store_rows({("BTC", 240): _series_rows("BTC", 240, drop_last=1)})  # store lags one 4h bar
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=store_rows)
    fetch = SettleFetch(full, "BTC")

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=fetch, clock=_clock())

    assert result.status == "success"
    assert fetch.lag_h4_calls == 2  # the first fetch settled nothing; the per-pair retry brought the bar
    assert len(calls) == 1


class FlakyFetch:
    def __init__(self, rows_by: dict):
        self.rows_by, self.calls = rows_by, 0

    def __call__(self, pair_key: str, interval: int) -> list[list]:
        self.calls += 1
        if self.calls == 1:
            raise OHLCError("transport failure")
        return self.rows_by[(KEY_TO_ASSET[pair_key], interval)][-2:]


def test_transport_error_retries_within_the_reserve(tmp_path, monkeypatch):
    config, rows_by, calls = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=FlakyFetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert len(calls) == 1


# --- intended orders -----------------------------------------------------------------------------


def test_first_cycle_orders_start_flat(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    expected_assets = [a for a in ASSETS if TARGETS[a] != 0.0]
    assert [o["asset"] for o in result.orders] == expected_assets
    for order in result.orders:
        asset = order["asset"]
        price = _base(asset) + N_H4 - 1  # the 4h close of the bar stamped cycle_ts - 4h
        assert order["side"] == "buy"  # flat previous book, all deltas positive
        assert order["price"] == price
        assert order["notional_eur"] == pytest.approx(TARGETS[asset] * 1000.0)
        assert order["quantity"] == pytest.approx(TARGETS[asset] * 1000.0 / price)

    lines = [json.loads(line) for line in (config.journal_dir / "2026-07-10" / "orders.jsonl").read_text().splitlines()]
    header = lines[0]
    assert header["cycle_ts"] == CYCLE_TS.isoformat()
    assert header["previous_cycle_ts"] is None
    assert "flat" in header["note"]
    assert lines[1:] == result.orders


def _success_record_json(boundary: datetime, targets: dict[str, float]) -> str:
    # A minimal previous-record fixture: run_cycle only reads final_targets back via from_json.
    record = CycleRecord(
        schema_version=1,
        cycle_ts=boundary,
        snapshots=(),
        final_targets=dict(targets),
        started_at=boundary,
        completed_at=boundary + timedelta(minutes=2),
        code_version="test",
        builder_path="fast",
    )
    return to_json(record)


def test_orders_cross_gap_to_the_last_successful_record(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    prev_boundary = CYCLE_TS - timedelta(hours=12)  # 2026-07-09 20:00
    prev_targets = dict.fromkeys(TARGETS, 0.0) | {"BTC": 0.3, "ETH": 0.15}
    prev_dir = config.journal_dir / "2026-07-09"
    prev_dir.mkdir(parents=True)
    (prev_dir / "cycle-20.json").write_text(_success_record_json(prev_boundary, prev_targets))
    # The immediately preceding boundary failed, the one before it is missing entirely.
    day_dir = config.journal_dir / "2026-07-10"
    day_dir.mkdir(parents=True)
    (day_dir / "failed-cycle-04.json").write_text(json.dumps({"reason": "stale_pair"}))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    by_asset = {o["asset"]: o for o in result.orders}
    assert by_asset["BTC"]["side"] == "sell"  # 0.2 - 0.3 < 0
    assert by_asset["BTC"]["notional_eur"] == pytest.approx(0.1 * 1000.0)
    assert "ETH" not in by_asset  # delta vs the gap-crossed previous is exactly 0 -- not vs a flat book
    header = json.loads((day_dir / "orders.jsonl").read_text().splitlines()[0])
    assert header["previous_cycle_ts"] == prev_boundary.isoformat()
    assert "gap" in header["note"]


def test_order_arithmetic_delta_times_nav_over_h4_close(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch, nav=2500.0)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    btc = next(o for o in result.orders if o["asset"] == "BTC")
    price = _base("BTC") + N_H4 - 1  # 305.0, the close of the bar stamped cycle_ts - 4h
    assert btc["price"] == price
    assert btc["notional_eur"] == pytest.approx(0.2 * 2500.0)
    assert btc["quantity"] == pytest.approx(0.2 * 2500.0 / price)


# --- union alignment + relocation ----------------------------------------------------------------


def test_union_alignment_journals_none_at_absences_and_replays_clean(tmp_path, monkeypatch):
    gap_ts = H4_LAST - timedelta(hours=8)
    rows_by = _store_rows({("DOGE", 240): _series_rows("DOGE", 240, skip=(gap_ts,))})  # a venue gap
    config, rows_by, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())
    assert result.status == "success"

    # The builder saw the union shape: one shared calendar per grid, None at DOGE's absence.
    daily_prices, daily_ts, h4_prices, h4_ts = calls[0]
    assert len(h4_ts) == N_H4 and len(daily_ts) == N_DAILY
    assert all(len(series) == N_H4 for series in h4_prices.values())
    assert all(len(series) == N_DAILY for series in daily_prices.values())
    gap_index = h4_ts.index(gap_ts)
    assert h4_prices["DOGE"][gap_index] is None
    assert all(c is not None for c in h4_prices["BTC"])

    # The journaled DOGE 4h snapshot carries the union calendar with the None close.
    frame = read_parquet(config.journal_dir / "2026-07-10" / "snapshots" / "cycle-08" / "DOGE-240.parquet")
    assert frame["ts"].to_list() == h4_ts
    assert frame["close"].to_list()[gap_index] is None

    # And it replays clean.
    record = from_json(result.record_path.read_text())
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    replayed = replay_cycle(record, _journal_reader(config.journal_dir), path="fast")
    assert compare_targets(record.final_targets, replayed).passed


def test_journal_relocation_round_trip(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    new_root = tmp_path / "relocated-journal"
    shutil.move(str(config.journal_dir), str(new_root))

    record = from_json((new_root / "2026-07-10" / "cycle-08.json").read_text())
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(TARGETS))
    replayed = replay_cycle(record, _journal_reader(new_root), path="fast")
    assert compare_targets(record.final_targets, replayed).passed


# --- the aware-UTC boundary ----------------------------------------------------------------------


def test_naive_cycle_ts_rejected(tmp_path, monkeypatch):
    config, rows_by, calls = _env(tmp_path, monkeypatch)

    with pytest.raises(EngineError, match="aware"):
        run_cycle(CYCLE_TS.replace(tzinfo=None), config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert not config.journal_dir.exists()
    assert calls == []


def test_off_grid_cycle_ts_rejected(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    with pytest.raises(EngineError, match="4h"):
        run_cycle(CYCLE_TS + timedelta(hours=1), config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert not config.journal_dir.exists()


def test_naive_clock_rejected(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    with pytest.raises(EngineError, match="clock"):
        run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=lambda: datetime(2026, 7, 10, 8, 1, 30))

    assert not config.journal_dir.exists()


def test_aware_non_utc_cycle_ts_normalized(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    cest = timezone(timedelta(hours=2))

    result = run_cycle(CYCLE_TS.astimezone(cest), config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert result.cycle_ts == CYCLE_TS
    assert result.cycle_ts.utcoffset() == timedelta(0)
    assert result.record_path == config.journal_dir / "2026-07-10" / "cycle-08.json"
    assert from_json(result.record_path.read_text()).cycle_ts == CYCLE_TS


# --- midnight-boundary settle (the iter-083 Task-2 review's catch) --------------------------------


def test_settle_pending_covers_the_daily_grid_at_midnight_boundaries(tmp_path):
    """At a 00:00 boundary the NEW daily bar settles like the 4h one; checking only the 4h tail
    would burn the reserve and journal an avoidable stale_pair. Both grids feed the pending set."""
    from cli.engine.cycle import _settle_pending

    midnight = datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
    store = tmp_path / "store"
    h4_last, daily_last = midnight - timedelta(hours=4), midnight - timedelta(days=1)
    for asset in ASSETS:
        h4_rows = [_row(h4_last - (5 - i) * timedelta(hours=4), _base(asset) + i) for i in range(6)]
        daily_rows = [_row(daily_last - (3 - i) * timedelta(days=1), _base(asset) + i) for i in range(4)]
        if asset == "BTC":
            daily_rows = daily_rows[:-1]  # the new daily bar not yet committed
        write_parquet(to_frame(h4_rows), store / asset / "EUR" / "240.parquet")
        write_parquet(to_frame(daily_rows), store / asset / "EUR" / "1440.parquet")

    assert _settle_pending(store, midnight) == {"BTC": PAIR_KEYS["BTC"]}

    # the settled daily bar clears the pending set
    fresh = [_row(daily_last - (3 - i) * timedelta(days=1), _base("BTC") + i) for i in range(4)]
    write_parquet(to_frame(fresh), store / "BTC" / "EUR" / "1440.parquet")
    assert _settle_pending(store, midnight) == {}

    # regression: at a NON-midnight boundary the (older) daily expectation is already satisfied
    non_midnight = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
    ok_store = tmp_path / "store2"
    for asset in ASSETS:
        h4 = [_row(non_midnight - timedelta(hours=4) - (5 - i) * timedelta(hours=4), 1.0 + i) for i in range(6)]
        daily = [_row(datetime(2026, 7, 9, tzinfo=UTC) - (3 - i) * timedelta(days=1), 1.0 + i) for i in range(4)]
        write_parquet(to_frame(h4), ok_store / asset / "EUR" / "240.parquet")
        write_parquet(to_frame(daily), ok_store / asset / "EUR" / "1440.parquet")
    assert _settle_pending(ok_store, non_midnight) == {}
