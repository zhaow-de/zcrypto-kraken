"""The red button's fake-client suite (spec 00106 D8): every read is parsed by named fields it
requires, and a field the venue stopped sending aborts rather than being guessed through.

The fake records every call in order, so the assertions here are about what actually reached the
venue -- never only about a return value."""

from __future__ import annotations

import json
import logging
import os
import pty
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import typer
from typer.testing import CliRunner

from cli.__main__ import app
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
        # The same calls again, unnormalised: the objects production actually handed over, so the
        # types and the keyword NAMES can be checked against the real client. `submitted` is
        # `_norm`'d, and `_norm` reduces a plain `"MARKET"` to the text a real `OrderType.MARKET`
        # gives -- it cannot tell the two apart, and only one of them reaches the venue.
        self.submitted_raw: list[tuple[tuple, dict]] = []

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
        self.submitted_raw.append(
            ((account_id, instrument_id, client_order_id, order_side, order_type, quantity, time_in_force), dict(kw))
        )
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


def test_a_position_read_that_answers_nothing_aborts_rather_than_reading_as_flat():
    """`None` is not an account with no positions, and read as `[]` it is the one shape that
    confirms itself: the plan shows no margin leg, the operator confirms, the cancel and the spot
    sells run, and then `judge_final` re-reads through this same function, finds no residual and
    reports the account flat at exit 0 with leveraged positions still open.

    The fake's answer script is a queue of whole answers, so `None` is scriptable with no special
    case -- the `[[]]` default applies only when no script is given and cannot mask this."""
    client = FakeClient(positions=[None])
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.read_positions(client, flatten.Recorder())
    assert "answered nothing" in str(exc.value)
    # The read went out and its answer is what was refused -- not a refusal before reaching the venue.
    assert names(client) == ["request_position_status_reports"]


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


# --- leg enumeration ----------------------------------------------------------------------------


def _listing(*symbols: str) -> dict[str, Any]:
    return {s: _Instrument(s) for s in symbols}


def test_a_long_row_becomes_a_sell_and_a_short_row_a_buy():
    """The side comes from `position_side` and never from a sign: PositionStatusReport carries an
    UNSIGNED quantity, so a sign-derived side would close in the wrong direction on a short."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "LONG", 0.5),
            flatten.PositionRow("ETH/EUR", "ETH/EUR.KRAKEN", "SHORT", 2.0),
        ],
        _listing("BTC/EUR", "ETH/EUR"),
    )
    assert unclosable == []
    assert [(leg.symbol, leg.side, leg.quantity) for leg in legs] == [("BTC/EUR", "SELL", 0.5), ("ETH/EUR", "BUY", 2.0)]
    assert all(leg.account_type == "MARGIN" and leg.kind == "margin" for leg in legs)


def test_a_flat_row_is_not_a_leg():
    rows = [flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "FLAT", 0.0)]
    assert flatten.margin_legs(rows, _listing("BTC/EUR")) == ([], [])


def test_an_unrecognised_position_side_is_named_and_never_read_as_flat_or_aborted_on():
    """Two failures at once are refused here. Reading an unknown side as 'nothing to do' would call
    an open position flat; RAISING on it would abort the sweep before the cancel, costing every
    other leg. The installed build's `PositionSide` carries a fourth member, `NO_POSITION_SIDE`,
    and which members the Kraken adapter emits is unmeasured -- so the row is named and the rest of
    the account is still flattened."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "NO_POSITION_SIDE", 1.0),
            flatten.PositionRow("ETH/EUR", "ETH/EUR.KRAKEN", "SHORT", 2.0),
        ],
        _listing("BTC/EUR", "ETH/EUR"),
    )
    assert [leg.symbol for leg in legs] == ["ETH/EUR"]
    assert unclosable == [
        {
            "symbol": "BTC/EUR",
            "side": "NO_POSITION_SIDE",
            "quantity": 1.0,
            "reason": "unrecognised_position_side",
            "note": "the venue answered a side this command cannot derive a close from",
        }
    ]


