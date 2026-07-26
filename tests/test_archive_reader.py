from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    segs = list(canonical_segments(pri, rec))
    assert len(segs) == 1  # the hour is substituted, never double-yielded
    got = {h: p for _, h, p in segs}
    assert got[H].is_relative_to(rec)  # reconciled-first


def test_a_reconciled_only_hour_absent_from_the_primary_is_yielded(tmp_path):
    # A wholly-missing primary hour, healed from the secondary: it exists ONLY in the overlay.
    pri = tmp_path / "raw"
    rec = tmp_path / "overlay"
    pri.mkdir()
    _final(rec, "BTC/EUR", "book", H)
    segs = list(canonical_segments(pri, rec))
    assert [(pair, h) for pair, h, _ in segs] == [("BTC/EUR", H)]
    assert segs[0][2].is_relative_to(rec)


def test_an_overlay_only_hour_between_raw_hours_is_yielded_in_hour_order(tmp_path):
    # Consumers concatenate hours in yield order and may NEVER re-sort rows by ts (L2 rows carry
    # absolute quantities), so a healed hour appended after later raw hours would splice a different
    # book. The contract: yields are sorted by (pair, hour), overlay-only hours included.
    pri = tmp_path / "raw"
    rec = tmp_path / "overlay"
    _final(pri, "BTC/EUR", "book", H - timedelta(hours=1))  # 08 raw
    _final(rec, "BTC/EUR", "book", H)  # 09 healed, absent from the primary
    _final(pri, "BTC/EUR", "book", H + timedelta(hours=1))  # 10 raw
    hours = [h for _, h, _ in canonical_segments(pri, rec)]
    assert hours == [H - timedelta(hours=1), H, H + timedelta(hours=1)]


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


def test_two_quote_dirs_under_one_base_stay_independent_streams(tmp_path):
    """`ETH/EUR` and `ETH/BTC` must resolve as two separate pairs, never merged by base (T0092).

    Until 2026-07-23 capture was EUR-only, so every base directory happened to hold exactly one
    quote subdirectory. That was an observation, not a guarantee, and nothing in the suite pinned
    it. `canonical_segments` keys on `BASE/QUOTE` by construction; this test makes a future
    refactor back to base-keying fail loudly instead of silently merging two books.
    """
    primary = tmp_path / "primary"
    _final(primary, "ETH/EUR", "book", H)
    _final(primary, "ETH/BTC", "book", H)
    _final(primary, "ETH/EUR", "book", H + timedelta(hours=1))

    segments = list(canonical_segments(primary, None, kind="book"))
    pairs = sorted({seg_pair for seg_pair, _, _ in segments})

    assert pairs == ["ETH/BTC", "ETH/EUR"], pairs
    assert len(segments) == 3
    # each pair's hours are its own -- the BTC leg must not inherit the EUR leg's second hour
    by_pair = {p: sorted(h for sp, h, _ in segments if sp == p) for p in pairs}
    assert by_pair["ETH/BTC"] == [H]
    assert by_pair["ETH/EUR"] == [H, H + timedelta(hours=1)]
