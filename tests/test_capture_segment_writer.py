import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import pytest

from cli.capture import segment_writer
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA, SegmentWriter, verify_manifest


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


def _trade_event(hour: int, sec: int, trade_id: int) -> dict:
    return {
        "ts": _ts(hour, sec // 60, sec % 60),
        "symbol": "BTC/EUR",
        "side": "buy",
        "price": 100.0,
        "qty": 1.0,
        "ord_type": "market",
        "trade_id": trade_id,
    }


def _segment_path(base_dir, hour: int, kind: str = "book"):
    return base_dir / "BTC/EUR" / kind / "2026" / "07" / "08" / f"{hour:02d}.parquet"


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
    """The host's wall clock, pinned and settable — production has one, so the tests do too."""

    def __init__(self) -> None:
        self.now = _ts(16, 0)


@pytest.fixture(autouse=True)
def clock(monkeypatch) -> _Clock:
    """Pin `_utcnow()`.

    The writer's hour state is read from disk and from the event stream — never from this clock — so
    no test has to move it in lockstep with the events it feeds. It is consulted in exactly one
    place: `_implausible()`, where it is one of the two witnesses that must BOTH call a `ts` garbage
    before a row is dropped. Pinned an hour ahead of the events the tests feed, so an ordinary event
    is plausible and only a genuinely far-future one is not.
    """
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


def test_close_flushes_the_buffer_without_publishing_a_partial_segment(tmp_path):
    # close() must not finalize: an hour cut short by a stop is not a whole hour, and `<HH>.parquet`
    # means "committed and complete" — the one invariant crash recovery rests on (T0036).
    writer = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    writer.append(_book_event(15, 0))
    writer.close()

    hour15 = _segment_path(tmp_path, 15)
    assert not hour15.exists()
    assert [p.name for p in hour15.parent.glob("15.part*.parquet")] == ["15.part0000.parquet"]

    # The next process finishes the hour on its first event, since by then the hour is over.
    w2 = SegmentWriter(tmp_path, "BTC/EUR", "book", BOOK_SCHEMA)
    w2.append(_book_event(16, 0))
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


def test_verify_manifest_treats_an_empty_sidecar_as_missing(tmp_path):
    # A pre-T0036 process killed inside its non-atomic `write_text` left a 0-byte sidecar, and
    # `read_text().split()[0]` then raised IndexError out of the archive's verify_tree — a crash
    # instead of a report. An empty (or unparseable) sidecar is a MISSING one, not a mismatch.
    path = tmp_path / "orphan.parquet"
    path.write_bytes(b"not-really-parquet")
    path.with_name(path.name + ".sha256").write_text("")
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


def _new_trade_writer(tmp_path, flush_rows: int) -> SegmentWriter:
    return SegmentWriter(tmp_path, "BTC/EUR", "trades", TRADE_SCHEMA, flush_rows=flush_rows, dedup_key="trade_id")


def test_hard_crash_restart_same_hour_keeps_every_flushed_row(tmp_path):
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
def test_restart_after_graceful_close_resumes_the_open_hour(tmp_path, flush_rows):
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


def test_the_first_event_sweeps_stale_parts_from_a_past_hour(tmp_path):
    # Scenario C: the process is down across the hour boundary, so the restarted writer never opens
    # hour 10 at all. Only the sweep can recover it — and it runs off the first event's own hour,
    # which is exchange time, never our wall clock.
    w1 = _new_writer(tmp_path, flush_rows=10)
    for i in range(51):  # 50 rows flushed into 5 parts, 1 buffered
        w1.append(_hour10_event(i * 60, i))
    del w1

    path10 = _segment_path(tmp_path, 10)
    w2 = _new_writer(tmp_path, flush_rows=10)
    w2.append(_book_event(11, 0, checksum=1000))  # the first event: hour 10 is over, sweep it

    df10 = pl.read_parquet(path10)
    assert df10.height == 50
    assert df10["checksum"].to_list() == list(range(50))
    assert df10["ts"][0] == _ts(10, 0, 0)
    assert not list(path10.parent.glob("10.part*.parquet"))
    assert verify_manifest(path10) is True

    for i in range(1, 20):
        w2.append(_book_event(11, i, checksum=1000 + i))
    w2.append(_book_event(12, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 11)).height == 20
    assert pl.read_parquet(path10).height == 50  # the swept hour is not re-clobbered


def test_multiple_restarts_within_one_hour_preserve_all_flushed_rows(tmp_path):
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


def test_merge_preserves_intra_timestamp_append_order(tmp_path):
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


def test_merge_preserves_part_order_across_many_parts(tmp_path):
    # The merge streams every part through ONE `scan_parquet(<list>)`, which is what makes rotation
    # cheap enough not to stall the event loop. Row order across the file list is what the whole
    # dataset rests on (absolute-quantity deltas), so pin it at a part count a real hour reaches —
    # and with the rows deliberately NOT sorted by ts, so a sort could never masquerade as order.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(300):  # 60 parts
        w.append(_book_event(10, 30 - (i % 30), 0, checksum=i))  # ts sweeps BACKWARD within the hour
    w.append(_book_event(11, 0, checksum=-1))

    df = pl.read_parquet(_segment_path(tmp_path, 10))
    assert df["checksum"].to_list() == list(range(300))  # append order, exactly
    assert not df["ts"].is_sorted()  # ... and it is emphatically not ts order


def test_a_torn_part_is_quarantined_and_never_bricks_the_writer(tmp_path):
    # A part left truncated by a hard kill (no PAR1 footer) must not abort the merge: it runs from
    # append(), so a raise propagates out of the daemon's consumer task and kills the whole capture —
    # every pair, every kind — until a human deletes the file. The torn part is renamed aside.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(15):  # 3 parts
        w.append(_hour10_event(i, i))
    del w

    hour_dir = _segment_path(tmp_path, 10).parent
    torn = hour_dir / "10.part0002.parquet"
    torn.write_bytes(torn.read_bytes()[:20])

    w2 = _new_writer(tmp_path, flush_rows=5)  # must not raise
    w2.append(_book_event(11, 0))  # nor may this

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(10))  # the two readable parts
    assert (hour_dir / "10.part0002.parquet.corrupt").exists()  # forensic evidence, kept
    assert verify_manifest(path) is True


