from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cli.engine.venue import VenueStatus, read_system_status

ARM_FILE = "armed"
KILL_FILE = "kill"
RESTART_HOLD_FILE = "restart-hold"

_EXEC_SUBDIR = "exec"


class GateLevel:
    """What may be submitted right now. Ordered least- to most-permissive."""

    NONE = "none"
    REDUCE_ONLY = "reduce_only"
    FULL = "full"


LEVEL_CODE: dict[str, int] = {GateLevel.NONE: 0, GateLevel.REDUCE_ONLY: 1, GateLevel.FULL: 2}


def exec_dir(state_dir: Path) -> Path:
    """The control-file directory. Presence is the whole protocol -- contents are informational."""
    return Path(state_dir) / _EXEC_SUBDIR


@dataclass(frozen=True)
class GateVerdict:
    """`reasons` is a TUPLE, not a single string, and carries EVERY condition that restricted the
    level -- several routinely apply at once (the disarmed resting state has both an absent arm
    file and a restart hold), and reporting only the first sends an operator to fix one condition
    while still refused. Order is declaration order in `evaluate`, so output is deterministic."""

    level: str
    reasons: tuple[str, ...]
    inputs: dict = field(default_factory=dict)


class ExecutionGate:
    """The single predicate every submission must pass.

    Cheap and side-effect-free by construction so that callers evaluate it immediately before
    EVERY submission rather than once per cycle: a resting post-only order that later crosses is a
    second submission decision, taken minutes after cycle entry, by which time the arm file, the
    kill file and the venue may all have changed. The only cost is two/three `Path.exists()` calls
    plus a venue read that is cached for `snapshot_max_age_seconds`.
    """

    def __init__(
        self,
        *,
        armed_in_config: bool,
        state_dir: Path,
        venue_reader=read_system_status,
        snapshot_max_age_seconds: float = 30.0,
    ) -> None:
        self._armed_in_config = armed_in_config
        self._dir = exec_dir(state_dir)
        self._venue_reader = venue_reader
        self._max_age = snapshot_max_age_seconds
        self._snapshot: VenueStatus | None = None

    def _present(self, name: str, *, fail_open: bool) -> bool:
        """Presence of one control file, with the safe error-direction split by what the file
        MEANS. `fail_open=False` (ARM_FILE): a missing dir, a permission error, a broken symlink
        all read as "absent" -- the safe direction for a key that must be affirmatively present to
        arm. `fail_open=True` (KILL_FILE, RESTART_HOLD_FILE): the safe direction is the opposite,
        because absence is what PERMITS -- "can't tell" must read as "assume present" and refuse,
        never as "no kill switch". Uses `os.path.lexists` rather than `Path.exists` for the
        fail_open case: `exists` follows the final symlink, so a broken symlink or a symlink loop
        reads as absent and silently permits -- `lexists` only asks whether something is there,
        which a broken link or a loop both satisfy. A whole-directory failure (e.g. the exec dir
        itself unreadable) still refuses either way, because the arm-file check on that same
        directory reads absent too.
        """
        try:
            if fail_open:
                return os.path.lexists(self._dir / name)
            return (self._dir / name).exists()
        except OSError:
            return fail_open

    def _venue(self, now: datetime) -> VenueStatus:
        snap = self._snapshot
        if snap is not None:
            # Valid iff `now` is at or after the cached reading AND within the bound -- NOT just
            # `delta <= max_age`. A clock that has stepped backwards makes delta negative, which
            # satisfies `<= max_age` for any max_age, so the old snapshot (however permissive) is
            # returned as still fresh and the reader is never called again. The floor forces a
            # re-read whenever `now` is not sequenced after the reading it would be trusting.
            delta = (now - snap.observed_at).total_seconds()
            if 0 <= delta <= self._max_age:
                return snap
        try:
            snap = self._venue_reader(now=now)
        except Exception:  # noqa: BLE001 -- a raising reader must refuse, never propagate
            snap = VenueStatus(status="unreachable", ok=False, observed_at=now)
        # A reader that RETURNS garbage is as dangerous as one that raises: `venue.ok` on a None
        # would raise AttributeError out of evaluate(), and at a 00090 submission site an
        # unhandled exception is not a refusal -- it has no safe direction. Validate the type, and
        # validate the one field evaluate() subtracts against `now`: a naive `observed_at` raises
        # `TypeError: can't subtract offset-naive and offset-aware datetimes` the instant it meets
        # an aware `now`, in both the age computation below and the cache check above -- the same
        # unhandled-exception-at-a-submission-site problem as a bad type, so the same fallback.
        if not isinstance(snap, VenueStatus) or snap.observed_at.tzinfo is None:
            snap = VenueStatus(status="unreadable", ok=False, observed_at=now)
        self._snapshot = snap
        return snap

    def evaluate(self, now: datetime) -> GateVerdict:
        armed_file = self._present(ARM_FILE, fail_open=False)
        kill = self._present(KILL_FILE, fail_open=True)
        hold = self._present(RESTART_HOLD_FILE, fail_open=True)
        venue = self._venue(now)
        # Unclamped on purpose: a negative age (the venue reading is dated AFTER `now`) is an
        # anomaly an operator needs to see, not a value to floor away to a reassuring 0.0.
        age = (now - venue.observed_at).total_seconds()

        reasons: list[str] = []
        level = GateLevel.FULL

        # Declaration order IS the reported order. Each condition appends independently; none
        # short-circuits, because the caller needs the complete picture.
        if kill:
            reasons.append("kill_switch")
            level = GateLevel.NONE
        if not self._armed_in_config:
            reasons.append("config_not_armed")
            level = GateLevel.NONE
        if not armed_file:
            reasons.append("arm_file_absent")
            level = GateLevel.NONE
        if not venue.ok:
            reasons.append("venue_not_online")
            level = GateLevel.NONE
        if hold:
            reasons.append("restart_hold")
            if level != GateLevel.NONE:
                level = GateLevel.REDUCE_ONLY

        return GateVerdict(
            level=level,
            reasons=tuple(reasons),
            inputs={
                "armed_in_config": self._armed_in_config,
                "arm_file": armed_file,
                "kill_file": kill,
                "restart_hold": hold,
                "venue_status": venue.status,
                "venue_snapshot_age_seconds": age,
            },
        )
