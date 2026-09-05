from __future__ import annotations

import ast
import json
import logging
import shutil
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.core import UUID4
from nautilus_trader.model import (
    AccountId,
    ClientOrderId,
    Currency,
    CurrencyPair,
    InstrumentId,
    LimitOrder,
    LiquiditySide,
    Money,
    OrderAccepted,
    OrderCanceled,
    OrderCancelRejected,
    OrderExpired,
    OrderFilled,
    OrderFillVoided,
    OrderRejected,
    OrderSide,
    OrderStatus,
    OrderSubmitted,
    OrderType,
    Position,
    PositionId,
    Price,
    Quantity,
    QuoteTick,
    StrategyId,
    Symbol,
    TimeInForce,
    TradeId,
    TraderId,
    VenueOrderId,
)

import cli.engine.execledger as execledger_module
import cli.engine.executor as executor_module
import cli.engine.venuestate as venuestate_module
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
    write_exec_record,
)
from cli.engine.executor import ProbeExecutor, set_executor_hooks, size_probe_order
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order
from cli.engine.journal import CycleRecord, SnapshotEntry, to_json
from cli.engine.node import ShadowStrategy
from cli.engine.probeplan import MODES, PLAN_FILENAME, ProbeIntent
from cli.engine.venue import VenueStatus
from cli.engine.venueledger import write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)

# One case per liquidity side the venue can report: (member, row value, metric label). The expected
# renderings are written out rather than read back off the member -- an expectation derived from the
# enum would agree with whatever the emit site produced, including a number. Completeness against
# the enum is asserted in the test that consumes this.
_LIQUIDITY_CASES = (
    (LiquiditySide.MAKER, "MAKER", "maker"),
    (LiquiditySide.TAKER, "TAKER", "taker"),
    (LiquiditySide.NO_LIQUIDITY_SIDE, "NO_LIQUIDITY_SIDE", "no_liquidity_side"),
)


# --- the sizing seam -------------------------------------------------------------------


_VERIFIED_VERSION = "1.230.0"  # in cli/engine/order-semantics-verified.json


# The running-nautilus gate input is held VERIFIED so it contributes no reason to any verdict below:
# left to the real interpreter this file would assert against whatever version happens to be
# installed, and would flip wholesale on the next bump.
@pytest.fixture(autouse=True)
def _nautilus_verified(monkeypatch):
    monkeypatch.setattr("cli.engine.execgate._installed_nautilus_version", lambda: _VERIFIED_VERSION)


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


# The dotted ATTRIBUTE REACH, never the bare word: `cli/engine/node.py` seals this surface by
# DEFINING those names to raise, and matching the bare word would make the seal itself the offender,
# leaving an allowance as the only way back. `cancel_order` is here because a cancel reaches the
# venue exactly as a submit does, `cancel_all_orders` because an account-wide cancel is the largest.
_VENUE_MUTATING_NAMES = (".submit_order", ".cancel_order", ".cancel_all_orders", ".order_factory")
# The engine's order machine and the red button, and nothing else. `cli/engine/flatten.py` is a
# second venue-mutating module BY DESIGN (spec 00106 D7): the button has to work when the machine
# is what broke, so the two deliberately share no code path, and the price of that is a second
# entry here rather than a guard that reuse would have satisfied.
_VENUE_MUTATING_MODULES = frozenset({"cli/engine/executor.py", "cli/engine/flatten.py"})


def test_the_venue_mutating_names_have_exactly_one_module():
    """Spec 00090 D4's structural pin, widened by spec 00106 D7: every venue-mutating call lives in
    `cli/engine/executor.py` or `cli/engine/flatten.py`. A text walk, not an import walk -- a
    reference in a comment is still one a refactor can activate."""
    offenders = []
    for path in sorted(Path("cli").rglob("*.py")):
        if path.as_posix() in _VENUE_MUTATING_MODULES:
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


def _step_precision(step: float) -> int:
    """The decimal precision one venue step implies -- 0.1 -> 1, 0.00000001 -> 8. Kraken publishes
    `pair_decimals`/`lot_decimals` alongside `tick_size`, and across the whole basket the step is
    exactly `10 ** -decimals`, so deriving one from the other keeps the fixture's instrument
    self-consistent the way a Cache instrument is."""
    return -Decimal(str(step)).as_tuple().exponent


def _quantity(value) -> Quantity:
    """A `Quantity` carrying `value` exactly, minted at the precision the value is written in -- so
    a fixture quantity is never silently rounded by the fixture itself."""
    return Quantity(float(value), _step_precision(float(value)))


def _price(value) -> Price:
    """A `Price` carrying `value` exactly, on the same terms as `_quantity`."""
    return Price(float(value), _step_precision(float(value)))


@lru_cache(maxsize=None)
def _rounding_delegate(symbol: str, lot_step: float, tick_size: float) -> CurrencyPair:
    """A REAL nautilus instrument at one leg's precisions. Only `make_qty`/`make_price` are read off
    it: their rounding is HALF-EVEN on the decimal the value is written as, and it is not the rule
    the bare `Quantity(value, precision)` / `Price(value, precision)` constructors use -- the two
    disagree at half-increments, so a stub restating either would be restating the wrong one."""
    base, quote = symbol.split("/")
    return CurrencyPair(
        instrument_id=InstrumentId.from_str(f"{symbol}.KRAKEN"),
        raw_symbol=Symbol(base + quote),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=_step_precision(tick_size),
        size_precision=_step_precision(lot_step),
        price_increment=Price(tick_size, _step_precision(tick_size)),
        size_increment=Quantity(lot_step, _step_precision(lot_step)),
        ts_event=0,
        ts_init=0,
    )


def _real_instrument(symbol: str) -> CurrencyPair:
    """The library instrument for one leg, at the same precisions `_fake_instrument` gives it -- what
    `Position` needs to do a fill's arithmetic in the venue's own terms."""
    attrs = _BTC_LEG_ATTRS.get(symbol, {})
    return _rounding_delegate(symbol, attrs.get("lot_step", 0.00000001), attrs.get("tick_size", 0.1))


def _fake_instrument(instrument_id: str, *, ordermin=0.0001, lot_step=0.00000001, tick_size=0.1):
    # min_notional mirrors observed live reality (cli/engine/venuestate.py, D5a): the installed
    # Kraken adapter never populates it. make_qty/make_price are BOUND FROM A REAL INSTRUMENT at
    # this leg's precisions: the executor hands the order factory whatever they return, so a stub
    # returning the value unchanged would agree with a `_place` that had lost the calls entirely.
    real = _rounding_delegate(instrument_id.rsplit(".", 1)[0], lot_step, tick_size)
    return SimpleNamespace(
        id=instrument_id,
        min_quantity=ordermin,
        min_notional=None,
        size_increment=lot_step,
        price_increment=tick_size,
        make_qty=real.make_qty,
        make_price=real.make_price,
    )


def _all_instruments(**overrides):
    instruments = {iid: _fake_instrument(iid, **_BTC_LEG_ATTRS.get(symbol, {})) for symbol, iid in INSTRUMENT_IDS.items()}
    instruments.update(overrides)
    return instruments


_STUB_STRATEGY_ID = StrategyId("ShadowStrategy-000")


class StubCache:
    """Duck-types the Cache accessors `venue_state_from_cache` and the executor call, matching
    their real signatures. `raises=True` is the no-venue-truth construction."""

    def __init__(self, *, instruments=None, balances=None, positions=None, open_orders=None, closed_orders=None, raises=False):
        self._instruments = _all_instruments() if instruments is None else instruments
        self._balances = {"ZEUR": 1000.0} if balances is None else balances
        self._positions = positions or {}
        self._external: dict[str, list] = {}
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
        """The installed Cache's accessors are typed and REFUSE a str (`TypeError: Argument
        'instrument_id' has incorrect type`), so this stub refuses one too: a coercing stub accepts
        what production cannot, and every live `_publish_fill` would raise into its swallowing
        `except` with the whole suite green."""
        if not isinstance(instrument_id, InstrumentId):
            raise TypeError(
                f"Argument 'instrument_id' has incorrect type (expected InstrumentId, got {type(instrument_id).__name__})"
            )
        return str(instrument_id)

    def positions_open(self, *, instrument_id=None, strategy_id=None, **kwargs):
        """Honours `strategy_id`: NETTING position ids are `f"{instrument_id}-{strategy_id}"`, so an
        external fill lands in a SEPARATE position and only a strategy-scoped read excludes the
        operator's book -- a stub that swallowed the filter could not tell a fixed
        `_reconcile_terminal` from a broken one."""
        if strategy_id is not None and not isinstance(strategy_id, StrategyId):
            raise TypeError(f"Argument 'strategy_id' has incorrect type (expected StrategyId, got {type(strategy_id).__name__})")
        key = self._position_key(instrument_id)
        own = self._positions.get(key, [])
        external = self._external.get(key, [])
        if strategy_id is None:
            return own + external
        if str(strategy_id) == "EXTERNAL":
            return external
        # An id that is neither ours nor EXTERNAL owns NOTHING -- the real Cache indexes positions by
        # the exact strategy id, so a wrong id returns []. Returning `own` here would let a caller
        # reading under the wrong identity look correct in tests and latch the kill switch in
        # production, which is the whole defect class this stub exists to keep visible.
        return own if str(strategy_id) == str(_STUB_STRATEGY_ID) else []

    def positions_closed(self, *, instrument_id=None, **kwargs):
        return self._closed.get(self._position_key(instrument_id), [])

    def set_position(self, symbol, signed_qty, *, realized_pnl=None):
        """What the Cache says is held, in the shape `_held()` builds -- the one accessor a test
        needs to make the venue disagree with the ledger, or to land a holding the engine never
        ordered (the manual settle). `realized_pnl` is `Money | None` on a real Position, and the
        None is the ordinary case for a leg with no closed round trip yet."""
        self._positions[INSTRUMENT_IDS[symbol]] = [SimpleNamespace(signed_qty=signed_qty, realized_pnl=realized_pnl)]

    def set_external_position(self, symbol, signed_qty):
        """A holding attributed to `StrategyId("EXTERNAL")` -- what an operator's hand settle, or
        any order this engine never placed, leaves in the Cache. Instrument-scoped reads see it;
        reads scoped to this engine's own strategy must not."""
        self._external[INSTRUMENT_IDS[symbol]] = [SimpleNamespace(signed_qty=signed_qty, realized_pnl=None)]

    def close_position(self, symbol, realized_pnl):
        """A CLOSED position carrying realized PnL -- what `positions_closed` serves once a round
        trip is done, and the half a sum over open positions alone would silently lose."""
        self._closed.setdefault(INSTRUMENT_IDS[symbol], []).append(SimpleNamespace(signed_qty=0.0, realized_pnl=realized_pnl))

    def move_position(self, symbol, delta):
        held = self._positions.get(INSTRUMENT_IDS[symbol], [])
        realized = held[0].realized_pnl if held else None
        self.set_position(symbol, sum(float(p.signed_qty) for p in held) + delta, realized_pnl=realized)

    def apply_fill(self, symbol, fill):
        """Move the held position the way a fill does, with the library's own `Position` doing the
        arithmetic off the event's `order_side` and `last_qty` -- a fixture that named the delta
        itself would agree with a mis-signed or mis-sized fill.

        The NETTING position id is stamped onto a copy only here: opening a `Position` needs one, and
        a dispatched fill carrying one cannot be voided afterwards. Rebuilt field by field rather
        than round-tripped through `to_dict`/`from_dict`, which answers `Unknown currency` for the
        venue's alias codes, so a commission denominated `ZEUR` or `XXBT` never survives the trip."""
        identified = OrderFilled(
            fill.trader_id, fill.strategy_id, fill.instrument_id, fill.client_order_id, fill.venue_order_id,
            fill.account_id, fill.trade_id, fill.order_side, fill.order_type, fill.last_qty, fill.last_px,
            fill.currency, fill.liquidity_side, fill.event_id, fill.ts_event, fill.ts_init, fill.reconciliation,
            PositionId(f"{INSTRUMENT_IDS[symbol]}-{_STUB_STRATEGY_ID}"), fill.commission,
        )  # fmt: skip
        delta = float(Position(_real_instrument(symbol), identified).signed_qty)
        self.move_position(symbol, delta)

    def order(self, client_order_id):
        """One order by id across the whole index, open or closed, and None for an id it does not
        hold -- the closed half is what every closed-while-down test rests on, since such an order is
        by definition absent from `orders_open`.

        Typed like the real one, which REFUSES a str (`'str' object is not an instance of
        'ClientOrderId'`): a stub that accepted one would let production hand it the plain string it
        carries everywhere else, and every live read would raise into a swallowing `except`."""
        if not isinstance(client_order_id, ClientOrderId):
            raise TypeError(
                f"Argument 'client_order_id' has incorrect type (expected ClientOrderId, got {type(client_order_id).__name__})"
            )
        wanted = str(client_order_id)
        return next((o for o in [*self._open_orders, *self._closed_orders] if str(o.client_order_id) == wanted), None)

    def orders_open(self, *, venue=None, **kwargs):
        return list(self._open_orders)

    def account_for_venue(self, *, venue=None, **kwargs):
        # `balances_free()` in the real account's own terms: dict[Currency, Money]. Both halves are
        # library types the reader has to coerce, and a real Currency keys the dict directly --
        # it is hashable and value-equal, which is what a plain namespace is not.
        balances = {Currency.from_str(code): Money(value, Currency.from_str(code)) for code, value in self._balances.items()}
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
        # A real StrategyId, not a str: `Cache.positions_open(strategy_id=...)` is typed and
        # refuses a str, so a stubbed str would accept what production cannot.
        self.strategy_id = _STUB_STRATEGY_ID
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

    def cancel_order(self, client_order_id):
        self.canceled.append(client_order_id)

    def subscribe_quotes(self, instrument_id):
        self.subscribed.append(str(instrument_id))

    def unsubscribe_quotes(self, instrument_id):
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
    """A resting order as reconciliation adopts it. `is_reduce_only` is here because the real adopted
    report carries it and the startup pass must be seen NOT to consult it; `filled_qty`, `is_open`
    and `status` are what that pass reads instead."""
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


# Sizes nothing on the executor's quote path reads -- `on_quote` takes the two prices and the
# instrument id. A QuoteTick cannot be built without them.
_QUOTE_SIZE = Quantity.from_str("1.0")


def _quote(instrument_id="BTC/EUR.KRAKEN", bid=30000.0, ask=30001.0):
    """A REAL `QuoteTick`, as the strategy's quote topic delivers it: `bid_price`/`ask_price` are
    `Price` objects, which is what `_as_price` has to coerce. The library REFUSES a tick whose two
    sides carry different precisions, so both are minted at the finer of the pair."""
    precision = max(_step_precision(bid), _step_precision(ask))
    return QuoteTick(
        InstrumentId.from_str(instrument_id), Price(bid, precision), Price(ask, precision), _QUOTE_SIZE, _QUOTE_SIZE, 0, 0
    )


_TRADER_ID = TraderId("TESTER-001")
_ACCOUNT_ID = AccountId("KRAKEN-001")
_VENUE_ORDER_ID = VenueOrderId("V-1")

# What each event kind carries beyond the identity fields every one of them has. These are what the
# LIBRARY requires, not what a test happens to read: a real event refuses a missing field, so a
# constructor that grows one fails here loudly instead of leaving a fabricated shape behind.
_EVENT_DEFAULTS = {
    OrderAccepted: {"venue_order_id": _VENUE_ORDER_ID, "account_id": _ACCOUNT_ID, "reconciliation": False},
    OrderCanceled: {"reconciliation": False},
    OrderExpired: {"reconciliation": False},
    OrderRejected: {"account_id": _ACCOUNT_ID, "reason": "the venue said no", "reconciliation": False},
    OrderCancelRejected: {"reason": "the venue said no", "reconciliation": False},
    OrderFilled: {
        "venue_order_id": _VENUE_ORDER_ID,
        "account_id": _ACCOUNT_ID,
        "order_side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "reconciliation": False,
    },
}


