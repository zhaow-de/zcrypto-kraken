"""The versions table: per generation, one part per tick on the record's chain and one head per part, each staged,
published by one rename and set 0555, and read back through a head with every hash it commits to checked."""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import stat
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl

from cli.capture.command import LOCKFILE_NAME
from cli.logging import get_logger
from cli.vintage import derive as derive_mod
from cli.vintage.chain import STAMP_RE, TickFile, chain, check_head, scan
from cli.vintage.derive import DERIVE_GENERATION, KINDS, LATER_FACTS_SCHEMA, DeriveError, DeriveState, derive_tick, frames
from cli.vintage.fetch import Clock, SystemClock
from cli.vintage.sources import LinkAcknowledgment
from cli.vintage.storage import AFTER_RENAME, create_exclusive, fsync_dir, publish_table_dir, refuse_table_root

FRAME_HASH_VERSION = 1
STAGING_SUBDIR = "staging"
GENERATION_JSON = "generation.json"
PART_JSON = "part.json"
HEAD_JSON = "head.json"
VERSIONS_FILE = "versions.parquet"
COVERAGE_FILE = "coverage.parquet"
_GENESIS_PARTS = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ISO = "%Y-%m-%dT%H:%M:%S.%fZ"
_HEAD_KEYS = frozenset(
    {
        "entries_sha256",
        "generation",
        "hash_version",
        "part",
        "part_json_sha256",
        "parts_sha256",
        "position",
        "prev",
        "prev_tick",
        "rows",
        "tick",
        "tick_json_sha256",
    }
)

log = get_logger("vintage.table")


class TableError(Exception):
    """A head, `part.json` or frame of the table that does not hash to what the chain records; `tick` names it."""

    def __init__(self, tick: str | None, message: str) -> None:
        super().__init__(message)
        self.tick = tick


@dataclass
class TableRead:
    head: dict
    versions: pl.DataFrame
    coverage: pl.DataFrame
    later_facts: pl.DataFrame


@dataclass
class DeriveOutcome:
    complete: bool
    head: dict | None
    parts_added: int
    at: str | None
    reason: str | None
    # The sha256 of the head's file bytes as read or written; None with no head.
    head_sha256: str | None = None
    # Whether the run listed the generation's heads, so `head` is the table's head, or None for an empty table.
    read: bool = False


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_iso(moment: datetime) -> str:
    """The instant as UTC with microseconds and `Z`; a naive datetime names no instant, so it is refused."""
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"a naive datetime names no instant: {moment.isoformat()}")
    return moment.astimezone(UTC).strftime(_ISO)


def _render_v1(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, datetime):
        return '"' + _utc_iso(value) + '"'
    if isinstance(value, date):
        return '"' + value.isoformat() + '"'
    if isinstance(value, str):
        return json.dumps(value)
    raise TypeError(f"no frame-hash rendering for {type(value).__name__}")


# Every version stays: a head names the one its frames were hashed with, and is read with that one.
_RENDERINGS = {1: _render_v1}


def frame_hash(df: pl.DataFrame, version: int) -> str:
    """The sha256 of the frame's lines: its column names, then one rendered row a line."""
    render = _RENDERINGS.get(version)
    if render is None:
        raise ValueError(f"no frame hash version {version}")
    digest = hashlib.sha256((json.dumps(df.columns) + "\n").encode())
    for row in df.iter_rows():
        digest.update(("[" + ",".join(render(value) for value in row) + "]\n").encode())
    return digest.hexdigest()


def generation_dir(table_root: Path, generation: int) -> Path:
    return table_root / f"gen-{generation}"


def _dated(root: Path, stamp: str) -> Path:
    return root / stamp[:4] / stamp[4:6] / stamp[6:8] / stamp


def _part_path(stamp: str) -> str:
    return f"parts/{stamp[:4]}/{stamp[4:6]}/{stamp[6:8]}/{stamp}"


def _head_path(gen_dir: Path, stamp: str) -> Path:
    return _dated(gen_dir / "heads", stamp) / HEAD_JSON


def _staging_name(prefix: str, run_second: int, suffix: str = "") -> str:
    return f"{prefix}.{run_second}.{secrets.token_hex(4)}{suffix}"


