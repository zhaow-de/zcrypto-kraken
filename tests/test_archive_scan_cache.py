"""Scan-cache fingerprints, persistence and skip preconditions (spec 00097 D4/D5)."""

from __future__ import annotations

import errno
import json
import os
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.archive import scan_cache
from cli.archive.mint import already_minted
from cli.archive.scan_cache import (
    CacheEntry,
    algo_salt,
    delete_cache,
    hour_fingerprint,
    is_skippable,
    load_cache,
    pick_audit_hours,
    save_cache,
)
from cli.archive.settle import hour_path, scan_hours
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA

H = datetime(2026, 7, 16, 9, tzinfo=UTC)
PAIR = "BTC/EUR"


def _book(pair: str, hour: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=o) for o in (1.0, 2.0, 3.0)],
            "symbol": [pair] * 3,
            "type": ["snapshot", "update", "update"],
            "side": ["bid"] * 3,
            "price": [1.0, 2.0, 3.0],
            "qty": [1.0] * 3,
            "checksum": [0] * 3,
        },
        schema=BOOK_SCHEMA,
    )


def _trades(pair: str, hour: datetime) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "ts": [hour + timedelta(seconds=o) for o in (1, 2)],
            "symbol": [pair] * 2,
            "side": ["buy"] * 2,
            "price": [1.0, 2.0],
            "qty": [1.0] * 2,
            "ord_type": ["limit"] * 2,
            "trade_id": [1, 2],
        },
        schema=TRADE_SCHEMA,
    )


