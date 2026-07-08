import math
from statistics import NormalDist

import pytest

from cli.validation import (
    ValidationError,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
)


def test_emp_single_trial_is_zero():
    assert expected_max_sharpe(1, 1.0) == 0.0


@pytest.mark.parametrize("n", [2, 10])
def test_emp_zero_variance_is_zero(n):
    assert expected_max_sharpe(n, 0.0) == 0.0


def test_emp_increases_with_trials():
    vals = [expected_max_sharpe(n, 1.0) for n in (2, 5, 10, 50)]
    assert vals == sorted(vals) and len(set(vals)) == 4


def test_emp_scales_with_sqrt_var():
    assert expected_max_sharpe(10, 4.0) == pytest.approx(2 * expected_max_sharpe(10, 1.0), rel=1e-12)


def test_emp_known_value():
    assert expected_max_sharpe(10, 1.0) == pytest.approx(1.574, abs=0.01)


@pytest.mark.parametrize(
    "n,v",
    [
        (0, 1.0),
        (2, -1.0),
        (2, float("inf")),
        (float("nan"), 1.0),
        (float("inf"), 1.0),
        (10**16, 1.0),
        (2, "x"),
    ],
)
def test_emp_guards(n, v):
    with pytest.raises(ValidationError):
        expected_max_sharpe(n, v)


def test_psr_at_benchmark_is_half():
    assert probabilistic_sharpe_ratio(0.5, 100, benchmark_sr=0.5) == pytest.approx(0.5)


def test_psr_increasing_in_sr():
    a = probabilistic_sharpe_ratio(0.0, 100)
    b = probabilistic_sharpe_ratio(0.1, 100)
    c = probabilistic_sharpe_ratio(0.5, 100)
    assert a == pytest.approx(0.5) and a < b < c


def test_psr_bounded_and_high_sr_near_one():
    p = probabilistic_sharpe_ratio(2.0, 1000)
    assert 0.0 <= p <= 1.0 and p > 0.999


def test_psr_matches_normaldist_cdf():
    sr, t = 0.3, 250
    denom = 1 - 0.0 * sr + (3.0 - 1) / 4 * sr**2
    z = (sr - 0.0) * math.sqrt(t - 1) / math.sqrt(denom)
    assert probabilistic_sharpe_ratio(sr, t) == pytest.approx(NormalDist().cdf(z), rel=1e-12)


@pytest.mark.parametrize(
    "args,kwargs",
    [
        ((0.5, 1), {}),  # n_obs < 2
        ((float("nan"), 100), {}),  # non-finite sr
        ((1.0, 100), {"skew": 5.0}),  # denom = 1 - 5 + 0.5 = -3.5 <= 0
        ((0.5, float("nan")), {}),  # non-finite n_obs
        ((0.5, float("inf")), {}),  # non-finite n_obs
        ((2.0, 100), {"kurtosis": 0.0}),  # denom = 1 - 0 + (0-1)/4*4 = 0 <= 0
        ((0.5, 100), {"skew": "x"}),  # non-numeric skew
        (("x", 100), {}),  # non-numeric sr
        ((0.5, 100), {"benchmark_sr": "x"}),  # non-numeric benchmark_sr
        ((0.5, 100), {"kurtosis": "x"}),  # non-numeric kurtosis
    ],
)
def test_psr_guards_never_nan(args, kwargs):
    with pytest.raises(ValidationError):
        probabilistic_sharpe_ratio(*args, **kwargs)


def test_dsr_equals_psr_with_emp_benchmark():
    sr, t, n, v = 1.5, 250, 50, 1.0
    expected = probabilistic_sharpe_ratio(sr, t, benchmark_sr=expected_max_sharpe(n, v))
    assert deflated_sharpe_ratio(sr, t, n, v) == pytest.approx(expected, rel=1e-12)


def test_dsr_deflation_reduces_significance():
    assert deflated_sharpe_ratio(2.0, 250, 100, 1.0) < probabilistic_sharpe_ratio(2.0, 250)


def test_dsr_finite_in_unit_interval():
    d = deflated_sharpe_ratio(1.8, 500, 200, 1.0, skew=-0.5, kurtosis=6.0)
    assert math.isfinite(d) and 0.0 <= d <= 1.0


@pytest.mark.parametrize(
    "args",
    [
        (float("nan"), 250, 100, 1.0),
        (1.5, 250, 100, float("nan")),
        (1.5, float("nan"), 100, 1.0),
        (1.5, 250, float("nan"), 1.0),
        (1.5, 250, float("inf"), 1.0),
    ],
)
def test_dsr_nan_refusal(args):
    with pytest.raises(ValidationError):
        deflated_sharpe_ratio(*args)


def test_dsr_passes_through_skew_kurtosis():
    sr, t, n, v, sk, ku = 1.5, 250, 50, 1.0, -0.5, 6.0
    expected = probabilistic_sharpe_ratio(sr, t, benchmark_sr=expected_max_sharpe(n, v), skew=sk, kurtosis=ku)
    assert deflated_sharpe_ratio(sr, t, n, v, skew=sk, kurtosis=ku) == pytest.approx(expected, rel=1e-12)
