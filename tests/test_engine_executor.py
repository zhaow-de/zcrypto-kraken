from __future__ import annotations

import json
import logging
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.model.enums import OrderSide, TimeInForce

import cli.engine.executor as executor_module
from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
from cli.engine.execledger import append_plan_entry, exec_record_path, read_exec_record
from cli.engine.executor import ProbeExecutor, set_executor_hooks, size_probe_order
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder
from cli.engine.probeplan import PLAN_FILENAME
from cli.engine.venue import VenueStatus
from cli.engine.venuestate import InstrumentConstraints, VenueState

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


# --- the sizing seam (Task 4) -------------------------------------------------------------------


def _constraints(**overrides):
    base = dict(
        symbol="BTC/EUR",
        instrument_id="BTC/EUR.KRAKEN",
        ordermin=0.0001,
        costmin=0.45,
        costmin_quote="EUR",
        lot_step=0.00000001,
        tick_size=0.1,
    )
    base.update(overrides)
    return InstrumentConstraints(**base)


def test_the_mismatched_denomination_raises_and_names_the_defect():
    """T0138's constructed defect: a BTC floor (2e-05) against a EUR notional. Assert WHICH failure
    fired -- the denomination guard, not a BelowMinimum or an unrelated raise."""
    c = _constraints(symbol="ETH/BTC", instrument_id="ETH/BTC.KRAKEN", costmin=2e-05, costmin_quote="BTC")
    with pytest.raises(EngineError, match="cross-denomination"):
        size_probe_order(0.01, 0.05, c)


def test_the_matched_eur_pair_sizes_through_size_order():
    sized = size_probe_order(0.001, 30000.0, _constraints())
    assert isinstance(sized, SizedOrder)
    assert sized.qty == 0.001 and sized.price == 30000.0


def test_a_below_minimum_result_passes_through_unchanged():
    """Names WHICH floor tripped -- an ordermin drop (e.g. ordermin=0.0) must not survive this
    test, so asserting only the type is not enough."""
    result = size_probe_order(0.00001, 30000.0, _constraints(ordermin=0.0001))
    assert isinstance(result, BelowMinimum)
    assert "ordermin" in result.reason


def test_a_below_costmin_result_names_the_floor():
    """The fail-open direction FINDING 1 flags: a matched EUR pair that clears ordermin but falls
    under the EUR costmin floor. A costmin drop (e.g. costmin=0.0) must not survive this test."""
    result = size_probe_order(0.001, 100.0, _constraints())
    assert isinstance(result, BelowMinimum)
    assert "costmin" in result.reason


# --- the structural pin -------------------------------------------------------------------------


def test_submit_order_and_order_factory_have_exactly_one_module():
    """D4's structural pin: all venue-mutating calls live in cli/engine/executor.py. A text walk,
    not an import walk -- a reference in a comment is still a reference a refactor can activate."""
    offenders = []
    for path in sorted(Path("cli").rglob("*.py")):
        if path.as_posix() == "cli/engine/executor.py":
            continue
        text = path.read_text()
        if "submit_order" in text or "order_factory" in text:
            offenders.append(path.as_posix())
    assert offenders == []


# --- the stub harness ---------------------------------------------------------------------------

# The two /BTC legs carry BTC-denominated attributes, deliberately distinct from the /EUR legs'
# defaults (tests/test_engine_venuestate.py's fixture reasoning): a bug that reused the EUR values
# for these two symbols would otherwise go undetected.
_BTC_LEG_ATTRS = {
    "ETH/BTC": {"ordermin": 0.004, "lot_step": 0.00001, "tick_size": 0.0000001},
    "SOL/BTC": {"ordermin": 0.1, "lot_step": 0.001, "tick_size": 0.0000001},
}


def _fake_instrument(instrument_id: str, *, ordermin=0.0001, lot_step=0.00000001, tick_size=0.1):
    # min_notional mirrors observed live reality (cli/engine/venuestate.py, D5a): the installed
    # Kraken adapter never populates it. make_qty/make_price are identity here -- the real Cache
    # instrument returns Quantity/Price value objects, and the executor must route the sized
    # numbers through them rather than handing raw floats to the order factory.
    return SimpleNamespace(
        id=instrument_id,
        min_quantity=ordermin,
        min_notional=None,
        size_increment=lot_step,
        price_increment=tick_size,
        make_qty=lambda value: value,
        make_price=lambda value: value,
    )


