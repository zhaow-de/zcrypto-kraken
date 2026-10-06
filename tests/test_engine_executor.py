from __future__ import annotations

import ast
import dataclasses
import json
import logging
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest
from nautilus_trader.common import SocketState, SocketStateChanged
from nautilus_trader.core import UUID4
from nautilus_trader.model import (
    AccountId,
    ClientId,
    ClientOrderId,
    Currency,
    CurrencyPair,
    FillReport,
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
    OrderPendingCancel,
    OrderRejected,
    OrderSide,
    OrderStatus,
    OrderStatusReport,
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
    Venue,
    VenueOrderId,
)
from prometheus_client import CollectorRegistry

import cli.engine.execledger as execledger_module
import cli.engine.executor as executor_module
import cli.engine.venuestate as venuestate_module
from cli.config import CacheSettings, EngineConfig
from cli.engine.accumledger import ACCUM_SCHEMA_VERSION, accum_record_path, read_accum_record, write_accum_record
from cli.engine.command import _ExecGauges, _ExecutionMetrics, _make_exec_sink, _seed_exec_positions
from cli.engine.draftplan import (
    LEGS,
    Constraints,
    DraftPlanError,
    assemble_plans,
    decide_leg,
    parse_balance_export,
    venue_balance,
)
from cli.engine.errors import EngineError, EngineJournalError
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
from cli.engine.executor import ProbeExecutor, read_venue_orders, restored_fill_state, set_executor_hooks, size_probe_order
from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order
from cli.engine.journal import CycleRecord, SnapshotEntry, from_json, to_json
from cli.engine.node import ShadowStrategy
from cli.engine.probeplan import MODES, PLAN_FILENAME, ProbeIntent, parse_plan
from cli.engine.venue import VenueStatus
from cli.engine.venueledger import write_venue_record
from cli.engine.venuestate import ConcordanceVerdict, InstrumentConstraints, VenueState
from tests import kraken_loopback

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
    """T0138's constructed defect: a BTC floor against a EUR notional. Assert WHICH failure fired --
    the denomination guard, not a BelowMinimum or an unrelated raise."""
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
    """The fail-open direction: a matched EUR pair that clears ordermin but falls under the EUR
    costmin floor. A costmin drop (e.g. costmin=0.0) must not survive this test."""
    result = size_probe_order(0.001, 100.0, _constraints())
    assert isinstance(result, BelowMinimum)
    assert "costmin" in result.reason


# --- a restored order's fill state (spec 00120 D9) ----------------------------------------------


@pytest.mark.parametrize(
    "fills, expected",
    [
        ([], "open"),
        ([0.4], "partial"),
        ([0.4, 0.6], "filled"),
    ],
)
def test_a_restored_orders_fill_state_is_read_off_its_filled_quantity(fills, expected):
    order = _resting_limit_order("O-1")
    for n, qty in enumerate(fills):
        order.apply(_fill("O-1", qty, trade_id=f"T-{n}"))
    assert restored_fill_state(order) == expected


@pytest.mark.parametrize(
    "filled, expected",
    [
        (1.0 - 1e-13, "filled"),
        (1.0 - 1e-11, "partial"),
        (1e-13, "open"),
    ],
)
def test_a_restored_orders_fill_state_reads_its_quantity_on_the_dead_band(filled, expected):
    # A fixed-point `Quantity` sums its fills exactly, so a real order never reaches the band; the
    # stand-in's floats sit inside it and just outside it.
    order = SimpleNamespace(filled_qty=filled, quantity=1.0)
    assert restored_fill_state(order) == expected


def test_reconciliation_regresses_a_partially_filled_orders_status_and_the_predicate_does_not_follow_it():
    order = _resting_limit_order("O-1")
    order.apply(_fill("O-1", 0.4))
    assert order.status == OrderStatus.PARTIALLY_FILLED
    order.apply(_event(OrderAccepted, client_order_id="O-1", reconciliation=True))
    assert order.status == OrderStatus.ACCEPTED
    assert restored_fill_state(order) == "partial"


# --- the structural pin -------------------------------------------------------------------------


# On the library's order surface and not venue-mutating: the exit's completion hook, the setter for
# which instruments count as external, and the GTD cancel, which stops a local timer and nothing else.
_ORDER_SURFACE_NOT_MUTATING = frozenset({"post_market_exit", "set_external_order_instrument_ids", "cancel_gtd_expiry"})
# On the Kraken HTTP clients and not venue-mutating: the credentials and endpoint they carry, the local
# instrument cache, and the cancel of this process's own in-flight requests. Every `request_*` and
# `get_*` is a read.
_HTTP_CLIENT_NOT_MUTATING = frozenset({"api_key", "api_key_masked", "base_url", "cache_instrument", "cancel_all_requests"})
# The engine's order machine and the red button, and nothing else. `cli/engine/flatten.py` is a
# second venue-mutating module BY DESIGN (spec 00106 D7): the button has to work when the machine
# is what broke, so the two deliberately share no code path, and the price of that is a second
# entry here rather than a guard that reuse would have satisfied.
_VENUE_MUTATING_MODULES = frozenset({"cli/engine/executor.py", "cli/engine/flatten.py"})
_REPO = Path(__file__).resolve().parents[1]


def _reach(name: str) -> re.Pattern:
    """`.name` as a whole attribute, called or bound, and never a longer name it prefixes."""
    return re.compile(rf"\.{re.escape(name)}\b")


def _http_client_order_surface() -> set[str]:
    import nautilus_trader.adapters.kraken as kraken

    clients = [getattr(kraken, name) for name in dir(kraken) if name.endswith("HttpClient")]
    assert len(clients) >= 2, f"the adapter exports only {clients}"
    return {
        name
        for client in clients
        for name in dir(client)
        if not name.startswith(("_", "request_", "get_")) and name not in _HTTP_CLIENT_NOT_MUTATING
    }


def _venue_mutating_reaches() -> list[re.Pattern]:
    """The installed wheel's own order surface, a strategy's and the Kraken HTTP clients' (the engine
    builds the spot one), so a method a later release adds is refused before anyone names it;
    `order_factory` mints the orders the rest submit."""
    from tests.test_engine_node import _order_mutating_surface

    names = (_order_mutating_surface() - _ORDER_SURFACE_NOT_MUTATING) | _http_client_order_surface() | {"order_factory"}
    assert len(names) >= 13, f"the derivation found only {sorted(names)}"
    return [_reach(name) for name in sorted(names)]


def test_the_venue_mutating_names_have_exactly_one_module():
    """Spec 00090 D4's structural pin. A text walk, not an import walk -- a reference in a comment is
    still one a refactor can activate."""
    reaches = _venue_mutating_reaches()
    files = sorted((_REPO / "cli").rglob("*.py"))
    assert len(files) > 100, f"the walk found {len(files)} files under cli/"
    offenders = []
    for path in files:
        rel = path.relative_to(_REPO).as_posix()
        if rel in _VENUE_MUTATING_MODULES:
            continue
        text = path.read_text()
        if any(reach.search(text) for reach in reaches):
            offenders.append(rel)
    assert offenders == []


# On the pinned wheel an instrument-named CancelAllOrders sends Kraken's account-wide CancelAll (upstream
# #5044 scopes it in a later nightly), so a cancel-all written for one pair cancels every pair's orders;
# the red button keeps its reach because its cancel is account-wide by design. A strategy sends it only
# with `strategy_only=False`; the probe's strategy runs live from infra/scripts/, hence the trees below.
# The match refuses the default form too: for a strategy registered under the operator's id it cancels
# the operator's orders (cli/engine/node.py), so narrowing it to `strategy_only=False` opens that door.
# `market_exit` issues that default form on each instrument the strategy holds orders or positions in.
_ACCOUNT_WIDE_CANCELS = {"cancel_all_orders": frozenset({"cli/engine/flatten.py"}), "market_exit": frozenset()}
_RUNTIME_TREES = ("cli", "infra", ".claude")


def test_only_the_red_button_reaches_a_cancel_all():
    """Tracked files only: `.claude/worktrees/` holds gitignored agent checkouts, copies of cli/
    included, which are not this tree's code. A tracked file deleted from the working tree is skipped."""
    listed = subprocess.run(
        ["git", "-C", str(_REPO), "ls-files", "-z", "--", *_RUNTIME_TREES], capture_output=True, text=True, check=True
    ).stdout.split("\0")
    tracked = [path for path in listed if path.endswith(".py") and (_REPO / path).is_file()]
    assert len(tracked) > 100, f"the walk found {len(tracked)} runtime .py files"
    offenders = [
        f"{path}: {name}"
        for path in tracked
        for name, allowed in _ACCOUNT_WIDE_CANCELS.items()
        if path not in allowed and _reach(name).search((_REPO / path).read_text())
    ]
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


def _orders_under(strategy_id, held):
    """`held` under `strategy_id`, the real Cache's own filter: every order when none is given, else
    the ones whose id equals it exactly, and a plain str refused as the typed accessor refuses it."""
    if strategy_id is None:
        return held
    if not isinstance(strategy_id, StrategyId):
        raise TypeError(f"Argument 'strategy_id' has incorrect type (expected StrategyId, got {type(strategy_id).__name__})")
    return [o for o in held if str(getattr(o, "strategy_id", None)) == str(strategy_id)]


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

    def hold_strategy_order(self, client_order_id, *, strategy_id, venue_order_id=None):
        """A REAL resting order under `strategy_id`, which `order` serves by `client_order_id` and the
        venue-order-id index by `venue_order_id` -- the Cache copy whose strategy a late fill's netting
        reads. `StubClient.submit_order` holds nothing here, so an order this process placed is absent
        from the Cache until a test holds it."""
        self._open_orders.append(_resting_limit_order(client_order_id, venue_order_id=venue_order_id, strategy_id=strategy_id))

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

    def client_order_id(self, venue_order_id):
        """The Cache's venue-order-id index: the client order id it holds an order under, None when
        it holds none. Typed like the real one, which refuses a str (`'str' object is not an
        instance of 'VenueOrderId'`)."""
        if not isinstance(venue_order_id, VenueOrderId):
            raise TypeError(f"'{type(venue_order_id).__name__}' object is not an instance of 'VenueOrderId'")
        wanted = str(venue_order_id)
        return next(
            (
                ClientOrderId(str(o.client_order_id))
                for o in [*self._open_orders, *self._closed_orders]
                if str(getattr(o, "venue_order_id", None)) == wanted
            ),
            None,
        )

    def orders(self, *, venue=None, strategy_id=None, **kwargs):
        """The whole index, open and closed, with `strategy_id` honoured as the real Cache honours it,
        by the exact id."""
        return _orders_under(strategy_id, [*self._open_orders, *self._closed_orders])

    def orders_open(self, *, venue=None, strategy_id=None, **kwargs):
        """The open half, `strategy_id` honoured the same way: the boot line's read."""
        return _orders_under(strategy_id, list(self._open_orders))

    def orders_inflight(self, *, venue=None, **kwargs):
        """The orders the library's in-flight check queries, derived from each held order's own
        `is_inflight` -- SUBMITTED, PENDING_UPDATE or PENDING_CANCEL on the real state machine -- so
        a test moves it only by applying the library's own events to a REAL order."""
        return [o for o in self._open_orders if getattr(o, "is_inflight", False)]

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
    """Counts evaluations. The idle-tick claim -- that with no plan on disk no gate is read inside
    the refresh period and one is per period past it -- is only checkable against something that
    records being asked."""

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


def _executor(
    tmp_path: Path,
    *,
    client=None,
    gate=None,
    config=None,
    clock=None,
    venue_orders=None,
    venue_cancel=None,
    venue_holdings=None,
    venue_fills=None,
    venue_positions=None,
    instrument_statuses=None,
) -> ProbeExecutor:
    client = client if client is not None else StubClient()
    return ProbeExecutor(
        client=client,
        gate=gate if gate is not None else _gate(tmp_path),
        config=config if config is not None else _config(tmp_path),
        clock=clock if clock is not None else (lambda: NOW),
        venue_orders=venue_orders,
        venue_cancel=venue_cancel,
        # An empty trade history unless a case hands one in: a withdrawal test's shortfall then trips
        # as it did before the history became the check's second source.
        venue_fills=venue_fills if venue_fills is not None else _VenueFills(),
        # An empty answer unless a case hands one in: the settle then publishes nothing, and the read
        # every startup pass makes reaches no venue.
        venue_holdings=venue_holdings if venue_holdings is not None else _VenueHoldings(),
        # No margin position unless a case hands one in: the mixed-inventory check then refuses nothing.
        venue_positions=venue_positions if venue_positions is not None else _VenuePositions(),
        # Every leg listed TRADING unless a case hands in its own: a case that drafts reaches no status read.
        instrument_statuses=instrument_statuses if instrument_statuses is not None else _all_trading,
    )


def _all_trading() -> dict[str, str]:
    return dict.fromkeys(INSTRUMENT_IDS, "TRADING")


@pytest.fixture(autouse=True)
def _no_production_venue_read(monkeypatch):
    """The executor's default venue read, venue cancel and holdings read are a real client on the
    trade credentials, and a developer's shell may hold them. A test that needs the venue's orders
    hands the executor its own reader, one that needs the re-cancel its own canceller, and `_executor`
    hands every case an empty holdings answer and every leg `TRADING`; reaching a default fails the
    test through every `except Exception` on the way, because `pytest.fail` raises a BaseException. The
    cancel's wrap, the two holdings reads' -- `read_venue_book`, the seam's default, and
    `read_venue_holdings`, which answers through it -- and the status read's let a call with a
    `base_url` through, the loopback cases' own, since those reach the real client on purpose."""

    def _refuse(since, **kwargs):
        pytest.fail(f"a test reached the production venue read (since {since.isoformat()}) -- pass venue_orders")

    cancel = executor_module.cancel_venue_order

    def _refuse_cancel(venue_order_id, instrument_id, *, base_url=None):
        if base_url is None:
            pytest.fail(f"a test reached the production venue cancel ({venue_order_id}) -- pass venue_cancel")
        return cancel(venue_order_id, instrument_id, base_url=base_url)

    holdings = executor_module.read_venue_holdings

    def _refuse_holdings(*, base_url=None):
        if base_url is None:
            pytest.fail("a test reached the production venue holdings read -- pass venue_holdings")
        return holdings(base_url=base_url)

    book = executor_module.read_venue_book

    def _refuse_book(*, base_url=None):
        if base_url is None:
            pytest.fail("a test reached the production venue book read -- pass venue_holdings")
        return book(base_url=base_url)

    statuses = executor_module.read_instrument_statuses

    def _refuse_statuses(*, base_url=None):
        if base_url is None:
            pytest.fail("a test reached the production instrument status read -- pass instrument_statuses")
        return statuses(base_url=base_url)

    def _refuse_fills(since, **kwargs):
        pytest.fail(f"a test reached the production venue fills read (since {since.isoformat()}) -- pass venue_fills")

    def _refuse_positions(**kwargs):
        pytest.fail("a test reached the production venue positions read -- pass venue_positions")

    monkeypatch.setattr(executor_module, "read_venue_orders", _refuse)
    monkeypatch.setattr(executor_module, "cancel_venue_order", _refuse_cancel)
    monkeypatch.setattr(executor_module, "read_venue_holdings", _refuse_holdings)
    monkeypatch.setattr(executor_module, "read_venue_book", _refuse_book)
    monkeypatch.setattr(executor_module, "read_instrument_statuses", _refuse_statuses)
    # `raising=False`: the two reads land with their source fence, and the cases fail on their own terms before it.
    monkeypatch.setattr(executor_module, "read_venue_fills", _refuse_fills, raising=False)
    monkeypatch.setattr(executor_module, "read_venue_positions", _refuse_positions, raising=False)


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
    """A REAL schema-2 `venue-<HH>.json` through `write_venue_record`, the shape the engine writes: the
    record whose balances, the Cache's stored account, the sell check never takes for the venue's."""
    state = VenueState(snapshot_at=when, instruments={}, positions=positions or {}, balances=balances)
    return write_venue_record(
        tmp_path / "journal",
        _boundary(when),
        state=state,
        concordance=ConcordanceVerdict(ok=True, failures=()),
        code_version="test",
    )


def _open_order(client_order_id, *, is_reduce_only=False, filled_qty=0.0, venue_order_id=None):
    """A resting order as reconciliation adopts it. `is_reduce_only` is here because the real adopted
    report carries it and the startup pass must be seen NOT to consult it; `filled_qty` and `status`
    are what `_reconcile_adopted_row` reads instead. On the pinned wheel a reconciled order's
    `client_order_id` IS its txid, since the adapter's reports carry none -- pass the txid as both."""
    return SimpleNamespace(
        client_order_id=client_order_id,
        venue_order_id=None if venue_order_id is None else VenueOrderId(venue_order_id),
        is_reduce_only=is_reduce_only,
        filled_qty=filled_qty,
        is_open=True,
        status=OrderStatus.ACCEPTED,
    )


def _report(txid, status, *, filled_qty="0", quantity="0.001"):
    """A REAL `OrderStatusReport` in the shape the adapter builds from Kraken's order rows -- which
    carries no client order id, ever: the txid is the only name the venue's answer has."""
    return OrderStatusReport(
        account_id=AccountId("KRAKEN-001"),
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]),
        venue_order_id=VenueOrderId(txid),
        order_side=OrderSide.SELL,
        order_type=OrderType.LIMIT,
        time_in_force=TimeInForce.GTC,
        order_status=status,
        quantity=Quantity.from_str(quantity),
        filled_qty=Quantity.from_str(filled_qty),
        ts_accepted=0,
        ts_last=0,
        ts_init=0,
        client_order_id=None,
    )


class _VenueOrders:
    """The executor's `venue_orders` reader: answers `reports`, or raises `raises`, and records the
    `since` of every call -- the startup pass reads once, and the re-read pass once more per arm
    over the rows it minted terminal; any other second call is a finding."""

    def __init__(self, *reports, raises=None):
        self.reports = list(reports)
        self.calls: list[datetime] = []
        self._raises = raises

    def __call__(self, since):
        self.calls.append(since)
        if self._raises is not None:
            raise self._raises
        return list(self.reports)


def _fill_report(txid, qty, *, trade_id="T-h1"):
    """A REAL `FillReport` in the shape the adapter builds from Kraken's trade history: the fill named by
    the order's txid and its own trade id, no client order id."""
    return FillReport(
        account_id=AccountId("KRAKEN-001"),
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]),
        venue_order_id=VenueOrderId(txid),
        trade_id=TradeId(trade_id),
        order_side=OrderSide.SELL,
        last_qty=Quantity.from_str(qty),
        last_px=Price.from_str("30000.0"),
        commission=Money(0.08, Currency.from_str("EUR")),
        liquidity_side=LiquiditySide.MAKER,
        ts_event=0,
        ts_init=0,
    )


class _VenueFills:
    """The executor's `venue_fills` reader: answers `reports`, or raises `raises`, and records the `since`
    of every call."""

    def __init__(self, *reports, raises=None):
        self.reports = list(reports)
        self.calls: list[datetime] = []
        self._raises = raises

    def __call__(self, since):
        self.calls.append(since)
        if self._raises is not None:
            raise self._raises
        return list(self.reports)


class _VenueCancel:
    """The executor's `venue_cancel`: records each `(venue_order_id, instrument_id)` it is asked to
    cancel, and raises `raises` instead when set -- the venue's refusal, or the cut not over."""

    def __init__(self, *, raises=None):
        self.calls: list[tuple[str, str]] = []
        self._raises = raises

    def __call__(self, venue_order_id, instrument_id):
        self.calls.append((venue_order_id, instrument_id))
        if self._raises is not None:
            raise self._raises


def _cancel_venue_order(*args, **kwargs):
    """`cancel_venue_order` through the module's attribute at the call, the one the autouse refusal
    wraps: a loopback `base_url` passes that wrap, so these cases prove the wrap lets one through."""
    return executor_module.cancel_venue_order(*args, **kwargs)


class _VenueHoldings:
    """The executor's `venue_holdings` reader: answers a book of `held`, which a test moves between two
    passes as the account moves, and of the EUR and earn figures it is handed, or raises `raises`
    instead, and counts its calls. A stub carries no margin, so its spot `balances` are its `held` per
    base."""

    def __init__(self, held=None, *, raises=None, eur_total=0.0, eur_free=0.0, earn=None):
        self.held = {} if held is None else dict(held)
        self.eur_total = eur_total
        self.eur_free = eur_free
        self.earn = {} if earn is None else dict(earn)
        self.calls = 0
        self._raises = raises

    def __call__(self):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return executor_module.VenueBook(
            held=dict(self.held),
            balances={symbol.split("/")[0]: qty for symbol, qty in self.held.items() if symbol.endswith("/EUR")},
            eur_total=self.eur_total,
            eur_free=self.eur_free,
            earn=dict(self.earn),
            read_at=NOW,
        )


class _VenuePositions:
    """The executor's `venue_positions` reader: answers `held`, the venue's margin positions by symbol,
    or raises `raises`, and counts its calls."""

    def __init__(self, held=None, *, raises=None):
        self.held = {} if held is None else dict(held)
        self.calls = 0
        self._raises = raises

    def __call__(self):
        self.calls += 1
        if self._raises is not None:
            raise self._raises
        return dict(self.held)


def _read_venue_holdings(**kwargs):
    """`read_venue_holdings` through the module's attribute at the call, the one the autouse refusal
    wraps, as `_cancel_venue_order` is."""
    return executor_module.read_venue_holdings(**kwargs)


def _closed_order(client_order_id, status, *, filled_qty=0.0, venue_order_id=None):
    """The order reconciliation leaves behind for one that reached a terminal state while this
    process was down. It is absent from `orders_open` entirely, which is exactly what made it
    invisible to the pass before the wide read."""
    return SimpleNamespace(
        client_order_id=client_order_id,
        venue_order_id=None if venue_order_id is None else VenueOrderId(venue_order_id),
        is_reduce_only=False,
        filled_qty=filled_qty,
        is_open=False,
        status=status,
    )


def _submitted_row(
    tmp_path: Path,
    client_order_id: str,
    *,
    reduce_only: bool,
    when: datetime = NOW,
    index: int = 0,
    venue_order_id: str | None = None,
    qty: float | None = 0.001,
    plan_id: str = "p-before-the-restart",
    symbol: str = "BTC/EUR",
    side: str = "sell",
) -> dict:
    """A write-ahead row a previous process left behind, through the real `append_submitted_row` --
    `state` is one of `_OPEN_ORDER_STATES`, so the row is in the re-attach set. With `venue_order_id`
    it carries the acceptance record `_on_order_event` writes; without one it is a row written before
    that record existed, or one whose order never got an acceptance."""
    row = {
        "plan_id": plan_id,
        "intent_index": index,
        "client_order_id": client_order_id,
        "intent": {"symbol": symbol, "side": side, "action": "close", "mode": "execute", "notional_eur": 30.0},
        "order": {
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": 30000.0,
            "notional": 30.0,
            "time_in_force": "GTC",
            "post_only": True,
            "leverage": 2,
            "reduce_only": reduce_only,
        },
        "state": "accepted",
        "filled_qty": 0.0,
        "events": (
            [] if venue_order_id is None else [{"type": "OrderAccepted", "at": when.isoformat(), "venue_order_id": venue_order_id}]
        ),
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


def _venue_order_id(client_order_id) -> VenueOrderId:
    """One venue order id per order, as the venue assigns them. A single shared id would make two
    different orders' events look like one order's, which the executor's venue-id lookup would then
    match -- the owner's hand settle included -- on a coincidence the venue never produces."""
    return VenueOrderId(f"V-{client_order_id}")


# What each event kind carries beyond the identity fields every one of them has. These are what the
# LIBRARY requires, not what a test happens to read: a real event refuses a missing field, so a
# constructor that grows one fails here loudly instead of leaving a fabricated shape behind. The
# kinds carrying a venue order id get the per-order one `_event` derives.
_EVENT_DEFAULTS = {
    OrderAccepted: {"account_id": _ACCOUNT_ID, "reconciliation": False},
    OrderCanceled: {"reconciliation": False},
    OrderExpired: {"reconciliation": False},
    OrderPendingCancel: {"account_id": _ACCOUNT_ID, "reconciliation": False},
    OrderRejected: {"account_id": _ACCOUNT_ID, "reason": "the venue said no", "reconciliation": False},
    OrderCancelRejected: {"reason": "the venue said no", "reconciliation": False},
    OrderFilled: {
        "account_id": _ACCOUNT_ID,
        "order_side": OrderSide.BUY,
        "order_type": OrderType.LIMIT,
        "reconciliation": False,
    },
}
_KINDS_REQUIRING_A_VENUE_ORDER_ID = (OrderAccepted, OrderFilled)


def _event(cls, **overrides):
    """One of the library's own order events, with the identity fields every kind carries baked in.
    The class IS the fixture: the executor dispatches on `type(event).__name__`, so nothing here can
    wear a name the library does not define, nor answer an attribute it does not carry."""
    client_order_id = str(overrides.get("client_order_id", "O-1"))
    kwargs = {
        "trader_id": _TRADER_ID,
        "strategy_id": _STUB_STRATEGY_ID,
        "instrument_id": InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]),
        "event_id": UUID4(),
        "ts_event": 0,
        "ts_init": 0,
        **({"venue_order_id": _venue_order_id(client_order_id)} if cls in _KINDS_REQUIRING_A_VENUE_ORDER_ID else {}),
        **_EVENT_DEFAULTS[cls],
        **overrides,
    }
    kwargs["client_order_id"] = ClientOrderId(client_order_id)
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


def _resting_executor(
    tmp_path, *, intents=None, bid=30000.0, ask=30001.0, client=None, venue_orders=None, venue_cancel=None, venue_holdings=None
):
    """A plan accepted and its first intent resting: exactly one order at the venue. The trailing
    assert is the point -- a helper that quietly submitted nothing would hand every ladder test
    below a green it never earned."""
    clock = _Clock()
    client = client if client is not None else StubClient()
    ex = _executor(
        tmp_path, client=client, clock=clock, venue_orders=venue_orders, venue_cancel=venue_cancel, venue_holdings=venue_holdings
    )
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
        self.gaps = []
        self.equity = []
        self.drawdowns = []
        self.frozen = []
        self.not_drafted = []
        self.verdicts = []

    def set_gap(self, symbol, eur):
        self.gaps.append((symbol, eur))

    def set_equity(self, value):
        self.equity.append(value)

    def set_drawdown(self, bps):
        self.drawdowns.append(bps)

    def set_watchdog_frozen(self, flag):
        self.frozen.append(flag)

    def set_boundary_not_drafted(self, flag):
        self.not_drafted.append(flag)

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


def test_an_idle_tick_reads_no_gate_inside_the_refresh_period_and_one_per_period_past_it(tmp_path):
    """The cheap-lstat claim, bounded: with no plan file there is no gate evaluation and no venue
    read inside the refresh period, then one per period -- the tick a plan runs on evaluates anyway.
    The plan-file half is what stops this passing vacuously against an executor that never
    evaluates anything."""
    gate = CountingGate()
    ex = _executor(tmp_path, gate=gate)

    ex.on_timer(NOW)
    ex.on_timer(NOW + timedelta(seconds=55))
    assert gate.calls == 0
    ex.on_timer(NOW + timedelta(seconds=60))
    ex.on_timer(NOW + timedelta(seconds=65))
    assert gate.calls == 1
    ex.on_timer(NOW + timedelta(seconds=120))
    assert gate.calls == 2

    _drop_plan(tmp_path, _plan_dict(created_at=NOW + timedelta(seconds=120)))
    ex.on_timer(NOW + timedelta(seconds=125))
    assert gate.calls > 2


def test_a_kill_file_removed_on_an_idle_engine_is_republished_within_the_refresh_period(tmp_path):
    """Drill D's shape: the boot publishes the switch as tripped and the file goes with no intent
    live. The idle tick re-evaluates the gate once a minute and the publish hook --
    `_ExecGauges.update` in production -- sees the file gone within it, with `heartbeat` False, so
    the staleness rule's series stays the boundary path's; the refresh journals nothing."""
    published = []
    set_executor_hooks(
        publish_verdict=lambda verdict, *, evaluated_at, heartbeat: published.append((evaluated_at, verdict, heartbeat))
    )
    ex = _executor(tmp_path, gate=_gate(tmp_path, GateLevel.NONE))  # the kill file stands at the boot

    ex.on_timer(NOW)
    _kill_file(tmp_path).unlink()
    ex.on_timer(NOW + timedelta(seconds=5))
    assert published == []
    ex.on_timer(NOW + timedelta(seconds=60))

    assert [(at, v.level, v.inputs["kill_file"], hb) for at, v, hb in published] == [
        (NOW + timedelta(seconds=60), GateLevel.FULL, False, False)
    ]
    assert not (tmp_path / "journal").exists()


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
    would pass the test above. Both the 0.001 qty and the venue's balance are load-bearing -- a larger
    qty is refused by the plan cap and a missing balance by the disposal classification (spec 00090
    D10), either of which greens this test for the wrong reason."""
    client = StubClient()
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_holdings=_VenueHoldings({"BTC/EUR": 0.002})
    )
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


def _raw_plan_text(**fields: str) -> str:
    """One plan document as TEXT, each named field replaced by a raw JSON fragment -- a 5000-digit
    integer is not a value `json.dumps` can be handed."""
    intent = {"symbol": '"BTC/EUR"', "side": '"buy"', "action": '"open"', "mode": '"execute"', "notional_eur": "30.0"}
    intent.update(fields)
    body = ", ".join(f'"{key}": {value}' for key, value in intent.items())
    created = (NOW - timedelta(minutes=5)).isoformat()
    return f'{{"plan_id": "p-1", "created_at": "{created}", "intents": [{{{body}}}]}}'


# Measured against this tree: each fragment drives `parse_plan` past its own ProbePlanError into the
# named builtin -- an unhashable value on a frozenset membership test, an integer too large for
# `float()`, and one longer than the 4300 digits `int()` will convert.
@pytest.mark.parametrize(
    ("field", "exception_class"),
    [
        ({"side": '["buy"]'}, "TypeError"),
        ({"notional_eur": "1" + "0" * 400}, "OverflowError"),
        ({"notional_eur": "1" + "0" * 5000}, "ValueError"),
    ],
    ids=["side-is-a-json-list", "notional-is-a-400-digit-integer", "notional-is-a-5000-digit-integer"],
)
def test_a_plan_whose_parse_raises_past_probeplanerror_is_journaled_by_class_and_deleted(tmp_path, field, exception_class):
    """A malformed document that leaves `parse_plan` as a builtin rather than a ProbePlanError is
    journaled under its class and deleted, so no later tick re-reads it."""
    ex = _executor(tmp_path)
    path = _plan_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_raw_plan_text(**field))

    ex.on_timer(NOW)
    ex.on_timer(NOW)  # the tick that re-reads a file the refusal failed to delete

    assert not path.exists()
    entry = _plan_entry(tmp_path)
    assert entry["plan_id"] == "unparseable" and entry["disposition"] == "refused"
    assert entry["reasons"][0].startswith(f"{exception_class}: ")
    assert len(_record(tmp_path)["plans"]) == 1


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


def test_a_plan_handed_in_memory_runs_through_the_pickups_refusals_and_journals_under_the_boundary_it_is_given(tmp_path):
    ex, client, _ = _idle_executor(tmp_path)
    ex.on_timer(NOW)
    plan = parse_plan(json.dumps(_plan_dict(plan_id="r3-20261109-00")))
    boundary = _boundary(NOW) - timedelta(hours=4)
    assert ex._accept_plan(plan, cycle_ts=boundary, now=NOW) == "accepted"
    assert not exec_record_path(tmp_path / "journal", _boundary(NOW)).exists()
    assert ex._plan is plan and _plan_entry(tmp_path, boundary)["plan_id"] == "r3-20261109-00"
    assert ex._accept_plan(plan, cycle_ts=boundary, now=NOW) == "refused"
    assert _plan_entry(tmp_path, boundary, index=1)["reasons"] == ["plan_id already ledgered"]
    assert not _plan_path(tmp_path).exists()


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
    trade_id="T-1",
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
        trade_id=TradeId(trade_id),
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
                # The event a command emits itself -- `OrderInitialized` at submit, `OrderPendingCancel`
                # at cancel -- is dispatched while this strategy's own command still runs, so `self.cache`
                # raises `Already mutably borrowed` there: the strategy's PyO3 cell is what the command
                # holds, not the Cache (`_pending_cancel_read_at_dispatch` reads it through a handle).
                # Only the venue's own answers are read here.
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


def _pending_cancel_read_at_dispatch(tmp_path) -> dict:
    """Run the adopt pass's cancel through a real engine: an observer strategy holds a resting order
    under its own id, as `node.py`'s external order observer holds an adopted one, and a second
    strategy, the executor's client, cancels it from a tick. The `OrderPendingCancel` that
    `cancel_order` publishes reaches the observer's handler while the client's own PyO3 cell is still
    held by that command -- the strategy's own cell, not the Cache --
    and a REAL engine is the only construction that reaches it. The executor is built inside the
    observer's `on_start`, where the client is not borrowed, as the node's factory builds it.
    Recorded, never asserted here: the library swallows a raising handler."""
    from nautilus_trader.backtest import BacktestEngine, BacktestEngineConfig
    from nautilus_trader.model import AccountType, OmsType, StrategyId, Venue
    from nautilus_trader.trading import Strategy, StrategyConfig

    venue = Venue("KRAKEN")
    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"])
    instrument = _real_instrument("BTC/EUR")
    readings: dict = {}

    def _config(tag):
        return StrategyConfig(strategy_id=StrategyId(f"PROBE-{tag}"), order_id_tag=tag)

    class _Canceller(Strategy):
        def __new__(cls):
            return super().__new__(cls, _config("002"))

        def __init__(self):
            super().__init__(config=_config("002"))
            self.target = None
            self.ticks = 0

        def on_start(self):
            self.subscribe_quotes(instrument_id)

        def on_quote(self, tick):
            self.ticks += 1
            if self.ticks == 3 and self.target is not None:
                self.cancel_order(self.target)

    class _Observer(Strategy):
        def __new__(cls, canceller):
            return super().__new__(cls, _config("001"))

        def __init__(self, canceller):
            super().__init__(config=_config("001"))
            self.canceller = canceller
            self.executor = None

        def on_start(self):
            self.executor = _executor(tmp_path, client=self.canceller)
            self.subscribe_quotes(instrument_id)
            order = self.order_factory.limit(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(0.001),
                price=instrument.make_price(1000.0),  # far below: it rests untouched
            )
            self.submit_order(order)
            self.canceller.target = order.client_order_id

        def on_order_event(self, event):
            if type(event).__name__ != "OrderPendingCancel":
                return
            try:
                self.canceller.cache
                readings["client_cache"] = "readable"
            except RuntimeError as exc:
                readings["client_cache"] = str(exc)
            with _executor_errors(level=logging.WARNING) as records:
                readings["terminal_state"] = self.executor._venue_terminal_state(event)
            readings["warnings"] = [r.getMessage() for r in records]
            readings["status"] = self.cache.order(event.client_order_id).status
            readings["handle_status"] = self.executor._cache.order(event.client_order_id).status

    canceller = _Canceller()
    engine = BacktestEngine(config=BacktestEngineConfig(trader_id=TraderId("PROBE-000")))
    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        base_currency=None,
        starting_balances=[Money(100_000, Currency.from_str("EUR")), Money(10, Currency.from_str("BTC"))],
    )
    engine.add_instrument(instrument)
    engine.add_strategy(_Observer(canceller))
    engine.add_strategy(canceller)
    engine.add_data(
        [
            QuoteTick(
                instrument_id,
                instrument.make_price(bid),
                instrument.make_price(bid + 1.0),
                instrument.make_qty(1.0),
                instrument.make_qty(1.0),
                ts,
                ts,
            )
            for ts, bid in ((1, 30001.0), (2_000_000_000, 29998.0), (3_000_000_000, 29998.0), (4_000_000_000, 29998.0))
        ]
    )
    try:
        engine.run()
    finally:
        engine.dispose()
    return readings


def test_the_pending_cancel_of_an_adopted_order_is_read_through_the_handle_taken_at_construction(tmp_path):
    """The adopt pass's cancel of a matched adopted order dispatches `OrderPendingCancel` inside the
    client's own `cancel_order`, where a read through the client's `cache` raises
    `RuntimeError: Already mutably borrowed`. The borrow is the client's, not the Cache's: the first reading pins
    that the construction reaches it, the second that the Cache is free and a handle not held by the
    command reads PENDING_CANCEL -- the observer's own and the executor's, taken in `on_start` before
    the order existed, alike -- and the third that the executor reads through that handle, answers no
    state, and logs nothing. A wheel that moved the borrow onto the
    Cache turns the second reading red rather than surfacing as a `PanicException` that no
    `except Exception` catches."""
    readings = _pending_cancel_read_at_dispatch(tmp_path)

    assert readings["client_cache"] == "Already mutably borrowed"
    assert (readings["status"], readings["handle_status"]) == (OrderStatus.PENDING_CANCEL, OrderStatus.PENDING_CANCEL)
    assert (readings["terminal_state"], readings["warnings"]) == (None, [])


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


# A Kraken txid in the venue's own shape. After a restart the reconciled order carries it as BOTH its
# client and its venue order id, because the adapter's reports carry no client order id.
_TXID = "OQCLML-BW3P3-BUCMWZ"


def test_the_acceptance_and_each_fill_record_the_venue_order_id_in_the_row(tmp_path):
    """The only link from a ledger row to its order once this process is gone: the next process's
    Cache names the order by its txid, never by the id this row is keyed on."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())
    ex.on_timer(NOW)
    ex.on_quote(_quote())

    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    _deliver_fill(ex, client, "O-1", 0.0004, venue_order_id=VenueOrderId(_TXID))

    events = _record(tmp_path)["submitted"][0]["events"]
    assert [(e.get("type") or e.get("event"), e["venue_order_id"]) for e in events] == [("OrderAccepted", _TXID), ("fill", _TXID)]
    assert events[0] == {"type": "OrderAccepted", "at": NOW.isoformat(), "venue_order_id": _TXID}


