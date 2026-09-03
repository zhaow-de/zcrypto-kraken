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

The client is ASYNC: every one of the seven methods this module calls schedules onto a running
asyncio loop and answers with an awaitable, and outside a loop each raises `RuntimeError: no
running event loop` before any request leaves. They are compiled, so `inspect.iscoroutinefunction`
is False on all seven and cannot be used to decide anything here -- the shape is measured by
calling. Hence `Recorder.call` awaits, everything reaching it is async, and the one loop is opened
at the CLI boundary (`cli/engine/command.py`'s `flatten`). A branch that awaited only when the
answer happened to be awaitable would let a synchronous fake keep passing, which is the defect that
kept this module unrunnable through ten green tasks -- there is one path.
`test_every_client_call_the_red_button_makes_needs_a_running_loop` pins it against the real class.

MARKET is used deliberately, overriding spec 00090 D6's rejection of it for the probe machine: in
a crash the price is not the variable, time is, and a bounded IOC in a fast market leaves residue
that IS the exposure.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Callable

from nautilus_trader.model import AccountId, AccountType, ClientOrderId, OrderSide, OrderType, Quantity, TimeInForce

from cli.engine.venue import read_system_status
from cli.logging import get_logger

logger = get_logger("engine.flatten")

if TYPE_CHECKING:
    from pathlib import Path

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
# The basket legs Kraken spells two ways, which are exactly the legs `read_open_orders` cannot see
# an order on -- that function states the mechanism and the consequence. Printed beside the flat
# verdict because a zero is what an operator acts on. Frozen text rather than a derivation, with
# `tests/test_engine_flatten.py::test_the_blind_legs_are_the_two_way_spelled_basket_legs`
# recomputing the set from `cli/engine/store.py`'s BASKET so a basket change cannot leave it stale.
BLIND_ORDER_READ_LEGS = ("BTC/EUR", "ETH/EUR", "XRP/EUR", "LTC/EUR", "ETH/BTC")

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

    async def call(self, name: str, params: dict, fn: Callable[[], Any]) -> Any:
        entry: dict = {"call": name, "params": dict(params)}
        self.entries.append(entry)
        try:
            answer = await fn()
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


async def read_open_orders(client: Any, rec: Recorder) -> list[Any]:
    """The orders resting at the venue that the adapter can resolve an instrument for -- NOT every
    order resting at the venue. Only the LIST is load-bearing here -- its length decides the exit
    code -- so no per-row field is required: an unparseable row must not abort a sweep whose whole
    answer is 'something is still working'.

    The gap is spelling-shaped, and it is the adapter's, not this module's. Its instrument cache is
    scanned by `raw_symbol`, which is Kraken's `AssetPairs` KEY (`XXBTZEUR`), while an open order is
    looked up by its own `descr.pair`, which is the ALTNAME (`XBTEUR`); the comparison is raw
    equality with no `else` on a miss, so a row on a leg spelled both ways is dropped and the call
    returns success. `BLIND_ORDER_READ_LEGS` names those legs.

    What that costs is the VERDICT, never the cancel: `sweep`'s `cancel_all_orders` is account-wide,
    names no pair, and reaches an order on a blind leg -- so exit 0 can be a false all-clear while
    the sweep itself did its job, and re-running the command is a real mitigation rather than a
    retry of the same blindness. `run_flatten` prints that caveat beside the flat verdict, and
    `infra/runbooks/engine-procedures.md`'s flatten procedure carries it for the operator.

    Not repaired here: repairing it means priming the adapter's instrument cache with both
    spellings before this read, which is a change to what the button does rather than to what it
    says. `T0160` carries the registration.
    """
    # `account_id` is the constant `_ACCOUNT` is minted from, not a second spelling of it.
    kwargs: dict[str, Any] = {"open_only": True}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = await rec.call(
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


async def read_positions(client: Any, rec: Recorder) -> list[PositionRow]:
    kwargs: dict[str, Any] = {
        "account_type": AccountType.MARGIN,
        "use_spot_position_reports": False,
        "quote_currency": QUOTE_CURRENCY,
    }
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = await rec.call(
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


async def read_balances(client: Any, rec: Recorder) -> list[BalanceRow]:
    kwargs: dict[str, Any] = {"account_type": AccountType.CASH}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        state = await rec.call(
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


async def read_listing(client: Any, rec: Recorder) -> dict[str, Any]:
    """ONE no-argument call for the whole listing. A per-pair request would error on an unknown
    pair and abort the sweep over an unrelated holding; pairlessness is read from this map."""
    try:
        rows = await rec.call("request_instruments", {"pairs": None}, lambda: client.request_instruments())
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


async def read_book_price(client: Any, rec: Recorder, constraints: PairConstraints, side: str) -> float:
    """Best bid for a sell, best ask for a buy. Used for the printed estimate and for the dust
    boundary -- never as an order price, since every order this module sends is MARKET."""
    params = {"instrument_id": str(constraints.instrument_id), "depth": BOOK_DEPTH}
    try:
        book = await rec.call(
            "request_book_snapshot",
            params,
            lambda: client.request_book_snapshot(constraints.instrument_id, depth=BOOK_DEPTH),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"{constraints.symbol}: the book could not be read: {exc}") from exc
    what = f"{constraints.symbol}'s book"
    # `OrderBook.bids`/`.asks` are METHODS on the real type (`nautilus_trader.model.OrderBook`), not
    # sequences. `_required` rejects only `None`, so reading the attribute alone hands back the bound
    # method itself; `list()` of that raises a bare TypeError, which nothing between here and the
    # operator catches -- a traceback where the exit-code contract promises a named unreachable.
    field = "bids" if side == "SELL" else "asks"
    read_side = _required(book, field, what)
    try:
        levels = list(read_side())
    except TypeError as exc:
        raise FlattenUnreachable(f"{what}: {field} is not the callable the venue's book type carries") from exc
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


async def read_snapshot(client: Any, rec: Recorder) -> Snapshot:
    """Orders, then positions, then balances -- in that order, so an order that fills between two
    of the reads lands in one that FOLLOWS rather than falling out of both."""
    return Snapshot(
        orders=await read_open_orders(client, rec),
        positions=await read_positions(client, rec),
        balances=await read_balances(client, rec),
    )


async def build_plan(client: Any, rec: Recorder, snapshot: Snapshot, listing: dict[str, Any]) -> Plan:
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
            prices[symbol] = await read_book_price(client, rec, constraints[symbol], side)
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
    need an FX rate this command has no mandate to invent.

    The order count is a floor, not a total: it comes from `read_open_orders`, which cannot see an
    order on the legs that function names. The count line says so rather than the operator reading
    an understated preview as an inventory."""
    echo(f"{plan.n_open_orders} resting order(s) seen -- the cancel is account-wide and reaches any this read could not see")
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


def kill_file_path(state_dir: Path) -> Path:
    """The engine's own control file, not a second spelling of it -- a kill file the engine does
    not read stops nothing."""
    from cli.engine.execgate import KILL_FILE, exec_dir

    return exec_dir(state_dir) / KILL_FILE


def check_kill_file(state_dir: Path) -> str:
    """Present or refuse. Without it, the engine's next start re-opens what this sweep closes; the
    host wrapper writes it before it stops the unit, so an absent one means the button was invoked
    some other way.

    `UnicodeDecodeError` is caught BESIDE `OSError` and is not a tidy-up to undo: it is a
    `ValueError`, so bytes that are not UTF-8 -- anything but the wrapper's own ASCII line wrote
    this file -- would otherwise travel straight past the refusal and hand the operator a traceback
    where the exit-code contract promises a named exit-1 naming the file to go and fix.
    """
    path = kill_file_path(state_dir)
    try:
        return path.read_text()
    except (OSError, UnicodeDecodeError) as exc:
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


def check_venue(venue_reader, now) -> Any:
    """The public unsigned status endpoint the execution gate already uses, with its own 10 s
    timeout. It never raises, so a refusal here is a reading and not an exception."""
    status = venue_reader(now=now)
    if not status.ok:
        raise FlattenUnreachable(f"the venue is not online (it reads {status.status!r}) -- nothing was sent")
    return status


@dataclass(frozen=True)
class LegOutcome:
    kind: str
    symbol: str
    side: str
    qty: float
    pass_name: str
    source: str
    client_order_id: str | None
    sent: bool
    reason: str | None
    answer: str | None
    error: str | None


@dataclass(frozen=True)
class SweepResult:
    cancel_ok: bool
    cancel_error: str | None
    orders_after_cancel: int | None
    post_write_failure: str | None
    outcomes: list[LegOutcome]
    final: Snapshot | None


def mint_client_order_id(stamp, index: int) -> str:
    """`FLT-<basic ISO-8601 UTC>-<n>`. Inside the id SHAPE Kraken has already accepted from this
    repo, and structurally distinct from the engine's `-001-000-` infix -- an id the executor could
    read as its own would route a flatten fill into the engine's ledger.

    `index` runs over the whole run rather than per pass: the venue refuses an id it has already
    seen, so two legs sharing one would be one leg silently unsent. A leg that is NOT sent still
    advances it, so the numbers an operator reads have gaps -- uniqueness is the property that
    matters here, and closing the gaps would mean reusing a number that has already gone out.

    `stamp` is the run's own and `index` restarts at 1, so two runs beginning inside the same second
    would mint the same ids. Each needs its own word typed at a terminal, and that is the bound --
    the journal's own collision protection does not extend here.
    """
    return f"{CLIENT_ORDER_ID_PREFIX}{stamp:%Y%m%dT%H%M%SZ}-{index}"


# The two sides a `Leg` can carry, and the only two this module can build an order from.
ORDER_SIDES = {"SELL": OrderSide.SELL, "BUY": OrderSide.BUY}


async def submit_leg(client: Any, rec: Recorder, sized: SizedLeg, constraints: PairConstraints, client_order_id: str) -> Any:
    """One MARKET IOC order. The quantity is minted at the precision the venue's own lot step
    implies, so the floored value is exactly representable and nothing is rounded UP past the
    position the report reported.

    Every scoping value is derived ONCE and then both sent and journalled -- `_journalled`'s rule,
    on the one call in this module that moves money. Spelled a second time beside the call, the
    journal an operator reads mid-incident can say MARGIN while CASH went out, or name a side the
    order did not carry.

    The side is LOOKED UP, never defaulted: `margin_legs` and `spot_legs` are the only places a
    `Leg` is built and both write a literal, so a third spelling can only be a defect -- and a
    conditional's else-branch would turn it into a real market order in the opposite direction. This
    module names what it cannot derive rather than guessing it.
    """
    margin = sized.leg.kind == "margin"
    quantity = Quantity(sized.qty, step_precision(constraints.lot_step))
    order_side = ORDER_SIDES[sized.leg.side]
    order_type, time_in_force = OrderType.MARKET, TimeInForce.IOC
    kwargs: dict[str, Any] = {"reduce_only": margin, "account_type": AccountType.MARGIN if margin else AccountType.CASH}
    if margin:
        kwargs["leverage"] = MARGIN_LEVERAGE
    params = {
        "account_id": ACCOUNT_ID,
        "instrument_id": str(constraints.instrument_id),
        "client_order_id": client_order_id,
        "order_side": str(order_side),
        "order_type": str(order_type),
        "quantity": float(quantity),
        "time_in_force": str(time_in_force),
        **_journalled(kwargs),
    }
    return await rec.call(
        "submit_order",
        params,
        lambda: client.submit_order(
            _ACCOUNT,
            constraints.instrument_id,
            ClientOrderId(client_order_id),
            order_side,
            order_type,
            quantity,
            time_in_force,
            **kwargs,
        ),
    )


def _sized_with_constraints(legs: list, listing: dict, plan: Plan) -> list:
    """Each leg paired with the constraints it will be sized and minted at. A pair absent from the
    plan's own map is looked up now; a shape failure there is a post-write failure, never a guess."""
    out = []
    for leg in legs:
        constraints = plan.constraints.get(leg.symbol) or constraints_for(leg.symbol, listing)
        out.append((size_leg(leg, constraints, plan.prices.get(leg.symbol)), constraints))
    return out


async def _send(client, rec, sized: SizedLeg, constraints: PairConstraints, stamp, index: int, pass_name: str) -> LegOutcome:
    """Never raises: a rejection is journaled and the sweep continues, and is never retried.

    `sent` stays True on every failure raised inside the send -- the purely local ones, the minting
    of the quantity and the side lookup, included, since nothing here can tell those apart from a
    request that left and was refused. The request may have reached the venue, and recording it as
    unsent would be the one lie an operator cannot afford here.

    A rejected margin closer this code had ALREADY sized below the pair's `ordermin` is labelled
    `unclosable_below_minimum` (spec 00106 D4): it is what routes an operator to the venue's own
    settle-position action, which a bare `EOrder:` string never does. The label comes from the
    pre-send arithmetic, never from the rejection text -- which Kraken message means "below the
    minimum" is unmeasured here -- so the venue's words are journaled beside it as the leg's
    `error`, and a refusal for a passing reason wears the same label as a refusal about the size.

    One `reason` field carries one label: where such a closer is also unpriced, the label is
    `unclosable_below_minimum` rather than `no_reference_price`. It is the one that names a next
    action, and the price costs a margin leg nothing -- a closer's quantity comes from the position
    report and never from a price.
    """
    base = dict(
        kind=sized.leg.kind,
        symbol=sized.leg.symbol,
        side=sized.leg.side,
        qty=sized.qty,
        pass_name=pass_name,
        source=sized.leg.source,
    )
    if not sized.send:
        return LegOutcome(**base, client_order_id=None, sent=False, reason=sized.reason, answer=None, error=None)
    client_order_id = mint_client_order_id(stamp, index)
    reason = "no_reference_price" if sized.reference_price is None else None
    try:
        answer = await submit_leg(client, rec, sized, constraints, client_order_id)
    except Exception as exc:  # noqa: BLE001 -- one leg's rejection must not end the sweep
        if sized.leg.kind == "margin" and sized.qty < constraints.ordermin:
            reason = "unclosable_below_minimum"
        logger.error("flatten leg %s %s was rejected: %s", sized.leg.symbol, sized.leg.side, exc)
        return LegOutcome(
            **base, client_order_id=client_order_id, sent=True, reason=reason, answer=None, error=f"{type(exc).__name__}: {exc}"
        )
    return LegOutcome(**base, client_order_id=client_order_id, sent=True, reason=reason, answer=repr(answer), error=None)


async def _read_for_the_record(what: str, read: Callable[[], Any]) -> Any:
    """A POST-WRITE read whose answer nothing but the journal consumes: run it, or name the failure
    and step over it.

    The asymmetry with every pre-write read is the whole point. Before the first write an unreadable
    answer must abort -- a shape the venue changed is a finding, and nothing has happened yet. After
    the cancel and the closes have gone out, aborting on a read NOTHING CONSUMES trades a
    journalling nicety for unsold balances: `read_positions` raises on a `None` answer, a live venue
    shape this module documents, and one such answer would otherwise take both spot passes and the
    final snapshot with it. `Recorder` has already written the request and whatever came back -- the
    unreadable answer itself, verbatim, or the transport error -- so the evidence an operator reads
    survives either way; only the abort goes away.

    Never widened to a read something DOES consume. The post-cancel position read that sizes the
    closers must still abort -- degraded, it would size them from an empty list and report the
    account flat.
    """
    try:
        return await read()
    except FlattenUnreachable as exc:
        logger.error("%s could not be read -- it is journaled and the sweep goes on: %s", what, exc)
        return None


async def sweep(client: Any, rec: Recorder, plan: Plan, listing: dict, *, stamp) -> SweepResult:
    """From the account-wide cancel to the final snapshot. Re-runnable: a second run finds less to
    do and does it, so nothing here is one-shot.

    Every read after the cancel whose answer this function CONSUMES is inside the one try: past the
    first write the account may have moved, so a read that fails ends the sweep with a named failure
    rather than with a verdict. The two that feed only the journal go through
    `_read_for_the_record`, which is where that asymmetry is argued.

    The final snapshot is read AFRESH rather than reusing the plan's -- a reused one is a second
    vote from the witness the sweep has just acted on, and it would report flat whatever the writes
    achieved.
    """
    outcomes: list[LegOutcome] = []
    cancel_ok, cancel_error = True, None
    try:
        await rec.call("cancel_all_orders", {}, client.cancel_all_orders)
    except Exception as exc:  # noqa: BLE001 -- the closes do not depend on the cancel
        cancel_ok, cancel_error = False, f"{type(exc).__name__}: {exc}"
        logger.error("the account-wide cancel failed: %s", exc)

    index, orders_after, post_write_failure, final = 0, None, None, None
    try:
        # Journal-only, both of them: `orders_after_cancel` is written into the record and read by
        # no decision -- the exit code judges the FINAL snapshot's orders, never this count.
        rows = await _read_for_the_record("the orders still resting after the cancel", lambda: read_open_orders(client, rec))
        orders_after = len(rows) if rows is not None else None
        margin_now, _ = margin_legs(await read_positions(client, rec), listing)
        for sized, constraints in _sized_with_constraints(margin_now, listing, plan):
            index += 1
            outcomes.append(await _send(client, rec, sized, constraints, stamp, index, "margin"))

        await _read_for_the_record("what the closes left behind", lambda: read_positions(client, rec))
        for pass_name in ("spot-1", "spot-2"):
            legs, _ = spot_legs(await read_balances(client, rec), listing)
            for sized, constraints in _sized_with_constraints(legs, listing, plan):
                index += 1
                outcomes.append(await _send(client, rec, sized, constraints, stamp, index, pass_name))

        final = await read_snapshot(client, rec)
    except FlattenUnreachable as exc:
        post_write_failure = str(exc)
        logger.error("a read after the first write failed: %s", exc)

    return SweepResult(
        cancel_ok=cancel_ok,
        cancel_error=cancel_error,
        orders_after_cancel=orders_after,
        post_write_failure=post_write_failure,
        outcomes=outcomes,
        final=final,
    )


def _utc_now():
    return datetime.now(timezone.utc)


def _snapshot_payload(snapshot: Snapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "open_orders": len(snapshot.orders),
        "positions": [{"symbol": r.symbol, "side": r.side, "quantity": r.quantity} for r in snapshot.positions],
        "balances": [{"code": r.code, "free": r.free} for r in snapshot.balances],
    }


def judge_final(final: Snapshot, listing: dict, prices: dict) -> list[dict]:
    """Everything in the final snapshot that says the account is not flat.

    A balance the listing cannot route, and a pair whose constraints cannot be read here, both
    count as residuals: neither is evidence of flatness, and the safe direction is to say so.

    Only FLAT is skipped, never a whitelist of LONG/SHORT: a side this code could not close from is
    exposure it could not act on, and reading it as flat would report the one row nothing was sent
    for as nothing to do.
    """
    residuals: list[dict] = []
    if final.orders:
        residuals.append({"kind": "order", "count": len(final.orders), "reason": "resting_order"})
    for row in final.positions:
        if row.side == "FLAT":
            continue
        residual = {"kind": "position", "symbol": row.symbol, "side": row.side, "quantity": row.quantity}
        if row.side not in ("LONG", "SHORT"):
            residual["reason"] = "unrecognised_position_side"
        elif row.symbol not in listing:
            # Nothing was sent for it and nothing could be: this is where that reaches the record.
            residual["reason"] = "pair_not_listed"
        else:
            # Every residual row carries a `reason`, including the ordinary one. An absent key is a
            # second row SHAPE in an artifact read mid-incident, where a missing field reads as a
            # different kind of thing rather than as the plain case.
            residual["reason"] = "open_position"
        residuals.append(residual)
    from cli.engine.instruments import EUR_CODES

    bases = listed_bases(listing)
    for row in final.balances:
        if row.code.upper() in EUR_CODES or row.free <= 0.0:
            continue
        base = resolve_base(row.code, bases)
        symbol = choose_pair(base, listing) if base else None
        if symbol is None:
            residuals.append({"kind": "balance", "code": row.code, "free": row.free, "reason": "no_eur_or_btc_pair"})
            continue
        try:
            constraints = constraints_for(symbol, listing)
        except FlattenUnreachable as exc:
            residuals.append({"kind": "balance", "code": row.code, "free": row.free, "reason": f"unjudgeable: {exc}"})
            continue
        if classify_balance(row.free, constraints, prices.get(symbol)) == "residual":
            residuals.append(
                {"kind": "balance", "code": row.code, "free": row.free, "symbol": symbol, "reason": "sellable_balance"}
            )
    return residuals


def exit_code(result: SweepResult, residuals: list) -> int:
    """0 flat, 2 partial. Derived from the final snapshot plus the two write-side failures -- never
    from what an individual leg answered, which the journal carries instead."""
    if result.post_write_failure is not None or not result.cancel_ok or residuals:
        return 2
    return 0


def journal_path(state_dir, stamp) -> Path:
    """ISO-8601 BASIC form: an operator types this path mid-incident, and the extended form's `:`
    and `+` need shell quoting to do it. The body carries the extended timestamp.

    The stamp is converted to UTC before it is formatted, so the `Z` in the name is never a claim
    about a zone the caller happened to be in while `started_at` carried the truth."""
    from cli.engine.execgate import exec_dir

    return exec_dir(state_dir) / f"flatten-{stamp.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.json"


def write_journal(state_dir, stamp, payload: dict) -> Path | None:
    """Its own artifact, never the engine's `exec-<HH>.json` (an unlocked single-writer
    read-modify-write this process must not join). Refuses to overwrite: a second run in the same
    second must not destroy the first one's incident record."""
    base = journal_path(state_dir, stamp)
    for suffix in ("", *(f"-{n}" for n in range(2, 100))):
        candidate = base.with_name(f"{base.stem}{suffix}.json")
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            return candidate
        except FileExistsError:
            continue
        except OSError:
            logger.critical("the flatten journal could not be written to %s -- the record follows", candidate, exc_info=True)
            body = json.dumps(payload, indent=2, sort_keys=True, default=str)
            try:
                print(body)
            except OSError:
                # The condition this fallback exists for is routinely the SAME one that broke the
                # file write: a full filesystem takes the wrapper's captured log with it, and a
                # dead wrapper takes the pipe. `logging` handles a failing handler internally and
                # cannot raise out of here, so it is what goes LAST -- a fallback that dies on the
                # very condition it exists to survive is no fallback.
                logger.critical("...and could not be written to stdout either -- the record is\n%s", body)
            return None
    logger.critical("the flatten journal could not be given a free name under %s", base.parent)
    return None


class _Echo:
    """`echo`, with a stdout that can go away.

    ENOSPC on the wrapper's captured log and EPIPE from a wrapper that died are both incident-day
    conditions, and `run_flatten` promises to raise nothing: an unguarded write turns a completed
    sweep into a traceback carrying Python's own exit 1 -- the code this command defines as
    "refused with nothing sent" -- with no journal to reconstruct from.

    `ok` goes False on the first line that did not land, and the two sides of the first write read
    it differently. BEFORE it, the caller aborts: a plan the operator could not read is a
    confirmation they cannot give, and aborting is free. AFTER it, `ok` is ignored -- nobody is
    reading, the orders have gone out, and the journal is the only thing that survives.
    """

    def __init__(self, echo: Callable[[str], None]) -> None:
        self._echo = echo
        self.ok = True

    def __call__(self, message: str) -> None:
        try:
            self._echo(message)
        except OSError as exc:
            self.ok = False
            logger.error("a line for the operator could not be written (%s): %s", exc, message)


async def run_flatten(
    client: Any,
    *,
    state_dir,
    execute: bool,
    now: Callable[[], Any] = _utc_now,
    venue_reader: Callable[..., Any] = read_system_status,
    tty_available: Callable[[], bool] = terminal_available,
    prompt: Callable[[str], str] = read_confirm,
    echo: Callable[[str], None] = print,
) -> int:
    """The whole button. Returns the process exit code; raises nothing.

    0 flat (or the default dry run completed) · 1 refused with nothing sent · 2 partial:
    the final snapshot is not flat, or a write-side failure means it cannot be called flat ·
    3 the venue could not be reached or read BEFORE the first write, which is the cancel.
    """
    stamp = now()
    say = _Echo(echo)
    rec = Recorder()
    record: dict = {
        "schema_version": 1,
        "mode": "execute" if execute else "dry-run",
        "started_at": stamp.isoformat(),
        "state_dir": str(state_dir),
        "api_key_masked": getattr(client, "api_key_masked", None),
        # Every journal that exists is an execute-mode one -- a dry run writes none (`_dry_exit`) --
        # and there the word is always required, so the pre-prompt value states that the prompt was
        # not reached, never that it was not needed. A refusal artifact denying the gate it just
        # enforced is a question post-incident forensics has to answer before it can start.
        "confirm": "not-reached",
        "kill_file": None,
        "requests": rec.entries,
    }

    def _finish(code: int, *lines: str) -> int:
        """The durable record is attempted BEFORE the human-readable summary, never after: a
        stdout that has gone away reaches nobody, and written first the journal exists whatever the
        terminal does next."""
        record["exit_code"] = code
        record["finished_at"] = now().isoformat()
        path = write_journal(state_dir, stamp, record)
        for line in lines:
            say(line)
        if path is not None:
            say(f"the record of this run is {path}")
        return code

    if execute:
        try:
            record["kill_file"] = check_kill_file(state_dir)
        except FlattenRefused as exc:
            return _finish(1, str(exc))
        if not tty_available():
            return _finish(1, "there is no controlling terminal to read the confirmation from -- nothing was sent")

    try:
        status = check_venue(venue_reader, stamp)
    except FlattenUnreachable as exc:
        record["venue_status"] = {"status": "not-online", "ok": False}
        return _finish(3, str(exc)) if execute else _dry_exit(3, str(exc), say)
    record["venue_status"] = {"status": status.status, "ok": status.ok}

    try:
        snapshot = await read_snapshot(client, rec)
        listing = await read_listing(client, rec)
        plan = await build_plan(client, rec, snapshot, listing)
    except FlattenUnreachable as exc:
        record["error"] = str(exc)
        return _finish(3, str(exc)) if execute else _dry_exit(3, str(exc), say)

    record["snapshot_before"] = _snapshot_payload(snapshot)
    render_plan(plan, say)
    if not say.ok:
        # Pre-write, so aborting is free and correct -- but cleanly: the plan is what the word is
        # typed against, and a dry run's whole product is that plan. Either way nothing was sent.
        record["display_failure"] = "the plan could not be written to the operator's terminal"
        message = "the plan could not be shown -- nothing was sent"
        return _finish(1, message) if execute else _dry_exit(1, message, say)

    if not execute:
        say("nothing was sent: this run reads and prints only")
        return 0

    try:
        reply = prompt(CONFIRM_PROMPT)
    except OSError as exc:
        # `tty_available()` passed a moment ago; between then and here the terminal can still go.
        # This function promises to raise nothing, and a traceback where the refusal contract
        # promises exit 1 leaves the operator with no journal and no code to read.
        record["confirm"] = "unreadable"
        return _finish(1, f"the confirmation could not be read from the terminal -- nothing was sent: {exc}")
    if not matches_confirm(reply):
        record["confirm"] = "mismatch"
        return _finish(1, "the confirmation did not match -- nothing was sent")
    record["confirm"] = "matched"

    result = await sweep(client, rec, plan, listing, stamp=stamp)
    # `result.final`, never `snapshot`: the pre-sweep one is the witness this sweep has just acted
    # on, and judged against it every position the closers cleared reads as a residual while an
    # order that outlived the cancel goes unnamed.
    residuals = judge_final(result.final, listing, plan.prices) if result.final is not None else []
    code = exit_code(result, residuals)
    record["cancel"] = {"ok": result.cancel_ok, "error": result.cancel_error, "orders_after": result.orders_after_cancel}
    record["post_write_failure"] = result.post_write_failure
    record["legs"] = [asdict(outcome) for outcome in result.outcomes]
    record["snapshot_after"] = _snapshot_payload(result.final)
    record["residuals"] = residuals
    # Handed to `_finish` rather than echoed here: past the first write the record must be on disk
    # before a single line is attempted, and a display failure may cost neither it nor the code.
    if code == 0:
        # The caveat rides the ZERO and only the zero: exit 2 already sends the operator back to the
        # venue, while a bare exit 0 is the one answer that ends the incident on a read that cannot
        # see an order on the legs `read_open_orders` names.
        lines = [
            "the account reads flat: no resting order, no open position, no sellable balance left",
            f"  BUT this read cannot see a resting order on {', '.join(BLIND_ORDER_READ_LEGS)}.",
            "  Confirm open orders on Kraken's own page before you treat this as done -- and if one",
            "  is there, run this command again: the account-wide cancel does reach it.",
        ]
    else:
        lines = ["the account does NOT read flat -- what is left:", *(f"  {row}" for row in residuals)]
        if result.post_write_failure:
            lines.append(f"  a read after the cancel failed: {result.post_write_failure}")
        if not result.cancel_ok:
            lines.append(f"  the account-wide cancel failed: {result.cancel_error}")
    return _finish(code, *lines)


def _dry_exit(code: int, message: str, echo: Callable[[str], None]) -> int:
    """A dry run leaves no artifact: it changed nothing, and the terminal is its whole record."""
    echo(message)
    return code
