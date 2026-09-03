import pytest

from cli.features._validate import _validate_levels, _validate_rates
from cli.features.errors import FeatureError


def test_validate_rates_accepts_negative_and_none():
    _validate_rates("funding", [-0.0003, 0.0, None, 0.0007])


def test_validate_rates_rejects_nonfinite_and_bool():
    for bad in ([1.0, float("nan")], [1.0, float("inf")], [1.0, True]):
        with pytest.raises(FeatureError):
            _validate_rates("funding", bad)


def test_validate_levels_accepts_positive_and_none_but_not_zero_or_negative():
    """`0.0` is rejected ON PURPOSE. Spec 00110 D5 rules a zero open interest a venue hole, which
    `oi_levels_from_raw` maps to `None` before this runs, so a `0.0` arriving here is a caller that
    skipped the mapping. Do not relax this to `>= 0`: `oi_log_delta` would then take `log(0)` and
    `oi_momentum` would divide by zero."""
    _validate_levels("oi", [100.0, None, 110.0])
    for bad in ([100.0, 0.0], [100.0, -1.0], [100.0, float("nan")]):
        with pytest.raises(FeatureError):
            _validate_levels("oi", bad)