def test_a_superseded_orders_late_acceptance_records_its_venue_order_id_too(tmp_path):
    """The detached path writes the same record: an acceptance that lands after its order was
    replaced is still the only place that order's txid reaches the ledger."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    _advance_with_quotes(ex, client, clock, minutes=16, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled("O-1"))
    assert client.last_order_id == "O-2"  # O-1 is superseded by the fallback IOC

    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))

    row = next(r for r in _record(tmp_path)["submitted"] if r["client_order_id"] == "O-1")
    assert row["events"][-1] == {"type": "OrderAccepted", "at": clock.now.isoformat(), "venue_order_id": _TXID}


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
    is left out rather than added to a EUR total. The round trips close after the executor is built:
    what the Cache holds at construction is the baseline the gauge subtracts."""
    client = StubClient()
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, client=client)
    client.cache.close_position("BTC/EUR", Money(-4.5, Currency.from_str("ZEUR")))
    client.cache.close_position("BTC/EUR", Money(1.25, Currency.from_str("EUR")))
    client.cache.close_position("BTC/EUR", Money(9999.0, Currency.from_str("XXBT")))  # never summed into a EUR total
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
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> the reprice waits for a tick
    ex.on_quote(_quote(bid=30.0, ask=30.05))
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

    def _publish(verdict, *, evaluated_at, heartbeat):
        seen.append((verdict.level, evaluated_at, heartbeat))
        raise RuntimeError("gauge registry is gone")

    metrics = RecordingMetrics()
    set_executor_hooks(publish_verdict=_publish, metrics=metrics)
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert len(client.submitted) == 1
    assert seen and all(level == GateLevel.FULL and heartbeat for level, _, heartbeat in seen)  # a plan's evaluations stamp it
    assert metrics.orders == ["submitted"]


# --- the maker-first ladder -----------------------------------------------------------------------


def test_a_venue_cancel_off_the_priced_tick_waits_for_the_next_quote_before_repricing(tmp_path):
    """The stored quote priced the order the venue just cancelled as crossing, so repricing off it
    is the same order again. The resubmission waits for a newer tick and prices off that; both
    rows record the tick that priced them."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))

    ex.on_order_event(_canceled(client.last_order_id))  # unrequested: the venue's post-only cancel

    assert len(client.submitted) == 1, "a second order means it repriced off the tick that priced the first"
    assert ex._active.phase == "awaiting_reprice"
    assert _record(tmp_path)["submitted"][0]["state"] == "venue_canceled"

    ex.on_quote(_quote(bid=29990.0, ask=29991.0))

    assert len(client.submitted) == 2
    second, _ = client.submitted[1]
    assert (second.price, second.time_in_force, second.post_only) == (29990.0, TimeInForce.GTC, True)
    assert ex._active.phase == "resting"
    rows = _record(tmp_path)["submitted"]
    assert [(r["order"]["bid"], r["order"]["ask"], r["order"]["quote_seq"]) for r in rows] == [
        (30000.0, 30001.0, 1),
        (29990.0, 29991.0, 2),
    ]


def test_a_tick_that_landed_before_the_cancel_reprices_on_the_cancel_itself(tmp_path):
    """The other arm of the comparison: a tick newer than the priced one has already arrived, so
    nothing is waited for. A rule that always waited would pass the case above and lose a tick."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_quote(_quote(bid=29990.0, ask=29991.0))

    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 2
    assert client.submitted[1][0].price == 29990.0
    assert ex._active.phase == "resting"


def test_alternating_crossings_place_one_order_per_tick_and_the_sixth_crossing_crosses_through_the_ioc(tmp_path):
    """Both crossing surfaces alternated, each answered by one new tick: one order per tick, five
    reprices, six post-only orders. The sixth crossing spends the maker budget and, in `execute`
    mode, crosses through the bounded IOC at the opposite touch instead of ending `unfilled`; three
    returned remainders end it `unfilled` with the fallback's own reason, nine orders in all."""
    ex, client, clock = _resting_executor(tmp_path)
    for i in range(5):
        if i % 2 == 0:
            ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        else:
            ex.on_order_event(_canceled(client.last_order_id))
        assert len(client.submitted) == i + 1, "the reprice fired before its tick"
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
        assert len(client.submitted) == i + 2
    assert all(order.post_only is True for order, _ in client.submitted)

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 7
    ioc, _ = client.submitted[6]
    assert (ioc.price, ioc.time_in_force, ioc.post_only) == (29997.0, TimeInForce.IOC, False)  # the last tick's ask
    assert ex._active.phase == "ioc"

    for _ in range(3):
        ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 9
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["the bounded fallback did not fill"]


def test_a_rest_hold_ladder_spent_by_rejections_ends_unfilled_and_never_crosses(tmp_path):
    """The rest modes end `unfilled` on the budget, with no IOC, since a mode built never to fill may
    not take."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    for i in range(5):
        ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
    assert len(client.submitted) == 6

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 6
    assert all(order.post_only is True for order, _ in client.submitted)
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["reprice budget exhausted"]


def test_a_kill_file_landing_while_a_reprice_waits_revokes_on_the_tick_with_no_cancel(tmp_path):
    """No order rests while the reprice waits, so the revoke has nothing to cancel and ends the
    intent on the tick itself; the plan halts as every revoke halts it."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and "kill_switch" in intent["reasons"]
    assert _intent_outcome(tmp_path, 1) == "refused"


def test_quote_silence_while_a_reprice_waits_revokes_on_the_tick_with_no_cancel(tmp_path):
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and intent["reasons"] == ["quote_silence"]


def test_the_time_box_elapsing_while_a_reprice_waits_fires_the_ioc_with_no_cancel(tmp_path):
    """The box declares the maker attempt over; with nothing resting there is nothing to cancel,
    so the IOC fires on the tick, at the opposite touch of the stored quote. The box is reached
    inside the quote-silence bound because the last tick landed ten seconds before the box."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=14.75)
    assert clock.now == NOW + timedelta(minutes=14, seconds=50)
    ex.on_order_event(_canceled(client.last_order_id))  # ticks have arrived since the first order: repriced at once
    assert len(client.submitted) == 2
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))  # none since the second: the reprice waits
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == []
    assert len(client.submitted) == 3
    ioc, _ = client.submitted[2]
    assert (ioc.price, ioc.time_in_force, ioc.post_only) == (30001.0, TimeInForce.IOC, False)


def test_the_hold_elapsing_while_a_rest_hold_reprice_waits_ends_it_expired_with_no_cancel(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=10)])
    _advance_with_quotes(ex, client, clock, minutes=9.75)
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert len(client.submitted) == 2
    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=10, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    assert _intent_outcome(tmp_path) == "rest_hold_expired"


def test_a_sell_closes_six_accept_then_cancel_crossings_end_in_an_ioc_at_the_bid(tmp_path):
    """A sell, accepted and then cancelled by the venue as crossing six times: the first five
    crossings are each answered by one tick, so each replacement is priced off a newer ask, and the
    sixth fires the IOC, bounded by the last tick's bid, the opposite touch on this side. A margin
    close, so the IOC also carries the closer's reduce-only flag."""
    client = StubClient(StubCache(positions=_held(**{"BTC/EUR": 0.001})))
    ex, client, clock = _resting_executor(
        tmp_path, client=client, intents=[_intent(side="sell", action="close", notional_eur=90.0, leverage=2)]
    )
    for i in range(5):
        ex.on_order_event(_accepted(client.last_order_id))
        ex.on_order_event(_canceled(client.last_order_id))
        assert len(client.submitted) == i + 1, "the reprice fired before its tick"
        ex.on_quote(_quote(bid=30000.0 + i, ask=30001.0 + i))
    assert [order.price for order, _ in client.submitted] == [30001.0, 30001.0, 30002.0, 30003.0, 30004.0, 30005.0]

    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 7
    ioc, _ = client.submitted[6]
    assert (ioc.price, ioc.time_in_force, ioc.post_only, ioc.reduce_only) == (30004.0, TimeInForce.IOC, False, True)


def test_a_fill_racing_the_venue_cancel_lands_detached_while_the_reprice_waits(tmp_path):
    """`ownTrades` and `openOrders` have no cross-stream ordering, so a fill on the cancelled order can
    land inside the wait. That order is no longer in flight: the fill takes the detached path, which
    appends without a state claim and credits the intent, so the row keeps `venue_canceled` and the
    replacement is sized to the remainder."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"

    _deliver_fill(ex, client, "O-1", 0.1, px=30.0)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("venue_canceled", 0.5)
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    assert client.submitted[1][0].quantity == 0.5


def test_a_replayed_cancel_ack_while_the_reprice_waits_counts_no_crossing(tmp_path):
    """A second `OrderCanceled` for the order the venue already ended is evidence on its row, not a
    crossing: it takes the detached path, and the maker budget is not spent on a replay."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted("O-1"))
    ex.on_order_event(_canceled("O-1"))
    assert (ex._active.phase, ex._active.reprices) == ("awaiting_reprice", 1)

    ex.on_order_event(_canceled("O-1"))

    assert (ex._active.phase, ex._active.reprices, len(client.submitted)) == ("awaiting_reprice", 1, 1)
    assert [e["type"] for e in _record(tmp_path)["submitted"][0]["events"]] == ["OrderAccepted", "OrderCanceled", "OrderCanceled"]


def test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_tick(tmp_path):
    """The cancelled order's late fills reach the target inside the wait, so the tick has nothing left
    to order: the intent ends `filled` with the whole quantity, where sizing would refuse the zero
    remainder as below the minimum and end it `partial` carrying that quantity."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    _deliver_fill(ex, client, "O-1", 0.6, px=30.0)

    ex.on_quote(_quote(bid=30.0, ask=30.05))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == ("filled", 1.0)


def test_a_late_fill_completing_the_intent_while_the_reprice_waits_ends_it_filled_on_the_timer_too(tmp_path):
    """The completing fill can be the last thing the feed delivers for a while: the timer ends the
    intent `filled` on its next tick, where the wait's revoke arms would otherwise end it `revoked`
    on silence or the kill file, its whole quantity in `filled_qty`, and halt the plan."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"
    _deliver_fill(ex, client, "O-1", 0.6, px=30.0)

    clock.now = NOW + timedelta(seconds=31)  # past the silence bound, and no tick since the fill
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == ("filled", 1.0)


def test_a_half_book_tick_while_a_reprice_waits_prices_nothing(tmp_path):
    """A tick carrying one side is not stored, so it is not the newer tick the reprice waits for:
    priced off the stale touch, the resubmission would be the crossing order again."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    ex.on_quote(SimpleNamespace(instrument_id="BTC/EUR.KRAKEN", bid_price=Price(29990.0, 1), ask_price=None))

    assert len(client.submitted) == 1 and ex._active.phase == "awaiting_reprice"
    ex.on_quote(_quote(bid=29990.0, ask=29991.0))
    assert len(client.submitted) == 2 and client.submitted[1][0].price == 29990.0


def test_a_half_book_tick_while_the_order_rests_is_not_the_newer_tick_a_reprice_waits_for(tmp_path):
    """A one-sided tick landing while the order rests advances no count, so the crossing after it
    still waits: counted, it would reprice at once off the touch it crossed on."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_quote(SimpleNamespace(instrument_id="BTC/EUR.KRAKEN", bid_price=Price(29990.0, 1), ask_price=None))

    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 1 and ex._active.phase == "awaiting_reprice"


def test_quote_silence_outranks_the_time_box_while_a_reprice_waits(tmp_path):
    """The checks are `resting`'s, in `resting`'s order: a feed dead for longer than the silence bound
    ends the intent `revoked` before the box can fire an IOC off that stale quote."""
    ex, client, clock = _resting_executor(tmp_path)
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=14.75)
    ex.on_order_event(_canceled(client.last_order_id))  # ticks have arrived since the first order: repriced at once
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=25)  # 35 s after the last tick, and past the box
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "revoked" and intent["reasons"] == ["quote_silence"]


def test_a_rest_cancel_ladder_spent_by_rejections_ends_unfilled_and_never_crosses(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-cancel")])
    for i in range(5):
        ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))
        ex.on_quote(_quote(bid=30000.0 - i, ask=30001.0 - i))
    assert len(client.submitted) == 6

    ex.on_order_event(_rejected(client.last_order_id, "POST_ONLY_REJECTED: would cross", due_post_only=True))

    assert len(client.submitted) == 6 and client.canceled == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "unfilled" and intent["reasons"] == ["reprice budget exhausted"]


@pytest.mark.parametrize("filled_before, outcome", [(0.0, "rest_cancel_ok"), (0.2, "partial")])
def test_the_time_box_elapsing_while_a_rest_cancel_reprice_waits_ends_it_rest_cancel_ok_or_partial_with_no_cancel(
    tmp_path, filled_before, outcome
):
    """A mode built never to fill takes no IOC when its box elapses inside the wait; a fill that
    landed ahead of the acceptance makes the end `partial`, since the name alone says nothing filled."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05, intents=[_intent(mode="rest-cancel")])
    if filled_before:
        _deliver_fill(ex, client, "O-1", filled_before, px=30.0)  # ahead of the acceptance: the streams' own ordering
    _advance_with_quotes(ex, client, clock, minutes=14.75, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel; ticks have arrived since: repriced at once
    assert len(client.submitted) == 2
    ex.on_order_event(_canceled(client.last_order_id))  # none since the second: the reprice waits
    assert ex._active.phase == "awaiting_reprice"

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert client.canceled == [] and len(client.submitted) == 2
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == (outcome, filled_before)


def test_a_raise_inside_a_waiting_reprice_journals_the_fills_that_already_happened(tmp_path):
    """A raise inside the resubmission refuses the intent on the tick, and the refusal carries
    `filled`, so a real partial is not erased from the summary."""
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    assert ex._active.phase == "awaiting_reprice"
    client.cache._raises = True  # the Cache's instrument read raises on the tick

    ex.on_quote(_quote(bid=30.0, ask=30.05))

    assert len(client.submitted) == 1
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"], intent["filled_qty"]) == ("refused", ["quote handling failed"], 0.4)


def test_a_raise_inside_a_waiting_reprices_time_box_ioc_refuses_the_intent_with_its_fills(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    _advance_with_quotes(ex, client, clock, minutes=14.75, bid=30.0, ask=30.05)
    ex.on_order_event(_canceled("O-1"))  # ticks have arrived since the first order: repriced at once
    ex.on_order_event(_accepted(client.last_order_id))
    ex.on_order_event(_canceled(client.last_order_id))  # none since the second: the reprice waits
    assert ex._active.phase == "awaiting_reprice"
    client.cache._raises = True  # the Cache's instrument read raises inside the IOC's placement

    clock.now = NOW + timedelta(minutes=15, seconds=5)
    ex.on_timer(clock.now)

    assert len(client.submitted) == 2
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"], intent["filled_qty"]) == ("refused", ["time-box handling failed"], 0.4)


_CROSSING = "POST_ONLY_REJECTED: would cross"


def _crossed_with_a_newer_tick(ex, client, clock):
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    return _canceled(client.last_order_id)


def _crossed_for_the_sixth_time(ex, client, clock):
    ex.on_order_event(_canceled(client.last_order_id))
    for _ in range(4):
        ex.on_quote(_quote(bid=30.0, ask=30.05))
        ex.on_order_event(_rejected(client.last_order_id, _CROSSING, due_post_only=True))
    ex.on_quote(_quote(bid=30.0, ask=30.05))
    assert len(client.submitted) == 6
    return _rejected(client.last_order_id, _CROSSING, due_post_only=True)


def _ioc_remainder_returned(ex, client, clock):
    ex.on_order_event(_crossed_for_the_sixth_time(ex, client, clock))
    assert ex._active.phase == "ioc"
    return _canceled(client.last_order_id)


def _time_box_cancel_answered(ex, client, clock):
    _advance_with_quotes(ex, client, clock, minutes=15.5, bid=30.0, ask=30.05)
    assert client.canceled
    return _canceled(client.last_order_id)


@pytest.mark.parametrize(
    "arrange",
    [_crossed_with_a_newer_tick, _crossed_for_the_sixth_time, _ioc_remainder_returned, _time_box_cancel_answered],
    ids=["reprice_at_once", "sixth_crossing_ioc", "next_ioc", "time_box_ioc"],
)
def test_a_raise_inside_a_resubmission_the_order_event_dispatch_runs_refuses_the_intent_with_its_fills(tmp_path, arrange):
    ex, client, clock = _resting_executor(
        tmp_path, bid=30.0, ask=30.05, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]
    )
    ex.on_order_event(_accepted(client.last_order_id))
    _deliver_fill(ex, client, client.last_order_id, 0.4, px=30.0)
    event = arrange(ex, client, clock)
    placed = len(client.submitted)
    client.cache._raises = True  # the Cache's instrument read raises inside the resubmission's placement

    with _executor_errors() as records:
        ex.on_order_event(event)

    assert len(client.submitted) == placed
    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["reasons"], intent["filled_qty"]) == ("refused", ["order-event handling failed"], 0.4)
    assert ex._plan is not None and ex._index == 1  # not dropped: the next tick starts intent 1
    assert [r.getMessage() for r in records] == ["executor order-event resubmission raised -- refusing the intent"]


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
    """Drill E's subject: the LEVEL bound in `_poll`, which is the arm a kill file reaches while an
    order rests. Its two siblings there, quote silence and the box, have their own tests."""
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
    ex.on_quote(_quote())  # the tick the reprice waits for, newer than the one that priced the rejected order
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


def test_a_kill_file_landing_during_the_time_box_cancel_refuses_the_fallback_ioc(tmp_path):
    """The fallback IOC goes through `_submit`, which evaluates the gate first: the kill file lands
    after the time-box cancel is out and before the venue answers it, the IOC is refused with nothing
    submitted, and the next intent is refused at its start by the same gate."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)])
    ex.on_order_event(_accepted(client.last_order_id))
    _advance_with_quotes(ex, client, clock, minutes=16)
    assert client.canceled  # the time-box cancel is out and the fallback is armed
    assert len(client.submitted) == 1

    (exec_dir(tmp_path) / KILL_FILE).touch()
    ex.on_order_event(_canceled(client.last_order_id))

    assert len(client.submitted) == 1, "the fallback IOC reached the client past a tripped gate"
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert "kill_switch" in intent["reasons"]
    ex.on_timer(clock.now + timedelta(seconds=10))
    assert _intent_outcome(tmp_path, 1) == "refused"  # intent 1 starts on this tick and meets the same gate
    assert "kill_switch" in _intent_entry(tmp_path, 1)["reasons"]  # the gate, not a halt or a venue-truth refusal
    assert client.subscribed == ["BTC/EUR.KRAKEN"]  # so it never subscribed


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
        "flagged": _record(tmp_path)["submitted"][0]["events"][-1].get("reconciliation"),
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

    assert venue == {"submissions": 2, "row_state": "canceled", "intent": "pending", "next_intent": "pending", "flagged": None}
    # No IOC, the row stays OPEN for re-attach because the order may still rest, and the ETH intent
    # never runs: the venue state that authorized it is no longer known. The row's event carries the flag.
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused", "flagged": True}


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
    assert venue == {"submissions": 1, "row_state": "rejected", "intent": "rejected", "next_intent": "pending", "flagged": None}
    assert minted == {"submissions": 1, "row_state": "ambiguous", "intent": "ambiguous", "next_intent": "refused", "flagged": True}


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
    ex.on_quote(_quote(bid=30.0, ask=30.05))  # the tick the reprice waits for

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
    """Cumulation, not the single-intent breach: 60.00 EUR declared plus 0.0015 ETH at the 30001 ask
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


def test_the_venues_balance_refutes_a_disposal_larger_than_itself(tmp_path):
    """The refutation half of D10: a POSITIVE balance smaller than the signed qty is the venue's
    balance contradicting the plan, and a contradiction refuses."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, venue_holdings=_VenueHoldings({"BTC/EUR": 0.0005}))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=None, qty=0.0006)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    intent = _intent_entry(tmp_path, 0)
    assert intent["outcome"] == "refused"
    assert intent["reasons"] == ["the venue's balance refutes the signed qty"]


def test_a_disposal_within_the_venues_balance_submits_a_plain_spot_sell(tmp_path):
    """No venue-side `reduce_only` on a spot order -- Kraken's flag is a margin concept, so the
    executor-side quantity bound plus the venue's insufficient-funds rejection is the whole guard."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, venue_holdings=_VenueHoldings({"BTC/EUR": 0.0005}))
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


@pytest.mark.parametrize(
    "qty, held, submits",
    [
        (0.0004, {"BTC/EUR": 0.0005}, True),
        (0.0006, {"BTC/EUR": 0.0005}, False),  # the full qty <= balance bound, not merely refutation
        (0.0004, {}, False),  # absent reads 0.0
    ],
)
def test_the_post_restart_disposal_takes_the_full_balance_bound(tmp_path, qty, held, submits):
    """At `reduce_only`, the restart hold's level, the whole `qty <= balance` bound applies over the
    venue's balance, in both directions."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_holdings=_VenueHoldings(held))
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
    assert intent["reasons"] == ["the venue's balance does not cover the signed qty"]


def test_a_spot_close_that_is_not_a_sell_is_refused(tmp_path):
    """A `close` that BUYS spot grows exposure whatever it is labelled -- the classification judges
    the order, never the label."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, venue_holdings=_VenueHoldings({"BTC/EUR": 0.002}))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="buy", action="close", notional_eur=None, qty=0.0004)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    assert _intent_entry(tmp_path, 0)["reasons"] == ["a spot close must be a sell"]


def test_a_spot_close_without_an_explicit_qty_is_refused(tmp_path):
    """Neither closer shape: no leverage to size against a position, no `qty` for the venue's balance to
    bound. Nothing here is a reducer this process can vouch for, so it refuses."""
    client = StubClient()
    ex = _executor(tmp_path, client=client)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(side="sell", action="close", notional_eur=30.0)]))

    ex.on_timer(NOW)
    ex.on_quote(_quote())

    assert client.submitted == [] and client.subscribed == []
    assert _intent_entry(tmp_path, 0)["reasons"] == ["a spot close needs an explicit qty"]


def test_a_dust_balance_under_ordermin_reads_as_absent_in_both_arms():
    close = ProbeIntent(symbol="BTC/EUR", side="sell", action="close", mode="execute", notional_eur=None, qty=0.001, leverage=None)
    full = executor_module._classify_spot_close(close, balances={"BTC": 1e-08}, level=GateLevel.FULL, ordermin=5e-05)
    held = executor_module._classify_spot_close(close, balances={"BTC": 1e-08}, level=GateLevel.REDUCE_ONLY, ordermin=5e-05)
    assert full.refusal is None and full.qty == 0.001
    assert held.refusal == "the venue's balance does not cover the signed qty"


def test_the_disposal_is_bounded_by_the_venues_book_and_not_by_the_record_it_refused_under(tmp_path):
    _venue_record(tmp_path, balances={"XXBT": 0.0005})
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(symbol="BTC/EUR", side="sell", action="close", notional_eur=None, qty=0.001)],
        client=StubClient(StubCache(balances={"ZEUR": 1000.0, "XXBT": 0.0005})),  # the stored account, the record's source
        venue_holdings=_VenueHoldings({"BTC/EUR": 0.001}),
    )
    assert len(client.submitted) == 1 and client.submitted[0][0].order_side == OrderSide.SELL


def test_a_process_that_has_read_no_book_refuses_the_disposal(tmp_path):
    client = StubClient()
    ex = _executor(tmp_path, client=client, venue_holdings=_VenueHoldings(raises=RuntimeError("down")))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(symbol="BTC/EUR", side="sell", action="close", notional_eur=None, qty=0.001)]))
    ex.on_timer(NOW)
    ex.on_quote(_quote())
    assert client.submitted == [] and _intent_outcome(tmp_path) == "refused"
    assert "have not been read in this process" in _intent_entry(tmp_path, 0)["reasons"][0]


def test_a_process_that_has_read_no_book_refuses_an_opening_plan_with_the_same_sentence(tmp_path):
    client = StubClient()
    ex = _executor(
        tmp_path, client=client, config=_cache_config(tmp_path), venue_holdings=_VenueHoldings(raises=RuntimeError("down"))
    )
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(symbol="BTC/EUR", side="buy", action="open", notional_eur=20.0)]))
    ex.on_timer(NOW)
    assert client.submitted == [] and "have not been read in this process" in _plan_entry(tmp_path)["reasons"][0]


# --- D10: the startup ledger-attach/cancel pass ---------------------------------------------------


def test_the_startup_pass_keeps_only_the_ledger_attached_reduce_only_order(tmp_path):
    """The whole matrix in one construction. `O-flagged` is the one that matters most: its report
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


def test_no_plan_is_picked_up_before_the_startup_pass_has_run(tmp_path):
    """Until the pass has run, no row is compared with the venue and its one venue read has not gone
    out -- a read that must reach the venue before any order of this process does. A plan waiting on
    disk is picked up on the tick the pass completes, not before."""
    client = StubClient(_FlakyOrdersCache())
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.FULL))
    plan_path = _drop_plan(tmp_path, _plan_dict())

    ex.on_timer(NOW)
    assert plan_path.exists() and not exec_record_path(tmp_path / "journal", _boundary(NOW)).exists()

    ex.on_timer(NOW + timedelta(seconds=5))
    assert not plan_path.exists() and _plan_entry(tmp_path)["disposition"] == "accepted"


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


@pytest.mark.parametrize(
    "armed_in_config, control_files, reasons",
    [
        # The engine's resting state: disarmed, with the hold every start writes. No kill file exists.
        (False, (RESTART_HOLD_FILE,), "config_not_armed, arm_file_absent, restart_hold"),
        (True, (ARM_FILE, KILL_FILE), "kill_switch"),
    ],
)
def test_the_startup_cancel_at_level_none_names_the_gates_own_reasons(tmp_path, armed_in_config, control_files, reasons):
    """The gate reads `none` for a disarmed engine as surely as for a latched kill file, and the
    operator reading this line during a restart acts on its cause -- a kill switch named over a
    disarmed engine sends them looking for a file and a trip that do not exist."""
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    for name in control_files:
        (d / name).touch()
    gate = ExecutionGate(armed_in_config=armed_in_config, state_dir=tmp_path, venue_reader=_venue_reader())
    assert gate.evaluate(NOW).level == GateLevel.NONE
    client = StubClient(StubCache(open_orders=[_open_order("O-orphan")]))
    ex = _executor(tmp_path, client=client, gate=gate)

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == ["O-orphan"]
    assert [r.getMessage() for r in records] == [f"canceling adopted resting order O-orphan -- the gate reads none ({reasons})"]


# --- the external topic: an adopted order's own events (spec 00098) ------------------------------


@contextmanager
def _executor_errors(level=logging.ERROR):
    """The executor logger's own records at `level` and above. Not `caplog`, blind here for the
    reasons `_the_tick_backstop_never_fires` gives."""
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


def _resting_limit_order(client_order_id, *, quantity="1.0", venue_order_id=None, strategy_id=_STUB_STRATEGY_ID):
    """A REAL `LimitOrder` resting at the venue, driven to ACCEPTED by the library's own events.

    Real because the terminal-state write reads `cache.order(...).status`, and only the library's own
    state machine can say what an event does to that status -- including for the stale and replayed
    acks it REFUSES, which is where reading the order rather than the event's name earns its place.
    `_resting_limit_order(_TXID, venue_order_id=_TXID)` is the shape a restart's reconciliation
    leaves on the pinned wheel: the order named by its txid on both ids. Under the stub's own
    `strategy_id` with the id this engine minted, it is the shape the cache restores."""
    head = (_TRADER_ID, strategy_id, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id))
    order = LimitOrder(
        *head, OrderSide.BUY, Quantity.from_str(quantity), Price.from_str("30000.0"), TimeInForce.GTC,
        False, False, False, UUID4(), 0,
    )  # fmt: skip
    order.apply(OrderSubmitted(*head, _ACCOUNT_ID, UUID4(), 0, 0))
    venue = _venue_order_id(client_order_id) if venue_order_id is None else VenueOrderId(venue_order_id)
    order.apply(OrderAccepted(*head, venue, _ACCOUNT_ID, UUID4(), 0, 0, False))
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


def test_an_external_event_the_ledger_does_not_vouch_for_reaches_no_trip_row_or_cancel(tmp_path):
    """The operator's hand settle, and the whole reason this subscription is safe to have: an event
    on the external topic naming an order no ledgered row vouches for is COUNTED and reaches no trip,
    no row write anywhere, no cancel -- while the engine is armed, a fill arms the re-read pass alone.
    The unknown-order trip stays scoped to this strategy's own topic, where every order arriving IS
    one this engine submitted."""
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
    arrive. The row is not special-cased -- the venue's order is still ACCEPTED after a refused
    cancel and no OPEN status is in the terminal map -- and the CRITICAL the refusal logs here too,
    unasserted, is pinned by the cancelled opener's case below."""
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
        (True, "ambiguous", ["O-opener"]),
    ],
)
def test_a_terminal_the_engine_minted_marks_the_adopted_row_ambiguous_where_the_venues_ack_closes_it(
    tmp_path, reconciled, expected_state, expected_open
):
    """A terminal the execution engine minted for itself is not a venue outcome, so the row takes the
    active path's word for an outcome the venue never established, `ambiguous`, and no venue claim.

    The construction is the production one: the startup pass cancels an adopted opener, the venue
    never answers on the stream, and past the in-flight retry budget the
    engine publishes the `OrderCanceled` itself. It is applied to the order before dispatch, so the
    Cache says CANCELED either way and only the flag can tell the two apart. `canceled` on it would
    put a venue claim in the ledger nobody made; `accepted` would claim the order still rests where
    the venue may have cancelled it. `ambiguous` keeps the row open, so the re-read pass settles it
    from the venue's own report on the next tick with nothing in flight, and a startup inside the
    re-attach window where the pass could not read. The line is a WARNING, the mint being the expected
    end of an adopt-pass cancel on this wheel, and the row's event records the flag so the ledger
    can tell the mint once the row is settled.

    Read as a pair: the false arm is the true positive, and the `open_submitted_rows` reading IS what
    the re-read pass and a startup inside the re-attach window read the row from."""
    ex, client, earlier = _adopted_executor(tmp_path, client_order_id="O-opener", reduce_only=False)
    assert [str(cid) for cid in client.canceled] == ["O-opener"]  # this process asked; the venue is what did not answer
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id="O-opener", reconciliation=reconciled))

    assert client.cache.order(ClientOrderId("O-opener")).status == OrderStatus.CANCELED  # both arms, so the status cannot decide
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == expected_state
    assert row["events"] == [  # evidence either way, the flag recorded where the engine minted it
        {"type": "OrderCanceled", "at": NOW.isoformat(), **({"reconciliation": True} if reconciled else {})}
    ]
    assert ex._attached["O-opener"][1]["state"] == expected_state  # the mirror stays with the row
    assert [r["client_order_id"] for _, r in open_submitted_rows(tmp_path / "journal", NOW)] == expected_open
    assert [(r.levelno, r.getMessage()) for r in records] == (
        [
            (
                logging.WARNING,
                "OrderCanceled for O-opener was reconciled, not received -- no venue answer reached this engine; its row "
                "reads ambiguous until the re-read pass settles it from the venue's own report",
            )
        ]
        if reconciled
        else []
    )
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


def _pending_plan_entry(tmp_path, when, *, plan_id="p-before-the-restart", n_intents=2, settled=None):
    """The plan entry a previous process journaled at pickup and never finished: every intent still
    `pending`, under the same boundary `_submitted_row` files that plan's rows; `settled` is one
    more intent, already terminal, that the sweep must leave as it is."""
    intents = [{"index": i, "intent": {}, "outcome": "pending", "reasons": [], "filled_qty": 0.0} for i in range(n_intents)]
    append_plan_entry(
        tmp_path / "journal",
        _boundary(when),
        {
            "plan_id": plan_id,
            "received_at": when.isoformat(),
            "disposition": "accepted",
            "reasons": [],
            "plan": {},
            "intents": intents + ([settled] if settled is not None else []),
        },
        verdict=GateVerdict(level=GateLevel.FULL, reasons=(), inputs={}),
        evaluated_at=when,
    )


def test_the_startup_pass_settles_the_intent_of_the_opener_it_cancels_and_the_ones_that_never_ran(tmp_path):
    """A rest-hold opener cancelled by the pass leaves its intent `pending` for good: the hold's timer
    died with the old process and nothing else writes an intent after a restart. The pass writes it
    `revoked` at its own boundary, and the plan's later intent, which no process will ever start,
    `refused` as not run."""
    earlier = NOW - timedelta(hours=4)
    done = {"index": 2, "intent": {}, "outcome": "filled", "reasons": [], "filled_qty": 0.001}
    _pending_plan_entry(tmp_path, earlier, settled=done)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_entry(tmp_path, 2, earlier) == done  # an intent already terminal is not the sweep's to rewrite
    first = _intent_entry(tmp_path, 0, earlier)
    assert (first["outcome"], first["reasons"], first["filled_qty"]) == (
        "revoked",
        ["the engine restarted while the intent was in flight"],
        0.0,
    )
    second = _intent_entry(tmp_path, 1, earlier)
    assert (second["outcome"], second["reasons"]) == ("refused", ["not run -- the engine restarted before it ran"])
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "accepted"  # the row still waits on the venue's answer


def test_the_startup_pass_leaves_the_intent_of_a_reducer_it_keeps_pending(tmp_path):
    """A kept reducer's order is live and its row is the record of it; the intent stays `pending`
    beside that open row, while the plan's later intent is still refused as never run."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert client.canceled == []
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"
    assert _intent_outcome(tmp_path, 1, earlier) == "refused"


def test_a_restart_with_nothing_resting_still_settles_the_windows_pending_intents(tmp_path):
    """The intent that was awaiting its first quote when the process stopped has no row at all, so no
    order-side event will ever reach it; the pass's early return on an empty Cache must not skip it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["reasons"]) == ("refused", ["not run -- the engine restarted before it ran"])


@pytest.mark.parametrize(
    "status, venue_filled, outcome, filled_qty",
    [
        (OrderStatus.CANCELED, "0", "revoked", 0.0),
        (OrderStatus.CANCELED, "0.0004", "revoked", 0.0004),
        (OrderStatus.FILLED, "0.001", "filled", 0.001),
    ],
)
def test_an_intent_whose_order_closed_while_down_is_settled_from_its_rows(tmp_path, status, venue_filled, outcome, filled_qty):
    """The row sweep reads the venue's own figure into the row first; the intent is then written
    from the rows -- `filled` once they carry the first order's quantity, `revoked` otherwise, a
    partial's fills carried either way."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, status, filled_qty=venue_filled))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == (outcome, filled_qty)


def test_a_failed_venue_read_leaves_the_pending_intents_as_they_are(tmp_path):
    """With the venue unread the rows' fills were never compared -- a finished row's for a withdrawal,
    an open row's against its venue figure -- so an intent written from them would carry a figure
    nobody checked; the pending intents wait for the restart that reads again. The row here is
    already closed on its fill, the one shape the open-row rule alone would settle."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-opener", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(raises=RuntimeError("the venue read failed"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_failed_ledger_read_leaves_the_pending_intents_as_they_are(tmp_path, monkeypatch):
    """The pass's row read raised, so it holds no rows at all; run over none, the sweep would write
    every intent `refused` as never run, an intent that filled included. The rows were never read,
    the venue-read skip's own reason, and the pending intents wait for the restart that reads again."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)

    def _unreadable(journal_dir, now):
        raise OSError("the exec ledger could not be read")

    monkeypatch.setattr(executor_module, "open_submitted_rows", _unreadable)
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_an_intents_two_orders_closed_while_down_are_summed_against_the_first_orders_quantity(tmp_path):
    """A first order of 0.001 filled 0.0004 and was cancelled as crossing; its reprice, a remainder of
    0.0006, filled 0.0003 and closed while the engine was down. The target is the first order's
    quantity, the largest among the intent's rows, and 0.0007 against it is `revoked` with the sum
    carried -- read off the remainder row it would be `filled`."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-first", reduce_only=False, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-remainder", reduce_only=False, when=earlier, venue_order_id="OREMDR-AAAAA-BBBBBB", qty=0.0006)
    venue = _VenueOrders(
        _report(_TXID, OrderStatus.CANCELED, filled_qty="0.0004"),
        _report("OREMDR-AAAAA-BBBBBB", OrderStatus.CANCELED, filled_qty="0.0003", quantity="0.0006"),
    )
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("revoked", pytest.approx(0.0007))


def test_a_row_with_no_readable_quantity_settles_its_intent_revoked_never_filled(tmp_path):
    """A row whose `order.qty` is unreadable reads 0.0, and nothing filled against 0.0 must not read
    as complete: `revoked`, since such a row is not one to reason from."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID, qty=None)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_an_order_resting_at_kraken_outside_the_cache_leaves_its_intent_pending(tmp_path):
    """The venue read returns the order still open and the Cache does not hold it: the pass can send
    it no cancel, so the order is live and its intent is not the sweep's to end."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "accepted"
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_cancelled_row_beside_an_order_resting_outside_the_cache_leaves_its_intent_pending(tmp_path):
    """The rule is per row: the pass's cancel of one of an intent's orders does not end the intent
    while another of its rows rests where no cancel of this pass reached."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-outside", reduce_only=False, when=earlier, venue_order_id="OOUTSD-AAAAA-BBBBBB")
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report("OOUTSD-AAAAA-BBBBBB", OrderStatus.ACCEPTED))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID] and venue.calls != []
    assert [row["state"] for row in _record(tmp_path, earlier)["submitted"]] == ["accepted", "accepted"]
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_row_the_venue_read_does_not_return_leaves_its_intent_pending(tmp_path):
    """The row's txid is in neither the Cache nor the venue's read, so the order may rest where no
    cancel of this process reaches it; the row reads `ambiguous` and the intent waits with it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    ex = _executor(
        tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=_VenueOrders()
    )

    ex.on_timer(NOW)

    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_cancel_that_raised_leaves_its_intent_pending(tmp_path):
    """The pass's own cancel raised, so the opener may still rest: an intent is settled once a cancel
    went out, never on the attempt."""

    class _CancelRaises(StubClient):
        def cancel_order(self, client_order_id):
            raise RuntimeError("the cancel could not be sent")

    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = _CancelRaises(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_reducer_cancelled_on_a_latched_kill_has_its_intent_revoked(tmp_path):
    """At level NONE the pass cancels ledgered reducers too, and a cancelled reducer's intent is
    settled like an opener's: keeping is what leaves an intent `pending`, not the row's flag."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.NONE))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_a_flagged_non_terminal_on_an_adopted_row_leaves_its_state_as_it_is(tmp_path):
    """The `reconciliation` flag rides on the library's non-terminals too, `OrderAccepted` among
    them, and only a minted TERMINAL says the venue never answered: a flagged acceptance on a kept
    reducer's row appends as evidence and moves nothing."""
    ex, client, earlier = _adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderAccepted, client_order_id="O-attached", reconciliation=True))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "accepted" and [e["type"] for e in row["events"]] == ["OrderAccepted"]
    assert records == [] and metrics.external == ["matched"]


def test_a_failed_ledger_read_with_an_opener_resting_cancels_it_and_leaves_the_pending_intents_as_they_are(tmp_path, monkeypatch):
    """The restart every drill takes: an opener rests, and the row read raises. The pass cancels the
    opener as unmatched, and the sweep, run over no rows, would write its intent `refused` as never
    run -- it is skipped, and the intent stays `pending`."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)

    def _unreadable(journal_dir, now):
        raise OSError("the exec ledger could not be read")

    monkeypatch.setattr(executor_module, "open_submitted_rows", _unreadable)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_failed_venue_read_with_an_opener_resting_cancels_it_and_leaves_the_pending_intents_as_they_are(tmp_path):
    """The same restart with a second row whose txid the Cache lacks, so the pass reaches the venue,
    and the read raises: the opener is cancelled, and both intents stay `pending` -- the sweep run
    over the rows would write the cancelled opener's `revoked` from fills the venue never vouched
    for."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-gone", reduce_only=False, when=earlier, index=1, venue_order_id="OGONE0-AAAAA-BBBBBB")
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(raises=RuntimeError("the venue read failed"))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID] and venue.calls != []
    assert (_intent_outcome(tmp_path, 0, earlier), _intent_outcome(tmp_path, 1, earlier)) == ("pending", "pending")


