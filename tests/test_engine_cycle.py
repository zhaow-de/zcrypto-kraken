import json
import math
import shutil
import types
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cli.config import EngineConfig
from cli.engine import concordance, cycle
from cli.engine.concordance import compare_targets, replay_cycle
from cli.engine.cycle import _code_version, _expand_to_basket, run_cycle, select_model_inputs, symbol_keyed_targets
from cli.engine.errors import EngineError
from cli.engine.instruments import COSTMIN, INSTRUMENT_IDS
from cli.engine.journal import SCHEMA_VERSION, CycleRecord, from_json, to_json, validate_record
from cli.engine.store import BASKET, GRID_INTERVALS, PAIR_KEYS, read_store_series
from cli.engine.venuestate import InstrumentConstraints, VenueState
from cli.ohlc.dataset import read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError
from cli.portfolio import build_crossfreq_system_fast
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

UTC = timezone.utc
CYCLE_TS = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
H4_LAST = CYCLE_TS - timedelta(hours=4)  # the boundary invariant: last 4h stamp == cycle_ts - 4h
DAILY_LAST = datetime(2026, 7, 9, tzinfo=UTC)  # last daily stamp == midnight(cycle_ts) - 1d
N_H4 = 6
N_DAILY = 4
ASSETS = tuple(sorted(PAIR_KEYS))  # the twelve full symbols, sorted
EUR_SYMBOLS = tuple(s for s in BASKET if s.endswith("/EUR"))  # the ten the model actually sees
BTC_SYMBOLS = tuple(s for s in BASKET if s.endswith("/BTC"))
KEY_TO_ASSET = {v: k for k, v in PAIR_KEYS.items()}
# What the (unwidened, ten-asset) model emits -- base-keyed, because that is the key space
# select_model_inputs hands it and the only one any sleeve ever works in.
MODEL_TARGETS = {
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
# What the cycle journals: the same ten values on their /EUR symbols, plus the two /BTC legs at the
# structural zero (spec 00094 D1).
TARGETS = {f"{base}/EUR": value for base, value in MODEL_TARGETS.items()} | dict.fromkeys(BTC_SYMBOLS, 0.0)


def _base(symbol: str) -> float:
    return 100.0 * (1 + ASSETS.index(symbol))


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
    for (symbol, interval), rows in rows_by.items():
        base, quote = symbol.split("/")
        write_parquet(to_frame(rows), store_dir / base / quote / f"{interval}.parquet")


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
    """Keyed by whatever it is handed, which on BOTH sides of the round trip is
    `select_model_inputs`' BASE keys -- so `targets` is MODEL_TARGETS everywhere. The symbol-keyed
    TARGETS appear only AFTER `_expand_to_basket`, which this stub never stands in for."""

    def builder(daily_prices, daily_ts, h4_prices, h4_ts, *, config=None):
        if calls is not None:
            calls.append((daily_prices, daily_ts, h4_prices, h4_ts))
        n_periods = len(h4_ts) - 1
        final = {a: [0.0] * n_periods + [targets[a]] for a in h4_prices}
        # The real builder's three fixed-weight sleeves; run_cycle reads the forming row of each.
        sleeves = {name: {a: [0.0] * n_periods + [targets[a]] for a in h4_prices} for name in ("B", "A1", "A2")}
        return types.SimpleNamespace(final_targets=final, n_periods=n_periods, sleeve_positions=sleeves)

    return builder


def _env(tmp_path, monkeypatch, *, rows_by: dict | None = None, nav: float = 1000.0):
    rows_by = rows_by if rows_by is not None else _store_rows()
    store_dir = tmp_path / "store"
    _write_store(store_dir, rows_by)
    config = EngineConfig(store_dir=store_dir, journal_dir=tmp_path / "journal", shadow_nav_eur=nav)
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    calls: list = []
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS, calls))
    return config, rows_by, calls


def _journal_reader(root: Path):
    def reader(entry):
        frame = read_parquet(root / entry.path)
        return frame["ts"].to_list(), frame["close"].to_list()

    return reader


def _adversarial_venue_state() -> VenueState:
    """A VenueState hostile to the read-only pin: every ordermin/costmin sits far above any order
    the fixture produces, and positions/balances carry large, non-flat values that would visibly
    move targets if netted. A permissive VenueState would pass even if run_cycle consulted it."""
    instruments = {
        symbol: InstrumentConstraints(
            symbol=symbol,
            instrument_id=INSTRUMENT_IDS[symbol],
            ordermin=1_000_000.0,
            costmin=1_000_000.0,
            # Read per symbol from the committed constant (spec 00094 D4), never a blanket "EUR":
            # this fixture spans all twelve legs, and a blanket quote would bake a denomination lie
            # into exactly the two /BTC legs the field exists to protect.
            costmin_quote=COSTMIN[symbol][1],
            lot_step=0.00000001,
            tick_size=0.01,
        )
        for symbol in ASSETS
    }
    return VenueState(
        snapshot_at=CYCLE_TS,
        instruments=instruments,
        positions=dict.fromkeys(ASSETS, 1_000.0),
        balances={"EUR": 1_000_000.0},
    )


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
    assert record.schema_version == SCHEMA_VERSION
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


# --- the journaled NAV and position (T0150) -------------------------------------------------------


