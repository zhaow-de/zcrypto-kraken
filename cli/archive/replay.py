"""Canonical book continuity-replay (spec 00051 OPS-3).

Proves that the canonical archive — reconciled-first, primary otherwise (`canonical_segments`) —
**replays as a coherent book**, per hour: it is chain-anchored, rows are non-decreasing in `ts`,
every message carries its capture-time `checksum` attestation, and the rows regroup into WS-shaped
messages that feed `OrderBook` without a structural throw. Its one genuinely new payoff over
manifests + continuity.py: it confirms the reconciler's spliced output stays anchored and coherent
across splice boundaries.

Anchoring (corrected 2026-07-15, spec 00052 D3 — the same real-data finding: Kraken snapshots arrive
on *subscribe*, not once per capture hour, so ~96% of real hours open with plain updates): an hour is
**chain-anchored** iff it opens with a snapshot, OR its exact predecessor hour (same pair) was
present in the enumeration AND was itself chain-anchored and error-free. `replay_segment` alone has
no chain context, so it reports only the RAW per-hour fact (`ReplayResult.anchored` = "opens with a
snapshot"); `verify_replay` walks its sorted `(pair, hour)` results afterwards and derives the
chain-corrected `anchored` verdict, since only it has the cross-hour context to do so.

Scope guard (finalized 2026-07-15, T0045): the archive stores `price`/`qty` as Float64, so Kraken's
CRC32 is NOT byte-exact re-derivable — a re-derived `OrderBook.checksum()` mismatches the stored
`checksum` column on every zero-trailing level, a guaranteed false alarm. The stored column is
therefore trusted as capture-time ground truth and never re-derived; the CRC-based return value of
`ingest_snapshot`/`ingest_update` is deliberately ignored. A "structural desync" heuristic is
likewise NOT implemented: for a depth-bounded book, a legitimate update to an out-of-window level is
indistinguishable from corruption without the CRC. Byte-exact CRC re-attestation was considered and consciously
DROPPED (T0045, 2026-08-23): it would cost a schema change on the unbackfillable live capture stream
and could only ever attest data captured after it. That is an accepted limit of the archive, not
work awaiting a turn -- a discrepancy the structural check cannot localise opens a NEW topic rather
than reviving that one.
"""

from __future__ import annotations

import dataclasses
import hashlib
import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl

from cli.archive.checkpoint import CheckpointRow, load_checkpoint, save_checkpoint
from cli.archive.reader import canonical_segments
from cli.capture.book import OrderBook
from cli.logging import get_logger

logger = get_logger("archive.replay")


@dataclass(frozen=True)
class ReplayResult:
    """One canonical hour's replay verdict. `error` is set (never raised) for an unreadable segment
    or a structural ingest throw — one bad hour must not abort the sweep.

    `anchored`: from `replay_segment` alone this is the RAW fact ("opens with a snapshot"); from
    `verify_replay` it is the chain-corrected verdict (module docstring)."""

    pair: str
    hour: datetime | None
    rows: int
    messages: int
    anchored: bool
    ts_ordered: bool
    checksum_present: bool
    replay_ok: bool
    error: str | None

    @property
    def passed(self) -> bool:
        return self.error is None and self.anchored and self.ts_ordered and self.checksum_present and self.replay_ok


def regroup_messages(frame: pl.DataFrame) -> list[dict]:
    """Rebuild the WS-shaped messages from the exploded per-level rows — the exact inverse of the
    capture writer's fan-out (cli/capture/command.py:146-158): consecutive rows sharing
    `(ts, symbol, type, checksum)` are one wire message, its levels rebuilt onto `bids`/`asks` by
    `side` in row order."""
    messages: list[dict] = []
    key: tuple | None = None
    for row in frame.iter_rows(named=True):
        row_key = (row["ts"], row["symbol"], row["type"], row["checksum"])
        if row_key != key:
            key = row_key
            messages.append(
                {
                    "ts": row["ts"],
                    "symbol": row["symbol"],
                    "type": row["type"],
                    "checksum": row["checksum"],
                    "bids": [],
                    "asks": [],
                }
            )
        side = "bids" if row["side"] == "bid" else "asks"
        messages[-1][side].append({"price": row["price"], "qty": row["qty"]})
    return messages


