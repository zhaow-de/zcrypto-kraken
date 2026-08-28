from __future__ import annotations

import hashlib
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
    hashed: int = 0  # defaulted -- command.py's reconcile path (_lag) builds a VerifyResult without it


def _hour_ts(path: Path) -> datetime | None:
    # .../<YYYY>/<MM>/<DD>/<HH>.parquet
    try:
        hh = path.stem
        d, m, y = path.parent.name, path.parent.parent.name, path.parent.parent.parent.name
        return datetime(int(y), int(m), int(d), int(hh), tzinfo=UTC)
    except ValueError, IndexError:
        return None


# Spec 00102 D3. A final is re-hashed in the cycle whose rotation index equals its slice, so every
# final is re-hashed every 24 cycles with no state -- a pure function of the name and the CALLER'S
# counter, never the clock: the NAS loop's period is 3600 + work, so `now.hour` drifts every cycle
# and, when the period divides 24 h, fixed slices are never visited at all (measured in the spec) --
# and the 24-cycle guarantee itself holds only across an uninterrupted run, since the counter lives
# in the caller's memory and resets to 0 on restart.
# The assert is spec 00062's: a counter modulo 24 can only produce [0, 23], so a larger modulus would
# leave high slices permanently unreachable and their finals silently never re-hashed.
_ROTATION_SLICES = 24
assert _ROTATION_SLICES <= 24, "_ROTATION_SLICES > 24 would leave high slices unreachable from a counter modulo 24"


def slice_of(rel_name: str) -> int:
    """The re-verification slice of a final, in [0, _ROTATION_SLICES), from its root-relative posix name."""
    return int(hashlib.sha256(rel_name.encode()).hexdigest()[:8], 16) % _ROTATION_SLICES


def verify_tree(
    root: Path, *, now: datetime, hash_only: frozenset[str] | None = None, rotation_slice: int | None = None
) -> VerifyResult:
    """Walk every final under `root`; hash each against its sidecar, or only a subset.

    `hash_only=None` hashes every final -- the whole-archive sweep. A set of root-relative names hashes
    those plus the finals whose `slice_of` equals `rotation_slice` -- required with a set: the caller's
    cycle counter modulo 24, never the clock (spec 00102 D3) -- and STILL WALKS EVERY FINAL: `checked` and
    `newest_ts` -- and through it the pull-lag figure the NAS entrypoint reads as its dead-man signal --
    come from the walk, not the hash, so a cycle that transferred nothing keeps reporting freshness
    (spec 00102 D1). `verified` lists only the finals hashed AND ok, so under a narrowed scope
    `prune_stale_parts` reaches a final's parts on its arrival cycle (a transfer in a clean cycle is always hashed) or
    within 24 cycles (its slice), never later.
    """
    checked = ok = hashed = 0
    failed: list[str] = []
    verified: list[str] = []
    newest: datetime | None = None
    if hash_only is not None and rotation_slice is None:
        raise ValueError("a narrowed hash scope needs a rotation slice")
    for p in sorted(root.rglob("*.parquet")):
        if ".part" in p.name or ".held" in p.name:  # in-progress part / quarantined held-spill, no manifest
            continue
        checked += 1
        ts = _hour_ts(p)
        if ts is not None and (newest is None or ts > newest):
            newest = ts
        rel = p.relative_to(root).as_posix()
        if hash_only is not None and rel not in hash_only and slice_of(rel) != rotation_slice:
            continue
        hashed += 1
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
    return VerifyResult(checked=checked, ok=ok, failed=tuple(failed), newest_ts=newest, verified=tuple(verified), hashed=hashed)


@dataclass(frozen=True)
class RsyncOutcome:
    returncode: int
    transferred: frozenset[str]  # dest-relative names of the *.parquet files rsync received this run


def transferred_parquets(itemized: str) -> frozenset[str]:
    """The dest-relative `*.parquet` names in rsync's `--out-format='%i %n'` output.

    `%i` is the 11-character itemize string; a received regular file begins `>f` (`>f+++++++++` new,
    `>f.st......` re-sent). Nothing else is a transfer: `.f...p.....` is an attribute-only touch (this
    pull's --chmod, every run), `cd+++++++++` a directory, `*deleting` a deletion. Only `>f` files are
    worth a hash -- an unchanged file's bytes are the bytes the last hash already covered.
    """
    names: set[str] = set()
    for line in itemized.splitlines():
        flags, _, name = line.partition(" ")
        if flags.startswith(">f") and name.endswith(".parquet"):
            names.add(name)
    return frozenset(names)


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
