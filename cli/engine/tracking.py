"""The realized half of the weekly tracking comparison: what the ledger says actually happened.

Pure. Reads a journal already on disk and returns numbers; writes nothing, reaches no venue. The
refusals are the point -- a tracking number nobody can stand behind is worse than none, because it
will be read as a gate input.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from cli.engine.errors import EngineError
from cli.engine.instruments import EUR_CODES
from cli.engine.store import BASKET
from cli.logging import get_logger

logger = get_logger("engine.tracking")

# The venue's own names, as `executor._liquidity` writes them. NOT lowercased: matching a casing
# the ledger never writes would abort every real fill while every fixture passed.
_PRICEABLE_LIQUIDITY = frozenset({"MAKER", "TAKER"})
_VENUE_LIQUIDITY = _PRICEABLE_LIQUIDITY | {"NO_LIQUIDITY_SIDE"}
_SIDES = frozenset({"buy", "sell"})
# The MODEL's universe is the ten EUR legs (cycle._MODEL_SYMBOLS). The two /BTC legs are real
# basket symbols with no model target, so they map to base None: excluded from drift, counted.
_BASE_BY_SYMBOL = {s: (s.split("/")[0] if s.endswith("/EUR") else None) for s in BASKET}


class Fill(NamedTuple):
    boundary: datetime  # the cycle whose decision produced it -- NOT the wall clock
    at: datetime
    base: str | None  # None for the /BTC legs, which carry no model target
    side: str
    qty: float
    px: float | None  # None for a venue repair, which has no price by construction
    fee: float | None  # None when not euro-denominated or the side is unpriceable
    liquidity: str
    trade_id: str


def extract_fills(records: list[dict]) -> tuple[list[Fill], list[str]]:
    """Every journaled fill, in ledger order, plus the notes that disabled part of the report."""
    out: list[Fill] = []
    notes: list[str] = []

    def note(text: str) -> None:
        if text not in notes:
            notes.append(text)
            logger.warning("%s", text)

    for rec in records:
        boundary = datetime.fromisoformat(rec["cycle_ts"])
        for row in rec.get("submitted", []):
            intent = row.get("intent") or {}
            symbol = intent.get("symbol")
            if symbol not in _BASE_BY_SYMBOL:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} names symbol {symbol!r}, "
                    "which is not in the basket -- refusing to attribute its fills"
                )
            side = intent.get("side")
            if side not in _SIDES:
                raise EngineError(
                    f"submitted row {row.get('client_order_id')!r} carries side {side!r}, not one "
                    f"of {sorted(_SIDES)} -- an unsigned quantity would book a sell as a buy"
                )
            base = _BASE_BY_SYMBOL[symbol]
            if base is None:
                note(f"{symbol} has no model target and is excluded from the drift half")
            for ev in row.get("events", []):
                kind = ev.get("event")
                if kind == "reconciled":
                    # An adopted order that filled at the venue while this process was down.
                    # `_reconcile_adopted_rows` credits the delta to the row's `filled_qty`, and it
                    # is the ONLY non-fill event that moves it (every other journaled event is a
                    # `{"type": ...}` payload written with `add_filled_qty=0.0`), so skipping it
                    # would make `held` under-report by exactly the repaired amount after every
                    # adopted-order repair.
                    #
                    # It becomes a Fill rather than a note, because `held` is base units only: the
                    # quantity is the whole of what the drift half needs, and a note announcing that
                    # the number is wrong is worse than the right number. No price and no fee exist
                    # by construction, so `px`/`fee` are None and it stays out of the cost blend --
                    # which is the same judgment the executor makes when it keeps a repair off the
                    # fill/fee counters.
                    #
                    # The row's own side signs it, exactly like a fill: `filled_qty` is a magnitude,
                    # so a positive delta means more filled in the ORDER's direction.
                    qty = float(ev["qty"])
                    client_order_id = row.get("client_order_id")
                    note(
                        f"{symbol} carries a venue repair of {qty:.10g} base units on "
                        f"{client_order_id} -- counted in the drift half, with no price"
                    )
                    out.append(
                        Fill(
                            boundary,
                            datetime.fromisoformat(ev["at"]),
                            base,
                            side,
                            qty,
                            None,
                            None,
                            "NO_LIQUIDITY_SIDE",
                            # A repair carries no venue trade id. This one is unique (a row is
                            # reconciled at most once per timestamp) and unmistakable for a venue
                            # id, which matters because the ledger match is keyed on `trade_id`.
                            f"reconciled:{client_order_id}:{ev['at']}",
                        )
                    )
                    continue
                if kind != "fill":
                    continue
                liq = ev.get("liquidity")
                if liq not in _VENUE_LIQUIDITY:
                    raise EngineError(
                        f"fill on {row.get('client_order_id')!r} carries liquidity={liq!r}, which "
                        "is not a name the venue's enum yields -- refusing to blend an unlabelled side"
                    )
                cur = ev.get("fee_currency")
                fee: float | None = float(ev["fee"])
                if cur not in EUR_CODES:
                    fee = None
                    note(f"fee on {symbol} is denominated in {cur}, not euro -- excluded from the cost blend")
                if liq not in _PRICEABLE_LIQUIDITY:
                    fee = None
                    note(f"a fill on {symbol} carries {liq} -- counted, but excluded from the cost blend")
                out.append(
                    Fill(
                        boundary,
                        datetime.fromisoformat(ev["at"]),
                        base,
                        side,
                        float(ev["qty"]),
                        float(ev["px"]),
                        fee,
                        liq,
                        str(ev["trade_id"]),
                    )
                )
    return out, notes
