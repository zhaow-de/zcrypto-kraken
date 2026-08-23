from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest

from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, exec_dir
from cli.engine.venue import VenueStatus

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


_VERIFIED_VERSION = "1.230.0"  # in cli/engine/order-semantics-verified.json


# Every test below is about some OTHER gate input -- control files, the venue reader, clock skew.
# The running-nautilus input is held VERIFIED for them so it contributes no reason; if it were left
# to the real interpreter, this file would be asserting against whatever version happens to be
# installed, and it would flip wholesale on the next bump. The tests that are ABOUT that input
# override this fixture explicitly and are grouped at the end of the file.
@pytest.fixture(autouse=True)
def _nautilus_verified(monkeypatch):
    monkeypatch.setattr("cli.engine.execgate._installed_nautilus_version", lambda: _VERIFIED_VERSION)


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


# --- Task 9 mutation-probe closeout -------------------------------------------------------------
# A mutation probe against the ARM branch's `except OSError: return False` (removing/narrowing it)
# survived every test above: on this Python's pathlib, `Path.exists()` already swallows OSError
# (and ValueError) internally for every condition constructible on a real filesystem here --
# chmod-000, a broken symlink, an embedded NUL byte all read `False` without raising (verified
# directly against pathlib, not assumed). The kill/hold branch's sibling except is proven reachable
# via `os.lstat`, which does NOT swallow those; the ARM branch's except has no such real-world
# trigger, so the raise is forced directly to prove the line still fails closed if it is ever hit.


def test_a_raising_arm_file_check_refuses_rather_than_propagating(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue())

    def boom(self, *args, **kwargs):
        raise OSError("simulated stat failure")

    orig_exists = Path.exists
    Path.exists = boom
    try:
        v = gate.evaluate(NOW)  # must not raise
    finally:
        Path.exists = orig_exists
    assert v.level == GateLevel.NONE
    assert "arm_file_absent" in v.reasons


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


# --- the restart hold, written at startup (Task 4) ----------------------------------------------


def test_write_restart_hold_creates_the_marker_and_the_dir(tmp_path):
    from cli.engine.execgate import write_restart_hold

    p = write_restart_hold(tmp_path, NOW)
    assert p.exists()
    assert p.name == RESTART_HOLD_FILE
    assert "2026-08-11T12:00:00" in p.read_text()  # informational only


def test_write_restart_hold_is_idempotent_and_restamps(tmp_path):
    from cli.engine.execgate import write_restart_hold

    write_restart_hold(tmp_path, NOW)
    later = NOW + timedelta(hours=3)
    p = write_restart_hold(tmp_path, later)
    assert "15:00:00" in p.read_text()  # the newest restart owns the marker


def test_nothing_in_the_gate_clears_the_restart_hold(tmp_path):
    # The latch is the point: only a human removes it. Evaluating many times must never clear it.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.REDUCE_ONLY
    assert (exec_dir(tmp_path) / RESTART_HOLD_FILE).exists()


# --- the running-nautilus input: the arming half of the order-semantics backstop ----------------
# The Ansible role refuses a CONVERGE that renders exec_armed=true on a version whose attended
# order-semantics pass has not run; this input refuses the ARMING. Both are needed: arming takes two
# keys and the arm file is placed by hand long after any converge, so a host that converged armed on
# a verified version and later took a newer image would otherwise arm on an unverified adapter.


def _gate_on_version(tmp_path: Path, version: str) -> ExecutionGate:
    """All-clear control files, so the ONLY thing that can refuse is the version input."""
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARM_FILE).touch()
    return ExecutionGate(
        armed_in_config=True,
        state_dir=tmp_path,
        venue_reader=_venue(),
        nautilus_version_reader=lambda: version,
    )


def test_an_unverified_running_nautilus_refuses_a_fully_armed_gate(tmp_path):
    """The constructed defect: both arming keys present, venue online, nothing held -- and the
    running adapter's order semantics have never been verified. Must refuse."""
    verdict = _gate_on_version(tmp_path, "1.231.0").evaluate(NOW)

    assert verdict.level == GateLevel.NONE
    assert "nautilus_unverified" in verdict.reasons
    assert verdict.inputs["nautilus_version"] == "1.231.0"
    assert verdict.inputs["nautilus_verified"] is False


def test_a_verified_running_nautilus_does_not_refuse_a_fully_armed_gate(tmp_path):
    """The true positive. A guard that refuses everything is as useless as one that refuses
    nothing -- on a recorded version this input must contribute no reason at all."""
    verdict = _gate_on_version(tmp_path, _VERIFIED_VERSION).evaluate(NOW)

    assert verdict.level == GateLevel.FULL
    assert verdict.reasons == ()
    assert verdict.inputs["nautilus_verified"] is True