def test_a_body_corrupt_part_is_quarantined_instead_of_killing_the_writer(tmp_path):
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


def test_finalized_segment_is_a_superset_and_manifest_matches(tmp_path):
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


def test_quarantine_never_clobbers_an_earlier_corrupt_file(tmp_path):
    # The part-sequence counter globs `<HH>.part*.parquet`, which `.corrupt` files do not match — so
    # once every part of an hour has been quarantined the numbering restarts at 0000 and the same
    # `.corrupt` target recurs. POSIX rename overwrites, destroying the bytes quarantine preserves.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(5):
        w.append(_hour10_event(i, i))
    del w

    hour_dir = _segment_path(tmp_path, 10).parent
    (hour_dir / "10.part0000.parquet.corrupt").write_bytes(b"earlier evidence")
    torn = hour_dir / "10.part0000.parquet"
    torn.write_bytes(torn.read_bytes()[:20])

    w2 = _new_writer(tmp_path, flush_rows=5)  # must not raise
    w2.append(_book_event(11, 0))  # nor may this

    assert (hour_dir / "10.part0000.parquet.corrupt").read_bytes() == b"earlier evidence"
    assert (hour_dir / "10.part0000.parquet.corrupt.1").exists()


def test_parts_segments_and_manifests_are_fsynced_before_the_rename(tmp_path, monkeypatch):
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
    path = _segment_path(tmp_path, 10)
    assert _ident(path) in synced
    # The sidecar too: a kill inside a bare write_text() left a 0-byte manifest that nothing would
    # ever rewrite (an existing sidecar is never re-blessed), flagging a good hour corrupt forever.
    assert _ident(path.with_name(path.name + ".sha256")) in synced


# --- the invariant: `<HH>.parquet` on disk is ALWAYS a committed, complete final -----------------
#
# It is what lets recovery be mechanical instead of a guess, and what lets the writer hold no wall
# clock at all. Every state below is built by driving the real writer and then restoring the exact
# bytes a kill would have left.