def _entries_list(entries: tuple[LinkAcknowledgment, ...]) -> list[list[str]]:
    return [[entry.successor, entry.recorded_prev_sha256, entry.witnessed_sha256] for entry in entries]


def write_part(staging: Path, name: str, versions: pl.DataFrame, coverage: pl.DataFrame, part: dict) -> Path:
    """The part's directory staged under `staging`, created exclusive, its frames first and `part.json` last."""
    staged = staging / name
    os.mkdir(staged, 0o755)
    for file, frame in ((VERSIONS_FILE, versions), (COVERAGE_FILE, coverage)):
        buffer = io.BytesIO()
        frame.write_parquet(buffer)
        create_exclusive(staged / file, buffer.getvalue())
    create_exclusive(staged / PART_JSON, canonical(part))
    fsync_dir(staged)
    return staged


def _read_bytes(path: Path, tick: str | None) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise TableError(tick, f"{path} unreadable: {type(exc).__name__}") from exc


def _loads(data: bytes, path: Path, tick: str | None) -> dict:
    try:
        value = json.loads(data)
    except ValueError as exc:
        raise TableError(tick, f"{path} does not parse") from exc
    if not isinstance(value, dict):
        raise TableError(tick, f"{path} is not an object")
    return value


def _listed_heads(gen_dir: Path) -> list[Path]:
    return sorted((gen_dir / "heads").glob(f"*/*/*/*/{HEAD_JSON}"))


def _checked_head(raw: bytes, path: Path) -> dict:
    """The head the bytes hold, refused unless they are a head's keys and its own canonical line."""
    tick = path.parent.name
    entry = _loads(raw, path, tick)
    if set(entry) != _HEAD_KEYS:
        raise TableError(tick, f"head {path} does not hold a head's keys")
    if canonical(entry) != raw:
        raise TableError(tick, f"head {path} is not its own canonical line")
    return entry


def _current(gen_dir: Path) -> tuple[Path, bytes, dict] | None:
    """The generation's head at the highest chain position, which a published clock regression cannot displace."""
    found = []
    for path in _listed_heads(gen_dir):
        raw = _read_bytes(path, path.parent.name)
        found.append((path, raw, _checked_head(raw, path)))
    if not found:
        return None
    return max(found, key=lambda item: item[2]["position"])


def head(table_root: Path, generation: int) -> dict | None:
    current = _current(generation_dir(table_root, generation))
    return None if current is None else current[2]


def _resolve(gen_dir: Path, named: str | Path) -> Path:
    if isinstance(named, str) and _SHA256.fullmatch(named):
        for path in _listed_heads(gen_dir):
            if _sha256(_read_bytes(path, path.parent.name)) == named:
                return path
        raise TableError(None, f"no head in {gen_dir} hashes to {named}")
    if isinstance(named, str) and STAMP_RE.fullmatch(named):
        return _head_path(gen_dir, named)
    path = Path(named)
    return path if path.is_absolute() else gen_dir / path


@dataclass
class _Part:
    raw: bytes
    part: dict
    versions: pl.DataFrame
    coverage: pl.DataFrame


def _load_part(part_dir: Path) -> _Part:
    tick = part_dir.name
    raw = _read_bytes(part_dir / PART_JSON, tick)
    try:
        versions = pl.read_parquet(part_dir / VERSIONS_FILE)
        coverage = pl.read_parquet(part_dir / COVERAGE_FILE)
    except (OSError, pl.exceptions.PolarsError) as exc:
        raise TableError(tick, f"a frame of {part_dir} unreadable: {type(exc).__name__}") from exc
    return _Part(raw, _loads(raw, part_dir / PART_JSON, tick), versions, coverage)


def _head_chain(gen_dir: Path, head_path: Path) -> list[dict]:
    """The heads from genesis to the one at `head_path`, each predecessor's bytes checked against its successor's
    `prev`, found by its `prev_tick`."""
    newest = _checked_head(_read_bytes(head_path, head_path.parent.name), head_path)
    walked = [newest]
    entry = newest
    while entry["prev_tick"] is not None:
        prev_path = _head_path(gen_dir, entry["prev_tick"])
        prev_raw = _read_bytes(prev_path, entry["prev_tick"])
        if _sha256(prev_raw) != entry["prev"]:
            raise TableError(entry["prev_tick"], f"head {prev_path} does not hash to the prev its successor records")
        entry = _checked_head(prev_raw, prev_path)
        walked.append(entry)
    if entry["prev"] is not None:
        raise TableError(entry["tick"], "the genesis head names a prev")
    return walked[::-1]


