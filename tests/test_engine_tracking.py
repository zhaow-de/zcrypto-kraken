import math
from datetime import date, datetime, timedelta

import pytest

from cli.engine.errors import EngineError
from cli.engine.feeders import CycleStages
from cli.engine.tracking import Fill, cost_blend, extract_fills, realized_drift, weekly_tracking
from cli.portfolio.crossfreq_system import CrossfreqSystemConfig

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


# --- realized drift, ISO weeks, and the rung boundary ---------------------------------------------

_MINIMUMS = {"BTC": (0.00005, 0.45)}


def _stage(ts, *, weight=1.0, close=50000.0):
    # CycleStages is a frozen dataclass with EIGHT required fields and no defaults; supplying
    # three raises TypeError at construction, before any assertion is reached.
    return CycleStages(
        cycle_ts=datetime.fromisoformat(ts),
        sleeve_positions={},
        combined={},
        capped={},
        final={"BTC": weight},
        multiplier=1.0,
        closes={"BTC": close},
        cap_bound=False,
    )


def _mk(boundary, qty, side="buy", px=50000.0):
    b = datetime.fromisoformat(boundary)
    return Fill(b, b, "BTC", side, qty, px, 0.05, "MAKER", f"T-{boundary}-{side}")


def test_a_fill_matching_the_target_leaves_zero_drift():
    # NAV 1000 at 50k -> target 0.02 BTC.
    out = realized_drift([_stage("2026-08-31T00:00:00+00:00")], [_mk("2026-08-31T00:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)


def test_a_price_move_moves_realized_drift_and_that_is_the_signal():
    # Held 0.02 BTC, close 50k -> 60k, NAV pinned at 1000: target falls to 0.016667 while held
    # stays put -> 0.003333 BTC * 60000 = 200 EUR = 2000 bps. An engine that kept placing would
    # have re-placed; one that stopped accumulates exactly this. It is the measurement, not a bug.
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00", close=60000.0)]
    out = realized_drift(stages, [_mk("2026-08-31T00:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)
    assert out["cycles"][1]["drift_bps"] == pytest.approx(2000.0)


def test_a_sell_reduces_held_and_a_round_trip_returns_it_to_zero():
    # The buy OVERSHOOTS the 0.02 target on purpose. Round-tripping a fill that exactly meets the
    # target leaves held at `target - q` when signed and `target + q` when unsigned, and drift is an
    # absolute value -- both read the same number, so the sign error would be unobservable.
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    fills = [_mk("2026-08-31T00:00:00+00:00", 0.05), _mk("2026-08-31T04:00:00+00:00", 0.05, side="sell")]
    out = realized_drift(stages, fills, 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(15000.0)  # 0.03 BTC over target
    # held back to 0 against a 0.02 target -> the whole NAV undeployed -> 10000 bps.
    assert out["cycles"][1]["drift_bps"] == pytest.approx(10000.0)


def test_a_fill_is_attributed_to_its_own_boundary_not_a_later_one():
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    out = realized_drift(stages, [_mk("2026-08-31T04:00:00+00:00", 0.02)], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(10000.0)  # nothing held yet
    assert out["cycles"][1]["drift_bps"] == pytest.approx(0.0)


def test_a_fill_past_the_last_cycle_is_refused_as_a_truncated_window():
    # Dropping it would overstate drift for every later cycle with no note and no refusal. Naming
    # the truncation is the point: widening the window fixes this one and cannot fix a hole.
    with pytest.raises(EngineError, match="OUTSIDE the cycle span"):
        realized_drift([_stage("2026-08-31T00:00:00+00:00")], [_mk("2026-08-31T04:00:00+00:00", 0.02)], 1000.0)


def test_a_fill_inside_the_span_whose_cycle_is_missing_is_refused_as_a_hole():
    # The reachable trigger: `accumulation_report` drops a record whose `replay_stages` raises and
    # counts it in `n_failed`, so a fill journaled under that boundary has no stage to land on. No
    # widening recovers it, which is why it must not read as a truncation.
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T08:00:00+00:00")]
    with pytest.raises(EngineError, match="INSIDE the cycle span"):
        realized_drift(stages, [_mk("2026-08-31T04:00:00+00:00", 0.02)], 1000.0)


def test_a_boundary_written_in_another_offset_is_one_instant_not_an_orphan():
    # `by_boundary`'s lookup is keyed by datetime INSTANT while the refusal once compared isoformat
    # text. 02:00+02:00 and 00:00+00:00 are one instant and two strings, so a text comparison
    # refuses a fill that the accumulation loop then goes on to apply.
    b = datetime.fromisoformat("2026-08-31T02:00:00+02:00")
    shifted = Fill(b, b, "BTC", "buy", 0.02, 50000.0, 0.05, "MAKER", "T-tz")
    out = realized_drift([_stage("2026-08-31T00:00:00+00:00")], [shifted], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)


def test_an_empty_window_answers_nan_rather_than_none():
    # One convention for "nothing to average" across both halves: `feeders._bps` renders NaN as
    # `n/a` and raises TypeError on None, and it is the renderer this payload feeds.
    out = realized_drift([], [], 1000.0)
    assert math.isnan(out["median_drift_bps"]) and math.isnan(out["p95_drift_bps"])


def test_a_fill_on_a_btc_quoted_leg_is_counted_but_never_aborts_the_report():
    # The "inflating a base" half is unfalsifiable by construction -- a base of None is never a key
    # in `final`, so `held[None]` is unreadable and the skip moves no drift number. What the skip
    # DOES decide is the second leg here, whose boundary no cycle covers: a leg carrying no model
    # target must not take the whole report down through the orphan refusal.
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    orphan_b = datetime.fromisoformat("2026-08-31T04:00:00+00:00")
    excluded = Fill(b, b, None, "buy", 5.0, 3000.0, None, "MAKER", "T-X")
    off_window = Fill(orphan_b, orphan_b, None, "buy", 5.0, 3000.0, None, "MAKER", "T-Y")
    out = realized_drift([_stage("2026-08-31T00:00:00+00:00")], [excluded, off_window], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(10000.0)
    assert out["n_fills"] == 2  # excluded from the drift half, still counted


def test_a_partial_iso_week_is_marked_and_carries_no_verdict():
    out = weekly_tracking([_stage("2026-08-31T00:00:00+00:00")], [], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert (wk["iso_week"], wk["complete"], wk["within_band"]) == ("2026-W36", False, None)
    assert out["verdict"] == "insufficient-data"


def test_no_data_means_the_series_never_started_not_a_quiet_week():
    # THE BLOCKER THIS PINS: an engine that stops placing is maximal tracking error, and is
    # exactly what a tracking-error trip exists to catch. A quiet week must carry a NUMBER.
    stages = [_stage(f"2026-08-31T{h:02d}:00:00+00:00") for h in (0, 4, 8, 12, 16, 20)] + [
        _stage(f"2026-09-07T{h:02d}:00:00+00:00") for h in (0, 4, 8, 12, 16, 20)
    ]
    out = weekly_tracking(stages, [_mk("2026-08-31T00:00:00+00:00", 0.02)], _MINIMUMS, 1000.0)
    weeks = {w["iso_week"]: w for w in out["weeks"]}
    assert weeks["2026-W36"]["realized_mean_bps"] is not None
    assert weeks["2026-W37"]["realized_mean_bps"] is not None, "a quiet week is not 'no data'"


def test_before_any_fill_the_series_has_not_started():
    out = weekly_tracking([_stage("2026-08-31T00:00:00+00:00")], [], _MINIMUMS, 1000.0)
    assert out["weeks"][0]["realized_mean_bps"] is None


def _full_week(monday="2026-08-31", **kw):
    # 42 stages = 6 boundaries x 7 days, so `partial` is False and the rung rule is the ONLY
    # thing that can make the week ineligible. A one-stage week is partial and would pass this
    # test with the rung rule deleted.
    day = date.fromisoformat(monday)
    return [_stage(f"{day + timedelta(days=d)}T{h:02d}:00:00+00:00", **kw) for d in range(7) for h in (0, 4, 8, 12, 16, 20)]


def _tracking_fills(stages, nav=1000.0):
    # A fill at every boundary that exactly meets that cycle's target -> realized drift 0.
    out = []
    for st in stages:
        held = (nav * st.final["BTC"]) / st.closes["BTC"]
        prev = sum(f.qty if f.side == "buy" else -f.qty for f in out)
        delta = held - prev
        if delta:
            out.append(
                Fill(
                    st.cycle_ts,
                    st.cycle_ts,
                    "BTC",
                    "buy" if delta > 0 else "sell",
                    abs(delta),
                    st.closes["BTC"],
                    0.05,
                    "MAKER",
                    f"T-{st.cycle_ts}",
                )
            )
    return out


def test_a_fill_whose_at_is_skewed_past_the_next_boundary_still_counts_at_its_own():
    # Every other fixture sets at == boundary, which makes the "attribute by wall clock"
    # mutation unobservable. This skew IS the defect being guarded.
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    late = Fill(b, datetime.fromisoformat("2026-08-31T05:30:00+00:00"), "BTC", "buy", 0.02, 50000.0, 0.05, "MAKER", "T-late")
    stages = [_stage("2026-08-31T00:00:00+00:00"), _stage("2026-08-31T04:00:00+00:00")]
    out = realized_drift(stages, [late], 1000.0)
    assert out["cycles"][0]["drift_bps"] == pytest.approx(0.0)


def test_three_complete_weeks_within_band_read_pass():
    # The only test that reaches a `pass` verdict -- without it the _GATE_MIN_WEEKS probe has
    # nothing to fail against, since every other fixture yields insufficient-data either way.
    stages = _full_week("2026-08-31") + _full_week("2026-09-07") + _full_week("2026-09-14")
    out = weekly_tracking(stages, _tracking_fills(stages), _MINIMUMS, 1000.0)
    assert out["complete_gate_eligible_weeks"] == 3
    assert out["verdict"] == "pass"


def test_two_complete_weeks_are_not_enough_for_a_verdict():
    # Pins the gate minimum from BELOW; the three-week test pins it only from above. Lowered, these
    # two in-band weeks read `pass` on less evidence than the gate requires, and no other fixture
    # notices: every remaining one has `decided == []`, which is short of any threshold.
    stages = _full_week("2026-08-31") + _full_week("2026-09-07")
    out = weekly_tracking(stages, _tracking_fills(stages), _MINIMUMS, 1000.0)
    assert out["complete_gate_eligible_weeks"] == 2
    assert out["verdict"] == "insufficient-data"


def _uneven_week(monday):
    # 42 cycles, three of them at ten times the others' weight. A flat week has ONE distinct floor
    # value, which makes its p95 and its median the same number and the band's edge unprovable;
    # here the p95 (nearest rank: the 40th of 42) is 1.0 bps while the median stays at 0.1.
    week = _full_week(monday, weight=1e-5)
    return week[:-3] + [_stage(s.cycle_ts.isoformat(), weight=1e-4) for s in week[-3:]]


def _light_weeks():
    # Three complete weeks whose floor never places: weight 1e-5 puts the target at 2e-7 BTC, under
    # the 0.00005 ordermin and the 0.45 costmin, so every cycle's floor drift is a flat 0.1 bps.
    # Non-zero on BOTH sides is what a fixture needs before it can say anything about a comparison.
    return _full_week("2026-08-31", weight=1e-5) + _full_week("2026-09-07", weight=1e-5) + _full_week("2026-09-14", weight=1e-5)


def test_a_realized_mean_strictly_inside_the_floor_band_reads_pass():
    # A single 1e-9 BTC fill against a 2e-7 target leaves the realized side at 0.0995 bps -- inside
    # a 0.1 floor, and inside it strictly. `<=` reads True here and `>=` reads False, which is the
    # only thing in the suite that pins which way the band comparison runs.
    out = weekly_tracking(_light_weeks(), [_mk("2026-08-31T00:00:00+00:00", 1e-9)], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert wk["floor_p95_bps"] == pytest.approx(0.1)
    assert wk["realized_mean_bps"] == pytest.approx(0.0995)
    assert wk["within_band"] is True
    assert out["verdict"] == "pass"


def test_a_realized_mean_outside_the_floor_band_reads_fail():
    # The only fixture that reaches `fail`. Same non-placing 0.1 bps floor; a 0.02 BTC fill against a
    # 2e-7 target leaves the book vastly over-deployed at 9999.9 bps.
    out = weekly_tracking(_light_weeks(), [_mk("2026-08-31T00:00:00+00:00", 0.02)], _MINIMUMS, 1000.0)
    assert out["weeks"][0]["realized_mean_bps"] == pytest.approx(9999.9)
    assert all(w["within_band"] is False for w in out["weeks"])
    assert out["verdict"] == "fail"


def test_the_bands_edge_is_the_floors_p95_not_its_median():
    # The realized mean lands at 0.1638 -- inside the p95 edge at 1.0, outside a median edge at 0.1 --
    # so the two statistics return opposite verdicts on identical data.
    stages = _uneven_week("2026-08-31") + _uneven_week("2026-09-07") + _uneven_week("2026-09-14")
    out = weekly_tracking(stages, [_mk("2026-08-31T00:00:00+00:00", 1e-9)], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert wk["floor_p95_bps"] == pytest.approx(1.0)
    assert wk["realized_mean_bps"] == pytest.approx(0.1637857142857143)
    assert out["verdict"] == "pass"  # a median edge would read `fail` on the same numbers


def test_a_week_straddling_the_first_fill_is_measured_but_not_gate_eligible():
    # The twenty pre-fill cycles hold nothing and each contribute the full 10000 bps, so a complete
    # week whose trading starts inside it reads 4761.9 -- an artefact of WHEN trading began, not of
    # tracking, and it would bias the first live week toward `fail`. Ruled like a partial week:
    # reported, excluded from the verdict. `complete` is True, so only the straddle rule can do it.
    stages = _full_week("2026-08-31")
    out = weekly_tracking(stages, [_mk(stages[20].cycle_ts.isoformat(), 0.02)], _MINIMUMS, 1000.0)
    wk = out["weeks"][0]
    assert wk["complete"] is True and wk["rung"] is None
    assert wk["realized_mean_bps"] == pytest.approx(4761.9047619047615)
    assert wk["gate_eligible"] is False and wk["within_band"] is None
    assert out["complete_gate_eligible_weeks"] == 0


def test_a_rung_2_week_is_measured_but_not_gate_eligible():
    # Given a FILL, so the exclusion is what makes it ineligible -- without one this test would
    # pass with the rung-2 rule entirely removed.
    stages = _full_week("2026-08-31")
    out = weekly_tracking(stages, _tracking_fills(stages), _MINIMUMS, 1000.0, rung_by_week={"2026-W36": 2})
    wk = out["weeks"][0]
    assert wk["complete"] is True, "a partial week would be ineligible whatever the rung rule"
    assert wk["rung"] == 2 and wk["gate_eligible"] is False
    assert wk["floor_p95_bps"] is not None
    assert out["complete_gate_eligible_weeks"] == 0


def _cf(liquidity="MAKER", qty=1.0, px=100.0, fee=0.1, base="BTC"):
    b = datetime.fromisoformat("2026-08-31T00:00:00+00:00")
    return Fill(b, b, base, "buy", qty, px, fee, liquidity, "T-1")


def test_the_blend_is_share_of_NOTIONAL_not_a_count_of_fills():
    # One large taker fill beside nine tiny maker ones is a taker-heavy book; a count-weighted
    # blend would call it 90% maker and under-price the cost.
    #
    # The two sides are deliberately heterogeneous in PRICE as well as quantity: at a shared px
    # every fixture makes `abs(qty) * px` and `abs(qty)` yield the identical share, so a uniform
    # one cannot tell notional-weighting from QUANTITY-weighting -- the likelier error across a
    # basket whose prices span BTC to DOGE. Here notional reads 0.99108 and quantity 0.01099.
    out = cost_blend([_cf("TAKER", qty=1.0, px=10000.0)] + [_cf("MAKER", qty=10.0, px=1.0) for _ in range(9)])
    assert out["taker_share"] > 0.98
    # Asserted, not assumed: without this the two shares could be the same number.
    assert out["maker_share"] == pytest.approx(1 - out["taker_share"])


def test_realized_fee_per_side_is_fees_over_priced_notional():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=0.25)])
    assert out["realized_fee_per_side"] == pytest.approx(0.0025)


def test_unpriced_fills_are_counted_but_excluded_from_the_rate():
    out = cost_blend([_cf(fee=0.1), _cf(fee=None)])
    assert (out["n_fills"], out["n_priced"]) == (2, 1)
    # The RATE is what the mutation moves: dividing by gross (200) instead of priced notional
    # (100) halves it, and a count-only assertion cannot see that.
    assert out["realized_fee_per_side"] == pytest.approx(0.001)


def test_no_priced_fills_proposes_nothing_rather_than_zero():
    out = cost_blend([_cf(fee=None)])
    assert out["realized_fee_per_side"] is None and out["proposed_fee_per_side"] is None
    assert "no euro-denominated fills" in out["basis"]


def test_it_prices_the_fee_term_and_leaves_the_spread_alone():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=0.25)])
    cfg = CrossfreqSystemConfig()
    assert out["current_fee_per_side"] == cfg.fee_per_side == 0.0040
    assert out["current_spread_per_side"] == cfg.spread_per_side == 0.0020
    assert out["proposed_fee_per_side"] == pytest.approx(0.0025)


def test_the_dispersion_is_a_spread_not_a_deviation():
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=f) for f in (0.1, 0.2, 0.6)])
    assert (out["per_fill_min"], out["per_fill_median"], out["per_fill_max"]) == (
        pytest.approx(0.001),
        pytest.approx(0.002),
        pytest.approx(0.006),
    )
    assert "std" not in out and "stdev" not in out


def test_an_unpriceable_side_is_left_out_of_the_blends_denominator():
    # A NO_LIQUIDITY_SIDE fill nine times the maker's size. It is real trading and it is counted,
    # but it carries no side to attribute, so putting its notional in `gross` would make BOTH
    # shares understate the book they claim to split: maker reads 1.0 here, 0.1 if it is included.
    out = cost_blend([_cf(qty=1.0, px=100.0), _cf("NO_LIQUIDITY_SIDE", qty=9.0, px=100.0, fee=None)])
    assert out["n_fills"] == 2
    assert out["maker_share"] == pytest.approx(1.0)
    assert out["taker_share"] == pytest.approx(0.0)


def test_a_repair_carries_no_price_and_is_skipped_rather_than_multiplied():
    # The shape `extract_fills` emits for a venue repair: px None, fee None. Reaching it without
    # the guard is `abs(qty) * None` -- a TypeError that takes the whole report down on the first
    # repair in a real window.
    out = cost_blend([_cf(qty=1.0, px=100.0, fee=0.1), _cf("NO_LIQUIDITY_SIDE", qty=5.0, px=None, fee=None)])
    assert (out["n_fills"], out["n_priced"]) == (2, 1)
    assert out["maker_share"] == pytest.approx(1.0)
    assert out["realized_fee_per_side"] == pytest.approx(0.001)


def test_a_zero_notional_fill_does_not_inflate_the_headline_rate():
    # Its fee in the numerator with no notional in the denominator doubles the headline while the
    # dispersion -- which already drops it -- still reads 0.001, so one payload contradicts itself.
    out = cost_blend([_cf(qty=0.0, fee=0.1), _cf(qty=1.0, fee=0.1)])
    assert out["realized_fee_per_side"] == pytest.approx(0.001)
    assert out["realized_fee_per_side"] == pytest.approx(out["per_fill_median"])


def test_priced_fills_carrying_no_notional_say_so_rather_than_claiming_none_were_priced():
    # `basis` is a payload key `--json` consumers read straight out, so the sentence has to be true
    # at source: these fills WERE euro-denominated, they just cannot carry a rate.
    out = cost_blend([_cf(qty=0.0, fee=0.1)])
    assert out["n_priced"] == 1
    assert out["proposed_fee_per_side"] is None
    assert "carry no notional" in out["basis"]