def _write(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    """A real segment final, written where the reconciler looks for it."""
    path = hour_path(root, pair, kind, hour)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = _book(pair, hour) if kind == "book" else _trades(pair, hour)
    frame.write_parquet(path, compression="zstd")
    return path


def _scans(pri: Path, sec: Path) -> dict:
    """The cycle's availability picture, built exactly as `command.py` builds it."""
    return {
        "primary": {kind: scan_hours(pri, kind) for kind in ("book", "trades")},
        "secondary": {kind: scan_hours(sec, kind) for kind in ("book", "trades")},
    }


def _fp(pri: Path, sec: Path, rec: Path, *, scans=None, book=(PAIR,), trades=()) -> tuple[str, bool]:
    """`hour_fingerprint` for hour H, re-scanning unless a (deliberately stale) `scans` is given."""
    return hour_fingerprint(
        H,
        scans=_scans(pri, sec) if scans is None else scans,
        primary_root=pri,
        secondary_root=sec,
        reconciled_root=rec,
        book_pairs=list(book),
        trade_pairs=list(trades),
    )


def _entry(**over) -> CacheEntry:
    fields = {
        "fingerprint": "abc",
        "examined_at": "2026-07-16T15:00:00+00:00",
        "late_at_exam": True,
        "failures": 0,
        "complete": True,
    }
    fields.update(over)
    return CacheEntry(**fields)


# --- fingerprint ---------------------------------------------------------------------------------


def test_fingerprint_changes_on_size_mtime_new_file_and_absence(tmp_path):
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    primary_file = _write(pri, PAIR, "book", H)
    _write(sec, PAIR, "book", H)
    fp1, complete1 = _fp(pri, sec, rec)
    assert complete1 is True
    # True positive: an untouched file-set fingerprints identically, so a settled hour IS skippable.
    assert _fp(pri, sec, rec) == (fp1, True)

    with primary_file.open("ab") as fh:  # size changes (and mtime with it)
        fh.write(b"\x00" * 16)
    fp2, complete2 = _fp(pri, sec, rec)
    assert fp2 != fp1
    assert complete2 is True

    st = primary_file.stat()  # mtime alone, size held constant
    os.utime(primary_file, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    fp3, _ = _fp(pri, sec, rec)
    assert fp3 != fp2

    hour_path(sec, PAIR, "book", H).unlink()  # a mirror goes absent
    fp4, complete4 = _fp(pri, sec, rec)
    assert fp4 != fp3
    assert complete4 is False

    _write(sec, PAIR, "book", H)  # ... and a late file ARRIVES: the hour must re-examine
    fp5, complete5 = _fp(pri, sec, rec)
    assert fp5 != fp4
    assert complete5 is True

    # A widened expected set (a trades leg that has not arrived) is an absence too.
    fp6, complete6 = _fp(pri, sec, rec, trades=(PAIR,))
    assert fp6 != fp5
    assert complete6 is False


def test_fingerprint_survives_a_non_enoent_stat_error(tmp_path, monkeypatch):
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    _write(pri, PAIR, "book", H)
    _write(sec, PAIR, "book", H)
    scans = _scans(pri, sec)  # the cycle scans first, then fingerprints

    healthy, complete = _fp(pri, sec, rec, scans=scans)  # control: this path is readable
    assert complete is True

    wobbling = hour_path(sec, PAIR, "book", H)
    real_stat = Path.stat

    def flaky(self, *args, **kwargs):
        if self == wobbling:
            raise OSError(errno.ESTALE, "Stale file handle")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky)
    stale_fp, stale_complete = _fp(pri, sec, rec, scans=scans)  # must NOT raise: the pre-pass never dies
    assert stale_complete is False  # uncacheable — the examination path reads it and reports honestly
    assert stale_fp != healthy


def test_a_mirror_landing_after_the_scan_is_never_cacheable(tmp_path):
    """Presence must come from `scans`, never from a fresh `stat` — or this is a live wrong-skip.

    A fingerprint that stat'd the disk would record the late file as present and `complete=True`, and
    cycle N+1 — which DOES owe the heal — would compute that same fingerprint and skip the hour forever.
    """
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    _write(pri, PAIR, "book", H)

    cycle_n = _scans(pri, sec)  # T_scan: the secondary hour is not there yet
    assert H not in cycle_n["secondary"]["book"].get(PAIR, set())
    _write(sec, PAIR, "book", H)  # ... and it lands between the scan and the pre-pass
    late_fp, late_complete = _fp(pri, sec, rec, scans=cycle_n)
    assert late_complete is False  # THE GUARD: uncacheable, whatever is on disk
    assert is_skippable(_entry(fingerprint=late_fp, complete=late_complete), late_fp, late_complete) is False

    cycle_n1 = _scans(pri, sec)  # the next cycle enumerates it — the heal IS owed now
    assert H in cycle_n1["secondary"]["book"][PAIR]
    owed_fp, owed_complete = _fp(pri, sec, rec, scans=cycle_n1)
    assert owed_complete is True
    assert owed_fp != late_fp  # a DIFFERENT file-set, so cycle N's entry cannot match it

    # True positive: once a cycle has both scanned and examined it, the settled hour IS skippable.
    assert is_skippable(_entry(fingerprint=owed_fp), *_fp(pri, sec, rec)) is True


def test_a_file_vanishing_after_the_scan_is_uncacheable_too(tmp_path):
    """The other skew: the scan listed it, the pre-pass cannot stat it. Also fail-open."""
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    _write(pri, PAIR, "book", H)
    _write(sec, PAIR, "book", H)
    scans = _scans(pri, sec)
    assert _fp(pri, sec, rec, scans=scans)[1] is True  # control: both listed and readable

    hour_path(sec, PAIR, "book", H).unlink()  # removed between scan and pre-pass
    gone_fp, gone_complete = _fp(pri, sec, rec, scans=scans)
    assert gone_complete is False
    assert is_skippable(_entry(fingerprint=gone_fp), gone_fp, gone_complete) is False


# --- persistence ---------------------------------------------------------------------------------


def test_save_load_round_trip_atomic(tmp_path):
    root = tmp_path / "reconciled" / "nested"  # save must create its parents
    salt = algo_salt(1.5, mint=True)
    entries = {
        "2026-07-16T09:00:00+00:00": _entry(fingerprint="aaa"),
        "2026-07-16T10:00:00+00:00": _entry(fingerprint="bbb", failures=2, complete=False, late_at_exam=False),
    }
    save_cache(root, entries, salt=salt)

    assert load_cache(root, salt=salt) == entries
    assert list(root.glob("*.tmp")) == []  # the temp file is renamed, never left behind

    delete_cache(root)
    assert load_cache(root, salt=salt) == {}
    delete_cache(root)  # missing_ok: a second delete is not an error


def test_delete_cache_raises_rather_than_swallowing(tmp_path, monkeypatch):
    """The deliberate asymmetry with `save_cache`, pinned so it is not "fixed" later."""
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    save_cache(root, {"2026-07-16T09:00:00+00:00": _entry()}, salt=salt)
    delete_cache(root)  # control: an ordinary delete works
    assert load_cache(root, salt=salt) == {}

    save_cache(root, {"2026-07-16T09:00:00+00:00": _entry()}, salt=salt)
    real_unlink = Path.unlink

    def refuses(self, *args, **kwargs):
        if self.name == "scan-cache.json":
            raise OSError(errno.EROFS, "Read-only file system")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuses)
    with pytest.raises(OSError):  # it must NOT be swallowed
        delete_cache(root)
    monkeypatch.undo()
    assert load_cache(root, salt=salt) != {}  # ... and the stale cache really is still there


