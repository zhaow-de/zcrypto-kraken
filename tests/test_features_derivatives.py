from datetime import datetime, timezone

import pytest

from cli.features.derivatives import align_asof, funding_accrued_carry, funding_sign_persistence, funding_zscore
from cli.features.errors import FeatureError

UTC = timezone.utc


def _t(h):
    return datetime(2022, 1, 1, h, tzinfo=UTC)


def test_align_asof_forward_fills_and_never_interpolates():
    src_ts = [_t(0), _t(8)]
    src_v = [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8), _t(12)]
    assert align_asof(src_ts, src_v, grid) == [1.0, 1.0, 2.0, 2.0]


def test_align_asof_is_none_before_the_first_source_row():
    assert align_asof([_t(8)], [2.0], [_t(0), _t(8)]) == [None, 2.0]


def test_a_null_source_row_erases_the_carry_rather_than_being_skipped():
    """Pins spec D5's null semantics: a null source value REPLACES the carry, it is not skipped.
    The competing reading (forward-fill the last observed value, skipping nulls) is equally
    plausible and silently different -- Tasks 4 and 5 feed nulls through this exact path
    (`oi_levels_from_raw`'s zero-to-None map, and the ratio columns' own nulls), so this is
    load-bearing: a later "fix" to the other reading would move every OI and ratio feature."""
    src_ts = [_t(0), _t(4)]
    src_v = [1.0, None]
    grid = [_t(0), _t(2), _t(4), _t(6)]
    assert align_asof(src_ts, src_v, grid) == [1.0, 1.0, None, None]


def test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit():
    """The look-ahead guard (spec D2/D10), in the form that actually bites.

    An earlier draft appended FUTURE source rows beyond the grid's last stamp and asserted the
    result was unchanged. The contract pin showed that test passes on a deliberate backward-fill
    defect (`if t >= g: return x`, which reads the NEXT source row) as readily as on the correct
    implementation, because rows past the grid's end cannot move any value under either semantics.

    This form truncates instead: recompute over `grid[:k]` using only source rows stamped at or
    before `grid[k-1]`, and demand the prefix match the full run's. The defect first mismatches at **k=2** (`[1.0, None]` vs `[1.0, 2.0]`); the correct implementation passes at
    every k."""
    src_ts, src_v = [_t(0), _t(8)], [1.0, 2.0]
    grid = [_t(0), _t(4), _t(8)]
    full = align_asof(src_ts, src_v, grid)
    for k in range(1, len(grid) + 1):
        cutoff = grid[k - 1]
        visible = [(t, v) for t, v in zip(src_ts, src_v) if t <= cutoff]
        prefix = align_asof([t for t, _ in visible], [v for _, v in visible], grid[:k])
        assert prefix == full[:k], f"prefix at k={k} disagrees with the full run"


def test_funding_zscore_recovers_a_planted_value():
    """Planted signal (spec D10) under D7's pinned window: inclusive trailing window ending at k,
    sample stdev. Nine identical prints then one outlier scores exactly 2.8460498941515410 --
    verified by computation, not asserted as a threshold. An earlier draft asserted `> 3.0`, which
    no window definition can produce: population stdev gives exactly 3.0, exclusive is undefined.

    The assertion is the FULL list, not `z[-1]`: it pins the length, the nine-`None` warm-up head
    that separates "undefined" from "exactly average", and the value -- and a `[-1]`-only form
    passes under a window that peeks one bar ahead, because at the last index it clamps."""
    rates = [0.0001] * 10 + [0.0009]
    assert funding_zscore(rates, window=10) == [None] * 9 + [0.0, pytest.approx(2.8460498941515410)]


def test_funding_zscore_of_a_constant_series_is_zero_not_spurious():
    assert funding_zscore([0.0001] * 12, window=10) == [None] * 9 + [0.0, 0.0, 0.0]


def test_funding_zscore_propagates_null():
    assert funding_zscore([0.0001] * 10 + [None], window=10) == [None] * 9 + [0.0, None]


def test_sign_persistence_counts_consecutive_same_sign_prints():
    """A zero print is its own sign (spec D7), and a null breaks the run without joining one."""
    assert funding_sign_persistence([0.1, 0.2, 0.0, -0.1, -0.2]) == [1, 2, 1, 1, 2]
    assert funding_sign_persistence([0.1, 0.2, None, -0.1, -0.2]) == [1, 2, None, 1, 2]


def test_accrued_carry_sums_the_window():
    assert funding_accrued_carry([1.0, 2.0, 3.0, 4.0], window=2) == [None, 3.0, 5.0, 7.0]
    assert funding_accrued_carry([1.0, 2.0, None, 4.0, 5.0], window=2) == [None, 3.0, None, None, 9.0]


def test_every_funding_feature_refuses_a_nonfinite_rate():
    """The other half of `_validate_rates` being a guard rather than an import: it must be CALLED,
    by all three. A NaN would otherwise propagate through every arithmetic path silently, and a NaN
    z-score compares unequal to everything -- including itself -- so no downstream assertion catches
    it either. The fixture is otherwise a healthy signed series, so only the NaN can be what fires."""
    for f, kw in ((funding_zscore, {"window": 3}), (funding_sign_persistence, {}), (funding_accrued_carry, {"window": 3})):
        with pytest.raises(FeatureError):
            f([0.0003, float("nan"), 0.0004, 0.0009], **kw)


def test_every_windowed_funding_feature_rejects_a_short_window():
    """The window half of the same guard: `_validate_window` must be CALLED, by both windowed forms.
    The rates below are healthy, so only the window can be what fires. `window=0` is the dangerous
    one -- the warm-up branch never runs and the trailing slice is empty, so an unguarded
    `funding_accrued_carry` returns `sum([]) == 0.0` at every index: a fabricated flat carry, which
    is exactly the reading spec D7 says a de-risking trigger acts on as safe. `window=1` is the
    loud one -- unguarded it raises `statistics.StatisticsError`, which is not `FeatureError`."""
    for f in (funding_zscore, funding_accrued_carry):
        for bad in (0, 1, 2.0, True):
            with pytest.raises(FeatureError):
                f([0.0003, -0.0001, 0.0004, 0.0009], window=bad)


def test_every_funding_feature_reproduces_itself_on_a_truncated_prefix():
    """The causality guard for this task's three functions (spec D2/D10), in the only form that
    bites. `test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit` has the same property for
    `align_asof`; it covers nothing here.

    Every assertion above is a fixed-input equality, and a window that reads one bar into the
    future agrees with the causal form at the last index -- so recompute over each prefix and
    demand the answers match. The fixture is deliberately non-degenerate: distinct magnitudes,
    both signs, and a zero, so no two candidate window offsets coincide."""
    rates = [0.0003, -0.0001, 0.0004, 0.0, 0.0009, -0.0002, 0.0011, 0.0005]
    cases = (
        (funding_zscore, {"window": 3}),
        (funding_sign_persistence, {}),
        (funding_accrued_carry, {"window": 3}),
    )
    for f, kw in cases:
        full = f(rates, **kw)
        for n in range(2, len(rates) + 1):
            assert f(rates[:n], **kw) == full[:n], f"{f.__name__} disagrees at n={n}"
