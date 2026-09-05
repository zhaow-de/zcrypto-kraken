import hashlib
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl
import pytest

from cli.capture import segment_writer
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, LIQ_AGG_SCHEMA, TRADE_SCHEMA, HourOracle, SegmentWriter, verify_manifest


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


def _segment_path(base_dir, hour: int, kind: str = "book", pair: str = "BTC/EUR"):
    return base_dir / pair / kind / "2026" / "07" / "08" / f"{hour:02d}.parquet"


def _corrupt_body(path: Path) -> None:
    """Destroy a parquet file's data pages while leaving its footer (and trailing magic) intact — the shape
    bit-rot and a partially-written page take, and one a footer-only check (`collect_schema()`) passes happily.
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
    """Pin `_utcnow()` an hour ahead of the events the tests feed, so an ordinary event is plausible and only
    a genuinely far-future one is not.

    A test that feeds events across a LONG stream gap must advance this clock as real time would:
    `_implausible`'s stream witness measures the stream against the clock's RATE, so a frozen clock plus a
    stream that jumps an hour is, correctly, a suspicious combination.
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
    # An empty (or unparseable) sidecar is a MISSING one, not a mismatch.
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
# Every state below is built by driving the real writer and then restoring the exact bytes a kill
# would have left.


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
    # The one genuinely AMBIGUOUS state, byte-indistinguishable between its two readings: "partial-final",
    # where the parts hold rows the final does not (merging is right), and "already-merged", where the final
    # already holds them (merging duplicates the hour and a fresh sha256 certifies the duplicate). Either
    # guess destroys the hour in the other reading, so the writer touches NOTHING and says so.
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
    # The hottest write in the daemon (every `flush_rows` rows) and, unguarded, one OSError away from taking
    # down the single consumer task — i.e. capture for every pair and both kinds. This buffer is lost either
    # way; the other streams need not be.
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
    # zcrypto-capture.service has no `After=time-sync.target` and `Restart=always`, so a writer can be
    # constructed in the instant before chrony's first step, with the host clock reading an hour or more
    # ahead. The writer must take its hour from the events, which carry the exchange's own clock — never
    # from a clock read once at construction and never re-derived.
    clock.now = _ts(11, 35)  # the RTC leads by 90 minutes at the instant of construction...
    w = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(10, 5)  # ... and chrony steps it correct a moment later

    for i in range(60):
        w.append(_hour10_event(i, i))
    clock.now = _ts(11, 0)  # time passes, as it does: the corrected clock reaches the boundary too
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
    # The clock is the sole witness for a stream's first event — at a cold start, and after an outage longer
    # than any disk-seeded stream witness's resolution — so a clock lagging by more than MAX_TS_AHEAD refuses
    # that event, and a dropped event never advances the stream witness. The cap bounds the cost at
    # MAX_CONSECUTIVE_DROPS rows: the guard then stands down, the stream is accepted, and the two witnesses
    # re-anchor.
    if history == "after-a-long-outage":
        w1 = _new_writer(tmp_path, flush_rows=5)
        w1.append(_book_event(2, 0, checksum=1))
        w1.append(_book_event(3, 0, checksum=2))  # hour 2 committed, then the daemon is down for hours
        del w1

    clock.now = _ts(7, 0)  # the restart's clock lags by ~4 hours
    w2 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        w2.append(_book_event(11, i // 60, i % 60, checksum=100 + i))
    clock.now = _ts(8, 0)  # time passes; the clock still lags by the same ~4 hours
    w2.append(_book_event(12, 0))

    kept = pl.read_parquet(_segment_path(tmp_path, 11))["checksum"].to_list()
    assert kept == list(range(100 + segment_writer.MAX_CONSECUTIVE_DROPS, 120))  # the cap's cost, and no more
    assert kept[-1] == 119  # the stream is alive and stays alive — never blacked out


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


# --- what recovery is allowed to TRUST -----------------------------------------------------------


@pytest.mark.parametrize("damage", ["bit-rot", "truncated"])
def test_an_unreadable_merging_file_is_quarantined_and_the_hour_rebuilt_from_its_parts(tmp_path, damage):
    # `_commit` hashes the merging file, unlinks the parts and renames it onto the final — decoding NOTHING —
    # so it is the one input the protocol trusts without reading, and the one it uses to justify deleting the
    # only other copy. Read it first: if it does not decode, quarantine it (never delete) and let the hour be
    # rebuilt from the parts, which are right there and readable.
    hour_dir = _crash_inside_merge(tmp_path, stage="unlink")  # parts + .merging, the kill window
    merging = hour_dir / "10.parquet.merging"
    if damage == "bit-rot":
        _corrupt_body(merging)
    else:
        merging.write_bytes(merging.read_bytes()[:20])

    w = _new_writer(tmp_path, flush_rows=5)  # construction must NOT commit it
    w.append(_book_event(11, 0, checksum=999))  # ... and the sweep rebuilds the hour from the parts

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # zero rows lost
    assert verify_manifest(path) is True  # and the sidecar blesses the REBUILT hour, not the rot
    assert (hour_dir / "10.parquet.merging.corrupt").exists()  # evidence, kept
    assert not list(hour_dir.glob("*.merging"))
    assert not list(hour_dir.glob("10.part*.parquet"))  # consumed by the rebuild, not by the rot


def test_an_unremovable_tmp_file_cannot_crash_loop_the_daemon(tmp_path):
    # A read-only remount — the aftermath of the very ENOSPC condition DiskWatermark exists for — makes
    # `_recover`'s `.tmp` unlink raise, and `__init__` runs for every stream before the daemon connects, so a
    # raise there crash-loops the whole capture. A leftover tmp is re-derivable garbage; failing to delete it
    # is not worth the daemon.
    hour_dir = _segment_path(tmp_path, 10).parent
    hour_dir.mkdir(parents=True)
    (hour_dir / "10.part0000.parquet.tmp").write_bytes(b"half a part")
    hour_dir.chmod(0o500)  # r-x: the file cannot be unlinked from here
    try:
        w = _new_writer(tmp_path, flush_rows=5)  # must not raise
        w.append(_book_event(11, 0, checksum=1))  # nor may this
    finally:
        hour_dir.chmod(0o700)

    assert (hour_dir / "10.part0000.parquet.tmp").exists()  # left behind, logged — but nothing died


# --- what the plausibility guard is allowed to accept, and what it may never cost ----------------


def test_a_bogus_stamp_inside_the_old_window_cannot_truncate_the_live_hour(tmp_path, clock):
    # A stamp ahead of BOTH witnesses must be refused: the window has to be narrow enough that one corrupt
    # `11:00` stamp cannot rotate the LIVE hour and publish it, manifest-verified, as a "committed and
    # complete" segment holding only its first five minutes.
    clock.now = _ts(10, 5)
    w = _new_writer(tmp_path, flush_rows=5)
    for i in range(5):
        w.append(_hour10_event(i * 60, i))  # 10:00 .. 10:04 — the live hour so far
    w.append(_book_event(11, 0, checksum=999))  # the bogus stamp: 56 min ahead of the stream AND the clock
    for i in range(5, 60):
        clock.now = _ts(10, i)
        w.append(_hour10_event(i * 60, i))  # 10:05 .. 10:59 — the rest of the live hour
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=1000))  # the GENUINE boundary

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))  # the whole hour, not 5 minutes of it
    assert verify_manifest(path) is True


def test_a_garbage_first_stamp_after_a_restart_cannot_black_out_the_stream(tmp_path, clock):
    # With no stream witness yet, the clock alone judges the first event after a restart — bounded by the drop
    # cap, so it can never be the sole judge for more than a moment. Unjudged, one garbage far-future stamp
    # opens the hour in the future and the late-event guard drops every genuine row behind it.
    clock.now = _ts(10, 5)
    w = _new_writer(tmp_path, flush_rows=5)
    w.append(_book_event(23, 59, checksum=999))  # the very first event: garbage
    for i in range(20):
        w.append(_hour10_event(i, i))
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=1000))

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20))  # every genuine row kept
    assert not _segment_path(tmp_path, 23).exists()  # and the garbage hour was never opened
    assert not list(path.parent.glob("23.part*.parquet"))


