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
