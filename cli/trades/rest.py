from __future__ import annotations

import datetime as dt
import json
import time
import urllib.error
import urllib.request

import polars as pl

from cli.backfill.errors import BackfillError
from cli.backfill.read import dump_pair_name
from cli.capture.segment_writer import TRADE_SCHEMA
from cli.logging import get_logger
from cli.trades.errors import TradeBackfillError

logger = get_logger("trades.rest")

_BASE_URL = "https://api.kraken.com/0/public/Trades"
_TIMEOUT_SECONDS = 30
_PAGE_ROWS = 1000  # Kraken's page size; a SHORT page means the series is exhausted
_MIN_INTERVAL_SECONDS = 3.0  # 1.5s was DEMONSTRABLY refused (EGeneral:Too many requests) on the
# live bulk run (T0053, resolved) -- do not "optimise" this back down without new measurement

_SIDE = {"b": "buy", "s": "sell"}
_ORD_TYPE = {"m": "market", "l": "limit"}


def _row_ts(raw: float) -> dt.datetime:
    """Convert Kraken's REST float epoch to a microsecond ts, TRUNCATING the fraction.

    Truncation is the better of two imperfect estimators against WS ground truth -- never "fix" it to round() (spec 00053 D6a).
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
    """Fetch Kraken public trades for `pair` from `since` (inclusive), in `TRADE_SCHEMA`, ascending `trade_id`, `symbol` the
    canonical pair. `until` bounds PAGING ONLY -- it stops further page requests once a page's newest row reaches it, never trims,
    and so can return rows past `until`. A REST row matches a WS-captured one on every field but `ts` (spec 00053 D6/D6a; see
    `_row_ts`), so the merge keys on `trade_id` ALONE and the WS row wins -- only a RECOVERED trade carries this estimate."""
    # The altname is derived (`dump_pair_name`) rather than mapped per pair, so a NEW capture pair
    # heals with no code change (T0055, resolved, records the residual per-aliased-asset drift).
    # Kraken answers under its OWN key (XBTEUR -> XXBTZEUR), so the series key below is positional.
    try:
        altname = dump_pair_name(pair)
    except BackfillError as exc:
        raise TradeBackfillError(f"no Kraken altname for pair {pair!r}: {exc}") from exc

    cursor = int(since.timestamp())
    frames: list[pl.DataFrame] = []
    max_trade_id_seen: int | None = None
    while True:
        url = f"{_BASE_URL}?pair={altname}&since={cursor}"
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
        page_max_id = int(frame["trade_id"].max())
        if max_trade_id_seen is not None and page_max_id <= max_trade_id_seen:
            # Defence in depth (spec 00053 D5a): the ns cursor always advances, so this should be
            # unreachable, but a stall would hammer a public endpoint forever.
            logger.warning(
                "trades.rest: %s page made no trade_id progress (max=%d, already seen up to %d); stopping pagination",
                pair,
                page_max_id,
                max_trade_id_seen,
            )
            break
        max_trade_id_seen = page_max_id
        frames.append(frame)
        logger.debug(
            "trades.rest: %s page %d rows=%d max_trade_id=%d cursor=%s",
            pair,
            len(frames),
            len(rows),
            page_max_id,
            cursor,
        )

        newest = frame["ts"].max()
        if until is not None and newest >= until:
            break
        if len(rows) < _PAGE_ROWS:
            break  # short page: the series is exhausted

        # `since` takes the raw ns `last` cursor as well as a seconds epoch, so feed `last` back
        # UNMODIFIED (spec 00053 D5a); it is inclusive, so a page break re-returns one row, absorbed
        # by the final dedupe. Converting it to seconds (`last // 1e9`) rewinds to the start of that
        # second and, when 1000 rows share one second, re-issues the same `since` -- an infinite loop.
        cursor = result["last"]
        sleep(_MIN_INTERVAL_SECONDS)

    if not frames:
        return pl.DataFrame([], schema=TRADE_SCHEMA)
    return pl.concat(frames).unique(subset=["trade_id"], keep="first").sort("trade_id")
