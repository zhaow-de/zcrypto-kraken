import math
from datetime import UTC, datetime, timedelta

import pytest

from cli.alpha.c2 import (
    STEP,
    cell_name,
    cell_reads,
    forward_returns,
    log_returns,
    moves,
    on_grid,
    per_year,
    rank_ic,
    signals,
    trailing_std,
)
from cli.alpha.errors import AlphaError


def _grid(n, start=datetime(2024, 1, 1, tzinfo=UTC)):
    return [start + i * STEP for i in range(n)]


def test_log_returns_are_none_at_index_0_and_across_a_non_15m_step():
    ts = _grid(3) + [_grid(3)[-1] + 2 * STEP]
    r = log_returns(ts, [100.0, 110.0, 121.0, 133.1])
    assert r[0] is None and r[3] is None
    assert r[1] == pytest.approx(math.log(1.1)) and r[2] == pytest.approx(math.log(1.1))


def test_trailing_std_is_the_sample_std_and_none_until_the_window_fills():
    vals = [None, 1.0, 2.0, 4.0, 8.0]
    s = trailing_std(vals, window=3)
    assert s[:3] == [None, None, None]
    assert s[3] == pytest.approx(1.5275252316519468)  # sample std of 1, 2, 4
    assert s[4] == pytest.approx(3.055050463303893)  # sample std of 2, 4, 8


def test_scale_is_none_while_a_gap_sits_inside_its_window():
    vals = [1.0, 2.0, None, 4.0, 5.0, 6.0]
    assert trailing_std(vals, window=3)[4] is None and trailing_std(vals, window=3)[5] is not None


def test_moves_sum_the_last_lag_returns_and_are_none_over_a_gap():
    r = [None, 0.1, 0.2, None, 0.3, 0.4]
    assert moves(r, lag=1)[1:3] == [0.1, 0.2]
    assert moves(r, lag=2)[2] == pytest.approx(0.3) and moves(r, lag=2)[4] is None and moves(r, lag=2)[5] == pytest.approx(0.7)


def test_signals_fire_beyond_threshold_times_sigma_times_sqrt_lag_on_either_side():
    m = [0.05, -0.05, 0.01, None, 0.05]
    sig = [0.02, 0.02, 0.02, 0.02, None]
    assert signals(m, sig, lag=4, threshold=1.0) == [1, -1, 0, 0, 0]  # 0.02*2 = 0.04 < 0.05
    assert signals(m, sig, lag=4, threshold=2.0) == [0, 0, 0, 0, 0]  # 0.02*2*2 = 0.08 > 0.05


def test_on_grid_drops_a_follower_bar_the_leader_lacks():
    grid = _grid(4)
    ts = [grid[0], grid[1], grid[1] + timedelta(minutes=7), grid[3]]
    closes, on, off = on_grid(grid, ts, [1.0, 2.0, 9.0, 4.0])
    assert closes == [1.0, 2.0, None, 4.0] and (on, off) == (3, 1)


def test_on_grid_refuses_a_duplicate_leader_stamp():
    g = _grid(3)
    with pytest.raises(AlphaError, match="duplicate"):
        on_grid(g + [g[-1]], g, [1.0, 1.0, 1.0])


def test_forward_return_is_none_across_a_leader_gap():
    grid = _grid(3) + [_grid(3)[-1] + 2 * STEP, _grid(3)[-1] + 3 * STEP]
    fwd = forward_returns(grid, [1.0, 2.0, 4.0, 8.0, 16.0], horizon=1)
    assert fwd[0] == pytest.approx(math.log(2)) and fwd[2] is None and fwd[3] == pytest.approx(math.log(2)) and fwd[4] is None
    # Both ends present, 15m steps, the close between absent.
    assert forward_returns(grid, [1.0, None, 4.0, 8.0, 16.0], horizon=2)[0] is None