def _crash_inside_merge(tmp_path, *, stage: str) -> Path:
    """Drive a real hour-10 merge, then restore the on-disk bytes a hard kill at `stage` leaves.

    The merging file's bytes ARE the bytes the final is renamed from, so renaming the committed
    final back to `<HH>.parquet.merging` reproduces them exactly. `stage` walks the commit sequence:
    `manifest` (killed before the sidecar was written), `unlink` (before the parts were removed),
    `replace` (before the atomic rename that publishes the hour).
    """
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # 4 parts, empty buffer
        w.append(_hour10_event(i, i))
    hour_dir = _segment_path(tmp_path, 10).parent
    parts = {p.name: p.read_bytes() for p in sorted(hour_dir.glob("10.part*.parquet"))}
    w.append(_book_event(11, 0))  # crossing the boundary merges + commits hour 10 for real
    del w

    (hour_dir / "10.parquet").rename(hour_dir / "10.parquet.merging")
    if stage == "manifest":
        (hour_dir / "10.parquet.sha256").unlink()
    if stage in ("manifest", "unlink"):
        for name, data in parts.items():
            (hour_dir / name).write_bytes(data)
    return hour_dir


@pytest.mark.parametrize("stage", ["manifest", "unlink", "replace"])
def test_an_interrupted_merge_is_committed_from_its_merging_file(tmp_path, stage):
    # The merged bytes are sunk atomically to `<HH>.parquet.merging` and renamed onto `<HH>.parquet`
    # LAST — so an interrupted merge is a complete file that simply was not published yet. It is
    # authoritative: recovery replays the three commit steps and never has to ask whether the parts
    # beside it are already inside it (they are), nor whether the final is whole (it is).
    hour_dir = _crash_inside_merge(tmp_path, stage=stage)
    _new_writer(tmp_path, flush_rows=5)  # construction alone must resolve it

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # not 0..19 twice
    assert not list(hour_dir.glob("10.part*.parquet"))
    assert not list(hour_dir.glob("*.merging"))
    assert verify_manifest(path) is True


@pytest.mark.parametrize("reading", ["partial-final", "already-merged"])
def test_parts_beside_a_readable_final_are_left_untouched_for_a_human(tmp_path, reading):
    # A pre-T0036 leftover, and the one state that is genuinely AMBIGUOUS — the old writer produced
    # BOTH readings of it, and they are byte-indistinguishable:
    #
    #   "partial-final"  its close() published the open hour, then it ran on and flushed MORE rows
    #                    into parts. The parts hold rows the final does not -> merging is right, and
    #                    dropping the parts (round 3 did) destroys them.
    #   "already-merged" its finalize sank the final and unlinked the parts only AFTERWARDS. A kill
    #                    in that window leaves parts the final ALREADY holds -> merging duplicates
    #                    the whole hour, and the fresh sha256 would certify the duplicate.
    #
    # Either guess permanently destroys the hour in the other reading. Every byte is safe on disk and
    # nothing is on fire, so the writer touches NOTHING and says so.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    del w
    hour_dir = _segment_path(tmp_path, 10).parent
    parts_before = {p.name: p.read_bytes() for p in sorted(hour_dir.glob("10.part*.parquet"))}

    final = hour_dir / "10.parquet"
    rows = range(20, 40) if reading == "partial-final" else range(20)  # disjoint rows, or the same ones
    pl.DataFrame([_hour10_event(i, i) for i in rows], schema=BOOK_SCHEMA).write_parquet(final, compression="zstd")
    digest = hashlib.sha256(final.read_bytes()).hexdigest()
    (hour_dir / "10.parquet.sha256").write_text(f"{digest}  10.parquet\n")
    final_before = final.read_bytes()

    w2 = _new_writer(tmp_path, flush_rows=5)
    w2.append(_book_event(11, 0))  # its sweep reaches hour 10 and must decline

    assert final.read_bytes() == final_before  # not re-merged, not duplicated, not truncated
    assert {p.name: p.read_bytes() for p in sorted(hour_dir.glob("10.part*.parquet"))} == parts_before
    assert not list(hour_dir.glob("*.corrupt"))  # nothing was unreadable, so nothing was binned
    assert verify_manifest(final) is True  # the sidecar it came with, untouched


