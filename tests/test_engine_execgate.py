from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

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
