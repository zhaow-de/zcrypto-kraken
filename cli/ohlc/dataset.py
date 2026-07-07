from __future__ import annotations

import hashlib
from pathlib import Path

import polars as pl

from cli.ohlc.errors import OHLCError

_RAW_COLUMNS = ["ts", "open", "high", "low", "close", "vwap", "volume", "count"]
_FLOAT_COLUMNS = ["open", "high", "low", "close", "vwap", "volume"]


def to_frame(rows: list[list]) -> pl.DataFrame:
    """Parse Kraken OHLC candle rows into a canonical, typed, sorted, de-duplicated frame.

    Schema: `ts` (`Datetime("us", "UTC")`, from the epoch-seconds col 0), `open/high/low/close/vwap/volume`
    (`Float64`, parsed from Kraken's string decimals), `count` (`Int64`). Exact-duplicate rows (e.g. from
    an overlapping refetch) are dropped. Raises `OHLCError` on an unparseable value (a non-numeric string
    in a price/count column), a NaN value, or on a non-monotonic/duplicate `ts` still remaining after
    de-duplication (two rows sharing a `ts` with differing data — an unresolvable conflict, not a true
    duplicate).
    """
    raw = pl.DataFrame(rows, schema=_RAW_COLUMNS, orient="row")
    try:
        frame = raw.with_columns(
            pl.from_epoch(pl.col("ts"), time_unit="s").dt.replace_time_zone("UTC"),
            pl.col(*_FLOAT_COLUMNS).cast(pl.Float64),
            pl.col("count").cast(pl.Int64),
        )
    except pl.exceptions.InvalidOperationError as exc:
        raise OHLCError(f"OHLC frame has an unparseable value: {exc}") from exc

    if frame.select(pl.any_horizontal(pl.col(_FLOAT_COLUMNS).is_nan())).to_series().any():
        raise OHLCError("OHLC frame contains NaN values")

    frame = frame.sort("ts").unique(maintain_order=True)

    if not frame["ts"].is_sorted() or frame["ts"].n_unique() != frame.height:
        raise OHLCError("OHLC frame has non-monotonic or conflicting-duplicate timestamps")

    return frame


def write_parquet(frame: pl.DataFrame, path: Path) -> None:
    """Write `frame` to `path` as Parquet, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def read_parquet(path: Path) -> pl.DataFrame:
    """Read a Parquet file written by `write_parquet` back into a frame."""
    return pl.read_parquet(path)


def dataset_hash(frame: pl.DataFrame) -> str:
    """Deterministic sha256 over `frame`'s canonical CSV serialization.

    Datasets are referenced by this hash (never "latest"), so it must be stable for identical data
    and change whenever any value does.
    """
    return hashlib.sha256(frame.write_csv().encode("utf-8")).hexdigest()