def test_a_withdrawal_the_pass_latched_the_kill_switch_on_leaves_the_pending_intents_as_they_are(tmp_path, kill_trip_expected):
    """The venue reports less filled than the finished row carries, so the pass latches the kill
    switch and repairs nothing; the rows' figures are the ones the venue just refuted, and an intent
    written from them would read `filled` for a leg the venue says never filled."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-opener", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _kill_file(tmp_path).exists()  # the withdrawal tripped
    assert _intent_outcome(tmp_path, 0, earlier) == "pending"


def test_a_cancel_the_venue_refused_on_an_adopted_order_logs_the_hand_cancel_and_leaves_the_row_accepted(tmp_path):
    """The pass cancelled the opener and wrote its intent `revoked` before the venue answered; the
    venue then refuses the cancel, so the order rests beside a terminal-looking intent and no cancel
    is re-sent. The own-order path's CRITICAL is the precedent: the line names the hand cancel, the
    row keeps its open state, and the intent stands as the pass wrote it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCancelRejected, client_order_id=_TXID, reason="EService:Busy"))

    assert [(r.levelno, r.getMessage()) for r in records] == [
        (
            logging.CRITICAL,
            f"cancel of adopted order {_TXID} was REJECTED by the venue -- the order may still rest, and the cancel is "
            "not re-sent: cancel it by hand on Kraken's open-orders page",
        )
    ]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], [e["type"] for e in row["events"]]) == ("accepted", ["OrderAccepted", "OrderCancelRejected"])
    assert client.cache.order(ClientOrderId(_TXID)).status == OrderStatus.ACCEPTED
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"  # the pass's write stands; the line sends the operator to the page


def test_a_mint_landing_detached_after_the_ack_deadline_stranded_the_intent_records_the_flag_on_its_row(tmp_path):
    """The third mint site. The ack deadline fires on the first tick after 30 s, and the library's
    mint, past its own in-flight budget, can land later, so a tick between the two strands the intent
    first and the minted terminal then lands detached, for an order no intent holds: the row keeps
    its state, no state claim being the detached path's rule, and the event carries the flag as at
    the other two sites, so the ledger tells the mint from the venue's own ack once the row is
    settled."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    client.cache._open_orders.append(order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the cancel goes out
    assert [str(cid) for cid in client.canceled] == ["O-1"]
    for _ in range(7):  # 35 s on, past `_ACK_WAIT`: the deadline strands the intent first
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)
    assert (_intent_outcome(tmp_path), ex._active) == ("ambiguous", None)

    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    ex.on_order_event(minted)

    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "accepted"
    assert row["events"][-1] == {"type": "OrderCanceled", "at": clock.now.isoformat(), "reconciliation": True}


def test_the_adopt_pass_cancel_of_a_matched_opener_reads_its_pending_cancel_through_the_handle_and_logs_no_traceback(
    tmp_path,
):
    """The stub twin of the real-engine reading: the client refuses the two attributes the executor
    reads, `cache` and `strategy_id`, while its own `cancel_order` runs and dispatches the
    `OrderPendingCancel` inside it, as the library does. The row keeps `accepted` with the event
    appended, the pass's own line is the one WARNING, and the client's refusal is not reached: the
    read went through the handle taken at construction."""

    class _HeldByItsOwnCancel(StubClient):
        def __init__(self, cache):
            self._held = False
            super().__init__(cache)
            self.executor = None

        @property
        def cache(self):
            if self._held:
                raise RuntimeError("Already mutably borrowed")
            return self._cache

        @cache.setter
        def cache(self, value):
            self._cache = value

        @property
        def strategy_id(self):
            if self._held:
                raise RuntimeError("Already mutably borrowed")
            return self._strategy_id

        @strategy_id.setter
        def strategy_id(self, value):
            self._strategy_id = value

        def cancel_order(self, client_order_id):
            super().cancel_order(client_order_id)
            self._held = True
            try:
                event = _event(OrderPendingCancel, client_order_id=str(client_order_id))
                self._cache.order(client_order_id).apply(event)
                self.executor.on_external_order_event(event)
            finally:
                self._held = False

    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = _HeldByItsOwnCancel(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    client.executor = ex

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]
    assert client.cache.order(ClientOrderId(_TXID)).status == OrderStatus.PENDING_CANCEL  # applied inside the cancel
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (logging.WARNING, f"canceling adopted resting order {_TXID} -- the ledger does not carry it as a resting reducer")
    ]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], [e["type"] for e in row["events"]]) == ("accepted", ["OrderAccepted", "OrderPendingCancel"])


def test_every_cache_and_strategy_id_read_in_the_executor_goes_through_the_handles():
    """The rule the real-engine case and its stub twin prove at one site, held over the module: a read
    through the client inside its own command's dispatch raises, and on `_reconcile_terminal`'s path
    a raise latches a false kill, so no site reads through the client."""
    source = Path(executor_module.__file__).read_text()
    assert (source.count("self._client.cache"), source.count("self._client.strategy_id")) == (0, 0)


# --- the re-read pass (drills F2, G and A1) ---------------------------------------------------------------


def _socket(state, endpoint="kraken-spot-data-streams"):
    """A REAL `SocketStateChanged`, as the client's socket-state stream delivers it once the strategy
    subscribed: the Kraken client's id and the socket's own endpoint name, `kraken-spot-data-streams`
    for the data socket, the name its loopback drop reports. The execution socket's name is unmeasured
    offline, which is why the executor keys on the set of endpoints down and never on a name."""
    return SocketStateChanged(_TRADER_ID, ClientId("KRAKEN"), Venue("KRAKEN"), endpoint, state, UUID4(), 0, 0)


def _reconnect(ex, *endpoints):
    """The cut and the return as the stream reports them: each endpoint down, then each one back."""
    endpoints = endpoints or ("kraken-spot-data-streams",)
    for endpoint in endpoints:
        ex.on_socket_state(_socket(SocketState.DISCONNECTED, endpoint))
    for endpoint in endpoints:
        ex.on_socket_state(_socket(SocketState.CONNECTED, endpoint))


def _hold_in_cache(client, order):
    """Put a REAL order into the stub Cache after the startup pass ran, as the library's own submit
    does for an order this process places: held from construction, the pass at the first tick would
    cancel it as an order with no row."""
    client.cache._open_orders.append(order)


def _minted_after_a_cut(tmp_path, *, venue_orders=None, venue_cancel=None):
    """Drill F2's shape on the plan's own order: a rest-hold order accepted under `_TXID`, the quote
    feed silent through the cut so the executor sends its one cancel, the venue never answering it,
    and the engine minting `OrderCanceled` for itself -- the Cache's order closed by the flagged
    terminal, the row `ambiguous`, the intent `ambiguous`, the plan dropped."""
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)],
        venue_orders=venue_orders,
        venue_cancel=venue_cancel,
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the one cancel goes out into the cut
    assert [str(cid) for cid in client.canceled] == ["O-1"]
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    ex.on_order_event(minted)
    assert (_record(tmp_path)["submitted"][0]["state"], _intent_outcome(tmp_path)) == ("ambiguous", "ambiguous")
    return ex, client, clock


def test_a_reconnect_after_a_minted_cancel_re_cancels_the_order_still_resting_and_settles_its_row(tmp_path):
    """Drill F2's shape: the REST cancel fails in the cut, the engine mints the cancel's terminal, and
    the order rests at Kraken with nothing else re-cancelling it on the reconnect. The sockets' return
    arms the pass; the next tick with nothing in flight reads the venue for the row the mint closed, the
    report says the order still rests, the cancel goes out by txid on the bare client -- the strategy
    handle refuses an order it holds closed -- and the venue's acceptance writes the row `canceled`. The
    intent stays `ambiguous`: it was terminal at the mint, and the row is the re-cancel's record. No
    counter moves for the re-cancel."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _reconnect(ex)
    assert venue.calls == [] and cancel.calls == []  # the handler arms; the tick runs
    clock.now += timedelta(seconds=5)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(clock.now)

    assert venue.calls == [_boundary(NOW) - timedelta(hours=1)]
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert [str(cid) for cid in client.canceled] == ["O-1"]  # no second cancel through the handle
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "canceled"
    assert row["events"][-1] == {"event": "recancelled", "at": clock.now.isoformat(), "venue_order_id": _TXID}
    assert _intent_outcome(tmp_path) == "ambiguous"
    assert metrics.orders == []
    assert [r.getMessage() for r in records if r.getMessage().startswith("re-cancelled")] == [
        f"re-cancelled O-1 (Kraken {_TXID}) -- it rested at Kraken (ACCEPTED) after a terminal this engine minted; "
        "its row reads canceled"
    ]
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1  # the arm is consumed: a later tick reads nothing


def test_a_reconnect_after_a_minted_cancel_of_an_adopted_opener_re_cancels_it_and_leaves_the_intent_the_sweep_wrote(
    tmp_path,
):
    """The adopted path's twin: the startup pass cancelled the opener and its sweep wrote the intent
    `revoked`; the cut lost the ack and the engine minted the terminal, the row `ambiguous`. The
    re-read pass reads the venue, cancels what still rests by txid and settles the row; the intent
    stands as the sweep wrote it."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=cancel)
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"
    assert venue.calls == []  # the Cache answered the startup pass, so the venue was not read
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled" and row["events"][-1]["event"] == "recancelled"
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"


def test_a_venue_report_closed_at_the_reconnect_settles_the_minted_row_without_a_cancel(tmp_path):
    """G's shape met on a reconnect rather than a startup: the venue had executed the cancel and lost
    the ack. The report closes the row as a startup would, and no cancel goes out."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert cancel.calls == []
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "canceled"
    assert [e.get("event") or e["type"] for e in row["events"]] == ["OrderAccepted", "OrderCanceled"]


def test_a_venue_report_filled_at_the_reconnect_settles_the_minted_row_filled_and_counts_it_as_a_startup_would(tmp_path):
    """The one counter the pass moves, and not for a re-cancel: a report that completes the row takes
    the startup's completion arm, `filled` written and counted once, so the board reads the fill the
    cut hid as a restart's sweep would read it. The intent stays as the mint left it."""
    venue = _VenueOrders()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    ordered = executor_module._ordered_qty(_record(tmp_path)["submitted"][0])
    venue.reports.append(_report(_TXID, OrderStatus.FILLED, filled_qty=f"{ordered:.8f}", quantity=f"{ordered:.8f}"))
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"], metrics.orders) == ("filled", ordered, ["filled"])
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_a_venue_read_failing_after_the_reconnect_is_tried_on_three_ticks_then_left_to_the_hand_cancel(tmp_path):
    """The sockets' return is the host's network, not Kraken's REST edge answering: the pass asks
    again on the next tick, three ticks in all, then names the hand cancel and the rows it could not
    read for, the ledger read having succeeded, and stops asking; a later return of the sockets arms
    it again, and a startup inside the re-attach window reads the row too, under the restart rule the
    error-logs page names. Unlike the startup read, no plan is refused for it."""
    venue = _VenueOrders(raises=RuntimeError("dns"))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())

    _reconnect(ex)
    with _executor_errors(level=logging.WARNING) as records:
        for _ in range(4):
            clock.now += timedelta(seconds=5)
            ex.on_timer(clock.now)

    assert len(venue.calls) == 3
    lines = [r for r in records if "re-read pass could not read" in r.getMessage()]
    assert [r.levelno for r in lines] == [logging.WARNING, logging.WARNING, logging.CRITICAL]
    assert (
        lines[-1]
        .getMessage()
        .endswith(f"may still rest at Kraken (O-1 (Kraken {_TXID})): cancel it by hand on Kraken's open-orders page")
    )
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert ex._reconciliation_refusal is None
    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 4


def test_a_reconnect_reads_the_venue_for_no_row_the_engine_did_not_mint_terminal(tmp_path):
    """The population is the rows whose Cache order a minted terminal closed and no other: a kept
    reducer's row is open and its order rests, so the sockets' return reads nothing for it."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)
    ex.on_timer(NOW)

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [] and client.canceled == []


def test_each_socket_reported_down_arms_the_pass_on_its_own_return_and_the_connect_itself_arms_nothing(tmp_path):
    """The stream delivers `CONNECTED` at the connect itself, which owes nothing. With two endpoints
    down, the first back owes the pass whatever the second reports -- the execution socket's name,
    and whether its return arrives under the string its drop carried, are unmeasured offline, and the
    data socket reports its return under its own name -- and the second back owes it again, an empty
    population consuming that arm with no order read. A socket reported down first holds the arm the
    mint set, so the first tick measures the connect's `CONNECTED` alone. Each drop and return logs
    its endpoint, the line F2's Record and the rollout's first hour read the execution socket's off."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_socket_state(_socket(SocketState.DISCONNECTED, "a-second-endpoint"))  # holds the arm the mint set

        ex.on_socket_state(_socket(SocketState.CONNECTED))  # the connect itself: not held down
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)
        assert venue.calls == []
        ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
        ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)
        assert len(venue.calls) == 1  # the first return arms it, the second endpoint still down
        assert (ex._reread_tries, set(ex._sockets_down)) == (0, {"a-second-endpoint"})
        ex.on_socket_state(_socket(SocketState.CONNECTED, "a-second-endpoint"))
        assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # armed again
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)
        assert len(venue.calls) == 1  # nothing left minted terminal: the arm is consumed with no order read

    assert [r.getMessage() for r in records if r.getMessage().startswith("socket ")] == [
        "socket a-second-endpoint is down -- an order whose terminal this engine mints meanwhile is re-read at the venue "
        "once a socket is back",
        "socket kraken-spot-data-streams is down -- an order whose terminal this engine mints meanwhile is re-read at the "
        "venue once a socket is back",
        "socket kraken-spot-data-streams is back (a-second-endpoint still down) -- the re-read pass runs on the next tick "
        "with nothing in flight",
        "socket a-second-endpoint is back and none is down -- the re-read pass runs on the next tick with nothing in flight",
    ]


def test_the_pass_waits_for_a_tick_with_nothing_of_this_process_in_flight(tmp_path):
    """The read and the cancel go out on a second client on the same key -- `read_venue_orders`'
    nonce hazard against the execution client's in-flight queries -- so the pass runs on a tick with
    no order of this process in flight, the arm -- a mint's, here, beside a live intent -- kept until one comes."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    clock = _Clock()
    ex = _executor(tmp_path, client=client, clock=clock, venue_orders=venue, venue_cancel=_VenueCancel())
    ex.on_timer(clock.now)
    _drop_plan(tmp_path, _plan_dict())
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    ex.on_quote(_quote())
    assert client.last_order_id == "O-1" and ex._active is not None  # the plan's own order is in flight

    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))  # the mint arms
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == []
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.001)
    assert ex._active is None
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"


def test_the_reread_pass_waits_while_a_startup_cancel_of_an_adopted_order_is_still_unanswered(tmp_path):
    """`_active` None is not nothing in flight: the startup pass's cancels of adopted orders, and a
    trip's, leave orders PENDING_CANCEL with no intent live, and the library's in-flight check
    queries those on the same key. The pass waits for a tick on which the Cache holds no order of
    this process in flight, and the minted terminal that ends the library's query is what frees it."""
    earlier = NOW - timedelta(hours=4)
    minted, pending = _TXID, "OBBBBB-BBBBB-BBBBBB"
    _pending_plan_entry(tmp_path, earlier, n_intents=2)
    _submitted_row(tmp_path, "O-a", reduce_only=False, when=earlier, index=0, venue_order_id=minted)
    _submitted_row(tmp_path, "O-b", reduce_only=False, when=earlier, index=1, venue_order_id=pending)
    orders = [_resting_limit_order(minted, venue_order_id=minted), _resting_limit_order(pending, venue_order_id=pending)]
    client = StubClient(StubCache(open_orders=orders))
    venue = _VenueOrders(_report(minted, OrderStatus.ACCEPTED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [minted, pending]
    for order in orders:  # the handle's own `OrderPendingCancel`, which the library applies on the cancel
        order.apply(_event(OrderPendingCancel, client_order_id=str(order.client_order_id)))
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=minted, reconciliation=True))

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))
    assert venue.calls == [] and ex._active is None  # the second cancel is still in flight
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=pending, reconciliation=True))
    ex.on_timer(NOW + timedelta(seconds=10))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]


def test_a_re_cancel_the_venue_refuses_leaves_the_row_and_names_the_hand_cancel(tmp_path):
    """The order went between the read and the cancel, or the cut is not over for REST: the venue's
    refusal, or a raise, leaves the row as it was and the line names the hand cancel -- the
    refused-cancel arm's precedent -- and the arm is consumed, since the line is the operator's."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel(raises=RuntimeError("EOrder:Unknown order"))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    with _executor_errors() as records:
        ex.on_timer(clock.now)

    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"
    assert [r.getMessage() for r in records] == [
        f"the re-read pass's cancel of O-1 (Kraken {_TXID}) raised or was refused -- the order may still rest at "
        "Kraken: cancel it by hand on Kraken's open-orders page"
    ]
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert len(venue.calls) == 1


def test_a_partial_fill_applied_after_the_mint_keeps_the_row_in_the_reread_pass_which_re_cancels_the_remainder(
    tmp_path,
):
    """The order F2 exists for: a maker at the touch part-fills during the cut, and the private stream
    delivers the fill after the reconnect. The state machine applies it to the order held
    minted-CANCELED -- its last event is then the fill -- so the mint is read off the order's
    history, the venue is asked, and the remainder still resting is re-cancelled with the fill on
    the row."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)
    order = client.cache.order(ClientOrderId("O-1"))
    fill = _fill("O-1", 0.0004, venue_order_id=VenueOrderId(_TXID))
    order.apply(fill)
    ex.on_order_event(fill)
    assert (order.status, type(order.last_event).__name__) == (OrderStatus.CANCELED, "OrderFilled")

    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0004)


def test_a_minted_cancel_of_an_adopted_opener_with_the_sockets_up_is_settled_from_the_venue_on_the_next_tick(tmp_path):
    """Drills G's and A1's shape, the one each adopt-pass cancel takes on this wheel: the pass cancels
    the adopted opener, Kraken cancels it at the second asked, nothing it answers is applied, and about
    31 s on the engine mints the cancel's terminal with the sockets up. The mint writes the row
    `ambiguous` at WARNING and arms the re-read pass; the next tick with nothing in flight reads the
    venue for the row, the report says closed, and the row settles `canceled` with no cancel sent, no
    counter moved, no CRITICAL line, and the intent as the sweep wrote it. The row's own evidence of the
    mint is the flag on its `OrderCanceled` event."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    cancel = _VenueCancel()
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=cancel)
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == [_TXID] and _intent_outcome(tmp_path, 0, earlier) == "revoked"
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    with _executor_errors(level=logging.WARNING) as records:
        _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
        assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"
        ex.on_timer(NOW + timedelta(seconds=5))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)] and cancel.calls == []
    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled"
    assert row["events"][-1] == {"type": "OrderCanceled", "at": NOW.isoformat(), "reconciliation": True}
    assert _intent_outcome(tmp_path, 0, earlier) == "revoked"
    assert metrics.orders == []
    assert [(r.levelno, r.getMessage()) for r in records] == [
        (
            logging.WARNING,
            f"OrderCanceled for {_TXID} was reconciled, not received -- no venue answer reached this engine; its row reads "
            "ambiguous until the re-read pass settles it from the venue's own report",
        ),
        (logging.WARNING, "the re-read pass reads 1 row(s) this engine minted terminal against the venue"),
    ]
    ex.on_timer(NOW + timedelta(seconds=10))
    assert len(venue.calls) == 1  # the arm is consumed


def test_a_socket_reported_down_holds_the_re_read_a_mint_armed_until_a_socket_is_back(tmp_path):
    """F2's shape, where the mint lands before the socket's own deadline reports the cut: the mint arms
    the pass, the `DISCONNECTED` holds it, so nothing is read inside the cut, and the socket's return
    arms it again."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # the mint armed it

    ex.on_socket_state(_socket(SocketState.DISCONNECTED))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == [] and ex._reread_tries == 0
    ex.on_socket_state(_socket(SocketState.CONNECTED))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"


def test_a_mint_while_a_socket_is_held_down_arms_nothing_and_the_sockets_return_does(tmp_path):
    """The other order of F2's two clocks: the socket reports the cut before the in-flight budget
    mints the terminal. The mint arms nothing while an endpoint is held down, the tick reads
    nothing, and the return arms the pass."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED))

    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    assert ex._reread_tries == 0
    ex.on_timer(NOW + timedelta(seconds=5))
    assert venue.calls == []
    ex.on_socket_state(_socket(SocketState.CONNECTED))
    ex.on_timer(NOW + timedelta(seconds=10))

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"


def test_a_socket_drop_after_another_sockets_return_leaves_that_returns_arm_and_the_pass_runs(tmp_path):
    """The execution socket drops about hourly on this wheel and reconnects in about 1.5 s, and its
    endpoint string is unmeasured: a `DISCONNECTED` of it landing after the data socket's return
    must not clear the arm that return set, or a return under another string would never re-arm it
    and the order the mint closed would rest until a startup. A mint's arm it does clear, and an
    entry held down under a string no `CONNECTED` matches holds every later mint's arm off, the
    cost the spec names."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED))
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    _reconnect(ex)  # the data socket down and back: the return arms the pass
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    assert (ex._reread_tries, set(ex._sockets_down)) == (executor_module._REREAD_ATTEMPTS, {"kraken-spot-user-streams"})

    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and _record(tmp_path)["submitted"][0]["state"] == "canceled"
    ex.on_socket_state(_socket(SocketState.CONNECTED, "another-string"))  # a return under another string arms nothing
    ex._arm_reread_after_mint()  # and the entry it left holds a mint's arm off
    assert (ex._reread_tries, set(ex._sockets_down)) == (0, {"kraken-spot-user-streams"})


@pytest.mark.parametrize(
    "venue_status, venue_filled", [(OrderStatus.PARTIALLY_FILLED, "0.0004"), (OrderStatus.FILLED, "the ordered quantity")]
)
def test_a_fill_the_stream_replays_after_the_pass_repaired_the_row_adds_nothing_and_trips_nothing(
    tmp_path, venue_status, venue_filled
):
    """F2's part-filled maker, the order the pass exists for, with the execution stream resubscribing
    behind the data socket's return: the pass repairs the row from the venue's report and re-cancels
    it, or settles it `filled`, and the stream then replays the fill the repair already carries --
    whether it does on this wheel is unmeasured, F2's Record reading it, and the replay here is
    delivered by hand. A fill credits the row with what the Cache's order holds beyond it, so the
    replay adds nothing: the event's quantity would read the row at twice the venue's figure, latch
    the kill switch at the next startup on a withdrawal that never happened, and on a whole fill's
    replay trip it on an overfill at once. The `fill` line keeps the stream's own quantity and
    carries what the cap credited the row, 0.0, the figure the ledger's readers count into `held`,
    the repair's `reconciled` line already carrying the fill."""
    venue = _VenueOrders()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    ordered = executor_module._ordered_qty(_record(tmp_path)["submitted"][0])
    filled = ordered if venue_filled == "the ordered quantity" else float(venue_filled)
    venue.reports.append(_report(_TXID, venue_status, filled_qty=f"{filled:.8f}", quantity=f"{ordered:.8f}"))
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    row = _record(tmp_path)["submitted"][0]
    settled = "canceled" if venue_status is OrderStatus.PARTIALLY_FILLED else "filled"
    assert (row["state"], row["filled_qty"]) == (settled, filled)

    order = client.cache.order(ClientOrderId("O-1"))
    replay = _fill("O-1", filled, venue_order_id=VenueOrderId(_TXID))
    order.apply(replay)
    ex.on_order_event(replay)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == (settled, filled)
    assert (row["events"][-1]["event"], row["events"][-1]["qty"], row["events"][-1]["credited"]) == ("fill", filled, 0.0)
    assert not _kill_file(tmp_path).exists() and metrics.orders == (["filled"] if settled == "filled" else [])
    later_status = OrderStatus.CANCELED if settled == "canceled" else OrderStatus.FILLED
    later = _VenueOrders(_report(_TXID, later_status, filled_qty=f"{filled:.8f}", quantity=f"{ordered:.8f}"))
    ex2 = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=later)
    ex2.on_timer(NOW + timedelta(minutes=10))
    assert not _kill_file(tmp_path).exists()  # the next startup reads the venue's figure and the row's as one


def test_a_fill_after_the_pass_re_cancelled_an_adopted_order_completes_its_row_on_the_passs_own_mirror(tmp_path):
    """The adopted path's row sits in `_attached` under its txid, the id the Cache names the order by,
    from the startup's mirror; the pass reads fresh rows from the ledger and re-attaches each under
    the Cache order's own id too, so a later fill reads the pass's row and not the startup's stale
    copy. The stream then replays the fill the repair carries, adding nothing, and delivers one
    beyond it, which completes the row on the pass's figure and counts once."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    order = _resting_limit_order(_TXID, quantity="0.001", venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[order]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006", quantity="0.001"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    ex.on_timer(NOW + timedelta(seconds=5))  # the mint armed the pass: the row is repaired to 0.0006 and re-cancelled
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0006)
    assert ex._attached[_TXID][1] is ex._attached["O-opener"][1]  # one row dict under both ids
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _deliver_external_event(ex, client, _fill(_TXID, 0.0006, venue_order_id=VenueOrderId(_TXID)))  # the replay
    _deliver_external_event(ex, client, _fill(_TXID, 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-2"))  # beyond it

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], metrics.orders) == ("filled", ["filled"])
    assert row["filled_qty"] == pytest.approx(0.001)
    # `credited` only where the cap moved the row by less: the replay's line carries 0.0, the fill beyond it none.
    assert [(e["qty"], e.get("credited")) for e in row["events"] if e.get("event") == "fill"] == [(0.0006, 0.0), (0.0004, None)]
    assert not _kill_file(tmp_path).exists()


def test_a_fill_beyond_the_passs_repair_that_the_cache_holds_whole_is_credited_whole_and_its_line_carries_no_credited(tmp_path):
    """The cap reads the Cache order's figure less the row's, two sums a float's rounding apart: the
    Cache at 0.0003 after a 0.0001 fill, less the row's 0.0002, reads 9.999999999999996e-05, which
    written as `credited` would tell the ledger's readers the fill moved the row by less than it did.
    A credit within `_OVERFILL_TOLERANCE` of the fill's quantity is that quantity, the sweep's own dead
    band, so the line carries none."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-opener", reduce_only=False, when=earlier, venue_order_id=_TXID)
    order = _resting_limit_order(_TXID, quantity="0.001", venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[order]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0002", quantity="0.001"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, venue_cancel=_VenueCancel()
    )
    ex.on_timer(NOW)
    _deliver_external_event(ex, client, _event(OrderCanceled, client_order_id=_TXID, reconciliation=True))
    ex.on_timer(NOW + timedelta(seconds=5))  # the mint armed the pass: the row is repaired to 0.0002 and re-cancelled

    _deliver_external_event(ex, client, _fill(_TXID, 0.0002, venue_order_id=VenueOrderId(_TXID)))  # the replay
    _deliver_external_event(ex, client, _fill(_TXID, 0.0001, venue_order_id=VenueOrderId(_TXID), trade_id="T-2"))  # beyond it

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [(e["qty"], e.get("credited")) for e in row["events"] if e.get("event") == "fill"] == [(0.0002, 0.0), (0.0001, None)]
    assert row["filled_qty"] == pytest.approx(0.0003)


def test_a_mint_landing_detached_after_the_ack_deadline_stranded_the_intent_arms_the_pass_which_re_cancels_the_order(
    tmp_path,
):
    """The third mint site: the ack deadline fires on the first tick after 30 s and the
    library's mint, past its own in-flight budget, can land later, so a tick between the two strands
    the intent first and the minted terminal lands detached, for an order no intent holds. It arms
    the pass as the other two sites do, and the next tick reads the venue and re-cancels the order
    still resting; without the arm the row would stay `accepted` and the order rest until a
    socket's return or a startup."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)], venue_orders=venue, venue_cancel=cancel
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the cancel goes out
    for _ in range(7):  # 35 s on, past `_ACK_WAIT`: the deadline strands the intent first
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)
    assert (_intent_outcome(tmp_path), ex._active, ex._reread_tries) == ("ambiguous", None, 0)
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    ex.on_order_event(minted)
    assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # the detached site armed it

    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["events"][-1]["event"]) == ("canceled", "recancelled")
    assert _intent_outcome(tmp_path) == "ambiguous"


def test_a_returns_arm_pending_behind_a_live_intent_is_cleared_by_the_cut_and_the_return_settles_the_row(tmp_path):
    """The execution socket drops and returns while an order rests, about hourly on this wheel: its
    return arms the pass, which waits behind the live intent. Then the cut: both endpoints report
    down, the quote silence sends the one cancel into it, and the engine mints the terminal. The
    arming endpoint's own drop cleared its arm, so nothing is read into the cut -- an arm every drop
    but its own left standing would read into it and page the CRITICAL over an order the return
    then settles -- and the return arms the pass, which settles the row. Past the grace the watchdog
    freezes, its one CRITICAL the only line at ERROR or above, and its sweep finds nothing open: the
    real Cache lists the minted order closed. The return's pass lifts the freeze on its own tick. The
    drops here lead the mint; the case below takes F2's order, the mint ahead of the first drop."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)], venue_orders=venue, venue_cancel=cancel
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    _reconnect(ex, "kraken-spot-user-streams")
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert venue.calls == [] and ex._reread_tries == executor_module._REREAD_ATTEMPTS  # the intent is live: the arm waits
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    assert ex._reread_tries == executor_module._REREAD_ATTEMPTS  # another endpoint's drop leaves it
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    assert ex._reread_tries == 0  # its own endpoint's drop clears it
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the one cancel goes out into the cut
    assert [str(cid) for cid in client.canceled] == ["O-1"]
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    client.cache._open_orders.remove(order)
    client.cache._closed_orders.append(order)
    ex.on_order_event(minted)
    with _executor_errors(level=logging.WARNING) as records:
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)  # 31 s after both drops: the freeze
        assert ex._frozen
        for _ in range(2):
            clock.now += timedelta(seconds=5)
            ex.on_timer(clock.now)
    assert venue.calls == [] and [str(cid) for cid in client.canceled] == ["O-1"]
    assert [r.getMessage() for r in records if r.levelno >= logging.ERROR] == [
        "the execution watchdog froze the loop -- socket kraken-spot-data-streams, kraken-spot-user-streams down past "
        "the 30s grace: a cancel is sent for the active intent's order and each order the Cache holds open, a resting "
        "intent revoked with socket_down, and every new intent is refused until the sockets are back and the re-read "
        "pass has settled"
    ]

    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled" and not ex._frozen


def test_a_returns_arm_pending_behind_a_live_intent_that_the_other_endpoints_drop_left_standing_is_closed_by_its_first_failed_read_into_the_cut(
    tmp_path,
):
    """The case above in F2's order: the mint ahead of the first `DISCONNECTED`, and the execution
    socket's own drop, the one that clears the arm its return set, later, its time unmeasured. The
    mint ends the intent, so nothing holds the arm back when the data socket reports down, and the
    tick reads into the cut: the first read that fails while an endpoint is held down
    closes the arm at WARNING -- one read, no CRITICAL -- where a budget spent into the cut would
    page over an order the return then settles. The return arms three again and settles the row."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)], venue_orders=venue, venue_cancel=cancel
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    _reconnect(ex, "kraken-spot-user-streams")
    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)  # quote silence: the one cancel goes out into the cut, the return's arm waiting behind the intent
    assert [str(cid) for cid in client.canceled] == ["O-1"] and venue.calls == []
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    ex.on_order_event(minted)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    assert (ex._active, ex._reread_tries, ex._reread_armed_by) == (
        None,
        executor_module._REREAD_ATTEMPTS,
        "kraken-spot-user-streams",
    )
    venue._raises = RuntimeError("dns")
    with _executor_errors(level=logging.WARNING) as records:
        for _ in range(3):
            clock.now += timedelta(seconds=5)
            ex.on_timer(clock.now)

    assert len(venue.calls) == 1 and (ex._reread_tries, ex._reread_armed_by) == (0, None)
    lines = [r for r in records if "re-read pass could not read" in r.getMessage()]
    assert [r.levelno for r in lines] == [logging.WARNING]
    assert "while socket kraken-spot-data-streams is down -- the arm closes" in lines[0].getMessage()

    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    venue._raises = None
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert len(venue.calls) == 2 and cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")]
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"


def test_a_row_the_read_has_no_order_for_is_marked_once_and_left_out_of_the_passs_later_arms(tmp_path):
    """A row whose txid the venue read does not return -- a closed order the adapter cannot resolve
    -- no read of this process settles: the pass marks it `ambiguous` with the unmatched event, once,
    its CRITICAL the operator's line, and leaves it out of every later arm, where re-reading it on
    each socket return, about hourly on this wheel, would page the same line each time over a row
    already read. A startup inside the re-attach window reads it again, the startup's own rule."""
    venue = _VenueOrders()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    marked_at = clock.now
    with _executor_errors() as records:
        ex.on_timer(clock.now)
        _reconnect(ex)
        clock.now += timedelta(seconds=5)
        ex.on_timer(clock.now)

    assert len(venue.calls) == 1
    assert [r.getMessage() for r in records] == [
        f"ledgered order O-1 matches no venue order -- the venue's order read has no order {_TXID}; its row is marked ambiguous"
    ]
    row = _record(tmp_path)["submitted"][0]
    assert row["state"] == "ambiguous"
    assert [e for e in row["events"] if e.get("type") == "ambiguous"] == [
        {"type": "ambiguous", "at": marked_at.isoformat(), "what": f"the venue's order read has no order {_TXID}"}
    ]


