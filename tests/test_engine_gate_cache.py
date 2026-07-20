"""Tests for the gate-export scoring cache primitives (cli/engine/gate_cache.py, spec 00060):
replay_fingerprint (D3 -- covers the replay CODE, not just the journal), evidence_fingerprint
(D2), and load_cache/save_cache (D5 fail-open, D6 atomic write). Everything here is synthetic --
no dataset access, no real replay."""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

import cli.engine.gate_cache as gate_cache
from cli.engine import CycleOutcome, CycleRecord, SnapshotEntry
from cli.engine.gate_cache import (
    CACHE_SCHEMA_VERSION,
    GateCache,
    due_for_reverification,
    evidence_fingerprint,
    load_cache,
    oldest_verification_age,
    replay_fingerprint,
    save_cache,
    slice_of,
)
from cli.portfolio import CrossfreqSystemConfig

# --- fixtures: a synthetic CycleRecord, mirroring tests/test_engine_journal.py's shape ----------

CYCLE_TS = datetime(2026, 7, 10, 8, 0)
VALID_H4_LAST = datetime(2026, 7, 10, 4, 0)
VALID_DAILY_LAST = datetime(2026, 7, 9, 0, 0)


def _entry(
    pair: str, grid: str, first_ts: datetime, last_ts: datetime, content_hash: str = "a" * 64, n_bars: int = 3
) -> SnapshotEntry:
    return SnapshotEntry(
        pair=pair,
        grid=grid,
        n_bars=n_bars,
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


def test_evidence_fingerprint_changes_when_n_bars_tampered_leaving_content_hash_untouched():
    # replay_cycle reconciles the freshly read data against entry.n_bars/first_ts/last_ts and
    # raises EngineJournalError on disagreement (see cli.engine.concordance.replay_cycle) -- an
    # evidence fingerprint keyed on content_hash alone would keep serving a stale cached PASS for a
    # record whose n_bars a real replay would reject. content_hash is deliberately left unchanged
    # here to isolate the metadata-only tamper.
    base = evidence_fingerprint(_record())
    tampered_snapshots = (
        _entry("BTC", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "a" * 64, n_bars=4),
        _entry("BTC", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "b" * 64),
        _entry("ETH", "240", datetime(2026, 7, 9, 20, 0), VALID_H4_LAST, "c" * 64),
        _entry("ETH", "1440", datetime(2026, 7, 7, 0, 0), VALID_DAILY_LAST, "d" * 64),
    )
    assert evidence_fingerprint(_record(snapshots=tampered_snapshots)) != base


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


def test_replay_fingerprint_covers_the_live_and_latent_gap_modules():
    # D3 was missing every module below -- a revised drawdown_governor ladder or a changed
    # validate_record/snapshot_content_hash (both LIVE, reachable on the "fast" path
    # _evaluate_journal actually uses) flips a replay's verdict with an unchanged fingerprint; the
    # LATENT four are only reachable on the "verified" path but cost nothing to over-cover (D3).
    # Membership check on the REAL, non-monkeypatched list -- must fail against the original
    # four-file list (crossfreq_system.py/crossfreq.py/limits.py/concordance.py only).
    covered = set(gate_cache._REPLAY_CODE_PATHS)
    expected_new = {
        gate_cache._REPO_ROOT / "cli" / "risk" / "governor.py",  # LIVE
        gate_cache._REPO_ROOT / "cli" / "engine" / "journal.py",  # LIVE
        gate_cache._REPO_ROOT / "cli" / "alpha" / "a1.py",  # LATENT
        gate_cache._REPO_ROOT / "cli" / "alpha" / "a2.py",  # LATENT
        gate_cache._REPO_ROOT / "cli" / "portfolio" / "builder.py",  # LATENT
        gate_cache._REPO_ROOT / "cli" / "benchmark" / "strategies.py",  # LATENT
    }
    assert expected_new <= covered
    for path in expected_new:
        assert path.is_file(), f"{path} must exist -- a covered module must not silently hash nothing"


def test_replay_fingerprint_changes_when_a_live_gap_module_changes(tmp_path, monkeypatch):
    # The two LIVE gaps in particular: mutating either's bytes must change the fingerprint. Swaps
    # in a mutable tmp copy of the real file's current bytes so the real repo source is never
    # touched by the test.
    for real_path in (
        gate_cache._REPO_ROOT / "cli" / "risk" / "governor.py",
        gate_cache._REPO_ROOT / "cli" / "engine" / "journal.py",
    ):
        stand_in = tmp_path / real_path.name
        stand_in.write_bytes(real_path.read_bytes())
        patched = tuple(stand_in if p == real_path else p for p in gate_cache._REPLAY_CODE_PATHS)
        monkeypatch.setattr(gate_cache, "_REPLAY_CODE_PATHS", patched)

        fp_before = replay_fingerprint()
        stand_in.write_bytes(stand_in.read_bytes() + b"\n# mutated\n")
        fp_after = replay_fingerprint()
        assert fp_after != fp_before, f"{real_path} is not covered by the fingerprint"


def test_replay_fingerprint_covers_the_replay_path():
    # D3: "fast" and "verified" select different builders (build_crossfreq_system_fast vs
    # build_crossfreq_system); a fast->verified switch must not serve the other route's cached
    # verdicts. Must fail if path is not folded into the digest.
    assert replay_fingerprint(path="fast") != replay_fingerprint(path="verified")
    # Defaulting to "fast" preserves every existing no-path call site's fingerprint.
    assert replay_fingerprint() == replay_fingerprint(path="fast")


def test_replay_fingerprint_covers_the_environment(monkeypatch):
    # T0074: a uv.lock bump touching numpy/Python numeric behaviour must invalidate the cache even
    # though the journal and the replay code are byte-for-byte unchanged -- otherwise a stale cache
    # silently serves a pre-bump verdict as gate evidence.
    fp_before = replay_fingerprint()
    assert replay_fingerprint() == fp_before  # stable when nothing changes

    monkeypatch.setattr(gate_cache, "version", lambda _pkg: "99.99.99")
    fp_numpy_changed = replay_fingerprint()
    assert fp_numpy_changed != fp_before

    monkeypatch.undo()
    monkeypatch.setattr(gate_cache.sys, "version_info", (3, 99, 0, "final", 0))
    fp_python_changed = replay_fingerprint()
    assert fp_python_changed != fp_before


def test_replay_fingerprint_survives_missing_distribution(monkeypatch):
    # importlib.metadata.version raises PackageNotFoundError for an odd/uninstalled distribution --
    # per D5's fail-open philosophy this must degrade to a sentinel string, never crash the
    # fingerprint (the caller's OSError guard does not cover this exception type).
    def _boom(_pkg):
        raise gate_cache.PackageNotFoundError("numpy")

    monkeypatch.setattr(gate_cache, "version", _boom)
    fp = replay_fingerprint()
    assert isinstance(fp, str)
    assert len(fp) == 64


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
            passing.cycle_ts: ("evidence-fp-1", passing, CYCLE_TS),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, CYCLE_TS),
            validation_failed.cycle_ts: ("evidence-fp-3", validation_failed, CYCLE_TS),
        },
    )
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    assert loaded.replay_fp == replay_fp
    assert loaded.entries.keys() == cache.entries.keys()
    for cycle_ts, (evidence_fp, outcome, verified_at) in cache.entries.items():
        loaded_evidence_fp, loaded_outcome, loaded_verified_at = loaded.entries[cycle_ts]
        assert loaded_evidence_fp == evidence_fp
        assert loaded_outcome == outcome
        assert loaded_verified_at == verified_at
        # A cached failure must never come back as a pass.
        assert loaded_outcome.mismatch == outcome.mismatch
        assert loaded_outcome.validation_failed == outcome.validation_failed
        assert loaded_outcome.compare_passed == outcome.compare_passed


