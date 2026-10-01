from __future__ import annotations

import io
import json
import os
import re
from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

import cli.engine.command as command
from cli.__main__ import app
from cli.engine.draftplan import (
    BOX_FIRST_DAY,
    BOX_LAST_DAY,
    EXIT_DAYS,
    INTENT_TIME_BOX,
    LEGS,
    RESTART_DAY,
    Constraints,
    DraftPlanError,
    LegDecision,
    assemble_plans,
    decide_leg,
    draft,
    drop_slots,
    fetch_ticker,
    leg_weights,
    maintenance_conflicts,
    mid_prices,
    next_plan_id,
    parse_balance_export,
    refuse_open_margin_positions,
    ruling_refusals,
    trim_buys_to_cash,
)
from cli.engine.journal import CycleRecord, SnapshotEntry, to_json
from cli.engine.probeplan import parse_plan
from cli.engine.store import BASKET, PAIR_KEYS

UTC = timezone.utc
BOUNDARY = datetime.combine(BOX_FIRST_DAY, time(12), tzinfo=UTC)
NOW = BOUNDARY + timedelta(minutes=12)
DAY = BOX_FIRST_DAY.isoformat()
EVE = BOX_FIRST_DAY - timedelta(days=1)
ORDERMIN = {
    "BTC/EUR": 5e-05,
    "ETH/EUR": 0.001,
    "SOL/EUR": 0.06,
    "XRP/EUR": 1.65,
    "DOGE/EUR": 50.0,
    "LTC/EUR": 0.1,
    "ADA/EUR": 20.0,
    "AVAX/EUR": 0.5,
    "DOT/EUR": 3.9,
}
PRICES = {
    "BTC/EUR": 73752.8,
    "ETH/EUR": 2366.65,
    "SOL/EUR": 103.87,
    "XRP/EUR": 1.31495,
    "DOGE/EUR": 0.0834301,
    "LTC/EUR": 59.23,
    "ADA/EUR": 0.219651,
    "AVAX/EUR": 9.691,
    "DOT/EUR": 1.0852,
}
FEED_URL = "https://status.kraken.com/api/v2/scheduled-maintenances.json"
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
runner = CliRunner()


def _record(targets: dict[str, float] | None = None, *, cycle_ts: datetime = BOUNDARY) -> CycleRecord:
    four_hour_last = cycle_ts - timedelta(hours=4)
    daily_last = cycle_ts.replace(hour=0) - timedelta(days=1)
    snapshots = tuple(
        SnapshotEntry("BTC/EUR", grid, 10, datetime(2020, 1, 1, tzinfo=UTC), last, "0" * 64, f"snap/{grid}.parquet")
        for grid, last in (("240", four_hour_last), ("1440", daily_last))
    )
    return CycleRecord(
        schema_version=2,
        cycle_ts=cycle_ts,
        snapshots=snapshots,
        final_targets={symbol: 0.0 for symbol in BASKET} | (targets or {}),
        started_at=cycle_ts + timedelta(seconds=90),
        completed_at=cycle_ts + timedelta(seconds=102),
        code_version="test",
        builder_path="fast",
    )


def _id(n: int, day: date = BOX_FIRST_DAY) -> str:
    return f"r2-{day:%Y%m%d}-{n}"


def _noon(day: date) -> datetime:
    return datetime.combine(day, time(12), tzinfo=UTC)


def _venue(*, cycle_ts: datetime = BOUNDARY, balances: dict | None = None, positions: dict | None = None) -> dict:
    instruments = {
        symbol: {
            "symbol": symbol,
            "instrument_id": f"{symbol}.KRAKEN",
            "ordermin": ORDERMIN.get(symbol, 0.001),
            "costmin": 0.45,
            "costmin_quote": "EUR",
            "lot_step": 1e-08,
            "tick_size": 0.01,
            "costmin_source": "snapshot-constant",
        }
        for symbol in BASKET
    }
    return {
        "schema_version": 2,
        "cycle_ts": cycle_ts.isoformat(),
        "code_version": "test",
        "status": "ok",
        "state": {
            "snapshot_at": (cycle_ts + timedelta(seconds=90)).isoformat(),
            "instruments": instruments,
            "positions": {symbol: 0 for symbol in BASKET} | (positions or {}),
            "balances": balances if balances is not None else {"EUR": 1050.0},
        },
        "concordance": {"ok": True, "failures": []},
    }


def _export(eur: float = 1050.0, **held: float) -> dict:
    return {"EUR": {"balance": eur, "hold_trade": 0.0}} | {code: {"balance": qty, "hold_trade": 0.0} for code, qty in held.items()}


def _ticker(prices: dict[str, float] = PRICES) -> dict:
    return {PAIR_KEYS[symbol]: {"a": [repr(p), "1", "1.000"], "b": [repr(p), "1", "1.000"]} for symbol, p in prices.items()}


def _maintenance(name: str, begins: str, ends: str, components: tuple[str, ...] = ()) -> dict:
    return {
        "name": name,
        "status": "scheduled",
        "scheduled_for": begins,
        "scheduled_until": ends,
        "components": [{"name": c} for c in components],
    }


def _feed(*entries: dict) -> dict:
    funding = _maintenance("Banking Circle Funding Maintenance", f"{DAY}T13:00:00.000Z", f"{DAY}T13:30:00.000Z")
    return {"page": {"id": "page"}, "scheduled_maintenances": [funding, *entries]}


def _draft(
    targets=None,
    *,
    boundary=BOUNDARY,
    record=None,
    venue=None,
    export=None,
    positions=None,
    rows=(),
    now=None,
    written=None,
    positions_written=None,
    feed=None,
    **options,
):
    now = now if now is not None else boundary + timedelta(minutes=12)
    return draft(
        record=record if record is not None else _record(targets, cycle_ts=boundary),
        venue=venue if venue is not None else _venue(cycle_ts=boundary),
        balances=export if export is not None else _export(),
        balances_written_at=written if written is not None else now - timedelta(minutes=2),
        positions=positions if positions is not None else {},
        positions_written_at=positions_written if positions_written is not None else now - timedelta(minutes=2),
        log_rows=list(rows),
        now=now,
        read_ticker=_ticker,
        read_feed=lambda: feed if feed is not None else _feed(),
        **options,
    )


def _leg(result, symbol: str) -> LegDecision:
    return next(d for d in result.decisions if d.symbol == symbol)


def _decide(symbol="SOL/EUR", *, weight=0.0, price=100.0, ordermin=0.06, lot_step=1e-08, held=0.0, venue_b=0.0):
    return decide_leg(
        symbol,
        weight=weight,
        price=price,
        constraints=Constraints(ordermin=ordermin, lot_step=lot_step),
        kraken_held=held,
        engine_held=held,
        venue_b=venue_b,
    )


def _placed(symbol: str, side: str, *, notional: float | None = None, qty: float | None = None, price=100.0, ordermin=0.001):
    return LegDecision(
        symbol=symbol,
        weight=0.0,
        target_eur=0.0,
        kraken_held=0.0,
        engine_held=0.0,
        venue_b=0.0,
        price=price,
        ordermin=ordermin,
        delta_eur=0.0,
        outcome="placed",
        side=side,
        qty=qty,
        notional_eur=notional,
    )


# ---- one leg -----------------------------------------------------------------------------------