def test_a_fill_after_the_re_cancel_on_a_cache_behind_the_venues_report_is_credited_beyond_the_caches_lag_alone(tmp_path):
    """The cut's partial never reaches the stream, so the Cache's order holds nothing of the 0.0004
    the pass repaired the row to from the report; a 0.0003 fill landing between the pass's read and
    its cancel is then delivered, and the cap credits what the Cache holds beyond the row -- nothing,
    the Cache behind by more than the fill, the cap unable to tell it from a replay. The row keeps
    the report's figure with the `fill` line carrying the fill and `credited` 0.0: the shortfall the
    row keeps, and a reader counting the line by `credited` with it."""
    venue = _VenueOrders()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=_VenueCancel())
    ordered = executor_module._ordered_qty(_record(tmp_path)["submitted"][0])
    venue.reports.append(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.00040000", quantity=f"{ordered:.8f}"))
    _reconnect(ex)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("canceled", 0.0004)

    order = client.cache.order(ClientOrderId("O-1"))
    later = _fill("O-1", 0.0003, venue_order_id=VenueOrderId(_TXID), trade_id="T-2")
    order.apply(later)
    ex.on_order_event(later)

    row = _record(tmp_path)["submitted"][0]
    assert (row["state"], row["filled_qty"], float(order.filled_qty)) == ("canceled", 0.0004, 0.0003)
    moving = [(e["event"], e["qty"], e.get("credited")) for e in row["events"] if e.get("event") in ("fill", "reconciled")]
    assert moving == [("reconciled", 0.0004, None), ("fill", 0.0003, 0.0)]


def test_a_plan_dropped_during_a_cut_starts_behind_the_re_cancel_on_the_same_tick(tmp_path):
    """The tick runs the pass before the pickup and the pump: a plan dropped while the sockets were
    down starts on the tick after the return, once the pass has re-cancelled the order the cut left
    resting, and never ahead of it. The pump first would arm its intent, and the pass, which waits
    for nothing of this process in flight, would wait behind that plan's every intent."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex, client, clock = _minted_after_a_cut(tmp_path, venue_orders=venue, venue_cancel=cancel)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED))
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", created_at=clock.now))
    ex.on_socket_state(_socket(SocketState.CONNECTED))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert cancel.calls == [(_TXID, "BTC/EUR.KRAKEN")] and ex._active is not None
    assert _record(tmp_path)["submitted"][0]["state"] == "canceled"


class _UnreadableOrderCache(StubCache):
    """A Cache whose `order()` refuses, with the text the client's `cache` getter raises inside its own
    command's dispatch -- raised here by the Cache itself, so the except arm for a read failing for any
    reason has a case. Switchable, because the startup pass reads the same accessor and the row has to
    attach against a readable Cache first."""

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

    No read here raises in production, since the executor reads through the handle taken at
    construction -- the borrow was the client's, inside its own command's dispatch, never the
    Cache's -- so this is the arm for a read failing for any other reason. Letting it escape would
    abandon the whole handler, and with it the forensic event payload, to decide a state the event
    never carried -- so the event still appends, the entry stays attached, and the row keeps the
    state it has. Read as a pair: without the readable arm an unconditional `None` would pass, and
    without the raising arm a narrowed `except` is invisible."""
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


# --- the stale-socket watchdog: the grace, the freeze, the lift ----------------------------------------


def _frozen_executor(tmp_path, *, venue_orders=None, venue_cancel=None, venue_holdings=None):
    """The cut carried to the mint: a rest-hold order accepted under `_TXID` and held in the Cache, both
    endpoints reported down, ticks with quotes past the grace so the freeze's cancel is the one, then
    the terminal the engine mints for itself, which gives the re-read pass a row to read. The minted
    order moves to the Cache's closed list, as the real Cache lists a canceled order where the stub's
    lists are static, so a later sweep finds nothing open."""
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)],
        venue_orders=venue_orders if venue_orders is not None else _VenueOrders(_report(_TXID, OrderStatus.CANCELED)),
        venue_cancel=venue_cancel if venue_cancel is not None else _VenueCancel(),
        venue_holdings=venue_holdings,
    )
    order = _resting_limit_order("O-1", venue_order_id=_TXID)
    _hold_in_cache(client, order)
    ex.on_order_event(_event(OrderAccepted, client_order_id="O-1", venue_order_id=VenueOrderId(_TXID)))
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    _advance_with_quotes(ex, client, clock, minutes=1)
    minted = _event(OrderCanceled, client_order_id="O-1", reconciliation=True)
    order.apply(minted)
    client.cache._open_orders.remove(order)
    client.cache._closed_orders.append(order)
    ex.on_order_event(minted)
    assert _record(tmp_path)["submitted"][0]["state"] == "ambiguous"  # the mint landed: the pass has a row to read
    return ex, client, clock


def test_a_three_second_blip_revokes_nothing_and_a_partial_cut_past_the_grace_revokes_the_resting_intent_on_its_ack(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=3)
    ex.on_timer(clock.now)  # a tick inside the blip, so a grace shorter than the blip would freeze here
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    _advance_with_quotes(ex, client, clock, minutes=1)
    assert client.canceled == [] and not ex._frozen
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))  # the execution socket stays up
    _advance_with_quotes(ex, client, clock, minutes=1)  # a tick every 10 s, past the 30 s grace
    assert ex._frozen and client.canceled == [client.last_order_id]
    ex.on_order_event(_canceled(client.last_order_id))  # the ack the execution socket carries
    assert _intent_outcome(tmp_path) == "revoked" and "socket_down" in _intent_entry(tmp_path, 0)["reasons"]


def test_a_cut_of_both_endpoints_past_the_grace_sends_the_cancel_and_the_row_ends_ambiguous_on_the_minted_terminal(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path)  # both endpoints down, the freeze's one cancel out, the terminal minted
    assert ex._frozen and [str(cid) for cid in client.canceled] == ["O-1"]
    assert _intent_outcome(tmp_path) == "ambiguous" and ex._plan is None
    assert "was reconciled, not received" in _intent_entry(tmp_path, 0)["reasons"][0]


def test_the_freezes_sweep_cancels_the_active_order_and_every_other_open_order_once(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    _hold_in_cache(client, _resting_limit_order("O-1", venue_order_id=_TXID))  # the active's own order, as the library holds it
    _hold_in_cache(client, _resting_limit_order("O-other"))
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    _advance_with_quotes(ex, client, clock, minutes=1)
    assert ex._frozen and sorted(str(cid) for cid in client.canceled) == ["O-1", "O-other"]


def test_a_freeze_with_no_intent_live_refuses_the_next_plans_every_intent_with_socket_down(tmp_path):
    clock = _Clock()
    ex = _executor(tmp_path, clock=clock)
    ex.on_timer(clock.now)  # the startup pass
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=31)
    ex.on_timer(clock.now)
    assert ex._frozen
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _intent(symbol="ETH/EUR", notional_eur=20.0)]))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    intents = [_intent_entry(tmp_path, index) for index in (0, 1)]
    assert [entry["outcome"] for entry in intents] == ["refused", "refused"]
    assert all("socket_down" in entry["reasons"] for entry in intents)


def test_the_freeze_lifts_only_once_the_set_is_empty_and_a_completed_pass_has_settled(tmp_path):
    holdings = _VenueHoldings({})
    ex, client, clock = _frozen_executor(tmp_path, venue_holdings=holdings)  # helper: the cut above, frozen
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    assert ex._frozen  # one endpoint still down
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    assert ex._frozen  # the set is empty but no pass has run
    with _executor_errors(level=logging.INFO) as records:
        ex.on_timer(clock.now)  # the pass runs with nothing in flight and settles
        ex.on_timer(clock.now + timedelta(seconds=5))  # the lift's condition still holds: nothing lifts twice
    assert not ex._frozen and holdings.calls >= 2
    assert sum("freeze lifted" in r.getMessage() for r in records) == 1


def test_the_freeze_and_its_lift_publish_the_watchdog_gauge(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _frozen_executor(tmp_path)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    ex.on_timer(clock.now)
    assert metrics.frozen == [True, False]


def test_a_stale_entry_holds_the_freeze_and_the_published_level_at_none(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    # the execution socket's return under another string
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams-2"))
    _advance_ticks(ex, minutes=20)
    verdict = ex._evaluate(clock.now)
    assert ex._frozen and verdict.level == GateLevel.NONE and "socket_down" in verdict.reasons


def test_a_pass_whose_budget_is_spent_leaves_the_freeze_standing(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path, venue_orders=_VenueOrders(raises=RuntimeError("down")))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    _advance_ticks(ex, minutes=1)
    assert ex._frozen and ex._reread_tries == 0


def test_a_settle_that_fails_on_the_returns_pass_spends_one_try_and_the_next_ticks_pass_lifts_the_freeze(tmp_path):
    holdings = _VenueHoldings({})
    ex, client, clock = _frozen_executor(tmp_path, venue_holdings=holdings)
    holdings._raises = RuntimeError("down")  # the startup's settle answered; the return's fails
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    ex.on_timer(clock.now)  # the pass's reads answer, its settle fails: one try spent, the freeze stands
    assert ex._frozen and ex._reread_tries == 2
    holdings._raises = None
    ex.on_timer(clock.now + timedelta(seconds=5))
    assert not ex._frozen and ex._reread_tries == 0


def test_a_pass_completed_before_the_cut_lifts_nothing_until_both_endpoints_are_back_and_a_pass_after_the_return_completes(
    tmp_path,
):
    holdings = _VenueHoldings({})
    clock = _Clock()
    ex = _executor(tmp_path, clock=clock, venue_holdings=holdings)
    ex.on_timer(clock.now)  # the startup pass
    _reconnect(ex)  # a blip before the cut: its return arms the pass
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)  # the pass completes, so both moments the lift reads are set before the cut
    assert ex._sockets_emptied_at is not None and ex._reread_completed_at is not None
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=31)
    ex.on_timer(clock.now)
    assert ex._frozen
    clock.now += timedelta(seconds=5)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)  # the data socket's pass completes with the execution socket still down
    assert ex._frozen
    holdings._raises = RuntimeError("down")
    clock.now += timedelta(seconds=5)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)  # the last return's pass fails its holdings read: none has completed since that return
    assert ex._frozen


def test_a_repeated_drop_of_one_endpoint_keeps_the_grace_running_from_its_first_drop(tmp_path):
    clock = _Clock()
    ex = _executor(tmp_path, clock=clock)
    ex.on_timer(clock.now)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=20)
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))  # the same cut, reported again
    clock.now += timedelta(seconds=11)
    ex.on_timer(clock.now)  # 31 s after the first drop, 11 s after the second
    assert ex._frozen


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
        _venue_order_id(client_order_id), _ACCOUNT_ID, f"reconciliation-R-1-{trade_id}", TradeId(trade_id), _quantity(qty),
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


# --- the row keying: after a restart every order is named by its Kraken txid ----------------------
#
# The adapter's order reports carry no client order id, so the startup reconciliation names each
# order it adopts by its txid, on both ids -- the shape `_resting_limit_order(_TXID,
# venue_order_id=_TXID)` builds. The ledger keys every row by the id this engine minted, and the row
# records the txid at acceptance. These tests drive the reconciled shape; every test above names the
# adopted order by the engine's own id, the shape no restart on the pinned wheel produces.


@pytest.mark.parametrize(
    "recorded, canceled",
    [
        (True, []),  # the row recorded its txid: the reducer is found, kept and re-attached
        (False, [_TXID]),  # a row with no txid names nothing the Cache holds: canceled as unledgered
    ],
)
def test_a_ledgered_reducer_reconciled_under_its_txid_is_left_resting(tmp_path, recorded, canceled):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID if recorded else None)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == canceled
    assert (_TXID in ex._attached) is recorded


def _txid_adopted_executor(tmp_path, *, reduce_only=True):
    """A previous process's order the ledger recorded under `_TXID`, adopted under that txid and
    attached to its row four hours back."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))
    ex.on_timer(NOW)
    assert _TXID in ex._attached
    return ex, client, earlier


def test_a_post_restart_fill_named_by_the_txid_lands_in_the_row_the_engine_keyed(tmp_path):
    """The fill arrives on the external topic naming the order by its txid; the ledger holds no row
    under that id, so the write must name the row by its own."""
    ex, client, earlier = _txid_adopted_executor(tmp_path)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _deliver_external_event(ex, client, _fill(_TXID, 0.0004, venue_order_id=VenueOrderId(_TXID)))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["client_order_id"] == "O-reducer"
    assert [e.get("event") for e in row["events"]][-1] == "fill" and row["filled_qty"] == 0.0004
    assert metrics.external == ["matched"]
    assert not _kill_file(tmp_path).exists()


def test_a_txid_named_fill_completing_the_ledgered_quantity_closes_the_row(tmp_path):
    """Nautilus publishes no terminal event after a resting order's final fill, so the completion
    write is the only thing that closes this row -- and it too must name the row by its own id."""
    ex, _client, earlier = _txid_adopted_executor(tmp_path)

    ex.on_external_order_event(_fill(_TXID, 0.001, venue_order_id=VenueOrderId(_TXID)))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "filled" and row["filled_qty"] == 0.001
    assert not _kill_file(tmp_path).exists()


def test_the_startup_cancel_of_an_opener_named_by_its_txid_closes_its_row_on_the_ack(tmp_path):
    """What Drill G reads: the pass cancels the adopted opener, and the venue's ack -- naming the
    order by its txid -- arrives matched and gives the row its terminal state."""
    ex, client, earlier = _txid_adopted_executor(tmp_path, reduce_only=False)
    assert [str(cid) for cid in client.canceled] == [_TXID]
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)

    _deliver_external_event(ex, client, _canceled(_TXID))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "canceled"
    assert row["events"][-1] == {"type": "OrderCanceled", "at": NOW.isoformat()}
    assert metrics.external == ["matched"]


def test_an_overfill_named_by_the_txid_trips_and_journals_the_fill_under_the_rows_own_id(tmp_path, kill_trip_expected):
    ex, client, earlier = _txid_adopted_executor(tmp_path)

    _deliver_external_event(ex, client, _fill(_TXID, 0.002, venue_order_id=VenueOrderId(_TXID)))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e.get("event") for e in row["events"]][-1] == "fill" and row["filled_qty"] == 0.002
    assert f"order O-reducer (Kraken {_TXID}) has now filled 0.002 of the 0.001" in _kill_file(tmp_path).read_text()


def test_an_event_naming_the_order_by_neither_attached_id_is_found_by_its_venue_order_id(tmp_path):
    """The fallback for an event whose client order id is no key the pass attached -- an adopted
    order whose events name it some third way. Its venue order id is the order's own, which no other
    order carries, so the match cannot catch the owner's hand settle: that one's txid is its own."""
    ex, client, earlier = _txid_adopted_executor(tmp_path)

    ex.on_external_order_event(_fill("O-120000-001-000-1", 0.0004, venue_order_id=VenueOrderId(_TXID)))
    ex.on_external_order_event(_fill("O-the-owners-own-hand", 0.5, venue_order_id=VenueOrderId("OOWNER-HANDS-ETTLE1")))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["filled_qty"] == 0.0004  # the first landed; the hand settle matched nothing
    assert not _kill_file(tmp_path).exists()


def test_an_open_row_reconciles_against_the_order_the_cache_holds_under_its_txid(tmp_path):
    """The sweep's own lookup, before any classification: the row's own id misses, and the Cache's
    venue-order-id index finds the order the row recorded."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    cache = StubCache(open_orders=[_open_order(_TXID, venue_order_id=_TXID, filled_qty=0.0004)])
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [e.get("event") or e.get("type") for e in row["events"]] == ["OrderAccepted", "reconciled"]
    assert row["filled_qty"] == 0.0004


def test_a_finished_row_is_compared_with_the_order_the_cache_holds_under_its_txid(tmp_path, kill_trip_expected):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    cache = StubCache(closed_orders=[_closed_order(_TXID, OrderStatus.FILLED, filled_qty=0.0, venue_order_id=_TXID)])
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY))

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"][-1]["event"] == "withdrawn"
    assert f"order O-finished (Kraken {_TXID}) shows 0 filled at the venue" in _kill_file(tmp_path).read_text()


# --- the closed-order read: what the venue says about an order the restarted Cache cannot hold ------


@pytest.mark.parametrize(
    "status, venue_filled, state, events",
    [
        # The commonest closed-while-down shape: cancelled with no fill, so no delta, only the state.
        (OrderStatus.CANCELED, "0", "canceled", ["OrderAccepted"]),
        (OrderStatus.FILLED, "0.001", "filled", ["OrderAccepted", "reconciled"]),
    ],
)
def test_an_order_that_closed_while_down_is_read_at_the_venue_by_its_txid(tmp_path, status, venue_filled, state, events):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, status, filled_qty=venue_filled))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == state
    assert [e.get("type") or e.get("event") for e in row["events"]] == events
    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]


def test_a_closed_while_down_order_the_ledger_is_ahead_of_trips_the_kill_switch(tmp_path, kill_trip_expected):
    """The boot divergence latch on a closed order, which only the venue read can reach: the ledger
    says 0.0006 filled and the venue says the order ended with 0.0002."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0006)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0002"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "canceled"
    assert (
        f"adopted order O-reducer (Kraken {_TXID}) shows 0.0002 filled at the venue, less than the 0.0006"
        in _kill_file(tmp_path).read_text()
    )


def test_a_withdrawn_fill_on_a_finished_row_is_read_at_the_venue_by_its_txid(tmp_path, kill_trip_expected):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["events"][-1] == {"event": "withdrawn", "at": NOW.isoformat(), "qty": -0.001, "venue_filled_qty": 0.0}
    assert "shows 0 filled at the venue, less than the 0.001" in _kill_file(tmp_path).read_text()


def test_the_venue_is_read_once_from_the_earliest_row_that_needs_it_and_only_when_one_does(tmp_path):
    """No row needing it -- nothing ledgered, a row the Cache answers, a finished row with no fill --
    means no read and no second client. Rows that need it are answered by ONE read."""
    early, late = NOW - timedelta(hours=8), NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-cached", reduce_only=True, when=late, venue_order_id="OCACHE-D0000-000001")
    _submitted_row(tmp_path, "O-unfilled", reduce_only=False, when=early, index=1, venue_order_id="OUNFIL-LED00-000002")
    update_submitted_row(tmp_path / "journal", _boundary(early), "O-unfilled", state="canceled")
    cache = StubCache(open_orders=[_open_order("OCACHE-D0000-000001", venue_order_id="OCACHE-D0000-000001")])
    idle = _VenueOrders()
    _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=idle).on_timer(NOW)
    assert idle.calls == []

    _submitted_row(tmp_path, "O-closed", reduce_only=True, when=late, index=2, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=early, index=3, venue_order_id="OFINIS-HED00-000003")
    update_submitted_row(tmp_path / "journal", _boundary(early), "O-finished", state="filled", add_filled_qty=0.001)
    needed = _VenueOrders(
        _report(_TXID, OrderStatus.CANCELED), _report("OFINIS-HED00-000003", OrderStatus.FILLED, filled_qty="0.001")
    )
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=needed)
    ex.on_timer(NOW)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert needed.calls == [_boundary(early) - timedelta(hours=1)]


def test_a_failed_venue_read_leaves_the_rows_and_refuses_every_plan_for_the_life_of_the_process(tmp_path):
    """Fail closed without a trip: the rows keep what they say -- the open row the read was for and
    the finished one with fills alike, neither marked as a row the read has no order for -- the
    resting reducer the Cache still answers is classified as ever, the read is not repeated, and every
    plan is refused with the reason until a restart reads again."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-closed", reduce_only=True, when=earlier, venue_order_id=_TXID)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, index=1, venue_order_id="ORESTI-NG000-000001")
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, index=2, venue_order_id="OFINIS-HED00-000003")
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    before = _record(tmp_path, earlier)["submitted"]
    client = StubClient(StubCache(open_orders=[_resting_limit_order("ORESTI-NG000-000001", venue_order_id="ORESTI-NG000-000001")]))
    venue = _VenueOrders(raises=RuntimeError("EAPI:Invalid nonce"))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    with _executor_errors(level=logging.CRITICAL) as records:
        ex.on_timer(NOW)
        _drop_plan(tmp_path, _plan_dict())
        ex.on_timer(NOW + timedelta(seconds=5))

    reason = (
        "the startup reconciliation could not read the venue's orders, so 2 ledgered row(s) were never compared "
        "against venue truth -- restart the engine to retry"
    )
    assert [r.getMessage() for r in records] == [
        "the venue's orders could not be read at startup -- 2 ledgered row(s) were never compared against venue "
        "truth; every plan is refused until the engine is restarted",
        f"probe plan p-1 refused: {reason}",
    ]
    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]  # read once, never retried
    assert client.canceled == [] and "ORESTI-NG000-000001" in ex._attached  # the resting reducer is kept
    assert _record(tmp_path, earlier)["submitted"] == before
    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"]) == ("refused", [reason])
    assert client.submitted == [] and not _plan_path(tmp_path).exists()


# --- the executor's own holds, folded into the verdict it publishes -------------------------------


def _verdict(*, level):
    return GateVerdict(
        level=level,
        reasons=(),
        inputs={"armed_in_config": True, "arm_file": True, "kill_file": False, "restart_hold": False, "venue_status": "online"},
    )


def _unreconciled_executor(tmp_path):
    _submitted_row(tmp_path, "O-open", reduce_only=True, when=NOW - timedelta(hours=4), venue_order_id=_TXID)
    ex = _executor(tmp_path, venue_orders=_VenueOrders(raises=RuntimeError("down")))
    with _executor_errors(level=logging.CRITICAL):
        ex.on_timer(NOW)
    return ex


def test_an_unread_startup_reconciliation_reads_none_with_its_reason_in_the_published_verdict(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(publish_verdict=lambda verdict, **_: metrics.verdicts.append(verdict), metrics=metrics)
    ex = _unreconciled_executor(tmp_path)
    verdict = ex._evaluate(NOW)
    assert verdict.level == GateLevel.NONE and verdict.reasons[-1] == "reconciliation_unread"
    assert verdict.inputs["reconciliation_unread"] is True and metrics.verdicts[-1] is verdict


def test_the_boundary_re_journals_the_folded_verdict_over_the_sinks_bare_one(tmp_path):
    ex = _unreconciled_executor(tmp_path)
    write_exec_record(ex._journal_dir, _boundary(NOW), _verdict(level=GateLevel.FULL), evaluated_at=NOW)
    ex.on_boundary(_boundary(NOW))
    doc = read_exec_record(exec_record_path(ex._journal_dir, _boundary(NOW)))
    assert doc["level"] == "none" and "reconciliation_unread" in doc["reasons"]


def test_the_boundary_re_journal_publishes_the_readings_and_leaves_the_heartbeat_a_failed_sink_write_froze(tmp_path, monkeypatch):
    registry = CollectorRegistry()
    gauges = _ExecGauges(registry)
    gate = _gate(tmp_path)
    sink = _make_exec_sink(gate, tmp_path / "journal", None, gauges, None)
    earlier = NOW - timedelta(hours=4)
    sink(SimpleNamespace(cycle_ts=earlier), earlier, 1.0)
    set_executor_hooks(publish_verdict=gauges.update)
    ex = _executor(tmp_path, gate=gate)

    def _raise(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("cli.engine.command.write_exec_record", _raise)
    with pytest.raises(OSError):
        sink(SimpleNamespace(cycle_ts=_boundary(NOW)), NOW, 1.0)
    _kill_file(tmp_path).touch()  # what the re-journal's publish must carry, so it is read by value
    ex.on_boundary(_boundary(NOW))

    assert registry.get_sample_value("zcrypto_exec_kill_tripped") == 1
    assert registry.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == earlier.timestamp()


def test_a_day_loss_hold_on_a_level_already_none_leaves_it_none(tmp_path):
    ex = _unreconciled_executor(tmp_path)
    ex._day_loss_hold = True
    verdict = ex._evaluate(NOW)
    assert verdict.level == GateLevel.NONE and verdict.reasons[-2:] == ("reconciliation_unread", "daily_loss_hold")


# --- a row no venue order matches is marked ambiguous ---------------------------------------------

_NO_TXID = "no Kraken order id is recorded for it, so a restart cannot match it to a venue order"


def test_an_open_row_with_no_recorded_txid_is_marked_ambiguous_once(tmp_path):
    """A row written before the acceptance recorded a txid, or one whose order never got an
    acceptance: nothing can match it to the venue's orders, which name themselves by txid alone. It
    takes the ledger's own word for that, keeps pointing at a possibly-live order, and asks no venue
    read -- and a second restart does not mark it again."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-legacy", reduce_only=True, when=earlier)
    venue = _VenueOrders()

    with _executor_errors(level=logging.WARNING) as records:
        _executor(
            tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue
        ).on_timer(NOW)
        _executor(
            tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue
        ).on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "ambiguous"
    assert row["events"] == [{"type": "ambiguous", "at": NOW.isoformat(), "what": _NO_TXID}]
    assert [(r.levelname, r.getMessage()) for r in records] == 2 * [
        ("WARNING", f"ledgered order O-legacy matches no venue order -- {_NO_TXID}; its row is marked ambiguous")
    ]
    assert venue.calls == []


def test_a_finished_row_with_fills_and_no_recorded_txid_takes_the_mark_but_keeps_its_state(tmp_path):
    """Its order ended, so the state `ambiguous` -- "may be resting" -- would be false; what nobody can
    establish is only whether the venue withdrew a fill since. A finished row with no fill has none
    to withdraw and is not marked at all."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-filled", reduce_only=False, when=earlier)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-filled", state="filled", add_filled_qty=0.001)
    _submitted_row(tmp_path, "O-unfilled", reduce_only=False, when=earlier, index=1)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-unfilled", state="canceled")

    for _ in range(2):
        _executor(
            tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=_VenueOrders()
        ).on_timer(NOW)

    filled, unfilled = _record(tmp_path, earlier)["submitted"]
    assert filled["state"] == "filled"
    assert filled["events"] == [{"type": "ambiguous", "at": NOW.isoformat(), "what": _NO_TXID}]
    assert (unfilled["state"], unfilled["events"]) == ("canceled", [])


def test_a_row_whose_events_record_two_txids_vouches_for_neither_order(tmp_path):
    """Its acceptance names one Kraken order and a fill another, so the row matches neither: the
    reducer resting under the acceptance's txid is not kept on its word, no venue read is asked for
    it, and the mark says what the row records rather than that it records nothing."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-conflict", reduce_only=True, when=earlier, venue_order_id=_TXID)
    other = "OOTHER-ORDER-000009"
    fill = {"event": "fill", "at": earlier.isoformat(), "qty": 0.0004, "px": 30000.0, "venue_order_id": other}
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-conflict", event=fill, add_filled_qty=0.0004)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(_TXID, venue_order_id=_TXID)]))
    venue = _VenueOrders()

    for _ in range(2):
        _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue).on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == "ambiguous"
    assert [e for e in row["events"] if e.get("type") == "ambiguous"] == [
        {
            "type": "ambiguous",
            "at": NOW.isoformat(),
            "what": f"its events record 2 different Kraken order ids ({other}, {_TXID}), so a restart cannot tell "
            "which venue order is its own",
        }
    ]
    assert [str(cid) for cid in client.canceled] == [_TXID, _TXID]  # canceled as unledgered, by each process
    assert venue.calls == []


@pytest.mark.parametrize("finished", [False, True])
def test_a_row_whose_txid_the_venue_read_does_not_return_is_marked_ambiguous(tmp_path, finished):
    """The read skips an order row the adapter cannot parse, so an open row's order may still rest at
    Kraken beyond every cancel this process can issue, and its line is CRITICAL. A finished row's
    order ended, and its line stays a WARNING. Outside the restored set the mark leaves a finished
    row's intent to the ledger's figure."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-gone", reduce_only=True, when=earlier, venue_order_id=_TXID)
    if finished:
        update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-gone", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report("OOTHER-ORDER-000009", OrderStatus.CANCELED))

    with _executor_errors(level=logging.WARNING) as records:
        _executor(
            tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue
        ).on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], _intent_entry(tmp_path, 0, earlier)["outcome"]) == (
        ("filled", "filled") if finished else ("ambiguous", "pending")
    )
    assert row["events"][-1] == {"type": "ambiguous", "at": NOW.isoformat(), "what": f"the venue's order read has no order {_TXID}"}
    assert [(r.levelname, r.getMessage()) for r in records] == [
        (
            "WARNING" if finished else "CRITICAL",
            f"ledgered order O-gone matches no venue order -- the venue's order read has no order {_TXID}; its row is "
            "marked ambiguous",
        )
    ]
    assert len(venue.calls) == 1


@pytest.mark.parametrize("finished", [False, True])
@pytest.mark.parametrize(
    "status, resting",
    [
        (OrderStatus.ACCEPTED, True),  # Kraken's `open`
        (OrderStatus.INITIALIZED, True),  # Kraken's `pending`
        (OrderStatus.CANCELED, False),
    ],
)
def test_a_venue_report_still_resting_for_an_order_the_cache_lacks_is_logged_critical(tmp_path, finished, status, resting):
    """The Cache holds no order under the row's ids, yet the venue reports one still resting: startup
    reconciliation dropped it, and no cancel this process can issue reaches it. A report that ended
    says nothing of the kind."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-dropped", reduce_only=False, when=earlier, venue_order_id=_TXID)
    if finished:
        update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-dropped", state="canceled", add_filled_qty=0.0004)
    venue = _VenueOrders(_report(_TXID, status, filled_qty="0.0004" if finished else "0"))

    with _executor_errors(level=logging.CRITICAL) as records:
        _executor(
            tmp_path, client=StubClient(StubCache()), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue
        ).on_timer(NOW)

    assert [r.getMessage() for r in records] == (
        [
            f"ledgered order O-dropped (Kraken {_TXID}) rests at Kraken ({status.name}) but this process's Cache does not "
            "hold it, so neither the startup pass nor a kill trip can cancel it -- cancel it by hand on Kraken's "
            "open-orders page"
        ]
        if resting
        else []
    )
    assert not _kill_file(tmp_path).exists()


# --- read_venue_orders against a loopback venue: the wheel's own client, offline ----------------------


@pytest.fixture
def _loopback_credentials(monkeypatch):
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", kraken_loopback.API_KEY)
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", kraken_loopback.API_SECRET)


def test_read_venue_orders_returns_open_and_closed_orders_by_txid_with_no_client_order_id(_loopback_credentials):
    """The reader's whole contract on the pinned wheel, offline: the listing is cached first, so an
    order Kraken spells by its altname (`XBTEUR`) resolves; open and closed orders both come back;
    every report carries `client_order_id` None whatever `cl_ord_id` Kraken stored; and ClosedOrders
    is asked from `since`."""
    since = NOW - timedelta(hours=9)
    btc = {"price": "30000.0", "volume": "0.00100000", "side": "sell"}
    with kraken_loopback.serve() as venue:
        venue.open_orders["OOPENA-XBT00-000001"] = kraken_loopback.open_order("XBTEUR", **btc, cl_ord_id="O-120000-001-000-1")
        venue.closed_orders[_TXID] = kraken_loopback.closed_order(
            "XBTEUR", **btc, status="closed", vol_exec="0.00100000", cl_ord_id="O-080000-001-000-2"
        )
        venue.closed_orders["OCANCL-SOL00-000003"] = kraken_loopback.closed_order(
            "SOLEUR", price="50.00", volume="0.06000000", side="sell", cl_ord_id="O-080000-001-000-3"
        )
        reports = {str(r.venue_order_id): r for r in read_venue_orders(since, base_url=venue.base_url)}

    assert sorted(reports) == sorted(["OOPENA-XBT00-000001", _TXID, "OCANCL-SOL00-000003"])
    assert {txid: r.client_order_id for txid, r in reports.items()} == dict.fromkeys(reports)
    assert (reports[_TXID].order_status, float(reports[_TXID].filled_qty)) == (OrderStatus.FILLED, 0.001)
    assert str(reports[_TXID].instrument_id) == "BTC/EUR.KRAKEN"
    assert reports["OCANCL-SOL00-000003"].order_status == OrderStatus.CANCELED
    assert venue.closed_order_forms[0]["start"] == str(int(since.timestamp()))


def test_read_venue_orders_answers_past_a_closed_order_on_a_pair_the_listing_lacks(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.open_orders["OOPENA-XBT00-000001"] = kraken_loopback.open_order("XBTEUR", price="30000.0", volume="0.00100000")
        venue.closed_orders[_TXID] = kraken_loopback.closed_order("XBTEUR", price="30000.0", volume="0.00100000")
        venue.closed_orders["OUNLIS-ETH00-000004"] = kraken_loopback.closed_order("ETHEUR", price="1000.0", volume="0.01000000")
        txids = sorted(str(r.venue_order_id) for r in read_venue_orders(NOW - timedelta(hours=9), base_url=venue.base_url))

    assert txids == sorted(["OOPENA-XBT00-000001", _TXID])


def test_read_venue_orders_raises_past_its_bound(_loopback_credentials, monkeypatch):
    monkeypatch.setattr(executor_module, "_VENUE_READ_TIMEOUT_SECONDS", 0.5)
    with kraken_loopback.serve() as venue:
        venue.stalls["ClosedOrders"] = 3.0
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            read_venue_orders(NOW, base_url=venue.base_url)
        assert time.monotonic() - started < 2.5


def test_read_venue_orders_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        read_venue_orders(NOW, base_url="http://127.0.0.1:9")


def test_cancel_venue_order_sends_the_txid_on_the_real_client_and_returns_on_count_1_and_count_0_alike(_loopback_credentials):
    """The re-cancel's whole contract on the pinned wheel, offline: the listing is cached first, the
    cancel names the order by its txid alone, and the client returns on the venue's answer without
    reading its `count` -- so `_recancel` writes `canceled` on a `{"count": 0}`, the answer Kraken may
    give for an order gone between the read and the cancel, exactly as on a `{"count": 1}`."""
    with kraken_loopback.serve() as venue:
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)
        venue.cancel_count = 0
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)

    assert [form["txid"] for form in venue.cancel_forms] == [_TXID, _TXID]
    assert venue.private_calls[-1] == "CancelOrder"


def test_cancel_venue_order_raises_on_the_venues_refusal(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.errors["CancelOrder"] = "EOrder:Unknown order"
        with pytest.raises(Exception, match="Unknown order"):
            _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url=venue.base_url)
    assert venue.private_calls[-1] == "CancelOrder"  # the refusal came from the venue, not from the client


def test_cancel_venue_order_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        _cancel_venue_order(_TXID, "BTC/EUR.KRAKEN", base_url="http://127.0.0.1:9")


# --- read_venue_book and read_venue_holdings against the loopback, and the settle they feed at the two passes


def test_read_venue_holdings_answers_every_traded_symbol_with_its_margin_position_and_the_coins_spot_lot(_loopback_credentials):
    """The reader's contract on the pinned wheel, offline: the listing is cached first, so a position
    Kraken spells by its altname resolves; a margin position is signed by its side under its
    instrument; a traded coin's spot balance -- its total, the part held against a resting order
    included, under the code the adapter strips the venue's prefix to -- lands under the coin's EUR
    pair; and every basket symbol is answered, 0.0 where the account holds nothing. SOL's short
    against its held lot nets to zero by the total alone: the free part would read -0.01."""
    with kraken_loopback.serve() as venue:
        venue.positions["TPOSAA-BBBBB-CCCCC1"] = kraken_loopback.margin_position("XBTEUR", volume="0.00100000")
        venue.positions["TPOSAA-BBBBB-CCCCC2"] = kraken_loopback.margin_position("SOLEUR", volume="0.06000000", side="sell")
        venue.balances = {
            "XXBT": kraken_loopback.balance("0.0003000000"),
            "ZEUR": kraken_loopback.balance("100.0000"),
            "SOL": kraken_loopback.balance("0.0600000000", hold="0.0100000000"),
            "XXDG": kraken_loopback.balance("12.5000000000"),
        }
        held = _read_venue_holdings(base_url=venue.base_url)

    assert held == pytest.approx(dict.fromkeys(INSTRUMENT_IDS, 0.0) | {"BTC/EUR": 0.0013, "DOGE/EUR": 12.5})
    assert venue.private_calls == ["TradeVolume", "OpenPositions", "BalanceEx"]


def test_read_venue_holdings_reads_an_empty_positions_list_as_a_flat_margin_book_and_the_settle_publishes_the_coins_spot_lot(
    tmp_path, _loopback_credentials
):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    reads = []
    with kraken_loopback.serve() as venue:
        venue.balances = {"XXBT": kraken_loopback.balance("0.0003000000"), "ZEUR": kraken_loopback.balance("100.0000")}

        def _holdings():
            reads.append(executor_module.read_venue_book(base_url=venue.base_url))
            return reads[-1]

        ex = _executor(tmp_path, venue_holdings=_holdings)
        ex.on_timer(NOW)

    assert [book.held for book in reads] == [pytest.approx(dict.fromkeys(INSTRUMENT_IDS, 0.0) | {"BTC/EUR": 0.0003})]
    assert metrics.positions == sorted(reads[0].held.items())
    assert venue.private_calls == ["TradeVolume", "OpenPositions", "BalanceEx"]


def test_read_venue_holdings_refuses_without_credentials_before_building_a_client(monkeypatch):
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with pytest.raises(EngineError, match="the trade credentials are not in this environment"):
        _read_venue_holdings(base_url="http://127.0.0.1:9")


def test_read_venue_holdings_refuses_an_empty_instrument_listing_and_the_settle_publishes_nothing(tmp_path, _loopback_credentials):
    """An empty listing is a read through which no margin position resolves, not a flat margin book:
    the reader refuses it before any private call, and the startup pass's settle takes its failed-read
    arm, so the gauge keeps its reading. Read through, the spot lot alone would be published over a
    margin book nobody read."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    with kraken_loopback.serve(asset_pairs={}) as venue:
        venue.balances = {"XXBT": kraken_loopback.balance("0.0003000000")}
        ex = _executor(tmp_path, venue_holdings=lambda: _read_venue_holdings(base_url=venue.base_url))
        with _executor_errors(logging.WARNING) as warnings:
            ex.on_timer(NOW)

    assert (metrics.positions, venue.private_calls) == ([], [])
    assert [(r.getMessage(), str(r.exc_info[1])) for r in warnings if "holdings" in r.getMessage()] == [
        (
            "the venue's holdings could not be read at the startup pass -- the position gauge keeps its reading until the next pass",
            "the venue's instrument listing came back empty -- no margin position resolves through it",
        )
    ]


def test_read_venue_holdings_refuses_a_positions_answer_of_none_and_the_settle_publishes_nothing(tmp_path, monkeypatch):
    """`None` for the margin positions is a venue that answered nothing, not an account holding none,
    and `zcrypto engine flatten` refuses it for the same reason. The adapter answers the loopback with a
    list, so the flatten suite's registered stand-in for the client answers the `None` here; the reader
    refuses it before the balances are asked for, and the settle publishes nothing."""
    from test_engine_flatten import FakeClient, _Instrument

    client = FakeClient(instruments=[_Instrument("BTC/EUR")], positions=[None])
    monkeypatch.setattr(executor_module, "_bare_client", lambda base_url: client)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(tmp_path, venue_holdings=lambda: _read_venue_holdings(base_url="http://127.0.0.1:9"))
    with _executor_errors(logging.WARNING) as warnings:
        ex.on_timer(NOW)

    assert metrics.positions == []
    assert [name for name, _ in client.calls] == ["request_instruments", "request_position_status_reports"]
    assert [(r.getMessage(), str(r.exc_info[1])) for r in warnings if "holdings" in r.getMessage()] == [
        (
            "the venue's holdings could not be read at the startup pass -- the position gauge keeps its reading until the next pass",
            "the venue answered nothing for the margin positions -- it is never read as a flat margin book",
        )
    ]


