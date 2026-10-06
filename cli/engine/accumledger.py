from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path

from cli.engine.errors import EngineJournalError

ACCUM_SCHEMA_VERSION = 1
ACCUM_STATUSES = frozenset({"ok", "no-cycle", "book-unread", "window-closed", "refused"})

# Deliberately not `cycle-<HH>.json` and not a `failed-cycle-*` sidecar: the Stage-6a streak is scored off those two
# names, and what the loop drafted at a boundary, or that it drafted nothing, says nothing of the research cycle's day --
# the same rationale as `execledger.py`'s `_PREFIX`. Every `_journal_artifacts` call in `cli/engine/command.py` names
# its glob, and none names `accum-*`.
_PREFIX = "accum"

_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "cycle_ts",
        "drafted_at",
        "status",
        "nav",
        "eur_total",
        "eur_free",
        "equity_eur",
        "hwm_eur",
        "drawdown_bps",
        "day_loss_bps",
        "day_loss_hold",
        "plan_id",
        "legs",
    }
)
_LEG_KEYS = frozenset(
    {
        "symbol",
        "weight",
        "target_eur",
        "close",
        "held_qty",
        "cache_net",
        "delta_eur",
        "outcome",
        "side",
        "qty",
        "notional_eur",
        "reason",
    }
)

# Each of the record's figures is null where its boundary never reached it, whatever the status; a leg's `qty` is a
# placed or queued sell's and its `notional_eur` a placed or queued buy's, null on any other leg. Every other figure is
# a finite number.
_RECORD_FIGURES = ("nav", "eur_total", "eur_free", "equity_eur", "hwm_eur", "drawdown_bps", "day_loss_bps")
_LEG_FIGURES = ("weight", "target_eur", "close", "held_qty", "cache_net", "delta_eur")
_LEG_NULLABLE_FIGURES = ("qty", "notional_eur")


def accum_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def _key_error(what: str, actual: object, expected: frozenset) -> EngineJournalError:
    got = sorted(actual.keys()) if isinstance(actual, dict) else actual
    return EngineJournalError(f"{what} keys {got!r} != expected {sorted(expected)}")


def _require_figure(what: str, value: object, *, nullable: bool) -> None:
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        allowed = "a finite number or null" if nullable else "a finite number"
        raise EngineJournalError(f"{what} must be {allowed}, got {value!r}")


def validate_accum_record(doc: dict) -> None:
    schema_version = doc.get("schema_version") if isinstance(doc, dict) else None
    if schema_version != ACCUM_SCHEMA_VERSION:
        raise EngineJournalError(f"unsupported accum schema_version {schema_version!r} (expected {ACCUM_SCHEMA_VERSION})")
    if frozenset(doc.keys()) != _RECORD_KEYS:
        raise _key_error("accum record", doc, _RECORD_KEYS)
    if doc["status"] not in ACCUM_STATUSES:
        raise EngineJournalError(f"accum record 'status' must be one of {sorted(ACCUM_STATUSES)}, got {doc['status']!r}")
    if not isinstance(doc["day_loss_hold"], bool):
        raise EngineJournalError(f"accum record 'day_loss_hold' must be a bool, got {doc['day_loss_hold']!r}")
    for field in _RECORD_FIGURES:
        _require_figure(f"accum record {field!r}", doc[field], nullable=True)
    if not isinstance(doc["legs"], list):
        raise EngineJournalError(f"accum record 'legs' must be a list, got {type(doc['legs']).__name__}")
    for leg in doc["legs"]:
        if not isinstance(leg, dict) or frozenset(leg.keys()) != _LEG_KEYS:
            raise _key_error("accum leg", leg, _LEG_KEYS)
        for field in _LEG_FIGURES:
            _require_figure(f"accum leg {leg['symbol']!r} {field!r}", leg[field], nullable=False)
        for field in _LEG_NULLABLE_FIGURES:
            _require_figure(f"accum leg {leg['symbol']!r} {field!r}", leg[field], nullable=True)


def write_accum_record(journal_dir: Path, cycle_ts: datetime, doc: dict) -> Path:
    """Validates first, so a malformed record never lands, then replaces the boundary's record whole -- nothing is
    merged -- through a tmp sibling renamed over it, so a reader never sees a partial one."""
    validate_accum_record(doc)
    path = accum_record_path(journal_dir, cycle_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    os.replace(tmp_path, path)
    return path


def read_accum_record(path: Path) -> dict:
    """The record as stored, unvalidated; a file that is not JSON raises EngineJournalError naming it."""
    try:
        return json.loads(Path(path).read_text())
    except json.JSONDecodeError as exc:
        raise EngineJournalError(f"accum record unreadable: {path}: {exc}") from exc


def _day_dirs(journal_dir: Path, since: datetime) -> list[Path]:
    """The day dirs dated `since`'s date or later, oldest first; a name that does not parse as `%Y-%m-%d` is skipped,
    this engine writing only that form."""
    root = Path(journal_dir)
    if not root.is_dir():
        return []
    out = []
    for path in root.iterdir():
        try:
            day = datetime.strptime(path.name, "%Y-%m-%d").date()
        except ValueError:
            continue
        if path.is_dir() and day >= since.date():
            out.append(path)
    return sorted(out)


def accum_records_since(journal_dir: Path, since: datetime, until: datetime) -> list[dict]:
    """The records with `since <= cycle_ts <= until`, oldest first. Both bounds are UTC instants: `since`'s date names
    the first day dir walked, and a record earlier on that day is out. Every record in a walked day dir is read and
    validated, in the window or not, and one that will not raises -- the scan refuses rather than reading past it."""
    found: list[tuple[datetime, dict]] = []
    for day_dir in _day_dirs(journal_dir, since):
        for path in sorted(day_dir.glob(f"{_PREFIX}-*.json")):
            doc = read_accum_record(path)
            validate_accum_record(doc)
            cycle_ts = datetime.fromisoformat(doc["cycle_ts"])
            if since <= cycle_ts <= until:
                found.append((cycle_ts, doc))
    return [doc for _, doc in sorted(found, key=lambda pair: pair[0])]
