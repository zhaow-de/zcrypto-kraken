from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from cli.backfill.aggregate import aggregate_minutes
from cli.backfill.read import read_minute_rows
from cli.ohlc.dataset import dataset_hash, to_frame, write_parquet
from cli.ohlc.qa import INTERVAL_SECONDS


def backfill_pair(source_dir: Path, symbol: str, intervals: list[str]) -> dict[str, pl.DataFrame]:
    """Reconstruct canonical OHLCVT frames for `symbol` at each cadence in `intervals`.

    Reads the pair's 1-minute rows once (`read_minute_rows`), then aggregates + canonicalizes
    (`aggregate_minutes` -> `to_frame`) per interval label — a key of `cli.ohlc.qa.INTERVAL_SECONDS`
    (e.g. `"1440"`, `"240"`, `"60"`). Returns `{interval_label: frame}`.
    """
    rows = read_minute_rows(source_dir, symbol)
    return {interval: to_frame(aggregate_minutes(rows, INTERVAL_SECONDS[interval])) for interval in intervals}


def backfill_basket(
    source_dir: Path,
    symbols: list[str],
    intervals: list[str],
    out_root: Path,
    fetched_at: str,
) -> dict:
    """Backfill every symbol x interval in the basket, writing canonical Parquet + a manifest.

    Writes `out_root/{base}/{quote}/{interval}.parquet` for each symbol x interval. Mirrors
    `cli.ohlc.ingest.ingest_basket`'s manifest shape: `fetched_at`, `source`, one `series` entry
    per symbol x interval (`rows`, `first_ts`, `last_ts`, `sha256`), and a `basket_sha256` over the
    sorted per-series hashes. Deterministic given a fixed `fetched_at`. Writes `out_root/manifest.json`
    and returns it.
    """
    series: dict[str, dict] = {}
    for symbol in symbols:
        frames = backfill_pair(source_dir, symbol, intervals)
        base, quote = symbol.split("/")
        for interval, frame in frames.items():
            write_parquet(frame, out_root / base / quote / f"{interval}.parquet")
            series.setdefault(symbol, {})[interval] = {
                "rows": frame.height,
                "first_ts": frame["ts"].min().isoformat(),
                "last_ts": frame["ts"].max().isoformat(),
                "sha256": dataset_hash(frame),
            }

    basket_sha256 = hashlib.sha256(
        "".join(series[symbol][interval]["sha256"] for symbol in sorted(series) for interval in sorted(series[symbol])).encode()
    ).hexdigest()

    manifest = {
        "fetched_at": fetched_at,
        "source": str(source_dir),
        "series": series,
        "basket_sha256": basket_sha256,
    }
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
