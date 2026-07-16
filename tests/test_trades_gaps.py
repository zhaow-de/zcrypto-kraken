import datetime as dt

import polars as pl

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.gaps import detect

T0 = dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC)


def _f(ids):
    return pl.DataFrame(
        [
            {
                "ts": T0 + dt.timedelta(seconds=i),
                "symbol": "BTC/EUR",
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": t,
            }
            for i, t in enumerate(ids)
        ],
        schema=TRADE_SCHEMA,
    )


def test_contiguous_stream_has_no_gaps_and_no_duplicates():
    d = detect(_f([10, 11, 12, 13]))
    assert d.gaps == [] and d.duplicate_ids == []
    assert (d.rows, d.unique, d.span, d.missing) == (4, 4, 4, 0)


def test_single_gap_is_reported_with_its_bracketing_timestamps():
    d = detect(_f([10, 11, 15, 16]))
    assert len(d.gaps) == 1
    g = d.gaps[0]
    assert (g.after_id, g.before_id, g.missing) == (11, 15, 3)
    assert g.ts_lo == T0 + dt.timedelta(seconds=1) and g.ts_hi == T0 + dt.timedelta(seconds=2)
    assert d.missing == 3


def test_multiple_gaps():
    d = detect(_f([1, 2, 5, 6, 9]))
    assert [(g.after_id, g.before_id) for g in d.gaps] == [(2, 5), (6, 9)]
    assert d.missing == 4  # 3,4 + 7,8


def test_duplicates_are_reported_and_never_counted_as_gaps():
    """v1 of the exploratory probe conflated these: sorted duplicates give (x, x), which trips a
    naive `b != a+1` and yields a negative-width 'gap'."""
    d = detect(_f([10, 11, 11, 12]))
    assert d.duplicate_ids == [11]
    assert d.gaps == []
    assert (d.rows, d.unique, d.missing) == (4, 3, 0)


def test_gap_widths_always_sum_to_missing():
    d = detect(_f([1, 5, 6, 20]))
    assert sum(g.missing for g in d.gaps) == d.missing


def test_endpoints_are_never_gaps():
    """The first id is capture-start, the last is the live edge. Absence outside the span is not
    loss (spec 00053 D1)."""
    d = detect(_f([100, 101, 102]))
    assert d.gaps == [] and d.span == 3


def test_empty_frame_is_inert():
    d = detect(pl.DataFrame([], schema=TRADE_SCHEMA))
    assert d.gaps == [] and d.duplicate_ids == [] and (d.rows, d.unique, d.span, d.missing) == (0, 0, 0, 0)


def test_unsorted_input_is_handled():
    d = detect(_f([12, 10, 11]))
    assert d.gaps == [] and d.missing == 0