def _check_part(entry: dict, loaded: _Part, parts_sha256: str, entries_sha256: str, generation: int) -> str:
    """The `parts_sha256` through this head, once its part and frames hash to what the head and `part.json` record."""
    tick = entry["tick"]
    if (entry["generation"], entry["entries_sha256"]) != (generation, entries_sha256):
        raise TableError(tick, "the head names another generation or other entries than its generation.json")
    if _sha256(loaded.raw) != entry["part_json_sha256"]:
        raise TableError(tick, "part.json does not hash to its head's part_json_sha256")
    through = _sha256((parts_sha256 + entry["part_json_sha256"]).encode("ascii"))
    if through != entry["parts_sha256"]:
        raise TableError(tick, "parts_sha256 does not chain to the head's")
    part = loaded.part
    if (part["tick"], part["position"], part["tick_json_sha256"]) != (tick, entry["position"], entry["tick_json_sha256"]):
        raise TableError(tick, "part.json names another tick than its head")
    _check_frames(tick, loaded, entry["hash_version"])
    return through


def _check_frames(tick: str, loaded: _Part, version: int) -> None:
    for name, frame in (("versions", loaded.versions), ("coverage", loaded.coverage)):
        recorded = loaded.part["frames"][name]
        if frame.height != recorded["rows"] or frame_hash(frame, version) != recorded["hash"]:
            raise TableError(tick, f"the {name} frame does not hash to its part.json")


def _facts(part: dict) -> list[dict]:
    return [
        {
            "tick": fact["tick"],
            "fact": fact["fact"],
            "taught_by": part["tick"],
            "taught_position": part["position"],
            "taught_at": datetime.strptime(fact["taught_at"], _ISO).replace(tzinfo=UTC),
        }
        for fact in part["later_facts"]
    ]


def _read_through(gen_dir: Path, head_path: Path, generation: int) -> tuple[TableRead, list[dict]]:
    """The table through the head, and the heads from genesis to it."""
    opened = _loads(_read_bytes(gen_dir / GENERATION_JSON, None), gen_dir / GENERATION_JSON, None)
    entries_sha256 = _sha256(canonical(opened["entries"]))
    heads = _head_chain(gen_dir, head_path)
    loaded = [_load_part(gen_dir / entry["part"]) for entry in heads]
    parts_sha256 = _GENESIS_PARTS
    coverage_rows = 0
    kinds: Counter[str] = Counter()
    for index, entry in enumerate(heads):
        if entry["position"] != index:
            raise TableError(entry["tick"], f"the head's position {entry['position']} is not its place {index} on the head log")
        parts_sha256 = _check_part(entry, loaded[index], parts_sha256, entries_sha256, generation)
        coverage_rows += loaded[index].coverage.height
        kinds.update(loaded[index].versions["kind"].to_list())
        if not kinds.keys() <= set(KINDS):
            raise TableError(
                entry["tick"], f"the versions through the head hold kinds no derive writes: {sorted(kinds.keys() - set(KINDS))}"
            )
        counted = {"coverage": coverage_rows, "versions": {kind: kinds[kind] for kind in KINDS}}
        if entry["rows"] != counted:
            raise TableError(entry["tick"], "the head's rows differ from the counts of the frames through it")
    versions = pl.concat([part.versions for part in loaded], how="vertical")
    coverage = pl.concat([part.coverage for part in loaded], how="vertical")
    later_facts = pl.DataFrame([fact for part in loaded for fact in _facts(part.part)], schema=LATER_FACTS_SCHEMA)
    return TableRead(heads[-1], versions, coverage, later_facts), heads


def read_table(table_root: Path, generation: int, head: str | Path) -> TableRead:
    """The table through a head named by its path within the generation, its tick's stamp or its sha256 alone;
    `TableError` where anything the head commits to does not hash."""
    gen_dir = generation_dir(table_root, generation)
    return _read_through(gen_dir, _resolve(gen_dir, head), generation)[0]


