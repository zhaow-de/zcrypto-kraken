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

# Mean effective spread, bps per side, mid-relative -- spec 00066's table, verbatim.
EXPECTED = {
    "BTC": {100: 0.266, 1_000: 0.392, 10_000: 0.635},
    "ETH": {100: 0.425, 1_000: 0.494, 10_000: 0.698},
    "XRP": {100: 0.768, 1_000: 1.121, 10_000: 2.076},
    "SOL": {100: 0.925, 1_000: 1.034, 10_000: 1.834},
    "DOGE": {100: 1.707, 1_000: 1.839, 10_000: 3.724},
    "LINK": {100: 2.102, 1_000: 2.275, 10_000: 3.677},
    "LTC": {100: 2.035, 1_000: 3.028, 10_000: 5.245},
    "ADA": {100: 2.174, 1_000: 2.452, 10_000: 5.324},
    "AVAX": {100: 2.438, 1_000: 2.886, 10_000: 5.916},
    "DOT": {100: 3.684, 1_000: 5.545, 10_000: 12.412},
}


def test_table_matches_the_calibration_exactly():
    assert SPREAD_CALIBRATION == EXPECTED


def test_provenance_is_pinned_so_a_recalibration_cannot_be_silent():
    # A new window MUST come with a new stamp; these are the figures spec 00066 reports.
    assert CALIBRATION_WINDOW == ("2026-07-08T13:47:33Z", "2026-07-21T15:59:59Z")
    assert CALIBRATION_HOURS == 315
    assert CALIBRATION_MIN_ROWS == 1_123_509


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
        effective_spread_bps("BTC", bad)


def test_above_the_pinned_grid_refuses_rather_than_extrapolating():
    # Convex curve: extrapolating understates cost exactly where it matters most (spec 00066 D3).
    with pytest.raises(CostModelError, match="10000"):
        effective_spread_bps("DOT", 10_001)


def test_below_the_grid_clamps_to_the_floor():
    assert effective_spread_bps("BTC", 1.0) == EXPECTED["BTC"][100]


def test_interpolation_is_log_notional_and_respects_convexity():
    # DOT between 1k and 10k: sqrt(1k*10k) ~= 3162 is the log-midpoint.
    mid = effective_spread_bps("DOT", math.sqrt(1_000 * 10_000))
    lo, hi = EXPECTED["DOT"][1_000], EXPECTED["DOT"][10_000]
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
        cur = effective_spread_bps("DOT", notional)
        assert cur >= prev
        prev = cur


# --- round-trip composition ---------------------------------------------------------------------


def test_round_trip_cost_components_sum_to_total():
    r = round_trip_cost(1_000.0, pair="BTC", maker_rate=0.0040, taker_rate=0.0080)
    assert set(r) == {"fee", "spread", "carry", "total"}
    assert r["total"] == pytest.approx(r["fee"] + r["spread"] + r["carry"])


def test_spread_is_charged_once_per_side():
    notional = 1_000.0
    r = round_trip_cost(notional, pair="DOT", maker_rate=0.0, taker_rate=0.0)
    expected = 2 * notional * EXPECTED["DOT"][1_000] / 10_000
    assert r["spread"] == pytest.approx(expected)
    assert r["fee"] == 0.0


def test_fee_component_delegates_rather_than_reimplementing():
    from cli.costs.fees import round_trip_fee

    notional, maker, taker = 5_000.0, 0.0015, 0.0030
    r = round_trip_cost(notional, pair="ETH", maker_rate=maker, taker_rate=taker, taker_open=True)
    assert r["fee"] == round_trip_fee(notional, maker_rate=maker, taker_rate=taker, taker_open=True)


def test_spot_path_has_no_carry():
    r = round_trip_cost(1_000.0, pair="ETH", maker_rate=0.0040, taker_rate=0.0080)
    assert r["carry"] == 0.0


def test_carry_applies_whenever_a_margin_rate_is_given():
    r = round_trip_cost(1_000.0, pair="ETH", maker_rate=0.0, taker_rate=0.0, hold_hours=24.0, margin_rate_=0.0002)
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
    r = round_trip_cost(1_000.0, pair="ETH", maker_rate=0.0, taker_rate=0.0, hold_hours=hold_hours, margin_rate_=0.0002)
    assert r["carry"] == pytest.approx(expected)


def test_carry_matches_margin_carry_exactly_rather_than_reimplementing():
    from cli.costs.margin import margin_carry

    r = round_trip_cost(2_500.0, pair="BTC", maker_rate=0.0, taker_rate=0.0, hold_hours=13.0, margin_rate_=0.0003)
    assert r["carry"] == margin_carry(2_500.0, 13.0, 0.0003)


def test_at_tier_one_fees_dominate_spread_even_on_the_widest_pair():
    # Spec 00066 D4: the spread term is additive to the fee term, never a substitute. If a future
    # edit swapped one for the other this guard catches the order-of-magnitude error.
    r = round_trip_cost(1_000.0, pair="DOT", maker_rate=0.0040, taker_rate=0.0080, taker_open=True, taker_close=True)
    assert r["fee"] > 10 * r["spread"]


def test_round_trip_rejects_a_notional_the_grid_cannot_price():
    with pytest.raises(CostModelError):
        round_trip_cost(50_000.0, pair="BTC", maker_rate=0.0040, taker_rate=0.0080)