def _all_instruments(**overrides):
    instruments = {iid: _fake_instrument(iid, **_BTC_LEG_ATTRS.get(symbol, {})) for symbol, iid in INSTRUMENT_IDS.items()}
    instruments.update(overrides)
    return instruments


# SimpleNamespace defines __eq__, so it is unhashable and cannot key balances_free()'s dict --
# the same reason tests/test_engine_venuestate.py uses a namedtuple for the fake Currency.
_FakeCurrency = namedtuple("_FakeCurrency", ["code"])


class StubCache:
    """Duck-types the Cache accessors `venue_state_from_cache` and the executor call, matching
    their real signatures. `raises=True` is the no-venue-truth construction."""

    def __init__(self, *, instruments=None, balances=None, positions=None, raises=False):
        self._instruments = _all_instruments() if instruments is None else instruments
        self._balances = {"ZEUR": 1000.0} if balances is None else balances
        self._positions = positions or {}
        self._raises = raises

    def instrument(self, instrument_id):
        if self._raises:
            raise RuntimeError("cache read failed")
        return self._instruments.get(str(instrument_id))

    def positions_open(self, *, instrument_id=None, **kwargs):
        return self._positions.get(str(instrument_id), [])

    def orders_open(self, *, venue=None, **kwargs):
        return []

    def account_for_venue(self, *, venue=None, **kwargs):
        balances = {_FakeCurrency(code=code): value for code, value in self._balances.items()}
        return SimpleNamespace(balances_free=lambda: balances)


class StubOrderFactory:
    def __init__(self):
        self._n = 0

    def limit(self, **kwargs):
        self._n += 1
        return SimpleNamespace(client_order_id=f"O-{self._n}", **kwargs)


class StubClient:
    """The strategy handle's surface, stubbed: nothing here reaches a venue. `submit_raises` is the
    constructed transport failure -- a submission whose outcome this process cannot know."""

    def __init__(self, cache=None, *, submit_raises=None):
        self.cache = cache if cache is not None else StubCache()
        self.order_factory = StubOrderFactory()
        self.submitted = []
        self.canceled = []
        self.subscribed = []
        self.unsubscribed = []
        self._submit_raises = submit_raises

    def submit_order(self, order, params=None):
        self.submitted.append((order, params))
        if self._submit_raises is not None:
            raise self._submit_raises

    def cancel_order(self, order):
        self.canceled.append(order)

    def subscribe_quote_ticks(self, instrument_id):
        self.subscribed.append(str(instrument_id))

    def unsubscribe_quote_ticks(self, instrument_id):
        self.unsubscribed.append(str(instrument_id))


def _venue_reader(status="online", ok=True):
    def reader(*, now, opener=None):
        return VenueStatus(status=status, ok=ok, observed_at=now)

    return reader


def _gate(tmp_path: Path, level: str = GateLevel.FULL) -> ExecutionGate:
    """A REAL ExecutionGate with the control files set for `level`. The trailing assert is the
    point: a helper that silently produced FULL for a NONE request would hand every refusal test a
    green it never earned."""
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARM_FILE).touch()
    if level == GateLevel.REDUCE_ONLY:
        (d / RESTART_HOLD_FILE).touch()
    if level == GateLevel.NONE:
        (d / KILL_FILE).touch()
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue_reader())
    assert gate.evaluate(NOW).level == level
    return gate


class CountingGate:
    """Counts evaluations. The idle-tick claim ("an idle tick does only the os.lstat") is only
    checkable against something that records being asked."""

    def __init__(self, level=GateLevel.FULL):
        self.calls = 0
        self._level = level

    def evaluate(self, now):
        self.calls += 1
        return GateVerdict(level=self._level, reasons=(), inputs={})


def _config(tmp_path: Path, **overrides) -> EngineConfig:
    # state_dir is journal_dir.parent (the 00088 convention), so exec/ lands at tmp_path/exec --
    # the same directory _gate() writes its control files into.
    base = dict(journal_dir=tmp_path / "journal", store_dir=tmp_path / "store")
    base.update(overrides)
    return EngineConfig(**base)


