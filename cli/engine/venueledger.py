from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.engine.errors import EngineJournalError
from cli.engine.venuestate import ConcordanceVerdict, VenueState

# Bumped 1 -> 2 (spec 00094): `state.to_payload()`'s shape changed four ways -- instruments/positions
# keys go base -> symbol, `InstrumentConstraints.symbol` (was `.base`), and the new `costmin_quote`
# field -- so a pre- and post-deploy record are distinguishable on inspection. Read by
# `validate_venue_record` below, which checks a loaded record's actual shape against its OWN
# declared `schema_version`, never against this constant.
VENUE_SCHEMA_VERSION = 2

# The journal's `_LOADABLE_SCHEMA_VERSIONS` pattern (cli/engine/journal.py): both schema_version 1
# (base-keyed instruments/positions, entries carrying "base", no `costmin_quote`) and 2
# (full-symbol keys, entries carrying "symbol" + `costmin_quote`) load; validate_venue_record checks
# each in its own exact shape, never normalizing one into the other. No v1 `venue-<HH>.json` has
# ever existed on the engine host (00089 deployed 2026-08-16 already at schema 2) -- v1 coverage is
# for workstation-side journals only.
_LOADABLE_VENUE_SCHEMA_VERSIONS = frozenset({1, 2})

_V1_INSTRUMENT_KEYS = frozenset({"base", "instrument_id", "ordermin", "costmin", "lot_step", "tick_size", "costmin_source"})
_V2_INSTRUMENT_KEYS = frozenset(
    {"symbol", "instrument_id", "ordermin", "costmin", "costmin_quote", "lot_step", "tick_size", "costmin_source"}
)
_STATE_KEYS = frozenset({"snapshot_at", "instruments", "positions", "balances"})
_CONCORDANCE_KEYS = frozenset({"ok", "failures"})


def _is_symbol_key(key: str) -> bool:
    """True for a full-symbol key ("BTC/EUR"), false for a bare base key ("BTC") -- restated from
    `cli.engine.journal._is_symbol_key` (the '/' separator `cli.engine.store.PAIR_KEYS` and every
    full-symbol consumer already use) so this module stays independent of the journal module."""
    return "/" in key


def _key_error(what: str, actual: object, expected: frozenset) -> EngineJournalError:
    got = sorted(actual.keys()) if isinstance(actual, dict) else actual
    return EngineJournalError(f"{what} keys {got!r} != expected {sorted(expected)}")


def validate_venue_record(doc: dict) -> None:
    """Raise EngineJournalError on any version-shape disagreement, mirroring
    `cli.engine.execledger.validate_exec_record`'s schema-aware, refuse-don't-normalize message
    style (the venue record's sibling): unknown schema_version; a missing `cycle_ts`/`code_version`/
    `status`; a `status == "error"` record missing `error` or carrying `state`/`concordance`; a
    `status == "ok"` record whose `state` or `concordance` key set isn't exactly `_STATE_KEYS`/
    `_CONCORDANCE_KEYS`; a `state.instruments`/`state.positions` key keyed in the wrong direction for
    its schema_version (schema 2 must be full-symbol, schema 1 must be base-only -- reusing
    `cli.engine.journal.validate_record`'s "wrong keying is refused, never silently normalized"
    reasoning); or an instrument entry whose key set isn't exactly `_V1_INSTRUMENT_KEYS`/
    `_V2_INSTRUMENT_KEYS` for its schema_version -- this alone rejects both "v2 with a base key or a
    missing `costmin_quote`" and "v1 with a symbol key or a `costmin_quote` it could never have
    produced"."""
    schema_version = doc.get("schema_version") if isinstance(doc, dict) else None
    if schema_version not in _LOADABLE_VENUE_SCHEMA_VERSIONS:
        raise EngineJournalError(
            f"unsupported venue schema_version {schema_version!r} (loadable: {sorted(_LOADABLE_VENUE_SCHEMA_VERSIONS)})"
        )
    for key in ("cycle_ts", "code_version", "status"):
        if key not in doc:
            raise EngineJournalError(f"venue record missing required key {key!r}")
    # Deliberately no exact-top-level-key-set check (unlike the sibling validate_exec_record): the
    # brief enumerates presence/absence per field rather than one blanket top-level set, so a stray
    # extra top-level key is tolerated here rather than refused.
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


# Same rationale as `execledger.py`'s `_PREFIX`: deliberately not `cycle-<HH>.json` and not a
# `failed-cycle-*` sidecar, so the Stage-6a streak's globs never see this file -- structural, not
# a matter of care (proved in tests/test_engine_execledger.py's two exec pins, parametrized over
# this prefix too).
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
    """`state=None` + `error=...` writes `status: "error"` with the reason and NO `state` key --
    `venue_state_from_cache` raised (venuestate.py docstring) and there is nothing to record but
    why. `state=None` with no `error` is a caller bug, not a degraded record: raises `ValueError`.
    """
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
