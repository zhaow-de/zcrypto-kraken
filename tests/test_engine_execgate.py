from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path

import pytest
import yaml

from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, exec_dir
from cli.engine.venue import VenueStatus

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


_VERIFIED_VERSION = "1.230.0"  # in cli/engine/order-semantics-verified.json


# The running-nautilus input is held VERIFIED so it contributes no reason to tests about some other
# gate input; left to the real interpreter, this file would assert against whatever version happens
# to be installed and flip wholesale on the next bump.
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
    # D7's latch: a kill switch that self-heals is not a kill switch.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.NONE
    assert (exec_dir(tmp_path) / KILL_FILE).exists()


def test_the_kill_switch_refuses_even_when_every_other_input_is_permissive(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("kill_switch",)  # the ONLY reason — everything else was fine


def test_the_kill_switch_does_not_SUPPRESS_the_other_reasons(tmp_path):
    """Kill does not short-circuit the other reasons. `if kill: return GateVerdict(NONE,
    ("kill_switch",), {})` is the natural way to express "kill overrides everything": it reports one
    reason and sends the operator to remove the kill file, only to be refused again by the arm file
    they were never told about."""
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
    # 29 s and 31 s straddle ExecutionGate's snapshot_max_age_seconds default.
    assert gate.evaluate(NOW + timedelta(seconds=29)).level == GateLevel.FULL
    assert calls["n"] == 1
    assert gate.evaluate(NOW + timedelta(seconds=31)).level == GateLevel.NONE
    assert calls["n"] == 2


def test_a_restart_hold_caps_at_reduce_only(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).write_text("2026-08-11T11:59:00Z")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.REDUCE_ONLY
    assert v.reasons == ("restart_hold",)


def test_every_applicable_reason_is_reported_not_just_the_first(tmp_path):
    (exec_dir(tmp_path)).mkdir(parents=True)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False))
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("config_not_armed", "arm_file_absent", "venue_not_online", "restart_hold")


def test_a_reader_that_RETURNS_garbage_refuses_rather_than_raising(tmp_path):
    # Nothing about `None` triggers an except clause, so an unguarded `venue.ok` raises out of
    # evaluate().
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


# --- no code path from an error to a permissive verdict -----------------------------------------


def test_an_unreadable_kill_file_refuses(tmp_path):
    # `Path.exists()` follows a broken symlink, finds nothing at the target, and reports absent.
    # Present AND UNREADABLE is exactly the case the kill switch exists to catch: refuse.
    gate = _all_clear(tmp_path)
    kill = exec_dir(tmp_path) / KILL_FILE
    kill.symlink_to(exec_dir(tmp_path) / "does-not-exist")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_a_symlink_loop_kill_file_refuses(tmp_path):
    gate = _all_clear(tmp_path)
    kill = exec_dir(tmp_path) / KILL_FILE
    kill.symlink_to(kill)
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_an_unreadable_restart_hold_file_caps_at_reduce_only(tmp_path):
    gate = _all_clear(tmp_path)
    hold = exec_dir(tmp_path) / RESTART_HOLD_FILE
    hold.symlink_to(exec_dir(tmp_path) / "does-not-exist")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.REDUCE_ONLY
    assert v.reasons == ("restart_hold",)


# `Path.exists()` swallows OSError and ValueError internally for every condition constructible on a
# real filesystem here, so the ARM branch's `except OSError: return False` has no real-world
# trigger: the raise is forced directly to prove the line still fails closed.


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
    # A naive `observed_at` makes `now - venue.observed_at` raise TypeError -- an unhandled
    # exception at a submission site has no safe direction.
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
    # A cache bounded only above (`delta <= max_age`) treats a backwards clock step as still fresh
    # -- a negative delta satisfies it for any max_age -- and never re-reads.
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
    v = gate.evaluate(NOW - timedelta(hours=1))
    assert calls["n"] == 2
    assert v.level == GateLevel.NONE


def test_the_reported_snapshot_age_is_not_clamped_when_negative(tmp_path):
    # A negative age is an anomaly an operator needs to see, not a value to floor away to 0.0.
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    def future(*, now, opener=None):
        return VenueStatus(status="online", ok=True, observed_at=now + timedelta(seconds=5))

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=future)
    v = gate.evaluate(NOW)
    assert v.inputs["venue_snapshot_age_seconds"] == -5.0


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_a_chmod_000_directory_reads_the_kill_file_as_present(tmp_path):
    # A broken symlink does not reach the `except OSError` branch -- `lexists` swallows it. A
    # chmod-000 exec dir does: `os.lstat` on the kill file raises PermissionError. The same denied
    # directory also makes `armed` read absent, so `level == NONE` alone would not say whether the
    # kill-specific fail-open logic engaged -- assert the reason.
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
    # Python defines naive as `tzinfo is None OR utcoffset() is None`, so a tzinfo object whose own
    # `utcoffset()` returns None is naive too and raises the identical TypeError.
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


