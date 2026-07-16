import datetime as dt
import io
import json

import polars as pl
import pytest

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.trades.errors import TradeBackfillError
from cli.trades.rest import fetch_trades


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _page(rows, last):
    return _Resp(json.dumps({"error": [], "result": {"XXBTZEUR": rows, "last": str(last)}}).encode())


ROW = ["56062.10000", "0.00008918", 1783735200.0737085, "b", "m", "", 108052012]


def test_normalizes_a_row_into_trade_schema():
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        return _page([ROW], 1783735200073708500)

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener)
    assert list(df.schema.items()) == list(pl.Schema(TRADE_SCHEMA).items())
    r = df.row(0, named=True)
    assert r["symbol"] == "BTC/EUR"  # canonical, not XXBTZEUR
    assert r["side"] == "buy"  # b -> buy
    assert r["ord_type"] == "market"  # m -> market
    assert r["price"] == 56062.1 and r["qty"] == 0.00008918
    assert r["trade_id"] == 108052012
    assert r["ts"] == dt.datetime(2026, 7, 11, 2, 0, 0, 73708, tzinfo=dt.UTC)
    assert "pair=XBTEUR" in calls[0] and "since=1783735200" in calls[0]  # SECONDS on the way in


def test_sell_and_limit_map_too():
    df = fetch_trades(
        "BTC/EUR",
        dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
        opener=lambda url, timeout=None: _page([["1", "2", 1783735200.0, "s", "l", "", 7]], 1783735200000000000),
    )
    assert df.row(0, named=True)["side"] == "sell"
    assert df.row(0, named=True)["ord_type"] == "limit"


def test_paginates_using_the_nanosecond_cursor_as_seconds():
    """The `last` cursor is NANOSECONDS; `since` takes SECONDS. Feeding ns back raw would jump
    ~31 years ahead and silently return nothing."""
    urls = []
    pages = [
        _page([[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)], 1783735201000000000),
        _page([["1", "1", 1783735300.0, "b", "m", "", 2000]], 1783735300000000000),
    ]

    def opener(url, timeout=None):
        urls.append(url)
        return pages[len(urls) - 1]

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener, sleep=lambda _: None)
    assert len(urls) == 2
    assert "since=1783735201" in urls[1]  # ns cursor converted to seconds, NOT passed through
    assert df.height == 1001
    assert df["trade_id"].is_sorted()


def test_stops_at_until_without_fetching_further():
    urls = []

    def opener(url, timeout=None):
        urls.append(url)
        return _page([[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)], 1783739000000000000)

    fetch_trades(
        "BTC/EUR",
        dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
        until=dt.datetime(2026, 7, 11, 2, 0, 30, tzinfo=dt.UTC),
        opener=opener,
        sleep=lambda _: None,
    )
    assert len(urls) == 1  # page already covers `until`; no second call


def test_kraken_error_array_raises():
    body = _Resp(json.dumps({"error": ["EGeneral:Too many requests"], "result": {}}).encode())
    with pytest.raises(TradeBackfillError, match="Too many requests"):
        fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=lambda u, timeout=None: body)


def test_unknown_pair_raises_before_any_request():
    with pytest.raises(TradeBackfillError, match="no Kraken altname"):
        fetch_trades("NOPE/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=lambda u, timeout=None: _page([], 0))


def test_ts_truncates_and_does_not_round_pinned_to_measured_venue_values():
    """Regression pin for spec 00053 D6a, using REAL floats Kraken returned for trades that also
    exist in the archive. Kraken's REST float runs systematically ~+0.7..+1.1us above the WS ISO
    microsecond, so truncation recovers the WS value 2/4 while rounding recovers 0/4. A future
    "fix" to round() is strictly worse — this test fails if anyone tries it.
    """
    cases = [
        # (raw REST time, truncated us == what we must emit, rounded us == what we must NOT emit)
        (1783738586.1807897, 180789, 180790),
        (1783738621.9864349, 986434, 986435),
    ]
    for raw, want_trunc, must_not in cases:
        df = fetch_trades(
            "BTC/EUR",
            dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
            opener=lambda url, timeout=None, _r=raw: _page([["1", "2", _r, "b", "m", "", 7]], 0),
        )
        got = df.row(0, named=True)["ts"].microsecond
        assert got == want_trunc, f"{raw}: expected truncated {want_trunc}, got {got}"
        assert got != must_not, f"{raw}: rounded to {must_not} — see D6a, truncation is measured better"
