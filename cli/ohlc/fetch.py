from __future__ import annotations

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
    """GET Kraken's public OHLC endpoint for `pair_key`/`interval` and return the candle rows; every refusal raises `OHLCError`.

    Kraken answers HTTP 200 with failures carried in the body's `error` array, and puts the rows under a
    pair-specific key beside `last`."""
    url = f"{_BASE_URL}?pair={pair_key}&interval={interval}"
    try:
        with opener(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        raise OHLCError(f"transport error fetching OHLC for {pair_key}@{interval}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OHLCError(f"invalid JSON from OHLC for {pair_key}@{interval}: {exc}") from exc

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