def test_an_embedded_nul_in_the_state_dir_refuses_rather_than_raising(tmp_path):
    # `os.lstat` raises ValueError, not OSError, for an embedded NUL, so `except OSError:` alone
    # lets it out of evaluate() -- and a raise is not a refusal.
    bad_dir = str(tmp_path) + "\x00evil"
    gate = ExecutionGate(armed_in_config=True, state_dir=bad_dir, venue_reader=_venue())
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


# --- the restart hold, written at startup ----------------------------------------------


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
    # The latch is the point: only a human removes it.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.REDUCE_ONLY
    assert (exec_dir(tmp_path) / RESTART_HOLD_FILE).exists()


# --- the running-nautilus input: the arming half of the order-semantics backstop ----------------


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
    """The constructed defect: fully armed, venue online, nothing held -- and the running adapter's
    order semantics never verified."""
    verdict = _gate_on_version(tmp_path, "1.232.0").evaluate(NOW)

    assert verdict.level == GateLevel.NONE
    assert "nautilus_unverified" in verdict.reasons
    assert verdict.inputs["nautilus_version"] == "1.232.0"
    assert verdict.inputs["nautilus_verified"] is False


def test_a_verified_running_nautilus_does_not_refuse_a_fully_armed_gate(tmp_path):
    """The true positive: a guard that refuses everything is as useless as one that refuses
    nothing."""
    verdict = _gate_on_version(tmp_path, _VERIFIED_VERSION).evaluate(NOW)

    assert verdict.level == GateLevel.FULL
    assert verdict.reasons == ()
    assert verdict.inputs["nautilus_verified"] is True


def test_the_version_input_is_inert_while_the_engine_rests_disarmed(tmp_path):
    """The version input does not perturb the disarmed resting state."""
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
        ('{"verified_nautilus_versions": ["1.230.0", 1231]}', "a MIXED list -- a real version beside a non-string"),
        ("{}", "the key missing entirely"),
    ],
)
def test_an_unusable_record_fails_closed_to_the_empty_set(tmp_path, monkeypatch, content, why):
    """A record that cannot be read cannot SHOW any version was verified, so it must yield the
    EMPTY set and refuse everything.

    The set itself is asserted, not merely that one probed version is refused: a failure open to
    some arbitrary non-empty set passes the weaker form.
    """
    from cli.engine.execgate import _verified_nautilus_versions

    record = tmp_path / "record.json"
    if content is not None:
        record.write_text(content)
    monkeypatch.setattr("cli.engine.execgate._VERIFIED_RECORD", record)

    assert _verified_nautilus_versions() == frozenset(), why
    for version in (_VERIFIED_VERSION, "1.231.0", "1.232.0", ""):
        verdict = _gate_on_version(tmp_path, version).evaluate(NOW)
        assert verdict.level == GateLevel.NONE
        assert "nautilus_unverified" in verdict.reasons


def test_the_committed_record_is_the_one_the_ansible_backstop_reads(tmp_path):
    """Single-sourced by construction: one file, two readers."""
    from cli.engine.execgate import _VERIFIED_RECORD, _verified_nautilus_versions

    repo = Path(__file__).resolve().parents[1]
    assert _VERIFIED_RECORD == repo / "cli" / "engine" / "order-semantics-verified.json"
    assert not (repo / "infra" / "ansible" / "order-semantics-verified.yml").exists()
    # Find the task by KEY and assert on that fact's own expression. Matching the file's text found
    # the path in a fail_msg while the real lookup() pointed elsewhere; stringifying the task dict and
    # searching THAT is the same defect one level in.
    role = yaml.safe_load((repo / "infra" / "ansible" / "roles" / "engine" / "tasks" / "main.yml").read_text())
    facts = next(mod for task in role for mod in task.values() if isinstance(mod, dict) and "engine_verified_nautilus" in mod)
    lookup = facts["engine_verified_nautilus"]
    assert "lookup('file', playbook_dir ~ '/../../cli/engine/order-semantics-verified.json')" in lookup, lookup
    assert _verified_nautilus_versions() == frozenset({"1.230.0", "1.231.0", "2.0.0rc4.dev20260825"}), (
        "the record changed. If an attended order-semantics pass really ran, update this "
        "deliberately alongside the new docs/reference/adapter-verification/ record -- and sweep the other "
        "homes of 'that version is unverified', enumerated in infra/runbooks/"
        "order-semantics-verification.md's write-up step, including this file"
    )
