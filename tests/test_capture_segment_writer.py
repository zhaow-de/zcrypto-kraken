import os
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from cli.capture import segment_writer
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, SegmentWriter, verify_manifest


def _ts(hour: int, minute: int = 0, sec: int = 0) -> datetime:
    return datetime(2026, 7, 8, hour, minute, sec, tzinfo=timezone.utc)


def _book_event(hour: int, minute: int = 0, sec: int = 0, *, price: float = 100.0, checksum: int = 42) -> dict:
    return {
        "ts": _ts(hour, minute, sec),
        "symbol": "BTC/EUR",
        "type": "update",
        "side": "bid",
        "price": price,
        "qty": 1.0,
        "checksum": checksum,
    }


def _segment_path(base_dir, hour: int):
    return base_dir / "BTC/EUR" / "book" / "2026" / "07" / "08" / f"{hour:02d}.parquet"


def _corrupt_body(path: Path) -> None:
    """Destroy a parquet file's data pages while leaving its footer (and trailing magic) intact.

    The shape bit-rot — and a partially-written page — takes. A footer-only check (`collect_schema()`)
    passes such a file happily, which is why anything certifying a segment must read the rows.
    """
    raw = bytearray(path.read_bytes())
    body_end = len(raw) - 8 - int.from_bytes(raw[-8:-4], "little")  # trailing: <footer len><PAR1>
    for i in range(4, body_end):  # keep the leading PAR1 magic
        raw[i] ^= 0xA5
    path.write_bytes(bytes(raw))


class _Clock:
    """The writer's wall clock, pinned and advanceable — production has one, so the tests do too."""

    def __init__(self) -> None:
        self.now = _ts(14, 30)


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> _Clock:
    """Pin `_utcnow()`. The writer is clock-coupled in two places — construction finalizes only hours
    strictly BEFORE the current one (the hour in progress is left as parts for the restarted writer to
    resume), and `append()` refuses events from an hour that is already over or implausibly ahead — so
    a test that restarts across an hour boundary must move the clock the way real time would."""
    clk = _Clock()
    monkeypatch.setattr(segment_writer, "_utcnow", lambda: clk.now)
    return clk


def test_close_with_no_events_writes_nothing(tmp_path):
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.close()
    assert not any(tmp_path.rglob("*.parquet"))


def test_writes_single_segment_and_manifest_on_hour_rotation(tmp_path):
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(14, 0))
    writer.append(_book_event(14, 30))
    writer.append(_book_event(15, 0))  # crossing the boundary finalizes hour 14

    path = _segment_path(tmp_path, 14)
    assert path.exists()
    manifest = path.with_name(path.name + ".sha256")
    assert manifest.exists()
    assert verify_manifest(path) is True

    df = pl.read_parquet(path)
    assert df.height == 2
    assert dict(df.schema) == BOOK_SCHEMA


def test_rotates_segment_at_hour_boundary(tmp_path):
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(14, 0))
    writer.append(_book_event(14, 59))
    # Crossing into hour 15 must finalize hour 14's segment immediately, before hour 15 is closed.
    writer.append(_book_event(15, 0))

    hour14 = _segment_path(tmp_path, 14)
    assert hour14.exists()
    assert pl.read_parquet(hour14).height == 2

    hour15 = _segment_path(tmp_path, 15)
    assert not hour15.exists()  # not finalized yet — still open


def test_close_flushes_the_buffer_without_publishing_a_partial_segment(tmp_path, clock):
    # close() must not finalize: an hour cut short by a stop is not a whole hour, and a final that
    # can appear beside its own parts is exactly what makes crash recovery ambiguous (T0036).
    clock.now = _ts(15, 30)
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(15, 0))
    writer.close()

    hour15 = _segment_path(tmp_path, 15)
    assert not hour15.exists()
    assert [p.name for p in hour15.parent.glob("15.part*.parquet")] == ["15.part0000.parquet"]

    # The next process finishes the hour, since by then it is over.
    clock.now = _ts(16, 5)
    SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    assert pl.read_parquet(hour15).height == 1
    assert verify_manifest(hour15) is True