def _hour_from_path(path: Path) -> datetime | None:
    """The hour a canonical final's `<...>/<YYYY>/<MM>/<DD>/<HH>.parquet` path encodes."""
    parts = path.parts
    try:
        return datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(path.name[:2]), tzinfo=UTC)
    except ValueError, IndexError:
        return None


def replay_segment(path: Path, symbol: str, depth: int) -> ReplayResult:
    """Replay one canonical hour through a fresh `OrderBook(symbol, depth)`. Never raises: an
    unreadable segment or a structural ingest throw is isolated into the result (the same
    isolation contract as infra/scripts/gap_distribution.py::observe_gaps).

    Has no chain context (no visibility into neighboring hours), so `ReplayResult.anchored` here is
    the RAW fact -- "this hour's first message is a snapshot" -- not the chain-corrected verdict;
    `verify_replay` derives that once it has the full per-pair sequence (module docstring)."""
    hour = _hour_from_path(path)
    try:
        frame = pl.read_parquet(path)
        messages = regroup_messages(frame)
    except Exception as exc:  # noqa: BLE001 — an unreadable segment is a finding, not a crash
        return ReplayResult(symbol, hour, 0, 0, False, False, False, False, f"{type(exc).__name__}: {exc}")

    opens_with_snapshot = bool(messages) and messages[0]["type"] == "snapshot"
    ts_ordered = bool(frame["ts"].is_sorted())  # non-strict: equal stamps are in order
    checksum_present = "checksum" in frame.columns and frame["checksum"].null_count() == 0

    book = OrderBook(symbol, depth)
    replay_ok, error = True, None
    try:
        for message in messages:
            # The CRC-based return value is deliberately ignored (T0045, module docstring): only a
            # structural throw fails the replay.
            if message["type"] == "snapshot":
                book.ingest_snapshot(message)
            else:
                book.ingest_update(message)
    except Exception as exc:  # noqa: BLE001 — a structural throw is exactly the finding this check exists for
        replay_ok, error = False, f"{type(exc).__name__}: {exc}"

    return ReplayResult(
        symbol, hour, frame.height, len(messages), opens_with_snapshot, ts_ordered, checksum_present, replay_ok, error
    )


def _chain_anchor(results: list[ReplayResult]) -> list[ReplayResult]:
    """Derive the chain-anchored verdict (spec 00052 D3 correction) over `results` in `(pair, hour)`
    order: an hour is anchored iff `replay_segment`'s raw fact says so, OR its exact predecessor hour
    for the same pair was present in `results` (i.e. in this enumeration) AND was itself anchored and
    error-free. `results` is walked in order, tracking each pair's previous hour + verdict -- exactly
    `canonical_segments`' sort contract, so no re-sort is needed (or safe: L2 hours are not
    reorderable)."""
    chained: list[ReplayResult] = []
    prev_hour: dict[str, datetime | None] = {}
    prev_ok: dict[str, bool] = {}
    for result in results:
        predecessor = prev_hour.get(result.pair)
        contiguous = result.hour is not None and predecessor is not None and result.hour == predecessor + timedelta(hours=1)
        chain_anchored = result.anchored or (contiguous and prev_ok.get(result.pair, False))
        chained.append(result if chain_anchored == result.anchored else dataclasses.replace(result, anchored=chain_anchored))
        prev_hour[result.pair] = result.hour
        prev_ok[result.pair] = chain_anchored and result.error is None
    return chained


def verify_replay(
    primary_root: Path,
    reconciled_root: Path | None,
    *,
    pair: str | None = None,
    since: datetime | None = None,
    depth: int,
) -> list[ReplayResult]:
    """Continuity-replay every canonical book hour (reconciled-first, primary otherwise), one
    `ReplayResult` per hour in `(pair, hour)` order. Per-hour failures are isolated into
    `ReplayResult.error`; the sweep never aborts on one bad hour. `anchored` is chain-derived
    (`_chain_anchor`, spec 00052 D3 correction) over this same enumeration -- a hole opened by
    `--pair`/`--since` counts as "predecessor not present", same as a real archive gap."""
    results: list[ReplayResult] = []
    for seg_pair, hour, path in canonical_segments(primary_root, reconciled_root, kind="book"):
        if pair is not None and seg_pair != pair:
            continue
        if since is not None and hour < since:
            continue
        try:
            result = replay_segment(path, seg_pair, depth)
        except Exception as exc:  # noqa: BLE001 — belt and braces: one bad hour must not abort the sweep
            result = ReplayResult(seg_pair, hour, 0, 0, False, False, False, False, f"{type(exc).__name__}: {exc}")
        results.append(result)
    return _chain_anchor(results)


