import http.client
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

    with pytest.raises(OHLCError) as caught:
        fetch_ohlc("XXBTZEUR", 1440, opener=_raise)
    assert "transport error fetching OHLC" in str(caught.value)
    # The IDENTITY, not the phrasing: an operator paged off the cycle must see WHICH pair stalled.
    assert "XXBTZEUR" in str(caught.value) and "1440" in str(caught.value)


def test_fetch_ohlc_raises_on_missing_result_key():
    body = {"error": []}
    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))


def test_fetch_ohlc_raises_on_result_with_only_last_key():
    body = {"error": [], "result": {"last": 1234567890}}
    with pytest.raises(OHLCError):
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))


def test_pair_keys_are_symbol_keyed_and_cover_every_candidate():
    from cli.ohlc.fetch import PAIR_KEYS
    from cli.snapshot.assetpairs import CANDIDATE_SYMBOLS

    assert all("/" in k for k in PAIR_KEYS), "PAIR_KEYS must be keyed BASE/QUOTE, not by base alone"
    missing = [s for s in CANDIDATE_SYMBOLS if s not in PAIR_KEYS]
    assert missing == [], f"no REST pair key for {missing}"


def test_the_btc_quoted_legs_carry_the_venues_xbt_spelling():
    # The venue spells it XBT and we spell it BTC. A key that reads "...BTC" would be wrong.
    from cli.ohlc.fetch import PAIR_KEYS

    assert PAIR_KEYS["ETH/BTC"] == "XETHXXBT"
    assert PAIR_KEYS["SOL/BTC"] == "SOLXBT"


def _raw_opener(payload: bytes):
    def _open(url, timeout=None):
        return io.BytesIO(payload)

    return _open


@pytest.mark.parametrize("payload", [b"\xff", b'{"error":[],"result":{"X":\xc3'])
def test_fetch_ohlc_contains_a_body_whose_bytes_do_not_decode(payload):
    """`UnicodeDecodeError` is a sibling of `JSONDecodeError` under `ValueError`, never a subclass,
    so the decode arm must name it to see a body that does not decode."""
    with pytest.raises(OHLCError) as caught:
        fetch_ohlc("XXBTZEUR", 1440, opener=_raw_opener(payload))
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
    # The LABEL, not just the containment: rejoining the two blocks would still raise `OHLCError`
    # -- the wide transport arm catches `ValueError` -- so only this pins the split.
    assert "undecodable or invalid JSON" in str(caught.value)
    assert "XXBTZEUR" in str(caught.value) and "1440" in str(caught.value)


@pytest.mark.parametrize("body", [[], "oops", None, 0])
def test_fetch_ohlc_contains_valid_json_that_is_not_an_object(body):
    """Valid JSON that is not an object is refused BY SHAPE, named as such rather than by whatever
    `.get` would have raised."""
    with pytest.raises(OHLCError) as caught:
        fetch_ohlc("XXBTZEUR", 1440, opener=_opener(body))
    assert "is not a JSON object" in str(caught.value)


def _raising_opener(exc: Exception):
    def _open(url, timeout=None):
        raise exc

    return _open


def _reading_opener(exc: Exception):
    class _Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def read(self, *args):
            raise exc

    def _open(url, timeout=None):
        return _Resp(b"")

    return _open


@pytest.mark.parametrize(
    "exc",
    [
        http.client.IncompleteRead(b"x" * 12, 42),
        http.client.BadStatusLine("garbage"),
        http.client.LineTooLong("header line"),
        ValueError("opener said no"),
    ],
)
def test_fetch_ohlc_contains_a_failing_opener(exc):
    """The opener seam is transport: `HTTPException` is neither `OSError` nor `ValueError`, so no
    arm saw it, and a plain `ValueError` from the opener had no arm either."""
    with pytest.raises(OHLCError) as caught:
        fetch_ohlc("XXBTZEUR", 1440, opener=_raising_opener(exc))
    assert caught.value.__cause__ is exc
    assert "transport error fetching OHLC" in str(caught.value)  # the LABEL, or the arms can swap silently


def test_fetch_ohlc_contains_a_truncated_body():
    """`IncompleteRead` from `.read()` is the production-reachable one: a body shorter than its
    `Content-Length`."""
    exc = http.client.IncompleteRead(b"x" * 12, 42)
    with pytest.raises(OHLCError) as caught:
        fetch_ohlc("XXBTZEUR", 1440, opener=_reading_opener(exc))
    assert caught.value.__cause__ is exc
    assert "transport error fetching OHLC" in str(caught.value)


@pytest.mark.parametrize(("pair_key", "interval"), [("XXBTZEUR", 1440), ("XETHZEUR", 60)])
def test_fetch_ohlc_names_the_pair_it_was_called_for(pair_key, interval):
    """A SECOND pair and interval, because every other call in this file passes the same literal.

    Against one fixture an identity pin cannot tell interpolation from a constant: a message
    hardcoding `XXBTZEUR@1440` satisfies it while naming the wrong pair to a paged operator."""

    def _raise(url, timeout=None):
        raise urllib.error.URLError("boom")

    with pytest.raises(OHLCError) as caught:
        fetch_ohlc(pair_key, interval, opener=_raise)
    assert pair_key in str(caught.value)
    assert str(interval) in str(caught.value)
