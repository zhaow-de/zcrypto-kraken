import math
import statistics
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from cli.portfolio.revalidation import (
    DECISIVE_START,
    METRIC_KEYS,
    P1_VAR_TRIALS,
    RECORD_47_RETURNS,
    RECORD_47_SHARPE,
    REFERENCE_LAST_BAR,
    SLICE_START,
    Band,
    RevalidationError,
    band,
    legs,
    prefix_end,
    revalidation_metrics,
    revalidation_verdict,
    slice_bounds,
)
from cli.validation import deflated_sharpe_ratio, max_drawdown, sharpe
from tests.test_trial_registry_provenance import _trials

_FIRST = datetime(2025, 1, 1, tzinfo=UTC)
_LAST = datetime(2026, 10, 10, 20, tzinfo=UTC)
_FOUR_HOURS = timedelta(hours=4)


def _grid(first: datetime, n: int) -> list[datetime]:
    return [first + k * _FOUR_HOURS for k in range(n)]


def _span() -> list[datetime]:
    return _grid(_FIRST, (_LAST - _FIRST) // _FOUR_HOURS + 1)


def _slice(grid: list[datetime]) -> tuple[int, int]:
    return grid.index(datetime(2026, 7, 10, tzinfo=UTC)), len(grid) - 1


def _planted() -> tuple[list[datetime], list[float], list[float], list[float]]:
    grid = _span()
    n = len(grid) - 1
    lo, hi = _slice(grid)
    governed = [(3 if i < 1380 else 1) * 0.001 * math.sin(i / 7) for i in range(n)]
    governed[2087:2107] = [-0.002] * 20
    governed[lo:hi] = governed[1380 : 1380 + (hi - lo)]
    ungoverned = [0.0015 * math.sin(i / 5 + 1) for i in range(n)]
    bench = [0.0008 * math.sin(i / 11 + 2) - 0.0003 for i in range(n)]
    return grid, governed, ungoverned, bench


def _record_47(metrics: dict) -> dict:
    return {**metrics, "in_sample_returns": 27337, "in_sample_sharpe": 1.5609}


def test_the_slice_starts_at_the_first_return_whose_first_bar_is_on_or_after_its_start():
    assert slice_bounds(_grid(datetime(2026, 7, 9, 12, tzinfo=UTC), 10), SLICE_START) == (3, 9)
    lo, hi = slice_bounds(_grid(datetime(2026, 7, 8, tzinfo=UTC), 12), SLICE_START)
    assert lo == hi


def test_the_reference_ends_at_the_last_return_whose_second_bar_is_on_or_before_its_end():
    assert prefix_end(_grid(datetime(2026, 3, 31, 8, tzinfo=UTC), 6), REFERENCE_LAST_BAR) == 3


def test_no_return_inside_the_holdout_window_enters_a_metric():
    grid = _span()
    series = [0.001 * math.sin(i) for i in range(len(grid) - 1)]
    first, last = datetime(2026, 3, 31, 20, tzinfo=UTC), datetime(2026, 7, 9, 20, tzinfo=UTC)
    spoiled = [0.5 if first <= grid[i] <= last else r for i, r in enumerate(series)]
    assert revalidation_metrics(spoiled, spoiled, spoiled, grid, n_trials=6) == revalidation_metrics(
        series, series, series, grid, n_trials=6
    )


def test_the_band_counts_every_window_that_fits_and_none_past_the_end():
    returns = [0.001 * math.sin(i) for i in range(20)]
    assert band(returns, 8, step=6).sharpes == tuple(sharpe(returns[s : s + 8], periods_per_year=2190) for s in (0, 6, 12))
    assert len(band(returns, 20, step=6).sharpes) == 1
    with pytest.raises(RevalidationError, match="reference's 20 returns hold no window of 21"):
        band(returns, 21, step=6)


def test_a_slice_equal_to_a_band_window_reads_that_windows_sharpe_and_drawdown():
    grid, governed, ungoverned, bench = _planted()
    metrics = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=6)
    window = governed[1380 : 1380 + metrics["slice_returns"]]
    assert metrics["slice_sharpe"] == sharpe(window, periods_per_year=2190)
    assert metrics["slice_maxdd"] == max_drawdown(window)
    assert (metrics["leg_sharpe_pass"], metrics["leg_maxdd_pass"]) == (1, 1)


def test_each_reported_read_is_computed_over_its_own_returns():
    grid, governed, ungoverned, bench = _planted()
    metrics = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=7)
    lo, hi = _slice(grid)
    in_sample, slice_returns = metrics["in_sample_returns"], metrics["slice_returns"]
    assert in_sample == prefix_end(grid, REFERENCE_LAST_BAR)
    assert metrics["in_sample_sharpe"] == sharpe(governed[:in_sample], periods_per_year=2190)
    assert metrics["reference_returns"] == in_sample - 1380
    assert slice_returns == hi - lo
    reference = governed[1380:in_sample]
    windows = [reference[s : s + slice_returns] for s in range(0, len(reference) - slice_returns + 1, 6)]
    assert metrics["band_windows"] == (metrics["reference_returns"] - slice_returns) // 6 + 1 == len(windows)
    sharpes = [sharpe(w, periods_per_year=2190) for w in windows]
    assert metrics["band_sharpe_q05"] == float(np.percentile(sharpes, 5))
    assert metrics["band_maxdd_q95"] == float(np.percentile([max_drawdown(w) for w in windows], 95))
    assert windows[0] == governed[lo:hi]
    assert metrics["slice_sharpe_rank"] == sum(s <= metrics["slice_sharpe"] for s in sharpes) / metrics["band_windows"]
    assert metrics["slice_sharpe_ungoverned"] == sharpe(ungoverned[lo:hi], periods_per_year=2190)
    assert metrics["slice_bench4h_sharpe"] == sharpe(bench[lo:hi], periods_per_year=2190)
    mean_diff = statistics.fmean(governed[lo:hi]) - statistics.fmean(bench[lo:hi])
    assert mean_diff > 0
    assert metrics["slice_mean_diff_vs_bench4h"] == pytest.approx(mean_diff)
    assert metrics["slice_dsr"] == deflated_sharpe_ratio(
        sharpe(governed[lo:hi]), slice_returns, n_trials=7, var_trials=P1_VAR_TRIALS
    )


