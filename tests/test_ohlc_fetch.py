import io
import json
import urllib.error
from pathlib import Path

import pytest

from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import fetch_ohlc

_FIXTURES = Path(__file__).parent / "fixtures"
OHLC_FIXTURE = json.loads((_FIXTURES / "kraken_ohlc_xxbtzeur_1440.json").read_text())


def _opener(body: dict):
    def _open(url, timeout=None):
        return io.BytesIO(json.dumps(body).encode("utf-8"))

    return _open


def test_fetch_ohlc_returns_rows_on_success():
    rows = fetch_ohlc("XXBTZEUR", 1440, opener=_opener(OHLC_FIXTURE))
    assert rows == OHLC_FIXTURE["result"]["XXBTZEUR"]


def test_fetch_ohlc_picks_series_key_ignoring_last():
    rows = fetch_ohlc("XXBTZEUR", 1440, opener=_opener(OHLC_FIXTURE))
    assert len(rows) == len(OHLC_FIXTURE["result"]["XXBTZEUR"])
    assert all(isinstance(row, list) for row in rows)


def test_fetch_ohlc_raises_on_nonempty_error_array():
    body = {"error": ["EGeneral:Invalid arguments"], "result": {}}
    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))


def test_fetch_ohlc_raises_on_transport_error():
    def _raise(url, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_raise)


def test_fetch_ohlc_raises_on_missing_result_key():
    body = {"error": []}
    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))


def test_fetch_ohlc_raises_on_result_with_only_last_key():
    body = {"error": [], "result": {"last": 1234567890}}
    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))