def test_the_success_record_journals_the_nav_it_priced_against(tmp_path, monkeypatch):
    """NAV sets BOTH halves of drift -- a target is `weight * nav / close` and the drift divides by
    nav -- so a week scored later must use the NAV that was live when it traded, not whatever the
    config says at scoring time."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    validate_record(record)
    assert record.nav == config.shadow_nav_eur


def test_the_success_record_journals_a_base_keyed_position_from_venue_state(tmp_path, monkeypatch):
    """`held` is the real book, so it comes from the venue read, not the model. BASE-keyed over the
    /EUR legs -- the model's key space, the same narrowing `closes` gets -- while VenueState itself
    is SYMBOL-keyed."""
    from cli.engine.venuestate import VenueState

    config, rows_by, _ = _env(tmp_path, monkeypatch)
    vs = VenueState(
        snapshot_at=CYCLE_TS,
        instruments={},
        positions={"BTC/EUR": 0.5, "ETH/EUR": -2.0, "ETH/BTC": 9.0},
        balances={"EUR": 100.0},
    )

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=vs)

    record = from_json(result.record_path.read_text())
    validate_record(record)
    # ETH/BTC is dropped: it is not in the model's key space, and folding it into "ETH" would
    # double-count the same base under two quotes.
    assert record.held == {"BTC": 0.5, "ETH": -2.0}


def test_a_non_finite_venue_quantity_journals_no_position_rather_than_failing_the_record(tmp_path, monkeypatch):
    """A non-finite quantity must not reach the record, and must not take the cycle down with it:
    venue truth never blocks the cycle, and absence is the honest answer."""
    from cli.engine.venuestate import VenueState

    config, rows_by, _ = _env(tmp_path, monkeypatch)
    vs = VenueState(
        snapshot_at=CYCLE_TS,
        instruments={},
        positions={"BTC/EUR": float("nan"), "ETH/EUR": -2.0},
        balances={"EUR": 100.0},
    )

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=vs)

    record = from_json(result.record_path.read_text())
    validate_record(record)
    assert record.held is None


def test_a_cycle_without_a_venue_read_journals_no_position(tmp_path, monkeypatch):
    """`venue_state` is None whenever the snapshot raised -- the node logs and proceeds. Absence is
    the honest answer; a zeroed book would read as FLAT, which is a real position and not the same
    as unknown."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    assert record.held is None


# --- the journaled forming-row closes ------------------------------------------------------------


def test_the_success_record_journals_the_forming_row_closes(tmp_path, monkeypatch):
    """The artifact carries the 4h close each model base was priced at, so realized drift is
    measurable at a boundary without replaying the cycle (a replay is minutes, not seconds)."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    validate_record(record)
    assert set(record.closes) == {s.split("/")[0] for s in EUR_SYMBOLS}
    assert set(record.final_targets) == set(ASSETS)
    # The forming row is the LAST 4h close. The first 4h close and the last DAILY close are the two
    # wrong series this pins away from, both of which a base-keyed ten-entry dict would satisfy.
    assert record.closes == {s.split("/")[0]: _base(s) + (N_H4 - 1) for s in EUR_SYMBOLS}


def test_a_missing_forming_row_close_fails_the_cycle(tmp_path, monkeypatch):
    """A cycle that cannot price its own forming row is refused rather than journaled with a hole.

    Nothing on the TRADE path makes this refusal: `replay_cycle` extracts no closes at all, so such
    a cycle replays and passes the gate cleanly; only `feeders.replay_stages`, the reports path,
    refuses the same input. Do not read the guard as duplicating a check downstream.

    Constructed at the contraction seam: after the staleness check every EUR leg carries the
    boundary stamp, so nothing a store fixture can express reaches this arm."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    real = cycle.select_model_inputs

    def holed(series):
        ts, prices = real(series)
        return ts, prices | {"BTC": prices["BTC"][:-1] + [None]}

    monkeypatch.setattr(cycle, "select_model_inputs", holed)

    with pytest.raises(EngineError, match="forming row"):
        run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    day_dir = config.journal_dir / "2026-07-10"
    assert not (day_dir / "cycle-08.json").exists()
    # Refused BEFORE the orders are appended: an orders.jsonl with no record behind it is a book the
    # engine believes it moved and cannot account for.
    assert not (day_dir / "orders.jsonl").exists()


@pytest.mark.parametrize("bad", [-5.0, 0.0, float("nan"), float("inf")])
def test_an_unusable_forming_row_close_fails_the_cycle_before_the_orders(tmp_path, monkeypatch, bad):
    """The early guard is a SUPERSET of validate_record's closes checks, and must be: validate_record
    runs on the CycleRecord -- after _append_orders has written orders.jsonl -- so a close caught
    only there leaves an orders block with no cycle-<HH>.json behind it, which the next boundary's
    _previous_success globs straight past."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    real = cycle.select_model_inputs

    def spoiled(series):
        ts, prices = real(series)
        return ts, prices | {"BTC": prices["BTC"][:-1] + [bad]}

    monkeypatch.setattr(cycle, "select_model_inputs", spoiled)

    with pytest.raises(EngineError) as excinfo:
        run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    # The FILE assertions come first: a narrowed guard still raises (validate_record's
    # EngineJournalError IS an EngineError), so only the artifacts show that it raised too late.
    day_dir = config.journal_dir / "2026-07-10"
    assert not (day_dir / "orders.jsonl").exists()
    assert not (day_dir / "cycle-08.json").exists()
    assert "forming row" in str(excinfo.value)


# --- the limit-bound verdict ---------------------------------------------------------------------


def _sleeve_result(position: float):
    """The builder-result shape `_limits_bound` reads: one forming row (`n_periods=0`) with all three
    fixed-1/3 sleeves holding `position` in every model asset, so the combined book is `position`."""
    c = CrossfreqSystemConfig()
    return types.SimpleNamespace(
        n_periods=0,
        sleeve_positions={name: {a: [position] for a in c.assets} for name in ("B", "A1", "A2")},
    )


def test_limits_bound_is_true_when_a_wired_limit_moves_the_book():
    # 0.9 per leg: the 0.20 long cap alone clips every asset, so the limited book differs from the
    # combined one. Without this true positive the False case below would pass against a function
    # hardwired to False.
    assert cycle._limits_bound(_sleeve_result(0.9)) is True


def test_limits_bound_is_false_on_a_book_that_breaches_nothing():
    # 0.01 per leg: 0.1 gross over ten assets, inside every limit the stack applies. Each limit
    # copies its input and only touches the bars it scales, so an unbreached book must come back
    # bit-identical.
    assert cycle._limits_bound(_sleeve_result(0.01)) is False


def test_the_success_result_carries_the_limit_bound_verdict(tmp_path, monkeypatch):
    # The fixture's targets peak at BTC 0.2 -- exactly the long cap, which is inclusive -- and sum to
    # 0.55 gross, so nothing binds and the verdict is a measured False, never an absent None.
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.limit_bound is False


def test_a_raising_limit_recomputation_never_costs_the_cycle(tmp_path, monkeypatch):
    """Guard-proving: the limit stack VALIDATES its input and raises on anything non-finite, unlike
    the sleeve-gross sum beside it. This is telemetry, so an unwrapped raise here would turn a cycle
    that built and journalled fine into a dead one -- constructed, not assumed."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    monkeypatch.setattr(cycle, "_limits_bound", lambda result: 1 / 0)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert result.record_path.exists()
    assert result.limit_bound is None  # no answer, never a False that would read as a quiet book


