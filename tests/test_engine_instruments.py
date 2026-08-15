import pytest

from cli.engine.instruments import COSTMIN, INSTRUMENT_IDS, BelowMinimum, SizedOrder, fx_eur_notional, size_order


def test_instrument_ids_cover_exactly_the_ratified_twelve_symbol_basket():
    from cli.engine.store import BASKET

    assert set(INSTRUMENT_IDS) == set(BASKET)
    assert INSTRUMENT_IDS["BTC/EUR"] == "BTC/EUR.KRAKEN"
    # The Kraken adapter strips venue aliases when building an InstrumentId (module docstring) --
    # ETH/BTC's id is the plain symbol, never the XBT-suffixed wire form (XETHXXBT).
    assert INSTRUMENT_IDS["ETH/BTC"] == "ETH/BTC.KRAKEN"
    assert INSTRUMENT_IDS["SOL/BTC"] == "SOL/BTC.KRAKEN"
    assert all(v == f"{symbol}.KRAKEN" for symbol, v in INSTRUMENT_IDS.items())


def test_costmin_covers_exactly_the_ratified_basket_with_explicit_quotes():
    # venue_state_from_cache does COSTMIN[symbol][0] for every INSTRUMENT_IDS symbol -- a missing
    # entry would KeyError at read time rather than degrade gracefully. The values themselves are
    # pinned against the venue's own published data by tests/test_costmin_drift.py.
    assert set(COSTMIN) == set(INSTRUMENT_IDS)
    assert COSTMIN["ETH/BTC"] == (2e-05, "BTC")
    assert COSTMIN["SOL/BTC"] == (2e-05, "BTC")
    eur_legs = {symbol: v for symbol, v in COSTMIN.items() if symbol not in ("ETH/BTC", "SOL/BTC")}
    assert len(eur_legs) == 10
    assert all(v == (0.45, "EUR") for v in eur_legs.values())


def test_fx_eur_notional_eur_quoted_leg_needs_no_conversion():
    assert fx_eur_notional("ETH/EUR", 2.0, 100.0, 30000.0) == 200.0


def test_fx_eur_notional_btc_quoted_leg_converts_through_the_close():
    assert fx_eur_notional("ETH/BTC", 2.0, 0.05, 30000.0) == 3000.0


@pytest.mark.parametrize("btc_eur_close", [0.0, -30000.0])
def test_fx_eur_notional_raises_on_a_non_positive_fx_close(btc_eur_close):
    with pytest.raises(ValueError, match="btc_eur_close"):
        fx_eur_notional("ETH/BTC", 2.0, 0.05, btc_eur_close)


def test_sizing_floors_qty_to_the_lot_step_and_price_to_the_tick():
    r = size_order(0.1234567, 100.007, ordermin=0.01, costmin=0.5, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, SizedOrder)
    assert r.qty == 0.1234  # floored, never rounded up past the target
    assert r.price == 100.0  # tick-misaligned reference price floors to the tick
    assert r.notional == r.qty * r.price


def test_one_lot_below_ordermin_is_below_minimum():
    r = size_order(0.0099, 100.0, ordermin=0.01, costmin=0.0, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
    assert "ordermin" in r.reason


def test_a_cent_below_costmin_is_below_minimum():
    # qty clears ordermin; cost 4.99 sits under costmin 5.00
    r = size_order(0.0499, 100.0, ordermin=0.01, costmin=5.0, lot_step=0.0001, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
    assert "costmin" in r.reason


def test_flooring_can_push_a_passing_target_below_ordermin():
    # target 0.0199 clears ordermin 0.011 -- but at lot_step 0.01 it floors to 0.01, which
    # does NOT. The ordermin check must run on the FLOORED qty, or an unfillable order passes.
    r = size_order(0.0199, 100.0, ordermin=0.011, costmin=0.0, lot_step=0.01, tick_size=0.01)
    assert isinstance(r, BelowMinimum)
