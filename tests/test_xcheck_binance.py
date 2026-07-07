from __future__ import annotations

import io
import json
import urllib.error
from unittest import mock

import polars as pl
import pytest

from cli.ohlc.dataset import to_frame, write_parquet
from cli.xcheck.binance import (
    binance_daily_closes,
    binance_pair_name,
    crosscheck_dataset,
    crosscheck_series,
    fetch_binance_klines,
    render_markdown,
)
from cli.xcheck.errors import XCheckError

BASE_TS = 1721174400  # 2024-07-17T00:00:00Z (seconds)
DAY = 86400


def _kline(ts_ms: int, close: float) -> list:
    return [ts_ms, "0", "0", "0", str(close), "0", ts_ms + 86_399_999]


def _kraken_row(ts: int, close: str = "100.0") -> list:
    return [ts, "100.0", "101.0", "99.0", close, "100.0", "10.0", 5]


def _kraken_frame(n: int, close_fn=lambda i: "100.0") -> pl.DataFrame:
    return to_frame([_kraken_row(BASE_TS + i * DAY, close_fn(i)) for i in range(n)])


def _binance_frame(n: int, close_fn=lambda i: 100.0) -> pl.DataFrame:
    ts_ms = [(BASE_TS + i * DAY) * 1000 for i in range(n)]
    return (
        pl.DataFrame({"ts_ms": ts_ms, "close": [close_fn(i) for i in range(n)]})
        .with_columns(pl.from_epoch(pl.col("ts_ms"), time_unit="ms").dt.replace_time_zone("UTC").alias("ts"))
        .select("ts", "close")
    )


# --- binance_pair_name ---


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        ("BTC/EUR", "BTCEUR"),
        ("DOGE/EUR", "DOGEEUR"),
        ("ETH/BTC", "ETHBTC"),
        ("SOL/BTC", "SOLBTC"),
        ("ETH/EUR", "ETHEUR"),
    ],
)
def test_binance_pair_name_maps_common_tickers(symbol, expected):
    assert binance_pair_name(symbol) == expected


def test_binance_pair_name_rejects_non_base_quote_symbol():
    with pytest.raises(XCheckError):
        binance_pair_name("BTCEUR")


# --- fetch_binance_klines ---


def test_fetch_binance_klines_raises_xcheck_error_on_http_error():
    http_error = urllib.error.HTTPError("url", 429, "Too Many Requests", None, None)
    with mock.patch("urllib.request.urlopen", side_effect=http_error):
        with pytest.raises(XCheckError):
            fetch_binance_klines("BTCEUR")


def test_fetch_binance_klines_raises_xcheck_error_on_url_error():
    with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
        with pytest.raises(XCheckError):
            fetch_binance_klines("BTCEUR")


def test_fetch_binance_klines_raises_xcheck_error_on_non_list_payload():
    body = json.dumps({"code": -1121, "msg": "Invalid symbol."}).encode("utf-8")
    with mock.patch("urllib.request.urlopen", return_value=io.BytesIO(body)):
        with pytest.raises(XCheckError):
            fetch_binance_klines("BTCEUR")


# --- binance_daily_closes ---


def test_binance_daily_closes_parses_sorts_and_dedupes():
    rows = [
        _kline(BASE_TS * 1000 + 2 * DAY * 1000, 102.0),
        _kline(BASE_TS * 1000, 100.0),
        _kline(BASE_TS * 1000, 100.0),  # exact duplicate of the first row
    ]

    frame = binance_daily_closes("BTCEUR", fetch_fn=lambda pair, *, limit=1000: rows)

    assert frame.columns == ["ts", "close"]
    assert frame.schema["ts"] == pl.Datetime("us", "UTC")
    assert frame.schema["close"] == pl.Float64
    assert frame.height == 2
    assert frame["ts"].is_sorted()
    assert frame["close"].to_list() == [100.0, 102.0]


def test_binance_daily_closes_raises_on_empty_result():
    with pytest.raises(XCheckError):
        binance_daily_closes("BTCEUR", fetch_fn=lambda pair, *, limit=1000: [])


def test_binance_daily_closes_raises_on_unparseable_row():
    with pytest.raises(XCheckError):
        binance_daily_closes("BTCEUR", fetch_fn=lambda pair, *, limit=1000: [["not-a-timestamp", "0", "0", "0", "100.0"]])


# --- crosscheck_series ---


