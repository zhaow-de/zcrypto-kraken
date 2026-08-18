"""The single venue-mutating module (spec 00090, the D4 walk test's anchor): every place this
engine talks to the venue lives here. This first cut is the pure sizing seam only -- the nautilus
imports (`InstrumentId`, `OrderSide`, `TimeInForce`, `Venue`) join in Task 5.
"""

from __future__ import annotations

from cli.engine.errors import EngineError
from cli.engine.instruments import BelowMinimum, SizedOrder, size_order
from cli.engine.venuestate import InstrumentConstraints


def size_probe_order(target_qty: float, touch_price: float, constraints: InstrumentConstraints) -> SizedOrder | BelowMinimum:
    """THE sizing call site (spec 00090 D8): every probe order is sized here, on the Cache-fresh
    constraints and the committed costmin, through the one proven size_order. The comparison this
    module makes is EUR-denominated end to end (an EUR intent notional, an EUR-quoted touch), so the
    guard T0138 holds lands immediately where the notional meets constraints.costmin: a floor
    denominated in anything but EUR must never be compared here -- a /BTC leg's 2e-05 BTC floor
    against a EUR notional passes everything silently (the fail-open defect). Route a future
    /BTC-leg notional through fx_eur_notional first; until then this raises."""
    if constraints.costmin_quote != "EUR":
        raise EngineError(
            f"{constraints.symbol}: costmin is denominated in {constraints.costmin_quote!r} but this "
            "path compares an EUR notional against it -- refusing a cross-denomination comparison "
            "(convert through fx_eur_notional before sizing a non-EUR-quoted leg)"
        )
    return size_order(
        target_qty,
        touch_price,
        ordermin=constraints.ordermin,
        costmin=constraints.costmin,
        lot_step=constraints.lot_step,
        tick_size=constraints.tick_size,
    )
