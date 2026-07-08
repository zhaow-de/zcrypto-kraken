from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
import pytest

from cli.tick.errors import TickError
from cli.tick.reconcile import KRAKEN_TICKER_MAP, csv_pair_to_canonical, reconcile

HOUR = 3600
BASE_TS = 1700000000


def _bars(n: int, *, open_=100.0, high=101.0, low=99.0, close=100.5) -> pl.DataFrame:
    ts = [datetime.fromtimestamp(BASE_TS + i * HOUR, tz=UTC) for i in range(n)]
    return pl.DataFrame(
        {
            "ts": ts,
            "open": [open_] * n,
            "high": [high] * n,
            "low": [low] * n,
            "close": [close] * n,
        },
        schema={
            "ts": pl.Datetime("us", "UTC"),
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
        },
    )


def test_reconcile_identical_bars_full_match():
    bars = _bars(5)

    report = reconcile(bars, bars)

    assert report["n_intervals"] == 5
    assert report["n_matched"] == 5
    assert report["pct_within_tol"] == 100.0
    assert report["pct_within_tol_loose"] == 100.0
    assert report["worst_mismatches"] == []


def test_reconcile_planted_ohlc_mismatch_is_caught_and_surfaced():
    tick_bars = _bars(5)
    ohlcvt_rows = _bars(5).to_dicts()
    ohlcvt_rows[2]["high"] = 999.0  # planted diff, well beyond both tol bands
    ohlcvt_bars = pl.DataFrame(ohlcvt_rows, schema=tick_bars.schema)

    report = reconcile(tick_bars, ohlcvt_bars)

    assert report["n_intervals"] == 5
    assert report["n_matched"] == 4
    assert report["pct_within_tol"] == pytest.approx(80.0)
    assert len(report["worst_mismatches"]) == 1
    mismatch = report["worst_mismatches"][0]
    assert mismatch["field"] == "high"
    assert mismatch["tick"] == pytest.approx(101.0)
    assert mismatch["ohlcvt"] == pytest.approx(999.0)
    assert mismatch["rel_diff"] == pytest.approx(abs(101.0 - 999.0) / 999.0)


def test_reconcile_loose_band_absorbs_a_small_diff_that_misses_the_strict_tol():
    tick_bars = _bars(3, close=100.0)
    ohlcvt_rows = _bars(3, close=100.0).to_dicts()
    ohlcvt_rows[0]["close"] = 100.005  # ~5e-5 relative diff: misses tol=1e-6, within loose 1e-3
    ohlcvt_bars = pl.DataFrame(ohlcvt_rows, schema=tick_bars.schema)

    report = reconcile(tick_bars, ohlcvt_bars, tol=1e-6)

    assert report["n_matched"] == 2
    assert report["n_matched_loose"] == 3
    assert report["pct_within_tol_loose"] == 100.0


def test_reconcile_zero_overlap_reports_vacuous_full_match():
    tick_bars = _bars(3)
    disjoint_ts = [datetime.fromtimestamp(BASE_TS + (100 + i) * HOUR, tz=UTC) for i in range(3)]
    ohlcvt_bars = _bars(3).with_columns(pl.Series("ts", disjoint_ts, dtype=pl.Datetime("us", "UTC")))

    report = reconcile(tick_bars, ohlcvt_bars)

    assert report["n_intervals"] == 0
    assert report["pct_within_tol"] == 100.0
    assert report["worst_mismatches"] == []


def test_csv_pair_to_canonical_ticker_map():
    assert csv_pair_to_canonical("XBTEUR") == ("BTC", "EUR")
    assert csv_pair_to_canonical("XDGEUR") == ("DOGE", "EUR")
    assert csv_pair_to_canonical("ETHEUR") == ("ETH", "EUR")
    assert csv_pair_to_canonical("SOLUSD") == ("SOL", "USD")


def test_csv_pair_to_canonical_uses_kraken_ticker_map_constant():
    assert KRAKEN_TICKER_MAP == {"XBT": "BTC", "XDG": "DOGE"}


def test_csv_pair_to_canonical_raises_on_unrecognized_quote():
    with pytest.raises(TickError):
        csv_pair_to_canonical("XBTGBP")
