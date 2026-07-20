"""The gate-export scoring cache primitives (spec 00060): fingerprints, load/save, and the
`GateCache` container that lets `_evaluate_journal` reuse a prior run's `CycleOutcome`s instead of
re-replaying every journaled cycle. Pure and file-format only -- no journal/replay wiring here (see
cli.engine.command for the `--cache` opt-in).

Two fingerprints (D2/D3): `evidence_fingerprint` covers what a single cycle's replay verdict
depends on from the journal side (every journaled SnapshotEntry IN FULL -- pair, grid, n_bars,
first_ts, last_ts, content_hash, path, not just content_hash -- plus cycle_ts, completed_at,
final_targets) -- a mismatch invalidates just that cycle's entry. `replay_fingerprint` covers the
REPLAY CODE instead -- the source bytes of the modules that determine a replay's result, the
effective CrossfreqSystemConfig, the replay path itself, and the execution environment (installed
numpy version, Python major.minor) -- stored once per cache file; a mismatch invalidates the whole
cache. Since spec 00065 that module set is DERIVED, not enumerated: `_replay_code_paths()` walks
the transitive `cli.*` import closure of `_REPLAY_ROOTS`. The hand-maintained list it replaced
covered 12 of those 61 modules and was wrong three separate times -- most consequentially it never
hashed `cli/portfolio/__init__.py`, the re-export layer every replay binds
`build_crossfreq_system_fast` through, so rebinding the fast builder to the verified one changed
every verdict while leaving the fingerprint byte-identical.

Deliberately over-sensitive (a comment-only edit to a covered module, or a `uv.lock` bump that
changes numpy/Python numeric behaviour with the journal and replay code otherwise unchanged, costs
one full rebuild): over-invalidation is safe, under-invalidation silently corrupts gate evidence
(T0074).

D5 -- fail open, never fail trusting: `load_cache` never raises; any problem (absent/unreadable/
truncated/unparseable file, wrong schema_version, or a replay_fp mismatch) degrades to an EMPTY
cache, which forces every cycle to be replayed. D6 -- `save_cache` writes atomically (`<path>.tmp`
+ os.replace) and never raises on write failure -- a crash or a failed write leaves the previous
cache intact, and the cache is an optimization: the run already succeeded without it.
"""

from __future__ import annotations

import ast
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
# due_for_reverification selects the current slice via `now.hour % _ROTATION_SLICES`, which can only
# ever produce [0, 23] -- any value > 24 would leave slices 24.._ROTATION_SLICES-1 permanently
# unreachable, silently never re-verified (the exact failure D2/D3 exist to prevent).
assert _ROTATION_SLICES <= 24, "_ROTATION_SLICES > 24 would leave high slices unreachable via now.hour % _ROTATION_SLICES"

# The replay entry points (spec 00065 D1). Coverage is DERIVED from these by _replay_code_paths()
# below -- the transitive cli.* import closure -- so the roots are the only hand-maintained input
# left, and therefore the only thing that can silently drift. concordance.py holds replay_cycle /
# compare_targets / evaluate_gate; command.py holds `_snapshot_reader` (the closure every replay
# reads price data through) and `_replay_one` (the exception->verdict classifier); dataset.py holds
# `read_parquet`, which feeds both that reader and the snapshot content hash.
#
# _REPO_ROOT and _REPLAY_ROOTS are read at call time, not captured, so tests can monkeypatch both
# at a synthetic tree instead of mutating this repo's real source on disk.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPLAY_ROOTS: tuple[Path, ...] = (
    _REPO_ROOT / "cli" / "engine" / "concordance.py",
    _REPO_ROOT / "cli" / "engine" / "command.py",
    _REPO_ROOT / "cli" / "ohlc" / "dataset.py",
)


