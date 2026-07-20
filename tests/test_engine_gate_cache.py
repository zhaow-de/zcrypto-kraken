"""Tests for the gate-export scoring cache primitives (cli/engine/gate_cache.py, spec 00060):
replay_fingerprint (D3 -- covers the replay CODE, not just the journal), evidence_fingerprint
(D2), and load_cache/save_cache (D5 fail-open, D6 atomic write). Everything here is synthetic --
no dataset access, no real replay."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import cli.engine.gate_cache as gate_cache
from cli.engine import CycleOutcome, CycleRecord, SnapshotEntry
from cli.engine.gate_cache import (
    CACHE_SCHEMA_VERSION,
    GateCache,
    evidence_fingerprint,
    load_cache,
    replay_fingerprint,
    save_cache,
)
from cli.portfolio import CrossfreqSystemConfig

# --- fixtures: a synthetic CycleRecord, mirroring tests/test_engine_journal.py's shape ----------

CYCLE_TS = datetime(2026, 7, 10, 8, 0)
VALID_H4_LAST = datetime(2026, 7, 10, 4, 0)
VALID_DAILY_LAST = datetime(2026, 7, 9, 0, 0)


def _entry(pair: str, grid: str, first_ts: datetime, last_ts: datetime, content_hash: str = "a" * 64) -> SnapshotEntry:
    return SnapshotEntry(
        pair=pair,
        grid=grid,
        n_bars=3,
        first_ts=first_ts,
        last_ts=last_ts,
        content_hash=content_hash,
        path=f"/snap/{pair}/{grid}.parquet",
    )


def _record(**overrides) -> CycleRecord:
    snapshots = overrides.pop(
        "snapshots",
        (
            _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64),
            _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
            _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
            _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
        ),
    )
    fields = {
        "schema_version": 1,
        "cycle_ts": CYCLE_TS,
        "snapshots": snapshots,
        "final_targets": {"BTC": 0.1, "ETH": -0.05},
        "started_at": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "code_version": "0.1.0+fast",
        "builder_path": "fast",
    }
    fields.update(overrides)
    return CycleRecord(**fields)


def _outcome(**overrides) -> CycleOutcome:
    fields = {
        "cycle_ts": CYCLE_TS,
        "completed_at": CYCLE_TS + timedelta(minutes=5),
        "compare_passed": True,
        "mismatch": False,
        "validation_failed": False,
    }
    fields.update(overrides)
    return CycleOutcome(**fields)


# --- evidence_fingerprint ---------------------------------------------------------------------


def test_evidence_fingerprint_changes_with_each_input():
    base = evidence_fingerprint(_record())

    # Mutating a snapshot's content_hash changes it.
    mutated_snapshots = (
        _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "z" * 64),
        _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
        _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
        _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
    )
    assert evidence_fingerprint(_record(snapshots=mutated_snapshots)) != base

    # Mutating cycle_ts changes it.
    assert evidence_fingerprint(_record(cycle_ts=CYCLE_TS + timedelta(hours=4))) != base

    # Mutating completed_at changes it.
    assert evidence_fingerprint(_record(completed_at=CYCLE_TS + timedelta(minutes=6))) != base

    # Mutating final_targets changes it.
    assert evidence_fingerprint(_record(final_targets={"BTC": 0.2, "ETH": -0.05})) != base

    # An identical record reproduces the same fingerprint.
    assert evidence_fingerprint(_record()) == base


# --- replay_fingerprint (D3) --------------------------------------------------------------------


def test_replay_fingerprint_covers_replay_code(tmp_path, monkeypatch):
    # This is D3's pin: the fingerprint must change when a covered module's bytes change, and must
    # be stable when nothing covered changes -- a journal-only (or config-only) implementation
    # would pass a "stable otherwise" check but fail the "changes with the code" half below.
    f1 = tmp_path / "a.py"
    f2 = tmp_path / "b.py"
    f1.write_text("# module a v1\n")
    f2.write_text("# module b v1\n")
    monkeypatch.setattr(gate_cache, "_REPLAY_CODE_PATHS", (f1, f2))

    fp_before = replay_fingerprint()

    # Stable across repeated calls with unchanged bytes.
    assert replay_fingerprint() == fp_before

    # Changing one covered file's bytes changes the fingerprint.
    f2.write_text("# module b v2 -- a comment-only edit is enough (deliberately over-sensitive)\n")
    fp_after = replay_fingerprint()
    assert fp_after != fp_before

    # Changing the effective config also changes the fingerprint (independent of file bytes).
    fp_default_config = replay_fingerprint()
    fp_other_config = replay_fingerprint(CrossfreqSystemConfig(long_cap=0.5))
    assert fp_other_config != fp_default_config


def test_replay_fingerprint_default_covers_the_real_files():
    # No monkeypatching -- exercises the real, hard-coded file list against the actual repo tree.
    fp = replay_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64
    assert fp == replay_fingerprint()  # stable/reproducible


# --- cache round-trip (D4/D8 of the spec test list) ----------------------------------------------


def test_cache_round_trip_preserves_outcome_exactly(tmp_path):
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    validation_failed = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=8), validation_failed=True, compare_passed=False)

    cache = GateCache(
        replay_fp=replay_fp,
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch),
            validation_failed.cycle_ts: ("evidence-fp-3", validation_failed),
        },
    )
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    assert loaded.replay_fp == replay_fp
    assert loaded.entries.keys() == cache.entries.keys()
    for cycle_ts, (evidence_fp, outcome) in cache.entries.items():
        loaded_evidence_fp, loaded_outcome = loaded.entries[cycle_ts]
        assert loaded_evidence_fp == evidence_fp
        assert loaded_outcome == outcome
        # A cached failure must never come back as a pass.
        assert loaded_outcome.mismatch == outcome.mismatch
        assert loaded_outcome.validation_failed == outcome.validation_failed
        assert loaded_outcome.compare_passed == outcome.compare_passed


# --- load_cache: fail open, never raise (D5) ------------------------------------------------------


def test_load_cache_degrades_never_raises(tmp_path):
    replay_fp = "fixed-replay-fp"

    # None path.
    empty = load_cache(None, replay_fp)
    assert empty.entries == {}
    assert empty.replay_fp == replay_fp

    # Absent file.
    absent_path = tmp_path / "does-not-exist.json"
    assert load_cache(absent_path, replay_fp).entries == {}

    # Truncated/unparseable JSON.
    truncated_path = tmp_path / "truncated.json"
    truncated_path.write_text('{"schema_version": 1, "replay_fp": "x", "entries": [')
    assert load_cache(truncated_path, replay_fp).entries == {}

    # Wrong schema_version.
    wrong_schema_path = tmp_path / "wrong-schema.json"
    wrong_schema_path.write_text(json.dumps({"schema_version": CACHE_SCHEMA_VERSION + 1, "replay_fp": replay_fp, "entries": []}))
    assert load_cache(wrong_schema_path, replay_fp).entries == {}

    # replay_fp mismatch.
    good_path = tmp_path / "good.json"
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome)})
    save_cache(good_path, cache)
    mismatched = load_cache(good_path, "a-different-replay-fp")
    assert mismatched.entries == {}
    assert mismatched.replay_fp == "a-different-replay-fp"

    # Unreadable path (a directory, not a file, raises IsADirectoryError on read).
    unreadable_path = tmp_path / "a-directory"
    unreadable_path.mkdir()
    assert load_cache(unreadable_path, replay_fp).entries == {}


# --- save_cache: atomic write (D6) ----------------------------------------------------------------


def test_save_cache_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    # A normal write lands via a .tmp sibling that is gone afterward.
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome)})
    save_cache(path, cache)
    assert path.exists()
    assert not path.with_suffix(path.suffix + ".tmp").exists()
    original_content = path.read_text()

    # None path is a no-op -- never raises, never creates a file.
    save_cache(None, cache)

    # A simulated mid-write failure (os.replace raising) must not corrupt or touch the pre-existing
    # cache, and save_cache itself must not raise (D6/D5: never fail trusting, never abort the run).
    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash between tmp-write and replace")

    monkeypatch.setattr(gate_cache.os, "replace", _boom)
    other_outcome = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4))
    other_cache = GateCache(replay_fp=replay_fp, entries={other_outcome.cycle_ts: ("evidence-fp-2", other_outcome)})
    save_cache(path, other_cache)  # must not raise

    assert path.read_text() == original_content  # the prior cache survives untouched
