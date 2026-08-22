from __future__ import annotations

import json
import logging
import re
from collections import namedtuple
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.model.enums import LiquiditySide, OrderSide, OrderStatus, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.orders.base import Order

import cli.engine.execledger as execledger_module
import cli.engine.executor as executor_module
from cli.config import EngineConfig
from cli.engine.errors import EngineError
from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, GateVerdict, exec_dir
from cli.engine.execledger import (
    append_plan_entry,
    append_submitted_row,
    exec_record_path,
    open_submitted_rows,
    read_exec_record,
    update_submitted_row,
)
from cli.engine.executor import ProbeExecutor, set_executor_hooks, size_probe_order
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder
from cli.engine.probeplan import PLAN_FILENAME
from cli.engine.venue import VenueStatus
from cli.engine.venueledger import write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

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


_VENUE_MUTATING_NAMES = ("submit_order", "cancel_order", "order_factory")


def test_the_venue_mutating_names_have_exactly_one_module():
    """D4's structural pin: all venue-mutating calls live in cli/engine/executor.py. A text walk,
    not an import walk -- a reference in a comment is still a reference a refactor can activate.
    `cancel_order` is on the list because the maker-first ladder cancels: a cancel reaches the venue
    exactly as a submit does, so a second module learning to cancel is the same escape."""
    offenders = []
    for path in sorted(Path("cli").rglob("*.py")):
        if path.as_posix() == "cli/engine/executor.py":
            continue
        text = path.read_text()
        if any(name in text for name in _VENUE_MUTATING_NAMES):
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

    def __init__(self, *, instruments=None, balances=None, positions=None, open_orders=None, closed_orders=None, raises=False):
        self._instruments = _all_instruments() if instruments is None else instruments
        self._balances = {"ZEUR": 1000.0} if balances is None else balances
        self._positions = positions or {}
        self._closed: dict[str, list] = {}
        self._open_orders = open_orders or []
        self._closed_orders = closed_orders or []
        self._raises = raises

    def instrument(self, instrument_id):
        if self._raises:
            raise RuntimeError("cache read failed")
        return self._instruments.get(str(instrument_id))

    @staticmethod
    def _position_key(instrument_id):
        """The installed Cache's accessors are Cython-typed and REFUSE a str -- `TypeError:
        Argument 'instrument_id' has incorrect type`. This stub used to coerce with `str()`, which
        accepted what production could not: every live `_publish_fill` raised into its swallowing
        `except` and the position/PnL gauges never moved, with the whole suite green. Refusing here
        is what makes that class of defect visible at all."""
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError(
                f"Argument 'instrument_id' has incorrect type (expected InstrumentId, got {type(instrument_id).__name__})"
            )
        return str(instrument_id)

    def positions_open(self, *, instrument_id=None, **kwargs):
        return self._positions.get(self._position_key(instrument_id), [])

    def positions_closed(self, *, instrument_id=None, **kwargs):
        return self._closed.get(self._position_key(instrument_id), [])

    def set_position(self, symbol, signed_qty, *, realized_pnl=None):
        """What the Cache says is held, in the shape `_held()` builds -- the one accessor a test
        needs to make the venue disagree with the ledger, or to land a holding the engine never
        ordered (the manual settle). `realized_pnl` is `Money | None` on a real Position, and the
        None is the ordinary case for a leg with no closed round trip yet."""
        self._positions[INSTRUMENT_IDS[symbol]] = [SimpleNamespace(signed_qty=signed_qty, realized_pnl=realized_pnl)]

    def close_position(self, symbol, realized_pnl):
        """A CLOSED position carrying realized PnL -- what `positions_closed` serves once a round
        trip is done, and the half a sum over open positions alone would silently lose."""
        self._closed.setdefault(INSTRUMENT_IDS[symbol], []).append(SimpleNamespace(signed_qty=0.0, realized_pnl=realized_pnl))

    def move_position(self, symbol, delta):
        held = self._positions.get(INSTRUMENT_IDS[symbol], [])
        realized = held[0].realized_pnl if held else None
        self.set_position(symbol, sum(float(p.signed_qty) for p in held) + delta, realized_pnl=realized)

    def orders_open(self, *, venue=None, **kwargs):
        return list(self._open_orders)

    def orders(self, *, venue=None, **kwargs):
        """The WIDE read the startup reconciliation takes -- the installed `Cache.orders` filters
        the full order index, so it serves closed orders alongside open ones, and a closed one is
        by definition absent from `orders_open`. A stub answering only the open half would hand
        every closed-while-down test the empty population the pre-D7 pass saw."""
        return list(self._open_orders) + list(self._closed_orders)

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

    @property
    def last_order_id(self):
        """The client_order_id of the most recent submission -- every reprice and every IOC attempt
        mints a new one, so a ladder test must never hardcode `O-1`."""
        return str(self.submitted[-1][0].client_order_id)

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


def _held(**by_symbol):
    """`StubCache(positions=...)`: constructed `signed_qty`/`realized_pnl` namespaces keyed by
    instrument id -- exactly the shape `Cache.positions_open(instrument_id=...)` returns (negative =
    SHORT). `realized_pnl` is `Money | None` on a real Position and None is the ordinary case."""
    return {INSTRUMENT_IDS[symbol]: [SimpleNamespace(signed_qty=qty, realized_pnl=None)] for symbol, qty in by_symbol.items()}


def _venue_record(tmp_path: Path, *, balances, positions=None, when: datetime = NOW) -> Path:
    """A REAL schema-2 `venue-<HH>.json` through `write_venue_record`. The executor
    `validate_venue_record`-checks what it reads, so a hand-built dict would prove nothing about the
    shape the engine actually writes."""
    state = VenueState(snapshot_at=when, instruments={}, positions=positions or {}, balances=balances)
    return write_venue_record(
        tmp_path / "journal",
        _boundary(when),
        state=state,
        concordance=ConcordanceVerdict(ok=True, failures=()),
        code_version="test",
    )


def _open_order(client_order_id, *, is_reduce_only=False, filled_qty=0.0):
    """A resting order as reconciliation adopts it. `is_reduce_only` is present because the real
    adopted report carries it -- and the startup pass must be seen NOT to consult it. `filled_qty`
    and `is_open`/`status` are what the startup reconciliation reads: the real `Order` carries the
    quantity applied to it during reconciliation, and its own open predicate is what the pass now
    derives the resting population from."""
    return SimpleNamespace(
        client_order_id=client_order_id,
        is_reduce_only=is_reduce_only,
        filled_qty=filled_qty,
        is_open=True,
        status=OrderStatus.ACCEPTED,
    )


def _closed_order(client_order_id, status, *, filled_qty=0.0):
    """The order reconciliation leaves behind for one that reached a terminal state while this
    process was down. It is absent from `orders_open` entirely, which is exactly what made it
    invisible to the pass before the wide read."""
    return SimpleNamespace(
        client_order_id=client_order_id,
        is_reduce_only=False,
        filled_qty=filled_qty,
        is_open=False,
        status=status,
    )