def test_load_returns_empty_on_absent_corrupt_and_foreign_salt(tmp_path):
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    entries = {"2026-07-16T09:00:00+00:00": _entry()}

    assert load_cache(root, salt=salt) == {}  # absent root
    root.mkdir()
    assert load_cache(root, salt=salt) == {}  # absent file

    save_cache(root, entries, salt=salt)
    assert load_cache(root, salt=salt) == entries  # true positive: a healthy cache DOES load
    cache_file = root / "scan-cache.json"

    cache_file.write_bytes(b"\x00\xffnot json at all")
    assert load_cache(root, salt=salt) == {}

    for scalar in ("null", "3", '"a string"', "[]", "true"):  # JSON-valid but not an object
        cache_file.write_text(scalar)
        assert load_cache(root, salt=salt) == {}, scalar

    for hours in ("[]", "null", '"nope"', "7"):  # object, but "hours" is not a mapping
        cache_file.write_text(json.dumps({"algo": salt}).rstrip("}") + f', "hours": {hours}}}')
        assert load_cache(root, salt=salt) == {}, hours

    cache_file.write_text(json.dumps({"algo": salt, "hours": {"2026-07-16T09:00:00+00:00": {"bogus": 1}}}))
    assert load_cache(root, salt=salt) == {}  # an entry that is not a CacheEntry

    cache_file.write_text(json.dumps({"algo": salt, "hours": {"2026-07-16T09:00:00+00:00": "not a dict"}}))
    assert load_cache(root, salt=salt) == {}

    cache_file.write_text(json.dumps({"hours": {}}))
    assert load_cache(root, salt=salt) == {}  # no "algo" at all

    save_cache(root, entries, salt=salt)
    assert load_cache(root, salt=algo_salt(2.0, mint=True)) == {}  # a foreign salt invalidates wholesale
    assert load_cache(root, salt=algo_salt(1.5, mint=False)) == {}  # ... and so does the mint-mode flip


def test_load_survives_a_recursion_error(tmp_path, monkeypatch):
    """`RecursionError` is a `RuntimeError`, which the obvious except tuple misses. The contract is
    "never raises", so it is caught.

    The defect is injected, not provoked by a deeply nested file: the depth at which CPython gives up
    is environment-dependent — the same nesting parses cleanly under `coverage run` in CI — so
    provoking it makes the control assertion the flaky part.
    """
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    save_cache(root, {"2026-07-16T09:00:00+00:00": _entry()}, salt=salt)
    assert load_cache(root, salt=salt) != {}  # control: this cache loads

    def _boom(*_args, **_kwargs):
        raise RecursionError("maximum recursion depth exceeded while decoding a JSON array")

    monkeypatch.setattr(scan_cache.json, "loads", _boom)
    assert load_cache(root, salt=salt) == {}  # ... and load_cache absorbs it


def test_load_survives_a_deeply_nested_corrupt_cache(tmp_path):
    """The real file shape, whichever way the parser rejects it: `{}` and no raise — the depth at
    which CPython gives up is not a property a test may pin."""
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    save_cache(root, {"2026-07-16T09:00:00+00:00": _entry()}, salt=salt)
    assert load_cache(root, salt=salt) != {}  # control: this cache loads

    (root / "scan-cache.json").write_text("[" * 100_000 + "]" * 100_000)
    assert load_cache(root, salt=salt) == {}