def test_a_failed_cycle_carries_no_limit_verdict(tmp_path, monkeypatch):
    # No build ran, so "did a limit bind" has no answer: None, not the False that would read as a
    # measured quiet book.
    store_rows = _store_rows({("ETH/EUR", 240): _series_rows("ETH/EUR", 240, drop_last=1)})
    config, _, _ = _env(tmp_path, monkeypatch, rows_by=store_rows)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert result.limit_bound is None


def test_happy_path_round_trips_through_replay_cycle_under_a_stub_builder(tmp_path, monkeypatch):
    """SCOPE: the builder is STUBBED on both sides here, so this pins the plumbing -- journaling, the
    snapshot manifest, the key spaces the two sides hand the builder, the expansion -- and nothing
    about the grid the real builder would receive. A stub keyed by whatever it is handed cannot tell
    a right grid from a wrong one; `test_real_builder_round_trips_through_replay_cycle` is the pin
    that can."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    # MODEL_TARGETS, not TARGETS: replay contracts the journaled twelve-symbol snapshots down to the
    # same base-keyed ten the cycle handed the builder, then expands the result back to the basket.
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))
    replayed = replay_cycle(record, _journal_reader(config.journal_dir), path="fast")

    assert compare_targets(record.final_targets, replayed).passed
    assert replayed == TARGETS  # the expansion really ran: twelve symbol keys, /BTC at 0.0


# --- failure sidecars ----------------------------------------------------------------------------


def test_persistently_lagging_tail_exhausts_reserve_as_refresh_deadline(tmp_path, monkeypatch):
    # A lagging tail the venue never heals gets the FULL retry budget, then fails as
    # refresh_deadline -- not an instant stale_pair with unused reserve.
    rows_by = _store_rows({("DOGE/EUR", 1440): _series_rows("DOGE/EUR", 1440, drop_last=1)})  # daily tail one bar behind
    stale_fetch = {(a, iv): rows[-2:] for (a, iv), rows in rows_by.items()}  # fetch keeps returning the stale tail
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=lambda k, iv: stale_fetch[(KEY_TO_ASSET[k], iv)], clock=_clock())

    assert result.status == "failed"
    assert result.reason == "refresh_deadline"
    assert result.offending_pairs == ("DOGE/EUR",)
    assert result.record_path is None and result.targets is None and result.orders is None
    assert calls == []  # the build is skipped
    assert result.sidecar_path == config.journal_dir / "2026-07-10" / "failed-cycle-08.json"
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "refresh_deadline"
    assert sidecar["offending_pairs"] == ["DOGE/EUR"]
    for key in ("cycle_ts", "attempted_at", "completed_at"):
        assert datetime.fromisoformat(sidecar[key]).tzinfo is not None  # ISO-8601 aware-UTC
    assert not (config.journal_dir / "2026-07-10" / "snapshots").exists()
    assert not (config.journal_dir / "2026-07-10" / "cycle-08.json").exists()


def test_stale_pair_sidecar_as_defense_in_depth(tmp_path, monkeypatch):
    # _stale_pairs can fire only if settle reports clean while the raw read disagrees (a store
    # race), so the settle check is patched to simulate one: the invariant must still refuse rather
    # than feed a stale book to the builder.
    import cli.engine.cycle as cycle_mod

    rows_by = _store_rows({("DOGE/EUR", 1440): _series_rows("DOGE/EUR", 1440, drop_last=1)})
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)
    monkeypatch.setattr(cycle_mod, "_settle_pending", lambda store_dir, cycle_ts: {})

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "failed"
    assert result.reason == "stale_pair"
    assert result.offending_pairs == ("DOGE/EUR",)
    assert calls == []
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "stale_pair"


def test_refresh_deadline_writes_sidecar(tmp_path, monkeypatch):
    store_rows = _store_rows({("ETH/EUR", 240): _series_rows("ETH/EUR", 240, drop_last=1)})
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=store_rows)

    # The fetch keeps returning the lagging tail: the cycle_ts - 4h bar never commits.
    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(store_rows), clock=_clock(step=timedelta(minutes=5)))

    assert result.status == "failed"
    assert result.reason == "refresh_deadline"
    assert result.offending_pairs == ("ETH/EUR",)
    assert calls == []
    sidecar = json.loads(result.sidecar_path.read_text())
    assert sidecar["reason"] == "refresh_deadline"
    assert sidecar["offending_pairs"] == ["ETH/EUR"]
    assert not (config.journal_dir / "2026-07-10" / "snapshots").exists()
    assert not (config.journal_dir / "2026-07-10" / "cycle-08.json").exists()


# --- settle-verify -------------------------------------------------------------------------------


class SettleFetch:
    """First 4h fetch for the lagging pair returns rows WITHOUT the boundary bar (a successful fetch
    of a not-yet-committed candle); the retry returns it."""

    def __init__(self, rows_by: dict, lag_symbol: str):
        self.rows_by, self.lag_symbol, self.lag_h4_calls = rows_by, lag_symbol, 0

    def __call__(self, pair_key: str, interval: int) -> list[list]:
        symbol = KEY_TO_ASSET[pair_key]
        rows = self.rows_by[(symbol, interval)]
        if symbol == self.lag_symbol and interval == 240:
            self.lag_h4_calls += 1
            if self.lag_h4_calls == 1:
                return rows[-3:-1]
        return rows[-2:]


def test_settle_verify_refetches_a_not_yet_committed_candle(tmp_path, monkeypatch):
    full = _store_rows()
    store_rows = _store_rows({("BTC/EUR", 240): _series_rows("BTC/EUR", 240, drop_last=1)})  # store lags one 4h bar
    config, _, calls = _env(tmp_path, monkeypatch, rows_by=store_rows)
    fetch = SettleFetch(full, "BTC/EUR")

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

    expected_symbols = [s for s in ASSETS if TARGETS[s] != 0.0]
    assert [o["asset"] for o in result.orders] == expected_symbols
    assert not set(expected_symbols) & set(BTC_SYMBOLS)  # structurally zero -> structurally silent
    for order in result.orders:
        symbol = order["asset"]
        price = _base(symbol) + N_H4 - 1  # the 4h close of the bar stamped cycle_ts - 4h
        assert order["side"] == "buy"  # flat previous book, all deltas positive
        assert order["price"] == price
        assert order["notional_eur"] == pytest.approx(TARGETS[symbol] * 1000.0)
        assert order["quantity"] == pytest.approx(TARGETS[symbol] * 1000.0 / price)

    lines = [json.loads(line) for line in (config.journal_dir / "2026-07-10" / "orders.jsonl").read_text().splitlines()]
    header = lines[0]
    assert header["cycle_ts"] == CYCLE_TS.isoformat()
    assert header["previous_cycle_ts"] is None
    assert "flat" in header["note"]
    assert lines[1:] == result.orders


def _success_record_json(boundary: datetime, targets: dict[str, float], *, schema_version: int = SCHEMA_VERSION) -> str:
    # A minimal previous-record fixture: run_cycle only reads final_targets back via from_json.
    record = CycleRecord(
        schema_version=schema_version,
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
    prev_targets = dict.fromkeys(TARGETS, 0.0) | {"BTC/EUR": 0.3, "ETH/EUR": 0.15}
    prev_dir = config.journal_dir / "2026-07-09"
    prev_dir.mkdir(parents=True)
    (prev_dir / "cycle-20.json").write_text(_success_record_json(prev_boundary, prev_targets))
    # The immediately preceding boundary failed, the one before it is missing entirely.
    day_dir = config.journal_dir / "2026-07-10"
    day_dir.mkdir(parents=True)
    (day_dir / "failed-cycle-04.json").write_text(json.dumps({"reason": "stale_pair"}))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    by_symbol = {o["asset"]: o for o in result.orders}
    assert by_symbol["BTC/EUR"]["side"] == "sell"  # 0.2 - 0.3 < 0
    assert by_symbol["BTC/EUR"]["notional_eur"] == pytest.approx(0.1 * 1000.0)
    assert "ETH/EUR" not in by_symbol  # delta vs the gap-crossed previous is exactly 0 -- not vs a flat book
    header = json.loads((day_dir / "orders.jsonl").read_text().splitlines()[0])
    assert header["previous_cycle_ts"] == prev_boundary.isoformat()
    assert "gap" in header["note"]


def test_order_arithmetic_delta_times_nav_over_h4_close(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch, nav=2500.0)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    btc = next(o for o in result.orders if o["asset"] == "BTC/EUR")
    price = _base("BTC/EUR") + N_H4 - 1  # 305.0, the close of the bar stamped cycle_ts - 4h
    assert btc["price"] == price
    assert btc["notional_eur"] == pytest.approx(0.2 * 2500.0)
    assert btc["quantity"] == pytest.approx(0.2 * 2500.0 / price)


# --- union alignment + relocation ----------------------------------------------------------------


def test_union_alignment_journals_none_at_absences_and_replays_clean(tmp_path, monkeypatch):
    gap_ts = H4_LAST - timedelta(hours=8)
    rows_by = _store_rows({("DOGE/EUR", 240): _series_rows("DOGE/EUR", 240, skip=(gap_ts,))})  # a venue gap
    config, rows_by, calls = _env(tmp_path, monkeypatch, rows_by=rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())
    assert result.status == "success"

    # The builder saw the contracted EUR shape: one shared calendar per grid, base-keyed, None at
    # DOGE/EUR's absence (the other nine EUR legs carry that stamp, so it stays in their union).
    daily_prices, daily_ts, h4_prices, h4_ts = calls[0]
    assert len(h4_ts) == N_H4 and len(daily_ts) == N_DAILY
    assert all(len(series) == N_H4 for series in h4_prices.values())
    assert all(len(series) == N_DAILY for series in daily_prices.values())
    gap_index = h4_ts.index(gap_ts)
    assert h4_prices["DOGE"][gap_index] is None
    assert all(c is not None for c in h4_prices["BTC"])

    # The journaled DOGE 4h snapshot carries the union calendar with the None close.
    # The '/' is sanitized out of the filename so the day's snapshots/ stays flat.
    frame = read_parquet(config.journal_dir / "2026-07-10" / "snapshots" / "cycle-08" / "DOGE-EUR-240.parquet")
    assert frame["ts"].to_list() == h4_ts
    assert frame["close"].to_list()[gap_index] is None

    record = from_json(result.record_path.read_text())
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))
    replayed = replay_cycle(record, _journal_reader(config.journal_dir), path="fast")
    assert compare_targets(record.final_targets, replayed).passed


def test_journal_relocation_round_trip(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    new_root = tmp_path / "relocated-journal"
    shutil.move(str(config.journal_dir), str(new_root))

    record = from_json((new_root / "2026-07-10" / "cycle-08.json").read_text())
    monkeypatch.setattr(concordance, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))
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


# --- midnight-boundary settle (the iter-083 review's catch) --------------------------------


def test_settle_pending_covers_the_daily_grid_at_midnight_boundaries(tmp_path):
    """At a 00:00 boundary the NEW daily bar settles like the 4h one; checking only the 4h tail
    would burn the reserve and journal an avoidable stale_pair. Both grids feed the pending set."""
    from cli.engine.cycle import _settle_pending

    midnight = datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
    store = tmp_path / "store"
    h4_last, daily_last = midnight - timedelta(hours=4), midnight - timedelta(days=1)
    for symbol in ASSETS:
        base, quote = symbol.split("/")
        h4_rows = [_row(h4_last - (5 - i) * timedelta(hours=4), _base(symbol) + i) for i in range(6)]
        daily_rows = [_row(daily_last - (3 - i) * timedelta(days=1), _base(symbol) + i) for i in range(4)]
        if symbol == "BTC/EUR":
            daily_rows = daily_rows[:-1]  # the new daily bar not yet committed
        write_parquet(to_frame(h4_rows), store / base / quote / "240.parquet")
        write_parquet(to_frame(daily_rows), store / base / quote / "1440.parquet")

    assert _settle_pending(store, midnight) == {"BTC/EUR": PAIR_KEYS["BTC/EUR"]}

    fresh = [_row(daily_last - (3 - i) * timedelta(days=1), _base("BTC/EUR") + i) for i in range(4)]
    write_parquet(to_frame(fresh), store / "BTC" / "EUR" / "1440.parquet")
    assert _settle_pending(store, midnight) == {}

    # regression: at a NON-midnight boundary the (older) daily expectation is already satisfied
    non_midnight = datetime(2026, 7, 10, 8, 0, tzinfo=UTC)
    ok_store = tmp_path / "store2"
    for symbol in ASSETS:
        base, quote = symbol.split("/")
        h4 = [_row(non_midnight - timedelta(hours=4) - (5 - i) * timedelta(hours=4), 1.0 + i) for i in range(6)]
        daily = [_row(datetime(2026, 7, 9, tzinfo=UTC) - (3 - i) * timedelta(days=1), 1.0 + i) for i in range(4)]
        write_parquet(to_frame(h4), ok_store / base / quote / "240.parquet")
        write_parquet(to_frame(daily), ok_store / base / quote / "1440.parquet")
    assert _settle_pending(ok_store, non_midnight) == {}


# --- the dead-man's-switch ping (spec 00042) -------------------------------------------------------

HC_URL = "https://hc.example/ping/abc123"


def test_success_pings_the_healthcheck_url(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    monkeypatch.setenv("HEALTHCHECK_URL", HC_URL)
    pings = []
    monkeypatch.setattr(cycle, "_hc_opener", lambda url, timeout: pings.append((url, timeout)))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert pings == [(HC_URL, 10)]


def test_failed_cycle_pings_the_fail_url(tmp_path, monkeypatch):
    rows_by = _store_rows({("DOGE/EUR", 1440): _series_rows("DOGE/EUR", 1440, drop_last=1)})
    stale_fetch = {(s, iv): rows[-2:] for (s, iv), rows in rows_by.items()}  # the venue never heals the lagging tail
    config, _, _ = _env(tmp_path, monkeypatch, rows_by=rows_by)
    monkeypatch.setenv("HEALTHCHECK_URL", HC_URL)
    pings = []
    monkeypatch.setattr(cycle, "_hc_opener", lambda url, timeout: pings.append((url, timeout)))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=lambda k, iv: stale_fetch[(KEY_TO_ASSET[k], iv)], clock=_clock())

    assert result.status == "failed"
    assert pings == [(HC_URL + "/fail", 10)]


def test_unset_healthcheck_url_never_opens(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
    pings = []
    monkeypatch.setattr(cycle, "_hc_opener", lambda url, timeout: pings.append((url, timeout)))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert result.status == "success"
    assert pings == []


def test_raising_opener_leaves_the_result_identical_to_the_no_ping_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))

    def boom(url, timeout):
        raise OSError("connection refused")

    results = {}
    for name in ("baseline", "raising"):
        rows_by = _store_rows()
        store = tmp_path / name / "store"
        _write_store(store, rows_by)
        config = EngineConfig(store_dir=store, journal_dir=tmp_path / name / "journal")
        if name == "baseline":
            monkeypatch.delenv("HEALTHCHECK_URL", raising=False)
        else:
            monkeypatch.setenv("HEALTHCHECK_URL", HC_URL)
            monkeypatch.setattr(cycle, "_hc_opener", boom)
        results[name] = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    baseline, raising = results["baseline"], results["raising"]
    assert raising.record_path.exists()  # the record landed before the ping even tried
    for field in ("status", "cycle_ts", "targets", "orders", "reason", "offending_pairs", "sidecar_path"):
        assert getattr(raising, field) == getattr(baseline, field)


# --- venue truth: the seam (00089 Task 4) ---------------------------------------------------------


def test_venue_record_is_written_first_and_survives_a_failing_cycle(tmp_path, monkeypatch):
    """The record lands BEFORE target computation, so a cycle that dies later still leaves the venue
    evidence for the boundary: a fetch_fn that raises kills run_cycle deep inside step 1 (settle-
    verify refresh), well before any target work -- venue-HH.json must already exist."""
    config, _, _ = _env(tmp_path, monkeypatch)

    def boom(pair_key: str, interval: int) -> list[list]:
        raise RuntimeError("transport is gone")

    with pytest.raises(RuntimeError, match="transport is gone"):
        run_cycle(CYCLE_TS, config=config, fetch_fn=boom, clock=_clock(), venue_state=_adversarial_venue_state())

    venue_path = config.journal_dir / "2026-07-10" / "venue-08.json"
    assert venue_path.exists()
    doc = json.loads(venue_path.read_text())
    assert doc["status"] == "ok"
    assert not (config.journal_dir / "2026-07-10" / "cycle-08.json").exists()


def test_targets_are_identical_with_and_without_venue_state(tmp_path, monkeypatch):
    """THE read-only pin: venue truth is journaled, never consulted. Two runs, identical inputs, one
    with venue_state=None, the other with an ADVERSARIAL VenueState -- final_targets, orders and the
    journaled record must be identical apart from `held`; only CycleResult.venue differs. A
    permissive VenueState would pass even if the cycle consulted it, proving nothing."""
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    monkeypatch.setattr(cycle, "build_crossfreq_system_fast", _fake_builder(MODEL_TARGETS))

    results = {}
    for name, state in (("none", None), ("adversarial", _adversarial_venue_state())):
        rows_by = _store_rows()
        store = tmp_path / name / "store"
        _write_store(store, rows_by)
        config = EngineConfig(store_dir=store, journal_dir=tmp_path / name / "journal")
        results[name] = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=state)

    none_result, adversarial_result = results["none"], results["adversarial"]
    assert none_result.status == adversarial_result.status == "success"
    assert none_result.targets == adversarial_result.targets == TARGETS
    assert none_result.orders == adversarial_result.orders

    # `held` is the ONE venue-derived field the cycle record carries, so a raw byte compare would
    # fail for the one difference that is supposed to exist: assert the position was journaled from
    # the adversarial read, then neutralise it and compare the rest byte-for-byte.
    none_record = from_json(none_result.record_path.read_text())
    adversarial_record = from_json(adversarial_result.record_path.read_text())
    assert none_record.held is None
    assert adversarial_record.held == {a.split("/")[0]: 1_000.0 for a in ASSETS if a.endswith("/EUR")}
    assert to_json(replace(none_record, held=None)) == to_json(replace(adversarial_record, held=None))

    assert none_result.venue is None
    assert adversarial_result.venue == {
        "loaded": len(PAIR_KEYS),
        "expected": len(INSTRUMENT_IDS),
        "failures": 0,
        "snapshot_at": CYCLE_TS.isoformat(),
    }


def test_no_snapshot_writes_an_error_record_and_the_cycle_proceeds(tmp_path, monkeypatch):
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=None)

    assert result.status == "success"
    assert result.venue is None
    doc = json.loads((config.journal_dir / "2026-07-10" / "venue-08.json").read_text())
    assert doc["status"] == "error"
    assert "state" not in doc


def test_a_venue_state_none_rerun_leaves_an_ok_record_alone(tmp_path, monkeypatch):
    """The write-first design's whole point (00089 D7): a boundary whose venue-<HH>.json already
    reads status "ok" is never clobbered by a later call carrying no VenueState. This is exactly the
    CLI's `cycle --replace` path (cli/engine/command.py): it calls run_cycle with no venue_state at
    all, so a manual re-run of an already-journaled boundary must not destroy the live engine's own
    soak evidence for it -- or, absent --replace, a crashed boundary's only surviving evidence."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    first = run_cycle(
        CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=_adversarial_venue_state()
    )
    assert first.status == "success"
    venue_path = config.journal_dir / "2026-07-10" / "venue-08.json"
    before = venue_path.read_text()

    second = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=None)

    assert second.status == "success"
    assert venue_path.read_text() == before
    assert second.venue is None


