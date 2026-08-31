"""`zcrypto engine flatten` -- the red button (spec 00106).

A standalone sweep of the whole Kraken account over the adapter's HTTP client: cancel every
resting order, close every margin position with a reduce-only MARKET order, sell every non-EUR
spot balance at MARKET. It shares NO code path with `cli/engine/executor.py` by design -- the
button must work when the engine's own order machine is what broke, which is why
`tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module` allowlists
this module as a second venue-mutating one rather than being satisfied by reuse.

Every venue answer is `typing.Any` (`nautilus_trader/adapters/kraken/__init__.pyi`), so the read
layer below names the fields it requires and ABORTS on an absent one rather than guessing: a shape
the venue changed is a finding. Before the first write that abort is exit 3; after it, exit 2 --
the account may already have moved.

MARKET is used deliberately, overriding spec 00090 D6's rejection of it for the probe machine: in
a crash the price is not the variable, time is, and a bounded IOC in a fast market leaves residue
that IS the exposure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from nautilus_trader.model import AccountId, AccountType, ClientOrderId, OrderSide, OrderType, Quantity, TimeInForce

from cli.logging import get_logger

logger = get_logger("engine.flatten")

if TYPE_CHECKING:
    from cli.engine.instruments import BelowMinimum, SizedOrder

# The account the exec client reports under -- `cli/engine/node.py`'s `_ACCOUNT_ID`, pinned equal
# by tests/test_engine_flatten.py so a rename cannot point the sweep at another account.
ACCOUNT_ID = "KRAKEN-001"
# Tier 1 taker, docs/reference/kraken-fee-schedule.md (schedule effective 2026-07-09). Printed as
# an estimate only; nothing branches on it.
TAKER_RATE = 0.0080
CONFIRM_WORD = "FLATTEN"
# Never collides with the engine's ids, which carry the `-001-000-` infix minted from
# TraderId("SHADOW-001") plus order-id tag "000" (`cli/engine/node.py`): the executor's own-order
# routing would otherwise treat an ack of ours as its own.
CLIENT_ORDER_ID_PREFIX = "FLT-"
BOOK_DEPTH = 1
# The venue-alias spelling of the euro on the quote surfaces (546 live instruments carry `ZEUR`,
# zero carry `EUR` -- docs/reference/adapter-verification/2.0.0rc4.dev20260825.md observation 4).
QUOTE_CURRENCY = "ZEUR"
# The rung-1 leverage, and the only value ever accepted live from this repo (probes 4c/4d in
# docs/reference/adapter-verification/2.0.0rc4.dev20260825.md). PositionStatusReport carries no
# leverage field, so a closer cannot echo the position's; what the venue does with a mismatched
# leverage on a reduce-only closer is unmeasured, and the go-live drill program's red-button drill
# is where it gets measured.
MARGIN_LEVERAGE = 2
# `Recorder.call` writes one `repr` per answer into a single JSON string field, and
# `request_instruments()` alone answers with ~1600 rows -- around 110 KB at the installed adapter's
# ~68-char `CurrencyPair.__repr__`. Capped so the incident artifact stays openable mid-incident.
_ANSWER_REPR_LIMIT = 4000

# Real nautilus types reach the client; the journal records their string forms. A plain `str` where
# the compiled signature wants `AccountId`/`AccountType` fails at the venue, not in a test.
_ACCOUNT = AccountId(ACCOUNT_ID)


class FlattenRefused(Exception):
    """Refused with nothing sent -- exit 1. The kill-file and terminal gates precede every read;
    the confirm mismatch follows the plan's reads and still precedes every write."""


class FlattenUnreachable(Exception):
    """The venue could not be reached or read. Exit 3 while raised before the first write; the
    caller converts it to exit 2 once `cancel_all_orders` has gone out."""


@dataclass(frozen=True)
class PairConstraints:
    symbol: str
    instrument_id: Any
    ordermin: float
    lot_step: float
    tick_size: float


@dataclass(frozen=True)
class PositionRow:
    symbol: str
    instrument_id: Any
    side: str  # LONG / SHORT / FLAT
    quantity: float  # unsigned; PositionStatusReport carries no signed quantity


@dataclass(frozen=True)
class BalanceRow:
    code: str
    free: float