# --- incremental replay (spec 00078) ----------------------------------------------------------------
#
# Replays only what changed while still certifying the WHOLE archive: each hour's RAW facts are
# checkpointed against the sha256 of the bytes replayed, and `_chain_anchor` is refolded over cached
# and fresh results alike on every run. The chain verdict is NEVER persisted (spec 00078 D1): it is a
# fold that can only widen, so caching its output would make anchoring irrevocable — an hour chained
# through a good predecessor would stay green forever after that predecessor is rewritten into a
# failure, with `failed_hours` reading 0.

VERIFIER_VERSION = 1

# Flush cadence (spec 00078 D8): ~20 min of work at risk, so a rebuild or long drain killed mid-run
# (the 02:25 reboot, an OOM) resumes instead of restarting.
_FLUSH_EVERY = 250

# Eviction refusal line (D7): the case this catches is the NFS primary resolving empty while the
# overlay is present — a nonempty enumeration that would otherwise evict the whole primary.
_EVICTION_LIMIT = 0.10

_monotonic = time.monotonic  # indirected so tests can drive the drain budget off a controlled clock


@dataclass(frozen=True)
class Census:
    """What one incremental run did, for the operator-facing census line."""

    replayed: int
    reused: int
    audited: int
    audit_mismatches: tuple[str, ...]  # "PAIR YYYY-MM-DD HH:00" labels
    pending: int
    evicted: int
    duration_s: float


class EvictionRefusedError(Exception):
    """The enumeration lost more than `_EVICTION_LIMIT` of the checkpoint's hours (spec 00078 D7)."""


def _sidecar_digest(path: Path) -> str | None:
    """The first whitespace-delimited token of `<path>.sha256`, or `None` when the sidecar is absent,
    empty, or unreadable.

    Absent/empty is `verify_manifest`'s own reading (a killed pre-T0036 writer left 0-byte sidecars);
    unreadable joins them because this probe sits OUTSIDE `replay_segment`'s never-raises contract and
    a transient EIO from the `ro,soft` NFS mount must stay one failing hour, not a whole-run crash.
    `None` never equals a cached hash, so such an hour is always replayed and always reported failing.
    """
    sidecar = path.with_name(path.name + ".sha256")
    try:
        recorded = sidecar.read_text().split()
    except OSError:
        return None
    return recorded[0] if recorded else None


def _cached_failure(row: CheckpointRow) -> bool:
    """Whether `row`'s cached verdict is a FAILURE, which is never trusted from cache (spec 00078 D3):
    `replay_segment` isolates any exception — including a transient NFS EIO — into `error`, and
    cache-trusting that would turn a one-off hiccup into a permanently-failing hour that never heals.

    `opens_with_snapshot` is deliberately excluded: it is a raw fact, not a failure (~96% of real
    hours open with a plain update and are anchored through their predecessor), and including it here
    would re-replay nearly the whole archive nightly.
    """
    return row.error is not None or not (row.ts_ordered and row.checksum_present and row.replay_ok)


def _is_stale(row: CheckpointRow, path: Path, *, reverify_all: bool) -> bool:
    """Whether a checkpointed hour must be replayed again (spec 00078 D3). The sidecar read is the
    cheap staleness probe; the byte hash itself is recomputed only on the hours actually replayed.

    `polars_version`/`depth` are recorded on the row but deliberately NOT consulted (D5): dependabot
    bumps polars ~monthly and a full drain takes ~74 nights at year-one size, so invalidating on them
    would leave the instrument permanently mid-drain with `pending` never reaching zero.
    """
    if reverify_all or row.verifier_version != VERIFIER_VERSION or _cached_failure(row):
        return True
    return _sidecar_digest(path) != row.byte_hash