def test_a_venue_state_none_rerun_still_overwrites_an_error_record(tmp_path, monkeypatch):
    """Only an "ok" record is protected -- an existing "error" record for the boundary is fair game
    and must be REWRITTEN, not left with stale content, on a later venue_state=None call."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    venue_dir = config.journal_dir / "2026-07-10"
    venue_dir.mkdir(parents=True)
    venue_path = venue_dir / "venue-08.json"
    venue_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cycle_ts": CYCLE_TS.isoformat(),
                "code_version": "stale-fixture",
                "status": "error",
                "error": "STALE FIXTURE MARKER",
            }
        )
    )

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock(), venue_state=None)

    assert result.status == "success"
    doc = json.loads(venue_path.read_text())
    assert doc["status"] == "error"
    assert doc["error"] == "no venue snapshot available for this cycle"


def test_code_version_composes_the_build_revision(monkeypatch):
    monkeypatch.setenv("ZCRYPTO_BUILD_REVISION", "0daa2c12aaaaabbbbbcccc")
    assert _code_version().endswith("+0daa2c12aaaa")
    monkeypatch.delenv("ZCRYPTO_BUILD_REVISION")
    assert "+" not in _code_version()


# --- the shared contraction and the expansion (spec 00094 D1/D2) ----------------------------------


def _tiny_series(btc_only_stamp: datetime | None = None) -> dict:
    """One grid's `{symbol: (ts, closes)}` over three shared stamps, optionally with a fourth stamp
    that ONLY the two /BTC legs carry."""
    stamps = [datetime(2026, 7, 1, tzinfo=UTC) + i * timedelta(hours=4) for i in range(3)]
    series = {}
    for i, symbol in enumerate(ASSETS):
        ts, closes = list(stamps), [10.0 + 100 * i + j for j in range(3)]
        if btc_only_stamp is not None and symbol in BTC_SYMBOLS:
            ts, closes = ts[:1] + [btc_only_stamp] + ts[1:], closes[:1] + [7.5] + closes[1:]
        series[symbol] = (ts, closes)
    return series


def _twelve_symbol_alignment(series: dict) -> dict:
    """What the journal stores and the gate replay reads back: every symbol on the union of ALL
    TWELVE calendars, None at absences -- run_cycle's `_union_align` shape, built here so the
    contraction's idempotence is asserted against an independently constructed input."""
    union = sorted({t for ts, _ in series.values() for t in ts})
    return {symbol: (list(union), [dict(zip(ts, closes)).get(t) for t in union]) for symbol, (ts, closes) in series.items()}