def test_a_sell_is_floored_to_the_lot_step():
    leg = _decide(weight=87.65433 / 720, held=1.0, lot_step=0.001)

    assert (leg.outcome, leg.side, leg.qty) == ("placed", "sell", 0.123)


def test_a_sell_leaving_less_than_ordermin_sells_the_whole_leg():
    leg = _decide(weight=3.0 / 720, held=0.1)

    assert (leg.outcome, leg.qty) == ("placed", 0.1)
    assert "whole leg" in leg.reason


def test_a_sell_under_ordermin_carries():
    leg = _decide(weight=8.0 / 720, held=0.1)

    assert (leg.outcome, leg.side, leg.qty) == ("carried", "sell", None)
    assert "under ordermin" in leg.reason


@pytest.mark.parametrize(("delta", "outcome"), [(5.24, "carried"), (5.30, "placed")])
def test_a_buy_needs_1_05_times_ordermin_at_the_price(delta, outcome):
    leg = _decide("DOGE/EUR", weight=delta / 720, price=0.1, ordermin=50.0)

    assert leg.outcome == outcome
    assert leg.buy_floor == pytest.approx(5.25)
    if outcome == "carried":
        assert "buy 5.2400 EUR is under the buy floor 5.2500 EUR" in leg.reason


def test_the_buy_floor_is_read_on_the_delta_and_the_buy_then_floored_to_the_cent():
    leg = _decide("DOGE/EUR", weight=5.2506 / 720, price=0.10001, ordermin=50.0)

    assert leg.buy_floor == pytest.approx(5.250525)
    assert (leg.outcome, leg.notional_eur) == ("placed", 5.25)


@pytest.mark.parametrize(("delta", "outcome"), [(0.49, "carried"), (0.51, "placed")])
def test_a_buy_needs_fifty_cents_where_ordermin_asks_less(delta, outcome):
    leg = _decide("BTC/EUR", weight=delta / 720, price=4000.0, ordermin=5e-05)

    assert leg.buy_floor == 0.50
    assert leg.outcome == outcome


def test_a_buy_is_floored_to_the_cent():
    leg = _decide("BTC/EUR", weight=0.0177, price=73752.8, ordermin=5e-05)

    assert (leg.outcome, leg.notional_eur) == ("placed", 12.74)


def test_a_whole_cent_buy_keeps_its_cent_under_float_noise():
    assert 720 * 0.03 < 21.60

    leg = _decide("LTC/EUR", weight=0.03, price=50.0, ordermin=0.01)

    assert (leg.outcome, leg.notional_eur) == ("placed", 21.60)


@pytest.mark.parametrize(("venue_b", "outcome"), [(0.05, "carried"), (0.0, "placed"), (0.1, "placed")])
def test_a_sell_the_venue_record_refutes_carries(venue_b, outcome):
    leg = _decide(held=0.1, venue_b=venue_b)

    assert leg.outcome == outcome
    if outcome == "carried":
        assert "b 0.05 is under the sell qty 0.1" in leg.reason
        assert "first boundary record written after the restart" in leg.reason


def test_a_negative_target_is_read_as_zero_and_sells_the_leg_whole():
    leg = _decide(weight=-0.01, held=0.1)

    assert leg.target_eur == 0.0
    assert (leg.outcome, leg.side, leg.qty) == ("placed", "sell", 0.1)


def test_a_negative_target_on_a_flat_leg_shorts_nothing():
    leg = _decide(weight=-0.01, held=0.0)

    assert (leg.outcome, leg.side) == ("on-target", None)


# ---- cash, the cap and the split -----------------------------------------------------------------


def test_buys_beyond_free_eur_less_five_trim_from_the_smallest():
    buys = [
        _placed("BTC/EUR", "buy", notional=20.0),
        _placed("ETH/EUR", "buy", notional=4.0),
        _placed("SOL/EUR", "buy", notional=3.0, ordermin=0.06),
    ]

    out = {d.symbol: d for d in trim_buys_to_cash(buys, free_eur=30.0)}

    assert (out["SOL/EUR"].outcome, out["SOL/EUR"].notional_eur) == ("carried", None)
    assert (out["ETH/EUR"].notional_eur, out["BTC/EUR"].notional_eur) == (4.0, 20.0)


def test_a_trim_that_leaves_a_buy_above_its_floor_keeps_the_rest_of_it():
    buys = [_placed("BTC/EUR", "buy", notional=20.0), _placed("ETH/EUR", "buy", notional=4.0)]

    out = {d.symbol: d for d in trim_buys_to_cash(buys, free_eur=28.0)}

    assert (out["ETH/EUR"].outcome, out["ETH/EUR"].notional_eur) == ("placed", 3.0)
    assert "trimmed by 1.00 EUR" in out["ETH/EUR"].reason
    assert out["BTC/EUR"].notional_eur == 20.0


def test_the_cash_budget_keeps_its_cent_under_float_noise():
    assert 1028.86 - 5 < 1023.86

    out = trim_buys_to_cash([_placed("BTC/EUR", "buy", notional=1023.86)], free_eur=1028.86)

    assert (out[0].outcome, out[0].notional_eur) == ("placed", 1023.86)


def test_no_buy_survives_free_eur_under_the_reserve_and_sells_are_untouched():
    legs = [_placed("BTC/EUR", "buy", notional=20.0), _placed("SOL/EUR", "sell", qty=0.1)]

    out = {d.symbol: d for d in trim_buys_to_cash(legs, free_eur=4.0)}

    assert out["BTC/EUR"].outcome == "carried"
    assert out["SOL/EUR"].outcome == "placed"


def test_plans_take_sells_first_and_at_most_three_intents():
    legs = [
        _placed("BTC/EUR", "buy", notional=10.0),
        _placed("ETH/EUR", "buy", notional=20.0),
        _placed("SOL/EUR", "sell", qty=0.05),
        _placed("XRP/EUR", "sell", qty=10.0, price=1.0),
        _placed("ADA/EUR", "buy", notional=5.0),
    ]

    plans = assemble_plans(legs)

    assert [[(d.symbol, d.side) for d in plan] for plan in plans] == [
        [("XRP/EUR", "sell"), ("SOL/EUR", "sell"), ("ETH/EUR", "buy")],
        [("BTC/EUR", "buy"), ("ADA/EUR", "buy")],
    ]


def test_a_plan_closes_before_it_would_pass_95_eur():
    legs = [
        _placed("BTC/EUR", "buy", notional=50.0),
        _placed("ETH/EUR", "buy", notional=40.0),
        _placed("SOL/EUR", "sell", qty=0.05),
    ]

    plans = assemble_plans(legs)

    assert [[d.symbol for d in plan] for plan in plans] == [["SOL/EUR", "BTC/EUR", "ETH/EUR"]]
    assert [[d.symbol for d in plan] for plan in assemble_plans([*legs, _placed("ADA/EUR", "buy", notional=1.0)])] == [
        ["SOL/EUR", "BTC/EUR", "ETH/EUR"],
        ["ADA/EUR"],
    ]
    assert [[d.symbol for d in plan] for plan in assemble_plans(legs[:2] + [_placed("ADA/EUR", "buy", notional=5.01)])] == [
        ["BTC/EUR", "ETH/EUR"],
        ["ADA/EUR"],
    ]


