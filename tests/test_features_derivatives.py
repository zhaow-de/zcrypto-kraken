import math
from datetime import datetime, timezone

import pytest

from cli.features.derivatives import (
    align_asof,
    coverage_by_year,
    funding_accrued_carry,
    funding_sign_persistence,
    funding_zscore,
    oi_levels_from_raw,
    oi_log_delta,
    oi_momentum,
    oi_zscore,
    ratio_features,
)
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
    plausible and silently different -- the OI and ratio features feed nulls through this exact path
    (`oi_levels_from_raw`'s zero-to-None map, and the ratio columns' own nulls), so a later "fix" to
    the other reading would move every one of them."""
    src_ts = [_t(0), _t(4)]
    src_v = [1.0, None]
    grid = [_t(0), _t(2), _t(4), _t(6)]
    assert align_asof(src_ts, src_v, grid) == [1.0, 1.0, None, None]


def test_align_asof_refuses_a_length_mismatch_and_either_unsorted_input_but_permits_a_tie():
    """The three preconditions the as-of walk rests on, and the one it deliberately does not
    impose. The source-order guard is the load-bearing refusal: `i` only ever advances, so an
    unsorted source is not a crash but a silently wrong carry from the first out-of-order row
    onward. Equal adjacent stamps are permitted on purpose (`b < a`, not `b <= a`) -- a venue may
    print twice at one stamp -- and the walk consumes both, so the later row is the one carried."""
    with pytest.raises(FeatureError):
        align_asof([_t(0), _t(4)], [1.0], [_t(0)])
    with pytest.raises(FeatureError):
        align_asof([_t(4), _t(0)], [1.0, 2.0], [_t(0)])
    with pytest.raises(FeatureError):
        align_asof([_t(0), _t(4)], [1.0, 2.0], [_t(4), _t(0)])
    assert align_asof([_t(0), _t(0)], [1.0, 2.0], [_t(0)]) == [2.0]


def test_a_truncated_prefix_reproduces_the_full_run_bit_for_bit():
    """The look-ahead guard (spec D2/D10), in the form that actually bites.

    Appending FUTURE source rows beyond the grid's last stamp proves nothing: rows past the grid's
    end cannot move any value under a backward-fill defect (`if t >= g: return x`, which reads the
    NEXT source row) either. This form truncates instead: recompute over `grid[:k]` using only
    source rows stamped at or before `grid[k-1]`, and demand the prefix match the full run's. The
    defect first mismatches at k=2 (`[1.0, None]` vs `[1.0, 2.0]`)."""
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
    sample stdev. The score is asserted as a computed value, never as a threshold: `> 3.0` pins no
    window at all, since population stdev gives exactly 3.0 and the exclusive window is undefined.

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
    """The causality guard for the three funding features (spec D2/D10), in the only form that bites.

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


def test_oi_log_delta_is_the_log_ratio_starts_none_and_propagates_null():
    assert oi_log_delta([100.0, 110.0, None, 120.0]) == [None, pytest.approx(math.log(110.0 / 100.0)), None, None]


def test_oi_zscore_recovers_a_planted_spike():
    """Same pinned definition, same arithmetic as the funding case -- and the same full-list
    assertion, which pins the nine-`None` warm-up head a `0.0`-filling implementation would
    replace with `exactly average`."""
    assert oi_zscore([100.0] * 10 + [180.0], window=10) == [None] * 9 + [0.0, pytest.approx(2.8460498941515410)]


def test_oi_zscore_propagates_null():
    assert oi_zscore([100.0] * 10 + [None], window=10) == [None] * 9 + [0.0, None]


def test_oi_momentum_pins_its_head_its_base_index_and_its_nulls():
    """Keep every level distinct: `lookback` 1, 2 and 3 then give three different answers, so an
    off-by-one base index cannot hide. A fixture whose head is constant makes them agree."""
    assert oi_momentum([100.0, 110.0, 121.0, 125.0], lookback=2) == [
        None,
        None,
        pytest.approx(0.21),
        pytest.approx(0.13636363636363646),
    ]
    assert oi_momentum([100.0, 110.0, None, 125.0, 140.0], lookback=2) == [
        None,
        None,
        None,
        pytest.approx(0.13636363636363646),
        None,
    ]