def test_cache_round_trip_preserves_verified_at(tmp_path):
    # D5/D6 (schema v2): verified_at round-trips alongside mismatch=True and validation_failed=True
    # entries, not just a passing one.
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    validation_failed = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=8), validation_failed=True, compare_passed=False)

    verified_at_passing = CYCLE_TS + timedelta(minutes=1)
    verified_at_mismatch = CYCLE_TS + timedelta(hours=4, minutes=1)
    verified_at_validation_failed = CYCLE_TS + timedelta(hours=8, minutes=1)

    cache = GateCache(
        replay_fp=replay_fp,
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing, verified_at_passing),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, verified_at_mismatch),
            validation_failed.cycle_ts: ("evidence-fp-3", validation_failed, verified_at_validation_failed),
        },
    )
    save_cache(path, cache)
    loaded = load_cache(path, replay_fp)

    assert loaded.entries[passing.cycle_ts][2] == verified_at_passing
    assert loaded.entries[mismatch.cycle_ts][2] == verified_at_mismatch
    assert loaded.entries[validation_failed.cycle_ts][2] == verified_at_validation_failed


# --- load_cache: fail open, never raise (D5) ------------------------------------------------------


def test_load_cache_degrades_never_raises(tmp_path):
    replay_fp = "fixed-replay-fp"

    # None path -- absent, not rejected.
    empty = load_cache(None, replay_fp)
    assert empty.entries == {}
    assert empty.replay_fp == replay_fp
    assert empty.rejected is False

    # Absent file -- absent, not rejected (no file ever existed to discard).
    absent_path = tmp_path / "does-not-exist.json"
    absent = load_cache(absent_path, replay_fp)
    assert absent.entries == {}
    assert absent.rejected is False

    # Truncated/unparseable JSON -- a file existed and was discarded.
    truncated_path = tmp_path / "truncated.json"
    truncated_path.write_text('{"schema_version": 1, "replay_fp": "x", "entries": [')
    truncated = load_cache(truncated_path, replay_fp)
    assert truncated.entries == {}
    assert truncated.rejected is True

    # Wrong schema_version -- discarded.
    wrong_schema_path = tmp_path / "wrong-schema.json"
    wrong_schema_path.write_text(json.dumps({"schema_version": CACHE_SCHEMA_VERSION + 1, "replay_fp": replay_fp, "entries": []}))
    wrong_schema = load_cache(wrong_schema_path, replay_fp)
    assert wrong_schema.entries == {}
    assert wrong_schema.rejected is True

    # replay_fp mismatch -- discarded.
    good_path = tmp_path / "good.json"
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome, CYCLE_TS)})
    save_cache(good_path, cache)
    mismatched = load_cache(good_path, "a-different-replay-fp")
    assert mismatched.entries == {}
    assert mismatched.replay_fp == "a-different-replay-fp"
    assert mismatched.rejected is True

    # Unreadable path (a directory, not a file, raises IsADirectoryError on read) -- discarded.
    unreadable_path = tmp_path / "a-directory"
    unreadable_path.mkdir()
    unreadable = load_cache(unreadable_path, replay_fp)
    assert unreadable.entries == {}
    assert unreadable.rejected is True


