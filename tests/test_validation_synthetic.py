import math
import statistics

import pytest

from cli.validation import ValidationError, linear_signal, sign_strategy_returns


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
