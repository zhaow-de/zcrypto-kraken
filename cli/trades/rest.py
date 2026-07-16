from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request

import polars as pl

from cli.capture.segment_writer import TRADE_SCHEMA
from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError

logger = get_logger("trades.rest")

_BASE_URL = "https://api.kraken.com/0/public/Trades"
_TIMEOUT_SECONDS = 30
_PAGE_ROWS = 1000  # Kraken's page size; a SHORT page means the series is exhausted
_MIN_INTERVAL_SECONDS = 1.5  # public-endpoint courtesy; ~200-400 calls for the historical sweep

# Canonical -> Kraken REST altname. Kraken answers under its OWN key (XBTEUR -> XXBTZEUR), so the
# response key is read positionally, never assumed.
KRAKEN_ALTNAME: dict[str, str] = {
    "BTC/EUR": "XBTEUR",
    "ETH/EUR": "ETHEUR",
    "SOL/EUR": "SOLEUR",
    "XRP/EUR": "XRPEUR",
    "ADA/EUR": "ADAEUR",
    "DOT/EUR": "DOTEUR",
    "LINK/EUR": "LINKEUR",
    "LTC/EUR": "LTCEUR",
    "DOGE/EUR": "XDGEUR",
    "AVAX/EUR": "AVAXEUR",
}
_SIDE = {"b": "buy", "s": "sell"}
_ORD_TYPE = {"m": "market", "l": "limit"}


def _row_ts(raw: float) -> dt.datetime:
    """Convert Kraken's REST float epoch to a microsecond ts, TRUNCATING the fraction.

    Truncation is not a style choice — it is the better of two imperfect options, measured against
    trades present in BOTH the archive (WS-captured) and REST (spec 00053 D6a). Kraken's REST float
    runs systematically ~+0.7..+1.1 us ABOVE the WS ISO microsecond for the same trade, e.g. REST
    948044.06 vs WS 948043, REST 180789.71 vs WS 180789. Against that ground truth, truncation
    recovers the WS value 2/4 and rounding 0/4 — so DO NOT "fix" this to round(); it is strictly
    worse. float64 cannot carry an exact microsecond at this epoch anyway (ULP ~0.238 us), and the
    offset exceeds it, so no rounding mode closes the gap.

    The residual is safe by construction: dedupe keys on `trade_id` ALONE and the primary (WS) row
    wins, so a trade present in both keeps its WS ts; only a RECOVERED trade — which has no WS
    counterpart to disagree with — carries this value, accurate to ~1 us.
    """
    seconds = int(raw)
    micros = int((raw - seconds) * 1_000_000)
    return dt.datetime.fromtimestamp(seconds, dt.UTC).replace(microsecond=micros)


def _rows_to_frame(rows: list[list], pair: str) -> pl.DataFrame:
    recs = []
    for r in rows:
        try:
            recs.append(
                {
                    "ts": _row_ts(float(r[2])),
                    "symbol": pair,
                    "side": _SIDE[r[3]],
                    "price": float(r[0]),
                    "qty": float(r[1]),
                    "ord_type": _ORD_TYPE[r[4]],
                    "trade_id": int(r[6]),
                }
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise TradeBackfillError(f"unexpected REST trade row for {pair}: {r!r} ({exc})") from exc
    return pl.DataFrame(recs, schema=TRADE_SCHEMA)


def fetch_trades(
    pair: str,
    since: dt.datetime,
    *,
    until: dt.datetime | None = None,
    opener=urllib.request.urlopen,
    sleep=time.sleep,
) -> pl.DataFrame:
    """Fetch Kraken public trades for `pair` from `since` (inclusive), paginating to `until`.

    Returns rows in `TRADE_SCHEMA`, ascending `trade_id`, `symbol` set to the CANONICAL pair — a
    REST-sourced row is byte-comparable with a WS-captured one for the same trade, which is what
    makes dedupe-on-`trade_id` safe (spec 00053 D6).
    """
    altname = KRAKEN_ALTNAME.get(pair)
    if altname is None:
        raise TradeBackfillError(f"no Kraken altname for pair {pair!r}")

    cursor_s = int(since.timestamp())
    frames: list[pl.DataFrame] = []
    while True:
        url = f"{_BASE_URL}?pair={altname}&since={cursor_s}"
        try:
            with opener(url, timeout=_TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except (urllib.error.URLError, OSError) as exc:
            raise TradeBackfillError(f"transport error fetching trades for {pair}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise TradeBackfillError(f"invalid JSON fetching trades for {pair}: {exc}") from exc

        errors = payload.get("error") or []
        if errors:
            raise TradeBackfillError(f"Kraken error fetching trades for {pair}: {errors}")
        result = payload.get("result") or {}
        series_key = next((k for k in result if k != "last"), None)
        if series_key is None:
            raise TradeBackfillError(f"no trade series in REST result for {pair}: keys={list(result)}")
        rows = result[series_key]
        if not rows:
            break

        frame = _rows_to_frame(rows, pair)
        frames.append(frame)

        newest = frame["ts"].max()
        if until is not None and newest >= until:
            break
        if len(rows) < _PAGE_ROWS:
            break  # short page: the series is exhausted

        # `last` is NANOSECONDS; `since` is SECONDS. Passing it through raw lands ~31 years ahead
        # and returns an empty page forever.
        cursor_s = int(int(result["last"]) // 1_000_000_000)
        sleep(_MIN_INTERVAL_SECONDS)

    if not frames:
        return pl.DataFrame([], schema=TRADE_SCHEMA)
    return pl.concat(frames).unique(subset=["trade_id"], keep="first").sort("trade_id")
