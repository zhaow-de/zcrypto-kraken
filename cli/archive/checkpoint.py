"""Checkpoint store for incremental verify-replay (spec 00078).

One row per `(pair, hour)` last verified, persisted to `<state_dir>/checkpoint.parquet` so a later
sweep can skip an unchanged hour instead of replaying it. Written atomically — temp file in the same
directory, then `os.replace` (`mint.py`'s idiom) — so a failed write can never corrupt a previously
published checkpoint. `load_checkpoint` never raises: absent, corrupt, and wrong-`schema_version` all
return `None`, and the caller (Task 4) announces the rebuild rather than crashing the nightly sweep.
"""

from __future__ import annotations

import dataclasses
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

CHECKPOINT_SCHEMA_VERSION = 1

_FILENAME = "checkpoint.parquet"


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


def load_checkpoint(state_dir: Path) -> dict[tuple[str, datetime], CheckpointRow] | None:
    """Load the checkpoint at `state_dir/checkpoint.parquet`, keyed by `(pair, hour)`.

    Never raises: an absent file, an unreadable one, or one written under a different
    `CHECKPOINT_SCHEMA_VERSION` all return `None` — the caller treats that as "no checkpoint" and
    rebuilds from scratch.
    """
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
    """Publish `rows` to `state_dir/checkpoint.parquet`, atomically.

    Writes `checkpoint.parquet.tmp` in `state_dir` and `os.replace`s it into place (`mint.py`'s
    idiom), so a failed write never corrupts a previously published checkpoint. Every OS/IO failure —
    including creating `state_dir` itself, e.g. a missing `:rw` mount — is wrapped in
    `CheckpointWriteError`, and any partial `.tmp` a failed write left behind is removed before that
    is raised.
    """
    frame = pl.DataFrame([dataclasses.asdict(row) for row in rows]).with_columns(
        pl.lit(CHECKPOINT_SCHEMA_VERSION).alias("schema_version")
    )
    tmp = state_dir / f"{_FILENAME}.tmp"
    try:
        state_dir.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(tmp)
        os.replace(tmp, state_dir / _FILENAME)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise CheckpointWriteError(f"failed to write checkpoint to {state_dir}: {exc}") from exc