def test_oi_levels_from_raw_maps_the_venue_hole_to_null():
    """Spec 00110 D5: a `0.0` open interest is a hole the venue wrote as a zero, not a market with
    no open interest. Without this mapping `_validate_levels` raises on the canonical substrate at
    first real use, and the cheapest-looking repair there is the imputation D5 forbids."""
    assert oi_levels_from_raw([100.0, 0.0, 110.0, None]) == [100.0, None, 110.0, None]


def test_every_oi_feature_refuses_a_raw_zero_instead_of_scoring_it():
    """`oi_levels_from_raw` is a step a caller has to remember, and these three assertions are what
    make forgetting it loud rather than silent. `oi_zscore` is why all three are asserted and not
    just the one where a bad level is obvious: a fabricated zero is a perfectly good number to take
    a mean and a sample stdev over, so an unguarded z-score returns a finite, plausible, large
    negative reading -- exactly what a de-risking trigger acts on. And `FeatureError` specifically:
    a bare `ValueError` out of `log(0)` is the contract failing too, not the contract holding."""
    for f, kw in ((oi_log_delta, {}), (oi_zscore, {"window": 3}), (oi_momentum, {"lookback": 2})):
        with pytest.raises(FeatureError):
            f([100.0, 0.0, 110.0, 120.0], **kw)


def test_every_windowed_oi_feature_rejects_a_short_window():
    """`_validate_window`, the second half of the house form, must be CALLED by both windowed OI
    forms too -- see the funding twin for what an unguarded `window=0` fabricates. The levels below
    are healthy positives, so only the window can be what fires. The parameter is spelled
    `lookback` on `oi_momentum`, and each function names its own in the error."""
    for f, param in ((oi_zscore, "window"), (oi_momentum, "lookback")):
        for bad in (0, 1, 2.0, True):
            with pytest.raises(FeatureError):
                f([100.0, 104.0, 99.0, 130.0], **{param: bad})


def test_every_oi_feature_reproduces_itself_on_a_truncated_prefix():
    """The causality guard for the three OI features (spec D2/D10). See
    `test_every_funding_feature_reproduces_itself_on_a_truncated_prefix` for why `[-1]` cannot carry
    it. The fixture rises and falls so no two candidate window offsets coincide."""
    levels = [100.0, 104.0, 99.0, 130.0, 128.0, 90.0, 155.0, 151.0]
    cases = (
        (oi_log_delta, {}),
        (oi_zscore, {"window": 3}),
        (oi_momentum, {"lookback": 2}),
    )
    for f, kw in cases:
        full = f(levels, **kw)
        for n in range(2, len(levels) + 1):
            assert f(levels[:n], **kw) == full[:n], f"{f.__name__} disagrees at n={n}"


_RATIOS = (
    "count_toptrader_long_short_ratio",
    "sum_toptrader_long_short_ratio",
    "count_long_short_ratio",
    "sum_taker_long_short_vol_ratio",
)


def test_ratio_features_prefix_every_column_with_its_venue():
    out = ratio_features({name: [1.0, 2.0] for name in _RATIOS})
    assert set(out) == {f"binperp_{name}" for name in _RATIOS}


def test_ratio_features_carry_nulls_and_real_zeros_through_untouched():
    """Spec 00110 D5: no imputation. A null in, a null out -- never 0.0, never a trailing mean.
    And a `0.0` in, a `0.0` out: D5 rules a ratio zero a real reading (an all-sell bar), unlike a
    zero in `sum_open_interest`, which is a venue hole.

    Every column gets a DIFFERENT head, and each is asserted against its own input rather than a
    shared literal. The four columns are not interchangeable, so an implementation that broadcast
    one input list across all four output keys would hand a trial the wrong column's values. Give
    them all the same list and that defect cannot move this fixture.

    Mis-keying has a second shape the distinct heads alone cannot catch: pairing output keys with
    input values POSITIONALLY -- zipping the module's canonical column order against
    `ratios.values()` -- agrees with the correct implementation for as long as the input arrives in
    `_RATIOS` order. So the call below hands the dict REVERSED; do not "simplify" it back to
    `ratio_features(inputs)`, which re-blinds this fixture to that half."""
    inputs = {name: [float(i + 1), None, 0.0, 3.0] for i, name in enumerate(_RATIOS)}
    out = ratio_features(dict(reversed(list(inputs.items()))))
    for name, values in inputs.items():
        assert out[f"binperp_{name}"] == values


