import datetime as dt
import logging

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.errors import TradeBackfillError
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
    naive `b != a+1` and yields a negative-width 'gap'. `unique()` is what actually prevents this
    here (post-`unique()`, `b > a` always holds, so `>` and `!=` are equivalent) — not the choice
    of comparator."""
    d = detect(_f([10, 11, 11, 12]))
    assert d.duplicate_ids == [11]
    assert d.gaps == []
    assert (d.rows, d.unique, d.missing) == (4, 3, 0)


def test_empty_frame_is_inert():
    d = detect(pl.DataFrame([], schema=TRADE_SCHEMA))
    assert d.gaps == [] and d.duplicate_ids == [] and (d.rows, d.unique, d.span, d.missing) == (0, 0, 0, 0)


def test_unsorted_input_is_handled():
    d = detect(_f([12, 10, 11]))
    assert d.gaps == [] and d.missing == 0


def test_non_monotone_ts_across_a_gap_is_normalized_and_warned(caplog):
    """The T0026 reconnect-overwrite signature: `ts` runs DESCENDING while `trade_id` still
    increases. Un-normalized, this gap's ts_lo/ts_hi would come out INVERTED (ts_lo > ts_hi),
    sending REST a `since` after the `until` -- silently yielding nothing. This must genuinely
    fail if the normalization is removed: reverting to plain `tss[i]`/`tss[i + 1]` makes
    `g.ts_lo <= g.ts_hi` false for this fixture."""
    df = pl.DataFrame(
        [
            {
                "ts": T0 + dt.timedelta(seconds=3 - i),
                "symbol": "BTC/EUR",
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": t,
            }
            for i, t in enumerate([10, 11, 15, 16])
        ],
        schema=TRADE_SCHEMA,
    )
    with caplog.at_level(logging.WARNING, logger="zcrypto.trades.gaps"):
        d = detect(df)
    assert len(d.gaps) == 1
    g = d.gaps[0]
    assert g.ts_lo <= g.ts_hi
    assert g.ts_lo == T0 + dt.timedelta(seconds=1) and g.ts_hi == T0 + dt.timedelta(seconds=2)
    assert any("non-monotone ts" in r.getMessage() for r in caplog.records)


def test_null_trade_id_raises_typed_error():
    df = pl.DataFrame(
        [
            {
                "ts": T0,
                "symbol": "BTC/EUR",
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": None,
            },
            {
                "ts": T0 + dt.timedelta(seconds=1),
                "symbol": "BTC/EUR",
                "side": "buy",
                "price": 1.0,
                "qty": 1.0,
                "ord_type": "market",
                "trade_id": 11,
            },
        ],
        schema=TRADE_SCHEMA,
    )
    with pytest.raises(TradeBackfillError, match="null trade_id"):
        detect(df)
