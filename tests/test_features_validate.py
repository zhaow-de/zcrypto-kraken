import pytest

from cli.features._validate import _validate_levels, _validate_rates
from cli.features.errors import FeatureError


def test_validate_rates_accepts_negative_and_none():
    _validate_rates("funding", [-0.0003, 0.0, None, 0.0007])


def test_validate_rates_rejects_nonfinite_and_bool():
    for bad in ([1.0, float("nan")], [1.0, float("inf")], [1.0, True]):
        with pytest.raises(FeatureError):
            _validate_rates("funding", bad)


def test_both_new_validators_reject_a_non_list_and_a_too_short_input():
    """The two halves of the same first line in each validator, on inputs that separate them. A
    tuple has a `len` and iterates, so only the `isinstance(values, list)` term refuses it; a
    single-value list satisfies that term and only `len(values) < 2` refuses it. Both matter to the
    features these gate: every window here needs two observations before it means anything -- a
    `statistics.stdev` over one value raises, and `oi_log_delta` over one value has no pair."""
    for bad in ((1.0, 2.0), [1.0]):
        for validate in (_validate_rates, _validate_levels):
            with pytest.raises(FeatureError):
                validate("series", bad)


def test_validate_levels_accepts_positive_and_none_but_not_zero_or_negative():
    """`0.0` is rejected ON PURPOSE. Spec 00110 D5 rules a zero open interest a venue hole, which
    `oi_levels_from_raw` maps to `None` before this runs, so a `0.0` arriving here is a caller that
    skipped the mapping. Do not relax this to `>= 0`: `oi_log_delta` would then take `log(0)` and
    `oi_momentum` would divide by zero."""
    _validate_levels("oi", [100.0, None, 110.0])
    for bad in ([100.0, 0.0], [100.0, -1.0], [100.0, float("nan")]):
        with pytest.raises(FeatureError):
            _validate_levels("oi", bad)


def test_validate_levels_rejects_a_bool_level():
    """`True` is an `int`, is finite and is `> 0`, so it satisfies every other term of the loop:
    the explicit `isinstance(v, bool)` term is the only one that refuses it. A bool arriving as a
    LEVEL is a caller that passed a flag where a series belongs, and `oi_log_delta` would score
    `log(1.0 / prev)` over it -- a finite, plausible reading of a level the venue never published,
    with nothing raising. The bool in `test_validate_rates_rejects_nonfinite_and_bool` exercises
    the sibling term in `_validate_rates`, not this one."""
    with pytest.raises(FeatureError):
        _validate_levels("oi", [100.0, True])
