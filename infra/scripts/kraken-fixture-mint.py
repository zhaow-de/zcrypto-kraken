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

EVERY SIZE COMES FROM THE VENUE'S OWN ROW AT RUN TIME. `ordermin`, `costmin` and both steps come
from the raw AssetPairs row on the run that uses them -- never from a remembered figure, which is
rejected at submit if it has fallen below a floor and silently accepted at a notional nobody chose if
it has not; and never from the adapter's instrument object, which is a TRANSLATION of that row and
can hand back None for a field it did not populate. A floor this script cannot read is a refusal:
defaulted to zero it would size a leg at nothing and report it clear of a minimum the venue still
enforces. The resting leg is sized at the price it will REST at, not at the bid -- `costmin` binds on
what an order is worth, and this one is worth a stated fraction of the market.

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

from cli.engine.flatten import BLIND_ORDER_READ_LEGS, QUOTE_CURRENCY, resolve_base
from cli.engine.instruments import (
    INSTRUMENT_IDS,
    BelowMinimum,
    SizedOrder,
    _floor_to_step,
    size_order,
)
from cli.snapshot.assetpairs import _COMMON_TO_KRAKEN, _wsname_index
from cli.snapshot.fetch import fetch_public

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

# The longest client order id this venue is RECORDED as having accepted: the order-semantics probe's
# `O-<YYYYMMDD>-<HHMMSS>-901-P6V-<seq>` at one-digit seq, whose passing runs the adapter-verification
# rows carry. It is a measurement, not a limit, which is why it is printed beside this script's own
# longer ids rather than used to size them.
_PROVEN_COID_LENGTH = 27

# Flooring can drop a target under a floor it cleared; a few steps is ample and a runaway is a
# listing that is not what this script assumes, which is a refusal rather than a loop.
_SIZE_WALK_LIMIT = 8


class Refusal(Exception):
    """A precondition this script will not proceed without. Never caught inside it."""


@dataclass(frozen=True)
class PairLimits:
    """What the venue's own AssetPairs row publishes about one pair, read on the run that uses it.

    The two steps are the row's `lot_decimals`/`pair_decimals` as a step, because that is the shape
    `size_order` quantizes in; the two floors are its `ordermin`/`costmin` verbatim.
    """

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
    if pair not in INSTRUMENT_IDS:
        raise Refusal(
            f"REFUSING: {pair} is not one of the basket's instruments, so this guard has no opinion "
            f"about it. Mint on a basket pair; {DEFAULT_PAIR} is the default.",
        )
    if pair in BLIND_ORDER_READ_LEGS:
        raise Refusal(
            f"REFUSING: {pair} is spelled two ways at the venue, so a resting order on it is "
            f"dropped by the order-report read and the attended pass would read clean against an "
            f"account it cannot see. Mint on a same-key pair; {DEFAULT_PAIR} is the default.",
        )


