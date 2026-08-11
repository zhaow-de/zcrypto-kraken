from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, exec_dir
from cli.engine.venue import VenueStatus

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _venue(status="online", ok=True):
    def reader(*, now, opener=None):
        return VenueStatus(status=status, ok=ok, observed_at=now)

    return reader


def _all_clear(tmp_path: Path) -> ExecutionGate:
    """Every control file in its permissive state: armed present, no kill, no restart hold."""
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARM_FILE).touch()
    return ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue())


def test_all_clear_is_full(tmp_path):
    v = _all_clear(tmp_path).evaluate(NOW)
    assert v.level == GateLevel.FULL
    assert v.reasons == ()


def test_config_false_refuses_even_with_the_arm_file(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "config_not_armed" in v.reasons


def test_config_true_without_the_arm_file_refuses(tmp_path):
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "arm_file_absent" in v.reasons


def test_the_kill_file_overrides_everything(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_nothing_in_the_gate_clears_the_kill_switch(tmp_path):
    # D7's latch. Evaluating repeatedly must never remove the file or stop honouring it: a kill
    # switch that self-heals is not a kill switch.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.NONE
    assert (exec_dir(tmp_path) / KILL_FILE).exists()


def test_the_kill_switch_refuses_even_when_every_other_input_is_permissive(tmp_path):
    # The override must not depend on anything else also being wrong.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("kill_switch",)  # the ONLY reason — everything else was fine


def test_the_kill_switch_does_not_SUPPRESS_the_other_reasons(tmp_path):
    """The companion the test above requires, and without it the whole all-reasons property is
    unguarded in the kill quadrant.

    Writing `if kill: return GateVerdict(NONE, ("kill_switch",), {})` is the NATURAL way to
    express "kill overrides everything", and it passes every other kill test here -- including
    the one directly above, whose asserted tuple is exactly what that early return produces. The
    multi-reason test cannot catch it either, because it sets no kill file. So this is the only
    test standing between the spec's D3 and an implementation that reports one reason and sends
    the operator to remove the kill file, only to be refused again by the arm file they were
    never told about.
    """
    (exec_dir(tmp_path)).mkdir(parents=True)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False))
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("kill_switch", "config_not_armed", "arm_file_absent", "venue_not_online")


def test_a_venue_in_maintenance_refuses(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False))
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons
    assert v.inputs["venue_status"] == "maintenance"


def test_a_raising_venue_reader_refuses_rather_than_propagating(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    def boom(*, now, opener=None):
        raise RuntimeError("reader blew up")

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=boom)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


def test_a_stale_snapshot_is_re_read_and_a_failed_re_read_refuses(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    calls = {"n": 0}

    def flaky(*, now, opener=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return VenueStatus(status="online", ok=True, observed_at=now)
        return VenueStatus(status="unreachable", ok=False, observed_at=now)

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=flaky)
    assert gate.evaluate(NOW).level == GateLevel.FULL
    # Inside the bound: cached, no second call, still permitted.
    assert gate.evaluate(NOW + timedelta(seconds=29)).level == GateLevel.FULL
    assert calls["n"] == 1
    # Past the bound: re-read, and the re-read fails, so it refuses.
    assert gate.evaluate(NOW + timedelta(seconds=31)).level == GateLevel.NONE
    assert calls["n"] == 2


def test_a_restart_hold_caps_at_reduce_only(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).write_text("2026-08-11T11:59:00Z")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.REDUCE_ONLY
    assert v.reasons == ("restart_hold",)


def test_every_applicable_reason_is_reported_not_just_the_first(tmp_path):
    # This is the live host's actual resting state: no arm file AND a restart hold. An
    # implementation that returns on the first failing check sends an operator to fix one
    # condition and leaves them still refused.
    (exec_dir(tmp_path)).mkdir(parents=True)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False))
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("config_not_armed", "arm_file_absent", "venue_not_online", "restart_hold")