def test_flush_rows_bounds_buffer_and_merges_parts_into_one_segment(tmp_path):
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA, flush_rows=2)
    for i in range(5):
        writer.append(_book_event(14, i, price=100.0 + i))
        # The buffer never grows past flush_rows before being flushed to a part file.
        assert len(writer._buffer) <= 2
    writer.append(_book_event(15, 0))  # rotation flushes the tail and merges the hour

    path = _segment_path(tmp_path, 14)
    df = pl.read_parquet(path)
    assert df.height == 5
    assert sorted(df["price"].to_list()) == [100.0, 101.0, 102.0, 103.0, 104.0]
    # Part files were merged away — only the final segment + manifest remain.
    remaining = sorted(p.name for p in path.parent.iterdir())
    assert remaining == [path.name, path.name + ".sha256"]


def test_verify_manifest_detects_tampering(tmp_path):
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(14))
    writer.append(_book_event(15))

    path = _segment_path(tmp_path, 14)
    with path.open("ab") as f:
        f.write(b"corruption")
    assert verify_manifest(path) is False


def test_verify_manifest_raises_when_manifest_missing(tmp_path):
    path = tmp_path / "orphan.parquet"
    path.write_bytes(b"not-really-parquet")
    with pytest.raises(CaptureError):
        verify_manifest(path)


def test_context_manager_flushes_on_exit(tmp_path):
    with SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA) as writer:
        writer.append(_book_event(14))
    assert list(_segment_path(tmp_path, 14).parent.glob("14.part*.parquet"))


# --- restart / recovery regressions (T0036) --------------------------------------------------
#
# A "restart" is modelled exactly as production does it: a NEW SegmentWriter is constructed over
# the SAME base_dir/pair/kind. A hard crash = the previous writer is dropped without close().


def _hour10_event(i: int, checksum: int) -> dict:
    """The i-th second-granular slot of hour 10 (i in 0..3599), tagged with `checksum`."""
    return _book_event(10, i // 60, i % 60, checksum=checksum)


def _new_writer(tmp_path, flush_rows: int) -> SegmentWriter:
    return SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA, flush_rows=flush_rows)


@pytest.fixture
def clock_in_hour10(clock):
    """Put the wall clock inside hour 10 — the hour these tests are still capturing."""
    clock.now = _ts(10, 30)
    return clock


def test_hard_crash_restart_same_hour_keeps_every_flushed_row(tmp_path, clock_in_hour10):
    # Scenario A: writer #1 dies mid-hour; writer #2 finishes the hour.
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(61):  # checksums 0..60; 60 flushed into 12 parts, 1 left in the buffer
        w1.append(_hour10_event(i * 30, i))
    del w1  # hard crash — no close()

    w2 = _new_writer(tmp_path, flush_rows=5)
    for i in range(61, 120):  # checksums 1000..1058
        w2.append(_hour10_event(i * 30, 1000 + (i - 61)))
    w2.append(_book_event(11, 0))  # crossing the boundary finalizes hour 10

    path = _segment_path(tmp_path, 10)
    df = pl.read_parquet(path)
    # Only w1's single unflushed buffered row is lost; everything that reached disk survives.
    assert df.height == 119
    assert df["checksum"].to_list() == list(range(60)) + list(range(1000, 1059))
    assert df["ts"][0] == _ts(10, 0, 0)
    assert not list(path.parent.glob("*.part*.parquet"))
    assert verify_manifest(path) is True


@pytest.mark.parametrize("flush_rows", [100, 5000])
def test_restart_after_graceful_close_resumes_the_open_hour(tmp_path, clock_in_hour10, flush_rows):
    # Scenario B: writer #1 is stopped gracefully mid-hour. Its close() flushes every buffered row
    # to a part but must NOT publish the half-hour as a segment; writer #2 resumes the same hour.
    w1 = _new_writer(tmp_path, flush_rows)
    for i in range(300):
        w1.append(_hour10_event(i, i))
    w1.close()

    path = _segment_path(tmp_path, 10)
    assert not path.exists()  # a partial hour is never published as a whole segment

    w2 = _new_writer(tmp_path, flush_rows)
    for i in range(300, 3600):
        w2.append(_hour10_event(i, i))
    w2.append(_book_event(11, 0))

    df = pl.read_parquet(path)
    assert df.height == 3600  # nothing the stopped writer had flushed was lost
    assert df["checksum"].to_list() == list(range(3600))
    assert df["ts"][0] == _ts(10, 0, 0)
    assert df["ts"][-1] == _ts(10, 59, 59)
    assert verify_manifest(path) is True


