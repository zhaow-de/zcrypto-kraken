import dataclasses
import json
from collections import namedtuple
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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

# spec 00094: the two /BTC legs' fake instruments carry XBT-denominated attributes, deliberately
# distinct from the EUR legs' generic defaults below -- a bug that reused the EUR fixture values
# for these two symbols would go undetected otherwise.
_XBT_LEG_ATTRS = {
    "ETH/BTC": {"ordermin": 0.004, "lot_step": 0.00001, "tick_size": 0.0000001},
    "SOL/BTC": {"ordermin": 0.1, "lot_step": 0.001, "tick_size": 0.0000001},
}


def _fake_instrument(instrument_id: str, *, ordermin=0.01, lot_step=0.0001, tick_size=0.01):
    # min_notional mirrors observed live reality (module docstring, D5a): the installed Kraken
    # adapter never populates it. venue_state_from_cache must never read it -- costmin comes from
    # the committed COSTMIN constant instead.
    return SimpleNamespace(
        id=instrument_id, min_quantity=ordermin, min_notional=None, size_increment=lot_step, price_increment=tick_size
    )


def _fake_position(signed_qty: float):
    return SimpleNamespace(signed_qty=signed_qty)


class FakeCache:
    """Duck-types the three Cache accessors venue_state_from_cache calls, matching their real
    signatures (`instrument(instrument_id)`, `positions_open(instrument_id=...)`,
    `account_for_venue(venue=...)`). Real Nautilus InstrumentId/Venue objects are passed in by the
    reader under test -- this fake matches them by str() so it never needs to import Nautilus."""

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


_FakeCurrency = namedtuple("_FakeCurrency", ["code"])  # SimpleNamespace is unhashable, dict keys must not be


def _fake_account(balances_free: dict[str, float]):
    balances = {_FakeCurrency(code=code): value for code, value in balances_free.items()}
    return SimpleNamespace(balances_free=lambda: balances)


def _all_instruments(**overrides):
    instruments = {
        iid_str: _fake_instrument(iid_str, **_XBT_LEG_ATTRS.get(symbol, {})) for symbol, iid_str in INSTRUMENT_IDS.items()
    }
    instruments.update(overrides)
    return instruments


@pytest.fixture
def fake_cache():
    # Adversarial-ish: BTC/EUR carries an open short and DOGE/EUR an open long, so a caller
    # netting positions against targets would see a nonzero effect -- a permissive fixture
    # (everything flat/zero) would pass even if a consumer never read positions/balances at all.
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
    instruments[INSTRUMENT_IDS["BTC/EUR"]] = _fake_instrument("WRONG/EUR.KRAKEN")
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


def test_a_missing_min_notional_from_the_cache_produces_no_concordance_failure(fake_cache):
    # D5a's fix, pinned directly: min_notional is None on every fake instrument by construction
    # (matching observed live reality), yet costmin reads the committed constant -- not 0.0/None
    # -- and the resulting state is concordance-clean.
    vs = venue_state_from_cache(fake_cache, clock=lambda: FIXED_NOW)
    assert vs.instruments["BTC/EUR"].costmin == COSTMIN["BTC/EUR"][0]
    assert runtime_concordance(vs) == ConcordanceVerdict(ok=True, failures=())


def test_costmin_quote_is_populated_per_symbol_from_the_committed_constant(fake_cache):
    # spec 00094 D4: costmin_quote is NOT a venue reading either (module docstring, D5a) -- it is
    # the same committed COSTMIN entry's quote currency, so a consumer can tell a BTC-denominated
    # costmin from a EUR-denominated one without guessing.
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