def test_crosscheck_series_identical_closes():
    kraken = _kraken_frame(5, close_fn=lambda i: str(100.0 + i))
    binance = _binance_frame(5, close_fn=lambda i: 100.0 + i)

    result = crosscheck_series(kraken, binance)

    assert result["overlap_rows"] == 5
    assert result["close_corr"] == pytest.approx(1.0)
    assert result["max_abs_rel_diff"] == 0.0


def test_crosscheck_series_planted_diff_reports_worst_row():
    kraken = _kraken_frame(5, close_fn=lambda i: str(100.0 + i))
    binance = _binance_frame(5, close_fn=lambda i: (100.0 + i) if i != 2 else 90.0)

    result = crosscheck_series(kraken, binance)

    expected_rel_diff = abs(102.0 - 90.0) / 90.0
    assert result["max_abs_rel_diff"] == pytest.approx(expected_rel_diff)
    assert result["max_rel_diff_ts"] == kraken["ts"][2]


def test_crosscheck_series_disjoint_ts_yields_zero_overlap_and_nulls():
    kraken = _kraken_frame(3)
    far_future_ts_ms = [(BASE_TS + 1000 * DAY + i * DAY) * 1000 for i in range(3)]
    binance = (
        pl.DataFrame({"ts_ms": far_future_ts_ms, "close": [100.0, 101.0, 102.0]})
        .with_columns(pl.from_epoch(pl.col("ts_ms"), time_unit="ms").dt.replace_time_zone("UTC").alias("ts"))
        .select("ts", "close")
    )

    result = crosscheck_series(kraken, binance)

    assert result == {
        "overlap_rows": 0,
        "close_corr": None,
        "return_corr": None,
        "max_abs_rel_diff": 0.0,
        "max_rel_diff_ts": None,
    }


def test_crosscheck_series_return_corr_on_monotone_series():
    kraken = _kraken_frame(6, close_fn=lambda i: str(100.0 + i * i))
    binance = _binance_frame(6, close_fn=lambda i: 100.0 + i * i)

    result = crosscheck_series(kraken, binance)

    assert result["overlap_rows"] == 6
    assert result["return_corr"] == pytest.approx(1.0)


# --- crosscheck_dataset ---


def test_crosscheck_dataset_skips_symbol_whose_binance_fetch_errors(tmp_path):
    root = tmp_path / "ohlc-full"
    for base, quote in [("BTC", "EUR"), ("SOL", "BTC")]:
        write_parquet(to_frame([_kraken_row(BASE_TS + i * DAY) for i in range(3)]), root / base / quote / "1440.parquet")

    def fetch_fn(pair, *, limit=1000):
        if pair == "SOLBTC":
            raise XCheckError("not listed on Binance")
        ts_ms = [(BASE_TS + i * DAY) * 1000 for i in range(3)]
        return [_kline(ts, 100.0) for ts in ts_ms]

    report = crosscheck_dataset(root, ["BTC/EUR", "SOL/BTC"], fetch_fn=fetch_fn)

    assert report["skipped"] == ["SOL/BTC"]
    assert "BTC/EUR" in report["series"]
    assert "SOL/BTC" not in report["series"]
    assert report["summary"]["series_count"] == 1


def test_crosscheck_dataset_skips_malformed_symbol_without_crashing(tmp_path):
    root = tmp_path / "ohlc-full"
    write_parquet(to_frame([_kraken_row(BASE_TS + i * DAY) for i in range(3)]), root / "BTC" / "EUR" / "1440.parquet")

    def fetch_fn(pair, *, limit=1000):
        ts_ms = [(BASE_TS + i * DAY) * 1000 for i in range(3)]
        return [_kline(ts, 100.0) for ts in ts_ms]

    report = crosscheck_dataset(root, ["BTCEUR", "BTC/EUR"], fetch_fn=fetch_fn)

    assert report["skipped"] == ["BTCEUR"]
    assert "BTC/EUR" in report["series"]
    assert report["summary"]["series_count"] == 1


# --- render_markdown ---


def test_render_markdown_contains_series_row_and_summary(tmp_path):
    root = tmp_path / "ohlc-full"
    write_parquet(to_frame([_kraken_row(BASE_TS + i * DAY) for i in range(3)]), root / "BTC" / "EUR" / "1440.parquet")

    def fetch_fn(pair, *, limit=1000):
        ts_ms = [(BASE_TS + i * DAY) * 1000 for i in range(3)]
        return [_kline(ts, 100.0) for ts in ts_ms]

    report = crosscheck_dataset(root, ["BTC/EUR"], fetch_fn=fetch_fn)
    md = render_markdown(report)

    assert "BTC/EUR" in md
    assert "## Summary" in md