def test_ratio_features_rejects_an_unknown_column():
    import pytest

    from cli.features.errors import FeatureError

    with pytest.raises(FeatureError):
        ratio_features({"not_a_ratio": [1.0, 2.0]})


def test_ratio_features_rejects_a_dropped_column():
    """The other half of the guard. Without it a caller that lost a column gets a silently smaller
    frame, and `coverage_by_year` reports nothing about a column that is not there."""
    import pytest

    from cli.features.errors import FeatureError

    with pytest.raises(FeatureError):
        ratio_features({name: [1.0, 2.0] for name in _RATIOS[:3]})


def test_coverage_by_year_separates_a_late_start_from_an_interior_outage():
    """The shape that motivated D6: an overall null rate reads as a nuisance while one year is
    almost entirely missing. Coverage must show the year, not the aggregate -- and within a year,
    the two timestamps, because 2021 and 2022 below carry the SAME `(non_null, total)` of `(2, 10)`
    and opposite meanings. 2021 spans January to October with an eight-month hole between them;
    2022 does not start until September. Only `first_non_null` / `last_non_null` separate them, so
    the 2021 and 2022 assertions below agree in their first two fields and differ only in the last
    two; a 2-tuple return fails all three on arity."""
    UTC = timezone.utc
    ts = [datetime(y, m, 1, tzinfo=UTC) for y in (2021, 2022, 2023) for m in range(1, 11)]
    vals = [1.0] + [None] * 8 + [1.0] + [None] * 8 + [1.0, 1.0] + [1.0] * 10
    cov = coverage_by_year(ts, vals)
    assert cov[2021] == (2, 10, datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 10, 1, tzinfo=UTC))
    assert cov[2022] == (2, 10, datetime(2022, 9, 1, tzinfo=UTC), datetime(2022, 10, 1, tzinfo=UTC))
    assert cov[2023] == (10, 10, datetime(2023, 1, 1, tzinfo=UTC), datetime(2023, 10, 1, tzinfo=UTC))
    assert 1 - cov[2022].non_null / cov[2022].total == 0.8


def test_coverage_by_year_rejects_a_length_mismatch_and_reports_an_empty_year():
    """The two contracts the summary's arithmetic rests on. The derived null fraction is only as
    good as `total`, and a `zip`-based implementation truncates to the shorter input and under-counts
    it with nothing raising. And an all-null year has no timestamps to report -- `None` twice, not a
    `min()` over an empty sequence."""
    import pytest

    from cli.features.errors import FeatureError

    UTC = timezone.utc
    ts = [datetime(2021, m, 1, tzinfo=UTC) for m in range(1, 4)]
    with pytest.raises(FeatureError):
        coverage_by_year(ts, [1.0, 2.0])
    assert coverage_by_year(ts, [None, None, None])[2021] == (0, 3, None, None)


def test_coverage_by_year_reports_the_span_not_the_positional_ends():
    """`coverage_by_year`'s EARLIEST/LATEST contract, on the only input shape that can refute the
    positional reading: the two non-null rows arrive Oct-then-Jan, so a `seen[0]`/`seen[-1]`
    implementation reports the span inverted -- `(Oct, Jan)` -- while `min`/`max` report the
    `(Jan, Oct)` the column actually covers. An in-order fixture cannot tell the two apart -- the
    out-of-order `ts` is the whole point of this case. `coverage_by_year` imposes no ordering
    precondition (unlike `align_asof`), so the span is what it owes on any input."""
    UTC = timezone.utc
    ts = [datetime(2021, 10, 1, tzinfo=UTC), datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 5, 1, tzinfo=UTC)]
    cov = coverage_by_year(ts, [1.0, 1.0, None])
    assert cov[2021] == (2, 3, datetime(2021, 1, 1, tzinfo=UTC), datetime(2021, 10, 1, tzinfo=UTC))
