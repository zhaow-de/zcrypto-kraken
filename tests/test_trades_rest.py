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


def _last_for(rows):
    """Kraken's `last` is the last row's OWN time, in nanoseconds — never an unrelated value."""
    return str(int(round(rows[-1][2] * 1_000_000_000)))


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


def test_paginates_feeding_the_raw_last_cursor_back():
    """Spec 00053 D5a: `since` accepts the raw ns `last` cursor as well as a seconds epoch, and the
    client feeds `last` back UNMODIFIED. `last` here is derived FROM the page's own last row, as
    Kraken returns it — a fixture handing back an unrelated `last` cannot catch a broken cursor."""
    urls = []
    page1_rows = [[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)]
    page1_last = _last_for(page1_rows)
    pages = [
        _page(page1_rows, page1_last),
        _page([["1", "1", 1783735300.0, "b", "m", "", 2000]], 1783735300000000000),
    ]

    def opener(url, timeout=None):
        urls.append(url)
        return pages[len(urls) - 1]

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener, sleep=lambda _: None)
    assert len(urls) == 2
    assert f"since={page1_last}" in urls[1]  # raw ns cursor passed through untouched
    assert df.height == 1001
    assert df["trade_id"].is_sorted()


def test_no_trade_id_progress_stops_pagination():
    """Defence in depth (spec 00053 D5a): the raw cursor is guaranteed to advance, but a page that
    contributes no NEW `trade_id` must still stop the loop rather than hammer the endpoint forever."""
    urls = []
    stuck_rows = [[str(i), "1", 1783735200.0 + i, "b", "m", "", 100 + i] for i in range(1000)]
    stuck_last = _last_for(stuck_rows)
    pages = [
        _page(stuck_rows, stuck_last),
        _page(stuck_rows, stuck_last),  # identical ids again: a stalled cursor
    ]

    def opener(url, timeout=None):
        urls.append(url)
        if len(urls) > len(pages):
            raise AssertionError("pagination did not stop after a page made no id progress")
        return pages[len(urls) - 1]

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener, sleep=lambda _: None)
    assert len(urls) == 2  # second page contributed no new ids -> the guard stops the loop
    assert df.height == 1000
    assert df["trade_id"].is_sorted()


def test_full_page_sharing_one_second_still_terminates():
    """The historical defect, reproduced (spec 00053 D5a): with 1000 rows inside ONE integer second,
    `last // 1e9` truncated back to the SAME `since` that produced the page — an infinite loop
    against the live venue; the raw `last` keeps the nanosecond fraction, which advances anyway.

    `responses` maps `since` -> a FACTORY, not a single-use stream, so `since=1783735200` genuinely
    re-serves `page1` — what the old conversion did to request 2. Against that old conversion this
    test fails on `df.height == 1001`, not on the 5-call cap, which is an independent safety net."""
    urls = []
    page1_rows = [[str(i), "1", 1783735200.0 + i / 1000, "b", "m", "", 100 + i] for i in range(1000)]
    page1_last = _last_for(page1_rows)
    page2_rows = [["1", "1", 1783735300.0, "b", "m", "", 2000]]
    page2_last = _last_for(page2_rows)
    responses = {
        "1783735200": lambda: _page(page1_rows, page1_last),  # the initial seconds-epoch `since`
        page1_last: lambda: _page(page2_rows, page2_last),  # the raw ns cursor from page 1
    }

    def opener(url, timeout=None):
        urls.append(url)
        if len(urls) > 5:
            raise AssertionError("pagination did not terminate (cursor appears stalled)")
        since_value = url.rsplit("since=", 1)[1]  # exact match: avoids "1783735200" prefix-matching
        if since_value not in responses:  # the raw cursor, e.g. "1783735200999000064"
            raise AssertionError(f"unexpected since={since_value}")
        return responses[since_value]()  # fresh _Resp per call: the mock can genuinely re-serve

    df = fetch_trades("BTC/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener, sleep=lambda _: None)
    assert len(urls) == 2
    assert df.height == 1001


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


def test_malformed_pair_raises_before_any_request():
    """A symbol that isn't `BASE/QUOTE` (no slash) can't be turned into an altname at all --
    `dump_pair_name` raises `BackfillError`, which must surface here as `TradeBackfillError`
    (cli/trades's error contract) before any request is issued."""
    calls = []

    def opener(u, timeout=None):
        calls.append(u)
        return _page([], 0)

    with pytest.raises(TradeBackfillError, match="no Kraken altname"):
        fetch_trades("NOPE", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener)
    assert calls == []  # "before any request" — the opener must never have been called


def test_new_pair_not_in_any_hardcoded_map_derives_and_fetches():
    """T0055: the 11th-pair case. `XYZ/EUR` is not, and never was, in any hardcoded map -- it must
    still derive an altname (`XYZEUR`, no alias applies) and issue a real request, proving the
    altname is DERIVED rather than looked up in a fixed table."""
    urls = []

    def opener(url, timeout=None):
        urls.append(url)
        return _page([], 0)

    df = fetch_trades("XYZ/EUR", dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC), opener=opener)
    assert len(urls) == 1
    assert "pair=XYZEUR" in urls[0]
    assert df.height == 0


def test_ts_truncation_pinned_to_measured_venue_values():
    """Regression pin for spec 00053 D6a, on REAL floats Kraken returned for trades that also exist
    in the archive: REST-float -> truncated-microsecond is what the client emits, and truncation
    does not always recover the WS value, so no case here asserts equality with one.

    Measured against WS ground truth: 1783738586.1807897 and 1783738621.9864349 truncate ONTO the
    WS microsecond (180789, 986434); 1783735200.948044 and 1783735200.671504 land 1us above it (WS
    948043, 671503). round() would be strictly worse (180790, 986435) — do not "fix" this to round()."""
    cases = [
        (1783738586.1807897, 180789),
        (1783738621.9864349, 986434),
        (1783735200.948044, 948044),
        (1783735200.671504, 671504),
    ]
    for raw, want_trunc in cases:
        df = fetch_trades(
            "BTC/EUR",
            dt.datetime(2026, 7, 11, 2, tzinfo=dt.UTC),
            opener=lambda url, timeout=None, _r=raw: _page([["1", "2", _r, "b", "m", "", 7]], 0),
        )
        got = df.row(0, named=True)["ts"].microsecond
        assert got == want_trunc, f"{raw}: expected truncated {want_trunc}, got {got}"
