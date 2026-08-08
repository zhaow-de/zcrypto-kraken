"""The captured-spread cost term (T0014, spec 00066).

The calibration is DATA: these tests pin the table's values and its provenance, so a recalibration
is a deliberate edit with a new window stamp rather than silent drift -- the same discipline
`SPOT_FEE_TIERS` gets in test_costs_fees.py."""

import math

import pytest

from cli.costs.errors import CostModelError
from cli.costs.spread import (
    CALIBRATION_HOURS,
    CALIBRATION_MIN_ROWS,
    CALIBRATION_WINDOW,
    SPREAD_CALIBRATION,
    effective_spread_bps,
    round_trip_cost,
)

# Mean effective spread, bps per side, mid-relative. Keyed by FULL SYMBOL (spec 00085 D3): a
# base-keyed table returns the EUR row for "ETH" while raising for "ETH/BTC", so the old shape's
# failure mode was a silently wrong value. The inner keys stay the EUR notionals -- on a BTC-quoted
# pair the rung is the BTC quantity worth that many EUR at the pinned FX reference (D1), so the key
# names a grid point, not a currency amount in the quote.
EXPECTED = {
    "ADA/EUR": {100: 2.383, 1_000: 2.686, 10_000: 5.389},
    "AVAX/EUR": {100: 2.417, 1_000: 2.838, 10_000: 6.031},
    "BTC/EUR": {100: 0.198, 1_000: 0.299, 10_000: 0.533},
    "DOGE/EUR": {100: 1.635, 1_000: 1.787, 10_000: 3.539},
    "DOT/EUR": {100: 2.812, 1_000: 4.053, 10_000: 10.054},
    "ETH/BTC": {100: 0.748, 1_000: 1.112, 10_000: 1.564},
    "ETH/EUR": {100: 0.344, 1_000: 0.404, 10_000: 0.619},
    "LINK/EUR": {100: 2.382, 1_000: 2.555, 10_000: 4.021},
    "LTC/EUR": {100: 2.103, 1_000: 2.908, 10_000: 5.124},
    "SOL/BTC": {100: 1.343, 1_000: 1.685, 10_000: 2.757},
    "SOL/EUR": {100: 0.927, 1_000: 1.041, 10_000: 1.798},
    "XRP/EUR": {100: 0.603, 1_000: 0.945, 10_000: 1.924},
}


def test_table_matches_the_calibration_exactly():
    assert SPREAD_CALIBRATION == EXPECTED


def test_provenance_is_pinned_so_a_recalibration_cannot_be_silent():
    # A new window MUST come with a new stamp. Restamped 2026-08-08 (spec 00085 D4) onto ONE window
    # shared by all twelve rows: the first full hour after the /BTC genesis through the last settled
    # hour, so the two BTC-quoted legs carry the same provenance as the ten EUR ones rather than a
    # second window to explain forever.
    #
    # 365 h == 15.21 days, which is what keeps Phase 2's ">=2 weeks of captured spreads" exit-bar row
    # DISCHARGED. That is load-bearing and nothing else checks it: the first window drafted for this
    # restamp ended 2026-08-06T06:00Z, ran 13.67 days, and would have silently un-discharged the bar
    # with every test still green. If a future restamp shortens this window below 14 days, the bar
    # goes with it.
    #
    # min_rows == max_rows == 365 * 3600 == 1_314_000 exactly: ZERO missing seconds and perfect joint
    # sampling, against 0.602 % shared gaps in the superseded window. A short window on one pair
    # cannot hide inside the mean.
    #
    # The EUR rows moved MATERIALLY across this restamp -- 9 of the 10 move >2 % at some rung, worst
    # -25.01 % (DOT @1k) -- where the spec had estimated under 2 %. That is market variation between
    # two disjoint windows, not drift in the pipeline: over the OLD window the same script against
    # the REGENERATED tree still reproduces the OLD table exactly (test_costs_calibrate.py). Treat
    # one window as a point estimate, never a constant.
    assert CALIBRATION_WINDOW == ("2026-07-23T14:00:00Z", "2026-08-07T19:00:00Z")
    assert CALIBRATION_HOURS == 365
    assert CALIBRATION_MIN_ROWS == 1_314_000