def _executor(tmp_path: Path, *, client=None, gate=None, config=None, clock=None) -> ProbeExecutor:
    client = client if client is not None else StubClient()
    return ProbeExecutor(
        client=client,
        gate=gate if gate is not None else _gate(tmp_path),
        config=config if config is not None else _config(tmp_path),
        clock=clock if clock is not None else (lambda: NOW),
    )


def _intent(**overrides):
    base = {"symbol": "BTC/EUR", "side": "buy", "action": "open", "mode": "execute", "notional_eur": 30.0}
    base.update(overrides)
    return base


def _plan_dict(*, plan_id="p-1", created_at=None, intents=None):
    return {
        "plan_id": plan_id,
        "created_at": (created_at if created_at is not None else NOW - timedelta(minutes=5)).isoformat(),
        "intents": intents if intents is not None else [_intent()],
    }


def _plan_path(tmp_path: Path) -> Path:
    return exec_dir(tmp_path) / PLAN_FILENAME


def _drop_plan(tmp_path: Path, plan: dict) -> Path:
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    path = d / PLAN_FILENAME
    path.write_text(json.dumps(plan))
    return path


def _boundary(when: datetime) -> datetime:
    """The 4 h floor, recomputed here rather than imported from the module under test."""
    when = when.astimezone(timezone.utc)
    return when.replace(hour=when.hour - when.hour % 4, minute=0, second=0, microsecond=0)


def _record(tmp_path: Path, when: datetime = NOW) -> dict:
    return read_exec_record(exec_record_path(tmp_path / "journal", _boundary(when)))


def _plan_entry(tmp_path: Path, when: datetime = NOW, index: int = 0) -> dict:
    return _record(tmp_path, when)["plans"][index]


def _intent_entry(tmp_path: Path, index: int, when: datetime = NOW) -> dict:
    entry = _plan_entry(tmp_path, when)
    return next(i for i in entry["intents"] if i["index"] == index)


def _quote(instrument_id="BTC/EUR.KRAKEN", bid=30000.0, ask=30001.0):
    return SimpleNamespace(instrument_id=instrument_id, bid_price=bid, ask_price=ask)


@pytest.fixture(autouse=True)
def _reset_executor_hooks():
    """`executor._publish_verdict`/`._metrics` are module-level globals (the cycle.set_metrics_sink
    pattern) -- a hook left installed by one test fires inside every later one in the same
    process, against a tmp_path that no longer exists."""
    yield
    set_executor_hooks()


@pytest.fixture(autouse=True)
def _the_tick_backstop_never_fires(caplog):
    """`on_timer`'s catch-all is a backstop for the unforeseen, not a mechanism any test may lean
    on: every refusal below has its own named path. It masked a missing method during development
    -- twenty-six tests stayed green while an intent silently never refused -- so a test that goes
    green WHILE the backstop fires now fails instead."""
    caplog.set_level(logging.ERROR, logger="zcrypto.engine.executor")
    yield
    swallowed = [r.getMessage() for r in caplog.records if "dropping the running plan" in r.getMessage()]
    assert swallowed == []


class RecordingMetrics:
    def __init__(self):
        self.orders = []

    def inc_order(self, outcome):
        self.orders.append(outcome)


# --- the happy path -----------------------------------------------------------------------------