def test_a_margin_row_on_a_pair_the_listing_does_not_carry_is_named_and_never_aborts():
    """The pairless class the whole button turns on: aborting one row among many would cancel
    nothing, close nothing and sell nothing, leaving the operator the entire account by hand."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("GONE/EUR", "GONE/EUR.KRAKEN", "LONG", 1.0),
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "SHORT", 0.5),
        ],
        _listing("BTC/EUR"),
    )
    assert [leg.symbol for leg in legs] == ["BTC/EUR"]
    assert unclosable == [
        {
            "symbol": "GONE/EUR",
            "side": "LONG",
            "quantity": 1.0,
            "reason": "pair_not_listed",
            "note": "the listing carries no such pair, so nothing can be sized against it",
        }
    ]


def test_euro_balances_in_either_spelling_are_not_legs():
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("EUR", 100.0), flatten.BalanceRow("ZEUR", 50.0)], _listing("BTC/EUR"))
    assert legs == [] and unsellable == []


def test_a_zero_or_negative_balance_is_not_a_leg():
    legs, unsellable = flatten.spot_legs(
        [flatten.BalanceRow("ADA", 0.0), flatten.BalanceRow("DOT", -1.0)], _listing("ADA/EUR", "DOT/EUR")
    )
    assert legs == [] and unsellable == []


def test_a_classic_asset_code_resolves_through_the_listing_not_through_string_surgery():
    """`XXBT` is the venue's classic spelling of BTC; a sweep that failed to resolve it would leave
    a real BTC balance unsold and call the account flat."""
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("XXBT", 0.5)], _listing("BTC/EUR"))
    assert unsellable == []
    assert [(leg.base, leg.symbol, leg.side) for leg in legs] == [("BTC", "BTC/EUR", "SELL")]


def test_an_x_prefixed_code_resolves_by_stripping_one_prefix_when_the_listing_lists_it():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("XXRP", 100.0)], _listing("XRP/EUR"))
    assert [leg.symbol for leg in legs] == ["XRP/EUR"]


def test_the_eur_pair_wins_over_the_btc_pair():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("ETH", 2.0)], _listing("ETH/EUR", "ETH/BTC"))
    assert [leg.symbol for leg in legs] == ["ETH/EUR"]


def test_an_asset_with_only_a_btc_pair_sells_against_btc():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("ETH", 2.0)], _listing("ETH/BTC"))
    assert [leg.symbol for leg in legs] == ["ETH/BTC"]


def test_an_asset_with_neither_pair_is_unsellable_and_never_silently_dropped():
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("WEIRD", 3.0)], _listing("BTC/EUR"))
    assert legs == []
    assert unsellable == [
        {"base": "WEIRD", "code": "WEIRD", "free": 3.0, "reason": "no_eur_or_btc_pair", "note": "no listed base matched the code"}
    ]


def test_an_unresolvable_code_is_reported_in_the_same_class_never_ignored():
    """A code the listing cannot map is not evidence of nothing held -- it is a balance this
    process could not route, and it reads as a residual exactly like a pairless one."""
    _, unsellable = flatten.spot_legs([flatten.BalanceRow("ZZZQ", 1.0)], _listing("BTC/EUR"))
    assert [u["reason"] for u in unsellable] == ["no_eur_or_btc_pair"]
    assert "ZZZQ" in unsellable[0]["code"]


def test_a_base_listed_only_against_a_third_quote_is_a_residual_not_a_leg():
    """The listing knows the base, so `resolve_base` answers -- and `choose_pair` still finds no
    route, because this command sells into EUR or BTC and nothing else. Read as a leg it would be
    sized against a pair that does not exist; dropped silently it would leave the operator holding
    it with the run reporting flat."""
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("ADA", 5.0)], _listing("ADA/USD"))
    assert legs == []
    assert [(u["base"], u["code"], u["free"], u["reason"]) for u in unsellable] == [("ADA", "ADA", 5.0, "no_eur_or_btc_pair")]
    assert unsellable[0]["note"] != "no listed base matched the code"


# --- sizing and the dust class ------------------------------------------------------------------

_ADA = flatten.PairConstraints("ADA/EUR", "ADA/EUR.KRAKEN", ordermin=15.0, lot_step=0.00000001, tick_size=0.000001)
_BTC = flatten.PairConstraints("BTC/EUR", "BTC/EUR.KRAKEN", ordermin=0.0001, lot_step=0.00000001, tick_size=0.1)
_ETHBTC = flatten.PairConstraints("ETH/BTC", "ETH/BTC.KRAKEN", ordermin=0.004, lot_step=0.00001, tick_size=0.0000001)
_UNLISTED = flatten.PairConstraints("WEIRD/EUR", "WEIRD/EUR.KRAKEN", ordermin=1.0, lot_step=0.001, tick_size=0.001)


def test_costmin_comes_from_the_committed_constant_and_only_when_the_quote_matches(monkeypatch):
    """The adapter never maps costmin onto min_notional, so it is committed per symbol and
    quote-explicit; comparing a BTC-quoted floor against a EUR notional would pass everything.

    The mismatch is CONSTRUCTED here rather than found: every quote-matching entry would pass under
    a `costmin_for` that dropped the check, so the last two lines are the only ones that read it."""
    from cli.engine import instruments

    assert flatten.costmin_for("ADA/EUR") == 0.45
    assert flatten.costmin_for("ETH/BTC") == 2e-05
    assert flatten.costmin_for("WEIRD/EUR") is None

    monkeypatch.setitem(instruments.COSTMIN, "ADA/EUR", (0.45, "BTC"))
    assert flatten.costmin_for("ADA/EUR") is None


def test_a_balance_below_ordermin_is_dust_and_one_above_every_floor_is_a_residual():
    assert flatten.classify_balance(10.0, _ADA, 0.40) == "dust"
    assert flatten.classify_balance(1200.0, _ADA, 0.40) == "residual"
    assert flatten.classify_balance(0.0, _ADA, 0.40) == "flat"


def test_a_balance_over_ordermin_but_under_costmin_is_still_dust():
    """Both floors apply; clearing one is not clearing them. 16 ADA at 0.02 EUR is 0.32 EUR, under
    the 0.45 EUR costmin."""
    assert flatten.classify_balance(16.0, _ADA, 0.02) == "dust"


def test_a_btc_quoted_costmin_is_applied_in_its_own_denomination():
    """The BTC-denominated floor has to BITE somewhere, or `costmin_for` returning it proves only
    that a lookup works. 0.005 ETH at 0.003 BTC is 1.5e-05 BTC, under the 2e-05 BTC costmin, while
    clearing the 0.004 ETH ordermin -- so only the notional floor can produce this verdict."""
    assert flatten.classify_balance(0.005, _ETHBTC, 0.003) == "dust"
    assert flatten.classify_balance(0.05, _ETHBTC, 0.003) == "residual"


def test_a_pair_with_no_committed_costmin_is_judged_on_ordermin_alone():
    assert flatten.classify_balance(2.0, _UNLISTED, 0.01) == "residual"


def test_a_balance_with_no_reference_price_is_judged_on_ordermin_alone():
    """No post-write book read ever happens, so a leg that surfaces only in a later pass has no
    price; judging it on ordermin alone is what keeps it from being skipped as dust unmeasured."""
    assert flatten.classify_balance(1200.0, _ADA, None) == "residual"
    assert flatten.classify_balance(10.0, _ADA, None) == "dust"


def test_a_quantity_that_clears_ordermin_only_before_flooring_is_dust():
    """The floors run on the POST-floor quantity -- the venue would reject an order sized on the
    pre-floor one. `ordermin` sits strictly BETWEEN 1.9 and its floored value 1.0, so an
    implementation checking the pre-floor quantity reads `residual` where this reads `dust`; 2.9,
    which floors to 2.0, is the true negative that keeps the fixture from refusing everything."""
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=1.5, lot_step=1.0, tick_size=0.01)
    assert flatten.classify_balance(1.9, coarse, 100.0) == "dust"
    assert flatten.classify_balance(2.9, coarse, 100.0) == "residual"


def test_a_spot_leg_below_a_floor_is_listed_and_not_sent():
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 10.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ADA, 0.40)
    assert sized.send is False
    assert sized.reason == "dust_below_venue_minimum"
    assert sized.qty == 10.0


def test_a_spot_leg_above_every_floor_is_sent_with_its_estimate_in_its_own_quote():
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 1200.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ADA, 0.40)
    assert sized.send is True and sized.reason is None
    assert sized.qty == 1200.0
    assert sized.quote == "EUR"
    assert sized.estimate == pytest.approx(480.0)
    assert sized.fee_estimate == pytest.approx(480.0 * flatten.TAKER_RATE)


def test_a_btc_quoted_leg_estimates_in_btc_and_never_in_euros():
    """No FX rate is invented; a BTC-quoted estimate stays BTC-quoted."""
    leg = flatten.Leg("spot", "ETH", "ETH/BTC", "SELL", 2.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ETHBTC, 0.03)
    assert sized.quote == "BTC"
    assert sized.estimate == pytest.approx(0.06)


def test_an_unpriced_leg_is_sized_and_sent_with_no_estimate_invented():
    """`plan.prices` carries no entry for a leg whose book read was refused, and `size_leg` is
    still called on it. Nothing may crash on the missing price and nothing may print a number
    standing in for it -- an estimate of 0.0 reads to an operator as a leg worth nothing.

    Both kinds run: the spot path reaches `classify_balance` with no price, the margin path skips
    it, and only the spot one could be silently downgraded to dust by an invented zero notional."""
    spot = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 1200.0, "CASH", "account_state.free")
    sized = flatten.size_leg(spot, _ADA, None)
    assert sized.send is True and sized.reason is None
    assert sized.qty == 1200.0
    assert sized.reference_price is None
    assert sized.estimate is None
    assert sized.fee_estimate is None

    margin = flatten.Leg("margin", "BTC", "BTC/EUR", "SELL", 0.5, "MARGIN", "position_status_report.quantity")
    closer = flatten.size_leg(margin, _BTC, None)
    assert closer.send is True and closer.reason is None
    assert closer.estimate is None


def test_a_margin_leg_is_never_dust_and_is_sent_below_every_floor():
    """The engine's own machine deliberately produces sub-ordermin remainders, and a remainder left
    open is exposure -- so the closer is sent and the venue rules on it."""
    leg = flatten.Leg("margin", "BTC", "BTC/EUR", "SELL", 0.00001, "MARGIN", "position_status_report.quantity")
    sized = flatten.size_leg(leg, _BTC, 60000.0)
    assert sized.send is True and sized.reason is None
    assert sized.qty == 0.00001


def test_a_margin_quantity_that_floors_to_zero_is_unclosable_here_and_named_as_such():
    """There is no order to send; the row stays in the final snapshot, and only the venue's own UI
    settle-position can clear it."""
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=1.0, lot_step=1.0, tick_size=0.01)
    leg = flatten.Leg("margin", "X", "X/EUR", "SELL", 0.4, "MARGIN", "position_status_report.quantity")
    sized = flatten.size_leg(leg, coarse, 100.0)
    assert sized.send is False
    assert sized.reason == "unclosable_below_minimum"


def test_a_margin_leg_quantity_never_exceeds_the_report_s_own():
    """Flooring may only reduce. A closer larger than the position would open the other way."""
    leg = flatten.Leg("margin", "X", "X/EUR", "SELL", 1.999, "MARGIN", "position_status_report.quantity")
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=0.5, lot_step=0.5, tick_size=0.01)
    sized = flatten.size_leg(leg, coarse, 100.0)
    assert sized.qty == 1.5
    assert sized.qty <= leg.quantity


def test_the_send_decision_and_the_residual_verdict_cannot_disagree():
    """One predicate serves both, so a balance skipped as dust can never be reported as a residual
    -- the contradiction that would tell an operator the account is both flat and not."""
    for free in (0.0, 5.0, 14.999, 15.0, 1200.0):
        leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", free, "CASH", "account_state.free")
        sized = flatten.size_leg(leg, _ADA, 0.40)
        assert sized.send is (flatten.classify_balance(free, _ADA, 0.40) == "residual")


def test_the_estimate_is_computed_at_the_tick_floored_price_never_the_raw_book_one():
    """A book price is floored to the tick before anything reads it, so the printed estimate cannot
    contradict the verdict printed beside it. 10 units at a raw 0.049 EUR is 0.49 EUR -- ABOVE the
    0.45 EUR costmin -- while the tick-floored 0.04 makes it 0.40, which is what the dust verdict is
    computed from. Printed raw, the operator reads `dust_below_venue_minimum` next to a notional
    over the minimum it names."""
    coarse_tick = flatten.PairConstraints("ADA/EUR", "ADA/EUR.KRAKEN", ordermin=1.0, lot_step=1.0, tick_size=0.01)
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 10.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, coarse_tick, 0.049)
    assert sized.reference_price == 0.04
    assert sized.estimate == pytest.approx(0.40)
    assert sized.reason == "dust_below_venue_minimum"
    assert sized.estimate < flatten.costmin_for("ADA/EUR")


def test_a_spot_quantity_is_floored_to_the_lot_step_before_it_is_sent():
    """The order quantity is the floored one on the spot path too, not only the margin one: a free
    balance carries more precision than the venue accepts, and flooring may only reduce it."""
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 1200.123456789, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ADA, 0.40)
    assert sized.send is True
    assert sized.qty == 1200.12345678
    assert sized.qty < leg.quantity


def test_the_estimate_is_the_floored_quantity_s_notional_never_the_balance_s():
    """The other axis of the same contradiction: an estimate multiplied out of the raw balance sits
    beside a verdict computed from the floored one. 1.9 units floor to 1.0, so 0.40 EUR is the
    notional the refusal names -- printed off 1.9 it reads 0.76, above the 0.45 costmin the same
    line refuses the leg for.

    The lot step is coarse deliberately: at a 1e-8 step the two products differ by less than
    `pytest.approx`'s default tolerance, and the assertion below would not discriminate.
    """
    coarse = flatten.PairConstraints("ADA/EUR", "ADA/EUR.KRAKEN", ordermin=1.0, lot_step=1.0, tick_size=0.01)
    spot = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 1.9, "CASH", "account_state.free")
    sized = flatten.size_leg(spot, coarse, 0.40)
    assert sized.qty == 1.0
    assert sized.estimate == pytest.approx(0.40)
    assert sized.reason == "dust_below_venue_minimum"
    assert sized.estimate < flatten.costmin_for("ADA/EUR")

    # The closer prints the same line, and a margin leg is sent -- so its inflated form would be
    # read as the value actually going to market.
    margin = flatten.Leg("margin", "ADA", "ADA/EUR", "SELL", 1.9, "MARGIN", "position_status_report.quantity")
    closer = flatten.size_leg(margin, coarse, 0.40)
    assert closer.send is True
    assert closer.estimate == pytest.approx(0.40)
    assert closer.fee_estimate == pytest.approx(0.40 * flatten.TAKER_RATE)


def test_a_price_the_tick_floor_leaves_at_nothing_degrades_to_unpriced_and_is_sold():
    """A price paired with another pair's tick floors to 0.0, every notional then reads as nothing,
    and half a bitcoin is judged dust -- with `judge_final` reading the same predicate at the same
    price and agreeing the account is flat. A live book price is a multiple of its own pair's tick,
    so only a mis-keyed pairing reaches this; the degradation is where the two cannot disagree.

    Unpriced is the direction that SELLS, which is the same direction `read_book_price` takes when
    it refuses a zero one step earlier."""
    assert flatten.classify_balance(0.5, _BTC, 0.03) == "residual"

    leg = flatten.Leg("spot", "BTC", "BTC/EUR", "SELL", 0.5, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _BTC, 0.03)
    assert sized.send is True and sized.reason is None
    assert sized.reference_price is None
    assert sized.estimate is None
    assert sized.send is (flatten.classify_balance(0.5, _BTC, 0.03) == "residual")


def test_a_price_at_its_own_tick_is_not_degraded():
    """The true negative for the degradation above: a price that floors to a positive number keeps
    its estimate, or the guard would refuse every priced leg and read as working."""
    leg = flatten.Leg("spot", "BTC", "BTC/EUR", "SELL", 0.5, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _BTC, 60000.0)
    assert sized.reference_price == 60000.0
    assert sized.estimate == pytest.approx(30000.0)


# --- the snapshot and the plan ------------------------------------------------------------------


def _client_with(*, orders=None, positions=None, balances=None, symbols=(), books=None):
    rows = [_Instrument(s) for s in symbols]
    return FakeClient(
        instruments=rows,
        orders=[orders or []],
        positions=[positions or []],
        balances=[balances or []],
        books=books or {},
    )


def test_the_snapshot_reads_orders_then_positions_then_balances():
    """Order matters: an order that fills between the reads must land in a read that FOLLOWS, so
    it cannot vanish from both."""
    client = _client_with(symbols=("BTC/EUR",))
    flatten.read_snapshot(client, flatten.Recorder())
    assert names(client) == ["request_order_status_reports", "request_position_status_reports", "request_account_state"]


def test_the_plan_reads_one_book_per_leg_pair_and_the_btc_euro_pair_when_a_leg_routes_through_btc():
    """Every book read happens before the first write, so a shape the venue changed aborts with
    nothing half-done -- which means pass two's BTC sell needs its price taken here, not later."""
    client = _client_with(
        balances=[_Balance("ETH", 2.0)],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    snapshot = flatten.read_snapshot(client, rec)
    plan = flatten.build_plan(client, rec, snapshot, listing)
    assert sorted(plan.prices) == ["BTC/EUR", "ETH/BTC"]
    assert plan.prices["ETH/BTC"] == 0.03


def test_no_btc_euro_book_is_read_when_no_leg_routes_through_btc():
    client = _client_with(
        balances=[_Balance("ADA", 1200.0)], symbols=("ADA/EUR", "BTC/EUR"), books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)}
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert sorted(plan.prices) == ["ADA/EUR"]