def _event(cls, **overrides):
    """One of the library's own order events, with the identity fields every kind carries baked in.
    The class IS the fixture: the executor dispatches on `type(event).__name__`, so nothing here can
    wear a name the library does not define, nor answer an attribute it does not carry."""
    kwargs = {
        "trader_id": _TRADER_ID,
        "strategy_id": _STUB_STRATEGY_ID,
        "instrument_id": InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]),
        "event_id": UUID4(),
        "ts_event": 0,
        "ts_init": 0,
        **_EVENT_DEFAULTS[cls],
        **overrides,
    }
    kwargs["client_order_id"] = ClientOrderId(str(overrides.get("client_order_id", "O-1")))
    return cls(**kwargs)


def _accepted(client_order_id):
    return _event(OrderAccepted, client_order_id=client_order_id)


def _canceled(client_order_id):
    return _event(OrderCanceled, client_order_id=client_order_id)


def _rejected(client_order_id, reason, *, due_post_only=False):
    """The venue's rejection. `due_post_only` is READ-ONLY on the constructor -- the only way to
    mint the adapter's synchronous post-only mapping is the event's own dict round trip, which is
    also the proof that the flag production reads is a field the library really carries."""
    event = _event(OrderRejected, client_order_id=client_order_id, reason=reason)
    if not due_post_only:
        return event
    return OrderRejected.from_dict({**event.to_dict(), "due_post_only": True})


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
    """Ticks carrying a live quote on every one -- the only way to reach the time-box, since quote
    silence would otherwise revoke the resting order first. Stops the moment a cancel goes out, so
    each test delivers the venue's answer itself."""
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
    """`on_timer`'s catch-all is a backstop for the unforeseen, not a mechanism any test may lean on:
    every refusal below has its own named path, so a test that goes green WHILE the backstop fires
    fails instead.

    Deliberately NOT `caplog`, blind here twice over: its handler sits on the ROOT logger and
    `cli.logging.config.configure` sets `zcrypto.propagate = False`, and `caplog.records` is
    PHASE-scoped, so a teardown-time read returns a list emptied moments earlier. An own handler on
    the executor's own logger, with the logger's level forced for the duration, dodges both."""
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
    """A trip creates a latching file no code may clear and stops this engine for good, so every
    OTHER test in this file is a healthy neighbour that must not cause one. Runs both ways: an
    announcing test that does NOT trip fails too. Watches the executor's own logger for the reasons
    `_the_tick_backstop_never_fires` gives."""
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
        self.tracking = []
        self.resting_ages = []

    def set_resting_age(self, mode, seconds):
        self.resting_ages.append((mode, seconds))

    def set_tracking_state(self, state):
        self.tracking.append(state)

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


# --- the venue value objects: what quantity and price actually reach the order factory -----------

# `instrument.make_price` / `instrument.make_qty` round HALF-EVEN on the decimal the value is
# WRITTEN as; the bare `Price(value, precision)` / `Quantity(value, precision)` constructors round
# the binary float and DISAGREE at half-increments, in both directions. Both columns are pinned
# because the pair is the finding -- reading `Quantity(x, instrument.size_precision)` as a free
# substitute for `instrument.make_qty(x)` changes the submitted quantity by one whole increment.
_MAKE_PRICE_CASES = (
    # (value, instrument.make_price at price_precision=2, Price(value, 2))
    (0.015, "0.02", "0.02"),
    (0.025, "0.02", "0.03"),
    (0.045, "0.04", "0.05"),
    (0.355, "0.36", "0.36"),
    (1.005, "1.00", "1.00"),
    (1.015, "1.02", "1.01"),
    (2.005, "2.00", "2.01"),
    (2.675, "2.68", "2.68"),
    (8.835, "8.84", "8.84"),
)

# (value, instrument.make_qty at size_precision=8 or None where it RAISES, Quantity(value, 8))
_MAKE_QTY_CASES = (
    (4.9e-09, None, "0.00000000"),
    (5e-09, None, "0.00000001"),
    (5.1e-09, "0.00000001", "0.00000001"),
    (1.25e-08, "0.00000001", "0.00000001"),
    (1.5e-08, "0.00000002", "0.00000001"),
    (2.5e-08, "0.00000002", "0.00000003"),
    (3.5e-08, "0.00000004", "0.00000004"),
)


@pytest.mark.parametrize("value, made, constructed", _MAKE_PRICE_CASES)
def test_the_instruments_price_rounding_is_not_the_bare_constructors(value, made, constructed):
    instrument = _rounding_delegate("ETH/EUR", 0.00000001, 0.01)
    assert instrument.price_precision == 2
    assert str(instrument.make_price(value)) == made
    assert str(Price(value, 2)) == constructed


@pytest.mark.parametrize("value, made, constructed", _MAKE_QTY_CASES)
def test_the_instruments_quantity_rounding_is_not_the_bare_constructors(value, made, constructed):
    """`make_qty` REFUSES a value that rounds to zero where the constructor returns a zero quantity,
    so the two differ in kind and not only in value below half an increment."""
    instrument = _rounding_delegate("ETH/EUR", 0.00000001, 0.01)
    assert instrument.size_precision == 8
    if made is None:
        with pytest.raises(ValueError, match="rounded to zero"):
            instrument.make_qty(value)
    else:
        assert str(instrument.make_qty(value)) == made
    assert str(Quantity(value, 8)) == constructed


def test_a_submitted_order_carries_the_floored_price_and_quantity_as_venue_value_objects(tmp_path):
    """`size_order` FLOORS to the venue step and what reaches the order factory is that floored
    number wrapped by the instrument's own maker. Both operands are chosen so the two roundings
    answer differently -- the raw touch and the raw quantity each round UP where the floor sends them
    down -- so a `_place` that lost the floor, or that priced off the raw touch, submits a different
    order and this test says which."""
    _venue_record(tmp_path, balances={"ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.001000015)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote(bid=30000.05, ask=30000.15))

    order, _ = client.submitted[0]
    assert isinstance(order.price, Price) and isinstance(order.quantity, Quantity)
    assert str(order.price) == "30000.1"
    assert str(order.quantity) == "0.00100001"
    # The journal row carries the sized floats, not the value objects -- the same two numbers.
    row = _record(tmp_path)["submitted"][0]["order"]
    assert (row["price"], row["qty"]) == (30000.1, 0.00100001)


def test_the_floor_is_what_keeps_make_qty_away_from_the_quantity_it_refuses(tmp_path):
    """`instrument.make_qty(sized.qty)` in `_place` sits OUTSIDE the try that wraps sizing and raises
    under half an increment, so the containment argument is that such a value cannot arrive:
    `size_order` floors to `lot_step` and then refuses anything under `ordermin`, which is at least
    one lot on every venue shape. Asserted at the tightest legal shape (`ordermin == lot_step`)."""
    instrument = _rounding_delegate("BTC/EUR", 0.00000001, 0.1)
    with pytest.raises(ValueError, match="rounded to zero"):
        instrument.make_qty(0.4 * 0.00000001)
    assert str(instrument.make_qty(0.00000001)) == "0.00000001"  # one whole lot survives

    below = size_order(0.4 * 0.00000001, 30000.1, ordermin=0.00000001, costmin=0.0, lot_step=0.00000001, tick_size=0.1)
    assert isinstance(below, BelowMinimum) and "ordermin" in below.reason

    # And end to end: the refusal is the intent's, never a ValueError out of the order factory.
    _venue_record(tmp_path, balances={"ZEUR": 1000.0})
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=4.9e-09)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == []
    assert _intent_entry(tmp_path, 0)["outcome"] == "refused"


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
    """The other half of the level rule: a `_level_permits` that refused everything at REDUCE_ONLY
    would pass the test above. Both the 0.001 qty and the venue record are load-bearing -- a larger
    qty is refused by the plan cap and a missing record by the disposal classification (spec 00090
    D10), either of which greens this test for the wrong reason."""
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
    """Owner ruling: an ambiguous outcome stops the plan -- the order may be live, so the position
    and free balance every LATER intent was authorized against are unknown. The remaining intents are
    journaled naming the ambiguous predecessor."""
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


def test_a_raising_own_position_read_refuses_the_intent_with_no_subscribe_and_no_submit(tmp_path):
    """`_start_intent` guards its two Cache reads separately and this cache refuses exactly the
    strategy-scoped one: `StubCache(raises=True)` fails `instrument()`, which the FIRST guard
    catches, leaving the second unreachable.

    Unguarded, the exception leaves `_active` unarmed and `_index` unadvanced -- the plan neither
    refused nor progressed -- and a raise after the subscribe would leak the quote subscription until
    restart."""

    class _OwnPositionUnreadable(StubCache):
        def positions_open(self, *, instrument_id=None, strategy_id=None, **kwargs):
            if strategy_id is not None:
                raise RuntimeError("strategy-scoped position read failed")
            return super().positions_open(instrument_id=instrument_id, strategy_id=strategy_id, **kwargs)

    client = StubClient(_OwnPositionUnreadable())
    ex = _executor(tmp_path, client=client)
    path = _drop_plan(tmp_path, _plan_dict())

    with _executor_errors(logging.WARNING) as records:
        ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["no venue truth"]
    assert not path.exists()
    # Both guards journal the same reason, so without this the fixture could silently regress to
    # exercising the FIRST one -- if `venue_state_from_cache` ever passed a strategy_id, this test
    # would go on passing while the guard under test went unreached again.
    assert any("own position unreadable" in r.getMessage() for r in records), (
        "the venue-truth guard refused this, not the own-position guard the test exists for"
    )


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
    """The LIVE spelling: production's free-cash read resolves on the `ZEUR`-then-`EUR` fallback's
    SECOND arm, which every other fixture here leaves unpinned -- deleting that arm would leave this
    suite green while production sized every plan against 0.00 free EUR. The assertion is the figure
    inside the reason, not the words 'margin floor': dropping the arm still refuses, so only the
    VALUE separates the two worlds."""
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


def _fill(
    client_order_id,
    last_qty,
    *,
    px=30000.0,
    fee=0.08,
    fee_code="EUR",
    symbol="BTC/EUR",
    side="buy",
    liquidity=LiquiditySide.MAKER,
    **overrides,
):
    """A REAL `OrderFilled`, carrying every field the executor's fill row reads in the venue's own
    types.

    `fee_code` is `EUR`, the currency a Kraken fill's commission carries
    (`docs/reference/adapter-verification/2.0.0rc4.dev20260825.md`, observation 4); the venue's
    `ZEUR` spelling belongs to its asset and instrument-quote surfaces, and
    `cli.engine.instruments.EUR_CODES` accepts both. Fee values are amounts two decimals can hold,
    for the reason `test_a_real_money_answers_both_accessors_the_fill_row_reads` measures; `fee=None`
    builds the commission-less fill that reaches the row builder's absent-fee branch.

    `liquidity_side` is a `LiquiditySide` member -- only a member has the `.name` the ledger row and
    the metric label are written from -- and `order_side` follows `side` so the library's own
    `Position` can compute what this fill does to a holding instead of the fixture asserting it. No
    `position_id`: `apply_fill` mints it there, because a fill carrying one makes a subsequent
    `OrderFillVoided` raise `Invalid event for order type`."""
    return _event(
        OrderFilled,
        client_order_id=client_order_id,
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS[symbol]),
        trade_id=TradeId("T-1"),
        order_side=OrderSide.BUY if side == "buy" else OrderSide.SELL,
        last_qty=_quantity(last_qty),
        last_px=_price(px),
        currency=Currency.from_str(symbol.split("/")[1]),
        liquidity_side=liquidity,
        commission=None if fee is None else Money(fee, Currency.from_str(fee_code)),
        **overrides,
    )


def _deliver_fill(ex, client, client_order_id, qty, *, symbol="BTC/EUR", side="buy", px=30000.0, **kwargs):
    """Deliver a fill the way the venue does: the Cache position moves FIRST, then the strategy sees
    the event -- the ordering `test_the_cache_already_carries_the_fill_when_the_strategy_handler_sees_it`
    measures, and the one `_reconcile_terminal` bets on, since it runs synchronously inside this
    dispatch and latches the kill switch on a disagreement.

    The MOVE is derived: `apply_fill` lets the library's own `Position` read the event's side and
    quantity, so this helper cannot move the position one way while the event says the other."""
    fill = _fill(client_order_id, qty, px=px, symbol=symbol, side=side, **kwargs)
    client.cache.apply_fill(symbol, fill)
    ex.on_order_event(fill)


def _cache_reads_at_dispatch() -> dict:
    """Run a real order through a real engine and read the Cache from inside the strategy's own event
    handler, at the instant each event is dispatched. A REAL `BacktestEngine` is the only construction
    that can answer this: its ExecutionEngine, Portfolio and Cache are compiled, so there is no source
    to read the ordering off. Two orders: one crosses and fills, one rests and is canceled.

    The readings are RECORDED and asserted by the caller, never here -- the library swallows a raising
    handler, so an assertion inside one is invisible and its test passes green."""
    from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.model import AccountType, OmsType, Venue
    from nautilus_trader.trading import Strategy

    venue = Venue("KRAKEN")
    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"])
    instrument = _real_instrument("BTC/EUR")
    readings: dict = {}

    class _Probe(Strategy):
        def __init__(self):
            super().__init__()
            self._ticks = 0
            self._resting = None

        def on_start(self):
            self.subscribe_quotes(instrument_id)

        def on_quote(self, tick):
            self._ticks += 1
            if self._ticks == 1:
                self.submit_order(self._limit(30000.0))  # the market comes to it and it fills
                self._resting = self._limit(1000.0)  # far below: it rests untouched
                self.submit_order(self._resting)
            elif self._ticks == 3:
                self.cancel_order(self._resting.client_order_id)

        def _limit(self, price):
            return self.order_factory.limit(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(0.001),
                price=instrument.make_price(price),
            )

        def on_order_event(self, event):
            name = type(event).__name__
            if name not in ("OrderFilled", "OrderCanceled"):
                # An event this process's own command generates is dispatched while the Cache is
                # still mutably borrowed for the write that produced it, and a read there raises
                # `Already mutably borrowed`. Only the venue's own answers are read here.
                return
            order = self.cache.order(event.client_order_id)
            readings[name] = {
                "filled_qty": float(order.filled_qty),
                "status": order.status,
                "in_orders_open": [o.client_order_id for o in self.cache.orders_open(venue=venue)],
                "position": sum(
                    float(p.signed_qty)
                    for p in self.cache.positions_open(instrument_id=instrument_id, strategy_id=self.strategy_id)
                ),
            }

    engine = BacktestEngine(config=BacktestEngineConfig(trader_id=TraderId("PROBE-000")))
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(100_000, Currency.from_str("EUR")), Money(10, Currency.from_str("BTC"))],
    )
    engine.add_instrument(instrument)
    engine.add_strategy(_Probe())
    engine.add_data(
        [
            # The sizes are minted through the instrument: a quote whose size precision differs from
            # the instrument's is accepted by the tick type and then matches nothing, so the order
            # rests forever and the run measures an ordering it never reached.
            QuoteTick(
                instrument_id,
                instrument.make_price(bid),
                instrument.make_price(bid + 1.0),
                instrument.make_qty(1.0),
                instrument.make_qty(1.0),
                ts,
                ts,
            )
            for ts, bid in ((1, 30001.0), (2_000_000_000, 29998.0), (3_000_000_000, 29998.0))
        ]
    )
    try:
        engine.run()
    finally:
        engine.dispose()
    return readings