def test_select_model_inputs_hands_the_model_exactly_its_configured_assets():
    """D1's first half at the seam: the builder's input key set is the ten bases
    CrossfreqSystemConfig declares -- no /BTC leg reaches a sleeve, and no symbol key does either."""
    ts, prices = select_model_inputs(_tiny_series())

    assert set(prices) == set(CrossfreqSystemConfig().assets)
    assert all("/" not in key for key in prices)
    assert len(ts) == 3


def test_a_btc_only_stamp_never_enters_the_model_calendar():
    """spec 00094 D2: the calendar is unioned over the ten EUR pairs ONLY. Today the /BTC stamps
    happen to be subsets of the EUR union; nothing constructs that, so this does."""
    odd_stamp = datetime(2026, 7, 1, 2, 0, tzinfo=UTC)  # off-grid, interior, /BTC-only

    plain_ts, plain_prices = select_model_inputs(_tiny_series())
    perturbed_ts, perturbed_prices = select_model_inputs(_tiny_series(btc_only_stamp=odd_stamp))

    assert odd_stamp not in perturbed_ts
    assert (perturbed_ts, perturbed_prices) == (plain_ts, plain_prices)


def test_select_model_inputs_is_idempotent_over_the_twelve_symbol_alignment():
    """The cycle contracts from RAW store reads; the gate replay contracts from journaled snapshots
    already aligned onto the twelve-symbol union, where every EUR leg carries None at a /BTC-only
    stamp. Both must reach the builder with the same grid, or every post-deploy replay mismatches."""
    raw = _tiny_series(btc_only_stamp=datetime(2026, 7, 1, 2, 0, tzinfo=UTC))
    aligned = _twelve_symbol_alignment(raw)

    assert len(aligned["BTC/EUR"][0]) == 4 and aligned["BTC/EUR"][1][1] is None  # the None really is there
    assert select_model_inputs(aligned) == select_model_inputs(raw)


