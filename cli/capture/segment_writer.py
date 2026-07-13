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


def _part_index(path: Path) -> int:
    """`"<HH>.part0007.parquet"` -> `7`. Numeric, so part9999 sorts before part10000."""
    return int(path.name.split(".part")[1].split(".")[0])


class SegmentWriter:
    """Buffers `(pair, kind)` capture events and streams them to hourly zstd-Parquet segments.

    Events are appended to a small in-memory buffer and flushed to a numbered "part" file once
    the buffer reaches `flush_rows` — the writer never holds more than that many rows in RAM at
    once, regardless of how much traffic an hour sees. At the hour boundary (detected from each
    event's own `ts`, not wall-clock) or on `close()`, the closing hour's part files are streamed
    (`scan_parquet` -> `sink_parquet`, not loaded whole) into the final `<HH>.parquet`, the parts
    are removed, and a sidecar `<file>.sha256` manifest is written.

    Restart-safe: the part sequence and the merge input list are derived from the hour directory
    on every use, never from process memory (which a restart resets), and construction sweeps any
    parts a previous process left behind. So an hour survives any number of restarts: its final
    segment is always a superset of every row ever flushed for it, and the manifest can therefore
    only ever bless a superset (see T0036).

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
        self._recover_stale_hours()

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

    def _parts_for(self, hour_dir: Path, hh: str) -> list[Path]:
        """Every part file on disk for `<HH>`, in ascending sequence order."""
        return sorted(hour_dir.glob(f"{hh}.part*.parquet"), key=_part_index)

    def _flush_buffer(self) -> None:
        if not self._buffer:
            return
        assert self._current_hour is not None
        hour_dir = self._hour_dir(self._current_hour)
        hour_dir.mkdir(parents=True, exist_ok=True)
        hh = f"{self._current_hour:%H}"
        # The next sequence number is read from disk, so a writer resuming a half-written hour
        # starts *past* the highest part already there and can never overwrite it.
        parts = self._parts_for(hour_dir, hh)
        seq = _part_index(parts[-1]) + 1 if parts else 0
        df = pl.DataFrame(self._buffer, schema=self._schema)
        df.write_parquet(hour_dir / f"{hh}.part{seq:04d}.parquet", compression="zstd")
        self._buffer = []

    def _finalize_hour(self, hour: datetime) -> None:
        self._flush_buffer()
        self._merge_hour(self._hour_dir(hour), f"{hour:%H}")

    def _merge_hour(self, hour_dir: Path, hh: str) -> None:
        """Merge every `<HH>.part*.parquet` on disk — plus any `<HH>.parquet` an earlier process
        already finalized, as the earliest input — into `<HH>.parquet`.

        Inputs come from the directory, not from instance state, so parts written by a previous
        process are merged rather than stranded, and an existing final segment is adopted rather
        than clobbered. Rows are concatenated in (existing-final, then part-sequence) order and
        are **never sorted**: L2 book deltas carry absolute quantities, so reordering rows that
        share a `ts` would silently corrupt the reconstructed book.
        """
        parts = self._parts_for(hour_dir, hh)
        if not parts:
            return
        final_path = hour_dir / f"{hh}.parquet"
        inputs = ([final_path] if final_path.exists() else []) + parts
        # Not `*.parquet`, so a tmp stranded by a crash is invisible to the archive's globs.
        tmp_path = hour_dir / f"{hh}.parquet.tmp"
        # An explicit per-file scan list: a multi-path `scan_parquet` may parallelize and does not
        # contractually preserve inter-file row order. `sink_parquet` still streams.
        pl.concat([pl.scan_parquet(p) for p in inputs], how="vertical").sink_parquet(tmp_path, compression="zstd")
        tmp_path.replace(final_path)  # atomic; final_path was itself a scan input
        for part in parts:
            part.unlink()
        self._write_manifest(final_path)
        logger.info("segment written pair=%s kind=%s path=%s", self._pair, self._kind, final_path)

    def _recover_stale_hours(self) -> None:
        """On construction, finalize every hour a previous process left behind as loose parts —
        including hours this writer will never open (a restart across an hour boundary)."""
        root = self._base_dir / self._pair / self._kind
        for hour_dir in sorted({p.parent for p in root.rglob("*.part*.parquet")}):
            for hh in sorted({p.name.split(".part")[0] for p in hour_dir.glob("*.part*.parquet")}):
                self._merge_hour(hour_dir, hh)

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