def _replay_and_checkpoint(pair: str, hour: datetime, path: Path, depth: int) -> tuple[ReplayResult, CheckpointRow]:
    """Replay one hour and build its checkpoint row.

    Identity is the sha256 of the bytes actually replayed, hashed BEFORE the replay and compared
    against the sidecar afterwards (spec 00078 D2) — not the sidecar's claim, since both writers
    publish sidecar-then-final and a crash mid-mint leaves a new sidecar over old bytes. A mismatch,
    or a missing sidecar, rewrites the verdict into a failure: it violates the archive's manifested
    invariant, and failures are never cache-trusted, so it re-checks nightly until resolved.

    The row's `opens_with_snapshot` is `replay_segment`'s RAW fact, captured here before any chain
    derivation — the checkpoint must never see `_chain_anchor`'s output (D1).
    """
    try:
        byte_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        # Outside `replay_segment`'s never-raises contract: isolate it into this hour, as a failure
        # with no usable identity, and let the run continue.
        result = ReplayResult(pair, hour, 0, 0, False, False, False, False, f"{type(exc).__name__}: {exc}")
        byte_hash = ""
    else:
        result = replay_segment(path, pair, depth)
        recorded = _sidecar_digest(path)
        if recorded is None:
            manifest_error = "no manifest sidecar"
        elif recorded != byte_hash:
            manifest_error = f"manifest mismatch: sidecar {recorded} != replayed bytes {byte_hash}"
        else:
            manifest_error = None
        if manifest_error is not None:
            error = manifest_error if result.error is None else f"{manifest_error} ({result.error})"
            result = dataclasses.replace(result, error=error)

    row = CheckpointRow(
        pair=pair,
        hour=hour,
        byte_hash=byte_hash,
        verifier_version=VERIFIER_VERSION,
        opens_with_snapshot=result.anchored,  # RAW — `_chain_anchor` has not run yet, and never will here
        ts_ordered=result.ts_ordered,
        checksum_present=result.checksum_present,
        replay_ok=result.replay_ok,
        error=result.error,
        rows=result.rows,
        messages=result.messages,
        polars_version=pl.__version__,
        depth=depth,
        verified_at=datetime.now(UTC),
    )
    return result, row


def _audit_facts(row: CheckpointRow) -> tuple:
    """The full RAW tuple the audit compares — every fact the cache serves on a reused hour. A
    difference in ANY of them is a mismatch. `verified_at`/`polars_version`/`depth` are forensics and
    `verifier_version` is the run's own, so none of them belong here."""
    return (
        row.byte_hash,
        row.opens_with_snapshot,
        row.ts_ordered,
        row.checksum_present,
        row.replay_ok,
        row.error,
        row.rows,
        row.messages,
    )


def _hour_label(pair: str, hour: datetime) -> str:
    """`PAIR YYYY-MM-DD HH:00` — how a mismatched hour is named to the operator."""
    return f"{pair} {hour:%Y-%m-%d %H:00}"


