"""Per-hour examination fingerprints for the reconcile skip-cache (spec 00097 D4/D5).

Mirror finals are immutable once pulled (written at hour close, hash-verified hourly by the NAS
pull), so `(size, mtime_ns)` identifies a final exactly; the fingerprint also records ABSENCES so a
file arriving late re-examines the hour. `load_cache` never raises — absent, corrupt, and
foreign-salt caches all read as empty, so every failure is fail-open to a SLOW full cycle, never to
a wrong skip. Written atomically (`checkpoint.py`'s tmp + `os.replace` idiom).

The `(size, mtime_ns)` pair is exactly the quick-check tuple the NAS's own `rsync -a` uses to decide
whether a file changed: a content change this fingerprint cannot see is one the transport would not
have delivered either.

PRESENCE COMES FROM `scans`, NEVER FROM A FRESH `stat` — the load-bearing contract, and the reason
`hour_fingerprint` takes the cycle's `scans` at all. The examination reads only what `scan_hours`
enumerated: a mirror that lands after the scan is `None` to it for the whole cycle. A fingerprint
that discovered presence by its own `stat` would therefore see files the examination will not, and
that is a live wrong-skip, not a theoretical one: the scan misses a late secondary, the examination
performs no witness-based heal, the fingerprint records the file as present and `complete=True` —
and the NEXT cycle, which does owe the heal, computes the same fingerprint and skips the hour
forever. Deriving presence from `scans` makes the hashed file-set exactly what the examination
reads, so every skew fails open instead: a post-scan arrival is `ABSENT` and uncacheable this cycle,
and a file that vanished after the scan fails its `stat` and is uncacheable too. It is also one
fewer `stat` per absent slot.

The overlay the reconciler WRITES is fingerprinted too — `already_minted` is the one per-hour verdict
input outside the mirrors, and it is read fresh (not from `scans`), so a fresh `stat` is the matching
source of truth. It is a BACKSTOP, not a replacement for the `delete_cache` that spec D4 requires of
a hand-repair: because the stored fingerprint is the pre-pass one, a MINTING cycle stores the
PRE-mint fingerprint, which is byte-identical to what removing the minted file restores — so for
that one hour, for one cycle, the backstop is blind and only `delete_cache` covers it. Its ABSENCE
deliberately does NOT set `complete=False`: no minted file is the ordinary case for a healthy hour,
and treating it as incomplete would make every such hour unskippable and delete the whole
optimization. `complete` is about the MIRROR finals an examination reads.

The LEDGER is deliberately not fingerprinted, though it is a verdict input (`_decided` suppresses,
and `_booked_dark`/`_booked_residual` are subtracted from what gets booked). It is ONE file shared by
every hour, so hashing it would move every hour's fingerprint on every append and delete the
optimization outright. A hand-repair that edits it is covered by the same required `delete_cache`.

Neither persistence call raises. `load_cache` returns `{}` for absent, corrupt, and foreign-salt
caches, and drops an individually malformed entry; `save_cache` swallows its write failure. Both are
fail-open to a SLOW full cycle, never to a wrong skip and never to a failed reconcile cycle — the
cache is an optimization, and a completed, correct cycle must not be turned into rc=1 by it.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from cli.logging import get_logger

from .settle import hour_path

logger = get_logger("archive.scan_cache")

ALGO_VERSION = 1
_FILENAME = "scan-cache.json"


@dataclass(frozen=True)
class CacheEntry:
    """One hour's FULL examination, as last performed."""

    fingerprint: str  # sha256 over the hour's file-set (presences with size+mtime_ns, plus absences)
    examined_at: str  # isoformat of the cycle-start `now` of that examination
    late_at_exam: bool  # it ran with the hour already past the late deadline
    failures: int  # failures attributed to this hour during it
    complete: bool  # no expected MIRROR final was absent at the time


_ENTRY_TYPES = {
    "fingerprint": str,
    "examined_at": str,
    "late_at_exam": bool,
    "failures": int,
    "complete": bool,
}


def algo_salt(min_gap_seconds: float, *, mint: bool) -> str:
    """The whole-cache invalidation key: everything outside the file-set that can change a VERDICT.

    `mint` is here as the second of two independent guards. Spec D4 already gates the cache to
    `--mint` cycles, so detect-only entries never reach a minting one — but a future caller that
    drops that gate would otherwise resurrect a hazard whose failure mode is a heal silently never
    performed. Cheap; a wrongly-inherited skip is not.
    """
    return f"v{ALGO_VERSION}:min_gap={min_gap_seconds!r}:mint={mint}"


