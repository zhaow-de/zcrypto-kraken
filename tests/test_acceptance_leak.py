import statistics

from cli.validation import cpcv_splits, nn_leak_metric, overlapping_label_series

N, H, N_GROUPS = 1000, 30, 40


def _mean_leak(*, label_horizon, embargo):
    x, y = overlapping_label_series(N, horizon=H, seed=11)
    splits = cpcv_splits(N, n_groups=N_GROUPS, n_test_groups=1, label_horizon=label_horizon, embargo=embargo)
    return statistics.mean(nn_leak_metric(x, y, s["train"], s["test"]) for s in splits)


def test_embargo_removes_the_injected_leak():
    # Unpurged, the 1-NN-by-index probe's nearest train neighbour sits inside the label overlap and a
    # signal-free series shows OOS skill; label_horizon=H drops the H indices before each test block
    # and embargo=H the H after, so every neighbour is > H away and Cov(y_i, y_j) = 0.
    leaked = _mean_leak(label_horizon=0, embargo=0)
    purged = _mean_leak(label_horizon=H, embargo=H)
    assert leaked > 5.0
    assert abs(purged) < 2.0
    assert leaked > 5 * abs(purged)
