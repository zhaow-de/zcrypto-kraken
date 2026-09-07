from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

from cli.ohlc.errors import OHLCError

_BASE_URL = "https://api.kraken.com/0/public/OHLC"
_TIMEOUT_SECONDS = 15

# Keyed by FULL symbol, not by base: ETH and SOL each carry two quotes, which a base key cannot
# express. Kraken spells bitcoin XBT in both the pair key and the wsname; our symbols say BTC.
PAIR_KEYS: dict[str, str] = {
    "BTC/EUR": "XXBTZEUR",
    "ETH/EUR": "XETHZEUR",
    "SOL/EUR": "SOLEUR",
    "XRP/EUR": "XXRPZEUR",
    "ADA/EUR": "ADAEUR",
    "LINK/EUR": "LINKEUR",
    "DOGE/EUR": "XDGEUR",
    "LTC/EUR": "XLTCZEUR",
    "DOT/EUR": "DOTEUR",
    "AVAX/EUR": "AVAXEUR",
    "ETH/BTC": "XETHXXBT",
    "SOL/BTC": "SOLXBT",
}


def fetch_ohlc(pair_key: str, interval: int, *, opener=urllib.request.urlopen) -> list[list]:
    """Kraken answers HTTP 200 with failures carried in the body's `error` array, and puts the rows
    under a pair-specific key beside `last`."""
    url = f"{_BASE_URL}?pair={pair_key}&interval={interval}"
    # TWO blocks, each wrapping only the statements whose failures its own arm names, so no arm can
    # relabel another's: one enumeration always leaves the next level open, and this closes the class.
    # The transport arm can be wide because nothing here decodes; the decode arm stays narrow because
    # `json.loads` is the only statement it covers. `read()` stays inside the `with` so the response closes.
    try:
        with opener(url, timeout=_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except (urllib.error.URLError, OSError, http.client.HTTPException, ValueError) as exc:
        raise OHLCError(f"transport error fetching OHLC for {pair_key}@{interval}: {exc}") from exc

    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OHLCError(f"undecodable or invalid JSON from OHLC for {pair_key}@{interval}: {exc}") from exc

    # Kraken's contract is a JSON object; anything else valid-but-not-an-object reached `.get` below.
    if not isinstance(payload, dict):
        raise OHLCError(f"OHLC response for {pair_key}@{interval} is not a JSON object: {type(payload).__name__}")

    errors = payload.get("error") or []
    if errors:
        raise OHLCError(f"Kraken API error for OHLC {pair_key}@{interval}: {errors}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise OHLCError(f"missing or malformed 'result' in OHLC response for {pair_key}@{interval}")

    series_key = next((key for key in result if key != "last"), None)
    if series_key is None:
        raise OHLCError(f"no series key in OHLC 'result' for {pair_key}@{interval}")

    return result[series_key]
