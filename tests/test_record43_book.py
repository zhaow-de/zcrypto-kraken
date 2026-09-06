"""Tests for the trial-43 stage-1 re-derivation and the 43-vs-44 cost sweep
(cli/portfolio/record43_book.py): the helper tests run anywhere, the DATA_ROOT-gated ones need the
canonical data/ohlc-full machine and share one derivation through module-scoped fixtures.
"""

from datetime import datetime, timedelta

import pytest

from cli.portfolio.record43_book import (
    DATA_ROOT,
    REGISTRY_PATH,
    WEIGHT_WINDOW,
    bisect_sign_change,
    crossing_43v44,
    dense_day_index,
    load_union,
    position_turnover,
    record44_stress_axis,
    rederive_record43_book,
    sleeve_weights,
    stressed_ungoverned,
)
from cli.registry import TrialRegistry

# Bar counts of the frozen trial-43/44 oracle. Cheap stand-in for the full extent guard: if the
# dataset drifts, every figure below is void, so fail before comparing any of them.
UNION_BARS = {1440: 4582, 240: 27338}

EQUAL_THIRDS = (1 / 3, 1 / 3, 1 / 3)


def registered_metrics(trial_id: int) -> dict:
    return {r.trial_id: r.metrics for r in TrialRegistry(REGISTRY_PATH).records}[trial_id]


def _alternating(amplitude: float, n: int) -> list[float]:
    """A zero-mean series whose population stdev over any even-length window is `amplitude`."""
    return [amplitude if k % 2 == 0 else -amplitude for k in range(n)]


def test_sleeve_weights_are_equal_thirds_through_the_180_bar_warmup():
    """No trailing window exists before bar 180, so every one of those bars takes the 1/3 fallback."""
    n = WEIGHT_WINDOW + 2
    nets = [_alternating(a, n) for a in (0.01, 0.02, 0.04)]

    weights, warmup_bars, zero_vol_bars = sleeve_weights(nets)

    assert (warmup_bars, zero_vol_bars) == (WEIGHT_WINDOW, 0)
    assert weights[:WEIGHT_WINDOW] == [EQUAL_THIRDS] * WEIGHT_WINDOW
    # The first live bar: weights proportional to 1/vol over bars [0, 180) — 1/0.01 : 1/0.02 : 1/0.04.
    assert weights[WEIGHT_WINDOW] == pytest.approx((4 / 7, 2 / 7, 1 / 7), rel=1e-9)


def test_sleeve_weights_fall_back_to_equal_thirds_on_a_zero_vol_window():
    """ANY degenerate sleeve takes the whole bar back to 1/3 — not just that sleeve's own weight."""
    n = WEIGHT_WINDOW + 2
    nets = [_alternating(0.01, n), _alternating(0.02, n), [0.0] * n]

    weights, warmup_bars, zero_vol_bars = sleeve_weights(nets)

    assert (warmup_bars, zero_vol_bars) == (WEIGHT_WINDOW, 2)
    assert weights[WEIGHT_WINDOW] == EQUAL_THIRDS
    assert weights[WEIGHT_WINDOW + 1] == EQUAL_THIRDS


def test_sleeve_weights_read_the_window_through_k_minus_1_only():
    """Bar k's window is [k-180, k) — bar k's own return must not reach its own weight."""
    n = WEIGHT_WINDOW + 1
    quiet = _alternating(0.01, n)
    # A single huge value AT bar 180: it would dominate any window that included it.
    spiked = _alternating(0.01, n)
    spiked[WEIGHT_WINDOW] = 5.0

    assert sleeve_weights([quiet, quiet, quiet])[0][WEIGHT_WINDOW] == sleeve_weights([spiked, quiet, quiet])[0][WEIGHT_WINDOW]


def test_dense_day_index_compresses_absent_calendar_days():
    """Governor days are dense ranks of the CLOSE stamp's date — a calendar day with no bar is simply
    absent (record 33's ratified semantics), and dense ranks keep the helper's contiguity guard."""
    # Bars closing on day 1, day 1, then day 3 — day 2 has no bar at all.
    h4_ts = [
        datetime(2013, 9, 10, 20),
        datetime(2013, 9, 11, 0),
        datetime(2013, 9, 11, 4),
        datetime(2013, 9, 13, 0),
    ]

    assert dense_day_index(h4_ts, 3) == [0, 0, 1]