def test_the_window_still_clears_the_two_week_exit_bar():
    """Phase 2's exit-bar row is ">=2 weeks of captured spreads", discharged by T0091 at 14.68 days
    after a 13.1-day predecessor explicitly failed it.

    This exists because the bar was nearly lost to a restamp: spec 00085's implementation plan
    drafted a window ending 2026-08-06T06:00Z, which spans 13.67 days. Every other assertion in this
    file would have stayed green on it -- the table, the provenance stamp, the row counts and the
    reproduction control are all blind to span. Only reading the two timestamps catches it, so a
    future restamp that shortens the window fails HERE rather than silently un-discharging a gate.
    """
    from datetime import datetime

    start, end = (datetime.fromisoformat(w.replace("Z", "+00:00")) for w in CALIBRATION_WINDOW)
    span_days = (end - start).total_seconds() / 86_400
    assert span_days >= 14.0, f"window spans {span_days:.2f} days, below the >=2-week exit bar"
    # The stamped hour count must describe that same window, or the two drift apart silently. Bound
    # it rather than equate it: `calibrate()` counts hourly FILES that OVERLAP the window, so
    # `span / 3600` is the right answer only when the window is hour-aligned. The superseded
    # 2026-07-08T13:47:33Z...2026-07-23T05:59:59Z window spans 352.21 h and correctly stamps 353,
    # so an equality here would fail a perfectly good restamp for the wrong reason.
    span_hours = (end - start).total_seconds() / 3_600
    assert math.floor(span_hours) <= CALIBRATION_HOURS <= math.ceil(span_hours) + 1


@pytest.mark.parametrize("pair", sorted(EXPECTED))
@pytest.mark.parametrize("size", [100, 1_000, 10_000])
def test_pinned_sizes_return_the_table_value(pair, size):
    assert effective_spread_bps(pair, size) == EXPECTED[pair][size]


def test_unknown_pair_raises():
    with pytest.raises(CostModelError, match="unknown pair"):
        effective_spread_bps("NOPE", 1_000)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 0.0])
def test_non_positive_or_non_finite_notional_raises(bad):
    with pytest.raises(CostModelError):
        effective_spread_bps("BTC/EUR", bad)


def test_above_the_pinned_grid_refuses_rather_than_extrapolating():
    # Convex curve: extrapolating understates cost exactly where it matters most (spec 00066 D3).
    with pytest.raises(CostModelError, match="10000"):
        effective_spread_bps("DOT/EUR", 10_001)


def test_below_the_grid_clamps_to_the_floor():
    assert effective_spread_bps("BTC/EUR", 1.0) == EXPECTED["BTC/EUR"][100]


def test_interpolation_is_log_notional_and_respects_convexity():
    # DOT between 1k and 10k: sqrt(1k*10k) ~= 3162 is the log-midpoint.
    mid = effective_spread_bps("DOT/EUR", math.sqrt(1_000 * 10_000))
    lo, hi = EXPECTED["DOT/EUR"][1_000], EXPECTED["DOT/EUR"][10_000]
    assert lo < mid < hi
    # The log-midpoint sits at the arithmetic mean of the endpoints...
    assert mid == pytest.approx((lo + hi) / 2, rel=1e-9)
    # ...which is ABOVE the linear-in-notional reading at the same notional, i.e. the interpolator
    # does not flatten the convexity the thin pairs actually exhibit.
    linear = lo + (hi - lo) * (math.sqrt(1_000 * 10_000) - 1_000) / (10_000 - 1_000)
    assert mid > linear


