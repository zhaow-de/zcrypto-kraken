from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.engine.errors import EngineJournalError
from cli.engine.venuestate import ConcordanceVerdict, VenueState

# The version `write_venue_record` stamps (spec 00094's full-symbol shape); a loaded record is
# validated against its OWN declared `schema_version`, never against this constant.
VENUE_SCHEMA_VERSION = 2

# Both versions load; `validate_venue_record` checks each in its own exact shape, never normalizing
# one into the other -- the journal's `_LOADABLE_SCHEMA_VERSIONS` pattern (cli/engine/journal.py).
_LOADABLE_VENUE_SCHEMA_VERSIONS = frozenset({1, 2})

_V1_INSTRUMENT_KEYS = frozenset({"base", "instrument_id", "ordermin", "costmin", "lot_step", "tick_size", "costmin_source"})
_V2_INSTRUMENT_KEYS = frozenset(
    {"symbol", "instrument_id", "ordermin", "costmin", "costmin_quote", "lot_step", "tick_size", "costmin_source"}
)
_STATE_KEYS = frozenset({"snapshot_at", "instruments", "positions", "balances"})
_CONCORDANCE_KEYS = frozenset({"ok", "failures"})


def _is_symbol_key(key: str) -> bool:
    """True for a full-symbol key ("BTC/EUR"), false for a bare base key ("BTC") -- restated from
    `cli.engine.journal._is_symbol_key` so this module stays independent of the journal module."""
    return "/" in key


def _key_error(what: str, actual: object, expected: frozenset) -> EngineJournalError:
    got = sorted(actual.keys()) if isinstance(actual, dict) else actual
    return EngineJournalError(f"{what} keys {got!r} != expected {sorted(expected)}")


def validate_venue_record(doc: dict) -> None:
    """Raise EngineJournalError when a record's `schema_version` or `status` is unrecognized, a
    required key missing or a forbidden one present, or a key set or its symbol-vs-base keying
    disagrees with the version the record itself declares -- refused, never silently normalized."""
    schema_version = doc.get("schema_version") if isinstance(doc, dict) else None
    if schema_version not in _LOADABLE_VENUE_SCHEMA_VERSIONS:
        raise EngineJournalError(
            f"unsupported venue schema_version {schema_version!r} (loadable: {sorted(_LOADABLE_VENUE_SCHEMA_VERSIONS)})"
        )
    for key in ("cycle_ts", "code_version", "status"):
        if key not in doc:
            raise EngineJournalError(f"venue record missing required key {key!r}")
    # Deliberately no exact top-level key-set check, unlike the sibling `validate_exec_record`: a
    # stray extra top-level key is tolerated here, not refused.
    status = doc["status"]
    if status == "error":
        if "error" not in doc:
            raise EngineJournalError("venue record status 'error' requires an 'error' key")
        if "state" in doc or "concordance" in doc:
            raise EngineJournalError("venue record status 'error' must not carry a 'state' or 'concordance' key")
        return
    if status != "ok":
        raise EngineJournalError(f"venue record 'status' must be 'ok' or 'error', got {status!r}")

    state = doc.get("state")
    if not isinstance(state, dict) or frozenset(state.keys()) != _STATE_KEYS:
        raise _key_error("venue record 'state'", state, _STATE_KEYS)
    concordance = doc.get("concordance")
    if not isinstance(concordance, dict) or frozenset(concordance.keys()) != _CONCORDANCE_KEYS:
        raise _key_error("venue record 'concordance'", concordance, _CONCORDANCE_KEYS)

    for field_name in ("instruments", "positions"):
        mapping = state[field_name]
        if not isinstance(mapping, dict):
            raise EngineJournalError(f"venue record state[{field_name!r}] must be a dict, got {mapping!r}")
        for key in mapping:
            if schema_version == 2 and not _is_symbol_key(key):
                raise EngineJournalError(
                    f"schema_version 2 state[{field_name!r}] key must be a full symbol (BASE/QUOTE), got {key!r}"
                )
            if schema_version == 1 and _is_symbol_key(key):
                raise EngineJournalError(f"schema_version 1 state[{field_name!r}] key must be a base key (no '/'), got {key!r}")

    instrument_keys = _V2_INSTRUMENT_KEYS if schema_version == 2 else _V1_INSTRUMENT_KEYS
    for symbol, entry in state["instruments"].items():
        if not isinstance(entry, dict) or frozenset(entry.keys()) != instrument_keys:
            raise _key_error(f"instrument entry {symbol!r}", entry, instrument_keys)


# Deliberately not `cycle-<HH>.json` and not a `failed-cycle-*` sidecar, so the Stage-6a streak's
# globs never see this file -- same rationale as `execledger.py`'s `_PREFIX`.
_PREFIX = "venue"


def venue_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def write_venue_record(
    journal_dir: Path,
    cycle_ts: datetime,
    *,
    state: VenueState | None,
    concordance: ConcordanceVerdict | None,
    code_version: str,
    error: str | None = None,
) -> Path:
    """Write the cycle's venue record; `state=None` requires `error` and writes `status: "error"`
    with no `state` key -- there is nothing to record but why -- while `state=None` without
    `error` is a caller bug and raises `ValueError`."""
    if state is None and error is None:
        raise ValueError("write_venue_record: state=None requires error to be set")
    path = venue_record_path(journal_dir, cycle_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": VENUE_SCHEMA_VERSION,
        "cycle_ts": cycle_ts.isoformat(),
        "code_version": code_version,
        "status": "error" if state is None else "ok",
    }
    if state is None:
        doc["error"] = error
    else:
        doc["state"] = state.to_payload()
        doc["concordance"] = {"ok": concordance.ok, "failures": list(concordance.failures)}
    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return path


def read_venue_record(path: Path) -> dict:
    return json.loads(Path(path).read_text())
