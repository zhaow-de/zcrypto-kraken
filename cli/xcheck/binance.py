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
    """No translation table: the project's symbols already carry the common tickers Binance expects, never Kraken's internal codes."""
    parts = symbol.split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise XCheckError(f"not a BASE/QUOTE symbol: {symbol!r}")
    base, quote = parts
    return f"{base}{quote}"


def fetch_binance_klines(pair: str, *, limit: int = 1000) -> list:
    """A recent-window check, never full history: `limit` is Binance's single-page maximum and this makes one request."""
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
    """A Binance kline row is `[openTime_ms, open, high, low, close, volume, closeTime, ...]`, which is what `row[0]` and `row[4]` below are."""
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
    """Compare two daily frames on their `ts` overlap: the relative difference is taken against Binance's close, and fewer than two overlapping rows is null, not zero correlation."""
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
    """Cross-check each symbol's Kraken daily series against Binance's closes into one dict of `series`, `skipped` and `summary`; a symbol that cannot be checked — malformed, no parquet, not listed on Binance — lands in `skipped`, never raises."""
    series: dict[str, dict] = {}
    skipped: list[str] = []

    for symbol in symbols:
        try:
            base, quote = symbol.split("/")
            kraken = read_parquet(kraken_root / base / quote / "1440.parquet")
            binance = binance_daily_closes(binance_pair_name(symbol), fetch_fn=fetch_fn)
        except ValueError, XCheckError, FileNotFoundError:
            skipped.append(symbol)
            continue
        series[symbol] = crosscheck_series(kraken, binance)

    close_corrs = [s["close_corr"] for s in series.values() if s["close_corr"] is not None]
    max_diffs = [s["max_abs_rel_diff"] for s in series.values()]
    summary = {
        "series_count": len(series),
        "min_close_corr": min(close_corrs) if close_corrs else None,
        # None, not 0.0, matching `min_close_corr` above: a maximum over no series has no value,
        # and zero deviation reads as every series matching exactly.
        "max_abs_rel_diff_overall": max(max_diffs) if max_diffs else None,
    }
    return {"series": series, "skipped": skipped, "summary": summary}


def render_markdown(report: dict) -> str:
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
    overall = summary["max_abs_rel_diff_overall"]
    max_abs_rel_diff = f"{overall:.6f}" if overall is not None else "n/a"
    lines += [
        "",
        "## Summary",
        "",
        f"- Series count: {summary['series_count']}",
        f"- Min close corr: {min_close_corr}",
        f"- Max abs rel diff overall: {max_abs_rel_diff}",
        "",
        "_Recent-window check: the most recent ≤ 1000 daily candles per pair (Binance single-page "
        "limit); Binance EUR history reaches ~2020, so full-overlap cross-check via startTime pagination "
        "is a deferred follow-up._",
    ]

    if report["skipped"]:
        lines += ["", "## Skipped (not on Binance)", ""]
        lines += [f"- {symbol}" for symbol in report["skipped"]]

    return "\n".join(lines) + "\n"