def hour_fingerprint(
    hour: datetime,
    *,
    scans: dict[str, dict[str, dict[str, set[datetime]]]],
    primary_root: Path,
    secondary_root: Path,
    reconciled_root: Path,
    book_pairs: list[str],
    trade_pairs: list[str],
) -> tuple[str, bool]:
    """`(sha256, complete)` over every per-hour input this hour's verdict depends on.

    Both mirrors' finals, plus the overlay's minted file. `scans` is the cycle's own
    `{source: {kind: {pair: {hour}}}}` and is the ONLY authority on mirror presence — see the module
    docstring for why a fresh `stat` there is a wrong-skip, and for why the overlay is hashed but
    never counts toward `complete`.
    """
    lines: list[str] = []
    complete = True
    for kind, pairs in (("book", book_pairs), ("trades", trade_pairs)):
        for pair in pairs:
            for source, root in (("primary", primary_root), ("secondary", secondary_root)):
                if hour not in scans[source][kind].get(pair, set()):
                    # Not `stat`-ed at all: the examination will treat this slot as absent for the
                    # whole cycle no matter what is on disk, so the fingerprint must agree with it.
                    lines.append(f"ABSENT|{pair}|{kind}|{source}")
                    complete = False
                    continue
                try:
                    st = hour_path(root, pair, kind, hour).stat()
                    lines.append(f"{pair}|{kind}|{source}|{st.st_size}|{st.st_mtime_ns}")
                except OSError:
                    # The scan listed it and it is now unreadable — a file removed between scan and
                    # pre-pass, or ESTALE/EIO from a wobbling NFS mount. Neither may kill the cycle
                    # here: record it absent, which makes the hour UNCACHEABLE, so the examination
                    # reads the file itself and reports the error honestly through `_fail` (spec D4).
                    lines.append(f"ABSENT|{pair}|{kind}|{source}")
                    complete = False
            try:
                st = hour_path(reconciled_root, pair, kind, hour).stat()
                lines.append(f"{pair}|{kind}|overlay|{st.st_size}|{st.st_mtime_ns}")
            except OSError:
                lines.append(f"ABSENT|{pair}|{kind}|overlay")  # ordinary — `complete` is untouched
    lines.sort()  # canonical: a reordered pair list is the same file-set, not a new one
    return hashlib.sha256("\n".join(lines).encode()).hexdigest(), complete


def _cache_path(reconciled_root: Path) -> Path:
    return reconciled_root / _FILENAME


def _entry_from(raw: object) -> CacheEntry | None:
    """One stored entry, or `None` when the JSON does not describe one.

    JSON carries no types, so `CacheEntry(**raw)` accepts `{"examined_at": 5}` happily and the
    failure surfaces two calls later in `pick_audit_hours`' comparison. Validated here instead, and
    a rejected entry is DROPPED rather than poisoning the whole cache — its hour simply has no
    entry, which is a full examination.
    """
    if not isinstance(raw, dict) or raw.keys() != _ENTRY_TYPES.keys():
        return None
    # `type(...) is`, not `isinstance`: bool subclasses int, so `isinstance` keeps {"failures": false}
    # and that entry stays skippable.
    if any(type(raw[field]) is not expected for field, expected in _ENTRY_TYPES.items()):
        return None
    return CacheEntry(**raw)


def load_cache(reconciled_root: Path, *, salt: str) -> dict[str, CacheEntry]:
    """The cache, or `{}` — this function NEVER raises (fail-open to a slow full cycle, spec D4)."""
    try:
        payload = json.loads(_cache_path(reconciled_root).read_text())
        # isinstance, not duck-typing: a JSON-valid scalar (`null`, `3`) reaches .get and would raise
        # AttributeError — which the except tuple below must ALSO carry, belt and braces, because this
        # function's whole contract is "never raises". RecursionError is in that tuple for the same
        # reason: `json.loads` on a deeply nested file raises it, and it is a RuntimeError, not a
        # ValueError, so the obvious tuple misses it.
        if not isinstance(payload, dict) or not isinstance(payload.get("hours"), dict):
            return {}
        if payload.get("algo") != salt:
            return {}
        loaded = {hour: _entry_from(raw) for hour, raw in payload["hours"].items()}
        return {hour: entry for hour, entry in loaded.items() if entry is not None}
    except OSError, ValueError, TypeError, KeyError, AttributeError, RecursionError:
        return {}


def save_cache(reconciled_root: Path, entries: dict[str, CacheEntry], *, salt: str) -> None:
    """Publish the cache atomically. NEVER raises — a failed save degrades to a slow NEXT cycle.

    `checkpoint.py`'s idiom in full, including its cleanup of the partial `.tmp` a failed write
    leaves behind. It diverges in one deliberate place: `checkpoint.py` raises a typed error, this
    logs and returns. A checkpoint is the product; this cache is an optimization, so letting an
    ENOSPC/EROFS out of here would turn a completed, correct reconcile cycle into rc=1.
    """
    path = _cache_path(reconciled_root)
    tmp = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps({"algo": salt, "hours": {h: asdict(e) for h, e in entries.items()}}))
        os.replace(tmp, path)
    except (OSError, TypeError) as exc:
        # TypeError as well as OSError, matching `engine/gate_cache.py`: the dataclass validates
        # nothing at runtime, so an `examined_at` left as a datetime reaches `json.dumps` and
        # raises — an optimization's serialization bug must not fail a correct cycle either.
        with contextlib.suppress(OSError):  # cleanup is best-effort — it must never shadow `exc`
            tmp.unlink(missing_ok=True)
        logger.warning("archive reconcile: scan-cache save failed (%s) — the next cycle runs full", exc)


def delete_cache(reconciled_root: Path) -> None:
    """Drop the cache. This one RAISES, unlike its two siblings — deliberately, do not "fix" it.

    A failed `save_cache` is fail-open: the next cycle runs full. A SWALLOWED delete failure is
    fail-closed-wrong — the caller believes the cache is gone, the stale file survives under the
    same salt, and the next cycle honours stale skips.
    """
    _cache_path(reconciled_root).unlink(missing_ok=True)


def is_skippable(entry: CacheEntry | None, fingerprint: str, complete: bool) -> bool:
    """Spec 00097 D4: all five preconditions, in one place, fail-closed."""
    return (
        entry is not None
        and entry.fingerprint == fingerprint
        and entry.late_at_exam
        and entry.failures == 0
        and entry.complete
        and complete
    )


def pick_audit_hours(skippable_hours: list[str], entries: dict[str, CacheEntry], k: int = 2) -> list[str]:
    """The k skippable hours least recently FULLY examined — deterministic, no randomness (D5)."""
    return sorted(skippable_hours, key=lambda h: (entries[h].examined_at, h))[:k]