def test_interpolation_is_monotone_across_the_whole_grid():
    prev = 0.0
    for notional in (100, 300, 1_000, 3_000, 10_000):
        cur = effective_spread_bps("DOT/EUR", notional)
        assert cur >= prev
        prev = cur


# --- round-trip composition ---------------------------------------------------------------------


def test_round_trip_cost_components_sum_to_total():
    r = round_trip_cost(1_000.0, pair="BTC/EUR", maker_rate=0.0040, taker_rate=0.0080)
    assert set(r) == {"fee", "spread", "carry", "total"}
    assert r["total"] == pytest.approx(r["fee"] + r["spread"] + r["carry"])


def test_spread_is_charged_once_per_side():
    notional = 1_000.0
    r = round_trip_cost(notional, pair="DOT/EUR", maker_rate=0.0, taker_rate=0.0)
    expected = 2 * notional * EXPECTED["DOT/EUR"][1_000] / 10_000
    assert r["spread"] == pytest.approx(expected)
    assert r["fee"] == 0.0


def test_fee_component_delegates_rather_than_reimplementing():
    from cli.costs.fees import round_trip_fee

    notional, maker, taker = 5_000.0, 0.0015, 0.0030
    r = round_trip_cost(notional, pair="ETH/EUR", maker_rate=maker, taker_rate=taker, taker_open=True)
    assert r["fee"] == round_trip_fee(notional, maker_rate=maker, taker_rate=taker, taker_open=True)


def test_spot_path_has_no_carry():
    r = round_trip_cost(1_000.0, pair="ETH/EUR", maker_rate=0.0040, taker_rate=0.0080)
    assert r["carry"] == 0.0


def test_carry_applies_whenever_a_margin_rate_is_given():
    r = round_trip_cost(1_000.0, pair="ETH/EUR", maker_rate=0.0, taker_rate=0.0, hold_hours=24.0, margin_rate_=0.0002)
    assert r["carry"] > 0.0
    assert r["total"] == pytest.approx(r["fee"] + r["spread"] + r["carry"])


@pytest.mark.parametrize(
    ("hold_hours", "expected"),
    [
        # margin_carry = notional * rate * (1 opening + floor(hold/4) rollovers). The OPENING charge
        # is unconditional, so a position opened and closed inside one 4h window still pays it --
        # gating the whole leg on `hold_hours` silently dropped it (cost-understating), and every
        # earlier test passed because none asserted a carry VALUE, only > 0 / == 0.
        (0.0, 0.2),
        (3.9, 0.2),
        (4.0, 0.4),
        (9.0, 0.6),
    ],
)
def test_carry_value_includes_the_unconditional_opening_charge(hold_hours, expected):
    r = round_trip_cost(1_000.0, pair="ETH/EUR", maker_rate=0.0, taker_rate=0.0, hold_hours=hold_hours, margin_rate_=0.0002)
    assert r["carry"] == pytest.approx(expected)


def test_carry_matches_margin_carry_exactly_rather_than_reimplementing():
    from cli.costs.margin import margin_carry

    r = round_trip_cost(2_500.0, pair="BTC/EUR", maker_rate=0.0, taker_rate=0.0, hold_hours=13.0, margin_rate_=0.0003)
    assert r["carry"] == margin_carry(2_500.0, 13.0, 0.0003)


def test_at_tier_one_fees_dominate_spread_even_on_the_widest_pair():
    # Spec 00066 D4: the spread term is additive to the fee term, never a substitute. If a future
    # edit swapped one for the other this guard catches the order-of-magnitude error.
    r = round_trip_cost(1_000.0, pair="DOT/EUR", maker_rate=0.0040, taker_rate=0.0080, taker_open=True, taker_close=True)
    assert r["fee"] > 10 * r["spread"]


def test_round_trip_rejects_a_notional_the_grid_cannot_price():
    with pytest.raises(CostModelError):
        round_trip_cost(50_000.0, pair="BTC/EUR", maker_rate=0.0040, taker_rate=0.0080)