def test_a_coherently_garbage_stream_can_never_be_written_to_the_archive(tmp_path, clock):
    # A COHERENTLY wrong stream — a `_parse_ts` unit bug, an exchange-side clock fault — advances at the
    # normal rate, so the stream witness is satisfied by construction and a run of it stands the drop cap
    # down. MAX_TS_ABSURD is checked before the cap and answers to no witness: a ts a DAY ahead of our clock
    # is not data under any reading, and a clock is wrong by minutes or hours, never by days.
    clock.now = _ts(10, 5)
    w = _new_writer(tmp_path, flush_rows=5)
    garbage = datetime(2030, 7, 8, 1, 0, tzinfo=timezone.utc)
    for i in range(10):  # a systematic source: ten coherent, normally-advancing garbage stamps
        w.append({**_book_event(10, 0, checksum=900 + i), "ts": garbage + timedelta(seconds=i)})
    for i in range(20):  # ... and the genuine live stream, still flowing underneath it
        w.append(_hour10_event(i, i))
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=1000))

    assert w._current_hour == _ts(11, 0)  # the far-future hour was NEVER opened
    assert not list(tmp_path.rglob("2030/**/*.parquet"))  # and nothing of it reached the archive
    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(20))


def test_a_future_dated_final_can_never_brick_the_stream(tmp_path, clock):
    # The poison pill. A far-future `<HH>.parquet` (what one accepted garbage stamp leaves behind)
    # seeds `_floor` on EVERY future restart — so every genuine event is dropped as "late", forever,
    # on every restart, until a human finds the file. An hour that has not happened yet cannot have
    # been committed: a future-dated final is nonsense and is ignored, loudly.
    clock.now = _ts(10, 5)
    future_dir = tmp_path / "BTC/EUR" / "book" / "2027" / "01" / "01"
    future_dir.mkdir(parents=True)
    pl.DataFrame([_book_event(10, 0, checksum=1)], schema=BOOK_SCHEMA).write_parquet(future_dir / "01.parquet", compression="zstd")

    w = _new_writer(tmp_path, flush_rows=5)
    assert w._floor is None  # the nonsense final is not "the newest closed hour"
    for i in range(20):
        w.append(_hour10_event(i, i))
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=1000))

    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(20))
    assert (future_dir / "01.parquet").exists()  # ignored, never deleted — it is evidence


def test_a_quiet_pair_under_a_lagging_clock_loses_nothing(tmp_path, clock):
    # Where the two failure modes MEET: a pair quiet for longer than the window (routine overnight on a thin
    # EUR alt) fires the stream witness, a clock lagging by more than the window fires the clock witness, and
    # a dropped event never advances `_max_ts`. Carrying `_max_ts` forward by the ELAPSED time cancels the
    # constant offset a wrong clock is, so nothing is lost.
    clock.now = _ts(9, 50)  # the host clock lags a steady 10 minutes, all the way through
    w = _new_trade_writer(tmp_path, flush_rows=5)
    for i in range(segment_writer.MAX_CONSECUTIVE_DROPS + 1):
        w.append(_trade_event(10, i, i))  # the day's first prints — they anchor the stream witness
    clock.now = _ts(14, 20)  # ... and then 4.5 hours of silence on the pair (it is really 14:30)
    for i in range(10):
        w.append(_trade_event(14, 30 * 60 + i, 100 + i))  # 14:30:00.. — genuine, live prints
    clock.now = _ts(15, 20)
    w.append(_trade_event(15, 30 * 60, 999))

    ids = pl.read_parquet(_segment_path(tmp_path, 14, "trades"))["trade_id"].to_list()
    assert ids == list(range(100, 110))  # every genuine print, not one dropped


def test_a_clock_step_costs_a_bounded_few_rows_and_never_the_stream(tmp_path, clock):
    # A clock that STEPS (chrony's first correction) breaks the rate assumption for exactly one interval, and
    # a dropped event never advances the reference — so without a cap that one interval would black the pair
    # out FOREVER. The cap stands the guard down, the first accepted event re-anchors it, and the loss is
    # bounded.
    clock.now = _ts(10, 0)  # a correct clock: the print below anchors both witnesses
    w = _new_trade_writer(tmp_path, flush_rows=5)
    w.append(_trade_event(10, 0, 1))
    clock.now = _ts(14, 0)  # the pair goes quiet, and chrony STEPS the clock back 30 min (it is 14:30)
    for i in range(10):
        w.append(_trade_event(14, 30 * 60 + i, 100 + i))
    clock.now = _ts(15, 0)
    w.append(_trade_event(15, 30 * 60, 999))

    ids = pl.read_parquet(_segment_path(tmp_path, 14, "trades"))["trade_id"].to_list()
    assert ids  # the pair is NOT blacked out ...
    assert ids[-1] == 109  # ... and it stays alive: re-anchored, the guard never fires again
    assert len(ids) == 10 - segment_writer.MAX_CONSECUTIVE_DROPS  # the loss is exactly the cap


# --- T0026: a reconnect replays recent trade prints ---------------------------------------------


def test_a_replayed_trade_print_is_deduped_not_duplicated(tmp_path):
    # On every (re)connect `ws_client` resubscribes with snapshot=True, so Kraken REPLAYS its recent prints,
    # whose ts is inside the open hour where the hour-granular late-event guard accepts them. trade_id is
    # globally unique: a print already in the open hour — including one only a PREVIOUS process wrote — is
    # recognized and dropped.
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


# --- T0037: cross-stream quorum — one untrusted `ts` can never rotate the hour ------------------
#
# A row for an hour the `HourOracle` has not confirmed is HELD, never dropped, so the live hour stays
# open and no genuine row behind a bogus stamp is ever refused. Loss is measured as a set-difference
# off disk (parts + finals), never predicted.


def _book_event_for(pair: str, hour: int, minute: int = 0, sec: int = 0, *, checksum: int = 42) -> dict:
    return {
        "ts": _ts(hour, minute, sec),
        "symbol": pair,
        "type": "update",
        "side": "bid",
        "price": 100.0,
        "qty": 1.0,
        "checksum": checksum,
    }


def _oracle_writer(tmp_path, oracle, *, pair="BTC/EUR", kind="book", schema=BOOK_SCHEMA, flush_rows=5, dedup_key=None):
    return SegmentWriter(tmp_path, pair, kind, schema, flush_rows=flush_rows, dedup_key=dedup_key, oracle=oracle)


def _disk_column(tmp_path, column: str, *, pair="BTC/EUR", kind="book") -> list:
    """Every value of `column` across every parquet on disk for the stream — parts AND finals. This
    is the ground truth for loss: a merge unlinks the parts it consumes, so nothing is double-counted
    within an hour, and a held/spilled hour contributes its parts. Loss is a set-difference off this."""
    files = sorted((tmp_path / pair / kind).rglob("*.parquet"))
    if not files:
        return []
    return pl.concat([pl.read_parquet(f) for f in files])[column].to_list()


def test_t0037_lone_in_window_bogus_stamp_never_truncates_the_live_hour(tmp_path, clock):
    # THE core residual (T0037): a bogus stamp <=5 min ahead, landing in the last 5 min of the hour, is inside
    # the plausibility window, so `_implausible` passes it. A single stream cannot second its own stamp: the
    # bogus 11:00 is HELD, hour 10 stays open, and every later genuine row lands.
    oracle = HourOracle()
    w = _oracle_writer(tmp_path, oracle)
    genuine = set()
    for mnt in range(0, 57):  # 10:00 .. 10:56 — the live hour so far
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(10, 56, 30)
    w.append(_book_event(11, 0, checksum=999))  # the bogus stamp: 3.5 min ahead — inside the window
    for mnt in (57, 58, 59):  # the rest of the live hour — pre-fix these were dropped as "late"
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)

    # The bogus stamp corroborated nothing, so hour 10 is STILL OPEN — not finalized, not published.
    assert not _segment_path(tmp_path, 10).exists()
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=100))  # a genuine hour-11 print — still only ONE witness
    assert not _segment_path(tmp_path, 10).exists()  # a lone stream cannot confirm its own boundary

    # The second witness arrives: the handicapped clock reaches 11:05, and the next event drains the
    # held hour-11 rows and finalizes hour 10 — publishing it whole for the first time.
    clock.now = _ts(11, 5)
    w.append(_book_event(11, 5, checksum=105))
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))  # the WHOLE hour, in order
    assert verify_manifest(path) is True
    w.close()

    # Zero genuine rows lost, and the bogus row is STORED in the hour its ts names (never deleted).
    survived = set(_disk_column(tmp_path, "checksum"))
    assert genuine <= survived
    hour11_parts = sorted(_segment_path(tmp_path, 11).parent.glob("11.part*.parquet"))
    hour11_cs = pl.concat([pl.read_parquet(p) for p in hour11_parts])["checksum"].to_list()
    assert 999 in hour11_cs  # the bogus 11:00 row lands in hour 11, its named hour — not deleted