def test_position_turnover_starts_flat_and_charges_the_entry_bar():
    """Bar 0 pays full entry (prev = 0.0), every later bar the per-asset absolute change."""
    positions = {"A": [0.2, 0.2, 0.0], "B": [0.0, -0.1, -0.1]}

    assert position_turnover(positions, 3, assets=("A", "B")) == pytest.approx([0.2, 0.1, 0.2])


def test_stressed_ungoverned_charges_the_extra_cost_on_the_books_own_turnover():
    """The ×1.0 book's net minus (m-1) x 0.006 per unit of ITS turnover — positions are never
    rebuilt at the stressed cost."""
    ungoverned = [0.010, -0.020]
    turnover = [1.0, 2.0]

    assert stressed_ungoverned(ungoverned, turnover, cost_multiplier=1.0) == ungoverned
    assert stressed_ungoverned(ungoverned, turnover, cost_multiplier=1.5) == [0.010 - 1.0 * 0.003, -0.020 - 2.0 * 0.003]
    assert stressed_ungoverned(ungoverned, turnover, cost_multiplier=2.0) == [0.010 - 1.0 * 0.006, -0.020 - 2.0 * 0.006]


def test_bisect_sign_change_brackets_the_flip_to_the_requested_width():
    """A jagged step function has no smooth root, so the contract is a BRACKET of the requested width
    whose ends straddle the flip — not a root-finder's convergence claim."""
    flip = 1.6180339

    low, high, midpoint = bisect_sign_change(lambda m: 1.0 if m < flip else -1.0, 1.0, 2.0, refine_to=0.001)

    assert high - low <= 0.001
    assert low < flip < high
    assert midpoint == pytest.approx((low + high) / 2)


@pytest.fixture(scope="module")
def unions():
    """The two frozen union grids, loaded once for the whole module, extent-guarded before use."""
    daily_ts, daily_prices = load_union(1440)
    h4_ts, h4_prices = load_union(240)
    for interval, ts in ((1440, daily_ts), (240, h4_ts)):
        assert len(ts) == UNION_BARS[interval], (
            f"canonical dataset drifted — STOP: {interval} union has {len(ts)} bars, expected "
            f"{UNION_BARS[interval]}; every record-43 figure below is void until that is explained"
        )
    return daily_ts, daily_prices, h4_ts, h4_prices


@pytest.fixture(scope="module")
def book(unions):
    daily_ts, daily_prices, h4_ts, h4_prices = unions
    return rederive_record43_book(daily_ts, daily_prices, h4_ts, h4_prices)