def test_an_intent_over_the_cap_on_its_own_is_refused():
    with pytest.raises(DraftPlanError, match="over the 95 EUR plan cap on its own"):
        assemble_plans([_placed("BTC/EUR", "buy", notional=95.01)])


# ---- the ruling's refusals on a plan -----------------------------------------------------------------


def _plan(*intents: dict, created_at: datetime = NOW):
    return parse_plan(json.dumps({"plan_id": _id(1), "created_at": created_at.isoformat(), "intents": list(intents)}))


def _buy(symbol="BTC/EUR", notional=10.0, **extra) -> dict:
    return {"symbol": symbol, "side": "buy", "action": "open", "mode": "execute", "notional_eur": notional} | extra


def _sell(symbol="SOL/EUR", qty=0.1) -> dict:
    return {"symbol": symbol, "side": "sell", "action": "close", "mode": "execute", "qty": qty}


def test_a_plan_inside_the_ruling_draws_no_refusal():
    assert ruling_refusals(_plan(_sell(), _buy(), _buy("ETH/EUR")), PRICES) == []


@pytest.mark.parametrize(
    ("intents", "fragment"),
    [
        ((_buy("LINK/EUR"),), "LINK/EUR is not one of the nine legs"),
        ((_buy(leverage=2),), "leverage 2 -- every intent is spot"),
        ((_buy(notional=50.0), _buy("ETH/EUR", notional=45.01)), "plan EUR 95.01 is over the 95 EUR cap"),
        ((_sell(qty=0.6), _buy(notional=50.0)), "plan EUR 112.32 is over the 95 EUR cap"),
        ((_buy(), _buy("ETH/EUR"), _buy("ADA/EUR"), _buy("DOT/EUR")), "4 intents, over the 3"),
        ((_buy(), _sell()), "a buy precedes a sell"),
        ((_buy(side="sell"),), "a sell open"),
        ((_buy(mode="rest-cancel"),), "mode 'rest-cancel'"),
    ],
)
def test_the_ruling_refuses(intents, fragment):
    assert any(fragment in reason for reason in ruling_refusals(_plan(*intents), PRICES))


def test_the_ruling_reads_a_plans_last_drop_by_its_own_intent_count():
    end = BOUNDARY + timedelta(hours=3)
    created = _at(BOUNDARY, "14:15:01")

    assert ruling_refusals(_plan(_sell(), _buy(), created_at=created), PRICES, window_end=end) == []
    assert ruling_refusals(_plan(_sell(), _buy(), _buy("ETH/EUR"), created_at=created), PRICES, window_end=end) == [
        "a plan of 3 intent(s) created at 14:15:01Z is past its last drop at 14:15Z"
    ]


def test_the_last_drop_gives_each_intent_the_executors_time_box():
    from cli.engine.executor import _TIME_BOX

    assert INTENT_TIME_BOX == _TIME_BOX


# ---- the plan id, the windows and the inputs ------------------------------------------------------------


def test_the_plan_id_counts_up_within_the_day_from_the_decision_log():
    rows = [{"plan_id": _id(1)}, {"plan_id": _id(2)}, {"plan_id": None}, {"plan_id": _id(7, EVE)}, {}]

    assert next_plan_id(rows, BOX_FIRST_DAY) == _id(3)
    assert next_plan_id(rows, BOX_FIRST_DAY + timedelta(days=1)) == _id(1, BOX_FIRST_DAY + timedelta(days=1))


@pytest.mark.parametrize(
    ("entry", "conflict"),
    [
        (
            _maintenance("Order Entry System Maintenance", f"{DAY}T14:50:00Z", f"{DAY}T15:30:00Z", ("Website", "WebSocket")),
            True,
        ),
        (_maintenance("Derivatives Platform Maintenance", f"{DAY}T11:00:00Z", f"{DAY}T12:10:00Z", ("REST API",)), True),
        (_maintenance("Scheduled maintenance for REST and WebSocket", f"{DAY}T13:20:00Z", f"{DAY}T13:25:00Z"), True),
        (_maintenance("Kraken Website and API Maintenance", f"{DAY}T15:01:00Z", f"{DAY}T15:16:00Z", ("REST",)), False),
        (_maintenance("Kraken Website and API Maintenance", f"{DAY}T15:00:00Z", f"{DAY}T15:16:00Z", ("REST",)), True),
        (_maintenance("Restricted funding restart", f"{DAY}T14:00:00Z", f"{DAY}T14:30:00Z", ("Interest",)), False),
    ],
)
def test_a_websocket_or_rest_window_overlapping_the_drop_window_conflicts(entry, conflict):
    slots = drop_slots(BOUNDARY)

    assert bool(maintenance_conflicts(_feed(entry), slots[0][0], slots[-1][1])) is conflict


def test_a_maintenance_overlapping_the_drop_window_refuses_the_draft():
    entry = _maintenance("Order Entry System Maintenance", f"{DAY}T14:50:00Z", f"{DAY}T15:30:00Z", ("WebSocket",))

    with pytest.raises(DraftPlanError, match="Order Entry System Maintenance"):
        _draft({"BTC/EUR": 0.0177}, feed=_feed(entry))


@pytest.mark.parametrize(
    ("feed", "fragment"),
    [
        ({"scheduled_maintenances": []}, "lists no maintenances"),
        ({"page": {}}, "lists no maintenances"),
        (_feed(_maintenance("REST maintenance", "soon", "later")), "carries no readable window"),
        (_feed(_maintenance("REST maintenance", f"{DAY}T14:00:00", f"{DAY}T15:00:00")), "carries no offset"),
    ],
)
def test_a_feed_that_cannot_clear_the_window_refuses(feed, fragment):
    with pytest.raises(DraftPlanError, match=fragment):
        maintenance_conflicts(feed, BOUNDARY, BOUNDARY + timedelta(hours=3))


def test_the_16z_fallback_has_its_own_drop_window_and_other_boundaries_have_none():
    fallback = drop_slots(BOUNDARY + timedelta(hours=4))

    assert [(a.strftime("%H:%M"), b.strftime("%H:%M")) for a, b in fallback] == [("16:10", "17:15"), ("17:30", "19:00")]
    with pytest.raises(DraftPlanError, match="no drop window follows"):
        drop_slots(BOUNDARY - timedelta(hours=4))


def test_a_record_older_than_the_latest_boundary_is_refused():
    with pytest.raises(DraftPlanError, match=f"older than the latest boundary {DAY} 16:00Z"):
        _draft({"BTC/EUR": 0.0177}, now=BOUNDARY + timedelta(hours=4, minutes=12))


def test_the_16z_record_drafts_inside_its_own_window():
    fallback = BOUNDARY + timedelta(hours=4)

    result = _draft(
        record=_record({"BTC/EUR": 0.0177}, cycle_ts=fallback),
        venue=_venue(cycle_ts=fallback),
        now=fallback + timedelta(minutes=12),
    )

    assert result.plan_id == _id(1)


@pytest.mark.parametrize(
    ("minutes", "fragment"),
    [(31, "31 minutes old, over 30"), (29, None), (-10, "dated 10 minutes after now"), (-0.5, None)],
)
def test_a_balance_export_over_30_minutes_old_or_dated_after_now_is_refused(minutes, fragment):
    written = NOW - timedelta(minutes=minutes)
    if fragment:
        with pytest.raises(DraftPlanError, match=fragment):
            _draft({"BTC/EUR": 0.0177}, written=written)
    else:
        assert _draft({"BTC/EUR": 0.0177}, written=written).plan_text is not None


