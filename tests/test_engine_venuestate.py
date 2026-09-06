import dataclasses
import json
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from nautilus_trader.model import Currency, CurrencyPair, InstrumentId, Money, Price, Quantity, Symbol

from cli.engine.errors import EngineError
from cli.engine.instruments import COSTMIN, INSTRUMENT_IDS
from cli.engine.venuestate import (
    ConcordanceVerdict,
    InstrumentConstraints,
    VenueState,
    runtime_concordance,
    venue_state_from_cache,
)

FIXED_NOW = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)

# spec 00094: the two /BTC legs' instruments carry XBT-denominated attributes, deliberately
# distinct from the EUR legs' generic defaults below -- a bug that reused the EUR fixture values
# for these two symbols would go undetected otherwise.
_XBT_LEG_ATTRS = {
    "ETH/BTC": {"ordermin": 0.004, "lot_step": 0.00001, "tick_size": 0.0000001},
    "SOL/BTC": {"ordermin": 0.1, "lot_step": 0.001, "tick_size": 0.0000001},
}


def _decimals(step: float) -> int:
    """The decimal precision one venue step implies. Kraken publishes `pair_decimals`/`lot_decimals`
    alongside `tick_size` and the step is exactly `10 ** -decimals` across the basket, so deriving
    one from the other keeps the fixture instrument self-consistent the way a Cache one is."""
    return max(0, -Decimal(str(step)).as_tuple().exponent)


def _instrument(instrument_id: str, *, ordermin=0.01, lot_step=0.0001, tick_size=0.01) -> CurrencyPair:
    """A REAL `CurrencyPair` at one leg's precisions -- what `Cache.instrument()` hands back.

    Its `id` and constraints are the real `InstrumentId`/`Quantity`/`Price` types, so the reader's
    coercions run; plain floats would leave `json.dumps` green on a shape the venue never sends.

    `min_notional` is left unset, mirroring observed live reality (cli/engine/venuestate.py's module
    docstring, D5a): the Kraken adapter never populates it, so costmin comes from the committed
    COSTMIN constant."""
    iid = InstrumentId.from_str(instrument_id)
    base, quote = str(iid.symbol).split("/")
    price_precision, size_precision = _decimals(tick_size), _decimals(lot_step)
    return CurrencyPair(
        instrument_id=iid,
        raw_symbol=Symbol(base + quote),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=price_precision,
        size_precision=size_precision,
        price_increment=Price(tick_size, price_precision),
        size_increment=Quantity(lot_step, size_precision),
        min_quantity=Quantity(ordermin, size_precision),
        ts_event=0,
        ts_init=0,
    )


def _fake_position(signed_qty: float):
    return SimpleNamespace(signed_qty=signed_qty)


class FakeCache:
    """Duck-types the Cache accessors `venue_state_from_cache` calls, matching them by `str()`
    because the reader passes real `InstrumentId`/`Venue` objects."""

    def __init__(self, instruments: dict[str, object], positions: dict[str, list], account):
        self._instruments = instruments
        self._positions = positions
        self._account = account

    def instrument(self, instrument_id):
        return self._instruments.get(str(instrument_id))

    def positions_open(self, *, instrument_id=None, **kwargs):
        return self._positions.get(str(instrument_id), [])

    def account_for_venue(self, *, venue=None, **kwargs):
        return self._account


def _fake_account(balances_free: dict[str, float]):
    """`balances_free()` in the real account's own terms: `dict[Currency, Money]`. Both halves are
    library types the reader has to coerce -- a plain str key and a float value would let a reader
    that never called `.code` or `float()` pass."""
    balances = {Currency.from_str(code): Money(value, Currency.from_str(code)) for code, value in balances_free.items()}
    return SimpleNamespace(balances_free=lambda: balances)


def _all_instruments(**overrides):
    instruments = {iid_str: _instrument(iid_str, **_XBT_LEG_ATTRS.get(symbol, {})) for symbol, iid_str in INSTRUMENT_IDS.items()}
    instruments.update(overrides)
    return instruments


@pytest.fixture
def fake_cache():
    # A permissive fixture (everything flat/zero) would pass even if a consumer never read
    # positions or balances at all.
    positions = {
        INSTRUMENT_IDS["BTC/EUR"]: [_fake_position(-0.5)],
        INSTRUMENT_IDS["DOGE/EUR"]: [_fake_position(1234.0)],
    }
    account = _fake_account({"EUR": 987.65, "BTC": 0.5})
    return FakeCache(_all_instruments(), positions, account)


