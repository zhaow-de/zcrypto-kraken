"""The gate-export scoring cache primitives (spec 00060): fingerprints, load/save, and the
`GateCache` container that lets `_evaluate_journal` reuse a prior run's `CycleOutcome`s instead of
re-replaying every journaled cycle. Pure and file-format only -- no journal/replay wiring here (see
cli.engine.command for the `--cache` opt-in).

Two fingerprints (D2/D3): `evidence_fingerprint` covers what a single cycle's replay verdict
depends on from the journal side (its snapshots' content hashes, cycle_ts, completed_at,
final_targets) -- a mismatch invalidates just that cycle's entry. `replay_fingerprint` covers the
REPLAY CODE instead -- the source bytes of the modules that determine a replay's result plus the
effective CrossfreqSystemConfig -- stored once per cache file; a mismatch invalidates the whole
cache. Deliberately over-sensitive (a comment-only edit to a covered module costs one full
rebuild): over-invalidation is safe, under-invalidation silently corrupts gate evidence.

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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from cli.engine.concordance import CycleOutcome
from cli.engine.journal import CycleRecord
from cli.logging import get_logger
from cli.portfolio import CrossfreqSystemConfig

logger = get_logger("engine.gate_cache")

CACHE_SCHEMA_VERSION = 1

# The modules that determine a replay's result (D3): source-bytes changes to any of these must
# invalidate the whole cache. Monkeypatched by tests to point at synthetic files instead of
# mutating this repo's real source on disk.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPLAY_CODE_PATHS: tuple[Path, ...] = (
    _REPO_ROOT / "cli" / "portfolio" / "crossfreq_system.py",
    _REPO_ROOT / "cli" / "portfolio" / "crossfreq.py",
    _REPO_ROOT / "cli" / "risk" / "limits.py",
    _REPO_ROOT / "cli" / "engine" / "concordance.py",
)


def replay_fingerprint(config: CrossfreqSystemConfig = CrossfreqSystemConfig()) -> str:
    """sha256 over the source bytes of the modules that determine a replay's result, plus the
    effective config. Deliberately over-sensitive: a comment-only edit invalidates the cache."""
    digest = hashlib.sha256()
    for path in _REPLAY_CODE_PATHS:
        digest.update(path.read_bytes())
    digest.update(repr(config).encode())
    return digest.hexdigest()


def evidence_fingerprint(record: CycleRecord) -> str:
    """sha256 over everything a replay verdict depends on from the journal side: every
    SnapshotEntry.content_hash in canonical (pair, grid) order, cycle_ts, completed_at,
    final_targets."""
    ordered = sorted(record.snapshots, key=lambda s: (s.pair, s.grid))
    payload = {
        "content_hashes": [s.content_hash for s in ordered],
        "cycle_ts": record.cycle_ts.isoformat(),
        "completed_at": record.completed_at.isoformat(),
        "final_targets": record.final_targets,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class GateCache:
    """`entries` maps a cycle's cycle_ts to its (evidence_fingerprint, CycleOutcome) pair."""

    replay_fp: str
    entries: dict[datetime, tuple[str, CycleOutcome]]


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
    unparseable, wrong schema_version, or a replay_fp mismatch (D3/D5)."""
    empty = GateCache(replay_fp=replay_fp, entries={})
    if path is None:
        return empty
    try:
        payload = json.loads(path.read_text())
        if payload["schema_version"] != CACHE_SCHEMA_VERSION:
            return empty
        if payload["replay_fp"] != replay_fp:
            return empty
        entries: dict[datetime, tuple[str, CycleOutcome]] = {}
        for item in payload["entries"]:
            outcome = _outcome_from_dict(item)
            entries[outcome.cycle_ts] = (item["evidence_fp"], outcome)
        return GateCache(replay_fp=replay_fp, entries=entries)
    except Exception as exc:
        logger.warning("load_cache: failed reading %s (%s); falling back to a full replay", path, exc)
        return empty


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
                {"evidence_fp": evidence_fp, **_outcome_to_dict(outcome)} for evidence_fp, outcome in cache.entries.values()
            ],
        }
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(payload, sort_keys=True))
        os.replace(tmp_path, path)
    except Exception as exc:
        logger.warning("save_cache: failed writing %s (%s); continuing without an updated cache", path, exc)