def assert_row_is_same_key(pair: str, pair_key: str, row: dict) -> None:
    """The same property as `assert_same_key`, measured from the venue's row instead of remembered.

    `assert_same_key` reads a list this repo maintains; this reads the property that list describes,
    off the row the run has already fetched. Two producers of one fact are the check on each other,
    and each refusal names which fired: a leg the list has not learned about yet is caught here, and
    a disagreement between the two is a finding about the list rather than a duplicate refusal.

    It cannot replace the list. It needs the listing, so it fires later than `assert_same_key`,
    which refuses before anything is read at all -- and the list's identity with `flatten`'s own
    constant is what keeps this script and the engine talking about the same five legs.
    """
    altname = _row_field(row, "altname", pair)
    if altname == pair_key:
        return
    remembered = (
        "the hardcoded list agrees"
        if pair in BLIND_ORDER_READ_LEGS
        else "and BLIND_ORDER_READ_LEGS does NOT carry this leg -- the list in cli/engine/flatten.py "
        "is behind the venue, which is a finding about the list"
    )
    raise Refusal(
        f"REFUSING (measured from the listing, not from the list): {pair} is keyed {pair_key} and "
        f"spelled {altname}, so an order on it is dropped by the adapter's order-report read and a "
        f"fixture there is invisible to the verdict it exists to exercise; {remembered}.",
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


def _row_field(row: dict, field: str, pair: str) -> str:
    """One published field, or a refusal. Never a default.

    A floor that is absent and a floor that is zero are the same number to `size_order` and opposite
    facts about the venue: the second says any size clears, the first says this script does not know.
    Defaulting the first to the second sizes a leg at nothing and prints it clear of a minimum the
    venue still enforces at submit, which is the failure this whole script exists to avoid staging.
    """
    value = row.get(field)
    if value is None:
        raise Refusal(
            f"REFUSING: {pair}'s AssetPairs row publishes no {field}. A floor this script cannot "
            f"read is not one it may assume -- re-run when the listing carries it.",
        )
    return value


def resolve_row(assetpairs_result: dict, pair: str) -> tuple[str, dict]:
    """This pair's `(key, row)` from the raw listing, resolved by wsname.

    Split from `pair_limits` so the lookup and the refusal it feeds are separately checkable: a
    lookup that could not find a two-way-spelled row would hide the refusal behind a miss.
    """
    base, quote = pair.split("/")
    ws_key = f"{_COMMON_TO_KRAKEN.get(base, base)}/{_COMMON_TO_KRAKEN.get(quote, quote)}"
    hit = _wsname_index(assetpairs_result).get(ws_key)
    if hit is None:
        raise Refusal(f"REFUSING: {pair} is in no AssetPairs row under the wsname {ws_key}")
    return hit


def pair_limits(assetpairs_result: dict, pair: str) -> PairLimits:
    """This pair's floors and steps, off the raw listing that the venue enforces at submit.

    Resolved through the snapshot register's own `wsname` index and its alias map, so a pair whose
    key, altname and wsname disagree (`XXBTZEUR` / `XBTEUR` / `XBT/EUR`) is found the one way that
    works for all of them -- and so this lookup cannot drift from the register's.
    """
    pair_key, row = resolve_row(assetpairs_result, pair)
    assert_row_is_same_key(pair, pair_key, row)
    return PairLimits(
        ordermin=float(_row_field(row, "ordermin", pair)),
        costmin=float(_row_field(row, "costmin", pair)),
        lot_step=10.0 ** -int(_row_field(row, "lot_decimals", pair)),
        price_step=10.0 ** -int(_row_field(row, "pair_decimals", pair)),
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
        # Priced first, then sized AT that price. `costmin` is a floor on the order's own notional,
        # and this order's notional is a stated fraction of the market's: sizing it at the bid
        # clears a floor the resting leg itself would miss, and the venue rejects it at submit.
        price = resting_price(best_bid, limits.price_step)
        qty, notional = size_leg(limits, price=price)
        legs.append(
            Leg(
                kind="resting",
                pair=pair,
                side="BUY",
                order_type="LIMIT",
                quantity=qty,
                price=price,
                notional_eur=notional,
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


def render_plan(legs: list[Leg], existing: AccountState, pair: str, stamp: str) -> str:
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
        coid = mint_client_order_id(leg.kind, stamp)
        lines.append(
            f"  {leg.kind:<8} {leg.side} {leg.quantity} {leg.pair} {price} "
            f"= EUR {leg.notional_eur:.2f} [{leg.account_type} {leg.time_in_force}]{lev} as {coid}"
        )
    total = sum(leg.notional_eur for leg in legs if leg.order_type == "MARKET")
    lines.append(f"  spends at market: EUR {total:.2f} (the resting leg rests, it does not spend)")
    # What the repo holds about id length is one measurement and one claim that cannot both be read
    # as written. The probe's ids were ACCEPTED AT SUBMIT at `_PROVEN_COID_LENGTH`; a comment in that
    # same probe asserts an 18-character venue truncation. Acceptance at submit does not refute a
    # truncation in what the venue STORES -- no run has ever read an id back -- so the two are not
    # strictly contradictory; what is self-inconsistent is the comment, which relies on an infix
    # sitting past character 18 surviving that very cut. The operator gets the measured number and
    # the open question, because picking one silently is how a contradiction becomes a fact.
    longest = max(len(mint_client_order_id(leg.kind, stamp)) for leg in legs)
    lines.append(
        f"  longest client order id here: {longest} characters. The only MEASURED acceptance on "
        f"this adapter is the order-semantics probe's shape, at {_PROVEN_COID_LENGTH}, and that is "
        f"acceptance AT SUBMIT -- no id has ever been read back from the venue. A comment in that "
        f"probe also claims an 18-character truncation. Record what the venue does with these ids "
        f"-- accepted, refused, or echoed back shortened -- in the version's "
        f"docs/reference/adapter-verification/ row."
    )
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
            f"Run through infra/scripts/mint-with-vaulted-key.sh, which puts the vaulted trade "
            f"key into this process's environment and nothing else -- it never reaches a file, a "
            f"shell you keep, or a command line. It is this script's own wrapper: the probe's "
            f"names a different program and cannot run this one.",
        )
    return os.environ[API_KEY_VAR], os.environ[API_SECRET_VAR]


# --------------------------------------------------------------------------------------------
# The venue surface. Everything above this line is pure and covered by `tests/`; everything below
# it is exercised only by an attended run against the live account, because it is the part that
# talks. Each takes the client, so the tests drive it with a recording stub.
# --------------------------------------------------------------------------------------------


async def read_pair(client, pair: str) -> tuple[float, object]:
    """The run's own best bid, and the instrument object -- for `cache_instrument` and nothing else.

    The object is needed because `submit_order` documents `The instrument is not found in cache.`
    among its errors and the cache's only writer is `cache_instrument`. It is NOT where a size comes
    from: it is the adapter's translation of the listing, and a field the translation does not
    populate arrives as None rather than as an error -- `min_quantity` came back None for SOL/EUR
    when this was measured. `pair_limits` reads the row the venue enforces instead.
    """
    from nautilus_trader.model import InstrumentId

    instrument_id = InstrumentId.from_str(INSTRUMENT_IDS[pair])
    rows = await client.request_instruments(pairs=None)
    match = [row for row in rows if str(getattr(row, "id", "")) == str(instrument_id)]
    if not match:
        raise Refusal(f"REFUSING: {pair} is not in the venue's listing")
    row = match[0]

    book = await client.request_book_snapshot(instrument_id, depth=1)
    # `bids`/`asks` are METHODS on the real `OrderBook`, not sequences -- reading the attribute
    # hands back a bound method, which is truthy and would price the leg off nonsense.
    bids = book.bids()
    if not bids:
        raise Refusal(f"REFUSING: {pair}'s book has no bid to price the resting leg from")
    return float(bids[0].price), row


async def read_account(client, pair: str, limits: PairLimits, best_bid: float) -> AccountState:
    """What the account already holds, so a re-run adds nothing it already has.

    Every kwarg here is `flatten`'s own, verbatim, because a read this script makes in a different
    MODE than the reader it is minting for answers a different question and this guard cannot tell
    the two apart -- an answer of "nothing" from the wrong mode is indistinguishable from a flat
    account, and it fails in the expensive direction: a leg minted again on every run.
    """
    account = AccountId(FIXTURE_ACCOUNT_ID)
    orders = await client.request_order_status_reports(account, open_only=True)
    # WITHOUT these three the client's own docstring says it "returns an empty vector" -- the CASH
    # default with spot reports off reads no leveraged position at all. This guard would then pass
    # against an account already carrying one and open another 2x position on every `--execute`,
    # while the printed plan says `positions: (none)`.
    positions = await client.request_position_status_reports(
        account,
        account_type=AccountType.MARGIN,
        use_spot_position_reports=False,
        quote_currency=QUOTE_CURRENCY,
    )
    state = await client.request_account_state(account, account_type=AccountType.CASH)
    base = pair.split("/")[0]
    return AccountState(
        resting_pairs=tuple({str(getattr(o, "instrument_id", "")).split(".")[0] for o in orders or ()}),
        position_pairs=tuple({str(getattr(p, "instrument_id", "")).split(".")[0] for p in positions or ()}),
        non_eur_assets=_held_bases(getattr(state, "balances", ()) or (), base, limits, best_bid),
    )


def _held_bases(balances, base: str, limits: PairLimits, best_bid: float) -> tuple[str, ...]:
    """Every non-EUR base the account holds, with the MINT pair's own base judged against its floors.

    Two things a bare currency-code set gets wrong about THIS pair's base, both in the direction of
    SKIPPING the spot leg and leaving the attended pass with nothing to sell. A code with a dust
    balance still satisfies a presence test: `flatten` drops a leg whose free amount is not positive
    and the venue refuses one under `ordermin`, so a residual left by a partial fill would satisfy
    this forever. And the venue spells assets its own way -- `XXDG` for DOGE -- so a raw code never
    equals the common base it stands for; the mapping is `flatten`'s `resolve_base` rather than a
    second copy of it here.

    The floors belong to the mint pair and to no other row. Every OTHER non-EUR code is listed as
    held at any size above zero, because this line is also what the operator reads to see the
    account, and judging a BTC balance by SOL's `ordermin` at SOL's bid would print
    `non-EUR: (none)` over an account holding a thousand euros of it. A zero row is still not a
    holding. Nothing is gated on those codes -- only `base` is.
    """
    held = set()
    for row in balances:
        code = str(getattr(getattr(row, "currency", None), "code", "") or "")
        if not code or code in ("EUR", "ZEUR"):
            continue
        free = float(getattr(row, "free", 0.0) or 0.0)
        # A zero row is not a holding. The venue lists an asset the account no longer has, and
        # `flatten` skips a leg whose free amount is not positive -- so printing it as held would be
        # the mirror of the defect the per-row floors fixed: a line the operator cannot trust.
        if free <= 0.0:
            continue
        resolved = resolve_base(code, frozenset({base})) or code
        if resolved != base:
            held.add(resolved)
            continue
        # BOTH floors, because `flatten` classifies a balance against both and this guard exists to
        # predict what `flatten` will find sellable. A quantity over `ordermin` whose notional is
        # under `costmin` is `dust` there and is not sold, so counting it here would skip the spot
        # leg and leave the sell path with a balance the command declines to touch.
        if free < limits.ordermin or free * best_bid < limits.costmin:
            continue
        held.add(resolved)
    return tuple(sorted(held))


async def submit(client, leg: Leg, instrument, client_order_id: str) -> None:
    """Send one leg. The only write this script makes, and there is no cancel to pair with it."""
    from nautilus_trader.model import InstrumentId

    client.cache_instrument(instrument)
    quantity = Quantity.from_str(str(leg.quantity))
    price = Price.from_str(str(leg.price)) if leg.price is not None else None
    # `from_str` parses a repr, and a float whose shortest repr runs past the venue's precision
    # comes back as a DIFFERENT number without raising. Both operands are `_floor_to_step` outputs
    # today, whose reprs are exact decimals, so this states the property rather than fixing it -- and
    # it is a raise rather than an `assert` because this is the last check on the number that reaches
    # the venue, and `assert` is the one guard shape `-O` removes without touching the file.
    if float(quantity) != leg.quantity or (price is not None and float(price) != leg.price):
        raise Refusal(
            f"REFUSING: the {leg.kind} leg's numbers changed in translation to the venue's types "
            f"({leg.quantity} -> {quantity}, {leg.price} -> {price}); nothing further was sent.",
        )
    await client.submit_order(
        account_id=AccountId(FIXTURE_ACCOUNT_ID),
        instrument_id=InstrumentId.from_str(INSTRUMENT_IDS[leg.pair]),
        client_order_id=ClientOrderId(client_order_id),
        order_side=OrderSide.BUY if leg.side == "BUY" else OrderSide.SELL,
        order_type=OrderType.LIMIT if leg.order_type == "LIMIT" else OrderType.MARKET,
        quantity=quantity,
        time_in_force=getattr(TimeInForce, leg.time_in_force),
        price=price,
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


def _live_client(key: str, secret: str):
    """The bare client `flatten` reads with. Imported here so the module loads without the adapter."""
    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    return KrakenSpotHttpClient(key, secret)


def _live_listing() -> dict:
    """The venue's AssetPairs `result`, through the repo's own public reader."""
    return fetch_public("AssetPairs")


async def _run(
    args: argparse.Namespace,
    *,
    client_factory,
    listing_factory,
    prompt=input,
) -> int:
    """Injected the way `run_flatten` injects its readers, so a test can drive the whole path with a
    recording client and assert on what was NOT sent -- which is the property that matters here.

    Both factories are REQUIRED, with no default between them: a default binds the live one at
    definition, so a test that patches the module attribute instead of passing the argument gets a
    real client built and a real request sent, silently and successfully. That has happened here.
    `main` is the only caller that names the live pair.
    """
    assert_same_key(args.pair)
    require_eur_quote(args.pair)
    key, secret = require_credentials()
    print(f"credentials: {API_KEY_VAR} and {API_SECRET_VAR} are present (never printed)")

    client = client_factory(key, secret)
    limits = pair_limits(listing_factory(), args.pair)
    best_bid, instrument = await read_pair(client, args.pair)
    # Warmed BEFORE the account reads, not just before `submit`. The order-report read resolves
    # rows through this cache, and the adapter drops a row it cannot resolve while returning
    # success -- so a cold cache would empty the resting-order guard rather than fail it. Cheap,
    # and it closes the question from this side rather than leaving it to the live run.
    client.cache_instrument(instrument)
    print(
        f"{args.pair} now: best bid {best_bid}, ordermin {limits.ordermin}, "
        f"costmin {limits.costmin} (read this run, not remembered)"
    )
    existing = await read_account(client, args.pair, limits, best_bid)
    legs = plan_legs(pair=args.pair, limits=limits, best_bid=best_bid, existing=existing)
    # Minted BEFORE the plan is printed and reused at submit, so the ids the operator reads are the
    # ids that go out -- not a second set generated after they approved the first.
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    print(render_plan(legs, existing, args.pair, stamp))

    if not args.execute:
        print("\nDRY RUN -- nothing was sent. Re-run with --execute to mint.")
        return 0
    if not legs:
        return 0
    if not sys.stdin.isatty():
        raise Refusal("REFUSING: --execute needs a terminal for the confirmation")
    check_confirmation(prompt(f"\nType {CONFIRM_WORD} to send the plan above: ").strip())

    for leg in legs:
        coid = mint_client_order_id(leg.kind, stamp)
        await submit(client, leg, instrument, coid)
        print(f"  sent {leg.kind} as {coid}")
    print(f"\nminted {len(legs)} leg(s). Nothing here cancels them.")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(_run(parse_args(argv), client_factory=_live_client, listing_factory=_live_listing))
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