def test_t0037_a_bogus_first_stamp_after_restart_cannot_sweep_publish_the_live_hour(tmp_path, clock):
    # The restart shape: a previous process left hour-10 parts (crash mid-hour) and exchange time is still
    # inside hour 10, so a bogus in-window first stamp would drive the startup SWEEP into publishing the live
    # hour truncated. The first `_enter_hour` is behind the oracle gate, so the garbage stamp is HELD and the
    # sweep never runs on it.
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # cs 0..19 flushed to 4 parts, hour 10 still live
        clock.now = _ts(10, i)
        w1.append(_book_event(10, i, checksum=i))
    del w1  # hard crash

    clock.now = _ts(10, 57)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(11, 0, checksum=999))  # the very first event of the new process: bogus

    assert w2._current_hour is None  # nothing was entered — the bogus is held, the sweep never ran
    assert not _segment_path(tmp_path, 10).exists()  # the live hour was NOT sweep-published
    assert len(list(_segment_path(tmp_path, 10).parent.glob("10.part*.parquet"))) == 4  # parts untouched

    for mnt in (57, 58, 59):  # the genuine rest of hour 10 — must be admitted, not dropped as late
        clock.now = _ts(10, mnt)
        w2.append(_book_event(10, mnt, checksum=20 + (mnt - 57)))
    clock.now = _ts(11, 0)
    w2.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    w2.append(_book_event(11, 5, checksum=105))  # the clock seconds hour 11 -> hour 10 finalizes

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(20)) + [20, 21, 22]  # every row
    assert verify_manifest(path) is True


def test_t0037_a_genuine_boundary_with_two_streams_publishes_within_one_event(tmp_path, clock):
    # The property a single bad field can never forge: AGREEMENT. The clock here LAGS by 4 min (inside the
    # window, so nothing is dropped), so `clock - CLOCK_WITNESS_MARGIN` can never reach 11:00 while the two
    # streams do — the corroboration here is the OTHER STREAM, not the clock.
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="BTC/EUR")
    b = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")

    def feed(w, pair, hour, minute, cs):
        clock.now = _ts(hour, minute) - timedelta(minutes=4)  # a steady 4-min lag: a constant offset
        w.append(_book_event_for(pair, hour, minute, checksum=cs))

    feed(a, "BTC/EUR", 10, 0, 0)  # A's first — held (only A witnessed, clock lags)
    feed(b, "ETH/EUR", 10, 0, 10)  # B seconds hour 10 -> B admits
    feed(a, "BTC/EUR", 10, 20, 1)  # A drains its held cs0, admits cs1
    feed(b, "ETH/EUR", 10, 20, 11)
    feed(a, "BTC/EUR", 10, 59, 2)
    feed(b, "ETH/EUR", 10, 59, 12)

    feed(a, "BTC/EUR", 11, 0, 3)  # A crosses first — only ONE stream at 11:00, hour 11 not confirmed
    assert not _segment_path(tmp_path, 10, pair="BTC/EUR").exists()  # A holds; its hour 10 stays open

    feed(b, "ETH/EUR", 11, 0, 13)  # B crosses — now TWO streams agree on 11:00, and the clock lags
    assert _segment_path(tmp_path, 10, pair="ETH/EUR").exists()  # B's hour 10 publishes on this event
    assert not _segment_path(tmp_path, 10, pair="BTC/EUR").exists()  # A's follows on A's next event

    feed(a, "BTC/EUR", 11, 1, 4)  # A's next event drains its held cs3 and finalizes A's hour 10
    a.close()
    b.close()
    assert pl.read_parquet(_segment_path(tmp_path, 10, pair="BTC/EUR"))["checksum"].to_list() == [0, 1, 2]
    assert pl.read_parquet(_segment_path(tmp_path, 10, pair="ETH/EUR"))["checksum"].to_list() == [10, 11, 12]
    assert verify_manifest(_segment_path(tmp_path, 10, pair="BTC/EUR")) is True
    assert verify_manifest(_segment_path(tmp_path, 10, pair="ETH/EUR")) is True


def _drive_lagging_clock_run(tmp_path, oracle, clock):
    """A cold start under a 10-min lagging clock, then hour-11 traffic, a boundary and close(). The
    guard's cold-start cap is what drops the first few rows — identically with or without the oracle,
    since the oracle sits BEHIND the guard. Returns the surviving checksum set off disk."""
    w = _oracle_writer(tmp_path, oracle)
    for i in range(20):  # 11:00:00 .. 11:00:19, one distinct ts each (so the drop-cap can advance)
        clock.now = _ts(11, 0, i) - timedelta(minutes=10)
        w.append(_book_event(11, 0, i, checksum=100 + i))
    clock.now = _ts(12, 0) - timedelta(minutes=10)
    w.append(_book_event(12, 0, checksum=200))  # a boundary
    w.close()
    return set(_disk_column(tmp_path, "checksum"))


def test_t0037_a_lagging_clock_adds_no_loss_over_the_oracle_free_baseline(tmp_path, clock):
    # Criterion (2): the oracle must never DARKEN a stream — under a lagging clock it must lose
    # EXACTLY what the oracle-free writer loses, no more. Both drop only the guard's cold-start cap
    # (a dropped event never advances the stream witness, so the cap re-anchors it); the oracle adds
    # zero. Asserted as set-EQUALITY against the real baseline, not against a hand-computed constant.
    base_dir = tmp_path / "baseline"
    orac_dir = tmp_path / "oracle"
    base_dir.mkdir()
    orac_dir.mkdir()

    baseline = _drive_lagging_clock_run(base_dir, None, clock)  # oracle=None == the 189a56a writer
    with_oracle = _drive_lagging_clock_run(orac_dir, HourOracle(), clock)

    assert with_oracle == baseline  # identical survivors — the oracle costs nothing under a lag
    assert baseline == set(range(100 + segment_writer.MAX_CONSECUTIVE_DROPS, 120)) | {200}  # only the cap


def test_t0037_a_leading_clock_never_publishes_the_hour_early(tmp_path, clock):
    # The other clock fault: a clock LEADING by 10 min. The handicapped clock witness (`clock - 5m`)
    # then reads 11:00 while exchange time is only 10:55 — but it is only ONE witness, and the stream
    # is the other, still at 10:55. So hour 11 cannot confirm until the STREAM genuinely crosses:
    # a leading clock can never finalize (and truncate) hour 10 early, and loses nothing.
    oracle = HourOracle()
    w = _oracle_writer(tmp_path, oracle)
    for mnt in range(0, 60):  # a full genuine hour 10, clock leading 10 min throughout
        clock.now = _ts(10, mnt) + timedelta(minutes=10)
        w.append(_book_event(10, mnt, checksum=mnt))
    # The clock says 11:09, but no hour-11 EVENT has arrived — hour 10 must still be open.
    assert not _segment_path(tmp_path, 10).exists()

    clock.now = _ts(11, 0) + timedelta(minutes=10)
    w.append(_book_event(11, 0, checksum=100))  # the genuine crossing — NOW hour 11 is corroborated
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))  # whole hour, zero loss
    assert verify_manifest(path) is True


def test_t0037_three_escalating_in_window_stamps_on_one_stream_lose_nothing(tmp_path, clock):
    # A burst of escalating bogus stamps, each a little further ahead but all inside the 5-min window, on ONE
    # stream — the shape that defeats any design corroborating WITHIN the stream. The second witness is
    # another stream or the handicapped clock, so one stream's escalating stamps confirm NOTHING.
    oracle = HourOracle()
    w = _oracle_writer(tmp_path, oracle)
    genuine = set()
    for mnt in range(0, 56):
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    escalating = [(_ts(10, 56, 0), _ts(11, 0, 0), 900), (_ts(10, 57, 0), _ts(11, 2, 0), 901), (_ts(10, 58, 0), _ts(11, 4, 0), 902)]
    tail = [56, 57, 58, 59]
    for i, (wall, bogus_ts, cs) in enumerate(escalating):
        clock.now = wall
        w.append({**_book_event(10, 0, checksum=cs), "ts": bogus_ts})  # escalating bogus
        clock.now = _ts(10, tail[i])
        w.append(_book_event(10, tail[i], checksum=tail[i]))  # a genuine row right after it
        genuine.add(tail[i])
    clock.now = _ts(10, 59)
    w.append(_book_event(10, 59, checksum=59))
    genuine.add(59)

    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    w.append(_book_event(11, 5, checksum=105))  # the clock seconds hour 11 -> hour 10 finalizes
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))  # not one genuine row lost
    assert verify_manifest(path) is True
    w.close()
    assert genuine <= set(_disk_column(tmp_path, "checksum"))


