"""The red button's fake-client suite (spec 00106 D8): every read is parsed by named fields it
requires, and a field the venue stopped sending aborts rather than being guessed through.

The fake records every call in order, so the assertions here are about what actually reached the
venue -- never only about a return value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cli.engine import flatten


@dataclass
class _Level:
    price: float


class _Book:
    def __init__(self, bid: float, ask: float) -> None:
        self.bids = [_Level(bid)]
        self.asks = [_Level(ask)]


class _Instrument:
    """A listing row shaped like the adapter's: every constraint float()-able or None."""

    def __init__(self, symbol: str, *, ordermin=0.0001, lot_step=0.00000001, tick_size=None) -> None:
        self.id = f"{symbol}.KRAKEN"
        self.min_quantity = ordermin
        self.size_increment = lot_step
        # The tick defaults by QUOTE, not to one number: a BTC-quoted pair ticks at seven decimals,
        # and the euro pairs' 0.1 would floor a reference price like 0.03 BTC to zero -- turning a
        # live balance into dust and hiding every routing assertion that depends on it being sold.
        self.price_increment = tick_size if tick_size is not None else (0.0000001 if symbol.endswith("/BTC") else 0.1)
        self.min_notional = None  # this adapter never maps costmin -- cli/engine/venuestate.py


class _Position:
    def __init__(self, symbol: str, side: str, qty: float) -> None:
        self.instrument_id = f"{symbol}.KRAKEN"
        self.position_side = side
        self.quantity = qty


class _Balance:
    def __init__(self, code: str, free: float) -> None:
        self.currency = type("C", (), {"code": code})()
        self.free = free


class _AccountState:
    def __init__(self, balances: list[_Balance]) -> None:
        self.balances = balances


def _norm(value: Any) -> Any:
    """Enum -> its bare member name, everything else untouched. The module hands the client REAL
    nautilus types (`AccountId`, `AccountType`, `OrderSide`, …); the assertions below are about
    which member was chosen, so the fake normalises once here instead of in every test."""
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = str(value)
    return text.rsplit(".", 1)[-1] if "." in text and " " not in text and "/" not in text else text