def _submitted_row(tmp_path: Path, client_order_id: str, *, reduce_only: bool, when: datetime = NOW, index: int = 0) -> dict:
    """A write-ahead row a previous process left behind, through the real `append_submitted_row` --
    `state` is one of `_OPEN_ORDER_STATES`, so the row is in the re-attach set."""
    row = {
        "plan_id": "p-before-the-restart",
        "intent_index": index,
        "client_order_id": client_order_id,
        "intent": {"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "notional_eur": 30.0},
        "order": {
            "symbol": "BTC/EUR",
            "side": "sell",
            "qty": 0.001,
            "price": 30000.0,
            "notional": 30.0,
            "time_in_force": "GTC",
            "post_only": True,
            "leverage": 2,
            "reduce_only": reduce_only,
        },
        "state": "accepted",
        "filled_qty": 0.0,
        "events": [],
    }
    append_submitted_row(
        tmp_path / "journal",
        _boundary(when),
        row,
        verdict=GateVerdict(level=GateLevel.REDUCE_ONLY, reasons=("restart_hold",), inputs={}),
        evaluated_at=when,
    )
    return row


def _quote(instrument_id="BTC/EUR.KRAKEN", bid=30000.0, ask=30001.0):
    return SimpleNamespace(instrument_id=instrument_id, bid_price=bid, ask_price=ask)


def _named(name, **attrs):
    """An instance of a dynamically created class called `name`, so the executor's
    `type(event).__name__` dispatch sees the real event names on plain stub objects."""
    return type(name, (SimpleNamespace,), {})(**attrs)


class _Clock:
    """A movable clock. The executor timestamps `last_quote_at` off its own clock, so a fixed
    `lambda: NOW` would make every advanced tick look like 30 s of quote silence and revoke the
    order long before the 15-minute time-box could ever elapse."""

    def __init__(self, start=NOW):
        self.now = start

    def __call__(self):
        return self.now


def _intent_outcome(tmp_path, index: int = 0, when: datetime = NOW) -> str:
    return _intent_entry(tmp_path, index, when)["outcome"]


def _resting_executor(tmp_path, *, intents=None, bid=30000.0, ask=30001.0, client=None):
    """A plan accepted and its first intent resting: exactly one order at the venue. The trailing
    assert is the point -- a helper that quietly submitted nothing would hand every ladder test
    below a green it never earned."""
    clock = _Clock()
    client = client if client is not None else StubClient()
    ex = _executor(tmp_path, client=client, clock=clock)
    _drop_plan(tmp_path, _plan_dict(intents=intents))
    ex.on_timer(clock.now)
    ex.on_quote(_quote(bid=bid, ask=ask))
    assert len(client.submitted) == 1
    return ex, client, clock


def _advance_ticks(ex, *, minutes):
    """Bare timer ticks from NOW, no quotes and no clock movement -- for a plan that must emit
    nothing whatever the timer does."""
    for step in range(1, int(minutes * 60 // 5) + 1):
        ex.on_timer(NOW + timedelta(seconds=5 * step))


def _advance_with_quotes(ex, client, clock, *, minutes, bid=30000.0, ask=30001.0):
    """Ticks carrying a live quote on every one. The time-box (15 min) can only be reached this way:
    quote silence (30 s) would otherwise revoke the resting order first.

    Stops the moment a cancel goes out, so each test delivers the venue's answer itself -- ticking
    on past an unanswered cancel is the ack watchdog's subject, not this helper's."""
    end = clock.now + timedelta(minutes=minutes)
    while clock.now < end:
        clock.now += timedelta(seconds=10)
        ex.on_quote(_quote(bid=bid, ask=ask))
        ex.on_timer(clock.now)
        if client.canceled:
            return


@pytest.fixture(autouse=True)
def _reset_executor_hooks():
    """`executor._publish_verdict`/`._metrics` are module-level globals (the cycle.set_metrics_sink
    pattern) -- a hook left installed by one test fires inside every later one in the same
    process, against a tmp_path that no longer exists."""
    yield
    set_executor_hooks()


@pytest.fixture(autouse=True)
def _the_tick_backstop_never_fires():
    """`on_timer`'s catch-all is a backstop for the unforeseen, not a mechanism any test may lean
    on: every refusal below has its own named path. It masked a missing method during development
    -- twenty-six tests stayed green while an intent silently never refused -- so a test that goes
    green WHILE the backstop fires fails instead.

    Deliberately NOT `caplog`, which is blind here for two independent reasons. Its handler sits on
    the ROOT logger, and `cli.logging.config.configure` sets `zcrypto.propagate = False` -- so every
    record stops arriving as soon as any CliRunner test has run earlier in the session (and
    `tests/test_engine_command.py` sorts ahead of this file). And `caplog.records` is PHASE-scoped:
    pytest calls `caplog_handler.reset()` entering each phase, so a teardown-time read returns a
    list emptied moments earlier -- vacuous even when this file runs alone. An own handler on the
    executor's own logger, with the logger's level forced for the duration, dodges both.
    """
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("zcrypto.engine.executor")
    handler = _Collect(level=logging.ERROR)
    previous_level = log.level
    log.setLevel(logging.DEBUG)  # a logger's own level wins over any ancestor a CLI test configured
    log.addHandler(handler)
    try:
        yield
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)
    assert [r.getMessage() for r in records if "dropping the running plan" in r.getMessage()] == []


@pytest.fixture
def kill_trip_expected():
    """Requested by the tests that CONSTRUCT a kill trip. Requesting it is also what disarms the
    guard below, so a test that trips the switch without saying so fails."""
    return None


@pytest.fixture(autouse=True)
def _no_unannounced_kill_trip(request):
    """A trip creates a latching file no code may clear and stops this engine for good. Every OTHER
    test in this file is a healthy neighbour that must not cause one -- so the quiet direction is
    proven once, here, against all of them, rather than only against the single external-fill
    construction D11 names. Runs both ways: an announcing test that does NOT trip fails too.

    Watches the executor's own logger for the two reasons `_the_tick_backstop_never_fires` documents
    -- caplog's handler sits on a root the CLI tests have detached, and its records are phase-scoped
    so a teardown read comes back empty."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("zcrypto.engine.executor")
    handler = _Collect(level=logging.CRITICAL)
    previous_level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        yield
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)
    tripped = [r.getMessage() for r in records if "kill switch tripped" in r.getMessage()]
    if "kill_trip_expected" in request.fixturenames:
        assert tripped, "this construction was supposed to trip the kill switch and did not"
    else:
        assert tripped == []


class RecordingMetrics:
    """`_ExecutionMetrics`' surface, recorded. Every method is on it because the executor's hooks
    are wrapped and log-and-continue: a stub missing one would turn a wiring regression into a log
    line no test reads."""

    def __init__(self):
        self.orders = []
        self.fills = []
        self.positions = []
        self.realized = []
        self.external = []

    def inc_order(self, outcome):
        self.orders.append(outcome)

    def inc_external(self, disposition):
        self.external.append(disposition)

    def inc_fill(self, liquidity, fee_eur):
        self.fills.append((liquidity, fee_eur))

    def set_position(self, symbol, qty):
        self.positions.append((symbol, qty))

    def set_realized(self, value):
        self.realized.append(value)


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


def test_a_kill_file_landing_after_the_intent_started_still_refuses_at_the_submit(tmp_path):
    """The taken-never-held property, constructed: the gate reads FULL when the intent starts and
    subscribes, and the kill file lands in the window before the quote arrives. `_submit` evaluates
    for itself, so the order is refused -- an executor carrying the start-time verdict forward, or
    accepting one as a parameter, would submit here."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    assert client.subscribed == ["BTC/EUR.KRAKEN"]

    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_quote(_quote())

    assert client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert "kill_switch" in intent["reasons"]


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
    at REDUCE_ONLY would pass the test above. The 0.001 qty is load-bearing: this intent's EUR
    notional only exists at sizing time, and 0.01 at the fixture touch would be refused by the plan
    cap instead, greening this test for the wrong reason. The venue record is load-bearing too: at
    REDUCE_ONLY the disposal takes the full `qty <= balance` bound (D10), so without a record
    showing the coin this intent is refused by the classification rather than permitted by the
    level -- which is the opposite of what this test is about."""
    client = StubClient()
    _venue_record(tmp_path, balances={"XXBT": 0.002, "ZEUR": 1000.0})
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(
        tmp_path, _plan_dict(intents=[{"symbol": "BTC/EUR", "side": "sell", "action": "close", "mode": "execute", "qty": 0.001}])
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


def test_a_raising_submit_marks_the_row_ambiguous_and_leaves_it_in_the_re_attach_set(tmp_path):
    """The transport failing AFTER the write-ahead row is the case the row exists for: the process
    cannot know whether the venue got it, so the row says `ambiguous` -- the honest state, and an
    OPEN one, so re-attach still finds a possibly-live order. Never `refused`, which would claim no
    order exists, and never propagated."""
    client = StubClient(submit_raises=RuntimeError("connection reset"))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1  # exactly one -- a retry wrapped around submit_order is banned
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "ambiguous"
    assert [r["client_order_id"] for _, r in open_submitted_rows(tmp_path / "journal", NOW)] == ["O-1"]
    assert _intent_entry(tmp_path, 0)["outcome"] == "ambiguous"


def test_an_ambiguous_submit_drops_the_rest_of_the_plan(tmp_path):
    """Owner ruling: an ambiguous outcome stops the plan. The order may be live, so the position and
    free balance the notional cap and margin floor authorized every LATER intent against are
    unknown -- and authorizing an order on unknown state is what refusal by default forbids. The
    remaining intents are journaled naming the ambiguous predecessor, so the ledger says why they
    never ran."""
    client = StubClient(submit_raises=RuntimeError("connection reset"))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_timer(NOW + timedelta(seconds=5))  # the tick that would otherwise start intent 1

    assert len(client.submitted) == 1
    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # intent 1 never even subscribed
    assert _intent_entry(tmp_path, 0)["outcome"] == "ambiguous"
    second = _intent_entry(tmp_path, 1)
    assert second["outcome"] == "refused"
    assert any("ambiguous" in r for r in second["reasons"])
    # The ambiguous intent's row says so, and `ambiguous` is an OPEN state -- re-attach still sees
    # a possibly-live order.
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"


def test_a_failing_plan_journal_leaves_the_file_and_runs_nothing(tmp_path, monkeypatch):
    """Journal first, delete second, run third. A plan that cannot be journaled is neither deleted
    nor run -- the next tick re-picks the file, and only a working ledger ever lets it through."""

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    client = StubClient()
    ex = _executor(tmp_path, client=client)
    path = _drop_plan(tmp_path, _plan_dict())
    monkeypatch.setattr(executor_module, "append_plan_entry", _raise)

    ex.on_timer(NOW)

    assert path.exists()
    assert client.subscribed == [] and client.submitted == []


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


def test_an_eur_only_balance_is_the_free_cash_figure_the_margin_floor_is_measured_against(tmp_path):
    """The LIVE spelling: the pre-merge read against the engine returned `{'EUR': 99.84}`, so the
    `ZEUR`-then-`EUR` fallback resolves on its SECOND arm in production. Every other fixture here
    spells it `ZEUR`, which left the live-resolving arm unpinned -- deleting it would have left this
    suite green while production sized every plan against 0.00 free EUR and refused it.

    The assertion is the figure inside the reason, not the word 'margin floor': dropping the `EUR`
    arm still refuses (0.00 is under any floor), so only the VALUE separates the two worlds."""
    client = StubClient(StubCache(balances={"EUR": 99.84}))
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=90.0, leverage=2)]))

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert entry["disposition"] == "refused"
    assert any("free_zeur 99.84 EUR" in r for r in entry["reasons"])


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


class OrderRejected:
    def __init__(self, client_order_id, reason):
        self.client_order_id = client_order_id
        self.reason = reason


class _FakeMoney:
    """`float(commission)` + `commission.currency.code` -- the two accessors the fill row reads off
    nautilus's Money, which is not importable as a plain value here."""

    def __init__(self, amount, code="EUR"):
        self._amount = amount
        self.currency = _FakeCurrency(code=code)

    def __float__(self):
        return float(self._amount)


def _fill(client_order_id, last_qty, *, px=30000.0, fee=0.012, fee_code="EUR", symbol="BTC/EUR", liquidity=LiquiditySide.MAKER):
    """An `OrderFilled` carrying every field the executor's fill row reads -- the real event always
    has them, so the stub must too, or the row would be pinned against a shape the venue never
    sends.

    `liquidity_side` is the REAL `LiquiditySide` member, never the string it looks like: in the
    installed nautilus-trader it is an int-backed enum whose `__str__` returns the NUMBER, so a
    plain-string fake makes `str(event.liquidity_side)` look correct here while production writes
    '1'/'2'. That gap hid a live defect in both the ledger row and the metric label.

    `instrument_id` is the REAL `InstrumentId` for the same reason: the venue's `OrderFilled`
    carries one, and the Cython Cache accessors `_publish_fill` hands it to refuse anything else."""
    return _named(
        "OrderFilled",
        client_order_id=client_order_id,
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS[symbol]),
        last_qty=last_qty,
        last_px=px,
        commission=_FakeMoney(fee, fee_code),
        liquidity_side=liquidity,
        trade_id="T-1",
    )


def _deliver_fill(ex, client, client_order_id, qty, *, symbol="BTC/EUR", side="buy", px=30000.0, **kwargs):
    """Deliver a fill the way the venue does: the Cache position moves FIRST, then the strategy sees
    the event. Read out of the installed nautilus-trader (`execution/engine.pyx`): `_handle_event`
    calls `_handle_order_fill` -- which adds or updates the Position in the Cache -- and only then
    publishes the event to the strategy's own topic. A harness that left the Cache untouched would
    model a divergence that never happens, and D11's post-terminal reconciliation would trip on every
    healthy fill."""
    client.cache.move_position(symbol, qty if side == "buy" else -qty)
    ex.on_order_event(_fill(client_order_id, qty, px=px, symbol=symbol, **kwargs))


def test_an_acceptance_then_a_full_fill_closes_the_intent_and_the_next_one_starts(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_order_event(OrderAccepted("O-1"))
    assert _record(tmp_path)["submitted"][0]["state"] == "accepted"

    _deliver_fill(ex, client, "O-1", 0.001)
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "filled" and row["filled_qty"] == 0.001
    assert _intent_entry(tmp_path, 0)["outcome"] == "filled"

    ex.on_timer(NOW + timedelta(seconds=5))
    assert client.subscribed == ["BTC/EUR.KRAKEN", "ETH/EUR.KRAKEN"]


# --- the fill metrics -----------------------------------------------------------------------------


def test_a_fill_publishes_its_liquidity_side_fee_and_the_position_the_cache_now_holds(tmp_path):
    """The live view of the row the fill just wrote: same event, same numbers. The Cache read is the
    point of the position half -- publishing the executor's own running total instead would report
    what this process THINKS it holds, which is exactly the quantity the reconciliation exists to
    doubt."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, fee=0.37, liquidity=LiquiditySide.TAKER)

    assert metrics.fills == [("taker", 0.37)]
    assert metrics.positions == [("BTC/EUR", 0.001)]
    assert metrics.realized == [0.0]  # no realized leg on this position yet -- a None contributes zero


@pytest.mark.parametrize(
    ("side", "row_value", "label"),
    [
        (LiquiditySide.MAKER, "MAKER", "maker"),
        (LiquiditySide.TAKER, "TAKER", "taker"),
        (LiquiditySide.NO_LIQUIDITY_SIDE, "NO_LIQUIDITY_SIDE", "no_liquidity_side"),
    ],
    ids=["maker", "taker", "unattributed"],
)
def test_a_fills_liquidity_side_is_named_not_numbered_in_both_the_row_and_the_metric(tmp_path, side, row_value, label):
    """`LiquiditySide` is an `IntFlag` over `ReprEnum` in the installed nautilus-trader, so
    `str(LiquiditySide.MAKER)` is '1', not 'MAKER'. A `str()` here puts '1'/'2' in the forensic row
    that outlives the probe AND mints a `liquidity="1"` metric child while the pre-registered
    maker/taker series read zero for the whole window -- the board reporting nothing traded while
    money moves, and the maker-vs-taker blend is the measurement this ladder exists to produce.

    Driven with the REAL enum member: a plain-string fake makes the broken idiom look correct."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, liquidity=side)

    fill_events = [e for e in _record(tmp_path)["submitted"][0]["events"] if e.get("event") == "fill"]
    assert [e["liquidity"] for e in fill_events] == [row_value]
    assert metrics.fills == [(label, pytest.approx(0.012))]


def test_a_composite_liquidity_side_never_reaches_the_helper_that_would_abort_the_process(tmp_path):
    """`liquidity_side_to_str` does not merely raise on an out-of-range value -- on 3 it hard-aborts
    the process with a Rust capacity-overflow panic (SIGABRT), which no `except BaseException` can
    catch. And 3 is CONSTRUCTIBLE as `LiquiditySide.MAKER | LiquiditySide.TAKER`, because IntFlag
    keeps out-of-range composites under its KEEP boundary. So the membership guard, not the
    try/except, is what keeps a live engine alive here: reaching the helper at all would kill the
    process on the write-ahead path with real money in flight.

    Unreachable in practice -- the fill's value arrives from the Rust core as 0, 1 or 2 -- but the
    failure mode is an uncatchable abort, so it is guarded rather than argued about. That this test
    RETURNS is itself half the assertion: before the guard, it takes the whole pytest process down
    with exit 134."""
    composite = LiquiditySide.MAKER | LiquiditySide.TAKER
    assert int(composite) == 3 and composite not in tuple(LiquiditySide)

    # The guard function directly, first: the one call that would abort.
    assert executor_module._liquidity(composite) == "3"

    # Then the whole write-ahead path: the fill still earns its forensic row.
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, liquidity=composite)

    row = _record(tmp_path)["submitted"][0]
    assert row["filled_qty"] == 0.001
    assert [e["liquidity"] for e in row["events"] if e.get("event") == "fill"] == ["3"]
    assert metrics.fills == [("3", pytest.approx(0.012))]


def test_an_unrecognisable_liquidity_side_still_gets_its_forensic_row(tmp_path):
    """The payload builder sits on the write-ahead path, where a raise costs the fill its row --
    and `liquidity_side_to_str` raises on a non-int and reads garbage memory on an out-of-range
    one. A value the enum cannot name is recorded verbatim and logged, never dropped."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, liquidity="WHO KNOWS")

    row = _record(tmp_path)["submitted"][0]
    assert row["filled_qty"] == 0.001
    fill_events = [e for e in row["events"] if e.get("event") == "fill"]
    assert [e["liquidity"] for e in fill_events] == ["WHO KNOWS"]


def test_a_non_eur_commission_reaches_the_metric_as_no_fee_at_all(tmp_path):
    """A BTC-denominated commission may never be added to a EUR total. The FILL still counts."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, fee=0.00002, fee_code="XXBT")

    assert metrics.fills == [("maker", None)]


def test_realized_pnl_sums_open_and_closed_positions_and_skips_a_non_eur_one(tmp_path):
    """`Position.realized_pnl` is `Money | None`. The None is skipped rather than `float()`-ed, the
    CLOSED positions are summed too (a round trip's PnL lives nowhere else), and a non-EUR position
    is left out rather than added to a EUR total."""
    client = StubClient()
    client.cache.close_position("BTC/EUR", _FakeMoney(-4.5, "ZEUR"))
    client.cache.close_position("BTC/EUR", _FakeMoney(1.25, "EUR"))
    client.cache.close_position("BTC/EUR", _FakeMoney(9999.0, "XXBT"))  # never summed into a EUR total
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001)

    assert metrics.realized == [pytest.approx(-3.25)]


