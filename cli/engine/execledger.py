from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.execgate import GateVerdict

EXEC_SCHEMA_VERSION = 2
# The journal's `_LOADABLE_SCHEMA_VERSIONS` pattern (cli/engine/journal.py): both schema_version 1
# (submitted == [], no `plans` key -- written by code that could not submit) and 2 (`plans` key
# present) load; validate_exec_record checks each in its own exact shape, never normalizing one
# into the other.
_LOADABLE_EXEC_SCHEMA_VERSIONS = frozenset({1, 2})

# Deliberately NOT `cycle-<HH>.json` and NOT a `failed-cycle-*` sidecar. The Stage-6a streak is
# scored off those two names, and a refusal to trade is not a broken research day -- the cycle
# computed its targets correctly and simply was not permitted to act. Keeping execution outcomes
# in a separate file with a separate prefix makes that structural rather than a matter of care.
_PREFIX = "exec"

_V1_KEYS = frozenset({"schema_version", "cycle_ts", "evaluated_at", "level", "reasons", "inputs", "submitted"})
_V2_KEYS = _V1_KEYS | {"plans"}
_ROW_KEYS = frozenset({"plan_id", "intent_index", "client_order_id", "intent", "order", "state", "filled_qty", "events"})
_PLAN_ENTRY_KEYS = frozenset({"plan_id", "received_at", "disposition", "reasons", "plan", "intents"})

_ROW_STATES = frozenset({"submitting", "accepted", "rejected", "venue_canceled", "canceled", "filled", "ambiguous"})
# A resting order that could still change state on its own (venue fill/cancel) or that this
# process could still act on -- the re-attach input for D10's reconciliation-on-restart.
_OPEN_ORDER_STATES = frozenset({"submitting", "accepted"})


def exec_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def _key_error(what: str, actual: object, expected: frozenset) -> EngineJournalError:
    got = sorted(actual.keys()) if isinstance(actual, dict) else actual
    return EngineJournalError(f"{what} keys {got!r} != expected {sorted(expected)}")


def validate_exec_record(doc: dict) -> None:
    """Raise EngineJournalError on any version-shape disagreement, mirroring
    `cli.engine.journal.validate_record`'s schema-aware, refuse-don't-normalize message style:
    unknown schema_version; a doc whose key set doesn't match its schema's exact set exactly (this
    alone rejects both "v1 with a `plans` key" and "v2 without `plans`"); a v1 record with a
    non-empty `submitted`; a submitted row or plan entry whose key set isn't the exact row/plan-entry
    set; a `submitted`/`plans`/`reasons`/`events` field that isn't a list; or a row whose `state`
    isn't one of `_ROW_STATES` -- the choke point every mutator's `_store` call routes through, so a
    typo'd state (e.g. "acepted") can never persist and silently drop out of `open_submitted_rows`'
    re-attach set with nothing ever raising."""
    schema_version = doc.get("schema_version") if isinstance(doc, dict) else None
    if schema_version not in _LOADABLE_EXEC_SCHEMA_VERSIONS:
        raise EngineJournalError(
            f"unsupported exec schema_version {schema_version!r} (loadable: {sorted(_LOADABLE_EXEC_SCHEMA_VERSIONS)})"
        )
    expected_keys = _V1_KEYS if schema_version == 1 else _V2_KEYS
    actual_keys = frozenset(doc.keys())
    if actual_keys != expected_keys:
        raise _key_error(f"exec record schema_version {schema_version}", doc, expected_keys)

    if not isinstance(doc["reasons"], list):
        raise EngineJournalError(f"exec record 'reasons' must be a list, got {doc['reasons']!r}")
    if not isinstance(doc["submitted"], list):
        raise EngineJournalError(f"exec record 'submitted' must be a list, got {doc['submitted']!r}")
    if schema_version == 1 and doc["submitted"]:
        raise EngineJournalError("schema_version 1 exec record must have an empty 'submitted' list")
    for row in doc["submitted"]:
        if not isinstance(row, dict) or frozenset(row.keys()) != _ROW_KEYS:
            raise _key_error("submitted row", row, _ROW_KEYS)
        if not isinstance(row["events"], list):
            raise EngineJournalError(f"submitted row 'events' must be a list, got {row['events']!r}")
        if row["state"] not in _ROW_STATES:
            raise EngineJournalError(f"submitted row 'state' must be one of {sorted(_ROW_STATES)}, got {row['state']!r}")

    if schema_version == 2:
        if not isinstance(doc["plans"], list):
            raise EngineJournalError(f"exec record 'plans' must be a list, got {doc['plans']!r}")
        for entry in doc["plans"]:
            if not isinstance(entry, dict) or frozenset(entry.keys()) != _PLAN_ENTRY_KEYS:
                raise _key_error("plan entry", entry, _PLAN_ENTRY_KEYS)
            if not isinstance(entry["reasons"], list):
                raise EngineJournalError(f"plan entry 'reasons' must be a list, got {entry['reasons']!r}")


