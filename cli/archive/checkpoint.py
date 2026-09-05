"""Checkpoint store for incremental verify-replay (spec 00078): one row per `(pair, hour)` last
verified, in `<state_dir>/checkpoint.parquet`, so a later sweep can skip an unchanged hour."""

from __future__ import annotations

import contextlib
import dataclasses
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

CHECKPOINT_SCHEMA_VERSION = 1

_FILENAME = "checkpoint.parquet"

# Every `CheckpointRow` field is pinned because, unpinned, `pl.DataFrame` infers a column's dtype from
# only the first `infer_schema_length` (default 100) rows: the nullable `error` is `None` through that
# window in a snapshot rewritten whole on every flush, and the first real error string past it raises
# `ComputeError` ("could not append value ... to the builder").
_ROW_SCHEMA = {
    "pair": pl.String,
    "hour": pl.Datetime("us", "UTC"),
    "byte_hash": pl.String,
    "verifier_version": pl.Int64,
    "opens_with_snapshot": pl.Boolean,
    "ts_ordered": pl.Boolean,
    "checksum_present": pl.Boolean,
    "replay_ok": pl.Boolean,
    "error": pl.String,
    "rows": pl.Int64,
    "messages": pl.Int64,
    "polars_version": pl.String,
    "depth": pl.Int64,
    "verified_at": pl.Datetime("us", "UTC"),
}


@dataclass(frozen=True)
class CheckpointRow:
    """One `(pair, hour)` verify-replay verdict, as last checkpointed."""

    pair: str
    hour: datetime  # tz-aware UTC
    byte_hash: str  # sha256 hex of the bytes replayed
    verifier_version: int
    opens_with_snapshot: bool
    ts_ordered: bool
    checksum_present: bool
    replay_ok: bool
    error: str | None
    rows: int
    messages: int
    polars_version: str  # recorded, NOT an invalidation key (D5)
    depth: int  # recorded, NOT an invalidation key (D5)
    verified_at: datetime


class CheckpointWriteError(Exception):
    """`save_checkpoint` could not create `state_dir` or publish the checkpoint into it."""


def _check_aware(row: CheckpointRow) -> None:
    """Refuse a naive `hour`/`verified_at`: `_ROW_SCHEMA` localizes a naive value to UTC on write, so
    a value off a non-UTC clock would be checkpointed silently under the wrong hour."""
    if row.hour.tzinfo is None:
        raise ValueError(f"CheckpointRow.hour is naive: {row.pair} {row.hour!r} — must be tz-aware UTC")
    if row.verified_at.tzinfo is None:
        raise ValueError(f"CheckpointRow.verified_at is naive: {row.pair} {row.verified_at!r} — must be tz-aware UTC")


def load_checkpoint(state_dir: Path) -> dict[tuple[str, datetime], CheckpointRow] | None:
    """Load the checkpoint at `state_dir/checkpoint.parquet`, keyed by `(pair, hour)`, never raising:
    an absent, unreadable, or wrong-`CHECKPOINT_SCHEMA_VERSION` file returns `None`."""
    path = state_dir / _FILENAME
    if not path.exists():
        return None
    try:
        frame = pl.read_parquet(path)
        if not (frame["schema_version"] == CHECKPOINT_SCHEMA_VERSION).all():
            return None
        fields = [f.name for f in dataclasses.fields(CheckpointRow)]
        return {
            (record["pair"], record["hour"]): CheckpointRow(**{name: record[name] for name in fields})
            for record in frame.iter_rows(named=True)
        }
    except Exception:
        return None


def save_checkpoint(state_dir: Path, rows: Iterable[CheckpointRow]) -> None:
    """Publish `rows` to `state_dir/checkpoint.parquet` atomically: a `.tmp` in the same directory,
    then `os.replace` (`mint.py`'s idiom), so a failed write never corrupts what was already
    published. An empty `rows` is a no-op — a zero-row file would shadow a good checkpoint — and every
    `OSError`, `state_dir`'s own creation included, is raised as `CheckpointWriteError`."""
    rows = list(rows)
    if not rows:
        return
    for row in rows:
        _check_aware(row)

    frame = pl.DataFrame([dataclasses.asdict(row) for row in rows], schema=_ROW_SCHEMA).with_columns(
        pl.lit(CHECKPOINT_SCHEMA_VERSION, dtype=pl.Int64).alias("schema_version")
    )
    tmp = state_dir / f"{_FILENAME}.tmp"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(tmp)
        os.replace(tmp, state_dir / _FILENAME)
    except OSError as exc:
        with contextlib.suppress(OSError):  # cleanup is best-effort — must never shadow `exc`
            tmp.unlink(missing_ok=True)
        raise CheckpointWriteError(f"failed to write checkpoint to {state_dir}: {exc}") from exc