def test_load_drops_a_malformed_entry_and_keeps_the_rest(tmp_path):
    """JSON carries no types, so a loadable-but-wrong entry used to explode two calls later in
    `pick_audit_hours`. Each bad shape is dropped; the healthy entry beside it survives."""
    root = tmp_path / "reconciled"
    root.mkdir()
    salt = algo_salt(1.5, mint=True)
    good_hour, bad_hour = "2026-07-16T09:00:00+00:00", "2026-07-16T10:00:00+00:00"
    good = asdict(_entry(fingerprint="good"))

    for bad in (
        {**good, "examined_at": 5},  # the shape that raised TypeError in the audit sort
        {**good, "fingerprint": None},
        {**good, "late_at_exam": "yes"},
        {**good, "failures": "none"},
        {**good, "complete": 1},
        {**good, "failures": False},  # bool subclasses int -- `isinstance` would keep this
        {**good, "extra": 1},  # unknown field
        {k: v for k, v in good.items() if k != "complete"},  # missing field
        "not a mapping",
        None,
    ):
        (root / "scan-cache.json").write_text(json.dumps({"algo": salt, "hours": {good_hour: good, bad_hour: bad}}))
        loaded = load_cache(root, salt=salt)
        assert list(loaded) == [good_hour], bad  # the healthy entry SURVIVES the bad one
        assert pick_audit_hours(list(loaded), loaded) == [good_hour], bad  # and nothing explodes downstream


def test_save_never_raises_and_leaves_no_partial(tmp_path, monkeypatch):
    """A full or read-only overlay must not turn a completed, correct cycle into rc=1."""
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    published = {"2026-07-16T09:00:00+00:00": _entry(fingerprint="published")}
    save_cache(root, published, salt=salt)  # control: a healthy save publishes

    def enospc(src, dst):
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "replace", enospc)
    save_cache(root, {"2026-07-16T10:00:00+00:00": _entry(fingerprint="lost")}, salt=salt)  # must NOT raise
    monkeypatch.undo()

    assert list(root.glob("*.tmp")) == []  # the partial is cleaned up, not left behind
    assert load_cache(root, salt=salt) == published  # and the published cache is intact


def test_save_never_raises_on_an_unserializable_entry(tmp_path):
    """`CacheEntry` validates nothing at runtime, so a caller slip (`examined_at=now` instead of
    `now.isoformat()`) reaches `json.dumps`. An optimization's serialization bug must not fail a
    completed, correct cycle either."""
    root = tmp_path / "reconciled"
    salt = algo_salt(1.5, mint=True)
    published = {"2026-07-16T09:00:00+00:00": _entry(fingerprint="published")}
    save_cache(root, published, salt=salt)  # control: a healthy save publishes

    slipped = _entry(examined_at=datetime(2026, 7, 16, 15, tzinfo=UTC))
    with pytest.raises(TypeError):  # the defect is real, not hypothetical
        json.dumps(asdict(slipped))

    save_cache(root, {"2026-07-16T10:00:00+00:00": slipped}, salt=salt)  # must NOT raise
    assert list(root.glob("*.tmp")) == []
    assert load_cache(root, salt=salt) == published  # the published cache is intact


# --- the skip decision ---------------------------------------------------------------------------


def test_is_skippable_requires_all_five_preconditions():
    good = _entry(fingerprint="fp")
    assert is_skippable(good, "fp", True) is True  # true positive

    assert is_skippable(None, "fp", True) is False  # never examined
    assert is_skippable(good, "OTHER", True) is False  # the file-set moved
    assert is_skippable(_entry(fingerprint="fp", late_at_exam=False), "fp", True) is False
    assert is_skippable(_entry(fingerprint="fp", failures=1), "fp", True) is False
    assert is_skippable(_entry(fingerprint="fp", complete=False), "fp", True) is False  # was incomplete
    assert is_skippable(good, "fp", False) is False  # IS incomplete now


def test_pick_audit_hours_is_oldest_examined_first_and_deterministic():
    hours = ["2026-07-16T09:00:00+00:00", "2026-07-16T10:00:00+00:00", "2026-07-16T11:00:00+00:00"]
    entries = {
        hours[0]: _entry(examined_at="2026-07-16T20:00:00+00:00"),
        hours[1]: _entry(examined_at="2026-07-16T22:00:00+00:00"),
        hours[2]: _entry(examined_at="2026-07-16T18:00:00+00:00"),
    }
    assert pick_audit_hours(hours, entries) == [hours[2], hours[0]]  # oldest examination first
    assert pick_audit_hours(list(reversed(hours)), entries) == [hours[2], hours[0]]  # input order is irrelevant
    assert pick_audit_hours(hours, entries, k=1) == [hours[2]]
    assert pick_audit_hours(hours, entries, k=9) == [hours[2], hours[0], hours[1]]
    assert pick_audit_hours([], entries) == []

    tied = {h: _entry(examined_at="2026-07-16T20:00:00+00:00") for h in hours}
    assert pick_audit_hours(list(reversed(hours)), tied) == [hours[0], hours[1]]  # ties break by hour ascending