def test_read_venue_book_totals_the_spot_eur_row_and_eur_m_and_the_spot_free_beside_the_holdings(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.balances["ZEUR"] = {"balance": "1000.0000", "hold_trade": "150.0000"}
        # EUR under an earn code: the mark's, never the budget's
        venue.balances["EUR.M"] = {"balance": "100.0000", "hold_trade": "0.0000"}
        # outside the mark until the owed read says what it holds
        venue.balances["EUR.HOLD"] = {"balance": "5.0000", "hold_trade": "0.0000"}
        venue.balances["XXBT"] = {"balance": "0.00100000", "hold_trade": "0.00000000"}
        venue.positions["TPOSAA-BBBBB-CCCCC1"] = kraken_loopback.margin_position("XBTEUR", volume="0.00200000")
        book = executor_module.read_venue_book(base_url=venue.base_url)
        held = executor_module.read_venue_holdings(base_url=venue.base_url)
    assert book.eur_total == 1100.0 and book.eur_free == 850.0
    assert book.held["BTC/EUR"] == pytest.approx(0.003) and book.balances["BTC"] == 0.001  # the margin long in held alone
    assert held == book.held


@pytest.mark.parametrize(
    ("earn", "spot", "base"),
    [("SOL.F", "SOL", "SOL"), ("XBT.M", "XXBT", "BTC"), ("XDG.F", "XXDG", "DOGE"), ("XRP.F", "XXRP", "XRP")],
)
def test_read_venue_book_keeps_a_basket_coins_earn_coded_balance_apart_and_the_draft_refuses_its_held(
    _loopback_credentials, earn, spot, base
):
    with kraken_loopback.serve() as venue:
        venue.balances[spot] = {"balance": "0.5000000000", "hold_trade": "0.0000000000"}
        venue.balances[earn] = {"balance": "2.0000000000", "hold_trade": "0.0000000000"}  # served by Kraken's own code
        book = executor_module.read_venue_book(base_url=venue.base_url)
        # the mark's figure, apart from held
        assert book.earn == {base: 2.0} and book.held[f"{base}/EUR"] == 0.5 and book.balances[base] == 0.5
        assert re.search(rf"2 {base} is held outside the spot wallet.*move it back to spot", book.earn_refusal() or "")
        del venue.balances[earn]
        assert executor_module.read_venue_book(base_url=venue.base_url).earn_refusal() is None


def test_every_basket_base_has_a_euro_pair_that_carries_its_spot_balance():
    # A base without one would have its lot unread, and the read says nothing about it.
    assert set(executor_module._SPOT_SYMBOL_BY_BASE) == {symbol.split("/")[0] for symbol in INSTRUMENT_IDS}


def test_the_startup_pass_keeps_a_hand_settled_lot_on_the_gauge_from_the_venues_holdings_until_the_engines_own_sale(tmp_path):
    """A hand settle of the engine's BTC/EUR long delivers the lot to the spot balance and the state
    machine refuses the settle's fill, so the Cache keeps the long and the account holds the lot until
    the engine's own sale."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    cache = StubCache()
    cache.set_position("BTC/EUR", 0.00026906)
    holdings = _VenueHoldings({"BTC/EUR": 0.00026906})
    ex = _executor(tmp_path, client=StubClient(cache), venue_holdings=holdings)
    with _executor_errors(logging.WARNING) as warnings:
        ex.on_timer(NOW)
    assert (metrics.positions, holdings.calls) == ([("BTC/EUR", 0.00026906)], 1)
    assert [r.getMessage() for r in warnings if "the venue holds" in r.getMessage()] == []

    cache.set_position("BTC/EUR", 0.0)
    ex._publish_fill(_fill("O-sale", 0.00026906, side="sell"))

    assert metrics.positions[-1] == ("BTC/EUR", 0.0)


def test_the_start_after_a_red_button_flatten_publishes_the_venues_holdings_flat_over_the_seeds_record(tmp_path):
    """The red button stops the engine before it places anything and writes no exec row, so the next
    start's seed republishes the pre-flatten record's positions while the rebuilt Cache holds none;
    the startup pass's holdings read publishes the flat book over the seed's figures, for every symbol
    the read answers, and logs no disagreement: the Cache and the venue agree, the seed alone was
    behind."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    holdings = _VenueHoldings({"BTC/EUR": 0.0, "ETH/EUR": 0.0})
    ex = _executor(tmp_path, client=StubClient(StubCache()), venue_holdings=holdings)

    ex.on_timer(NOW)

    assert (metrics.positions, holdings.calls) == ([("BTC/EUR", 0.0), ("ETH/EUR", 0.0)], 1)


def test_a_start_whose_journal_seeds_no_position_gives_the_gauge_every_basket_child_at_the_first_tick(tmp_path):
    registry = CollectorRegistry()
    exec_metrics = _ExecutionMetrics(registry)
    assert _seed_exec_positions(tmp_path / "journal") is None
    assert [s for s in INSTRUMENT_IDS if registry.get_sample_value("zcrypto_exec_position", {"symbol": s}) is not None] == []
    set_executor_hooks(metrics=exec_metrics)
    held = dict.fromkeys(INSTRUMENT_IDS, 0.0) | {"BTC/EUR": 0.001}
    ex = _executor(tmp_path, client=StubClient(StubCache()), venue_holdings=_VenueHoldings(held))

    ex.on_timer(NOW)

    assert {s: registry.get_sample_value("zcrypto_exec_position", {"symbol": s}) for s in INSTRUMENT_IDS} == held


def test_a_close_filled_while_the_engine_was_down_with_no_catch_up_reads_flat_from_the_venues_holdings_at_the_startup_pass(
    tmp_path,
):
    """The reduce-only close rested at Kraken through a crash-restart inside the gap and filled while
    the engine was down: the seed folds no `reconciled` line, so it republished the record's long, and
    the startup sweep repairs the row from the venue's report over a Cache rebuilt flat. The holdings
    read, made after that report's read and before any cancel, publishes the venue's flat book over
    the seed's long, and the row reads `filled` beside it."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-close", reduce_only=True, when=earlier, venue_order_id=_TXID)
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    holdings = _VenueHoldings({"BTC/EUR": 0.0})
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache()),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        venue_holdings=holdings,
    )

    ex.on_timer(NOW)

    assert (metrics.positions, len(venue.calls), holdings.calls) == ([("BTC/EUR", 0.0)], 1, 1)
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "filled"


def test_an_opposing_hand_trade_the_running_engine_refused_settles_from_the_venues_holdings_at_the_re_read_pass_and_the_next_fill_moves_from_that_figure(
    tmp_path,
):
    """The engine's long closed by an opposing trade on Kraken's page: the state machine refuses the
    EXTERNAL fill, the Cache keeps the long and the gauge with it. The next re-read pass -- a socket's
    return arms it here, a mint arms it too -- reads the venue flat, logs the disagreement and publishes
    the venue's figure; the engine's next fill on the instrument then moves the gauge from that figure
    through what the Cache took since, not from the long the Cache never let go: the Cache reads 0.002
    after a fresh 0.001 long, the gauge 0.001."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    cache = StubCache()
    holdings = _VenueHoldings({"BTC/EUR": 0.0})
    ex = _executor(tmp_path, client=StubClient(cache), venue_holdings=holdings)
    ex.on_timer(NOW)
    cache.set_position("BTC/EUR", 0.001)  # the engine's own long, which the hand trade then closes at the venue
    _reconnect(ex)
    with _executor_errors(logging.WARNING) as warnings:
        ex.on_timer(NOW + timedelta(seconds=5))
    assert (metrics.positions, holdings.calls) == ([("BTC/EUR", 0.0), ("BTC/EUR", 0.0)], 2)
    assert [r.getMessage() for r in warnings if "the venue holds" in r.getMessage()] == [
        "the venue holds 0.0 BTC/EUR where the Cache reads 0.001 -- the position gauge takes the venue's figure at the re-read pass"
    ]

    cache.set_position("BTC/EUR", 0.002)
    ex._publish_fill(_fill("O-next", 0.001))

    assert metrics.positions[-1] == ("BTC/EUR", pytest.approx(0.001))


def test_the_venues_holdings_failing_to_read_keeps_the_gauges_reading_and_logs_a_warning(tmp_path):
    """The venue unreachable at the startup pass: nothing is published, so the gauge keeps the seed's
    fold, and the WARNING says the next pass reads again; the pass's own order read is untouched."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    holdings = _VenueHoldings(raises=RuntimeError("dns"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), venue_holdings=holdings)

    with _executor_errors(logging.WARNING) as warnings:
        ex.on_timer(NOW)

    assert (metrics.positions, holdings.calls) == ([], 1)
    assert [r.getMessage() for r in warnings if "holdings" in r.getMessage()] == [
        "the venue's holdings could not be read at the startup pass -- the position gauge keeps its reading until the next pass"
    ]


def test_the_settle_keeps_the_book_it_read_and_reads_with_no_metrics_hook_installed(tmp_path):
    set_executor_hooks()
    holdings = _VenueHoldings({"BTC/EUR": 0.001}, eur_total=1000.0, eur_free=850.0)
    ex = _executor(tmp_path, venue_holdings=holdings)
    ex.on_timer(NOW)  # the startup pass's settle
    assert holdings.calls == 1 and ex._venue_book.eur_free == 850.0 and ex._venue_book.held["BTC/EUR"] == 0.001


def test_an_unmatched_external_fill_arms_the_re_read_pass_and_the_next_tick_settles_the_holdings(tmp_path):
    holdings = _VenueHoldings({"BTC/EUR": 0.5})
    ex, client, _ = _idle_executor(tmp_path)
    ex._venue_holdings = holdings
    ex.on_timer(NOW)  # the startup pass: one read
    ex.on_timer(NOW + executor_module._GATE_REFRESH)  # the idle refresh reads the gate armed
    _hold_in_cache(client, _resting_limit_order("O-hand"))  # the delivery helper reads the order from the Cache
    _deliver_external_event(ex, client, _fill("O-hand", 0.5, symbol="BTC/EUR", side="buy"))
    assert ex._reread_tries == 3
    ex.on_timer(NOW + executor_module._GATE_REFRESH + timedelta(seconds=5))
    assert holdings.calls == 2 and ex._reread_tries == 0


def test_an_unmatched_external_cancel_arms_nothing(tmp_path):
    ex, client, _ = _idle_executor(tmp_path)
    ex.on_timer(NOW)
    ex.on_timer(NOW + executor_module._GATE_REFRESH)  # armed, so only the event's kind keeps the pass unarmed
    _hold_in_cache(client, _resting_limit_order("O-hand"))
    _deliver_external_event(ex, client, _canceled("O-hand"))
    assert ex._reread_tries == 0


def test_an_unmatched_external_fill_arms_nothing_while_the_engine_is_disarmed(tmp_path):
    ex, client, _ = _idle_executor(tmp_path)
    (exec_dir(tmp_path) / ARM_FILE).unlink()  # disarmed, as the attended passes on the engine's key run it
    ex.on_timer(NOW)
    ex.on_timer(NOW + executor_module._GATE_REFRESH)  # the idle refresh reads the gate disarmed
    _hold_in_cache(client, _resting_limit_order("O-hand"))
    _deliver_external_event(ex, client, _fill("O-hand", 0.5, symbol="BTC/EUR", side="buy"))
    assert ex._reread_tries == 0


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
    """The settle's healthy path, proven quiet: the Cache position moves and nothing reaches
    `on_order_event`; a live settle arrives on the OTHER stream, where `_on_external_event`'s
    unmatched early return keeps it from the trip. No intent active, and no kill file."""
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

    ex.on_order_event(_canceled("O-1"))  # the venue's own cancel -> the reprice waits for a tick
    ex.on_quote(_quote(bid=30.0, ask=30.05))
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

    # The trip cancelled the resting order, and after the restart the venue says so: the row that
    # recorded its txid at acceptance is read at the venue, which the restarted Cache cannot answer.
    canceled = _VenueOrders(_report(str(_venue_order_id(client.last_order_id)), OrderStatus.CANCELED))
    restarted_client = StubClient()
    restarted = _executor(tmp_path, client=restarted_client, gate=_gate(tmp_path, GateLevel.NONE), venue_orders=canceled)
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
    ex.on_order_event(_canceled("O-1"))  # superseded by the reprice, once its tick arrives
    ex.on_quote(_quote(bid=30.0, ask=30.05))

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

    ex.on_order_event(_canceled(client.last_order_id))  # would reprice, once its tick arrives
    ex.on_quote(_quote())

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
    """One pair x grid pair, shaped to the no-peek invariant so `validate_record` ACCEPTS the fixture.

    Not a record the writer could have emitted: `content_hash` is a placeholder and `n_bars=400` is declared over
    a 90-day window, which is 540 bars on the 4h grid. Nothing these cases reach recomputes either. A test that
    does needs a fixture built by the writer's own arithmetic."""
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
    week-old fill, which is the one thing it refuses. The owner's opening holdings then follow the
    birth it minted, ten zero rows -- the book held nothing before its first fill."""
    _tracking_executor(tmp_path, at=at, **kwargs).on_boundary(at)
    birth = exec_dir(tmp_path) / executor_module.FIRST_FILL_FILE
    if birth.exists():
        _write_opening_holdings(tmp_path, datetime.fromisoformat(birth.read_text().strip()))


def _write_birth(tmp_path, at):
    """The birth record written by hand, as the entry's re-date writes it."""
    path = exec_dir(tmp_path) / executor_module.FIRST_FILL_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{at.isoformat()}\n")


def _write_opening_holdings(tmp_path, birth, **held):
    """The opening holdings stamped at `birth`: one row per basket base, `held`'s balance or 0.0, at the fixture's close."""
    rows = [
        {"base": base, "codes": [base], "balance": held.get(base, 0.0), "close": close} for base, close in _TRACK_CLOSES.items()
    ]
    # Spelled as the owner's procedures spell it, never through the module's constant: the owner installs it by hand.
    path = exec_dir(tmp_path) / "opening-holdings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": 1, "birth": birth.isoformat(), "rows": rows}))


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
    resting order and nothing in flight, reaches the executor and latches the kill file. No tick is
    driven here, so a trip hooked on the tick's `_evaluate` could not fire here -- and the kill file
    has no other producer in this construction."""
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
    away, so the opening slice is gone and `held` is short. Nothing on disk distinguishes that from
    a real breach, so it is refused by `_score_closed_week`'s birth-record arm -- which REPLACED
    asking whether the oldest surviving boundary carries a fill."""
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
    journal scans a day, and the idle tick is contracted to read no gate inside the refresh period
    (`_refresh_gate`); the three ticks here precede the period's first elapse from the executor's
    construction."""
    _journal_week(tmp_path, fills=_BREACH_FILLS, lead=6)
    gate = CountingGate()
    executor = _tracking_executor(tmp_path)
    executor._gate = gate

    for minute in range(3):
        executor.on_timer(_TRACK_EVAL + timedelta(minutes=minute))

    assert not _kill_file(tmp_path).exists()
    assert gate.calls == 0  # the three ticks fall before the first refresh


# The ramp an operator arming exactly ON a week boundary produces: the first slice lands at the
# week's own first boundary, the rest ten boundaries in -- an undeployed book averaged with a
# deployed one, which is the WEEK THE SERIES STARTED IN wearing a settled week's clothes.
_BOUNDARY_RAMP_FILLS = {
    _TRACK_MONDAY: [("BTC/EUR", "buy", 0.00042)],
    _IN_WEEK: [("BTC/EUR", "buy", 0.00290), *_NINE_LEGS],
}
# NOT the shared `_MINT_AT`, which predates this ramp's own first fill: with no birth record the
# birth arm refuses the week, and the week-start arm this fixture exists for is never reached.
_RAMP_MINT_AT = _TRACK_MONDAY + timedelta(hours=4)


def test_a_pruned_journal_head_refuses_instead_of_scoring_a_short_held(tmp_path):
    """The retention prune turns the true positive into a latched false kill, and this is that
    construction: the HEALTHY fixture -- the week that must pass -- with the two oldest boundaries
    deleted. The opening slice goes with them, `held` is short by it, and the journal reads a
    breach.

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
    the week the series started in. The WEEK-START arm refuses it, read off that arm's own message
    since every arm publishes `_TRACKING_UNSCORED`, and `>` for `>=` there latches the kill file."""
    _journal_week(tmp_path, fills=_BOUNDARY_RAMP_FILLS, lead=6)

    with _executor_errors(logging.WARNING) as records:
        tripped, states = _tracking_states(tmp_path, mint_at=_RAMP_MINT_AT)

    assert not tripped
    assert states == [executor_module._TRACKING_UNSCORED]
    refused = [m for m in (r.getMessage() for r in records) if "is not scored" in m]
    assert refused, "the scorer refused nothing -- the week was scored, or its refusal wording moved"
    # `[-1]`: `_tracking_states` mints inside this block, and that boundary refuses the week before.
    assert f"at or after {_TRACK_MONDAY:%G-W%V} began" in refused[-1], refused


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


def test_a_re_dated_birth_scores_the_series_from_it_and_reads_an_earlier_fill_as_a_prior_series(tmp_path):
    """`_journal_week(tmp_path, fills=..., lead=12)` with the healthy fixture's fills and, before them,
    a prior series' lone BTC/EUR sell of 0.01 at `_TRACK_MONDAY - timedelta(hours=40)` -- the shape the
    journal holds once the prune has taken a prior series' buys and not yet its sells -- and the birth
    record and its opening holdings, ten zero rows, written by hand at `_OPENING`, as the entry's
    re-date writes them, with no mint (`mint_at=None`): the week scores within the band. Read into
    `held`, the prior sell latches the kill at about 6046 bps against the 120 bps band; the base
    refuses the week on `birth != first_fill`."""
    prior = _TRACK_MONDAY - timedelta(hours=40)
    _journal_week(tmp_path, fills={prior: [("BTC/EUR", "sell", 0.01)], **_HEALTHY_FILLS}, lead=12)
    _write_birth(tmp_path, _OPENING)
    _write_opening_holdings(tmp_path, _OPENING)

    tripped, states = _tracking_states(tmp_path, mint_at=None)

    assert not tripped
    assert states == [executor_module._TRACKING_WITHIN_BAND]


def test_the_opening_holdings_start_held_at_the_birth_and_a_residual_held_there_is_not_drift(tmp_path):
    """The healthy build-out alone, `_journal_week(tmp_path, fills={_BUILD_OUT: _HEALTHY_FILLS[_BUILD_OUT]},
    lead=6)`, the birth written by hand at `_OPENING` and the opening holdings beside it carrying BTC 0.00042 --
    the residual Kraken held at the re-date, the slice the healthy fixture fills at `_OPENING`: the
    week scores within the band. Read from zero, the book is BTC 25.2 EUR short at every cycle, 298.4
    bps against the 120 bps band, and the kill latches -- the probe's reading."""
    _journal_week(tmp_path, fills={_BUILD_OUT: _HEALTHY_FILLS[_BUILD_OUT]}, lead=6)
    _write_birth(tmp_path, _OPENING)
    _write_opening_holdings(tmp_path, _OPENING, BTC=0.00042)

    tripped, states = _tracking_states(tmp_path, mint_at=None)

    assert not tripped
    assert states == [executor_module._TRACKING_WITHIN_BAND]


def test_an_absent_opening_holdings_record_or_one_stamped_for_another_birth_refuses_the_week(tmp_path):
    """The healthy journal with the birth written by hand at `_OPENING`: no record refuses the week
    naming the birth, and a record stamped four hours earlier refuses naming both instants; stamped
    at the birth, the week scores within the band."""
    _journal_week(tmp_path, fills=_HEALTHY_FILLS, lead=6)
    _write_birth(tmp_path, _OPENING)
    earlier = _OPENING - timedelta(hours=4)
    refusals = {
        None: f"no opening holdings are recorded for the series born at {_OPENING.isoformat()} -- the owner records them with the birth",
        earlier: f"the opening holdings were taken for the series born at {earlier.isoformat()}, not {_OPENING.isoformat()}",
    }
    for stamp, refusal in refusals.items():
        if stamp is not None:
            _write_opening_holdings(tmp_path, stamp)
        with _executor_errors(logging.WARNING) as records:
            tripped, states = _tracking_states(tmp_path, mint_at=None)
        assert not tripped and states == [executor_module._TRACKING_UNSCORED], stamp
        assert f"the most recently closed week is not scored: {refusal}" in [r.getMessage() for r in records]

    _write_opening_holdings(tmp_path, _OPENING)
    tripped, states = _tracking_states(tmp_path, mint_at=None)
    assert not tripped and states == [executor_module._TRACKING_WITHIN_BAND]


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


def test_a_late_fill_of_an_earlier_intent_on_the_same_instrument_does_not_trip_the_terminal_reconciliation(tmp_path):
    """Cycle N's sell of BTC/EUR, its row open, fills while cycle N+1's buy of BTC/EUR runs: the
    strategy-scoped position moves by the sell, which is in `actual` and not in the intent's own
    fills. Netted, the terminal reads clean; un-netted it latches the kill file."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="buy", notional_eur=30.0)])
    earlier = _submitted_row(
        tmp_path,
        "O-earlier",
        reduce_only=False,
        when=NOW - timedelta(hours=4),
        plan_id="r3-20261109-00",
        symbol="BTC/EUR",
        side="sell",
        qty=0.001,
    )
    ex._attach((_boundary(NOW - timedelta(hours=4)), earlier), "O-earlier", venue_order_id=None)
    client.cache.hold_strategy_order("O-earlier", strategy_id=client.strategy_id)
    _deliver_fill(ex, client, "O-earlier", 0.001, symbol="BTC/EUR", side="sell")
    _deliver_fill(ex, client, client.last_order_id, 0.001, symbol="BTC/EUR", side="buy")  # the active buy fills whole
    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


def test_a_late_fill_of_an_earlier_intent_on_another_instrument_is_not_netted(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="buy", notional_eur=30.0)])
    earlier = _submitted_row(
        tmp_path,
        "O-earlier",
        reduce_only=False,
        when=NOW - timedelta(hours=4),
        plan_id="r3-20261109-00",
        symbol="ETH/EUR",
        side="sell",
        qty=0.01,
    )
    ex._attach((_boundary(NOW - timedelta(hours=4)), earlier), "O-earlier", venue_order_id=None)
    client.cache.hold_strategy_order("O-earlier", strategy_id=client.strategy_id)  # so the instrument alone keeps it out
    _deliver_fill(ex, client, "O-earlier", 0.01, symbol="ETH/EUR", side="sell")
    _deliver_fill(ex, client, client.last_order_id, 0.001, symbol="BTC/EUR", side="buy")
    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


def test_a_fill_on_a_restored_external_copy_is_not_netted(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="buy", notional_eur=30.0)])
    earlier = _submitted_row(
        tmp_path,
        "O-earlier",
        reduce_only=False,
        when=NOW - timedelta(hours=4),
        plan_id="r3-20261109-00",
        symbol="BTC/EUR",
        side="sell",
        qty=0.001,
        venue_order_id=_TXID,
    )
    ex._attach((_boundary(NOW - timedelta(hours=4)), earlier), _TXID, venue_order_id=_TXID)
    client.cache.hold_strategy_order(_TXID, strategy_id=StrategyId("EXTERNAL"), venue_order_id=_TXID)
    client.cache.set_external_position("BTC/EUR", -0.001)  # the copy's fill books under EXTERNAL, not this strategy
    ex.on_external_order_event(
        _fill(_TXID, 0.001, side="sell", venue_order_id=VenueOrderId(_TXID), strategy_id=StrategyId("EXTERNAL"))
    )
    _deliver_fill(ex, client, client.last_order_id, 0.001, symbol="BTC/EUR", side="buy")
    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


def test_a_late_fill_of_the_running_intents_superseded_order_is_credited_once_and_not_netted(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, bid=30.0, ask=30.05)
    client.cache.hold_strategy_order("O-1", strategy_id=client.strategy_id)  # so `_claims` alone keeps its late fill out
    ex.on_order_event(_accepted("O-1"))
    _deliver_fill(ex, client, "O-1", 0.4, px=30.0)
    ex.on_order_event(_canceled("O-1"))
    _deliver_fill(ex, client, "O-1", 0.6, px=30.0)

    ex.on_quote(_quote(bid=30.0, ask=30.05))

    intent = _intent_entry(tmp_path, 0)
    assert (intent["outcome"], intent["filled_qty"]) == ("filled", 1.0)
    assert not _kill_file(tmp_path).exists()


def test_a_late_fill_of_an_earlier_intent_whose_cache_order_cannot_be_read_is_not_netted_and_trips_the_terminal(
    tmp_path, kill_trip_expected
):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="buy", notional_eur=30.0)])
    earlier = _submitted_row(
        tmp_path,
        "O-earlier",
        reduce_only=False,
        when=NOW - timedelta(hours=4),
        plan_id="r3-20261109-00",
        symbol="BTC/EUR",
        side="sell",
        qty=0.001,
    )
    ex._attach((_boundary(NOW - timedelta(hours=4)), earlier), "O-earlier", venue_order_id=None)
    with _executor_errors(logging.WARNING) as records:
        _deliver_fill(ex, client, "O-earlier", 0.001, symbol="BTC/EUR", side="sell")
        _deliver_fill(ex, client, client.last_order_id, 0.001, symbol="BTC/EUR", side="buy")
    assert [r.getMessage() for r in records if r.levelno == logging.WARNING and "O-earlier" in r.getMessage()] != []
    assert _kill_file(tmp_path).exists()


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
    hold one: the executor (through the handle `self._cache` taken at construction, and the local
    `cache` it aliases it to) and the venue-state reader (through its `cache` argument). Derived
    rather than listed, for the same reason the client surface is."""
    reached: set[str] = set()
    for module in (executor_module, venuestate_module):
        tree = ast.parse(Path(module.__file__).read_text())
        for n in ast.walk(tree):
            if not isinstance(n, ast.Attribute):
                continue
            holder = n.value
            if (isinstance(holder, ast.Attribute) and holder.attr in ("cache", "_cache")) or (
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
    `.currency.code` for its denomination -- pinned by VALUE rather than by a name-existence walk.
    Only `_fee_eur`'s currency read is `getattr`-wrapped; its amount read and both of
    `_fill_payload`'s are bare, so a dropped accessor raises rather than quietly defaulting.

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
        "hold_strategy_order",
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


# --- the tracking read validates what it keeps, and refuses what it orders (T0194) ----------------
# Two fixes met in `_cycle_records_through` and the first review of them missed that they collide: the
# `cycle_ts <= until` filter moved ABOVE `validate_record` so an artifact no pass will score cannot refuse every
# pass, and the filter orders two stamps, which on a naive `cycle_ts` raised TypeError straight past the
# `except EngineError` the caller holds. Both halves are asserted here; neither was, and restoring the pre-fix
# ordering exactly left the suite green.


def _journal_with(tmp_path, boundary, *, mangle=None):
    """One `cycle-<HH>.json` under a day directory, optionally mangled after serialisation."""
    from cli.engine.executor import _cycle_records_through  # noqa: PLC0415 -- the private reader IS the subject

    record = CycleRecord(
        schema_version=2,
        cycle_ts=boundary,
        snapshots=_track_snapshots(boundary),
        final_targets={"BTC/EUR": 0.1},
        started_at=boundary + timedelta(seconds=90),
        completed_at=boundary + timedelta(minutes=2),
        code_version="1.0.0",
        builder_path="fast",
    )
    journal = tmp_path / "journal"
    day = journal / f"{boundary:%Y-%m-%d}"
    day.mkdir(parents=True, exist_ok=True)
    text = to_json(record)
    if mangle is not None:
        text = mangle(text)
    (day / f"cycle-{boundary:%H}.json").write_text(text)
    return journal, _cycle_records_through


def _drop_snapshots(text: str) -> str:
    """A record that loads and does not validate: `snapshots` emptied, which validate_record refuses."""
    payload = json.loads(text)
    payload["snapshots"] = []
    return json.dumps(payload)


def test_an_invalid_record_outside_the_window_does_not_refuse_the_pass(tmp_path):
    """The reorder's point. One schema-invalid artifact from a week nothing will ever score used to refuse every
    later scoring pass, and the refusal lands as a WARNING with no alert rule behind it."""
    boundary = datetime(2026, 7, 10, 4, tzinfo=timezone.utc)
    journal, reader = _journal_with(tmp_path, boundary, mangle=_drop_snapshots)
    assert reader(journal, boundary - timedelta(hours=4)) == {}


def test_an_invalid_record_inside_the_window_refuses_the_pass(tmp_path):
    """The other half: a record this pass WILL score is validated, and its refusal propagates, because `_stage`
    reads final, closes and nav straight out of it on the live trade path."""
    boundary = datetime(2026, 7, 10, 4, tzinfo=timezone.utc)
    journal, reader = _journal_with(tmp_path, boundary, mangle=_drop_snapshots)
    with pytest.raises(EngineJournalError, match="snapshots"):
        reader(journal, boundary)


def test_a_naive_cycle_ts_is_refused_with_this_modules_error_not_a_typeerror(tmp_path):
    """The collision the second read found: the filter orders `cycle_ts` against an aware boundary BEFORE
    validate_record can see it, so a naive stamp escaped as TypeError past the caller's `except EngineError`.
    The reader refuses it first, with the error the caller handles."""
    boundary = datetime(2026, 7, 10, 4, tzinfo=timezone.utc)

    def naive_cycle_ts(text: str) -> str:
        payload = json.loads(text)
        payload["cycle_ts"] = boundary.replace(tzinfo=None).isoformat()
        return json.dumps(payload)

    journal, reader = _journal_with(tmp_path, boundary, mangle=naive_cycle_ts)
    with pytest.raises(EngineJournalError, match="timezone-aware"):
        reader(journal, boundary)


# --- the cache's restored orders and positions (spec 00120 D6 to D10, D12) ------------------------


def _cache_config(tmp_path, enabled=True):
    return _config(tmp_path, cache=CacheSettings(enabled=enabled))


def _restored_order(client_order_id="O-restored", *, filled=None, quantity="0.001"):
    """The Cache's copy of an order a previous process placed, restored under this engine's own id and
    the txid it recorded, with the previous process's fills applied when `filled` is given."""
    order = _resting_limit_order(client_order_id, quantity=quantity, venue_order_id=_TXID)
    if filled is not None:
        order.apply(_fill(client_order_id, filled, venue_order_id=VenueOrderId(_TXID), trade_id="T-before"))
    return order


@pytest.mark.parametrize("enabled", [True, False])
def test_the_restored_set_is_every_order_the_cache_holds_at_construction_only_with_the_cache_enabled(tmp_path, enabled):
    external = _resting_limit_order("OEXTRN-AAAAA-BBBBBB", venue_order_id="OEXTRN-AAAAA-BBBBBB", strategy_id=StrategyId("EXTERNAL"))
    client = StubClient(StubCache(open_orders=[_restored_order(), external]))

    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path, enabled))

    assert ex._restored == ({"O-restored": _TXID, "OEXTRN-AAAAA-BBBBBB": "OEXTRN-AAAAA-BBBBBB"} if enabled else {})


def test_a_restored_set_the_cache_cannot_read_leaves_every_row_to_the_venue_and_refuses_every_plan(tmp_path):
    class _Unreadable(StubCache):
        def orders(self, *, venue=None, strategy_id=None, **kwargs):
            raise RuntimeError("cache read failed")

    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", add_filled_qty=0.0004)
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006"))
    with _executor_errors(level=logging.CRITICAL) as records:
        ex = _executor(
            tmp_path,
            client=StubClient(_Unreadable(open_orders=[_restored_order(filled=0.0008)])),
            gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
            venue_orders=venue,
            config=_cache_config(tmp_path),
        )

    assert ex._restored == {} and ex._reconciliation_refusal is not None
    assert [r.getMessage() for r in records] == [
        "the restored orders could not be read at start -- every ledgered row is read at the venue as a restored one, "
        "and every plan is refused until the engine is restarted"
    ]

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], venue.calls) == (pytest.approx(0.0006), [_boundary(earlier) - timedelta(hours=1)])


@pytest.mark.parametrize(
    "enabled, filled_qty, events",
    [(True, 0.0006, ["OrderAccepted", "reconciled"]), (False, 0.0004, ["OrderAccepted"])],
)
def test_the_startup_pass_asks_the_venue_over_a_restored_orders_cache_copy_and_the_report_wins(
    tmp_path, enabled, filled_qty, events
):
    """The Cache's copy is the previous process's view, 0.0004 filled, and the ledger agrees with it;
    the venue says 0.0006. With the cache enabled the venue is read and its figure repairs the row;
    without it the Cache's copy answers as before and no venue read is made."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", add_filled_qty=0.0004)
    client = StubClient(StubCache(open_orders=[_restored_order(filled=0.0004)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006"))
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path, enabled),
    )

    ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], [e.get("type") or e.get("event") for e in row["events"]]) == (filled_qty, events)
    assert venue.calls == ([_boundary(earlier) - timedelta(hours=1)] if enabled else [])
    assert client.canceled == []  # a ledgered reducer, kept on both settings


def test_a_restored_order_the_venue_reports_closed_has_its_row_written_from_the_report_and_no_cancel_sent(tmp_path):
    """Mass status reads open orders only, so an order that filled while the engine was down comes back
    open in the Cache; the venue's report writes the row, settles the intent through the sweep, and the
    stale open copy is left where it is with no cancel through the handle."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("filled", 0.001)
    assert client.canceled == [] and "O-restored" in ex._attached
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "filled"
    assert metrics.orders == ["filled"]
    assert "restored order O-restored is filled at the venue -- its stale open copy stays in the Cache and no cancel is sent" in [
        r.getMessage() for r in records
    ]