def test_t0037_a_stand_down_burst_never_publishes_the_future_hour(tmp_path, clock):
    # A burst of far-future stamps stands the plausibility guard down (MAX_CONSECUTIVE_DROPS), so the stamps
    # after the cap slip past it. The ORACLE holds them: the future hour is never confirmed, so it is never
    # published, and the genuine live stream underneath loses nothing.
    clock.now = _ts(10, 5)
    w = _oracle_writer(tmp_path, oracle=HourOracle())
    for i in range(5):  # five distinct far-future stamps: 3 caught by the cap, 2 slip the stood-down guard
        w.append({**_book_event(10, 0, checksum=800 + i), "ts": _ts(15, i)})
    genuine = set()
    for i in range(20):  # the genuine live stream, still flowing under the burst
        clock.now = _ts(10, 5) + timedelta(seconds=i)
        w.append(_book_event(10, 5, i, checksum=i))
        genuine.add(i)
    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    w.append(_book_event(11, 5, checksum=105))  # hour 10 finalizes; hour 15 stays held
    w.close()

    assert not _segment_path(tmp_path, 15).exists()  # the future hour is NEVER published as a final
    assert not list((tmp_path / "BTC/EUR" / "book" / "2026" / "07" / "08").glob("15.parquet"))
    assert genuine <= set(_disk_column(tmp_path, "checksum"))  # the live stream lost nothing


def test_t0037_a_lone_stream_rotation_is_clock_paced_and_never_lost(tmp_path, clock):
    # S8: one live stream (a single pair whose trades fall silent across the boundary). With no second
    # STREAM to second the boundary, rotation is paced by the handicapped clock — bounded to
    # CLOCK_WITNESS_MARGIN (300 s) — and a lone print in an otherwise empty hour is admitted (never
    # lost) the moment the clock confirms. Nothing is darkened; the rotation is merely a little later.
    clock.now = _ts(10, 0)
    w = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, dedup_key="trade_id")
    w.append(_trade_event(10, 0, 1))  # THE lone print of hour 10, then the pair goes quiet

    clock.now = _ts(11, 0)
    w.append(_trade_event(11, 0, 2))  # crosses the boundary; the lone hour-10 print is drained/admitted
    assert not _segment_path(tmp_path, 10, "trades").exists()  # not published — clock only reads 10:55

    clock.now = _ts(11, 4)
    w.append(_trade_event(11, 4 * 60, 3))
    assert not _segment_path(tmp_path, 10, "trades").exists()  # still within the 5-min margin: held

    clock.now = _ts(11, 5)  # the margin elapses -> the clock seconds hour 11
    w.append(_trade_event(11, 5 * 60, 4))
    path = _segment_path(tmp_path, 10, "trades")
    assert pl.read_parquet(path)["trade_id"].to_list() == [1]  # the lone print, published, never lost
    assert verify_manifest(path) is True
    w.close()
    assert {1, 2, 3, 4} <= set(_disk_column(tmp_path, "trade_id", kind="trades"))


def test_t0037_close_spills_held_rows_that_a_restart_redeems_merges_and_dedups(tmp_path, clock):
    # close() must not lose held rows, and must not FINALIZE (T0036 intact): the held rows become
    # HELD-SPILL files of the hour their ts names — quarantine, invisible to the sweep. A restart
    # that genuinely opens the hour redeems them into parts and merges them, and a replay of a held
    # print is deduped via the part-seeded `_seen` — no loss, no duplicate.
    clock.now = _ts(10, 3)
    w1 = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, dedup_key="trade_id")
    for i in range(3):  # held (a lone stream, clock < 10:05 -> hour 10 not yet confirmed)
        w1.append(_trade_event(10, i, i))
    assert w1._held  # the rows are held, not admitted
    w1.close()

    trades_dir = _segment_path(tmp_path, 10, "trades").parent
    assert not _segment_path(tmp_path, 10, "trades").exists()  # close() never finalizes
    spilled = pl.concat([pl.read_parquet(p) for p in trades_dir.glob("10.held*.parquet")])
    assert sorted(spilled["trade_id"].to_list()) == [0, 1, 2]  # the held rows are safe on disk, quarantined

    clock.now = _ts(10, 6)
    w2 = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, dedup_key="trade_id")
    for i in (1, 2):  # the resubscribe REPLAYS held prints already on disk
        w2.append(_trade_event(10, i, i))
    for i in (3, 4):  # ... and genuinely new prints
        w2.append(_trade_event(10, i, i))
    clock.now = _ts(11, 0)
    w2.append(_trade_event(11, 0, 100))
    clock.now = _ts(11, 5)
    w2.append(_trade_event(11, 5 * 60, 101))  # confirm hour 11 -> hour 10 finalizes
    w2.close()

    path = _segment_path(tmp_path, 10, "trades")
    ids = pl.read_parquet(path)["trade_id"].to_list()
    assert sorted(ids) == [0, 1, 2, 3, 4]  # the spilled parts merged, replays deduped — no dup, no loss
    assert len(ids) == len(set(ids))
    assert verify_manifest(path) is True


def test_t0037_a_held_hour_above_the_event_hour_is_not_drained_out_of_order(tmp_path, clock):
    # The load-bearing drain bounds: held hours drain ASCENDING, and only those `h <= event_hour` (draining a
    # higher held hour on a lower-hour event would misfile the current row) and `h <= confirmed`. So a bogus
    # hour-11 row waits for a genuine hour-11 event, while the cold start's hour-10 rows drain in ARRIVAL
    # order ahead of the confirming event.
    oracle = HourOracle()
    w = _oracle_writer(tmp_path, oracle)
    for mnt in range(0, 3):  # 10:00..10:02 — held during the cold start (clock < 10:05)
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
    assert w._held  # all three are held, none admitted yet
    for mnt in range(3, 56):  # ... at 10:05 the clock confirms hour 10 and the held run drains ASCENDING
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))

    clock.now = _ts(10, 56, 30)
    w.append(_book_event(11, 0, checksum=999))  # a bogus hour-11 row — held
    for mnt in (56, 57, 58, 59):  # later hour-10 events must NOT drain the held hour-11 row (h > event_hour)
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
    assert not _segment_path(tmp_path, 10).exists()  # hour 10 never finalized by a lower-hour event

    clock.now = _ts(11, 0)
    w.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    w.append(_book_event(11, 5, checksum=105))
    path = _segment_path(tmp_path, 10)
    # Arrival order preserved through the cold-start drain (0..4 held, drained ascending) — never
    # interleaved with the bogus 999, which was held above the event hour and lands in hour 11.
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))
    w.close()


def test_t0037_a_poisoned_witness_can_never_second_a_lone_bogus_stamp(tmp_path, clock):
    # The T0037 truncation re-attacked through the oracle itself: a garbage burst on stream A stands its
    # plausibility guard down (MAX_CONSECUTIVE_DROPS), and the stamp that then slips through would set A's
    # shared witness ~20 h ahead — witnesses never expire — seconding a LONE in-window bogus stamp on B. An
    # unconfirmed stamp may vouch that time has reached T only while the wall clock is itself within
    # MAX_TS_AHEAD of T: witnesses are clamped at `now + MAX_TS_AHEAD` when observed, so A's burst vouches
    # for nothing beyond 10:25.
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")
    b = _oracle_writer(tmp_path, oracle)
    genuine = set()
    for mnt in range(0, 20):  # B's genuine live hour 10 begins
        clock.now = _ts(10, mnt)
        b.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(10, 20)
    for i in range(4):  # A's burst: 3 distinct stamps eaten by the run cap, the 4th slips through
        a.append({**_book_event_for("ETH/EUR", 10, 0, checksum=800 + i), "ts": _ts(10, 0) + timedelta(hours=20, minutes=i)})
    for mnt in range(20, 56):  # B's hour continues under the poisoned witness
        clock.now = _ts(10, mnt)
        b.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(10, 56, 30)
    b.append(_book_event(11, 0, checksum=999))  # the lone in-window bogus stamp on B
    assert not _segment_path(tmp_path, 10).exists()  # A's poisoned witness seconded NOTHING
    for mnt in (56, 57, 58, 59):  # pre-fix these were dropped as late — fed=60, LOST=[56..59]
        clock.now = _ts(10, mnt)
        b.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(11, 0)
    b.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    b.append(_book_event(11, 5, checksum=105))  # the clock seconds hour 11 -> hour 10 finalizes WHOLE
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(60))  # every genuine row
    assert verify_manifest(path) is True
    b.close()
    a.close()
    assert genuine <= set(_disk_column(tmp_path, "checksum"))


def test_t0037_a_replay_into_an_unconfirmed_hour_is_deduped_not_duplicated(tmp_path, clock):
    # T0026 x T0037: a reconnect replay landing while its hour is still UNCONFIRMED is held, and a stop before
    # confirmation spills it beside its original for the next process to merge into the committed,
    # manifest-certified final. Duplicated prints corrupt a reconstructed book exactly as badly as lost ones,
    # so held rows pass the same trade_id de-dup as stored ones.
    clock.now = _ts(10, 0, 30)
    w1 = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, flush_rows=50, dedup_key="trade_id")
    for i in range(5):
        w1.append(_trade_event(10, i, i))  # held: hour 10 is unconfirmed (lone stream, clock < 10:05)
    for i in range(5):
        w1.append(_trade_event(10, i, i))  # the reconnect REPLAYS the same prints into the hold window
    w1.close()  # stop before confirmation — the held rows spill to disk

    clock.now = _ts(10, 6)
    w2 = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, flush_rows=50, dedup_key="trade_id")
    w2.append(_trade_event(10, 6 * 60, 10))  # hour 10 confirms (stream + clock): the spill is picked up
    clock.now = _ts(11, 0)
    w2.append(_trade_event(11, 0, 100))
    clock.now = _ts(11, 5)
    w2.append(_trade_event(11, 5 * 60, 101))  # hour 11 confirmed -> hour 10 finalizes
    w2.close()

    ids = pl.read_parquet(_segment_path(tmp_path, 10, "trades"))["trade_id"].to_list()
    assert sorted(ids) == [0, 1, 2, 3, 4, 10]  # exactly ONE copy of every held print
    assert len(ids) == len(set(ids))


def test_t0037_a_replay_of_an_on_disk_print_never_survives_a_held_spill(tmp_path, clock):
    # The restart shape: the ORIGINAL prints are already in an on-disk part from the previous process, and the
    # replay lands while the hour is UNCONFIRMED (a restart inside the hour's first 5 minutes), is held, and
    # would be spilled beside its original. The hold path seeds its de-dup from the hour's on-disk files, so
    # the replay never reaches disk at all.
    oracle1 = HourOracle()
    a = _oracle_writer(tmp_path, oracle1, kind="trades", schema=TRADE_SCHEMA, flush_rows=50, dedup_key="trade_id")
    b = _oracle_writer(tmp_path, oracle1, pair="ETH/EUR")
    clock.now = _ts(10, 1)
    b.append(_book_event_for("ETH/EUR", 10, 1))  # a second stream seconds hour 10...
    a.append(_trade_event(10, 70, 1))  # ...so the prints are ADMITTED
    a.append(_trade_event(10, 80, 2))
    a.close()  # part [1, 2] on disk; the process dies

    clock.now = _ts(10, 3)  # restart INSIDE the hour's first 5 minutes: hour 10 unconfirmed again
    w2 = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, flush_rows=3, dedup_key="trade_id")
    for tid in (1, 2):  # Kraken replays the prints already on disk — held pre-fix, without de-dup
        w2.append(_trade_event(10, 60 + 10 * tid, tid))
    for tid in (3, 4, 5):  # ...and genuinely new prints; flush_rows=3 spills the hold to disk
        w2.append(_trade_event(10, 180 + tid, tid))
    clock.now = _ts(10, 6)
    w2.append(_trade_event(10, 6 * 60, 6))  # hour 10 confirms
    clock.now = _ts(11, 0)
    w2.append(_trade_event(11, 0, 100))
    clock.now = _ts(11, 5)
    w2.append(_trade_event(11, 5 * 60, 101))  # hour 10 finalizes
    w2.close()

    ids = pl.read_parquet(_segment_path(tmp_path, 10, "trades"))["trade_id"].to_list()
    assert sorted(ids) == [1, 2, 3, 4, 5, 6]  # the replays are recognized against the on-disk part
    assert len(ids) == len(set(ids))


def test_t0037_a_never_confirmed_held_spill_cannot_fabricate_an_hour(tmp_path, clock):
    # A never-confirmed held row spills under a held-spill name (`<HH>.held####`) that the sweep and the merge
    # ignore, and is redeemed as a part only when a live, quorum-confirmed event stream OPENS its hour —
    # otherwise a stop, then an outage across the stamp's hour, mints a manifest-certified final for an hour
    # that had NO genuine capture. Quarantined, never deleted.
    w = _oracle_writer(tmp_path, HourOracle())
    for mnt in range(0, 57):
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
    clock.now = _ts(10, 57)
    w.append(_book_event(11, 0, checksum=999))  # a lone in-window bogus stamp — held, unconfirmed
    w.close()  # the process stops, and stays down through the whole of hour 11

    clock.now = _ts(13, 30)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(13, 30, checksum=1))  # the first genuine event after the outage -> sweep

    path10 = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path10)["checksum"].to_list() == list(range(57))  # the genuine hour: swept
    assert verify_manifest(path10) is True
    assert not _segment_path(tmp_path, 11).exists()  # NO fabricated hour-11 final
    held = list(path10.parent.glob("11.held*.parquet"))
    assert held  # the bogus row is quarantined, never deleted...
    assert pl.read_parquet(held[0])["checksum"].to_list() == [999]  # ...and still readable, as evidence


def test_t0037_a_held_spill_never_marks_its_hour_closed(tmp_path, clock):
    # A held-spill file is quarantine, not a final: it must not seed the recovery floor (an hour is
    # closed by `<HH>.parquet` ALONE), or a restart would drop every genuine row of the very hour
    # the spill named — and when the hour IS genuinely captured, opening it redeems the spill, so
    # the quarantined row still lands in the hour its ts names, ahead of the new rows.
    clock.now = _ts(10, 57)
    w1 = _oracle_writer(tmp_path, HourOracle())
    w1.append(_book_event(11, 0, checksum=999))  # a lone in-window bogus stamp: held
    w1.close()  # spilled as a held-spill file

    clock.now = _ts(11, 30)  # restart inside hour 11 — the hour is genuinely live this time
    w2 = _oracle_writer(tmp_path, HourOracle())
    for mnt in (30, 31, 32):
        clock.now = _ts(11, mnt)
        w2.append(_book_event(11, mnt, checksum=mnt))  # must be admitted, not dropped as late
    clock.now = _ts(12, 0)
    w2.append(_book_event(12, 0, checksum=100))
    clock.now = _ts(12, 5)
    w2.append(_book_event(12, 5, checksum=105))  # hour 12 confirms -> hour 11 finalizes
    path = _segment_path(tmp_path, 11)
    assert pl.read_parquet(path)["checksum"].to_list() == [999, 30, 31, 32]  # redeemed + genuine, in order
    assert verify_manifest(path) is True


def test_t0037_a_coherently_fast_walk_cannot_poison_the_witness(tmp_path, clock):
    # An IN-BAND walk — stamps each exactly MAX_TS_AHEAD ahead of the last, so the plausibility guard passes
    # every one — would carry stream A's witness ~100 minutes into the future while the wall still read 10:00,
    # for the same truncation on B as the burst shape. The clamp pins A's witness at 10:05: however far the
    # walk's stamps name, the stream cannot vouch past the wall's own reach.
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")
    b = _oracle_writer(tmp_path, oracle)
    clock.now = _ts(10, 0)
    for i in range(1, 21):  # 10:05, 10:10, ... 11:40 — each within the window of the last accepted
        a.append({**_book_event_for("ETH/EUR", 10, 0, checksum=800 + i), "ts": _ts(10, 0) + timedelta(minutes=5 * i)})
    genuine = set()
    for mnt in range(1, 56):  # B's genuine live hour 10
        clock.now = _ts(10, mnt)
        b.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(10, 56, 30)
    b.append(_book_event(11, 0, checksum=999))  # the lone in-window bogus stamp on B
    assert not _segment_path(tmp_path, 10).exists()  # the walked witness seconded NOTHING
    for mnt in (56, 57, 58, 59):
        clock.now = _ts(10, mnt)
        b.append(_book_event(10, mnt, checksum=mnt))
        genuine.add(mnt)
    clock.now = _ts(11, 0)
    b.append(_book_event(11, 0, checksum=100))
    clock.now = _ts(11, 5)
    b.append(_book_event(11, 5, checksum=105))
    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(1, 60))  # not one genuine row lost
    assert verify_manifest(path) is True
    b.close()
    a.close()
    assert genuine <= set(_disk_column(tmp_path, "checksum"))
    assert 999 in set(_disk_column(tmp_path, "checksum"))


def test_t0037_early_finalize_counted_on_rotation(tmp_path, clock):
    # Residual (a) — the loss the oracle ACCEPTS (spec 00103 D1): TWO streams stamped bogus inside
    # the same closing window meet quorum, and the second stamp's rotation publishes its live hour
    # truncated. The segment is committed and verify-clean, so the counter is the only signature.
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="BTC/EUR")
    b = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")
    for mnt in range(0, 56):  # both live hours genuine so far
        clock.now = _ts(10, mnt)
        a.append(_book_event_for("BTC/EUR", 10, mnt, checksum=mnt))
        b.append(_book_event_for("ETH/EUR", 10, mnt, checksum=mnt))
    clock.now = _ts(10, 56, 30)
    a.append(_book_event_for("BTC/EUR", 11, 0, checksum=901))  # bogus, 3.5 min ahead — held, ONE witness
    assert a.hour_finalized_early == 0  # a lone stamp still confirms nothing
    b.append(_book_event_for("ETH/EUR", 11, 0, checksum=902))  # the second bogus stamp meets quorum
    assert b.hour_finalized_early == 1  # B's hour 10 published 3.5 min early — counted at the rotation
    assert _segment_path(tmp_path, 10, pair="ETH/EUR").exists()  # ... and the truncated publish is real