def test_the_cache_already_carries_the_fill_when_the_strategy_handler_sees_it():
    """By the time a handler is dispatched an order event, the Cache has already applied it -- the
    premise `_deliver_fill` is built on and the one `_reconcile_terminal` bets the kill switch on,
    since a Cache that moved AFTER the handler would leave every healthy round trip short by the fill
    it is standing in, and nothing in the stubbed harness could tell the two orderings apart.

    The fixture is not degenerate: the position is 0.0 before the fill and 0.001 after, and the order
    is ACCEPTED before and FILLED after. The cancel half is the same premise for terminal events."""
    readings = _cache_reads_at_dispatch()

    assert set(readings) == {"OrderFilled", "OrderCanceled"}, readings  # the run really produced both

    filled = readings["OrderFilled"]
    assert filled["filled_qty"] == 0.001  # the fill is applied, not pending
    assert filled["status"] == OrderStatus.FILLED
    assert filled["position"] == 0.001  # what `_reconcile_terminal` reads, already moved
    canceled = readings["OrderCanceled"]
    assert canceled["status"] == OrderStatus.CANCELED
    assert canceled["filled_qty"] == 0.0
    assert canceled["in_orders_open"] == []  # a settled order has already left the open index


def test_an_acceptance_then_a_full_fill_closes_the_intent_and_the_next_one_starts(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    ex.on_order_event(_accepted("O-1"))
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


@pytest.mark.parametrize(("side", "row_value", "label"), _LIQUIDITY_CASES, ids=["maker", "taker", "unattributed"])
def test_a_fills_liquidity_side_is_named_not_numbered_in_both_the_row_and_the_metric(tmp_path, side, row_value, label):
    """The whole write-ahead path, driven with a REAL `LiquiditySide` member: a plain-string fake
    would make any rendering the emit site produced look correct.

    A number in the forensic row outlives the probe, and a numeric metric child mints an unadmitted
    series while the pre-registered maker/taker ones read zero -- the board reporting nothing traded
    while money moves. The case list is checked against `LiquiditySide.variants()` first, which is
    the enumeration; the class itself is not iterable."""
    assert {case[1] for case in _LIQUIDITY_CASES} == {member.name for member in LiquiditySide.variants()}
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
    assert metrics.fills == [(label, pytest.approx(0.08))]


def test_an_unrecognisable_liquidity_side_is_recorded_verbatim_rather_than_raised():
    """`_liquidity` sits on the write-ahead path, where a raise costs the fill its row, and it reads
    an attribute off a value arriving from outside this process: a value the enum cannot name is
    recorded verbatim and logged, never dropped. `tracking.py` is where a liquidity outside the
    venue's own names is refused.

    Driven at the function rather than through a fill, because the library will not build the input --
    an `OrderFilled` takes a `LiquiditySide` member and nothing else -- so the branch is reachable
    only from a value no real event can carry."""
    with _executor_errors(logging.WARNING) as records:
        assert executor_module._liquidity("WHO KNOWS") == "WHO KNOWS"

    assert [r.getMessage() for r in records] == [
        "fill carries an unrecognisable liquidity side 'WHO KNOWS' -- recording it verbatim"
    ]


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


def test_the_venues_other_euro_spelling_reaches_the_metric_as_a_euro_fee(tmp_path):
    """`EUR_CODES` carries both spellings and `_fee_eur` reads the constant, not a literal -- the
    fills elsewhere in this file are `EUR`, so a `_fee_eur` narrowed to `== "EUR"` would drop every
    `ZEUR` fee out of the counter with the whole module still green. The counter's VALUE is what is
    read: a fee excluded from a EUR total is `None`, not zero."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, fee=0.08, fee_code="ZEUR")

    assert metrics.fills == [("maker", 0.08)]


def test_a_commission_less_fill_still_gets_its_forensic_row_with_a_null_fee(tmp_path):
    """`OrderFilled.commission` is `Money | None`, and reading it bare would raise inside
    `on_order_event`'s blanket except, DROPPING the fill's row after `_on_fill` already credited
    `active.filled` -- a quantity the ledger cannot describe. A null fee is the truthful way to say
    the venue reported none, and the EUR total is untouched by a fee that does not exist."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())
    _deliver_fill(ex, client, "O-1", 0.001, fee=None)

    row = _record(tmp_path)["submitted"][0]
    assert row["filled_qty"] == 0.001
    fill_events = [e for e in row["events"] if e.get("event") == "fill"]
    assert len(fill_events) == 1, "the fill's row is the thing that must never be dropped"
    assert fill_events[0]["fee"] is None
    assert fill_events[0]["fee_currency"] is None
    assert fill_events[0]["qty"] == 0.001
    assert metrics.fills == [("maker", None)]


def test_realized_pnl_sums_open_and_closed_positions_and_skips_a_non_eur_one(tmp_path):
    """`Position.realized_pnl` is `Money | None`. The None is skipped rather than `float()`-ed, the
    CLOSED positions are summed too (a round trip's PnL lives nowhere else), and a non-EUR position
    is left out rather than added to a EUR total."""
    client = StubClient()
    client.cache.close_position("BTC/EUR", Money(-4.5, Currency.from_str("ZEUR")))
    client.cache.close_position("BTC/EUR", Money(1.25, Currency.from_str("EUR")))
    client.cache.close_position("BTC/EUR", Money(9999.0, Currency.from_str("XXBT")))  # never summed into a EUR total
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
    ex.on_order_event(_accepted("O-1"))
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> reprice
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
    ex.on_order_event(_rejected("O-1", "EOrder:Post only order"))

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
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        else:
            ex.on_order_event(_canceled(client.last_order_id))
        ex.on_quote(_quote(bid=30000.0, ask=30001.0))
    assert len(client.submitted) == 6  # initial + 5 reprices
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 6  # the sixth reprice refused, nothing new
    assert _intent_outcome(tmp_path) == "unfilled"


def test_an_ambiguous_rejection_halts_with_no_second_order(tmp_path):
    """The double-submit construction, seen refused: a timeout surfaced as a rejection carrying no
    Kraken error code and no post-only marker. The intent halts ambiguous; no reprice, no IOC."""
    ex, client, now = _resting_executor(tmp_path)
    ex.on_order_event(_rejected(client.last_order_id, "request timed out", due_post_only=False))
    _advance_ticks(ex, minutes=20)  # deep past the time-box: still nothing may be emitted
    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_an_ambiguous_rejection_drops_the_later_intents_too(tmp_path):
    """The other half of the halt: a plan's remaining intents were authorized against a venue state
    that an order which may be live has just made unknown."""
    ex, client, _ = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_rejected(client.last_order_id, "request timed out"))
    ex.on_timer(NOW + timedelta(seconds=5))

    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # intent 1 never even subscribed
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_the_time_box_cancels_then_fires_an_ioc_at_the_opposite_touch(tmp_path):
    """The fallback is price-bounded, never a market order: a LIMIT IOC at the opposite touch."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled == [resting_order.client_order_id]
    assert len(client.submitted) == 1  # the cancel is not a submission -- the ack is what fires the IOC

    ex.on_order_event(_canceled(client.last_order_id))
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
    ex.on_order_event(_accepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0)
    assert _record(tmp_path)["submitted"][0]["filled_qty"] == 0.4

    _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 2
    assert client.submitted[1][0].quantity == 0.6


def test_three_unfilled_iocs_end_the_intent_unfilled_after_exactly_four_submissions(tmp_path):
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)

    for _ in range(3):  # the time-box cancel ack, then each IOC's unfilled remainder coming back
        ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 4  # the maker order + three IOC attempts

    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 4  # the budget is three, not four
    assert _intent_outcome(tmp_path) == "unfilled"


def test_every_returned_ioc_remainder_counts_its_outcome_so_the_board_still_balances(tmp_path):
    """The operator surface, not the ledger: during an unfilled fallback ladder the board must not
    show `submitted` advancing with nothing terminal behind it. Each IOC's unfilled remainder comes
    back as an unrequested cancel, writes row state `venue_canceled`, and must count that outcome --
    which only driving the ladder and reading the counter can establish."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)

    for _ in range(4):  # the time-box cancel ack, then all three IOC remainders returning
        ex.on_order_event(_canceled(client.last_order_id))

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
    ex.on_order_event(_accepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.00095)  # of a 0.001 target: 5e-05 left, ordermin is 1e-04

    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "partial"
    assert any("ordermin" in r for r in intent["reasons"])
    assert intent["filled_qty"] == 0.00095


def test_a_kill_file_mid_rest_cancels_with_no_fallback_and_halts_the_plan(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())  # a live quote: what revokes here is the gate, not silence
    ex.on_timer(clock.now)
    assert client.canceled == [resting_order.client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
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
    ex.on_order_event(_accepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)
    assert client.canceled == [client.submitted[0][0].client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
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

    ex.on_order_event(_accepted(client.last_order_id))
    assert client.canceled == [order.client_order_id]  # cancelled on the acknowledgment, not on a timer

    ex.on_order_event(_canceled(client.last_order_id))
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
    assert client.canceled == [client.submitted[0][0].client_order_id]
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 1
    assert _intent_outcome(tmp_path) == "rest_cancel_ok"


def test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses(tmp_path):
    """The mode exists to rest, so the one thing it must never do is what the time box does for
    `execute`: cancel and then cross with a marketable IOC. The defect is a single character --
    `!=` where `==` belongs at the fallback -- and it puts the most aggressive order on the path
    from the intent built least to want it."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=1)])
    _advance_with_quotes(ex, client, clock, minutes=3)
    assert client.canceled == [client.submitted[0][0].client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 1, "a second order means it fell back and crossed"
    assert client.submitted[0][0].post_only is True
    assert _intent_outcome(tmp_path) == "rest_hold_expired"


def test_a_rest_hold_order_is_not_cancelled_when_the_venue_acknowledges_it(tmp_path):
    """`rest-cancel`'s defining behaviour, inverted. Without this the drills have no subject: an
    order cancelled on the ack leaves no window for any induction to act in."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))
    assert client.canceled == []
    assert ex._active.phase == "resting"


def test_an_unrequested_cancel_ends_a_rest_hold_intent_instead_of_re_placing_it(tmp_path):
    """Spec 00108 D5. `_on_cancel_ack`'s unrequested arm reprices for ANY venue-originated cancel while
    the phase is not `ioc` -- it tests nothing about crossing -- so without this branch the venue's
    (or the operator's) cancel of a resting drill order silently puts a fresh one back at a new
    price, swapping the drill's subject mid-induction."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))

    ex.on_order_event(_canceled(client.last_order_id))  # unrequested: the venue's own doing

    assert len(client.submitted) == 1, "a second order means the venue's cancel was undone"
    assert _intent_outcome(tmp_path) == "rest_hold_venue_canceled"
    assert _record(tmp_path)["submitted"][0]["state"] == "venue_canceled"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [({"side": "buy"}, 28500.0), ({"side": "sell", "leverage": 3}, 33180.0)],
    ids=["buy-off-the-bid", "sell-off-the-ask"],
)
def test_a_rest_hold_order_is_priced_the_declared_percent_passive_of_the_touch(tmp_path, overrides, expected):
    """5.0 means five percent. The dangerous misreading is the quiet one: an author copying
    `_REST_CANCEL_OFFSET`'s fractional 0.05 would rest five hundredths of a percent off the touch
    and fill. The arithmetic here is `rest-cancel`'s own, with the constant made per-intent --
    30000 x 0.95 off the bid, 31600 x 1.05 off the ask."""
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45, **overrides)],
        bid=30000.0,
        ask=31600.0,
    )
    assert client.submitted[0][0].price == expected


def test_the_kill_file_revokes_a_resting_rest_hold_order_within_one_tick(tmp_path):
    """Drill E's subject, and the only bound that acts on a resting order while it rests. The path
    is exercised today only against `execute`."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())  # a live quote: what revokes here is the gate, not silence
    ex.on_timer(clock.now)
    assert client.canceled == [resting_order.client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 1  # a revoked intent NEVER falls back
    assert _intent_outcome(tmp_path) == "revoked", "a kill is a revoke, never an expiry"


def test_quote_silence_still_revokes_a_resting_rest_hold_order(tmp_path):
    """Drill F2 has no subject without it: 30 s of silence, one cancel attempt, no retry. Exempting
    this mode would delete the drill whose result decides whether re-cancel-on-reconnect is built."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert client.canceled == [client.submitted[0][0].client_order_id]
    ex.on_order_event(_canceled(client.last_order_id))
    assert _intent_entry(tmp_path, 0)["reasons"] == ["quote_silence"]


def test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero(tmp_path):
    """A mode that deliberately leaves an order resting for up to an hour ships with the instrument
    that shows it. The label is what keeps the panel legible across the eras: a drill's artifact and
    a rung-1 trading order are the same shape, and only the mode tells them apart."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=120)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)

    published = dict(metrics.resting_ages[-len(MODES) :])
    assert published["rest-hold"] == pytest.approx(120.0, abs=6)
    # The true positive: without a second label asserted zero, a gauge stuck at the resting value
    # for every mode would pass.
    assert published["execute"] == 0.0

    ex.on_order_event(_canceled(client.last_order_id))  # the venue takes it off the book
    ex.on_timer(NOW + timedelta(seconds=125))
    assert dict(metrics.resting_ages[-len(MODES) :])["rest-hold"] == 0.0


def test_an_outstanding_cancel_zeroes_the_resting_age_though_the_order_may_still_be_at_the_venue(tmp_path):
    """The publish reads a THREE-part condition -- `_active` set, phase `resting`, `placed_at`
    stamped -- and this fixture negates exactly the phase term: the kill file revoked the order, so
    the intent is live and `placed_at` still holds NOW, but a cancel is outstanding at the venue.
    Zero is the declared reading, because the gauge is the engine's BELIEF about an order it has
    already asked back; without the phase term the age would climb through a cancel and past a
    revocation.

    The third term is unreachable by construction: `_enter` is the only writer of the `resting` phase
    and stamps `placed_at` in the same breath. It guards the `None` deref below it."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=30)
    ex.on_quote(_quote())  # a live quote: what revokes here is the gate, not silence
    ex.on_timer(clock.now)

    assert client.canceled == [client.submitted[0][0].client_order_id]
    assert ex._active is not None and ex._active.placed_at == NOW, "the other two terms still hold"
    assert ex._active.phase == "cancelling"
    assert dict(metrics.resting_ages[-len(MODES) :]) == dict.fromkeys(MODES, 0.0)


def test_a_raise_inside_the_resting_age_publish_never_ends_the_running_plan(tmp_path, monkeypatch):
    """`on_timer`'s catch-all drops the plan and nulls `_active`, so a raise anywhere in the publish
    would leave a live order at the venue with nothing tracking it -- `_poll` is unreachable with no
    `_active`. The publish is wrapped WHOLE: `_set_resting_age`'s own try/except covers neither the
    loop, the phase read, nor the arithmetic around it."""

    def _boom(mode, seconds):
        raise RuntimeError("the resting-age publish is broken")

    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_order_event(_accepted(client.last_order_id))
    monkeypatch.setattr("cli.engine.executor._set_resting_age", _boom)

    clock.now = NOW + timedelta(seconds=10)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)

    assert ex._plan is not None and ex._active is not None
    assert ex._active.phase == "resting"
    assert client.canceled == []


def test_a_resting_orders_placement_time_belongs_to_the_order_and_to_no_other_phase(tmp_path):
    """Any age bound reads `placed_at`, so it must track the ORDER: a post-only rejection's reprice
    replaces the order and the replacement's age starts with it, where an intent-scoped stamp would
    age the new order from the old one's placement. `cancelling` is a phase this intent passes
    through, never a placement."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    assert ex._active.placed_at == NOW

    clock.now = NOW + timedelta(minutes=7)
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 2  # the rejection repriced: nothing was ever resting
    assert ex._active.placed_at == clock.now, "the replacement order's age starts with it"

    replaced_at = clock.now
    clock.now = NOW + timedelta(minutes=8)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert ex._active.phase == "cancelling"
    assert ex._active.placed_at == replaced_at, "entering `cancelling` is not a placement"


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
    ex.on_order_event(_rejected(client.last_order_id, "EOrder:Insufficient funds"))
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
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_canceled(client.last_order_id))
    assert client.submitted[1][0].time_in_force == TimeInForce.IOC

    ex.on_order_event(_accepted(client.last_order_id))  # the venue acknowledges the IOC
    ex.on_order_event(_canceled(client.last_order_id))

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
    ex.on_order_event(_accepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.1, px=37.5)
    _deliver_fill(ex, client, client.last_order_id, 0.7, px=37.5)

    assert _record(tmp_path)["submitted"][0]["state"] == "filled"
    assert _intent_outcome(tmp_path) == "filled"


def test_a_cancel_rejection_parks_the_intent_ambiguous_and_halts_the_plan(tmp_path):
    """The venue positively says the cancel failed, so the order may still rest. Nothing may be
    submitted against a position this process can no longer describe."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert client.canceled

    ex.on_order_event(_event(OrderCancelRejected, client_order_id=client.last_order_id, reason="EOrder:Unknown order"))

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
    ex.on_order_event(_accepted(client.last_order_id))

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
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 2  # the IOC is out at the venue

    clock.now += timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert len(client.submitted) == 2
    assert _intent_outcome(tmp_path) == "ambiguous"


def _time_boxed_cancel_answered_by(tmp_path, event) -> dict:
    """A funded two-intent plan driven to its time-box cancel, then answered by `event(coid)`.

    Everything up to the answer is identical between the two arms below, which is the point: the
    ONLY difference the readings can be attributed to is the flag the answering event carries."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled  # the time-box cancel is out and the fallback is armed
    assert len(client.submitted) == 1

    ex.on_order_event(event(client.last_order_id))
    return {
        "submissions": len(client.submitted),
        "row_state": _record(tmp_path)["submitted"][0]["state"],
        "intent": _intent_outcome(tmp_path),
        "next_intent": _intent_outcome(tmp_path, 1),
    }


def test_a_cancel_ack_the_engine_minted_halts_where_the_venues_own_ack_falls_back(tmp_path):
    """The pair that can tell reading the `reconciliation` flag from ignoring it: the same event
    class, the same time-boxed intent waiting on the same cancel, the flag false and true, opposite
    outcomes -- an implementation that halted on EVERY cancel ack would pass the true arm and break
    maker-first outright.

    False is the venue's ack, so the bounded IOC fires at the opposite touch. True is the execution
    engine minting the ack itself: nobody at the venue confirmed it, the original may still be
    resting, and crossing there would put a second order on the book against the first."""
    venue = _time_boxed_cancel_answered_by(tmp_path / "venue", _canceled)
    minted = _time_boxed_cancel_answered_by(
        tmp_path / "minted",
        lambda coid: _event(OrderCanceled, client_order_id=coid, reconciliation=True),
    )

    assert venue == {"submissions": 2, "row_state": "canceled", "intent": "pending", "next_intent": "pending"}
    # No IOC, the row stays OPEN for re-attach because the order may still rest, and the ETH intent
    # never runs: the venue state that authorized it is no longer known.
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused"}


def test_a_kraken_coded_rejection_the_engine_minted_is_ambiguous_rather_than_terminal(tmp_path):
    """`_on_rejected` reads the venue's error text to decide a rejection is a positive verdict; a
    rejection the engine minted carries no verdict at all, so the guard sits ABOVE the dispatch and a
    marker added to `_KRAKEN_ERROR_MARKERS` later cannot silently promote one. The reason string here
    would classify as terminal on the venue-sourced side, which is what makes the two arms differ on
    the same words."""
    reason = "EOrder:Insufficient funds"
    venue = _time_boxed_cancel_answered_by(tmp_path / "venue", lambda coid: _rejected(coid, reason))
    minted = _time_boxed_cancel_answered_by(
        tmp_path / "minted",
        lambda coid: _event(OrderRejected, client_order_id=coid, reason=reason, reconciliation=True),
    )

    # The venue's coded rejection is a positive verdict: the intent ends `rejected` and the ETH
    # intent stays runnable -- it is `pending` rather than submitted only because starting it is the
    # next tick's business. The minted one halts the plan instead, and ETH never runs at all.
    assert venue == {"submissions": 1, "row_state": "rejected", "intent": "rejected", "next_intent": "pending"}
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused"}


def test_a_fill_the_engine_reconciled_still_gets_its_row_its_credit_and_its_counter(tmp_path):
    """The deliberate exception to the rule above: a reconciled fill is the venue's own report
    transcribed late, so it is money that MOVED and the ambiguous exit would drop the row, the
    quantity credit and the published fill. `reconciliation` true and false must produce the SAME
    reading, and the sizing assertion is why -- a dropped credit makes the next resubmission over-ask
    by exactly the fill."""
    readings = []
    for reconciled in (False, True):
        path = tmp_path / f"reconciled-{reconciled}"
        ex, client, clock = _resting_executor(path, bid=30.0, ask=30.05)
        ex.on_order_event(_accepted(client.last_order_id))
        _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0, reconciliation=reconciled)

        _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
        ex.on_order_event(_canceled(client.last_order_id))
        row = _record(path)["submitted"][0]
        # `submitted[-1]`, never `[1]`: an implementation that halted here would leave one
        # submission and raise IndexError, which is a crash rather than a reading -- and a reading
        # is what names WHICH property the defect moved.
        readings.append((row["filled_qty"], len(row["events"]), len(client.submitted), client.submitted[-1][0].quantity))

    assert readings[0] == (0.4, 3, 2, 0.6)  # accepted, fill, cancel -- and the IOC asks for the remainder
    assert readings[1] == readings[0]


def test_a_refused_resubmission_journals_the_fills_that_already_happened(tmp_path):
    """`update_plan_intent` SETS filled_qty rather than accumulating, so a resubmission refused at
    the gate would otherwise overwrite the intent's summary with 0.0 -- the operator's summary
    surface saying nothing was bought when 0.4 was."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0)

    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_order_event(_canceled(client.last_order_id))  # the venue's own cancel

    assert len(client.submitted) == 1  # the gate refused the reprice
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["filled_qty"] == 0.4


def test_a_rejection_during_a_time_box_cancel_still_proceeds_to_the_fallback(tmp_path):
    """A time-box cancel declares the maker attempt over and says CROSS NOW; a revoke declares the
    book untradeable and says STOP. Conflating the two silently drops the fallback, and the fallback
    existing at all is why maker-first was acceptable, since an unfilled leg strands the probe."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled  # the time-box cancel is out, and the venue answers with a rejection

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

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
    ex.on_order_event(_accepted(client.last_order_id))
    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)
    assert client.canceled

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

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
    ex.on_order_event(_accepted(client.last_order_id))
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
    ex.on_order_event(_accepted(client.last_order_id))
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

    assert [str(cid) for cid in client.canceled] == ["O-opener", "O-flagged", "O-orphan"]
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

    assert [str(cid) for cid in client.canceled] == ["O-done"]


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

    assert [str(cid) for cid in client.canceled] == ["O-attached"]