def test_partial_final_from_an_old_writer_is_adopted_not_dropped(tmp_path, clock_in_hour10):
    # Migration: a pre-T0036 process published the open hour on close(), so the hour it was stopped
    # in already has a partial <HH>.parquet whose rows are in no part file. The new writer must fold
    # it back in — treating it as a committed final would drop everything captured after the deploy.
    hour_dir = _segment_path(tmp_path, 10).parent
    hour_dir.mkdir(parents=True)
    old = pl.DataFrame([_hour10_event(i, i) for i in range(10)], schema=BOOK_SCHEMA)
    old.write_parquet(hour_dir / "10.parquet", compression="zstd")
    (hour_dir / "10.parquet.sha256").write_text("stale-digest  10.parquet\n")

    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(10, 30):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))

    path = _segment_path(tmp_path, 10)
    df = pl.read_parquet(path)
    assert df["checksum"].to_list() == list(range(30))  # the pre-restart rows, then the new ones
    assert verify_manifest(path) is True


def test_late_event_for_a_closed_hour_never_reopens_it(tmp_path, clock_in_hour10):
    # A reconnect's trade snapshot replays prints from before the hour boundary (T0026). Rotating
    # backwards onto that closed hour would finalize the CURRENT hour early — and every row it then
    # captured would be dropped as "already merged". The hour is monotone: late rows are dropped.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(10):
        w.append(_hour10_event(i, i))
    clock_in_hour10.now = _ts(11, 30)
    for i in range(10):
        w.append(_book_event(11, i, checksum=100 + i))
    w.append(_hour10_event(59, 999))  # the replayed straggler
    for i in range(10, 20):
        w.append(_book_event(11, i, checksum=100 + i))
    w.append(_book_event(12, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(10))
    hour11 = pl.read_parquet(_segment_path(tmp_path, 11))
    assert hour11["checksum"].to_list() == list(range(100, 120))  # complete, not cut at the straggler


def test_construction_sweeps_stale_parts_from_a_past_hour(tmp_path, clock_in_hour10):
    # Scenario C: the process is down across the hour boundary, so the restarted writer never
    # opens hour 10 at all. Only a construction-time sweep can recover it.
    w1 = _new_writer(tmp_path, flush_rows=10)
    for i in range(51):  # 50 rows flushed into 5 parts, 1 buffered
        w1.append(_hour10_event(i * 60, i))
    del w1

    path10 = _segment_path(tmp_path, 10)
    clock_in_hour10.now = _ts(11, 30)  # the restart lands after the boundary
    w2 = _new_writer(tmp_path, flush_rows=10)  # sweep happens at construction, before any append

    df10 = pl.read_parquet(path10)
    assert df10.height == 50
    assert df10["checksum"].to_list() == list(range(50))
    assert df10["ts"][0] == _ts(10, 0, 0)
    assert not list(path10.parent.glob("10.part*.parquet"))
    assert verify_manifest(path10) is True

    for i in range(20):
        w2.append(_book_event(11, i, checksum=1000 + i))
    w2.append(_book_event(12, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 11)).height == 20
    assert pl.read_parquet(path10).height == 50  # the swept hour is not re-clobbered


def test_multiple_restarts_within_one_hour_preserve_all_flushed_rows(tmp_path, clock_in_hour10):
    # Scenario D: two hard crashes inside one hour. No generation's parts may be overwritten
    # (filename collision) or stranded (excluded from the merge).
    w1 = _new_writer(tmp_path, flush_rows=10)
    for i in range(25):  # 20 flushed, 5 buffered and lost
        w1.append(_hour10_event(i, i))
    del w1

    w2 = _new_writer(tmp_path, flush_rows=10)
    for i in range(25):  # 20 flushed, 5 buffered and lost
        w2.append(_hour10_event(100 + i, 100 + i))
    del w2

    w3 = _new_writer(tmp_path, flush_rows=10)
    for i in range(25):
        w3.append(_hour10_event(200 + i, 200 + i))
    w3.append(_book_event(11, 0))  # rotation flushes w3's buffer, so all 25 of its rows land

    path = _segment_path(tmp_path, 10)
    df = pl.read_parquet(path)
    assert df.height == 65
    assert df["checksum"].to_list() == (list(range(20)) + list(range(100, 120)) + list(range(200, 225)))
    assert verify_manifest(path) is True


def test_merge_preserves_intra_timestamp_append_order(tmp_path, clock_in_hour10):
    # L2 book deltas carry ABSOLUTE quantities: re-ordering rows that share a ts corrupts the
    # reconstructed book. The merge must concatenate, never sort.
    w1 = _new_writer(tmp_path, flush_rows=3)
    for i in range(6):  # all at the very same ts; 2 full parts, empty buffer
        w1.append(_book_event(10, 0, 0, checksum=i))
    del w1

    w2 = _new_writer(tmp_path, flush_rows=3)
    for i in range(6, 12):
        w2.append(_book_event(10, 0, 0, checksum=i))
    w2.append(_book_event(11, 0))

    df = pl.read_parquet(_segment_path(tmp_path, 10))
    assert df["checksum"].to_list() == list(range(12))


def _crash_mid_merge(tmp_path, clock, *, keep_manifest: bool):
    """Drive a real writer through a full hour-10 finalize, then put back the exact on-disk state a
    hard kill *inside* the merge leaves behind: the committed `10.parquet` plus the part files it
    was merging (the kill came before the unlink loop finished) and, unless `keep_manifest`, without
    the sidecar (the kill came before the manifest was written). Nothing is mocked — the merge that
    produced the final is the writer's own."""
    clock.now = _ts(10, 30)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # 4 parts, empty buffer
        w.append(_hour10_event(i, i))
    hour_dir = _segment_path(tmp_path, 10).parent
    saved = {p.name: p.read_bytes() for p in sorted(hour_dir.glob("10.part*.parquet"))}
    w.append(_book_event(11, 0))  # crossing the boundary finalizes hour 10 for real
    del w

    for name, data in saved.items():
        (hour_dir / name).write_bytes(data)
    if not keep_manifest:
        (hour_dir / "10.parquet.sha256").unlink()
    clock.now = _ts(11, 5)  # the restart lands after the boundary
    return hour_dir


def test_leftover_parts_beside_a_final_are_never_re_merged(tmp_path, clock):
    # A kill between the final's atomic commit and the part unlinks leaves parts that are ALREADY in
    # the final. Merging them again would duplicate every row — and the regenerated sha256 would
    # then bless the duplicate, so verify_manifest() would report a false all-clear.
    hour_dir = _crash_mid_merge(tmp_path, clock, keep_manifest=True)
    _new_writer(tmp_path, flush_rows=5)  # the construction sweep must resolve this, not re-merge

    path = _segment_path(tmp_path, 10)
    df = pl.read_parquet(path)
    assert df["checksum"].to_list() == list(range(20))  # not 0..19 twice
    assert not list(hour_dir.glob("10.part*.parquet"))
    assert verify_manifest(path) is True


def test_crash_between_the_final_and_its_manifest_is_healed(tmp_path, clock):
    # Same kill, one step earlier: the manifest was not written yet. Recovery must bless the final
    # that is on disk — not re-merge the parts into it.
    hour_dir = _crash_mid_merge(tmp_path, clock, keep_manifest=False)
    _new_writer(tmp_path, flush_rows=5)

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))
    assert not list(hour_dir.glob("10.part*.parquet"))
    assert verify_manifest(path) is True