def test_a_raising_fill_metrics_hook_never_costs_the_fill_its_row(tmp_path):
    """Guard-proving: the hook object raises on every call, which is the failure the wrap exists to
    isolate. The ledger row, the intent outcome and the ladder must be untouched -- metrics are
    observation, and observation may never change what this engine does with real money."""

    class _RaisingMetrics:
        def inc_order(self, outcome):
            raise RuntimeError("registry is gone")

        def inc_external(self, disposition):
            raise RuntimeError("registry is gone")

        def inc_fill(self, liquidity, fee_eur):
            raise RuntimeError("registry is gone")

        def set_position(self, symbol, qty):
            raise RuntimeError("registry is gone")

        def set_realized(self, value):
            raise RuntimeError("registry is gone")

    client = StubClient()
    set_executor_hooks(metrics=_RaisingMetrics())
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001)

    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "filled" and row["filled_qty"] == 0.001
    assert _intent_entry(tmp_path, 0)["outcome"] == "filled"


def test_a_late_fill_on_a_superseded_order_is_published_too(tmp_path):
    """The detached path. Its own ledger row is written in exactly the same terms as an in-flight
    one, and its fee is just as real -- counting only in-flight fills would under-report the money
    actually paid while every test stayed green."""
    ex, client, _ = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(OrderAccepted("O-1"))
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-1"))  # the venue's own cancel -> reprice
    assert len(client.submitted) == 2

    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    _deliver_fill(ex, client, "O-1", 0.0004, fee=0.05)  # the superseded order fills late

    assert metrics.fills == [("maker", 0.05)]
    assert metrics.positions == [("BTC/EUR", 0.0004)]


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


# --- the maker-first ladder -----------------------------------------------------------------------


def test_both_crossing_surfaces_count_one_reprice_and_the_sixth_refuses(tmp_path):
    """Surface 1: OrderRejected(due_post_only=True) -- the adapter's synchronous mapping.
    Surface 2: accept-then-venue-cancel (OrderCanceled with no cancel requested). Alternate them:
    5 reprices happen (6 submissions total), the 6th reprice is refused and the intent halts
    unfilled with NO 7th order."""
    ex, client, now = _resting_executor(tmp_path)  # helper: plan accepted, first order submitted
    # _named(name, **attrs) builds an instance of a dynamically created class called `name`, so the
    # executor's type(event).__name__ dispatch sees the real event names on plain stub objects.
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(
                _named(
                    "OrderRejected",
                    client_order_id=client.last_order_id,
                    reason="POST_ONLY_REJECTED: would cross",
                    due_post_only=True,
                )
            )
        else:
            ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
        ex.on_quote(_quote(bid=30000.0, ask=30001.0))
    assert len(client.submitted) == 6  # initial + 5 reprices
    ex.on_order_event(
        _named("OrderRejected", client_order_id=client.last_order_id, reason="POST_ONLY_REJECTED: would cross", due_post_only=True)
    )
    assert len(client.submitted) == 6  # the sixth reprice refused, nothing new
    assert _intent_outcome(tmp_path) == "unfilled"


def test_an_ambiguous_rejection_halts_with_no_second_order(tmp_path):
    """The double-submit construction, seen refused: a timeout surfaced as a rejection carrying no
    Kraken error code and no post-only marker. The intent halts ambiguous; no reprice, no IOC."""
    ex, client, now = _resting_executor(tmp_path)
    ex.on_order_event(
        _named("OrderRejected", client_order_id=client.last_order_id, reason="request timed out", due_post_only=False)
    )
    _advance_ticks(ex, minutes=20)  # deep past the time-box: still nothing may be emitted
    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_an_ambiguous_rejection_drops_the_later_intents_too(tmp_path):
    """The other half of the halt: a plan's remaining intents were authorized against a venue state
    that an order which may be live has just made unknown."""
    ex, client, _ = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_named("OrderRejected", client_order_id=client.last_order_id, reason="request timed out"))
    ex.on_timer(NOW + timedelta(seconds=5))

    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # intent 1 never even subscribed
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_the_time_box_cancels_then_fires_an_ioc_at_the_opposite_touch(tmp_path):
    """The fallback is price-bounded, never a market order: a LIMIT IOC at the opposite touch."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled == [resting_order]
    assert len(client.submitted) == 1  # the cancel is not a submission -- the ack is what fires the IOC

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 2
    ioc, _ = client.submitted[1]
    assert ioc.price == 30001.0  # the ASK -- a buy's opposite touch, bounded by a limit
    assert ioc.time_in_force == TimeInForce.IOC
    assert ioc.post_only is False
    assert ioc.order_side == OrderSide.BUY
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"


def test_a_partial_fill_then_the_time_box_sizes_the_ioc_to_the_remainder(tmp_path):
    """Quantity conservation across orders: 30 EUR at a 30.00 touch is a 1.0 target, 0.4 fills on
    the maker order, so the fallback may only ask for 0.6. A resubmission at full size would
    over-execute the intent by 0.4 -- and every assertion below still passes if it did, except this
    one."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    assert client.submitted[0][0].quantity == 1.0
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0)
    assert _record(tmp_path)["submitted"][0]["filled_qty"] == 0.4

    _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))

    assert len(client.submitted) == 2
    assert client.submitted[1][0].quantity == 0.6


def test_three_unfilled_iocs_end_the_intent_unfilled_after_exactly_four_submissions(tmp_path):
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)

    for _ in range(3):  # the time-box cancel ack, then each IOC's unfilled remainder coming back
        ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 4  # the maker order + three IOC attempts

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 4  # the budget is three, not four
    assert _intent_outcome(tmp_path) == "unfilled"


def test_every_returned_ioc_remainder_counts_its_outcome_so_the_board_still_balances(tmp_path):
    """The operator surface, not the ledger: during an unfilled fallback ladder the board must not
    show `submitted` advancing with nothing terminal behind it. Each IOC's unfilled remainder comes
    back as an unrequested cancel, writes row state `venue_canceled`, and must count that outcome --
    exactly as the resting-phase arm of the same ack already does. The label test derives its set
    from the executor's `_inc_order` call sites, so it passes whether or not this arm counts; only
    driving the ladder and reading the counter can tell."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)

    for _ in range(4):  # the time-box cancel ack, then all three IOC remainders returning
        ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))

    assert _intent_outcome(tmp_path) == "unfilled"
    assert [row["state"] for row in _record(tmp_path)["submitted"]] == [
        "canceled",
        "venue_canceled",
        "venue_canceled",
        "venue_canceled",
    ]
    # One terminal outcome per order, and the four submissions are fully accounted for.
    assert metrics.orders == [
        "submitted",
        "accepted",
        "canceled",
        "submitted",
        "venue_canceled",
        "submitted",
        "venue_canceled",
        "submitted",
        "venue_canceled",
    ]
    assert metrics.orders.count("venue_canceled") == 3
    terminal = ("canceled", "venue_canceled", "filled", "rejected", "ambiguous")
    assert sum(o in terminal for o in metrics.orders) == metrics.orders.count("submitted") == 4


def test_a_remainder_below_ordermin_ends_the_intent_partial_with_no_further_order(tmp_path):
    """A terminal partial is a legitimate end state -- never an unfillable order the venue rejects."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.00095)  # of a 0.001 target: 5e-05 left, ordermin is 1e-04

    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "partial"
    assert any("ordermin" in r for r in intent["reasons"])
    assert intent["filled_qty"] == 0.00095


def test_a_kill_file_mid_rest_cancels_with_no_fallback_and_halts_the_plan(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())  # a live quote: what revokes here is the gate, not silence
    ex.on_timer(clock.now)
    assert client.canceled == [resting_order]

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 1  # a revoked intent NEVER falls back
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked"
    assert "kill_switch" in intent["reasons"]
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"

    ex.on_timer(NOW + timedelta(seconds=10))
    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # the plan halted: intent 1 never subscribed
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_quote_silence_past_the_window_cancels_and_halts_the_plan(tmp_path):
    """The second intent is what makes the halt half of this name testable: on a single-intent plan
    there is no later intent for a missing halt to wrongly run."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)
    assert client.canceled == [client.submitted[0][0]]

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked"
    assert intent["reasons"] == ["quote_silence"]

    clock.now = NOW + timedelta(seconds=36)
    ex.on_timer(clock.now)
    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # the plan halted: intent 1 never subscribed
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_rest_cancel_mode_rests_five_percent_passive_and_never_executes(tmp_path):
    """The drill: it must never be fillable in the instant between acknowledgment and the cancel,
    so it prices 5% away on the passive side instead of joining the touch."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-cancel")])
    order, _ = client.submitted[0]
    assert order.price == 28500.0  # 5% BELOW the 30000 bid
    assert order.post_only is True and order.time_in_force == TimeInForce.GTC

    ex.on_order_event(OrderAccepted(client.last_order_id))
    assert client.canceled == [order]  # cancelled on the acknowledgment, not on a timer

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 1  # exactly one submission, ever
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "canceled" and row["filled_qty"] == 0.0
    assert _intent_outcome(tmp_path) == "rest_cancel_ok"