def test_the_version_input_is_inert_while_the_engine_rests_disarmed(tmp_path):
    """The property that had to hold before this could ship: it must not perturb the resting
    state. Disarmed, the level is already NONE and the reported reasons keep naming every
    condition -- the new one joins them rather than replacing or reordering the others.
    """
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / RESTART_HOLD_FILE).touch()  # the deployed resting shape: no arm file, hold latched
    gate = ExecutionGate(
        armed_in_config=False,
        state_dir=tmp_path,
        venue_reader=_venue(),
        nautilus_version_reader=lambda: _VERIFIED_VERSION,
    )

    verdict = gate.evaluate(NOW)

    assert verdict.level == GateLevel.NONE
    assert verdict.reasons == ("config_not_armed", "arm_file_absent", "restart_hold")


@pytest.mark.parametrize("version", ["", "1.230", "1.230.0.post1", " 1.230.0", "1.2300"])
def test_a_version_that_is_not_exactly_recorded_refuses(tmp_path, version):
    """Exact-match membership, not a prefix or a substring: a near-miss is an unverified adapter."""
    verdict = _gate_on_version(tmp_path, version).evaluate(NOW)

    assert verdict.level == GateLevel.NONE
    assert "nautilus_unverified" in verdict.reasons


def test_a_raising_version_reader_refuses_rather_than_propagating(tmp_path):
    """Same direction as the venue reader: at a submission site an unhandled exception is not a
    refusal, it has no safe direction."""

    def boom():
        raise RuntimeError("no adapter")

    verdict = _gate_on_version(tmp_path, "unused").evaluate(NOW)  # sanity: the helper itself works
    assert "nautilus_unverified" in verdict.reasons

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue(), nautilus_version_reader=boom)
    assert "nautilus_unverified" in gate.evaluate(NOW).reasons


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (None, "absent"),
        ("{not json at all", "malformed"),
        ('{"verified_nautilus_versions": "1.230.0"}', "a string where a list belongs"),
        ('{"verified_nautilus_versions": [1230]}', "a non-string entry"),
        ("{}", "the key missing entirely"),
    ],
)
def test_an_unusable_record_fails_closed_to_the_empty_set(tmp_path, monkeypatch, content, why):
    """A record that cannot be read cannot SHOW any version was verified, so it must yield the
    EMPTY set and refuse everything.

    Asserting the set itself, not merely that one version is refused: a mutation that failed open
    to some arbitrary non-empty set SURVIVED the weaker form of this test, because the version it
    happened to contain was not the one being probed.
    """
    from cli.engine.execgate import _verified_nautilus_versions

    record = tmp_path / "record.json"
    if content is not None:
        record.write_text(content)
    monkeypatch.setattr("cli.engine.execgate._VERIFIED_RECORD", record)

    assert _verified_nautilus_versions() == frozenset(), why
    # ...and every version is refused through the gate, including the one really recorded.
    for version in (_VERIFIED_VERSION, "1.231.0", ""):
        verdict = _gate_on_version(tmp_path, version).evaluate(NOW)
        assert verdict.level == GateLevel.NONE
        assert "nautilus_unverified" in verdict.reasons


def test_the_committed_record_is_the_one_the_ansible_backstop_reads(tmp_path):
    """Single-sourced by construction: one file, two readers. If this record is ever duplicated
    under infra/, this test is where the divergence shows up."""
    from cli.engine.execgate import _VERIFIED_RECORD, _verified_nautilus_versions

    repo = Path(__file__).resolve().parents[1]
    assert _VERIFIED_RECORD == repo / "cli" / "engine" / "order-semantics-verified.json"
    assert not (repo / "infra" / "ansible" / "order-semantics-verified.yml").exists()
    role = (repo / "infra" / "ansible" / "roles" / "engine" / "tasks" / "main.yml").read_text()
    assert "cli/engine/order-semantics-verified.json" in role
    assert _verified_nautilus_versions() == frozenset({"1.230.0"}), (
        "the record changed. If an attended order-semantics pass really ran, update this "
        "deliberately alongside the new docs/research/ verification doc -- and sweep the other "
        "homes of 'only 1.230.0 is verified' named in the go-live topic's bump sub-item "
        "(docs/open-topics/T0085-final-pre-golive-steps.md), including this file"
    )