def test_final_left_without_a_manifest_is_blessed_at_construction(tmp_path, clock_in_hour10):
    # The pre-T0036 merge unlinked the parts BEFORE writing the manifest, so a kill in that window
    # left a complete, correct segment that nothing would ever bless: no parts remain to retrigger a
    # merge, so verify_manifest() (and the archive's verify_tree) flag the hour corrupt forever.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))
    del w

    path = _segment_path(tmp_path, 10)
    path.with_name(path.name + ".sha256").unlink()  # the kill: parts already gone, manifest not yet written

    clock_in_hour10.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)
    assert verify_manifest(path) is True
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))


def test_a_torn_part_is_quarantined_and_never_bricks_construction(tmp_path, clock_in_hour10):
    # A part left truncated by a hard kill (no PAR1 footer) must not abort construction: the writers
    # are built at daemon startup, so a raise here crash-loops the whole capture — every pair, every
    # kind — until a human deletes the file. The torn part is renamed aside, never deleted.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(15):  # 3 parts
        w.append(_hour10_event(i, i))
    del w

    hour_dir = _segment_path(tmp_path, 10).parent
    torn = hour_dir / "10.part0002.parquet"
    torn.write_bytes(torn.read_bytes()[:20])

    clock_in_hour10.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)  # must not raise

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(10))  # the two readable parts
    assert (hour_dir / "10.part0002.parquet.corrupt").exists()  # forensic evidence, kept
    assert verify_manifest(path) is True