def test_a_slice_planted_below_the_bands_5th_percentile_fails_leg_1():
    grid, governed, ungoverned, bench = _planted()
    lo, hi = _slice(grid)
    governed[lo:hi] = [-0.00002 + 0.00001 * math.sin(i / 7) for i in range(hi - lo)]
    metrics = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=6)
    assert metrics["slice_sharpe"] < metrics["band_sharpe_q05"]
    assert (metrics["leg_sharpe_pass"], metrics["leg_maxdd_pass"]) == (0, 1)
    assert revalidation_verdict(_record_47(metrics)) == "park"


def test_a_slice_planted_past_the_bands_95th_percentile_drawdown_fails_leg_2():
    grid, governed, ungoverned, bench = _planted()
    lo, _ = _slice(grid)
    governed[lo + 100 : lo + 120] = [-0.004] * 20
    governed[lo + 120 : lo + 140] = [0.004] * 20
    metrics = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=6)
    assert metrics["slice_maxdd"] > metrics["band_maxdd_q95"]
    assert (metrics["leg_sharpe_pass"], metrics["leg_maxdd_pass"]) == (1, 0)
    assert revalidation_verdict(_record_47(metrics)) == "park"


def test_a_leg_at_its_band_edge_passes():
    edge = Band(sharpe_q05=-1.25, maxdd_q95=0.0625, sharpes=(-1.25, 0.5, 2.0))
    assert legs(edge.sharpe_q05, edge.maxdd_q95, edge) == (1, 1)
    assert legs(math.nextafter(edge.sharpe_q05, -math.inf), math.nextafter(edge.maxdd_q95, math.inf), edge) == (0, 0)


@pytest.mark.parametrize(
    "in_sample_returns,in_sample_sharpe,verdict",
    [
        (27336, 1.5609, None),
        (27337, 1.5609 + 0.00006, None),
        (27337, 1.5609 - 0.00006, None),
        (27337, 1.5609 + 0.00004, "adopt"),
        (27337, 1.5609 - 0.00004, "adopt"),
    ],
)
def test_the_instrument_check_gives_no_verdict_off_record_47(in_sample_returns, in_sample_sharpe, verdict):
    metrics = {
        **dict.fromkeys(METRIC_KEYS, 0),
        "in_sample_returns": in_sample_returns,
        "in_sample_sharpe": in_sample_sharpe,
        "leg_sharpe_pass": 1,
        "leg_maxdd_pass": 1,
    }
    assert revalidation_verdict(metrics) == verdict


@pytest.mark.parametrize("returns", [0, 1, 179])
def test_a_short_slice_is_refused_before_any_metric(returns):
    grid = _grid(_FIRST, _slice(_span())[0] + returns + 1)
    series = [0.001 * math.sin(i) for i in range(len(grid) - 1)]
    with pytest.raises(RevalidationError, match=rf"holds {returns} returns,"):
        revalidation_metrics(series, series, series, grid, n_trials=6)


def test_a_slice_of_exactly_a_month_is_admitted():
    grid = _grid(_FIRST, _slice(_span())[0] + 180 + 1)
    series = [0.001 * math.sin(i) for i in range(len(grid) - 1)]
    assert revalidation_metrics(series, series, series, grid, n_trials=6)["slice_returns"] == 180


def test_the_metrics_carry_exactly_the_declared_keys():
    grid, governed, ungoverned, bench = _planted()
    metrics = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=6)
    assert set(metrics) == METRIC_KEYS
    assert {key: type(value) for key, value in metrics.items() if type(value) not in (int, float)} == {}


def test_a_flat_benchmark_slice_reads_a_zero_sharpe_and_moves_no_leg():
    grid, governed, ungoverned, bench = _planted()
    lo, hi = _slice(grid)
    flat = bench[:lo] + [0.0] * (hi - lo)
    planted = revalidation_metrics(governed, ungoverned, bench, grid, n_trials=6)
    flat_read = revalidation_metrics(governed, ungoverned, flat, grid, n_trials=6)
    assert flat_read["slice_bench4h_sharpe"] == 0.0
    moved = {"slice_bench4h_sharpe", "slice_mean_diff_vs_bench4h"}
    assert {k: v for k, v in flat_read.items() if k not in moved} == {k: v for k, v in planted.items() if k not in moved}
    assert (flat_read["leg_sharpe_pass"], flat_read["leg_maxdd_pass"]) == (1, 1)


def test_the_registered_constants_are_record_47s_and_p1s():
    trials = _trials()
    for n in (43, 44, 47):
        assert P1_VAR_TRIALS == 1.3058096692086857e-05 == trials[n]["metrics"]["var_trials_4h"]
    assert (
        (RECORD_47_RETURNS, RECORD_47_SHARPE, DECISIVE_START)
        == (27337, 1.5609, 1380)
        == tuple(trials[47]["metrics"][k] for k in ("n_bars_compared_4h", "ann_sharpe_noc", "decisive_start"))
    )