@pytest.fixture
def fake_cache_missing_dot():
    instruments = _all_instruments()
    del instruments[INSTRUMENT_IDS["DOT/EUR"]]
    return FakeCache(instruments, {}, _fake_account({"EUR": 100.0}))


def test_venue_state_freezes_the_twelve_legs(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert set(vs.instruments) == set(INSTRUMENT_IDS)
    assert vs.snapshot_at == FIXED_NOW
    with pytest.raises(dataclasses.FrozenInstanceError):
        vs.snapshot_at = FIXED_NOW


def test_a_missing_instrument_raises_rather_than_silently_narrowing(fake_cache_missing_dot):
    with pytest.raises(EngineError, match="DOT/EUR"):
        venue_state_from_cache(fake_cache_missing_dot, clock=lambda: FIXED_NOW)


def test_no_account_cached_raises():
    cache = FakeCache(_all_instruments(), {}, None)
    with pytest.raises(EngineError, match="account"):
        venue_state_from_cache(cache, clock=lambda: FIXED_NOW)


def test_a_cache_instrument_id_mismatch_raises():
    # A silent instrument_id mismatch is exactly the venue-truth divergence this spec exists to
    # surface, so it must never narrow into "whatever the Cache happened to hand back."
    instruments = _all_instruments()
    instruments[INSTRUMENT_IDS["BTC/EUR"]] = _instrument("WRONG/EUR.KRAKEN")
    cache = FakeCache(instruments, {}, _fake_account({}))
    with pytest.raises(EngineError, match="BTC/EUR"):
        venue_state_from_cache(cache, clock=lambda: FIXED_NOW)


def test_positions_are_signed_and_flat_defaults_to_zero(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.positions["BTC/EUR"] == -0.5  # short
    assert vs.positions["DOGE/EUR"] == 1234.0  # long
    assert vs.positions["ETH/EUR"] == 0.0  # no open position -> flat, not a failure


def test_balances_are_read_by_currency_code(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.balances == {"EUR": 987.65, "BTC": 0.5}


def test_the_xbt_legs_freeze_their_own_cache_constraints(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)

    for symbol, attrs in _XBT_LEG_ATTRS.items():
        constraints = vs.instruments[symbol]
        assert constraints.ordermin == attrs["ordermin"]
        assert constraints.lot_step == attrs["lot_step"]
        assert constraints.tick_size == attrs["tick_size"]
    eur = vs.instruments["BTC/EUR"]  # and the EUR legs keep _fake_instrument's generic defaults
    assert (eur.ordermin, eur.lot_step, eur.tick_size) == (0.01, 0.0001, 0.01)


def test_a_missing_min_notional_from_the_cache_produces_no_concordance_failure(fake_cache):
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.instruments["BTC/EUR"].costmin == COSTMIN["BTC/EUR"][0]
    assert runtime_concordance(vs) == ConcordanceVerdict(ok=True, failures=())


def test_costmin_quote_is_populated_per_symbol_from_the_committed_constant(fake_cache):
    # spec 00094 D4: costmin_quote is NOT a venue reading either (cli/engine/venuestate.py's module
    # docstring, D5a) -- it is the same committed COSTMIN entry's quote currency, so a consumer can
    # tell a BTC-denominated costmin from a EUR-denominated one without guessing.
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.instruments["BTC/EUR"].costmin_quote == "EUR"
    assert vs.instruments["ETH/BTC"].costmin_quote == "BTC"
    assert vs.instruments["SOL/BTC"].costmin_quote == "BTC"


def test_payload_round_trips_to_json(fake_cache):
    payload = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW).to_payload()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["snapshot_at"] == FIXED_NOW.isoformat()
    assert payload["instruments"]["BTC/EUR"]["ordermin"] == 0.01
    assert payload["instruments"]["BTC/EUR"]["costmin_source"] == "snapshot-constant"
    assert payload["instruments"]["BTC/EUR"]["costmin_quote"] == "EUR"
    assert payload["instruments"]["ETH/BTC"]["costmin_quote"] == "BTC"


def _valid_state(**instrument_overrides) -> VenueState:
    instruments = {
        symbol: InstrumentConstraints(
            symbol=symbol,
            instrument_id=iid,
            ordermin=0.01,
            costmin=5.0,
            costmin_quote=COSTMIN[symbol][1],  # the real per-symbol quote (D4) -- never a blanket
            # "EUR", or the two /BTC legs would carry a denomination lie baked into the fixture.
            lot_step=0.0001,
            tick_size=0.01,
        )
        for symbol, iid in INSTRUMENT_IDS.items()
    }
    instruments.update(instrument_overrides)
    return VenueState(snapshot_at=FIXED_NOW, instruments=instruments, positions={}, balances={})


def test_runtime_concordance_ok_on_a_fully_valid_state():
    verdict = runtime_concordance(_valid_state())
    assert verdict == ConcordanceVerdict(ok=True, failures=())


@pytest.mark.parametrize("field_name", ["ordermin", "lot_step", "tick_size"])
def test_runtime_concordance_flags_a_non_positive_constraint(field_name):
    broken = dataclasses.replace(
        InstrumentConstraints(
            symbol="BTC/EUR",
            instrument_id=INSTRUMENT_IDS["BTC/EUR"],
            ordermin=0.01,
            costmin=5.0,
            costmin_quote="EUR",
            lot_step=0.0001,
            tick_size=0.01,
        ),
        **{field_name: 0.0},
    )
    verdict = runtime_concordance(_valid_state(**{"BTC/EUR": broken}))
    assert verdict.ok is False
    assert len(verdict.failures) == 1
    assert verdict.failures[0].startswith("BTC/EUR: ")
    assert field_name in verdict.failures[0]


def test_runtime_concordance_ignores_a_non_positive_costmin():
    # D5a: costmin's correctness is test_costmin_drift.py's job, not the runtime check's -- a
    # broken costmin must never fail concordance, or D6's alert would hold red forever (T0135).
    broken = dataclasses.replace(
        InstrumentConstraints(
            symbol="BTC/EUR",
            instrument_id=INSTRUMENT_IDS["BTC/EUR"],
            ordermin=0.01,
            costmin=5.0,
            costmin_quote="EUR",
            lot_step=0.0001,
            tick_size=0.01,
        ),
        costmin=0.0,
    )
    verdict = runtime_concordance(_valid_state(**{"BTC/EUR": broken}))
    assert verdict == ConcordanceVerdict(ok=True, failures=())


def test_runtime_concordance_flags_a_base_missing_from_the_snapshot():
    state = _valid_state()
    del state.instruments["DOT/EUR"]
    verdict = runtime_concordance(state)
    assert verdict.ok is False
    assert verdict.failures == ("DOT/EUR: instrument not present in snapshot",)


# --- this file's library stand-ins, checked against the library ----------------------------------
#
# tests/test_engine_stub_fidelity.py classifies every test double in the engine suite and names the
# guard below; the reasoning that makes it worth having lives there.


def _library_standins():
    """(label, stub instance, real class, plumbing) for every test double in this file that stands
    in for a library type. Built inside a function so the extra imports are paid only by the test
    that needs them."""
    from nautilus_trader.common import Cache
    from nautilus_trader.model import MarginAccount, Position

    return [
        ("FakeCache", FakeCache({}, {}, None), Cache, frozenset({"_instruments", "_positions", "_account"})),
        ("_fake_position", _fake_position(1.0), Position, frozenset()),
        ("_fake_account", _fake_account({"EUR": 1.0}), MarginAccount, frozenset()),
    ]


def test_no_stub_in_the_venue_reader_suite_offers_a_name_its_real_library_type_lacks():
    """A stub MISSING something the reader calls raises the first time a test runs it; a stub
    OFFERING something the real type lacks fails NOTHING -- every test believes the fabricated
    attribute forever, and only the live boundary reads it back wrong. Violations are collected
    rather than raised at the first, so one red run names all of them."""
    violations = []
    for label, stub, real, plumbing in _library_standins():
        offered = {name for name in dir(stub) if not name.startswith("__")} - plumbing
        assert offered, f"{label} offers nothing outside its plumbing list -- the check is vacuous"
        stale = sorted(name for name in plumbing if hasattr(real, name))
        extra = sorted(name for name in offered if not hasattr(real, name))
        if extra:
            violations.append(f"{label} offers {extra}, which {real.__name__} does not carry")
        if stale:
            violations.append(f"{label}'s plumbing list exempts {stale}, which {real.__name__} DOES carry -- check them instead")
    assert violations == [], "; ".join(violations)