def test_a_rest_cancel_drill_that_reaches_the_time_box_still_never_falls_back(tmp_path):
    """The drill's order is never acknowledged, so the cancel-on-ack never fires and the time-box
    is what ends it. A drill that fell back would emit the most aggressive order on this path --
    a marketable IOC -- from an intent whose entire point is that it must not execute."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-cancel")])

    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled == [client.submitted[0][0]]
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))

    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "rest_cancel_ok"


def test_a_disposal_intent_over_the_plan_cap_is_refused_naming_the_cap(tmp_path):
    """D8's sizing-time half: a `qty` intent's EUR notional exists only here (`qty x the chosen
    limit price`), so `plan_refusals` counted it as 0.00 at the plan wall. 0.01 BTC at 30001 is
    300 EUR against the 100 EUR cap -- and the cap has no exclusion for a disposal."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.01)]))

    ex.on_timer(NOW)
    assert _plan_entry(tmp_path)["disposition"] == "accepted"  # the plan wall could not see it
    ex.on_quote(_quote())

    assert client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert any("exceeds the cap" in r for r in intent["reasons"])


def test_a_kraken_coded_rejection_is_terminal_with_no_retry(tmp_path):
    """A positive venue verdict -- the order does not exist and never will. No reprice, no IOC."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_named("OrderRejected", client_order_id=client.last_order_id, reason="EOrder:Insufficient funds"))
    _advance_with_quotes(ex, client, clock, minutes=16)

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "rejected"
    assert intent["reasons"] == ["EOrder:Insufficient funds"]
    assert _record(tmp_path)["submitted"][0]["state"] == "rejected"


# --- the ladder's fix round -----------------------------------------------------------------------


def test_an_accepted_ioc_coming_back_fires_the_next_ioc_never_a_new_gtc(tmp_path):
    """The adapter acknowledges an IOC like any other order. If that acknowledgment put the intent
    back in the resting regime, the IOC's unfilled remainder would read as the venue-cancel crossing
    surface: a reprice burned and a post-only GTC submitted after the time-box already expired --
    up to 7 orders where the design allows 4."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert client.submitted[1][0].time_in_force == TimeInForce.IOC

    ex.on_order_event(OrderAccepted(client.last_order_id))  # the venue acknowledges the IOC
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))

    assert len(client.submitted) == 3
    third, _ = client.submitted[2]
    assert third.time_in_force == TimeInForce.IOC and third.post_only is False


def test_a_fill_pair_that_sums_an_ulp_short_still_terminates_the_intent(tmp_path):
    """0.1 + 0.7 == 0.7999999999999999 -- an ulp under the 0.8 that was ordered. An exact
    `filled >= qty` test strands a fully-filled intent on a dead order forever: the time-box then
    cancels it and the venue answers a cancel-rejection. A remainder below one lot step can never be
    ordered anyway, which is the judgment the BelowMinimum path already makes."""
    assert 0.1 + 0.7 < 0.8  # the defect this pins, spelled out
    ex, client, clock = _resting_executor(tmp_path, bid=37.5, ask=37.6)
    assert client.submitted[0][0].quantity == 0.8  # 30 EUR / 37.50
    ex.on_order_event(OrderAccepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.1, px=37.5)
    _deliver_fill(ex, client, client.last_order_id, 0.7, px=37.5)

    assert _record(tmp_path)["submitted"][0]["state"] == "filled"
    assert _intent_outcome(tmp_path) == "filled"


def test_a_cancel_rejection_parks_the_intent_ambiguous_and_halts_the_plan(tmp_path):
    """The venue positively says the cancel failed, so the order may still rest. Nothing may be
    submitted against a position this process can no longer describe."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))
    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert client.canceled

    ex.on_order_event(_named("OrderCancelRejected", client_order_id=client.last_order_id, reason="EOrder:Unknown order"))

    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "ambiguous"
    # The order may still rest, so the row stays OPEN for re-attach -- never a terminal state.
    assert _record(tmp_path)["submitted"][0]["state"] == "accepted"
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_a_cancel_the_venue_never_answers_ends_ambiguous_and_frees_the_engine(tmp_path):
    """Without a bound on our own bookkeeping the intent parks forever -- and the plan pointer stays
    non-None, so the executor silently ignores EVERY later plan file until a process restart: a dead
    engine that looks alive. The second half of this test is that claim, constructed."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence revokes -- and the venue never answers the cancel
    assert client.canceled

    clock.now = NOW + timedelta(seconds=62)
    ex.on_timer(clock.now)

    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "ambiguous"

    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", created_at=clock.now - timedelta(minutes=1)))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert _record(tmp_path, clock.now)["plans"][-1]["plan_id"] == "p-2"


def test_an_ioc_the_venue_never_answers_ends_ambiguous_rather_than_parking_the_plan(tmp_path):
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))
    assert len(client.submitted) == 2  # the IOC is out at the venue

    clock.now += timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert len(client.submitted) == 2
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_a_refused_resubmission_journals_the_fills_that_already_happened(tmp_path):
    """`update_plan_intent` SETS filled_qty rather than accumulating, so a resubmission refused at
    the gate would otherwise overwrite the intent's summary with 0.0 -- the operator's summary
    surface saying nothing was bought when 0.4 was."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0)

    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))  # the venue's own cancel

    assert len(client.submitted) == 1  # the gate refused the reprice
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["filled_qty"] == 0.4


def test_a_rejection_during_a_time_box_cancel_still_proceeds_to_the_fallback(tmp_path):
    """The other side of the same branch. A time-box cancel declares the maker attempt over and says
    CROSS NOW; a revoke declares the book untradeable and says STOP. Conflating the two silently
    drops the fallback -- and the fallback existing at all is why maker-first was acceptable, since
    an unfilled leg strands the probe. The safety envelope does not depend on this branch: the IOC
    still goes through `_submit`, which evaluates the gate as its first act."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled  # the time-box cancel is out, and the venue answers with a rejection

    ex.on_order_event(
        _named("OrderRejected", client_order_id=client.last_order_id, reason="POST_ONLY_REJECTED: would cross", due_post_only=True)
    )

    assert len(client.submitted) == 2
    ioc, _ = client.submitted[1]
    assert ioc.time_in_force == TimeInForce.IOC and ioc.post_only is False
    assert ioc.price == 30001.0  # the ask -- the fallback, not a reprice at the bid
    assert _record(tmp_path)["submitted"][0]["state"] == "rejected"


def test_a_rejection_arriving_during_a_revoke_terminates_rather_than_repricing(tmp_path):
    """The revoke declared this book untradeable; a post-only rejection is the reprice trigger, so
    repricing here would put a brand-new order on exactly that book. Paired with the time-box test
    above: the branch is only proven with both directions constructed."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))
    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert client.canceled

    ex.on_order_event(
        _named("OrderRejected", client_order_id=client.last_order_id, reason="POST_ONLY_REJECTED: would cross", due_post_only=True)
    )

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked"
    assert "kill_switch" in intent["reasons"]
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_a_disposal_under_the_cap_alone_is_refused_once_the_plans_declared_notional_is_added(tmp_path):
    """Cumulation, not the single-intent breach: 60.00 EUR declared plus 0.0015 BTC at the 30001 ask
    (45.00 EUR) is 105.00 against the 100 EUR cap, and neither half breaches it alone."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(
        tmp_path,
        _plan_dict(
            intents=[
                _intent(notional_eur=60.0),
                _intent(symbol="ETH/EUR", side="sell", action="close", notional_eur=None, qty=0.0015),
            ]
        ),
    )

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, client.submitted[0][0].quantity)
    assert _intent_outcome(tmp_path, 0) == "filled"

    ex.on_timer(NOW + timedelta(seconds=5))
    ex.on_quote(_quote(instrument_id="ETH/EUR.KRAKEN"))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 1)
    assert intent["outcome"] == "refused"
    assert any("exceeds the cap" in r for r in intent["reasons"])


