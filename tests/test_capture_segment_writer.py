from datetime import datetime, timezone

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


def test_close_flushes_the_buffer_without_publishing_a_partial_segment(tmp_path):
    # close() must not finalize: an hour cut short by a stop is not a whole hour, and a final that
    # can appear beside its own parts is exactly what makes crash recovery ambiguous (T0036).
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(15, 0))
    writer.close()

    hour15 = _segment_path(tmp_path, 15)
    assert not hour15.exists()
    assert [p.name for p in hour15.parent.glob("15.part*.parquet")] == ["15.part0000.parquet"]

    # The next process finishes the hour, since by then it is over.
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
def clock_in_hour10(monkeypatch):
    """Pin the writer's wall clock inside hour 10 — the hour these tests are still capturing.

    Construction finalizes only hours strictly BEFORE the current one; the hour in progress is left
    as parts for the restarted writer to resume. Without pinning the clock, hour 10 of 2026-07-08
    is long past, so the sweep would (correctly, but uninterestingly) close it at construction and
    the restart-within-the-open-hour behaviour would never be exercised.
    """
    monkeypatch.setattr(segment_writer, "_utcnow", lambda: _ts(10, 30))


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


def test_late_event_for_a_closed_hour_never_reopens_it(tmp_path):
    # A reconnect's trade snapshot replays prints from before the hour boundary (T0026). Rotating
    # backwards onto that closed hour would finalize the CURRENT hour early — and every row it then
    # captured would be dropped as "already merged". The hour is monotone: late rows are dropped.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(10):
        w.append(_hour10_event(i, i))
    for i in range(10):
        w.append(_book_event(11, i, checksum=100 + i))
    w.append(_hour10_event(59, 999))  # the replayed straggler
    for i in range(10, 20):
        w.append(_book_event(11, i, checksum=100 + i))
    w.append(_book_event(12, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(10))
    hour11 = pl.read_parquet(_segment_path(tmp_path, 11))
    assert hour11["checksum"].to_list() == list(range(100, 120))  # complete, not cut at the straggler


def test_construction_sweeps_stale_parts_from_a_past_hour(tmp_path):
    # Scenario C: the process is down across the hour boundary, so the restarted writer never
    # opens hour 10 at all. Only a construction-time sweep can recover it.
    w1 = _new_writer(tmp_path, flush_rows=10)
    for i in range(51):  # 50 rows flushed into 5 parts, 1 buffered
        w1.append(_hour10_event(i * 60, i))
    del w1

    path10 = _segment_path(tmp_path, 10)
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


def _crash_mid_merge(tmp_path, *, keep_manifest: bool):
    """Drive a real writer through a full hour-10 finalize, then put back the exact on-disk state a
    hard kill *inside* the merge leaves behind: the committed `10.parquet` plus the part files it
    was merging (the kill came before the unlink loop finished) and, unless `keep_manifest`, without
    the sidecar (the kill came before the manifest was written). Nothing is mocked — the merge that
    produced the final is the writer's own."""
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
    return hour_dir


def test_leftover_parts_beside_a_final_are_never_re_merged(tmp_path):
    # A kill between the final's atomic commit and the part unlinks leaves parts that are ALREADY in
    # the final. Merging them again would duplicate every row — and the regenerated sha256 would
    # then bless the duplicate, so verify_manifest() would report a false all-clear.
    hour_dir = _crash_mid_merge(tmp_path, keep_manifest=True)
    _new_writer(tmp_path, flush_rows=5)  # the construction sweep must resolve this, not re-merge

    path = _segment_path(tmp_path, 10)
    df = pl.read_parquet(path)
    assert df["checksum"].to_list() == list(range(20))  # not 0..19 twice
    assert not list(hour_dir.glob("10.part*.parquet"))
    assert verify_manifest(path) is True


def test_crash_between_the_final_and_its_manifest_is_healed(tmp_path):
    # Same kill, one step earlier: the manifest was not written yet. Recovery must bless the final
    # that is on disk — not re-merge the parts into it.
    hour_dir = _crash_mid_merge(tmp_path, keep_manifest=False)
    _new_writer(tmp_path, flush_rows=5)

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))
    assert not list(hour_dir.glob("10.part*.parquet"))
    assert verify_manifest(path) is True


def test_final_left_without_a_manifest_is_blessed_at_construction(tmp_path):
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

    _new_writer(tmp_path, flush_rows=5)
    assert verify_manifest(path) is True
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))


def test_a_torn_part_is_quarantined_and_never_bricks_construction(tmp_path):
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

    _new_writer(tmp_path, flush_rows=5)  # must not raise

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(10))  # the two readable parts
    assert (hour_dir / "10.part0002.parquet.corrupt").exists()  # forensic evidence, kept
    assert verify_manifest(path) is True


def test_an_unreadable_final_is_not_blessed_with_a_manifest(tmp_path):
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
