from __future__ import annotations

import json
import urllib.error
import urllib.request

from cli.ohlc.errors import OHLCError

_BASE_URL = "https://api.kraken.com/0/public/OHLC"
_TIMEOUT_SECONDS = 15


def fetch_ohlc(pair_key: str, interval: int, *, opener=urllib.request.urlopen) -> list[list]:
    """GET Kraken's public OHLC endpoint for `pair_key`/`interval` and return the candle rows.

    Raises `OHLCError` on a transport/JSON failure, or when Kraken's `error` array is non-empty
    (Kraken returns HTTP 200 with errors carried in the response body). The `result` dict carries
    the candle-row list under a pair-specific key alongside `last`; this returns that series.
    """
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

    result = payload["result"]
    series_key = next(key for key in result if key != "last")
    return result[series_key]
