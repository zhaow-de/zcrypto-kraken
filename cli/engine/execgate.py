from __future__ import annotations

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
    while still refused. Order is declaration order in `_evaluate`, so output is deterministic."""

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

    def _present(self, name: str) -> bool:
        # A missing exec dir, a permission error, a broken symlink -- all read as "absent", which
        # is the safe direction for `armed` and, for `kill`, is why the kill file's absence is
        # never load-bearing on its own: the gate still needs both arming keys.
        try:
            return (self._dir / name).exists()
        except OSError:
            return False

    def _venue(self, now: datetime) -> VenueStatus:
        snap = self._snapshot
        if snap is not None and (now - snap.observed_at).total_seconds() <= self._max_age:
            return snap
        try:
            snap = self._venue_reader(now=now)
        except Exception:  # noqa: BLE001 -- a raising reader must refuse, never propagate
            snap = VenueStatus(status="unreachable", ok=False, observed_at=now)
        # A reader that RETURNS garbage is as dangerous as one that raises: `venue.ok` on a None
        # would raise AttributeError out of evaluate(), and at a 00090 submission site an
        # unhandled exception is not a refusal -- it has no safe direction. Validate the type.
        if not isinstance(snap, VenueStatus):
            snap = VenueStatus(status="unreadable", ok=False, observed_at=now)
        self._snapshot = snap
        return snap

    def evaluate(self, now: datetime) -> GateVerdict:
        armed_file = self._present(ARM_FILE)
        kill = self._present(KILL_FILE)
        hold = self._present(RESTART_HOLD_FILE)
        venue = self._venue(now)
        age = max(0.0, (now - venue.observed_at).total_seconds())

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