def test_t0037_early_finalize_counted_on_the_sweep_path(tmp_path, clock):
    # The SAME residual landing in a restart window (spec 00103 D2): `_current_hour is None`, so the
    # bogus-confirmed first event publishes the truncated hour through `_sweep` -> `_merge_hour`
    # directly — `_finalize_hour` never runs, so a rotation-only instrumentation leaves this at 0.
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):  # cs 0..19 flushed to 4 parts, hour 10 still live
        clock.now = _ts(10, i)
        w1.append(_book_event(10, i, checksum=i))
    del w1  # hard crash

    clock.now = _ts(10, 57)
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="BTC/EUR")  # inherits the crash-leftover hour-10 parts
    b = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")
    b.append(_book_event_for("ETH/EUR", 11, 0, checksum=901))  # bogus — held, ONE witness
    assert b.hour_finalized_early == 0
    a.append(_book_event_for("BTC/EUR", 11, 0, checksum=902))  # the second bogus stamp meets quorum
    assert a._current_hour == _ts(11, 0)  # entered via the `is None` branch: this WAS the sweep path
    assert _segment_path(tmp_path, 10).exists()  # hour 10 published truncated to the crash leftovers
    assert a.hour_finalized_early == 1  # ... 3 minutes early, and the sweep counted it


def test_t0037_genuine_boundary_counts_no_earliness(tmp_path, clock):
    # CONTROL for the rotation site: a genuine two-stream boundary under a healthy clock publishes
    # hour 10 at 11:00:00 sharp — zero earliness, and the counter must stay silent (`>`, not `>=`:
    # publishing the instant the hour ends is on time). An unconditional or sign-flipped count fires here.
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="BTC/EUR")
    b = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")

    def feed(w, pair, hour, minute, cs, sec=0):
        clock.now = _ts(hour, minute, sec)  # a healthy clock: wall time == exchange time
        w.append(_book_event_for(pair, hour, minute, sec, checksum=cs))

    feed(a, "BTC/EUR", 10, 0, 0)  # held — only A witnessed, the clock's handicap lags
    feed(b, "ETH/EUR", 10, 0, 10)  # B seconds hour 10 -> B admits
    feed(a, "BTC/EUR", 10, 30, 1)
    feed(b, "ETH/EUR", 10, 30, 11)
    feed(a, "BTC/EUR", 11, 0, 2)  # A crosses first — held, hour 11 still unconfirmed
    feed(b, "ETH/EUR", 11, 0, 12)  # B crosses: quorum -> B's hour 10 publishes at 11:00:00 exactly
    feed(a, "BTC/EUR", 11, 0, 3, sec=30)  # A's next event finalizes A's hour 10, 30 s AFTER it ended
    assert _segment_path(tmp_path, 10, pair="ETH/EUR").exists()  # both publishes really happened...
    assert _segment_path(tmp_path, 10, pair="BTC/EUR").exists()
    assert b.hour_finalized_early == 0  # ... and neither was early
    assert a.hour_finalized_early == 0


def test_t0037_swept_past_hour_counts_no_earliness(tmp_path, clock):
    # CONTROL for the sweep site: the sweep's ordinary job is republishing hours a dead process left
    # behind, long after they ended. Negative earliness, excluded by the arithmetic (spec 00103 D2)
    # — a count here would fire on every routine restart.
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(20):
        clock.now = _ts(10, i)
        w1.append(_book_event(10, i, checksum=i))
    del w1  # hard crash: hour-10 parts left behind

    clock.now = _ts(12, 30)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(12, 30, checksum=100))  # genuine first event: sweeps and publishes hour 10
    assert _segment_path(tmp_path, 10).exists()  # the republish really ran through the sweep
    assert w2.hour_finalized_early == 0  # ... and a 90-minutes-gone hour is not "early"


def test_t0037_lagging_clock_counts_early_by_design(tmp_path, clock):
    """A clock lagging 3 min under GENUINE two-stream traffic fires the counter — intended (spec 00103 D3):
    the earliness is measured with the same lagging clock, so a genuine boundary reads 3 min early."""
    oracle = HourOracle()
    a = _oracle_writer(tmp_path, oracle, pair="BTC/EUR")
    b = _oracle_writer(tmp_path, oracle, pair="ETH/EUR")

    def feed(w, pair, hour, minute, cs):
        clock.now = _ts(hour, minute) - timedelta(minutes=3)  # a steady 3-min lag
        w.append(_book_event_for(pair, hour, minute, checksum=cs))

    feed(a, "BTC/EUR", 10, 0, 0)  # held — only A witnessed, the lagging clock cannot second
    feed(b, "ETH/EUR", 10, 0, 10)  # B seconds hour 10 -> B admits
    feed(a, "BTC/EUR", 10, 30, 1)
    feed(b, "ETH/EUR", 10, 30, 11)
    feed(a, "BTC/EUR", 11, 0, 2)  # A crosses first — held
    feed(b, "ETH/EUR", 11, 0, 12)  # B crosses: quorum, and the wall still reads 10:57
    assert b.hour_finalized_early == 1  # a genuine boundary, counted early: the clock's error, reported
    assert _segment_path(tmp_path, 10, pair="ETH/EUR").exists()  # the publish itself is healthy


def test_t0037_past_dated_first_stamp_counted(tmp_path, clock):
    # Residual (c) — the past-dated fabrication (spec 00103 D5, narrowed by spec 00109 D1): a process's FIRST
    # stamp is the only event that can open an hour behind the wall clock. Hour 08 is committed first so the
    # recovery floor is real (09:00) and the stamp lands ABOVE it, where the late-event guard cannot refuse
    # it. Neither writer appended in hour 10, so it holds no `.part` files — a fabrication rather than a
    # re-open, the property `test_t0037_restart_reopening_a_captured_hour_counts_nothing` inverts.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(8, 30)
    w1.append(_book_event(8, 30, checksum=1))
    clock.now = _ts(9, 0)
    w1.append(_book_event(9, 0, checksum=2))  # rotates: hour 08 commits, so the recovery floor is 09:00
    del w1  # hard crash — the buffered hour-9 row is lost, leaving no parts to sweep

    clock.now = _ts(12, 30)
    w2 = _oracle_writer(tmp_path, HourOracle())
    w2.append(_book_event(10, 0, checksum=999))  # the first stamp opens never-captured hour 10, 2.5 h back
    assert w2._current_hour == _ts(10, 0)  # the past hour genuinely OPENED — the late-event guard let it through
    assert w2.ts_past_dated_hour == 1


def test_t0037_restart_reopening_a_captured_hour_counts_nothing(tmp_path, clock):
    # Spec 00109 D1: a mid-hour restart whose FIRST event is a replayed pre-restart print opens the PREVIOUS
    # hour — but that hour HAS parts on disk, so nothing was fabricated and nothing may be counted. Hour 14 is
    # committed first so the floor is seeded as it always is on a capture host, where every previous hour has
    # a final: a count keyed on `self._floor is not None` passes here, and must not.
    # `test_t0037_a_held_only_past_hour_still_counts` is this fixture with hour 15's `.part` swapped for a
    # `.held`, and must read 1.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(14, 30)
    for i in range(5):
        w1.append(_book_event(14, 30, checksum=i + 1))
    clock.now = _ts(15, 5)
    w1.finalize_completed_hours(_ts(15, 0))  # 14.parquet commits, so the recovery floor is 15:00
    clock.now = _ts(15, 30)
    for i in range(5):  # flush_rows=5 → these land as 15.part0000.parquet
        w1.append(_book_event(15, 30, checksum=i + 1))
    del w1  # crash mid-hour: parts on disk, hour never finalized (close() never finalizes anyway)

    assert list(tmp_path.rglob("15.part*.parquet"))  # hour 15 holds its own parts — never captured is false

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    assert w2._floor == _ts(15, 0)  # a floor, and the stamp lands ON it — the late-event guard cannot refuse it
    w2.append(_book_event(15, 30, checksum=999))  # replayed pre-restart print, one hour back
    assert w2._current_hour == _ts(15, 0)  # the past hour DID open — the branch ran
    assert w2.ts_past_dated_hour == 0  # …and counted nothing, because the hour was captured


