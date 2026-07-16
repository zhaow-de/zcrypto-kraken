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
# live bulk run 2026-07-16 (T0053) -- do not "optimise" this back down without new measurement

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
    """Fetch Kraken public trades for `pair` from `since` (inclusive).

    `until`, when given, bounds PAGING ONLY: it stops issuing further page requests once a page's
    newest row reaches it. It does NOT trim the returned rows to `until` — the returned frame can
    contain rows past `until`. The caller filters to whatever range it actually wants.

    Returns rows in `TRADE_SCHEMA`, ascending `trade_id`, `symbol` set to the CANONICAL pair. A
    REST-sourced row matches a WS-captured one for the same trade EXACTLY on `trade_id`, `symbol`,
    `side`, `price`, `qty`, and `ord_type` (D6) — but NOT on `ts`, which REST cannot reproduce
    (D6a: its float epoch runs ~+1 us above the WS microsecond; see `_row_ts`). That is why dedupe
    keys on `trade_id` ALONE and the primary row wins: a trade present in both keeps its WS `ts`,
    and only a recovered trade carries this one.
    """
    # Reuse `cli.backfill.read.dump_pair_name` instead of a hardcoded per-pair map (T0055): the old
    # `KRAKEN_ALTNAME` dict listed exactly the 10 pairs in the capture universe with nothing tying
    # the two together, so an 11th pair would silently never heal. Deriving the altname makes that
    # structurally impossible -- a new pair works automatically. Kraken still answers under its OWN
    # key (XBTEUR -> XXBTZEUR), so the response key below is read positionally, never assumed.
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
            # Defence in depth (D5a): the raw cursor is nanoseconds and always advances, so this
            # should be unreachable — but the blast radius of a stall (hammering a public
            # endpoint forever) is out of proportion to the cost of this check.
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

        # D5a (measured against the live endpoint): `since` accepts BOTH a seconds epoch AND the
        # raw ns `last` cursor — feed `last` back UNMODIFIED. It is Kraken's documented usage and
        # is inclusive of the last row (a page break re-returns exactly 1 row, absorbed by
        # dedupe). Converting it to seconds (`last // 1e9`) was the defect: it rewinds to the
        # start of that second and, when 1000 rows share one second, yields the SAME `since` as
        # before — an infinite loop against the live venue.
        cursor = result["last"]
        sleep(_MIN_INTERVAL_SECONDS)

    if not frames:
        return pl.DataFrame([], schema=TRADE_SCHEMA)
    return pl.concat(frames).unique(subset=["trade_id"], keep="first").sort("trade_id")
