from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from cli.archive.reconcile import (
    Gap,
    _inside,
    _message_ts,
    find_book_gaps,
    measure_residual,
    secondary_covers,
    splice_book,
    union_trades,
)
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA

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


# --- multi-gap splice: row conservation (adversarial review, spec 00050) ------------------------


def _row_conservation_holds(primary: pl.DataFrame, secondary: pl.DataFrame, gaps: list[Gap], blocks: list) -> bool:
    """sum(block heights) == (primary rows outside every gap) + (secondary rows inside any gap).

    Generic pin for `splice_book`: however many blocks it emits, no row may be dropped OR duplicated.
    """
    if not gaps:
        return sum(b.frame.height for b in blocks) == primary.height
    inside_any = pl.any_horizontal([_inside(g) for g in gaps])
    primary_outside = primary.filter(~inside_any).height
    secondary_inside = secondary.filter(inside_any).height
    return sum(b.frame.height for b in blocks) == primary_outside + secondary_inside


def test_head_interior_tail_gaps_are_spliced_without_duplicating_any_row():
    # A regression here is exactly the one the adversarial review found: removing the per-gap
    # cursor re-filter in `splice_book` still passes every OTHER test in this file, because none of
    # them exercise 2+ gaps. With that mutation, the primary rows already emitted before an interior
    # gap get RE-emitted at the next gap's "before" filter (which recomputes from the start of the
    # hour, not from the cursor): rows (ts=600, 700) here would be duplicated, yielding primary row
    # order [600, 700, 600, 700, 1200, 1300] instead of [600, 700, 1200, 1300].
    primary = _book([(600, "update"), (700, "update"), (1200, "update"), (1300, "update")])
    secondary = _book([(100, "update"), (300, "update"), (900, "update"), (2000, "update"), (3000, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in gaps] == [
        (H, H + timedelta(seconds=600)),
        (H + timedelta(seconds=700), H + timedelta(seconds=1200)),
        (H + timedelta(seconds=1300), HOUR_END),
    ]

    blocks = splice_book(primary, secondary, gaps)
    primary_ts = [t for b in blocks if b.source == "primary" for t in b.frame["ts"].to_list()]
    secondary_ts = [t for b in blocks if b.source == "secondary" for t in b.frame["ts"].to_list()]
    assert primary_ts == [H + timedelta(seconds=o) for o in (600, 700, 1200, 1300)]
    assert secondary_ts == [H + timedelta(seconds=o) for o in (100, 300, 900, 2000, 3000)]
    assert _row_conservation_holds(primary, secondary, gaps, blocks)


def test_two_adjacent_gaps_sharing_one_primary_message_keep_it_exactly_once():
    # An isolated primary message (silence on BOTH sides) is simultaneously the end of one gap and
    # the start of the next -- the two gaps share it as their common boundary. It must land in
    # exactly one block, with both its level-rows together: never split, never duplicated.
    primary = pl.concat(
        [
            _book([(0, "update"), (5, "update")]),  # a busy early block, no gap here
            _book([(1800, "update"), (1800, "update")]),  # the isolated shared message, 2 level-rows
            _book([(3500, "update"), (3505, "update")]),  # a busy late block, no gap here
        ]
    )
    secondary = _book([(900, "update"), (2500, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert [(g.start, g.end) for g in gaps] == [
        (H + timedelta(seconds=5), H + timedelta(seconds=1800)),
        (H + timedelta(seconds=1800), H + timedelta(seconds=3500)),
    ]

    blocks = splice_book(primary, secondary, gaps)
    primary_blocks = [b for b in blocks if b.source == "primary"]
    shared = [b for b in primary_blocks if b.frame["ts"].to_list() == [H + timedelta(seconds=1800)] * 2]
    assert len(shared) == 1  # the shared message appears in exactly one block, both rows together
    primary_ts = [t for b in primary_blocks for t in b.frame["ts"].to_list()]
    assert primary_ts == [H + timedelta(seconds=o) for o in (0, 5, 1800, 1800, 3500, 3505)]
    assert _row_conservation_holds(primary, secondary, gaps, blocks)


# --- the hour bounds are required, and `ts` monotonicity is asserted ----------------------------


def test_the_hour_bounds_are_required_not_optional():
    # A detector whose false negative is permanent loss must not let a caller silently opt out of
    # the two windows that catch a crash: omitting the bounds is a TypeError, not crash-blindness.
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (60, "update"), (120, "update")])
    with pytest.raises(TypeError):
        find_book_gaps(primary, secondary, min_gap_seconds=30)  # type: ignore[call-arg]


def test_hour_start_must_be_tz_aware():
    naive_start = datetime(2026, 7, 16, 9)
    primary = _book([(0, "update")])
    secondary = _book([(0, "update")])
    with pytest.raises(CaptureError, match="tz-aware"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=naive_start, hour_end=naive_start + timedelta(hours=1))


def test_hour_start_must_be_aligned_to_an_hour_boundary():
    misaligned = H + timedelta(minutes=1)
    primary = _book([(0, "update")])
    secondary = _book([(0, "update")])
    with pytest.raises(CaptureError, match="hour boundary"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=misaligned, hour_end=misaligned + timedelta(hours=1))


def test_hour_end_must_be_exactly_one_hour_after_hour_start():
    primary = _book([(0, "update")])
    secondary = _book([(0, "update")])
    with pytest.raises(CaptureError, match="hour_end"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END - timedelta(seconds=1))
    with pytest.raises(CaptureError, match="hour_end"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END + timedelta(seconds=1))


def test_a_too_early_hour_end_is_rejected_instead_of_silently_truncating_a_real_gap():
    # Pre-fix repro (adversarial review): a genuine crash at 09:56:40 UTC (3400s into the hour)
    # leaves a real 200s tail gap [09:56:40, 10:00:00). An `hour_end` 100s too early used to report
    # only the first 100s of it -- the remaining 100s of real, secondary-witnessed loss vanished
    # silently: not in any Gap, not ledgered, not spliced. The fix refuses the call outright.
    primary = _book([(0, "update"), (3400, "update")])
    secondary = _book([(0, "update"), (3400, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)
    assert len(gaps) == 1
    assert gaps[0].seconds == pytest.approx(200.0)

    wrong_hour_end = HOUR_END - timedelta(seconds=100)
    with pytest.raises(CaptureError, match="hour_end"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=wrong_hour_end)


def test_a_primary_row_outside_the_hour_window_is_rejected():
    primary = _book([(-5, "update")])  # a stray row from the previous hour
    secondary = _book([(0, "update")])
    with pytest.raises(CaptureError, match="primary row"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)


def test_a_secondary_row_outside_the_hour_window_is_rejected():
    # e.g. a stray row that leaked in from the NEXT hour -- a too-large `hour_end` would otherwise
    # splice it into this hour's output.
    primary = _book([(0, "update")])
    secondary = _book([(3600, "update")])  # exactly at hour_end -- outside the exclusive [start, end)
    with pytest.raises(CaptureError, match="secondary row"):
        find_book_gaps(primary, secondary, min_gap_seconds=30, hour_start=H, hour_end=HOUR_END)


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


def test_a_repeated_ts_reappearing_after_a_newer_one_raises_even_though_dedup_would_hide_it():
    # Raw order [0, 5, 0]: the exact-duplicate stamp 0 reappears AFTER a strictly newer 5.
    # Dedup-then-check (unique(maintain_order=True), THEN check the deduped list) can't see this --
    # it collapses to [0, 5], which looks monotone. The guard must inspect RAW row order.
    frame = _book([(0, "update"), (5, "update"), (0, "update")])
    with pytest.raises(CaptureError, match="non-monotonic ts in the BTC/EUR book stream"):
        _message_ts(frame)


# --- trade union: row-level, trade_id-keyed, primary priority (spec 00050 constraint 2) ---------


def _trades(ids: list[int], *, offset: int = 0) -> pl.DataFrame:
    # `trade_id` is `int` here, not `str`: `TRADE_SCHEMA` (cli/capture/segment_writer.py) declares it
    # `pl.Int64`, and the capture writer stores `int(trade["trade_id"])` — matching production dtype
    # matters because a string column would sort LEXICOGRAPHICALLY ("10" < "9"), silently breaking
    # the union's claimed chronological order.
    return pl.DataFrame(
        {
            "ts": [H + timedelta(seconds=i + offset) for i in ids],
            "symbol": ["BTC/EUR"] * len(ids),
            "side": ["buy"] * len(ids),
            "price": [1.0] * len(ids),
            "qty": [1.0] * len(ids),
            "trade_id": ids,
        }
    )


def test_primary_deficit_is_healed_from_the_secondary_ordered_by_trade_id():
    u = union_trades(_trades([1, 2, 5]), _trades([1, 2, 3, 4, 5]))
    assert u.added_from_secondary == 2
    assert u.frame["trade_id"].to_list() == [1, 2, 3, 4, 5]
    assert u.deduped_rows == 0


def test_no_deficit_is_a_no_op():
    u = union_trades(_trades([1, 2, 3]), _trades([1, 2, 3]))
    assert u.added_from_secondary == 0


def test_a_secondary_only_deficit_is_a_qa_signal_not_a_mint():
    u = union_trades(_trades([1, 2, 3]), _trades([1, 2]))
    assert u.added_from_secondary == 0
    assert u.secondary_deficit == 1


def test_intra_stream_duplicate_ids_are_deduped_with_a_count_primary_wins():
    # a pre-T0037 archive hour (T0026 reconnect replay) genuinely contains duplicate trade_ids
    primary = pl.concat([_trades([1, 2]), _trades([2])])  # id 2 twice
    u = union_trades(primary, _trades([1, 2, 3]))
    assert u.frame["trade_id"].to_list() == [1, 2, 3]
    assert u.deduped_rows == 1
    assert u.added_from_secondary == 1


def test_union_is_idempotent():
    once = union_trades(_trades([1, 2]), _trades([1, 2, 3]))
    twice = union_trades(once.frame, _trades([1, 2, 3]))
    assert twice.added_from_secondary == 0
    assert twice.frame["trade_id"].to_list() == once.frame["trade_id"].to_list()


# --- T0103: measure the OUTPUT, not the input ----------------------------------------------------
#
# `healed_seconds` recorded the full WIDTH of a primary-silence window on the strength of one
# secondary `update` row anywhere inside it, and `residual_seconds` on a minted record was the
# literal 0.0. Measured on the real 2026-07-27 07:00 hour: 2,311.536587 s booked healed against
# 82.955463 s actually filled -- 3.59% -- while the same hour separately recorded 2,385.847992 s of
# both_streams_silent, so 2,187.027326 stream-seconds sat in BOTH a "we covered it" counter and a
# "nobody covered it" counter in one cycle.
#
# `measure_residual` re-runs the window arithmetic over the SPLICED result, so what is reported is
# what the mint actually inserted.


def _rows(pair: str, stamps: list[tuple[datetime, str]]) -> pl.DataFrame:
    return pl.DataFrame(
        [{"ts": ts, "symbol": pair, "type": kind, "side": "bid", "price": 100.0, "qty": 1.0, "checksum": 1} for ts, kind in stamps],
        schema=BOOK_SCHEMA,
    )


def test_measure_residual_reports_what_the_splice_did_not_fill():
    """The production shape: one secondary update inside a wide gap heals an instant, not the gap."""
    h0 = datetime(2026, 7, 27, 7, tzinfo=UTC)
    gap = Gap(start=h0, end=h0 + timedelta(seconds=200), seconds=200.0, start_is_primary_message=False, end_is_primary_message=True)
    # The secondary contributes a single update 190 s in -- the tail of an outage it also suffered.
    spliced = _rows("BTC/EUR", [(h0 + timedelta(seconds=190), "update")])

    residual = measure_residual([gap], spliced, min_gap_seconds=30.0)
    total = sum(g.seconds for g in residual)
    assert total == pytest.approx(190.0), f"residual {total}s: the 190 s before the witness is still missing"
    healed = gap.seconds - total
    assert healed == pytest.approx(10.0), "only the 10 s after the witness was actually covered"


def test_measure_residual_is_empty_when_the_splice_genuinely_filled_the_gap():
    """The 2026-07-17 drill shape: a live secondary really does cover the window, and must not be
    slandered by a stricter measure -- 99.84% of that event was genuinely healed."""
    h0 = datetime(2026, 7, 27, 7, tzinfo=UTC)
    gap = Gap(start=h0, end=h0 + timedelta(seconds=100), seconds=100.0, start_is_primary_message=False, end_is_primary_message=True)
    spliced = _rows("BTC/EUR", [(h0 + timedelta(seconds=s), "update") for s in range(0, 101, 10)])

    assert measure_residual([gap], spliced, min_gap_seconds=30.0) == []


def test_measure_residual_ignores_sub_threshold_holes():
    """Consistency with the detector: a hole below `min_gap_seconds` is not a gap on the way in, so
    it must not become residual on the way out."""
    h0 = datetime(2026, 7, 27, 7, tzinfo=UTC)
    gap = Gap(start=h0, end=h0 + timedelta(seconds=100), seconds=100.0, start_is_primary_message=False, end_is_primary_message=True)
    spliced = _rows("BTC/EUR", [(h0 + timedelta(seconds=s), "update") for s in (0, 20, 45, 70, 100)])

    assert measure_residual([gap], spliced, min_gap_seconds=30.0) == []


def test_measure_residual_counts_a_wholly_unfilled_gap_in_full():
    """The ADA/EUR shape: the secondary held only snapshot rows at one instant, so nothing witnessed
    the gap and nothing was spliced. The whole window is residual -- it must not vanish."""
    h0 = datetime(2026, 7, 27, 7, tzinfo=UTC)
    gap = Gap(start=h0, end=h0 + timedelta(seconds=208), seconds=208.0, start_is_primary_message=False, end_is_primary_message=True)

    residual = measure_residual([gap], pl.DataFrame(schema=BOOK_SCHEMA), min_gap_seconds=30.0)
    assert sum(g.seconds for g in residual) == pytest.approx(208.0)


def test_measure_residual_never_exceeds_the_gap_it_measures():
    """The invariant that makes healed+residual a partition rather than double counting: residual is
    bounded by the window, so `healed = width - residual` can never be negative."""
    h0 = datetime(2026, 7, 27, 7, tzinfo=UTC)
    gaps = [
        Gap(start=h0, end=h0 + timedelta(seconds=200), seconds=200.0, start_is_primary_message=False, end_is_primary_message=True),
        Gap(
            start=h0 + timedelta(seconds=400),
            end=h0 + timedelta(seconds=500),
            seconds=100.0,
            start_is_primary_message=True,
            end_is_primary_message=True,
        ),
    ]
    spliced = _rows("BTC/EUR", [(h0 + timedelta(seconds=450), "update")])
    residual = measure_residual(gaps, spliced, min_gap_seconds=30.0)
    for g in gaps:
        covered = sum(r.seconds for r in residual if r.start >= g.start and r.end <= g.end)
        assert covered <= g.seconds + 1e-9, f"residual {covered}s exceeds its own {g.seconds}s window"