def _seal(table_root: Path) -> None:
    """Every published generation, part and head directory a crash left writable, between its rename and its chmod,
    set to 0555; one it cannot seal is named and passed over."""
    for gen_dir in sorted(table_root.glob("gen-*")):
        for directory in [gen_dir, *sorted(gen_dir.glob("parts/*/*/*/*")), *sorted(gen_dir.glob("heads/*/*/*/*"))]:
            try:
                if stat.S_IMODE(directory.stat().st_mode) & 0o222:
                    os.chmod(directory, 0o555)
            except OSError as exc:
                log.error("vintage derive could not seal a published table dir=%s: %s", directory, type(exc).__name__)


def _name_leftovers(staging: Path) -> None:
    leftovers = " ".join(sorted(entry.name for entry in staging.iterdir())) if staging.is_dir() else ""
    if leftovers:
        log.warning(
            "vintage derive staging holds a dead run's leftovers, never published; read, then delete by hand: %s", leftovers
        )


def _ancestry(ticks: list[TickFile], stamp: str) -> list[TickFile]:
    """The chain that ends at the named tick, genesis first."""
    by_stamp = {tick.stamp: tick for tick in ticks}
    tick = by_stamp.get(stamp)
    if tick is None:
        raise DeriveError(f"the record holds no tick {stamp}")
    walked: list[TickFile] = []
    while tick is not None:
        if tick in walked:
            raise DeriveError(f"a prev cycle through tick={tick.stamp}")
        walked.append(tick)
        if tick.manifest is None:
            raise DeriveError(f"tick.json unreadable tick={tick.stamp}: {tick.error}")
        prev = tick.manifest.get("prev")
        tick = by_stamp.get(prev["tick"]) if isinstance(prev, dict) and isinstance(prev.get("tick"), str) else None
    return walked[::-1]


def _link_refusal(tick: TickFile, predecessor_sha256: str | None, entries: tuple[LinkAcknowledgment, ...]) -> str | None:
    """Why the tick's link to its predecessor does not stand, None when its `prev` records the sha256 the table holds
    for the predecessor, carries the chaining check's error, or is named by one of the generation's entries."""
    prev = tick.manifest.get("prev") if tick.manifest is not None else None
    if prev is None and predecessor_sha256 is None:
        return None
    if not isinstance(prev, dict):
        return "the link names no predecessor"
    if prev.get("error") is not None or prev.get("tick_json_sha256") == predecessor_sha256:
        return None
    for entry in entries:
        named = (entry.successor, entry.recorded_prev_sha256, entry.witnessed_sha256)
        if named == (tick.stamp, prev.get("tick_json_sha256"), predecessor_sha256):
            return None
    return f"the link does not hash: prev records {prev.get('tick_json_sha256')} for {prev.get('tick')}, the table holds {predecessor_sha256}"


def _open_generation(
    gen_dir: Path, staging: Path, generation: int, entries: tuple, opened_by: str, run_second: int, walls: dict
) -> None:
    staged = staging / _staging_name(gen_dir.name, run_second)
    os.mkdir(staged, 0o755)
    opened = {
        "entries": _entries_list(entries),
        "generation": generation,
        "hash_version": FRAME_HASH_VERSION,
        "opened_by": opened_by,
    }
    create_exclusive(staged / GENERATION_JSON, canonical(opened))
    for subdir in ("parts", "heads"):
        os.mkdir(staged / subdir, 0o755)
    fsync_dir(staged)
    publish_table_dir(staged, gen_dir, **walls)


def _not_lock(table_root: Path) -> list[str]:
    if not table_root.exists():
        return []
    return sorted([entry.name for entry in table_root.iterdir() if entry.name != LOCKFILE_NAME])


def _record_order(record_root: Path, through: str | None) -> list[TickFile]:
    scanned = scan(record_root)
    if scanned.unreadable:
        named = " ".join(f"{path} ({reason})" for path, reason in scanned.unreadable)
        raise DeriveError(f"record paths unreadable, the record read as damaged: {named}")
    if through is not None:
        return _ancestry(scanned.ticks, through)
    found = chain(scanned.ticks)
    if found.cycle:
        raise DeriveError("no tick is a head candidate (a prev cycle, or a regression over an unreadable predecessor)")
    return list(found.order)


