"""Tests for the record-44 leg re-derivation (cli/portfolio/record44_legs.py): every leg of
record 44's benchmark-relative basis is pinned at its registered precision, so a change that
silently moves any of them fails here.
"""

from datetime import datetime, timedelta

import pytest

from cli.portfolio.record44_legs import (
    DATA_ROOT,
    REGISTRY_PATH,
    a1_family_var_trials_4h,
    calendar_year_slices,
    load_union,
    rederive_record44_legs,
)
from cli.registry import TrialRegistry

# Bar counts of the frozen trial-44 oracle. Cheap stand-in for the full extent guard: if the dataset
# drifts, every figure below is void, so fail before comparing any of them.
UNION_BARS = {1440: 4582, 240: 27338}


def registered_metrics() -> dict:
    return {r.trial_id: r.metrics for r in TrialRegistry(REGISTRY_PATH).records}[44]


def test_var_trials_4h_reproduces_registered_value_exactly():
    """The DSR leg's var_trials is derivable from the committed registry alone — no dataset needed.
    Bit-identical, not approximate: it is a pure function of the recorded A1 per-period Sharpes."""
    assert a1_family_var_trials_4h() == registered_metrics()["var_trials_4h"]


def test_calendar_year_slices_stamps_by_close_and_drops_stubs():
    """Bar k belongs to the year of h4_ts[k + 1], and the 2013/2026 stubs are excluded."""
    # The 20:00 bar STARTS in 2013 but CLOSES in 2014, so close-stamping keeps it and start-stamping
    # would drop it as a stub — the fixture discriminates the two conventions.
    h4_ts = [datetime(2013, 12, 31, 16) + timedelta(hours=4 * k) for k in range(4)]
    assert calendar_year_slices([1.0, 2.0, 3.0], h4_ts) == {"2014": [2.0, 3.0]}
    h4_ts_2026 = [datetime(2025, 12, 31, 16) + timedelta(hours=4 * k) for k in range(4)]
    assert calendar_year_slices([1.0, 2.0, 3.0], h4_ts_2026) == {"2025": [1.0]}


@pytest.mark.skipif(not DATA_ROOT.exists(), reason="canonical dataset not present")
def test_record44_legs_reproduce_the_registered_basis():
    registered = registered_metrics()
    daily_ts, daily_prices = load_union(1440)
    h4_ts, h4_prices = load_union(240)
    for interval, ts in ((1440, daily_ts), (240, h4_ts)):
        assert len(ts) == UNION_BARS[interval], (
            f"canonical dataset drifted — STOP: {interval} union has {len(ts)} bars, expected "
            f"{UNION_BARS[interval]}; every record-44 figure below is void until that is explained"
        )

    legs = rederive_record44_legs(daily_ts, daily_prices, h4_ts, h4_prices, var_trials=a1_family_var_trials_4h())

    # Exactly reproducible legs: the SPA p-values are (count + 1) / 2001 rationals and the
    # per-period Sharpe / var_trials are deterministic floats, so nothing here needs a tolerance.
    for key in (
        "per_period_sharpe_4h",
        "var_trials_4h",
        "spa_p_full",
        "spa_p_decisive",
        "spa_grid_b30_s7",
        "spa_grid_b30_s1234",
        "spa_grid_b102_s42",
        "spa_grid_b102_s7",
        "spa_grid_b102_s1234",
        "cap_breach_bars",
        "governor_engaged_bars",
        "worst_slice_relative_pass",
    ):
        assert legs[key] == registered[key], key

    # Legs the registry rounded when it stored them.
    for key, places in (
        ("ann_sharpe_noc", 4),
        ("ann_sharpe_noc_decisive", 4),
        ("bench4h_sharpe_full", 4),
        ("bench4h_sharpe_decisive", 4),
    ):
        assert round(legs[key], places) == registered[key], key
    assert legs["dsr"] == pytest.approx(registered["dsr"], abs=1e-6)

    # Every ratified leg still passes on the reproduced basis (the go/no-go's benchmark-relative arm).
    assert legs["spa_p_decisive"] < 0.05
    assert max(legs[k] for k in legs if k.startswith("spa_grid_")) < 0.05
    assert legs["dsr"] > 0.95
    assert legs["worst_slice_relative_pass"] == 1

    # The worst-slice diagnostic behind that bare flag — record 44's notes are its only other home.
    relative = legs["worst_slice_relative"]
    assert relative["worst_book_slice"] == "2022"
    assert relative["worst_benchmark_slice"] == "2014"
    assert round(relative["worst_book_sharpe"], 4) == -0.0290
    assert round(relative["worst_benchmark_sharpe"], 4) == -0.0797
    assert (relative["n_slices_book_smaller_drawdown"], relative["n_compared"]) == (6, 12)
    assert relative["skipped"] == []