def test_a_post_restart_fill_on_a_re_attached_order_lands_in_its_own_boundarys_row(tmp_path):
    """Spec 00090 D5 across a restart: an adopted order left resting must still have an appender, and
    the appender must write the row's OWN boundary -- the row lives four hours behind the tick that
    adopted it.

    The event is injected DIRECTLY into the own-topic handler, which is the whole scope of the claim:
    what this pins is the appender and its boundary arithmetic, not the delivery. On the live engine
    a reconciled venue order wears the EXTERNAL strategy id and its fills arrive on
    `events.order.EXTERNAL` instead."""
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
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)

    _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled("O-1"))
    assert client.submitted[1][0].quantity == 0.6  # the IOC, sized against the 0.4 already in

    _deliver_fill(ex, client, "O-1", 0.1, px=30.0)  # the late fill, for the order already superseded
    ex.on_order_event(_canceled("O-2"))  # the IOC comes back unfilled

    assert len(client.submitted) == 3
    assert client.submitted[2][0].quantity == 0.5  # not 0.6 -- the late fill was counted
    row = _record(tmp_path)["submitted"][0]
    assert row["client_order_id"] == "O-1" and row["filled_qty"] == 0.5


class _FlakyOrdersCache(StubCache):
    """`orders_open` raises the first time and answers the second -- the transient a startup pass must
    survive rather than latch through. It is `orders_open` because that is the only read the pass
    takes for its population; aimed elsewhere this class would raise nowhere the pass can see."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.calls = 0

    def orders_open(self, *, venue=None, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("the cache is not populated yet")
        return super().orders_open(venue=venue, **kwargs)


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
    assert [str(cid) for cid in client.canceled] == ["O-opener"]

    ex.on_order_event(_fill("O-opener", 0.0002, px=30000.0))
    ex.on_order_event(_canceled("O-opener"))

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
    assert [str(cid) for cid in client.canceled] == ["O-orphan"]


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

    assert [str(cid) for cid in client.canceled] == expected
    # Attached either way (cancel is a request, not an outcome), so the ack lands in the row.
    ex.on_order_event(_canceled("O-attached"))
    assert [e["type"] for e in _record(tmp_path, earlier)["submitted"][0]["events"]] == ["OrderCanceled"]


# --- the external topic: an adopted order's own events (spec 00098) ------------------------------


@contextmanager
def _executor_errors(level=logging.ERROR):
    """The executor logger's own records at `level` and above -- for the tests that must see a
    swallowed failure LOGGED, and at WARNING for the one that must see NOTHING logged. Not `caplog`,
    blind here for the reasons `_the_tick_backstop_never_fires` gives."""
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


def _resting_limit_order(client_order_id, *, quantity="1.0"):
    """A REAL `LimitOrder` resting at the venue, driven to ACCEPTED by the library's own events.

    Real because the terminal-state write reads `cache.order(...).status`, and only the library's own
    state machine can say what an event does to that status -- including for the stale and replayed
    acks it REFUSES, which is where reading the order rather than the event's name earns its place."""
    head = (_TRADER_ID, _STUB_STRATEGY_ID, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id))
    order = LimitOrder(
        *head, OrderSide.BUY, Quantity.from_str(quantity), Price.from_str("30000.0"), TimeInForce.GTC,
        False, False, False, UUID4(), 0,
    )  # fmt: skip
    order.apply(OrderSubmitted(*head, _ACCOUNT_ID, UUID4(), 0, 0))
    order.apply(OrderAccepted(*head, _VENUE_ORDER_ID, _ACCOUNT_ID, UUID4(), 0, 0, False))
    assert order.status == OrderStatus.ACCEPTED  # a fixture that started closed would adopt nothing
    return order