def test_a_restored_orders_stale_open_copy_is_not_cancelled_at_a_later_restart_once_its_row_is_closed(tmp_path):
    """The restart after the one that wrote the row terminal: the row is among the window's closed
    rows, the Cache still lists the copy open, and the classification loop sends it no cancel."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.001)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert client.canceled == [] and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert "restored order O-restored is filled at the venue -- its stale open copy stays in the Cache and no cancel is sent" in [
        r.getMessage() for r in records
    ]
    assert not _kill_file(tmp_path).exists()


@pytest.mark.parametrize(
    "strategy_id, state, filled, status",
    [
        ("EXTERNAL", "filled", 0.001, OrderStatus.FILLED),
        ("EXTERNAL", "canceled", None, OrderStatus.CANCELED),
        (None, "canceled", None, OrderStatus.CANCELED),
    ],
    ids=["external-filled", "external-canceled-unfilled", "own-canceled-unfilled"],
)
def test_a_restored_copy_the_venue_holds_closed_is_sent_no_cancel_at_a_later_restart_whatever_its_id(
    tmp_path, strategy_id, state, filled, status
):
    earlier = NOW - timedelta(hours=4)
    cid = "O-restored" if strategy_id is None else _TXID
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state=state, add_filled_qty=filled or 0.0)
    copy = _resting_limit_order(
        cid, venue_order_id=_TXID, strategy_id=_STUB_STRATEGY_ID if strategy_id is None else StrategyId(strategy_id)
    )
    client = StubClient(StubCache(open_orders=[copy]))
    venue = _VenueOrders(_report(_TXID, status, filled_qty=str(filled or 0)))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert client.canceled == [] and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert f"restored order {cid} is {state} at the venue -- its stale open copy stays in the Cache and no cancel is sent" in [
        r.getMessage() for r in records
    ]
    assert not _kill_file(tmp_path).exists()


def test_a_restored_row_the_order_read_failed_for_stays_unread_and_the_next_restart_trips_nothing(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0006)
    reads = (
        _VenueOrders(raises=RuntimeError("timed out")),
        _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006")),
    )
    for restart, venue in enumerate(reads):
        client = StubClient(StubCache(open_orders=[_restored_order("O-reducer", filled=0.0008)]))
        ex = _executor(
            tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
        )

        with _executor_errors(level=logging.CRITICAL):
            ex.on_timer(NOW + timedelta(minutes=restart))

        row = _record(tmp_path, earlier)["submitted"][0]
        reconciled = [e for e in row["events"] if e.get("event") == "reconciled"]
        assert (row["filled_qty"], reconciled, client.canceled) == (0.0006, [], []), restart
        assert "O-reducer" in ex._attached and not _kill_file(tmp_path).exists(), restart


def test_a_restored_row_without_a_txid_is_read_by_its_copys_txid_and_settled_from_the_report(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-open", reduce_only=False, when=earlier)
    reads = []
    for restart in range(2):
        client = StubClient(StubCache(closed_orders=[_restored_order("O-open", filled=0.001)]))
        venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
        ex = _executor(
            tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
        )

        ex.on_timer(NOW + timedelta(minutes=restart))

        row = _record(tmp_path, earlier)["submitted"][0]
        types = [e.get("type") or e.get("event") for e in row["events"]]
        assert (row["state"], row["filled_qty"], types) == ("filled", 0.001, ["reconciled"]), restart
        assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "filled", restart
        assert client.canceled == [] and not _kill_file(tmp_path).exists(), restart
        reads.append(venue.calls)
    assert reads[0] == [_boundary(earlier) - timedelta(hours=1)]


def _unaccepted_order(client_order_id):
    head = (_TRADER_ID, _STUB_STRATEGY_ID, InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]), ClientOrderId(client_order_id))
    order = LimitOrder(
        *head, OrderSide.BUY, Quantity.from_str("0.001"), Price.from_str("30000.0"), TimeInForce.GTC,
        False, False, False, UUID4(), 0,
    )  # fmt: skip
    order.apply(OrderSubmitted(*head, _ACCOUNT_ID, UUID4(), 0, 0))
    assert order.venue_order_id is None
    return order


def test_a_restored_row_with_no_txid_anywhere_is_marked_ambiguous_at_warning(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier)
    client = StubClient(StubCache(open_orders=[_unaccepted_order("O-reducer")]))
    venue = _VenueOrders()
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    marks = [e["what"] for e in row["events"] if e.get("type") == "ambiguous"]
    assert (row["state"], row["filled_qty"], marks, venue.calls) == ("ambiguous", 0.0, [_NO_TXID], [])
    line = f"ledgered order O-reducer matches no venue order -- {_NO_TXID}; its row is marked ambiguous"
    assert [r.levelname for r in records if r.getMessage() == line] == ["WARNING"]


@pytest.mark.parametrize("venue_order_id", [None, _TXID], ids=["the-copys-txid", "the-rows-txid"])
def test_a_restored_row_a_good_read_omits_is_marked_ambiguous_at_critical_and_never_repaired(tmp_path, venue_order_id):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=venue_order_id)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0006)
    client = StubClient(StubCache(open_orders=[_restored_order("O-reducer", filled=0.0008)]))
    venue = _VenueOrders()
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    row = _record(tmp_path, earlier)["submitted"][0]
    reconciled = [e for e in row["events"] if e.get("event") == "reconciled"]
    marks = [e["what"] for e in row["events"] if e.get("type") == "ambiguous"]
    what = f"the venue's order read has no order {_TXID}"
    assert (row["state"], row["filled_qty"], reconciled, marks) == ("ambiguous", 0.0006, [], [what])
    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    line = f"ledgered order O-reducer matches no venue order -- {what}; its row is marked ambiguous"
    assert [r.levelname for r in records if r.getMessage() == line] == ["CRITICAL"]
    assert client.canceled == [] and not _kill_file(tmp_path).exists()

    fill = _fill("O-reducer", 0.0001, venue_order_id=VenueOrderId(_TXID), trade_id="T-after")
    client.cache.order(ClientOrderId("O-reducer")).apply(fill)
    ex.on_order_event(fill)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert len(venue.calls) == 1  # the re-read pass the fill armed leaves the marked row out


def test_a_restored_row_marked_under_its_copys_txid_is_left_out_of_the_re_read_pass(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier)
    copy = _restored_order("O-reducer")
    copy.apply(_event(OrderCanceled, client_order_id="O-reducer", reconciliation=True))
    client = StubClient(StubCache(closed_orders=[copy]))
    venue = _VenueOrders()
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    ex.on_timer(NOW)
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], [e["what"] for e in row["events"] if e.get("type") == "ambiguous"]) == (
        "ambiguous",
        [f"the venue's order read has no order {_TXID}"],
    )

    _reconnect(ex)
    ex.on_timer(NOW + timedelta(seconds=5))

    assert len(venue.calls) == 1


# --- the one door: a restored row read by `_read_id` and answered by the venue's report alone ---------

_OTHER_TXID = "OOTHER-ORDER-000009"
_ANCHOR_TXID = "OANCHR-ORDER-000001"
_EXTERNAL = StrategyId("EXTERNAL")

# ledger, txid, read, pass -> outcome, state, filled_qty, the mark's level, the intent; the case below builds each label.
_ONE_DOOR_MATRIX = [
    ("open", "recorded", "answers", "startup", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "recorded", "omits", "startup", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "recorded", "fails", "startup", "unread", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "answers", "startup", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "copys", "omits", "startup", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "copys", "fails", "startup", "unread", "accepted", 0.0004, None, "pending"),
    ("open", "none", "omits", "startup", "marked", "ambiguous", 0.0004, "WARNING", "pending"),
    ("open", "none", "fails", "startup", "marked", "ambiguous", 0.0004, "WARNING", "pending"),
    ("open", "two", "answers", "startup", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "two", "omits", "startup", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "two", "fails", "startup", "unread", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "answers", "startup", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "differs", "omits", "startup", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "differs", "fails", "startup", "unread", "accepted", 0.0004, None, "pending"),
    ("finished", "recorded", "answers", "startup", "applied", "filled", 0.001, None, "pending"),
    ("finished", "recorded", "omits", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "recorded", "fails", "startup", "unread", "filled", 0.001, None, "pending"),
    ("finished", "copys", "answers", "startup", "applied", "filled", 0.001, None, "pending"),
    ("finished", "copys", "omits", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "copys", "fails", "startup", "unread", "filled", 0.001, None, "pending"),
    ("finished", "none", "omits", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "none", "fails", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "two", "answers", "startup", "applied", "filled", 0.001, None, "pending"),
    ("finished", "two", "omits", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "two", "fails", "startup", "unread", "filled", 0.001, None, "pending"),
    ("finished", "differs", "answers", "startup", "applied", "filled", 0.001, None, "pending"),
    ("finished", "differs", "omits", "startup", "marked", "filled", 0.001, "WARNING", "pending"),
    ("finished", "differs", "fails", "startup", "unread", "filled", 0.001, None, "pending"),
    ("open", "recorded", "answers", "re-read", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "recorded", "omits", "re-read", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "recorded", "fails", "re-read", "unread", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "answers", "re-read", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "copys", "omits", "re-read", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "copys", "fails", "re-read", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "two", "answers", "re-read", "applied", "accepted", 0.0006, None, "pending"),
    ("open", "two", "omits", "re-read", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "two", "fails", "re-read", "unread", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "answers", "re-read", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "differs", "omits", "re-read", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "differs", "fails", "re-read", "unread", "ambiguous", 0.0004, None, "pending"),
    ("finished", "recorded", "answers", "re-read", "applied", "canceled", 0.0006, None, "revoked"),
    ("finished", "recorded", "omits", "re-read", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("finished", "recorded", "fails", "re-read", "unread", "canceled", 0.0004, None, "pending"),
    ("finished", "two", "answers", "re-read", "applied", "canceled", 0.0006, None, "revoked"),
    ("finished", "two", "omits", "re-read", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("finished", "two", "fails", "re-read", "unread", "canceled", 0.0004, None, "pending"),
    ("finished", "recorded", "answers", "restart", "applied", "canceled", 0.0006, None, "revoked"),
    ("finished", "recorded", "omits", "restart", "marked", "canceled", 0.0, "WARNING", "pending"),
    ("finished", "recorded", "fails", "restart", "unread", "canceled", 0.0, None, "pending"),
    ("finished", "two", "answers", "restart", "applied", "canceled", 0.0006, None, "revoked"),
    ("finished", "two", "omits", "restart", "marked", "canceled", 0.0, "WARNING", "pending"),
    ("finished", "two", "fails", "restart", "unread", "canceled", 0.0, None, "pending"),
    ("open", "recorded", "fails", "ledger-fails", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "fails", "ledger-fails", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "none", "fails", "ledger-fails", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "two", "fails", "ledger-fails", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "fails", "ledger-fails", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "answers", "early-terminal", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "recorded", "omits", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "recorded", "fails", "early-terminal", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "answers", "early-terminal", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "copys", "omits", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "copys", "fails", "early-terminal", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "none", "omits", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "none", "fails", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "two", "answers", "early-terminal", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "two", "omits", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "two", "fails", "early-terminal", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "answers", "early-terminal", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "differs", "omits", "early-terminal", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "differs", "fails", "early-terminal", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "answers", "fill-after-answer", "applied", "canceled", 0.0006, None, "pending"),
    ("open", "copys", "answers", "fill-after-answer", "applied", "canceled", 0.0006, None, "pending"),
    ("open", "two", "answers", "fill-after-answer", "applied", "canceled", 0.0006, None, "pending"),
    ("open", "differs", "answers", "fill-after-answer", "applied", "canceled", 0.0006, None, "pending"),
    ("open", "recorded", "below-short", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "startup", "covered", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "below-short", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "below-unread", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "below-covered", "startup", "covered", "accepted", 0.0004, None, "pending"),
    ("open", "two", "below-short", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "two", "below-unread", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "two", "below-covered", "startup", "covered", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "below-short", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "below-unread", "startup", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "below-covered", "startup", "covered", "accepted", 0.0004, None, "pending"),
    ("finished", "recorded", "below-unread", "startup", "refuted", "filled", 0.001, None, "pending"),
    ("finished", "recorded", "below-covered", "startup", "covered", "filled", 0.001, None, "filled"),
    ("finished", "copys", "below-unread", "startup", "refuted", "filled", 0.001, None, "pending"),
    ("finished", "copys", "below-covered", "startup", "covered", "filled", 0.001, None, "filled"),
    ("finished", "two", "below-unread", "startup", "refuted", "filled", 0.001, None, "pending"),
    ("finished", "two", "below-covered", "startup", "covered", "filled", 0.001, None, "filled"),
    ("finished", "differs", "below-unread", "startup", "refuted", "filled", 0.001, None, "pending"),
    ("finished", "differs", "below-covered", "startup", "covered", "filled", 0.001, None, "filled"),
    ("open", "recorded", "below-short", "re-read", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "re-read", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "re-read", "covered", "accepted", 0.0004, None, "pending"),
    ("open", "copys", "below-short", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-unread", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-covered", "re-read", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "two", "below-short", "re-read", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "two", "below-unread", "re-read", "refuted", "accepted", 0.0004, None, "pending"),
    ("open", "two", "below-covered", "re-read", "covered", "accepted", 0.0004, None, "pending"),
    ("open", "differs", "below-short", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-unread", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-covered", "re-read", "covered", "canceled", 0.0004, None, "revoked"),
    ("finished", "recorded", "below-short", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("finished", "recorded", "below-unread", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("finished", "recorded", "below-covered", "re-read", "covered", "canceled", 0.0004, None, "revoked"),
    ("finished", "two", "below-short", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("finished", "two", "below-unread", "re-read", "refuted", "canceled", 0.0004, None, "pending"),
    ("finished", "two", "below-covered", "re-read", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "recorded", "below-short", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "early-terminal", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "copys", "below-short", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-unread", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-covered", "early-terminal", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "two", "below-short", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-unread", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-covered", "early-terminal", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "differs", "below-short", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-unread", "early-terminal", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-covered", "early-terminal", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "recorded", "answers", "minted-before", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "recorded", "omits", "minted-before", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "recorded", "fails", "minted-before", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "recorded", "below-short", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "minted-before", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "copys", "answers", "minted-before", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "copys", "omits", "minted-before", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "copys", "fails", "minted-before", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "copys", "below-short", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-unread", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-covered", "minted-before", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "two", "answers", "minted-before", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "two", "omits", "minted-before", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "two", "fails", "minted-before", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "two", "below-short", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-unread", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-covered", "minted-before", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "differs", "answers", "minted-before", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "differs", "omits", "minted-before", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "differs", "fails", "minted-before", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "differs", "below-short", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-unread", "minted-before", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-covered", "minted-before", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "recorded", "answers", "reconnect", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "recorded", "omits", "reconnect", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "recorded", "fails", "reconnect", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "recorded", "below-short", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "reconnect", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "copys", "answers", "reconnect", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "copys", "omits", "reconnect", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "copys", "fails", "reconnect", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "copys", "below-short", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-unread", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "copys", "below-covered", "reconnect", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "two", "answers", "reconnect", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "two", "omits", "reconnect", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "two", "fails", "reconnect", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "two", "below-short", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-unread", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "two", "below-covered", "reconnect", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "differs", "answers", "reconnect", "recancelled", "canceled", 0.0006, None, "revoked"),
    ("open", "differs", "omits", "reconnect", "marked", "ambiguous", 0.0004, "CRITICAL", "pending"),
    ("open", "differs", "fails", "reconnect", "unread", "ambiguous", 0.0004, None, "pending"),
    ("open", "differs", "below-short", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-unread", "reconnect", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "differs", "below-covered", "reconnect", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "recorded", "answers", "minted-external", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "recorded", "omits", "minted-external", "marked", "canceled", 0.0004, "CRITICAL", "pending"),
    ("open", "recorded", "fails", "minted-external", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-short", "minted-external", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "minted-external", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "minted-external", "covered", "canceled", 0.0004, None, "revoked"),
    ("open", "recorded", "answers", "early-external", "applied", "canceled", 0.0006, None, "revoked"),
    ("open", "recorded", "omits", "early-external", "marked", "canceled", 0.0004, "WARNING", "pending"),
    ("open", "recorded", "fails", "early-external", "unread", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-short", "early-external", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-unread", "early-external", "refuted", "canceled", 0.0004, None, "pending"),
    ("open", "recorded", "below-covered", "early-external", "covered", "canceled", 0.0004, None, "revoked"),
]

_ONE_DOOR_TXIDS = ("recorded", "copys", "none", "two", "differs")
_ONE_DOOR_BELOW = ("below-short", "below-unread", "below-covered")
_ONE_DOOR_READS = ("answers", "omits", "fails", *_ONE_DOOR_BELOW)
_ONE_DOOR_PASSES = (
    "startup",
    "re-read",
    "restart",
    "ledger-fails",
    "early-terminal",
    "fill-after-answer",
    "minted-before",
    "reconnect",
    "minted-external",
    "early-external",
)
_ONE_DOOR_DROPPED = {
    **{
        (ledger, "none", read, "startup"): "a row with no txid anywhere has no report a read could answer with"
        for ledger in ("open", "finished")
        for read in ("answers", *_ONE_DOOR_BELOW)
    },
    **{
        ("open", "none", read, "re-read"): (
            "marked at startup, and the filter leaves it out; a fill that arms the pass records its txid, the recorded shape"
        )
        for read in _ONE_DOOR_READS
    },
    **{
        ("finished", txid, read, "re-read"): (
            "a closed row enters the pass only through a fill, which records the copy's txid: the recorded shape, or two "
            "beside the row's own"
        )
        for txid in ("copys", "none", "differs")
        for read in _ONE_DOOR_READS
    },
    **{
        ("open", txid, read, "restart"): "an open row below the venue's figure is the startup shape, the open sweep's repair"
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
    },
    **{
        ("finished", txid, read, "restart"): (
            "the credit-0 fill recorded the copy's txid on the row: the recorded shape, or two beside the row's own"
        )
        for txid in ("copys", "none", "differs")
        for read in _ONE_DOOR_READS
    },
    **{
        ("open", txid, read, "ledger-fails"): "with the ledger unread the startup reads the venue for no row: the failed read"
        for txid in _ONE_DOOR_TXIDS
        for read in ("answers", "omits", *_ONE_DOOR_BELOW)
    },
    **{
        ("finished", txid, read, "ledger-fails"): (
            "never attached at construction, and the startup's settle skips whole on the failed ledger read: no writer "
            "reaches its intent"
        )
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
    },
    **{
        ("open", "none", read, pass_): "a row with no txid anywhere has no report a read could answer with"
        for pass_, reads in (("early-terminal", ("answers", *_ONE_DOOR_BELOW)), ("fill-after-answer", ("answers", "below-covered")))
        for read in reads
    },
    **{
        ("open", txid, read, "fill-after-answer"): "no read answered the row, so its fill closes nothing: the startup's tail"
        for txid in _ONE_DOOR_TXIDS
        for read in ("omits", "fails", "below-short", "below-unread")
    },
    **{
        ("finished", txid, read, pass_): "a finished row's terminal came before construction: the startup shape"
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
        for pass_ in ("early-terminal", "fill-after-answer", "early-external")
    },
    **{
        ("finished", txid, "below-short", "startup"): (
            "the answers row: a finished startup row's report reads below its ledger, the trade history short of it"
        )
        for txid in ("recorded", "copys", "two", "differs")
    },
    **{
        ("finished", txid, read, "restart"): "a credit-0 row's ledger reads 0.0, which no report reads below"
        for txid in ("recorded", "two")
        for read in _ONE_DOOR_BELOW
    },
    **{
        ("open", txid, "below-covered", "fill-after-answer"): (
            "the answers rows: a covered row is answered as a repaired one is, and its fill re-closes it alike"
        )
        for txid in ("recorded", "copys", "two", "differs")
    },
    **{
        ("open", "none", read, pass_): (
            "a row with no txid anywhere is marked at startup whatever its copy holds, and the pass's filter leaves it out: "
            "the startup rows"
        )
        for read in _ONE_DOOR_READS
        for pass_ in ("minted-before", "reconnect")
    },
    **{
        ("finished", txid, read, pass_): "the finished sweep reads no restored copy, minted or not: the startup shape"
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
        for pass_ in ("minted-before", "minted-external")
    },
    **{
        ("finished", txid, read, "reconnect"): "the pass reads a finished row only once a fill reached it: the re-read rows"
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
    },
    **{
        ("open", txid, read, pass_): (
            "an EXTERNAL copy is restored under the one txid its row recorded: a row recording none, two or another is no copy's"
        )
        for txid in ("copys", "none", "two", "differs")
        for read in _ONE_DOOR_READS
        for pass_ in ("minted-external", "early-external")
    },
}


def test_the_one_door_matrix_is_every_shape_but_the_ones_that_cannot_occur():
    shapes = {
        (ledger, txid, read, pass_)
        for ledger in ("open", "finished")
        for txid in _ONE_DOOR_TXIDS
        for read in _ONE_DOOR_READS
        for pass_ in _ONE_DOOR_PASSES
    }
    listed = [case[:4] for case in _ONE_DOOR_MATRIX]
    assert len(listed) == len(set(listed)) and not set(listed) & set(_ONE_DOOR_DROPPED)
    assert set(listed) | set(_ONE_DOOR_DROPPED) == shapes


@pytest.mark.parametrize(
    "ledger, txid, read, pass_, outcome, state, filled, level, intent",
    _ONE_DOOR_MATRIX,
    ids=["-".join(case[:4]) for case in _ONE_DOOR_MATRIX],
)
def test_a_restored_row_is_read_by_its_read_id_and_the_venues_report_alone_decides_it(
    tmp_path, request, ledger, txid, read, pass_, outcome, state, filled, level, intent
):
    earlier = NOW - timedelta(hours=4)
    journal = tmp_path / "journal"
    withdrawal = ledger == "finished" and pass_ == "startup"
    external = pass_ in ("minted-external", "early-external")
    prior_mint = pass_ in ("minted-before", "reconnect", "minted-external")
    read_id = _OTHER_TXID if txid == "differs" else _TXID
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    recorded = {"recorded": _TXID, "two": _TXID, "differs": _OTHER_TXID}.get(txid)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=recorded)
    base = 0.0 if pass_ == "restart" else 0.0004
    other = {"event": "fill", "at": earlier.isoformat(), "qty": 0.0004, "px": 30000.0, "venue_order_id": _OTHER_TXID}
    if pass_ == "restart":
        other["credited"] = 0.0
    update_submitted_row(
        journal,
        _boundary(earlier),
        "O-restored",
        state="ambiguous" if prior_mint else None,
        event=other if txid == "two" else None,
        add_filled_qty=base,
    )
    if withdrawal:
        update_submitted_row(journal, _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.0006)
    if pass_ == "restart":
        credit_0 = {"event": "fill", "at": earlier.isoformat(), "qty": 0.0002, "px": 30000.0, "venue_order_id": _TXID}
        update_submitted_row(journal, _boundary(earlier), "O-restored", state="canceled", event={**credit_0, "credited": 0.0})
    # A finished row with fills outside the restored set, at a later boundary: the startup read is made, and
    # reaches back to the restored row's boundary only when that row's own read id asks for it.
    _submitted_row(tmp_path, "O-anchor", reduce_only=False, index=1, venue_order_id=_ANCHOR_TXID)
    update_submitted_row(journal, _boundary(NOW), "O-anchor", state="filled", add_filled_qty=0.001)
    strategy = {"strategy_id": _EXTERNAL} if external else {}
    if txid == "none":
        copy = _unaccepted_order("O-restored")
    elif external:
        copy = _resting_limit_order(_TXID, quantity="0.001", venue_order_id=_TXID, strategy_id=_EXTERNAL)
        copy.apply(_fill(_TXID, 0.0008, venue_order_id=VenueOrderId(_TXID), trade_id="T-before", **strategy))
    else:
        copy = _restored_order("O-restored", filled=0.0003 if withdrawal else 0.0008)
        if ledger == "finished" and pass_ != "re-read":
            copy.apply(_event(OrderCanceled, client_order_id="O-restored"))
    copy_id = str(copy.client_order_id)
    if prior_mint:
        copy.apply(_event(OrderCanceled, client_order_id=copy_id, reconciliation=True, **strategy))
    cache = StubCache(closed_orders=[copy]) if copy.is_closed else StubCache(open_orders=[copy])
    anchor = _report(_ANCHOR_TXID, OrderStatus.FILLED, filled_qty="0.001")
    closed = ledger == "finished" and not withdrawal
    early = pass_ in ("early-terminal", "early-external")
    status = OrderStatus.CANCELED if ledger == "finished" or early or pass_ == "minted-before" else OrderStatus.PARTIALLY_FILLED
    figure = "0.0005" if withdrawal else "0.0002" if read in _ONE_DOOR_BELOW else "0.0006"
    answer = _report(read_id, status, filled_qty=figure)
    # A read that omits the row's own txid answers its copy's where the two differ, the report a read by the copy finds.
    omitted = [_report(_TXID, status, filled_qty=figure), anchor] if txid == "differs" else [anchor]
    reports = {"omits": omitted, "fails": []}.get(read, [answer, anchor])
    if pass_ in ("re-read", "reconnect"):
        venue = _VenueOrders(_report(read_id, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"), anchor)
    else:
        venue = _VenueOrders(*reports, raises=RuntimeError("timed out") if read == "fails" else None)
    history = {
        "below-unread": _VenueFills(raises=RuntimeError("timed out")),
        "below-covered": _VenueFills(_fill_report(read_id, "0.001" if withdrawal else "0.0004")),
    }.get(read, _VenueFills())
    if (outcome == "applied" and withdrawal) or outcome == "refuted":
        request.getfixturevalue("kill_trip_expected")
    cancel = _VenueCancel()
    client = StubClient(cache)
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        venue_cancel=cancel,
        venue_fills=history,
        config=_cache_config(tmp_path),
    )
    if pass_ == "ledger-fails":

        def _unreadable(*args, **kwargs):
            raise OSError("read-only file system")

        request.getfixturevalue("monkeypatch").setattr(executor_module, "open_submitted_rows", _unreadable)
    terminal = _event(OrderCanceled, client_order_id=copy_id, **strategy)

    def _terminate(event):
        if external:
            _deliver_external_event(ex, client, event)
            return
        if not copy.is_closed:
            copy.apply(event)
        ex.on_order_event(event)

    with _executor_errors(level=logging.WARNING) as records:
        if early:
            _terminate(terminal)
            cache._open_orders.remove(copy)
            cache._closed_orders.append(copy)
        ex.on_timer(NOW)
        if pass_ == "fill-after-answer":
            ex.on_order_event(_fill("O-restored", 0.0002, venue_order_id=VenueOrderId(read_id), trade_id="T-credit-0"))
        if pass_ in ("ledger-fails", "fill-after-answer", "minted-external"):
            _terminate(terminal)
        if pass_ == "re-read":
            if txid in ("copys", "differs"):
                minted = _event(OrderCanceled, client_order_id="O-restored", reconciliation=True)
                copy.apply(minted)
                ex.on_order_event(minted)
            else:
                ex.on_order_event(_fill("O-restored", 0.0002, venue_order_id=VenueOrderId(_TXID), trade_id="T-credit-0"))
            if closed:
                canceled = _event(OrderCanceled, client_order_id="O-restored")
                copy.apply(canceled)
                ex.on_order_event(canceled)
        if pass_ == "reconnect":
            _reconnect(ex)
        if pass_ in ("re-read", "reconnect"):
            venue.reports = reports
            if read == "fails":
                venue._raises = RuntimeError("timed out")
            ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    what = _NO_TXID if txid == "none" else f"the venue's order read has no order {read_id}"
    line = f"ledgered order O-restored matches no venue order -- {what}; its row is marked ambiguous"
    marks = [e["what"] for e in row["events"] if e.get("type") == "ambiguous"]
    figures = [e["venue_filled_qty"] for e in row["events"] if e.get("event") in ("reconciled", "withdrawn")]
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (row["state"], row["filled_qty"], entry["outcome"]) == (state, pytest.approx(filled), intent)
    assert intent == "pending" or entry["filled_qty"] == pytest.approx(filled)
    # Every mirror this process holds for the row reads its ledgered figure, whichever id an event names it by.
    mirrors = [mirror["filled_qty"] for _, mirror in ex._attached.values() if mirror["client_order_id"] == "O-restored"]
    assert mirrors == [pytest.approx(row["filled_qty"])] * len(mirrors)
    assert (marks, [r.levelname for r in records if r.getMessage() == line]) == (
        ([what], [level]) if outcome == "marked" else ([], [])
    )
    withdrawn = outcome == "refuted" and (withdrawal or early)
    assert figures == ([float(answer.filled_qty)] if outcome in ("applied", "recancelled") or withdrawn else [])
    assert float(copy.filled_qty) not in (row["filled_qty"], *figures)
    recancels = (pass_ == "reconnect" or pass_ == "re-read" and txid in ("copys", "differs")) and read not in ("omits", "fails")
    assert cancel.calls == ([(read_id, INSTRUMENT_IDS["BTC/EUR"])] if ledger == "open" and recancels else [])
    assert _kill_file(tmp_path).exists() == ((outcome == "applied" and withdrawal) or outcome == "refuted")
    assert (ex._reconciliation_refusal is not None) == (read == "fails" and pass_ not in ("re-read", "reconnect", "ledger-fails"))
    since = _boundary(NOW if txid == "none" else earlier) - timedelta(hours=1)
    assert venue.calls == {"re-read": [since, since], "reconnect": [since, since], "ledger-fails": []}.get(pass_, [since])

    if outcome == "marked" and pass_ == "re-read":
        later = _fill("O-restored", 0.0001, venue_order_id=VenueOrderId(read_id), trade_id="T-later")
        ex.on_order_event(later)
        ex.on_timer(NOW + timedelta(seconds=10))
        assert len(venue.calls) == 2  # the marked row is left out of the pass the later fill armed
    if outcome in ("marked", "unread", "refuted", "covered"):
        _terminate(_event(OrderCanceled, client_order_id=copy_id, **strategy))
        answered = outcome == "covered" or pass_ == "reconnect" and outcome in ("marked", "unread")
        row = _record(tmp_path, earlier)["submitted"][0]
        entry = _intent_entry(tmp_path, 0, earlier)
        assert (row["state"], entry["outcome"]) == (
            "canceled" if ledger == "open" else state,
            intent if intent != "pending" else "revoked" if answered else "pending",
        )
        assert entry["outcome"] == "pending" or entry["filled_qty"] == pytest.approx(row["filled_qty"])


def test_a_restored_row_an_earlier_process_marked_is_read_again_by_the_re_read_pass_once_this_process_answers_it(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    mark = {"type": "ambiguous", "at": earlier.isoformat(), "what": f"the venue's order read has no order {_TXID}"}
    update_submitted_row(
        tmp_path / "journal", _boundary(earlier), "O-restored", state="ambiguous", event=mark, add_filled_qty=0.0004
    )
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006"))
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(open_orders=[_restored_order("O-restored", filled=0.0009)])),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )
    ex.on_timer(NOW)
    ex.on_order_event(_fill("O-restored", 0.0002, venue_order_id=VenueOrderId(_TXID), trade_id="T-credit-0"))
    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0008")]

    ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], len(venue.calls)) == ("ambiguous", pytest.approx(0.0008), 2)


@pytest.mark.parametrize(
    "reports, filled, outcome",
    [([], 0.0, "pending"), ([_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0002")], 0.0002, "revoked")],
    ids=["the-startup-marked-it", "the-startup-read-answered-it"],
)
def test_the_cancel_ack_of_a_restored_row_writes_its_intent_unless_the_startup_marked_it(tmp_path, reports, filled, outcome):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    credit_0 = {"event": "fill", "at": earlier.isoformat(), "qty": 0.0002, "px": 30000.0, "venue_order_id": _TXID, "credited": 0.0}
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", event=credit_0)
    copy = _restored_order("O-restored", filled=0.0008)
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(open_orders=[copy])),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=_VenueOrders(*reports),
        config=_cache_config(tmp_path),
    )
    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW)
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"

    canceled = _event(OrderCanceled, client_order_id="O-restored")
    copy.apply(canceled)
    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], _intent_entry(tmp_path, 0, earlier)["outcome"]) == (
        "canceled",
        pytest.approx(filled),
        outcome,
    )


@pytest.mark.parametrize(
    "reread, filled, outcome",
    [(False, 0.0, "pending"), (True, 0.0006, "revoked")],
    ids=["no-read-answered-it", "a-re-read-answered-it"],
)
def test_the_cancel_ack_of_a_restored_row_a_failed_startup_read_left_unread_writes_its_intent_once_a_read_answers(
    tmp_path, reread, filled, outcome
):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=True, when=earlier, venue_order_id=_TXID)
    credit_0 = {"event": "fill", "at": earlier.isoformat(), "qty": 0.0002, "px": 30000.0, "venue_order_id": _TXID, "credited": 0.0}
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", event=credit_0)
    copy = _restored_order("O-restored", filled=0.0008)
    venue = _VenueOrders(raises=RuntimeError("timed out"))
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(open_orders=[copy])),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )
    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW)
        if reread:
            ex.on_order_event(_fill("O-restored", 0.0002, venue_order_id=VenueOrderId(_TXID), trade_id="T-credit-0"))
            venue._raises = None
            venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0006")]
            ex.on_timer(NOW + timedelta(seconds=5))

    canceled = _event(OrderCanceled, client_order_id="O-restored")
    copy.apply(canceled)
    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], _intent_entry(tmp_path, 0, earlier)["outcome"]) == (
        "canceled",
        pytest.approx(filled),
        outcome,
    )
    assert len(venue.calls) == (2 if reread else 1)


def test_the_cancel_ack_of_an_adopted_reducer_outside_the_restored_set_writes_no_intent(tmp_path):
    ex, client, earlier = _adopted_executor(tmp_path)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)

    _deliver_external_event(ex, client, _canceled("O-attached"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], _intent_entry(tmp_path, 0, earlier)["outcome"]) == ("canceled", "pending")


@pytest.mark.parametrize("external", [False, True], ids=["own-copy", "external-copy"])
def test_a_mint_on_a_restored_row_the_startup_answered_keeps_its_intent_pending_at_a_later_venue_ack(tmp_path, external):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    cid, strategy_id = (_TXID, StrategyId("EXTERNAL")) if external else ("O-reducer", _STUB_STRATEGY_ID)
    client = StubClient(StubCache(open_orders=[_resting_limit_order(cid, venue_order_id=_TXID, strategy_id=strategy_id)]))
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=_VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0002")),
        config=_cache_config(tmp_path),
    )
    ex.on_timer(NOW)
    assert _record(tmp_path, earlier)["submitted"][0]["filled_qty"] == pytest.approx(0.0002)

    with _executor_errors(level=logging.WARNING):
        for reconciliation in (True, False):
            event = _event(OrderCanceled, client_order_id=cid, strategy_id=strategy_id, reconciliation=reconciliation)
            if external:
                _deliver_external_event(ex, client, event)
            else:
                if reconciliation:
                    client.cache.order(ClientOrderId(cid)).apply(event)
                ex.on_order_event(event)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], _intent_entry(tmp_path, 0, earlier)["outcome"]) == (
        "canceled",
        pytest.approx(0.0002),
        "pending",
    )


def test_a_finished_restored_row_the_venue_answers_at_its_own_figure_has_its_intent_settled_at_startup(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report(_TXID, OrderStatus.FILLED, filled_qty="0.001"))
    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(closed_orders=[_restored_order("O-restored", filled=0.001)])),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )

    ex.on_timer(NOW)

    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"], len(venue.calls)) == ("filled", 0.001, 1)


def test_a_restored_row_is_read_at_the_venue_when_a_read_of_its_copy_raises(tmp_path, kill_trip_expected):
    class _NoOrderRead(StubCache):
        def order(self, client_order_id):
            raise RuntimeError("cache read failed")

    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.001)
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0005"))
    ex = _executor(
        tmp_path,
        client=StubClient(_NoOrderRead(closed_orders=[_restored_order(filled=0.001)])),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )

    with _executor_errors(level=logging.CRITICAL):
        ex.on_timer(NOW)

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert _kill_file(tmp_path).exists() and _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"


# The reads of a row's txid, the restored set or a Cache copy other than through `_read_id`, per function; which arm of a sweep reads is the matrix's.
_ONE_DOOR_NAMES = frozenset({"_row_venue_order_id", "_row_venue_order_ids", "_cached_order", "_cache_lookup", "_restored"})
_ONE_DOOR_LOOKUPS = frozenset({"_cached_order", "_cache_lookup"})
_ONE_DOOR_CACHE_ACCESSORS = frozenset({"order", "client_order_id"})
_ONE_DOOR_COPY_FIGURES = frozenset({"filled_qty", "status"})
_ONE_DOOR_TXID_KEY = "venue_order_id"
_ONE_DOOR_CALLERS = {
    ("__init__", "_restored"): "the restored set's empty start, before `_read_restored` fills it",
    ("_read_restored", "_restored"): "the restored set itself, read from the Cache at construction",
    ("_read_restored", "_row_venue_order_id"): "the ledger's own txid map, attaching a restored copy to its row",
    ("_adopt_resting_orders", "_restored"): "whether a resting copy is restored, deciding its cancel, not its row's figure",
    ("_adopt_resting_orders", "_row_venue_order_id"): "the ledger's own txid map, finding a resting order's row",
    ("_read_id", "_restored"): "the one door itself: the copy's txid where the row recorded none",
    ("_read_id", "_row_venue_order_id"): "the one door itself: the row's own txid first",
    ("_restored_row", "_restored"): "membership of the restored set",
    ("_restored_row", "_row_venue_order_id"): "an EXTERNAL copy is restored under the txid its row recorded",
    ("_row_venue_order_id", "_row_venue_order_ids"): "the single txid is read off the set of them",
    ("_row_venue_order_ids", f"[{_ONE_DOOR_TXID_KEY!r}]"): "the ledger's txid key, read in this one place",
    ("_unmatchable_what", "_row_venue_order_ids"): "the mark's text names every txid the row recorded",
    ("_trip_on_fill", "_row_venue_order_id"): "a label: the kill reason names the txid the row recorded",
    ("_cached_order", "_cache_lookup"): "the minted-terminal filter over the lookup",
    ("_cache_lookup", "_cache.order"): "the lookup itself, by the row's own id",
    ("_cache_lookup", "_cache.client_order_id"): "the lookup itself, by txid through the Cache's own index",
    ("_minted_closed", "_cache_lookup"): "whether the copy was minted closed, the re-read pass's population",
    ("_read_venue_orders", "_cached_order"): "whether a row the venue is not asked over needs the read all the same",
    (
        "_reconcile_adopted_rows",
        "_cached_order",
    ): "a row outside the restored set is reconciled from it, and its presence routes a mint",
    ("_reconcile_adopted_rows", "_cache_lookup"): "the Cache order's own id, re-attaching a row a report repaired",
    ("_reconcile_adopted_rows", "copy.filled_qty"): "a row outside the restored set is repaired from its Cache order's figure",
    ("_reconcile_adopted_rows", "copy.status"): "a row outside the restored set takes its Cache order's status",
    (
        "_reconcile_finished_rows",
        "_cached_order",
    ): "a row outside the restored set is checked against it; a restored row's presence",
    ("_reconcile_finished_rows", "copy.filled_qty"): "a row outside the restored set is checked against its Cache order's figure",
    ("_reconcile_finished_rows", "_cache_lookup"): "the copy's own id, re-attaching a restored row the upward arm repaired",
    ("_venue_terminal_state", "_cache.order"): "the event path: the order a venue event was applied to",
    ("_venue_terminal_state", "copy.status"): "the event path: the status the venue's event put on the order",
    ("_fill_credit", "_cache.order"): "the event path: the replay cap on a row outside the restored set",
    ("_fill_credit", "copy.filled_qty"): "the event path: what the Cache's order holds beyond a row the pass repaired",
    (
        "_net_foreign_fill",
        "_cache_lookup",
    ): "whose strategy a late-filling row's Cache order carries, deciding the netting and no row's figure",
}
# Every writer of a plan intent, per function: a restored row's intent is written only from `_answered`.
_INTENT_WRITER = "update_plan_intent"
_INTENT_WRITERS = {
    "_journal_intent": "the running plan's own intents, which no restored row belongs to",
    "_settle_pending_intents": "the startup's settle, a restored row's intent only from `_answered`",
    "_settle_restored_intent": "a restored row's terminal, only from `_answered`",
}


def _one_door_callers() -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()

    def cache(node, aliases):
        return isinstance(node, ast.Attribute) and node.attr == "_cache" or isinstance(node, ast.Name) and node.id in aliases

    def lookup(node, aliases):
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and (
                node.func.attr in _ONE_DOOR_LOOKUPS
                or node.func.attr in _ONE_DOOR_CACHE_ACCESSORS
                and cache(node.func.value, aliases)
            )
        )

    names = _ONE_DOOR_NAMES | {_INTENT_WRITER}

    def read(node, aliases, copies):
        if isinstance(node, ast.Name) and node.id in names:
            return node.id
        if isinstance(node, ast.alias) and node.name in names and node.asname not in (None, node.name):
            return node.name  # an import under another name, whose calls no read below would see
        if isinstance(node, ast.Constant) and node.value in names:
            return node.value  # `getattr` or `globals()` by the name
        if isinstance(node, ast.Attribute):
            if node.attr in names:
                return node.attr
            if node.attr in _ONE_DOOR_CACHE_ACCESSORS and cache(node.value, aliases):
                return f"_cache.{node.attr}"
            if node.attr in _ONE_DOOR_COPY_FIGURES and isinstance(node.value, ast.Name) and node.value.id in copies:
                return f"copy.{node.attr}"
        key = node.slice if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) else None
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" and node.args:
            key = node.args[0]
        if isinstance(key, ast.Constant) and key.value == _ONE_DOOR_TXID_KEY:
            return f"[{_ONE_DOOR_TXID_KEY!r}]"
        return None

    def walk(node, owner, aliases, copies):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assigns = [n for n in ast.walk(child) if isinstance(n, ast.Assign)]
                handles = {t.id for n in assigns if cache(n.value, set()) for t in n.targets if isinstance(t, ast.Name)}
                held = {
                    t.id
                    for n in assigns
                    if any(lookup(c, handles) for c in ast.walk(n.value))
                    for t in n.targets
                    if isinstance(t, ast.Name)
                }
                walk(child, child.name if owner is None else f"{owner}.{child.name}", handles, held)
                continue
            name = read(child, aliases, copies)
            if name is not None:
                found.add((owner or "<module>", name))
            walk(child, owner, aliases, copies)

    walk(ast.parse(Path(executor_module.__file__).read_text()), None, set(), set())
    return found


def test_every_read_of_a_rows_txid_or_its_cache_copy_goes_through_the_one_door_and_every_intent_writer_is_listed():
    found = _one_door_callers()
    writers = {owner for owner, name in found if name == _INTENT_WRITER}
    found -= {(owner, _INTENT_WRITER) for owner in writers}
    assert sorted(writers - set(_INTENT_WRITERS)) == [], (
        f"{sorted(writers - set(_INTENT_WRITERS))} write a plan intent -- a restored row's intent is written only once a "
        "venue report of this process has answered it since its last fill or mint (`_answered`); write it through "
        "`_settle_restored_intent`, or list the writer in `_INTENT_WRITERS` with its reason"
    )
    assert sorted(set(_INTENT_WRITERS) - writers) == [], "an entry no function calls any more leaves `_INTENT_WRITERS`"
    elsewhere = sorted(
        path.name
        for path in Path(executor_module.__file__).parent.rglob("*.py")
        if path.name not in ("executor.py", "execledger.py") and _INTENT_WRITER in path.read_text()
    )
    assert elsewhere == [], f"{elsewhere} name `{_INTENT_WRITER}`, which the walk above reads in the executor alone"
    unlisted = sorted(found - set(_ONE_DOOR_CALLERS))
    assert unlisted == [], (
        f"{unlisted} read a row's txid or its Cache copy directly -- the one door: every ledgered row either pass reads "
        "is read at the venue by `_read_id`, and a restored row's figure and status come from the venue's report alone; "
        "read it through `_read_id`, or list the caller in `_ONE_DOOR_CALLERS` with the reason it reads no row at the venue"
    )
    assert sorted(set(_ONE_DOOR_CALLERS) - found) == [], "an entry no function calls any more leaves `_ONE_DOOR_CALLERS`"


def test_a_plan_the_other_checks_refused_takes_no_mixed_inventory_read(tmp_path):
    positions = _VenuePositions({"BTC/EUR": 0.001})
    ex = _executor(
        tmp_path, client=StubClient(StubCache(balances={"ZEUR": 1000.0})), config=_cache_config(tmp_path), venue_positions=positions
    )
    _drop_plan(tmp_path, _plan_dict(created_at=NOW + timedelta(minutes=5)))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"], positions.calls) == ("refused", ["created_at is in the future"], 0)


def test_a_restored_copy_whose_row_is_closed_is_cancelled_when_the_venue_cannot_be_read(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-restored", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-restored", state="filled", add_filled_qty=0.001)
    copy = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    client = StubClient(StubCache(open_orders=[copy]))
    venue = _VenueOrders(raises=RuntimeError("timed out"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [_TXID]


@pytest.mark.parametrize("reduce_only, canceled, line", [
    (False, ["O-restored"], "canceling restored order O-restored, partial -- the ledger does not carry it as a resting reducer"),
    (True, [], "adopted resting order O-restored is a ledgered reducer -- left resting and re-attached"),
])  # fmt: skip
def test_a_restored_opener_the_venue_reports_open_is_cancelled_by_the_pass_and_a_kept_reducer_is_not(
    tmp_path, reduce_only, canceled, line
):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order(filled=0.0004)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == canceled
    assert line in [r.getMessage() for r in records]
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == ("revoked" if canceled else "pending")


def test_a_finished_row_with_fills_is_read_at_the_venue_over_the_caches_closed_copy_with_the_cache_enabled(
    tmp_path, kill_trip_expected
):
    """The withdrawal check compared against the Cache's restored copy would compare the ledger with
    itself: the copy agrees with the row at 0.001, the venue says the order ended with 0.0006."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    cache = StubCache(closed_orders=[_closed_order("O-finished", OrderStatus.FILLED, filled_qty=0.001, venue_order_id=_TXID)])
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0006"))
    ex = _executor(
        tmp_path,
        client=StubClient(cache),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )

    ex.on_timer(NOW)

    assert venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert _record(tmp_path, earlier)["submitted"][0]["events"][-1]["event"] == "withdrawn"
    assert (
        f"order O-finished (Kraken {_TXID}) shows 0.0006 filled at the venue, less than the 0.001"
        in _kill_file(tmp_path).read_text()
    )


