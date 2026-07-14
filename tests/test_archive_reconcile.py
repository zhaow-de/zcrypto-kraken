from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.archive.reconcile import Gap, find_book_gaps, secondary_covers, splice_book

H = datetime(2026, 7, 16, 9, tzinfo=UTC)


def _book(rows: list[tuple[float, str]]) -> pl.DataFrame:
    """rows = [(offset_seconds, type)]; one wire message per row."""
    return pl.DataFrame(
        {
            "ts": [H + timedelta(seconds=o) for o, _ in rows],
            "symbol": ["BTC/EUR"] * len(rows),
            "type": [t for _, t in rows],
            "side": ["bid"] * len(rows),
            "price": [1.0] * len(rows),
            "qty": [1.0] * len(rows),
            "checksum": [0] * len(rows),
        }
    )


def test_a_quiet_primary_with_no_secondary_activity_is_not_a_gap():
    # 60 s of primary silence, but the secondary is equally quiet -> the market was quiet.
    primary = _book([(0, "update"), (60, "update")])
    secondary = _book([(0, "update"), (60, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []


def test_primary_silence_with_secondary_updates_inside_is_a_gap():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert len(gaps) == 1
    assert gaps[0].start == H
    assert gaps[0].end == H + timedelta(seconds=120)
    assert gaps[0].seconds == pytest.approx(120.0)


def test_a_secondary_resubscribe_snapshot_alone_never_fabricates_a_gap():
    # THE pinned spec case: a snapshot is full state, not market activity. If the only secondary
    # rows inside the window are snapshot rows, nothing was lost -> no gap, no heal.
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (60, "snapshot"), (120, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []


def test_silence_below_the_threshold_is_not_a_gap():
    primary = _book([(0, "update"), (20, "update")])
    secondary = _book([(0, "update"), (10, "update"), (20, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []


def test_multiple_gaps_in_one_hour_are_all_found():
    primary = _book([(0, "update"), (100, "update"), (200, "update"), (400, "update")])
    secondary = _book(
        [(0, "update"), (50, "update"), (100, "update"), (150, "update"), (200, "update"), (300, "update"), (400, "update")]
    )
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert [(g.start, g.end) for g in gaps] == [
        (H, H + timedelta(seconds=100)),
        (H + timedelta(seconds=100), H + timedelta(seconds=200)),
        (H + timedelta(seconds=200), H + timedelta(seconds=400)),
    ]


def test_an_empty_primary_hour_is_one_whole_hour_gap():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert len(gaps) == 1


def test_secondary_covers_requires_an_update_row_strictly_inside():
    gap = Gap(start=H, end=H + timedelta(seconds=120), seconds=120.0)
    assert secondary_covers(_book([(60, "update")]), gap) is True
    assert secondary_covers(_book([(60, "snapshot")]), gap) is False
    assert secondary_covers(_book([]), gap) is False
    # boundary rows are NOT inside (strict inequalities keep same-ts wire messages intact)
    assert secondary_covers(_book([(0, "update"), (120, "update")]), gap) is False


def test_splice_orders_blocks_primary_secondary_primary_and_never_sorts():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["primary", "secondary", "primary"]
    out = pl.concat([b.frame for b in blocks])
    # every primary row survives, the secondary fills only the window, nothing is reordered
    assert out["ts"].to_list() == [H, H + timedelta(seconds=40), H + timedelta(seconds=80), H + timedelta(seconds=120)]


def test_a_shared_ts_wire_message_is_never_split_across_blocks():
    # two rows share ts=0 (one message, two levels). The primary block must keep BOTH.
    primary = pl.concat([_book([(0, "update"), (0, "update")]), _book([(120, "update")])])
    secondary = _book([(0, "update"), (60, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert blocks[0].frame.height == 2  # both level-rows of the ts=0 message
    assert blocks[1].source == "secondary"
    assert blocks[1].frame["ts"].to_list() == [H + timedelta(seconds=60)]


def test_a_missing_primary_hour_becomes_one_full_secondary_block():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["secondary"]
    assert blocks[0].frame.height == 2