def _adopted_executor(tmp_path, *, client_order_id="O-attached", reduce_only=True):
    """A previous process's resting order, adopted by the startup pass and attached to its OWN
    boundary's row four hours back -- the only state the external topic's matched path is reachable
    from. The trailing assert is the point: a construction that attached nothing would hand every
    test below the unmatched path's green instead."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, client_order_id, reduce_only=reduce_only, when=earlier)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(client_order_id)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert client_order_id in ex._attached
    return ex, client, earlier


def _deliver_external_event(ex, client, event):
    """Deliver an event on the external topic the way the venue does: the order the Cache holds takes
    it FIRST, then the strategy sees it. The resulting status is DERIVED, never stated -- the
    library's own state machine decides it, which is what makes a stale ack behave here as it does in
    production: the transition is refused, the order keeps the status it had, and the event is
    dispatched anyway."""
    order = client.cache.order(event.client_order_id)
    assert order is not None, f"{event.client_order_id} is not in the cache -- the delivery would prove nothing"
    try:
        order.apply(event)
    except RuntimeError as exc:  # the state machine declining a stale or replayed ack: still published
        assert "Invalid order state transition" in str(exc), exc
    ex.on_external_order_event(event)


def test_an_external_fill_completing_an_adopted_order_appends_counts_and_closes_the_row(tmp_path):
    """The matched clean path end to end, and the pin on the DELEGATION ORDER: the trip runs FIRST,
    so this fill is measured against a row not yet credited with it -- swap the two and the mirrored
    quantity is counted twice, latching the kill switch on a perfectly healthy final fill.

    The row's STATE closes here because nautilus publishes no terminal event after a resting order's
    last fill. The entry itself stays attached, so a fill racing the close still journals."""
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
    assert metrics.fills == [("maker", 0.08)] and metrics.positions == [("BTC/EUR", -0.001)]


def test_a_partial_external_fill_leaves_the_adopted_row_open_and_attached(tmp_path):
    """The completion rule's other direction, without which a rule that closed the row on ANY fill
    would ship green: a fill short of the ledgered quantity makes no state claim and keeps the entry
    attached for the remainder's own fill. The pair also exercises the tolerance across two float
    additions."""
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
    assert [str(cid) for cid in client.canceled] == ["O-attached"]  # the trip pulls it
    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e["event"] for e in row["events"]] == ["fill"]
    assert row["filled_qty"] == overfill
    assert metrics.external == ["matched"]


@pytest.mark.parametrize(
    "event_cls, expected_state",
    [(OrderCanceled, "canceled"), (OrderExpired, "venue_canceled"), (OrderRejected, "rejected")],
)
def test_an_external_terminal_event_closes_the_row_but_keeps_it_attached_for_a_racing_fill(tmp_path, event_cls, expected_state):
    """The ruled map, written from `validate_exec_record`'s own state names -- `_store` would refuse a
    minted one anyway -- and reached through the venue's ORDER rather than the event's class name: the
    event is applied to the real `LimitOrder` the Cache holds, its status moves by the library's own
    state machine, and the row's state is what that status maps to.

    The row's STATE closes; the ATTACHMENT does not. `ownTrades` and `openOrders` are separate Kraken
    WS channels with no cross-stream ordering guarantee, so a fill can land after the terminal ack,
    and popping here would send it to the unmatched branch to be counted and never journaled -- the
    no-fill-without-a-record invariant broken on the path built to restore it."""
    ex, client, earlier = _adopted_executor(tmp_path, client_order_id="O-opener", reduce_only=False)
    assert [str(cid) for cid in client.canceled] == ["O-opener"]  # the pass's own cancel
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _deliver_external_event(ex, client, _event(event_cls, client_order_id="O-opener"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == expected_state
    assert [e["type"] for e in row["events"]] == [event_cls.__name__]
    assert row["filled_qty"] == 0.0
    assert "O-opener" in ex._attached

    ex.on_external_order_event(_fill("O-opener", 0.0004))  # the fill that raced the ack

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e.get("event") or e.get("type") for e in row["events"]] == [event_cls.__name__, "fill"]
    assert row["filled_qty"] == 0.0004  # journaled, not counted-and-dropped
    assert row["state"] == expected_state  # the detached append makes no state claim of its own
    assert metrics.external == ["matched", "matched"]  # never `unmatched`: the row is still vouched
    assert metrics.fills == [("maker", 0.08)]
    assert not _kill_file(tmp_path).exists()


def test_a_terminal_ack_after_the_completing_fill_never_demotes_the_row(tmp_path):
    """A row that is COMPLETE may not be un-said by a later terminal ack: completion is inferred from
    the LEDGERED quantity, so a venue order can outlive it and be canceled afterwards, and an
    unconditional terminal write would rewrite `state` to `canceled` on a full row whose completion
    has already been counted -- permanently, since a terminal row never re-attaches.

    Replayed acks reach here too: a non-fill event the order's own state machine REFUSES is still
    published, and the duplicate-fill and overfill guards do not cover terminal events."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex.on_external_order_event(_fill("O-attached", 0.001))  # completes the ledgered quantity
    assert metrics.orders == ["filled"]

    _deliver_external_event(ex, client, _canceled("O-attached"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled"  # the completion stands; `canceled` here would be a lie
    assert row["filled_qty"] == pytest.approx(0.001)
    assert [e.get("event") or e.get("type") for e in row["events"]] == ["fill", "OrderCanceled"]  # still evidence
    assert metrics.orders == ["filled"]  # counted once, and the record never contradicts it
    assert ex._attached["O-attached"][1]["state"] == "filled"  # the mirror the guard itself reads
    assert not _kill_file(tmp_path).exists()


def test_a_stale_terminal_ack_never_overwrites_the_state_the_venues_order_actually_reached(tmp_path):
    """Where reading the ORDER and reading the event's NAME part company, on the live trade path.
    `ownTrades` and `openOrders` are separate Kraken WS channels with no cross-stream ordering
    guarantee, so a stale `OrderExpired` can land after a cancel the venue already took; the order's
    own state machine REFUSES that transition and the event is published anyway.

    Keyed on the name, the second ack rewrites the row to `venue_canceled` and the ledger then says
    the venue ended an order this engine cancelled -- permanently, since a terminal row never
    re-attaches. The fixture is not degenerate: the two readings of the SAME event differ."""
    ex, client, earlier = _adopted_executor(tmp_path, client_order_id="O-opener", reduce_only=False)
    assert [str(cid) for cid in client.canceled] == ["O-opener"]  # the pass's own cancel went out

    _deliver_external_event(ex, client, _canceled("O-opener"))
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"

    _deliver_external_event(ex, client, _event(OrderExpired, client_order_id="O-opener"))

    assert client.cache.order(ClientOrderId("O-opener")).status == OrderStatus.CANCELED  # the refusal
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled"  # NOT venue_canceled: this engine asked, and the venue took it
    assert [e["type"] for e in row["events"]] == ["OrderCanceled", "OrderExpired"]  # both are evidence
    assert ex._attached["O-opener"][1]["state"] == "canceled"  # the mirror the completion guard reads


def test_an_external_cancel_rejection_is_recorded_without_closing_the_adopted_row(tmp_path):
    """The venue positively says the cancel did NOT take, so the order may still rest: the event is
    evidence, the row keeps its open state, and the entry stays attached for the fill that can still
    arrive. Nothing special-cases it -- the venue's order is still ACCEPTED after a refused cancel
    and no OPEN status is in the terminal map."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _deliver_external_event(ex, client, _event(OrderCancelRejected, client_order_id="O-attached", reason="EOrder:Unknown order"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "accepted"
    assert row["events"] == [{"type": "OrderCancelRejected", "at": NOW.isoformat(), "reason": "EOrder:Unknown order"}]
    assert "O-attached" in ex._attached
    assert metrics.external == ["matched"]


@pytest.mark.parametrize(
    "reconciled, expected_state, expected_open",
    [
        # The venue's own ack, and it is what makes the fixture non-degenerate: the same event class,
        # the same row, driving the same order to the same CANCELED status -- and the two arms end on
        # DIFFERENT states, one of them terminal and one of them re-attachable.
        (False, "canceled", []),
        (True, "accepted", ["O-opener"]),
    ],
)
def test_a_terminal_the_engine_minted_leaves_the_adopted_row_open_where_the_venues_ack_closes_it(
    tmp_path, reconciled, expected_state, expected_open
):
    """A terminal the execution engine minted for itself is not a venue outcome, so it writes no venue
    outcome down -- the adopted surface's half of the property the own-order surface holds.

    The construction is the production one: the startup pass cancels an adopted non-reducer, the
    venue never answers, and past the in-flight retry budget the engine publishes the `OrderCanceled`
    itself. It is applied to the order before dispatch, so the Cache says CANCELED either way and
    only the flag can tell the two apart. Closing the row on it would put a venue claim in the ledger
    nobody made, and `_OPEN_ORDER_STATES` holds no terminal state, so the row would never re-attach.

    Read as a pair: the false arm is the true positive, and the `open_submitted_rows` reading IS what
    the next startup re-attaches from."""
    ex, client, earlier = _adopted_executor(tmp_path, client_order_id="O-opener", reduce_only=False)
    assert [str(cid) for cid in client.canceled] == ["O-opener"]  # this process asked; the venue is what did not answer
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id="O-opener", reconciliation=reconciled))

    assert client.cache.order(ClientOrderId("O-opener")).status == OrderStatus.CANCELED  # both arms, so the status cannot decide
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == expected_state
    assert row["events"] == [{"type": "OrderCanceled", "at": NOW.isoformat()}]  # evidence, either way
    assert ex._attached["O-opener"][1]["state"] == expected_state  # the mirror stays with the row
    assert [r["client_order_id"] for _, r in open_submitted_rows(tmp_path / "journal", NOW)] == expected_open
    assert [r.getMessage() for r in records] == (
        ["OrderCanceled for O-opener was reconciled, not received -- the venue never answered, so its row keeps the state it has"]
        if reconciled
        else []
    )
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


class _UnreadableOrderCache(StubCache):
    """A Cache whose `order()` refuses the way the real one does from INSIDE an order-event handler:
    `RuntimeError("Already mutably borrowed")`, because the Cache is still mutably borrowed for the
    write that produced the event -- which this process's own cancel command generates, from the
    adopt pass and from a trip. Switchable, because the startup pass reads the same accessor and the
    row has to attach against a readable Cache first."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fail_order_reads = False
        self.refused = 0

    def order(self, client_order_id):
        if self.fail_order_reads:
            self.refused += 1
            raise RuntimeError("Already mutably borrowed")
        return super().order(client_order_id)


@pytest.mark.parametrize(
    "unreadable, expected_state, expected_warnings",
    [
        # The healthy read, and it is what makes the fixture non-degenerate: the same event, the
        # same row, and the two arms end on DIFFERENT states.
        (False, "canceled", []),
        (True, "accepted", ["the venue order behind O-attached could not be read -- its row keeps the state it has"]),
    ],
)
def test_an_unreadable_cache_costs_the_terminal_state_and_never_the_event(tmp_path, unreadable, expected_state, expected_warnings):
    """A Cache read that RAISES must cost the row its terminal state and nothing else.

    The dominant source of a terminal ack on this path is a cancel this very process sent, and a read
    taken inside that handler finds the Cache still mutably borrowed for the write that produced it.
    Letting it escape would abandon the whole handler, and with it the forensic event payload, to
    decide a state the event never carried -- so the event still appends, the entry stays attached,
    and the row keeps the state it has. Read as a pair: without the readable arm an unconditional
    `None` would pass, and without the raising arm a narrowed `except` is invisible."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-attached", reduce_only=True, when=earlier)
    cache = _UnreadableOrderCache(open_orders=[_resting_limit_order("O-attached")])
    client = StubClient(cache)
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert "O-attached" in ex._attached  # a construction that attached nothing proves nothing below
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    # The venue's own order takes the event first, exactly as `_deliver_external_event` does -- then
    # the read the handler takes afterwards is the one under test.
    event = _canceled("O-attached")
    cache.order(ClientOrderId("O-attached")).apply(event)
    cache.fail_order_reads = unreadable
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_external_order_event(event)

    assert cache.refused == (1 if unreadable else 0)  # the branch under test was the one that ran
    assert [r.getMessage() for r in records] == expected_warnings
    assert all(r.exc_info is not None for r in records)  # logged with the traceback, not bare
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == expected_state
    assert row["events"] == [{"type": "OrderCanceled", "at": NOW.isoformat()}]  # evidence, either way
    assert row["filled_qty"] == 0.0
    assert ex._attached["O-attached"][1]["state"] == expected_state  # the mirror stays with the row
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


def test_the_external_handler_logs_and_continues_when_the_ledger_write_raises(tmp_path, monkeypatch):
    """A raise out of this handler is the event loop's problem, not this process's to take -- so the
    one thing on this path that touches disk is made to fail and the handler must swallow it, loudly.
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
    """A previous process's ledgered row plus the cache order reconciliation left behind for it, with
    the two quantities set independently -- the delta between them is what the startup sweep reads.
    `closed_status` builds the closed-while-down shape, reachable only through the wide read.

    Returned BEFORE the first tick so a test can install its metrics hooks first: the completion
    counter fires inside `on_timer`."""
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


@pytest.mark.parametrize(
    "ledgered, venue",
    [
        (0.0004, 0.0004 + executor_module._OVERFILL_TOLERANCE / 10),  # venue ahead by an ulp
        # LEDGER ahead: a clean three-fill restart, where the sum of per-fill floats exceeds the
        # venue's one exactly-rounded figure. Without the negative dead-band this LATCHES THE KILL
        # SWITCH AT BOOT, on a restart where nothing whatever is wrong.
        (0.0003 + 0.0004 + 0.0005, float(Quantity.from_str("0.00120000"))),
    ],
)
def test_a_sub_tolerance_difference_between_ledger_and_venue_is_reconciled_silently(tmp_path, ledgered, venue):
    """The dead-band, and the arm that must produce NOTHING: the ledgered figure is a sum of per-fill
    floats and the venue's is one exactly-rounded `float(Quantity)`, so a clean multi-fill restart
    differs by ulps and a repair arm without the dead-band journals a phantom repair on every healthy
    restart. The two figures differ by a tenth of the tolerance rather than by zero, which an
    exact-equality construction would not catch.

    BOTH SIGNS are pinned because only one is survivable to get wrong: the venue-ahead case costs a
    phantom repair, while the LEDGER-ahead case is the ordinary shape of a healthy multi-fill restart
    and reaches `_trip_kill`, which latches at boot and cannot be cleared by any code."""
    ex, _client, earlier = _reconciling_executor(tmp_path, ledgered_filled=ledgered, venue_filled=venue)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"] == []  # no event
    assert row["filled_qty"] == ledgered and row["state"] == "accepted"  # no state write, no quantity moved
    assert [r.getMessage() for r in records if "reconcil" in r.getMessage()] == []  # and no log
    assert metrics.orders == []
    assert not _kill_file(tmp_path).exists()


def test_a_positive_reconciliation_delta_is_journaled_as_a_repair_and_mirrored(tmp_path):
    """The down-window fill, recovered: the quantity is resident in the reconciled order's own
    `filled_qty` because the engine applies the fill and publishes it in one synchronous body. It is
    journaled as a REPAIR, not a fill -- there is no per-fill detail or fee behind it, and a fills
    increment with no fee would make the two counters disagree in a way the row cannot explain."""
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
    assert [str(cid) for cid in client.canceled] == ["O-attached", "O-attached"]


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


# --- D16: the venue withdrawing a fill from an order this engine already closed (spec 00100) -----


_FINISHED_QTY = 0.001


def _finished_row_executor(tmp_path, *, withdrawn):
    """A row a previous process CLOSED on `_FINISHED_QTY`, plus the venue order left behind for it,
    with the venue's own fill withdrawal applied or without.

    The order is a REAL `LimitOrder` driven through the library's own events, because only the state
    machine can say what a withdrawal does to one: `OrderFillVoided` lands `OrderStatus.VOIDED` with
    `filled_qty` back at zero, while the arm that skips it stays `FILLED` at the full quantity. The
    event carries `reconciliation=True`, the only shape the framework mints.

    THE PAIR IS THE FIXTURE: both arms are closed and identical on disk, and differ in exactly the
    quantity the sweep compares -- an order the withdrawal does not move would pass under either
    behaviour and prove nothing."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=True, when=earlier)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=_FINISHED_QTY)
    order = _resting_limit_order("O-finished", quantity=f"{_FINISHED_QTY:.8f}")
    order.apply(_fill("O-finished", _FINISHED_QTY))
    assert order.status == OrderStatus.FILLED and float(order.filled_qty) == _FINISHED_QTY
    if withdrawn:
        order.apply(_fill_voided("O-finished", _FINISHED_QTY))
        assert order.status == OrderStatus.VOIDED and float(order.filled_qty) == 0.0
    client = StubClient(StubCache(closed_orders=[order]))
    return _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY)), client, earlier


def _fill_voided(client_order_id, qty, *, trade_id="T-1"):
    """The library's own `OrderFillVoided` for a fill `_fill` produced, in the shape the framework's
    reconciliation mints: `reconciliation=True`, the ORIGINAL fill's trade id (a void references the
    trade it undoes, unlike a synthesized fill, which mints one), and a `correction_id` naming the
    report it came from."""
    return OrderFillVoided(
        _TRADER_ID, _STUB_STRATEGY_ID, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id),
        _VENUE_ORDER_ID, _ACCOUNT_ID, f"reconciliation-R-1-{trade_id}", TradeId(trade_id), _quantity(qty),
        OrderSide.BUY, OrderType.LIMIT, _price(30000.0), Currency.from_str("EUR"), LiquiditySide.MAKER,
        UUID4(), 0, 0, True,
    )  # fmt: skip


def test_a_withdrawn_fill_on_a_row_this_engine_closed_latches_the_kill_switch(tmp_path, kill_trip_expected):
    """The one correction that lands on a FINISHED order, which `open_submitted_rows` cannot show
    anyone: the venue reports the order filled for less than the quantity this engine recorded,
    published and sized against.

    The engine never sees the withdrawal as an event -- the library applies it during the node's
    startup reconciliation, before any handler is subscribed -- so the venue order's own lowered
    `filled_qty` is the whole signal. NOTHING is reversed: the ledger records what the venue reported
    when it reported it, and a row silently corrected to match would no longer show that the two
    figures ever disagreed."""
    ex, client, earlier = _finished_row_executor(tmp_path, withdrawn=True)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    assert (
        _kill_file(tmp_path)
        .read_text()
        .endswith("order O-finished shows 0 filled at the venue, less than the 0.001 this engine recorded and closed it on\n")
    )
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled"  # never demoted: the fills that completed it were reported and counted
    assert row["filled_qty"] == _FINISHED_QTY  # and never subtracted
    assert row["events"] == [{"event": "withdrawn", "at": NOW.isoformat(), "qty": -_FINISHED_QTY, "venue_filled_qty": 0.0}]
    assert "O-finished" not in ex._attached  # a finished row is not re-attached by this sweep
    assert metrics.orders == []  # the outcome counters are never retracted, and none is added
    assert client.canceled == []  # nothing was resting to pull


def test_a_finished_row_the_venue_still_agrees_with_is_swept_silently(tmp_path):
    """The true positive: the same closed row and the same completed order, the withdrawal alone
    removed. A sweep that latched on every finished row -- or on the mere fact that a row is closed --
    would pass the test above and kill the engine at every boot after any order ever filled."""
    ex, client, earlier = _finished_row_executor(tmp_path, withdrawn=False)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    ex.on_timer(NOW)

    assert not _kill_file(tmp_path).exists()
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled"
    assert row["filled_qty"] == _FINISHED_QTY
    assert row["events"] == []
    assert metrics.orders == []
    assert client.canceled == []


def test_a_ledger_the_finished_row_sweep_cannot_write_still_latches_the_kill_switch(tmp_path, monkeypatch, kill_trip_expected):
    """The journal write stands IN FRONT of the trip, so a read-only journal must not be able to
    swallow the latch -- `_record_trip_fill`'s ruling, on this path. Guard-proving: the failure is
    constructed, and WHICH log line fired is read rather than merely that one did."""
    ex, _client, _earlier = _finished_row_executor(tmp_path, withdrawn=True)

    def _raise(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(executor_module, "update_submitted_row", _raise)
    with _executor_errors() as records:
        ex.on_timer(NOW)

    assert "the withdrawal on finished row O-finished could not be journaled" in [r.getMessage() for r in records]
    assert _kill_file(tmp_path).exists()


def _limit_orders_by_status():
    """One REAL `LimitOrder` per `OrderStatus` the library defines, driven there by the library's own
    events, plus the refusals for the statuses this order type cannot wear. `LimitOrder` is the class
    this engine's orders are and the only one the startup pass adopts. Returns `(reached, refused)`:
    requested status -> the order wearing it, and requested status -> the exception the library raised
    refusing to put it there. Built inside a function so the extra library imports are paid only by
    the test that needs them."""
    from nautilus_trader.model import (
        OrderDenied,
        OrderEmulated,
        OrderPendingCancel,
        OrderPendingUpdate,
        OrderReleased,
        OrderSubmitted,
        OrderTriggered,
        Venue,
    )

    head = (TraderId("TESTER-001"), StrategyId("S-1"), InstrumentId(Symbol("BTC/EUR"), Venue("KRAKEN")), ClientOrderId("O-1"))
    account, venue_order_id = AccountId("KRAKEN-001"), VenueOrderId("V-1")
    price, eur = Price.from_str("100.0"), Currency.from_str("EUR")

    def order():
        return LimitOrder(*head, OrderSide.BUY, Quantity.from_str("1.0"), price, TimeInForce.GTC, False, False, False, UUID4(), 0)

    def event(cls, *middle, reconciliation=None):
        # The three-field tail every order event carries, and the `reconciliation` flag the ones
        # published by the venue leg carry after it.
        tail = (UUID4(), 0, 0) if reconciliation is None else (UUID4(), 0, 0, reconciliation)
        return cls(*head, *middle, *tail)

    def fill(qty):
        return OrderFilled(
            *head,
            venue_order_id,
            account,
            TradeId(f"T-{qty}"),
            OrderSide.BUY,
            OrderType.LIMIT,
            Quantity.from_str(qty),
            price,
            eur,
            LiquiditySide.MAKER,
            UUID4(),
            0,
            0,
            False,
        )

    resting = [lambda: event(OrderSubmitted, account), lambda: event(OrderAccepted, venue_order_id, account, reconciliation=False)]
    paths = {
        OrderStatus.INITIALIZED: [],
        OrderStatus.DENIED: [lambda: event(OrderDenied, "the risk engine said no")],
        OrderStatus.EMULATED: [lambda: event(OrderEmulated)],
        OrderStatus.RELEASED: [lambda: event(OrderEmulated), lambda: event(OrderReleased, price)],
        OrderStatus.SUBMITTED: resting[:1],
        OrderStatus.ACCEPTED: resting,
        OrderStatus.REJECTED: [*resting[:1], lambda: event(OrderRejected, account, "insufficient funds", reconciliation=False)],
        OrderStatus.CANCELED: [*resting, lambda: event(OrderCanceled, reconciliation=False)],
        OrderStatus.EXPIRED: [*resting, lambda: event(OrderExpired, reconciliation=False)],
        OrderStatus.TRIGGERED: [*resting, lambda: event(OrderTriggered, reconciliation=False)],
        OrderStatus.PENDING_UPDATE: [*resting, lambda: event(OrderPendingUpdate, account, reconciliation=False)],
        OrderStatus.PENDING_CANCEL: [*resting, lambda: event(OrderPendingCancel, account, reconciliation=False)],
        OrderStatus.PARTIALLY_FILLED: [*resting, lambda: fill("0.4")],
        OrderStatus.FILLED: [*resting, lambda: fill("1.0")],
        OrderStatus.VOIDED: [
            *resting,
            lambda: fill("1.0"),
            lambda: OrderFillVoided(
                *head,
                venue_order_id,
                account,
                "C-1",
                TradeId("T-1.0"),
                Quantity.from_str("1.0"),
                OrderSide.BUY,
                OrderType.LIMIT,
                price,
                eur,
                LiquiditySide.MAKER,
                UUID4(),
                0,
                0,
                False,
            ),
        ],
    }

    reached, refused = {}, {}
    for status, steps in paths.items():
        subject = order()
        try:
            for step in steps:
                subject.apply(step())
        except Exception as exc:
            refused[status] = exc
            continue
        reached[status] = subject
    return reached, refused


def test_the_terminal_state_map_is_total_over_the_librarys_own_closed_statuses():
    """The ONE map both row-state paths write through -- the startup reconciliation and the live
    external stream -- covers every closed status the installed library defines.

    Totality against the library rather than against a hand-written list: a status the map does not
    carry leaves a closed order's row open forever, and the failure is silent. It is also why the
    live path reads the order's status rather than the event's class name -- a name is an open string
    space over which no totality statement is expressible.

    `TRIGGERED` is the one status outside the domain, and it costs the proof nothing: a limit order
    has no trigger, and the rows this pass adopts are this engine's own limit orders."""
    reached, refused = _limit_orders_by_status()

    assert set(reached) | set(refused) == set(OrderStatus.variants())
    assert set(refused) == {OrderStatus.TRIGGERED}
    for status, exc in refused.items():
        assert isinstance(exc, RuntimeError) and "Invalid event for order type" in str(exc), f"{status}: {exc!r}"
    for status, subject in reached.items():
        assert subject.status == status, f"the path for {status} landed on {subject.status}"

    closed = {status for status, subject in reached.items() if subject.is_closed}
    assert len(closed) >= 5

    assert set(executor_module._ADOPTED_TERMINAL_STATES) == closed
    assert set(executor_module._ADOPTED_TERMINAL_STATES.values()) <= execledger_module._ROW_STATES


def test_a_repair_then_an_external_fill_for_the_remainder_completes_the_row_exactly_once(tmp_path):
    """Spec 00098's D7 meeting D1, the sequence where a mis-mirror costs money: the sweep repairs the
    down-window partial and the subscription delivers the remainder, so the row must read the full
    ledgered quantity, state `filled`, counted once, with no trip. Unmirrored, the repair never moves
    the trip base and the completion never fires; double-mirrored, this fill overshoots and
    false-kills."""
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

    assert [str(cid) for cid in client.canceled] == ["O-opener"]
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

    assert [str(cid) for cid in client.canceled] == ["O-opener"]
    assert [r.getMessage() for r in records] == ["adopted row O-opener could not be reconciled against the venue"]
    assert _record(tmp_path, earlier)["submitted"][0]["events"] == []  # nothing was written from an unreadable figure


def test_a_ledger_that_cannot_be_written_never_costs_the_overshoot_trip(tmp_path, monkeypatch, kill_trip_expected):
    """A ledger failure may never cost the trip, which is why `_record_trip_fill`'s own `try` is
    scoped to the write alone: the repair write comes FIRST on this arm, so a wrapper spanning both
    would let a read-only journal swallow the latch and the gate would then read normal over a live
    venue-vs-ledger divergence. The in-process quantity is credited either way, since it tracks what
    filled rather than what could be written down."""
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
    client.cache.set_external_position("BTC/EUR", 0.0004)  # the settle landed as a holding, attributed to EXTERNAL
    _advance_ticks(ex, minutes=2)
    assert not (exec_dir(state_dir) / KILL_FILE).exists()
    assert client.canceled == []  # and nothing was pulled off the venue for it either


def test_a_fill_for_an_order_this_engine_never_submitted_trips_the_kill_switch(tmp_path, kill_trip_expected):
    """The unknown own-strategy order. The same event SHAPE as the settle above and the opposite
    verdict: what separates them is that this one names an order id, on this engine's own strategy,
    that the ledger has no row for -- so a fill exists that nothing here can account for."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    resting = client.submitted[0][0]

    ex.on_order_event(_fill("O-unknown", 0.001))

    text = _kill_file(tmp_path).read_text()
    assert "no open order record" in text and "O-unknown" in text  # WHICH condition fired
    assert client.canceled == [resting.client_order_id]
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
    ex.on_order_event(_accepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.0006)
    assert not _kill_file(tmp_path).exists()  # 0.0006 of 0.001 is a partial, not a divergence
    _deliver_fill(ex, client, client.last_order_id, 0.0006)

    assert "of the 0.001 it was submitted for" in _kill_file(tmp_path).read_text()
    assert client.canceled == [resting.client_order_id]
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
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)

    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> reprice
    resting = client.submitted[1][0]
    assert resting.quantity == 0.6

    _deliver_fill(ex, client, "O-1", 0.3, px=30.0)  # the late fill on the superseded order
    assert not _kill_file(tmp_path).exists()  # 0.7 of a 1.0 target, 0.7 of O-1's own 1.0: healthy
    _deliver_fill(ex, client, "O-2", 0.6, px=30.0)

    assert "across its orders" in _kill_file(tmp_path).read_text()
    assert client.canceled == [resting.client_order_id]
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
    ex.on_order_event(_accepted(client.last_order_id))

    cache.set_position("BTC/EUR", 0.0005)  # the venue moved by half of what the fill claims
    ex.on_order_event(_fill(client.last_order_id, 0.001))

    assert "not the 0.001" in _kill_file(tmp_path).read_text()
    assert [str(cid) for cid in client.canceled] == ["O-attached"]
    assert _intent_outcome(tmp_path, 0) == "filled"  # it DID fill -- the divergence is what follows
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_a_terminal_whose_position_matches_its_fills_does_not_trip(tmp_path):
    """The reconciliation's other direction, on the identical construction one number apart: the
    Cache agrees with the fills, so the intent ends and the NEXT one starts. Without this a check
    that tripped on every terminal would pass the test above."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))

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
    ex.on_order_event(_accepted(client.last_order_id))
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
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))  # superseded by the reprice

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
    ex.on_order_event(_accepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.001, side="sell", px=30001.0)

    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