def test_cell_reads_with_no_trade_and_with_one_trade():
    years = [2024, 2024, 2025]
    none = cell_reads([0, 0, 0], "up", [0.1, 0.1, 0.1], years)
    assert none == {"per_year": {"2024": {"n": 0}, "2025": {"n": 0}}, "n": 0}
    one = cell_reads([1, 0, 0], "up", [0.03, 0.1, 0.1], years)
    assert one["n"] == 1 and one["mean_gross"] == pytest.approx(0.03) and one["mean_net"] == pytest.approx(0.018) and "p" not in one
    assert one["per_year"]["2025"] == {"n": 0}


def test_cell_reads_take_the_down_side_short_and_skip_an_absent_forward():
    years = [2024] * 4
    c = cell_reads([-1, -1, 1, -1], "down", [-0.02, None, 0.5, -0.04], years, n_resamples=50)
    assert c["n"] == 2 and c["mean_gross"] == pytest.approx(0.03) and c["mean_net"] == pytest.approx(0.018)
    assert 0.0 < c["p"] <= 1.0


def test_cell_reads_file_each_trade_under_its_own_bars_year_and_bootstrap_the_net():
    c = cell_reads([0, 1, 1, 1, 1], "up", [0.5, 0.01, 0.03, None, 0.05], [2023, 2024, 2024, 2025, 2025], n_resamples=50)
    assert c["per_year"]["2023"] == {"n": 0}
    assert c["per_year"]["2024"] == pytest.approx({"n": 2, "mean_gross": 0.02, "mean_net": 0.008})
    assert c["per_year"]["2025"] == pytest.approx({"n": 1, "mean_gross": 0.05, "mean_net": 0.038})
    below = cell_reads([1] * 40, "up", [0.004, 0.008] * 20, [2024] * 40, n_resamples=50)
    assert below["mean_gross"] == pytest.approx(0.006) and below["p"] > 0.5


def test_a_planted_lead_is_recovered_and_a_null_reads_zero():
    # Leader moves +1 at even bars; the follower's next bar return equals the leader's move: gross 0.05 a trade, net 0.038.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    planted = cell_reads(sig, "up", fwd, years, n_resamples=200)
    assert planted["n"] == 100 and planted["mean_gross"] == pytest.approx(0.05) and planted["p"] < 0.05
    null = cell_reads(sig, "up", [0.0] * 200, years, n_resamples=200)
    assert null["mean_gross"] == pytest.approx(0.0) and null["p"] >= 0.99


def test_a_trade_reads_the_forward_return_at_its_own_signal_index():
    # The planted lead above with every signal one bar later: each trade then reads an odd bar's -0.05, never its neighbour's.
    years = [2024] * 200
    sig = [1 if i % 2 == 0 else 0 for i in range(200)]
    fwd = [0.05 if i % 2 == 0 else -0.05 for i in range(200)]
    delayed = [0] + sig[:-1]
    assert cell_reads(delayed, "up", fwd, years, n_resamples=50)["mean_gross"] == pytest.approx(-0.05)


def test_rank_ic_is_spearman_and_none_without_two_pairs_or_variance():
    assert rank_ic([1.0, 2.0, 3.0, None], [10.0, 30.0, 20.0, 5.0]) == pytest.approx(0.5)
    assert rank_ic([1.0, None], [1.0, 2.0]) is None
    assert rank_ic([1.0, 1.0, 1.0], [1.0, 2.0, 3.0]) is None


def test_per_year_groups_present_values_keys_every_year_and_refuses_unequal_lengths():
    assert per_year([1.0, None, 3.0], [2023, 2023, 2024]) == {"2023": [1.0], "2024": [3.0]}
    assert per_year([None, 3.0], [2023, 2024]) == {"2023": [], "2024": [3.0]}
    with pytest.raises(ValueError):
        per_year([1.0], [2023, 2024])


def test_cell_name():
    assert cell_name("ETH/EUR", 1, 2, 4, "up") == "ETH/EUR|L1|th2|H4|up"