def test_a_reader_that_RETURNS_garbage_refuses_rather_than_raising(tmp_path):
    # The sibling of the raising-reader case, and the easier one to get wrong: nothing about
    # `None` triggers an except clause, so an unguarded `venue.ok` raises out of evaluate().
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=lambda *, now: None)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


def test_a_missing_exec_dir_refuses_rather_than_raising(tmp_path):
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path / "nope", venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE


def test_inputs_carry_every_value_the_verdict_was_derived_from(tmp_path):
    v = _all_clear(tmp_path).evaluate(NOW)
    assert v.inputs["armed_in_config"] is True
    assert v.inputs["arm_file"] is True
    assert v.inputs["kill_file"] is False
    assert v.inputs["restart_hold"] is False
    assert v.inputs["venue_status"] == "online"
    assert v.inputs["venue_snapshot_age_seconds"] == 0.0


# --- fix round 1 -------------------------------------------------------------------------------
# Findings from the first review of commit 51b48e28. All three are the same class of bug: a
# per-file or per-field failure mode that `_present`'s / `_venue`'s error handling maps to the
# PERMISSIVE direction instead of the refusing one, in violation of the plan's global "no code
# path from an error to a permissive verdict" constraint.


def test_an_unreadable_kill_file_refuses(tmp_path):
    # A broken symlink at KILL_FILE: `Path.exists()` follows the link, finds nothing at the
    # target, and reports absent -- which used to read as "no kill switch" and permit. The file
    # PRESENT AND UNREADABLE is exactly the case the kill switch exists to catch: refuse.
    gate = _all_clear(tmp_path)
    kill = exec_dir(tmp_path) / KILL_FILE
    kill.symlink_to(exec_dir(tmp_path) / "does-not-exist")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_a_symlink_loop_kill_file_refuses(tmp_path):
    # The other shape of "present but Path.exists() can't resolve it": a self-referential symlink.
    gate = _all_clear(tmp_path)
    kill = exec_dir(tmp_path) / KILL_FILE
    kill.symlink_to(kill)
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_an_unreadable_restart_hold_file_caps_at_reduce_only(tmp_path):
    # Same fail_open asymmetry, the restart-hold sibling: a broken symlink used to read as
    # "no hold" and permit FULL; it must cap at REDUCE_ONLY like a plain touch()'d hold file does.
    gate = _all_clear(tmp_path)
    hold = exec_dir(tmp_path) / RESTART_HOLD_FILE
    hold.symlink_to(exec_dir(tmp_path) / "does-not-exist")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.REDUCE_ONLY
    assert v.reasons == ("restart_hold",)


def test_a_naive_observed_at_refuses_rather_than_raising(tmp_path):
    # `NOW` (the `now` argument) is tz-aware throughout this suite. A reader that hands back a
    # naive `observed_at` makes `now - venue.observed_at` raise TypeError the moment evaluate()
    # (or a later cache check) subtracts them -- an unhandled exception at what will be a
    # submission site, with no safe direction. Must refuse instead of raising.
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    def naive(*, now, opener=None):
        return VenueStatus(status="online", ok=True, observed_at=datetime(2026, 8, 11, 12, 0))

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=naive)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


def test_a_backwards_clock_forces_a_re_read(tmp_path):
    # A cache valid whenever `delta <= max_age` (no floor) treats a backwards clock step as
    # "still fresh" -- a negative delta satisfies `<= max_age` for any max_age -- and returns the
    # stale, possibly-permissive snapshot without ever calling the reader again. The fix requires
    # `0 <= delta <= max_age`, so a negative delta must force a re-read.
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    calls = {"n": 0}

    def flaky(*, now, opener=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return VenueStatus(status="online", ok=True, observed_at=now)
        return VenueStatus(status="maintenance", ok=False, observed_at=now)

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=flaky)
    assert gate.evaluate(NOW).level == GateLevel.FULL
    assert calls["n"] == 1
    # The clock steps backwards an hour. A cache bounded only above would still call this "fresh"
    # (delta = -3600s <= 30s) and return the stale FULL verdict without touching the reader.
    v = gate.evaluate(NOW - timedelta(hours=1))
    assert calls["n"] == 2
    assert v.level == GateLevel.NONE