def test_a_torn_final_beside_its_parts_is_quarantined_and_the_hour_recovered(tmp_path):
    # The pre-T0036 merge wrote `<HH>.parquet` NON-atomically (`sink_parquet` straight to the final).
    # A process hard-killed inside that sink — the slow, IO-heavy step of an ordinary rotation —
    # leaves a torn final beside the parts, which still hold the complete hour. Trusting the final
    # because it exists (or because its footer parses) would delete a 100%-recoverable hour.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # 4 parts, empty buffer
        w.append(_hour10_event(i, i))
    del w
    hour_dir = _segment_path(tmp_path, 10).parent
    (hour_dir / "10.parquet").write_bytes(b"PAR1" + b"\x00" * 200)  # the sink, cut off mid-write

    w2 = _new_writer(tmp_path, flush_rows=5)
    w2.append(_book_event(11, 0))  # the sweep must recover the hour, not bin it

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # the parts, merged
    assert verify_manifest(path) is True
    assert (hour_dir / "10.parquet.corrupt").exists()  # the torn bytes are evidence, never deleted
    assert not list(hour_dir.glob("10.part*.parquet"))


def test_a_bit_rotted_final_is_never_re_blessed(tmp_path):
    # The sha256 sidecar is the ONLY corruption detector this unbackfillable dataset has. Rewriting
    # it over an existing one flips verify_manifest() from False back to True and destroys it — so a
    # final whose digest no longer matches is never folded into a new segment, and never re-blessed.
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
    part = pl.DataFrame([_hour10_event(0, 0)], schema=BOOK_SCHEMA)
    part.write_parquet(path.parent / "10.part0000.parquet", compression="zstd")

    w2 = _new_writer(tmp_path, flush_rows=5)
    w2.append(_book_event(12, 0))  # its sweep reaches hour 10

    assert verify_manifest(path) is False  # still flagged — the sidecar was not touched
    assert manifest.read_text() == recorded
    assert (path.parent / "10.part0000.parquet").exists()  # and nothing was deleted to tidy it away


def test_a_final_this_writer_did_not_produce_is_never_touched(tmp_path):
    # A `<HH>.parquet` with no parts beside it is a committed hour. The writer has no business
    # rewriting it, quarantining it, or inventing a manifest for a segment it cannot even read:
    # blessing one would certify garbage as verified, and the archive's verify_tree — which reports
    # it — is the fail-safe direction.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))
    del w

    path = _segment_path(tmp_path, 10)
    _corrupt_body(path)  # a footer that parses over data pages that do not
    manifest = path.with_name(path.name + ".sha256")
    manifest.unlink()
    frozen = path.read_bytes()

    w2 = _new_writer(tmp_path, flush_rows=5)  # must not raise
    w2.append(_book_event(12, 0))

    assert not manifest.exists()
    assert path.read_bytes() == frozen
    assert not list(path.parent.glob("*.corrupt"))


def test_an_uncommittable_merge_is_never_sunk_over(tmp_path, monkeypatch):
    # A merge whose commit fails (a transient IO error — ENOSPC, EIO) leaves `<HH>.parquet.merging`
    # holding the hour's ONLY copy: its parts are already unlinked. That hour must count as CLOSED
    # even though no `<HH>.parquet` exists — otherwise the live stream re-opens it, and the next
    # rotation sinks a fresh merge straight over the only bytes there were.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))
    hour_dir = _segment_path(tmp_path, 10).parent
    parts = {p.name: p.read_bytes() for p in sorted(hour_dir.glob("10.part*.parquet"))}
    w.append(_book_event(11, 0))
    del w

    # The exact bytes a kill between the part unlinks and the atomic rename leaves behind.
    (hour_dir / "10.parquet").rename(hour_dir / "10.parquet.merging")
    merged = (hour_dir / "10.parquet.merging").read_bytes()

    # ... and the restart's promotion of it hits an IO error, which recovery logs and survives.
    boom = [True]

    def _explode(self, source, final_path):
        if boom[0]:
            boom[0] = False
            raise OSError(28, "No space left on device")
        _real_write_manifest(self, source, final_path)

    _real_write_manifest = SegmentWriter._write_manifest
    monkeypatch.setattr(SegmentWriter, "_write_manifest", _explode)

    w2 = _new_writer(tmp_path, flush_rows=5)  # must not raise
    assert (hour_dir / "10.parquet.merging").read_bytes() == merged  # still the only copy
    for i in range(20, 25):  # the live stream is still inside hour 10 — it must NOT re-open it
        w2.append(_hour10_event(i, i))
    w2.append(_book_event(11, 30))

    assert (hour_dir / "10.parquet.merging").read_bytes() == merged  # never sunk over
    assert not parts.keys() & {p.name for p in hour_dir.glob("10.part*.parquet")}  # and none re-appeared

    _new_writer(tmp_path, flush_rows=5)  # the next start's promotion succeeds
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))
    assert verify_manifest(path) is True
    assert not list(hour_dir.glob("*.merging"))


@pytest.mark.parametrize("stray", ["10.partial.parquet", "10.part0000-copy.parquet", "10.part.parquet"])
def test_a_stray_file_in_the_tree_cannot_crash_loop_the_daemon(tmp_path, stray):
    # `__init__` and `append()` both run on the daemon's single consumer task, so ANY raise out of
    # them kills capture for every pair and both kinds — and would do so again on every restart.
    # A human's backup, an rsync artefact or a restored file must never be able to do that.
    hour_dir = _segment_path(tmp_path, 10).parent
    hour_dir.mkdir(parents=True)
    (hour_dir / stray).write_bytes(b"not parquet")  # all three match a `10.part*.parquet` glob
    (tmp_path / "BTC/EUR" / "book" / "notes.parquet").write_bytes(b"not parquet")
    (tmp_path / "BTC/EUR" / "book" / "junk.tmp").mkdir()  # ... and `__init__` unlinks `*.tmp`

    w = _new_writer(tmp_path, flush_rows=5)  # must not raise
    for i in range(10):
        w.append(_hour10_event(i, i))  # nor may this
    w.append(_book_event(11, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(10))
    assert (hour_dir / stray).exists()  # left alone, not swept into the segment, not deleted


def test_a_failed_flush_never_takes_down_the_other_streams(tmp_path, monkeypatch):
    # The hottest write in the daemon (every `flush_rows` rows) and, unguarded, one OSError away from
    # taking down the single consumer task — i.e. capture for all 10 pairs and BOTH kinds. The
    # buffer is lost either way; the other 19 streams need not be.
    w = _new_writer(tmp_path, flush_rows=5)

    def _explode(source, dest):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(segment_writer, "_replace_durably", _explode)
    for i in range(5):
        w.append(_hour10_event(i, i))  # the flush fails — and must not raise

    monkeypatch.undo()
    for i in range(5, 10):
        w.append(_hour10_event(i, i))  # the disk comes back
    w.append(_book_event(11, 0))

    # The 5 rows in the failed flush are gone (they never reached disk); the stream carried on.
    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(5, 10))


def test_an_unreadable_part_does_not_silently_disable_the_dedup(tmp_path):
    # `_open_hour` seeds the de-dup keys from the parts on disk. Reading them as ONE scan means a
    # single unreadable part empties the whole set — and the reconnect's replay is then written a
    # second time, hash-clean. (The pre-T0036 writer's `_flush_buffer` wrote parts with a bare
    # `write_parquet`, so a SIGKILL leaves exactly this: a torn part. The deploy lands on it.)
    w1 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(20):  # trade_ids 0..19 -> 4 parts
        w1.append(_trade_event(10, i, i))
    del w1

    hour_dir = _segment_path(tmp_path, 10, "trades").parent
    torn = hour_dir / "10.part0002.parquet"  # trade_ids 10..14
    torn.write_bytes(torn.read_bytes()[:20])

    w2 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(3, 30):  # the resubscribe replays 3..19, of which 15..19 are still readable on disk
        w2.append(_trade_event(10, i, i))
    w2.append(_trade_event(11, 0, 999))

    ids = pl.read_parquet(_segment_path(tmp_path, 10, "trades"))["trade_id"].to_list()
    assert len(ids) == len(set(ids))  # no print is stored twice
    # 10..14 were only ever in the torn part, so the replay RECOVERS them; everything else is once.
    assert sorted(ids) == list(range(30))
    assert (hour_dir / "10.part0002.parquet.corrupt").exists()


