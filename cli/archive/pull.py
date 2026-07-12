from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cli.capture.errors import CaptureError
from cli.capture.segment_writer import verify_manifest


@dataclass(frozen=True)
class VerifyResult:
    checked: int
    ok: int
    failed: tuple[str, ...]
    newest_ts: datetime | None


def _hour_ts(path: Path) -> datetime | None:
    # .../<YYYY>/<MM>/<DD>/<HH>.parquet
    try:
        hh = path.stem
        d, m, y = path.parent.name, path.parent.parent.name, path.parent.parent.parent.name
        return datetime(int(y), int(m), int(d), int(hh), tzinfo=UTC)
    except ValueError, IndexError:
        return None


def verify_tree(root: Path, *, now: datetime) -> VerifyResult:
    checked = ok = 0
    failed: list[str] = []
    newest: datetime | None = None
    for p in sorted(root.rglob("*.parquet")):
        if ".part" in p.name:  # in-progress current-hour part, no manifest yet
            continue
        checked += 1
        try:
            verified = verify_manifest(p)
        except CaptureError:
            failed.append(str(p))
        else:
            if verified:
                ok += 1
            else:
                failed.append(str(p))
        ts = _hour_ts(p)
        if ts is not None and (newest is None or ts > newest):
            newest = ts
    return VerifyResult(checked=checked, ok=ok, failed=tuple(failed), newest_ts=newest)


def pull_lag_seconds(result: VerifyResult, *, now: datetime) -> float | None:
    if result.newest_ts is None:
        return None
    return (now - result.newest_ts).total_seconds()