def test_select_model_inputs_refuses_a_series_map_missing_a_eur_leg():
    incomplete = {symbol: series for symbol, series in _tiny_series().items() if symbol != "LINK/EUR"}
    with pytest.raises(EngineError, match="LINK/EUR"):
        select_model_inputs(incomplete)


def test_expand_to_basket_carries_the_ten_and_zeroes_the_two():
    expanded = _expand_to_basket(MODEL_TARGETS)

    assert set(expanded) == set(BASKET)
    assert expanded == TARGETS
    for leg in BTC_SYMBOLS:
        assert expanded[leg] == 0.0
    assert expanded["BTC/EUR"] == 0.2  # a carried value, not a default -- MODEL_TARGETS has no 0.2 twin


def test_expand_to_basket_refuses_a_model_asset_with_no_eur_leg():
    # A silently dropped target is a position the engine believes it holds and never trades.
    with pytest.raises(EngineError, match="ratified basket"):
        _expand_to_basket(MODEL_TARGETS | {"PEPE": 0.11})


def test_symbol_keyed_targets_normalizes_a_v1_record_and_leaves_v2_alone():
    v1 = from_json(_success_record_json(CYCLE_TS, MODEL_TARGETS, schema_version=1))
    v2 = from_json(_success_record_json(CYCLE_TS, TARGETS))

    assert symbol_keyed_targets(v1) == {f"{base}/EUR": value for base, value in MODEL_TARGETS.items()}
    assert symbol_keyed_targets(v2) == TARGETS


