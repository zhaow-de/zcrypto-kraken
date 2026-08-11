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
    kill file and the venue may all have changed. The only cost is one `Path.exists()` call plus
    two `os.lstat()` calls plus a venue read that is cached for `snapshot_max_age_seconds`.
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
        """Presence of one control file. The arm file fails closed by reading ABSENT on any
        doubt; the kill and restart-hold files fail closed by reading PRESENT on any doubt --
        opposite directions, both deliberate, because absence is what ARMS the first and PERMITS
        the second.

        `fail_open=False` (ARM_FILE): `Path.exists()`, `except OSError: return False`. A missing
        dir, a permission error, a broken symlink -- anything that keeps us from confirming the
        file is there -- reads as "not armed".

        `fail_open=True` (KILL_FILE, RESTART_HOLD_FILE): a direct `os.lstat()`, not
        `Path.exists()`/`os.path.lexists()` -- both of those swallow EVERY `OSError`/`ValueError`
        (EACCES, EIO, ELOOP, ENAMETOOLONG, a stale mount, a chmod-000 parent, an embedded NUL)
        into `False`, which is exactly the wrong direction for a fail-open file: "can't tell"
        would silently read as "no kill switch" and permit. Only `FileNotFoundError` -- the file
        genuinely is not there -- reads as absent; every other `OSError`, and `ValueError` (which
        `os.lstat` raises rather than `OSError` for an embedded NUL byte -- there is no path on
        disk for that to be a filesystem error about), reads as present and refuses.
        """
        path = self._dir / name
        if not fail_open:
            try:
                return path.exists()
            except OSError:
                return False
        try:
            os.lstat(path)
        except FileNotFoundError:
            return False
        except OSError, ValueError:
            return True  # can't tell -> assume present -> refuse
        return True

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
        # Python's own definition of naive is `tzinfo is None OR utcoffset() is None` -- a tzinfo
        # object that itself returns None from utcoffset() is still naive by that rule and still
        # raises the identical TypeError, so check utcoffset() rather than tzinfo alone; it
        # subsumes the plain `tzinfo is None` case for free (datetime.utcoffset() returns None
        # whenever tzinfo is None, without raising).
        if not isinstance(snap, VenueStatus) or snap.observed_at.utcoffset() is None:
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
