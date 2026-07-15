from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cli.capture.errors import CaptureError
from cli.capture.segment_writer import verify_manifest
from cli.logging import get_logger

logger = get_logger("archive.pull")


@dataclass(frozen=True)
class VerifyResult:
    checked: int
    ok: int
    failed: tuple[str, ...]
    newest_ts: datetime | None
    verified: tuple[str, ...] = ()  # the final paths that verified OK -- the authority `prune_stale_parts` uses


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
    verified: list[str] = []
    newest: datetime | None = None
    for p in sorted(root.rglob("*.parquet")):
        if ".part" in p.name or ".held" in p.name:  # in-progress part / quarantined held-spill, no manifest
            continue
        checked += 1
        try:
            is_ok = verify_manifest(p)
        except CaptureError, IndexError:
            failed.append(str(p))
        else:
            if is_ok:
                ok += 1
                verified.append(str(p))
            else:
                failed.append(str(p))
        ts = _hour_ts(p)
        if ts is not None and (newest is None or ts > newest):
            newest = ts
    return VerifyResult(checked=checked, ok=ok, failed=tuple(failed), newest_ts=newest, verified=tuple(verified))


def prune_stale_parts(verified_finals: tuple[str, ...]) -> tuple[int, int]:
    """Delete the `<HH>.part####.parquet` siblings of each VERIFIED final. Returns (hours, parts_deleted).

    T0038: Role A's `rsync -a` has no `--delete` (by design -- the NAS is the only backup of an
    unbackfillable dataset, so a `--delete` would propagate a VPS loss to the backup), so already-merged
    parts pile up beside the finals until the mirror is majority stale parts. Any consumer that globs
    `**/*.parquet` then reads the hour TWICE, and L2 rows carry ABSOLUTE quantities, so a doubled stream
    reconstructs a *different* book.

    The safety rule is the whole design: a part is deleted ONLY when the hour has a final that VERIFIED
    against its manifest. `verified_finals` is exactly that set (from `verify_tree`), so an hour with no
    final, or one whose final is corrupt/unverifiable, is never touched -- its parts are then the only
    intact copy. NAS-only by construction: `zcrypto archive pull` is Role A's tool and never runs on the
    capture host, which manages its own parts. Pruning every verified final each cycle also drains the
    existing backlog on the first post-deploy run for free -- no separate sweep.
    """
    hours = parts = 0
    for final in verified_finals:
        fp = Path(final)
        # STRICT `<HH>.part<digits>.parquet` only. The glob `{stem}.part*.parquet` also matches a
        # non-daemon name -- an rsync artefact or a hand-made backup like `15.part0000-copy.parquet` --
        # and this deletes from the only copy of unbackfillable data, so a name the writer would never
        # emit is left ALONE, not swept (segment_writer's `_part_index` is the same paranoia).
        pat = re.compile(rf"{re.escape(fp.stem)}\.part\d+\.parquet\Z")
        siblings = [p for p in fp.parent.glob(f"{fp.stem}.part*.parquet") if pat.match(p.name)]
        pruned_here = 0
        for part in siblings:
            try:
                part.unlink()
            except OSError as exc:
                # Never let a single unlink failure escape as an unhandled exception: it would skip the
                # pull command's failed-verify -> exit-1 path. Log and keep going; the part simply stays.
                logger.warning("prune: could not delete stale part path=%s error=%s", part, exc)
                continue
            pruned_here += 1
        if pruned_here:
            hours += 1
            parts += pruned_here
    return hours, parts


def pull_lag_seconds(result: VerifyResult, *, now: datetime) -> float | None:
    if result.newest_ts is None:
        return None
    return (now - result.newest_ts).total_seconds()