def test_a_failed_merge_leaves_no_tmp_behind(tmp_path, monkeypatch):
    # The merge tmp is a full-hour-sized file, on the very disk DiskWatermark guards, and it is
    # invisible to the archive's `*.parquet` globs. A merge that fails must not leak one per attempt.
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w.append(_hour10_event(i, i))

    def _explode(source, dest):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(segment_writer, "_replace_durably", _explode)
    w.append(_book_event(11, 0))  # the rotation's merge fails — but must not raise, and must tidy up

    hour_dir = _segment_path(tmp_path, 10).parent
    assert not list(hour_dir.glob("*.tmp"))
    assert len(list(hour_dir.glob("10.part*.parquet"))) == 4  # every row still on disk, untouched


# --- no wall clock: the disk says which hours are closed, the stream says which are over ---------


def test_a_leading_clock_at_startup_cannot_drop_the_live_stream(tmp_path, clock):
    # zcrypto-capture.service has no `After=time-sync.target` and `Restart=always`, so a writer can
    # be constructed in the instant before chrony's first step, with the host clock reading an hour
    # or more ahead. Seeding the hour state from that clock ONCE (and never re-deriving it) dropped
    # EVERY live event until exchange time reached the seeded hour — up to 59:59, on all 10 pairs and
    # both kinds — while the dead-man's switch stayed green. Stepping the clock correct did not heal
    # it. The writer must take its hour from the events, which carry the exchange's own clock.
    clock.now = _ts(11, 35)  # the RTC leads by 90 minutes at the instant of construction...
    w = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(10, 5)  # ... and chrony steps it correct a moment later

    for i in range(60):
        w.append(_hour10_event(i, i))
    w.append(_book_event(11, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(60))


def test_a_leading_clock_cannot_publish_the_hour_still_in_progress(tmp_path, clock):
    # The same bad clock, the other artifact: a construction sweep keyed on the WALL-CLOCK hour
    # merged and sha256-blessed the hour STILL IN PROGRESS — publishing a truncated hour as a
    # complete, verify-clean segment, and then dropping the rest of that hour's live rows as "late".
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w1.append(_hour10_event(i, i))
    del w1  # hard crash, mid-hour-10

    clock.now = _ts(11, 1)  # the restart's clock leads by 5 minutes: exchange time is still 10:56
    w2 = _new_writer(tmp_path, flush_rows=5)
    assert not _segment_path(tmp_path, 10).exists()  # nothing on disk says hour 10 is over

    clock.now = _ts(10, 56)  # chrony steps it back
    for i in range(20, 40):
        w2.append(_hour10_event(i, i))
    w2.append(_book_event(11, 0))

    df = pl.read_parquet(_segment_path(tmp_path, 10))
    assert df["checksum"].to_list() == list(range(40))  # the whole hour, not the pre-crash prefix
    assert verify_manifest(_segment_path(tmp_path, 10)) is True


def test_an_implausible_far_future_ts_cannot_brick_the_writer(tmp_path):
    # Rotation follows the event's own ts, so one garbage-but-parseable far-future stamp finalized
    # the live hour early and then had the late-event guard drop every genuine row after it — for
    # the life of the process. Our clock and the stream itself BOTH call this stamp garbage.
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


@pytest.mark.parametrize("history", ["cold-start", "after-a-long-outage"])
def test_a_lagging_clock_can_never_black_out_the_stream(tmp_path, clock, history):
    # `_implausible` needs TWO witnesses, and the stream's one is `_max_ts` — which a DROPPED event
    # never advances. So if the clock is ever the sole witness, a clock lagging by more than
    # MAX_TS_AHEAD rejects the first live event, and then every one after it, forever. (chrony only
    # *slews* an offset that appears after startup, so the lag can last hours, and `Restart=always`
    # re-enters the state on every restart.) There are exactly two ways to have no second witness:
    # a brand-new stream, and — if the witness is seeded off disk — an outage longer than the seed's
    # own resolution, which is precisely the reboot this whole fix exists for. So: no witness, no
    # drop. The clock is never allowed to judge live data on its own.
    if history == "after-a-long-outage":
        w1 = _new_writer(tmp_path, flush_rows=5)
        w1.append(_book_event(2, 0, checksum=1))
        w1.append(_book_event(3, 0, checksum=2))  # hour 2 committed, then the daemon is down for hours
        del w1

    clock.now = _ts(7, 0)  # the restart's clock lags by ~4 hours
    w2 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w2.append(_book_event(11, i // 60, i % 60, checksum=100 + i))
    w2.append(_book_event(12, 0))

    assert pl.read_parquet(_segment_path(tmp_path, 11))["checksum"].to_list() == list(range(100, 120))


def test_a_quiet_stream_is_never_bricked_by_the_plausibility_guard(tmp_path, clock):
    # The other half of the same guard. A thin EUR alt can go hours without a print, so bounding an
    # event's ts against the LAST ACCEPTED ts alone would reject the next genuine trade — and, since
    # the reference could then never advance again, every trade after it, silently and forever.
    # The wall clock is the second witness, and it says this print is happening right now.
    clock.now = _ts(10, 5)
    w = _new_trade_writer(tmp_path, flush_rows=5)
    w.append(_trade_event(10, 0, 1))  # a print, and then 4.5 hours of silence on the pair
    clock.now = _ts(14, 30)
    w.append(_trade_event(14, 15 * 60, 2))  # 4h15m past the last accepted ts, but genuinely live
    clock.now = _ts(15, 5)
    w.append(_trade_event(15, 0, 3))

    assert pl.read_parquet(_segment_path(tmp_path, 14, "trades"))["trade_id"].to_list() == [2]


# --- T0026: a reconnect replays recent trade prints ---------------------------------------------


def test_a_replayed_trade_print_is_deduped_not_duplicated(tmp_path):
    # On every (re)connect `ws_client` resubscribes with snapshot=True, so Kraken REPLAYS its recent
    # prints. Their ts is inside the open hour, so the hour-granular late-event guard accepts them —
    # and they landed in the segment TWICE. (The pre-T0036 writer hid this by clobbering the earlier
    # parts, i.e. by losing rows instead.) trade_id is globally unique: a print already in the open
    # hour — including one only a PREVIOUS process wrote — is recognized and dropped.
    w1 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(20):  # trade_ids 0..19, all flushed to parts
        w1.append(_trade_event(10, i, i))
    del w1  # hard crash at 10:00:19

    w2 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(10, 30):  # the resubscribe: 10..19 are REPLAYS of rows already on disk...
        w2.append(_trade_event(10, i, i))  # ... 20..29 are prints we would otherwise never have seen
    w2.append(_trade_event(11, 0, 999))

    path = _segment_path(tmp_path, 10, "trades")
    assert pl.read_parquet(path)["trade_id"].to_list() == list(range(30))  # each print exactly once
    assert verify_manifest(path) is True


def test_a_replayed_print_cannot_reopen_a_committed_hour(tmp_path):
    # Same replay, one boundary later: hour 10 is COMMITTED — its `<HH>.parquet` is on disk, which is
    # the writer's entire definition of "closed". The replayed prints must be dropped, not written
    # into a part beside the committed final (where the next merge would fold them in as duplicates,
    # and re-bless the result). No clock is consulted: disk is the ground truth.
    w1 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w1.append(_trade_event(10, i, i))
    w1.append(_trade_event(11, 0, 100))  # an exchange-time hour-11 print COMMITS hour 10
    del w1

    path = _segment_path(tmp_path, 10, "trades")
    assert verify_manifest(path) is True

    w2 = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(15, 20):  # the resubscribe's replayed pre-boundary prints
        w2.append(_trade_event(10, i, i))
    assert not w2._buffer  # not even buffered: the hour is over
    assert not list(path.parent.glob("10.part*.parquet"))  # never written beside the closed hour

    for i in range(101, 111):
        w2.append(_trade_event(11, i - 100, i))
    w2.append(_trade_event(12, 0, 200))

    assert pl.read_parquet(path)["trade_id"].to_list() == list(range(20))  # the closed hour is intact
    assert verify_manifest(path) is True
    assert pl.read_parquet(_segment_path(tmp_path, 11, "trades"))["trade_id"].to_list() == list(range(101, 111))
