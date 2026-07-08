from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import polars as pl

from cli.capture.errors import CaptureError
from cli.logging import get_logger

logger = get_logger("capture.segment_writer")

# One row per book-update price-level change (snapshot rows use type="snapshot").
BOOK_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "type": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "checksum": pl.Int64,
}

# One row per trade print.
TRADE_SCHEMA: dict[str, pl.DataType] = {
    "ts": pl.Datetime("us", "UTC"),
    "symbol": pl.Utf8,
    "side": pl.Utf8,
    "price": pl.Float64,
    "qty": pl.Float64,
    "ord_type": pl.Utf8,
    "trade_id": pl.Int64,
}

DEFAULT_FLUSH_ROWS = 5_000


def _hour_start(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


class SegmentWriter:
    """Buffers `(pair, kind)` capture events and streams them to hourly zstd-Parquet segments.

    Events are appended to a small in-memory buffer and flushed to a numbered "part" file once
    the buffer reaches `flush_rows` — the writer never holds more than that many rows in RAM at
    once, regardless of how much traffic an hour sees. At the hour boundary (detected from each
    event's own `ts`, not wall-clock) or on `close()`, the closing hour's part files are streamed
    (`scan_parquet` -> `sink_parquet`, not loaded whole) into the final `<HH>.parquet`, the parts
    are removed, and a sidecar `<file>.sha256` manifest is written.

    Segment layout: `<base_dir>/<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet`.
    """

    def __init__(
        self,
        base_dir: Path,
        pair: str,
        kind: str,
        schema: dict[str, pl.DataType],
        *,
        flush_rows: int = DEFAULT_FLUSH_ROWS,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._pair = pair
        self._kind = kind
        self._schema = schema
        self._flush_rows = flush_rows
        self._buffer: list[dict] = []
        self._current_hour: datetime | None = None
        self._part_paths: list[Path] = []
        self._part_seq = 0

    def append(self, event: dict) -> None:
        """Append one event dict (keys matching `schema`). Rotates the previous hour's segment
        first if `event["ts"]` has crossed into a new hour."""
        hour = _hour_start(event["ts"])
        if self._current_hour is not None and hour != self._current_hour:
            self._finalize_hour(self._current_hour)
        self._current_hour = hour
        self._buffer.append(event)
        if len(self._buffer) >= self._flush_rows:
            self._flush_buffer()

    def close(self) -> None:
        """Finalize whatever hour is currently open (idempotent; a no-op if nothing was written)."""
        if self._current_hour is not None:
            self._finalize_hour(self._current_hour)
            self._current_hour = None

    def _hour_dir(self, hour: datetime) -> Path:
        return self._base_dir / self._pair / self._kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        assert self._current_hour is not None
        df = pl.DataFrame(self._buffer, schema=self._schema)
        hour_dir = self._hour_dir(self._current_hour)
        hour_dir.mkdir(parents=True, exist_ok=True)
        part_path = hour_dir / f"{self._current_hour:%H}.part{self._part_seq:04d}.parquet"
        df.write_parquet(part_path, compression="zstd")
        self._part_paths.append(part_path)
        self._part_seq += 1
        self._buffer = []

    def _finalize_hour(self, hour: datetime) -> None:
        self._flush_buffer()
        self._part_seq = 0
        if not self._part_paths:
            return
        final_path = self._hour_dir(hour) / f"{hour:%H}.parquet"
        parts, self._part_paths = self._part_paths, []
        if len(parts) == 1:
            parts[0].rename(final_path)
        else:
            pl.scan_parquet(parts).sink_parquet(final_path, compression="zstd")
            for part in parts:
                part.unlink()
        self._write_manifest(final_path)
        logger.info("segment written pair=%s kind=%s path=%s", self._pair, self._kind, final_path)

    def _write_manifest(self, path: Path) -> None:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest_path = path.with_name(path.name + ".sha256")
        manifest_path.write_text(f"{digest}  {path.name}\n")

    def __enter__(self) -> SegmentWriter:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def verify_manifest(path: Path) -> bool:
    """Recompute `path`'s sha256 and compare it against its `<path>.sha256` sidecar."""
    manifest_path = path.with_name(path.name + ".sha256")
    if not manifest_path.exists():
        raise CaptureError(f"no manifest for {path}")
    recorded = manifest_path.read_text().split()[0]
    return hashlib.sha256(path.read_bytes()).hexdigest() == recorded