def test_a_short_leg_prices_off_the_ask_and_a_long_off_the_bid():
    """Both halves the name claims, so neither side of the mapping can be wired to the other."""
    client = _client_with(
        positions=[_Position("BTC/EUR", "SHORT", 0.5), _Position("ETH/EUR", "LONG", 1.0)],
        symbols=("BTC/EUR", "ETH/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ETH/EUR.KRAKEN": _Book(3000.0, 3001.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices["BTC/EUR"] == 60010.0  # SHORT -> the closer BUYs -> priced off the ask
    assert plan.prices["ETH/EUR"] == 3000.0  # LONG -> the closer SELLs -> priced off the bid


def test_a_book_read_failure_on_one_leg_never_aborts_the_plan_or_any_other_leg():
    """The abort that would cost everything: the kill file is latched and the engine stopped by the
    time this runs, so raising here returns exit 3 with nothing cancelled, closed or sold. The ADA
    book is absent, so its read raises where the BTC one answers -- and the ADA leg is still sized
    and still sent, on the quantity floor alone."""
    client = _client_with(
        positions=[_Position("BTC/EUR", "LONG", 0.5)],
        balances=[_Balance("ADA", 1200.0)],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices == {"BTC/EUR": 60000.0}
    assert [sized.leg.symbol for sized in plan.spot] == ["ADA/EUR"]
    assert plan.spot[0].send is True and plan.spot[0].reference_price is None
    assert [sized.leg.symbol for sized in plan.margin] == ["BTC/EUR"]


def test_a_book_that_prices_at_zero_leaves_the_leg_unpriced_and_still_sold():
    """The degradation is what makes refusing a zero price safe: the leg is sized on the quantity
    floor alone and SENT, exactly as one whose book read raised. Carried instead, the zero would
    make it dust -- not sent, not a residual, and the run would report flat while still holding
    it."""
    zero = _Book(0.4, 0.41)
    zero.bids = [_Level(0.0)]
    client = _client_with(balances=[_Balance("ADA", 1200.0)], symbols=("ADA/EUR",), books={"ADA/EUR.KRAKEN": zero})
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices == {}
    (sized,) = plan.spot
    assert sized.send is True and sized.reference_price is None


def test_a_missing_constraint_on_a_leg_s_pair_aborts_the_plan():
    rows = [_Instrument("ADA/EUR")]
    rows[0].min_quantity = None
    client = FakeClient(instruments=rows, balances=[[_Balance("ADA", 1200.0)]], books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)})
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)


def test_the_rendered_plan_names_every_leg_every_dust_line_and_everything_it_cannot_touch():
    """What the operator reads has to include what the sweep will NOT do -- a balance no pair can
    carry and a position whose pair the listing does not have are both still there afterwards."""
    client = _client_with(
        orders=[object()],
        positions=[_Position("BTC/EUR", "LONG", 0.5), _Position("GONE/EUR", "LONG", 1.0)],
        balances=[_Balance("ADA", 1200.0), _Balance("DOT", 0.001), _Balance("WEIRD", 3.0)],
        symbols=("BTC/EUR", "ADA/EUR", "DOT/EUR"),
        books={
            "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0),
            "ADA/EUR.KRAKEN": _Book(0.4, 0.41),
            "DOT/EUR.KRAKEN": _Book(4.0, 4.01),
        },
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    lines: list[str] = []
    flatten.render_plan(plan, lines.append)
    text = "\n".join(lines)
    assert "BTC/EUR" in text and "SELL" in text
    assert "ADA/EUR" in text
    assert "DOT/EUR" in text and "not sent" in text
    assert "WEIRD" in text
    assert "GONE/EUR" in text and "cannot be closed here" in text
    assert "1 resting order" in text


def test_the_rendered_plan_prints_no_cross_currency_total():
    """A BTC-quoted estimate and a EUR one are not summable without an FX rate this command has no
    mandate to invent, so no grand total is printed at all."""
    client = _client_with(
        balances=[_Balance("ETH", 2.0)],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    lines: list[str] = []
    flatten.render_plan(plan, lines.append)
    assert not any("total" in line.lower() for line in lines)


def test_a_snapshot_read_that_answers_nothing_aborts_instead_of_becoming_an_empty_snapshot():
    """`read_snapshot` composes three aborting reads and must not soften any of them: a `Snapshot`
    carrying `positions=[]` because the venue answered `None` is the shape that confirms itself all
    the way to exit 0 over open leverage. The abort also STOPS the sequence -- the balance read must
    not run and hand the operator a plan built from half a snapshot."""
    client = FakeClient(positions=[None], balances=[[_Balance("ADA", 1200.0)]])
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_snapshot(client, flatten.Recorder())
    assert names(client) == ["request_order_status_reports", "request_position_status_reports"]


def test_a_venue_that_answers_empty_is_a_plan_with_no_legs_that_says_so_in_words():
    """The other half of the same distinction: `[]` is a real answer and must NOT abort. What the
    operator then reads has to say so in words -- a render that printed only the order line leaves
    'no positions' indistinguishable from 'the position section is missing'. No book is read either,
    since there is no leg to price."""
    client = _client_with(symbols=("BTC/EUR",))
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert (plan.margin, plan.spot, plan.unsellable, plan.unclosable, plan.prices) == ([], [], [], [], {})
    assert plan.n_open_orders == 0
    assert "request_book_snapshot" not in names(client)
    lines: list[str] = []
    flatten.render_plan(plan, lines.append)
    assert "no margin position to close" in lines
    assert "no non-EUR spot balance to sell" in lines


def test_a_margin_and_a_spot_leg_on_one_pair_share_one_book_read_taken_on_the_margin_side():
    """One read per PAIR, not per leg: every book read is pre-write, and a second request on a pair
    already read is one more chance to be rate-limited before the cancel goes out. The margin leg
    fixes the side, so the shared price is the ask its BUY closer would cross -- one spread from the
    bid the spot leg would have taken, which moves the printed estimate and nothing that is sent."""
    client = _client_with(
        positions=[_Position("BTC/EUR", "SHORT", 0.5)],
        balances=[_Balance("BTC", 0.5)],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert names(client).count("request_book_snapshot") == 1
    assert plan.prices == {"BTC/EUR": 60010.0}
    assert [sized.leg.symbol for sized in plan.margin] == ["BTC/EUR"]
    assert [sized.leg.symbol for sized in plan.spot] == ["BTC/EUR"]


def test_each_leg_is_sized_with_the_price_and_the_constraints_of_its_own_pair():
    """Defence in depth behind `_tick_floored`: a price handed another pair's constraints floors to
    nothing and the leg degrades to unpriced -- safe, but silently estimate-less. The fixture makes
    the two pairs discriminate: 0.03 BTC survives ETH/BTC's 1e-7 tick and is erased by BTC/EUR's
    0.1, so a leg sized against the wrong row loses both its estimate and its quote."""
    client = _client_with(
        balances=[_Balance("ETH", 2.0)],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    (sized,) = plan.spot
    assert sized.leg.symbol == "ETH/BTC"
    assert sized.reference_price == 0.03
    assert sized.quote == "BTC"
    assert sized.estimate == pytest.approx(0.06)
    assert plan.constraints["ETH/BTC"].tick_size == 0.0000001


# --- the gates and the confirm ------------------------------------------------------------------


def _exec_dir(tmp_path: Path) -> Path:
    d = tmp_path / "exec"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _drain(fd: int) -> bytes:
    """Everything the child wrote to the pty, read after it exited.

    Linux hands back the buffered output first and only then raises EIO on the master, so a read
    loop that stops at the OSError sees what the child printed (measured on cpython 3.14.6).
    """
    seen = b""
    try:
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            seen += chunk
    except OSError:
        pass
    return seen


def test_an_absent_kill_file_refuses(tmp_path):
    """The file is load-bearing: without it nothing stops the engine re-opening what this sweep
    closes, so the sweep does not start."""
    _exec_dir(tmp_path)
    with pytest.raises(flatten.FlattenRefused):
        flatten.check_kill_file(tmp_path)


def test_a_present_kill_file_passes_and_its_text_is_returned_for_the_record(tmp_path):
    (_exec_dir(tmp_path) / "kill").write_text("2026-08-30T12:00:00+00:00 flatten\n")
    assert "flatten" in flatten.check_kill_file(tmp_path)


def test_a_kill_file_that_is_not_utf_8_refuses_by_name_rather_than_crashing(tmp_path):
    """Neither present nor absent is a crash. The kill file is the interlock the whole command
    hangs on, and a read that raises past the refusal hands the operator a traceback where the
    exit-code contract promises a named exit-1 refusal naming the file to go and fix."""
    (_exec_dir(tmp_path) / "kill").write_bytes(b"\xff\xfe not utf-8")
    with pytest.raises(flatten.FlattenRefused) as exc:
        flatten.check_kill_file(tmp_path)
    assert "unreadable" in str(exc.value)


def test_the_kill_file_path_is_the_engine_s_own(tmp_path):
    """One control-file directory. A second spelling here is a kill file the engine never reads."""
    from cli.engine.execgate import KILL_FILE, exec_dir

    assert flatten.kill_file_path(tmp_path) == exec_dir(tmp_path) / KILL_FILE


def test_a_venue_that_is_not_online_aborts():
    from cli.engine.venue import VenueStatus

    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    ok = VenueStatus(status="online", ok=True, observed_at=now)
    bad = VenueStatus(status="maintenance", ok=False, observed_at=now)
    assert flatten.check_venue(lambda **_: ok, now).status == "online"
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.check_venue(lambda **_: bad, now)
    assert "maintenance" in str(exc.value)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("FLATTEN", True),
        ("  FLATTEN  ", True),
        ("flatten", False),
        ("FLATTE", False),
        # The one negative that CONTAINS the word: every other one here passes under a substring
        # match too, so without this the exact-vs-substring defect is invisible and `FLATTEN NOW`
        # authorises the whole irreversible sweep.
        ("FLATTEN NOW", False),
        ("", False),
        ("y", False),
    ],
)
def test_only_the_exact_word_matches(reply, expected):
    """Case-sensitive, exact, and not merely CONTAINED: a red button that accepts `y` is a button
    pressed by accident, and one that accepts `FLATTEN NOW` is pressed by a typo."""
    assert flatten.matches_confirm(reply) is expected


def test_the_prompt_names_the_word_and_says_what_pressing_it_does():
    assert flatten.CONFIRM_WORD in flatten.CONFIRM_PROMPT
    assert "market" in flatten.CONFIRM_PROMPT
    assert "aborts" in flatten.CONFIRM_PROMPT


def test_the_confirm_reads_the_controlling_terminal_and_never_stdin(tmp_path):
    """A pipe or a heredoc must not be able to drive the confirm (converge.sh's rule). The child's
    stdin is EMPTY here, so an implementation reading stdin raises instead of returning the word."""
    out = tmp_path / "reply.txt"
    pid, fd = pty.fork()
    if pid == 0:  # child: the pty is its controlling terminal
        try:
            os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
            from cli.engine import flatten as child_flatten

            out.write_text(child_flatten.read_confirm("word? "))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.write(fd, b"FLATTEN\n")
    os.waitpid(pid, 0)
    os.close(fd)
    assert out.read_text().strip() == "FLATTEN"


def test_the_prompt_is_written_to_the_terminal_and_not_to_this_process_s_stdout(tmp_path):
    """The read is only half the confirm: a prompt that goes to stdout is a prompt the operator
    never sees when the wrapper has captured stdout to a log, and the button then waits at a blank
    screen for a word nobody knows to type. pytest's default fd-level capture has already taken
    this process's fd 1, so a prompt printed rather than written to `/dev/tty` reaches the capture
    file and never the terminal drained below. That is also this guard's limit: run under `-s` the
    child's fd 1 IS the pty slave, and a prompt sent to stdout would reach the drain and pass."""
    out = tmp_path / "reply.txt"
    pid, fd = pty.fork()
    if pid == 0:
        try:
            os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
            from cli.engine import flatten as child_flatten

            out.write_text(child_flatten.read_confirm("TYPE-THE-WORD? "))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.write(fd, b"FLATTEN\n")
    os.waitpid(pid, 0)
    seen = _drain(fd)
    os.close(fd)
    assert out.read_text().strip() == "FLATTEN"
    assert b"TYPE-THE-WORD?" in seen


def test_the_terminal_check_answers_true_from_a_controlling_terminal(tmp_path):
    """The gate's other direction. One that answers False everywhere refuses the button in exactly
    the crisis it exists for, and the no-terminal test below cannot tell the two apart."""
    out = tmp_path / "answer.txt"
    pid, fd = pty.fork()
    if pid == 0:
        try:
            from cli.engine import flatten as child_flatten

            out.write_text(str(child_flatten.terminal_available()))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    os.close(fd)
    assert out.read_text() == "True"


def test_the_terminal_check_answers_false_with_no_controlling_terminal(tmp_path):
    """Refusing early costs nothing and saves an operator five venue reads before the refusal."""
    out = tmp_path / "answer.txt"
    pid = os.fork()
    if pid == 0:
        try:
            # Always succeeds here: a freshly forked child carries a new pid and its parent's group,
            # so it is never the group leader `setsid` refuses. Nothing skips this assertion.
            os.setsid()  # a fresh session has no controlling terminal
            from cli.engine import flatten as child_flatten

            out.write_text(str(child_flatten.terminal_available()))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            # Without this the parent reads a file that was never written: a FileNotFoundError at
            # `out.read_text()` instead of an assertion naming what went wrong inside the check.
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    assert out.read_text() == "False"


# --- the write sequence -------------------------------------------------------------------------

_STAMP = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _sweep_client(*, orders, positions, balances, symbols, books):
    """Queues, one entry per read of that kind, in call order: orders 3 (snapshot, post-cancel,
    final), positions 4 (snapshot, post-cancel, post-margin, final), balances 4 (snapshot,
    post-margin, post-pass-one, final). The last entry repeats if a read happens again."""
    return FakeClient(
        instruments=[_Instrument(s) for s in symbols],
        orders=orders,
        positions=positions,
        balances=balances,
        books=books,
    )


def _plan_of(client):
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    return rec, listing, plan


def test_the_full_sequence_calls_the_venue_in_the_order_the_design_fixes():
    """The order is the design: nothing is sized from the pre-confirm snapshot, a fill during the
    human-paced confirm lands in the post-cancel read, and the final snapshot reads orders before
    positions before balances."""
    client = _sweep_client(
        orders=[[], [], []],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    before = len(client.calls)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert names(client)[before:] == [
        "cancel_all_orders",
        "request_order_status_reports",
        "request_position_status_reports",
        "submit_order",
        "request_position_status_reports",
        "request_account_state",
        "submit_order",
        "request_account_state",
        "request_order_status_reports",
        "request_position_status_reports",
        "request_account_state",
    ]


def test_a_margin_closer_carries_reduce_only_market_ioc_leverage_and_the_margin_account():
    """The client-side side-and-cap invariant is the bound this repo has proven; the venue's own
    reduce_only flag is the second, and it must actually be sent."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "SHORT", 0.5)], [_Position("BTC/EUR", "SHORT", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    (sent,) = client.submitted
    assert sent["order_side"] == "BUY"  # a SHORT closes with a BUY, never a SELL
    assert sent["order_type"] == "MARKET"
    assert sent["time_in_force"] == "IOC"
    assert sent["reduce_only"] is True
    assert sent["leverage"] == flatten.MARGIN_LEVERAGE
    assert sent["account_type"] == "MARGIN"
    assert sent["quantity"] == 0.5


def test_a_spot_sell_carries_no_reduce_only_and_no_leverage():
    """Kraken's reduce_only is a margin concept a spot order cannot carry."""
    client = _sweep_client(
        orders=[[]],
        positions=[[]],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("ADA/EUR",),
        books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    (sent,) = client.submitted
    assert sent["order_side"] == "SELL"
    assert sent["account_type"] == "CASH"
    assert sent.get("reduce_only") is False
    assert "leverage" not in sent


def test_a_fill_during_the_confirm_is_closed_at_the_post_cancel_size_not_the_snapshot_size():
    """The closes are sized from the read AFTER the cancel. Sizing from the pre-confirm snapshot
    would leave the difference open and call the account flat."""
    client = _sweep_client(
        orders=[[]],
        positions=[
            [_Position("BTC/EUR", "LONG", 0.5)],
            [_Position("BTC/EUR", "LONG", 0.9)],
            [_Position("BTC/EUR", "LONG", 0.9)],
            [_Position("BTC/EUR", "LONG", 0.9)],
        ],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert client.submitted[0]["quantity"] == 0.9
    assert result.final.positions[0].quantity == 0.9


def test_a_rejected_margin_leg_is_journaled_and_the_sweep_continues_to_the_spot_pass():
    """A rejection is never retried and never stops the rest of the account being flattened, and a
    leg that cleared `ordermin` before it was sent gains no label from having been refused -- the
    rejection text is never read."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    client.raises["submit_order"] = RuntimeError("EOrder:Insufficient margin")
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    margin_outcome = next(o for o in result.outcomes if o.kind == "margin")
    assert margin_outcome.sent is True and "Insufficient margin" in margin_outcome.error
    assert margin_outcome.reason is None  # 0.5 clears _Instrument's 0.0001 ordermin
    assert [o.symbol for o in result.outcomes if o.kind == "spot"] == ["ADA/EUR"]
    assert result.final is not None


def test_a_rejected_sub_ordermin_closer_is_labelled_from_the_arithmetic_not_from_the_venue_s_words():
    """The other side of the test above, and the label an operator acts on: this closer was sized
    BELOW the pair's own `ordermin` before it was sent, so its refusal routes to Kraken's
    settle-position action rather than to a second run.

    The rejection text deliberately says nothing about a minimum -- which Kraken message means
    "below the minimum" is unmeasured here, so the label may only come from the pre-send
    arithmetic. Read off the venue's words instead, this leg would wear no label at all."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.00005)], [_Position("BTC/EUR", "LONG", 0.00005)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    client.raises["submit_order"] = RuntimeError("EOrder:Insufficient margin")
    rec, listing, plan = _plan_of(client)
    (outcome,) = flatten.sweep(client, rec, plan, listing, stamp=_STAMP).outcomes
    assert outcome.sent is True  # it was sent: a sub-ordermin closer is the venue's to refuse
    assert outcome.reason == "unclosable_below_minimum"
    assert "Insufficient margin" in outcome.error


def test_a_failing_cancel_does_not_stop_the_closes():
    """The closes do not depend on the cancel, so its failure is recorded and the sweep runs on."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    client.raises["cancel_all_orders"] = RuntimeError("EGeneral:Temporary lockout")
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert result.cancel_ok is False and "lockout" in result.cancel_error
    assert len(client.submitted) == 1


def test_a_broken_shape_on_the_post_cancel_re_read_stops_before_any_order():
    """The first-write boundary is the cancel, not the first order: after it, a read that cannot be
    parsed leaves the account possibly changed, so nothing further is sent and nothing reads flat.

    The ADA balance is what makes `submitted == []` a claim rather than a restatement of the
    fixture. Without something else to sell it is empty under the defect too -- and the defect here
    is real and adjacent: `_read_for_the_record` widened to cover THIS read sizes the closers off an
    empty list, sends none of them, and sells the spot book anyway. That mutant passed this test
    until the balance was added."""
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.quantity
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [broken]],
        balances=[[_Balance("ADA", 1200.0)]],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert "cancel_all_orders" in names(client)
    assert client.submitted == []
    assert result.post_write_failure is not None
    assert result.final is None


def test_the_second_spot_pass_sells_the_btc_the_first_pass_produced():
    """Pass one sells a BTC-quoted leg; pass two sells the BTC that produced, priced from the
    BTC/EUR book taken at the snapshot."""
    client = _sweep_client(
        orders=[[]],
        positions=[[]],
        balances=[
            [_Balance("ETH", 2.0)],
            [_Balance("ETH", 2.0)],
            [_Balance("XXBT", 0.06)],
            [_Balance("XXBT", 0.0)],
        ],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert [s["instrument_id"] for s in client.submitted] == ["ETH/BTC.KRAKEN", "BTC/EUR.KRAKEN"]


def test_a_leg_below_the_venue_minimum_is_recorded_and_never_reaches_the_venue():
    """Two of `_send`'s three verdicts on one read, and the third is every other test here.

    The DOT balance is dust -- 0.001 at 4.00 EUR is 0.004 EUR against the 0.45 EUR costmin -- so no
    order is constructed for it and it carries no client order id: an id minted for an order that
    was never sent is an id an operator looks for at the venue. The ADA balance beside it has no
    reference price (its book is absent) and is sent anyway, which is what keeps this from being a
    fixture that would pass under a `_send` refusing everything."""
    client = _sweep_client(
        orders=[[]],
        positions=[[]],
        balances=[
            [_Balance("ADA", 1200.0), _Balance("DOT", 0.001)],
            [_Balance("ADA", 1200.0), _Balance("DOT", 0.001)],
            [],
            [],
        ],
        symbols=("ADA/EUR", "DOT/EUR"),
        books={"DOT/EUR.KRAKEN": _Book(4.0, 4.01)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert [s["instrument_id"] for s in client.submitted] == ["ADA/EUR.KRAKEN"]

    ada = next(o for o in result.outcomes if o.symbol == "ADA/EUR")
    assert ada.sent is True and ada.reason == "no_reference_price"
    assert ada.client_order_id.startswith(flatten.CLIENT_ORDER_ID_PREFIX)

    dot = next(o for o in result.outcomes if o.symbol == "DOT/EUR")
    assert dot.sent is False and dot.reason == "dust_below_venue_minimum"
    assert dot.client_order_id is None and dot.error is None


def test_the_client_order_id_cannot_collide_with_the_engine_s_or_the_probe_harness_s():
    """The executor routes an ack it recognises as its own; an id sharing the engine's shape would
    make a flatten fill land in the engine's ledger."""
    cid = flatten.mint_client_order_id(_STAMP, 3)
    assert cid.startswith(flatten.CLIENT_ORDER_ID_PREFIX)
    assert "-001-000-" not in cid
    assert not cid.startswith("O-")
    assert cid != flatten.mint_client_order_id(_STAMP, 4)


def test_every_order_in_one_run_carries_its_own_client_order_id_across_all_three_passes():
    """The id counter runs over the WHOLE run, not per pass: Kraken refuses a client order id it has
    already seen, so two legs sharing one id is one leg silently unsent -- recorded as sent, with
    the venue's duplicate refusal the only trace.

    Three orders across all three passes -- the margin close, pass one's BTC-quoted sell, and pass
    two's sale of the BTC it produced -- so a counter that restarts at a pass boundary is visible
    where one restarting per leg would not be."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[_Balance("ETH", 2.0)], [_Balance("ETH", 2.0)], [_Balance("XXBT", 0.06)], []],
        symbols=("BTC/EUR", "ETH/BTC"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ETH/BTC.KRAKEN": _Book(0.03, 0.031)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    ids = [s["client_order_id"] for s in client.submitted]
    assert len(ids) == 3, ids
    assert len(set(ids)) == 3, ids
    assert all(cid.startswith(flatten.CLIENT_ORDER_ID_PREFIX) for cid in ids)
    assert [o.client_order_id for o in result.outcomes] == ids


def test_the_journal_records_the_scoping_of_the_order_that_actually_went_out():
    """The journal is what an operator reads mid-incident, and one that says MARGIN while CASH went
    out is worse than none. Every scoping value is derived once and both sent and journalled, so the
    two cannot be spelled differently; this pins the pairing on both account types at once -- a
    hand-written literal is correct for one of them and wrong for the other."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "SHORT", 0.5)], [_Position("BTC/EUR", "SHORT", 0.5)], [], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    journalled = [entry["params"] for entry in rec.entries if entry["call"] == "submit_order"]
    assert [p["account_type"] for p in journalled] == ["MARGIN", "CASH"]
    for params, sent in zip(journalled, client.submitted, strict=True):
        assert params["account_id"] == flatten.ACCOUNT_ID
        for field in ("instrument_id", "client_order_id", "order_side", "order_type", "quantity", "time_in_force"):
            assert params[field] == sent[field], field
        assert params["reduce_only"] is sent["reduce_only"]
        assert params["account_type"] == sent["account_type"]
        assert params.get("leverage") == sent.get("leverage")


def test_the_submit_call_carries_the_library_s_own_types_and_binds_against_the_real_client():
    """`FakeClient.submit_order` takes `**kw`, so it accepts every keyword including ones the real
    client does not have, and `_norm` reduces a plain `"MARKET"` to the same text a real
    `OrderType.MARKET` gives. Every other assertion in this section therefore passes under an
    implementation that sends strings at a compiled signature and fails only at the venue, on the
    one call that moves money.

    Both halves the send depends on: the seven positionals land on the parameters they are meant
    for -- a parameter inserted upstream would slide the client order id into another slot with
    every fake-driven test still green -- and the scoping keywords exist on the real signature.
    `instrument_id` is deliberately not type-asserted: it is handed back verbatim from the listing
    row the venue answered with, so its type is the venue's to choose. `cancel_all_orders` is bound
    beside it because it is the other venue-mutating call this module makes."""
    import inspect

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient
    from nautilus_trader.model import AccountId, AccountType, ClientOrderId, OrderSide, OrderType, Quantity, TimeInForce

    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "SHORT", 0.5)], [_Position("BTC/EUR", "SHORT", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    ((positional, kwargs),) = client.submitted_raw

    account_id, _instrument_id, client_order_id, order_side, order_type, quantity, time_in_force = positional
    assert isinstance(account_id, AccountId)
    assert isinstance(client_order_id, ClientOrderId)
    assert isinstance(order_side, OrderSide)
    assert isinstance(order_type, OrderType)
    assert isinstance(quantity, Quantity)
    assert isinstance(time_in_force, TimeInForce)
    assert isinstance(kwargs["account_type"], AccountType)

    bound = inspect.signature(KrakenSpotHttpClient.submit_order).bind(None, *positional, **kwargs)
    assert list(bound.arguments)[1:8] == [
        "account_id",
        "instrument_id",
        "client_order_id",
        "order_side",
        "order_type",
        "quantity",
        "time_in_force",
    ]
    inspect.signature(KrakenSpotHttpClient.cancel_all_orders).bind(None)


def test_a_failing_read_that_nothing_consumes_does_not_cost_the_spot_passes():
    """The position read taken after the closes feeds only the journal. Inside the one post-write
    try it took both spot passes and the final snapshot with it: the margin close went out, a
    1200 ADA balance was left unsold, and the run returned no verdict at all -- because a read
    nobody reads failed.

    `test_a_broken_shape_on_the_post_cancel_re_read_stops_before_any_order` is the other half of the
    asymmetry, and it still holds: the read that SIZES the closers must abort, because a degraded
    one would size them off an empty list and call the account flat."""
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.quantity
    client = _sweep_client(
        orders=[[], [], []],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [broken], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert [s["instrument_id"] for s in client.submitted] == ["BTC/EUR.KRAKEN", "ADA/EUR.KRAKEN"]
    assert result.post_write_failure is None
    assert result.final is not None
    # The evidence survives the degrade: the request went out and its answer -- the unreadable row
    # itself -- is in the journal, which is the whole point of taking the read.
    position_reads = [entry for entry in rec.entries if entry["call"] == "request_position_status_reports"]
    assert len(position_reads) == 4 and all("answer" in entry for entry in position_reads)


def test_a_failing_post_cancel_order_count_does_not_cost_the_closes():
    """The same class, one read earlier. `orders_after_cancel` is written into the record and read
    by no decision -- the exit code judges the FINAL snapshot's orders, never this count. `None`
    there is a count nobody took; an abort there is every position left open."""
    client = _sweep_client(
        orders=[[], None, []],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert result.orders_after_cancel is None
    assert [s["instrument_id"] for s in client.submitted] == ["BTC/EUR.KRAKEN"]
    assert result.post_write_failure is None and result.final is not None


def test_a_leg_side_this_module_cannot_map_sends_nothing_and_is_named():
    """Unreachable from `margin_legs`/`spot_legs` -- the only two places a `Leg` is built, both
    writing a literal side -- so this pins the direction a defect would take rather than a live
    path. A conditional's else-branch turns an unmapped side into a real market order the other way;
    the lookup sends nothing and puts the side in the record.

    `sent` stays True on a purely local failure by design (nothing here can tell one from a request
    that left and was refused), so the assertion that the venue saw nothing is the one that carries
    the claim."""
    client = FakeClient()
    leg = flatten.Leg("margin", "BTC", "BTC/EUR", "SIDEWAYS", 0.5, "MARGIN", "position_status_report.quantity")
    sized = flatten.size_leg(leg, _BTC, 60000.0)
    outcome = flatten._send(client, flatten.Recorder(), sized, _BTC, _STAMP, 1, "margin")
    assert client.submitted == []
    assert outcome.sent is True and "SIDEWAYS" in outcome.error


# --- exit codes, the journal, and the command end to end ----------------------------------------


def _online(**_):
    from cli.engine.venue import VenueStatus

    return VenueStatus(status="online", ok=True, observed_at=_STAMP)


def _offline(**_):
    from cli.engine.venue import VenueStatus

    return VenueStatus(status="maintenance", ok=False, observed_at=_STAMP)


def _armed(tmp_path: Path) -> Path:
    (_exec_dir(tmp_path) / "kill").write_text("2026-08-30T12:00:00+00:00 flatten\n")
    return tmp_path


def _run(client, tmp_path, *, execute=True, reply="FLATTEN", venue=_online, tty=True, lines=None, prompt=None, echo=None):
    return flatten.run_flatten(
        client,
        state_dir=tmp_path,
        execute=execute,
        now=lambda: _STAMP,
        venue_reader=venue,
        tty_available=lambda: tty,
        prompt=prompt if prompt is not None else (lambda _: reply),
        echo=echo if echo is not None else (lines.append if lines is not None else (lambda _: None)),
    )


class _StdoutThatDies:
    """An echo that starts raising the moment `trigger()` says so, and remembers what landed
    before that.

    ENOSPC on the wrapper's captured log and EPIPE from a wrapper that died are the incident-day
    conditions; what the two fixtures below vary is the TIMING relative to the first write, which
    is the whole of the asymmetry being pinned. `lines` is what makes each one bite: it names the
    line that would have been there had the trigger never fired.
    """

    def __init__(self, trigger) -> None:
        self.trigger = trigger
        self.lines: list[str] = []

    def __call__(self, line: str) -> None:
        if self.trigger():
            raise OSError(28, "No space left on device")
        self.lines.append(line)


def _flat_client(**kw):
    defaults = dict(
        orders=[[]], positions=[[]], balances=[[]], symbols=("BTC/EUR",), books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)}
    )
    defaults.update(kw)
    return _sweep_client(**defaults)


def test_the_default_invocation_sends_nothing_needs_no_kill_file_and_exits_zero(tmp_path):
    """The invocation an operator reaches by accident or by muscle memory must be the one that
    changes nothing -- which is why there is no flag meaning 'do nothing' to forget."""
    client = _flat_client(
        balances=[[_Balance("ADA", 1200.0)]],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    lines: list[str] = []
    assert _run(client, tmp_path, execute=False, lines=lines) == 0
    assert "cancel_all_orders" not in names(client)
    assert "submit_order" not in names(client)
    assert any("ADA/EUR" in line for line in lines)
    assert list(_exec_dir(tmp_path).glob("flatten-*.json")) == []


@pytest.mark.parametrize(
    ("setup", "reply", "tty", "armed"),
    [("kill-absent", "FLATTEN", True, False), ("confirm", "nope", True, True), ("no-tty", "FLATTEN", False, True)],
)
def test_every_refusal_exits_one_with_no_request_and_no_write(tmp_path, setup, reply, tty, armed):
    """The only path to `submit_order` or `cancel_all_orders` runs through --execute AND a matched
    confirm. Each refusal is asserted on what reached the venue, not on the exit code alone."""
    if armed:
        _armed(tmp_path)
    else:
        _exec_dir(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path, reply=reply, tty=tty) == 1
    assert "cancel_all_orders" not in names(client)
    assert "submit_order" not in names(client)
    if setup == "kill-absent":
        assert client.calls == []  # refused before a single request
    # Every exit-1 refusal `run_flatten` itself makes leaves the record: the refusal and its reason
    # are what the artifact exists for, and an unrecorded refusal is one nobody can reconstruct.
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == 1


@pytest.mark.parametrize("execute", [True, False])
def test_a_venue_that_is_not_online_exits_three_with_nothing_sent(tmp_path, execute):
    """The dry run takes the venue gate too -- only the kill-file gate is skipped without
    `--execute`. The two invocations differ in exactly one way: the dry run leaves no artifact,
    which is `_dry_exit`'s whole contract and is reachable from no other fixture."""
    _armed(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path, execute=execute, venue=_offline) == 3
    assert client.calls == []
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == (1 if execute else 0)


@pytest.mark.parametrize("execute", [True, False])
def test_a_missing_field_on_a_pre_write_read_exits_three_and_the_cancel_never_goes_out(tmp_path, execute):
    """The first write is the cancel. Before it, a shape the venue changed aborts with the account
    untouched -- that is the whole difference between exit 3 and exit 2. An absent NAMED FIELD is
    that case; an unrecognised VALUE in a field that is present is not, and has its own fixture.
    The dry run reaches the same code through `_dry_exit` and leaves no artifact."""
    _armed(tmp_path)
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.position_side
    client = _flat_client(positions=[[broken]])
    assert _run(client, tmp_path, execute=execute) == 3
    assert "cancel_all_orders" not in names(client)
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == (1 if execute else 0)


def test_an_unrecognised_position_side_never_aborts_the_button_and_exits_two(tmp_path):
    """The row the venue answers with a side this build knows (`NO_POSITION_SIDE`) and this command
    cannot close from. Aborting would leave the resting orders resting, every balance held and the
    engine already stopped; reading it as flat would exit 0 over an open position. So: the cancel
    goes out, every other leg is sent, the row is named in the record, and the account reads 2."""
    _armed(tmp_path)
    odd = [_Position("BTC/EUR", "NO_POSITION_SIDE", 1.0)]
    client = _flat_client(
        positions=[odd, odd, odd, odd],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert [sent["instrument_id"] for sent in client.submitted] == ["ADA/EUR.KRAKEN"]
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    positions = [row for row in json.loads(path.read_text())["residuals"] if row["kind"] == "position"]
    assert [row["reason"] for row in positions] == ["unrecognised_position_side"]


def test_a_clean_sweep_of_a_flat_account_exits_zero(tmp_path):
    _armed(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path) == 0


def test_a_flat_row_alone_in_the_final_snapshot_exits_zero(tmp_path):
    """A FLAT row is not a leg and is not a residual; reading it as one would report a flat account
    as partial forever."""
    _armed(tmp_path)
    flat = [_Position("BTC/EUR", "FLAT", 0.0)]
    client = _flat_client(positions=[flat, flat, flat, flat])
    assert _run(client, tmp_path) == 0
    assert client.submitted == []


def test_a_resting_order_that_outlived_the_cancel_exits_two_even_with_nothing_else_open(tmp_path):
    """It can fill after the operator was told the book was flat."""
    _armed(tmp_path)
    client = _flat_client(orders=[[], [], [object()]])
    assert _run(client, tmp_path) == 2


def test_a_residual_position_after_the_closes_exits_two(tmp_path):
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, row, row])
    assert _run(client, tmp_path) == 2
    assert client.submitted != []
    # Every residual row carries a `reason`, the ordinary one included: an absent key is a second
    # row shape in an artifact read mid-incident. LONG on a listed pair is the ordinary case.
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    (position,) = [r for r in json.loads(path.read_text())["residuals"] if r["kind"] == "position"]
    assert position["reason"] == "open_position"


def test_a_fill_during_the_confirm_leaves_its_residual_in_the_final_snapshot_and_exits_two(tmp_path):
    """The close is sized from the post-cancel read, and what that read shows is what gets closed --
    but the account still has to be JUDGED afterwards, so a position the sweep could not finish
    reads 2 rather than flat."""
    _armed(tmp_path)
    grown = [_Position("BTC/EUR", "LONG", 0.9)]
    client = _flat_client(positions=[[_Position("BTC/EUR", "LONG", 0.5)], grown, grown, grown])
    assert _run(client, tmp_path) == 2
    assert client.submitted[0]["quantity"] == 0.9


def test_a_broken_shape_on_the_post_cancel_re_read_exits_two_with_no_order_sent(tmp_path):
    """The first-write boundary is the cancel: past it, neither 0 nor 3 is a claim this run can
    make. `test_a_broken_shape_on_the_post_cancel_re_read_stops_before_any_order` pins the same
    fixture at sweep level; this one pins the code it composes to."""
    _armed(tmp_path)
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.quantity
    client = _flat_client(positions=[[_Position("BTC/EUR", "LONG", 0.5)], [broken]])
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert client.submitted == []


def test_a_sub_ordermin_margin_row_is_sent_and_its_rejection_still_exits_two(tmp_path):
    """The engine's own machine produces sub-ordermin remainders by design, and a remainder left
    open is exposure -- so it is sent, and the venue rules on it. The label is minted from the
    pre-send arithmetic and the venue's own words are kept beside it: the exit code says 2 for a
    hundred reasons, an operator reading a bare `EOrder:` string is never routed to the venue's
    settle-position action, and the words are what say whether the refusal was about the size."""
    _armed(tmp_path)
    tiny = [_Position("BTC/EUR", "LONG", 0.00002)]  # under _Instrument's 0.0001 ordermin
    client = _flat_client(positions=[tiny, tiny, tiny, tiny])
    client.raises["submit_order"] = RuntimeError("EOrder:Invalid volume")
    assert _run(client, tmp_path) == 2
    assert client.submitted != []
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    (leg,) = [row for row in json.loads(path.read_text())["legs"] if row["kind"] == "margin"]
    assert leg["reason"] == "unclosable_below_minimum"
    assert "EOrder:Invalid volume" in leg["error"]  # the venue's own words are kept beside the label


def test_a_margin_row_on_an_unlisted_pair_never_aborts_the_button_and_exits_two(tmp_path):
    """The one pairlessness that could cost everything: aborting before the cancel would leave the
    resting orders resting, every other position open and every balance held, with the engine
    already stopped. So the row is named, the rest of the sweep runs, and the account reads 2."""
    _armed(tmp_path)
    stranded = [_Position("GONE/EUR", "LONG", 1.0)]
    client = _flat_client(
        positions=[stranded, stranded, stranded, stranded],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert [sent["instrument_id"] for sent in client.submitted] == ["ADA/EUR.KRAKEN"]
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    positions = [row for row in json.loads(path.read_text())["residuals"] if row["kind"] == "position"]
    assert [row["symbol"] for row in positions] == ["GONE/EUR"]
    assert positions[0]["reason"] == "pair_not_listed"


def test_a_balance_in_an_asset_with_neither_pair_exits_two_never_zero(tmp_path):
    _armed(tmp_path)
    held = [_Balance("WEIRD", 3.0)]
    client = _flat_client(balances=[held, held, held, held])
    assert _run(client, tmp_path) == 2


def test_a_dust_balance_alone_in_the_final_snapshot_exits_zero(tmp_path):
    """Dust is listed, not sent, and does not make the account not-flat -- the venue would reject
    the order that would clear it."""
    _armed(tmp_path)
    dust = [_Balance("ADA", 10.0)]
    client = _flat_client(
        balances=[dust, dust, dust, dust],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    for row in client._instruments:
        if row.id.startswith("ADA"):
            row.min_quantity = 15.0
    assert _run(client, tmp_path) == 0
    assert client.submitted == []


def test_a_failed_cancel_exits_two_whatever_each_leg_answered(tmp_path):
    _armed(tmp_path)
    client = _flat_client()
    client.raises["cancel_all_orders"] = RuntimeError("EGeneral:Temporary lockout")
    assert _run(client, tmp_path) == 2


def test_a_read_that_fails_after_the_first_write_exits_two_and_never_three(tmp_path):
    """Never 0 and never 3: the account may already have changed, so neither 'flat' nor 'untouched'
    is a claim this run can make."""
    _armed(tmp_path)
    client = _flat_client()
    # Break the THIRD open-order read -- the final snapshot's, the last read of the whole run.
    original, state = client.request_order_status_reports, {"n": 0}

    def counting(account_id, **kw):
        state["n"] += 1
        if state["n"] == 3:
            raise RuntimeError("connection reset")
        return original(account_id, **kw)

    client.request_order_status_reports = counting
    assert _run(client, tmp_path) == 2


def test_an_instrument_with_no_committed_costmin_is_still_sized_and_sent(tmp_path):
    """min_notional always reads None from this adapter, so a pair outside the committed table has
    no notional floor at all -- and must still be sold, not skipped."""
    _armed(tmp_path)
    held = [_Balance("WEIRD", 3.0)]
    client = _flat_client(
        # snapshot, the read that sizes pass one, then flat: pass two finds nothing left to send.
        balances=[held, held, [], []],
        symbols=("BTC/EUR", "WEIRD/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "WEIRD/EUR.KRAKEN": _Book(1.0, 1.01)},
    )
    assert _run(client, tmp_path) == 0
    assert [s["instrument_id"] for s in client.submitted] == ["WEIRD/EUR.KRAKEN"]


def test_a_balance_that_appears_after_the_snapshot_is_sold_unpriced_and_the_journal_says_so(tmp_path):
    """No post-write book read ever happens, so a balance surfacing only in a later pass has no
    reference price. It is still sold -- skipping it would leave a live holding the run then calls
    flat -- and the label is what tells the operator no estimate backed that order."""
    _armed(tmp_path)
    late = [_Balance("ADA", 1200.0)]
    client = _flat_client(
        # Empty at the snapshot, so no ADA/EUR book is read and the plan carries no ADA price.
        balances=[[], late, [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
    )
    assert _run(client, tmp_path) == 0
    assert [s["instrument_id"] for s in client.submitted] == ["ADA/EUR.KRAKEN"]
    assert "request_book_snapshot" not in names(client)
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    (leg,) = [row for row in json.loads(path.read_text())["legs"] if row["kind"] == "spot"]
    assert leg["sent"] is True and leg["reason"] == "no_reference_price"


def test_the_journal_records_the_snapshots_the_requests_the_confirm_and_the_exit_code(tmp_path):
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, [], []])
    assert _run(client, tmp_path) == 0
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["mode"] == "execute"
    assert doc["confirm"] == "matched"
    assert doc["exit_code"] == 0
    assert doc["snapshot_before"]["positions"][0]["symbol"] == "BTC/EUR"
    assert doc["snapshot_after"]["positions"] == []
    assert [e["call"] for e in doc["requests"]].count("submit_order") == 1
    assert doc["api_key_masked"] == "kr***xy"
    # The key's own VALUE, and never the name of the variable it arrived in: that name reaches no
    # part of this process, so asserting its absence is green under every implementation, leak
    # included. Only the masked form may appear in an artifact written to the engine's exec dir.
    assert FakeClient.api_key not in path.read_text()


def test_the_residuals_are_judged_against_the_final_snapshot_and_never_the_pre_sweep_one(tmp_path):
    """`run_flatten` holds both snapshots, so it is the first place the stale one can be judged --
    and residuals read off the pre-sweep snapshot would name positions the sweep has since closed
    while missing an order that outlived the cancel.

    The fixture makes the two snapshots disagree in BOTH directions, so the exit code alone cannot
    tell them apart -- it is 2 either way. Pre-sweep: no resting order, one LONG 0.5. Final: one
    resting order, no position. The residual KINDS are what differ, and are what is asserted."""
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(orders=[[], [], [object()]], positions=[row, row, [], []])
    assert _run(client, tmp_path) == 2
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    # Non-degenerate by construction: the recorded snapshots are the two that disagree.
    assert doc["snapshot_before"]["open_orders"] == 0
    assert [r["symbol"] for r in doc["snapshot_before"]["positions"]] == ["BTC/EUR"]
    assert doc["snapshot_after"]["open_orders"] == 1 and doc["snapshot_after"]["positions"] == []
    assert [r["kind"] for r in doc["residuals"]] == ["order"]


def test_the_journal_payload_is_json_serializable_without_the_dump_s_str_fallback(tmp_path, monkeypatch):
    """`write_journal` is the first code in this module to serialize the recorded request params,
    and it dumps with `default=str` -- a net that would quietly stringify a value nobody converted.
    This round-trips the REAL payload strictly, so the explicit conversions the record depends on
    are pinned rather than assumed: `_journalled`'s `str()` on `AccountType`, and `submit_leg`'s on
    the order side, the order type, the time in force and the quantity. Every one of those objects
    raises `TypeError` under a bare `json.dumps`.

    NOT the instrument id: `_Instrument.id` is a plain `str` here where production hands
    `constraints_for` a real `InstrumentId`, so that conversion is invisible from any fixture built
    on this fake and is pinned by
    `test_the_recorded_instrument_id_is_converted_where_the_fake_cannot_show_it` instead.

    A margin leg is the fixture because it is the only path carrying BOTH an `AccountType` and the
    `leverage` int -- a spot-only sweep never records the enum at all."""
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, [], []])
    captured: dict = {}
    original = flatten.write_journal

    def spy(state_dir, stamp, payload):
        captured["payload"] = payload
        return original(state_dir, stamp, payload)

    monkeypatch.setattr(flatten, "write_journal", spy)
    assert _run(client, tmp_path) == 0
    params = [e["params"] for e in captured["payload"]["requests"] if e["call"] == "submit_order"]
    assert params and params[0]["account_type"] == "MARGIN" and params[0]["leverage"] == flatten.MARGIN_LEVERAGE
    json.dumps(captured["payload"])  # no `default=`: the record must be serializable on its own


def test_the_recorded_instrument_id_is_converted_where_the_fake_cannot_show_it():
    """The one journalled conversion no sweep-level fixture can reach. `constraints_for` reads the
    id straight off the listing row, and this file's row carries a `str` -- so a dropped
    `str(constraints.instrument_id)` is invisible from every fake-driven run. Built here with the
    production type, which a bare `json.dumps` refuses, so the fourth conversion is pinned too."""
    from nautilus_trader.model import InstrumentId

    constraints = flatten.PairConstraints(
        "BTC/EUR", InstrumentId.from_str("BTC/EUR.KRAKEN"), ordermin=0.0001, lot_step=0.00000001, tick_size=0.1
    )
    leg = flatten.Leg("spot", "BTC", "BTC/EUR", "SELL", 0.5, "CASH", "account_state.balances")
    rec = flatten.Recorder()
    flatten.submit_leg(FakeClient(), rec, flatten.size_leg(leg, constraints, 60000.0), constraints, "FLT-20260830T120000Z-1")
    (entry,) = rec.entries
    assert entry["params"]["instrument_id"] == "BTC/EUR.KRAKEN"
    json.dumps(rec.entries)  # no `default=`: what `write_journal` would have to fall back on


def test_a_refused_run_still_journals_the_refusal(tmp_path):
    """The confirm that did not match is exactly the thing worth having a record of."""
    _armed(tmp_path)
    assert _run(_flat_client(), tmp_path, reply="nope") == 1
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["confirm"] == "mismatch" and doc["exit_code"] == 1


def test_a_second_run_in_the_same_second_does_not_destroy_the_first_record(tmp_path):
    _armed(tmp_path)
    assert _run(_flat_client(), tmp_path) == 0
    assert _run(_flat_client(), tmp_path) == 0
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == 2


def test_the_journal_filename_needs_no_shell_quoting(tmp_path):
    """An operator types this path mid-incident."""
    name = flatten.journal_path(tmp_path, _STAMP).name
    assert name == "flatten-20260830T120000Z.json"
    assert not set(name) & set(":+ '\"")


# --- a stdout that goes away, on both sides of the first write ------------------------------


@pytest.mark.parametrize("execute", [True, False])
def test_a_stdout_that_dies_while_the_plan_is_printed_refuses_cleanly_and_never_tracebacks(tmp_path, execute):
    """Pre-write, so aborting is free -- but cleanly. Unguarded this is an `OSError` out of a
    function whose contract says it raises nothing, and the traceback carries Python's own exit 1:
    the code this command defines as "refused with nothing sent", with no journal beside it.

    The trigger fires on the FIRST line, which `render_plan` writes before anything else, so
    `echo.lines == []` is what says it bit: the plan's opening line is unconditional and would be
    there under any implementation that got past it. The dry run reaches the same gate and keeps
    its own contract of leaving no artifact."""
    _armed(tmp_path)
    client = _flat_client(positions=[[_Position("BTC/EUR", "LONG", 0.5)]] * 4)
    echo = _StdoutThatDies(lambda: True)
    assert _run(client, tmp_path, execute=execute, echo=echo) == 1
    assert echo.lines == []  # not one line landed: the trigger fired on the plan's first
    assert "cancel_all_orders" not in names(client)
    assert "submit_order" not in names(client)
    journals = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    assert len(journals) == (1 if execute else 0)
    if execute:
        doc = json.loads(journals[0].read_text())
        assert doc["exit_code"] == 1 and "display_failure" in doc


def test_a_stdout_that_dies_after_the_orders_went_out_keeps_the_true_code_and_the_record(tmp_path):
    """The instance that costs the most. Post-write a display failure may cost neither the exit
    code nor the journal: the cancel and the market sells have reached a real account, and an
    operator told "refused, nothing sent" -- which is what Python's exit 1 on a traceback says --
    acts on the opposite of what happened, with nothing to reconstruct from.

    `client.submitted` is the trigger, so every line up to and including the plan lands and the
    first line AFTER the sweep raises. Two values make it bite: `submitted` is non-empty (the
    margin closer went out, so the trigger certainly fires) and the summary's own opening line is
    absent from `echo.lines` (it would be there had it not). The residual position is what makes
    the true code 2 rather than 0 -- a code a traceback could never produce, and the one an
    operator has to see."""
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, row, row])
    echo = _StdoutThatDies(lambda: bool(client.submitted))
    assert _run(client, tmp_path, echo=echo) == 2
    assert client.submitted != []  # the trigger armed itself: orders reached the venue
    assert echo.lines != [] and not any("does NOT read flat" in line for line in echo.lines)
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["exit_code"] == 2
    assert [r["kind"] for r in doc["residuals"]] == ["position"]


def test_the_journal_s_own_fallback_survives_the_stdout_that_broke_the_file_write(tmp_path, monkeypatch, caplog):
    """`write_journal`'s last act may not be able to raise. The two failures arrive together on an
    incident day -- a full filesystem takes the wrapper's captured log with the artifact, a dead
    wrapper takes the pipe -- so a fallback that prints is a fallback that dies on the very
    condition it exists to survive, and it dies INSIDE `_finish`, taking the exit code with it.

    Two fixture values, and removing either makes this green under the defect: `exec_dir` points
    THROUGH a regular file, so `mkdir` raises `NotADirectoryError` and the file write really does
    fail; and `print` really does raise, so the fallback really is the thing under test. The
    payload's own marker in the log is what says the record survived rather than merely not
    crashing -- `logging` handles a failing handler internally and cannot raise out of here."""
    (tmp_path / "blocker").write_text("not a directory")

    def through_a_file(_state_dir):
        return tmp_path / "blocker" / "exec"

    class _DeadStdout:
        """The condition itself, not a stubbed `print`: `print` is left alone and the STREAM under
        it is what has gone. Patching `builtins.print` instead reaches inside `logging`'s own
        failure handling and makes the fallback look broken for a reason production cannot have."""

        def write(self, _text):
            raise OSError(28, "No space left on device")

        def flush(self):
            raise OSError(28, "No space left on device")

    monkeypatch.setattr("cli.engine.execgate.exec_dir", through_a_file)
    monkeypatch.setattr("sys.stdout", _DeadStdout())
    with caplog.at_level("CRITICAL", logger="engine.flatten"):
        assert flatten.write_journal(tmp_path, _STAMP, {"schema_version": 1, "marker": "kept"}) is None
    assert '"marker": "kept"' in caplog.text


def test_a_terminal_that_dies_between_the_check_and_the_prompt_refuses_and_journals(tmp_path):
    """`tty_available()` passed a moment ago and the confirm still raised -- a wrapper killed in
    between, a pty that went. Every other exit-1 refusal is pinned by a fixture; this handler sits
    on the same contract, on the gate between an operator and a real account, so it gets one too.

    Without it the raise leaves a traceback and Python's own exit 1, which reads identically to a
    refusal and leaves nothing behind: the journal and the recorded `unreadable` are what tell the
    two apart afterwards."""
    _armed(tmp_path)
    client = _flat_client()

    def gone(_):
        raise OSError(5, "Input/output error")

    assert _run(client, tmp_path, prompt=gone) == 1
    assert names(client) != []  # the pre-write reads ran -- this is not the kill-file refusal
    assert "cancel_all_orders" not in names(client)
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    # Never "not-required", which is what a dry run records: the word was asked for and could not
    # be read, and a record that cannot say which of those happened is one nobody can act on.
    assert doc["confirm"] == "unreadable" and doc["exit_code"] == 1


# --- the CLI surface ----------------------------------------------------------------------------

_runner = CliRunner()


def test_the_subcommand_is_registered_and_its_help_says_what_pressing_it_does():
    result = _runner.invoke(app, ["engine", "flatten", "--help"])
    assert result.exit_code == 0
    assert "--execute" in result.output
    assert "--state-dir" in result.output
    assert "market" in result.output


def test_the_state_dir_is_required_so_the_button_never_depends_on_a_config_mount():
    """The environment being broken is the situation this command exists for."""
    result = _runner.invoke(app, ["engine", "flatten"])
    assert result.exit_code != 0


def test_absent_credentials_refuse_with_exit_one_and_never_construct_a_client(monkeypatch, tmp_path):
    """Exit 1 is the refusal code, and it lands here before a client exists: one built without a
    key is a single request away from the venue.

    The unconstructed client is asserted SEPARATELY from the code, because the code alone cannot
    see this defect: drop the credential check and the constructor is reached with `None`, and the
    exception that follows reaches `CliRunner` as exit code 1 as well -- identical from the outside,
    with the object that holds a venue session already built."""
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    constructed: list[tuple] = []
    import nautilus_trader.adapters.kraken as kraken_adapter

    monkeypatch.setattr(kraken_adapter, "KrakenSpotHttpClient", lambda *args, **kwargs: constructed.append(args))
    result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert constructed == []


def test_the_command_never_names_a_credential_value(monkeypatch, tmp_path, caplog):
    """The refusal goes through `_abort`, which LOGS and never echoes, so the log record is the only
    surface a key could leak on -- an assertion on `result.output` alone stays green on an
    implementation that prints the value into it (`tests/test_error_paths_are_logged.py`).

    `caplog.handler` is attached to the "zcrypto" logger by hand, and the presence half is asserted
    before the containment half. `cli.logging.config.configure()` sets `propagate = False` there on
    the CLI's first invocation in the process while caplog's own handler sits on the root, so this
    reads an EMPTY log depending only on what ran earlier in the session -- and an empty log
    contains no key either, which is the whole test passing while looking at nothing."""
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "the-key-value")
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    zcrypto_logger = logging.getLogger("zcrypto")
    zcrypto_logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="zcrypto"):
            result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)])
    finally:
        zcrypto_logger.removeHandler(caplog.handler)
    assert result.exit_code == 1
    assert "KRAKEN_SPOT_API_SECRET" in caplog.text  # the refusal really did reach the log
    assert "the-key-value" not in caplog.text


