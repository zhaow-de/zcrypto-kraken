from datetime import datetime

import pytest

from cli.engine.errors import EngineError
from cli.engine.tracking import extract_fills

_BOUNDARY = "2026-09-01T00:00:00+00:00"


def _rec(events, *, symbol="BTC/EUR", side="buy", cycle_ts=_BOUNDARY):
    return {
        "schema_version": 2,
        "cycle_ts": cycle_ts,
        "evaluated_at": cycle_ts,
        "level": "full",
        "reasons": [],
        "inputs": {},
        "plans": [],
        "submitted": [
            {
                "plan_id": "p1",
                "intent_index": 0,
                "client_order_id": "O-1",
                "intent": {
                    "symbol": symbol,
                    "side": side,
                    "action": "open",
                    "mode": "spot",
                    "notional_eur": 50.0,
                    "qty": None,
                    "leverage": None,
                },
                "order": {"qty": 0.001},
                "state": "filled",
                "filled_qty": 0.001,
                "events": events,
            }
        ],
    }


def _fill(**kw):
    base = {
        "event": "fill",
        "at": "2026-09-01T00:01:00+00:00",
        "qty": 0.001,
        "px": 50000.0,
        "fee": 0.05,
        "fee_currency": "EUR",
        "liquidity": "MAKER",
        "trade_id": "T-1",
    }
    base.update(kw)
    return base


def _repair(**kw):
    # The shape `executor._reconcile_adopted_rows` journals: no price, no fee, no trade id.
    base = {"event": "reconciled", "at": "2026-09-01T00:02:00+00:00", "qty": 0.002, "venue_filled_qty": 0.003}
    base.update(kw)
    return base


def test_reads_the_venues_own_uppercase_liquidity_and_the_rows_boundary():
    fills, notes = extract_fills([_rec([_fill()])])
    assert notes == []
    f = fills[0]
    assert (f.base, f.side, f.qty, f.px, f.fee, f.liquidity, f.trade_id) == (
        "BTC",
        "buy",
        0.001,
        50000.0,
        0.05,
        "MAKER",
        "T-1",
    )
    # Attribution is the ROW's boundary, not the fill's wall clock: a fill arriving after the
    # boundary belongs to the decision that produced it.
    assert f.boundary == datetime.fromisoformat(_BOUNDARY)
    assert f.at != f.boundary


def test_a_sell_is_carried_as_a_sell():
    fills, _ = extract_fills([_rec([_fill()], side="sell")])
    assert fills[0].side == "sell"


def test_lowercase_liquidity_is_refused_because_the_ledger_never_writes_it():
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="maker")])])


def test_a_liquidity_the_enum_cannot_name_aborts():
    # `str()` on the pinned IntFlag yields "1" -- this repo shipped exactly that once.
    with pytest.raises(EngineError, match="liquidity"):
        extract_fills([_rec([_fill(liquidity="1")])])


def test_no_liquidity_side_is_counted_but_unpriced_and_never_aborts():
    fills, notes = extract_fills([_rec([_fill(liquidity="NO_LIQUIDITY_SIDE")])])
    assert len(fills) == 1 and fills[0].fee is None
    assert any("NO_LIQUIDITY_SIDE" in n for n in notes)


def test_zeur_is_a_euro():
    fills, notes = extract_fills([_rec([_fill(fee_currency="ZEUR")])])
    assert notes == [] and fills[0].fee == 0.05


def test_a_btc_denominated_fee_disables_pricing_without_aborting():
    fills, notes = extract_fills([_rec([_fill(fee_currency="XXBT")], symbol="ETH/BTC")])
    assert len(fills) == 1 and fills[0].fee is None
    assert any("XXBT" in n for n in notes)


def test_the_btc_quoted_legs_are_excluded_from_the_drift_half_and_counted():
    # select_model_inputs DROPS ETH/BTC and SOL/BTC, so the model's targets are ten EUR bases.
    # Folding such a fill into held["ETH"] would inflate held against a target that never had it.
    fills, notes = extract_fills([_rec([_fill()], symbol="ETH/BTC")])
    assert fills[0].base is None
    assert any("ETH/BTC" in n for n in notes)


def test_a_symbol_outside_the_basket_aborts():
    with pytest.raises(EngineError, match="basket"):
        extract_fills([_rec([_fill()], symbol="PEPE/EUR")])


def test_a_side_outside_buy_sell_aborts():
    with pytest.raises(EngineError, match="side"):
        extract_fills([_rec([_fill()], side="flat")])


def test_every_fill_of_every_row_of_every_record_is_read():
    two_rows = _rec([_fill(trade_id="T-1"), _fill(trade_id="T-2")])
    two_rows["submitted"].append({**two_rows["submitted"][0], "client_order_id": "O-2", "events": [_fill(trade_id="T-3")]})
    fills, _ = extract_fills([two_rows, _rec([_fill(trade_id="T-4")], cycle_ts="2026-09-01T04:00:00+00:00")])
    assert [f.trade_id for f in fills] == ["T-1", "T-2", "T-3", "T-4"]


def test_a_venue_repair_is_real_base_quantity_and_reaches_the_drift_half():
    # `_reconcile_adopted_rows` credits its delta to the row's `filled_qty` -- the only non-fill
    # event that does. Skipping it would make `held` under-report by exactly the repaired amount.
    fills, notes = extract_fills([_rec([_repair()])])
    assert len(fills) == 1
    f = fills[0]
    assert (f.base, f.side, f.qty) == ("BTC", "buy", 0.002)
    # No price and no fee exist for a repair, so it is counted but stays out of the cost blend.
    assert f.px is None and f.fee is None
    assert f.liquidity == "NO_LIQUIDITY_SIDE"
    # Task 5 matches ledger rows by trade_id, so a repair's must be non-empty and unmistakable.
    assert f.trade_id.startswith("reconciled:") and f.trade_id.endswith(":2026-09-01T00:02:00+00:00")
    assert any("repair" in n and "0.002" in n for n in notes)


def test_a_sell_side_repair_is_carried_as_a_sell():
    # `filled_qty` is a magnitude, so the delta is signed by the ORDER's direction, not its own.
    fills, _ = extract_fills([_rec([_repair()], side="sell")])
    assert fills[0].side == "sell"


def test_a_lifecycle_event_that_moves_no_quantity_is_skipped():
    # Every non-quantity event is journaled as `{"type": <class name>, "at": ...}` with NO "event"
    # key at all (executor._on_detached_event, written with add_filled_qty=0.0). Only "fill" and
    # "reconciled" ever move filled_qty.
    accepted = {"type": "OrderAccepted", "at": "2026-09-01T00:00:30+00:00"}
    fills, notes = extract_fills([_rec([accepted, _fill()])])
    assert [f.trade_id for f in fills] == ["T-1"]
    assert notes == []
