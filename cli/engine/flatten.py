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
from typing import Any, Callable

from nautilus_trader.model import AccountId, AccountType, ClientOrderId, OrderSide, OrderType, Quantity, TimeInForce

from cli.logging import get_logger

logger = get_logger("engine.flatten")

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