class FakeClient:
    """Answers from a script and records every call. `raises` maps a method name to an exception
    instance the next call to it will raise."""

    api_key_masked = "kr***xy"
    # The secret itself, distinct from its masked form, so a journal test can assert on the VALUE
    # that would leak rather than on the name of the variable it arrived in.
    api_key = "kNEVER-IN-THE-JOURNAL-0000"

    def __init__(self, *, instruments=None, orders=None, positions=None, balances=None, books=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._instruments = instruments if instruments is not None else []
        self._orders = list(orders or [[]])
        self._positions = list(positions or [[]])
        self._balances = list(balances or [[]])
        self._books = books or {}
        self.raises: dict[str, Exception] = {}
        self.submitted: list[dict] = []

    def _maybe_raise(self, name):
        exc = self.raises.pop(name, None)
        if exc is not None:
            raise exc

    def _next(self, queue):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def request_instruments(self, pairs=None):
        self.calls.append(("request_instruments", {"pairs": pairs}))
        self._maybe_raise("request_instruments")
        return self._instruments

    def _record(self, name, account_id, kw):
        self.calls.append((name, {"account_id": _norm(account_id), **{k: _norm(v) for k, v in kw.items()}}))

    def request_order_status_reports(self, account_id, **kw):
        self._record("request_order_status_reports", account_id, kw)
        self._maybe_raise("request_order_status_reports")
        return self._next(self._orders)

    def request_position_status_reports(self, account_id, **kw):
        self._record("request_position_status_reports", account_id, kw)
        self._maybe_raise("request_position_status_reports")
        return self._next(self._positions)

    def request_account_state(self, account_id, **kw):
        self._record("request_account_state", account_id, kw)
        self._maybe_raise("request_account_state")
        return _AccountState(self._next(self._balances))

    def request_book_snapshot(self, instrument_id, depth=None):
        self.calls.append(("request_book_snapshot", {"instrument_id": str(instrument_id), "depth": depth}))
        self._maybe_raise("request_book_snapshot")
        return self._books[str(instrument_id)]

    def cancel_all_orders(self):
        self.calls.append(("cancel_all_orders", {}))
        self._maybe_raise("cancel_all_orders")
        return {"ok": True}

    def submit_order(self, account_id, instrument_id, client_order_id, order_side, order_type, quantity, time_in_force, **kw):
        params = {
            "instrument_id": str(instrument_id),
            "client_order_id": str(client_order_id),
            "order_side": _norm(order_side),
            "order_type": _norm(order_type),
            "quantity": float(quantity),
            "time_in_force": _norm(time_in_force),
            **{k: _norm(v) for k, v in kw.items()},
        }
        self.calls.append(("submit_order", params))
        self.submitted.append(params)
        self._maybe_raise("submit_order")
        return {"ok": True}


def names(client: FakeClient) -> list[str]:
    return [name for name, _ in client.calls]


# --- the read layer -----------------------------------------------------------------------------


def test_the_listing_is_keyed_by_symbol_and_a_missing_constraint_aborts_the_pair():
    """`constraints_for` requires ordermin, lot_step and tick_size on the pair it is asked for --
    and only on that pair: an unrelated listing row missing one must not abort the whole sweep."""
    listing_rows = [_Instrument("BTC/EUR"), _Instrument("ADA/EUR")]
    listing_rows[1].size_increment = None
    client = FakeClient(instruments=listing_rows)
    rec = flatten.Recorder()

    listing = flatten.read_listing(client, rec)
    assert set(listing) == {"BTC/EUR", "ADA/EUR"}

    good = flatten.constraints_for("BTC/EUR", listing)
    assert (good.ordermin, good.lot_step, good.tick_size) == (0.0001, 0.00000001, 0.1)

    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.constraints_for("ADA/EUR", listing)
    # The venue's own field name: an absent field is caught by `_required`, which never sees the
    # friendly label `_as_float` would have used.
    assert "size_increment" in str(exc.value)


@pytest.mark.parametrize("field", ["size_increment", "price_increment"])
def test_a_zero_quantization_step_aborts_rather_than_dividing_by_it(field):
    """A step of zero passes an is-it-absent check and then divides. `_floor_to_step` raises a bare
    ValueError on it, which nothing between here and the operator catches -- so the exit-code
    contract would arrive as a traceback with no journal."""
    rows = [_Instrument("BTC/EUR")]
    setattr(rows[0], field, 0.0)
    client = FakeClient(instruments=rows)
    rec = flatten.Recorder()
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    assert "positive step" in str(exc.value)


def test_an_empty_listing_aborts():
    """An empty listing is not an account with nothing to sell -- it is a read that told us
    nothing, and every pair lookup after it would silently answer 'no pair'."""
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_listing(FakeClient(instruments=[]), flatten.Recorder())


def test_positions_are_read_by_named_fields_and_a_missing_one_aborts():
    """`position_side` and `quantity` are the two fields a close is built from; a row missing
    either is a shape this process may not reason about."""
    rows = [_Position("BTC/EUR", "LONG", 0.5), _Position("ETH/EUR", "FLAT", 0.0)]
    read = flatten.read_positions(FakeClient(positions=[rows]), flatten.Recorder())
    assert [(r.symbol, r.side, r.quantity) for r in read] == [("BTC/EUR", "LONG", 0.5), ("ETH/EUR", "FLAT", 0.0)]

    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.position_side
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.read_positions(FakeClient(positions=[[broken]]), flatten.Recorder())
    assert "position_side" in str(exc.value)


def test_the_position_read_is_scoped_to_margin_with_spot_reports_off():
    """The three parameters that scope this read are asserted rather than assumed: MARGIN, spot
    position reports off, and the euro quote. Whether they actually keep a spot holding out of the
    report is a live property no fake can show; spec 00106 D8.2's read-only dry-run establishes
    that, and until it runs the parameters are all that is pinned here."""
    client = FakeClient(positions=[[]])
    flatten.read_positions(client, flatten.Recorder())
    _, params = client.calls[0]
    assert params["account_type"] == "MARGIN"
    assert params["use_spot_position_reports"] is False
    assert params["quote_currency"] == flatten.QUOTE_CURRENCY


def test_balances_are_read_from_the_cash_account():
    """Under MARGIN the account reports one EUR figure, not per-asset balances (the same record,
    observation 2), so the spot enumeration reads CASH."""
    client = FakeClient(balances=[[_Balance("XXBT", 0.5), _Balance("ZEUR", 100.0)]])
    read = flatten.read_balances(client, flatten.Recorder())
    assert [(r.code, r.free) for r in read] == [("XXBT", 0.5), ("ZEUR", 100.0)]
    assert client.calls[0][1]["account_type"] == "CASH"


def test_the_open_order_read_asks_for_open_only():
    client = FakeClient(orders=[[]])
    flatten.read_open_orders(client, flatten.Recorder())
    assert client.calls[0][1]["open_only"] is True


def test_the_book_read_takes_the_bid_for_a_sell_and_the_ask_for_a_buy():
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": _Book(bid=60000.0, ask=60010.0)})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    assert flatten.read_book_price(client, rec, constraints, "SELL") == 60000.0
    assert flatten.read_book_price(client, rec, constraints, "BUY") == 60010.0
    assert client.calls[-1][1]["depth"] == flatten.BOOK_DEPTH


def test_an_empty_book_side_aborts_rather_than_guessing_a_price():
    """A price is what sizes the dust boundary; an absent one must not be defaulted."""
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    book = _Book(bid=60000.0, ask=60010.0)
    book.bids = []
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": book})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_book_price(client, rec, constraints, "SELL")


def test_a_non_positive_book_price_aborts_the_read_rather_than_pricing_a_leg_at_nothing():
    """Zero passes every is-it-absent check and then makes every notional read as nothing: below
    every `costmin`, so each basket leg would be listed as dust and not sent, and the one predicate
    judging the final snapshot would agree the account is flat with the whole spot book still held.
    The other side of the same book is the true negative -- a check refusing every price fails it."""
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    book = _Book(bid=60000.0, ask=60010.0)
    book.bids = [_Level(0.0)]
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": book})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_book_price(client, rec, constraints, "SELL")
    assert flatten.read_book_price(client, rec, constraints, "BUY") == 60010.0


def test_the_recorder_keeps_every_call_with_its_parameters_and_answer():
    """The journal's whole value is that it says what was asked and what came back; a recorder
    that drops the answer leaves an operator with a list of intentions."""
    client = FakeClient(orders=[[]])
    rec = flatten.Recorder()
    flatten.read_open_orders(client, rec)
    assert rec.entries[0]["call"] == "request_order_status_reports"
    assert rec.entries[0]["params"]["open_only"] is True
    assert "answer" in rec.entries[0]


def test_a_raising_read_is_recorded_with_its_error_and_re_raised():
    client = FakeClient(orders=[[]])
    client.raises["request_order_status_reports"] = RuntimeError("connection reset")
    rec = flatten.Recorder()
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_open_orders(client, rec)
    assert "connection reset" in rec.entries[0]["error"]


def test_the_account_id_matches_the_engine_node():
    """One account, one id. A drift here sends every read at an account the engine does not
    trade."""
    from cli.engine import node

    assert flatten.ACCOUNT_ID == node._ACCOUNT_ID


def test_step_precision_matches_the_lot_step_s_own_decimal_places():
    """The docstring's worked examples, asserted: a coarse EUR-quoted step and a fine BTC-quoted
    one, so a minted `Quantity` is exact at either end of the basket."""
    assert flatten.step_precision(0.1) == 1
    assert flatten.step_precision(0.00000001) == 8


def test_a_huge_answer_is_truncated_in_the_journal_and_says_that_it_was():
    """`request_instruments()` alone answers with ~1600 rows, and every answer's `repr` goes into
    one JSON string field. The cap keeps the incident artifact openable; the suffix is what stops a
    reader mistaking a truncated repr for the venue's whole answer."""
    rec = flatten.Recorder()
    rec.call("request_instruments", {"pairs": None}, lambda: "x" * (flatten._ANSWER_REPR_LIMIT * 2))
    answer = rec.entries[0]["answer"]
    assert len(answer) < flatten._ANSWER_REPR_LIMIT * 2
    assert answer.endswith("chars total]")