@pytest.mark.parametrize(
    ("minutes", "fragment"),
    [(31, "the positions export is 31 minutes old, over 30"), (29, None), (-10, "the positions export is dated 10 minutes after")],
)
def test_a_positions_export_over_30_minutes_old_or_dated_after_now_is_refused(minutes, fragment):
    written = NOW - timedelta(minutes=minutes)
    if fragment:
        with pytest.raises(DraftPlanError, match=fragment):
            _draft({"BTC/EUR": 0.0177}, positions_written=written)
    else:
        assert _draft({"BTC/EUR": 0.0177}, positions_written=written).plan_text is not None


def _at(boundary: datetime, clock: str) -> datetime:
    return datetime.combine(boundary.date(), time.fromisoformat(clock), tzinfo=UTC)


@pytest.mark.parametrize(
    ("hour", "clock", "fragment"),
    [
        (12, "14:45:01", "it is 14:45:01Z, past 14:45Z, the last drop of a one-intent plan in the window after the 12Z record"),
        (12, "15:00:00", "it is 15:00:00Z, past 14:45Z"),
        (16, "18:45:01", "it is 18:45:01Z, past 18:45Z, the last drop of a one-intent plan in the window after the 16Z record"),
        (16, "19:30:00", "it is 19:30:00Z, past 18:45Z"),
    ],
)
def test_a_draft_past_a_one_intent_plans_last_drop_is_refused(hour, clock, fragment):
    boundary = BOUNDARY.replace(hour=hour)

    with pytest.raises(DraftPlanError, match=fragment):
        _draft(record=_record({"BTC/EUR": 0.0177}, cycle_ts=boundary), venue=_venue(cycle_ts=boundary), now=_at(boundary, clock))


@pytest.mark.parametrize(
    ("venue", "fragment"),
    [
        (_venue(balances={"EUR": 1050.0, "SOL": "abc"}), "SOL balance 'abc' is unreadable"),
        (_venue(balances={"EUR": 1050.0, "XDG": "nan"}), "XDG balance 'nan' is unreadable"),
        (_venue(positions={"BTC/EUR": "x"}), "BTC/EUR position 'x' is unreadable"),
        (_venue(positions={"SOL/EUR": "nan"}), "SOL/EUR position 'nan' is unreadable"),
        (
            {"schema_version": 2, "cycle_ts": BOUNDARY.isoformat(), "code_version": "test", "status": "error", "error": "down"},
            "not an ok schema-2 snapshot (status 'error'",
        ),
    ],
)
def test_a_venue_record_the_draft_cannot_read_b_or_a_legs_position_from_is_refused(venue, fragment):
    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _draft({"BTC/EUR": 0.0177}, venue=venue)


def test_a_venue_record_of_another_boundary_is_refused():
    with pytest.raises(DraftPlanError, match="pass one boundary's pair"):
        _draft({"BTC/EUR": 0.0177}, venue=_venue(cycle_ts=BOUNDARY - timedelta(hours=4)))


_EXPORT_AS_PRINTED = '{"BTC":{"balance":0.0,"hold_trade":0.0},"EUR":{"balance":98.8386,"hold_trade":0.0},"EURC":{"balance":0.0,"hold_trade":0.0},"SOL":{"balance":0.0,"hold_trade":0.0}}'
_EXPORT_WITH_A_RESTING_ORDER = '{"BTC":{"balance":0.0,"hold_trade":0.0},"EUR":{"balance":99.0369,"hold_trade":3.5548}}'


def test_the_extended_balance_export_as_it_prints_is_read():
    export = parse_balance_export(json.loads(_EXPORT_AS_PRINTED))

    assert (export.free_eur, export.outside) == (98.8386, {})
    assert set(export.held.values()) == {0.0}


def test_the_export_is_read_in_either_kraken_spelling():
    export = parse_balance_export(
        {
            "ZEUR": {"balance": "98.0951", "hold_trade": "0.0000"},
            "XXBT": {"balance": "0.0001000000", "hold_trade": "0.0000000000"},
            "XDG": {"balance": 60.5, "hold_trade": 0.0},
            "LINK": {"balance": 0.4, "hold_trade": 0.0},
            "ETH.F": {"balance": 0.0, "hold_trade": 0.0},
        }
    )

    assert export.free_eur == 98.0951
    assert (export.held["BTC"], export.held["DOGE"], export.held["SOL"]) == (0.0001, 60.5, 0.0)
    assert export.outside == {"LINK": 0.4}


@pytest.mark.parametrize(
    ("doc", "fragment"),
    [
        ({"error": "auth", "message": "Invalid key"}, "an error answer, not balances: Invalid key"),
        ({"EUR": 1050.0}, "export the extended balance"),
        ({"EUR": {"balance": 1050.0, "hold_trade": 2.25}}, "the previous plan is not terminal"),
        ({"EUR": {"balance": 1050.0}, "SOL": {"balance": 0.1, "hold_trade": 0.1}}, "the previous plan is not terminal"),
        ({"EUR": {"balance": 1050.0}, "XXBT": {"balance": 0.1}, "BTC": {"balance": 0.1}}, "lists BTC twice"),
        ({"SOL": {"balance": 0.1}}, "no EUR row"),
        ({"EUR": {"balance": True}}, "EUR balance is not a number: True"),
        ({"EUR": {"balance": -1.0}}, "EUR balance is not a finite non-negative amount"),
        ({"EUR": {"balance": "nan"}}, "EUR balance is not a finite non-negative amount"),
        ({"error": [], "result": {"ZEUR": {"balance": "1050.0"}}}, "a REST answer envelope"),
        ({"EUR": {"balance": 1050.0}, "SOL.F": {"balance": 0.2}}, "SOL.F holds 0.2 SOL outside the spot wallet"),
        ({"EUR": {"balance": 1050.0}, "DOT28.S": {"balance": 4.0}}, "DOT28.S holds 4 DOT outside the spot wallet"),
        (json.loads(_EXPORT_WITH_A_RESTING_ORDER), "EUR has 3.5548 held against a resting order"),
    ],
)
def test_an_export_the_draft_cannot_trust_is_refused(doc, fragment):
    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        parse_balance_export(doc)


_POSITIONS_AS_PRINTED = '{"TU7O4B-NJL5A-GY5DRP":{"asset_class":"forex","cost":6.156,"fee":0.05048,"margin":3.078,"misc":"","oflags":"","ordertxid":"OAHUQV-4Z3XL-7N4LUX","ordertype":"market","pair":"SOLEUR","posstatus":"open","rollovertm":"1790298560","side":"buy","terms":"0.0200% per 4 hours","time":"1790284160.725662","vol":0.06,"vol_closed":0.0}}'