def test_t0037_a_held_only_past_hour_still_counts(tmp_path, clock):
    # Spec 00109 D1's DANGEROUS case: an hour holding only a quarantined `.held` spill was never corroborated
    # by the oracle, so it is NOT captured. Opening it redeems that spill into a manifest-certified final
    # built from rows nothing confirmed — a fabrication, and it must count.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(14, 30)
    for i in range(5):
        w1.append(_book_event(14, 30, checksum=i + 1))
    clock.now = _ts(15, 5)
    w1.finalize_completed_hours(_ts(15, 0))  # 14.parquet commits, so the recovery floor is 15:00
    w1._write_part([_book_event(15, 40, checksum=7)], _ts(15, 0), marker=".held")
    del w1

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    assert not w2._parts_for(w2._hour_dir(_ts(15, 0)), "15")  # no parts…
    assert w2._parts_for(w2._hour_dir(_ts(15, 0)), "15", marker=".held")  # …but a held spill
    w2.append(_book_event(15, 40, checksum=999))
    assert w2._current_hour == _ts(15, 0)  # a `.held` seeds no floor, so the hour really opens
    assert w2.ts_past_dated_hour == 1


def test_t0037_a_finalized_past_hour_never_reaches_the_counter(tmp_path, clock, caplog):
    # Why `.part`-absence is a sound test for "never captured" (spec 00109 D1): `_commit` unlinks an hour's
    # parts once the merged bytes are durable, so a COMMITTED hour also has none. It is the recovery floor,
    # not the predicate, that rules that hour out — `_recover` seeds `_floor` at the newest final plus an
    # hour, and the late-event guard refuses the stamp before `_enter_hour` runs. If this ever fails, fix
    # `_recover` or the late-event guard, not the predicate, whose text this test never reads.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(15, 30)
    for i in range(5):
        w1.append(_book_event(15, 30, checksum=i + 1))
    clock.now = _ts(16, 15)
    w1.finalize_completed_hours(_ts(16, 0))  # hour 15 commits AND its parts are unlinked
    del w1

    w2 = _oracle_writer(tmp_path, HourOracle())
    assert not w2._parts_for(w2._hour_dir(_ts(15, 0)), "15")  # the predicate alone would say "never captured"
    assert w2._floor == _ts(16, 0)  # …but the floor is above hour 15
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w2.append(_book_event(15, 40, checksum=999))
    assert _drop_levels(caplog, "dropping late event") == [logging.INFO]  # the FLOOR refused it…
    assert w2._current_hour is None  # …so the branch never ran
    assert w2.ts_past_dated_hour == 0


def test_t0037_a_never_captured_hour_beside_unswept_parts_still_counts(tmp_path, clock):
    # The predicate's GRANULARITY: it must ask about the hour that OPENED, not about the day or the stream. A
    # glob that drops the `<HH>` prefix (the day dir), or that walks the stream root the way `_sweep` and
    # `finalize_completed_hours` legitimately do, sees the unswept hour-14 parts here and reads 0 — blind to
    # its own target case whenever a crash hour shares a day with the fabricated one.
    w1 = _new_writer(tmp_path, flush_rows=5)
    clock.now = _ts(14, 30)
    for i in range(5):
        w1.append(_book_event(14, 30, checksum=i + 1))
    del w1  # crash in hour 14: its parts stay unswept, and hour 15 never receives an event

    clock.now = _ts(16, 15)
    w2 = _oracle_writer(tmp_path, HourOracle())
    assert list(tmp_path.rglob("14.part*.parquet"))  # hour 14's parts are on disk WHEN the branch reads
    w2.append(_book_event(15, 40, checksum=999))  # the first stamp opens never-captured hour 15
    assert w2._current_hour == _ts(15, 0)
    assert not list(tmp_path.rglob("14.part*.parquet"))  # `_sweep` merged hour 14 — the branch really ran
    assert w2.ts_past_dated_hour == 1


def test_t0037_normal_start_counts_no_past_dated_hour(tmp_path, clock):
    # CONTROL for the ordinary case: a mid-hour start whose first stamp names the CURRENT wall hour.
    # `hour < _hour_start(now)` is false, so nothing counts — an unconditional or sign-flipped count
    # fires here. The open-hour assert proves the first-event branch (the only counting site) ran.
    clock.now = _ts(10, 30)
    w = _oracle_writer(tmp_path, HourOracle())
    w.append(_book_event(10, 30, checksum=1))
    assert w._current_hour == _ts(10, 0)  # admitted and opened via the first-event branch, not held
    assert w.ts_past_dated_hour == 0


def test_t0037_draining_held_rows_counts_no_past_dated_hour(tmp_path, clock):
    # CONTROL with teeth: TWO held rows carrying DISTINCT timestamps, then drained. `_hold` already
    # advanced `_max_ts` past the older row, so the drain re-admits it through `_admit` reading
    # "backward" — routine, not a defect, and the counter must stay at 0. ONE held row re-admits
    # nothing backward and would prove nothing; two distinct timestamps is the minimum that bites.
    clock.now = _ts(10, 2)
    w = _oracle_writer(tmp_path, HourOracle())
    w.append(_book_event(10, 0, 0, checksum=0))  # held: a lone stream, and the clock handicap reads 09:57
    w.append(_book_event(10, 0, 30, checksum=1))  # a second held row, DISTINCT ts
    assert w._held  # both really held — nothing admitted, nothing entered yet
    clock.now = _ts(10, 6)  # the handicapped clock crosses 10:00 -> hour 10 confirms
    w.append(_book_event(10, 6, checksum=2))  # drains both held rows through `_admit`, then admits itself
    assert w._current_hour == _ts(10, 0)
    assert not w._held  # the drain really ran — the re-admission path was exercised
    assert w.ts_past_dated_hour == 0


def test_t0037_lone_bogus_future_stamp_counts_no_past_dated_hour(tmp_path, clock):
    # CONTROL with teeth: the pinned-healthy lone-in-window-bogus-stamp scenario (the shape of
    # test_t0037_lone_in_window_bogus_stamp_never_truncates_the_live_hour). The held bogus 11:00
    # advances `_max_ts`, so every genuine 10:57–10:59 row behind it reads "backward" on a healthy
    # stream; this counter must read 0.
    w = _oracle_writer(tmp_path, HourOracle())
    for mnt in range(0, 57):  # 10:00 .. 10:56 — the live hour so far
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
    clock.now = _ts(10, 56, 30)
    w.append(_book_event(11, 0, checksum=999))  # the bogus stamp: 3.5 min ahead — inside the window, held
    for mnt in (57, 58, 59):  # the genuine rest of the hour, each ts behind the neutralized stamp
        clock.now = _ts(10, mnt)
        w.append(_book_event(10, mnt, checksum=mnt))
    clock.now = _ts(11, 5)
    w.append(_book_event(11, 5, checksum=105))  # the clock seconds hour 11 -> hour 10 finalizes whole
    assert pl.read_parquet(_segment_path(tmp_path, 10))["checksum"].to_list() == list(range(60))  # still the pinned outcome
    assert w.ts_past_dated_hour == 0


def test_t0037_an_oracle_less_writer_reopening_a_prior_hour_counts_nothing(tmp_path, clock):
    # CONTROL with teeth for the gate: `finalize_completed_hours` nulls `_current_hour`, so an
    # oracle-less poller re-enters the first-event branch every cycle, and a sparse symbol waking up
    # into a prior hour above the re-anchored floor is its DESIGNED write mode (T0046), not a
    # fabrication. It bites: without `self._oracle is not None` the append below reads 1.
    w = _new_writer(tmp_path, flush_rows=5000)  # oracle-less, as the poller builds them
    w.append(_book_event(10, 0))
    assert w.finalize_completed_hours(_ts(11, 0)) == 1
    assert w._current_hour is None  # the re-entry this gate exists for

    w.append(_book_event(11, 30))  # at/above the floor, but behind the pinned 16:00 clock

    assert w.ts_past_dated_hour == 0


# --- T0046: wall-clock hour finalization for sparse writers --------------------------------------
#
# `finalize_completed_hours(cutoff)` only ever touches hours strictly before `cutoff`; its caller (the
# Coinalyze poller) owns that margin's safety.


def test_finalize_completed_hours_on_a_fresh_writer_is_a_no_op(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)
    assert w.finalize_completed_hours(_ts(11, 0)) == 0


def test_finalize_completed_hours_flushes_and_finalizes_a_stale_open_hour(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)  # large enough that both rows stay buffered in RAM
    w.append(_book_event(10, 0))
    w.append(_book_event(10, 30))

    finalized = w.finalize_completed_hours(_ts(11, 0))

    assert finalized == 1
    assert w._buffer == []
    assert w._current_hour is None
    path = _segment_path(tmp_path, 10)
    assert path.exists()
    assert verify_manifest(path) is True
    assert pl.read_parquet(path).height == 2


