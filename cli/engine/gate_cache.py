"""The gate-export scoring cache primitives (spec 00060): fingerprints, load/save, and the
`GateCache` container that lets `_evaluate_journal` reuse a prior run's `CycleOutcome`s instead of
re-replaying every journaled cycle. Pure and file-format only -- no journal/replay wiring here (see
cli.engine.command for the `--cache` opt-in).

Two fingerprints (D2/D3): `evidence_fingerprint` covers what a single cycle's replay verdict
depends on from the journal side (every journaled SnapshotEntry IN FULL -- pair, grid, n_bars,
first_ts, last_ts, content_hash, path, not just content_hash -- plus cycle_ts, completed_at,
final_targets) -- a mismatch invalidates just that cycle's entry. `replay_fingerprint` covers the
REPLAY CODE instead -- the source bytes of the modules that determine a replay's result on either
the "fast" or "verified" route, the effective CrossfreqSystemConfig, the replay path itself, and
the execution environment (installed numpy version, Python major.minor) -- stored once per cache
file; a mismatch invalidates the whole cache. Deliberately over-sensitive (a comment-only edit to a
covered module, or a `uv.lock` bump that changes numpy/Python numeric behaviour with the journal
and replay code otherwise unchanged, costs one full rebuild): over-invalidation is safe,
under-invalidation silently corrupts gate evidence (T0074).

D5 -- fail open, never fail trusting: `load_cache` never raises; any problem (absent/unreadable/
truncated/unparseable file, wrong schema_version, or a replay_fp mismatch) degrades to an EMPTY
cache, which forces every cycle to be replayed. D6 -- `save_cache` writes atomically (`<path>.tmp`
+ os.replace) and never raises on write failure -- a crash or a failed write leaves the previous
cache intact, and the cache is an optimization: the run already succeeded without it.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from cli.engine.concordance import CycleOutcome
from cli.engine.journal import CycleRecord
from cli.logging import get_logger
from cli.portfolio import CrossfreqSystemConfig

logger = get_logger("engine.gate_cache")

CACHE_SCHEMA_VERSION = 2
_ROTATION_SLICES = 24

# The modules that determine a replay's result (D3): source-bytes changes to any of these must
# invalidate the whole cache. Monkeypatched by tests to point at synthetic files instead of
# mutating this repo's real source on disk.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPLAY_CODE_PATHS: tuple[Path, ...] = (
    # LIVE -- reachable on the "fast" route _evaluate_journal actually uses.
    _REPO_ROOT / "cli" / "portfolio" / "crossfreq_system.py",
    _REPO_ROOT / "cli" / "portfolio" / "crossfreq.py",
    _REPO_ROOT / "cli" / "risk" / "limits.py",
    _REPO_ROOT / "cli" / "risk" / "governor.py",
    _REPO_ROOT / "cli" / "engine" / "concordance.py",
    _REPO_ROOT / "cli" / "engine" / "journal.py",
    # LATENT -- only reachable on the "verified" route; covered anyway per D3's
    # over-invalidation-is-safe rationale even though no caller passes path="verified" today.
    _REPO_ROOT / "cli" / "alpha" / "a1.py",
    _REPO_ROOT / "cli" / "alpha" / "a2.py",
    _REPO_ROOT / "cli" / "portfolio" / "builder.py",
    _REPO_ROOT / "cli" / "benchmark" / "strategies.py",
)


def replay_fingerprint(config: CrossfreqSystemConfig = CrossfreqSystemConfig(), *, path: str = "fast") -> str:
    """sha256 over the source bytes of the modules that determine a replay's result, the effective
    config, the replay path ("fast"/"verified" select different builders -- a route switch must
    not serve the other route's cached verdicts), and the execution environment (T0074: numpy
    version + Python major.minor -- a `uv.lock` bump can change numeric behaviour with the journal
    and every covered module's bytes unchanged, which would otherwise serve a stale cached PASS).
    Deliberately over-sensitive: a comment-only edit to any covered module, a numpy version
    change, or a Python MINOR bump all invalidate the cache. A Python PATCH release deliberately
    does not -- patch releases do not change float arithmetic, so the full rebuild would buy
    nothing; `sys.version_info[:2]` is the digested value."""
    digest = hashlib.sha256()
    for module_path in _REPLAY_CODE_PATHS:
        digest.update(module_path.read_bytes())
    digest.update(repr(config).encode())
    digest.update(path.encode())
    try:
        numpy_version = version("numpy")
    except PackageNotFoundError:
        numpy_version = "numpy-not-found"
    digest.update(numpy_version.encode())
    digest.update(repr(sys.version_info[:2]).encode())
    return digest.hexdigest()


def evidence_fingerprint(record: CycleRecord) -> str:
    """sha256 over everything a replay verdict depends on from the journal side: every journaled
    SnapshotEntry in FULL (pair, grid, n_bars, first_ts, last_ts, content_hash, path) in canonical
    (pair, grid) order, plus cycle_ts, completed_at, final_targets. The full entry, not just
    content_hash, because replay_cycle also reconciles freshly read data against
    n_bars/first_ts/last_ts and raises EngineJournalError on disagreement -- a content_hash-only
    fingerprint would let a cached PASS survive a metadata tamper the real replay would reject."""
    ordered = sorted(record.snapshots, key=lambda s: (s.pair, s.grid))
    payload = {
        "snapshots": [
            {
                "pair": s.pair,
                "grid": s.grid,
                "n_bars": s.n_bars,
                "first_ts": s.first_ts.isoformat(),
                "last_ts": s.last_ts.isoformat(),
                "content_hash": s.content_hash,
                "path": s.path,
            }
            for s in ordered
        ],
        "cycle_ts": record.cycle_ts.isoformat(),
        "completed_at": record.completed_at.isoformat(),
        "final_targets": record.final_targets,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def slice_of(cycle_ts: datetime) -> int:
    """The cycle's permanent re-verification slice, in [0, _ROTATION_SLICES) (D2). sha256 over the
    ISO timestamp -- NOT the builtin hash(), which is not guaranteed stable across processes or
    releases -- and keyed on cycle_ts, NOT a loop index or list position: the journal grows and
    artifact ordering can shift, so an index-keyed slice would move between runs and coverage would
    be neither uniform nor provable. A cycle's slice is therefore a fixed property of the cycle,
    for all time."""
    digest = hashlib.sha256(cycle_ts.isoformat().encode())
    return int(digest.hexdigest(), 16) % _ROTATION_SLICES


def due_for_reverification(cycle_ts: datetime, now: datetime) -> bool:
    """True when this cycle falls in the run's current slice (D3): `now.hour % _ROTATION_SLICES`.
    Stateless -- no rotation cursor to persist, corrupt, or reset."""
    return slice_of(cycle_ts) == now.hour % _ROTATION_SLICES


@dataclass(frozen=True)
class GateCache:
    """`entries` maps a cycle's cycle_ts to its (evidence_fingerprint, CycleOutcome, verified_at)
    triple (schema v2, D5). `verified_at` is when the entry was last *actually replayed*: a cache
    hit carries the stored value forward, a replay stamps `now`.

    `rejected` distinguishes, for the caller's invalidated-metric (D8), "empty because no cache
    file existed" (rejected=False) from "empty because a file existed but load_cache discarded it"
    (rejected=True: wrong schema_version, a replay_fp mismatch, or an unreadable/unparseable file)
    -- load_cache's fail-open contract (never raise) is unchanged either way."""

    replay_fp: str
    entries: dict[datetime, tuple[str, CycleOutcome, datetime]]
    rejected: bool = False


def oldest_verification_age(cache: GateCache, now: datetime) -> float | None:
    """now - min(verified_at) in seconds, across every entry (D5); None when the cache is empty.
    Makes the cache's staleness observable -- a rotation that silently stops looks exactly like a
    healthy cache without this."""
    if not cache.entries:
        return None
    oldest = min(verified_at for _, _, verified_at in cache.entries.values())
    return (now - oldest).total_seconds()


def _outcome_to_dict(outcome: CycleOutcome) -> dict:
    return {
        "cycle_ts": outcome.cycle_ts.isoformat(),
        "completed_at": outcome.completed_at.isoformat(),
        "compare_passed": outcome.compare_passed,
        "mismatch": outcome.mismatch,
        "validation_failed": outcome.validation_failed,
    }


def _outcome_from_dict(d: dict) -> CycleOutcome:
    return CycleOutcome(
        cycle_ts=datetime.fromisoformat(d["cycle_ts"]),
        completed_at=datetime.fromisoformat(d["completed_at"]),
        compare_passed=d["compare_passed"],
        mismatch=d["mismatch"],
        validation_failed=d["validation_failed"],
    )


def load_cache(path: Path | None, replay_fp: str) -> GateCache:
    """Read + validate. Returns an EMPTY cache (never raises) on: path None/absent, unreadable,
    unparseable, wrong schema_version, or a replay_fp mismatch (D3/D5). `rejected` is True only
    for the latter group -- a path that existed but was discarded -- never for path None/absent."""
    empty = GateCache(replay_fp=replay_fp, entries={})
    if path is None or not path.exists():
        return empty
    rejected = GateCache(replay_fp=replay_fp, entries={}, rejected=True)
    try:
        payload = json.loads(path.read_text())
        if payload["schema_version"] != CACHE_SCHEMA_VERSION:
            return rejected
        if payload["replay_fp"] != replay_fp:
            return rejected
        entries: dict[datetime, tuple[str, CycleOutcome, datetime]] = {}
        for item in payload["entries"]:
            outcome = _outcome_from_dict(item)
            verified_at = datetime.fromisoformat(item["verified_at"])
            entries[outcome.cycle_ts] = (item["evidence_fp"], outcome, verified_at)
        return GateCache(replay_fp=replay_fp, entries=entries)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("load_cache: failed reading %s (%s); falling back to a full replay", path, exc)
        return rejected


def save_cache(path: Path | None, cache: GateCache) -> None:
    """Atomic <path>.tmp + os.replace. No-op when path is None. Never raises on write failure --
    log and continue (the cache is an optimization; the run already succeeded)."""
    if path is None:
        return
    try:
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "replay_fp": cache.replay_fp,
            "entries": [
                {"evidence_fp": evidence_fp, "verified_at": verified_at.isoformat(), **_outcome_to_dict(outcome)}
                for _, (evidence_fp, outcome, verified_at) in sorted(cache.entries.items())
            ],
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True))
        os.replace(tmp_path, path)
    except (OSError, TypeError) as exc:
        logger.warning("save_cache: failed writing %s (%s); continuing without an updated cache", path, exc)
