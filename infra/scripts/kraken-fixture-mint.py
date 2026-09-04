#!/usr/bin/env python3
"""Mint the three account ingredients an attended flatten pass needs, on a live Kraken account.

`zcrypto engine flatten` has three halves to exercise and no fixture mints them: a RESTING ORDER its
own client did not place, a MARGIN POSITION (the leg `margin_legs`, the reduce-only close and the
`position_side` read all run on), and a NON-EUR SPOT BALANCE for the sell path. This script mints
those three and stops. It has no cancel path -- not for its own legs, not for anything else -- so it
cannot unmake a fixture, its own or a hand-placed one.

Two properties are load-bearing and neither announces itself when broken:

EVERY LEG IS ON A SAME-KEY PAIR. Kraken spells five basket pairs two ways -- `BLIND_ORDER_READ_LEGS`,
imported rather than restated -- and on those the adapter's order-report read returns success with the
row dropped. A fixture resting there is invisible to the very verdict the attended pass reads, so the
pass would report clean against an account it cannot see. `assert_same_key` refuses at plan time,
before anything is sized or printed.

EVERY SIZE COMES FROM THE VENUE AT RUN TIME. `ordermin`, `costmin` and the price step are read from
AssetPairs on the run that uses them, and the resting price is a stated fraction below the run's own
best bid. A remembered figure is rejected at submit if it has fallen below a floor, and silently
accepted at a notional nobody chose if it has not.

The client is the bare `KrakenSpotHttpClient` -- the same construction `flatten` reads with, so the
legs land on the surface that will be asked about them. It is deliberately not the order-semantics
harness's node: that harness cancels its outstanding orders when it stops, which is correct for a
probe and fatal for a fixture.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime

from nautilus_trader.model import (
    AccountId,
    AccountType,
    ClientOrderId,
    OrderSide,
    OrderType,
    Price,
    Quantity,
    TimeInForce,
)

from cli.engine.flatten import BLIND_ORDER_READ_LEGS
from cli.engine.instruments import (
    INSTRUMENT_IDS,
    BelowMinimum,
    SizedOrder,
    _floor_to_step,
    size_order,
)

API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"

DEFAULT_PAIR = "SOL/EUR"

# The resting leg sits this far below the run's own best bid. Far enough that it cannot fill while
# the fixture is wanted; a fraction rather than a price, because a price is a fact about one minute.
AWAY_FRACTION = 0.45

# The venue's minimum for a margin leg. Leverage reaches this leg and no other -- a spot leg that
# carried it would open a position nobody planned.
MARGIN_LEVERAGE = 2

# Its own id, as the order-semantics harness has its own: an account id shared with the engine would
# make this script's legs indistinguishable from the engine's in anything that reads by account.
FIXTURE_ACCOUNT_ID = "KRAKEN-902"
FIXTURE_ORDER_TAG = "FIXMINT"

# Typed in full, and deliberately not a word a reflex answers.
CONFIRM_WORD = "MINT"

# Flooring can drop a target under a floor it cleared; a few steps is ample and a runaway is a
# listing that is not what this script assumes, which is a refusal rather than a loop.
_SIZE_WALK_LIMIT = 8


class Refusal(Exception):
    """A precondition this script will not proceed without. Never caught inside it."""


@dataclass(frozen=True)
class PairLimits:
    """What AssetPairs publishes about one pair, read on the run that uses it."""

    ordermin: float
    costmin: float
    lot_step: float
    price_step: float


@dataclass(frozen=True)
class Leg:
    """One order this script would send. `price` is None for a market leg."""

    kind: str
    pair: str
    side: str
    order_type: str
    quantity: float
    price: float | None
    notional_eur: float
    leverage: int | None
    account_type: str
    time_in_force: str


@dataclass(frozen=True)
class AccountState:
    """What the account already holds, read before anything is planned.

    A re-run must not double the fixture, so each leg is dropped when its ingredient is already
    present. Keyed on THIS pair: a resting order somewhere else is not this fixture's resting leg.
    """

    resting_pairs: tuple[str, ...] = ()
    position_pairs: tuple[str, ...] = ()
    non_eur_assets: tuple[str, ...] = field(default=())


def assert_same_key(pair: str) -> None:
    """Refuse a pair whose Kraken altname differs from its AssetPairs key.

    The adapter caches instruments under the key and looks an order up by its altname, comparing by
    raw equality with no miss branch, so a row on one of these legs is dropped and the read returns
    success. A fixture there is invisible to the verdict it exists to exercise.
    """
    if pair in BLIND_ORDER_READ_LEGS:
        raise Refusal(
            f"REFUSING: {pair} is spelled two ways at the venue, so a resting order on it is "
            f"dropped by the order-report read and the attended pass would read clean against an "
            f"account it cannot see. Mint on a same-key pair; {DEFAULT_PAIR} is the default.",
        )


def require_eur_quote(pair: str) -> None:
    """Refuse a leg this script cannot size honestly.

    `size_order` leaves denomination to its caller: `costmin` for a `/BTC` leg is quoted in BTC, and
    comparing it against a EUR notional compares two currencies as if they were one. Every printed
    figure here is EUR, so a non-EUR quote is refused rather than converted.
    """
    if not pair.endswith("/EUR"):
        raise Refusal(
            f"REFUSING: {pair} is not EUR-quoted, and this script's floors and printed notionals "
            f"are EUR. Mint on a EUR pair; {DEFAULT_PAIR} is the default.",
        )


def resting_price(best_bid: float, price_step: float) -> float:
    """A stated fraction below the run's own best bid, floored to the venue's price step."""
    return _floor_to_step(best_bid * (1 - AWAY_FRACTION), price_step)


def size_leg(limits: PairLimits, price: float) -> tuple[float, float]:
    """The smallest quantity clearing BOTH of the venue's floors AFTER flooring, and its notional.

    `ordermin` is a quantity and `costmin` a cost, so which binds depends on the day's price: a
    cheap asset clears `ordermin` long before `costmin`. `size_order` owns the arithmetic -- it
    floors to the lot step in exact base-10 and then checks the FLOORED numbers, because a target
    that clears a floor before flooring can fall under it after. A target that lands short is walked
    up one lot step at a time rather than guessed at.
    """
    if price <= 0:
        raise Refusal(f"REFUSING: a price of {price} cannot size a leg")
    target = max(limits.ordermin, limits.costmin / price)
    for _ in range(_SIZE_WALK_LIMIT):
        sized = size_order(
            target,
            price,
            ordermin=limits.ordermin,
            costmin=limits.costmin,
            lot_step=limits.lot_step,
            tick_size=limits.price_step,
        )
        if isinstance(sized, SizedOrder):
            return sized.qty, sized.notional
        assert isinstance(sized, BelowMinimum)
        target += limits.lot_step
    raise Refusal(
        f"REFUSING: could not clear ordermin {limits.ordermin} and costmin {limits.costmin} at "
        f"price {price} within {_SIZE_WALK_LIMIT} lot steps -- the listing is not what was expected",
    )


def plan_legs(*, pair: str, limits: PairLimits, best_bid: float, existing: AccountState) -> list[Leg]:
    """The legs this run would send: the three ingredients, minus whatever is already there."""
    assert_same_key(pair)
    require_eur_quote(pair)
    base = pair.split("/")[0]
    legs: list[Leg] = []

    if pair not in existing.resting_pairs:
        qty, notional = size_leg(limits, price=best_bid)
        price = resting_price(best_bid, limits.price_step)
        legs.append(
            Leg(
                kind="resting",
                pair=pair,
                side="BUY",
                order_type="LIMIT",
                quantity=qty,
                price=price,
                notional_eur=qty * price,
                leverage=None,
                account_type="CASH",
                time_in_force="GTC",
            )
        )

    if pair not in existing.position_pairs:
        qty, notional = size_leg(limits, price=best_bid)
        legs.append(
            Leg(
                kind="margin",
                pair=pair,
                side="BUY",
                order_type="MARKET",
                quantity=qty,
                price=None,
                notional_eur=notional,
                leverage=MARGIN_LEVERAGE,
                account_type="MARGIN",
                time_in_force="IOC",
            )
        )

    if base not in existing.non_eur_assets:
        qty, notional = size_leg(limits, price=best_bid)
        legs.append(
            Leg(
                kind="spot",
                pair=pair,
                side="BUY",
                order_type="MARKET",
                quantity=qty,
                price=None,
                notional_eur=notional,
                leverage=None,
                account_type="CASH",
                time_in_force="IOC",
            )
        )

    return legs


def check_confirmation(typed: str) -> None:
    """The second half of the gate. `--execute` alone sends nothing."""
    if typed != CONFIRM_WORD:
        raise Refusal(
            f"REFUSING: confirmation did not match. Type {CONFIRM_WORD} exactly; nothing was sent.",
        )


def render_plan(legs: list[Leg], existing: AccountState, pair: str) -> str:
    """What the operator reads before deciding. Every leg states what it would spend."""
    lines = [
        f"account already holds -- resting: {existing.resting_pairs or '(none)'} - "
        f"positions: {existing.position_pairs or '(none)'} - "
        f"non-EUR: {existing.non_eur_assets or '(none)'}",
    ]
    if not legs:
        lines.append(f"the fixture is complete for {pair}; nothing to mint")
        return "\n".join(lines)
    for leg in legs:
        price = f"@ {leg.price}" if leg.price is not None else "@ market"
        lev = f" leverage {leg.leverage}" if leg.leverage is not None else ""
        lines.append(
            f"  {leg.kind:<8} {leg.side} {leg.quantity} {leg.pair} {price} "
            f"= EUR {leg.notional_eur:.2f} [{leg.account_type} {leg.time_in_force}]{lev}"
        )
    total = sum(leg.notional_eur for leg in legs if leg.order_type == "MARKET")
    lines.append(f"  spends at market: EUR {total:.2f} (the resting leg rests, it does not spend)")
    return "\n".join(lines)


def mint_client_order_id(kind: str, stamp: str) -> str:
    """Identifiable by construction, so a later reader can tell what minted a row."""
    return f"{FIXTURE_ORDER_TAG}-{kind}-{stamp}"


def require_credentials() -> tuple[str, str]:
    """Mirrors the order-semantics harness: the wrapper puts them here and nowhere else."""
    missing = [v for v in (API_KEY_VAR, API_SECRET_VAR) if not os.environ.get(v)]
    if missing:
        raise Refusal(
            f"REFUSING: {' and '.join(missing)} not set in the environment.\n"
            f"Run through infra/scripts/probe-with-vaulted-key.sh, which puts the vaulted trade "
            f"key into this process's environment and nothing else -- it never reaches a file, a "
            f"shell you keep, or a command line.",
        )
    return os.environ[API_KEY_VAR], os.environ[API_SECRET_VAR]


# --------------------------------------------------------------------------------------------
# The venue surface. Everything above this line is pure and covered by `tests/`; everything below
# it is exercised only by an attended run against the live account, because it is the part that
# talks. Each takes the client, so the tests drive it with a recording stub.
# --------------------------------------------------------------------------------------------


async def read_pair(client, pair: str) -> tuple[PairLimits, float, object]:
    """The pair's floors and the run's own best bid, both read now rather than remembered.

    The instrument is returned with them because `submit_order` needs it cached: the client
    documents `The instrument is not found in cache.` among its errors, and the cache's only writer
    is `cache_instrument`. That is a requirement of MINTING, and says nothing about what any other
    reader of this account can see.
    """
    from nautilus_trader.model import InstrumentId

    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS[pair])
    rows = await client.request_instruments(pairs=None)
    match = [row for row in rows if str(getattr(row, "id", "")) == str(instrument_id)]
    if not match:
        raise Refusal(f"REFUSING: {pair} is not in the venue's listing")
    row = match[0]
    limits = PairLimits(
        ordermin=float(row.min_quantity),
        costmin=float(row.min_notional),
        lot_step=float(row.size_increment),
        price_step=float(row.price_increment),
    )

    book = await client.request_book_snapshot(instrument_id, depth=1)
    # `bids`/`asks` are METHODS on the real `OrderBook`, not sequences -- reading the attribute
    # hands back a bound method, which is truthy and would price the leg off nonsense.
    bids = book.bids()
    if not bids:
        raise Refusal(f"REFUSING: {pair}'s book has no bid to price the resting leg from")
    return limits, float(bids[0].price), row


async def read_account(client, pair: str) -> AccountState:
    """What the account already holds, so a re-run adds nothing it already has."""
    account = AccountId(FIXTURE_ACCOUNT_ID)
    orders = await client.request_order_status_reports(account, open_only=True)
    positions = await client.request_position_status_reports(account)
    state = await client.request_account_state(account)
    return AccountState(
        resting_pairs=tuple({str(getattr(o, "instrument_id", "")).split(".")[0] for o in orders or ()}),
        position_pairs=tuple({str(getattr(p, "instrument_id", "")).split(".")[0] for p in positions or ()}),
        non_eur_assets=tuple(
            {
                code
                for code in (str(getattr(b, "currency", "")) for b in getattr(state, "balances", ()) or ())
                if code and code not in ("EUR", "ZEUR")
            }
        ),
    )


async def submit(client, leg: Leg, instrument, client_order_id: str) -> None:
    """Send one leg. The only write this script makes, and there is no cancel to pair with it."""
    from nautilus_trader.model import InstrumentId

    client.cache_instrument(instrument)
    await client.submit_order(
        account_id=AccountId(FIXTURE_ACCOUNT_ID),
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS[leg.pair]),
        client_order_id=ClientOrderId(client_order_id),
        order_side=OrderSide.BUY if leg.side == "BUY" else OrderSide.SELL,
        order_type=OrderType.LIMIT if leg.order_type == "LIMIT" else OrderType.MARKET,
        quantity=Quantity.from_str(str(leg.quantity)),
        time_in_force=getattr(TimeInForce, leg.time_in_force),
        price=Price.from_str(str(leg.price)) if leg.price is not None else None,
        leverage=leg.leverage,
        account_type=AccountType.MARGIN if leg.account_type == "MARGIN" else AccountType.CASH,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mint the resting order, margin position and non-EUR balance an attended "
        "flatten pass needs. Dry run by default: --execute is required before anything is sent.",
    )
    parser.add_argument("--pair", default=DEFAULT_PAIR, help=f"default {DEFAULT_PAIR}")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="send the plan. Without it nothing reaches the venue.",
    )
    return parser.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    assert_same_key(args.pair)
    require_eur_quote(args.pair)
    key, secret = require_credentials()
    print(f"credentials: {API_KEY_VAR} and {API_SECRET_VAR} are present (never printed)")

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    client = KrakenSpotHttpClient(key, secret)
    limits, best_bid, instrument = await read_pair(client, args.pair)
    print(
        f"{args.pair} now: best bid {best_bid}, ordermin {limits.ordermin}, "
        f"costmin {limits.costmin} (read this run, not remembered)"
    )
    existing = await read_account(client, args.pair)
    legs = plan_legs(pair=args.pair, limits=limits, best_bid=best_bid, existing=existing)
    print(render_plan(legs, existing, args.pair))

    if not args.execute:
        print("\nDRY RUN -- nothing was sent. Re-run with --execute to mint.")
        return 0
    if not legs:
        return 0
    if not sys.stdin.isatty():
        raise Refusal("REFUSING: --execute needs a terminal for the confirmation")
    check_confirmation(input(f"\nType {CONFIRM_WORD} to send the plan above: ").strip())

    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    for leg in legs:
        coid = mint_client_order_id(leg.kind, stamp)
        await submit(client, leg, instrument, coid)
        print(f"  sent {leg.kind} as {coid}")
    print(f"\nminted {len(legs)} leg(s). Nothing here cancels them.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_run(parse_args(argv)))
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