def test_finalize_completed_hours_leaves_an_hour_at_or_after_the_cutoff_untouched(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(14, 0))

    finalized = w.finalize_completed_hours(_ts(14, 0))  # the open hour itself -- not STRICTLY older

    assert finalized == 0
    assert w._current_hour == _ts(14, 0)
    assert w._buffer  # still buffered -- untouched
    assert not _segment_path(tmp_path, 14).exists()


def test_finalize_completed_hours_merges_crash_leftover_parts_with_no_open_hour(tmp_path):
    # A previous process opened hour 10, flushed parts, and crashed (no close()) -- this fresh
    # writer never received an event, so `_current_hour` is None and the ordinary sweep (deferred
    # to the first event) has not run either.
    w1 = _new_writer(tmp_path, flush_rows=5)
    for i in range(15):  # 3 parts, no rotation triggered (no next-hour event)
        w1.append(_hour10_event(i, i))
    del w1

    w2 = _new_writer(tmp_path, flush_rows=5)
    assert w2._current_hour is None

    finalized = w2.finalize_completed_hours(_ts(11, 0))

    assert finalized == 1
    path = _segment_path(tmp_path, 10)
    assert path.exists()
    assert verify_manifest(path) is True
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(15))
    assert not list(path.parent.glob("10.part*.parquet"))

    # The finalized hour is still floor-protected: a late replay must not reopen it.
    w2.append(_hour10_event(5, 999))
    assert pl.read_parquet(path)["checksum"].to_list() == list(range(15))
    assert w2._current_hour is None


def test_finalize_completed_hours_is_idempotent(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(10, 0))

    assert w.finalize_completed_hours(_ts(11, 0)) == 1
    assert w.finalize_completed_hours(_ts(11, 0)) == 0
    assert w.finalize_completed_hours(_ts(12, 0)) == 0  # a later cutoff still finds nothing left


def test_finalize_completed_hours_makes_a_later_replay_a_dropped_late_event(tmp_path):
    # `finalize_completed_hours` is the only path that clears `_current_hour` without opening a new hour, so
    # it must re-anchor `_floor` itself -- otherwise a replay arriving while `_current_hour` is `None`
    # silently reopens an hour already committed to disk, exactly the "parts beside a readable final"
    # ambiguity T0036 exists to prevent.
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(10, 0))
    assert w.finalize_completed_hours(_ts(11, 0)) == 1

    w.append(_book_event(10, 30, checksum=999))  # a late replay for the now-finalized hour

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == [42]  # only the original row; replay dropped
    assert w._current_hour is None  # the late event must not reopen the hour


def test_finalize_completed_hours_then_close_is_safe(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(10, 0))
    assert w.finalize_completed_hours(_ts(11, 0)) == 1

    w.close()  # must not raise, and must not touch the already-finalized hour

    path = _segment_path(tmp_path, 10)
    assert pl.read_parquet(path)["checksum"].to_list() == [42]
    assert verify_manifest(path) is True


def test_restart_reseeds_dedup_keys_from_open_hour_parts(tmp_path, caplog):
    # Spec 00055 D5: a dedup-keyed writer restarted over an open hour with flushed parts reseeds `_seen` from
    # disk, so a re-submitted event is dropped, never duplicated. This is the anomaly-detector backstop the
    # liquidations watermark relies on.
    event = {
        "ts": _ts(10, 0, 0),
        "symbol": "BTCUSDT_PERP.A",
        "long_usd": 1.0,
        "short_usd": 2.0,
        "event_id": "BTCUSDT_PERP.A-1",
    }
    w1 = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    w1.append(dict(event))
    w1.close()

    w2 = SegmentWriter(tmp_path, "BTC", "liquidations-1m", LIQ_AGG_SCHEMA, dedup_key="event_id")
    with caplog.at_level(logging.INFO):
        w2.append(dict(event))
    w2.close()
    assert "dropping replayed event" in caplog.text

    parts = sorted(tmp_path.rglob("*.part*.parquet"))
    assert sum(pl.read_parquet(p).height for p in parts) == 1  # one row, not two


# --- spec 00069 T3: additive metrics counters (segments/bytes/held/quarantined rows) --------------


def test_segments_written_and_segment_bytes_increment_on_commit(tmp_path):
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(14, 0))
    assert w.segments_written == 0  # not yet finalized -- still the open hour
    w.append(_book_event(15, 0))  # crosses the boundary -> hour 14 finalizes

    path = _segment_path(tmp_path, 14)
    assert w.segments_written == 1
    assert w.segment_bytes == path.stat().st_size


def test_rows_held_counts_every_row_parked_pending_oracle_confirmation(tmp_path, clock):
    clock.now = _ts(10, 3)
    w = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, dedup_key="trade_id")
    for i in range(3):  # held: a lone stream, clock < 10:05 -> hour 10 not yet confirmed
        w.append(_trade_event(10, i, i))
    assert w._held  # sanity: the rows really are in the held state, not admitted
    assert w.rows_held == 3


def test_rows_quarantined_counts_only_rows_actually_spilled_to_a_held_file(tmp_path, clock):
    clock.now = _ts(10, 3)
    w = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, dedup_key="trade_id")
    for i in range(3):
        w.append(_trade_event(10, i, i))
    assert w.rows_quarantined == 0  # held in RAM so far, nothing spilled to disk yet

    w.close()  # close() spills every still-held row to a `.held` quarantine file
    assert w.rows_quarantined == 3


def test_a_raising_metrics_update_after_a_segment_commit_does_not_undo_or_interrupt_it(tmp_path, monkeypatch, caplog):
    # Isolation invariant (spec 00069 D5): `_merge_hour` already committed the segment (durable on
    # disk, manifest written) by the time the metrics update runs -- a raising `stat()` there must
    # never look like the merge itself failing, and must never propagate into `append()`'s caller
    # (the capture message-handler path).
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(14, 0))

    path = _segment_path(tmp_path, 14)
    real_stat = Path.stat

    def _boom_stat(self, *args, **kwargs):
        if self == path:
            raise OSError("simulated stat failure")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", _boom_stat)
    with caplog.at_level(logging.ERROR):
        w.append(_book_event(15, 0))  # crosses the boundary -> finalizes/merges hour 14 -- must not raise
    monkeypatch.undo()  # restore the real stat() before inspecting the result below

    assert path.exists()  # the segment itself committed regardless of the metrics failure
    assert verify_manifest(path) is True
    assert w.segments_written == 1  # incremented before the raising stat() call
    assert w.segment_bytes == 0  # the byte count itself is what failed to update
    assert "segment committed but its metrics update failed" in caplog.text
    assert "merge failed" not in caplog.text  # the merge succeeded; only its OWN metrics update failed


# --- spec 00107 D4: the reconnect-replay drops are INFO, and the reconnect counter is the signal ----


def _drop_levels(caplog, prefix: str) -> list[int]:
    """The level of every record whose message starts with `prefix`, as a LIST: a site that stopped
    logging (no record) must fail exactly like one that logs at the wrong level."""
    return [r.levelno for r in caplog.records if r.getMessage().startswith(prefix)]


def test_a_late_event_behind_a_committed_hour_is_dropped_at_info(tmp_path, caplog):
    # A reconnect's replay is expected, not a fault, so the drop is INFO and not a warning:
    # `zcrypto_capture_reconnects_total` -- never a count of these lines -- measures how often it happens.
    w = _new_writer(tmp_path, flush_rows=5000)
    w.append(_book_event(10, 0))
    assert w.finalize_completed_hours(_ts(11, 0)) == 1
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_book_event(10, 30, checksum=999))
    assert _drop_levels(caplog, "dropping late event") == [logging.INFO]


def test_a_replay_into_the_open_hour_is_dropped_at_info(tmp_path, caplog):
    w = _new_trade_writer(tmp_path, flush_rows=50)
    w.append(_trade_event(10, 0, 1))
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_trade_event(10, 0, 1))
    w.close()
    assert _drop_levels(caplog, "dropping replayed event") == [logging.INFO]


def test_a_replay_into_a_held_hour_is_dropped_at_info(tmp_path, clock, caplog):
    # The third site: the hold path runs its own de-dup while the hour is still unconfirmed.
    clock.now = _ts(10, 0, 30)
    w = _oracle_writer(tmp_path, HourOracle(), kind="trades", schema=TRADE_SCHEMA, flush_rows=50, dedup_key="trade_id")
    w.append(_trade_event(10, 0, 0))
    with caplog.at_level(logging.INFO, logger="zcrypto.capture.segment_writer"):
        w.append(_trade_event(10, 0, 0))
    w.close()
    assert _drop_levels(caplog, "dropping replayed event") == [logging.INFO]