def _orders_lines(config: EngineConfig) -> list[str]:
    return (config.journal_dir / "2026-07-10" / "orders.jsonl").read_text().splitlines()


def test_btc_legs_are_exactly_zero_and_emit_no_orders(tmp_path, monkeypatch):
    """D1's zero pin, end to end: a full cycle journals ETH/BTC and SOL/BTC at exactly 0.0, and the
    orders list carries no row for either. The ten EUR legs are asserted alongside, so a run whose
    expansion dropped the model's values entirely (everything 0.0) cannot read as a pass."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    record = from_json(result.record_path.read_text())
    assert set(record.final_targets) == set(result.targets) == set(BASKET)
    for leg in BTC_SYMBOLS:
        assert result.targets[leg] == 0.0
        assert record.final_targets[leg] == 0.0
    assert {o["asset"] for o in result.orders}.isdisjoint(BTC_SYMBOLS)
    assert not any(json.loads(line).get("asset") in BTC_SYMBOLS for line in _orders_lines(config)[1:])
    # the carried half, so the zeros above are legible as structural rather than universal
    assert {symbol: record.final_targets[symbol] for symbol in EUR_SYMBOLS} == {
        f"{base}/EUR": value for base, value in MODEL_TARGETS.items()
    }


def test_a_schema_1_predecessor_emits_only_genuine_deltas(tmp_path, monkeypatch):
    """The deploy-boundary money defect (spec 00094 D8): the FIRST schema-2 cycle follows a
    base-keyed schema-1 record. Un-normalized, every `.get(symbol, 0.0)` misses, the engine reads
    the whole book as flat and writes a full from-flat rebalance into orders.jsonl and the exec
    ledger -- silently, because the gate never reads orders. The v1 predecessor here holds this very
    cycle's book except for BTC, so exactly ONE order is owed; a missed normalization emits seven."""
    config, rows_by, _ = _env(tmp_path, monkeypatch)
    prev_boundary = CYCLE_TS - timedelta(hours=4)
    day_dir = config.journal_dir / "2026-07-10"
    day_dir.mkdir(parents=True)
    prev_v1 = MODEL_TARGETS | {"BTC": 0.3}
    (day_dir / "cycle-04.json").write_text(_success_record_json(prev_boundary, prev_v1, schema_version=1))

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    assert [o["asset"] for o in result.orders] == ["BTC/EUR"]
    assert result.orders[0]["side"] == "sell"  # 0.2 - 0.3 < 0
    assert result.orders[0]["notional_eur"] == pytest.approx(0.1 * 1000.0)
    header, *rows = _orders_lines(config)
    assert json.loads(header)["previous_cycle_ts"] == prev_boundary.isoformat()
    assert len(rows) == 1  # the journal agrees with the in-memory result -- no phantom rebalance


# --- D1/D2 through the REAL builder ---------------------------------------------------------------
#
# A hand-built expansion-only test would stay green if the pipeline fed the model differently, so
# the tests below run the whole cycle against a standalone ten-asset build over the same ten EUR
# series.

_REAL_N_DAILY = 300  # > the longest daily lookback in play (A2's 240 arm): a shorter history makes
_REAL_N_H4 = 420  # every target 0.0, which no assertion below could tell from a structural zero
_REAL_DAILY_TS = tuple(DAILY_LAST - (_REAL_N_DAILY - 1 - i) * timedelta(days=1) for i in range(_REAL_N_DAILY))
_REAL_H4_TS = tuple(H4_LAST - (_REAL_N_H4 - 1 - i) * timedelta(hours=4) for i in range(_REAL_N_H4))
# An interior stamp near the tail. Near the tail is load-bearing: an all-None row further back
# washes out of the builder's windows, and the pin would sit green either way (measured).
_BTC_ONLY_INSERT_AT = -5
_BTC_ONLY_OFFSET = {1440: timedelta(hours=5), 240: timedelta(hours=1)}  # off both grids, so no EUR leg has it


def _real_closes(symbol: str, n: int, scale: int) -> list[float]:
    """A distinct trending-plus-cycling path per symbol. The constants are tuned, not arbitrary: the
    ten EUR targets must come out non-zero AND pairwise distinct, or a value carried through the
    pipeline would be indistinguishable from a default that was never written."""
    k = BASKET.index(symbol)
    level, amplitude, period = 100.0 * (1 + k), 0.10 + 0.03 * k, (37 + 7 * k) * scale
    return [level * (1.0 + amplitude * math.sin(2 * math.pi * i / period) + 0.003 * i / scale) for i in range(n)]


