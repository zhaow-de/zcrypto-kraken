"""The engine's venue instrument map, the committed costmin constant, and the pure order-sizing
function (spec 00089).

`INSTRUMENT_IDS` is derived from `cli.engine.store.PAIR_KEYS` -- the ten EUR-only bases the engine
trades. Probed against the installed nautilus-trader Kraken adapter's `normalize_spot_symbol`
(`nautilus_kraken::common::parse`): it renames Kraken's legacy `XBT`/`XDG` codes to `BTC`/`DOGE`
before building the InstrumentId, so the venue form matches our bases exactly -- no alias
override is needed, unlike the pair *key* Kraken uses on the wire (`XXBTZEUR`, `XDGEUR`).

`COSTMIN_EUR` is why costmin does NOT flow through `cli.engine.venuestate.venue_state_from_cache`'s
Cache read the way `ordermin`/`lot_step`/`tick_size` do -- see the constant's own comment (D5a).

`size_order` is pure and unused by any production path yet -- it exists so 00090's real order
path inherits ONE proven function instead of building sizing beside real money. Both
quantizations (qty to `lot_step`, reference price to `tick_size`) happen here, and the `ordermin`
check runs on the FLOORED qty: a target that clears `ordermin` before flooring can fall below it
after, which the venue would reject.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from cli.engine.store import PAIR_KEYS

INSTRUMENT_IDS: dict[str, str] = {base: f"{base}/EUR.KRAKEN" for base in PAIR_KEYS}

# Committed, not read live (spec 00089 D5a, measured): the installed nautilus-trader 1.230.0
# Kraken adapter never maps Kraken's `costmin` onto `min_notional` -- the Cache instrument always
# reads it back None (loopback-probed through the compiled parser, cli/engine/venuestate.py). The
# engine host also carries no refdata snapshot (only /var/lib/zcrypto-engine and the config file
# are mounted), so a runtime file read isn't available either. costmin is not a venue constant
# (0.5 / 0.45 / 0.00002 depending on the pair) so it can't be a single hardcoded number -- these
# ten values are per-base, pinned against the venue's own published data by
# tests/test_costmin_drift.py, which turns red on a venue change instead of silently mis-sizing an
# order. cli/engine/venuestate.py::runtime_concordance deliberately does NOT check costmin -- its
# correctness is this drift test's job.
COSTMIN_EUR: dict[str, float] = {
    "ADA": 0.45,
    "AVAX": 0.45,
    "BTC": 0.45,
    "DOGE": 0.45,
    "DOT": 0.45,
    "ETH": 0.45,
    "LINK": 0.45,
    "LTC": 0.45,
    "SOL": 0.45,
    "XRP": 0.45,
}


@dataclass(frozen=True)
class SizedOrder:
    qty: float
    price: float
    notional: float


@dataclass(frozen=True)
class BelowMinimum:
    reason: str


def _floor_to_step(value: float, step: float) -> float:
    """Floor `value` down to the nearest multiple of `step`, exact under float equality.

    `math.floor(value / step) * step` in plain floats drifts by an ULP or two (e.g.
    0.1234567 / 0.0001 * 0.0001 -> 0.12340000000000001, not 0.1234) -- fatal for a caller that
    checks the result against a venue-quoted minimum. Routing the division through `Decimal(str(x))`
    keeps the arithmetic exact in base 10, which is what both `value` and `step` are quoted in.
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    dv = Decimal(str(value))
    ds = Decimal(str(step))
    return float(math.floor(dv / ds) * ds)


def size_order(
    target_qty: float,
    reference_price: float,
    *,
    ordermin: float,
    costmin: float,
    lot_step: float,
    tick_size: float,
) -> SizedOrder | BelowMinimum:
    """Quantize `target_qty`/`reference_price` to the venue's `lot_step`/`tick_size`, then check
    the FLOORED quantity against `ordermin` and the floored notional against `costmin`, in that
    order. Both checks run on the post-floor numbers -- a target that clears `ordermin` before
    flooring can fall below it after, which the venue would reject as unfillable.
    """
    qty = _floor_to_step(target_qty, lot_step)
    price = _floor_to_step(reference_price, tick_size)

    if qty < ordermin:
        return BelowMinimum(reason=f"floored qty {qty} is below ordermin {ordermin}")

    notional = qty * price
    if notional < costmin:
        return BelowMinimum(reason=f"notional {notional} (qty {qty} x price {price}) is below costmin {costmin}")

    return SizedOrder(qty=qty, price=price, notional=notional)