def _taken_off(heads: list[dict], order: list[TickFile]) -> tuple[str, str] | None:
    """The first tick the table's heads name that is no longer on the chain at its position (a fork), or whose
    `tick.json` no longer hashes to what the table recorded (a moved tick)."""
    for entry in heads:
        position, stamp = entry["position"], entry["tick"]
        on_chain = order[position] if position < len(order) else None
        if on_chain is None or on_chain.stamp != stamp:
            return stamp, f"fork: tick {stamp}, taken at position {position}, has left the record's chain"
        if on_chain.sha256 != entry["tick_json_sha256"]:
            return (
                stamp,
                f"moved tick: tick {stamp}'s tick.json no longer hashes to the {entry['tick_json_sha256']} the table recorded",
            )
    return None


def _part(
    tick: TickFile, position: int, generation: int, versions: pl.DataFrame, coverage: pl.DataFrame, facts: list[dict]
) -> dict:
    return {
        "frames": {
            "coverage": {"hash": frame_hash(coverage, FRAME_HASH_VERSION), "rows": coverage.height},
            "versions": {"hash": frame_hash(versions, FRAME_HASH_VERSION), "rows": versions.height},
        },
        "generation": generation,
        "later_facts": [{"fact": fact["fact"], "taught_at": _utc_iso(fact["taught_at"]), "tick": fact["tick"]} for fact in facts],
        "position": position,
        "tick": tick.stamp,
        "tick_json_sha256": tick.sha256,
    }


def _rows(previous: dict | None, versions: list[dict], coverage: list[dict]) -> dict:
    before = previous["rows"] if previous is not None else {"coverage": 0, "versions": dict.fromkeys(KINDS, 0)}
    counted = Counter(row["kind"] for row in versions)
    return {
        "coverage": before["coverage"] + len(coverage),
        "versions": {kind: before["versions"][kind] + counted[kind] for kind in KINDS},
    }


def _after_rename(exc: OSError) -> str | None:
    """The step that failed after a publishing rename, with the error's class; None for a failure before it."""
    steps = [note.removeprefix(AFTER_RENAME) for note in getattr(exc, "__notes__", ()) if note.startswith(AFTER_RENAME)]
    return f"{steps[0]} ({type(exc).__name__})" if steps else None


def _outcome(
    complete: bool, read: bool, last: dict | None, last_raw: bytes | None, added: int, at: str | None, reason: str | None
) -> DeriveOutcome:
    return DeriveOutcome(complete, last, added, at, reason, None if last_raw is None else _sha256(last_raw), read)