def _resolve_module(dotted: str, repo_root: Path) -> list[Path]:
    """The files a dotted `cli.*` module name can live in, under `repo_root`. Non-`cli` names
    resolve to nothing (D3: third-party is out -- numpy's version is digested separately per T0074,
    and walking site-packages would be enormous and version-noisy).

    Returns BOTH `cli/pkg/__init__.py` and `cli/pkg.py`-style candidates when both exist, because
    D5's over-inclusion is the point: for `from cli.pkg import X`, `X` may be a submodule or a name
    re-exported by the package's `__init__`, and static analysis cannot always tell which. Hashing
    both is safe (over-invalidation costs one rebuild); hashing the wrong one silently corrupts gate
    evidence."""
    parts = dotted.split(".")
    if parts[0] != "cli":
        return []
    base = repo_root.joinpath(*parts)
    found = [candidate for candidate in (base / "__init__.py", base.with_suffix(".py")) if candidate.is_file()]
    # ANCESTOR PACKAGES (spec 00065 D10, added at review). Importing `cli.engine.command` EXECUTES
    # `cli/__init__.py` and `cli/engine/__init__.py` first -- unconditionally, by Python's import
    # machinery -- so their bytes determine a replay's result as surely as the leaf's do. Omitting
    # them was the same under-invalidation hole this iteration exists to close, one package over,
    # and it was exploitable: rebinding build_crossfreq_system_fast in `cli/engine/__init__.py`
    # changed every verdict at a BYTE-IDENTICAL fingerprint with the whole suite green. These
    # __init__ files are not inert -- `cli/engine/__init__.py` carries a live PEP 562 `__getattr__`.
    found.extend(_ancestor_packages(base, repo_root))
    return found


def _ancestor_packages(module_path: Path, repo_root: Path) -> list[Path]:
    """Every `__init__.py` between `repo_root` and `module_path`, exclusive of the module itself.
    Shared by `_resolve_module` (edges) and by the root seeding in `_replay_code_paths`, so the
    D10 rule cannot hold for one and not the other."""
    try:
        parts = module_path.relative_to(repo_root).parts
    except ValueError:
        return []
    return [ancestor for depth in range(1, len(parts)) if (ancestor := repo_root.joinpath(*parts[:depth], "__init__.py")).is_file()]


def _import_edges(module_path: Path, repo_root: Path) -> list[Path]:
    """The `cli.*` modules `module_path` imports. Best-effort BY DESIGN (D6): a file that cannot be
    read or parsed yields NO edges rather than raising, and the caller digests its bytes anyway. The
    safe direction is always-hash / sometimes-fail-to-traverse -- swallowing a SyntaxError into "no
    imports" is survivable, swallowing it into "not covered" is the exact under-invalidation this
    walker exists to close. Traversal loss is bounded: a file that does not parse does not import.

    TRAVERSAL LIMITS, stated in full because presenting one of them as the only one is how the
    ancestor-package gap stayed hidden: (1) only ABSOLUTE `cli.*` imports are traversed -- `cli/`
    contains none of the relative kind (verified: 0 of 134 modules), so no edge is lost today;
    (2) dynamic imports (`importlib`, `__import__`, a PEP 562 `__getattr__`) are invisible to a
    static walk -- `cli/engine/__init__.py` has such a `__getattr__`, which is one reason the
    superset test matters; (3) ancestor packages are handled explicitly in `_resolve_module`
    rather than falling out of the walk. A relative import added later
    would not be followed."""
    try:
        tree = ast.parse(module_path.read_bytes())
    except (OSError, SyntaxError, ValueError) as exc:
        logger.warning(
            "replay-fingerprint closure: cannot parse %s (%s); its bytes are still digested, but its imports are not traversed",
            module_path,
            exc,
        )
        return []
    edges: list[Path] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                edges.extend(_resolve_module(alias.name, repo_root))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # D5: the package itself AND each imported name as a possible submodule.
            edges.extend(_resolve_module(node.module, repo_root))
            for alias in node.names:
                edges.extend(_resolve_module(f"{node.module}.{alias.name}", repo_root))
    return edges