def test_a_second_disposal_cumulates_against_the_first_ones_resolved_notional(tmp_path):
    """Two disposals the plan wall had to count as 0.00 EUR each: 0.002 at the fixture ask is 60.00
    EUR apiece, 120.00 together. The first is under the cap and submits; the second may not."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    disposal = dict(side="sell", action="close", notional_eur=None, qty=0.002)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(**disposal), _intent(symbol="ETH/EUR", **disposal)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    assert len(client.submitted) == 1  # 60.00 EUR alone clears the cap
    ex.on_order_event(OrderAccepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.002, side="sell")

    ex.on_timer(NOW + timedelta(seconds=5))
    ex.on_quote(_quote(instrument_id="ETH/EUR.KRAKEN"))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 1)
    assert intent["outcome"] == "refused"
    assert any("exceeds the cap" in r for r in intent["reasons"])


# --- D10: the reduce-only classification ----------------------------------------------------------


def test_a_margin_closer_is_sized_from_the_live_position_and_carries_the_venue_flag(tmp_path):
    """The plan's 90 EUR would be 0.003 at the fixture ask; the position is 0.001. Sizing from the
    Cache's live position is what makes an over-|held| closer unconstructible rather than merely
    refused -- so the assertion is on the QUANTITY, not on the submission happening. The venue's own
    `reduce_only` flag rides too, so the venue enforces the same bound this process just computed."""
    client = StubClient(StubCache(positions=_held(**{"BTC/EUR": 0.001})))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=90.0, leverage=2)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    order, params = client.submitted[0]
    assert order.quantity == 0.001  # abs(held) -- NOT 90 EUR / 30001, which is 0.00299
    assert order.reduce_only is True
    assert params == {"leverage": 2}
    assert _record(tmp_path)["submitted"][0]["order"]["reduce_only"] is True


@pytest.mark.parametrize(
    "signed_qty, reason",
    [
        (-0.001, "side does not reduce the position"),  # a sell against a SHORT would double it
        (0.0, "no position to close"),
    ],
)
def test_a_margin_closer_that_does_not_reduce_is_refused(tmp_path, signed_qty, reason):
    client = StubClient(StubCache(positions=_held(**{"BTC/EUR": signed_qty})))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=30.0, leverage=2)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == [reason]  # WHICH branch refused, not merely that one did


def test_the_venue_record_refutes_a_disposal_larger_than_the_balance_it_shows(tmp_path):
    """The refutation half of D10: a POSITIVE balance smaller than the signed qty is the venue
    record contradicting the plan, and a contradiction refuses."""
    _venue_record(tmp_path, balances={"XXBT": 0.0005, "ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.0006)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the venue record refutes the signed qty"]


def test_a_disposal_within_the_recorded_balance_submits_a_plain_spot_sell(tmp_path):
    """No venue-side `reduce_only` on a spot order -- Kraken's flag is a margin concept, so the
    executor-side quantity bound plus the venue's insufficient-funds rejection is the whole guard."""
    _venue_record(tmp_path, balances={"XXBT": 0.0005, "ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.0004)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    order, params = client.submitted[0]
    assert order.quantity == 0.0004
    assert order.order_side == OrderSide.SELL
    assert not hasattr(order, "reduce_only")  # never passed to the factory at all
    assert params is None  # spot: no leverage param
    assert _record(tmp_path)["submitted"][0]["order"]["reduce_only"] is False


@pytest.mark.parametrize("balances", [{"ZEUR": 1000.0}, {"XXBT": 0.0, "ZEUR": 1000.0}])
def test_a_zero_or_absent_recorded_balance_cannot_refute_the_signed_qty(tmp_path, balances):
    """The pre-restart record's balances come from the connect-time account read, so it CANNOT see a
    manually-created balance: zero-or-absent proves nothing and the intent proceeds on the G2-signed
    figure, with the venue's own rejection as the backstop. A bound that read absence as 0.0 here
    would refuse the one disposal the probe exists to run."""
    _venue_record(tmp_path, balances=balances)
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.0006)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    assert client.submitted[0][0].quantity == 0.0006


@pytest.mark.parametrize(
    "qty, balances, submits",
    [
        (0.0004, {"XXBT": 0.0005}, True),
        (0.0006, {"XXBT": 0.0005}, False),  # the full qty <= balance bound, not merely refutation
        (0.0004, {"ZEUR": 1000.0}, False),  # absent reads 0.0 once the record is fresh
    ],
)
def test_the_post_restart_disposal_takes_the_full_balance_bound(tmp_path, qty, balances, submits):
    """`reduce_only` implies the restart hold, which implies a fresh startup account read -- so the
    record CAN confirm and the whole `qty <= balance` bound applies, in both directions."""
    _venue_record(tmp_path, balances={**balances, "ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=qty)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    if submits:
        assert len(client.submitted) == 1
        assert not hasattr(client.submitted[0][0], "reduce_only")  # still no venue-side flag
        return
    assert client.submitted == [] and client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the venue record's balance does not cover the signed qty"]


def test_a_spot_close_that_is_not_a_sell_is_refused(tmp_path):
    """A `close` that BUYS spot grows exposure whatever it is labelled -- the classification judges
    the order, never the label."""
    _venue_record(tmp_path, balances={"XXBT": 0.002, "ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="buy", action="close", notional_eur=None, qty=0.0004)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    assert _intent_entry(tmp_path, 0)["reasons"] == ["a spot close must be a sell"]


def test_a_spot_close_without_an_explicit_qty_is_refused(tmp_path):
    """Neither closer shape: no leverage to size against a position, no `qty` for the venue record to
    bound. Nothing here is a reducer this process can vouch for, so it refuses."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=30.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    assert _intent_entry(tmp_path, 0)["reasons"] == ["a spot close needs an explicit qty"]


def test_an_unreadable_venue_record_refuses_the_disposal(tmp_path):
    """A malformed record is not an absent one: absence proves nothing (and proceeds), but a record
    this process cannot read leaves it unable to say whether the venue refutes the qty."""
    day_dir = tmp_path / "journal" / f"{_boundary(NOW):%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / "venue-12.json").write_text('{"schema_version": 99}')
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.0004)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    assert _intent_entry(tmp_path, 0)["reasons"] == ["the venue record could not be read"]


# --- D10: the startup ledger-attach/cancel pass ---------------------------------------------------


def test_the_startup_pass_keeps_only_the_ledger_attached_reduce_only_order(tmp_path):
    """The whole matrix in one construction. (c) is the one that matters most: its adopted report
    says `is_reduce_only=True` and it is canceled anyway -- whether Kraken's echo survives adoption
    truthfully is unverifiable in the installed source, so the write-ahead row is the only witness."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, index=1)
    cache = StubCache(
        open_orders=[
            _open_order("O-attached"),
            _open_order("O-opener"),
            _open_order("O-flagged", is_reduce_only=True),
            _open_order("O-orphan"),
        ]
    )
    client = StubClient(cache)
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == ["O-opener", "O-flagged", "O-orphan"]
    ex.on_timer(NOW + timedelta(seconds=5))
    assert len(client.canceled) == 3  # the pass is a STARTUP pass, not a per-tick sweep


def test_a_terminal_ledger_row_does_not_save_its_order_from_the_startup_pass(tmp_path):
    """The row must be non-terminal to justify keeping the order: a `canceled`/`filled` row says
    this process already accounted for that order, so an order still resting under it is a
    divergence, not something to re-attach to."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-done", reduce_only=True, when=earlier)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-done", state="canceled")
    client = StubClient(StubCache(open_orders=[_open_order("O-done", is_reduce_only=True)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == ["O-done"]


def test_an_unreadable_ledger_cancels_every_resting_order(tmp_path, monkeypatch):
    """The pass may cancel; it may never KEEP what it cannot justify from the ledger. With the
    ledger unreadable, nothing is justifiable -- including the order whose row would have saved it."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "open_submitted_rows", _raise)
    client = StubClient(StubCache(open_orders=[_open_order("O-attached")]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == ["O-attached"]


def test_a_post_restart_fill_on_a_re_attached_order_lands_in_its_own_boundarys_row(tmp_path):
    """D5 across a restart: an adopted order left resting must still have an appender, and the
    appender must write the row's OWN boundary -- the row lives in the 08:00 record, four hours
    behind the tick that adopted it.

    The event is injected DIRECTLY into the own-topic handler, which is the whole scope of the
    claim: what this pins is the appender and its boundary arithmetic, not the delivery. On the live
    engine a reconciled venue order is assigned the EXTERNAL strategy id and its fills arrive on
    `events.order.EXTERNAL` instead -- subscribed, matched against the re-attached rows, and handed
    to this same appender at the end of it. That route is pinned by its own tests, here and in
    tests/test_engine_node.py."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)
    client = StubClient(StubCache(open_orders=[_open_order("O-attached")]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)
    assert client.canceled == []

    ex.on_order_event(_fill("O-attached", 0.0004, px=30000.0))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.0004
    assert [e["event"] for e in row["events"]] == ["fill"]
    assert row["events"][0]["px"] == 30000.0 and row["events"][0]["qty"] == 0.0004
    # Nothing was written to the CURRENT boundary: a fill filed under the tick that saw it would be
    # a row this order's forensics never reach.
    assert not exec_record_path(tmp_path / "journal", _boundary(NOW)).exists()


def test_a_late_fill_on_a_superseded_order_shrinks_the_next_resubmission(tmp_path):
    """Reconciliation by ORDER, not only by re-attach. A fill arriving for an order the executor is
    no longer tracking used to be dropped by the client-order-id filter -- which now feeds remainder
    arithmetic, so the next resubmission would over-ask by exactly the dropped 0.1."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    assert client.submitted[0][0].quantity == 1.0
    ex.on_order_event(OrderAccepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)

    _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-1"))
    assert client.submitted[1][0].quantity == 0.6  # the IOC, sized against the 0.4 already in

    _deliver_fill(ex, client, "O-1", 0.1, px=30.0)  # the late fill, for the order already superseded
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-2"))  # the IOC comes back unfilled

    assert len(client.submitted) == 3
    assert client.submitted[2][0].quantity == 0.5  # not 0.6 -- the late fill was counted
    row = _record(tmp_path)["submitted"][0]
    assert row["client_order_id"] == "O-1" and row["filled_qty"] == 0.5


class _FlakyOrdersCache(StubCache):
    """`orders` raises the first time and answers the second -- the transient a startup pass must
    survive rather than latch through. It is `orders`, not `orders_open`, because that is the read
    the pass now takes FIRST and the only one it takes at all: aimed at the other accessor this
    class would raise nowhere the pass can see, and its test would prove the retry against a read
    that never happens."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    def orders(self, *, venue=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("the cache is not populated yet")
        return super().orders(venue=venue, **kwargs)


def test_a_startup_canceled_orders_fill_and_cancel_ack_still_land_in_its_row(tmp_path):
    """The cancel is a request, not an outcome: between it and the venue's answer the order can
    still fill. Attaching only the KEPT orders would drop that fill and the ack with it, leaving the
    row open and underfilled forever -- a fill with no forensic row, which is the one thing the
    write-ahead row exists to make impossible."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier)
    client = StubClient(StubCache(open_orders=[_open_order("O-opener")]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)
    assert [str(o.client_order_id) for o in client.canceled] == ["O-opener"]

    ex.on_order_event(_fill("O-opener", 0.0002, px=30000.0))
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-opener"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.0002
    assert [e.get("event") or e.get("type") for e in row["events"]] == ["fill", "OrderCanceled"]
    assert row["state"] == "accepted"  # no state claim: this process is not tracking that lifecycle


def test_a_raising_orders_read_leaves_the_startup_pass_able_to_run_again(tmp_path):
    """Latching the pass on a read that classified NOTHING would leave every previous-process order
    resting unclassified for the life of the process. Nothing was canceled on that branch, so the
    retry cannot double-cancel."""
    client = StubClient(_FlakyOrdersCache(open_orders=[_open_order("O-orphan")]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)
    assert client.canceled == []  # the read raised: nothing classified, nothing touched

    ex.on_timer(NOW + timedelta(seconds=5))
    assert [str(o.client_order_id) for o in client.canceled] == ["O-orphan"]


@pytest.mark.parametrize(
    "level, expected",
    [
        (GateLevel.NONE, ["O-attached"]),  # a latched kill file leaves NOTHING working at the venue
        (GateLevel.REDUCE_ONLY, []),  # the same construction, one level up: the reducer keeps working
    ],
)
def test_a_latched_kill_file_cancels_even_the_ledger_attached_reducer(tmp_path, level, expected):
    """The kill switch's semantics are that a trip cancels resting orders, and `_poll` already
    revokes a resting CLOSE when the level drops to NONE -- so "nothing is working at the venue"
    must not have a restart-shaped hole. Both directions are constructed: without the second case a
    pass that cancelled everything unconditionally would pass the first."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)
    client = StubClient(StubCache(open_orders=[_open_order("O-attached")]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, level))

    ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == expected
    # Attached either way (cancel is a request, not an outcome), so the ack lands in the row.
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-attached"))
    assert [e["type"] for e in _record(tmp_path, earlier)["submitted"][0]["events"]] == ["OrderCanceled"]


# --- the external topic: an adopted order's own events (spec 00098) ------------------------------


@contextmanager
def _executor_errors(level=logging.ERROR):
    """The executor logger's own records at `level` and above, for the tests that must see a
    swallowed failure LOGGED rather than merely swallowed -- and, at WARNING, for the one that must
    see NOTHING logged. Deliberately not `caplog`, blind here for the two reasons
    `_the_tick_backstop_never_fires` documents: a root logger the CLI tests have detached, and
    phase-scoped records."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    log = logging.getLogger("zcrypto.engine.executor")
    handler = _Collect(level=level)
    previous_level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        yield records
    finally:
        log.removeHandler(handler)
        log.setLevel(previous_level)


def _adopted_executor(tmp_path, *, client_order_id="O-attached", reduce_only=True):
    """A previous process's resting order, adopted by the startup pass and attached to its OWN
    boundary's row four hours back -- the only state the external topic's matched path is reachable
    from. The trailing assert is the point: a construction that attached nothing would hand every
    test below the unmatched path's green instead."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, client_order_id, reduce_only=reduce_only, when=earlier)
    client = StubClient(StubCache(open_orders=[_open_order(client_order_id)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert client_order_id in ex._attached
    return ex, client, earlier


def test_an_external_fill_completing_an_adopted_order_appends_counts_and_closes_the_row(tmp_path):
    """The matched clean path end to end -- and the pin on the DELEGATION ORDER, which nothing else
    catches: the trip runs FIRST, so this fill (exactly the ledgered quantity) is measured against a
    row not yet credited with it. Swap the two and the mirrored quantity is counted twice, latching
    the kill switch on a perfectly healthy final fill.

    The row's STATE closes here because nautilus publishes no terminal event after a resting order's
    last fill -- without that it would read open forever and re-attach on every future scan. The
    entry itself stays attached: neither path ever pops, so a fill racing the close still journals."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    client.cache.move_position("BTC/EUR", -0.001)  # the venue moves the Cache first, then publishes

    ex.on_external_order_event(_fill("O-attached", 0.001))

    assert not _kill_file(tmp_path).exists()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.001
    assert [e["event"] for e in row["events"]] == ["fill"]
    assert row["events"][0]["px"] == 30000.0 and row["events"][0]["qty"] == 0.001
    assert row["state"] == "filled"
    assert "O-attached" in ex._attached  # retained: a racing fill must still find its row
    assert metrics.external == ["matched"]
    assert metrics.orders == ["filled"]
    assert metrics.fills == [("maker", 0.012)] and metrics.positions == [("BTC/EUR", -0.001)]


def test_a_partial_external_fill_leaves_the_adopted_row_open_and_attached(tmp_path):
    """The completion rule's other direction, without which a rule that closed the row on ANY fill
    would ship green: a fill short of the ledgered quantity makes no state claim and keeps the entry
    attached -- the remainder is still working at the venue, and its own fill needs this same row and
    this same overfill bound. The pair also exercises the tolerance across two float additions,
    which is the only reason the second fill completes rather than reading an ulp short."""
    ex, _client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_external_order_event(_fill("O-attached", 0.0004))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "accepted" and row["filled_qty"] == 0.0004
    assert "O-attached" in ex._attached
    assert metrics.orders == []  # nothing completed, so no outcome is counted

    ex.on_external_order_event(_fill("O-attached", 0.0006))  # the remainder

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled" and row["filled_qty"] == pytest.approx(0.001)
    assert "O-attached" in ex._attached  # completed, still retained -- neither path pops
    assert metrics.orders == ["filled"]
    assert metrics.external == ["matched", "matched"]


def test_a_fill_beyond_a_completed_adopted_orders_quantity_trips_like_any_other_overfill(tmp_path, kill_trip_expected):
    """The symmetry the retained row buys. A completed row keeps its attachment, so a further fill
    reaches `_trip_on_fill` and latches on the overfill arm -- the same verdict an own order's
    post-completion fill gets. Popping at completion would have made this fill unmatched instead:
    counted, logged, and never journaled, which is a divergence answered with a metric increment."""
    ex, _client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex.on_external_order_event(_fill("O-attached", 0.001))  # completes the ledgered quantity
    assert not _kill_file(tmp_path).exists()

    ex.on_external_order_event(_fill("O-attached", 0.0002))  # and then one more

    assert _kill_file(tmp_path).exists()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e["event"] for e in row["events"]] == ["fill", "fill"]  # the tripping fill is recorded
    assert row["filled_qty"] == pytest.approx(0.0012)
    assert metrics.external == ["matched", "matched"]  # matched both times, never unmatched


def test_a_dust_fill_on_a_completed_adopted_row_is_journaled_without_recounting_the_completion(tmp_path):
    """The completion write fires ONCE. A fill under `_OVERFILL_TOLERANCE` does not trip (that is
    what the tolerance is for), so it reaches the completion branch a second time -- and an unguarded
    branch would re-write the state and count a second `filled` outcome for one order, inflating the
    outcome counter against a row that completed once. The fill itself is still journaled."""
    ex, _client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex.on_external_order_event(_fill("O-attached", 0.001))
    assert metrics.orders == ["filled"]

    ex.on_external_order_event(_fill("O-attached", executor_module._OVERFILL_TOLERANCE / 10))

    assert not _kill_file(tmp_path).exists()
    assert metrics.orders == ["filled"]  # once, for one completed order
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled"
    assert [e["event"] for e in row["events"]] == ["fill", "fill"]  # no fill goes unrecorded
    assert "O-attached" in ex._attached


def test_an_external_event_the_ledger_does_not_vouch_for_reaches_nothing_at_all(tmp_path):
    """The operator's hand settle, and the whole reason this subscription is safe to have: an event
    on the external topic naming an order no ledgered row vouches for is COUNTED and ignored -- no
    trip, no row write anywhere, no cancel. The unknown-order trip stays scoped to this strategy's
    own topic, where every order arriving IS one this engine submitted."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_external_order_event(_fill("O-the-owners-own-hand", 0.5))

    assert not _kill_file(tmp_path).exists()
    assert client.canceled == []  # nothing was pulled off the venue for it either
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.0 and row["events"] == []  # the adopted row is untouched
    assert not exec_record_path(tmp_path / "journal", _boundary(NOW)).exists()  # and no new record
    assert metrics.external == ["unmatched"]  # the disposition that carries the whole signal
    assert metrics.fills == [] and metrics.orders == []


def test_an_external_overfill_on_an_adopted_row_trips_the_kill_and_still_journals_the_fill(tmp_path, kill_trip_expected):
    """A matched row is this engine's own pre-restart order, so a fill past what the ledger says it
    was submitted for is the same divergence the own-topic per-order trip guards. The fill still
    gets its forensic row -- no-fill-without-a-record has no divergence exemption -- and gets it
    EXACTLY ONCE: a second fill event here would mean the row append ran before the trip."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    overfill = 0.001 + 2 * executor_module._OVERFILL_TOLERANCE

    ex.on_external_order_event(_fill("O-attached", overfill))

    assert _kill_file(tmp_path).exists()
    assert [str(o.client_order_id) for o in client.canceled] == ["O-attached"]  # the trip pulls it
    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e["event"] for e in row["events"]] == ["fill"]
    assert row["filled_qty"] == overfill
    assert metrics.external == ["matched"]


@pytest.mark.parametrize(
    "event_name, expected_state",
    [("OrderCanceled", "canceled"), ("OrderExpired", "venue_canceled"), ("OrderRejected", "rejected")],
)
def test_an_external_terminal_event_closes_the_row_but_keeps_it_attached_for_a_racing_fill(tmp_path, event_name, expected_state):
    """The ruled map, written from `validate_exec_record`'s own state names -- no new state string is
    minted here, and `_store` would refuse one anyway. `canceled` makes no we-requested claim on this
    path, which is why the adopt pass's OWN cancel acks may wear it, and that those acks now CLOSE
    their rows (they used to stay open and re-read as possibly-live on every future scan) is the side
    effect worth its own assertion.

    The row's STATE closes; the ATTACHMENT does not. `ownTrades` and `openOrders` are separate Kraken
    WS channels with no cross-stream ordering guarantee, so a fill can land after the terminal ack --
    and popping here would send it to the unmatched branch to be counted and never journaled, which
    is the no-fill-without-a-record invariant broken on the very path built to restore it. Retained,
    it journals as a detached append exactly as an own order's late fill does."""
    ex, client, earlier = _adopted_executor(tmp_path, client_order_id="O-opener", reduce_only=False)
    assert [str(o.client_order_id) for o in client.canceled] == ["O-opener"]  # the pass's own cancel
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_external_order_event(_named(event_name, client_order_id="O-opener"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == expected_state
    assert [e["type"] for e in row["events"]] == [event_name]
    assert row["filled_qty"] == 0.0
    assert "O-opener" in ex._attached

    ex.on_external_order_event(_fill("O-opener", 0.0004))  # the fill that raced the ack

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e.get("event") or e.get("type") for e in row["events"]] == [event_name, "fill"]
    assert row["filled_qty"] == 0.0004  # journaled, not counted-and-dropped
    assert row["state"] == expected_state  # the detached append makes no state claim of its own
    assert metrics.external == ["matched", "matched"]  # never `unmatched`: the row is still vouched
    assert metrics.fills == [("maker", 0.012)]
    assert not _kill_file(tmp_path).exists()


def test_an_external_cancel_rejection_is_recorded_without_closing_the_adopted_row(tmp_path):
    """The venue positively says the cancel did NOT take, so the order may still rest: the event is
    evidence, the row keeps its open state, and the entry stays attached for the fill that can still
    arrive. Deliberately out of the terminal map for exactly that reason."""
    ex, _client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_external_order_event(_named("OrderCancelRejected", client_order_id="O-attached", reason="EOrder:Unknown order"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "accepted"
    assert row["events"] == [{"type": "OrderCancelRejected", "at": NOW.isoformat(), "reason": "EOrder:Unknown order"}]
    assert "O-attached" in ex._attached
    assert metrics.external == ["matched"]


def test_the_external_handler_logs_and_continues_when_the_ledger_write_raises(tmp_path, monkeypatch):
    """A msgbus handler's raise is the event loop's problem, not this process's to take -- so the one
    thing on this path that touches disk is made to fail and the handler must swallow it, loudly.
    Guard-proving: the failure is constructed, and WHICH log line fired is read, not just that one
    did."""
    ex, _client, _earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "update_submitted_row", _raise)
    with _executor_errors() as records:
        ex.on_external_order_event(_fill("O-attached", 0.0004))

    assert [r.getMessage() for r in records] == ["executor external-order-event handling raised -- continuing"]
    assert records[0].exc_info is not None  # logger.exception, so the traceback is in the record
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


# --- D7: the startup pass reconciles each row against venue truth (spec 00098) -------------------


def _reconciling_executor(
    tmp_path,
    *,
    venue_filled,
    ledgered_filled=0.0,
    closed_status=None,
    client_order_id="O-attached",
    reduce_only=True,
):
    """A previous process's ledgered row plus the cache order reconciliation left behind for it,
    with the two quantities set independently -- which is the whole point: the delta between them is
    what the startup sweep exists to read. `closed_status` builds the closed-while-down shape, where
    the order is absent from `orders_open` and reachable only through the wide read.

    The executor is returned BEFORE the first tick, so a test can install its metrics hooks first --
    the completion counter fires inside `on_timer`, and hooks installed after it would record
    nothing while every assertion still read green."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, client_order_id, reduce_only=reduce_only, when=earlier)
    if ledgered_filled:
        update_submitted_row(tmp_path / "journal", _boundary(earlier), client_order_id, add_filled_qty=ledgered_filled)
    if closed_status is None:
        cache = StubCache(open_orders=[_open_order(client_order_id, filled_qty=venue_filled)])
    else:
        cache = StubCache(closed_orders=[_closed_order(client_order_id, closed_status, filled_qty=venue_filled)])
    client = StubClient(cache)
    return _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY)), client, earlier


def test_a_sub_tolerance_difference_between_ledger_and_venue_is_reconciled_silently(tmp_path):
    """The dead-band, and the arm that must produce NOTHING. The ledgered figure is a sum of
    per-fill floats and the venue's is one exactly-rounded `float(Quantity)`, so a clean multi-fill
    restart differs by ulps -- a repair arm without the dead-band journals a phantom repair and
    shouts a WARNING on every healthy restart. An exact-equality construction would not catch that,
    which is why the two figures here differ by a tenth of the tolerance rather than by zero."""
    ex, _client, earlier = _reconciling_executor(
        tmp_path, ledgered_filled=0.0004, venue_filled=0.0004 + executor_module._OVERFILL_TOLERANCE / 10
    )
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"] == []  # no event
    assert row["filled_qty"] == 0.0004 and row["state"] == "accepted"  # no state write, no quantity moved
    assert [r.getMessage() for r in records if "reconcil" in r.getMessage()] == []  # and no log
    assert metrics.orders == []


def test_a_positive_reconciliation_delta_is_journaled_as_a_repair_and_mirrored(tmp_path):
    """The down-window fill, recovered. The quantity is resident in the reconciled order's own
    `filled_qty` because the engine applies the fill and publishes it in one synchronous body -- the
    publish reached no subscriber, the quantity survived. It is journaled as a REPAIR, not a fill:
    there is no per-fill detail and no fee behind it, and a fills increment with no fee would make
    the two counters disagree in a way the row cannot explain."""
    ex, _client, earlier = _reconciling_executor(tmp_path, venue_filled=0.0004)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.0004
    assert row["state"] == "accepted"  # short of the ledgered 0.001: still working, no state claim
    assert [e["event"] for e in row["events"]] == ["reconciled"]
    assert row["events"][0]["qty"] == 0.0004 and row["events"][0]["venue_filled_qty"] == 0.0004
    assert ex._attached["O-attached"][1]["filled_qty"] == 0.0004  # the mirror: the trip base moved
    assert metrics.fills == [] and metrics.orders == []  # a repair is not a fill


def test_a_reconciliation_delta_that_completes_the_row_closes_it_and_counts_it_once(tmp_path):
    """A repair restoring the quantity and still leaving the row reading open is the defect the
    completion write exists to prevent -- the row would re-read as possibly-live on every future
    scan. The mirrored `state` is load-bearing too: `_on_external_event`'s once-only guard reads it,
    so a stale mirror would let a later fill re-count the completion."""
    ex, _client, earlier = _reconciling_executor(tmp_path, venue_filled=0.001)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.001 and row["state"] == "filled"
    assert ex._attached["O-attached"][1]["state"] == "filled"
    assert metrics.orders == ["filled"]  # exactly once, for one completed order


def test_a_venue_quantity_past_the_ledgered_order_trips_after_the_repair_is_journaled(tmp_path, kill_trip_expected):
    """The overshoot arm. The repair is journaled FIRST and the switch latches second: the fill
    happened at the venue, and no-fill-without-a-record has no divergence exemption. The trip's own
    cancel and the classification pass both pull the order, because a latched kill file is exactly
    the state that leaves nothing working at the venue."""
    overfilled = 0.001 + 2 * executor_module._OVERFILL_TOLERANCE
    ex, client, earlier = _reconciling_executor(tmp_path, venue_filled=overfilled)

    ex.on_timer(NOW)

    assert _kill_file(tmp_path).exists()
    assert "O-attached" in _kill_file(tmp_path).read_text()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e["event"] for e in row["events"]] == ["reconciled"]  # journaled before the trip
    assert row["filled_qty"] == overfilled
    assert [str(o.client_order_id) for o in client.canceled] == ["O-attached", "O-attached"]


def test_a_ledger_ahead_of_the_venue_trips_and_names_both_figures(tmp_path, kill_trip_expected):
    """The dangerous direction: the ledger claims more filled than the venue reports, which makes
    the engine believe it reduced more than it did. Clamping it to zero would swallow exactly that
    signal, so the arm exists to trip -- and the reason carries BOTH figures, because an operator
    reading it mid-incident cannot get the venue's number from anywhere else in this process."""
    ex, _client, earlier = _reconciling_executor(tmp_path, ledgered_filled=0.0006, venue_filled=0.0002)

    ex.on_timer(NOW)

    reason = _kill_file(tmp_path).read_text()
    assert "0.0006" in reason and "0.0002" in reason and "O-attached" in reason
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"] == [] and row["filled_qty"] == 0.0006  # nothing was written down for it


def test_an_order_that_closed_while_the_process_was_down_is_repaired_and_given_its_terminal_state(tmp_path):
    """The window the pre-D7 early return could not reach at all: `orders_open` is EMPTY, so the
    pass used to return before reading a single row, and this order's row kept a stale quantity and
    an open state forever. Reached now through the wide read, it is repaired AND closed, and its row
    is attached -- so a late duplicate event for it lands matched rather than counted as a settle."""
    ex, client, earlier = _reconciling_executor(tmp_path, venue_filled=0.001, closed_status=OrderStatus.FILLED)
    assert client.cache.orders_open() == []  # the construction: nothing is resting
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.001
    assert [e["event"] for e in row["events"]] == ["reconciled"]
    assert row["state"] == "filled"
    assert "O-attached" in ex._attached
    assert client.canceled == []  # nothing resting to classify, and a closed order is never cancelled
    assert metrics.orders == ["filled"]


def test_a_cancel_that_landed_while_the_process_was_down_closes_its_row_without_a_repair(tmp_path):
    """The commonest closed-while-down shape, and the one a naive `if delta == 0: continue` skips
    forever: an order canceled with zero fills has no delta at all, so the terminal write has to be
    independent of all four comparison arms. `canceled` makes no we-requested claim here -- nothing
    at startup can tell a venue cancel from one the previous process sent."""
    ex, client, earlier = _reconciling_executor(tmp_path, venue_filled=0.0, closed_status=OrderStatus.CANCELED)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"] == []  # no repair: there was no delta
    assert row["state"] == "canceled"  # and the row is closed anyway
    assert row["filled_qty"] == 0.0
    assert "O-attached" in ex._attached
    assert metrics.orders == []  # a terminal state moves no order-outcome counter, as on the D2 path
    assert client.canceled == []


def test_the_startup_terminal_map_is_total_over_the_librarys_own_closed_statuses():
    """Totality against the installed library rather than against a hand-written list: an order
    status the map does not carry leaves a closed order's row open forever, and the failure is
    silent. The closed set lives in `Order.is_closed_c`, compiled and unreachable from Python, so
    its own property docstring -- the list the library maintains and a version bump would move -- is
    the domain. The parse is asserted non-empty first: a docstring reformat must fail loudly here
    rather than hand this test an empty set to trivially satisfy."""
    documented = re.findall(r"``([A-Z_]+)``", Order.is_closed.__doc__ or "")
    assert len(documented) >= 5
    closed = {getattr(OrderStatus, name) for name in documented}

    assert set(executor_module._ADOPTED_TERMINAL_STATES) == closed
    assert set(executor_module._ADOPTED_TERMINAL_STATES.values()) <= execledger_module._ROW_STATES


def test_a_repair_then_an_external_fill_for_the_remainder_completes_the_row_exactly_once(tmp_path):
    """D7 meeting D1, the sequence where a mis-mirror costs money. The sweep repairs the down-window
    partial and the subscription delivers the remainder: the row must read the full ledgered
    quantity, state `filled`, counted once, with no trip. Unmirrored, the repair never moves the
    trip base and the completion never fires; double-mirrored, this fill overshoots and false-kills.
    Both are invisible to a test that only reads the STORED row."""
    ex, _client, earlier = _reconciling_executor(tmp_path, venue_filled=0.0004)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex.on_timer(NOW)
    assert metrics.orders == []  # 0.0004 of 0.001: nothing completed yet

    ex.on_external_order_event(_fill("O-attached", 0.0006))

    assert not _kill_file(tmp_path).exists()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == pytest.approx(0.001)
    assert row["state"] == "filled"
    assert [e.get("event") for e in row["events"]] == ["reconciled", "fill"]
    assert metrics.orders == ["filled"]


def test_a_later_fill_on_a_row_a_repair_completed_trips_the_overfill_arm(tmp_path, kill_trip_expected):
    """The mirror of the sequence above, and what proves the repair moved the TRIP BASE rather than
    merely a stored number: once the sweep has completed the row, the next fill is an overfill and
    must latch. Without the mirror this fill would read as the row's first 0.0002 and pass."""
    ex, _client, earlier = _reconciling_executor(tmp_path, venue_filled=0.001)
    ex.on_timer(NOW)
    assert not _kill_file(tmp_path).exists()

    ex.on_external_order_event(_fill("O-attached", 0.0002))

    assert _kill_file(tmp_path).exists()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e.get("event") for e in row["events"]] == ["reconciled", "fill"]  # the tripping fill is recorded
    assert row["filled_qty"] == pytest.approx(0.0012)


def test_a_repair_that_cannot_be_journaled_still_leaves_the_resting_opener_canceled(tmp_path, monkeypatch):
    """The sweep introduces raising calls the pass never had, and `_adopted` is set before it -- so
    an escape would leave a previous process's resting opener working at the venue, uncanceled and
    unattached, for the life of this process. The write is wrapped where it is made, so it logs and
    classifies anyway. Guard-proving: WHICH log line fired is read, not just that one did."""
    ex, client, _earlier = _reconciling_executor(tmp_path, venue_filled=0.0004, client_order_id="O-opener", reduce_only=False)

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "update_submitted_row", _raise)
    with _executor_errors(logging.CRITICAL) as records:
        ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == ["O-opener"]
    assert [r.getMessage() for r in records] == ["the repair for adopted order O-opener could not be journaled"]
    assert records[0].exc_info is not None


def test_a_row_the_sweep_cannot_read_at_all_is_logged_and_the_pass_classifies_anyway(tmp_path):
    """The per-row wrapper's own proof, kept separate from the ledger-write one now that each write
    is wrapped where it is made: this failure is upstream of every write, in the read of the venue's
    own quantity, so only the outer wrapper can catch it. Delete that wrapper and the classification
    pass dies here, leaving the opener working at the venue."""
    ex, client, earlier = _reconciling_executor(tmp_path, venue_filled=0.0004, client_order_id="O-opener", reduce_only=False)
    ex._client.cache._open_orders[0].filled_qty = "not a quantity"

    with _executor_errors(logging.CRITICAL) as records:
        ex.on_timer(NOW)

    assert [str(o.client_order_id) for o in client.canceled] == ["O-opener"]
    assert [r.getMessage() for r in records] == ["adopted row O-opener could not be reconciled against the venue"]
    assert _record(tmp_path, earlier)["submitted"][0]["events"] == []  # nothing was written from an unreadable figure


def test_a_ledger_that_cannot_be_written_never_costs_the_overshoot_trip(tmp_path, monkeypatch, kill_trip_expected):
    """A ledger failure may never cost the trip -- `_record_trip_fill`'s ruling, and the reason its
    own `try` is scoped to the write alone. The repair write comes FIRST on this arm, so a wrapper
    spanning both would let a read-only journal swallow the latch: one CRITICAL logged, no kill file,
    and the gate then reads normal over a live venue-vs-ledger divergence. The in-process quantity is
    credited either way, since it tracks what filled rather than what could be written down."""
    overfilled = 0.001 + 2 * executor_module._OVERFILL_TOLERANCE
    ex, _client, _earlier = _reconciling_executor(tmp_path, venue_filled=overfilled)

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "update_submitted_row", _raise)
    with _executor_errors(logging.CRITICAL) as records:
        ex.on_timer(NOW)

    assert _kill_file(tmp_path).exists()
    assert "O-attached" in _kill_file(tmp_path).read_text()
    assert "the repair for adopted order O-attached could not be journaled" in [r.getMessage() for r in records]
    assert ex._attached["O-attached"][1]["filled_qty"] == overfilled


def test_a_ledger_that_cannot_be_written_never_costs_the_closed_orders_negative_delta_trip(
    tmp_path, monkeypatch, kill_trip_expected
):
    """The same ruling on the arm where the preceding write is the TERMINAL one rather than a repair
    -- a closed order whose row claims more filled than the venue reports. The negative arm journals
    nothing itself, so nothing but the state write stands between this divergence and the latch, and
    a wrapper spanning both would swallow exactly the dangerous direction."""
    ex, _client, _earlier = _reconciling_executor(
        tmp_path, ledgered_filled=0.0006, venue_filled=0.0002, closed_status=OrderStatus.CANCELED
    )

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "update_submitted_row", _raise)
    with _executor_errors(logging.CRITICAL) as records:
        ex.on_timer(NOW)

    reason = _kill_file(tmp_path).read_text()
    assert "0.0006" in reason and "0.0002" in reason
    assert "the startup state for adopted row O-attached could not be journaled" in [r.getMessage() for r in records]


def test_a_second_tick_after_the_startup_pass_reconciles_nothing_further(tmp_path):
    """Idempotence is structural: the pass runs once per process, reads each order's `filled_qty`
    exactly once, and journals a difference -- so a repeat tick has no second delta to find. A sweep
    that re-ran would append the same repair again on every tick."""
    ex, _client, earlier = _reconciling_executor(tmp_path, venue_filled=0.0004)

    ex.on_timer(NOW)
    ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e["event"] for e in row["events"]] == ["reconciled"]
    assert row["filled_qty"] == 0.0004


# --- D11: the first automatic kill trips ----------------------------------------------------------


def _kill_file(tmp_path: Path) -> Path:
    return exec_dir(tmp_path) / KILL_FILE


def _idle_executor(tmp_path):
    """An armed executor with no plan running -- the state the probe sits in between plans, and the
    state the owner's manual settle happens in. Returns the state dir the kill file would appear
    under (`journal_dir.parent`, the 00088 convention `_config` follows)."""
    client = StubClient()
    return _executor(tmp_path, client=client), client, tmp_path


def test_an_external_fill_with_no_strategy_claim_does_not_trip(tmp_path):
    """The settle's healthy path, proven quiet: the Cache position moves with NO order event
    reaching the executor (an external fill routes through reconciliation, never on_order_event).
    Ticks pass, no intent is active -- the kill file must NOT appear."""
    ex, client, state_dir = _idle_executor(tmp_path)
    client.cache.set_position("BTC/EUR", 0.0004)  # the settle landed as a holding
    _advance_ticks(ex, minutes=2)
    assert not (exec_dir(state_dir) / KILL_FILE).exists()
    assert client.canceled == []  # and nothing was pulled off the venue for it either


def test_a_fill_for_an_order_this_engine_never_submitted_trips_the_kill_switch(tmp_path, kill_trip_expected):
    """The unknown own-strategy order. The same event SHAPE as the settle above and the opposite
    verdict: what separates them is that this one names an order id, on this engine's own strategy,
    that the ledger has no row for -- so a fill exists that nothing here can account for."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))
    resting = client.submitted[0][0]

    ex.on_order_event(_fill("O-unknown", 0.001))

    text = _kill_file(tmp_path).read_text()
    assert "no open order record" in text and "O-unknown" in text  # WHICH condition fired
    assert client.canceled == [resting]
    assert _intent_outcome(tmp_path, 0) == "revoked"
    assert _intent_outcome(tmp_path, 1) == "refused"
    assert _record(tmp_path)["submitted"][0]["filled_qty"] == 0.0  # nothing was credited to OUR order


def test_an_order_filling_past_the_quantity_it_was_submitted_for_trips(tmp_path, kill_trip_expected):
    """Per-order overfill: 0.0006 twice against the 0.001 that order carried. Both this condition
    and the per-intent one are true here, and the reason must name THIS one -- an operator sent to
    the ladder's remainder arithmetic would be looking at the wrong thing."""
    ex, client, clock = _resting_executor(tmp_path)
    resting = client.submitted[0][0]
    assert resting.quantity == 0.001
    ex.on_order_event(OrderAccepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.0006)
    assert not _kill_file(tmp_path).exists()  # 0.0006 of 0.001 is a partial, not a divergence
    _deliver_fill(ex, client, client.last_order_id, 0.0006)

    assert "of the 0.001 it was submitted for" in _kill_file(tmp_path).read_text()
    assert client.canceled == [resting]
    # The overfilling fill is journaled anyway: it happened at the venue, and the row is where the
    # operator reads what the kill reason is talking about.
    assert _record(tmp_path)["submitted"][0]["filled_qty"] == 0.0012


def test_an_intents_orders_filling_past_its_target_between_them_trips(tmp_path, kill_trip_expected):
    """D6's remainder sizing, backstopped. The first order is superseded with 0.4 in; the reprice
    sizes the second to the 0.6 remainder; a LATE fill on the superseded order then lands, and the
    second order fills its whole 0.6 -- 1.3 against a 1.0 target, with NEITHER order overfilled on
    its own. Only the cross-order sum can see it, which is why it is checked separately."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    assert client.submitted[0][0].quantity == 1.0
    ex.on_order_event(OrderAccepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)

    ex.on_order_event(_named("OrderCanceled", client_order_id="O-1"))  # the venue's own cancel -> reprice
    resting = client.submitted[1][0]
    assert resting.quantity == 0.6

    _deliver_fill(ex, client, "O-1", 0.3, px=30.0)  # the late fill on the superseded order
    assert not _kill_file(tmp_path).exists()  # 0.7 of a 1.0 target, 0.7 of O-1's own 1.0: healthy
    _deliver_fill(ex, client, "O-2", 0.6, px=30.0)

    assert "across its orders" in _kill_file(tmp_path).read_text()
    assert client.canceled == [resting]
    assert _intent_outcome(tmp_path) == "revoked"


def test_a_position_that_contradicts_the_intents_fills_trips_at_the_terminal(tmp_path, kill_trip_expected):
    """Post-terminal reconciliation: the intent's own fills say 0.001 was bought, the Cache says
    0.0005 is held. The adopted reducer the startup pass deliberately left resting is what proves a
    trip cancels resting orders it did not itself place -- a latched kill leaves NOTHING working at
    the venue, which is the same judgment that pass already makes when it starts up onto one."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)
    cache = StubCache(open_orders=[_open_order("O-attached")])
    ex, client, clock = _resting_executor(
        tmp_path, client=StubClient(cache), intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]
    )
    assert client.canceled == []  # the startup pass kept the ledgered reducer
    ex.on_order_event(OrderAccepted(client.last_order_id))

    cache.set_position("BTC/EUR", 0.0005)  # the venue moved by half of what the fill claims
    ex.on_order_event(_fill(client.last_order_id, 0.001))

    assert "not the 0.001" in _kill_file(tmp_path).read_text()
    assert [str(o.client_order_id) for o in client.canceled] == ["O-attached"]
    assert _intent_outcome(tmp_path, 0) == "filled"  # it DID fill -- the divergence is what follows
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_a_terminal_whose_position_matches_its_fills_does_not_trip(tmp_path):
    """The reconciliation's other direction, on the identical construction one number apart: the
    Cache agrees with the fills, so the intent ends and the NEXT one starts. Without this a check
    that tripped on every terminal would pass the test above."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(OrderAccepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.001)

    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path, 0) == "filled"
    ex.on_timer(NOW + timedelta(seconds=5))
    assert client.subscribed == ["BTC/EUR.KRAKEN", "ETH/EUR.KRAKEN"]


def test_a_tripped_kill_switch_refuses_every_later_plan(tmp_path, kill_trip_expected):
    """The trip's DURABLE half, isolated the only way it can be: a restarted process carries no
    memory of the trip, so what refuses its plan is the file itself -- the gate's own input. The
    same-process refusal is a different mechanism, proven separately below; run here it would hide
    this one. Nothing in either process cleared the file; nothing in either process can."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    ex.on_order_event(_fill("O-unknown", 0.001))
    assert _kill_file(tmp_path).exists()

    restarted_client = StubClient()
    restarted = _executor(tmp_path, client=restarted_client, gate=_gate(tmp_path, GateLevel.NONE))
    later = NOW + timedelta(seconds=5)
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", created_at=later - timedelta(minutes=1)))
    restarted.on_timer(later)
    restarted.on_quote(_quote())

    assert restarted_client.submitted == []  # nothing reached the venue after the restart either
    entry = _record(tmp_path)["plans"][-1]
    assert entry["plan_id"] == "p-2"
    assert entry["intents"][0]["outcome"] == "refused"
    assert "kill_switch" in entry["intents"][0]["reasons"]


def test_a_superseded_orders_late_fills_are_summed_against_that_orders_own_quantity(tmp_path, kill_trip_expected):
    """Per-order accounting has to survive the order ceasing to be the one in flight: 0.4 while it
    rested plus 0.7 in late fills afterwards is 1.1 of the 1.0 that order carried. Both overfill
    conditions are true by then, and the reason still names the ORDER -- which it can only do if the
    detached path kept that order's own running total."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(OrderAccepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_named("OrderCanceled", client_order_id="O-1"))  # superseded by the reprice

    _deliver_fill(ex, client, "O-1", 0.3, px=30.0)
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)

    assert "order O-1 has now filled" in _kill_file(tmp_path).read_text()  # not the cross-order sum
    assert "it was submitted for" in _kill_file(tmp_path).read_text()


def test_a_closer_that_flattens_its_position_reconciles_against_what_it_started_holding(tmp_path):
    """The reconciliation's other operand, and the only construction that can see it: an intent that
    starts holding 0.001 and sells exactly that ends FLAT, not short. Read `position_before` as zero
    -- or drop the term -- and this healthy close trips instead."""
    client = StubClient(StubCache(positions=_held(**{"BTC/EUR": 0.001})))
    ex, client, clock = _resting_executor(
        tmp_path, client=client, intents=[_intent(side="sell", action="close", notional_eur=90.0, leverage=2)]
    )
    assert client.submitted[0][0].quantity == 0.001
    ex.on_order_event(OrderAccepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.001, side="sell", px=30001.0)

    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


# --- D11 fix round: the in-process backstop, and the branches that only fire on failure ------------


def test_a_kill_file_that_could_not_be_written_still_refuses_the_next_plan(tmp_path, kill_trip_expected):
    """The kill FILE is the durable latch; when it cannot be written there is still one thing left,
    and it must be a refusal. A directory sitting in the kill file's place stands in for any write
    failure -- a read-only mount, a full disk, a permission error -- and it is removed afterwards so
    the gate reads `full` again: from there the ONLY thing refusing is this process's own memory
    that it tripped. Without that memory the next plan is picked up, submitted, and the published
    gauge still reads zero, while the log claims the engine stopped."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    obstruction = exec_dir(tmp_path) / KILL_FILE
    obstruction.mkdir()

    ex.on_order_event(_fill("O-unknown", 0.001))

    assert not obstruction.is_file()  # the latch never reached disk
    obstruction.rmdir()
    _gate(tmp_path)  # its trailing assert: nothing on disk refuses anything any more

    clock.now = NOW + timedelta(seconds=5)
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", created_at=clock.now - timedelta(minutes=1)))
    ex.on_timer(clock.now)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1  # nothing new reached the venue
    entry = _record(tmp_path)["plans"][-1]
    assert entry["plan_id"] == "p-2" and entry["disposition"] == "refused"
    assert entry["reasons"] == ["the kill switch tripped in this process"]
    assert not _plan_path(tmp_path).exists()  # journaled AND deleted, never re-read every tick


def test_the_chokepoint_refuses_once_this_process_has_tripped(tmp_path):
    """The backstop BEHIND the plan-pickup refusal, at the one place every order goes through. The
    flag is set directly because after a real trip nothing can reach the chokepoint any more -- the
    plan is gone -- which is exactly what makes this a belt behind a belt rather than the belt."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(OrderAccepted(client.last_order_id))
    ex._kill_tripped = True

    ex.on_order_event(_named("OrderCanceled", client_order_id=client.last_order_id))  # would reprice

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the kill switch tripped in this process"]


class _PositionReadFails(StubCache):
    """`positions_open` answers until `broken` is set: the intent has to be able to START -- venue
    truth reads the same accessor -- and only then lose the read."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.broken = False

    def positions_open(self, *, instrument_id=None, **kwargs):
        if self.broken:
            raise RuntimeError("the position store is not readable")
        return super().positions_open(instrument_id=instrument_id, **kwargs)


def test_a_position_that_cannot_be_read_at_the_terminal_trips(tmp_path, kill_trip_expected):
    """An unverifiable position after a fill is not something to place the next order against. The
    venue-truth read at intent start proved this same Cache readable minutes earlier, so a raise
    here is an anomaly rather than routine -- and the branch runs inside an exception handler inside
    an event catch-all, which is where an untested one is only ever found in the field."""
    cache = _PositionReadFails()
    ex, client, clock = _resting_executor(tmp_path, client=StubClient(cache))
    ex.on_order_event(OrderAccepted(client.last_order_id))

    cache.broken = True
    ex.on_order_event(_fill(client.last_order_id, 0.001))

    text = _kill_file(tmp_path).read_text()
    assert "could not be read" in text and "BTC/EUR" in text


def test_a_ledger_row_with_no_readable_order_quantity_trips_on_any_fill(tmp_path, kill_trip_expected):
    """A fill this process cannot BOUND is itself the divergence, so an order payload carrying no
    quantity reads 0.0 rather than being waved through. The shape is one this engine never writes --
    a write-ahead row always carries the sized order -- so it can only be a foreign or damaged
    record, which is not one to reason from."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-shapeless", reduce_only=True, when=earlier)
    path = exec_record_path(tmp_path / "journal", _boundary(earlier))
    doc = read_exec_record(path)
    doc["submitted"][0]["order"] = {}
    path.write_text(json.dumps(doc))

    client = StubClient(StubCache(open_orders=[_open_order("O-shapeless")]))
    ex = _executor(tmp_path, client=client)
    ex.on_timer(NOW)

    ex.on_order_event(_fill("O-shapeless", 0.0004))

    assert "of the 0 it was submitted for" in _kill_file(tmp_path).read_text()
