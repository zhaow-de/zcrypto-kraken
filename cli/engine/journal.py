"""The journal contract (spec 00040 SS the concordance core): a documented, versioned per-cycle
record — the input-snapshot manifest (per pair x grid: bar count, first/last ts, content hash,
file path), the computed newest-row final_targets, and cycle timing/provenance. schema_version is
covered by SCHEMA_VERSION below; a record failing validate_record's schema or snapshot-boundary
(no-peek) checks is a journal-validation error, classified as a failed cycle by the gate (never
silently replayed) -- see cli.engine.concordance.evaluate_gate.

snapshot_content_hash is THE one hashing helper both the iter-083 writer and this iteration's
reader (cli.engine.concordance.replay_cycle) call -- never reimplemented from prose.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cli.engine.errors import EngineJournalError

SCHEMA_VERSION = 2
# The registry's own pattern (cli/registry/record.py): both schema_version 1 (base-keyed
# final_targets/snapshot pairs, e.g. "BTC") and 2 (full-symbol keys, e.g. "BTC/EUR", spec 00094)
# load. A v1 record's keys are never rewritten on load -- each schema replays and compares in its
# own native key space (cli.engine.concordance); normalizing v1 to symbol keys here would turn
# every v1 record into a structural mismatch at the gate.
_LOADABLE_SCHEMA_VERSIONS = frozenset({1, 2})
_VALID_GRIDS = frozenset({"1440", "240"})
_VALID_BUILDER_PATHS = frozenset({"fast", "verified"})


@dataclass(frozen=True)
class SnapshotEntry:
    """One journaled input snapshot: pair x grid ("1440" daily | "240" 4h)."""

    pair: str
    grid: str
    n_bars: int
    first_ts: datetime
    last_ts: datetime
    content_hash: str
    path: str


@dataclass(frozen=True)
class CycleRecord:
    """One engine cycle's journal entry. snapshots carries one SnapshotEntry per pair x grid;
    final_targets is the newest-row per-asset targets the cycle computed and traded.

    closes is the forming row's 4h close the cycle priced each MODEL base at -- the input a drift
    measurement needs, journaled so a boundary never has to replay a cycle to learn what it priced.
    The INPUT is journaled, not a derived drift number: a derivative would rot against the code that
    computed it. It is BASE-keyed ("BTC") in BOTH schemas -- final_targets widened to full symbols
    at schema 2, the model did not -- and `None` on every record written before the key existed."""

    schema_version: int
    cycle_ts: datetime
    snapshots: tuple[SnapshotEntry, ...]
    final_targets: dict[str, float]
    started_at: datetime
    completed_at: datetime
    code_version: str
    builder_path: str
    closes: dict[str, float] | None = None
    nav: float | None = None
    held: dict[str, float] | None = None


def _epoch_seconds(ts: datetime) -> int:
    """Whole-second UTC epoch time for a bar-start stamp. A naive datetime is treated as already-UTC
    (this repo's bar-timestamp convention); an aware one is converted to UTC first."""
    aware = ts if ts.tzinfo is not None else ts.replace(tzinfo=timezone.utc)
    return int(aware.astimezone(timezone.utc).timestamp())


def snapshot_content_hash(ts: list[datetime], closes: list[float | None]) -> str:
    """The ONE hashing helper both the iter-083 writer and this reader call for a pair x grid
    snapshot -- never reimplemented from prose.

    Byte layout (exact, pinned by schema_version -- changing it is a schema break): sha256 over two
    blocks concatenated in this order, with no separators, length prefixes, or interleaving:

      1. every ts[i], as int64 epoch-seconds (UTC; see `_epoch_seconds`), little-endian, in row
         order -- 8 * len(ts) bytes;
      2. every closes[i], as IEEE-754 float64, little-endian, in row order, with a None close
         encoded as NaN -- 8 * len(closes) bytes.
    """
    if len(ts) != len(closes):
        raise EngineJournalError(f"snapshot_content_hash: ts (len {len(ts)}) and closes (len {len(closes)}) length mismatch")
    ts_block = b"".join(struct.pack("<q", _epoch_seconds(t)) for t in ts)
    close_block = b"".join(struct.pack("<d", math.nan if c is None else c) for c in closes)
    return hashlib.sha256(ts_block + close_block).hexdigest()


def _is_symbol_key(key: str) -> bool:
    """True for a full-symbol key ("BTC/EUR"), false for a bare base key ("BTC") -- the '/'
    separator cli.engine.store.PAIR_KEYS and every full-symbol consumer already use."""
    return "/" in key


def validate_record(record: CycleRecord) -> None:
    """Raise EngineJournalError on any schema violation or on the snapshot-boundary (no-peek)
    invariant: per pair, the last "240" (4h) stamp must equal cycle_ts - 4h (the bar closing
    exactly at cycle_ts), and the last "1440" (daily) stamp must equal (the last midnight <=
    cycle_ts) - 1 day -- the node must drop Kraken REST's trailing in-progress candle.

    Schema-aware over final_targets AND the snapshot pair fields: a schema_version 1 record must
    key both by base ("BTC"); a schema_version 2 record must key both by full symbol ("BTC/EUR").
    Wrong keying is refused, never silently normalized -- a v2 record was written by code that
    could only have produced symbol keys, and vice versa for v1."""
    if record.schema_version not in _LOADABLE_SCHEMA_VERSIONS:
        raise EngineJournalError(
            f"unsupported schema_version {record.schema_version!r} (loadable: {sorted(_LOADABLE_SCHEMA_VERSIONS)})"
        )
    if not isinstance(record.cycle_ts, datetime):
        raise EngineJournalError(f"cycle_ts must be a datetime, got {record.cycle_ts!r}")
    if not isinstance(record.snapshots, tuple) or not record.snapshots:
        raise EngineJournalError("snapshots must be a non-empty tuple of SnapshotEntry")

    by_pair: dict[str, dict[str, SnapshotEntry]] = {}
    for entry in record.snapshots:
        if not isinstance(entry, SnapshotEntry):
            raise EngineJournalError(f"snapshots must contain SnapshotEntry instances, got {entry!r}")
        if not isinstance(entry.pair, str) or not entry.pair:
            raise EngineJournalError(f"snapshot pair must be a non-empty str, got {entry.pair!r}")
        if record.schema_version == 1 and _is_symbol_key(entry.pair):
            raise EngineJournalError(f"schema_version 1 snapshot pair must be a base key (no '/'), got {entry.pair!r}")
        if record.schema_version == 2 and not _is_symbol_key(entry.pair):
            raise EngineJournalError(f"schema_version 2 snapshot pair must be a full symbol key (BASE/QUOTE), got {entry.pair!r}")
        if entry.grid not in _VALID_GRIDS:
            raise EngineJournalError(f"snapshot grid must be one of {sorted(_VALID_GRIDS)}, got {entry.grid!r}")
        if not isinstance(entry.n_bars, int) or isinstance(entry.n_bars, bool) or entry.n_bars < 1:
            raise EngineJournalError(f"snapshot n_bars must be an int >= 1, got {entry.n_bars!r}")
        if not isinstance(entry.first_ts, datetime) or not isinstance(entry.last_ts, datetime):
            raise EngineJournalError(f"snapshot first_ts/last_ts must be datetimes, got {entry.first_ts!r}/{entry.last_ts!r}")
        if entry.first_ts >= entry.last_ts:
            raise EngineJournalError(f"snapshot first_ts must precede last_ts, got {entry.first_ts!r} >= {entry.last_ts!r}")
        if not isinstance(entry.content_hash, str) or len(entry.content_hash) != 64:
            raise EngineJournalError(f"snapshot content_hash must be a 64-char hex str, got {entry.content_hash!r}")
        if not isinstance(entry.path, str) or not entry.path:
            raise EngineJournalError(f"snapshot path must be a non-empty str, got {entry.path!r}")
        pair_grids = by_pair.setdefault(entry.pair, {})
        if entry.grid in pair_grids:
            raise EngineJournalError(f"duplicate snapshot for pair={entry.pair!r} grid={entry.grid!r}")
        pair_grids[entry.grid] = entry

    for pair, grids in by_pair.items():
        missing = sorted(_VALID_GRIDS - set(grids))
        if missing:
            raise EngineJournalError(f"pair={pair!r} is missing snapshot grid(s) {missing}")

    if not isinstance(record.final_targets, dict) or not record.final_targets:
        raise EngineJournalError("final_targets must be a non-empty dict[str, float]")
    for asset, value in record.final_targets.items():
        if not isinstance(asset, str) or not asset:
            raise EngineJournalError(f"final_targets key must be a non-empty str, got {asset!r}")
        if record.schema_version == 1 and _is_symbol_key(asset):
            raise EngineJournalError(f"schema_version 1 final_targets key must be a base key (no '/'), got {asset!r}")
        if record.schema_version == 2 and not _is_symbol_key(asset):
            raise EngineJournalError(f"schema_version 2 final_targets key must be a full symbol key (BASE/QUOTE), got {asset!r}")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise EngineJournalError(f"final_targets[{asset!r}] must be a finite number, got {value!r}")

    # closes is optional: absent (None) on every record written before the key existed, and those
    # must keep validating. Present-but-empty is a writer bug, not absence -- absence is None. The
    # base-key check is NOT schema-conditional: closes lives in the model's key space, which never
    # widened. Zero and negative are refused because a close is a price and divides downstream.
    # nav and held are the other two terms a drift measurement needs (T0150). Both are optional for
    # the same reason closes is: absent on every record written before the keys existed.
    if record.nav is not None:
        if isinstance(record.nav, bool) or not isinstance(record.nav, (int, float)):
            raise EngineJournalError(f"nav must be a number when present, got {record.nav!r}")
        if not math.isfinite(record.nav) or record.nav <= 0:
            # NAV sets BOTH halves of drift -- a target is `weight * nav / close` and the drift
            # divides by nav -- so a zero divides by zero and a negative signs every reading.
            raise EngineJournalError(f"nav must be finite and positive when present, got {record.nav!r}")
    if record.held is not None:
        if not isinstance(record.held, dict):
            raise EngineJournalError("held must be a dict[str, float] when present")
        for asset, value in record.held.items():
            if not isinstance(asset, str) or not asset:
                raise EngineJournalError(f"held key must be a non-empty str, got {asset!r}")
            if "/" in asset:
                raise EngineJournalError(f"held key must be a base key (no '/'), got {asset!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                # Zero and negative are both real books (flat, and short); only non-numbers are not.
                raise EngineJournalError(f"held[{asset!r}] must be a finite number, got {value!r}")
    if record.closes is not None:
        if not isinstance(record.closes, dict) or not record.closes:
            raise EngineJournalError("closes must be a non-empty dict[str, float] when present")
        for asset, value in record.closes.items():
            if not isinstance(asset, str) or not asset:
                raise EngineJournalError(f"closes key must be a non-empty str, got {asset!r}")
            if _is_symbol_key(asset):
                raise EngineJournalError(f"closes key must be a base key (no '/'), got {asset!r}")
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise EngineJournalError(f"closes[{asset!r}] must be a finite positive number, got {value!r}")

    if not isinstance(record.started_at, datetime) or not isinstance(record.completed_at, datetime):
        raise EngineJournalError("started_at/completed_at must be datetimes")
    if record.started_at > record.completed_at:
        raise EngineJournalError(f"started_at {record.started_at!r} must be <= completed_at {record.completed_at!r}")
    if not isinstance(record.code_version, str) or not record.code_version:
        raise EngineJournalError(f"code_version must be a non-empty str, got {record.code_version!r}")
    if record.builder_path not in _VALID_BUILDER_PATHS:
        raise EngineJournalError(f"builder_path must be one of {sorted(_VALID_BUILDER_PATHS)}, got {record.builder_path!r}")

    # Snapshot-boundary (no-peek) invariant.
    expected_h4_last = record.cycle_ts - timedelta(hours=4)
    midnight = record.cycle_ts.replace(hour=0, minute=0, second=0, microsecond=0)
    expected_daily_last = midnight - timedelta(days=1)
    for pair, grids in by_pair.items():
        h4_last = grids["240"].last_ts
        if h4_last != expected_h4_last:
            raise EngineJournalError(f"pair={pair!r}: 4h snapshot last_ts {h4_last!r} != cycle_ts - 4h ({expected_h4_last!r})")
        daily_last = grids["1440"].last_ts
        if daily_last != expected_daily_last:
            raise EngineJournalError(
                f"pair={pair!r}: daily snapshot last_ts {daily_last!r} != (last midnight <= cycle_ts) - 1d "
                f"({expected_daily_last!r})"
            )


def to_json(record: CycleRecord) -> str:
    """Serialize a CycleRecord to JSON; every datetime as an ISO-8601 UTC string."""
    payload = {
        "schema_version": record.schema_version,
        "cycle_ts": record.cycle_ts.isoformat(),
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
            for s in record.snapshots
        ],
        "final_targets": dict(record.final_targets),
        "started_at": record.started_at.isoformat(),
        "completed_at": record.completed_at.isoformat(),
        "code_version": record.code_version,
        "builder_path": record.builder_path,
    }
    # OMITTED when absent, never emitted as null: a record predating the key must re-serialize
    # byte-identically (the v1 golden pin), and an absent-vs-null distinction would be a second
    # dialect every reader has to carry.
    if record.closes is not None:
        payload["closes"] = dict(record.closes)
    if record.nav is not None:
        payload["nav"] = record.nav
    if record.held is not None:
        payload["held"] = dict(record.held)
    return json.dumps(payload, sort_keys=True)


def from_json(s: str) -> CycleRecord:
    """Deserialize a CycleRecord from to_json's output (round-trips exactly). Raises
    EngineJournalError on malformed JSON or a missing/mistyped required key; does NOT itself call
    validate_record -- schema and the boundary invariant are the caller's separate concern."""
    try:
        payload = json.loads(s)
    except json.JSONDecodeError as exc:
        raise EngineJournalError(f"invalid journal JSON: {exc}") from exc
    try:
        return CycleRecord(
            schema_version=payload["schema_version"],
            cycle_ts=datetime.fromisoformat(payload["cycle_ts"]),
            snapshots=tuple(
                SnapshotEntry(
                    pair=e["pair"],
                    grid=e["grid"],
                    n_bars=e["n_bars"],
                    first_ts=datetime.fromisoformat(e["first_ts"]),
                    last_ts=datetime.fromisoformat(e["last_ts"]),
                    content_hash=e["content_hash"],
                    path=e["path"],
                )
                for e in payload["snapshots"]
            ),
            final_targets=dict(payload["final_targets"]),
            started_at=datetime.fromisoformat(payload["started_at"]),
            completed_at=datetime.fromisoformat(payload["completed_at"]),
            code_version=payload["code_version"],
            builder_path=payload["builder_path"],
            # .get, not [...]: every record already on disk predates this key, and a reader that
            # raised on their absence would take the journal's consumers down over its own upgrade.
            # Coerced through dict() exactly as final_targets is, so a truncated artifact whose
            # closes is a list or a scalar raises here rather than loading clean -- several callers
            # read a record without ever calling validate_record.
            closes=dict(raw) if (raw := payload.get("closes")) is not None else None,
            nav=payload.get("nav"),
            held=dict(rawh) if (rawh := payload.get("held")) is not None else None,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise EngineJournalError(f"journal JSON is missing or misshapes a required key: {exc}") from exc