def test_v1_cache_is_rejected_wholesale(tmp_path):
    # D6: CACHE_SCHEMA_VERSION 1 -> 2 (verified_at changes the entry shape). A v1 file on disk must
    # be rejected wholesale -- no partial read of its (now-shaped-differently) entries -- forcing one
    # full replay and rewrite, per the existing fail-open contract (never a migration).
    replay_fp = "fixed-replay-fp"
    path = tmp_path / "gate-cache.json"
    v1_payload = {
        "schema_version": 1,
        "replay_fp": replay_fp,
        "entries": [
            {
                "evidence_fp": "evidence-fp",
                "cycle_ts": CYCLE_TS.isoformat(),
                "completed_at": (CYCLE_TS + timedelta(minutes=5)).isoformat(),
                "compare_passed": True,
                "mismatch": False,
                "validation_failed": False,
            }
        ],
    }
    path.write_text(json.dumps(v1_payload))

    loaded = load_cache(path, replay_fp)

    assert loaded.entries == {}
    assert loaded.rejected is True


# --- save_cache: atomic write (D6) ----------------------------------------------------------------


def test_save_cache_is_atomic(tmp_path, monkeypatch):
    path = tmp_path / "gate-cache.json"
    replay_fp = "fixed-replay-fp"

    # A normal write lands via a .tmp sibling that is gone afterward.
    outcome = _outcome()
    cache = GateCache(replay_fp=replay_fp, entries={outcome.cycle_ts: ("evidence-fp", outcome, CYCLE_TS)})
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
    other_cache = GateCache(replay_fp=replay_fp, entries={other_outcome.cycle_ts: ("evidence-fp-2", other_outcome, CYCLE_TS)})
    save_cache(path, other_cache)  # must not raise

    assert path.read_text() == original_content  # the prior cache survives untouched