def test_an_unreadable_final_is_not_blessed_with_a_manifest(tmp_path, clock_in_hour10):
    # The pre-T0036 merge wrote <HH>.parquet non-atomically, so a kill could leave a torn final with
    # no sidecar. Writing one would certify garbage as verified; leaving it unblessed keeps the
    # archive's verify_tree reporting it, which is the fail-safe direction.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))
    del w

    path = _segment_path(tmp_path, 10)
    path.write_bytes(path.read_bytes()[:20])
    manifest = path.with_name(path.name + ".sha256")
    manifest.unlink()

    clock_in_hour10.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)  # must not raise
    assert not manifest.exists()


def test_finalized_segment_is_a_superset_and_manifest_matches(tmp_path, clock_in_hour10):
    # The sha256 sidecar may only ever bless a file that holds every row that ever reached disk —
    # otherwise the integrity check certifies a truncated (or a duplicated) segment.
    w1 = _new_writer(tmp_path, flush_rows=7)
    for i in range(40):
        w1.append(_hour10_event(i, i))
    w1.close()

    path = _segment_path(tmp_path, 10)
    persisted = pl.concat([pl.read_parquet(p) for p in sorted(path.parent.glob("10.part*.parquet"))])
    assert persisted["checksum"].to_list() == list(range(40))

    w2 = _new_writer(tmp_path, flush_rows=7)
    for i in range(40, 90):
        w2.append(_hour10_event(i, i))
    w2.append(_book_event(11, 0))

    final = pl.read_parquet(path)["checksum"].to_list()
    assert final[:40] == persisted["checksum"].to_list()  # prefix-preserving superset
    assert final == list(range(90))
    assert verify_manifest(path) is True


# --- a final is only a commit marker if it can actually be READ (T0036, round 3) ----------------
#
# "A final exists ⇒ the parts beside it are its own already-merged inputs" is an assumption, and it
# is false in states this very deploy reaches. Every claim below is checked against the file, never
# against the rule.


def test_a_torn_final_beside_its_parts_is_quarantined_and_the_hour_recovered(tmp_path, clock):
    # The pre-T0036 merge wrote `<HH>.parquet` NON-atomically (`sink_parquet` straight to the final)
    # and unlinked the parts only afterwards. A process hard-killed inside that sink — the slow, IO
    # heavy step of an ordinary rotation — leaves a torn final beside the parts, which still hold the
    # complete hour. Trusting the final because it exists would delete a 100%-recoverable hour.
    clock.now = _ts(10, 30)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # 4 parts, empty buffer
        w.append(_hour10_event(i, i))
    del w
    hour_dir = _segment_path(tmp_path, 10).parent
    (hour_dir / "10.parquet").write_bytes(b"PAR1" + b"\x00" * 200)  # the sink, cut off mid-write

    clock.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)  # the construction sweep must recover the hour, not bin it

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # the parts, merged
    assert verify_manifest(path) is True
    assert (hour_dir / "10.parquet.corrupt").exists()  # the torn bytes are evidence, never deleted
    assert not list(hour_dir.glob("10.part*.parquet"))


def test_a_bit_rotted_final_is_never_re_blessed(tmp_path, clock):
    # The sha256 sidecar is the ONLY corruption detector this unbackfillable dataset has. Rewriting
    # it over an existing one flips verify_manifest() from False back to True and destroys it.
    clock.now = _ts(10, 30)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))  # hour 10 is committed: final + manifest, parts unlinked
    del w

    path = _segment_path(tmp_path, 10)
    manifest = path.with_name(path.name + ".sha256")
    recorded = manifest.read_text()
    # Bit-rot the committed final into a file that still READS fine but no longer matches its digest
    # — precisely the corruption class the sidecar exists to catch, because the reader cannot.
    pl.read_parquet(path).with_columns(checksum=pl.col("checksum") + 1).write_parquet(path, compression="zstd")
    assert verify_manifest(path) is False  # the detector fires
    # A part appears beside the committed final — routine: a reconnect replays pre-boundary prints.
    part = pl.DataFrame([_hour10_event(0, 0)], schema=BOOK_SCHEMA)
    part.write_parquet(path.parent / "10.part0000.parquet", compression="zstd")

    clock.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)

    assert verify_manifest(path) is False  # still flagged — the sidecar was not touched
    assert manifest.read_text() == recorded