@pytest.fixture(scope="module")
def sweep(unions, book):
    daily_ts, daily_prices, h4_ts, h4_prices = unions
    axis44 = record44_stress_axis(daily_ts, daily_prices, h4_ts, h4_prices)
    return crossing_43v44(book["stress_axis"], axis44)


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_record43_stage1_reproduces_the_registered_row(book):
    registered = registered_metrics(43)

    # Integer counts and criterion flags: registered exactly, so no tolerance.
    for key in (
        "cap_breach_bars",
        "governor_engaged_bars",
        "weight_warmup_bars",
        "weight_zero_vol_fallback_bars",
        "criterion_dd_aware",
        "criterion_sharpe_primary",
    ):
        assert book[key] == registered[key], key

    # Figures the registry rounded when it stored them.
    for key, places in (
        ("ann_sharpe_noc", 4),
        ("ann_sharpe_noc_decisive", 4),
        ("bench4h_sharpe_full", 4),
        ("bench4h_sharpe_decisive", 4),
        ("maxdd", 4),
        ("maxdd_pre_governor", 4),
        ("spot_drag_pct_yr", 4),
    ):
        assert round(book[key], places) == registered[key], key

    # The row's own headline reading of itself: ADOPT under the Sharpe-primary branch, not the
    # DD-aware one.
    assert (book["criterion_sharpe_primary"], book["criterion_dd_aware"]) == (1, 0)

    # The QA gates the driver runs before any headline counts — each one anchored to a figure that
    # was registered by an earlier trial, so a silently-changed upstream primitive fails here.
    qa = book["qa"]
    assert qa["b_sleeve_max_abs_diff_vs_builder"] < 1e-12
    assert round(qa["b_sleeve_daily_sharpe"], 4) == 1.2455
    assert round(qa["a1lf_book_sharpe"], 4) == 1.3798
    assert [round(s, 4) for s in qa["a2_arm_sharpes"].values()] == [1.3274, 1.3017, 1.3585]
    # The close-time expansion mapping: raw bar-start stamps would inflate B to ~1.76, so these two
    # readings are that mapping's regression pin.
    assert round(qa["expansion_sharpes"]["B"], 4) == 1.2704
    assert round(qa["expansion_sharpes"]["A1"], 4) == 1.3927

    for stats in qa["weight_stats"]:
        assert stats["max"] - stats["min"] > 1e-6
        assert 0.0 < stats["min"] and stats["max"] < 1.0


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_both_books_reproduce_every_registered_cost_stress_anchor(sweep):
    """The load-bearing validation: no sweep point means anything until BOTH instruments land on all
    four registered stress figures and both ×1.0 headlines. A miss is a porting defect, never a
    number to tune."""
    anchors = sweep["anchors"]
    for trial_id in (43, 44):
        registered = registered_metrics(trial_id)
        assert round(anchors[trial_id][1.0], 4) == registered["ann_sharpe_noc"], trial_id
        assert round(anchors[trial_id][1.5], 4) == registered["cost_stress_1_5x_sharpe_ann"], trial_id
        assert round(anchors[trial_id][2.0], 4) == registered["cost_stress_2x_sharpe_ann"], trial_id

    # Record 44's own governed series, re-derived through this module's stress machinery at ×1.0,
    # must be the builder's — the trial-44 half of the instrument validation.
    assert sweep["record44_x1_max_abs_diff_vs_builder"] < 1e-12


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_neither_book_holds_a_durable_lead_across_the_cost_axis(sweep):
    """Record 44 leads at the ×1.5 rung and record 43 at ×2.0 (both registered), the ordering
    changes sign between them, and both books still lead somewhere above the band — so no "beyond
    ×x it has reversed" reading survives. The flip count and the last flip's position move with the
    grid's step and ceiling, and are deliberately not pinned."""
    registered43, registered44 = registered_metrics(43), registered_metrics(44)
    assert registered44["cost_stress_1_5x_sharpe_ann"] > registered43["cost_stress_1_5x_sharpe_ann"]
    assert registered44["cost_stress_2x_sharpe_ann"] < registered43["cost_stress_2x_sharpe_ann"]

    anchors = sweep["anchors"]
    assert anchors[44][1.0] > anchors[43][1.0]
    assert anchors[44][1.5] > anchors[43][1.5]
    assert anchors[44][2.0] < anchors[43][2.0]

    # The sign changes somewhere between the two registered rungs — which is all the registry
    # discloses, and all this test is entitled to claim about that interval.
    assert [pair for pair in sweep["flip_brackets"] if 1.5 <= pair[0] and pair[1] <= 2.0]

    # Neither book owns the tail: each still leads at some point above ×2.0, so any durable-reversal
    # claim would be an artifact of where the sweep stops.
    assert sweep["lead_counts"][43] > 0 and sweep["lead_counts"][44] > 0
    assert sweep["highest_lead_multiplier"][43] > 2.0
    assert sweep["highest_lead_multiplier"][44] > 2.0

    # A claim about the measured execution band is only earned if the sweep covered it, and the band
    # is not one-sided either.
    band_low, band_high = sweep["realistic_band"]
    assert sweep["grid"][0][0] <= band_low and sweep["grid"][-1][0] >= band_high
    assert sweep["band"]["lead_counts"][43] > 0 and sweep["band"]["lead_counts"][44] > 0
    assert sweep["band"]["flip_brackets"]

    # The flip-bracket and tail claims above are only resolvable on a grid this fine and this long.
    params = sweep["sweep_parameters"]
    assert params["step"] <= 0.002 and params["high"] >= 3.0
