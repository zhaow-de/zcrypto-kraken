from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.archive.reconcile import Gap, _message_ts, find_book_gaps, secondary_covers, splice_book
from cli.capture.errors import CaptureError

H = datetime(2026, 7, 16, 9, tzinfo=UTC)
HOUR_END = H + timedelta(hours=1)


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
    assert find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []


def test_primary_silence_with_secondary_updates_inside_is_a_gap():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1
    assert gaps[0].start == H
    assert gaps[0].end == H + timedelta(seconds=120)
    assert gaps[0].seconds == pytest.approx(120.0)


def test_a_secondary_resubscribe_snapshot_alone_never_fabricates_a_gap():
    # THE pinned spec case: a snapshot is full state, not market activity. If the only secondary
    # rows inside the window are snapshot rows, nothing was lost -> no gap, no heal.
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (60, "snapshot"), (120, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []


def test_silence_below_the_threshold_is_not_a_gap():
    primary = _book([(0, "update"), (20, "update")])
    secondary = _book([(0, "update"), (10, "update"), (20, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []


def test_multiple_gaps_in_one_hour_are_all_found():
    primary = _book([(0, "update"), (100, "update"), (200, "update"), (400, "update")])
    secondary = _book(
        [(0, "update"), (50, "update"), (100, "update"), (150, "update"), (200, "update"), (300, "update"), (400, "update")]
    )
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in gaps] == [
        (H, H + timedelta(seconds=100)),
        (H + timedelta(seconds=100), H + timedelta(seconds=200)),
        (H + timedelta(seconds=200), H + timedelta(seconds=400)),
    ]


def test_an_empty_primary_hour_is_one_whole_hour_gap():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1


def test_secondary_covers_requires_an_update_row_strictly_inside():
    gap = Gap(
        start=H,
        end=H + timedelta(seconds=120),
        seconds=120.0,
        start_is_primary_message=True,
        end_is_primary_message=True,
    )
    assert secondary_covers(_book([(60, "update")]), gap) is True
    assert secondary_covers(_book([(60, "snapshot")]), gap) is False
    assert secondary_covers(_book([]), gap) is False
    # boundary rows are NOT inside (strict inequalities keep same-ts wire messages intact)
    assert secondary_covers(_book([(0, "update"), (120, "update")]), gap) is False


def test_secondary_covers_is_inclusive_on_a_boundary_that_is_not_a_primary_message():
    # C2: an hour-boundary / secondary-owned edge belongs to NOBODY. Excluding it would silently
    # drop the only witness there is, and with it every row of that message.
    gap = Gap(
        start=H,
        end=H + timedelta(seconds=120),
        seconds=120.0,
        start_is_primary_message=False,
        end_is_primary_message=False,
    )
    assert secondary_covers(_book([(0, "update")]), gap) is True
    assert secondary_covers(_book([(120, "update")]), gap) is True
    assert secondary_covers(_book([(0, "snapshot"), (120, "snapshot")]), gap) is False


def test_splice_orders_blocks_primary_secondary_primary_and_never_sorts():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["primary", "secondary", "primary"]
    out = pl.concat([b.frame for b in blocks])
    # every primary row survives, the secondary fills only the window, nothing is reordered
    assert out["ts"].to_list() == [H, H + timedelta(seconds=40), H + timedelta(seconds=80), H + timedelta(seconds=120)]


def test_a_shared_ts_wire_message_is_never_split_across_blocks():
    # two rows share ts=0 (one message, two levels). The primary block must keep BOTH.
    primary = pl.concat([_book([(0, "update"), (0, "update")]), _book([(120, "update")])])
    secondary = _book([(0, "update"), (60, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    blocks = splice_book(primary, secondary, gaps)
    assert blocks[0].frame.height == 2  # both level-rows of the ts=0 message
    assert blocks[1].source == "secondary"
    assert blocks[1].frame["ts"].to_list() == [H + timedelta(seconds=60)]


def test_a_missing_primary_hour_becomes_one_full_secondary_block():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["secondary"]
    assert blocks[0].frame.height == 2


# --- C1: silence before the first / after the last primary message ----------------------------


def test_a_crashed_primary_leaves_a_tail_gap():
    # THE crash shape: the primary records for 5 minutes, then dies. The rest of the hour is silent
    # -- there is no "next primary message" to pair with, so consecutive-pairing alone sees nothing.
    primary = _book([(0, "update"), (150, "update"), (300, "update")])
    secondary = _book([(0, "update"), (300, "update"), (900, "update"), (3500, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1
    assert gaps[0].start == H + timedelta(seconds=300)
    assert gaps[0].end == HOUR_END
    assert gaps[0].seconds == pytest.approx(3300.0)
    assert gaps[0].start_is_primary_message is True
    assert gaps[0].end_is_primary_message is False  # the hour boundary is nobody's message


def test_a_late_starting_primary_leaves_a_head_gap():
    primary = _book([(1800, "update"), (1900, "update")])
    secondary = _book([(0, "update"), (600, "update"), (1800, "update"), (1900, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1
    assert gaps[0].start == H
    assert gaps[0].end == H + timedelta(seconds=1800)
    assert gaps[0].start_is_primary_message is False
    assert gaps[0].end_is_primary_message is True


def test_a_single_message_hour_yields_both_a_head_and_a_tail_gap():
    primary = _book([(1800, "update")])
    secondary = _book([(600, "update"), (1800, "update"), (3000, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in gaps] == [
        (H, H + timedelta(seconds=1800)),
        (H + timedelta(seconds=1800), HOUR_END),
    ]
    assert [(g.start_is_primary_message, g.end_is_primary_message) for g in gaps] == [(False, True), (True, False)]


def test_a_head_or_tail_gap_still_needs_a_secondary_witness():
    # The primary crashed at 300 s -- but the secondary is just as silent afterwards, so nothing was
    # lost: a quiet market must never be "healed".
    primary = _book([(0, "update"), (300, "update")])
    secondary = _book([(0, "update"), (300, "update"), (3000, "snapshot")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []


def test_a_healthy_hour_has_no_head_or_tail_gap():
    # A healthy stream's file begins at :00:00.0x and ends just shy of the next hour: the head and
    # tail silences are real but far below the threshold, so probing the edges must not fire here.
    primary = _book([(0.03, "update"), (1800, "update"), (3599.97, "update")])
    secondary = _book([(0.02, "update"), (1800, "update"), (3599.98, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []


# --- C2: boundary ownership -- the splice must not drop the secondary's edge rows ---------------


def test_splicing_a_tail_gap_keeps_every_secondary_row_after_the_crash():
    primary = _book([(0, "update"), (300, "update")])
    secondary = _book([(0, "update"), (300, "update"), (900, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["primary", "secondary"]
    out = pl.concat([b.frame for b in blocks])
    assert out["ts"].to_list() == [
        H,
        H + timedelta(seconds=300),  # the primary owns its own last message
        H + timedelta(seconds=900),
        H + timedelta(seconds=3599),  # ... and the secondary's last row is NOT dropped
    ]


def test_splicing_a_head_gap_keeps_a_secondary_row_sitting_on_the_hour_boundary():
    # The hour boundary is not a primary message, so nothing owns it: a strict `>` there would
    # silently drop every row of the secondary's first message.
    primary = _book([(1800, "update"), (1900, "update")])
    secondary = _book([(0, "update"), (600, "update"), (1800, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["secondary", "primary"]
    out = pl.concat([b.frame for b in blocks])
    assert out["ts"].to_list() == [
        H,  # exactly on the hour boundary -- kept
        H + timedelta(seconds=600),
        H + timedelta(seconds=1800),  # the primary's own first message, from the primary block
        H + timedelta(seconds=1900),
    ]


def test_an_absent_primary_hour_with_bounds_yields_every_secondary_row():
    primary = _book([])
    secondary = _book([(0, "update"), (1800, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in gaps] == [(H, HOUR_END)]
    assert (gaps[0].start_is_primary_message, gaps[0].end_is_primary_message) == (False, False)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["secondary"]
    assert blocks[0].frame.height == 3  # including the row on the hour boundary itself


# --- the hour bounds are required, and `ts` monotonicity is asserted ----------------------------


def test_the_hour_bounds_are_required_not_optional():
    # A detector whose false negative is permanent loss must not let a caller silently opt out of
    # the two windows that catch a crash: omitting the bounds is a TypeError, not crash-blindness.
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (60, "update"), (120, "update")])
    with pytest.raises(TypeError):
        find_book_gaps(primary, secondary, min_gap_seconds=30)  # type: ignore[call-arg]


def test_silence_exactly_at_the_threshold_is_not_a_gap():
    # The spec's rule is silence STRICTLY GREATER than the threshold.
    secondary = _book([(0, "update"), (15, "update"), (30, "update")])
    at = _book([(0, "update"), (30, "update")])
    assert find_book_gaps(at, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END) == []
    over = _book([(0, "update"), (30.001, "update")])
    gaps = find_book_gaps(over, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1
    assert gaps[0].seconds == pytest.approx(30.001)


def test_message_ts_collapses_the_level_rows_of_one_wire_message():
    # One Kraken message carries many book levels: many ROWS, one `ts`. Gap detection counts
    # messages, not rows -- three levels of one message are not three messages.
    frame = _book([(0, "update"), (0, "update"), (0, "update"), (120, "update"), (120, "update")])
    assert _message_ts(frame) == [H, H + timedelta(seconds=120)]


def test_out_of_order_timestamps_raise_instead_of_corrupting_silently():
    # Untreated, out-of-order input fabricates one wide window that SWALLOWS the interleaved message
    # (here the one at 100 s) and the splice drops its rows -- silent, permanent corruption. Sorting
    # is forbidden (L2 rows carry absolute quantities), so the only honest response is to refuse.
    # Kraken's `ts` is non-decreasing across every production row measured (T0037): this never fires.
    primary = _book([(100, "update"), (0, "update"), (200, "update")])
    secondary = _book([(50, "update"), (150, "update")])
    with pytest.raises(CaptureError, match="non-monotonic ts in the BTC/EUR book stream"):
        _message_ts(primary)
    with pytest.raises(CaptureError, match="non-monotonic"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