# --- D11 fix round: the in-process backstop, and the branches that only fire on failure ------------


def test_a_kill_file_that_could_not_be_written_still_refuses_the_next_plan(tmp_path, kill_trip_expected):
    """The kill FILE is the durable latch; when it cannot be written the only thing left is this
    process's own memory that it tripped, and that must be a refusal. A directory in the kill file's
    place stands in for any write failure, and it is removed afterwards so the gate reads `full`
    again -- from there nothing on disk refuses anything, which is what makes the memory the subject."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
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
    ex.on_order_event(_accepted(client.last_order_id))
    ex._kill_tripped = True

    ex.on_order_event(_canceled(client.last_order_id))  # would reprice

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
    ex.on_order_event(_accepted(client.last_order_id))

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


# --- the weekly tracking-error trip --------------------------------------------------------------
#
# The call site is the 4-HOURLY BOUNDARY ALERT, never `on_timer`: a tick-path trip would sit behind
# an operator-written probe-plan.json and could never fire in the stopped-placing state it exists for.

_TRACK_MONDAY = datetime(2026, 9, 7, tzinfo=timezone.utc)  # ISO 2026-W37, the week under test
_TRACK_LEAD = _TRACK_MONDAY - timedelta(days=1)  # six boundaries before it, so the book is built
_TRACK_EVAL = _TRACK_MONDAY + timedelta(days=7)  # the boundary alert that scores W37
_TRACK_NEXT_EVAL = _TRACK_EVAL + timedelta(days=7)
_TRACK_BAND = 120.0
_TRACK_NAV = 1000.0

# Ten EUR legs at DISTINCT non-zero weights, one of them negative (a short leg signs `held`, so a
# sell booked as a buy would double the apparent position); the two /BTC legs at 0.0, which is what
# `final_targets` really carries -- symbol-keyed TWELVE against base-keyed TEN closes. A uniform or
# all-zero book cannot tell a wrong key space, a lost sign or a dropped leg from a healthy read.
_TRACK_WEIGHTS = {
    "BTC/EUR": 0.20,
    "ETH/EUR": 0.15,
    "SOL/EUR": 0.12,
    "ADA/EUR": 0.10,
    "DOGE/EUR": 0.08,
    "XRP/EUR": 0.07,
    "DOT/EUR": 0.06,
    "LINK/EUR": 0.05,
    "LTC/EUR": 0.04,
    "AVAX/EUR": -0.03,
    "ETH/BTC": 0.0,
    "SOL/BTC": 0.0,
}
# Base-keyed, spanning five orders of magnitude: a close is a DIVISOR in drift_bps, so a fixture
# whose prices are all ~1 would score identically however the legs were mixed up.
_TRACK_CLOSES = {
    "BTC": 60000.0,
    "ETH": 3200.0,
    "SOL": 145.0,
    "LTC": 85.0,
    "AVAX": 22.0,
    "LINK": 14.0,
    "DOT": 4.2,
    "XRP": 0.62,
    "ADA": 0.45,
    "DOGE": 0.13,
}
_TRACK_BASES = tuple(_TRACK_CLOSES)

_OPENING = _TRACK_LEAD + timedelta(hours=4)  # the journal's oldest boundary carries NO fill
_BUILD_OUT = _TRACK_LEAD + timedelta(hours=16)
_IN_WEEK = _TRACK_MONDAY + timedelta(hours=40)  # 2026-09-08 16:00, boundary 10 of the week
_MINT_AT = _OPENING + timedelta(hours=4)  # the boundary a live engine dates itself at: the next one

# Asymmetric by construction: ten different sizes, one sell, and BTC arriving in two slices at two
# different boundaries -- so a reader that ignored the boundary a fill was filed under, or summed
# magnitudes unsigned, would land on a different number.
_NINE_LEGS = [
    ("ETH/EUR", "buy", 0.0468),
    ("SOL/EUR", "buy", 0.825),
    ("ADA/EUR", "buy", 220.0),
    ("DOGE/EUR", "buy", 610.0),
    ("XRP/EUR", "buy", 112.0),
    ("DOT/EUR", "buy", 14.2),
    ("LINK/EUR", "buy", 3.55),
    ("LTC/EUR", "buy", 0.468),
    ("AVAX/EUR", "sell", 1.36),
]
# ~46 bps: the book is deployed and tracks. THE TRUE POSITIVE -- a band that refused this would ship
# an always-tripping switch.
_HEALTHY_FILLS = {
    _OPENING: [("BTC/EUR", "buy", 0.00042)],
    _BUILD_OUT: [("BTC/EUR", "buy", 0.00290), *_NINE_LEGS],
}
# ~317 bps: the same book with BTC 26 EUR short of its target, plus one in-week DOGE top-up, so the
# per-cycle series is not flat across the week and boundary attribution is load-bearing.
_BREACH_FILLS = {
    _OPENING: [("BTC/EUR", "buy", 0.00042)],
    _BUILD_OUT: [("BTC/EUR", "buy", 0.00248), *_NINE_LEGS],
    _IN_WEEK: [("DOGE/EUR", "buy", 30.0)],
}
# The same shortfall with NOTHING filled inside the week: started, quiet, and fully measured.
_QUIET_FILLS = {b: rows for b, rows in _BREACH_FILLS.items() if b != _IN_WEEK}
# The same book, opened a day earlier, so the day-dir holding the opening slice can be deleted
# WHOLE -- which is the only cut `zcrypto-engine-journal-prune.sh` actually makes. What survives is
# a day whose 00:00 boundary is quiet and whose 16:00 carries the build-out.
_EARLY_OPENING = _TRACK_MONDAY - timedelta(days=2) + timedelta(hours=4)
_PRUNABLE_FILLS = {
    _EARLY_OPENING: [("BTC/EUR", "buy", 0.00042)],
    _BUILD_OUT: [("BTC/EUR", "buy", 0.00290), *_NINE_LEGS],
}
# ~5500 bps: only two legs were ever opened. Started (so it is not the never-traded case) and
# violently outside any band, so a partial week that was scored would be unmistakable.
_PARTIAL_FILLS = {_OPENING: [("BTC/EUR", "buy", 0.00332), ("ETH/EUR", "buy", 0.0468)]}


def _track_snapshots(boundary):
    """One pair x grid pair, shaped to the no-peek invariant so the fixture is a record the engine
    could really have written."""
    midnight = boundary.replace(hour=0, minute=0, second=0, microsecond=0)
    return tuple(
        SnapshotEntry(
            pair="BTC/EUR",
            grid=grid,
            n_bars=400,
            first_ts=boundary - timedelta(days=90),
            last_ts=last,
            content_hash="a" * 64,
            path=f"{boundary:%Y-%m-%d}/snapshots/cycle-{boundary:%H}/BTC-EUR-{grid}.parquet",
        )
        for grid, last in (("240", boundary - timedelta(hours=4)), ("1440", midnight - timedelta(days=1)))
    )


def _track_fill_row(index, symbol, side, qty):
    px = _TRACK_CLOSES[symbol.split("/")[0]] if symbol.endswith("/EUR") else 0.05
    return {
        "plan_id": f"plan-{index}",
        "intent_index": 0,
        "client_order_id": f"O-{index}",
        "intent": {"symbol": symbol, "side": side, "action": "open", "mode": "execute", "notional_eur": qty * px},
        "order": {"symbol": symbol, "side": side, "qty": qty, "price": px},
        "state": "filled",
        "filled_qty": qty,
        "events": [
            {
                "event": "fill",
                "at": None,  # stamped by the caller, which knows the boundary
                "qty": qty,
                "px": px,
                "fee": 0.02,
                "fee_currency": "EUR",
                "liquidity": "MAKER",
                "trade_id": f"T-{index}",
            }
        ],
    }


def _journal_week(tmp_path, *, fills, start=_TRACK_MONDAY, n_cycles=42, lead=0, level="full", overrides=None):
    """`lead` boundaries before `start` plus `n_cycles` from it, each with the cycle record AND the
    exec record the engine writes at that boundary. `fills` maps a boundary to (symbol, side, qty)
    tuples; `overrides` maps a boundary to any of `level`/`weights`/`closes`."""
    journal = tmp_path / "journal"
    overrides = overrides or {}
    boundaries = [start - timedelta(hours=4 * (lead - i)) for i in range(lead)]
    boundaries += [start + timedelta(hours=4 * i) for i in range(n_cycles)]
    index = 0
    for boundary in boundaries:
        override = overrides.get(boundary, {})
        weights = override.get("weights", _TRACK_WEIGHTS)
        closes = override.get("closes", _TRACK_CLOSES) if "closes" in override else _TRACK_CLOSES
        record = CycleRecord(
            schema_version=2,
            cycle_ts=boundary,
            snapshots=_track_snapshots(boundary),
            final_targets=dict(weights),
            started_at=boundary + timedelta(seconds=90),
            completed_at=boundary + timedelta(minutes=2),
            code_version="1.0.0",
            builder_path="fast",
            closes=None if closes is None else dict(closes),
        )
        day = journal / f"{boundary:%Y-%m-%d}"
        day.mkdir(parents=True, exist_ok=True)
        (day / f"cycle-{boundary:%H}.json").write_text(to_json(record))
        verdict = GateVerdict(level=override.get("level", level), reasons=(), inputs={})
        write_exec_record(journal, boundary, verdict, evaluated_at=boundary)
        for symbol, side, qty in fills.get(boundary, ()):
            index += 1
            row = _track_fill_row(index, symbol, side, qty)
            row["events"][0]["at"] = (boundary + timedelta(minutes=3)).isoformat()
            append_submitted_row(journal, boundary, row, verdict=verdict, evaluated_at=boundary)
    return journal


def _tracking_executor(tmp_path, *, band=_TRACK_BAND, armed=True, clock=None, gate=None, at=_TRACK_EVAL):
    # The clock sits just past the boundary being scored, as the live one does: the alert fires at
    # `boundary + settle delay`, and the birth recorder reads the journal "through now".
    config = _config(tmp_path, exec_armed=armed, tracking_band_bps=band, shadow_nav_eur=_TRACK_NAV)
    return _executor(tmp_path, config=config, clock=clock or (lambda: at + timedelta(minutes=2)), gate=gate)


def _mint_birth(tmp_path, at=_MINT_AT, **kwargs):
    """Run the boundary the live engine would have DATED ITSELF at -- the first one after its first
    fill. Every fixture below is a journal the engine lived through boundary by boundary, so a test
    that jumped straight to the scoring boundary a week later would be asking the recorder to date a
    week-old fill, which is the one thing it refuses."""
    _tracking_executor(tmp_path, at=at, **kwargs).on_boundary(at)


def _tracking_states(tmp_path, boundary=_TRACK_EVAL, mint_at=_MINT_AT, **kwargs):
    """Fire one boundary alert against a fresh executor and return (kill-file-exists, states).

    `mint_at=None` is the engine that never witnessed its own first fill -- no record, and whatever
    the journal still holds is all it has."""
    set_executor_hooks()  # the mint is setup, not the measurement -- it publishes into nobody's list
    if mint_at is not None:
        _mint_birth(tmp_path, at=mint_at, **kwargs)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    _tracking_executor(tmp_path, at=boundary, **kwargs).on_boundary(boundary)
    return _kill_file(tmp_path).exists(), metrics.tracking


def test_the_boundary_alert_reaches_the_executors_tracking_trip_with_no_plan_file(tmp_path, kill_trip_expected):
    """The whole design in one test: the strategy's 4-hourly alert, with NO probe plan on disk, no
    resting order and nothing in flight, reaches the executor and latches the kill file. Every
    `_evaluate` on the tick path is gated behind that absent plan file, so a trip hooked there
    could not fire here -- and the kill file has no other producer in this construction."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    _mint_birth(tmp_path)
    assert not _plan_path(tmp_path).exists()
    executor = _tracking_executor(tmp_path)
    strategy = SimpleNamespace(
        clock=None,
        _engine_config=executor._config,
        _run_cycle_fn=lambda cycle_ts, *, config, venue_state=None: None,
        _snapshot_venue_state=lambda: None,
        _next_cycle_ts=_TRACK_EVAL,
        _executor=executor,
    )
    strategy._schedule_alert = lambda boundary, alert_time: setattr(strategy, "_next_cycle_ts", boundary)

    ShadowStrategy._on_cycle_alert(strategy, None)

    assert "2026-W37" in _kill_file(tmp_path).read_text()
    assert executor._plan is None and not _plan_path(tmp_path).exists()