def _real_rows(symbol: str, interval: int, *, btc_only_stamp: bool = False) -> list[list]:
    ts = list(_REAL_DAILY_TS if interval == 1440 else _REAL_H4_TS)
    closes = _real_closes(symbol, len(ts), 1 if interval == 1440 else 6)
    if btc_only_stamp:
        at = len(ts) + _BTC_ONLY_INSERT_AT
        stamp = ts[at - 1] + _BTC_ONLY_OFFSET[interval]
        ts, closes = ts[:at] + [stamp] + ts[at:], closes[:at] + [closes[at - 1]] + closes[at:]
    return [_row(t, c) for t, c in zip(ts, closes)]


def _real_store_rows(*, btc_only_stamp: bool = False) -> dict:
    return {
        (symbol, interval): _real_rows(symbol, interval, btc_only_stamp=btc_only_stamp and symbol in BTC_SYMBOLS)
        for symbol in ASSETS
        for interval in GRID_INTERVALS
    }


def _real_env(tmp_path, monkeypatch) -> EngineConfig:
    """Like `_env`, but the builder is NOT stubbed -- these tests are about what the real one does."""
    monkeypatch.setattr(cycle, "_sleep", lambda seconds: None)
    return EngineConfig(store_dir=tmp_path / "store", journal_dir=tmp_path / "journal", shadow_nav_eur=1000.0)


def _standalone_ten_asset_targets() -> dict[str, float]:
    """build_crossfreq_system_fast over the ten EUR series ALONE, base-keyed: the model exactly as it
    exists today, with nothing else in the room."""
    daily = {s.split("/")[0]: _real_closes(s, _REAL_N_DAILY, 1) for s in EUR_SYMBOLS}
    h4 = {s.split("/")[0]: _real_closes(s, _REAL_N_H4, 6) for s in EUR_SYMBOLS}
    result = build_crossfreq_system_fast(daily, list(_REAL_DAILY_TS), h4, list(_REAL_H4_TS))
    targets = {base: series[result.n_periods] for base, series in result.final_targets.items()}
    # The fixture must be able to tell "the pipeline carried the model's value" from "a structural
    # zero was never touched" -- ten non-zero, pairwise-distinct targets is what makes that so.
    assert len(targets) == 10
    assert all(value != 0.0 for value in targets.values())
    assert len(set(targets.values())) == 10
    return targets


def test_eur_targets_equal_a_standalone_ten_asset_build(tmp_path, monkeypatch):
    """D1's identity pin, through the REAL path: the full cycle build produces /EUR-keyed targets
    equal to a standalone build over the ten EUR series alone. It goes red if
    CrossfreqSystemConfig.assets widens, and (with the fixture below) if a /BTC calendar stamp
    shifts an EUR window."""
    config = _real_env(tmp_path, monkeypatch)
    rows_by = _real_store_rows()
    _write_store(config.store_dir, rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    standalone = _standalone_ten_asset_targets()
    assert result.status == "success"
    assert set(result.targets) == set(BASKET)
    assert {s: result.targets[s] for s in EUR_SYMBOLS} == {f"{base}/EUR": v for base, v in standalone.items()}
    for leg in BTC_SYMBOLS:
        assert result.targets[leg] == 0.0
    assert from_json(result.record_path.read_text()).final_targets == result.targets


def test_a_btc_stamp_the_eur_legs_lack_moves_no_eur_window(tmp_path, monkeypatch):
    """The calendar pin (spec 00094 D2): a fixture whose twelve-symbol stamp union differs from the
    ten-EUR union -- one /BTC-only timestamp per grid -- leaves every EUR target identical to the
    unperturbed standalone build."""
    config = _real_env(tmp_path, monkeypatch)
    rows_by = _real_store_rows(btc_only_stamp=True)
    _write_store(config.store_dir, rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())

    # The perturbation really did reach the pipeline: the twelve-symbol union carries the extra
    # stamp (so the journaled snapshots do too), and the contraction is what drops it again.
    raw = {symbol: read_store_series(config.store_dir, symbol, 240) for symbol in ASSETS}
    assert len({t for ts, _ in raw.values() for t in ts}) == _REAL_N_H4 + 1
    assert len(select_model_inputs(raw)[0]) == _REAL_N_H4
    snapshots = {(e.pair, e.grid): e for e in from_json(result.record_path.read_text()).snapshots}
    assert snapshots[("BTC/EUR", "240")].n_bars == _REAL_N_H4 + 1

    standalone = _standalone_ten_asset_targets()
    assert {s: result.targets[s] for s in EUR_SYMBOLS} == {f"{base}/EUR": v for base, v in standalone.items()}


def test_real_builder_round_trips_through_replay_cycle(tmp_path, monkeypatch):
    """The round trip with NO stub anywhere: run_cycle journals, and replay_cycle reads those
    journaled twelve-symbol snapshots back and must reproduce the same twelve targets exactly.

    A builder keyed by whatever it is handed agrees with any grid, so a stubbed round trip stays
    green if replay feeds the model a different calendar, a different key space, or all twelve legs
    -- the last of which is a hard PortfolioError on the real builder.
    `_real_store_rows(btc_only_stamp=True)` is deliberate: the journaled snapshots then carry a
    stamp no EUR leg has, so the replay only matches if its own contraction drops that stamp exactly
    as the cycle's did."""
    config = _real_env(tmp_path, monkeypatch)
    rows_by = _real_store_rows(btc_only_stamp=True)
    _write_store(config.store_dir, rows_by)

    result = run_cycle(CYCLE_TS, config=config, fetch_fn=_tail_fetch(rows_by), clock=_clock())
    assert result.status == "success"

    record = from_json(result.record_path.read_text())
    replayed = replay_cycle(record, _journal_reader(config.journal_dir), path="fast")

    verdict = compare_targets(record.final_targets, replayed)
    assert verdict.passed, (verdict, replayed)
    assert not verdict.structural_mismatch
    assert replayed == record.final_targets  # bit-exact, not merely within tol
    assert set(replayed) == set(BASKET)
    # The fixture can tell "carried the model's value" from "a structural zero nobody wrote": the
    # ten EUR legs are non-zero and pairwise distinct, the two /BTC legs are exactly 0.0.
    eur = {replayed[s] for s in EUR_SYMBOLS}
    assert len(eur) == 10 and 0.0 not in eur
    assert all(replayed[leg] == 0.0 for leg in BTC_SYMBOLS)
