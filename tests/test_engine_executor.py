import pytest

from cli.engine.errors import EngineError
from cli.engine.executor import size_probe_order
from cli.engine.instruments import BelowMinimum, SizedOrder
from cli.engine.venuestate import InstrumentConstraints


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