def derive_table(
    record_root: Path,
    table_root: Path,
    *,
    through: str | None = None,
    nas_mount: Path,
    generation: int = DERIVE_GENERATION,
    opened_by: str,
    clock: Clock | None = None,
) -> DeriveOutcome:
    """Every tick on the record's chain after the generation's head, oldest first, one part and one head each; with
    `through`, the chain that ends at that tick, into a table root holding nothing but the lockfile. The run stops at
    the first refusal, every part published before it kept."""
    clock = SystemClock() if clock is None else clock
    run_second = int(clock.now().timestamp())
    refusal = refuse_table_root(table_root, record_root, nas_mount)
    if refusal is not None:
        return DeriveOutcome(False, None, 0, None, f"table root refused: {refusal}")
    if not record_root.is_dir():
        return DeriveOutcome(False, None, 0, None, f"the record root {record_root} is no directory")
    if through is not None and _not_lock(table_root):
        held = " ".join(_not_lock(table_root))
        return DeriveOutcome(False, None, 0, None, f"--through takes a table root holding only {LOCKFILE_NAME}; it holds {held}")
    entries = derive_mod.GENERATION_ENTRIES.get(generation)
    if entries is None:
        return DeriveOutcome(False, None, 0, None, f"no link entries are pinned for generation {generation}")
    walls = {"table_root": table_root, "record_root": record_root, "nas_mount": nas_mount}
    gen_dir = generation_dir(table_root, generation)
    staging = table_root / STAGING_SUBDIR
    last: dict | None = None
    prev_raw: bytes | None = None
    read = False
    added = 0
    at: str | None = None
    try:
        table_root.mkdir(parents=True, exist_ok=True)
        _seal(table_root)
        _name_leftovers(staging)
        if not staging.exists():
            os.mkdir(staging, 0o750)
        if not gen_dir.exists():
            _open_generation(gen_dir, staging, generation, entries, opened_by, run_second, walls)
        current = _current(gen_dir)
        read = True
        if current is not None:
            _, prev_raw, last = current
        opened = _loads(_read_bytes(gen_dir / GENERATION_JSON, None), gen_dir / GENERATION_JSON, None)
        if opened.get("entries") != _entries_list(entries):
            reason = f"{GENERATION_JSON}'s entries differ from those the code pins for generation {generation}"
            return _outcome(False, read, last, prev_raw, 0, None, reason)
        heads: list[dict] = []
        state = DeriveState.empty()
        if current is not None:
            through_head, heads = _read_through(gen_dir, current[0], generation)
            state = DeriveState.from_frames(through_head.versions, through_head.coverage)
        order = _record_order(record_root, through)
        if heads and not order:
            reason = (
                f"the record root {record_root} holds no tick while the table holds {len(heads)} heads, as an unmounted copy does"
            )
            return _outcome(False, read, last, prev_raw, 0, None, reason)
        taken_off = _taken_off(heads, order)
        if taken_off is not None:
            return _outcome(False, read, last, prev_raw, 0, *taken_off)
        entries_sha256 = _sha256(canonical(_entries_list(entries)))
        parts_sha256 = _GENESIS_PARTS if last is None else last["parts_sha256"]
        for position in range(len(heads), len(order)):
            tick = order[position]
            at = tick.stamp
            predecessor_sha256 = None if position == 0 else order[position - 1].sha256
            link = _link_refusal(tick, predecessor_sha256, entries)
            if link is not None:
                return _outcome(False, read, last, prev_raw, added, at, link)
            damage = check_head(tick)
            if damage is not None:
                return _outcome(False, read, last, prev_raw, added, at, f"the tick's files do not re-hash: {damage}")
            regression = position > 0 and tick.stamp <= order[position - 1].stamp
            found = derive_tick(state, tick, position, tick_dir=tick.dir, regression=regression, entries=entries)
            versions, coverage, _ = frames(*found)
            part = _part(tick, position, generation, versions, coverage, found[2])
            part_raw = canonical(part)
            part_dir = _dated(gen_dir / "parts", tick.stamp)
            if part_dir.exists():
                orphan = _load_part(part_dir)
                if orphan.raw != part_raw:
                    reason = "a published part without its head differs from the part derived"
                    return _outcome(False, read, last, prev_raw, added, at, reason)
                _check_frames(at, orphan, FRAME_HASH_VERSION)
            else:
                staged = write_part(staging, _staging_name(tick.stamp, run_second, ".part"), versions, coverage, part)
                publish_table_dir(staged, part_dir, **walls)
            part_sha256 = _sha256(part_raw)
            parts_sha256 = _sha256((parts_sha256 + part_sha256).encode("ascii"))
            entry = {
                "entries_sha256": entries_sha256,
                "generation": generation,
                "hash_version": FRAME_HASH_VERSION,
                "part": _part_path(tick.stamp),
                "part_json_sha256": part_sha256,
                "parts_sha256": parts_sha256,
                "position": position,
                "prev": None if prev_raw is None else _sha256(prev_raw),
                "prev_tick": None if last is None else last["tick"],
                "rows": _rows(last, found[0], found[1]),
                "tick": tick.stamp,
                "tick_json_sha256": tick.sha256,
            }
            head_raw = canonical(entry)
            staged = staging / _staging_name(tick.stamp, run_second, ".head")
            os.mkdir(staged, 0o755)
            create_exclusive(staged / HEAD_JSON, head_raw)
            fsync_dir(staged)
            try:
                publish_table_dir(staged, _dated(gen_dir / "heads", tick.stamp), **walls)
            except OSError as exc:
                failed = _after_rename(exc)
                if failed is None:
                    raise
                prev_raw, last = head_raw, entry
                added += 1
                return _outcome(False, read, last, prev_raw, added, at, f"the head was published, then {failed} failed")
            prev_raw, last = head_raw, entry
            added += 1
    except TableError as exc:
        return _outcome(False, read, last, prev_raw, added, exc.tick, str(exc))
    except Exception as exc:
        return _outcome(False, read, last, prev_raw, added, at, f"{type(exc).__name__}: {exc}")
    return _outcome(True, read, last, prev_raw, added, None, None)
