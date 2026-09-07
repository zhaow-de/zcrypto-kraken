"""The engine's venue instrument map, the committed costmin constant, and the pure sizing and FX terms (spec
00089, widened by spec 00094).

`INSTRUMENT_IDS` was probed at nautilus-trader 1.230.0 against its Kraken adapter `normalize_spot_symbol`
(re-probe when the pin moves), which
renames the legacy `XBT`/`XDG` codes and STRIPS the venue alias whichever currency is the quote -- so
`ETH/BTC`'s InstrumentId is `ETH/BTC.KRAKEN`, never an XBT form, though the venue's own wire pair key is
`XETHXXBT` (`cli.engine.store.PAIR_KEYS["ETH/BTC"]`). The tests pin the dict below, not the adapter's parse,
so re-probe this agreement when the nautilus pin moves.

`COSTMIN`'s quote currency is spelled the way the refdata snapshot spells it (`"EUR"`/`"BTC"`, never the
venue-alias forms `ZEUR`/`XXBT`) -- a consumer that needs the adapter's alias maps it at its own read site."""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from cli.engine.store import BASKET

INSTRUMENT_IDS: dict[str, str] = {symbol: f"{symbol}.KRAKEN" for symbol in BASKET}

# Kraken spells the euro both ways across its surfaces (the adapter's Money and the measured free
# balances carry `EUR`, the asset/instrument-quote surfaces the classic `ZEUR`); anything else is a
# different currency and is never summed into a EUR total. It lives on this shared leaf rather than
# in `executor.py` so a reader of the journal can import it without importing the order path --
# `executor.py` imports from here, so the reverse direction is a circular import at engine start.
EUR_CODES = ("EUR", "ZEUR")

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
    """The `ordermin` and `costmin` checks run on the POST-floor numbers -- a target that clears `ordermin`
    before flooring can fall below it after, which the venue would reject as unfillable.

    `costmin` is a bare number, not a `(value, quote)` pair -- the CALLER owns denomination:
    `reference_price` must already be quoted in `costmin`'s currency, or the notional check compares two
    different currencies as if they were one (a BTC-quoted `/BTC` leg's floor against a EUR notional)."""
    qty = _floor_to_step(target_qty, lot_step)
    price = _floor_to_step(reference_price, tick_size)

    if qty < ordermin:
        return BelowMinimum(reason=f"floored qty {qty} is below ordermin {ordermin}")

    notional = qty * price
    if notional < costmin:
        return BelowMinimum(reason=f"notional {notional} (qty {qty} x price {price}) is below costmin {costmin}")

    return SizedOrder(qty=qty, price=price, notional=notional)


def fx_eur_notional(symbol: str, qty: float, price: float, btc_eur_close: float) -> float:
    """`btc_eur_close` is validated unconditionally, even on the `/EUR` path where it goes unused -- a caller
    passing a non-positive rate has a bug regardless of which leg it happens to size."""
    if btc_eur_close <= 0:
        raise ValueError(f"btc_eur_close must be positive, got {btc_eur_close}")
    quote = symbol.split("/")[1]
    if quote == "EUR":
        return qty * price
    if quote == "BTC":
        return qty * price * btc_eur_close
    raise ValueError(f"fx_eur_notional: unsupported quote {quote!r} for symbol {symbol!r}")
