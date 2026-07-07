from __future__ import annotations

import json
from pathlib import Path

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
    """Fetch, normalize, and write canonical Parquet for each symbol x interval in the basket.

    For each `display_symbol -> kraken_pair_key` in `pair_keys`, times each interval in `intervals`:
    fetch -> `to_frame` -> write `out_dir/{symbol}/{interval}.parquet`. Builds a manifest dict:
    `fetched_at` plus one `series` entry per symbol x interval (symbol, interval, rows, first_ts,
    last_ts, dataset_hash); writes it to `out_dir/manifest.json` and returns it. Deterministic given
    a fixed `fetched_at` and `fetch_fn`.
    """
    series = []
    for symbol, pair_key in pair_keys.items():
        for interval in intervals:
            frame = to_frame(fetch_fn(pair_key, interval))
            write_parquet(frame, out_dir / symbol / f"{interval}.parquet")
            series.append(
                {
                    "symbol": symbol,
                    "interval": interval,
                    "rows": frame.height,
                    "first_ts": frame["ts"].min().isoformat(),
                    "last_ts": frame["ts"].max().isoformat(),
                    "dataset_hash": dataset_hash(frame),
                }
            )
    manifest = {"fetched_at": fetched_at, "series": series}
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True))
    return manifest