def read_exec_record(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _read_existing(path: Path) -> dict:
    """`read_exec_record`, wrapping a JSON-decode failure into EngineError -- clobbering forensics
    is never the answer, so a caller that hits this never proceeds to overwrite `path`."""
    try:
        return read_exec_record(path)
    except json.JSONDecodeError as exc:
        raise EngineError(f"exec record unreadable: {path}: {exc}") from exc


def _cycle_ts_from_path(path: Path) -> datetime:
    """The inverse of `exec_record_path`: day dir + `-<HH>` suffix -> the boundary datetime (UTC)."""
    day = datetime.strptime(path.parent.name, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    hour = int(path.stem.rsplit("-", 1)[-1])
    return day + timedelta(hours=hour)


def _load_or_new(path: Path, verdict: GateVerdict, evaluated_at: datetime) -> dict:
    """The read half of every mutator's read-modify-write: an absent file builds a fresh v2 record;
    an existing one is validated in its own shape and upgraded to v2, carrying `submitted`/`plans`
    forward untouched (a v1 record has no `plans` -- it upgrades to `plans: []`). Only the verdict
    fields (`level`, `reasons`, `inputs`, `evaluated_at`) come from this call's arguments -- that is
    the whole of merge-never-clobber.

    Single-writer assumption: this read-modify-write plus `_store`'s fixed `.tmp` sibling name carry
    no lock, so two mutators racing on the same `path` can lose one's update. Holds today because
    every mutator call site runs on the node's one event-loop thread (the cycle runs on it
    synchronously; the executor is driven by that same loop's timers/callbacks). If a caller is ever
    added on a different thread or process, this pair needs a real lock, not just this comment.
    """
    cycle_ts = _cycle_ts_from_path(path)
    submitted: list = []
    plans: list = []
    if path.exists():
        existing = _read_existing(path)
        validate_exec_record(existing)
        submitted = list(existing["submitted"])
        plans = list(existing.get("plans", []))
    return {
        "schema_version": EXEC_SCHEMA_VERSION,
        "cycle_ts": cycle_ts.isoformat(),
        "evaluated_at": evaluated_at.isoformat(),
        "level": verdict.level,
        "reasons": list(verdict.reasons),
        "inputs": dict(verdict.inputs),
        "submitted": submitted,
        "plans": plans,
    }


def _store(path: Path, doc: dict) -> Path:
    """Validate then write via `.tmp` sibling + `os.replace` (the `_write_prom_textfile` pattern in
    `cli/engine/command.py`), so a reader never sees a partial record and a mutator can never
    persist a record that would refuse its own next read."""
    validate_exec_record(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    os.replace(tmp_path, path)
    return path


def write_exec_record(journal_dir: Path, cycle_ts: datetime, verdict: GateVerdict, *, evaluated_at: datetime) -> Path:
    path = exec_record_path(journal_dir, cycle_ts)
    doc = _load_or_new(path, verdict, evaluated_at)
    return _store(path, doc)


def append_submitted_row(journal_dir: Path, cycle_ts: datetime, row: dict, *, verdict: GateVerdict, evaluated_at: datetime) -> Path:
    """The write-ahead call: creates the boundary's v2 record from `verdict` when absent, appends
    `row` when present. Raises on any failure -- the caller refuses the submission."""
    path = exec_record_path(journal_dir, cycle_ts)
    doc = _load_or_new(path, verdict, evaluated_at)
    doc["submitted"].append(row)
    return _store(path, doc)


def update_submitted_row(
    journal_dir: Path,
    cycle_ts: datetime,
    client_order_id: str,
    *,
    state: str | None = None,
    event: dict | None = None,
    add_filled_qty: float = 0.0,
) -> None:
    """Appends `event` to the row's `events`, sets `state`, adds to `filled_qty`. Never creates a
    record -- raises EngineError when the record or the row is absent."""
    path = exec_record_path(journal_dir, cycle_ts)
    if not path.exists():
        raise EngineError(f"exec record absent: {path}")
    doc = _read_existing(path)
    validate_exec_record(doc)
    row = next((r for r in doc["submitted"] if r["client_order_id"] == client_order_id), None)
    if row is None:
        raise EngineError(f"{path}: no submitted row for client_order_id={client_order_id!r}")
    if event is not None:
        row["events"].append(event)
    if state is not None:
        row["state"] = state
    row["filled_qty"] = row["filled_qty"] + add_filled_qty
    _store(path, doc)


def append_plan_entry(journal_dir: Path, cycle_ts: datetime, entry: dict, *, verdict: GateVerdict, evaluated_at: datetime) -> Path:
    path = exec_record_path(journal_dir, cycle_ts)
    doc = _load_or_new(path, verdict, evaluated_at)
    doc["plans"].append(entry)
    return _store(path, doc)


def update_plan_intent(
    journal_dir: Path,
    cycle_ts: datetime,
    plan_id: str,
    index: int,
    *,
    outcome: str,
    reasons: tuple[str, ...] = (),
    filled_qty: float = 0.0,
) -> None:
    """Sets `outcome`/`reasons`/`filled_qty` on the `index`-matching element of `plan_id`'s
    `intents`. Never creates a record -- raises EngineError when the record, the plan entry, or the
    intent is absent."""
    path = exec_record_path(journal_dir, cycle_ts)
    if not path.exists():
        raise EngineError(f"exec record absent: {path}")
    doc = _read_existing(path)
    validate_exec_record(doc)
    entry = next((e for e in doc.get("plans", []) if e["plan_id"] == plan_id), None)
    if entry is None:
        raise EngineError(f"{path}: no plan entry for plan_id={plan_id!r}")
    intent = next((i for i in entry["intents"] if i["index"] == index), None)
    if intent is None:
        raise EngineError(f"{path}: plan_id={plan_id!r} has no intent at index={index}")
    intent["outcome"] = outcome
    intent["reasons"] = list(reasons)
    intent["filled_qty"] = filled_qty
    _store(path, doc)


def _day_dirs(journal_dir: Path, now: datetime) -> list[Path]:
    """The current and previous UTC day dirs, in that order."""
    today = now.date()
    return [Path(journal_dir) / d.isoformat() for d in (today, today - timedelta(days=1))]


def _exec_records_in_window(journal_dir: Path, now: datetime) -> list[dict]:
    """Every `exec-*.json` under the current and previous UTC day dirs, each
    validate_exec_record-checked -- a corrupt or unreadable record's raise propagates, refusing the
    whole scan rather than silently skipping it."""
    docs = []
    for day_dir in _day_dirs(journal_dir, now):
        if not day_dir.is_dir():
            continue
        for path in sorted(day_dir.glob(f"{_PREFIX}-*.json")):
            doc = _read_existing(path)
            validate_exec_record(doc)
            docs.append(doc)
    return docs


def ledgered_plan_ids(journal_dir: Path, now: datetime) -> frozenset[str]:
    ids: set[str] = set()
    for doc in _exec_records_in_window(journal_dir, now):
        ids.update(entry["plan_id"] for entry in doc.get("plans", []))
        ids.update(row["plan_id"] for row in doc["submitted"])
    return frozenset(ids)


def ledgered_intent_keys(journal_dir: Path, now: datetime) -> frozenset[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for doc in _exec_records_in_window(journal_dir, now):
        keys.update((row["plan_id"], row["intent_index"]) for row in doc["submitted"])
    return frozenset(keys)


def open_submitted_rows(journal_dir: Path, now: datetime) -> list[tuple[datetime, dict]]:
    out: list[tuple[datetime, dict]] = []
    for doc in _exec_records_in_window(journal_dir, now):
        boundary = datetime.fromisoformat(doc["cycle_ts"])
        out.extend((boundary, row) for row in doc["submitted"] if row["state"] in _OPEN_ORDER_STATES)
    return out