def test_an_unset_band_never_trips(tmp_path):
    """Ships disarmed: the same breaching week, with no band configured, decides nothing."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path, band=None)

    assert not tripped
    assert states == [executor_module._TRACKING_DISARMED]


def test_a_complete_week_beyond_the_band_latches_the_kill_file(tmp_path, kill_trip_expected):
    """The constructed defect: a fully-eligible week whose realized mean is ~317 bps against a 120
    bps band. The reason names the week and both numbers -- it is what an operator finds mid-incident."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path)

    assert tripped
    text = _kill_file(tmp_path).read_text()
    assert "2026-W37" in text and "317" in text and "120" in text
    assert states == [executor_module._TRACKING_BREACHED]


def test_a_healthy_complete_week_does_not_trip(tmp_path):
    """THE TRUE POSITIVE, and the reason the band is compared in the direction it is: the same
    fixture with the book fully deployed reads ~46 bps, strictly the other side of 120, and must
    pass. A guard that refused this would be an always-refusing guard shipping green."""
    _journal_week(tmp_path, fills=_HEALTHY_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_WITHIN_BAND]


def test_a_quiet_week_with_a_started_series_still_trips(tmp_path, kill_trip_expected):
    """ "No data" means the realized series never STARTED, never that a week was quiet. A week with
    no fills at all but a `held` that stopped tracking its targets is fully measured -- and is
    precisely the stopped-placing state this trip exists to catch."""
    _journal_week(tmp_path, fills=_QUIET_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path)

    assert tripped
    assert states == [executor_module._TRACKING_BREACHED]


def test_a_partial_week_never_trips_however_bad_it_looks(tmp_path):
    """41 boundaries, not 0, at ~5500 bps: a week the engine did not fully live through is not
    comparable to one it did, and the fixture is far enough outside the band that scoring it would
    be unmistakable."""
    _journal_week(tmp_path, fills=_PARTIAL_FILLS, lead=6, n_cycles=41)

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_a_week_the_gate_never_reached_full_does_not_trip(tmp_path):
    """Eligibility is the JOURNALED level, not live config: `restart_hold` is written at every
    engine start and cleared only by hand, so a week spent held reads as fully armed while the
    engine never traded. The fixture is the breaching one but for ONE boundary's level, so only
    eligibility can tell the two apart."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6, overrides={_TRACK_MONDAY + timedelta(hours=80): {"level": "reduce_only"}})

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_the_week_containing_the_first_fill_is_not_scored(tmp_path):
    """A week holding cycles on BOTH sides of the first fill averages an undeployed book (10000 bps
    a cycle) with a deployed one, so the first week of live trading is biased toward a trip. It is
    excluded -- and the NEXT week, on the same held, must still be SCORED and pass: a rule that
    refused both would be indistinguishable here."""
    _journal_week(tmp_path, fills={_TRACK_MONDAY + timedelta(hours=80): [("BTC/EUR", "buy", 0.00332), *_NINE_LEGS]}, lead=6)
    _journal_week(tmp_path, fills={}, start=_TRACK_EVAL)

    straddling, straddling_states = _tracking_states(tmp_path)
    settled, settled_states = _tracking_states(tmp_path, boundary=_TRACK_NEXT_EVAL)

    assert not straddling and straddling_states == [executor_module._TRACKING_UNSCORED]
    assert not settled and settled_states == [executor_module._TRACKING_WITHIN_BAND]


def test_a_fill_at_the_journals_oldest_boundary_is_refused(tmp_path):
    """The truncated journal: the same HEALTHY week with everything before the build-out pruned
    away, so the opening slice is gone, `held` is short and the week reads ~290 bps. Nothing on
    disk distinguishes that from a real breach, so a first fill sitting on the oldest boundary the
    journal still holds is refused rather than scored."""
    journal = _journal_week(tmp_path, fills=_HEALTHY_FILLS, lead=6)
    for boundary in (_TRACK_LEAD, _OPENING, _TRACK_LEAD + timedelta(hours=8), _TRACK_LEAD + timedelta(hours=12)):
        (journal / f"{boundary:%Y-%m-%d}" / f"cycle-{boundary:%H}.json").unlink()
        (journal / f"{boundary:%Y-%m-%d}" / f"exec-{boundary:%H}.json").unlink()

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_it_is_refused_while_exec_armed_is_false(tmp_path):
    """Every journaled level still reads `full`, so only the config gate can stop this one."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path, armed=False)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_a_week_missing_journaled_closes_is_refused_not_guessed(tmp_path):
    """Every artifact written before the closes key existed reads None. The price a cycle actually
    used is not recoverable afterwards, and a guessed one moves every leg's drift at once."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6, overrides={_TRACK_MONDAY + timedelta(hours=80): {"closes": None}})

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_a_week_whose_targets_miss_a_model_leg_is_refused(tmp_path):
    """A leg absent from `final_targets` contributes no drift at all, so a book that dropped one
    reads BETTER than it is -- the fail-open direction, and the one a trip must never take."""
    thin = {s: w for s, w in _TRACK_WEIGHTS.items() if s != "ADA/EUR"}
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6, overrides={_TRACK_MONDAY + timedelta(hours=80): {"weights": thin}})

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_an_unreadable_journal_does_not_raise_onto_the_trade_path(tmp_path):
    """A measurement may never take the engine down. The refusal is published as one, so an
    operator can tell "not scored" from "nothing ran"."""
    journal = _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    (journal / f"{_TRACK_MONDAY:%Y-%m-%d}" / "exec-08.json").write_text("{not json")

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_the_trip_keeps_the_first_reason_across_a_restart(tmp_path, kill_trip_expected):
    """The kill file IS the durable state -- there is no marker, no checkpoint. A restarted process
    re-derives the same breaching week and must leave the first reason exactly as it found it: that
    text, with its timestamp, is what the operator reads to know when the engine stopped."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    _mint_birth(tmp_path)
    _tracking_executor(tmp_path).on_boundary(_TRACK_EVAL)
    first = _kill_file(tmp_path).read_text()

    # A REAL gate over the latched tree -- `_gate()` asserts FULL and a kill file makes it `none`,
    # which is exactly the state a restart into a tripped engine starts in.
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue_reader())
    later = _tracking_executor(tmp_path, clock=lambda: _TRACK_EVAL + timedelta(days=30), gate=gate)
    later.on_boundary(_TRACK_EVAL + timedelta(hours=4))

    assert _kill_file(tmp_path).read_text() == first
    assert later._kill_tripped is False  # nothing tripped again -- the latch on disk was enough