# --- slice_of / due_for_reverification (D2/D3) ---------------------------------------------------


def test_slice_of_is_deterministic_and_process_stable():
    # Hardcoded (cycle_ts -> slice) pairs, computed once from the sha256(isoformat) % 24 derivation
    # and pinned here: a future change to the derivation must FAIL this test rather than silently
    # redistributing every cycle's slice, which would look like nothing happened while quietly
    # resetting the whole rotation schedule.
    pinned = {
        datetime(2026, 7, 10, 8, 0): 13,
        datetime(2020, 1, 1, 0, 0): 13,
        datetime(2026, 12, 31, 23, 0): 23,
    }
    for cycle_ts, expected_slice in pinned.items():
        assert slice_of(cycle_ts) == expected_slice
        # Same cycle_ts -> same slice across repeated calls (process-stable, not e.g. seeded by
        # builtin hash() randomization).
        assert slice_of(cycle_ts) == slice_of(cycle_ts)


def test_slice_of_distributes_without_gross_skew():
    base = datetime(2024, 1, 1, 0, 0)
    n = 480
    slices = [slice_of(base + timedelta(hours=i)) for i in range(n)]

    counts = Counter(slices)
    assert set(counts) == set(range(24))  # every slice covered

    mean = n / 24
    for slice_index, count in counts.items():
        assert count <= 3 * mean, f"slice {slice_index} holds {count}, more than 3x the mean {mean}"


def test_due_for_reverification_matches_the_run_hour():
    cycle_ts = datetime(2026, 7, 10, 8, 0)
    expected_slice = slice_of(cycle_ts)
    for hour in range(24):
        now = datetime(2026, 7, 15, hour, 0)
        assert due_for_reverification(cycle_ts, now) == (expected_slice == hour % 24)


# --- oldest_verification_age (D5) -----------------------------------------------------------------


def test_oldest_verification_age():
    now = CYCLE_TS + timedelta(days=2)

    assert oldest_verification_age(GateCache(replay_fp="fp", entries={}), now) is None

    passing = _outcome()
    mismatch = _outcome(cycle_ts=CYCLE_TS + timedelta(hours=4), mismatch=True, compare_passed=False)
    oldest_verified_at = CYCLE_TS - timedelta(hours=10)  # the least-recent of the two
    newest_verified_at = CYCLE_TS + timedelta(hours=1)

    cache = GateCache(
        replay_fp="fp",
        entries={
            passing.cycle_ts: ("evidence-fp-1", passing, newest_verified_at),
            mismatch.cycle_ts: ("evidence-fp-2", mismatch, oldest_verified_at),
        },
    )
    age = oldest_verification_age(cache, now)
    assert age == (now - oldest_verified_at).total_seconds()
