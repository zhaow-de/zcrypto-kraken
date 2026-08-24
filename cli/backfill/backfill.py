from __future__ import annotations

import hashlib
import json
from pathlib import Path

import polars as pl

from cli.backfill.aggregate import aggregate_minutes
from cli.backfill.read import read_minute_rows
from cli.data.manifest import build_manifest, series_entry
from cli.ohlc.dataset import to_frame, write_parquet
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
            relpath = f"{base}/{quote}/{interval}.parquet"
            write_parquet(frame, out_root / relpath)
            series[relpath] = series_entry(frame, relpath)

    # `source` is machine-local and `fetched_at` is a wall clock: both move without content moving,
    # so both are quarantined in `provenance`, outside every digest.
    manifest = build_manifest(series, written_at=fetched_at, provenance={"fetched_at": fetched_at, "source": str(source_dir)})
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
