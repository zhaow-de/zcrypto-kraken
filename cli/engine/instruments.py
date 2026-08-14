"""The engine's venue instrument map, the committed costmin constant, the pure order-sizing
function, and the pure FX term (spec 00089, widened by spec 00094).

`INSTRUMENT_IDS` is derived from `cli.engine.store.BASKET` -- all twelve symbols the engine
trades (ten `/EUR` pairs plus `ETH/BTC`/`SOL/BTC`). Probed against the installed nautilus-trader
Kraken adapter's `normalize_spot_symbol` (`nautilus_kraken::common::parse`): it renames Kraken's
legacy `XBT`/`XDG` codes to `BTC`/`DOGE` before building the InstrumentId, and it STRIPS the venue
alias regardless of which currency is the quote -- so `ETH/BTC`'s InstrumentId is
`ETH/BTC.KRAKEN`, never an XBT form, even though the venue's own pair *key* on the wire is
`XETHXXBT` (`cli.engine.store.PAIR_KEYS["ETH/BTC"]`).

`COSTMIN` is why costmin does NOT flow through `cli.engine.venuestate.venue_state_from_cache`'s
Cache read the way `ordermin`/`lot_step`/`tick_size` do -- see the constant's own comment (D5a).
Its quote currency is spelled the way the refdata snapshot itself spells it (`"EUR"`/`"BTC"`,
never the venue-alias forms `ZEUR`/`XXBT`) -- a consumer that needs the adapter's alias maps it at
its own read site.

`size_order` is pure and unused by any production path yet -- it exists so 00090's real order
path inherits ONE proven function instead of building sizing beside real money. Both
quantizations (qty to `lot_step`, reference price to `tick_size`) happen here, and the `ordermin`
check runs on the FLOORED qty: a target that clears `ordermin` before flooring can fall below it
after, which the venue would reject. It takes `costmin` as a plain number and never a
`(value, quote)` pair -- the CALLER owns denomination (compare a BTC-quoted floor only against a
BTC-quoted notional, never against a EUR one).

`fx_eur_notional` is likewise pure and uncalled by production yet -- the `size_order` precedent:
it exists so the next spec that needs a EUR-denominated `/BTC`-leg notional inherits one proven
conversion instead of writing it beside real money.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from cli.engine.store import BASKET

INSTRUMENT_IDS: dict[str, str] = {symbol: f"{symbol}.KRAKEN" for symbol in BASKET}

# Committed, not read live (spec 00089 D5a, measured): the installed nautilus-trader 1.230.0
# Kraken adapter never maps Kraken's `costmin` onto `min_notional` -- the Cache instrument always
# reads it back None (loopback-probed through the compiled parser, cli/engine/venuestate.py). The
# engine host also carries no refdata snapshot (only /var/lib/zcrypto-engine and the config file
# are mounted), so a runtime file read isn't available either. costmin is not a venue constant
# (0.5 / 0.45 / 0.00002 depending on the pair) so it can't be a single hardcoded number -- these
# twelve values are per-symbol, quote-explicit (the two `/BTC` legs are BTC-denominated, not EUR),
# pinned against the venue's own published data by tests/test_costmin_drift.py, which turns red on
# a venue change instead of silently mis-sizing an order.
# cli/engine/venuestate.py::runtime_concordance deliberately does NOT check costmin -- its
# correctness is this drift test's job.
COSTMIN: dict[str, tuple[float, str]] = {
    "ADA/EUR": (0.45, "EUR"),
    "AVAX/EUR": (0.45, "EUR"),
    "BTC/EUR": (0.45, "EUR"),
    "DOGE/EUR": (0.45, "EUR"),
    "DOT/EUR": (0.45, "EUR"),
    "ETH/BTC": (2e-05, "BTC"),
    "ETH/EUR": (0.45, "EUR"),
    "LINK/EUR": (0.45, "EUR"),
    "LTC/EUR": (0.45, "EUR"),
    "SOL/BTC": (2e-05, "BTC"),
    "SOL/EUR": (0.45, "EUR"),
    "XRP/EUR": (0.45, "EUR"),
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

    `costmin` is a bare number, not a `(value, quote)` pair -- the CALLER owns denomination.
    `reference_price` must already be quoted in the same currency `costmin` is, or the notional
    check compares two different currencies as if they were one (e.g. a BTC-quoted `/BTC` leg's
    floor against a EUR notional).
    """
    qty = _floor_to_step(target_qty, lot_step)
    price = _floor_to_step(reference_price, tick_size)

    if qty < ordermin:
        return BelowMinimum(reason=f"floored qty {qty} is below ordermin {ordermin}")

    notional = qty * price
    if notional < costmin:
        return BelowMinimum(reason=f"notional {notional} (qty {qty} x price {price}) is below costmin {costmin}")

    return SizedOrder(qty=qty, price=price, notional=notional)


def fx_eur_notional(symbol: str, qty: float, price: float, btc_eur_close: float) -> float:
    """EUR-denominate one symbol's `qty * price` notional, quote-aware: an `/EUR` leg needs no
    conversion; a `/BTC` leg (`ETH/BTC`, `SOL/BTC`) is converted through `btc_eur_close`. Pure and
    uncalled by production (the `size_order` precedent, module docstring) -- it exists so the next
    spec inherits one proven conversion instead of writing it beside real money.

    `btc_eur_close` is validated unconditionally, even on the `/EUR` path where it goes unused --
    a caller passing a non-positive rate has a bug regardless of which leg it happens to size.
    """
    if btc_eur_close <= 0:
        raise ValueError(f"btc_eur_close must be positive, got {btc_eur_close}")
    quote = symbol.split("/")[1]
    if quote == "EUR":
        return qty * price
    if quote == "BTC":
        return qty * price * btc_eur_close
    raise ValueError(f"fx_eur_notional: unsupported quote {quote!r} for symbol {symbol!r}")