def verify_replay_incremental(
    primary_root: Path,
    reconciled_root: Path | None,
    *,
    state_dir: Path,
    depth: int,
    drain_budget_s: float = 7200.0,
    audit_k: int = 25,
    reverify_all: bool = False,
    rng: random.Random | None = None,
) -> tuple[list[ReplayResult], Census]:
    """Continuity-replay the canonical archive incrementally, returning the same `(pair, hour)`-ordered
    verdict list `verify_replay` produces plus a `Census` of what was actually done.

    Hours never seen before are replayed unconditionally — otherwise the sweep falls behind ingest and
    `hours_total` stops matching the archive. Older stale hours (version bumps, rewrites, cached
    failures, `reverify_all`) drain oldest-first until `drain_budget_s` is spent; the remainder is
    `pending` and announced. Everything else is served from the checkpoint, and `_chain_anchor` is
    refolded over the whole sequence.

    Raises `EvictionRefusedError` when the enumeration lost more than 10% of the checkpoint's hours,
    and `CheckpointWriteError` when the state dir cannot be written — both before/instead of a
    summary, so the run reads broken rather than green.

    After the drain, `audit_k` cache-trusted REUSED hours are re-replayed and compared against their
    checkpoint rows (spec 00078 D6) — the only guard that can detect the cache being wrong, since
    `replayed=288 reused=5712` is otherwise both the healthy signature and the wrong-reuse one. A
    mismatch is named in `Census.audit_mismatches` and self-heals (the fresh row replaces the cached
    one, here and in the checkpoint); deciding whether that fails the run loudly is the CLI's.
    """
    started = _monotonic()
    segments = list(canonical_segments(primary_root, reconciled_root, kind="book"))
    if not segments:
        # An empty enumeration never touches the checkpoint (spec 00078 D7): an unmounted NAS reads as
        # zero hours, and evicting the archive on that reading would force an unplanned rebuild.
        return [], Census(0, 0, 0, (), 0, 0, _monotonic() - started)

    checkpoint = load_checkpoint(state_dir) or {}  # absent/corrupt/wrong-schema → every hour is new
    present = {(pair, hour) for pair, hour, _ in segments}
    evicted = [key for key in checkpoint if key not in present]
    if checkpoint and len(evicted) > _EVICTION_LIMIT * len(checkpoint):
        # Before any replay: a refused run must waste no work.
        raise EvictionRefusedError(
            f"refusing to evict {len(evicted)} of {len(checkpoint)} checkpointed hours "
            f"(over {_EVICTION_LIMIT:.0%}) — the enumeration lost hours it should not have"
        )

    rows = {key: row for key, row in checkpoint.items() if key in present}
    mandatory: list[tuple[str, datetime, Path]] = []
    drain: list[tuple[str, datetime, Path]] = []
    for pair, hour, path in segments:
        row = checkpoint.get((pair, hour))
        if row is None:
            mandatory.append((pair, hour, path))
        elif _is_stale(row, path, reverify_all=reverify_all):
            drain.append((pair, hour, path))
    drain.sort(key=lambda segment: (segment[1], segment[0]))  # oldest first, `(hour, pair)`

    fresh: dict[tuple[str, datetime], ReplayResult] = {}

    def replay_one(pair: str, hour: datetime, path: Path) -> None:
        result, row = _replay_and_checkpoint(pair, hour, path, depth)
        fresh[(pair, hour)] = result
        rows[(pair, hour)] = row
        if len(fresh) % _FLUSH_EVERY == 0:
            save_checkpoint(state_dir, rows.values())

    for pair, hour, path in mandatory:  # already in `(pair, hour)` order
        replay_one(pair, hour, path)

    pending: set[tuple[str, datetime]] = set()
    drain_started = _monotonic()
    for index, (pair, hour, path) in enumerate(drain):
        if _monotonic() - drain_started >= drain_budget_s:
            pending = {(drained_pair, drained_hour) for drained_pair, drained_hour, _ in drain[index:]}
            break
        replay_one(pair, hour, path)

    results: list[ReplayResult] = []
    # The reused keys — rows the stale predicate passed THIS run — materialized here because they are
    # the audit's population: a lie can only live in a row trusted as current (D6).
    reused_keys: list[tuple[str, datetime]] = []
    reused_paths: dict[tuple[str, datetime], Path] = {}
    reused_index: dict[tuple[str, datetime], int] = {}
    for pair, hour, path in segments:
        key = (pair, hour)
        if key in fresh:
            results.append(fresh[key])
            continue
        row = rows[key]
        results.append(
            ReplayResult(
                pair,
                hour,
                row.rows,
                row.messages,
                row.opens_with_snapshot,  # the RAW fact; the chain verdict is refolded below
                row.ts_ordered,
                row.checksum_present,
                row.replay_ok,
                row.error,
            )
        )
        if key not in pending:
            reused_keys.append(key)
            reused_paths[key] = path
            reused_index[key] = len(results) - 1

    # The sampled audit (D6). Pending rows are NEVER sampled: one is known-stale by construction (its
    # hash or version already failed the predicate), so auditing it mismatches with certainty and would
    # fail the run every night of a legitimate large drain — ~74 consecutive nights at year-one size.
    mismatches: list[str] = []
    audited = min(audit_k, len(reused_keys)) if audit_k > 0 else 0
    if audited:
        sampler = rng if rng is not None else random.Random()
        for pair, hour in sampler.sample(reused_keys, audited):
            key = (pair, hour)
            result, row = _replay_and_checkpoint(pair, hour, reused_paths[key], depth)
            if _audit_facts(row) != _audit_facts(rows[key]):
                mismatches.append(_hour_label(pair, hour))
            # The fresh row replaces the cached one either way — on a mismatch that self-heals the
            # cache, and on a match it records that this hour was re-verified under today's code.
            rows[key] = row
            results[reused_index[key]] = result

    save_checkpoint(state_dir, rows.values())
    census = Census(len(fresh), len(reused_keys), audited, tuple(mismatches), len(pending), len(evicted), _monotonic() - started)
    return _chain_anchor(results), census