@pytest.mark.parametrize(
    ("doc", "fragment"),
    [
        (
            json.loads(_POSITIONS_AS_PRINTED),
            "Kraken reports an open margin position TU7O4B-NJL5A-GY5DRP (SOLEUR buy 0.06): the box is spot only",
        ),
        ({"TXID-A": {"pair": "XXBTZEUR"}}, "position TXID-A (XXBTZEUR None None): the box is spot only"),
        ({"TXID-A": {"pair": "XXBTZEUR"}, "TXID-B": 1}, "not the position map the open-positions export prints: TXID-B carries no"),
        ({"result": {}}, "not the position map the open-positions export prints: result carries no position's pair"),
        ({"error": ""}, "not the position map the open-positions export prints: error carries no position's pair"),
        ({"error": "auth", "message": "Invalid key"}, "the positions export is an error answer, not positions: Invalid key"),
        ({"error": ["EAPI:Invalid key"]}, "the positions export is an error answer, not positions: ['EAPI:Invalid key']"),
        ({"error": [], "result": {}}, "a REST answer envelope {error, result}"),
        ([], "must be a JSON object of position id -> position, empty when nothing is open"),
        ("{}", "must be a JSON object"),
    ],
)
def test_a_positions_export_that_does_not_show_the_account_spot_only_is_refused(doc, fragment):
    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        refuse_open_margin_positions(doc)
    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _draft({"BTC/EUR": 0.0177}, positions=doc)


def test_the_positions_export_with_nothing_open_is_an_empty_object():
    assert refuse_open_margin_positions(json.loads("{}\n")) is None


@pytest.mark.parametrize(("bid", "ask"), [("104.0", "103.9"), ("0", "103.9"), ("nan", "103.9")])
def test_a_touch_that_is_not_a_market_is_refused(bid, ask):
    ticker = _ticker()
    ticker[PAIR_KEYS["SOL/EUR"]] = {"a": [ask, "1", "1.000"], "b": [bid, "1", "1.000"]}

    with pytest.raises(DraftPlanError, match="SOL/EUR touch is not a market"):
        mid_prices(ticker)


def test_a_record_without_schema_2_targets_for_every_leg_is_refused():
    record = _record({"BTC/EUR": 0.0177})

    with pytest.raises(DraftPlanError, match="schema 1"):
        leg_weights(replace(record, schema_version=1))
    with pytest.raises(DraftPlanError, match="no target for DOT/EUR"):
        leg_weights(replace(record, final_targets={k: v for k, v in record.final_targets.items() if k != "DOT/EUR"}))


def test_the_ticker_is_read_for_the_nine_legs_and_an_error_answer_refuses():
    asked = []

    def opener(url, timeout):
        asked.append(url)
        return io.BytesIO(json.dumps({"error": ["EGeneral:Too many requests"]}).encode())

    with pytest.raises(DraftPlanError, match="Too many requests"):
        fetch_ticker(opener=opener)
    assert asked == [f"https://api.kraken.com/0/public/Ticker?pair={','.join(PAIR_KEYS[s] for s in LEGS)}"]


# ---- the whole draft ---------------------------------------------------------------------------------


TARGETS = {"BTC/EUR": 0.0177, "ETH/EUR": 0.0176, "SOL/EUR": -0.01, "DOGE/EUR": 0.002, "ADA/EUR": 0.01, "LINK/EUR": 0.05}


def _book_draft(boundary=BOUNDARY, **kwargs):
    venue = _venue(cycle_ts=boundary, balances={"EUR": 1000.0, "SOL": 0.12}, positions={"SOL/EUR": 0.12})
    return _draft(TARGETS, boundary=boundary, venue=venue, export=_export(1000.0, SOL=0.12), **kwargs)


def test_the_draft_places_sells_first_and_queues_what_a_plan_cannot_carry():
    result = _book_draft()

    plan = parse_plan(result.plan_text)
    assert plan.plan_id == _id(1)
    assert plan.created_at == NOW
    assert [(i.symbol, i.side, i.action, i.qty, i.notional_eur, i.leverage) for i in plan.intents] == [
        ("SOL/EUR", "sell", "close", 0.12, None, None),
        ("BTC/EUR", "buy", "open", None, 12.74, None),
        ("ETH/EUR", "buy", "open", None, 12.67, None),
    ]
    assert _leg(result, "ADA/EUR").outcome == "queued"
    assert _leg(result, "DOGE/EUR").outcome == "carried"
    assert _leg(result, "XRP/EUR").outcome == "on-target"
    assert "LINK/EUR" not in {d.symbol for d in result.decisions}
    assert ruling_refusals(plan, PRICES) == []


def test_the_draft_writes_one_decision_row_per_leg():
    result = _book_draft(rows=[{"plan_id": _id(1)}])

    assert [row["symbol"] for row in result.rows] == list(LEGS)
    sol = next(row for row in result.rows if row["symbol"] == "SOL/EUR")
    expected = {
        "cycle_ts": BOUNDARY.isoformat(),
        "minutes_after_boundary": 12,
        "weight": -0.01,
        "target_eur": 0.0,
        "kraken_held": 0.12,
        "engine_held": 0.12,
        "venue_b": 0.12,
        "outcome": "placed",
        "side": "sell",
        "qty": 0.12,
        "plan_id": _id(2),
    }
    assert {key: sol[key] for key in expected} == expected
    assert {row["plan_id"] for row in result.rows if row["outcome"] != "placed"} == {None}


@pytest.mark.parametrize(
    ("previous", "fragment"), [(0.05, "x2.15 -- FLAGGED"), (0.08, "x1.34"), (0.2, "x0.54 -- FLAGGED"), (0.0, "xinf -- FLAGGED")]
)
def test_a_gross_jump_against_the_previous_attended_record_is_flagged(previous, fragment):
    rows = [
        {"cycle_ts": _noon(EVE - timedelta(days=1)).isoformat(), "record_gross": 9.0},
        {"cycle_ts": _noon(EVE).isoformat(), "record_gross": previous},
        {"cycle_ts": BOUNDARY.isoformat(), "record_gross": 9.0},
    ]

    report = _book_draft(rows=rows).report

    assert f"gross 0.1073 against {previous:.4f} at {EVE} 12:00Z: {fragment}" in report
    assert fragment.endswith("FLAGGED") is ("FLAGGED" in report)


def _placed_row(symbol: str, plan_id: str, drafted_at: datetime = NOW) -> dict:
    return {"symbol": symbol, "outcome": "placed", "plan_id": plan_id, "drafted_at": drafted_at.isoformat()}


def test_a_leg_a_plan_of_today_carried_is_never_drafted_again_that_day():
    rows = [_placed_row("SOL/EUR", _id(1)), _placed_row("BTC/EUR", _id(1, EVE), NOW - timedelta(days=1))]

    result = _book_draft(rows=rows)

    sol = _leg(result, "SOL/EUR")
    assert (sol.outcome, sol.qty) == ("carried", None)
    assert sol.reason == f"{_id(1)} carried it earlier today; never re-placed the same day"
    assert result.plan_id == _id(2)
    assert [i.symbol for i in parse_plan(result.plan_text).intents] == ["BTC/EUR", "ETH/EUR", "ADA/EUR"]


def test_a_discarded_plan_frees_its_legs():
    rows = [_placed_row("SOL/EUR", _id(1)), _placed_row("BTC/EUR", _id(2))]

    result = _book_draft(rows=rows, discard=_id(2))

    assert result.rows[0] | {"drafted_at": None} == {
        "drafted_at": None,
        "plan_id": _id(2),
        "outcome": "discarded",
        "reason": "never placed",
    }
    assert [row["symbol"] for row in result.rows[1:]] == list(LEGS)
    assert (_leg(result, "SOL/EUR").outcome, _leg(result, "BTC/EUR").outcome) == ("carried", "placed")
    assert result.plan_id == _id(3)
    assert _leg(_book_draft(rows=[*rows, result.rows[0]]), "BTC/EUR").outcome == "placed"