def test_the_idle_tick_never_evaluates_tracking(tmp_path):
    """`on_timer` is not a call site for this. A week-wide read on a 5-second tick would be 17280
    journal scans a day, and the tick's whole cheap-idle contract is that it does an os.lstat and
    stops."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    gate = CountingGate()
    executor = _tracking_executor(tmp_path)
    executor._gate = gate

    for minute in range(3):
        executor.on_timer(_TRACK_EVAL + timedelta(minutes=minute))

    assert not _kill_file(tmp_path).exists()
    assert gate.calls == 0  # the idle path reads nothing at all


# The ramp an operator arming exactly ON a week boundary produces: the first slice lands at the
# week's own first boundary, the rest ten boundaries in -- an undeployed book averaged with a
# deployed one, which is the WEEK THE SERIES STARTED IN wearing a settled week's clothes.
_BOUNDARY_RAMP_FILLS = {
    _TRACK_MONDAY: [("BTC/EUR", "buy", 0.00042)],
    _IN_WEEK: [("BTC/EUR", "buy", 0.00290), *_NINE_LEGS],
}


def test_a_pruned_journal_head_refuses_instead_of_scoring_a_short_held(tmp_path):
    """The retention prune turns the true positive into a latched false kill, and this is that
    construction: the HEALTHY fixture -- the week that must pass -- with the two oldest boundaries
    deleted as `zcrypto-engine-journal-prune.sh` deletes day-dirs. The opening slice goes with them,
    `held` is short by it, and the same journal reads a breach.

    Nothing on disk distinguishes that from a real breach, and asking whether the oldest surviving
    boundary carries a fill passes whenever the prune cuts at a quiet one. The birth record answers
    the question actually being asked."""
    journal = _journal_week(tmp_path, fills=_HEALTHY_FILLS, lead=6)
    healthy, healthy_states = _tracking_states(tmp_path)
    assert not healthy and healthy_states == [executor_module._TRACKING_WITHIN_BAND]
    birth = exec_dir(tmp_path) / executor_module.FIRST_FILL_FILE
    assert birth.read_text().strip() == _OPENING.isoformat()

    # Cut per BOUNDARY, which is the granularity the check itself works at -- not a replica of the
    # prune, which removes whole day-dirs. The shape a real prune produces is the same one: a first
    # fill late on day D, and a quiet 00:00 on D+1 left as the oldest survivor. The sibling test
    # below builds exactly that, with the whole day-dir deleted.
    for boundary in (_TRACK_LEAD, _OPENING):
        for prefix in ("cycle", "exec"):
            (journal / f"{boundary:%Y-%m-%d}" / f"{prefix}-{boundary:%H}.json").unlink()

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]
    # Write-once: the record still names the fill that is no longer on disk, which is the whole of
    # what it knows and the only reason the refusal above is possible.
    assert birth.read_text().strip() == _OPENING.isoformat()


def test_the_first_fill_landing_on_the_week_boundary_is_not_scored_either(tmp_path):
    """A first fill exactly ON Monday 00:00 -- what arming at a week boundary produces -- is still
    the week the series started in, and its ramp is still in the mean: 2118.2 bps against a 120 bps
    band. A strictly-interior test (`>`) scores it and latches the kill file on an engine that was
    doing exactly what it was told."""
    _journal_week(tmp_path, fills=_BOUNDARY_RAMP_FILLS, lead=6)

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_a_malformed_fill_event_does_not_raise_onto_the_trade_path(tmp_path):
    """The outer catch's own defect, constructed rather than assumed: `validate_exec_record` checks a
    row's KEY SET and that `events` is a list, never an event's contents -- so a fill event missing
    `px` passes every ledger check and `KeyError`s inside `extract_fills`, which is not an
    `EngineError` and escapes the refusal arm. The catch publishes because a measurement may neither
    take the engine down nor leave the previous verdict standing on the board."""
    journal = _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    path = journal / f"{_BUILD_OUT:%Y-%m-%d}" / f"exec-{_BUILD_OUT:%H}.json"
    doc = read_exec_record(path)
    del doc["submitted"][0]["events"][0]["px"]
    path.write_text(json.dumps(doc))
    execledger_module.validate_exec_record(doc)  # the ledger's own checks still pass it

    tripped, states = _tracking_states(tmp_path)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]


def test_a_pruned_head_is_refused_when_no_birth_record_survives(tmp_path):
    """The missing-file path, which is NOT the same event as "the series has not started".

    The recorder is gated on the record being absent, so an engine that lost it -- a rebuilt state
    directory, a restore -- runs the mint against whatever the journal still holds. Here the day-dir
    carrying the opening slice is gone and the surviving day opens on a QUIET 00:00, so the "oldest
    boundary carries no fill" evidence is satisfied perfectly and the earliest surviving fill would
    be minted as a birth it never was.

    What stops it is that a birth is something a boundary WITNESSES hours after the fill, so a
    week-old candidate is refused and nothing is written: an engine that cannot date itself must not
    invent a date."""
    journal = _journal_week(tmp_path, fills=_PRUNABLE_FILLS, lead=12)
    shutil.rmtree(journal / f"{_EARLY_OPENING:%Y-%m-%d}")

    tripped, states = _tracking_states(tmp_path, mint_at=None)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]
    assert not (exec_dir(tmp_path) / executor_module.FIRST_FILL_FILE).exists()


# --- _reconcile_terminal is scoped to this engine's own position (the operator's hand settle) ----


def _terminal_intent(*, filled, symbol="BTC/EUR", side="buy", position_before=0.0, own_position_before=0.0):
    """An intent already at its terminal exit, carrying only what `_reconcile_terminal` reads."""
    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS[symbol])
    return executor_module._ActiveIntent(
        index=0,
        intent=ProbeIntent(symbol=symbol, side=side, action="open", mode="execute", notional_eur=30.0, qty=None, leverage=None),
        raw_intent={},
        instrument_id=instrument_id,
        constraints=InstrumentConstraints(
            symbol=symbol,
            instrument_id=str(instrument_id),
            ordermin=0.0001,
            costmin=0.5,
            costmin_quote="EUR",
            lot_step=1e-08,
            tick_size=0.1,
        ),
        phase="terminal",
        started_at=NOW,
        quote_deadline=NOW,
        timebox_at=NOW,
        filled=filled,
        position_before=position_before,
        own_position_before=own_position_before,
    )


def test_an_operator_holding_present_at_intent_start_never_reaches_the_terminal_comparison(tmp_path):
    """The CAPTURE end of the scoping, driven through production because the three
    `_reconcile_terminal` tests below never execute `_start_intent`'s own read. The operator is
    already holding when the intent starts and the intent fills exactly what it asked for: an
    instrument-scoped capture would carry the operator's 0.5 into `own_position_before`, the
    strategy-scoped terminal read would exclude it, and the kill switch would latch on a sanctioned
    hand settle."""
    cache = StubCache()
    cache.set_external_position("BTC/EUR", 0.5)
    ex, client, clock = _resting_executor(tmp_path, client=StubClient(cache))
    ex.on_order_event(_accepted(client.last_order_id))

    _deliver_fill(ex, client, client.last_order_id, 0.001)  # moves OUR position, as the venue does

    assert not _kill_file(tmp_path).exists(), (
        "an operator holding that predates the intent entered this engine's own baseline -- the "
        "capture read must be scoped to this strategy, not to the instrument"
    )
    assert _intent_outcome(tmp_path, 0) == "filled"


def test_reconcile_terminal_ignores_a_holding_this_engine_never_ordered(tmp_path):
    """The operator hand-settles on a symbol this engine also trades, while an intent is running:
    spec 00098 D1's scope property says that reaches no trip, no row and no cancel, and an
    instrument-scoped position read breaks it -- the operator's holding lands in the post-terminal
    comparison and latches the kill switch on a sanctioned action."""
    cache = StubCache()
    cache.set_position("BTC/EUR", 0.001)  # exactly what our own fill bought
    cache.set_external_position("BTC/EUR", 0.5)  # the operator's, mid-intent
    ex = _executor(tmp_path, client=StubClient(cache=cache))

    ex._reconcile_terminal(_terminal_intent(filled=0.001))

    assert not (exec_dir(tmp_path) / KILL_FILE).exists(), (
        "a holding this engine never ordered tripped the kill switch -- spec 00098 D1's scope "
        "property says an operator's hand settle reaches no trip"
    )


def test_reconcile_terminal_still_trips_when_our_own_position_diverges(tmp_path, kill_trip_expected):
    """The true positive, without which the scoping fix above could ship as an always-passing guard:
    the same shape with the divergence in THIS engine's own position -- a fill it never saw or one it
    mis-accounted."""
    cache = StubCache()
    cache.set_position("BTC/EUR", 0.002)  # twice what our fills account for
    ex = _executor(tmp_path, client=StubClient(cache=cache))

    ex._reconcile_terminal(_terminal_intent(filled=0.001))

    assert (exec_dir(tmp_path) / KILL_FILE).exists(), "a divergence in this engine's own position must still latch the kill switch"


def test_reconcile_terminal_baselines_against_our_own_holding_not_the_instrument(tmp_path):
    """Scoping the READ alone is not the fix: the baseline has to be scoped too. The operator was
    already holding 0.5 when the intent started, so the instrument-scoped `position_before` and this
    engine's own genuinely disagree, and a fix that narrowed only the post-terminal read would expect
    0.501, see its own 0.001, and trip."""
    cache = StubCache()
    cache.set_position("BTC/EUR", 0.001)
    cache.set_external_position("BTC/EUR", 0.5)
    ex = _executor(tmp_path, client=StubClient(cache=cache))

    ex._reconcile_terminal(_terminal_intent(filled=0.001, position_before=0.5, own_position_before=0.0))

    assert not (exec_dir(tmp_path) / KILL_FILE).exists(), (
        "the post-terminal comparison baselined against the whole instrument -- both ends must be "
        "scoped to this engine's own position or a pre-existing operator holding trips it"
    )


# --- the client handle is the real Strategy, and this file's stub is only a restatement of it ----


def _client_surface_reached_by_the_executor() -> set[str]:
    """Every name `ProbeExecutor` reaches through `self._client`, read off the executor's own
    source. Derived rather than listed: a hand-written list is a second restatement of the same
    contract, and would go stale at exactly the moment a new call site appears."""
    tree = ast.parse(Path(executor_module.__file__).read_text())
    return {
        n.attr
        for n in ast.walk(tree)
        if isinstance(n, ast.Attribute)
        and isinstance(n.value, ast.Attribute)
        and n.value.attr == "_client"
        and isinstance(n.value.value, ast.Name)
        and n.value.value.id == "self"
    }


def test_every_client_surface_the_executor_reaches_exists_on_the_real_strategy():
    """Production hands `ProbeExecutor` a nautilus `Strategy` and every test here hands it
    `StubClient`, so this reads production's call set against the REAL class and never against the
    stub: a name the library does not have raises inside an `except` that refuses an intent or trips
    the kill switch, while the suite stays green because the stub still carries it. The two halves
    are deliberately independent -- a name planted in the stub cannot trip this test, and one planted
    in production cannot be rescued by the stub."""
    from nautilus_trader.trading import Strategy

    surface = _client_surface_reached_by_the_executor()
    assert len(surface) >= 5, f"the walk found only {sorted(surface)} -- vacuous"
    missing = sorted(name for name in surface if not hasattr(Strategy, name))
    assert missing == [], f"the executor reaches {missing} on its client, which the real Strategy does not carry"


# --- this file's other nautilus stand-ins, checked against the library ---------------------------
#
# tests/test_engine_stub_fidelity.py classifies every test double in the engine suite and names the
# guards below; the reasoning that makes them worth having lives there.


def _cache_accessors_the_engine_reaches() -> set[str]:
    """Every accessor production calls through a nautilus `Cache`, read off the two modules that
    hold one: the executor (through `self._client.cache`) and the venue-state reader (through its
    `cache` argument). Derived rather than listed, for the same reason the client surface is."""
    reached: set[str] = set()
    for module in (executor_module, venuestate_module):
        tree = ast.parse(Path(module.__file__).read_text())
        for n in ast.walk(tree):
            if not isinstance(n, ast.Attribute):
                continue
            holder = n.value
            if (isinstance(holder, ast.Attribute) and holder.attr == "cache") or (
                isinstance(holder, ast.Name) and holder.id == "cache"
            ):
                reached.add(n.attr)
    return reached


def test_every_cache_accessor_the_engine_reaches_exists_on_the_real_cache():
    """`StubCache` restates the Cache, and the executor reaches it on the live trade path inside
    `except` blocks that refuse an intent or trip the kill switch -- so an accessor the library has
    dropped is a silent refusal in production and a green suite here."""
    from nautilus_trader.common import Cache

    reached = _cache_accessors_the_engine_reaches()
    assert len(reached) >= 5, f"the walk found only {sorted(reached)} -- vacuous"
    missing = sorted(name for name in reached if not hasattr(Cache, name))
    assert missing == [], f"the engine reaches {missing} on the Cache, which the real Cache does not carry"


def _limit_call_the_executor_makes() -> tuple[int, set[str]]:
    """The positional count and keyword names of the executor's one `order_factory.limit(...)`
    call, `**flag` resolved to the keys of the dict it is built from. Read off production rather
    than restated: `StubOrderFactory.limit(**kwargs)` accepts literally anything, so nothing else
    in this file can tell a keyword the real factory takes from one it does not."""
    tree = ast.parse(Path(executor_module.__file__).read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "limit"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "order_factory"
    ]
    assert len(calls) == 1, f"expected exactly one order_factory.limit call, found {len(calls)}"
    call = calls[0]
    names = {kw.arg for kw in call.keywords if kw.arg is not None}
    splatted = {kw.value.id for kw in call.keywords if kw.arg is None and isinstance(kw.value, ast.Name)}
    for name in splatted:
        assigns = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets)
        ]
        assert len(assigns) == 1, (
            f"`{name}` is splatted into the limit call and assigned {len(assigns)} times -- cannot resolve its keys"
        )
        keys = {
            k.value
            for a in assigns
            for d in ast.walk(a.value)
            if isinstance(d, ast.Dict)
            for k in d.keys
            if isinstance(k, ast.Constant)
        }
        assert keys, f"`**{name}` resolved to no keys -- the resolution is checking nothing"
        names |= keys
    return len(call.args), names


def test_the_limit_call_the_executor_makes_binds_against_the_real_order_factory():
    """`StubOrderFactory`'s whole surface is `limit(**kwargs)`, which agrees with every keyword
    including one the real factory would reject, so binding production's call against the REAL
    signature is what makes the keywords checkable: a renamed or dropped parameter is red here
    instead of raising at the first live submission, inside the `except` that refuses the intent."""
    import inspect

    from nautilus_trader.common import OrderFactory

    positional, names = _limit_call_the_executor_makes()
    assert len(names) >= 5, f"the walk found only {sorted(names)} -- vacuous"
    # A placeholder per argument: `bind` checks arity and keyword names, never the values.
    inspect.signature(OrderFactory.limit).bind(None, *[None] * positional, **dict.fromkeys(names))


def test_a_real_money_answers_both_accessors_the_fill_row_reads():
    """The two accessors the fill path takes off a commission -- `float(...)` for the amount and
    `.currency.code` for its denomination -- pinned by VALUE rather than by a name-existence walk:
    both reads are wrapped in `getattr(..., default)`, so a dropped accessor does not raise in
    production, it silently reports a fee of None while the EUR fee total stops accumulating.

    The second half is the quantization every fee number in this file rests on: a `Money` quantizes
    to its currency's precision, so a `EUR` fee written to two decimals survives it and a finer one
    does not -- a fixture written that way would be asserting its own rounding."""
    real = Money(1.25, Currency.from_str("EUR"))
    assert float(real) == pytest.approx(1.25)
    assert real.currency.code == "EUR"

    assert Currency.from_str("EUR").precision == 2
    assert float(Money(0.08, Currency.from_str("EUR"))) == pytest.approx(0.08)
    assert float(Money(0.012, Currency.from_str("EUR"))) == pytest.approx(0.01)
    assert Currency.from_str("XXBT").precision == 8
    assert float(Money(0.00002, Currency.from_str("XXBT"))) == pytest.approx(0.00002)


# Names each stub below carries for the harness's own sake, modelling nothing on the real type: the
# storage it answers from, and the mutators tests drive it with. Listed one by one on purpose -- a
# blanket "underscore-prefixed names are plumbing" rule would exempt exactly the shape this guard
# exists to catch.
_STUB_CACHE_PLUMBING = frozenset(
    {
        "_instruments",
        "_balances",
        "_positions",
        "_external",
        "_closed",
        "_open_orders",
        "_closed_orders",
        "_raises",
        "_position_key",
        "set_position",
        "set_external_position",
        "close_position",
        "move_position",
        "apply_fill",
    }
)


def _nautilus_standins():
    """(label, stub instance, real class, plumbing) for every test double in this file that stands
    in for a nautilus type. Built inside a function so the extra library imports are paid only by
    the test that needs them."""
    from nautilus_trader.common import Cache, OrderFactory
    from nautilus_trader.model import Position
    from nautilus_trader.trading import Strategy

    return [
        ("_fake_instrument", _fake_instrument("BTC/EUR.KRAKEN"), CurrencyPair, frozenset()),
        ("StubCache", StubCache(), Cache, _STUB_CACHE_PLUMBING),
        ("_FlakyOrdersCache", _FlakyOrdersCache(), Cache, _STUB_CACHE_PLUMBING | {"calls"}),
        ("_PositionReadFails", _PositionReadFails(), Cache, _STUB_CACHE_PLUMBING | {"broken"}),
        ("_UnreadableOrderCache", _UnreadableOrderCache(), Cache, _STUB_CACHE_PLUMBING | {"fail_order_reads", "refused"}),
        ("StubOrderFactory", StubOrderFactory(), OrderFactory, frozenset({"_n"})),
        (
            "StubClient",
            StubClient(),
            Strategy,
            frozenset({"submitted", "canceled", "subscribed", "unsubscribed", "_submit_raises", "last_order_id"}),
        ),
        ("_held", _held(**{"BTC/EUR": 0.1})[INSTRUMENT_IDS["BTC/EUR"]][0], Position, frozenset()),
        ("_open_order", _open_order("O-1"), LimitOrder, frozenset()),
        ("_closed_order", _closed_order("O-1", OrderStatus.FILLED), LimitOrder, frozenset()),
    ]


def test_no_stub_in_this_file_offers_a_name_its_real_nautilus_type_lacks():
    """A stub MISSING something production calls fails loudly the first time a test runs it; a stub
    OFFERING something the real type lacks fails NOTHING -- every test believes the fabricated
    attribute forever, and production is the only place the read comes back wrong. Every violation is
    collected rather than raised at the first, so one red run names all of them."""
    violations = []
    for label, stub, real, plumbing in _nautilus_standins():
        offered = {name for name in dir(stub) if not name.startswith("__")} - plumbing
        assert offered, f"{label} offers nothing outside its plumbing list -- the check is vacuous"
        stale = sorted(name for name in plumbing if hasattr(real, name))
        extra = sorted(name for name in offered if not hasattr(real, name))
        if extra:
            violations.append(f"{label} offers {extra}, which {real.__name__} does not carry")
        if stale:
            violations.append(f"{label}'s plumbing list exempts {stale}, which {real.__name__} DOES carry -- check them instead")
    assert violations == [], "; ".join(violations)


def test_the_offers_walk_reaches_every_stub_the_fidelity_table_points_at_it():
    """`_nautilus_standins` is the entire reach of the guard above, and
    tests/test_engine_stub_fidelity.py's table is what CLAIMS that guard covers a given stub; nothing
    joined the two, so a stub could wear the claim while sitting outside the list. The join is a set
    equality both ways: a table row the walk omits is coverage claimed and not delivered, and a
    walked stub the table does not point here is a library stand-in nobody classified. Imported
    rather than restated, so it cannot be satisfied by a copy that drifts."""
    from test_engine_stub_fidelity import _OFFERS_EXECUTOR, TABLE

    named = {name for name, entry in TABLE[Path(__file__).name].items() if _OFFERS_EXECUTOR in entry.guards}
    assert len(named) > 5, f"the table points only {sorted(named)} at this guard -- the join is checking nothing"
    walked = {label for label, *_ in _nautilus_standins()}
    assert named == walked, f"{sorted(named ^ walked)} is claimed on one side of the join and absent from the other"