class Recorder:
    """Every request with its parameters and every answer verbatim -- the journal's spine.

    `repr` is the verbatim form available: the adapter returns opaque objects with no committed
    serialization, and a reader mid-incident needs what came back, not our summary of it. Capped at
    `_ANSWER_REPR_LIMIT` with the full length named in the suffix, so the one ~1600-row listing
    answer cannot make the artifact awkward to open and no reader mistakes a cut repr for the whole.
    """

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def call(self, name: str, params: dict, fn: Callable[[], Any]) -> Any:
        entry: dict = {"call": name, "params": dict(params)}
        self.entries.append(entry)
        try:
            answer = fn()
        except Exception as exc:  # noqa: BLE001 -- every transport failure is recorded, then classified
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        answer_repr = repr(answer)
        if len(answer_repr) > _ANSWER_REPR_LIMIT:
            answer_repr = f"{answer_repr[:_ANSWER_REPR_LIMIT]}... [truncated, {len(answer_repr)} chars total]"
        entry["answer"] = answer_repr
        return answer


def _required(obj: Any, field: str, what: str) -> Any:
    value = getattr(obj, field, None)
    if value is None:
        raise FlattenUnreachable(f"{what}: the venue's answer carries no readable {field}")
    return value


def _as_float(value: Any, field: str, what: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not a number") from exc
    if not math.isfinite(out):
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not finite")
    return out


def _as_step(value: Any, field: str, what: str) -> float:
    """A quantization step, which must be positive to be one.

    `_required` only rejects `None`, so a venue publishing `0` would reach `_floor_to_step` and
    raise a bare `ValueError` no caller here catches -- the operator would get a traceback where
    the exit-code contract promises a named unreachable. A zero step IS a shape the venue changed.
    """
    out = _as_float(value, field, what)
    if out <= 0.0:
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not a positive step")
    return out


def _symbol_of(instrument_id: Any) -> str:
    """`BTC/EUR.KRAKEN` -> `BTC/EUR`. The venue half is stripped; the adapter has already renamed
    Kraken's legacy XBT/XDG codes (`cli/engine/instruments.py`)."""
    return str(instrument_id).rsplit(".", 1)[0]


def _journalled(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments as the journal records them: a nautilus enum by its string form, every
    other value verbatim.

    Each read below builds ONE kwargs dict and both sends and journals it, so no scoping value is
    spelled a second time beside the call. A hand-written literal is a journal that can read MARGIN
    while CASH went out, and the journal is what an operator reads mid-incident.
    """
    return {key: str(value) if isinstance(value, AccountType) else value for key, value in kwargs.items()}


def read_open_orders(client: Any, rec: Recorder) -> list[Any]:
    """Every order resting at the venue. Only the LIST is load-bearing here -- its length decides
    the exit code -- so no per-row field is required: an unparseable row must not abort a sweep
    whose whole answer is 'something is still working'."""
    # `account_id` is the constant `_ACCOUNT` is minted from, not a second spelling of it.
    kwargs: dict[str, Any] = {"open_only": True}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = rec.call(
            "request_order_status_reports",
            params,
            lambda: client.request_order_status_reports(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"open orders could not be read: {exc}") from exc
    if rows is None:
        raise FlattenUnreachable("open orders could not be read: the venue answered nothing")
    return list(rows)


def read_positions(client: Any, rec: Recorder) -> list[PositionRow]:
    kwargs: dict[str, Any] = {
        "account_type": AccountType.MARGIN,
        "use_spot_position_reports": False,
        "quote_currency": QUOTE_CURRENCY,
    }
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = rec.call(
            "request_position_status_reports",
            params,
            lambda: client.request_position_status_reports(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"margin positions could not be read: {exc}") from exc
    # `None` read as "no positions" is the one shape that CONFIRMS ITSELF: `build_plan` shows no
    # margin leg, the writes run, and `judge_final` re-reads through this same function, finds no
    # residual and reports the account flat at exit 0 with leveraged positions still open. Unlike
    # its three siblings this read has no downstream backstop -- `read_listing` has its empty-map
    # raise and `read_balances` has `_required(state, "balances")`.
    if rows is None:
        raise FlattenUnreachable("margin positions could not be read: the venue answered nothing")
    out = []
    for row in list(rows or []):
        what = "a margin position row"
        instrument_id = _required(row, "instrument_id", what)
        side = str(_required(row, "position_side", what))
        # `PositionSide.LONG` and a bare `LONG` both reduce to the last dotted component.
        side = side.rsplit(".", 1)[-1].upper()
        qty = _as_float(_required(row, "quantity", what), "quantity", what)
        out.append(PositionRow(symbol=_symbol_of(instrument_id), instrument_id=instrument_id, side=side, quantity=qty))
    return out


def read_balances(client: Any, rec: Recorder) -> list[BalanceRow]:
    kwargs: dict[str, Any] = {"account_type": AccountType.CASH}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        state = rec.call(
            "request_account_state",
            params,
            lambda: client.request_account_state(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"spot balances could not be read: {exc}") from exc
    what = "the account state"
    balances = _required(state, "balances", what)
    out = []
    for row in list(balances):
        currency = _required(row, "currency", "a balance row")
        code = str(_required(currency, "code", "a balance row's currency"))
        free = _as_float(_required(row, "free", f"the {code} balance"), "free", f"the {code} balance")
        out.append(BalanceRow(code=code, free=free))
    return out


def read_listing(client: Any, rec: Recorder) -> dict[str, Any]:
    """ONE no-argument call for the whole listing. A per-pair request would error on an unknown
    pair and abort the sweep over an unrelated holding; pairlessness is read from this map."""
    try:
        rows = rec.call("request_instruments", {"pairs": None}, lambda: client.request_instruments())
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"the instrument listing could not be read: {exc}") from exc
    listing = {}
    for row in list(rows or []):
        instrument_id = getattr(row, "id", None)
        if instrument_id is None:
            continue
        listing[_symbol_of(instrument_id)] = row
    if not listing:
        raise FlattenUnreachable("the instrument listing came back empty -- every pair lookup after it would read as pairless")
    return listing


def constraints_for(symbol: str, listing: dict[str, Any]) -> PairConstraints:
    """The three constraints a sized order needs, required on THIS pair only. Validating the whole
    ~1600-row listing would let one unrelated row abort the button.

    Reaching the absent-row raise below means a caller handed over a leg it should have routed:
    `margin_legs` and `spot_legs` both hold back a pairless one, precisely so that one row cannot
    abort a sweep that has not yet cancelled, closed or sold anything.
    """
    row = listing.get(symbol)
    if row is None:
        raise FlattenUnreachable(f"{symbol} is not in the venue's listing")
    what = f"{symbol}'s listing row"
    return PairConstraints(
        symbol=symbol,
        instrument_id=_required(row, "id", what),
        ordermin=_as_float(_required(row, "min_quantity", what), "ordermin", what),
        lot_step=_as_step(_required(row, "size_increment", what), "lot_step", what),
        tick_size=_as_step(_required(row, "price_increment", what), "tick_size", what),
    )


def read_book_price(client: Any, rec: Recorder, constraints: PairConstraints, side: str) -> float:
    """Best bid for a sell, best ask for a buy. Used for the printed estimate and for the dust
    boundary -- never as an order price, since every order this module sends is MARKET."""
    params = {"instrument_id": str(constraints.instrument_id), "depth": BOOK_DEPTH}
    try:
        book = rec.call(
            "request_book_snapshot",
            params,
            lambda: client.request_book_snapshot(constraints.instrument_id, depth=BOOK_DEPTH),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"{constraints.symbol}: the book could not be read: {exc}") from exc
    what = f"{constraints.symbol}'s book"
    levels = _required(book, "bids" if side == "SELL" else "asks", what)
    levels = list(levels)
    if not levels:
        raise FlattenUnreachable(f"{what}: the {'bid' if side == 'SELL' else 'ask'} side is empty")
    price = _as_float(_required(levels[0], "price", what), "price", what)
    if price <= 0.0:
        # `_required` rejects only `None` and `_as_float` only the non-finite, so a zero would flow
        # into `plan.prices` and make every notional read as nothing -- below every `costmin`, so
        # `size_leg` lists every basket leg as dust and `judge_final`, one predicate at the same
        # price, agrees: the account reported flat at exit 0 with the whole spot book still held.
        # Refused here, the leg degrades to unpriced, which is the direction that SELLS it.
        raise FlattenUnreachable(f"{what}: the top of the {'bid' if side == 'SELL' else 'ask'} side is {price!r}, not a price")
    return price


def step_precision(step: float) -> int:
    """The decimal precision one venue step implies -- 0.1 -> 1, 0.00000001 -> 8. Kraken publishes
    `lot_decimals` alongside the step and the two agree across the basket, so deriving one from the
    other keeps a minted Quantity exactly representable at the floored value."""
    return max(0, -Decimal(str(step)).as_tuple().exponent)


# Kraken's legacy codes, renamed by the adapter's own `normalize_spot_symbol` before an
# InstrumentId is built (`cli/engine/instruments.py`'s module docstring). The `X`/`Z` strip below
# handles the mechanical prefixes; these two renames it cannot derive.
ASSET_ALIASES = {"XBT": "BTC", "XXBT": "BTC", "XDG": "DOGE", "XXDG": "DOGE"}


@dataclass(frozen=True)
class Leg:
    kind: str  # margin | spot
    base: str
    symbol: str
    side: str  # BUY | SELL
    quantity: float
    account_type: str  # MARGIN | CASH
    source: str  # what the quantity came from, for the journal


def listed_bases(listing: dict[str, Any]) -> frozenset[str]:
    return frozenset(symbol.split("/")[0] for symbol in listing)


def resolve_base(code: str, bases: frozenset[str]) -> str | None:
    """Map one balance currency code onto a base the listing actually lists. The LISTING is the
    authority -- a spelling rule alone would invent a base the venue does not trade."""
    upper = code.upper()
    for candidate in (upper, ASSET_ALIASES.get(upper), upper[1:] if len(upper) > 3 and upper[0] in ("X", "Z") else None):
        if candidate and candidate in bases:
            return candidate
    return None


def choose_pair(base: str, listing: dict[str, Any]) -> str | None:
    """EUR first, BTC second, nothing third. Read from the ONE listing taken at the snapshot, never
    from a per-pair request that would error on an unknown pair."""
    for quote in ("EUR", "BTC"):
        symbol = f"{base}/{quote}"
        if symbol in listing:
            return symbol
    return None


def margin_legs(positions: list[PositionRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]:
    """One leg per LONG or SHORT row, plus the rows this code cannot build a closer for.

    A FLAT row is not a leg. Every other row this code cannot act on -- a side that is none of the
    three (the installed `PositionSide` carries a fourth member and which ones the adapter emits is
    unmeasured), a pair the listing does not carry -- is NAMED rather than raised on and never read
    as flat: nothing can be sized for it, and one such row must not abort a button that has not yet
    cancelled an order, closed another position or sold a single balance. `judge_final` reads both
    classes back out of the final snapshot, so neither can leave the run reading 0.
    """
    sides = {"LONG": "SELL", "SHORT": "BUY"}
    out = []
    unclosable: list[dict] = []
    for row in positions:
        if row.side == "FLAT":
            continue
        side = sides.get(row.side)
        if side is None:
            unclosable.append(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "reason": "unrecognised_position_side",
                    "note": "the venue answered a side this command cannot derive a close from",
                }
            )
            continue
        if row.symbol not in listing:
            unclosable.append(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "reason": "pair_not_listed",
                    "note": "the listing carries no such pair, so nothing can be sized against it",
                }
            )
            continue
        out.append(
            Leg(
                kind="margin",
                base=row.symbol.split("/")[0],
                symbol=row.symbol,
                side=side,
                quantity=row.quantity,
                account_type="MARGIN",
                source="position_status_report.quantity",
            )
        )
    return out, unclosable


def spot_legs(balances: list[BalanceRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]:
    """One SELL leg per non-EUR free balance above zero, plus the balances no pair can carry.

    `EUR_CODES` is imported rather than restated so the euro's two venue spellings have one home.
    """
    from cli.engine.instruments import EUR_CODES

    bases = listed_bases(listing)
    legs: list[Leg] = []
    unsellable: list[dict] = []
    for row in balances:
        if row.code.upper() in EUR_CODES:
            continue
        if row.free <= 0.0:
            continue
        base = resolve_base(row.code, bases)
        if base is None:
            unsellable.append(
                {
                    "base": row.code,
                    "code": row.code,
                    "free": row.free,
                    "reason": "no_eur_or_btc_pair",
                    "note": "no listed base matched the code",
                }
            )
            continue
        symbol = choose_pair(base, listing)
        if symbol is None:
            unsellable.append(
                {
                    "base": base,
                    "code": row.code,
                    "free": row.free,
                    "reason": "no_eur_or_btc_pair",
                    "note": "the listing carries neither a EUR nor a BTC pair for it",
                }
            )
            continue
        legs.append(
            Leg(
                kind="spot",
                base=base,
                symbol=symbol,
                side="SELL",
                quantity=row.free,
                account_type="CASH",
                source="account_state.free",
            )
        )
    return legs, unsellable


@dataclass(frozen=True)
class SizedLeg:
    leg: Leg
    qty: float
    reference_price: float | None
    quote: str
    estimate: float | None
    fee_estimate: float | None
    send: bool
    reason: str | None


def costmin_for(symbol: str) -> float | None:
    """The committed per-symbol notional floor, or None when it does not apply to this pair.

    It is committed rather than read live because the adapter never maps Kraken's `costmin` onto
    `min_notional` (`cli/engine/venuestate.py`), and it applies only where its own quote matches
    the pair's -- a BTC-denominated floor compared against a EUR notional passes everything.
    """
    from cli.engine.instruments import COSTMIN

    entry = COSTMIN.get(symbol)
    if entry is None:
        return None
    amount, quote = entry
    return amount if quote == symbol.split("/")[1] else None


def _tick_floored(reference_price: float | None, constraints: PairConstraints) -> float | None:
    """The reference price at the venue's tick, or None where the floor leaves nothing of it.

    A live book price is itself a multiple of its own pair's tick, so a floor to 0.0 means a price
    and a constraint from DIFFERENT pairs were paired. Left at 0.0 every notional reads as nothing,
    the balance is judged dust and `judge_final` -- one predicate, the same price -- agrees the
    account is flat. Unpriced is the direction that SELLS it, which is the direction
    `read_book_price` already takes when it refuses a zero one step earlier.
    """
    from cli.engine.instruments import _floor_to_step

    if reference_price is None:
        return None
    price = _floor_to_step(reference_price, constraints.tick_size)
    return price if price > 0.0 else None


def _size(free: float, constraints: PairConstraints, reference_price: float | None) -> SizedOrder | BelowMinimum:
    """`size_order`'s verdict on one quantity -- the engine's own arithmetic, floors and all.

    A floor that does not apply is passed as 0.0 rather than skipped, so there is ONE call and no
    second flooring implementation beside the one the engine trusts. An absent reference price
    therefore disables only the notional floor, never the quantity one.
    """
    from cli.engine.instruments import size_order

    price = _tick_floored(reference_price, constraints)
    costmin = costmin_for(constraints.symbol)
    applicable = costmin if (costmin is not None and price is not None) else 0.0
    return size_order(
        free,
        price if price is not None else 0.0,
        ordermin=constraints.ordermin,
        costmin=applicable,
        lot_step=constraints.lot_step,
        tick_size=constraints.tick_size,
    )


def classify_balance(free: float, constraints: PairConstraints, reference_price: float | None) -> str:
    """`flat` / `dust` / `residual` for one non-EUR free spot balance.

    THE predicate: the sweep's send decision and the final snapshot's residual verdict both read
    it, so a balance skipped as dust can never also be reported as a residual.

    A margin row is NEVER judged here. Dust is a spot class: the engine's machine deliberately
    produces sub-`ordermin` remainders, and a remainder left open is exposure, so a position below
    every floor is still closed (`size_leg`) and still a residual.
    """
    from cli.engine.instruments import BelowMinimum

    if free <= 0.0:
        return "flat"
    return "dust" if isinstance(_size(free, constraints, reference_price), BelowMinimum) else "residual"


def size_leg(leg: Leg, constraints: PairConstraints, reference_price: float | None) -> SizedLeg:
    """One leg's order quantity and whether it is sent at all.

    A margin closer is sent regardless of the floors -- the engine's machine deliberately produces
    sub-`ordermin` remainders and a remainder left open is exposure, so the venue rules on it. Its
    only unsendable case is a quantity that floors to nothing: there is no order to construct.
    A spot leg below any applicable floor is listed and not sent; the venue would reject it, and it
    does not make the account not-flat.
    """
    from cli.engine.instruments import _floor_to_step

    quote = constraints.symbol.split("/")[1]
    qty = _floor_to_step(leg.quantity, constraints.lot_step)
    # Both operands floored before anything reads them: `size_order` runs its checks on the floored
    # quantity at the floored price, so an estimate printed off the raw balance or the raw book
    # price would disagree with the dust boundary this same leg is judged by.
    price = _tick_floored(reference_price, constraints)
    estimate = qty * price if price is not None else None
    fee = estimate * TAKER_RATE if estimate is not None else None
    base = dict(leg=leg, qty=qty, reference_price=price, quote=quote, estimate=estimate, fee_estimate=fee)

    if leg.kind == "margin":
        if qty <= 0.0:
            return SizedLeg(**base, send=False, reason="unclosable_below_minimum")
        return SizedLeg(**base, send=True, reason=None)

    if classify_balance(leg.quantity, constraints, price) == "residual":
        return SizedLeg(**base, send=True, reason=None)
    return SizedLeg(**base, send=False, reason="dust_below_venue_minimum")


@dataclass(frozen=True)
class Snapshot:
    orders: list
    positions: list
    balances: list


@dataclass(frozen=True)
class Plan:
    margin: list
    spot: list
    unsellable: list
    unclosable: list
    prices: dict
    constraints: dict
    n_open_orders: int


def read_snapshot(client: Any, rec: Recorder) -> Snapshot:
    """Orders, then positions, then balances -- in that order, so an order that fills between two
    of the reads lands in one that FOLLOWS rather than falling out of both."""
    return Snapshot(
        orders=read_open_orders(client, rec),
        positions=read_positions(client, rec),
        balances=read_balances(client, rec),
    )


def build_plan(client: Any, rec: Recorder, snapshot: Snapshot, listing: dict[str, Any]) -> Plan:
    """Every leg, sized, with its reference price -- and every book read taken HERE, before the
    first write.

    `BTC/EUR` is priced whenever a SPOT leg routes through a `/BTC` pair, because the second spot
    pass sells the BTC those legs produce and no read may happen after the first write. A leg with
    no price here -- one that surfaces only in a later pass, a margin leg's `/BTC` proceeds
    included, and equally one whose OWN book read failed -- is sized on the quantity floor alone,
    which is the safe direction: an unpriced balance is sold, never skipped as dust.

    A failing book read is the one pre-write read failure that does not abort (spec D2). Aborting
    here would return exit 3 with the kill file already latched and the engine already stopped: no
    order cancelled, no position closed, no balance sold, over one illiquid pair's empty side.
    """
    margin_raw, unclosable = margin_legs(snapshot.positions, listing)
    spot_raw, unsellable = spot_legs(snapshot.balances, listing)

    wanted: dict[str, str] = {}
    for leg in [*margin_raw, *spot_raw]:
        # One book read per pair, and the FIRST leg on a pair fixes which side it is priced from --
        # margin legs first. Where a margin leg and a spot leg share a pair the loser is priced one
        # spread away, which moves the printed estimate and the dust boundary and nothing else: no
        # order this module sends carries a price.
        wanted.setdefault(leg.symbol, leg.side)
    if any(leg.symbol.endswith("/BTC") for leg in spot_raw) and "BTC/EUR" in listing:
        wanted.setdefault("BTC/EUR", "SELL")

    constraints = {symbol: constraints_for(symbol, listing) for symbol in wanted}
    prices: dict[str, float] = {}
    for symbol, side in wanted.items():
        try:
            prices[symbol] = read_book_price(client, rec, constraints[symbol], side)
        except FlattenUnreachable as exc:
            # Spec D2's ONE exception to abort-on-a-pre-write-read-failure. A thin pair with an
            # empty side, or one rate-limited request, must not cost the account its cancel and
            # every other leg its close: the price is never an order price here (every order is
            # MARKET), so the leg is sized on the quantity floor alone and sent.
            logger.error("%s: no reference price -- sized on the quantity floor alone: %s", symbol, exc)

    return Plan(
        margin=[size_leg(leg, constraints[leg.symbol], prices.get(leg.symbol)) for leg in margin_raw],
        spot=[size_leg(leg, constraints[leg.symbol], prices.get(leg.symbol)) for leg in spot_raw],
        unsellable=unsellable,
        unclosable=unclosable,
        prices=prices,
        constraints=constraints,
        n_open_orders=len(snapshot.orders),
    )


def _leg_line(sized: SizedLeg) -> str:
    head = f"  {sized.leg.kind:<6} {sized.leg.symbol} {sized.leg.side} {sized.qty:.8f}".rstrip()
    if not sized.send:
        return f"{head} -- below the venue minimum: not sent"
    tail = "market, reduce-only" if sized.leg.kind == "margin" else "market"
    if sized.estimate is not None:
        tail += f", about {sized.estimate:.8f} {sized.quote}, fee about {sized.fee_estimate:.8f} {sized.quote}"
    else:
        tail += ", no reference price read"
    return f"{head} -- {tail}"


def render_plan(plan: Plan, echo: Callable[[str], None]) -> None:
    """What an operator reads before typing the word. Estimates stay in each leg's own quote
    currency and no grand total is printed -- summing a BTC-quoted leg into a euro figure would
    need an FX rate this command has no mandate to invent."""
    echo(f"{plan.n_open_orders} resting order(s) will be cancelled account-wide")
    if not plan.margin:
        echo("no margin position to close")
    for sized in plan.margin:
        echo(_leg_line(sized))
    if not plan.spot:
        echo("no non-EUR spot balance to sell")
    for sized in plan.spot:
        echo(_leg_line(sized))
    for row in plan.unsellable:
        echo(f"  balance {row['code']} {row['free']:.8f} -- neither a EUR nor a BTC pair: it cannot be sold from here")
    for row in plan.unclosable:
        # The row's own `note`, not one hard-coded sentence: two different classes land here (a pair
        # the listing does not carry, a side no closer can be derived from) and printing either as
        # the other tells the operator the wrong thing to go and do on Kraken.
        echo(f"  {row['symbol']} {row['side']} {row['quantity']:.8f} -- {row['note']}: it cannot be closed here")


CONFIRM_PROMPT = f"Type {CONFIRM_WORD} to close every position and sell every non-EUR balance at market, anything else aborts: "


def kill_file_path(state_dir):
    """The engine's own control file, not a second spelling of it -- a kill file the engine does
    not read stops nothing."""
    from cli.engine.execgate import KILL_FILE, exec_dir

    return exec_dir(state_dir) / KILL_FILE


def check_kill_file(state_dir) -> str:
    """Present or refuse. Without it, the engine's next start re-opens what this sweep closes; the
    host wrapper writes it before it stops the unit, so an absent one means the button was invoked
    some other way."""
    path = kill_file_path(state_dir)
    try:
        return path.read_text()
    except OSError as exc:
        raise FlattenRefused(
            f"the kill file {path} is absent or unreadable -- nothing was sent; place it and run this again"
        ) from exc


def terminal_available() -> bool:
    """Whether a controlling terminal exists at all. Checked before any venue read, so a session
    that could never answer the confirm is refused without spending five requests on it."""
    try:
        with open("/dev/tty", "rb"):
            return True
    except OSError:
        return False


def read_confirm(prompt_text: str) -> str:
    """The typed word, read from the controlling terminal and NEVER from stdin: a pipe or a heredoc
    must not be able to press this button (`infra/ansible/scripts/converge.sh`'s rule). There is
    deliberately no flag that skips it -- a red button pressed by a script is a different product.

    The PROMPT goes to the terminal too, never to stdout: the host wrapper captures stdout to a
    log, and a prompt that lands there leaves the operator at a blank screen while the button waits.

    TWO opens, never one `"r+"`: text `"r+"` builds a buffered random-access stream, which requires
    a seekable file, and a tty is not one -- it raises `io.UnsupportedOperation` before a word is
    ever read (measured under `pty.fork()` on cpython 3.14.6).
    """
    with open("/dev/tty", "w") as out:
        out.write(prompt_text)
        out.flush()
    with open("/dev/tty", "r") as tty:
        return (tty.readline() or "").strip()


def matches_confirm(reply: str) -> bool:
    return reply.strip() == CONFIRM_WORD


def check_venue(venue_reader, now):
    """The public unsigned status endpoint the execution gate already uses, with its own 10 s
    timeout. It never raises, so a refusal here is a reading and not an exception."""
    status = venue_reader(now=now)
    if not status.ok:
        raise FlattenUnreachable(f"the venue is not online (it reads {status.status!r}) -- nothing was sent")
    return status