def test_the_reported_snapshot_age_is_not_clamped_when_negative(tmp_path):
    # A future-dated reading (the venue reader's `observed_at` is ahead of the `now` evaluate()
    # was called with) must show up as a negative age in `inputs`, not get floored to 0.0 -- the
    # floor was hiding exactly the anomaly an operator needs to see.
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    def future(*, now, opener=None):
        return VenueStatus(status="online", ok=True, observed_at=now + timedelta(seconds=5))

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=future)
    v = gate.evaluate(NOW)
    assert v.inputs["venue_snapshot_age_seconds"] == -5.0


# --- fix round 2 -------------------------------------------------------------------------------
# The round-1 kill/restart-hold fix used `os.path.lexists`, whose `except OSError` branch is
# provably unreachable (CPython's `posixpath.lexists` swallows every OSError into False itself),
# so the fail-open direction never actually engaged for anything but ENOENT -- a chmod-000
# directory (EACCES), EIO, ELOOP, or ENAMETOOLONG all still silently read as "no kill switch".
# FIX 1 replaces it with a direct `os.lstat`, whose exceptions this module now handles itself.


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_a_chmod_000_directory_reads_the_kill_file_as_present(tmp_path):
    # `test_an_unreadable_kill_file_refuses` (round 1) used a broken symlink, which `lexists`
    # already handled correctly -- it does not prove the `except OSError` branch is reachable at
    # all. A chmod-000 exec dir does: `os.lstat` on the kill file raises PermissionError, which
    # round 1's `lexists`-based code silently swallowed to False. It also makes `armed` read
    # absent (via the SAME denied directory), so checking only `level == NONE` would not tell
    # whether the kill-specific fail-open logic engaged, or whether `arm_file_absent` alone was
    # doing the work -- assert the reason directly.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    exec_dir(tmp_path).chmod(0o000)
    try:
        v = gate.evaluate(NOW)
    finally:
        exec_dir(tmp_path).chmod(0o755)  # restore so tmp_path's own cleanup can remove it
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_a_tzinfo_with_no_utcoffset_refuses_rather_than_raising(tmp_path):
    # Python defines "naive" as `tzinfo is None OR utcoffset() is None`. Round 1's guard checked
    # only `tzinfo is None`, so a reader whose `observed_at` carries a tzinfo object that itself
    # returns None from `utcoffset()` is still naive by Python's own rule and still raises the
    # identical `TypeError: can't subtract offset-naive and offset-aware datetimes` the guard was
    # meant to close off.
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    class _NoOffsetTzinfo(tzinfo):
        def utcoffset(self, dt):
            return None

        def dst(self, dt):
            return None

        def tzname(self, dt):
            return None

    def broken_tz(*, now, opener=None):
        return VenueStatus(status="online", ok=True, observed_at=datetime(2026, 8, 11, 12, 0, tzinfo=_NoOffsetTzinfo()))

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=broken_tz)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


# --- fix round 3 -------------------------------------------------------------------------------
# FIX 1's os.lstat call is a regression risk of its own: os.lstat raises ValueError, not OSError,
# for a path with an embedded NUL byte (`Path.exists()`/`os.path.lexists()` swallow both, which is
# how round 1's dead branch masked this too), so the round-2 `except OSError:` alone let a NUL byte
# in the config-derived state_dir propagate straight out of evaluate().


def test_an_embedded_nul_in_the_state_dir_refuses_rather_than_raising(tmp_path):
    # `os.lstat` raises `ValueError: embedded null character in path`, not `OSError`, so
    # `except OSError:` alone does not catch it. The path is built from `state_dir` (config-
    # derived) plus a constant basename, so this can only arise from a malformed state_dir --
    # low likelihood, but the same "no code path from an error to a permissive verdict" rule
    # applies, and a raise is not a refusal.
    bad_dir = str(tmp_path) + "\x00evil"
    gate = ExecutionGate(armed_in_config=True, state_dir=bad_dir, venue_reader=_venue())
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons
