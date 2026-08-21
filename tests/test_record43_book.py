"""Tests for the trial-43 stage-1 re-derivation (cli/portfolio/record43_book.py).

The sleeve-weight unit tests run anywhere — they are the always-on cover for the one rule record 44
does not have (its weights are fixed 1/3, so nothing in `record44_legs` exercises the adaptive
branch). The end-to-end reproduction needs the canonical data/ohlc-full machine and takes ~2 min
(the three A2 arms and the two daily sleeves dominate); it pins every stage-1 figure registry row 43
registered, at the precision the row stores, so a change that silently moves any of them fails here.
"""

from datetime import datetime, timedelta

import pytest

from cli.portfolio.record43_book import (
    DATA_ROOT,
    REGISTRY_PATH,
    WEIGHT_WINDOW,
    dense_day_index,
    load_union,
    rederive_record43_book,
    sleeve_weights,
)
from cli.registry import TrialRegistry

# Bar counts of the frozen trial-43/44 oracle. Cheap stand-in for the full extent guard: if the
# dataset drifts, every figure below is void, so fail before comparing any of them.
UNION_BARS = {1440: 4582, 240: 27338}

EQUAL_THIRDS = (1 / 3, 1 / 3, 1 / 3)


def registered_metrics() -> dict:
    return {r.trial_id: r.metrics for r in TrialRegistry(REGISTRY_PATH).records}[43]


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


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_record43_stage1_reproduces_the_registered_row():
    registered = registered_metrics()
    daily_ts, daily_prices = load_union(1440)
    h4_ts, h4_prices = load_union(240)
    for interval, ts in ((1440, daily_ts), (240, h4_ts)):
        assert len(ts) == UNION_BARS[interval], (
            f"canonical dataset drifted — STOP: {interval} union has {len(ts)} bars, expected "
            f"{UNION_BARS[interval]}; every record-43 figure below is void until that is explained"
        )

    book = rederive_record43_book(daily_ts, daily_prices, h4_ts, h4_prices)

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
    # DD-aware one. Asserted on the flags rather than restated in prose.
    assert (book["criterion_sharpe_primary"], book["criterion_dd_aware"]) == (1, 0)

    # The QA gates the driver runs before any headline counts — each one anchored to a figure that
    # was registered by an earlier trial, so a silently-changed upstream primitive fails here.
    qa = book["qa"]
    assert qa["b_sleeve_max_abs_diff_vs_builder"] < 1e-12
    assert round(qa["b_sleeve_daily_sharpe"], 4) == 1.2455
    assert round(qa["a1lf_book_sharpe"], 4) == 1.3798
    assert [round(s, 4) for s in qa["a2_arm_sharpes"].values()] == [1.3274, 1.3017, 1.3585]
    # The close-time expansion mapping: raw bar-start stamps would inflate B to ~1.76 (the
    # look-ahead the pre-run review caught), so these two readings are the mapping's regression pin.
    assert round(qa["expansion_sharpes"]["B"], 4) == 1.2704
    assert round(qa["expansion_sharpes"]["A1"], 4) == 1.3927

    # Engagement: all three sleeve weights move, none pinned at 0 or 1.
    for stats in qa["weight_stats"]:
        assert stats["max"] - stats["min"] > 1e-6
        assert 0.0 < stats["min"] and stats["max"] < 1.0
