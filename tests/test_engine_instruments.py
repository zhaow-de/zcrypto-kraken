from cli.engine.instruments import INSTRUMENT_IDS, BelowMinimum, SizedOrder, size_order


def test_instrument_ids_cover_exactly_the_ratified_basket():
    from cli.engine.store import PAIR_KEYS

    assert set(INSTRUMENT_IDS) == set(PAIR_KEYS)
    assert INSTRUMENT_IDS["BTC"] == "BTC/EUR.KRAKEN"
    assert all(v == f"{base}/EUR.KRAKEN" for base, v in INSTRUMENT_IDS.items())


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