def test_any_plan_of_today_not_already_discarded_can_be_discarded():
    rows = [
        _placed_row("SOL/EUR", _id(1)),
        _placed_row("BTC/EUR", _id(2)),
        _placed_row("ETH/EUR", _id(1, EVE), NOW - timedelta(days=1)),
    ]

    earlier = _book_draft(rows=rows, discard=_id(1))

    assert (_leg(earlier, "SOL/EUR").outcome, _leg(earlier, "BTC/EUR").outcome) == ("placed", "carried")
    assert earlier.plan_id == _id(3)
    with pytest.raises(DraftPlanError, match=re.escape(f"{_id(1)} is not one of today's plans") + ".*" + re.escape(f"({_id(2)})")):
        _book_draft(rows=[*rows, earlier.rows[0]], discard=_id(1))
    with pytest.raises(DraftPlanError, match=re.escape(f"({_id(1)}, {_id(2)})")):
        _book_draft(rows=rows, discard=_id(1, EVE))
    with pytest.raises(DraftPlanError, match=r"\(none\) -- a plan is discarded on the day it was drafted, and once"):
        _book_draft(discard=_id(1))


_HELD = {"BTC": 0.0002, "ETH": 0.005, "SOL": 0.1, "XRP": 10.0, "DOGE": 100.0, "LTC": 0.2, "ADA": 50.0, "AVAX": 1.0, "DOT": 3.0}


EXIT_BOUNDARY = _noon(EXIT_DAYS[0])


def test_the_exit_sells_every_held_leg_whole_and_buys_nothing():
    result = _draft(
        {symbol: 0.05 for symbol in LEGS},
        boundary=EXIT_BOUNDARY,
        venue=_venue(cycle_ts=EXIT_BOUNDARY, balances={"EUR": 900.0} | _HELD),
        export=_export(900.0, **_HELD),
        exiting=True,
    )

    plan = parse_plan(result.plan_text)
    assert [(i.symbol, i.side, i.qty) for i in plan.intents] == [
        ("BTC/EUR", "sell", 0.0002),
        ("XRP/EUR", "sell", 10.0),
        ("LTC/EUR", "sell", 0.2),
    ]
    assert {d.side for d in result.decisions} == {"sell"}
    assert {d.symbol: d.outcome for d in result.decisions if d.outcome != "queued"} == {
        "BTC/EUR": "placed",
        "XRP/EUR": "placed",
        "LTC/EUR": "placed",
        "DOT/EUR": "carried",
    }
    assert _leg(result, "BTC/EUR").reason == "exit: target 0; the whole leg"
    assert _leg(result, "DOT/EUR").reason == "exit: target 0; sell 3 is under ordermin 3.9"
    assert all(d.reason.startswith("exit: target 0") for d in result.decisions)
    assert result.report.startswith("EXIT: every leg's target is 0")


def test_the_exit_on_a_flat_book_drafts_nothing():
    result = _draft({symbol: 0.05 for symbol in LEGS}, boundary=EXIT_BOUNDARY, exiting=True)

    assert result.plan_id is None
    assert {d.outcome for d in result.decisions} == {"on-target"}
    assert ruling_refusals(_plan(_sell(), _buy(), created_at=EXIT_BOUNDARY), PRICES, exiting=True) == [
        "a buy in an exit plan -- the exit only sells"
    ]


_LOTS = {"BTC": 0.00029, "ETH": 0.0076, "SOL": 0.12, "XRP": 10.0}
_DAY_TWO = BOUNDARY + timedelta(days=1)


def _day_two_draft(targets, boundary=_DAY_TWO, **options):
    venue = _venue(cycle_ts=boundary, positions={f"{base}/EUR": qty for base, qty in _LOTS.items()})
    return _draft(targets, boundary=boundary, venue=venue, export=_export(1000.0, **_LOTS), **options)


def test_a_venue_record_holding_the_books_spot_lots_drafts_buys_and_sells():
    result = _day_two_draft({"BTC/EUR": 0.0297, "ETH/EUR": 0.0125, "SOL/EUR": 0.004, "XRP/EUR": 0.0183, "ADA/EUR": 0.01})

    assert [(i.symbol, i.side, i.qty, i.notional_eur) for i in parse_plan(result.plan_text).intents] == [
        ("SOL/EUR", "sell", 0.12, None),
        ("ETH/EUR", "sell", 0.00379715, None),
        ("ADA/EUR", "buy", None, 7.2),
    ]
    assert _leg(result, "SOL/EUR").reason == "the whole leg: the remainder would be under ordermin"
    assert (_leg(result, "BTC/EUR").outcome, _leg(result, "XRP/EUR").outcome) == ("carried", "carried")
    assert {d.symbol: d.engine_held for d in result.decisions if d.engine_held} == {
        f"{base}/EUR": qty for base, qty in _LOTS.items()
    }
    assert "engine held differs" not in result.report


def test_a_venue_record_holding_the_books_spot_lots_drafts_the_exit():
    result = _day_two_draft({symbol: 0.05 for symbol in LEGS}, boundary=EXIT_BOUNDARY, exiting=True)

    assert [(i.symbol, i.side, i.qty) for i in parse_plan(result.plan_text).intents] == [
        ("BTC/EUR", "sell", 0.00029),
        ("ETH/EUR", "sell", 0.0076),
        ("XRP/EUR", "sell", 10.0),
    ]
    assert (_leg(result, "SOL/EUR").outcome, _leg(result, "SOL/EUR").qty) == ("queued", 0.12)


def test_a_negative_position_in_the_venue_record_is_carried_and_decides_nothing():
    venue = _venue(balances={"EUR": 1000.0, "SOL": 0.2}, positions={"SOL/EUR": -0.08, "LINK/EUR": -0.58882411})

    result = _draft({"BTC/EUR": 0.0177}, venue=venue, export=_export(1000.0, SOL=0.12))

    assert [(i.symbol, i.side, i.qty, i.notional_eur) for i in parse_plan(result.plan_text).intents] == [
        ("SOL/EUR", "sell", 0.12, None),
        ("BTC/EUR", "buy", None, 12.74),
    ]
    assert _leg(result, "SOL/EUR").engine_held == -0.08
    assert next(row for row in result.rows if row["symbol"] == "SOL/EUR")["engine_held"] == -0.08


def test_positions_reading_zero_while_kraken_holds_the_lots_draft_what_matching_positions_draft():
    targets = {"BTC/EUR": 0.0297, "ETH/EUR": 0.0125, "SOL/EUR": 0.004, "XRP/EUR": 0.0183, "ADA/EUR": 0.01}

    result = _draft(targets, boundary=_DAY_TWO, venue=_venue(cycle_ts=_DAY_TWO), export=_export(1000.0, **_LOTS))

    assert {d.engine_held for d in result.decisions} == {0}
    assert result.plan_text == _day_two_draft(targets).plan_text