def test_a_finished_row_the_caches_closed_copy_agrees_with_is_not_read_at_the_venue_without_the_cache(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-finished", reduce_only=False, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-finished", state="filled", add_filled_qty=0.001)
    cache = StubCache(closed_orders=[_closed_order("O-finished", OrderStatus.FILLED, filled_qty=0.001, venue_order_id=_TXID)])
    venue = _VenueOrders(_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0006"))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue)

    ex.on_timer(NOW)

    assert venue.calls == [] and not _kill_file(tmp_path).exists()


def test_a_fill_on_a_restored_row_before_the_first_tick_lands_in_its_row_and_trips_nothing(tmp_path):
    """The attach at construction (spec 00120 D6): a restored order's fill can reach the own topic in
    the seconds between `on_start` and the first tick, where `_trip_on_fill` runs first and an order
    no row is attached for latches the kill switch. Attached at construction, under its own id and
    its txid, the fill takes the detached path -- the row's `fill` line with `credited` 0, no kill
    file, and the re-read pass armed for the repair."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order("O-reducer")]))
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path))
    assert not ex._adopted and "O-reducer" in ex._attached and _TXID in ex._attached_by_venue

    fill = _fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-early")
    client.cache.order(ClientOrderId("O-reducer")).apply(fill)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_order_event(fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0, "accepted")
    assert row["events"][-1]["event"] == "fill" and (row["events"][-1]["qty"], row["events"][-1]["credited"]) == (0.0004, 0.0)
    assert not _kill_file(tmp_path).exists() and ex._reread_tries == 3
    assert [r.getMessage() for r in records] == [
        "a fill on restored order O-reducer credits nothing until the venue is read -- the next restart is taken flat"
    ]


def test_a_restored_order_the_cache_holds_closed_is_read_at_the_venue_and_the_report_wins(tmp_path):
    """The restored set takes the Cache's closed copies too: a kept reducer's double-booked copy reads
    FILLED where the venue says partial (spec 00120 D7), and a set read from the open orders alone would
    trust exactly that copy. The row, repaired to 0.0007 by the previous process, stays there: the venue
    is read and its partial report is the figure."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0007)
    client = StubClient(StubCache(closed_orders=[_restored_order("O-reducer", filled=0.001)]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0007"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    assert client.cache.order(ClientOrderId("O-reducer")).status == OrderStatus.FILLED

    ex.on_timer(NOW)

    assert ex._restored == {"O-reducer": _TXID} and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], [e.get("event") for e in row["events"] if e.get("event")]) == ("accepted", 0.0007, [])
    assert not _kill_file(tmp_path).exists() and "O-reducer" in ex._attached


def test_a_restored_external_copy_of_a_kept_reducer_credits_its_fills_nothing_and_the_pass_repairs_the_row(tmp_path):
    """The store persists the EXTERNAL copy a previous process adopted by its txid and restores it with
    that process's fills, the library state a restored own order has and the same double booking on a
    trade frame: the copy is in the restored set under its txid, the venue answers for it, its fills
    credit the row nothing, and the re-read pass repairs the row from the venue's figure."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    update_submitted_row(tmp_path / "journal", _boundary(earlier), "O-reducer", add_filled_qty=0.0004)
    copy = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    copy.apply(_fill(_TXID, 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-before", strategy_id=StrategyId("EXTERNAL")))
    client = StubClient(StubCache(open_orders=[copy]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004"))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert ex._restored == {_TXID: _TXID} and venue.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert client.canceled == [] and f"adopted resting order {_TXID} is a ledgered reducer -- left resting and re-attached" in [
        r.getMessage() for r in records
    ]
    for trade_id in ("T-inferred", "T-frame"):
        fill = _fill(_TXID, 0.0003, venue_order_id=VenueOrderId(_TXID), trade_id=trade_id, strategy_id=StrategyId("EXTERNAL"))
        _deliver_external_event(ex, client, fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0004, "accepted") and not _kill_file(tmp_path).exists()
    assert [(e["qty"], e.get("credited")) for e in row["events"] if e.get("event") == "fill"] == [(0.0003, 0.0), (0.0003, 0.0)]

    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0007")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"], row["events"][-1]["event"]) == (0.0007, "accepted", "reconciled")
    assert "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue" in [
        r.getMessage() for r in records
    ]
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending" and len(venue.calls) == 2


def _kept_reducer(tmp_path, venue, *, reduce_only=True, client_type=None):
    """A restored reducer the startup pass keeps: its row, its pending intent, the Cache's copy under
    this engine's own id, and the pass run against `venue`'s first report. With `reduce_only` False
    and a `client_type` whose cancel raises, it is a restored opener the pass could not cancel."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = (client_type or StubClient)(StubCache(open_orders=[_restored_order("O-reducer")]))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    ex.on_timer(NOW)
    assert client.canceled == [] and ex._restored == {"O-reducer": _TXID}
    return ex, client, earlier


def test_a_fill_on_a_restored_row_credits_nothing_and_the_re_read_pass_repairs_the_row_from_the_venue(tmp_path):
    """D8's credit rule and the pass that follows it: the frame's fill lands in the row as the stream's
    record with `credited` 0, the row's quantity waits for the venue's cumulative figure, and the
    pass reads it on the next tick with nothing in flight; the completing repair writes the row
    `filled`, counts it, and writes the kept reducer's intent."""
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex, client, earlier = _kept_reducer(tmp_path, venue)
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    order = client.cache.order(ClientOrderId("O-reducer"))

    fill = _fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-2")
    order.apply(fill)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_order_event(fill)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.0, "accepted")
    assert row["events"][-1]["event"] == "fill" and (row["events"][-1]["qty"], row["events"][-1]["credited"]) == (0.0004, 0.0)
    assert not _kill_file(tmp_path).exists() and ex._reread_tries == 3
    assert [r.getMessage() for r in records] == [
        "a fill on restored order O-reducer credits nothing until the venue is read -- the next restart is taken flat"
    ]

    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"], row["events"][-1]["event"]) == (0.0004, "accepted", "reconciled")
    assert len(venue.calls) == 2 and _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"
    assert [r.getMessage() for r in records][:1] == [
        "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue"
    ]

    last = _fill("O-reducer", 0.0006, venue_order_id=VenueOrderId(_TXID), trade_id="T-3")
    order.apply(last)
    ex.on_order_event(last)
    venue.reports = [_report(_TXID, OrderStatus.FILLED, filled_qty="0.001")]
    ex.on_timer(NOW + timedelta(seconds=10))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["filled_qty"], row["state"]) == (0.001, "filled")
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("filled", 0.001)
    assert metrics.orders == ["filled"] and len(venue.calls) == 3


@pytest.mark.parametrize(
    "reduce_only, reconciliation, state, outcome, reasons",
    [
        (True, False, "canceled", "revoked", ["the kept reducer ended without filling"]),
        (True, True, "ambiguous", "pending", []),
        (False, False, "canceled", "revoked", ["the restored opener ended without filling"]),
    ],
    ids=["kept-reducer", "kept-reducer-minted", "opener-whose-cancel-raised"],
)
def test_a_terminal_on_a_restored_kept_reducer_writes_the_venues_state_and_its_intent(
    tmp_path, reduce_only, reconciliation, state, outcome, reasons
):
    """The own topic's detached path makes the external path's writes for a restored row: the venue's
    cancel closes the row and writes the intent, a minted one reads ambiguous and leaves the intent for
    the pass that settles the row."""

    class _CancelRaises(StubClient):
        def cancel_order(self, client_order_id):
            raise RuntimeError("the cancel could not be sent")

    ex, client, earlier = _kept_reducer(
        tmp_path,
        _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED)),
        reduce_only=reduce_only,
        client_type=None if reduce_only else _CancelRaises,
    )
    canceled = _event(OrderCanceled, client_order_id="O-reducer", reconciliation=reconciliation)
    client.cache.order(ClientOrderId("O-reducer")).apply(canceled)

    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert row["state"] == state and row["events"][-1]["type"] == "OrderCanceled"
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["reasons"]) == (outcome, reasons)


@pytest.mark.parametrize("minted", [False, True], ids=["venue-ack", "minted-terminal"])
@pytest.mark.parametrize("reduce_only", [True, False], ids=["kept-reducer", "cancelled-opener"])
def test_a_fill_then_a_terminal_on_a_restored_row_before_the_next_tick_is_repaired_by_the_pass(tmp_path, reduce_only, minted):
    """D7's race on the event path: a restored row takes a fill, credited nothing, and a terminal
    closes it before the re-read pass runs -- the venue's cancel ack, or one the library flagged
    `reconciliation`, which the row reads `ambiguous`. The pass reads the row either way, names it
    among the restored rows with a fill, and repairs it to the
    venue's figure; a kept reducer's intent is written then, at the repaired quantity, never at the
    terminal's credit-0 figure, and a cancelled opener's the startup sweep already wrote."""
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-restored", reduce_only=reduce_only, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order()]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(
        tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_orders=venue, config=_cache_config(tmp_path)
    )
    ex.on_timer(NOW)
    assert [str(cid) for cid in client.canceled] == ([] if reduce_only else ["O-restored"])
    order = client.cache.order(ClientOrderId("O-restored"))

    fill = _fill("O-restored", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-race")
    order.apply(fill)
    ex.on_order_event(fill)
    canceled = _event(OrderCanceled, client_order_id="O-restored", reconciliation=minted)
    order.apply(canceled)
    ex.on_order_event(canceled)

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"]) == ("ambiguous" if minted else "canceled", 0.0)
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == ("pending" if reduce_only else "revoked")

    venue.reports = [_report(_TXID, OrderStatus.CANCELED, filled_qty="0.0004")]
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], row["events"][-1]["event"]) == ("canceled", 0.0004, "reconciled")
    assert [r.getMessage() for r in records if r.getMessage().startswith("the re-read pass reads")] == [
        "the re-read pass reads 1 restored row(s) with a fill since its last read against the venue"
    ]
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("revoked", 0.0004 if reduce_only else 0.0)
    assert entry["reasons"] == (
        ["the kept reducer ended partly filled"] if reduce_only else ["the engine restarted while the intent was in flight"]
    )
    assert ex._restored_fills == set() and len(venue.calls) == 2


def test_a_minted_terminal_on_a_restored_kept_reducer_the_venue_holds_open_is_re_cancelled_and_its_intent_written(tmp_path):
    earlier = NOW - timedelta(hours=4)
    _pending_plan_entry(tmp_path, earlier, n_intents=1)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    client = StubClient(StubCache(open_orders=[_restored_order("O-reducer")]))
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    cancel = _VenueCancel()
    ex = _executor(
        tmp_path,
        client=client,
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        venue_cancel=cancel,
        config=_cache_config(tmp_path),
    )
    ex.on_timer(NOW)
    order = client.cache.order(ClientOrderId("O-reducer"))
    fill = _fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-race")
    order.apply(fill)
    ex.on_order_event(fill)
    canceled = _event(OrderCanceled, client_order_id="O-reducer", reconciliation=True)
    order.apply(canceled)
    ex.on_order_event(canceled)
    assert _record(tmp_path, earlier)["submitted"][0]["state"] == "ambiguous"
    assert _intent_entry(tmp_path, 0, earlier)["outcome"] == "pending"

    venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004")]
    with _executor_errors(level=logging.WARNING):
        ex.on_timer(NOW + timedelta(seconds=5))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert (row["state"], row["filled_qty"], row["events"][-1]["event"]) == ("canceled", 0.0004, "recancelled")
    assert [venue_order_id for venue_order_id, _ in cancel.calls] == [_TXID]
    entry = _intent_entry(tmp_path, 0, earlier)
    assert (entry["outcome"], entry["filled_qty"]) == ("revoked", 0.0004)


@pytest.mark.parametrize("raised", [False, True], ids=["marked-by-a-good-read", "its-reconcile-raised"])
def test_a_restored_row_the_re_read_pass_could_not_repair_stays_among_the_rows_a_fill_reached(tmp_path, raised):
    class _OrderReadRaises(StubCache):
        raises = False

        def order(self, client_order_id):
            if self.raises:
                raise RuntimeError("cache read failed")
            return super().order(client_order_id)

    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-reducer", reduce_only=True, when=earlier, venue_order_id=_TXID)
    cache = _OrderReadRaises(open_orders=[_restored_order("O-reducer")])
    venue = _VenueOrders(_report(_TXID, OrderStatus.ACCEPTED))
    ex = _executor(
        tmp_path,
        client=StubClient(cache),
        gate=_gate(tmp_path, GateLevel.REDUCE_ONLY),
        venue_orders=venue,
        config=_cache_config(tmp_path),
    )
    ex.on_timer(NOW)

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_order_event(_fill("O-reducer", 0.0004, venue_order_id=VenueOrderId(_TXID), trade_id="T-1"))
        venue.reports = [_report(_TXID, OrderStatus.PARTIALLY_FILLED, filled_qty="0.0004")] if raised else []
        cache.raises = raised
        ex.on_timer(NOW + timedelta(seconds=5))
        cache.raises = False
        if raised:
            _reconnect(ex)
            ex.on_timer(NOW + timedelta(seconds=10))
        else:
            ex.on_order_event(_fill("O-reducer", 0.0001, venue_order_id=VenueOrderId(_TXID), trade_id="T-2"))

    row = _record(tmp_path, earlier)["submitted"][0]
    assert [r.getMessage() for r in records if "credits nothing" in r.getMessage()] == [
        "a fill on restored order O-reducer credits nothing until the venue is read -- the next restart is taken flat"
    ]
    assert (row["state"], row["filled_qty"], len(venue.calls)) == (
        ("accepted", pytest.approx(0.0004), 3) if raised else ("ambiguous", 0.0, 2)
    )


def test_realized_pnl_takes_the_caches_realizations_at_construction_as_a_baseline(tmp_path):
    """A restored closed position carries a previous run's realization; the gauge reads this
    process's own from the baseline read at construction."""
    client = StubClient()
    client.cache.close_position("BTC/EUR", Money(5.0, Currency.from_str("EUR")))
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path))
    ex._traded.add(InstrumentId.from_str(INSTRUMENT_IDS["BTC/EUR"]))

    assert ex._realized_eur() == 0.0
    client.cache.close_position("BTC/EUR", Money(-1.5, Currency.from_str("EUR")))
    assert ex._realized_eur() == pytest.approx(-1.5)


_MARGIN_OPEN = _intent(leverage=2)
_SPOT_CLOSE = _intent(side="sell", action="close", notional_eur=None, qty=0.001)
_MARGIN_CLOSE = _intent(side="sell", action="close", leverage=2)


@pytest.mark.parametrize(
    "intent, margin, spot, refused",
    [
        (_intent(), {"BTC/EUR": 0.001}, {}, "a spot open on BTC/EUR beside a margin position of 0.001 there"),
        (_MARGIN_OPEN, {}, {"BTC/EUR": 0.01}, "a margin open on BTC/EUR beside 0.01 BTC spot inventory"),
        (_MARGIN_OPEN, {}, {"BTC/EUR": 0.0001}, "a margin open on BTC/EUR beside 0.0001 BTC spot inventory"),
        (_MARGIN_OPEN, {}, {"BTC/EUR": 0.00005}, None),
        (
            _intent(symbol="DOGE/EUR", leverage=2),
            {},
            {"DOGE/EUR": 12.5},
            "a margin open on DOGE/EUR beside 12.5 DOGE spot inventory",
        ),
        (_intent(), {}, {"BTC/EUR": 0.01}, None),
        (_MARGIN_OPEN, {"BTC/EUR": 0.001}, {}, None),
        (_SPOT_CLOSE, {"BTC/EUR": 0.001}, {"BTC/EUR": 0.001}, None),
        (_MARGIN_CLOSE, {"BTC/EUR": 0.001}, {"BTC/EUR": 0.001}, None),
    ],
    ids=[
        "spot-open-beside-margin",
        "margin-open-beside-spot",
        "margin-open-beside-spot-at-ordermin",
        "margin-open-beside-spot-dust",
        "margin-open-beside-spot-on-doge",
        "spot-beside-spot",
        "margin-beside-margin",
        "spot-close",
        "margin-close",
    ],
)
def test_an_opening_intent_that_would_mix_spot_and_margin_inventory_on_its_pair_is_refused_and_a_close_never_is(
    tmp_path, intent, margin, spot, refused
):
    """The refusal 00118 D11 carries into spec 00120 D12, on what can create the mixed shape alone: a
    spot open where the venue's margin positions hold the pair, a margin open where the venue's book
    holds spot inventory of the base at or above the pair's `ordermin` (0.0001 on the stub's BTC/EUR)
    -- a lot under it is dust the engine cannot sell. The same kind beside itself, and a close of
    either kind beside both, are admitted -- the Cache's own position would read a spot lot as the
    margin one, so the margin figure is the venue's, and a close takes inventory off."""
    positions = _VenuePositions(margin)
    ex = _executor(
        tmp_path,
        client=StubClient(),
        config=_cache_config(tmp_path),
        venue_holdings=_VenueHoldings(spot),
        venue_positions=positions,
    )
    _drop_plan(tmp_path, _plan_dict(intents=[intent]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    expected = [f"intent 0: {refused} -- the cache's restore does not distinguish them"] if refused else []
    reads = 1 if intent["action"] == "open" else 0  # a plan of closes reads no venue position
    assert (entry["disposition"], entry["reasons"], positions.calls) == ("refused" if refused else "accepted", expected, reads)


def test_the_mixed_inventory_check_reads_no_venue_position_for_a_plan_of_closes_or_without_the_cache(tmp_path):
    positions = _VenuePositions({"BTC/EUR": 0.001})
    ex = _executor(tmp_path, client=StubClient(StubCache(balances={"ZEUR": 1000.0, "XXBT": 0.01})), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict())
    ex.on_timer(NOW)
    assert (_plan_entry(tmp_path)["disposition"], positions.calls) == ("accepted", 0)

    ex = _executor(
        tmp_path,
        client=StubClient(StubCache(balances={"ZEUR": 1000.0, "XXBT": 0.01})),
        config=_cache_config(tmp_path),
        venue_positions=positions,
    )
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", intents=[_SPOT_CLOSE]))
    ex.on_timer(NOW + timedelta(seconds=5))
    assert (_plan_entry(tmp_path, index=1)["disposition"], positions.calls) == ("accepted", 0)


@pytest.mark.parametrize("enabled", [True, False])
def test_a_plan_with_an_opening_intent_waits_for_a_tick_with_nothing_in_flight_before_the_mixed_inventory_read(tmp_path, enabled):
    """The startup pass's cancel of an adopted order is PENDING_CANCEL on the tick it goes out, and the
    mixed-inventory check's positions read is a signed read on the same key: with the cache enabled
    the plan waits in its file for a tick with nothing in flight, and is picked up on the next one;
    without the cache no venue read is made and the plan is picked up on the first tick."""

    class _PendingCancel(StubClient):
        def cancel_order(self, client_order_id):
            super().cancel_order(client_order_id)
            self.cache.order(client_order_id).apply(
                _event(OrderPendingCancel, client_order_id=str(client_order_id), strategy_id=StrategyId("EXTERNAL"))
            )

    adopted = "OADOPT-AAAAA-BBBBBB"
    client = _PendingCancel(
        StubCache(open_orders=[_resting_limit_order(adopted, venue_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))])
    )
    positions = _VenuePositions()
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path, enabled), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict())

    with _executor_errors(level=logging.INFO) as records:
        ex.on_timer(NOW)

    assert [str(cid) for cid in client.canceled] == [adopted] and client.cache.order(ClientOrderId(adopted)).is_inflight
    held = "probe plan p-1 waits for a tick with nothing in flight -- its opening intents take a venue read"
    if enabled:
        assert _plan_path(tmp_path).exists() and positions.calls == 0
        assert held in [r.getMessage() for r in records]
        client.cache.order(ClientOrderId(adopted)).apply(
            _event(OrderCanceled, client_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))
        )
        ex.on_timer(NOW + timedelta(seconds=5))
    else:
        assert held not in [r.getMessage() for r in records]
    assert not _plan_path(tmp_path).exists()
    assert (_plan_entry(tmp_path)["disposition"], positions.calls) == ("accepted", 1 if enabled else 0)


def test_a_margin_position_read_that_fails_refuses_the_opening_intents_by_name(tmp_path):
    positions = _VenuePositions(raises=RuntimeError("timed out"))
    ex = _executor(tmp_path, client=StubClient(StubCache()), config=_cache_config(tmp_path), venue_positions=positions)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(), _SPOT_CLOSE]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"]) == (
        "refused",
        ["intent 0: the venue's margin positions could not be read for the mixed-inventory check -- RuntimeError: timed out"],
    )


# --- the withdrawal check's second source: the venue's trade history (spec 00120 D19) ---------------


def _cold_start_row(tmp_path, *, finished=False):
    """A cold start's shape: the ledger recorded 0.4 filled on an order the Cache holds under the venue's
    txid at ACCEPTED with no fill applied -- the library created it from the venue's report and applied
    none of the trade history's fills to it. `finished` closes the row on that quantity instead."""
    earlier = NOW - timedelta(hours=4)
    _submitted_row(tmp_path, "O-cold", reduce_only=False, when=earlier, venue_order_id=_TXID, qty=1.0)
    update_submitted_row(
        tmp_path / "journal", _boundary(earlier), "O-cold", add_filled_qty=0.4, state="filled" if finished else None
    )
    return earlier


@pytest.mark.parametrize("finished", [False, True])
def test_a_cold_starts_order_figure_short_of_the_ledger_is_no_withdrawal_when_the_trade_history_covers_it(tmp_path, finished):
    earlier = _cold_start_row(tmp_path, finished=finished)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    cache = (
        StubCache(closed_orders=[_closed_order("O-cold", OrderStatus.FILLED, filled_qty=0.0, venue_order_id=_TXID)])
        if finished
        else StubCache(open_orders=[order])
    )
    client = StubClient(cache)
    fills = _VenueFills(_fill_report(_TXID, "0.4"))
    ex = _executor(tmp_path, client=client, gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    assert not _kill_file(tmp_path).exists()
    assert fills.calls == [_boundary(earlier) - timedelta(hours=1)]
    row = _record(tmp_path, earlier)["submitted"][0]
    assert (
        row["filled_qty"] == 0.4 and [e.get("event") for e in row["events"] if e.get("event") in ("withdrawn", "reconciled")] == []
    )
    kind = "finished order" if finished else "adopted order"
    assert f"{kind} O-cold (Kraken {_TXID}) reads 0 filled on its order figure against the 0.4" in " ".join(
        r.getMessage() for r in records
    )
    if not finished:
        assert [str(cid) for cid in client.canceled] == [_TXID]  # cancelled as an order the ledger carries as no reducer
        assert "O-cold" in ex._rows_the_pass_repaired  # a fill the library infers at the ack credits nothing beyond the Cache


@pytest.mark.parametrize(
    "history",
    [(), (("0.2", _TXID), ("0.4", f"{_TXID}-other"))],
    ids=["no-fill", "short-on-the-txid-and-covered-on-another"],
)
@pytest.mark.parametrize("finished", [False, True])
def test_a_true_withdrawal_with_no_fill_in_the_trade_history_trips_the_kill_switch_as_today(
    tmp_path, finished, history, kill_trip_expected
):
    """The cover is the row's own txid's sum: a history short on that txid trips however much another
    order's fills would make up, and presence alone is no cover."""
    earlier = _cold_start_row(tmp_path, finished=finished)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    cache = (
        StubCache(closed_orders=[_closed_order("O-cold", OrderStatus.FILLED, filled_qty=0.0, venue_order_id=_TXID)])
        if finished
        else StubCache(open_orders=[order])
    )
    fills = _VenueFills(*(_fill_report(txid, qty, trade_id=f"T-h{i}") for i, (qty, txid) in enumerate(history)))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    ex.on_timer(NOW)

    assert fills.calls == [_boundary(earlier) - timedelta(hours=1)]
    assert f"O-cold (Kraken {_TXID}) shows 0 filled at the venue, less than the 0.4" in _kill_file(tmp_path).read_text()
    last = _record(tmp_path, earlier)["submitted"][0]["events"][-1]
    assert (last.get("event"), last.get("type")) == (("withdrawn", None) if finished else (None, "OrderAccepted"))


def test_a_trade_history_read_that_fails_leaves_the_withdrawal_check_on_the_order_figure(tmp_path, kill_trip_expected):
    earlier = _cold_start_row(tmp_path)
    order = _resting_limit_order(_TXID, venue_order_id=_TXID, strategy_id=StrategyId("EXTERNAL"))
    fills = _VenueFills(raises=RuntimeError("timed out"))
    ex = _executor(
        tmp_path, client=StubClient(StubCache(open_orders=[order])), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills
    )

    with _executor_errors(level=logging.CRITICAL) as records:
        ex.on_timer(NOW)

    assert len(fills.calls) == 1 and f"O-cold (Kraken {_TXID}) shows 0 filled at the venue" in _kill_file(tmp_path).read_text()
    assert "the venue's trade history could not be read for the withdrawal check -- the order's figure decides" in [
        r.getMessage() for r in records
    ]
    _ = earlier


def test_the_trade_history_is_read_once_per_pass_from_the_earliest_rows_boundary_and_a_failed_read_is_not_retried(
    tmp_path, kill_trip_expected
):
    """D19's once per pass: two finished rows short of the ledger, under two boundaries, and a reader
    that raises -- one call, from one hour before the earlier boundary, both rows tripping on their
    order figure."""
    rows = {"O-cold-1": (NOW - timedelta(hours=4), f"{_TXID}-1"), "O-cold-2": (NOW - timedelta(hours=8), f"{_TXID}-2")}
    for cid, (when, txid) in rows.items():
        _submitted_row(tmp_path, cid, reduce_only=False, when=when, venue_order_id=txid, qty=1.0)
        update_submitted_row(tmp_path / "journal", _boundary(when), cid, add_filled_qty=0.4, state="filled")
    cache = StubCache(
        closed_orders=[
            _closed_order(cid, OrderStatus.FILLED, filled_qty=0.0, venue_order_id=txid) for cid, (_, txid) in rows.items()
        ]
    )
    fills = _VenueFills(raises=RuntimeError("timed out"))
    ex = _executor(tmp_path, client=StubClient(cache), gate=_gate(tmp_path, GateLevel.REDUCE_ONLY), venue_fills=fills)

    ex.on_timer(NOW)

    assert fills.calls == [_boundary(NOW - timedelta(hours=8)) - timedelta(hours=1)]
    assert _kill_file(tmp_path).exists()


# --- the boundary's cycle plan: the book read, the table, the window, the carry, the record, the gap gauge ---

RUNG2 = Path(__file__).parent / "fixtures" / "rung2"
_RUNG2_12Z = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)  # the fixture's cycle_ts
_TEN_EUR_LEGS = sorted(executor_module._SPOT_SYMBOL_BY_BASE.values())


def _rung2_venue() -> dict:
    return json.loads((RUNG2 / "venue-12.json").read_text())


def _rung2_holdings() -> dict[str, float]:
    """`balance.json`'s nine coins under their EUR pairs, read by the rung-2 helper's own parse."""
    export = parse_balance_export(json.loads((RUNG2 / "balance.json").read_text()))
    return {f"{base}/EUR": qty for base, qty in export.held.items()}


def _rung2_record(tmp_path: Path, **changes) -> Path:
    """The fixture's cycle record with `changes`, written beside the case: a later `cycle_ts` moves the 4-hourly
    snapshots with it and re-dates the daily ones, so the copy still validates."""
    record = from_json((RUNG2 / "cycle-12.json").read_text())
    if "cycle_ts" in changes:
        at = changes["cycle_ts"]
        shift = at - record.cycle_ts
        daily_last = at.replace(hour=0) - timedelta(days=1)
        changes["snapshots"] = tuple(
            dataclasses.replace(s, first_ts=s.first_ts + shift, last_ts=s.last_ts + shift)
            if s.grid == "240"
            else dataclasses.replace(s, first_ts=daily_last - (s.last_ts - s.first_ts), last_ts=daily_last)
            for s in record.snapshots
        )
        changes.setdefault("started_at", record.started_at + shift)
        changes.setdefault("completed_at", record.completed_at + shift)
    record = dataclasses.replace(record, **changes)
    path = tmp_path / "records" / f"cycle-{record.cycle_ts:%Y%m%d%H}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(to_json(record))
    return path


def _journal_cycle_record(tmp_path: Path, record_path: Path) -> CycleRecord:
    record = from_json(record_path.read_text())
    day = tmp_path / "journal" / f"{record.cycle_ts:%Y-%m-%d}"
    day.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(record_path, day / f"cycle-{record.cycle_ts:%H}.json")
    return record


def _accum_doc(at: datetime, status: str, **fields) -> dict:
    doc = dict.fromkeys(("nav", "eur_total", "eur_free", "equity_eur", "hwm_eur", "drawdown_bps", "day_loss_bps"))
    return (
        doc
        | {
            "schema_version": ACCUM_SCHEMA_VERSION,
            "cycle_ts": at.isoformat(),
            "drafted_at": at.isoformat(),
            "status": status,
            "day_loss_hold": False,
            "plan_id": None,
            "legs": [],
        }
        | fields
    )


def _boundary_executor(
    tmp_path, *, record_path, holdings, eur_total, eur_free, now, statuses=None, earn=None, series=(), plan_cap=1000.0
):
    """An executor at a boundary whose cycle record is `record_path`'s, journaled under its own day: the venue truth
    is `venue-12.json`'s instruments, the book every `INSTRUMENT_IDS` symbol -- 0.0 where `holdings` names none, as
    `read_venue_book` answers all twelve -- and every leg `TRADING` but the ones `statuses` names. `series` is the
    equities of the boundaries before it, oldest first, journaled as their `ok` draft records, the equity series
    started at the first of them; with none, the boundary's mark starts it."""
    record = _journal_cycle_record(tmp_path, record_path)
    for i, equity in enumerate(series):
        at = record.cycle_ts - timedelta(hours=4 * (len(series) - i))
        write_accum_record(tmp_path / "journal", at, _accum_doc(at, "ok", equity_eur=equity))
    if series:
        _start_series(tmp_path, record.cycle_ts - timedelta(hours=4 * len(series)))
    venue = _rung2_venue()["state"]
    instruments = {
        entry["instrument_id"]: _fake_instrument(
            entry["instrument_id"], ordermin=entry["ordermin"], lot_step=entry["lot_step"], tick_size=entry["tick_size"]
        )
        for entry in venue["instruments"].values()
    }
    client = StubClient(StubCache(instruments=instruments, balances=venue["balances"]))
    clock = _Clock(now)
    listed = dict.fromkeys(INSTRUMENT_IDS, "TRADING") | dict(statuses or {})
    ex = _executor(
        tmp_path,
        client=client,
        clock=clock,
        config=_config(tmp_path, exec_max_plan_notional_eur=plan_cap),
        venue_holdings=_VenueHoldings(
            dict.fromkeys(INSTRUMENT_IDS, 0.0) | dict(holdings), eur_total=eur_total, eur_free=eur_free, earn=earn
        ),
        instrument_statuses=lambda: dict(listed),
    )
    return ex, client, clock


def _series_start_path(tmp_path: Path) -> Path:
    # Spelled as the owner's procedures spell it, never through the module's constant: the re-mint is a hand `rm`.
    return exec_dir(tmp_path) / "equity-series-start"


def _start_series(tmp_path: Path, at: datetime) -> None:
    _series_start_path(tmp_path).parent.mkdir(parents=True, exist_ok=True)
    _series_start_path(tmp_path).write_text(f"{at.isoformat()}\n")


def _accum(tmp_path: Path, when: datetime = _RUNG2_12Z) -> dict:
    return read_accum_record(accum_record_path(tmp_path / "journal", when))


def _legs(tmp_path: Path, when: datetime = _RUNG2_12Z) -> dict[str, dict]:
    return {leg["symbol"]: leg for leg in _accum(tmp_path, when)["legs"]}


def _ticks(ex, clock, n: int) -> None:
    for _ in range(n):
        ex.on_timer(clock.now)
        clock.now += timedelta(seconds=5)


def _only(*symbols: str) -> dict[str, float]:
    """The fixture's targets with every leg but `symbols` at 0.0."""
    targets = from_json((RUNG2 / "cycle-12.json").read_text()).final_targets
    return {symbol: weight if symbol in symbols else 0.0 for symbol, weight in targets.items()}


def _the_ten_at(weight: float) -> dict[str, float]:
    return {symbol: weight if symbol.endswith("/EUR") else 0.0 for symbol in INSTRUMENT_IDS}


def test_rung_twos_entry_day_drafts_the_ten_legs_at_nav_1000_with_the_notionals_the_floor_arithmetic_gives(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    plan = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert plan["plan_id"] == "r3-20261005-12" and plan["disposition"] == "accepted"
    intents = {i["symbol"]: i for i in plan["plan"]["intents"]}
    assert set(intents) == set(_TEN_EUR_LEGS) and "LINK/EUR" in intents
    # targets 38.6427 and 15.3318, a buy floored to the cent
    assert intents["BTC/EUR"]["notional_eur"] == pytest.approx(38.64, abs=0.005)
    assert intents["LINK/EUR"]["notional_eur"] == pytest.approx(15.33, abs=0.005)
    record = _accum(tmp_path)
    assert record["status"] == "ok" and record["nav"] == 1000.0 and record["eur_free"] == 1500.0
    assert record["plan_id"] == "r3-20261005-12" and all(leg["outcome"] == "placed" for leg in record["legs"])


def test_the_loops_rows_at_eur_720_on_the_nine_legs_equal_the_helpers_decision_rows(tmp_path, monkeypatch):
    """The helper's rows are recomputed here -- `decide_leg` at its hand-window defaults over the same fixtures, the
    box's own decision log being gitignored -- and the loop's are its table's, as `decide_leg` returns them before the
    cash trim and the plan, where the two differ by design: the reserve, the split and the cap."""
    rows: list = []
    real = executor_module.decide_leg
    monkeypatch.setattr(executor_module, "decide_leg", lambda *args, **kwargs: rows.append(real(*args, **kwargs)) or rows[-1])
    holdings = _rung2_holdings()
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, nav=720.0),
        holdings=holdings,
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)

    record = from_json((RUNG2 / "cycle-12.json").read_text())
    venue = _rung2_venue()["state"]
    helper = [
        decide_leg(
            symbol,
            weight=record.final_targets[symbol],
            price=record.closes[symbol.split("/")[0]],
            constraints=Constraints(
                ordermin=venue["instruments"][symbol]["ordermin"], lot_step=venue["instruments"][symbol]["lot_step"]
            ),
            kraken_held=holdings[symbol],
            engine_held=None,
            venue_b=venue_balance(venue["balances"], symbol.split("/")[0]),
        )
        for symbol in LEGS
    ]

    def _row(leg):
        return (leg.symbol, leg.outcome, leg.side, leg.notional_eur, leg.qty, leg.reason)

    loop = {leg.symbol: _row(leg) for leg in rows}
    assert sorted(loop) == _TEN_EUR_LEGS
    assert [loop[leg.symbol] for leg in helper] == [_row(leg) for leg in helper]
    assert {leg.outcome for leg in helper} == {"placed", "carried"}


