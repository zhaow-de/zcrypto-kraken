from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import polars as pl

from cli.ohlc.dataset import read_parquet
from cli.xcheck.errors import XCheckError

_BASE_URL = "https://data-api.binance.vision/api/v3/klines"
_TIMEOUT_SECONDS = 15


def binance_pair_name(symbol: str) -> str:
    """Map a canonical `"BASE/QUOTE"` symbol to its Binance ticker (e.g. `"BTC/EUR"` -> `"BTCEUR"`).

    The project's symbols already use the common tickers Binance expects (`BTC`, `DOGE`, ...), not
    Kraken's internal codes (`XBT`, `XDG`), so no translation table is needed. Raises `XCheckError`
    on a symbol that isn't `"BASE/QUOTE"`.
    """
    parts = symbol.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise XCheckError(f"not a BASE/QUOTE symbol: {symbol!r}")
    base, quote = parts
    return f"{base}{quote}"


def fetch_binance_klines(pair: str, *, limit: int = 1000) -> list:
    """GET Binance's public daily klines for `pair` and return the raw kline rows.

    Raises `XCheckError` on a transport/JSON failure, or when the decoded body isn't a list.
    """
    url = f"{_BASE_URL}?symbol={pair}&interval=1d&limit={limit}"
    try:
        with urllib.request.urlopen(url, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError) as exc:
        raise XCheckError(f"transport error fetching Binance klines for {pair}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise XCheckError(f"invalid JSON from Binance klines for {pair}: {exc}") from exc

    if not isinstance(payload, list):
        raise XCheckError(f"expected a list of klines for {pair}, got {type(payload).__name__}")
    return payload


def binance_daily_closes(pair: str, *, fetch_fn=fetch_binance_klines, limit: int = 1000) -> pl.DataFrame:
    """Fetch daily klines for `pair` via `fetch_fn` and parse into a canonical `{ts, close}` frame.

    Each kline row is `[openTime_ms, open, high, low, close, volume, closeTime, ...]` (>= 5 fields);
    `openTime_ms` -> `ts` (`Datetime("us", "UTC")`), `close` (row[4], a string) -> `Float64`. The
    result is sorted ascending and exact-`ts` de-duped. Raises `XCheckError` on an empty result or
    an unparseable row.
    """
    rows = fetch_fn(pair, limit=limit)
    if not rows:
        raise XCheckError(f"empty klines result for {pair}")

    try:
        parsed = [[int(row[0]), float(row[4])] for row in rows]
    except (IndexError, TypeError, ValueError) as exc:
        raise XCheckError(f"unparseable kline row for {pair}: {exc}") from exc

    frame = (
        pl.DataFrame(parsed, schema=["ts_ms", "close"], orient="row")
        .with_columns(pl.from_epoch(pl.col("ts_ms"), time_unit="ms").dt.replace_time_zone("UTC").alias("ts"))
        .select("ts", "close")
        .sort("ts")
        .unique(subset=["ts"], keep="first", maintain_order=True)
    )
    return frame


def crosscheck_series(kraken: pl.DataFrame, binance: pl.DataFrame) -> dict:
    """Cross-check a canonical Kraken daily frame against a Binance daily-closes frame on their `ts` overlap.

    Returns `{overlap_rows, close_corr, return_corr, max_abs_rel_diff, max_rel_diff_ts}`, where
    `max_abs_rel_diff = max(|k_close - b_close| / b_close)` and `max_rel_diff_ts` is its date;
    `close_corr` / `return_corr` are the Pearson correlation of the closes / of daily pct-returns.
    Fewer than 2 overlapping rows yields null correlations and a zero max-diff.
    """
    joined = kraken.select("ts", "close").join(binance.select("ts", "close"), on="ts", how="inner", suffix="_binance").sort("ts")
    overlap_rows = joined.height
    if overlap_rows < 2:
        return {
            "overlap_rows": overlap_rows,
            "close_corr": None,
            "return_corr": None,
            "max_abs_rel_diff": 0.0,
            "max_rel_diff_ts": None,
        }

    diffs = joined.with_columns(((pl.col("close") - pl.col("close_binance")).abs() / pl.col("close_binance")).alias("rel_diff"))
    worst = diffs.sort("rel_diff", descending=True).row(0, named=True)

    returns = diffs.select(
        pl.col("close").pct_change().alias("k_ret"),
        pl.col("close_binance").pct_change().alias("b_ret"),
    ).drop_nulls()

    return {
        "overlap_rows": overlap_rows,
        "close_corr": diffs.select(pl.corr("close", "close_binance")).item(),
        "return_corr": returns.select(pl.corr("k_ret", "b_ret")).item(),
        "max_abs_rel_diff": float(worst["rel_diff"]),
        "max_rel_diff_ts": worst["ts"],
    }


def crosscheck_dataset(kraken_root: Path, symbols: list[str], *, fetch_fn=fetch_binance_klines) -> dict:
    """Cross-check each `symbol`'s Kraken daily series under `kraken_root` against Binance.

    For each `"BASE/QUOTE"` in `symbols`, reads `kraken_root/{base}/{quote}/1440.parquet` and compares
    it to Binance's daily closes (`binance_pair_name(symbol)`, fetched via `fetch_fn`). A symbol whose
    Binance fetch raises `XCheckError` (pair not listed on Binance) is skipped and recorded under
    `skipped` instead of `series`. Returns `{series: {symbol: crosscheck_series-dict}, skipped: [...],
    summary}`, where `summary` is `{series_count, min_close_corr, max_abs_rel_diff_overall}`.
    """
    series: dict[str, dict] = {}
    skipped: list[str] = []

    for symbol in symbols:
        base, quote = symbol.split("/")
        kraken = read_parquet(kraken_root / base / quote / "1440.parquet")
        try:
            binance = binance_daily_closes(binance_pair_name(symbol), fetch_fn=fetch_fn)
        except XCheckError:
            skipped.append(symbol)
            continue
        series[symbol] = crosscheck_series(kraken, binance)

    close_corrs = [s["close_corr"] for s in series.values() if s["close_corr"] is not None]
    max_diffs = [s["max_abs_rel_diff"] for s in series.values()]
    summary = {
        "series_count": len(series),
        "min_close_corr": min(close_corrs) if close_corrs else None,
        "max_abs_rel_diff_overall": max(max_diffs) if max_diffs else 0.0,
    }
    return {"series": series, "skipped": skipped, "summary": summary}


def render_markdown(report: dict) -> str:
    """Render a cross-check `report` (as returned by `crosscheck_dataset`) as a Markdown table + summary."""
    lines = [
        "# Binance Cross-Check Report",
        "",
        "| Symbol | Overlap rows | Close corr | Return corr | Max abs rel diff | Worst-diff date |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for symbol, s in report["series"].items():
        close_corr = f"{s['close_corr']:.4f}" if s["close_corr"] is not None else "n/a"
        return_corr = f"{s['return_corr']:.4f}" if s["return_corr"] is not None else "n/a"
        worst_date = s["max_rel_diff_ts"].date().isoformat() if s["max_rel_diff_ts"] is not None else "n/a"
        lines.append(
            f"| {symbol} | {s['overlap_rows']} | {close_corr} | {return_corr} | {s['max_abs_rel_diff']:.6f} | {worst_date} |"
        )

    summary = report["summary"]
    min_close_corr = f"{summary['min_close_corr']:.4f}" if summary["min_close_corr"] is not None else "n/a"
    lines += [
        "",
        "## Summary",
        "",
        f"- Series count: {summary['series_count']}",
        f"- Min close corr: {min_close_corr}",
        f"- Max abs rel diff overall: {summary['max_abs_rel_diff_overall']:.6f}",
    ]

    if report["skipped"]:
        lines += ["", "## Skipped (not on Binance)", ""]
        lines += [f"- {symbol}" for symbol in report["skipped"]]

    return "\n".join(lines) + "\n"