def test_the_reserve_day_drafts_the_exit_of_the_legs_still_held_when_the_sold_legs_read_negative():
    reserve = _noon(EXIT_DAYS[1])
    sold = {"BTC": 0.0002, "XRP": 10.0, "LTC": 0.2}
    still_held = {base: qty for base, qty in _HELD.items() if base not in sold}
    venue = _venue(cycle_ts=reserve, balances={"EUR": 900.0} | _HELD, positions={f"{base}/EUR": -qty for base, qty in sold.items()})

    result = _draft({}, boundary=reserve, venue=venue, export=_export(930.0, **still_held), exiting=True)

    assert [(i.symbol, i.side, i.qty) for i in parse_plan(result.plan_text).intents] == [
        ("ETH/EUR", "sell", 0.005),
        ("ADA/EUR", "sell", 50.0),
        ("SOL/EUR", "sell", 0.1),
    ]
    assert {d.symbol for d in result.decisions if d.outcome == "on-target"} == {f"{base}/EUR" for base in sold}
    assert {d.symbol for d in result.decisions if d.outcome == "queued"} == {"DOGE/EUR", "AVAX/EUR"}


# ---- the box's calendar ------------------------------------------------------------------------------


def _named(day: date) -> str:
    return f"{day:%a %Y-%m-%d}"


def test_the_box_is_four_iso_weeks_from_a_monday_with_its_restart_on_the_last_friday():
    assert BOX_FIRST_DAY.isoweekday() == 1
    assert (BOX_LAST_DAY - BOX_FIRST_DAY, BOX_LAST_DAY.isoweekday()) == (timedelta(days=27), 7)
    assert (RESTART_DAY, EXIT_DAYS) == (BOX_LAST_DAY - timedelta(days=2), (BOX_LAST_DAY - timedelta(days=1), BOX_LAST_DAY))


@pytest.mark.parametrize("day", [EVE, BOX_LAST_DAY + timedelta(days=1)])
@pytest.mark.parametrize("exiting", [False, True])
def test_a_draft_dated_outside_the_box_is_refused(day, exiting):
    fragment = f"{_named(day)} is outside the box, {_named(BOX_FIRST_DAY)} to {_named(BOX_LAST_DAY)}"

    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _draft(TARGETS, boundary=_noon(day), exiting=exiting)
    assert ruling_refusals(_plan(_sell(), created_at=_noon(day)), PRICES, exiting=exiting)[0] == fragment


def test_the_boxs_first_and_last_days_draft():
    assert _draft(TARGETS).plan_id == _id(1)
    assert _day_two_draft({}, boundary=_noon(BOX_LAST_DAY), exiting=True).plan_id == _id(1, BOX_LAST_DAY)


@pytest.mark.parametrize("day", EXIT_DAYS)
def test_an_exit_day_refuses_a_draft_without_exit(day):
    fragment = f"{_named(day)} is an exit day -- only --exit drafts on it, and nothing is bought"

    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _draft(TARGETS, boundary=_noon(day))
    assert ruling_refusals(_plan(_sell(), created_at=_noon(day)), PRICES) == [fragment]
    assert ruling_refusals(_plan(_sell(), created_at=_noon(day)), PRICES, exiting=True) == []
    fallback = _noon(day) + timedelta(hours=4)
    assert _day_two_draft({}, boundary=fallback, exiting=True).plan_id == _id(1, day)


@pytest.mark.parametrize("day", [BOX_FIRST_DAY, RESTART_DAY - timedelta(days=1), RESTART_DAY])
def test_exit_is_refused_on_every_day_but_the_two_exit_days(day):
    fragment = f"{_named(day)} is not an exit day -- --exit drafts on {_named(EXIT_DAYS[0])} and {_named(EXIT_DAYS[1])} alone"

    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _day_two_draft({}, boundary=_noon(day), exiting=True)
    assert ruling_refusals(_plan(_sell(), created_at=_noon(day)), PRICES, exiting=True) == [fragment]


RESTART_BOUNDARY = _noon(RESTART_DAY)


@pytest.mark.parametrize("clock", ["12:12:00", "13:15:00"])
def test_the_restart_day_drops_a_plan_of_any_size_by_13_15z(clock):
    result = _book_draft(boundary=RESTART_BOUNDARY, now=_at(RESTART_BOUNDARY, clock))

    assert [i.symbol for i in parse_plan(result.plan_text).intents] == ["SOL/EUR", "BTC/EUR", "ETH/EUR"]
    assert (
        f"drop window 12:10-13:15Z for this plan's 3 intent(s): on {_named(RESTART_DAY)} a plan of any size drops by 13:15Z, "
        "and the planned restart follows after 13:30Z -- no plan follows it"
    ) in result.report
    assert "13:30-" not in result.report
    assert "no published WebSocket/REST maintenance overlaps 12:10-15:00Z" in result.report


@pytest.mark.parametrize("clock", ["13:15:01", "13:40:00", "14:20:00"])
def test_the_restart_day_refuses_a_draft_past_13_15z(clock):
    fragment = f"it is {clock}Z, past 13:15Z, the last drop on {_named(RESTART_DAY)} for a plan of any size"

    with pytest.raises(DraftPlanError, match=re.escape(fragment)):
        _book_draft(boundary=RESTART_BOUNDARY, now=_at(RESTART_BOUNDARY, clock))


def test_the_restart_days_16z_record_drafts_nothing():
    fallback = RESTART_BOUNDARY + timedelta(hours=4)
    fragment = f"the 16Z record of {_named(RESTART_DAY)}, the restart day, drafts nothing -- only the 12Z record drafts that day"

    with pytest.raises(DraftPlanError, match=re.escape(fragment) + ": no plan follows the planned restart"):
        _book_draft(boundary=fallback)


def test_the_ruling_reads_the_restart_days_last_drop_for_a_plan_of_any_size():
    end = RESTART_BOUNDARY + timedelta(hours=3)
    three = (_sell(), _buy(), _buy("ETH/EUR"))

    assert ruling_refusals(_plan(*three, created_at=_at(RESTART_BOUNDARY, "13:15:00")), PRICES, window_end=end) == []
    assert ruling_refusals(_plan(_sell(), created_at=_at(RESTART_BOUNDARY, "13:15:01")), PRICES) == [
        f"a plan created at 13:15:01Z on {_named(RESTART_DAY)} is past that day's last drop at 13:15Z -- no plan follows the "
        "planned restart"
    ]
    assert len(ruling_refusals(_plan(_sell(), created_at=_at(RESTART_BOUNDARY, "16:12:00")), PRICES)) == 1


def test_a_day_with_nothing_placeable_drafts_no_plan():
    result = _draft({"DOGE/EUR": 0.002})

    assert (result.plan_id, result.plan_text) == (None, None)
    assert "nothing placeable" in result.report
    assert len(result.rows) == len(LEGS)


