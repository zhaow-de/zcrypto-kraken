import math
import statistics

import pytest

from cli.validation import (
    ValidationError,
    linear_signal,
    nn_leak_metric,
    outperformance_matrix,
    overlapping_label_series,
    sign_strategy_returns,
)


def test_linear_signal_reproducible():
    a = linear_signal(50, beta=0.5, noise_sd=1.0, seed=1)
    b = linear_signal(50, beta=0.5, noise_sd=1.0, seed=1)
    assert a == b
    assert a != linear_signal(50, beta=0.5, noise_sd=1.0, seed=2)


def test_linear_signal_shape():
    x, r = linear_signal(100, beta=0.5, noise_sd=1.0, seed=3)
    assert len(x) == 100 and len(r) == 100
    assert all(math.isfinite(v) for v in [*x, *r])


def test_linear_signal_null_low_correlation():
    x, r = linear_signal(5000, beta=0.0, noise_sd=1.0, seed=4)
    assert abs(statistics.correlation(x, r)) < 0.1


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n": 0, "beta": 0.5, "noise_sd": 1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": 1.0, "seed": "x"},
        {"n": 10, "beta": float("nan"), "noise_sd": 1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": -1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": float("inf"), "seed": 1},
        {"n": 10, "beta": "x", "noise_sd": 1.0, "seed": 1},
        {"n": 10, "beta": 0.5, "noise_sd": "x", "seed": 1},
    ],
)
def test_linear_signal_guards(kwargs):
    with pytest.raises(ValidationError):
        linear_signal(**kwargs)


def test_sign_strategy_returns_basic():
    assert sign_strategy_returns([1.0, -1.0, 0.5], [2.0, 3.0, 4.0]) == [2.0, -3.0, 4.0]
    assert sign_strategy_returns([0.0], [5.0]) == [5.0]  # sign at 0 -> +1


@pytest.mark.parametrize("features,targets", [([1.0], [1.0, 2.0]), ([], []), ([1.0, float("nan")], [1.0, 2.0])])
def test_sign_strategy_returns_guards(features, targets):
    with pytest.raises(ValidationError):
        sign_strategy_returns(features, targets)


def test_overlapping_label_series_reproducible_and_shaped():
    a = overlapping_label_series(50, horizon=5, seed=1)
    assert a == overlapping_label_series(50, horizon=5, seed=1)
    x, y = a
    assert len(x) == 50 and len(y) == 50 and x == [float(t) for t in range(50)]


def test_overlapping_label_covariance():
    _x, y = overlapping_label_series(20000, horizon=10, seed=2)
    import statistics as _st

    var = _st.variance(y)
    cov1 = _st.covariance(y[:-1], y[1:])  # |i-j|=1 -> ~ horizon-1 = 9
    cov_h = _st.covariance(y[:-10], y[10:])  # |i-j|=horizon -> ~0
    assert abs(var - 10) < 1.0
    assert abs(cov1 - 9) < 1.0
    assert abs(cov_h) < 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n": 0, "horizon": 5, "seed": 1},
        {"n": 10, "horizon": 0, "seed": 1},
        {"n": 10, "horizon": 2.5, "seed": 1},
        {"n": 10, "horizon": 5, "seed": "x"},
    ],
)
def test_overlapping_label_series_guards(kwargs):
    with pytest.raises(ValidationError):
        overlapping_label_series(**kwargs)


def test_nn_leak_metric_nearest_pick():
    # features = index; test point 2's nearest train index is 1 (or 3). labels chosen so the pick is unambiguous.
    feats = [0.0, 1.0, 2.0, 3.0, 4.0]
    labels = [10.0, 5.0, 100.0, 5.0, 10.0]
    # train {0,1,3,4}, test {2}: nearest to index 2 is 1 or 3 (dist 1); tie -> smaller |i-j| equal -> smaller j = 1
    assert nn_leak_metric(feats, labels, [0, 1, 3, 4], [2]) == 5.0 * 100.0


@pytest.mark.parametrize(
    "args",
    [
        ([1.0], [1.0, 2.0], [0], [0]),  # length mismatch
        ([1.0, 2.0], [1.0, 2.0], [], [0]),  # empty train
        ([1.0, 2.0], [1.0, 2.0], [0], []),  # empty test
        ([1.0, 2.0], [1.0, 2.0], [5], [0]),  # out-of-range
        ([1.0, float("nan")], [1.0, 2.0], [0], [1]),  # non-finite
    ],
)
def test_nn_leak_metric_guards(args):
    with pytest.raises(ValidationError):
        nn_leak_metric(*args)


def test_outperformance_matrix_reproducible_and_shaped():
    a = outperformance_matrix(30, 4, edge=0.5, seed=1)
    assert a == outperformance_matrix(30, 4, edge=0.5, seed=1)
    assert len(a) == 30 and all(len(r) == 4 for r in a)


def test_outperformance_matrix_edge_column_leads():
    m = outperformance_matrix(5000, 4, edge=0.5, seed=2, edge_col=1)
    means = [statistics.mean(row[k] for row in m) for k in range(4)]
    assert means[1] == pytest.approx(0.5, abs=0.1)
    assert all(abs(means[k]) < 0.1 for k in (0, 2, 3))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"n_periods": 0, "n_strategies": 3, "edge": 0.1, "seed": 1},
        {"n_periods": 10, "n_strategies": 0, "edge": 0.1, "seed": 1},
        {"n_periods": 10, "n_strategies": 3, "edge": "x", "seed": 1},
        {"n_periods": 10, "n_strategies": 3, "edge": 0.1, "seed": "x"},
        {"n_periods": 10, "n_strategies": 3, "edge": 0.1, "seed": 1, "edge_col": 3},
    ],
)
def test_outperformance_matrix_guards(kwargs):
    with pytest.raises(ValidationError):
        outperformance_matrix(**kwargs)