def _stub_the_button(monkeypatch, seen, *, code: int) -> None:
    """Credentials present, the adapter class and `run_flatten` both replaced by recorders.

    Both are imported INSIDE the command body, so both are attribute lookups on their module at
    call time and `setattr` on the module reaches them."""
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "the-key")
    monkeypatch.setenv("KRAKEN_SPOT_API_SECRET", "the-secret")

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            seen["client_args"] = args
            seen["client_kwargs"] = kwargs

    import nautilus_trader.adapters.kraken as kraken_adapter

    monkeypatch.setattr(kraken_adapter, "KrakenSpotHttpClient", _FakeClient)

    def _fake_run_flatten(client: Any, **kwargs: Any) -> int:
        seen["client"] = client
        seen.update(kwargs)
        return code

    monkeypatch.setattr(flatten, "run_flatten", _fake_run_flatten)


@pytest.mark.parametrize("code", [0, 1, 2, 3])
def test_the_code_run_flatten_returns_is_the_code_the_process_exits_with(monkeypatch, tmp_path, code):
    """The four codes are the command's contract -- 0 flat, 1 refused, 2 something is still open,
    3 the venue could not be read -- and a wrapper, a monitor and an operator all read the process's
    code, never the return value.

    A Typer command body that `return`s the number instead of raising `typer.Exit` exits 0 whatever
    it returned, so 1/2/3 are the fixture values that bite and 0 is the true positive that must
    still pass. Parametrized rather than asserted on one code: a command hardcoding `Exit(2)` would
    pass a single-code test on 2."""
    seen: dict[str, Any] = {}
    _stub_the_button(monkeypatch, seen, code=code)
    result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)])
    assert result.exit_code == code