def test_a_sidecar_boundary_writes_no_cycle_and_drafts_nothing(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    (tmp_path / "journal" / f"{_RUNG2_12Z:%Y-%m-%d}" / "failed-cycle-12.json").write_text("{}")
    ex.on_boundary(_RUNG2_12Z)
    _ticks(ex, clock, 2)
    record = _accum(tmp_path)
    assert record["status"] == "no-cycle" and record["legs"] == [] and record["plan_id"] is None
    assert _record(tmp_path, _RUNG2_12Z)["plans"] == [] and metrics.not_drafted == [True]


def test_a_book_read_that_fails_three_ticks_writes_book_unread_and_the_next_boundary_absorbs_the_gap(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    holdings = ex._venue_holdings
    holdings._raises = RuntimeError("EAPI:Invalid nonce")
    ex.on_boundary(_RUNG2_12Z)
    _ticks(ex, clock, 3)
    assert accum_record_path(tmp_path / "journal", _RUNG2_12Z).exists()
    record = _accum(tmp_path)
    assert record["status"] == "book-unread" and record["legs"] == [] and record["eur_free"] is None
    assert _record(tmp_path, _RUNG2_12Z)["plans"] == [] and holdings.calls == 4  # the startup pass's, then three

    later = _RUNG2_12Z + timedelta(hours=4)
    _journal_cycle_record(tmp_path, _rung2_record(tmp_path, cycle_ts=later))
    holdings._raises = None
    clock.now = later + timedelta(minutes=2)
    ex.on_boundary(later)
    ex.on_timer(clock.now)
    plan = _plan_entry(tmp_path, when=later)
    assert plan["plan_id"] == "r3-20261005-16" and plan["disposition"] == "accepted"
    assert {i["symbol"] for i in plan["plan"]["intents"]} == set(_TEN_EUR_LEGS)


def test_an_earn_coded_basket_coin_refuses_the_drafts_held_and_three_ticks_write_book_unread(tmp_path):
    """`SOL.F` holding 2.0 beside a spot 0.5 (`earn={"SOL": 2.0}`): the book answers, the draft refuses `held` at
    WARNING with `2 SOL is held outside the spot wallet` three ticks running, and the third writes `book-unread` with
    no plan entry; the probe skips the refusal and SOL/EUR is drafted against its spot 0.5."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={"SOL/EUR": 0.5},
        eur_total=1500.0,
        eur_free=1500.0,
        earn={"SOL": 2.0},
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    with _executor_errors(level=logging.WARNING) as records:
        _ticks(ex, clock, 3)
    assert accum_record_path(tmp_path / "journal", _RUNG2_12Z).exists()
    record = _accum(tmp_path)
    assert record["status"] == "book-unread" and record["legs"] == [] and record["eur_free"] == 1500.0
    assert _record(tmp_path, _RUNG2_12Z)["plans"] == []
    assert sum("2 SOL is held outside the spot wallet" in r.getMessage() for r in records) == 3


def _left_pending_cancel():
    """An order the startup pass cancels and the venue has not answered: PENDING_CANCEL, in flight in the Cache's
    terms."""
    order = _open_order("O-left-by-the-last-process", venue_order_id="OLEFT-AAAAA-BBBBBB")
    order.is_inflight = True
    return order


def test_the_whole_draft_waits_on_a_tick_with_nothing_in_flight_and_created_at_is_that_ticks_now(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    client.cache._open_orders.append(_left_pending_cancel())
    ex.on_boundary(_RUNG2_12Z)
    _ticks(ex, clock, 2)
    assert _record(tmp_path, _RUNG2_12Z)["plans"] == [] and ex._venue_holdings.calls == 1  # the startup pass's alone

    client.cache._open_orders.clear()
    clock.now = _RUNG2_12Z + timedelta(minutes=7)
    ex.on_timer(clock.now)
    plans = _record(tmp_path, _RUNG2_12Z)["plans"]
    assert len(plans) == 1 and plans[0]["disposition"] == "accepted"
    assert plans[0]["plan"]["created_at"] == plans[0]["received_at"] == clock.now.isoformat()


def test_a_draft_still_waiting_past_the_window_writes_window_closed(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    client.cache._open_orders.append(_left_pending_cancel())
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    clock.now = _RUNG2_12Z + timedelta(hours=3, minutes=31)
    ex.on_timer(clock.now)
    assert accum_record_path(tmp_path / "journal", _RUNG2_12Z).exists()
    record = _accum(tmp_path)
    assert record["status"] == "window-closed" and record["legs"] == [] and metrics.not_drafted == [True]
    assert _record(tmp_path, _RUNG2_12Z)["evaluated_at"] == clock.now.isoformat() and ex._pending_draft is None


@pytest.mark.parametrize(
    ("ends", "starts"), [(timedelta(hours=3, minutes=29), True), (timedelta(hours=3, minutes=31), False)], ids=["3h29", "3h31"]
)
def test_an_intent_does_not_start_past_the_windows_close_and_is_journaled_carried(tmp_path, ends, starts):
    """An intent whose predecessor ends at B+3h31 is carried with `the submission window closed`; at B+3h29 it starts.
    The probe deletes the close and the B+3h31 start then happens."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR", "ETH/EUR")),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + ends - timedelta(minutes=5),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    ex.on_quote(_quote(bid=98250.0, ask=98250.1))
    order = client.submitted[-1][0]
    ex.on_order_event(_accepted(str(order.client_order_id)))
    _advance_with_quotes(ex, client, clock, minutes=5, bid=98250.0, ask=98250.1)
    assert clock.now == _RUNG2_12Z + ends and not client.canceled
    _deliver_fill(ex, client, str(order.client_order_id), float(order.quantity), px=98250.0)
    ex.on_timer(clock.now)

    second = _intent_entry(tmp_path, 1, when=_RUNG2_12Z)
    if starts:
        assert second["outcome"] == "pending" and client.subscribed == ["BTC/EUR.KRAKEN", "ETH/EUR.KRAKEN"]
    else:
        assert second["outcome"] == "carried" and second["reasons"] == ["the submission window closed"]
        assert client.subscribed == ["BTC/EUR.KRAKEN"]


def test_a_leg_with_an_open_ledger_row_is_carried_until_the_venue_has_answered_it(tmp_path):
    """A BTC/EUR row `ambiguous` inside the window: the draft carries BTC/EUR with the open-row reason and drafts no
    second sell; with the row closed the next draft sells."""
    earlier = _RUNG2_12Z - timedelta(hours=4)
    _submitted_row(tmp_path, "O-ambiguous", reduce_only=True, when=earlier)
    update_submitted_row(tmp_path / "journal", earlier, "O-ambiguous", state="ambiguous")
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR")),
        holdings={"BTC/EUR": 0.001},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    assert _record(tmp_path, _RUNG2_12Z)["plans"] == []
    btc = _legs(tmp_path)["BTC/EUR"]
    assert btc["outcome"] == "carried" and btc["reason"] == "an order of this symbol may still rest at the venue"

    update_submitted_row(tmp_path / "journal", earlier, "O-ambiguous", state="canceled")
    later = _RUNG2_12Z + timedelta(hours=4)
    _journal_cycle_record(tmp_path, _rung2_record(tmp_path, final_targets=_only("BTC/EUR"), cycle_ts=later))
    clock.now = later + timedelta(minutes=2)
    ex.on_boundary(later)
    ex.on_timer(clock.now)
    intents = _plan_entry(tmp_path, when=later)["plan"]["intents"]
    assert [(i["symbol"], i["side"]) for i in intents] == [("BTC/EUR", "sell")]


def test_a_re_armed_draft_after_a_restart_inside_the_window_is_refused_by_the_dedup_wall(tmp_path):
    """The previous process journaled the boundary's plan and ended before its draft record was written: the first
    tick after the restart arms the boundary again, and the plan it drafts is refused `plan_id already ledgered`. A
    third process finds the record naming the plan and arms nothing."""
    kwargs = dict(record_path=RUNG2 / "cycle-12.json", holdings={}, eur_total=1500.0, eur_free=1500.0)
    ex, client, clock = _boundary_executor(tmp_path, now=_RUNG2_12Z + timedelta(minutes=2), **kwargs)
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    assert _plan_entry(tmp_path, when=_RUNG2_12Z)["disposition"] == "accepted"
    accum_record_path(tmp_path / "journal", _RUNG2_12Z).unlink()

    restarted, _, restart_clock = _boundary_executor(tmp_path, now=_RUNG2_12Z + timedelta(minutes=10), **kwargs)
    restarted.on_timer(restart_clock.now)
    assert accum_record_path(tmp_path / "journal", _RUNG2_12Z).exists()
    record = _accum(tmp_path)
    entry = _plan_entry(tmp_path, when=_RUNG2_12Z, index=1)
    assert record["status"] == "refused" and record["plan_id"] == "r3-20261005-12"
    assert entry["plan_id"] == "r3-20261005-12" and entry["reasons"] == ["plan_id already ledgered"]
    carried = {leg["symbol"] for leg in record["legs"] if leg["reason"] == "plan_id already ledgered"}
    assert carried and carried == {i["symbol"] for i in entry["plan"]["intents"]}

    third, _, third_clock = _boundary_executor(tmp_path, now=_RUNG2_12Z + timedelta(minutes=20), **kwargs)
    third.on_timer(third_clock.now)
    assert _accum(tmp_path) == record and len(_record(tmp_path, _RUNG2_12Z)["plans"]) == 2


def test_a_drill_plan_dropped_during_a_cycle_plan_waits_in_its_file(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR", "ETH/EUR")),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    drill = _drop_plan(tmp_path, _plan_dict(plan_id="drill-1", created_at=clock.now))
    _ticks(ex, clock, 2)
    assert drill.exists() and [e["plan_id"] for e in _record(tmp_path, _RUNG2_12Z)["plans"]] == ["r3-20261005-12"]

    _ticks(ex, clock, 20)  # each intent of the cycle plan ends with no quote inside its wait
    assert not drill.exists()
    assert [e["plan_id"] for e in _record(tmp_path, _RUNG2_12Z)["plans"]] == ["r3-20261005-12", "drill-1"]


def test_a_eur_160_leg_at_nav_1000_is_drafted_into_the_boundarys_one_plan(tmp_path):
    """A synthetic record with BTC/EUR at weight 0.16: the loop drafts the leg where the helper's `assemble_plans`
    raises at the 95 EUR cap; the helper's own tests' assertions are untouched."""
    targets = {**_only(*_TEN_EUR_LEGS), "BTC/EUR": 0.16}
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=targets),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    plans = _record(tmp_path, _RUNG2_12Z)["plans"]
    assert len(plans) == 1 and plans[0]["disposition"] == "accepted"
    assert {i["symbol"]: i["notional_eur"] for i in plans[0]["plan"]["intents"]}["BTC/EUR"] == 160.0
    leg = decide_leg(
        "BTC/EUR",
        weight=0.16,
        price=98250.0,
        constraints=Constraints(ordermin=5e-05, lot_step=1e-08),
        kraken_held=0.0,
        engine_held=None,
        venue_b=0.0,
        eur_per_weight=1000.0,
    )
    with pytest.raises(DraftPlanError, match="over the 95 EUR plan cap on its own"):
        assemble_plans([leg])


def test_a_long_book_over_the_cap_from_a_flat_book_drafts_one_plan_at_the_cap_and_carries_the_rest(tmp_path):
    """A synthetic record with the ten EUR legs at 0.12 (long gross 1.2) from a flat book with `eur_free` 1,500 and
    `plan_cap=500.0`, a cap under the sleeve's free cash: the cash trim takes the buys to EUR 990, the sleeve's free
    cash less the reserve, then the table trims them from the smallest until the plan fits
    `exec_max_plan_notional_eur` 500.0, the plan is `accepted` with Σ `notional_eur` ≤ 500 and the legs the cap
    carries name it."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_the_ten_at(0.12)),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        plan_cap=500.0,
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    plans = _record(tmp_path, _RUNG2_12Z)["plans"]
    assert len(plans) == 1 and plans[0]["disposition"] == "accepted"
    intents = {i["symbol"]: i["notional_eur"] for i in plans[0]["plan"]["intents"]}
    assert intents == dict.fromkeys(("LINK/EUR", "LTC/EUR", "SOL/EUR", "XRP/EUR"), 120.0)  # 480, the cap's fit
    capped = {s for s, leg in _legs(tmp_path).items() if leg["reason"] == "over the plan cap 500 EUR; carries to the next boundary"}
    assert capped == {"AVAX/EUR", "BTC/EUR", "DOGE/EUR", "DOT/EUR", "ETH/EUR"}


def test_the_buys_are_bounded_by_the_sleeves_free_cash_and_never_by_the_accounts(tmp_path):
    """A synthetic record with the ten EUR legs at 0.12, the book holding each leg at EUR 60 at the record's close
    (EUR 600 of coin) on an account whose `eur_free` is 1,500: the sleeve's free cash is 400, so the buys, about EUR 60
    a leg, trim to Σ `notional_eur` ≤ 390 with the cash trim's reason on the legs it carries; a second build with
    `eur_free` 200 trims them to ≤ 190, the account's cash the bound."""
    closes = from_json((RUNG2 / "cycle-12.json").read_text()).closes
    holdings = {f"{base}/EUR": 60.0 / close for base, close in closes.items()}
    for eur_free, bound in ((1500.0, 390.0), (200.0, 190.0)):
        case = tmp_path / f"free-{eur_free:.0f}"
        case.mkdir()
        ex, client, clock = _boundary_executor(
            case,
            record_path=_rung2_record(case, final_targets=_the_ten_at(0.12)),
            holdings=holdings,
            eur_total=eur_free,
            eur_free=eur_free,
            now=_RUNG2_12Z + timedelta(minutes=2),
        )
        ex.on_boundary(_RUNG2_12Z)
        ex.on_timer(clock.now)
        plans = _record(case, _RUNG2_12Z)["plans"]
        assert len(plans) == 1 and plans[0]["disposition"] == "accepted"
        total = sum(i["notional_eur"] for i in plans[0]["plan"]["intents"])
        assert 0.0 < total <= bound + 1e-9, (eur_free, total)
        assert any(leg["reason"] == "buys beyond free EUR - 10 trim from the smallest" for leg in _legs(case).values())


def test_a_closed_week_holding_an_undrafted_boundary_is_refused_naming_it(tmp_path):
    """42 `full` exec records with a `book-unread` record at one boundary: `_score_closed_week` refuses the week at
    that boundary; with the record `ok` it scores. The probe deletes the accum read and the week scores either way."""
    _journal_week(tmp_path, fills=_HEALTHY_FILLS, lead=6)
    undrafted = _IN_WEEK
    write_accum_record(tmp_path / "journal", undrafted, _accum_doc(undrafted, "book-unread"))
    with _executor_errors(level=logging.WARNING) as records:
        tripped, states = _tracking_states(tmp_path)
    assert not tripped and states == [executor_module._TRACKING_UNSCORED]
    assert any(f"below the full level or undrafted (first at {undrafted.isoformat()})" in r.getMessage() for r in records)

    write_accum_record(tmp_path / "journal", undrafted, _accum_doc(undrafted, "ok"))
    tripped, states = _tracking_states(tmp_path)
    assert not tripped and states == [executor_module._TRACKING_WITHIN_BAND]


def test_an_intent_of_the_cycle_plan_re_sets_its_legs_gap_by_what_it_filled_and_a_refused_one_reads_its_whole_delta(
    tmp_path,
):
    """The draft reads each leg's whole delta; BTC's intent fills and its leg reads the delta less the fill at the
    close, about 0, and ETH's, refused at its start under a gate disarmed meanwhile, reads its whole delta."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR", "ETH/EUR")),
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    legs = _legs(tmp_path)
    assert dict(metrics.gaps) == {symbol: leg["delta_eur"] for symbol, leg in legs.items()}

    ex.on_quote(_quote(bid=98250.0, ask=98250.1))
    order = client.submitted[-1][0]
    ex.on_order_event(_accepted(str(order.client_order_id)))
    _deliver_fill(ex, client, str(order.client_order_id), float(order.quantity), px=98250.0)
    (exec_dir(tmp_path) / ARM_FILE).unlink()
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert _intent_outcome(tmp_path, 0, when=_RUNG2_12Z) == "filled" and _intent_outcome(tmp_path, 1, when=_RUNG2_12Z) == "refused"
    gaps = dict(metrics.gaps)
    assert gaps["BTC/EUR"] == pytest.approx(legs["BTC/EUR"]["delta_eur"] - float(order.quantity) * 98250.0)
    assert abs(gaps["BTC/EUR"]) < 0.01 and gaps["ETH/EUR"] == legs["ETH/EUR"]["delta_eur"]


def test_the_cross_check_logs_the_venue_holds_warning_and_drafts_from_the_venues_figure(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={"BTC/EUR": 0.0002},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    ex.on_boundary(_RUNG2_12Z)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(clock.now)
    assert (
        "the venue holds 0.0002 BTC/EUR where the Cache reads 0 -- the position gauge takes the venue's figure at the boundary read"
    ) in [r.getMessage() for r in records]
    btc = _legs(tmp_path)["BTC/EUR"]
    assert btc["held_qty"] == 0.0002 and btc["cache_net"] == 0.0
    assert btc["delta_eur"] == pytest.approx(38.6427 - 0.0002 * 98250.0) and btc["notional_eur"] == 18.99


def test_the_gap_gauge_reads_each_legs_delta_at_the_draft_placed_or_carried(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={"BTC/EUR": 0.0002},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        statuses={"SOL/EUR": "PAUSE"},
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    legs = _legs(tmp_path)
    assert legs["SOL/EUR"]["outcome"] == "carried" and legs["BTC/EUR"]["outcome"] == "placed"
    assert sorted(metrics.gaps) == sorted((symbol, leg["delta_eur"]) for symbol, leg in legs.items())


def test_a_leg_whose_instrument_is_not_online_at_the_boundary_is_carried_with_the_status_in_its_reason(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        statuses={"SOL/EUR": "HALT"},
    )
    ex.on_boundary(_RUNG2_12Z)
    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(clock.now)
    plan = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert plan["disposition"] == "accepted"
    assert {i["symbol"] for i in plan["plan"]["intents"]} == set(_TEN_EUR_LEGS) - {"SOL/EUR"}
    sol = _legs(tmp_path)["SOL/EUR"]
    assert sol["outcome"] == "carried" and sol["side"] is None and "HALT, not TRADING" in sol["reason"]
    assert sol["delta_eur"] == pytest.approx(24.71, abs=0.01)
    assert "the venue lists SOL/EUR HALT, not TRADING -- the leg carries to the next boundary" in [r.getMessage() for r in records]


def test_a_status_read_that_raises_spends_the_book_reads_try_and_three_write_book_unread(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )

    def _unanswered():
        raise RuntimeError("EService:Unavailable")

    ex._instrument_statuses = _unanswered
    ex.on_boundary(_RUNG2_12Z)
    _ticks(ex, clock, 3)
    assert accum_record_path(tmp_path / "journal", _RUNG2_12Z).exists()
    assert _accum(tmp_path)["status"] == "book-unread" and _record(tmp_path, _RUNG2_12Z)["plans"] == []


def test_a_boundary_armed_before_the_startup_pass_has_run_drafts_nothing_until_it_has(tmp_path):
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1500.0,
        eur_free=1500.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )

    unread = [True]
    orders_open = client.cache.orders_open

    def _orders_open(**kwargs):
        if unread[0]:
            raise RuntimeError("cache read failed")
        return orders_open(**kwargs)

    client.cache.orders_open = _orders_open
    ex.on_boundary(_RUNG2_12Z)
    with _executor_errors(level=logging.CRITICAL):
        ex.on_timer(clock.now)
    assert not ex._adopted and _record(tmp_path, _RUNG2_12Z)["plans"] == []

    unread[0] = False
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)
    assert ex._adopted and _plan_entry(tmp_path, when=_RUNG2_12Z)["disposition"] == "accepted"


def test_read_instrument_statuses_reads_the_action_per_symbol_from_the_loopback(_loopback_credentials):
    pairs = json.loads(kraken_loopback.ASSET_PAIRS_FIXTURE.read_text())
    pairs["SOLEUR"]["status"] = "cancel_only"
    with kraken_loopback.serve(pairs) as venue:
        statuses = executor_module.read_instrument_statuses(base_url=venue.base_url)
        assert statuses["SOL/EUR"] == "HALT" and statuses["BTC/EUR"] == "TRADING" and statuses["ADA/EUR"] == "absent"
        assert venue.private_calls == []
        venue.errors["AssetPairs"] = "EService:Unavailable"
        with pytest.raises(RuntimeError, match="EService:Unavailable"):
            executor_module.read_instrument_statuses(base_url=venue.base_url)


# --- the equity mark and the two drawdown trips over the NAV -------------------------------------


def _boundary_drafts(ex, clock, boundary: datetime, record_path: Path | None = None) -> None:
    """A later boundary of the same process: its cycle record journaled, the alert, and the tick that drafts it."""
    if record_path is not None:
        _journal_cycle_record(ex._journal_dir.parent, record_path)
    clock.now = boundary + timedelta(minutes=2)
    ex.on_boundary(boundary)
    ex.on_timer(clock.now)


def _carried_under_the_entrys_reason(record: dict, entry: dict) -> set[str]:
    reason = "; ".join(entry["reasons"])
    carried = {leg["symbol"] for leg in record["legs"] if leg["reason"] == reason}
    assert carried and carried == {i["symbol"] for i in entry["plan"]["intents"]}, (carried, reason)
    return carried


def test_equity_is_marked_at_the_eur_balances_total_and_a_resting_bid_on_hold_trips_nothing(tmp_path):
    """total 1,000, free 850, nothing lost: the mark at `total` reads no drawdown; the probe marks
    at `free` and the 15 % floor trips on a book that lost nothing."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1000.0,
        eur_free=850.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert record["status"] == "ok" and record["equity_eur"] == 1000.0 and record["hwm_eur"] == 1000.0
    assert not _kill_file(tmp_path).exists() and record["drawdown_bps"] == 0.0


def test_a_fifteen_percent_fall_from_the_high_water_mark_latches_the_kill_file_with_the_figures(tmp_path, kill_trip_expected):
    """The series' high-water mark at EUR 1,000 and this boundary's equity at 850, 1500 bps of the NAV 1,000: the
    mark latches the kill file with the figures, ahead of the table; the plan the draft still assembles meets the
    in-process backstop, and the boundary's record reads `refused`, every placed leg carried under the plan entry's
    reason. The probe trips only past the floor, and 1500 bps trips nothing."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=850.0,
        eur_free=850.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    kill = _kill_file(tmp_path)
    assert kill.exists() and kill.read_text().split(" ", 1)[1] == (
        "equity 850.00 EUR is 150.00 EUR under the series' high-water mark of 1000.00 EUR, 1500 bps of the 1000 EUR NAV\n"
    )
    record = _accum(tmp_path)
    entry = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert record["status"] == "refused" and record["drawdown_bps"] == 1500.0 and record["hwm_eur"] == 1000.0
    assert entry["disposition"] == "refused" and entry["reasons"] == [executor_module._TRIPPED_REFUSAL]
    _carried_under_the_entrys_reason(record, entry)
    assert metrics.equity == [850.0] and metrics.drawdowns == [1500.0]


def test_the_hwm_scan_is_bounded_by_the_series_start_and_an_older_drawdown_trips_nothing(tmp_path):
    """A record at equity 1,300 at the boundary before `equity-series-start`'s instant, the same UTC
    day, and this boundary's at 1,000: the bounded scan reads an HWM of 1,000; the probe deletes the
    bound and the kill latches."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1000.0,
        eur_free=1000.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1300.0],
    )
    _start_series(tmp_path, _RUNG2_12Z)
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert record["hwm_eur"] == 1000.0 and record["drawdown_bps"] == 0.0 and not _kill_file(tmp_path).exists()


def test_a_same_day_re_mint_puts_the_days_earlier_records_outside_the_day_loss_base(tmp_path):
    """EUR 160 withdrawn paused at 10Z from a book of 1,000 and the file re-minted at the 12Z boundary:
    the 12Z base is its own equity (840, a loss of 0) and the 16Z base is 12Z's; the probe bounds the
    base by the day instead of the instant and the hold latches on the withdrawal."""
    flat = _the_ten_at(0.0)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=flat),
        holdings={},
        eur_total=840.0,
        eur_free=840.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0, 1000.0, 1000.0],
    )
    _series_start_path(tmp_path).unlink()  # the owner's re-mint, after the withdrawal
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    noon = _accum(tmp_path)
    assert _series_start_path(tmp_path).read_text() == f"{_RUNG2_12Z.isoformat()}\n"
    assert noon["equity_eur"] == 840.0 and noon["drawdown_bps"] == 0.0
    assert noon["day_loss_bps"] == 0.0 and noon["day_loss_hold"] is False

    later = _RUNG2_12Z + timedelta(hours=4)
    ex._venue_holdings.eur_total = 830.0
    _boundary_drafts(ex, clock, later, _rung2_record(tmp_path, final_targets=flat, cycle_ts=later))
    afternoon = _accum(tmp_path, later)
    assert afternoon["day_loss_bps"] == 100.0 and afternoon["day_loss_hold"] is False and not ex._day_loss_hold


def test_a_three_percent_day_loss_latches_the_hold_for_the_date_and_a_recovery_does_not_lift_it(tmp_path):
    """The date's 00Z record at EUR 1,000 and the 12Z mark at 970, 300 bps of the NAV: the hold latches and the 12Z
    record carries it; the 16Z mark back at 1,000 reads a loss of 0, and the hold stands on the 12Z record, in the
    16Z draft record and the 16Z exec record. The probe keeps the hold as the boundary's own loss alone and the
    recovery lifts it."""
    flat = _the_ten_at(0.0)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=flat),
        holdings={},
        eur_total=970.0,
        eur_free=970.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0, 1000.0, 1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    noon = _accum(tmp_path)
    assert noon["day_loss_bps"] == 300.0 and noon["day_loss_hold"] is True and not _kill_file(tmp_path).exists()

    later = _RUNG2_12Z + timedelta(hours=4)
    ex._venue_holdings.eur_total = 1000.0
    _boundary_drafts(ex, clock, later, _rung2_record(tmp_path, final_targets=flat, cycle_ts=later))
    afternoon = _accum(tmp_path, later)
    assert afternoon["day_loss_bps"] == 0.0 and afternoon["day_loss_hold"] is True
    exec_16 = _record(tmp_path, later)
    assert exec_16["level"] == GateLevel.REDUCE_ONLY and "daily_loss_hold" in exec_16["reasons"]


def test_the_hold_is_derived_after_a_restart_from_the_dates_records(tmp_path):
    """The date's 04Z record latched the hold at 400 bps: a process started at 06Z holds opens from its first tick,
    its verdict `reduce_only` with `daily_loss_hold`, before any boundary of its own; the probe deletes the first
    tick's derivation and the restart reads `full`."""
    day = _RUNG2_12Z.replace(hour=0)
    journal = tmp_path / "journal"
    write_accum_record(journal, day, _accum_doc(day, "ok", equity_eur=1000.0, day_loss_bps=0.0))
    dawn = day + timedelta(hours=4)
    write_accum_record(journal, dawn, _accum_doc(dawn, "ok", equity_eur=960.0, day_loss_bps=400.0, day_loss_hold=True))
    clock = _Clock(day + timedelta(hours=6))
    ex = _executor(tmp_path, clock=clock)
    _start_series(tmp_path, day)
    assert ex._day_loss_hold is False

    ex.on_timer(clock.now)

    verdict = ex._evaluate(clock.now)
    assert verdict.level == GateLevel.REDUCE_ONLY and "daily_loss_hold" in verdict.reasons


def test_a_hold_latched_yesterday_is_dropped_at_the_new_dates_first_boundary_whether_or_not_it_marks(tmp_path):
    """The hold latched at 20Z; the 00Z cycle a sidecar (`no-cycle`, no mark): 00Z's exec record reads
    `full` with no `daily_loss_hold`, and the 04Z mark derives afresh."""
    flat = _the_ten_at(0.0)
    evening = _RUNG2_12Z + timedelta(hours=8)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=flat, cycle_ts=evening),
        holdings={},
        eur_total=960.0,
        eur_free=960.0,
        now=evening + timedelta(minutes=2),
        series=[1000.0] * 5,
    )
    ex.on_boundary(evening)
    ex.on_timer(clock.now)
    assert _accum(tmp_path, evening)["day_loss_hold"] is True
    assert _record(tmp_path, evening)["level"] == GateLevel.REDUCE_ONLY

    midnight = evening + timedelta(hours=4)
    day = tmp_path / "journal" / f"{midnight:%Y-%m-%d}"
    day.mkdir(parents=True, exist_ok=True)
    (day / "failed-cycle-00.json").write_text("{}")
    _boundary_drafts(ex, clock, midnight)
    exec_00 = _record(tmp_path, midnight)
    assert exec_00["level"] == GateLevel.FULL and "daily_loss_hold" not in exec_00["reasons"]
    assert exec_00["inputs"]["daily_loss_hold"] is False
    assert _accum(tmp_path, midnight)["status"] == "no-cycle" and _accum(tmp_path, midnight)["day_loss_hold"] is False

    dawn = midnight + timedelta(hours=4)
    _boundary_drafts(ex, clock, dawn, _rung2_record(tmp_path, final_targets=flat, cycle_ts=dawn))
    record = _accum(tmp_path, dawn)
    assert record["day_loss_bps"] == 0.0 and record["day_loss_hold"] is False


def test_under_the_hold_the_boundarys_sells_run_and_its_buys_are_refused_with_the_reason(tmp_path):
    """The boundary whose mark latches the hold: its sells run, its buys are refused with the reason,
    and its own `exec-<HH>.json` reads `reduce_only` with `daily_loss_hold` — journaled with the plan
    entry, whose verdict `_accept_plan` evaluated after the mark latched."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=_only("BTC/EUR", "ETH/EUR")),
        holdings={"SOL/EUR": 0.1},
        eur_total=930.0,
        eur_free=930.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0, 1000.0, 1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    assert _accum(tmp_path)["day_loss_hold"] is True
    entry = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert [(i["symbol"], i["side"]) for i in entry["plan"]["intents"]] == [
        ("SOL/EUR", "sell"),
        ("BTC/EUR", "buy"),
        ("ETH/EUR", "buy"),
    ]
    exec_12 = _record(tmp_path, _RUNG2_12Z)
    assert exec_12["level"] == GateLevel.REDUCE_ONLY and "daily_loss_hold" in exec_12["reasons"]

    ex.on_quote(_quote("SOL/EUR.KRAKEN", bid=186.4, ask=186.41))
    order = client.submitted[-1][0]
    assert str(order.instrument_id) == "SOL/EUR.KRAKEN" and order.order_side == OrderSide.SELL
    ex.on_order_event(_accepted(str(order.client_order_id)))
    _deliver_fill(ex, client, str(order.client_order_id), float(order.quantity), symbol="SOL/EUR", side="sell", px=186.41)
    clock.now += timedelta(seconds=5)
    ex.on_timer(clock.now)

    assert _intent_outcome(tmp_path, 0, when=_RUNG2_12Z) == "filled"
    for index in (1, 2):
        intent = _intent_entry(tmp_path, index, when=_RUNG2_12Z)
        assert intent["outcome"] == "refused" and "daily_loss_hold" in intent["reasons"], intent
    assert len(client.submitted) == 1


def test_a_day_loss_hold_latched_at_a_boundary_that_places_nothing_reads_in_its_own_exec_record(tmp_path):
    """The mark latches the hold at a boundary whose free EUR is under the reserve, every buy carried
    and no sell owed: the record is `ok` with `plan_id: None` and no plan entry is journaled, so the
    draft's terminal re-journal alone puts `reduce_only` with `daily_loss_hold` in the boundary's own
    exec record, over the first act's `full`."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=950.0,
        eur_free=5.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0, 1000.0, 1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    assert _record(tmp_path, _RUNG2_12Z)["level"] == GateLevel.FULL
    ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert record["status"] == "ok" and record["plan_id"] is None and record["day_loss_hold"] is True
    assert {leg["outcome"] for leg in record["legs"]} == {"carried"}
    exec_12 = _record(tmp_path, _RUNG2_12Z)
    assert exec_12["plans"] == [] and exec_12["level"] == GateLevel.REDUCE_ONLY and "daily_loss_hold" in exec_12["reasons"]


def test_the_series_file_is_written_once_at_the_first_mark_and_never_rewritten(tmp_path):
    """No series file before the first mark: the 12Z mark writes its own `cycle_ts`, and the 16Z mark reads it and
    leaves it, its high-water mark reaching back to 12Z's equity; the probe writes the file at every mark and it
    reads 16Z."""
    flat = _the_ten_at(0.0)
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, final_targets=flat),
        holdings={},
        eur_total=1000.0,
        eur_free=1000.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
    )
    assert not _series_start_path(tmp_path).exists()
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    assert _series_start_path(tmp_path).read_text() == f"{_RUNG2_12Z.isoformat()}\n"

    later = _RUNG2_12Z + timedelta(hours=4)
    ex._venue_holdings.eur_total = 990.0
    _boundary_drafts(ex, clock, later, _rung2_record(tmp_path, final_targets=flat, cycle_ts=later))
    assert _series_start_path(tmp_path).read_text() == f"{_RUNG2_12Z.isoformat()}\n"
    assert _accum(tmp_path, later)["hwm_eur"] == 1000.0


def test_a_150_eur_fall_from_the_high_water_mark_latches_the_kill_at_nav_1000_on_an_account_of_1443(tmp_path, kill_trip_expected):
    """Rung 2's deposit reused: the series' high-water mark at EUR 1,443 and this boundary's equity at
    1,293, the book sized at the record's NAV 1,000. 150 EUR is 1500 bps of the NAV and latches the
    kill; over the account's equity it reads about 1040 bps and trips nothing, the probe's reading."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1293.0,
        eur_free=1293.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1443.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert _kill_file(tmp_path).exists() and record["drawdown_bps"] == 1500.0
    assert "1500 bps of the 1000 EUR NAV" in _kill_file(tmp_path).read_text()
    entry = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert record["status"] == "refused" and entry["reasons"] == [executor_module._TRIPPED_REFUSAL]
    _carried_under_the_entrys_reason(record, entry)


def test_a_30_eur_day_loss_latches_the_hold_at_nav_1000_on_an_account_of_1443(tmp_path):
    """The date's 00Z record at EUR 1,443 and this boundary's equity at 1,413: 300 bps of the NAV
    latches the hold, and 300 bps under the high-water mark trips no kill; over the base's equity the
    loss reads about 208 bps and latches nothing, the probe's reading."""
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1413.0,
        eur_free=1413.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1443.0, 1443.0, 1443.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert record["day_loss_bps"] == 300.0 and record["day_loss_hold"] is True
    assert record["drawdown_bps"] == 300.0 and not _kill_file(tmp_path).exists()


def test_equity_counts_an_earn_coded_basket_coin_at_its_close_and_a_move_into_earn_reads_no_loss(tmp_path):
    """SOL 0.5 under `SOL.F` and none spot (`earn={"SOL": 0.5}`), the series' high-water mark the
    equity that counts it: the draft refuses `held`, and the third tick's `book-unread` record carries
    `equity_eur` with SOL's 0.5 x close in it and `drawdown_bps` 0.0; the probe leaves `earn` out of
    the mark and the move into Auto Earn reads as a loss of 0.5 x close."""
    sol = from_json((RUNG2 / "cycle-12.json").read_text()).closes["SOL"]
    equity = 1000.0 + 0.5 * sol
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=RUNG2 / "cycle-12.json",
        holdings={},
        eur_total=1000.0,
        eur_free=1000.0,
        earn={"SOL": 0.5},
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[equity],
    )
    ex.on_boundary(_RUNG2_12Z)
    _ticks(ex, clock, 3)
    record = _accum(tmp_path)
    assert record["status"] == "book-unread" and record["equity_eur"] == equity and record["drawdown_bps"] == 0.0


def test_a_cycle_record_missing_a_close_marks_no_equity_and_names_the_base(tmp_path):
    """A record whose closes lack SOL: the mark's figures read None, at WARNING naming the base, and no trip is
    evaluated -- the draft refuses on the same absence."""
    closes = {base: close for base, close in from_json((RUNG2 / "cycle-12.json").read_text()).closes.items() if base != "SOL"}
    ex, client, clock = _boundary_executor(
        tmp_path,
        record_path=_rung2_record(tmp_path, closes=closes),
        holdings={},
        eur_total=100.0,
        eur_free=100.0,
        now=_RUNG2_12Z + timedelta(minutes=2),
        series=[1000.0],
    )
    ex.on_boundary(_RUNG2_12Z)
    with _executor_errors(logging.WARNING) as records:
        ex.on_timer(clock.now)
    record = _accum(tmp_path)
    assert record["status"] == "refused" and record["equity_eur"] is None and record["drawdown_bps"] is None
    assert not _kill_file(tmp_path).exists()
    assert any("marks no equity: the cycle record carries no close for SOL" in r.getMessage() for r in records)