def test_a_valid_plan_subscribes_then_submits_one_post_only_gtc_order_at_the_touch(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    assert client.subscribed == ["BTC/EUR.KRAKEN"]
    assert client.submitted == []  # nothing submits before a quote exists

    ex.on_quote(_quote())
    assert len(client.submitted) == 1
    order, params = client.submitted[0]
    assert order.post_only is True
    assert order.time_in_force == TimeInForce.GTC
    assert order.order_side == OrderSide.BUY
    assert order.price == 30000.0  # the BID -- a buy joins the near touch, it does not cross
    assert order.quantity == 0.001  # 30 EUR / 30000
    assert params is None  # spot: no leverage param

    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "submitting"  # the write-ahead row, not yet acknowledged by the venue
    assert row["client_order_id"] == "O-1"
    assert row["intent"] == _intent()
    assert row["plan_id"] == "p-1" and row["intent_index"] == 0


def test_a_sell_intent_joins_the_ask_and_a_margin_intent_carries_the_leverage_param(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", leverage=3)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    order, params = client.submitted[0]
    assert order.order_side == OrderSide.SELL
    assert order.price == 30001.0  # the ASK
    assert params == {"leverage": 3}


def test_pickup_journals_the_plan_verbatim_then_deletes_the_file(tmp_path):
    plan = _plan_dict()
    ex = _executor(tmp_path)
    path = _drop_plan(tmp_path, plan)

    ex.on_timer(NOW)

    assert not path.exists()
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "accepted"
    assert entry["plan"] == plan  # verbatim, not a re-serialisation of the parsed model
    assert entry["reasons"] == []
    assert [i["index"] for i in entry["intents"]] == [0]


def test_an_idle_tick_reads_no_gate_at_all(tmp_path):
    """The cheap-lstat claim: with no plan file there is no gate evaluation and therefore no venue
    read. The second half is what stops this passing vacuously against an executor that never
    evaluates anything."""
    gate = CountingGate()
    ex = _executor(tmp_path, gate=gate)

    ex.on_timer(NOW)
    assert gate.calls == 0

    _drop_plan(tmp_path, _plan_dict())
    ex.on_timer(NOW)
    assert gate.calls > 0


# --- the gate refusals --------------------------------------------------------------------------


def test_the_kill_file_refuses_the_submission_and_no_order_reaches_the_client(tmp_path):
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.NONE))
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == []
    assert client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert "kill_switch" in intent["reasons"]
    assert metrics.orders == ["refused"]


def test_reduce_only_refuses_an_open_intent(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)

    assert client.submitted == [] and client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert "restart_hold" in intent["reasons"]


def test_reduce_only_permits_a_close_intent(tmp_path):
    """The other half of the level rule -- without it, a `_level_permits` that refused everything
    at REDUCE_ONLY would pass the test above."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(
        tmp_path, _plan_dict(intents=[{"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "qty": 0.01}])
    )

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.subscribed == ["BTC/EUR.KRAKEN"]
    assert len(client.submitted) == 1


# --- the ledger write-ahead ---------------------------------------------------------------------


def test_a_failing_ledger_write_refuses_the_submission_and_the_client_is_never_called(tmp_path, monkeypatch):
    """The write-ahead precondition, constructed: `append_submitted_row` raises, so no order may
    exist. Asserts WHICH refusal fired -- the ledger one, not the gate's."""

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    monkeypatch.setattr(executor_module, "append_submitted_row", _raise)
    ex.on_quote(_quote())

    assert client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["exec ledger write failed"]
    assert metrics.orders == ["refused"]


def test_a_raising_submit_leaves_the_write_ahead_row_and_journals_the_intent_ambiguous(tmp_path):
    """The transport failing AFTER the write-ahead row is the case the row exists for: the process
    cannot know whether the venue got it, so the row stays `submitting` and the intent is journaled
    ambiguous -- never refused (which would claim no order exists) and never propagated."""
    client = StubClient(submit_raises=RuntimeError("connection reset"))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "submitting"
    assert _intent_entry(tmp_path, 0)["outcome"] == "ambiguous"


# --- venue truth --------------------------------------------------------------------------------


def test_a_raising_venue_read_refuses_the_plan_with_no_subscribe_and_no_submit(tmp_path):
    client = StubClient(StubCache(raises=True))
    ex = _executor(tmp_path, client=client)
    path = _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert entry["reasons"] == ["no venue truth"]
    assert not path.exists()