def test_a_body_corrupt_part_is_quarantined_instead_of_killing_the_writer(tmp_path, clock_in_hour10):
    # A part whose footer is intact but whose data pages are not passes a footer-only check and
    # reaches `sink_parquet`, which raises. On the rotation path that escapes `append()` — and
    # neither _handle_book_message, _consume nor _run catches it, so capture dies for EVERY pair and
    # both kinds, mid-hour. An unreadable part must be quarantined, and the merge must go on.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(15):  # 3 parts
        w.append(_hour10_event(i, i))
    hour_dir = _segment_path(tmp_path, 10).parent
    _corrupt_body(hour_dir / "10.part0001.parquet")

    w.append(_book_event(11, 0))  # crossing the boundary merges hour 10 — this must not raise

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == [0, 1, 2, 3, 4, 10, 11, 12, 13, 14]
    assert (hour_dir / "10.part0001.parquet.corrupt").exists()
    assert verify_manifest(path) is True


def test_a_body_corrupt_final_is_never_blessed_with_a_manifest(tmp_path, clock_in_hour10):
    # Same footer-only blindness, one file up: blessing a final whose data pages are gone certifies
    # an unreadable segment as verified. Validate by reading the rows, not the footer.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))
    del w

    path = _segment_path(tmp_path, 10)
    manifest = path.with_name(path.name + ".sha256")
    _corrupt_body(path)
    manifest.unlink()  # the pre-T0036 kill between the final and its manifest, which blessing heals

    clock_in_hour10.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)  # must not raise
    assert not manifest.exists()


def test_a_replayed_pre_boundary_print_cannot_reopen_a_closed_hour(tmp_path, clock):
    # The late-event guard was dead on a process's FIRST event (`_current_hour` was still None), and
    # ws_client resubscribes with snapshot=True on every connect — so after a restart the first event
    # can be a replayed print stamped before the boundary (T0026). It reopened the already-finalized
    # hour: its rows were written to a part beside the final and then unlinked.
    clock.now = _ts(10, 30)
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w1.append(_hour10_event(i, i))
    del w1  # hard crash inside hour 10

    clock.now = _ts(11, 0, 3)  # the daemon comes back just after the boundary
    w2 = _new_writer(tmp_path, flush_rows=5)  # its sweep finalizes hour 10
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path).height == 20

    for i in range(6):  # the resubscribe's replayed pre-boundary prints (enough to force a flush)
        w2.append(_hour10_event(3594 + i, 900 + i))
    assert not w2._buffer  # not even buffered: the hour is over
    assert not list(path.parent.glob("10.part*.parquet"))  # never written beside the closed hour

    for i in range(10):
        w2.append(_book_event(11, i, checksum=100 + i))
    w2.append(_book_event(12, 0))

    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # the closed hour is intact
    assert pl.read_parquet(_segment_path(tmp_path, 11))["checksum"].to_list() == list(range(100, 110))


def test_replayed_prints_never_publish_an_hour_that_was_never_captured(tmp_path, clock):
    # Same dead guard, worse consequence: with the daemon down across the WHOLE of hour 10 there is
    # no final to collide with, so the replayed prints published `10.parquet` — a manifested,
    # verify-clean, complete-looking segment for an hour that was never captured.
    clock.now = _ts(11, 0, 3)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(6):
        w.append(_hour10_event(3594 + i, i))  # 10:59:54 .. 10:59:59, replayed on resubscribe
    for i in range(10):
        w.append(_book_event(11, i, checksum=100 + i))
    w.append(_book_event(12, 0))

    hour10 = _segment_path(tmp_path, 10)
    assert not hour10.exists()  # coverage is not falsified
    assert not list(hour10.parent.glob("10.part*.parquet"))
    assert pl.read_parquet(_segment_path(tmp_path, 11))["checksum"].to_list() == list(range(100, 110))