@pytest.mark.parametrize(("argv", "execute"), [([], False), (["--execute"], True)])
def test_the_typed_state_dir_and_the_execute_flag_are_what_run_flatten_is_handed(monkeypatch, tmp_path, argv, execute):
    """Both parametrizations are needed: a body that hardcodes `execute=False` sends nothing on an
    incident day and passes the flag-less case, and one that hardcodes `True` sends without the
    operator asking and passes the `--execute` case.

    `echo` is asserted to be `typer.echo` ITSELF: `run_flatten` wraps it internally in a guard that
    swallows a dead stdout, so a caller that pre-wraps it double-wraps, and `CliRunner` redirects
    `sys.stdout` -- which makes the module's own `print` default indistinguishable from `typer.echo`
    in captured output. Identity is the only thing that can see the difference here."""
    seen: dict[str, Any] = {}
    _stub_the_button(monkeypatch, seen, code=0)
    state_dir = tmp_path / "engine-state"
    result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(state_dir), *argv])
    assert result.exit_code == 0
    assert seen["state_dir"] == state_dir
    assert seen["execute"] is execute
    assert seen["echo"] is typer.echo


def test_the_client_is_built_key_first_then_secret(monkeypatch, tmp_path):
    """Two DIFFERENT fixture values, so a swapped pair is visible: swapped, every request this
    command makes fails authentication, and it fails on the day the account has to be emptied."""
    seen: dict[str, Any] = {}
    _stub_the_button(monkeypatch, seen, code=0)
    assert _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)]).exit_code == 0
    assert seen["client_args"] == ("the-key", "the-secret")
    assert seen["client_kwargs"] == {}
    assert seen["client"] is not None  # the client the command built is the one run_flatten got