@pytest.mark.parametrize("min_gap", [0.5, 1.0, 1.5])
def test_algo_salt_pins_the_gap_threshold_the_mint_mode_and_the_version(min_gap):
    assert str(min_gap) in algo_salt(min_gap, mint=True)
    assert algo_salt(min_gap, mint=True).startswith("v")
    # The mint flip must invalidate wholesale: a detect-only entry inherited by a minting cycle is a
    # heal silently never performed.
    assert algo_salt(min_gap, mint=True) != algo_salt(min_gap, mint=False)


# --- the overlay is a verdict input ---------------------------------------------------------------


def test_hand_repair_of_a_minted_hour_re_examines_it(tmp_path):
    """`already_minted` is the one per-hour verdict input outside the mirrors.

    A hand-repair removes the minted file (and that hour's ledger records) to force a re-mint. The
    MIRRORS are byte-identical across it — so with the overlay left out of the fingerprint the hour
    stays skippable and the re-mint, plus every record the cycle would have written, is suppressed
    forever.
    """
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    _write(pri, PAIR, "book", H)
    _write(sec, PAIR, "book", H)

    def mirrors():
        stats = [hour_path(root, PAIR, "book", H).stat() for root in (pri, sec)]
        return [(st.st_size, st.st_mtime_ns) for st in stats]

    untouched = mirrors()

    # A healthy hour with nothing minted — the ordinary case. True positive: an absent overlay must
    # NOT read as incomplete, or every healthy hour is unskippable and the cache buys nothing.
    unminted, complete = _fp(pri, sec, rec)
    assert complete is True
    assert is_skippable(_entry(fingerprint=unminted), unminted, complete) is True

    minted_file = _write(rec, PAIR, "book", H)  # ... the cycle heals the hour
    assert already_minted(rec, PAIR, "book", H)
    minted, minted_complete = _fp(pri, sec, rec)
    assert minted != unminted
    assert minted_complete is True  # the overlay never speaks for `complete`
    settled = _entry(fingerprint=minted)
    assert is_skippable(settled, minted, minted_complete) is True  # settled again, still skippable

    minted_file.unlink()  # ... and the hand-repair removes it
    repaired, repaired_complete = _fp(pri, sec, rec)
    assert mirrors() == untouched  # the mirrors did not move: only the overlay can see this
    assert repaired == unminted  # back to exactly the pre-mint file-set
    assert repaired != minted
    assert is_skippable(settled, repaired, repaired_complete) is False  # THE GUARD: full examination


def test_the_overlay_backstop_is_blind_for_the_minting_cycle_itself(tmp_path):
    """The overlay term's blind spot, pinned so the backstop is not mistaken for a replacement.

    An entry holding the PRE-mint fingerprint cannot see a hand-repair that restores exactly that
    file-set. The caller never writes one — it refuses to cache an hour the cycle changed.
    """
    pri, sec, rec = tmp_path / "primary", tmp_path / "secondary", tmp_path / "reconciled"
    _write(pri, PAIR, "book", H)
    _write(sec, PAIR, "book", H)

    pre_mint, _ = _fp(pri, sec, rec)  # the minting cycle's pre-pass ...
    stored = _entry(fingerprint=pre_mint)  # ... and therefore the entry it stores
    minted_file = _write(rec, PAIR, "book", H)  # the cycle mints
    post_mint, _ = _fp(pri, sec, rec)
    assert post_mint != pre_mint

    minted_file.unlink()  # a hand-repair lands before the NEXT pre-pass
    repaired, repaired_complete = _fp(pri, sec, rec)
    assert repaired == pre_mint  # exactly the state the stored entry recorded
    assert is_skippable(stored, repaired, repaired_complete) is True  # BLIND — `delete_cache` covers this

    # For contrast, the case the backstop does cover: any later cycle stored the post-mint fingerprint.
    assert is_skippable(_entry(fingerprint=post_mint), repaired, repaired_complete) is False