@pytest.mark.parametrize(
    ("hour", "clock", "drops", "intents"),
    [
        (12, "14:15:00", "12:10-13:15Z, 13:30-14:15Z", 3),
        (12, "14:15:01", "12:10-13:15Z, 13:30-14:30Z", 2),
        (12, "14:30:00", "12:10-13:15Z, 13:30-14:30Z", 2),
        (12, "14:30:01", "12:10-13:15Z, 13:30-14:45Z", 1),
        (12, "14:45:00", "12:10-13:15Z, 13:30-14:45Z", 1),
        (16, "18:15:00", "16:10-17:15Z, 17:30-18:15Z", 3),
        (16, "18:15:01", "16:10-17:15Z, 17:30-18:30Z", 2),
        (16, "18:30:00", "16:10-17:15Z, 17:30-18:30Z", 2),
        (16, "18:30:01", "16:10-17:15Z, 17:30-18:45Z", 1),
        (16, "18:45:00", "16:10-17:15Z, 17:30-18:45Z", 1),
    ],
)
def test_a_plan_drops_15_minutes_per_intent_before_the_windows_end(hour, clock, drops, intents):
    boundary = BOUNDARY.replace(hour=hour)

    result = _draft(
        record=_record(TARGETS, cycle_ts=boundary),
        venue=_venue(cycle_ts=boundary, balances={"EUR": 1000.0, "SOL": 0.12}),
        export=_export(1000.0, SOL=0.12),
        now=_at(boundary, clock),
    )

    drafted = [i.symbol for i in parse_plan(result.plan_text).intents]
    assert drafted == ["SOL/EUR", "BTC/EUR", "ETH/EUR"][:intents]
    assert {d.symbol for d in result.decisions if d.outcome == "queued"} == {"SOL/EUR", "BTC/EUR", "ETH/EUR", "ADA/EUR"} - set(
        drafted
    )
    assert f"drop window {drops} for this plan's {intents} intent(s), 15 minutes each before {hour + 3}:00Z" in result.report
    assert (f"a plan drafted at {clock}Z fits at most {intents}" in result.report) is (intents < 3)
    assert f"no published WebSocket/REST maintenance overlaps {hour}:10-{hour + 3}:00Z" in result.report


# ---- the command -------------------------------------------------------------------------------------


def _opener(feed: dict):
    def opener(url, timeout):
        if url == FEED_URL:
            return io.BytesIO(json.dumps(feed).encode())
        if url.startswith("https://api.kraken.com/0/public/Ticker?pair="):
            return io.BytesIO(json.dumps({"error": [], "result": _ticker()}).encode())
        raise AssertionError(f"draft-plan reached {url}")

    return opener


def _command_inputs(tmp_path, *, export_age=timedelta(minutes=3), positions="{}\n"):
    cycle = tmp_path / "cycle-12.json"
    cycle.write_text(to_json(_record(TARGETS)))
    venue = tmp_path / "venue-12.json"
    venue.write_text(json.dumps(_venue(balances={"EUR": 1000.0, "SOL": 0.12})))
    balances = tmp_path / "balances.json"
    balances.write_text(json.dumps(_export(1000.0, SOL=0.12)))
    held = tmp_path / "positions.json"
    held.write_text(positions)
    stamp = (NOW - export_age).timestamp()
    os.utime(balances, (stamp, stamp))
    os.utime(held, (stamp, stamp))
    decisions = tmp_path / "rung2" / "decisions.jsonl"
    args = [
        "engine",
        "draft-plan",
        "--cycle",
        str(cycle),
        "--venue",
        str(venue),
        "--balances",
        str(balances),
        "--positions",
        str(held),
        "--decisions",
        str(decisions),
    ]
    return args, decisions


def _invoke(monkeypatch, args, feed=None):
    monkeypatch.setattr(command, "_utc_now", lambda: NOW)
    monkeypatch.setattr(command, "_urlopen", _opener(feed if feed is not None else _feed()))
    result = runner.invoke(app, args)
    return result, _ANSI_RE.sub("", result.output)


def test_the_command_writes_the_plan_and_the_decision_rows(tmp_path, monkeypatch):
    args, decisions = _command_inputs(tmp_path)

    result, out = _invoke(monkeypatch, args)

    assert result.exit_code == 0, out
    plan_path = decisions.parent / f"{_id(1)}.json"
    plan = parse_plan(plan_path.read_text())
    assert [i.symbol for i in plan.intents] == ["SOL/EUR", "BTC/EUR", "ETH/EUR"]
    assert len(decisions.read_text().splitlines()) == len(LEGS)
    assert f"plan written to {plan_path}" in out
    assert "engine held differs from Kraken held on: SOL/EUR" in out

    again, out = _invoke(monkeypatch, args)

    assert again.exit_code == 0, out
    assert [i.symbol for i in parse_plan((decisions.parent / f"{_id(2)}.json").read_text()).intents] == ["ADA/EUR"]
    assert len(decisions.read_text().splitlines()) == 2 * len(LEGS)
    assert f"engine held differs from Kraken held on: SOL/EUR (in {_id(1)}, drafted after the record)" in out


def test_a_refused_command_writes_nothing(tmp_path, monkeypatch):
    args, decisions = _command_inputs(tmp_path, export_age=timedelta(minutes=45))

    result, out = _invoke(monkeypatch, args)

    assert result.exit_code == 1
    assert "draft refused: the balance export is 45 minutes old" in out
    assert not decisions.parent.exists()


def test_the_command_refuses_on_an_open_margin_position_and_without_the_positions_export(tmp_path, monkeypatch):
    args, decisions = _command_inputs(tmp_path, positions=_POSITIONS_AS_PRINTED)

    result, out = _invoke(monkeypatch, args)

    assert result.exit_code == 1
    assert "draft refused: Kraken reports an open margin position TU7O4B-NJL5A-GY5DRP" in out
    assert not decisions.parent.exists()

    at = args.index("--positions")
    missing, out = _invoke(monkeypatch, args[:at] + args[at + 2 :])

    assert missing.exit_code == 2
    assert "--positions" in out
    assert not decisions.parent.exists()


@pytest.mark.parametrize("configured", [True, False])
def test_the_decision_log_defaults_under_the_configured_data_dir(tmp_path, monkeypatch, configured):
    args, decisions = _command_inputs(tmp_path)
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()
    if configured:
        (workdir / "zcrypto.toml").write_text(f'[zcrypto]\ndata_dir = "{tmp_path / "data"}"\n')
    monkeypatch.chdir(workdir)

    result, out = _invoke(monkeypatch, args[: args.index("--decisions")])

    if configured:
        assert result.exit_code == 0, out
        assert (tmp_path / "data" / "rung2" / f"{_id(1)}.json").exists()
        assert len((tmp_path / "data" / "rung2" / "decisions.jsonl").read_text().splitlines()) == len(LEGS)
    else:
        assert result.exit_code == 1
        assert "no data_dir configured" in out
        assert list(workdir.iterdir()) == []


def test_the_plan_is_written_before_its_rows(tmp_path, monkeypatch):
    args, decisions = _command_inputs(tmp_path)
    plan_path = tmp_path / "plan.json"
    real_open = Path.open

    def open_failing_the_append(path, mode="r", *rest, **options):
        if path == decisions and "a" in mode:
            raise OSError("no space left on device")
        return real_open(path, mode, *rest, **options)

    monkeypatch.setattr(Path, "open", open_failing_the_append)

    result, out = _invoke(monkeypatch, [*args, "--out", str(plan_path)])

    assert result.exit_code == 1
    assert f"{plan_path} was written without its rows" in out
    assert parse_plan(plan_path.read_text()).plan_id == _id(1)


def test_the_command_never_overwrites_a_plan(tmp_path, monkeypatch):
    args, decisions = _command_inputs(tmp_path)
    existing = tmp_path / "plan.json"
    existing.write_text("{}")

    result, out = _invoke(monkeypatch, [*args, "--out", str(existing)])

    assert result.exit_code == 1
    assert "is never overwritten" in out
    assert existing.read_text() == "{}"
    assert not decisions.exists()