def test_an_intent_symbol_absent_from_venue_truth_is_refused(tmp_path, monkeypatch):
    """A venue state that parsed and balanced but carries no entry for the intent's symbol. Without
    the guard this is a KeyError/AttributeError at a submission site, which has no safe direction."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)

    def _stateless(cache, *, clock):
        return VenueState(snapshot_at=clock(), instruments={}, positions={}, balances={"ZEUR": 1000.0})

    monkeypatch.setattr(executor_module, "venue_state_from_cache", _stateless)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["BTC/EUR is absent from venue truth"]


# --- the plan walls -----------------------------------------------------------------------------


def test_an_expired_plan_is_journaled_refused_and_deleted(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    path = _drop_plan(tmp_path, _plan_dict(created_at=NOW - timedelta(minutes=61)))

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert any("expired" in r for r in entry["reasons"])
    assert not path.exists()


def test_a_plan_id_already_ledgered_is_refused(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    append_plan_entry(
        tmp_path / "journal",
        _boundary(NOW),
        {"plan_id": "p-1", "received_at": NOW.isoformat(), "disposition": "accepted", "reasons": [], "plan": {}, "intents": []},
        verdict=GateVerdict(level=GateLevel.FULL, reasons=(), inputs={}),
        evaluated_at=NOW,
    )
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _record(tmp_path)["plans"][-1]
    assert entry["disposition"] == "refused"
    assert entry["reasons"] == ["plan_id already ledgered"]


def test_an_over_cap_plan_is_refused_naming_the_cap(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=120.0)]))

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert any("exceeds the cap" in r for r in entry["reasons"])


def test_a_margin_floor_violating_plan_is_refused_naming_the_floor(tmp_path):
    """Free ZEUR 50 against 90 EUR at 3x: 30 EUR of margin needs 75 EUR of collateral at the 250%
    floor. Reads the live balance the executor pulled from venue truth, not from config."""
    client = StubClient(StubCache(balances={"ZEUR": 50.0}))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=90.0, leverage=3)]))

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert any("margin floor" in r for r in entry["reasons"])


def test_an_unparseable_plan_is_journaled_and_deleted(tmp_path):
    ex = _executor(tmp_path)
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    path = d / PLAN_FILENAME
    path.write_text("{not json")

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert entry["plan_id"] == "unparseable"
    assert entry["plan"] == {}
    assert entry["disposition"] == "refused" and entry["reasons"]
    assert not path.exists()


def test_the_dedup_window_is_computed_in_utc_not_the_callers_offset(tmp_path):
    """A plan ledgered early on one UTC day, re-dropped a few hours later while the caller's clock
    carries a negative offset: `now.date()` in that offset is still the PREVIOUS day, so an
    uncoerced scanner window ([08-13, 08-12]) misses the 08-14 record entirely and the plan runs a
    second time. The executor coerces to UTC at every ledger call site."""
    journal_dir = tmp_path / "journal"
    ledgered_at = datetime(2026, 8, 14, 0, 0, tzinfo=timezone.utc)
    append_plan_entry(
        journal_dir,
        ledgered_at,
        {
            "plan_id": "p-1",
            "received_at": ledgered_at.isoformat(),
            "disposition": "accepted",
            "reasons": [],
            "plan": {},
            "intents": [],
        },
        verdict=GateVerdict(level=GateLevel.FULL, reasons=(), inputs={}),
        evaluated_at=ledgered_at,
    )
    # 2026-08-14T04:00Z, spelled in UTC-5 where `.date()` reads 2026-08-13.
    now = datetime(2026, 8, 13, 23, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert now.astimezone(timezone.utc) == datetime(2026, 8, 14, 4, 0, tzinfo=timezone.utc)

    client = StubClient()
    ex = _executor(tmp_path, client=client, clock=lambda: now)
    _drop_plan(tmp_path, _plan_dict(created_at=now - timedelta(minutes=30)))

    ex.on_timer(now)

    assert client.subscribed == [] and client.submitted == []
    entry = _record(tmp_path, now)["plans"][-1]
    assert entry["reasons"] == ["plan_id already ledgered"]


# --- the per-intent dedup belt ------------------------------------------------------------------


def test_a_restored_plan_whose_intent_already_submitted_is_refused_at_the_plan_wall(tmp_path):
    """The realistic restart: the plan file is restored after intent 0 already reached the venue.
    `ledgered_plan_ids` unions plan entries AND submitted rows' plan_ids, so the outer wall stops
    it before any intent starts -- no resubmission across a restart."""
    client = StubClient()
    first = _executor(tmp_path, client=client)
    plan = _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    _drop_plan(tmp_path, plan)
    first.on_timer(NOW)
    first.on_quote(_quote())
    assert len(client.submitted) == 1

    restored = StubClient()
    second = _executor(tmp_path, client=restored)
    _drop_plan(tmp_path, plan)
    second.on_timer(NOW)

    assert restored.submitted == [] and restored.subscribed == []
    assert _record(tmp_path)["plans"][-1]["reasons"] == ["plan_id already ledgered"]


def test_the_per_intent_belt_skips_a_ledgered_intent_and_starts_the_next(tmp_path):
    """The inner belt, reached the only way it can be: the plan wall above fires first for any
    restored FILE, so the belt is proved against a resumed plan whose intent 0 carries a REAL
    submitted row written by the real `_submit` path. A crash loses the in-memory queue, not the
    row -- so the belt must never resubmit index 0."""
    client = StubClient()
    first = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))
    first.on_timer(NOW)
    first.on_quote(_quote())
    assert len(client.submitted) == 1

    resumed_client = StubClient()
    resumed = _executor(tmp_path, client=resumed_client)
    resumed._plan = first._plan
    resumed._plan_cycle_ts = first._plan_cycle_ts
    resumed._index = 0

    resumed.on_timer(NOW)

    assert _intent_entry(tmp_path, 0)["outcome"] == "already_ledgered"
    assert resumed_client.submitted == []
    assert resumed_client.subscribed == ["ETH/EUR.KRAKEN"]


# --- sizing and the quote deadline ---------------------------------------------------------------


def test_a_below_minimum_sizing_refuses_the_intent(tmp_path):
    instruments = _all_instruments(**{INSTRUMENT_IDS["BTC/EUR"]: _fake_instrument(INSTRUMENT_IDS["BTC/EUR"], ordermin=1.0)})
    client = StubClient(StubCache(instruments=instruments))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert any("ordermin" in r for r in intent["reasons"])


def test_no_quote_inside_the_wait_refuses_the_intent(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    assert client.subscribed == ["BTC/EUR.KRAKEN"]
    ex.on_timer(NOW + timedelta(seconds=31))

    assert client.submitted == []
    assert client.unsubscribed == ["BTC/EUR.KRAKEN"]
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert any("no quote" in r for r in intent["reasons"])


# --- order events -------------------------------------------------------------------------------


class OrderAccepted:
    def __init__(self, client_order_id):
        self.client_order_id = client_order_id


class OrderFilled:
    def __init__(self, client_order_id, last_qty):
        self.client_order_id = client_order_id
        self.last_qty = last_qty


class OrderRejected:
    def __init__(self, client_order_id, reason):
        self.client_order_id = client_order_id
        self.reason = reason


def test_an_acceptance_then_a_full_fill_closes_the_intent_and_the_next_one_starts(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_order_event(OrderAccepted("O-1"))
    assert _record(tmp_path)["submitted"][0]["state"] == "accepted"

    ex.on_order_event(OrderFilled("O-1", 0.001))
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "filled" and row["filled_qty"] == 0.001
    assert _intent_entry(tmp_path, 0)["outcome"] == "filled"

    ex.on_timer(NOW + timedelta(seconds=5))
    assert client.subscribed == ["BTC/EUR.KRAKEN", "ETH/EUR.KRAKEN"]


def test_a_rejection_closes_the_intent_as_rejected(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_order_event(OrderRejected("O-1", "EOrder:Post only order"))

    assert _record(tmp_path)["submitted"][0]["state"] == "rejected"
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "rejected"
    assert intent["reasons"] == ["EOrder:Post only order"]


# --- the telemetry hooks -------------------------------------------------------------------------


def test_the_verdict_hook_sees_every_evaluation_and_a_raising_hook_never_stops_a_submission(tmp_path):
    seen = []

    def _publish(verdict, *, evaluated_at):
        seen.append((verdict.level, evaluated_at))
        raise RuntimeError("gauge registry is gone")

    metrics = RecordingMetrics()
    set_executor_hooks(publish_verdict=_publish, metrics=metrics)
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    assert seen and all(level == GateLevel.FULL for level, _ in seen)
    assert metrics.orders == ["submitted"]
