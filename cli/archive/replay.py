"""Canonical book continuity-replay (spec 00051 OPS-3).

Proves that the canonical archive — reconciled-first, primary otherwise (`canonical_segments`) —
**replays as a coherent book**, per hour: it opens with a snapshot, rows are non-decreasing in `ts`,
every message carries its capture-time `checksum` attestation, and the rows regroup into WS-shaped
messages that feed `OrderBook` without a structural throw. Its one genuinely new payoff over
manifests + continuity.py: it confirms the reconciler's spliced output stays snapshot-anchored and
coherent across splice boundaries.

Scope guard (finalized 2026-07-15, T0045): the archive stores `price`/`qty` as Float64, so Kraken's
CRC32 is NOT byte-exact re-derivable — a re-derived `OrderBook.checksum()` mismatches the stored
`checksum` column on every zero-trailing level, a guaranteed false alarm. The stored column is
therefore trusted as capture-time ground truth and never re-derived; the CRC-based return value of
`ingest_snapshot`/`ingest_update` is deliberately ignored. A "structural desync" heuristic is
likewise NOT implemented: for a depth-bounded book, a legitimate update to an out-of-window level is
indistinguishable from corruption without the CRC. The byte-exact CRC replay is deferred to T0045
(the raw-string schema change unblocks it).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from cli.archive.reader import canonical_segments
from cli.capture.book import OrderBook
from cli.logging import get_logger

logger = get_logger("archive.replay")


@dataclass(frozen=True)
class ReplayResult:
    """One canonical hour's replay verdict. `error` is set (never raised) for an unreadable segment
    or a structural ingest throw — one bad hour must not abort the sweep."""

    pair: str
    hour: datetime | None
    rows: int
    messages: int
    snapshot_anchored: bool
    ts_ordered: bool
    checksum_present: bool
    replay_ok: bool
    error: str | None

    @property
    def passed(self) -> bool:
        return self.error is None and self.snapshot_anchored and self.ts_ordered and self.checksum_present and self.replay_ok


def regroup_messages(frame: pl.DataFrame) -> list[dict]:
    """Rebuild the WS-shaped messages from the exploded per-level rows — the exact inverse of the
    capture writer's fan-out (cli/capture/command.py:146-158): consecutive rows sharing
    `(ts, symbol, type, checksum)` are one wire message, its levels rebuilt onto `bids`/`asks` by
    `side` in row order."""
    messages: list[dict] = []
    key: tuple | None = None
    for row in frame.iter_rows(named=True):
        row_key = (row["ts"], row["symbol"], row["type"], row["checksum"])
        if row_key != key:
            key = row_key
            messages.append(
                {
                    "ts": row["ts"],
                    "symbol": row["symbol"],
                    "type": row["type"],
                    "checksum": row["checksum"],
                    "bids": [],
                    "asks": [],
                }
            )
        side = "bids" if row["side"] == "bid" else "asks"
        messages[-1][side].append({"price": row["price"], "qty": row["qty"]})
    return messages


def _hour_from_path(path: Path) -> datetime | None:
    """The hour a canonical final's `<...>/<YYYY>/<MM>/<DD>/<HH>.parquet` path encodes."""
    parts = path.parts
    try:
        return datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(path.name[:2]), tzinfo=UTC)
    except ValueError, IndexError:
        return None


def replay_segment(path: Path, symbol: str, depth: int) -> ReplayResult:
    """Replay one canonical hour through a fresh `OrderBook(symbol, depth)`. Never raises: an
    unreadable segment or a structural ingest throw is isolated into the result (the same
    isolation contract as infra/scripts/gap_distribution.py::observe_gaps)."""
    hour = _hour_from_path(path)
    try:
        frame = pl.read_parquet(path)
        messages = regroup_messages(frame)
    except Exception as exc:  # noqa: BLE001 — an unreadable segment is a finding, not a crash
        return ReplayResult(symbol, hour, 0, 0, False, False, False, False, f"{type(exc).__name__}: {exc}")

    snapshot_anchored = bool(messages) and messages[0]["type"] == "snapshot"
    ts_ordered = bool(frame["ts"].is_sorted())  # non-strict: equal stamps are in order
    checksum_present = "checksum" in frame.columns and frame["checksum"].null_count() == 0

    book = OrderBook(symbol, depth)
    replay_ok, error = True, None
    try:
        for message in messages:
            # The CRC-based return value is deliberately ignored (T0045, module docstring): only a
            # structural throw fails the replay.
            if message["type"] == "snapshot":
                book.ingest_snapshot(message)
            else:
                book.ingest_update(message)
    except Exception as exc:  # noqa: BLE001 — a structural throw is exactly the finding this check exists for
        replay_ok, error = False, f"{type(exc).__name__}: {exc}"

    return ReplayResult(
        symbol, hour, frame.height, len(messages), snapshot_anchored, ts_ordered, checksum_present, replay_ok, error
    )


def verify_replay(
    primary_root: Path,
    reconciled_root: Path | None,
    *,
    pair: str | None = None,
    since: datetime | None = None,
    depth: int,
) -> list[ReplayResult]:
    """Continuity-replay every canonical book hour (reconciled-first, primary otherwise), one
    `ReplayResult` per hour in `(pair, hour)` order. Per-hour failures are isolated into
    `ReplayResult.error`; the sweep never aborts on one bad hour."""
    results: list[ReplayResult] = []
    for seg_pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="book"):
        if pair is not None and seg_pair != pair:
            continue
        if since is not None and hour < since:
            continue
        try:
            result = replay_segment(path, seg_pair, depth)
        except Exception as exc:  # noqa: BLE001 — belt and braces: one bad hour must not abort the sweep
            result = ReplayResult(seg_pair, hour, 0, 0, False, False, False, False, f"{type(exc).__name__}: {exc}")
        results.append(result)
    return results