def test_a_committed_final_is_never_demoted_when_the_clock_lags(tmp_path, clock):
    # Rotation follows Kraken's EXCHANGE ts; the sweep read our own WALL clock. Any lag (or backward
    # NTP/VM step) put a restart in a window where recovery mistook a cleanly committed final for a
    # partial one, demoting it to part0000 and deleting its manifest — the hour then has no segment
    # for the daemon's entire uptime. Adoption must key on the first event's own hour, not the clock.
    clock.now = _ts(10, 30)
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w1.append(_hour10_event(i, i))
    w1.append(_book_event(11, 0))  # an exchange-time hour-11 event commits hour 10...
    del w1

    path = _segment_path(tmp_path, 10)
    clock.now = _ts(10, 59, 59)  # ...while our clock still reads hour 10
    w2 = _new_writer(tmp_path, flush_rows=5)
    assert path.exists()  # the committed final stays committed
    assert verify_manifest(path) is True
    assert not list(path.parent.glob("10.part*.parquet"))

    for i in range(10):  # the live stream is in hour 11 and never crosses back
        w2.append(_book_event(11, i, checksum=100 + i))
    clock.now = _ts(11, 30)
    w2.append(_book_event(12, 0))

    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))
    assert verify_manifest(path) is True
    assert pl.read_parquet(_segment_path(tmp_path, 11))["checksum"].to_list() == list(range(100, 110))


def test_an_implausible_far_future_ts_cannot_brick_the_writer(tmp_path, clock_in_hour10):
    # Rotation follows the event's own ts, so one garbage-but-parseable far-future stamp finalized
    # the live hour early and then had the late-event guard drop every genuine row after it — for
    # the life of the process.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(10):
        w.append(_hour10_event(i, i))
    w.append(_book_event(23, 59, checksum=999))  # garbage
    for i in range(10, 20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # nothing was dropped
    assert not _segment_path(tmp_path, 23).exists()


def test_quarantine_never_clobbers_an_earlier_corrupt_file(tmp_path, clock):
    # The part-sequence counter globs `<HH>.part*.parquet`, which `.corrupt` files do not match — so
    # once every part of an hour has been quarantined the numbering restarts at 0000 and the same
    # `.corrupt` target recurs. POSIX rename overwrites, destroying the bytes quarantine preserves.
    clock.now = _ts(10, 30)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(5):
        w.append(_hour10_event(i, i))
    del w

    hour_dir = _segment_path(tmp_path, 10).parent
    (hour_dir / "10.part0000.parquet.corrupt").write_bytes(b"earlier evidence")
    torn = hour_dir / "10.part0000.parquet"
    torn.write_bytes(torn.read_bytes()[:20])

    clock.now = _ts(11, 5)
    _new_writer(tmp_path, flush_rows=5)  # must not raise

    assert (hour_dir / "10.part0000.parquet.corrupt").read_bytes() == b"earlier evidence"
    assert (hour_dir / "10.part0000.parquet.corrupt.1").exists()


def test_parts_and_segments_are_fsynced_before_the_rename(tmp_path, clock_in_hour10, monkeypatch):
    # `os.replace` is atomic but not durable: on a power loss (as opposed to a process kill) the
    # rename can reach the disk while the data blocks it points at have not, resurrecting a torn
    # file. The data, then the directory entry, must be fsynced. This dataset is unbackfillable.
    synced: set[tuple[int, int]] = set()
    real_fsync = os.fsync

    def _record(fd: int) -> None:
        st = os.fstat(fd)
        synced.add((st.st_dev, st.st_ino))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", _record)

    def _ident(path):
        st = path.stat()
        return (st.st_dev, st.st_ino)

    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(5):
        w.append(_hour10_event(i, i))

    hour_dir = _segment_path(tmp_path, 10).parent
    part = hour_dir / "10.part0000.parquet"
    assert _ident(part) in synced  # the tmp's data blocks (the rename keeps the inode)
    assert _ident(hour_dir) in synced  # the directory entry the rename created

    w.append(_book_event(11, 0))
    assert _ident(_segment_path(tmp_path, 10)) in synced
