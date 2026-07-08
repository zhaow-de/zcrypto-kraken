import math
import statistics

import pytest

from cli.validation import ValidationError, bootstrap_ci, stationary_bootstrap_indices


def test_indices_reproducible_and_bounded():
    a = stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed=1)
    b = stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed=1)
    assert a == b
    assert len(a) == 5 and all(len(r) == 10 for r in a)
    assert all(0 <= i < 10 for r in a for i in r)


def test_indices_different_seed_differs():
    a = stationary_bootstrap_indices(50, mean_block=5, n_resamples=3, seed=1)
    b = stationary_bootstrap_indices(50, mean_block=5, n_resamples=3, seed=2)
    assert a != b


def test_indices_mean_block_one_is_valid():
    a = stationary_bootstrap_indices(8, mean_block=1, n_resamples=4, seed=1)
    assert len(a) == 4 and all(len(r) == 8 and all(0 <= i < 8 for i in r) for r in a)


def test_ci_reproducible():
    kw = dict(mean_block=4, n_resamples=200, seed=7)
    assert bootstrap_ci([float(i % 5) for i in range(40)], statistics.mean, **kw) == bootstrap_ci(
        [float(i % 5) for i in range(40)], statistics.mean, **kw
    )


def test_ci_constant_series_is_exact():
    r = bootstrap_ci([5.0] * 20, statistics.mean, mean_block=4, seed=7)
    assert r["point"] == 5.0 and r["lower"] == 5.0 and r["upper"] == 5.0
    assert r["n_resamples"] == 1000 and r["mean_block"] == 4


def test_ci_varied_series_has_positive_width():
    r = bootstrap_ci([float(i) for i in range(50)], statistics.mean, mean_block=5, n_resamples=500, seed=3)
    assert math.isfinite(r["lower"]) and math.isfinite(r["upper"]) and math.isfinite(r["point"])
    assert r["lower"] < r["upper"]


@pytest.mark.parametrize(
    "series,kwargs",
    [
        ([], {"mean_block": 3, "seed": 1}),
        ([1.0, float("nan"), 2.0], {"mean_block": 3, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 0.5, "seed": 1}),
        ([1.0, 2.0], {"mean_block": float("inf"), "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "n_resamples": 0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "n_resamples": 2.5, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "n_resamples": float("nan"), "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "alpha": 0.0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "alpha": 1.0, "seed": 1}),
        ([1.0, 2.0], {"mean_block": 2, "seed": "x"}),
    ],
)
def test_ci_guards(series, kwargs):
    with pytest.raises(ValidationError):
        bootstrap_ci(series, statistics.mean, **kwargs)


def test_ci_statistic_returning_nan_raises():
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: float("nan"), mean_block=2, seed=1)


def test_ci_statistic_that_raises_is_validation_error():
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: xs[10**9], mean_block=2, seed=1)


def test_indices_guards():
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(0, mean_block=3, n_resamples=5, seed=1)
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(10, mean_block=3, n_resamples=5, seed="x")
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(10.5, mean_block=3, n_resamples=5, seed=1)
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(float("nan"), mean_block=3, n_resamples=5, seed=1)
    with pytest.raises(ValidationError):
        stationary_bootstrap_indices(10, mean_block=3, n_resamples=2.5, seed=1)


def test_ci_statistic_non_numeric_return_raises():
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: "not a number", mean_block=2, seed=1)
    with pytest.raises(ValidationError):
        bootstrap_ci([1.0, 2.0, 3.0], lambda xs: None, mean_block=2, seed=1)
