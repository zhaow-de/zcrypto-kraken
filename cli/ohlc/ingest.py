from __future__ import annotations

import json
from pathlib import Path

from cli.data.manifest import build_manifest, series_entry
from cli.ohlc.dataset import dataset_hash, to_frame, write_parquet
from cli.ohlc.fetch import fetch_ohlc


def ingest_basket(
    pair_keys: dict[str, str],
    intervals: list[int],
    out_dir: Path,
    fetched_at: str,
    *,
    fetch_fn=fetch_ohlc,
) -> dict:
    """Fetch every symbol x interval in the basket into `out_dir/{symbol}/{interval}.parquet`, then
    write the manifest keyed by those relative paths to `out_dir/manifest.json` and return it."""
    series: dict[str, dict] = {}
    for symbol, pair_key in pair_keys.items():
        for interval in intervals:
            frame = to_frame(fetch_fn(pair_key, interval))
            relpath = f"{symbol}/{interval}.parquet"
            write_parquet(frame, out_dir / relpath)
            series[relpath] = series_entry(frame, relpath)
    manifest = build_manifest(series, written_at=fetched_at, provenance={"fetched_at": fetched_at})
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