def _replay_code_paths() -> tuple[Path, ...]:
    """The transitive `cli.*` import closure of `_REPLAY_ROOTS` (spec 00065) -- the
    modules that determine a replay's result, DERIVED rather than enumerated. Replaces the
    hand-maintained twelve-path list, which covered 12 of these 61 modules (~20%) and was wrong
    three separate times; the re-export layers it missed (`cli/portfolio/__init__.py` above all)
    are how every replay binds `build_crossfreq_system_fast`.

    Coverage is MEASURED, not asserted -- the same phrase ("the modules that determine a replay's
    result") is what spec 00060 D3 claimed for the twelve-path list while it covered a fifth of
    them, so it is worth nothing without a check. `test_closure_covers_every_module_the_replay_roots_actually_execute`
    imports the roots in a clean subprocess and asserts this closure is a superset of what actually
    ran: 61 covered, 60 executed, 0 executed-but-uncovered, 1 harmless over-inclusion
    (`cli/engine/node.py`). That test is the claim; this docstring only reports it.

    A STATIC walk (D2), never `sys.modules`: a runtime view would make the fingerprint depend on
    which CLI subcommand is running, since a different entry point imports a different set --
    `gate-export` and `report` would then disagree on identical code and the cache would invalidate
    on invocation shape rather than on code change.

    Sorted (D4). Every path shares the `repo_root` prefix, so sorting the absolute paths is exactly
    sorted repo-relative order. Determinism is load-bearing, not cosmetic: an unstable digest
    rebuilds the cache on every run, which looks exactly like a working cache while doing no work.

    Reads `_REPO_ROOT` / `_REPLAY_ROOTS` at call time so tests can point both at a synthetic tree.
    Raises nothing itself; a root that does not exist simply contributes no edges, and the missing
    bytes surface as the OSError `_evaluate_journal` already catches to degrade to a full replay
    without a cache (D8 / spec 00060 D5)."""
    repo_root = _REPO_ROOT
    seen: set[Path] = set()
    # Seed with the roots AND their own ancestor packages. Without this the D10 ancestor rule
    # applies to edges only, so a root two packages deep with no cli.* imports would yield a
    # closure of just itself. Latent today -- every real ancestor arrives via 6-47 separate edges,
    # and the superset test would catch a regression -- but an asymmetry inside the D10 fix itself
    # is exactly the kind of "correct for the case we thought of" this iteration is about.
    pending = list(_REPLAY_ROOTS)
    for root in _REPLAY_ROOTS:
        pending.extend(_ancestor_packages(root, repo_root))
    while pending:
        module_path = pending.pop()
        if module_path in seen:
            continue
        seen.add(module_path)
        pending.extend(edge for edge in _import_edges(module_path, repo_root) if edge not in seen)
    return tuple(sorted(seen))


def replay_fingerprint(config: CrossfreqSystemConfig = CrossfreqSystemConfig(), *, path: str = "fast") -> str:
    """sha256 over the source bytes of the modules that determine a replay's result, the effective
    config, the replay path ("fast"/"verified" select different builders -- a route switch must
    not serve the other route's cached verdicts), and the execution environment (T0074: numpy
    version + Python major.minor -- a `uv.lock` bump can change numeric behaviour with the journal
    and every covered module's bytes unchanged, which would otherwise serve a stale cached PASS).
    Deliberately over-sensitive: a comment-only edit to any covered module, a numpy version
    change, or a Python MINOR bump all invalidate the cache. A Python PATCH release deliberately
    does not -- patch releases do not change float arithmetic, so the full rebuild would buy
    nothing; `sys.version_info[:2]` is the digested value.

    Since spec 00065 the covered set is `_replay_code_paths()` -- the transitive `cli.*` import
    closure of `_REPLAY_ROOTS`, not a hand-maintained list -- so an edit to any module that
    executes on a replay invalidates the cache, including parts of those modules unrelated to
    replay. "Executes", not merely "is imported by": the first cut of this walk covered only leaf
    modules, leaving the four ancestor `__init__.py` files running unhashed on every replay, and
    that gap was exploitable at a byte-identical fingerprint. The superset test named above is what
    makes this sentence checkable rather than aspirational. That cost is accepted, and is the same trade as before, only wider:
    over-invalidation costs one rebuild, under-invalidation silently corrupts gate evidence
    (T0074). Whole files are digested rather than the verdict-path code extracted, because moving
    code onto and off the verdict path is riskier than the cache efficiency that would buy."""
    digest = hashlib.sha256()
    for module_path in _replay_code_paths():
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
