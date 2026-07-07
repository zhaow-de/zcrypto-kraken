import math
import statistics

import pytest

from cli.validation import ValidationError, pbo


def test_pbo_dominant_config_is_zero():
    r = pbo([[10, 0]] * 4, n_splits=2)
    assert r["pbo"] == 0.0 and r["n_combinations"] == 2


def test_pbo_reversed_config_is_one():
    r = pbo([[5, 1], [5, 1], [1, 5], [1, 5]], n_splits=2)
    assert r["pbo"] == 1.0 and r["n_combinations"] == 2


def _bounds_matrix():
    # deterministic, finite, 16 rows x 3 configs, varied
    return [[(i * 7 + j * 13) % 11 - 5 for j in range(3)] for i in range(16)]


def test_pbo_bounds_and_n_combinations_default():
    r = pbo(_bounds_matrix())
    assert 0.0 <= r["pbo"] <= 1.0
    assert r["n_combinations"] == math.comb(16, 8)


@pytest.mark.parametrize("s,expected", [(2, 2), (4, 6), (16, math.comb(16, 8))])
def test_pbo_n_combinations(s, expected):
    rows = max(16, s)
    m = [[(i * 3 + j) % 7 for j in range(3)] for i in range(rows)]
    assert pbo(m, n_splits=s)["n_combinations"] == expected


def test_pbo_custom_metric_is_used():
    r = pbo(_bounds_matrix(), metric=statistics.median)
    assert 0.0 <= r["pbo"] <= 1.0 and r["n_combinations"] == math.comb(16, 8)


@pytest.mark.parametrize(
    "matrix,kwargs",
    [
        ([[10, 0]] * 4, {"n_splits": 3}),  # odd n_splits
        ([[10, 0]] * 4, {"n_splits": 1}),  # n_splits < 2
        ([[10, 0]] * 2, {"n_splits": 4}),  # T < n_splits
        ([[1], [2], [3], [4]], {"n_splits": 2}),  # N < 2 (single config)
        ([[1, 2], [3]], {"n_splits": 2}),  # non-rectangular
        ([[1, 2], [float("nan"), 3], [1, 2], [3, 4]], {"n_splits": 2}),  # non-finite cell
        ([[10, 0]] * 4, {"n_splits": 2.0}),  # even-float n_splits
    ],
)
def test_pbo_guards(matrix, kwargs):
    with pytest.raises(ValidationError):
        pbo(matrix, **kwargs)


def test_pbo_metric_returning_nan_raises():
    with pytest.raises(ValidationError):
        pbo([[10, 0]] * 4, n_splits=2, metric=lambda xs: float("nan"))


def test_pbo_metric_that_raises_is_validation_error():
    with pytest.raises(ValidationError):
        pbo([[10, 0]] * 4, n_splits=2, metric=lambda xs: xs[99])


def test_pbo_first_argmax_tie_breaking():
    # IS tie between configs 0 and 1; first-argmax (config 0, OOS-worst) must win -> pbo 0.5 (last-argmax would give 0.0)
    assert pbo([[2, 2], [2, 2], [0, 3], [0, 3]], n_splits=2)["pbo"] == 0.5


def test_pbo_all_tied_is_not_overfit():
    # w == 0.5 exactly (logit 0) must count as NOT overfit (strict <) -> pbo 0.0 (a <= boundary would give 1.0)
    assert pbo([[5, 5, 5]] * 4, n_splits=2)["pbo"] == 0.0
