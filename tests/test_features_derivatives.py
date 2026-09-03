from datetime import datetime, timezone

import pytest

from cli.features.derivatives import align_asof

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
