from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cli.archive.reader import canonical_segments
from cli.archive.settle import hour_path

H = datetime(2026, 7, 16, 9, tzinfo=UTC)


def _final(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    path = hour_path(root, pair, kind, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def _part(root: Path, pair: str, kind: str, hour: datetime, *, seq: int) -> Path:
    path = hour_path(root, pair, kind, hour).with_name(f"{hour:%H}.part{seq:04d}.parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def _held(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    path = hour_path(root, pair, kind, hour).with_name(f"{hour:%H}.held0000.parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_a_reconciled_hour_wins_over_the_raw_primary(tmp_path):
    pri = tmp_path / "raw"
    rec = tmp_path / "overlay"
    _final(pri, "BTC/EUR", "book", H)  # raw hour
    _final(rec, "BTC/EUR", "book", H)  # healed hour
    got = {h: p for _, h, p in canonical_segments(pri, rec)}
    assert got[H].is_relative_to(rec)  # reconciled-first


def test_raw_hours_with_no_overlay_still_resolve(tmp_path):
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    assert len(list(canonical_segments(pri, None))) == 1


def test_a_stale_part_file_is_never_yielded(tmp_path):
    # THE T0038 TRAP: a bare `**/*.parquet` glob matches 09.part0003.parquet and double-counts the hour.
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    _part(pri, "BTC/EUR", "book", H, seq=3)
    assert len(list(canonical_segments(pri, None))) == 1


def test_held_and_corrupt_files_are_never_yielded(tmp_path):
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    _held(pri, "BTC/EUR", "book", H)
    assert len(list(canonical_segments(pri, None))) == 1
