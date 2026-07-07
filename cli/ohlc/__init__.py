from cli.ohlc.dataset import dataset_hash, read_parquet, to_frame, write_parquet
from cli.ohlc.errors import OHLCError
from cli.ohlc.fetch import fetch_ohlc
from cli.ohlc.ingest import ingest_basket
from cli.ohlc.qa import INTERVAL_SECONDS, detect_gaps, price_discontinuities, qa_dataset, qa_series, render_markdown, wick_outliers

# 1d / 4h / 1h — the §6 decision-cadence intervals (minutes).
DEFAULT_INTERVALS = [1440, 240, 60]

__all__ = [
    "fetch_ohlc",
    "to_frame",
    "write_parquet",
    "read_parquet",
    "dataset_hash",
    "ingest_basket",
    "DEFAULT_INTERVALS",
    "OHLCError",
    "INTERVAL_SECONDS",
    "detect_gaps",
    "wick_outliers",
    "price_discontinuities",
    "qa_series",
    "qa_dataset",
    "render_markdown",
]
